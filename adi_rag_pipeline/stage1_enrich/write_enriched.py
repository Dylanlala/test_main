"""
对每个 solution 目录：根据 collect_links 结果 + 爬取缓存，调用 LLM 抽取参数，
写回该 solution 目录下的 enriched_products.json。
格式：[ { "model", "product_link", "category", "description", "extracted_params" }, ... ]
"""
import json
import os
import sys
import time
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from adi_rag_pipeline.config import ANALOG_DATA_ROOT, CRAWL_CACHE_DIR, ENRICHED_PRODUCTS_FILENAME
from adi_rag_pipeline.stage1_enrich.collect_links import collect_by_solution
from adi_rag_pipeline.stage1_enrich.crawl_products import get_cached_content
from adi_rag_pipeline.stage1_enrich.llm_extract_params import extract_params_with_llm


def write_enriched_for_solution(
    solution_dir: str,
    rows: List[Dict[str, Any]],
    cache_dir: str,
    skip_existing: bool = True,
) -> int:
    """
    为单个 solution 生成 enriched_products.json。
    rows 为该 solution 的 product 列表（含 model, product_link 等）。
    返回写入的条目数。
    """
    out_path = os.path.join(solution_dir, ENRICHED_PRODUCTS_FILENAME)
    if skip_existing and os.path.isfile(out_path):
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if isinstance(existing, list) and len(existing) > 0:
                return len(existing)
        except Exception:
            pass

    enriched = []
    for r in rows:
        model = r.get("model", "")
        link = r.get("product_link", "")
        content = get_cached_content(cache_dir, link)
        extracted_params = extract_params_with_llm(model, content) if content else {}
        enriched.append({
            "model": model,
            "product_link": link,
            "category": r.get("category", ""),
            "description": (r.get("description") or "")[:500],
            "extracted_params": extracted_params,
        })
        time.sleep(0.5)  # 限流 LLM

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)
    return len(enriched)


def run_write_all(data_root: str = None, cache_dir: str = None, skip_existing: bool = True):
    data_root = data_root or ANALOG_DATA_ROOT
    cache_dir = cache_dir or CRAWL_CACHE_DIR
    by_solution = collect_by_solution(data_root)
    total = 0
    for solution_dir, rows in by_solution.items():
        n = write_enriched_for_solution(solution_dir, rows, cache_dir, skip_existing)
        total += n
        print(f"  {os.path.basename(solution_dir)}: {n} enriched")
    return total


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--no-skip-existing", action="store_true", help="覆盖已有 enriched_products.json")
    args = ap.parse_args()
    total = run_write_all(
        args.data_root,
        args.cache_dir,
        skip_existing=not args.no_skip_existing,
    )
    print(f"Total enriched: {total}")
