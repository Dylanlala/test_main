"""
GraphRAG：从向量 RAG 返回的 solution_id / product_id 在 Neo4j 中多跳扩展，将子图转为文本供 LLM 参考。
包含 Solution -> Product/Parameter/Category 以及 Solution -> SignalChain（若已写入 signal_chain_descriptions）。
"""
import os
import sys
from typing import List, Dict, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from adi_rag_pipeline.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


def _subgraph_to_text(records: List[Dict]) -> str:
    """将 Neo4j 返回的节点属性列表转为可读文本。"""
    lines = []
    seen = set()
    for rec in records:
        if not isinstance(rec, dict):
            continue
        for k, v in rec.items():
            if v is None:
                continue
            if isinstance(v, str) and v not in seen and len(v) > 5:
                seen.add(v)
                lines.append(f"{k}: {v}")
            elif isinstance(v, (int, float)):
                lines.append(f"{k}: {v}")
    return "\n".join(lines[:80])


class GraphRAG:
    def __init__(self, uri: str = None, user: str = None, password: str = None):
        try:
            from neo4j import GraphDatabase
        except ImportError:
            raise ImportError("请安装 neo4j: pip install neo4j")
        self.uri = uri or NEO4J_URI
        self.user = user or NEO4J_USER
        self.password = password or NEO4J_PASSWORD
        self._driver = None

    def _driver_get(self):
        if self._driver is None:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        return self._driver

    def expand_from_solution_ids(self, solution_ids: List[str], hops: int = 2) -> str:
        """
        从 solution_id 出发扩展 hops 跳（Solution -> Product -> Parameter, Category），返回子图文本。
        """
        if not solution_ids:
            return ""
        driver = self._driver_get()
        ids = list(solution_ids)[:20]
        query = """
        MATCH path = (s:Solution)-[*1..%d]-(n)
        WHERE s.solution_id IN $ids
        WITH collect(DISTINCT n) AS nodes
        UNWIND nodes AS node
        RETURN properties(node) AS p
        """ % hops
        with driver.session() as session:
            result = session.run(query, ids=ids)
            records = [r["p"] for r in result if r.get("p")]
        return _subgraph_to_text(records)

    def expand_from_product_ids(self, product_ids: List[str], hops: int = 2) -> str:
        """从 product_id 出发扩展，返回子图文本。"""
        if not product_ids:
            return ""
        driver = self._driver_get()
        ids = list(product_ids)[:30]
        query = """
        MATCH path = (p:Product)-[*1..%d]-(n)
        WHERE p.product_id IN $ids
        WITH collect(DISTINCT n) AS nodes
        UNWIND nodes AS node
        RETURN properties(node) AS p
        """ % hops
        with driver.session() as session:
            result = session.run(query, ids=ids)
            records = [r["p"] for r in result if r.get("p")]
        return _subgraph_to_text(records)

    def expand_from_rag_metadata(self, rag_results: List[Dict[str, Any]], hops: int = 2) -> str:
        """
        从 stage2 retriever 返回的列表中提取 solution_id，再扩展子图。
        rag_results 每项含 metadata: { solution_id, title, page_url }。
        """
        solution_ids = []
        for r in rag_results:
            meta = r.get("metadata") or {}
            sid = meta.get("solution_id")
            if sid:
                solution_ids.append(sid)
        return self.expand_from_solution_ids(solution_ids, hops=hops)

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None


def create_graph_rag(uri: str = None, user: str = None, password: str = None) -> GraphRAG:
    return GraphRAG(uri=uri, user=user, password=password)
