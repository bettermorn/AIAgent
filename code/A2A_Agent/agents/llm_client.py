"""
公共 LLM 客户端工具

统一从项目根目录的 config.env 加载配置，
并创建调用 DeepSeek 模型的 OpenAI 兼容客户端。
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, AsyncOpenAI

# 项目根目录（agents/ 的上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.env"

# 优先加载项目根目录的 config.env，再兜底加载系统环境变量
load_dotenv(CONFIG_PATH)
load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")


def get_deepseek_client() -> OpenAI:
    """创建同步 DeepSeek 客户端（OpenAI 兼容接口）"""
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


def get_async_deepseek_client() -> AsyncOpenAI:
    """创建异步 DeepSeek 客户端（OpenAI 兼容接口）"""
    return AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
