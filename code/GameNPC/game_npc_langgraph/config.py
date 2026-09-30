"""配置加载模块：从项目根目录的 config.env 读取环境变量"""
import os
from pathlib import Path
from dotenv import load_dotenv

# config.env 位于项目根目录（game_npc_langgraph 的上一级）
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.env"
load_dotenv(CONFIG_PATH)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == "sk-xxx":
    print("⚠️  警告：尚未在 config.env 中配置有效的 DEEPSEEK_API_KEY")
