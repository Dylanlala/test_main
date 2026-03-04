"""
从 complete_data.json + enriched_products.json + signal_chain_descriptions.json 构建 Neo4j 图。
"""
import json
import os
import sys
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from adi_rag_pipeline.config import (
    ANALOG_DATA_ROOT,
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
    ENRICHED_PRODUCTS_FILENAME,
    SIGNAL_CHAIN_DESCRIPTIONS_FILENAME,
)
from adi_rag_pipeline.stage3_kg.schema import (
    LABEL_SOLUTION,
    LABEL_PRODUCT,
    LABEL_PARAMETER,
    LABEL_CATEGORY,
    LABEL_SIGNAL_CHAIN,
    REL_CONTAINS,
    REL_HAS_PARAM,
    REL_IN_CATEGORY,
    REL_HAS_SIGNAL_CHAIN,
    SOLUTION_ID,
    SOLUTION_TITLE,
    SOLUTION_PAGE_URL,
    SOLUTION_DESCRIPTION,
    SOLUTION_OVERVIEW,
    SOLUTION_NAV_PATH,
    PRODUCT_ID,
    PRODUCT_MODEL,
    PRODUCT_LINK,
    PRODUCT_DESCRIPTION,
    PARAM_NAME,
    PARAM_VALUE,
    CATEGORY_NAME,
    SIGNAL_CHAIN_ID,
    SIGNAL_CHAIN_NAME,
    SIGNAL_CHAIN_DESCRIPTION,
    SIGNAL_CHAIN_IMAGE_URL,
)


def _sanitize(s: str) -> str:
    if s is None:
        return ""
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def run_build(data_root: str = None):
    try:
        from neo4j import GraphDatabase
    except ImportError:
        raise ImportError("请安装 neo4j: pip install neo4j")

    data_root = data_root or ANALOG_DATA_ROOT
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    def create_constraints(tx):
        tx.run("CREATE CONSTRAINT solution_id IF NOT EXISTS FOR (s:Solution) REQUIRE s.solution_id IS UNIQUE")
        tx.run("CREATE CONSTRAINT product_id IF NOT EXISTS FOR (p:Product) REQUIRE p.product_id IS UNIQUE")
        tx.run("CREATE CONSTRAINT category_name IF NOT EXISTS FOR (c:Category) REQUIRE c.name IS UNIQUE")
        tx.run("CREATE CONSTRAINT signal_chain_id IF NOT EXISTS FOR (sc:SignalChain) REQUIRE sc.chain_id IS UNIQUE")

    def clear_graph(tx):
        tx.run("MATCH (n) DETACH DELETE n")

    with driver.session() as session:
        session.execute_write(create_constraints)
        session.execute_write(clear_graph)

    solution_count = 0
    product_count = 0
    param_count = 0
    signal_chain_count = 0

    for name in sorted(os.listdir(data_root)):
        solution_dir = os.path.join(data_root, name)
        if not os.path.isdir(solution_dir):
            continue

        complete_path = os.path.join(solution_dir, "complete_data.json")
        enriched_path = os.path.join(solution_dir, ENRICHED_PRODUCTS_FILENAME)

        data = {}
        if os.path.isfile(complete_path):
            try:
                with open(complete_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        page_info = data.get("page_info") or {}
        solution_id = name
        title = _sanitize(page_info.get("title", name))
        page_url = _sanitize(page_info.get("url", ""))
        description = _sanitize(page_info.get("description", ""))[:1000]
        overview = _sanitize(page_info.get("component_overview", ""))[:2000]
        nav_path = _sanitize(page_info.get("navigation_path", ""))

        with driver.session() as session:
            session.run(
                """
                MERGE (s:Solution {solution_id: $solution_id})
                SET s.title = $title, s.page_url = $page_url, s.description = $description,
                    s.overview = $overview, s.navigation_path = $nav_path
                """,
                solution_id=solution_id, title=title, page_url=page_url, description=description,
                overview=overview, nav_path=nav_path,
            )
            solution_count += 1

        # 产品：优先 enriched_products.json
        products_to_add = []
        if os.path.isfile(enriched_path):
            try:
                with open(enriched_path, "r", encoding="utf-8") as f:
                    products_to_add = json.load(f)
            except Exception:
                pass
        if not products_to_add:
            for key in ("hardware_products", "evaluation_products", "reference_products"):
                for p in data.get(key) or []:
                    if isinstance(p, dict) and (p.get("model") or p.get("model_name")):
                        products_to_add.append({
                            "model": p.get("model") or p.get("model_name", ""),
                            "product_link": p.get("product_link") or p.get("model_url", ""),
                            "category": p.get("category", ""),
                            "description": (p.get("description") or "")[:500],
                            "extracted_params": {},
                        })

        for item in products_to_add:
            if not isinstance(item, dict):
                continue
            model = (item.get("model") or "").strip()
            if not model:
                continue
            product_id = f"{solution_id}::{model}"
            link = _sanitize(item.get("product_link", ""))
            desc = _sanitize((item.get("description") or "")[:500])
            category_name = _sanitize(item.get("category", "") or "其他")

            with driver.session() as session:
                session.run(
                    """
                    MERGE (s:Solution {solution_id: $solution_id})
                    MERGE (p:Product {product_id: $product_id})
                    SET p.model = $model, p.product_link = $link, p.description = $desc
                    MERGE (s)-[:CONTAINS]->(p)
                    MERGE (c:Category {name: $category_name})
                    MERGE (p)-[:IN_CATEGORY]->(c)
                    """,
                    solution_id=solution_id, product_id=product_id, model=model, link=link, desc=desc,
                    category_name=category_name,
                )
                product_count += 1

            params = item.get("extracted_params") or {}
            for param_name, param_value in params.items():
                if param_value is None or param_value == "":
                    continue
                pname = _sanitize(str(param_name))[:200]
                pval = _sanitize(str(param_value))[:500]
                with driver.session() as session:
                    session.run(
                        """
                        MERGE (p:Product {product_id: $product_id})
                        CREATE (p)-[:HAS_PARAM]->(x:Parameter {name: $pname, value: $pval})
                        """,
                        product_id=product_id, pname=pname, pval=pval,
                    )
                    param_count += 1

        # 信号链：从 signal_chain_descriptions.json 写入，供 GraphRAG 扩展
        sc_desc_path = os.path.join(solution_dir, SIGNAL_CHAIN_DESCRIPTIONS_FILENAME)
        if os.path.isfile(sc_desc_path):
            try:
                with open(sc_desc_path, "r", encoding="utf-8") as f:
                    sc_data = json.load(f)
                for c in sc_data.get("chains") or []:
                    chain_id_raw = c.get("chain_id") or ""
                    desc = (c.get("description") or "").strip()
                    if not chain_id_raw:
                        continue
                    sc_id = f"{solution_id}::{chain_id_raw}"
                    list_name = _sanitize(c.get("list_name") or chain_id_raw)[:300]
                    img_url = _sanitize(c.get("image_url", ""))[:500]
                    desc_san = _sanitize(desc)[:4000]
                    with driver.session() as session:
                        session.run(
                            """
                            MERGE (s:Solution {solution_id: $solution_id})
                            MERGE (sc:SignalChain {chain_id: $sc_id})
                            SET sc.list_name = $list_name, sc.description = $desc, sc.image_url = $img_url
                            MERGE (s)-[:HAS_SIGNAL_CHAIN]->(sc)
                            """,
                            solution_id=solution_id,
                            sc_id=sc_id,
                            list_name=list_name,
                            desc=desc_san,
                            img_url=img_url,
                        )
                    signal_chain_count += 1
            except Exception:
                pass

    driver.close()
    print(
        f"Neo4j build done: Solutions={solution_count}, Products={product_count}, "
        f"Params={param_count}, SignalChains={signal_chain_count}"
    )
    return solution_count, product_count, param_count


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=None)
    args = ap.parse_args()
    run_build(args.data_root)
