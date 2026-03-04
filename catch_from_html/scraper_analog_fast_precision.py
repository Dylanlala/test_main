# -*- coding: utf-8 -*-
"""
Analog.com 高速精密解决方案页面爬虫
目标: https://www.analog.com/cn/solutions/precision-technology/fast-precision.html

功能:
- 抓取导航（面包屑）：主页 / 解决方案概要 / 精密技术解决方案 / 高速精密解决方案
- 抓取页面到「资源」之前的所有文字
- 抓取所有表格（如密度优化下的表格）及表格下方的图片并下载到本地

反爬处理:
- 优先用 requests + 浏览器头；若返回 403 或内容异常则自动用 Selenium 无头浏览器

用法:
- 在线: python scraper_analog_fast_precision.py
- 本地（网络/DNS 不可用时）: 浏览器打开页面另存为「网页，仅 HTML」，
  再运行: python scraper_analog_fast_precision.py --local 保存的文件.html

依赖: pip install requests beautifulsoup4
可选（在线 Selenium）: pip install selenium webdriver-manager
"""

import argparse
import os
import re
import sys
import json
import time
import hashlib
import urllib.parse
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

# 可选：反爬时使用 Selenium
USE_SELENIUM_FALLBACK = True
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
except ImportError:
    USE_SELENIUM_FALLBACK = False

try:
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    HAS_WEBDRIVER_MANAGER = True
except ImportError:
    HAS_WEBDRIVER_MANAGER = False

BASE_URL = "https://www.analog.com"
TARGET_URL = "https://www.analog.com/cn/solutions/precision-technology/fast-precision.html"
OUTPUT_DIR = Path(__file__).resolve().parent / "analog_fast_precision_output"
IMAGES_DIR = OUTPUT_DIR / "images"


def _session_headers() -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.analog.com/cn/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Cache-Control": "max-age=0",
    }


def _get_html_requests(url: str) -> Optional[str]:
    s = requests.Session()
    s.headers.update(_session_headers())
    try:
        r = s.get(url, timeout=30)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text
    except Exception as e:
        print(f"[requests] 请求失败: {e}")
        return None


def _get_html_selenium(url: str) -> Optional[str]:
    if not USE_SELENIUM_FALLBACK:
        print("未安装 selenium，无法使用浏览器方案")
        return None
    ua = _session_headers()["User-Agent"]
    driver = None
    # 1) 尝试 Chrome + webdriver-manager（自动下载 ChromeDriver）
    if HAS_WEBDRIVER_MANAGER:
        try:
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument(f"user-agent={ua}")
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.get(url)
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(2)
            return driver.page_source
        except Exception as e:
            print(f"[Selenium Chrome] 失败: {e}")
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = None
        # 2) 尝试 Edge（Windows 常见，自动下载 EdgeDriver）
        try:
            from selenium.webdriver.edge.options import Options as EdgeOptions
            from selenium.webdriver.edge.service import Service as EdgeService
            options = EdgeOptions()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")
            options.add_argument(f"user-agent={ua}")
            service = EdgeService(EdgeChromiumDriverManager().install())
            driver = webdriver.Edge(service=service, options=options)
            driver.get(url)
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(2)
            return driver.page_source
        except Exception as e:
            print(f"[Selenium Edge] 失败: {e}")
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            return None
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
    # 无 webdriver-manager：仅尝试系统 PATH 下的 Chrome
    try:
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(f"user-agent={ua}")
        driver = webdriver.Chrome(options=options)
        driver.get(url)
        WebDriverWait(driver, 15).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(2)
        return driver.page_source
    except Exception as e:
        print(f"[Selenium] 获取页面失败: {e}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def get_page_html(url: str = TARGET_URL) -> Optional[str]:
    html = _get_html_requests(url)
    if html and _looks_valid(html):
        print("使用 requests 获取页面成功")
        return html
    print("尝试使用 Selenium...")
    html = _get_html_selenium(url)
    if html:
        print("使用 Selenium 获取页面成功")
    return html


def _looks_valid(html: str) -> bool:
    """简单判断是否为正常内容页（非反爬/错误页）"""
    if not html or len(html) < 2000:
        return False
    if "高速精密" in html or "精密技术" in html or "Analog" in html:
        return True
    if "access denied" in html.lower() or "blocked" in html.lower():
        return False
    return True


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return BASE_URL.rstrip("/") + url
    return url


def extract_breadcrumb(soup: BeautifulSoup) -> list:
    """提取导航面包屑：主页 / 解决方案概要 / 精密技术解决方案 / 高速精密解决方案"""
    nav_texts = []
    # 常见选择器
    for selector in (
        "nav[aria-label='Breadcrumb'] a",
        ".breadcrumb a",
        "[class*='breadcrumb'] a",
        "nav ol li a",
        "nav li a",
    ):
        els = soup.select(selector)
        if els:
            for a in els:
                t = (a.get_text() or "").strip()
                if t and t not in nav_texts:
                    nav_texts.append(t)
            if nav_texts:
                break
    # 备用：找包含「主页」或「精密」的段落
    if not nav_texts:
        for tag in soup.find_all(["nav", "div", "ol", "ul"], class_=re.compile(r"bread|nav", re.I)):
            text = tag.get_text(separator=" ", strip=True)
            if "主页" in text or "精密" in text:
                parts = re.split(r"\s*[/|]\s*", text)
                nav_texts = [p.strip() for p in parts if p.strip()]
                break
    # 若仍无，从 title 或 h1 推断
    if not nav_texts:
        title = soup.find("title")
        if title and "高速精密" in title.get_text():
            nav_texts = ["主页", "解决方案概要", "精密技术解决方案", "高速精密解决方案"]
    return nav_texts


def _find_resource_element(soup: BeautifulSoup):
    """找到「资源」标题对应的元素"""
    for tag in soup.find_all(["h2", "h3", "h4", "section"]):
        if tag.get_text(strip=True) == "资源":
            return tag
    return None


def _document_order_index(soup: BeautifulSoup, target) -> int:
    """目标元素在文档中的顺序索引"""
    for i, tag in enumerate(soup.find_all(True)):
        if tag == target:
            return i
    return -1


def get_text_before_resource(soup: BeautifulSoup) -> str:
    """获取「资源」之前的所有文字（整页文字在「资源」处截断）"""
    main = soup.find("main") or soup.find("article") or soup.find("body") or soup
    full = main.get_text(separator="\n", strip=True)
    if "资源" in full:
        full = full.split("资源", 1)[0].strip()
    return full


def extract_tables_before_resource(soup: BeautifulSoup) -> list:
    """提取「资源」之前的所有 table，转为列表（表头+行）"""
    resource_el = _find_resource_element(soup)
    resource_idx = _document_order_index(soup, resource_el) if resource_el else -1
    tables = []
    for table in soup.find_all("table"):
        if resource_idx >= 0:
            idx = _document_order_index(soup, table)
            if idx >= resource_idx:
                continue
        rows = []
        for tr in table.find_all("tr"):
            cells = []
            for cell in tr.find_all(["th", "td"]):
                cells.append(cell.get_text(separator=" ", strip=True))
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def extract_images_before_resource(soup: BeautifulSoup) -> list:
    """提取「资源」之前的所有 img，返回 [(src, alt), ...]"""
    resource_el = _find_resource_element(soup)
    resource_idx = _document_order_index(soup, resource_el) if resource_el else -1
    out = []
    for img in soup.find_all("img"):
        if resource_idx >= 0:
            idx = _document_order_index(soup, img)
            if idx >= resource_idx:
                continue
        src = img.get("src") or img.get("data-src")
        if not src:
            continue
        src = _normalize_url(src.strip())
        if not src:
            continue
        alt = (img.get("alt") or "").strip()
        out.append((src, alt))
    return out


def download_image(url: str, folder: Path) -> Optional[str]:
    """下载图片到 folder，返回本地相对路径或 None"""
    folder.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(url, headers=_session_headers(), timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"  下载失败 {url}: {e}")
        return None
    ext = ".png"
    ct = r.headers.get("Content-Type", "")
    if "jpeg" in ct or "jpg" in ct:
        ext = ".jpg"
    elif "gif" in ct:
        ext = ".gif"
    elif "webp" in ct:
        ext = ".webp"
    name = hashlib.md5(url.encode()).hexdigest()[:12] + ext
    path = folder / name
    path.write_bytes(r.content)
    return str(path.relative_to(OUTPUT_DIR))


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    html = get_page_html()
    if not html:
        print("无法获取页面，请检查网络或使用代理/Selenium")
        return

    soup = BeautifulSoup(html, "html.parser")

    breadcrumb = extract_breadcrumb(soup)
    print("面包屑:", breadcrumb)

    text_content = get_text_before_resource(soup)
    tables = extract_tables_before_resource(soup)
    images = extract_images_before_resource(soup)

    # 保存文字（到「资源」之前）
    text_path = OUTPUT_DIR / "content_before_resources.txt"
    text_path.write_text(text_content, encoding="utf-8")
    print(f"已保存文字: {text_path}")

    # 保存表格（JSON）
    tables_data = [{"rows": t} for t in tables]
    tables_path = OUTPUT_DIR / "tables.json"
    tables_path.write_text(
        json.dumps(tables_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已保存表格: {tables_path} (共 {len(tables)} 个)")

    # 下载图片并记录
    image_records = []
    for i, (src, alt) in enumerate(images):
        local = download_image(src, IMAGES_DIR)
        if local:
            image_records.append({"url": src, "alt": alt, "local": local})
            print(f"  图片已保存: {local}")
    images_path = OUTPUT_DIR / "images_list.json"
    images_path.write_text(
        json.dumps(image_records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已保存图片列表: {images_path} (共 {len(image_records)} 张)")

    # 汇总
    summary = {
        "url": TARGET_URL,
        "breadcrumb": breadcrumb,
        "text_file": str(text_path.relative_to(OUTPUT_DIR)),
        "tables_count": len(tables),
        "images_count": len(image_records),
    }
    summary_path = OUTPUT_DIR / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"汇总: {summary_path}")


if __name__ == "__main__":
    run()
