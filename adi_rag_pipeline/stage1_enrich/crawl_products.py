"""
使用 crawl4ai 批量爬取 product_link，将页面内容缓存到本地。
缓存 key：url 的简单 hash，value：markdown 或 cleaned_html 文本。
"""
import asyncio
import hashlib
import json
import os
import random
import time
from typing import List, Dict, Any, Optional

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from adi_rag_pipeline.config import (
    CRAWL_CACHE_DIR,
    CRAWL_DELAY_MIN,
    CRAWL_DELAY_MAX,
    MAX_PAGE_CHARS_FOR_EXTRACT,
)

from adi_rag_pipeline.stage1_enrich.collect_links import collect_all_links


def _url_to_cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _cache_path(cache_dir: str, url: str) -> str:
    key = _url_to_cache_key(url)
    return os.path.join(cache_dir, f"{key}.json")


def get_cached_content(cache_dir: str, url: str) -> Optional[str]:
    path = _cache_path(cache_dir, url)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("markdown") or data.get("content") or ""
    except Exception:
        return None


def save_cached_content(cache_dir: str, url: str, content: str, model: str = ""):
    os.makedirs(cache_dir, exist_ok=True)
    path = _cache_path(cache_dir, url)
    data = {"url": url, "model": model, "markdown": content[:MAX_PAGE_CHARS_FOR_EXTRACT], "content": content[:MAX_PAGE_CHARS_FOR_EXTRACT]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=0)


async def crawl_one(url: str, cache_dir: str, model: str = "") -> str:
    """爬取单 URL，先查缓存；未命中则 crawl4ai 并写入缓存。"""
    cached = get_cached_content(cache_dir, url)
    if cached:
        return cached

    try:
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
    except ImportError:
        raise ImportError("请安装 crawl4ai: pip install crawl4ai")

    run_config = CrawlerRunConfig(
        verbose=False,
        cache_mode=CacheMode.BYPASS,
        page_timeout=60000,
        delay_before_return_html=1.0,
    )
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=run_config)

    if not result.success:
        return ""
    content = getattr(result, "markdown", None) or getattr(result, "cleaned_html", None) or ""
    if content:
        save_cached_content(cache_dir, url, content, model)
    return content
s
"""
这是crawl4ai走串行的，for循环一个个请求发送
"""
# async def crawl_batch(rows: List[Dict[str, Any]], cache_dir: str = None) -> Dict[str, str]:
#     """
#     批量爬取。rows 为 collect_all_links 返回的列表（可先去重 by product_link）。
#     返回 url -> content（已截断），未命中或失败则为空字符串。
#     """
#     cache_dir = cache_dir or CRAWL_CACHE_DIR
#     os.makedirs(cache_dir, exist_ok=True)
#
#     # 按 link 去重，保留一条
#     by_link = {}
#     for r in rows:
#         link = r.get("product_link", "")
#         if link and link not in by_link:
#             by_link[link] = r
#
#     url_to_content = {}
#     for i, (url, r) in enumerate(by_link.items()):
#         model = r.get("model", "")
#         content = await crawl_one(url, cache_dir, model)
#         url_to_content[url] = content or ""
#         if (i + 1) % 5 == 0:
#             delay = random.uniform(CRAWL_DELAY_MIN, CRAWL_DELAY_MAX)
#             await asyncio.sleep(delay)
#     return url_to_content


async def crawl_batch(rows: List[Dict[str, Any]], cache_dir: str = None, max_concurrent: int = 5) -> Dict[str, str]:
    """
    批量爬取（并发版）。rows 为 collect_all_links 返回的列表（可先去重 by product_link）。
    返回 url -> content（已截断），未命中或失败则为空字符串。
    max_concurrent: 最大并发数，默认 5。
    """
    cache_dir = cache_dir or CRAWL_CACHE_DIR
    os.makedirs(cache_dir, exist_ok=True)

    # 按 link 去重，保留一条
    by_link = {}
    for r in rows:
        link = r.get("product_link", "")
        if link and link not in by_link:
            by_link[link] = r

    # 并发控制信号量
    semaphore = asyncio.Semaphore(max_concurrent)

    async def crawl_with_limit(url: str, model: str) -> tuple[str, str]:
        """带并发限制的爬取包装器"""
        async with semaphore:
            # 如果想保留原代码中的随机延迟，可以在这里加入：
            # delay = random.uniform(CRAWL_DELAY_MIN, CRAWL_DELAY_MAX)
            # await asyncio.sleep(delay)
            content = await crawl_one(url, cache_dir, model)
            return url, content or ""

    # 创建所有任务并发执行
    tasks = [asyncio.create_task(crawl_with_limit(url, r.get("model", ""))) for url, r in by_link.items()]
    results = await asyncio.gather(*tasks)

    # 组装结果字典
    return {url: content for url, content in results}


def run_crawl_all(data_root: str = None, cache_dir: str = None) -> Dict[str, str]:
    """同步入口：收集链接并爬取，返回 url -> content。"""
    from adi_rag_pipeline.config import ANALOG_DATA_ROOT
    from adi_rag_pipeline.stage1_enrich.collect_links import collect_all_links

    rows = collect_all_links(data_root or ANALOG_DATA_ROOT)
    cache_dir = cache_dir or CRAWL_CACHE_DIR
    return asyncio.run(crawl_batch(rows, cache_dir))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--cache-dir", default=None)
    args = ap.parse_args()
    result = run_crawl_all(args.data_root, args.cache_dir)
    print(f"Crawled {len(result)} URLs, with content: {sum(1 for v in result.values() if v)}")