"""
Summarizer Agent - 摘要生成代理
端口：8002
功能：生成文本摘要

使用 Google A2A SDK (0.3.8) 实现标准的 Agent-to-Agent 协议
使用 DeepSeek (deepseek-v4-flash) 进行智能摘要，配置读取自项目根目录 config.env
"""
from a2a.server.apps import A2AFastAPIApplication
from a2a.types import AgentCard, Message, Part, TextPart, Role, AgentCapabilities, AgentSkill, MessageSendParams
from a2a.server.request_handlers import RequestHandler
import uvicorn
import uuid
import json
from llm_client import get_deepseek_client, DEEPSEEK_MODEL


class SummarizerHandler:
    """摘要生成逻辑处理器"""

    def __init__(self):
        self.client = get_deepseek_client()
        self.model = DEEPSEEK_MODEL

    async def handle_message(self, message: Message) -> Message:
        # 提取用户文本
        user_text = ""
        for part in message.parts:
            if isinstance(part.root, TextPart):
                user_text = part.root.text
                break
        summary = await self._generate_summary(user_text)
        return Message(
            message_id=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=summary))]
        )

    async def _generate_summary(self, text: str) -> str:
        """调用 DeepSeek 模型生成摘要；若超时或失败，降级为本地快速摘要。

        降级策略：
        1. 取首段/首 3~5 句
        2. 提取出现频次较高的关键词（简单分词按中文/英文词切分）
        """
        cleaned = text.strip()
        if not cleaned:
            return "# 摘要\n\n(空输入)"

        # 输入过长先截断，减少外部调用时间
        MAX_INPUT = 4000  # chars
        truncated = cleaned[:MAX_INPUT]

        prompt = f"""请为以下文本生成一个结构化的 Markdown 摘要：
要求：
1. 先给 2-3 句总体概述
2. 用项目符号列出 3-6 个关键要点
3. 给出 5-10 个关键词
4. 保留原文中重要数字或日期

文本（可能已截断至前 {MAX_INPUT} 个字符）：
{truncated}
"""

        try:
            import asyncio
            # 在线程池中执行同步调用，避免阻塞事件循环
            def _call_sync():
                return self.client.chat.completions.create(  # type: ignore
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "你是一个专业的中文技术写作与信息提炼助手。"},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.4,
                    max_tokens=8192,  # 充足的输出空间，避免思考过程耗尽 token 导致摘要截断
                )
            response = await asyncio.to_thread(_call_sync)

            choices = getattr(response, "choices", [])  # type: ignore
            first = choices[0] if choices else None
            content = getattr(getattr(first, "message", None), "content", "") if first else ""
            summary = (content or "").strip()
            if not summary:
                raise ValueError("模型返回空摘要")
            summary += (
                f"\n\n---\n**统计信息**\n- 原文长度: {len(cleaned)}\n"
                f"- 处理长度: {len(truncated)}\n- 摘要长度: {len(summary)}\n- 模型: {self.model}\n"
            )
            return summary
        except Exception as e:  # noqa: BLE001
            print(f"[summarizer] ❌ LLM 调用失败，使用降级摘要: {e}")
            return self._fallback_summary(truncated, original_len=len(cleaned))

    def _fallback_summary(self, text: str, original_len: int) -> str:
        import re
        # 取前 5 句（按句号/换行/中文标点拆分）
        sentences = [s.strip() for s in re.split(r'[。.!?\n]', text) if s.strip()]
        head = sentences[:5]
        head_block = "\n- " + "\n- ".join(head) if head else "(内容过短)"
        # 关键词（简单：按非字母数字中文切分，统计频次）
        tokens = re.split(r'[^0-9A-Za-z\u4e00-\u9fff]+', text)
        freq = {}
        for t in tokens:
            if len(t) < 2:
                continue
            freq[t] = freq.get(t, 0) + 1
        keywords = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:10]
        kw_line = ", ".join(k for k, _ in keywords) if keywords else "无"
        return (
            f"# 简要摘要 (降级)\n\n**原文长度**: {original_len}\n\n**要点**:{head_block}\n\n**关键词**: {kw_line}\n"
        )


class SummarizerRequestHandler(RequestHandler):
    def __init__(self, logic: SummarizerHandler):
        self.logic = logic

    async def on_message_send(self, params: MessageSendParams, context=None):  # type: ignore[override]
        return await self.logic.handle_message(params.message)

    async def on_get_task(self, params, context=None):  # type: ignore[override]
        raise NotImplementedError
    async def on_cancel_task(self, params, context=None):  # type: ignore[override]
        raise NotImplementedError
    async def on_message_send_stream(self, params, context=None):  # type: ignore[override]
        raise NotImplementedError
    async def on_resubscribe_to_task(self, params, context=None):  # type: ignore[override]
        raise NotImplementedError
    async def on_set_task_push_notification_config(self, params, context=None):  # type: ignore[override]
        raise NotImplementedError
    async def on_get_task_push_notification_config(self, params, context=None):  # type: ignore[override]
        raise NotImplementedError
    async def on_list_task_push_notification_config(self, params, context=None):  # type: ignore[override]
        raise NotImplementedError
    async def on_delete_task_push_notification_config(self, params, context=None):  # type: ignore[override]
        raise NotImplementedError


if __name__ == "__main__":
    # 定义 AgentCard
    agent_card = AgentCard(
        name="Summarizer Agent",
        description="生成文本摘要和关键信息提取",
        version="1.0.0",
        url="http://localhost:8002",
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="summarize",
                name="生成摘要",
                description="对长文本生成简洁摘要",
                tags=["summarization", "nlp", "text-processing"],
                examples=[
                    "对以下信息生成摘要：...",
                    "提取关键信息：...",
                    "总结一下这篇文章",
                ],
                input_modes=["text/plain"],
                output_modes=["text/plain"],
            )
        ],
    )

    logic = SummarizerHandler()
    handler = SummarizerRequestHandler(logic)
    app_wrapper = A2AFastAPIApplication(agent_card, handler)
    fastapi_app = app_wrapper.build()
    print("[summarizer] ✅ FastAPI app 构建完成并绑定路由")
    print("🚀 Summarizer Agent 启动: http://localhost:8002")
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8002)
