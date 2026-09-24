"""DeepSeek 大语言模型服务（兼容 OpenAI SDK 协议）"""
import json
import re

from openai import OpenAI

from app import config

_client: OpenAI | None = None


def get_client() -> OpenAI:
    """获取 DeepSeek 客户端（懒加载单例）"""
    global _client
    if _client is None:
        if not config.DEEPSEEK_API_KEY:
            raise RuntimeError(
                "未配置 DEEPSEEK_API_KEY 环境变量。请在 .env 中设置后重启服务。"
            )
        _client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
        )
    return _client


def chat(
    system: str,
    user: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """调用 DeepSeek 对话接口，返回文本"""
    client = get_client()
    resp = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature if temperature is not None else config.DEEPSEEK_TEMPERATURE,
        max_tokens=max_tokens if max_tokens is not None else config.DEEPSEEK_MAX_TOKENS,
    )
    return resp.choices[0].message.content or ""


def chat_json(
    system: str,
    user: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
):
    """调用 DeepSeek 并解析 JSON 输出（自动剥离 markdown 代码块）"""
    raw = chat(system, user, temperature=temperature, max_tokens=max_tokens)
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"[\[{].*[\]}]", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise
