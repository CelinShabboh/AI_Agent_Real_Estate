import uuid
import chromadb
from chromadb.utils import embedding_functions
import os

CHROMA_DATA_PATH = "chroma_data"
client = chromadb.PersistentClient(path=CHROMA_DATA_PATH)

openai_ef = embedding_functions.OpenAIEmbeddingFunction(
    api_key=os.getenv("OPENAI_API_KEY"),
    model_name="text-embedding-3-small" 
)

site_collection = client.get_or_create_collection(name="site_knowledge", embedding_function=openai_ef)
docs_collection = client.get_or_create_collection(name="user_documents", embedding_function=openai_ef)

def add_to_vector_db(text: str, metadata: dict, collection_type="docs"):
    collection = docs_collection if collection_type == "docs" else site_collection

    chunks = [text[i:i+500] for i in range(0, len(text), 500)]
    ids = [str(uuid.uuid4()) for _ in chunks]

    collection.add(
        documents=chunks,
        metadatas=[metadata for _ in chunks],
        ids=ids
    )

def search_vector_db(query: str, conversation_id: int = None, collection_type="docs"):
    collection = docs_collection if collection_type == "docs" else site_collection
    
    where_filter = None
    if conversation_id and collection_type == "docs":
        where_filter = {"conversation_id": conversation_id}
    
    results = collection.query(
        query_texts=[query],
        n_results=3,
        where=where_filter
    )
    
    return "\n".join(results['documents'][0]) if results['documents'] else ""