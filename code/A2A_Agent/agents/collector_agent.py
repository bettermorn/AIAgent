"""
Collector Agent - 信息收集代理
端口：8001
功能：
  1. 解析用户请求（主题 + 数量，DeepSeek deepseek-v4-flash）
  2. 调用网络搜索（SerpAPI / Bocha，配置读取自 config.env）
  3. 将搜索结果记录到 PostgreSQL（agents/db.py）
  4. 搜索不可用时降级返回本地 NEWS_DB 静态数据
模型：DeepSeek (deepseek-v4-flash)，从项目根目录 config.env 读取 DEEPSEEK_API_KEY
"""
import asyncio
import uuid
import json
import re
from datetime import datetime

from llm_client import get_deepseek_client, DEEPSEEK_MODEL
import search_service
import db

from a2a.server.apps import A2AFastAPIApplication
from a2a.types import AgentCard, Message, Part, TextPart, DataPart, Role, AgentCapabilities, AgentSkill, MessageSendParams
from a2a.server.request_handlers import RequestHandler
import uvicorn

# 支持的主题（与 Classifier Agent 的 CATEGORIES 保持一致）
AVAILABLE_TOPICS = ["集成电路", "工业软件", "生物医药"]

# 各主题的精准搜索词模板（确保按类别返回正确的信息）
TOPIC_QUERIES = {
    "集成电路": "半导体 集成电路 行业 最新新闻 动态",
    "工业软件": "工业软件 CAD EDA 智能制造 最新新闻 动态",
    "生物医药": "生物医药 创新药 行业 最新新闻 动态",
}

# 降级解析时的主题别名（用户可能使用的相关词汇）
TOPIC_ALIASES = {
    "集成电路": ["集成电路", "半导体", "芯片", "晶圆", "光刻"],
    "工业软件": ["工业软件", "CAD", "CAE", "数字孪生", "智能制造", "MES"],
    "生物医药": ["生物医药", "医药", "创新药", "制药", "疫苗"],
}

NEWS_DB = {
    "集成电路": [
        {"id": 1, "title": "2025年全球半导体销售额达7917亿美元", "content": "半导体行业协会（SIA）宣布，2025年全球半导体销售额达7917亿美元，较2024年的6305亿美元增长25.6%，其中第四季度创历史新高。", "date": "2026-02-06"},
        {"id": 2, "title": "SEMICON China 2026 聚焦AI算力与化合物半导体", "content": "中国电子商会与 SEMI 携手升级展会内涵，聚焦 AI 算力、化合物半导体、先进显示等方向，全产业链覆盖。", "date": "2026-09-22"},
        {"id": 3, "title": "中国集成电路产业系列研究报告发布", "content": "2026年度中国集成电路产业系列研究报告（共六篇）发布，覆盖设计、制造、封测、设备、材料、EDA 全环节。", "date": "2026-09-10"},
    ],
    "工业软件": [
        {"id": 4, "title": "工信部印发《“人工智能+软件”专项行动实施方案》", "content": "工信部发布专项行动实施方案，推动工业软件智能化转型，加快 CAD/CAE/EDA 等研发设计软件的国产化替代。", "date": "2026-09-15"},
        {"id": 5, "title": "工信部：推动工业软件智能化转型", "content": "工信部新闻发布会强调，以数字孪生、智能制造为主攻方向，提升工业软件供给能力，赋能新型工业化。", "date": "2026-09-18"},
        {"id": 8, "title": "“人工智能+软件”专项行动新闻发布会举行", "content": "工信部举行专题发布会，介绍专项行动目标：到2027年建成一批高水平工业软件平台，形成智能化生态体系。", "date": "2026-09-16"},
    ],
    "生物医药": [
        {"id": 6, "title": "今年以来已批准上市创新药59个", "content": "从2026张江药谷大会暨上海国际生物医药产业周获悉，2026年创新药批准上市增长势头不减，今年以来已批准上市创新药59个。", "date": "2026-09-25"},
        {"id": 7, "title": "《医药工业发展“十五五”规划》印发", "content": "工信部、国家发改委等十部门联合印发规划，提出到2030年生物医药研发应用稳居全球前列的目标。", "date": "2026-09-20"},
        {"id": 9, "title": "新版国家基本药物目录发布", "content": "国家卫生健康委等部门联合发布《国家基本药物目录（2026年版）》，自2026年9月1日起施行，创新药纳入数量创新高。", "date": "2026-07-09"},
    ]
}

class CollectorHandler:
    def __init__(self):
        self.client = get_deepseek_client()
        self.model = DEEPSEEK_MODEL
        # 初始化 PostgreSQL（幂等；失败仅告警，不影响服务）
        self.db_ready = db.init_db()
        print(f"[collector] 🗄️ PostgreSQL 就绪: {self.db_ready}")

    async def handle_message(self, message: Message) -> Message:
        # 1. 提取文本
        user_text = ""
        for part in message.parts:
            if isinstance(part.root, TextPart):
                user_text = part.root.text
                break
        print(f"[collector] 📨 收到请求: {user_text!r}")

        # 2. 解析请求（LLM -> fallback）
        topic, max_items = self._parse_request(user_text)
        print(f"[collector] 🔍 解析结果 topic={topic} max_items={max_items}")

        # 3. 按类别构建精准搜索词并执行网络搜索（线程池中执行，避免阻塞事件循环）
        search_query = f"{TOPIC_QUERIES.get(topic, topic + ' 最新新闻')} {datetime.now().year}"
        search_source = "local"
        db_saved = 0
        try:
            results, search_source = await asyncio.to_thread(
                search_service.search, search_query, max_items, TOPIC_ALIASES.get(topic, [topic])
            )
            news_list = [
                {
                    "title": r["title"],
                    "content": r["snippet"],
                    "url": r["url"],
                    "site": r["source"],
                    "date": r["date"] or datetime.now().strftime("%Y-%m-%d"),
                }
                for r in results
            ]
            # 4. 记录到 PostgreSQL
            db_saved = await asyncio.to_thread(
                db.save_results, search_query, topic, search_source, results
            )
            print(f"[collector] 🌐 搜索成功 ({search_source})，入库 {db_saved} 条")
        except Exception as e:  # noqa: BLE001
            # 搜索失败：优先用 PostgreSQL 中该主题的历史搜索结果，再降级本地 NEWS_DB
            print(f"[collector] ⚠️ 网络搜索不可用: {e}")
            history = await asyncio.to_thread(db.recent_results, topic, max_items)
            if history:
                print(f"[collector] 💾 使用 PostgreSQL 历史记录 ({len(history)} 条)")
                search_source = "postgres-history"
                news_list = [
                    {
                        "title": r["title"],
                        "content": r.get("snippet", ""),
                        "url": r.get("url", ""),
                        "site": "",
                        "date": (r.get("created_at") or "")[:10],
                    }
                    for r in history
                ]
            else:
                print("[collector] ⚠️ 历史记录为空，降级本地 NEWS_DB")
                fallback = AVAILABLE_TOPICS[0]  # 默认取第一个可用主题
                news_list = NEWS_DB.get(topic, NEWS_DB.get(fallback, []))[:max_items]

        # 5. 组织输出
        result = {
            "topic": topic,
            "count": len(news_list),
            "search_source": search_source,
            "db_saved": db_saved,
            "news": news_list,
            "timestamp": datetime.now().isoformat()
        }

        text_out = [
            f"收集到 {len(news_list)} 条关于 {topic} 的信息（来源: {search_source}"
            + (f"，已入库 {db_saved} 条" if db_saved else "")
            + "）：",
            "",
        ]
        for i, n in enumerate(news_list, 1):
            text_out.append(f"{i}. {n['title']}\n   {n['content']}\n   日期: {n['date']}\n")
            if n.get("url"):
                text_out.append(f"   链接: {n['url']}\n")
        result_text = "\n".join(text_out)

        # 6. 返回（补：message_id + role=agent）
        return Message(
            message_id=str(uuid.uuid4()),
            role=Role.agent,
            parts=[
                Part(root=TextPart(text=result_text)),
                Part(root=DataPart(data=result))
            ]
        )

    def _parse_request(self, text: str):
        try:
            prompt = f"""解析用户信息收集请求:
可选主题: {', '.join(AVAILABLE_TOPICS)}
用户输入: \"{text}\"
返回 JSON:
{{
  "topic": "主题 (默认 {AVAILABLE_TOPICS[0]})",
  "max_items": 数量 (默认 3 最大 10)
}}"""
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个请求解析器，负责提取主题和数量"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            topic = data.get("topic", AVAILABLE_TOPICS[0])
            if topic not in AVAILABLE_TOPICS:
                topic = AVAILABLE_TOPICS[0]
            max_items = min(int(data.get("max_items", 3)), 10)
            return topic, max_items
        except Exception as e:
            # 降级简单规则
            return self._extract_topic_simple(text), self._extract_count_simple(text)

    def _extract_topic_simple(self, text: str) -> str:
        text_lower = text.lower()
        for topic, aliases in TOPIC_ALIASES.items():
            for alias in aliases:
                if alias.lower() in text_lower:
                    return topic
        return AVAILABLE_TOPICS[0]

    def _extract_count_simple(self, text: str) -> int:
        nums = re.findall(r"\d+", text)
        if nums:
            return min(int(nums[0]), 10)
        return 3

class CollectorRequestHandler(RequestHandler):
    """适配 A2A RequestHandler 接口，将 handle_message 暴露为 on_message_send"""
    def __init__(self, logic: CollectorHandler):
        self.logic = logic

    async def on_message_send(self, params: MessageSendParams, context=None):  # type: ignore[override]
        return await self.logic.handle_message(params.message)

    # 以下为协议要求的接口，当前示例不实现任务管理，统一返回 NotImplemented
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
    agent_card = AgentCard(
        name="Collector Agent",
        description="信息收集智能代理",
        version="1.0.0",
        url="http://localhost:8001",
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain", "application/json"],
        skills=[
            AgentSkill(
                id="collect_news",
                name="收集信息",
                description="根据主题和数量收集信息",
                tags=["news", "collection", "data"],
                examples=[
                    "收集集成电路行业的最新动态",
                    "查找工业软件领域的新闻",
                    "收集生物医药行业的最新信息",
                ],
                input_modes=["text/plain"],
                output_modes=["application/json", "text/plain"],
            )
        ],
    )

    logic = CollectorHandler()
    handler = CollectorRequestHandler(logic)
    app_wrapper = A2AFastAPIApplication(agent_card, handler)
    # 通过 build() 获取真正的 FastAPI 实例
    fastapi_app = app_wrapper.build()
    print("[collector] ✅ FastAPI app 构建完成并绑定路由")
    print("🚀 Collector Agent 启动: http://localhost:8001")
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8001)