#!/usr/bin/env python3
"""
Stage 3 一键执行：从 complete_data + enriched_products 构建 Neo4j 知识图谱（不包含 SignalChain）
请先启动 Neo4j 并设置 NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adi_rag_pipeline.config import ANALOG_DATA_ROOT
from adi_rag_pipeline.stage3_kg.build_graph import run_build


def main():
    print("Stage 3: 构建 Neo4j 知识图谱...")
    run_build(ANALOG_DATA_ROOT)
    print("Stage 3 完成。")


if __name__ == "__main__":
    main()
