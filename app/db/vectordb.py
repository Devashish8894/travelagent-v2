import chromadb
from chromadb.utils import embedding_functions

class VectorDBManager:
    def __init__(self, persist_path: str = "./chroma_db"):
        self.client = chromadb.PersistentClient(path=persist_path)
        self.embed_fn = embedding_functions.DefaultEmbeddingFunction()

        self.knowledge_col = self.client.get_or_create_collection(
            name="travel_knowledge",
            embedding_function=self.embed_fn
        )

        self.memory_col = self.client.get_or_create_collection(
            name="user_memory",
            embedding_function=self.embed_fn
        )

    def search_knowledge(self, query: str, n_results: int = 2) -> list[str]:
        res = self.knowledge_col.query(query_texts=[query], n_results=n_results)
        return res["documents"][0] if res["documents"] else []

    def add_user_preference(self, user_id: str, preference_text: str):
        pref_id = f"{user_id}_{hash(preference_text)}"
        self.memory_col.upsert(
            documents=[preference_text],
            metadatas=[{"user_id": user_id}],
            ids=[pref_id]
        )

    def get_user_preferences(self, user_id: str, query: str = "travel preference") -> list[str]:
        res = self.memory_col.query(
            query_texts=[query],
            where={"user_id": user_id},
            n_results=3
        )
        return res["documents"][0] if res["documents"] else []

# Global instance accessible for imports:
vector_db = VectorDBManager()