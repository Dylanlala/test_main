# -*- coding: utf-8 -*-
"""
Analog.com 解决方案全站爬虫
- 入口: https://www.analog.com/cn/solutions.html
- 解析「行业解决方案」与「技术解决方案」下的分类及具体场景链接
- 对每个场景调用 analog_search.EnhancedAnalogDevicesScraper 爬取正文/表格/图片等

用法:
  python analog_solutions_crawler.py                    # 先只拉取索引（不爬详情）
  python analog_solutions_crawler.py --crawl-all        # 拉取索引并爬取所有场景
  python analog_solutions_crawler.py --crawl-all --limit 5  # 只爬前 5 个场景（调试）
  python analog_solutions_crawler.py --index-file index.json  # 使用已有索引文件
"""

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# 可选：用 Selenium 拉 solutions 首页（反爬时）
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False

BASE = "https://www.analog.com"
SOLUTIONS_URL = "https://www.analog.com/cn/solutions.html"
OUTPUT_ROOT = Path(__file__).resolve().parent / "analog_solutions_data"
INDEX_FILENAME = "index.json"


def _headers() -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": BASE + "/cn/",
    }


def _get_html(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers=_headers(), timeout=30)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text
    except Exception as e:
        print(f"[requests] {url} 失败: {e}")
        return None


def _get_html_selenium(url: str) -> Optional[str]:
    if not HAS_SELENIUM:
        return None
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument(f"user-agent={_headers()['User-Agent']}")
    driver = None
    try:
        driver = webdriver.Chrome(options=opts)
        driver.get(url)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)
        return driver.page_source
    except Exception as e:
        print(f"[Selenium] {url} 失败: {e}")
        return None
    finally:
        if driver:
            driver.quit()


def get_page(url: str) -> Optional[str]:
    html = _get_html(url)
    if html and len(html) > 2000:
        return html
    return _get_html_selenium(url)


def _normalize_url(href: str) -> str:
    if not href or href.startswith("#") or href.startswith("javascript:"):
        return ""
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return BASE.rstrip("/") + href
    return href


def _slug(s: str) -> str:
    """用于目录名：去掉非法字符，截断"""
    s = re.sub(r'[<>:"/\\|?*]', "_", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return (s[:80] + "_") if len(s) > 80 else s


def _is_solutions_link(href: str) -> bool:
    if not href:
        return False
    path = urlparse(_normalize_url(href)).path
    return "/cn/solutions" in path and path.endswith(".html")


def _link_type(path: str) -> str:
    """category: 单段 /cn/solutions/xxx.html；scenario: 两段 /cn/solutions/xxx/yyy.html"""
    path = path.rstrip("/")
    if not path.endswith(".html"):
        return ""
    parts = path.replace("\\", "/").rstrip("/").split("/")
    # .../cn/solutions/xxx.html -> category
    # .../cn/solutions/xxx/yyy.html -> scenario
    if "solutions" in parts:
        idx = parts.index("solutions")
        rest = parts[idx + 1:]
        if len(rest) == 1:
            return "category"
        if len(rest) == 2:
            return "scenario"
    return ""


def parse_solutions_index(html: str, base_url: str = SOLUTIONS_URL) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str, str]]]:
    """
    解析 solutions 首页，得到：
    - categories: [(name, url), ...]
    - scenarios: [(category_name, scenario_name, url), ...]（从首页直接能拿到的场景）
    """
    soup = BeautifulSoup(html, "html.parser")
    categories = []
    scenarios = []
    seen_urls = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        full = _normalize_url(href)
        if not full or not _is_solutions_link(href):
            continue
        path = urlparse(full).path
        typ = _link_type(path)
        text = (a.get_text() or "").strip()
        if not text or len(text) > 200:
            continue
        if full in seen_urls:
            continue
        seen_urls.add(full)

        if typ == "category":
            categories.append((text, full))
        elif typ == "scenario":
            # 从路径取分类名：/cn/solutions/precision-technology/fast-precision.html -> precision-technology
            parts = path.replace("\\", "/").rstrip("/").split("/")
            if "solutions" in parts:
                idx = parts.index("solutions")
                rest = parts[idx + 1:]
                if len(rest) == 2:
                    cat_slug = rest[0]
                    # 用 slug 或链接文本的父级作为 category_name，这里简化为 slug
                    category_name = cat_slug
                    scenarios.append((category_name, text, full))


def fetch_category_scenarios(category_name: str, category_url: str) -> List[Tuple[str, str]]:
    """抓取某个分类页，返回该分类下的场景 [(scene_name, url), ...]"""
    html = get_page(category_url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    out = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        full = _normalize_url(href)
        if not full or not _is_solutions_link(href):
            continue
        path = urlparse(full).path
        if _link_type(path) != "scenario":
            continue
        if full in seen:
            continue
        seen.add(full)
        text = (a.get_text() or "").strip()
        if not text or len(text) > 200:
            text = Path(path).stem
        out.append((text, full))
    return out


def build_index(
    use_selenium_for_index: bool = False,
    index_file: Optional[str] = None,
) -> Dict:
    """
    拉取 solutions 首页 + 各分类页，构建「行业/技术」分类与场景索引，并写入 index.json。
    返回 index 字典结构：
    {
      "技术解决方案": { "精密技术解决方案": [ {"name": "高速精密解决方案", "url": "..."}, ... ], ... },
      "行业解决方案": { ... }
    }
    """
    if index_file and os.path.isfile(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return json.load(f)

    html = _get_html_selenium(SOLUTIONS_URL) if use_selenium_for_index else get_page(SOLUTIONS_URL)
    if not html:
        print("无法获取 solutions 首页")
        return {"技术解决方案": {}, "行业解决方案": {}}

    categories, direct_scenarios = parse_solutions_index(html)
    # 用「技术解决方案」作为大类（首页当前只有技术方案列表；若有行业方案再分）
    tech_tree = {}
    industry_tree = {}

    # 从首页得到的分类，逐个请求分类页拿场景
    for cat_name, cat_url in categories:
        key = _slug(cat_name) or cat_name
        if not key:
            key = urlparse(cat_url).path.split("/")[-1].replace(".html", "")
        scenes = fetch_category_scenarios(cat_name, cat_url)
        if not scenes:
            # 可能首页已有该分类下的场景链接
            scenes = [(name, url) for (c, name, url) in direct_scenarios if c == key or c in cat_url]
        if not scenes:
            scenes = []
        tech_tree[cat_name] = [{"name": name, "url": url} for name, url in scenes]
        time.sleep(0.5)

    # 首页直接得到的场景（无分类页或未在 categories 里）
    for cat_slug, scene_name, scene_url in direct_scenarios:
        if cat_slug not in tech_tree:
            tech_tree[cat_slug] = []
        if not any(s["url"] == scene_url for s in tech_tree[cat_slug]):
            tech_tree[cat_slug].append({"name": scene_name, "url": scene_url})

    index = {
        "source": SOLUTIONS_URL,
        "技术解决方案": tech_tree,
        "行业解决方案": industry_tree,
    }

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    idx_path = OUTPUT_ROOT / INDEX_FILENAME
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"索引已写入: {idx_path}")
    return index


def crawl_all_scenarios(
    index: Dict,
    limit: Optional[int] = None,
    section: str = "技术解决方案",
) -> None:
    """根据索引对每个场景调用 analog_search 爬虫，结果按 分类/场景 存到 analog_solutions_data 下。"""
    try:
        from analog_search import EnhancedAnalogDevicesScraper
    except ImportError:
        print("请在同一目录下保留 analog_search.py，并安装依赖（selenium, beautifulsoup4, requests, pandas）")
        return

    count = 0
    for category_name, scenes in index.get(section, {}).items():
        if not isinstance(scenes, list):
            continue
        for scene in scenes:
            if limit is not None and count >= limit:
                print(f"已达限制 {limit}，停止爬取")
                return
            name = scene.get("name") or "unknown"
            url = scene.get("url")
            if not url:
                continue
            slug_cat = _slug(category_name)
            slug_scene = _slug(name)
            base_dir = str(OUTPUT_ROOT / section / slug_cat / slug_scene)
            print(f"[{count + 1}] 爬取: {category_name} / {name}")
            scraper = EnhancedAnalogDevicesScraper(url, base_dir=base_dir)
            try:
                scraper.run()
                count += 1
            except Exception as e:
                print(f"  失败: {e}")
            time.sleep(1)

    print(f"共爬取 {count} 个场景。")


def main():
    parser = argparse.ArgumentParser(description="Analog 解决方案全站爬虫")
    parser.add_argument("--crawl-all", action="store_true", help="拉取索引后爬取所有场景详情")
    parser.add_argument("--limit", type=int, default=None, help="仅爬取前 N 个场景（调试用）")
    parser.add_argument("--index-file", type=str, default=None, help="使用已有 index.json 路径")
    parser.add_argument("--section", type=str, default="技术解决方案", help="只爬该大类：技术解决方案 / 行业解决方案")
    parser.add_argument("--use-selenium-index", action="store_true", help="索引页也用 Selenium 拉取")
    args = parser.parse_args()

    index = build_index(use_selenium_for_index=args.use_selenium_index, index_file=args.index_file)
    if args.crawl_all:
        crawl_all_scenarios(index, limit=args.limit, section=args.section)
    else:
        print("未加 --crawl-all，仅生成索引。若要爬取所有场景，请运行: python analog_solutions_crawler.py --crawl-all")


if __name__ == "__main__":
    main()
