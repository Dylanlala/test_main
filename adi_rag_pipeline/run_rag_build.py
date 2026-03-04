#!/usr/bin/env python3
"""
Stage 2 一键执行：从 solutions + enriched_products 构建 RAG 文档 -> 建 FAISS 索引
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adi_rag_pipeline.config import ANALOG_DATA_ROOT, RAG_DOCS_PATH, RAG_INDEX_PATH
from adi_rag_pipeline.stage2_rag.build_docs import run_build_and_save
from adi_rag_pipeline.stage2_rag.build_index import run_build


def main():
    print("Stage 2: 构建 RAG 文档...")
    run_build_and_save(ANALOG_DATA_ROOT, RAG_DOCS_PATH)
    print("Stage 2: 构建 FAISS 索引...")
    run_build(RAG_DOCS_PATH, RAG_INDEX_PATH)
    print("Stage 2 完成。")


if __name__ == "__main__":
    main()
