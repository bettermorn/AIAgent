import os
from dotenv import load_dotenv
#from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_pinecone import PineconeVectorStore
from loader import load_and_chunk

from pinecone import Pinecone, ServerlessSpec

load_dotenv("config.env")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv("PINECONE_INDEX", "helpdesk-knowledge")

def main():
    if not PINECONE_API_KEY:
        raise ValueError("PINECONE_API_KEY must be set in your .env file.")




    
    docs = load_and_chunk(data_dir="data")
    print(docs)
    #embeddings = OpenAIEmbeddings(model="text-embedding-3-small", dimensions=512)

    # 使用本地中文 Embedding 模型
    embeddings = HuggingFaceEmbeddings(
        #model_name="BAAI/bge-small-zh-v1.5",
        model_name="./models/AI-ModelScope--bge-small-zh-v1.5/snapshots/master",

        model_kwargs={
            "device": "cpu"
        },
        encode_kwargs={
            "normalize_embeddings": True
        }
    )

    # 根据 Embedding 模型实际输出结果确定维度
    test_vector = embeddings.embed_query("测试文本")
    dimension = len(test_vector)

    print("Embedding dimension:", dimension)

    # 连接 Pinecone
    pc = Pinecone(api_key=PINECONE_API_KEY)

    existing_indexes = [index.name for index in pc.list_indexes()]
    print("Existing indexes:", existing_indexes)

    # 没有 Index 时创建
    if INDEX_NAME not in existing_indexes:
        print(f"Creating Pinecone index: {INDEX_NAME}")

        pc.create_index(
            name=INDEX_NAME,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )

        # 等待 Index 创建完成
        while not pc.describe_index(INDEX_NAME).status["ready"]:
            print("Waiting for Pinecone index to become ready...")
            time.sleep(2)

    # 再次确认 Index 已经存在并可用
    index_info = pc.describe_index(INDEX_NAME)
    print("Index status:", index_info.status)



    texts = [c for c, _ in docs]
    metadatas = [m for _, m in docs]
    vectorstore = PineconeVectorStore.from_texts(
        texts=texts,
        embedding=embeddings,
        index_name=INDEX_NAME,
        pinecone_api_key=PINECONE_API_KEY,
        metadatas=metadatas
    )
    print(f"Ingested {len(texts)} chunks into {INDEX_NAME}")

if __name__ == "__main__":
    main()
