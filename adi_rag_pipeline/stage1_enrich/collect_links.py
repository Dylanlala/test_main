"""
从 analog_devices_data_test 下所有 complete_data.json 收集 (solution_dir, model, product_link)。
支持 hardware_products / evaluation_products / reference_products；
兼容 model+product_link 与 model_name+model_url。
"""
import json
import os
from typing import List, Dict, Any

# 项目根 = fae_main
import sys
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
from adi_rag_pipeline.config import ANALOG_DATA_ROOT


def _normalize_url(url: str) -> str:
    if not url or not isinstance(url, str):
        return ""
    u = url.strip().rstrip("/")
    return u


def _collect_from_list(products: List[Dict], solution_dir: str, solution_title: str, page_url: str) -> List[Dict[str, Any]]:
    rows = []
    for p in products:
        if not isinstance(p, dict):
            continue
        model = p.get("model") or p.get("model_name") or ""
        link = p.get("product_link") or p.get("product_url") or p.get("model_url") or ""
        link = _normalize_url(link)
        if not model or not link or not link.startswith("http"):
            continue
        rows.append({
            "solution_dir": solution_dir,
            "solution_title": solution_title,
            "page_url": page_url,
            "model": model.strip(),
            "product_link": link,
            "category": p.get("category", ""),
            "description": (p.get("description") or "")[:500],
        })
    return rows


def collect_all_links(data_root: str = None) -> List[Dict[str, Any]]:
    data_root = data_root or ANALOG_DATA_ROOT
    if not os.path.isdir(data_root):
        return []

    all_rows = []
    seen_links = set()

    for name in os.listdir(data_root):
        solution_dir = os.path.join(data_root, name)
        if not os.path.isdir(solution_dir):
            continue
        complete_path = os.path.join(solution_dir, "complete_data.json")
        if not os.path.isfile(complete_path):
            continue

        try:
            with open(complete_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        page_info = data.get("page_info") or {}
        solution_title = page_info.get("title", name)
        page_url = page_info.get("url", "")

        for key in ("hardware_products", "evaluation_products", "reference_products"):
            products = data.get(key)
            if not isinstance(products, list):
                continue
            for row in _collect_from_list(products, solution_dir, solution_title, page_url):
                link = row["product_link"]
                if link not in seen_links:
                    seen_links.add(link)
                all_rows.append(row)

    return all_rows


def collect_by_solution(data_root: str = None) -> Dict[str, List[Dict[str, Any]]]:
    """按 solution 目录分组返回，key 为 solution_dir。"""
    rows = collect_all_links(data_root)
    by_solution = {}
    for r in rows:
        sd = r["solution_dir"]
        if sd not in by_solution:
            by_solution[sd] = []
        by_solution[sd].append(r)
    return by_solution


if __name__ == "__main__":
    rows = collect_all_links()
    print(f"Total product links: {len(rows)}")
    by_sol = collect_by_solution()
    print(f"Solutions: {len(by_sol)}")
    for sd, items in list(by_sol.items())[:2]:
        print(f"  {os.path.basename(sd)}: {len(items)} products")
