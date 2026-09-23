from openai import OpenAI
from .config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MODEL_NAME

def get_client() -> OpenAI:
    # DeepSeek API 兼容 OpenAI SDK，通过 base_url 指向 DeepSeek 端点
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

def complete_with_citations(system_prompt: str, user_prompt: str) -> str:
    client = get_client()
    resp = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""
