"""DeepSeek 客户端公共模块：统一加载 config.env 并创建 OpenAI 兼容客户端。"""
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# 加载项目根目录下的 config.env
load_dotenv(Path(__file__).resolve().parent.parent / "config.env")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def is_configured():
    return bool(DEEPSEEK_API_KEY) and DEEPSEEK_API_KEY != "your_deepseek_api_key_here"


def get_client():
    """返回 DeepSeek 的 OpenAI 兼容客户端。"""
    if not is_configured():
        raise RuntimeError(
            "DEEPSEEK_API_KEY 未配置，请在项目根目录的 config.env 中填写真实 API Key。"
        )
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


def chat(messages, temperature=0.0, model=None):
    """调用 DeepSeek 模型，返回文本内容。"""
    client = get_client()
    response = client.chat.completions.create(
        model=model or DEEPSEEK_MODEL,
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()
