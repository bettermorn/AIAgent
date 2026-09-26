# download_embedding_model.py

from modelscope import snapshot_download

model_dir = snapshot_download(
    "AI-ModelScope/bge-small-zh-v1.5",
    cache_dir="./"
)

print("模型目录：", model_dir)