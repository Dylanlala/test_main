#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识图谱构建脚本：读取 kg_pipeline 产出的 product_core_params 与 solution_summaries，
构建「方案-产品」图并导出为 CSV / JSON / Neo4j Cypher，供后续图数据库或 RAG 使用。
"""

import json
import os
import glob
import csv
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

# 默认从管线输出目录读取
OUTPUT_KG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output_kg")
KG_EXPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kg_export")


def find_latest_files(output_dir: str) -> Tuple[Optional[str], Optional[str]]:
    """找到最新的 product_core_params 与 solution_summaries 文件。"""
    products = sorted(
        glob.glob(os.path.join(output_dir, "product_core_params_*.json")),
        key=os.path.getmtime,
        reverse=True,
    )
    solutions = sorted(
        glob.glob(os.path.join(output_dir, "solution_summaries_*.json")),
        key=os.path.getmtime,
        reverse=True,
    )
    return (products[0] if products else None, solutions[0] if solutions else None)


def load_pipeline_output(
    product_path: Optional[str] = None,
    solution_path: Optional[str] = None,
    output_dir: str = OUTPUT_KG_DIR,
) -> Tuple[List[Dict], List[Dict]]:
    """加载产品核心参数列表 与 方案摘要列表。"""
    if not product_path or not solution_path:
        p_path, s_path = find_latest_files(output_dir)
        product_path = product_path or p_path
        solution_path = solution_path or s_path
    if not product_path or not os.path.isfile(product_path):
        raise FileNotFoundError(f"未找到产品文件: {product_path}")
    if not solution_path or not os.path.isfile(solution_path):
        raise FileNotFoundError(f"未找到方案文件: {solution_path}")

    with open(product_path, "r", encoding="utf-8") as f:
        product_data = json.load(f)
    products = product_data.get("items") or product_data if isinstance(product_data, dict) else product_data
    if not isinstance(products, list):
        products = []

    with open(solution_path, "r", encoding="utf-8") as f:
        solutions = json.load(f)
    if not isinstance(solutions, list):
        solutions = []

    return products, solutions


def build_graph(products: List[Dict], solutions: List[Dict]) -> Dict[str, Any]:
    """
    构建知识图谱结构：
    - nodes: { solution: [...], product: [...] }
    - edges: [ (from_id, to_id, relation_type, props), ... ]
    节点 id：方案用 solution_dir 或 solution_name，产品用 model 或 source_url 归一化。
    """
    # 产品节点：以 source_url 为唯一 id（同一型号可能出现在多方案，用 url 去重）
    product_nodes = []
    model_to_product = {}
    for p in products:
        url = (p.get("source_url") or "").strip()
        model = (p.get("model") or "").strip() or url
        if not url:
            continue
        node = {
            "id": url,
            "label": "Product",
            "model": model,
            "title": p.get("title") or model,
            "brand_cn": p.get("brand_cn"),
            "brand_en": p.get("brand_en"),
            "category": p.get("category"),
            "description": (p.get("description") or "")[:500],
            "source_url": url,
            "core_params": p.get("core_params") or [],
            "key_features": p.get("key_features") or [],
            "applications": p.get("applications") or [],
        }
        product_nodes.append(node)
        model_to_product[model] = node
        model_to_product[url] = node

    # 方案节点
    solution_nodes = []
    solution_by_dir = {}
    for s in solutions:
        if "solution_name" not in s:
            continue
        sid = (s.get("solution_dir") or s.get("solution_name") or "").strip() or s.get("solution_name")
        node = {
            "id": sid,
            "label": "Solution",
            "solution_name": s.get("solution_name"),
            "solution_url": s.get("solution_url"),
            "solution_summary": (s.get("solution_summary") or "")[:1000],
            "keywords": s.get("keywords"),
            "key_features": s.get("key_features") or [],
            "core_advantages": s.get("core_advantages") or [],
            "target_applications": s.get("target_applications") or [],
        }
        solution_nodes.append(node)
        solution_by_dir[sid] = node

    # 边：Solution -[:CONTAINS_PRODUCT]-> Product（用 model_url 匹配 product id）
    edges = []
    for s in solutions:
        if "solution_name" not in s:
            continue
        sid = (s.get("solution_dir") or s.get("solution_name") or "").strip() or s.get("solution_name")
        for comp in s.get("hardware_components") or []:
            url = (comp.get("model_url") or "").strip()
            if not url:
                continue
            if url in model_to_product:
                edges.append({
                    "from_id": sid,
                    "to_id": url,
                    "relation": "CONTAINS_PRODUCT",
                    "from_label": "Solution",
                    "to_label": "Product",
                    "web_category": comp.get("web_category"),
                    "category": comp.get("category"),
                    "model": comp.get("model"),
                })
            # 若 url 不在已爬产品中，仍可建边，产品节点可后续补全
            else:
                edges.append({
                    "from_id": sid,
                    "to_id": url,
                    "relation": "CONTAINS_PRODUCT",
                    "from_label": "Solution",
                    "to_label": "Product",
                    "web_category": comp.get("web_category"),
                    "category": comp.get("category"),
                    "model": comp.get("model"),
                    "description": (comp.get("description") or "")[:200],
                })

    return {
        "nodes": {"solution": solution_nodes, "product": product_nodes},
        "edges": edges,
        "meta": {
            "solution_count": len(solution_nodes),
            "product_count": len(product_nodes),
            "edge_count": len(edges),
            "build_time": datetime.now().isoformat(),
        },
    }


def export_csv(graph: Dict[str, Any], export_dir: str) -> None:
    """导出节点与边为 CSV，便于 Excel / 其他图库导入。"""
    os.makedirs(export_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 方案节点
    sol_path = os.path.join(export_dir, f"nodes_solution_{ts}.csv")
    with open(sol_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "solution_name", "solution_url", "solution_summary", "keywords", "key_features", "core_advantages", "target_applications"])
        for n in graph["nodes"]["solution"]:
            w.writerow([
                n["id"],
                n.get("solution_name"),
                n.get("solution_url"),
                (n.get("solution_summary") or "")[:2000],
                n.get("keywords"),
                "|".join(n.get("key_features") or []),
                "|".join(n.get("core_advantages") or []),
                "|".join(n.get("target_applications") or []),
            ])
    print(f"  已写: {sol_path}")

    # 产品节点（core_params 用 JSON 字符串或省略，避免列过多）
    prod_path = os.path.join(export_dir, f"nodes_product_{ts}.csv")
    with open(prod_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "model", "title", "brand_cn", "brand_en", "category", "description", "source_url", "key_features", "applications"])
        for n in graph["nodes"]["product"]:
            w.writerow([
                n["id"],
                n.get("model"),
                n.get("title"),
                n.get("brand_cn"),
                n.get("brand_en"),
                n.get("category"),
                (n.get("description") or "")[:500],
                n.get("source_url"),
                "|".join(n.get("key_features") or []),
                "|".join(n.get("applications") or []),
            ])
    print(f"  已写: {prod_path}")

    # 边
    edge_path = os.path.join(export_dir, f"edges_contains_product_{ts}.csv")
    with open(edge_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["from_id", "to_id", "relation", "from_label", "to_label", "web_category", "category", "model"])
        for e in graph["edges"]:
            w.writerow([
                e["from_id"],
                e["to_id"],
                e["relation"],
                e["from_label"],
                e["to_label"],
                e.get("web_category"),
                e.get("category"),
                e.get("model"),
            ])
    print(f"  已写: {edge_path}")


def export_json(graph: Dict[str, Any], export_dir: str) -> str:
    """导出完整图为 JSON，供自定义程序或 RAG 使用。"""
    os.makedirs(export_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(export_dir, f"knowledge_graph_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    print(f"  已写: {path}")
    return path


def export_neo4j_cypher(graph: Dict[str, Any], export_dir: str) -> str:
    """生成 Neo4j Cypher 脚本，可在 Neo4j Browser 或 cypher-shell 中执行。"""
    os.makedirs(export_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(export_dir, f"neo4j_import_{ts}.cypher")
    lines = ["// 知识图谱 Neo4j 导入脚本", "// 执行前请先清空或使用新库", ""]

    def escape(s):
        if s is None:
            return "null"
        return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'

    for n in graph["nodes"]["solution"]:
        name = escape(n.get("solution_name"))
        url = escape(n.get("solution_url"))
        summary = escape((n.get("solution_summary") or "")[:2000])
        keywords = escape(n.get("keywords"))
        lines.append(f"MERGE (s:Solution {{ id: {escape(n['id'])}}}) SET s.solution_name={name}, s.solution_url={url}, s.solution_summary={summary}, s.keywords={keywords};")

    for n in graph["nodes"]["product"]:
        model = escape(n.get("model"))
        title = escape(n.get("title"))
        cat = escape(n.get("category"))
        desc = escape((n.get("description") or "")[:500])
        surl = escape(n.get("source_url"))
        lines.append(f"MERGE (p:Product {{ id: {escape(n['id'])}}}) SET p.model={model}, p.title={title}, p.category={cat}, p.description={desc}, p.source_url={surl};")

    for e in graph["edges"]:
        # 边可能指向未在 product 节点列表中的 URL（未爬到的产品），Neo4j 中需先 MERGE 该 Product 再建边
        lines.append(f"MERGE (b:Product {{ id: {escape(e['to_id'])}}}) ON CREATE SET b.model = {escape(e.get('model'))};")
        lines.append(
            f"MATCH (a:Solution {{ id: {escape(e['from_id'])}}}) "
            f"MATCH (b:Product {{ id: {escape(e['to_id'])}}}) "
            f"MERGE (a)-[r:CONTAINS_PRODUCT]->(b) SET r.web_category={escape(e.get('web_category'))}, r.category={escape(e.get('category'))}, r.model={escape(e.get('model'))};"
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  已写: {path}")
    return path


def run(
    output_dir: str = OUTPUT_KG_DIR,
    export_dir: str = KG_EXPORT_DIR,
    product_path: Optional[str] = None,
    solution_path: Optional[str] = None,
    export_csv_flag: bool = True,
    export_json_flag: bool = True,
    export_neo4j_flag: bool = True,
) -> Dict[str, Any]:
    """加载管线输出 → 构建图 → 导出 CSV/JSON/Neo4j。"""
    print("=" * 60)
    print("知识图谱构建")
    print("=" * 60)
    products, solutions = load_pipeline_output(
        product_path=product_path,
        solution_path=solution_path,
        output_dir=output_dir,
    )
    print(f"加载产品数: {len(products)}，方案数: {len(solutions)}")

    graph = build_graph(products, solutions)
    print(f"图统计: 方案节点 {graph['meta']['solution_count']}，产品节点 {graph['meta']['product_count']}，边 {graph['meta']['edge_count']}")

    print("\n导出:")
    if export_csv_flag:
        export_csv(graph, export_dir)
    if export_json_flag:
        export_json(graph, export_dir)
    if export_neo4j_flag:
        export_neo4j_cypher(graph, export_dir)

    print("\n完成。输出目录:", export_dir)
    return graph


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="从 output_kg 构建知识图谱并导出")
    p.add_argument("--output-dir", default=OUTPUT_KG_DIR, help="管线输出目录")
    p.add_argument("--export-dir", default=KG_EXPORT_DIR, help="图谱导出目录")
    p.add_argument("--product-file", default=None, help="指定 product_core_params JSON 路径")
    p.add_argument("--solution-file", default=None, help="指定 solution_summaries JSON 路径")
    p.add_argument("--no-csv", action="store_true", help="不导出 CSV")
    p.add_argument("--no-json", action="store_true", help="不导出 JSON")
    p.add_argument("--no-neo4j", action="store_true", help="不导出 Neo4j Cypher")
    args = p.parse_args()
    run(
        output_dir=args.output_dir,
        export_dir=args.export_dir,
        product_path=args.product_file,
        solution_path=args.solution_file,
        export_csv_flag=not args.no_csv,
        export_json_flag=not args.no_json,
        export_neo4j_flag=not args.no_neo4j,
    )
