#!/usr/bin/env python3
"""
Stage 1 一键执行：收集 product_link -> crawl4ai 爬取 -> LLM 抽取参数 -> 写回各 solution 下 enriched_products.json
运行前请确保已安装 crawl4ai、openai、json_repair；且 analog_devices_data_test 存在。
"""
import asyncio
import os
import sys

# 项目根
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adi_rag_pipeline.config import ANALOG_DATA_ROOT, CRAWL_CACHE_DIR
from adi_rag_pipeline.stage1_enrich.collect_links import collect_all_links, collect_by_solution
from adi_rag_pipeline.stage1_enrich.crawl_products import crawl_batch
from adi_rag_pipeline.stage1_enrich.write_enriched import write_enriched_for_solution


def main():
    print("Stage 1: 收集链接...")
    rows = collect_all_links(ANALOG_DATA_ROOT)
    if not rows:
        print("未找到任何 product_link，请检查 analog_devices_data_test 下是否有 complete_data.json")
        return
    print(f"  共 {len(rows)} 条产品链接（去重前）")

    print("Stage 1: 爬取产品页（crawl4ai）...")
    by_link = {}
    for r in rows:
        link = r.get("product_link", "")
        if link and link not in by_link:
            by_link[link] = r
    list_rows = [by_link[url] for url in by_link]
    url_to_content = asyncio.run(crawl_batch(list_rows, CRAWL_CACHE_DIR))
    print(f"  已爬取 {sum(1 for v in url_to_content.values() if v)} / {len(url_to_content)} 条")

    print("Stage 1: LLM 抽取参数并写回 enriched_products.json...")
    by_solution = collect_by_solution(ANALOG_DATA_ROOT)
    total = 0
    for solution_dir, sol_rows in by_solution.items():
        n = write_enriched_for_solution(solution_dir, sol_rows, CRAWL_CACHE_DIR, skip_existing=False)
        total += n
        print(f"  {os.path.basename(solution_dir)}: {n}")
    print(f"Stage 1 完成，共写入 {total} 条产品参数。")


if __name__ == "__main__":
    main()
