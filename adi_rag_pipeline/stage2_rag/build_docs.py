"""
从 analog_devices_data_test 各 solution 的 complete_data.json + enriched_products.json 构建 RAG 文档列表。
每个 solution 一条文档（或按长度再切 chunk），包含方案概述 + 产品型号与抽取参数。
"""
import json
import os
import sys
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from adi_rag_pipeline.config import (
    ANALOG_DATA_ROOT,
    RAG_DOCS_PATH,
    ENRICHED_PRODUCTS_FILENAME,
    SIGNAL_CHAIN_DESCRIPTIONS_FILENAME,
)


def _params_to_text(params: Dict[str, Any]) -> str:
    if not params:
        return ""
    parts = []
    for k, v in params.items():
        if v is None or v == "":
            continue
        parts.append(f"{k}: {v}")
    return "；".join(parts)


def build_doc_for_solution(solution_dir: str, solution_name: str) -> Dict[str, Any]:
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

    title = page_info.get("title", solution_name)
    page_url = page_info.get("url", "")
    description = page_info.get("description", "")
    overview = page_info.get("component_overview", "")
    nav = page_info.get("navigation_path", "")
    keywords = page_info.get("keywords", "")

    products_text = []
    enriched_list = []
    if os.path.isfile(enriched_path):
        try:
            with open(enriched_path, "r", encoding="utf-8") as f:
                enriched_list = json.load(f)
        except Exception:
            pass

    for item in enriched_list:
        if not isinstance(item, dict):
            continue
        model = item.get("model", "")
        desc = item.get("description", "")
        params = item.get("extracted_params") or {}
        params_str = _params_to_text(params)
        products_text.append(f"型号 {model}：{desc}" + (f"；参数：{params_str}" if params_str else ""))

    if not products_text:
        for key in ("hardware_products", "evaluation_products", "reference_products"):
            for p in data.get(key) or []:
                if isinstance(p, dict):
                    model = p.get("model") or p.get("model_name", "")
                    desc = p.get("description", "")
                    if model:
                        products_text.append(f"型号 {model}：{desc}")

    text_parts = [
        f"方案名称：{title}",
        f"导航路径：{nav}",
        f"关键词：{keywords}",
        f"描述：{description}",
        f"概述：{overview}",
        "产品与参数：",
        "\n".join(products_text) if products_text else "（无）",
    ]

    # 信号链图转文描述：若有则拼入文档，供 RAG 检索（如「BMS 架构」「车载充电」等）
    sc_desc_path = os.path.join(solution_dir, SIGNAL_CHAIN_DESCRIPTIONS_FILENAME)
    if os.path.isfile(sc_desc_path):
        try:
            with open(sc_desc_path, "r", encoding="utf-8") as f:
                sc_data = json.load(f)
            chains = sc_data.get("chains") or []
            if chains:
                parts_sc = []
                for c in chains:
                    name = c.get("list_name") or c.get("chain_id") or ""
                    desc = (c.get("description") or "").strip()
                    if desc:
                        parts_sc.append(f"信号链【{name}】：{desc}")
                if parts_sc:
                    text_parts.append("信号链与系统架构描述（图转文）：")
                    text_parts.append("\n\n".join(parts_sc))
        except Exception:
            pass
    text = "\n".join(text_parts)
    return {
        "text": text,
        "metadata": {
            "solution_id": solution_name,
            "solution_dir": solution_dir,
            "page_url": page_url,
            "title": title,
        },
    }


def build_all_docs(data_root: str = None) -> List[Dict[str, Any]]:
    data_root = data_root or ANALOG_DATA_ROOT
    docs = []
    for name in sorted(os.listdir(data_root)):
        solution_dir = os.path.join(data_root, name)
        if not os.path.isdir(solution_dir):
            continue
        doc = build_doc_for_solution(solution_dir, name)
        docs.append(doc)
    return docs


def run_build_and_save(data_root: str = None, out_path: str = None):
    data_root = data_root or ANALOG_DATA_ROOT
    out_path = out_path or RAG_DOCS_PATH
    docs = build_all_docs(data_root)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)
    print(f"Built {len(docs)} documents -> {out_path}")
    return docs


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    run_build_and_save(args.data_root, args.out)
