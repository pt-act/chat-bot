from langchain_chroma import Chroma

from config import get_settings
from utils.embedding_adapter import get_embeddings


def get_vectorstore() -> Chroma:
    setting = get_settings()
    return Chroma(
        collection_name=setting.chroma_collection,
        persist_directory=setting.chroma_persist_dir,
        embedding_function=get_embeddings(),
        collection_metadata={"hnsw:space": "cosine"},
    )


def chroma() -> Chroma:
    return get_vectorstore()


class VectorStoreRepository:
    """Thin adapter around ChromaDB to avoid touching private _collection API outside this module."""

    def __init__(self, vs: Chroma) -> None:
        self._vs = vs

    def get_by_doc_id(self, doc_id: str) -> dict:
        return self._vs._collection.get(where={"doc_id": doc_id})

    def delete_by_ids(self, ids: list[str]) -> None:
        if ids:
            self._vs._collection.delete(ids=ids)

    def add_documents(self, docs: list) -> None:
        self._vs.add_documents(docs)

    def similarity_search_with_relevance_scores(self, query: str, k: int = 1):
        return self._vs.similarity_search_with_relevance_scores(query, k=k)

    def max_marginal_relevance_search(self, query: str, k: int = 3, fetch_k: int = 10):
        return self._vs.max_marginal_relevance_search(query, k=k, fetch_k=fetch_k)


def get_vectorstore_repo() -> VectorStoreRepository:
    return VectorStoreRepository(get_vectorstore())


def get_chunks_by_doc_id(vs: Chroma, doc_id: str) -> dict:
    return VectorStoreRepository(vs).get_by_doc_id(doc_id)


def delete_chunks_by_ids(vs: Chroma, ids: list[str]) -> None:
    VectorStoreRepository(vs).delete_by_ids(ids)
