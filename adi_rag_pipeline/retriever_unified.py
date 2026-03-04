"""
统一检索入口：向量 RAG（ADI 方案）+ 可选 GraphRAG 扩展，返回可注入 system_gen 的 expert_cases_text。
供 server_wb 或 generdatedata 调用。
"""
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adi_rag_pipeline.config import RAG_INDEX_PATH
from adi_rag_pipeline.stage2_rag.retriever import create_adi_retriever, ADISolutionRetriever
from adi_rag_pipeline.stage4_graph_rag.graph_rag import create_graph_rag


class UnifiedADIRetriever:
    def __init__(
        self,
        index_path: str = None,
        embedding_model=None,
        use_graph_rag: bool = True,
        neo4j_uri: str = None,
        neo4j_user: str = None,
        neo4j_password: str = None,
    ):
        self.adi_retriever = create_adi_retriever(index_path=index_path, embedding_model=embedding_model)
        self.use_graph_rag = use_graph_rag
        self.graph_rag = None
        if use_graph_rag:
            try:
                self.graph_rag = create_graph_rag(uri=neo4j_uri, user=neo4j_user, password=neo4j_password)
            except Exception:
                self.graph_rag = None

    def retrieve_for_intention(self, intention: str, top_k: int = 5, max_tokens: int = 2000) -> str:
        """
        根据用户 intention 检索 ADI 方案 + 可选图扩展，返回一段可直接填入 prompt 的 expert_cases_text。
        """
        try:
            cases = self.adi_retriever.retrieve(intention, top_k=top_k)
        except FileNotFoundError:
            return "暂无 ADI 方案参考（请先运行 run_rag_build.py 构建索引）。"
        text = self.adi_retriever.format_cases_for_llm(cases, max_tokens=max_tokens)
        if self.graph_rag and cases:
            try:
                subgraph_text = self.graph_rag.expand_from_rag_metadata(cases, hops=2)
                if subgraph_text:
                    text += "\n\n【知识图谱扩展】\n" + subgraph_text[:1500]
            except Exception:
                pass
        return text or "暂无 ADI 方案参考。"


def create_unified_retriever(
    index_path: str = None,
    embedding_model=None,
    use_graph_rag: bool = True,
) -> UnifiedADIRetriever:
    return UnifiedADIRetriever(
        index_path=index_path or RAG_INDEX_PATH,
        embedding_model=embedding_model,
        use_graph_rag=use_graph_rag,
    )
