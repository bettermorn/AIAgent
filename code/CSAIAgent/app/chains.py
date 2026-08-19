import json
import os
from typing import Any, Dict

from dotenv import load_dotenv

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import (
    RunnableLambda,
    RunnablePassthrough,
)
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore




DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"

INTENT_LABELS = (
    "FAQ",
    "TICKET",
    "COMPLAINT",
    "ESCALATION",
)


INTENT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
你是企业级客服路由器。

请根据用户话语判断用户意图和槽位。

意图只能从以下列表中选择：
{labels}

必须严格输出一个合法的 JSON 对象，不要输出 Markdown，
不要输出 ```json，不要添加额外解释。

JSON 格式如下：
{{
  "intent": "FAQ",
  "slots": {{}}
}}

其中：
- intent 必须是 FAQ、TICKET、COMPLAINT、ESCALATION 之一
- slots 必须是 JSON 对象
""",
        ),
        ("human", "{query}"),
    ]
)


def build_deepseek_llm() -> ChatOpenAI:
    """
    创建 DeepSeek 聊天模型。

    ChatOpenAI 在这里仅作为 OpenAI-compatible API 客户端使用。
    """

    load_dotenv("config.env")
    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        raise RuntimeError(
            "缺少 DEEPSEEK_API_KEY，请在环境变量或 .env 文件中配置。"
        )

    return ChatOpenAI(
        model=DEEPSEEK_MODEL,
        temperature=0,
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL,
    )


def build_intent_chain(
    labels=INTENT_LABELS,
):
    llm = build_deepseek_llm()

    chain = (
        INTENT_PROMPT
        | llm
        | StrOutputParser()
    )

    return chain, labels


def build_rag_chain(index_name: str):
    """
    创建 RAG 链。

    注意：这里的 Embedding 必须和创建 Pinecone 索引时使用的 Embedding
    完全一致。
    """
    #openai_api_key = os.getenv("OPENAI_API_KEY")


    # 使用本地中文 Embedding 模型
    embeddings = HuggingFaceEmbeddings(
        #model_name="BAAI/bge-small-zh-v1.5",
        model_name="./models/AI-ModelScope--bge-small-zh-v1.5/snapshots/master",

        model_kwargs={
            "device": "cpu"
        },
        encode_kwargs={
            "normalize_embeddings": True
        }
    )

    vector_store = PineconeVectorStore.from_existing_index(
        index_name=index_name,
        embedding=embeddings,
    )

    retriever = vector_store.as_retriever(
        search_kwargs={"k": 4}
    )

    rag_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
你是企业 FAQ 助手。

请根据检索结果回答用户问题，并遵守以下规则：

1. 只能根据检索结果回答。
2. 每个关键结论都尽量引用对应出处。
3. 使用 [1]、[2] 这样的编号引用来源。
4. 如果检索结果没有足够依据，请明确说明无法确认。
5. 当无法确认时，建议用户转人工或创建工单。
6. 不要编造不存在的政策、流程、时间或数据。
""",
            ),
            (
                "human",
                "问题：{query}\n\n检索结果：\n{contexts}",
            ),
        ]
    )

    def fetch_context(payload: Dict[str, Any]) -> Dict[str, str]:
        query = payload["query"]

        # 新版 LangChain 推荐使用 retriever.invoke()
        docs = retriever.invoke(query)

        contexts = "\n\n".join(
            [
                (
                    f"[{i + 1}] "
                    f"{doc.page_content[:300]} "
                    f"(source={doc.metadata.get('source')}, "
                    f"chunk={doc.metadata.get('chunk_id')})"
                )
                for i, doc in enumerate(docs)
            ]
        )

        return {
            "query": query,
            "contexts": contexts or "没有检索到相关内容。",
        }

    llm = build_deepseek_llm()

    chain = (
        RunnablePassthrough()
        | RunnableLambda(fetch_context)
        | rag_prompt
        | llm
        | StrOutputParser()
    )

    return chain


def parse_intent_result(intent_text: str, labels) -> tuple[str, Dict[str, Any]]:
    """
    解析 DeepSeek 返回的意图 JSON。

    即使模型偶尔返回非法 JSON，也保证路由流程有默认行为。
    """
    try:
        # 防止模型偶尔返回 ```json ... ```
        cleaned = intent_text.strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```json", "")
            cleaned = cleaned.replace("```", "")
            cleaned = cleaned.strip()

        info = json.loads(cleaned)

        intent = info.get("intent", "FAQ")
        slots = info.get("slots", {})

        if intent not in labels:
            intent = "FAQ"

        if not isinstance(slots, dict):
            slots = {}

        return intent, slots

    except (json.JSONDecodeError, TypeError, AttributeError):
        return "FAQ", {}


def build_router(index_name: str):
    intent_chain, labels = build_intent_chain(
        labels=INTENT_LABELS
    )

    rag_chain = build_rag_chain(index_name)

    def route(payload: Dict[str, Any]) -> Dict[str, Any]:
        query = payload["query"]

        intent_text = intent_chain.invoke(
            {
                "query": query,
                "labels": ", ".join(labels),
            }
        )

        intent, slots = parse_intent_result(
            intent_text,
            labels,
        )

        if intent == "FAQ":
            answer = rag_chain.invoke(
                {
                    "query": query,
                }
            )

            return {
                "intent": intent,
                "slots": slots,
                "answer": answer,
                "actions": [],
            }

        if intent in (
            "TICKET",
            "COMPLAINT",
            "ESCALATION",
        ):
            return {
                "intent": intent,
                "slots": slots,
                "answer": None,
                "actions": [
                    "create_or_update_ticket",
                ],
            }

        # 兜底逻辑
        answer = rag_chain.invoke(
            {
                "query": query,
            }
        )

        return {
            "intent": "FAQ",
            "slots": slots,
            "answer": answer,
            "actions": [],
        }

    return RunnableLambda(route)