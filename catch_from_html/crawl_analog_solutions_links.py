#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 Analog Devices 解决方案首页爬取「具体到具体场景」的所有解决方案链接。

入口: https://www.analog.com/cn/solutions.html
目标: 所有形如 /cn/solutions/{category}/{subcategory}/{page}.html 的详情页链接，
      以及 /cn/solutions/{category}/{page}.html 等，排除仅目录页如 /cn/solutions/aerospace-and-defense.html。

输出: CSV + JSON，字段含 url、title、category_path。
"""

import os
import re
import csv
import json
import time
import logging
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.analog.com"
SOLUTIONS_INDEX = "https://www.analog.com/cn/solutions.html"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "analog_devices_data", "solutions_links")
CSV_FILE = os.path.join(OUTPUT_DIR, "all_solution_links.csv")
JSON_FILE = os.path.join(OUTPUT_DIR, "all_solution_links.json")

# 只保留「具体场景」详情页：/cn/solutions/ 之后至少有一个 /（即至少两层：category/page 或 category/subcategory/page）
# 例如: /cn/solutions/aerospace-and-defense/avionics/next-gen-weather-radar.html ✅
#       /cn/solutions/industrial-automation/.../analog-input-output-module.html ✅
#       /cn/solutions/aerospace-and-defense.html ❌（仅目录）
DETAIL_PATH_PATTERN = re.compile(
    r"^/cn/solutions/[^/]+/.+\.html$",
    re.I
)


def normalize_url(href: str) -> str:
    """转为绝对 URL，去掉 fragment 和多余空格。"""
    if not href or not href.strip():
        return ""
    href = href.strip().split("#")[0].split("?")[0]
    if not href.startswith("http"):
        href = urljoin(BASE_URL, href)
    return href.rstrip("/")


def is_solution_detail_url(url: str) -> bool:
    """判断是否为「具体场景」解决方案详情页（排除仅目录页）。"""
    try:
        parsed = urlparse(url)
        path = (parsed.path or "").rstrip("/")
        if not path.startswith("/cn/solutions/"):
            return False
        if not path.endswith(".html"):
            return False
        # 去掉 /cn/solutions/ 后，至少还要有一段子路径（即路径中含至少一个 /）
        after = path[len("/cn/solutions/"):]
        return "/" in after and DETAIL_PATH_PATTERN.match(path) is not None
    except Exception:
        return False


def extract_category_path(url: str) -> str:
    """从 URL 提取层级路径，如 aerospace-and-defense/avionics/next-gen-weather-radar.html -> 航空航天/航空电子/下一代气象雷达（仅做路径字符串）。"""
    try:
        parsed = urlparse(url)
        path = (parsed.path or "").strip()
        if not path.startswith("/cn/solutions/"):
            return ""
        return path[len("/cn/solutions/"):].replace(".html", "").replace("/", " / ")
    except Exception:
        return ""


def fetch_html(url: str, use_selenium: bool = False) -> str:
    """获取页面 HTML。默认 requests；若 use_selenium=True 则用 Selenium（用于 JS 渲染）。"""
    if use_selenium:
        return _fetch_html_selenium(url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text
    except Exception as e:
        logger.error(f"请求失败 {url}: {e}")
        return ""


def _fetch_html_selenium(url: str) -> str:
    """使用 Selenium 获取页面（备用）。"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        opts = Options()
        opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-gpu")
        driver = webdriver.Chrome(options=opts)
        driver.get(url)
        time.sleep(5)
        html = driver.page_source
        driver.quit()
        return html
    except Exception as e:
        logger.error(f"Selenium 获取失败: {e}")
        return ""


def collect_links_from_html(html: str, base_url: str = BASE_URL) -> list[dict]:
    """
    从解决方案首页 HTML 中提取所有「具体场景」链接。
    返回: [ {"url": str, "title": str, "category_path": str}, ... ]
    """
    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    results = []

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        full_url = normalize_url(href)
        if not full_url.startswith(BASE_URL):
            full_url = urljoin(base_url, href)
            full_url = normalize_url(full_url)
        if full_url in seen:
            continue
        if not is_solution_detail_url(full_url):
            continue
        seen.add(full_url)
        title = (a.get_text(strip=True) or "").strip()[:200]
        results.append({
            "url": full_url,
            "title": title,
            "category_path": extract_category_path(full_url),
        })

    return results


def crawl_all_solution_links(use_selenium: bool = False) -> list[dict]:
    """
    从 solutions 首页爬取所有具体场景链接。
    若首页为静态，一次请求即可；若需 JS 渲染可传 use_selenium=True。
    """
    logger.info("正在获取解决方案首页: %s", SOLUTIONS_INDEX)
    html = fetch_html(SOLUTIONS_INDEX, use_selenium=use_selenium)
    if not html:
        logger.error("未获取到页面内容")
        return []

    links = collect_links_from_html(html)
    logger.info("共提取到 %d 个具体场景链接", len(links))
    return links


def save_results(links: list[dict]) -> None:
    """保存为 CSV 和 JSON。"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["url", "title", "category_path"])
        for row in links:
            w.writerow([row.get("url", ""), row.get("title", ""), row.get("category_path", "")])
    logger.info("已保存 CSV: %s", CSV_FILE)

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(links, f, ensure_ascii=False, indent=2)
    logger.info("已保存 JSON: %s", JSON_FILE)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="爬取 Analog 解决方案具体场景链接")
    parser.add_argument("--selenium", action="store_true", help="使用 Selenium 获取页面（默认 requests）")
    args = parser.parse_args()

    links = crawl_all_solution_links(use_selenium=args.selenium)
    if not links:
        logger.warning("未获取到任何链接，请检查网络或尝试 --selenium")
        return

    save_results(links)
    print(f"\n完成。共 {len(links)} 条链接 -> {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
