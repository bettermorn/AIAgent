"""DeepSeek 大模型封装（OpenAI 兼容接口）。

- 密钥来自 code/config.env 的 DEEPSEEK_API_KEY
- 统一计量 token、记录模型版本（文档 6.7 审计要求）
- JSON 输出：提示词约束 + 容错解析 + 重试（文档 4.6 校验层 1：退回重抽，最多 2 次）
- 流式输出：用于问答首字延迟
"""
from __future__ import annotations

import contextvars
import json
import logging
import re
import threading
import time
from typing import Any, Callable, Iterator, Optional

from openai import OpenAI

from .config import settings

log = logging.getLogger("windom.llm")


class LLMError(RuntimeError):
    pass


class UsageMeter:
    """任务级 token/模型使用累计。

    基于 contextvars：Agent 运行时在任务入口 start()；并行子线程通过 copy_context().run 提交后
    共享同一个累计器，因此可正确汇总到任务的 token 配额与审计记录。
    """

    def __init__(self) -> None:
        self._acc: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar("llm_usage", default=None)
        self._lock = threading.Lock()

    def start(self) -> dict:
        acc = {"tokens": 0, "models": [], "calls": 0}
        self._acc.set(acc)
        return acc

    def add(self, tokens: int, model: str) -> None:
        acc = self._acc.get()
        if acc is None:
            return
        with self._lock:
            acc["tokens"] += tokens
            acc["calls"] += 1
            if model not in acc["models"]:
                acc["models"].append(model)

    def snapshot(self) -> dict:
        acc = self._acc.get()
        if acc is None:
            return {"tokens": 0, "models": [], "calls": 0}
        with self._lock:
            return {"tokens": acc["tokens"], "models": list(acc["models"]), "calls": acc["calls"]}


meter = UsageMeter()
_client: Optional[OpenAI] = None
_client_lock = threading.Lock()


def available() -> bool:
    return bool(settings.deepseek_api_key)


def client() -> OpenAI:
    global _client
    if not settings.deepseek_api_key:
        raise LLMError("未配置 DEEPSEEK_API_KEY（请检查 code/config.env）")
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url,
                                 timeout=settings.llm_timeout, max_retries=0)
    return _client


def _extract_json(text: str) -> Any:
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # 取第一个完整的 {...} 或 [...]
    for open_c, close_c in (("{", "}"), ("[", "]")):
        s = t.find(open_c)
        e = t.rfind(close_c)
        if s != -1 and e > s:
            try:
                return json.loads(t[s:e + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("模型输出不是合法 JSON")


def chat(messages: list[dict], *, model: str | None = None, temperature: float = 0.2,
         max_tokens: int = 2048, json_mode: bool = False) -> str:
    model = model or settings.llm_model
    kw: dict[str, Any] = dict(model=model, messages=messages, temperature=temperature, max_tokens=max_tokens)
    if json_mode:
        kw["response_format"] = {"type": "json_object"}
    last: Exception | None = None
    for attempt in range(settings.llm_retries + 1):
        try:
            resp = client().chat.completions.create(**kw)
            used = getattr(resp, "usage", None)
            meter.add(getattr(used, "total_tokens", 0) or 0, getattr(resp, "model", model) or model)
            content = resp.choices[0].message.content or ""
            if not content.strip():
                raise LLMError("模型返回空内容")
            return content
        except Exception as e:  # 网络/限流/5xx 重试
            last = e
            log.warning("LLM 调用失败(第%d次): %s", attempt + 1, e)
            time.sleep(min(2 ** attempt, 6))
    raise LLMError(f"LLM 调用失败: {last}")


def chat_json(messages: list[dict], *, model: str | None = None, temperature: float = 0.1,
              max_tokens: int = 2048, validator: Callable[[Any], Any] | None = None, retries: int = 2) -> Any:
    """要求模型输出 JSON；解析/校验失败时携带错误信息退回重抽（最多 retries 次）。"""
    msgs = list(messages)
    if not any("JSON" in (m.get("content") or "") or "json" in (m.get("content") or "") for m in msgs):
        msgs.append({"role": "user", "content": "请仅输出一个合法 JSON 对象。"})
    err = None
    for i in range(retries + 1):
        text = chat(msgs, model=model, temperature=temperature, max_tokens=max_tokens, json_mode=True)
        try:
            data = _extract_json(text)
            return validator(data) if validator else data
        except Exception as e:
            err = e
            msgs = msgs + [{"role": "assistant", "content": text},
                           {"role": "user", "content": f"上次输出不符合要求：{e}。请严格按要求重新输出合法 JSON。"}]
    raise LLMError(f"JSON 输出校验失败: {err}")


def stream(messages: list[dict], *, model: str | None = None, temperature: float = 0.3,
           max_tokens: int = 2048) -> Iterator[str]:
    model = model or settings.llm_model
    try:
        resp = client().chat.completions.create(model=model, messages=messages, temperature=temperature,
                                                max_tokens=max_tokens, stream=True,
                                                stream_options={"include_usage": True})
        seen_model = model
        for chunk in resp:
            if getattr(chunk, "usage", None):
                meter.add(chunk.usage.total_tokens or 0, getattr(chunk, "model", seen_model) or seen_model)
            if chunk.choices:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
    except Exception as e:
        raise LLMError(f"LLM 流式调用失败: {e}")
