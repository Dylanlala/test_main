"""
一键构建信号链 RAG：先生成文档列表（build_docs），再建 FAISS 索引（build_index）。
数据根默认 analog_test1，输出到 stage2_rag_build/rag_documents.json 与 rag_index/。
"""
import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from adi_rag_pipeline.config import ANALOG_DATA_ROOT, RAG_BUILD_DOCS_PATH, RAG_BUILD_INDEX_PATH
from adi_rag_pipeline.stage2_rag_build.build_docs import run_build_and_save
from adi_rag_pipeline.stage2_rag_build.build_index import run_build


def main():
    ap = argparse.ArgumentParser(description="一键构建信号链 RAG（文档 + FAISS 索引）")
    ap.add_argument("--data-root", default=ANALOG_DATA_ROOT, help="方案数据根目录")
    ap.add_argument("--docs", default=None, help="文档 JSON 输出路径")
    ap.add_argument("--index", default=None, help="FAISS 索引输出目录")
    ap.add_argument("--docs-only", action="store_true", help="仅生成文档，不建索引")
    ap.add_argument("--index-only", action="store_true", help="仅建索引（需已有 rag_documents.json）")
    args = ap.parse_args()

    docs_path = args.docs or RAG_BUILD_DOCS_PATH
    index_path = args.index or RAG_BUILD_INDEX_PATH

    if not args.index_only:
        print("Step 1: Building RAG documents ...")
        run_build_and_save(data_root=args.data_root, out_path=docs_path)
    if args.docs_only:
        print("Done (docs only).")
        return

    if not args.docs_only:
        print("Step 2: Building FAISS index ...")
        run_build(docs_path=docs_path, index_path=index_path)
    print("Done.")


if __name__ == "__main__":
    main()
