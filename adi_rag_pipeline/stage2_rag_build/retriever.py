"""
信号链 RAG 检索器：加载 FAISS 索引与文档列表，按 query 返回 top_k 条 chunk（含 text + metadata）。
供上游组装「方案 + 器件组成 + 电路设计 + 器件→型号参考」使用。
"""
import json
import os
import sys
from typing import List, Dict, Any, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from adi_rag_pipeline.config import (
    RAG_BUILD_DOCS_PATH,
    RAG_BUILD_INDEX_PATH,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_CACHE,
)


def get_embedding_model():
    from langchain_community.embeddings import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_NAME,
        cache_folder=EMBEDDING_CACHE,
        model_kwargs={"local_files_only": True},
    )


class SignalChainRAGRetriever:
    """信号链 RAG 检索：query -> top_k chunks (text + metadata)."""

    def __init__(
        self,
        index_path: str = None,
        docs_path: str = None,
        embedding_model=None,
    ):
        self.index_path = index_path or RAG_BUILD_INDEX_PATH
        self.docs_path = docs_path or RAG_BUILD_DOCS_PATH
        self._embedding = embedding_model
        self._vectorstore = None

    def _get_embedding(self):
        if self._embedding is None:
            self._embedding = get_embedding_model()
        return self._embedding

    def _get_vectorstore(self):
        if self._vectorstore is not None:
            return self._vectorstore
        if not os.path.isdir(self.index_path):
            raise FileNotFoundError(f"Index not found: {self.index_path}. Run build_index.py first.")
        from langchain_community.vectorstores import FAISS
        self._vectorstore = FAISS.load_local(self.index_path, self._get_embedding(), allow_dangerous_deserialization=True)
        return self._vectorstore

    def retrieve(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        检索与 query 最相关的 top_k 条 chunk。
        返回列表，每项为 {"text": str, "metadata": dict}，metadata 含 solution_id、chain_id、source、has_csv、csv_files_for_chain 等。
        """
        vs = self._get_vectorstore()
        docs = vs.similarity_search(query, k=top_k)
        return [
            {"text": d.page_content, "metadata": d.metadata}
            for d in docs
        ]

    def retrieve_with_scores(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """检索并返回相似度分数（距离，越小越相似）。"""
        vs = self._get_vectorstore()
        pairs = vs.similarity_search_with_score(query, k=top_k)
        return [
            {"text": d.page_content, "metadata": d.metadata, "score": float(score)}
            for d, score in pairs
        ]


def create_retriever(
    index_path: str = None,
    docs_path: str = None,
    embedding_model=None,
) -> Optional[SignalChainRAGRetriever]:
    """创建检索器；若索引不存在则返回 None。"""
    index_path = index_path or RAG_BUILD_INDEX_PATH
    if not os.path.isdir(index_path) or not os.path.exists(os.path.join(index_path, "index.faiss")):
        return None
    return SignalChainRAGRetriever(index_path=index_path, docs_path=docs_path, embedding_model=embedding_model)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="测试信号链 RAG 检索")
    ap.add_argument("query", nargs="?", default="雷达领域精密SMU/PMU半导体参数测量信号链", help="检索 query")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--index", default=None)
    ap.add_argument("--docs", default=None)
    args = ap.parse_args()
    retriever = create_retriever(args.index, args.docs)
    if not retriever:
        print("Index not found. Run run_build.py first.")
        sys.exit(1)
    results = retriever.retrieve(args.query, top_k=args.top_k)
    print(f"Query: {args.query}\nTop-{args.top_k} results:\n")
    for i, r in enumerate(results, 1):
        meta = r.get("metadata", {})
        print(f"--- {i} --- solution_id={meta.get('solution_id')} source={meta.get('source')} chain_id={meta.get('chain_id')} ---")
        print(r["text"][:400] + "..." if len(r["text"]) > 400 else r["text"])
        print()
