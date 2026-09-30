"""
Classifier Agent - 分类代理
端口：8004
功能：内容分类

使用 Google A2A SDK (0.3.8) 实现标准的 Agent-to-Agent 协议
使用 DeepSeek (deepseek-v4-flash) 进行智能分类，配置读取自项目根目录 config.env
"""

from a2a.server.apps import A2AFastAPIApplication
from a2a.types import AgentCard, Message, Part, TextPart, DataPart, Role, AgentCapabilities, AgentSkill, MessageSendParams
from a2a.server.request_handlers import RequestHandler
import uvicorn
import os, json, uuid
from llm_client import get_deepseek_client, DEEPSEEK_MODEL

CATEGORIES = {
    #"AI": ["AI", "人工智能", "机器学习", "深度学习", "GPT", "GPT-6", "模型", "OpenAI", "Gemini", "DeepSeek", "Agent", "大模型"],
    #"科技": ["科技", "技术", "iPhone", "量子", "芯片", "骁龙", "2nm", "苹果", "谷歌", "6G", "通信"],
    #"金融": ["金融", "比特币", "美联储", "加息", "利率", "股市", "投资", "美元", "国债"],
    "集成电路": ["集成电路", "半导体", "晶圆", "光刻", "刻蚀", "封装测试", "EDA", "中芯国际", "台积电", "英伟达", "ASML", "存储芯片", "功率器件", "模拟芯片", "先进制程", "chiplet", "氮化镓", "碳化硅", "fab", "foundry"],
    "工业软件": ["工业软件", "CAD", "CAE", "EDA工具", "PLC", "MES", "SCADA", "DCS", "数字孪生", "仿真", "中望软件", "华大九天", "用友", "金蝶", "工业互联网", "智能制造", "MES系统", "研发设计软件", "生产管理软件", "西门子工业"],
    "生物医药": ["生物医药", "创新药", "疫苗", "抗体", "临床试验", "CXO", "CRO", "CDMO", "基因治疗", "细胞治疗", "CAR-T", "mRNA", "FDA", "NMPA", "集采", "医保", "恒瑞医药", "百济神州", "药明康德", "GLP-1", "ADC", "阿尔茨海默", "肿瘤药", "医疗器械"],
}

class ClassifierHandler:
    """分类逻辑处理器"""

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

        category, confidence, scores = self._classify(user_text)

        result_text = self._format_result(category, confidence, scores)

        return Message(
            message_id=str(uuid.uuid4()),
            role=Role.agent,
            parts=[
                Part(root=TextPart(text=result_text)),
                Part(root=DataPart(data={
                    "category": category,
                    "confidence": confidence,
                    "scores": scores
                }))
            ]
        )

    def _classify(self, text: str):
        """调用 DeepSeek 模型分类，失败则降级关键词匹配"""
        try:
            prompt = f"""请对以下文本进行分类，从这些类别中选择一个最合适的：AI、科技、金融、集成电路、工业软件、生物医药、其他

返回 JSON：
{{
  "category": "类别",
  "confidence": 0.9,
  "reasoning": "理由"
}}
文本内容：{text}"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的文本分类助手。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )

            raw_content = response.choices[0].message.content or "{}"
            result = json.loads(raw_content)
            category = result.get("category", "其他")
            confidence = result.get("confidence", 0.0)
            reasoning = result.get("reasoning", "")

            return category, confidence, {"reasoning": reasoning, category: confidence}

        except Exception:
            scores = {}
            for cat, kws in CATEGORIES.items():
                score = sum(1 for kw in kws if kw in text)
                if score > 0:
                    scores[cat] = score
            if scores:
                cat = max(scores.keys(), key=lambda k: scores[k])
                conf = scores[cat] / len(CATEGORIES[cat])
                return cat, conf, scores
            return "其他", 0.0, {}

    def _format_result(self, category, confidence, scores):
        return f"分类结果: {category}, 置信度: {confidence:.2%}\n详情: {scores}"

class ClassifierRequestHandler(RequestHandler):
    def __init__(self, logic: ClassifierHandler):
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
        name="Classifier Agent",
        description="内容分类和标签识别智能代理",
        version="1.0.0",
        url="http://localhost:8004",
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain", "application/json"],
        skills=[
            AgentSkill(
                id="classify",
                name="分类",
                description="对文本内容进行分类",
                tags=["classification", "nlp", "categorization"],
                examples=[
                    "对以下内容分类：...",
                    "识别文本类别：...",
                    "这段文字属于什么主题？",
                ],
                input_modes=["text/plain"],
                output_modes=["text/plain", "application/json"],
            )
        ],
    )

    logic = ClassifierHandler()
    handler = ClassifierRequestHandler(logic)
    app_wrapper = A2AFastAPIApplication(agent_card, handler)
    fastapi_app = app_wrapper.build()
    print("[classifier] ✅ FastAPI app 构建完成并绑定路由")
    print("🚀 Classifier Agent 启动中: http://localhost:8004")
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8004)
