"""
从 adi_rag_documents.json 构建 FAISS 向量索引并持久化。
"""
import json
import os
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from adi_rag_pipeline.config import RAG_DOCS_PATH, RAG_INDEX_PATH, EMBEDDING_MODEL_NAME, EMBEDDING_CACHE


def get_embedding_model():
    from langchain_community.embeddings import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_NAME,
        cache_folder=EMBEDDING_CACHE,
        model_kwargs={"local_files_only": True},
    )


def run_build(docs_path: str = None, index_path: str = None):
    docs_path = docs_path or RAG_DOCS_PATH
    index_path = index_path or RAG_INDEX_PATH
    if not os.path.isfile(docs_path):
        print(f"Documents not found: {docs_path}. Run build_docs.py first.")
        return

    with open(docs_path, "r", encoding="utf-8") as f:
        docs = json.load(f)
    texts = [d["text"] for d in docs]
    metadatas = [d.get("metadata", {}) for d in docs]

    embeddings = get_embedding_model()
    from langchain_community.vectorstores import FAISS
    vectorstore = FAISS.from_texts(texts, embeddings, metadatas=metadatas)
    os.makedirs(os.path.dirname(index_path) or ".", exist_ok=True)
    vectorstore.save_local(index_path)
    print(f"FAISS index saved to {index_path} ({len(texts)} docs)")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default=None)
    ap.add_argument("--index", default=None)
    args = ap.parse_args()
    run_build(args.docs, args.index)
