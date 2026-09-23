from dotenv import load_dotenv
import os

load_dotenv("config.env")

# HuggingFace 端点：国内网络默认走镜像 hf-mirror.com，
# 可通过环境变量 HF_ENDPOINT 覆盖（例如 https://huggingface.co）
if "HF_ENDPOINT" not in os.environ:
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-chat")
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
INDEX_DIR = os.path.join(os.path.dirname(__file__), "index")
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
AUDIT_LOG = os.path.join(LOG_DIR, "audit.jsonl")

DISCLAIMER = (
    "本系统仅用于健康信息教育与辅助，不构成医疗诊断或治疗建议；"
    "如出现急症或警示症状，请立即拨打当地急救电话或就医。"
)
