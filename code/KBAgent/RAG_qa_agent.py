# -*- coding: utf-8 -*-
"""
LangChain 1.x + DashScope + FAISS RAG FAQ 问答系统
"""

import os
from typing import Any, List, Mapping, Optional

import dashscope
import gradio as gr
from dotenv import load_dotenv

from langchain_community.vectorstores import FAISS

from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import (
    create_stuff_documents_chain
)

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.llms import LLM
from langchain_core.prompts import PromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter


# ============================================================
# 1. 加载环境变量并初始化 DashScope
# ============================================================

# config.env 文件内容示例：
#
# DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx
#
# 也可以直接使用系统环境变量 DASHSCOPE_API_KEY
load_dotenv("config.env")

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")

if not DASHSCOPE_API_KEY:
    raise RuntimeError(
        "未找到 DASHSCOPE_API_KEY，请在 config.env 或系统环境变量中配置。"
    )

dashscope.api_key = DASHSCOPE_API_KEY


# ============================================================
# 2. 自定义 DashScope Embeddings
# ============================================================

class DashScopeEmbeddings(Embeddings):
    """
    使用阿里云 DashScope 文本嵌入模型生成向量。
    """

    def __init__(
        self,
        model_name: str = "text-embedding-v2"
    ):
        self.model_name = model_name

    @staticmethod
    def _get_value(obj: Any, key: str, default: Any = None) -> Any:
        """
        兼容 DashScope 返回 dict 或对象两种形式。
        """
        if isinstance(obj, dict):
            return obj.get(key, default)

        return getattr(obj, key, default)

    def embed_documents(
        self,
        texts: List[str]
    ) -> List[List[float]]:
        """
        为多个文档生成嵌入向量。
        """

        response = dashscope.TextEmbedding.call(
            model=self.model_name,
            input=texts
        )

        status_code = self._get_value(response, "status_code")

        if status_code is not None and status_code != 200:
            message = self._get_value(
                response,
                "message",
                "未知错误"
            )
            raise RuntimeError(
                f"DashScope 嵌入模型调用失败，"
                f"status_code={status_code}，message={message}"
            )

        output = self._get_value(response, "output")

        if output is None:
            message = self._get_value(
                response,
                "message",
                "未知错误"
            )
            raise RuntimeError(
                f"DashScope 嵌入模型调用失败：{message}"
            )

        embeddings = self._get_value(output, "embeddings")

        if not embeddings:
            raise RuntimeError(
                f"DashScope 未返回有效 embeddings，响应内容：{response}"
            )

        result = []

        for item in embeddings:
            embedding = self._get_value(item, "embedding")

            if embedding is None:
                raise RuntimeError(
                    f"嵌入结果中不存在 embedding 字段：{item}"
                )

            result.append(embedding)

        return result

    def embed_query(self, text: str) -> List[float]:
        """
        为查询文本生成嵌入向量。
        """
        return self.embed_documents([text])[0]


# ============================================================
# 3. 自定义 DashScope LLM
# ============================================================

class DashScopeLLM(LLM):
    """
    使用阿里云 DashScope Generation API 的 LangChain LLM 封装。
    """

    model_name: str = "qwen-plus"
    temperature: float = 0.3
    max_tokens: int = 512

    @property
    def _llm_type(self) -> str:
        return "dashscope"

    @staticmethod
    def _get_value(obj: Any, key: str, default: Any = None) -> Any:
        """
        兼容 DashScope 返回 dict 或对象两种形式。
        """
        if isinstance(obj, dict):
            return obj.get(key, default)

        return getattr(obj, key, default)

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any
    ) -> str:
        """
        LangChain 调用 LLM 时会进入这个方法。
        """

        if stop:
            raise ValueError("当前 DashScopeLLM 暂不支持 stop 参数。")

        response = dashscope.Generation.call(
            model=self.model_name,
            prompt=prompt,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            **kwargs
        )

        status_code = self._get_value(response, "status_code")

        if status_code is not None and status_code != 200:
            message = self._get_value(
                response,
                "message",
                "未知错误"
            )
            raise RuntimeError(
                f"DashScope LLM 调用失败，"
                f"status_code={status_code}，message={message}"
            )

        output = self._get_value(response, "output")

        if output is None:
            message = self._get_value(
                response,
                "message",
                "未知错误"
            )
            raise RuntimeError(
                f"DashScope LLM 调用失败：{message}"
            )

        text = self._get_value(output, "text")

        if text is None:
            raise RuntimeError(
                f"DashScope 未返回有效文本，响应内容：{response}"
            )

        return str(text).strip()

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }


# ============================================================
# 4. 准备 FAQ 数据
# ============================================================

faq_data = [
    {
        "question": "公司的工作时间是什么？",
        "answer": "工作日为周一至周五，上午9:00到下午6:00。"
    },
    {
        "question": "如何申请年假？",
        "answer": "通过HR系统提交休假申请，主管审批后生效。"
    },
    {
        "question": "有没有远程办公政策？",
        "answer": "支持混合办公模式，每周可在家工作最多两天。"
    },
    {
        "question": "加班有补贴吗？",
        "answer": "是的，超过晚上8点的加班可申请调休或加班费。"
    }
]


documents = []

for item in faq_data:
    content = (
        f"问题：{item['question']}\n"
        f"答案：{item['answer']}"
    )

    documents.append(
        Document(
            page_content=content,
            metadata={
                "source": "faq",
                "question": item["question"]
            }
        )
    )

print(f"共加载 {len(documents)} 条 FAQ 数据")


# ============================================================
# 5. 文本切分
# ============================================================

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50
)

split_docs = text_splitter.split_documents(documents)

print(f"切分后得到 {len(split_docs)} 个文本块")


# ============================================================
# 6. 创建 FAISS 向量库
# ============================================================

embeddings = DashScopeEmbeddings(
    model_name="text-embedding-v2"
)

db = FAISS.from_documents(
    documents=split_docs,
    embedding=embeddings
)

db.save_local("faiss_index_dashscope")

print("FAISS 向量库已保存到：faiss_index_dashscope")


# ============================================================
# 7. 创建检索器
# ============================================================

retriever = db.as_retriever(
    search_kwargs={
        "k": 2
    }
)


# 测试检索
query = "怎么请假？"

docs = retriever.invoke(query)

print("\n检索结果：")

for i, doc in enumerate(docs, start=1):
    print(f"{i}. {doc.page_content}\n")


# ============================================================
# 8. 初始化 LLM
# ============================================================

llm = DashScopeLLM(
    model_name="qwen-plus",
    temperature=0.3,
    max_tokens=512
)


# ============================================================
# 9. 创建新版 RAG 问答链
# ============================================================

prompt_template = """
你是一个企业 HR 知识库问答助手。

请严格根据下面的上下文回答问题，不要编造信息。

如果上下文中没有足够的信息，请直接回答“不知道”。
回答要简洁、准确。

上下文：
{context}

问题：
{input}

回答：
"""

prompt = PromptTemplate(
    template=prompt_template,
    input_variables=["context", "input"]
)


# 创建文档组合链
document_chain = create_stuff_documents_chain(
    llm=llm,
    prompt=prompt
)


# 创建检索问答链
qa_chain = create_retrieval_chain(
    retriever=retriever,
    combine_docs_chain=document_chain
)


# ============================================================
# 10. 问答函数
# ============================================================

def ask_question(question: str) -> str:
    """
    执行一次知识库问答。
    """

    if not question or not question.strip():
        return "❌ 请输入问题。"

    try:
        result = qa_chain.invoke({
            "input": question.strip()
        })

        answer = result.get(
            "answer",
            "不知道"
        )

        response = f"✅ 回答：{answer}"

        source_documents = result.get(
            "context",
            []
        )

        if source_documents:
            response += "\n\n📎 参考来源：\n"

            for i, doc in enumerate(source_documents, start=1):
                page_content = doc.page_content

                if "答案：" in page_content:
                    source_text = page_content.split(
                        "答案：",
                        1
                    )[-1].strip()
                else:
                    source_text = page_content

                response += f"  [{i}] {source_text}\n"

        return response + "\n" + ("-" * 50)

    except Exception as e:
        return f"❌ 错误：{str(e)}"


# ============================================================
# 11. 测试单轮问答
# ============================================================

print(ask_question("我该怎么申请年假？"))
print(ask_question("上班时间是几点？"))
print(ask_question("可以远程办公吗？"))
print(ask_question("远程办公有什么规定？"))
print(ask_question("那我可以一周在家三天吗？"))


# ============================================================
# 12. 启动 Gradio 界面
# ============================================================

def yes_man(
    query: str,
    history: list
) -> str:
    """
    Gradio ChatInterface 回调函数。
    """
    return ask_question(query)


demo = gr.ChatInterface(
    fn=yes_man,
    chatbot=gr.Chatbot(height=400),
    textbox=gr.Textbox(
        placeholder="请在这里输入你的问题",
        container=False,
        scale=5,
        submit_btn="提交"
    ),
    title="欢迎使用 RAG 问答系统！请问有什么可以帮助您的？",
    description="可以问我关于 HR 方面的问题"
)

demo.launch()