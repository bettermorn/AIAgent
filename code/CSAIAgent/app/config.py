import os
from dotenv import load_dotenv
load_dotenv("config.env")
INDEX_NAME = os.getenv("PINECONE_INDEX","helpdesk-knowledge")
