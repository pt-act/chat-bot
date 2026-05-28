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


def get_chunks_by_doc_id(vs: Chroma, doc_id: str) -> dict:
    return vs._collection.get(where={"doc_id": doc_id})


def delete_chunks_by_ids(vs: Chroma, ids: list[str]) -> None:
    if ids:
        vs._collection.delete(ids=ids)