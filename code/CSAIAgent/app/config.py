import os
from dotenv import load_dotenv
load_dotenv("config.env")
INDEX_NAME = os.getenv("PINECONE_INDEX","helpdesk-knowledge")
# 每次检索召回的知识块数量，需覆盖知识库中的所有文件
RETRIEVER_K = int(os.getenv("RETRIEVER_K", "12"))

