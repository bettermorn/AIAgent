# test_embedding.py

from modelscope import snapshot_download
from langchain_huggingface import HuggingFaceEmbeddings

model_dir = snapshot_download(
    "AI-ModelScope/bge-small-zh-v1.5",
    cache_dir="./models"
)

print("实际模型路径：", model_dir)

embeddings = HuggingFaceEmbeddings(
    model_name=model_dir,
    model_kwargs={
        "device": "cpu"
    },
    encode_kwargs={
        "normalize_embeddings": True
    }
)

vector = embeddings.embed_query("这是一个测试文本")

print("Embedding 加载成功")
print("向量维度：", len(vector))