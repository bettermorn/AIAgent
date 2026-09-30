
from openai import OpenAI
from app.settings import settings

# DeepSeek 兼容 OpenAI SDK：指定 base_url 即可切换到 DeepSeek
client = OpenAI(
    api_key=settings.deepseek_api_key,
    base_url=settings.deepseek_base_url,
)


class DeepSeekLLM:
    def __init__(self, model=None):
        self.model = model or settings.deepseek_model

    def chat(self, prompt: str) -> str:
        if not settings.deepseek_api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY 未配置：请在 config.env 中设置 DEEPSEEK_API_KEY"
            )
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        return resp.choices[0].message.content


def get_llm(model_name=None):
    """默认使用 DEEPSEEK_MODEL（deepseek-chat），可传 deepseek-reasoner 使用推理模型。"""
    return DeepSeekLLM(model_name or settings.deepseek_model)
