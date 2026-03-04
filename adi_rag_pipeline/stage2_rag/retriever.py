"""
ADI 方案 RAG 检索器：加载 FAISS 索引，按 query 返回 top_k 条文档，可格式化为 expert_cases_text 供 system_gen 使用。
"""
import os
import sys
from typing import List, Dict, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from adi_rag_pipeline.config import RAG_INDEX_PATH, EMBEDDING_MODEL_NAME, EMBEDDING_CACHE


def get_embedding_model():
    from langchain_community.embeddings import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_NAME,
        cache_folder=EMBEDDING_CACHE,
        model_kwargs={"local_files_only": True},
    )


class ADISolutionRetriever:
    def __init__(self, index_path: str = None, embedding_model=None):
        self.index_path = index_path or RAG_INDEX_PATH
        self._store = None
        self._embedding_model = embedding_model

    def _load(self):
        if self._store is not None:
            return
        if not os.path.isdir(self.index_path):
            raise FileNotFoundError(f"FAISS index not found: {self.index_path}")
        from langchain_community.vectorstores import FAISS
        emb = self._embedding_model or get_embedding_model()
        self._store = FAISS.load_local(self.index_path, emb, allow_dangerous_deserialization=True)

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        self._load()
        docs = self._store.similarity_search_with_score(query, k=top_k)
        return [
            {"text": d.page_content, "metadata": d.metadata, "score": float(score)}
            for d, score in docs
        ]

    def format_cases_for_llm(self, cases: List[Dict[str, Any]], max_tokens: int = 2000) -> str:
        parts = []
        total = 0
        for c in cases:
            text = c.get("text", "")
            meta = c.get("metadata", {})
            title = meta.get("title", "")
            url = meta.get("page_url", "")
            block = f"【{title}】\n{text}"
            if url:
                block += f"\n链接：{url}"
            if total + len(block) > max_tokens * 2:  # 粗估字符
                break
            parts.append(block)
            total += len(block)
        return "\n\n---\n\n".join(parts) if parts else ""


def create_adi_retriever(index_path: str = None, embedding_model=None) -> ADISolutionRetriever:
    return ADISolutionRetriever(index_path=index_path, embedding_model=embedding_model)
