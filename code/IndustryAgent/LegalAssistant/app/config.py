"""应用配置：路径与环境变量"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv("config.env")

BASE_DIR = Path(__file__).resolve().parent.parent

# 目录
CORPUS_DIR = BASE_DIR / "ingest" / "corpus"
POLICIES_DIR = BASE_DIR / "policies"
BASELINE_CLAUSES_FILE = BASE_DIR / "standard_clauses" / "baseline_dpa.txt"
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# DeepSeek 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_TEMPERATURE = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.2"))
DEEPSEEK_MAX_TOKENS = int(os.getenv("DEEPSEEK_MAX_TOKENS", "1500"))

# 检索配置（对应 config/retriever.toml）
RETRIEVER_TOP_K = 6
RETRIEVER_CHUNK_SIZE = 700
RETRIEVER_CHUNK_OVERLAP = 100

DISCLAIMER = (
    "本工具不提供法律建议，输出结果仅供参考，必须由合格的法律顾问审查。"
)
