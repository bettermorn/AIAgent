
from pydantic import BaseModel
import os
from pathlib import Path
from dotenv import load_dotenv

# 优先加载项目根目录下的 config.env
load_dotenv(Path(__file__).resolve().parent.parent / "config.env")


class Settings(BaseModel):
    app_name: str = "Manus+ Demo"
    use_mock_models: bool = True if os.getenv("USE_MOCK", "0") == "1" else False
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    deepseek_model_reasoner: str = os.getenv("DEEPSEEK_MODEL_REASONER", "deepseek-reasoner")


settings = Settings()
