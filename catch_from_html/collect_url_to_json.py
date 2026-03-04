#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 Analog Devices 解决方案首页爬取「具体到具体场景」的所有解决方案链接。
"""

import os
import re
import csv
import json
import time
import random
import logging
from urllib.parse import urljoin, urlparse
from typing import List, Dict

import requests
from bs4 import BeautifulSoup

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("solution_crawler.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SolutionCrawler:
    def __init__(self):
        # 配置参数
        self.BASE_URL = "https://www.analog.com"
        self.SOLUTIONS_INDEX = "https://www.analog.com/cn/solutions.html"
        self.OUTPUT_DIR = os.path.join(os.path.dirname(__file__),"solutions_links")
        self.CSV_FILE = os.path.join(self.OUTPUT_DIR, "all_solution_links.csv")
        self.JSON_FILE = os.path.join(self.OUTPUT_DIR, "all_solution_links.json")

        # 请求配置（默认值）
        self.REQUEST_TIMEOUT = 60
        self.RETRY_COUNT = 3
        self.DELAY_BETWEEN_REQUESTS = 2

        # User-Agent列表
        self.USER_AGENTS = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36"
        ]

        # 只保留「具体场景」详情页
        self.DETAIL_PATH_PATTERN = re.compile(
            r"^/cn/solutions/[^/]+/.+\.html$",
            re.I
        )

        # 创建输出目录
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)

    def normalize_url(self, href: str) -> str:
        """转为绝对 URL，去掉 fragment 和多余空格。"""
        if not href or not href.strip():
            return ""
        href = href.strip().split("#")[0].split("?")[0]
        if not href.startswith("http"):
            href = urljoin(self.BASE_URL, href)
        return href.rstrip("/")

    def is_solution_detail_url(self, url: str) -> bool:
        """判断是否为「具体场景」解决方案详情页（排除仅目录页）。"""
        try:
            parsed = urlparse(url)
            path = (parsed.path or "").rstrip("/")

            # 基础检查
            if not path.startswith("/cn/solutions/"):
                return False
            if not path.endswith(".html"):
                return False

            # 去掉 /cn/solutions/ 后，至少还要有一段子路径
            after = path[len("/cn/solutions/"):]
            if "/" not in after:
                return False

            return self.DETAIL_PATH_PATTERN.match(path) is not None

        except Exception as e:
            logger.error(f"判断URL {url} 失败: {e}")
            return False




    def extract_category_path(self, url: str) -> str:
        """从 URL 提取层级路径。"""
        try:
            parsed = urlparse(url)
            path = (parsed.path or "").strip()
            if not path.startswith("/cn/solutions/"):
                return ""

            # 提取 /cn/solutions/ 之后的部分，去掉.html
            category_path = path[len("/cn/solutions/"):].replace(".html", "")

            # 将路径中的连字符转换为空格，并首字母大写
            def format_segment(segment: str) -> str:
                segment = segment.replace('-', ' ').replace('_', ' ')
                return segment.title()

            # 分割路径并格式化每个部分
            segments = category_path.split('/')
            formatted_segments = [format_segment(seg) for seg in segments]

            return ' / '.join(formatted_segments)

        except Exception as e:
            logger.error(f"提取分类路径失败 {url}: {e}")
            return ""

    def get_random_user_agent(self) -> str:
        """获取随机User-Agent"""
        return random.choice(self.USER_AGENTS)

    def fetch_html_with_retry(self, url: str, use_selenium: bool = False) -> str:
        """带重试机制的页面获取"""

        if use_selenium:
            return self._fetch_html_selenium(url)

        headers = {
            "User-Agent": self.get_random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

        for attempt in range(self.RETRY_COUNT):
            try:
                logger.info(f"尝试 {attempt + 1}/{self.RETRY_COUNT}: 获取 {url}")

                # 添加随机延迟避免被屏蔽
                time.sleep(self.DELAY_BETWEEN_REQUESTS + random.uniform(0, 1))

                response = requests.get(
                    url,
                    headers=headers,
                    timeout=self.REQUEST_TIMEOUT,
                    verify=True
                )

                response.raise_for_status()

                # 尝试多种编码方式
                if response.encoding is None or response.encoding.lower() == 'iso-8859-1':
                    response.encoding = response.apparent_encoding or 'utf-8'

                logger.info(f"成功获取 {url}, 状态码: {response.status_code}, 大小: {len(response.text)} 字节")
                return response.text

            except requests.exceptions.Timeout:
                logger.warning(f"请求超时 {url} (尝试 {attempt + 1}/{self.RETRY_COUNT})")
                if attempt < self.RETRY_COUNT - 1:
                    time.sleep(5 * (attempt + 1))
                else:
                    logger.error(f"所有重试均超时: {url}")

            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP错误 {url}: {e}")
                if hasattr(e, 'response') and e.response.status_code == 403:
                    logger.error("被拒绝访问 (403)，可能需要更改IP或使用代理")
                break

            except requests.exceptions.RequestException as e:
                logger.error(f"请求异常 {url} (尝试 {attempt + 1}/{self.RETRY_COUNT}): {e}")
                if attempt < self.RETRY_COUNT - 1:
                    time.sleep(3 * (attempt + 1))

            except Exception as e:
                logger.error(f"未知错误 {url}: {e}")
                break

        return ""

    def _fetch_html_selenium(self, url: str) -> str:
        """使用 Selenium 获取页面（备用）。"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            logger.info(f"使用Selenium获取: {url}")

            opts = Options()
            opts.add_argument("--headless")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument(f"--user-agent={self.get_random_user_agent()}")

            driver = webdriver.Chrome(options=opts)

            try:
                driver.get(url)

                # 等待页面加载完成
                wait = WebDriverWait(driver, 30)
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

                # 等待额外的JavaScript加载
                time.sleep(5)

                # 滚动页面以触发懒加载
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(1)

                html = driver.page_source

                logger.info(f"Selenium获取成功，页面大小: {len(html)} 字节")
                return html

            finally:
                driver.quit()

        except Exception as e:
            logger.error(f"Selenium获取失败 {url}: {e}")
            return ""

    def collect_links_from_html(self, html: str, source_url: str = None) -> List[Dict]:
        """
        从解决方案首页 HTML 中提取所有「具体场景」链接。
        返回: [ {"url": str, "title": str, "category_path": str, "source_url": str}, ... ]
        """
        if not html:
            return []

        if source_url is None:
            source_url = self.SOLUTIONS_INDEX

        soup = BeautifulSoup(html, "html.parser")
        seen_urls = set()
        results = []

        # 查找所有链接
        all_links = soup.find_all("a", href=True)
        logger.info(f"从HTML中找到 {len(all_links)} 个链接")

        for a in all_links:
            try:
                href = a.get("href", "").strip()
                if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                    continue

                # 规范化URL
                if not href.startswith("http"):
                    full_url = urljoin(source_url, href)
                else:
                    full_url = href

                full_url = self.normalize_url(full_url)

                # 检查是否已经处理过
                if full_url in seen_urls:
                    continue

                # 检查是否为解决方案详情页
                if not self.is_solution_detail_url(full_url):
                    continue

                seen_urls.add(full_url)

                # 提取标题
                title = a.get_text(strip=True)
                if not title:
                    # 尝试从其他属性获取标题
                    title = a.get("title", "") or a.get("aria-label", "")

                # 清理标题
                title = re.sub(r'\s+', ' ', title).strip()[:300]

                # 提取分类路径
                category_path = self.extract_category_path(full_url)

                results.append({
                    "url": full_url,
                    "title": title,
                    "category_path": category_path,
                    "source_url": source_url,
                    "crawl_time": time.strftime("%Y-%m-%d %H:%M:%S")
                })

            except Exception as e:
                logger.error(f"处理链接失败 {a.get('href', '')}: {e}")

        logger.info(f"提取到 {len(results)} 个有效解决方案链接")
        return results

    def crawl_all_solution_links(self, use_selenium: bool = False) -> List[Dict]:
        """
        从 solutions 首页爬取所有具体场景链接。
        """
        logger.info("=" * 60)
        logger.info("开始爬取Analog Devices解决方案链接")
        logger.info(f"目标URL: {self.SOLUTIONS_INDEX}")
        logger.info(f"使用Selenium: {use_selenium}")
        logger.info("=" * 60)

        start_time = time.time()

        # 获取页面
        html = self.fetch_html_with_retry(self.SOLUTIONS_INDEX, use_selenium=use_selenium)

        if not html:
            logger.error("无法获取页面内容")
            return []

        # 提取链接
        links = self.collect_links_from_html(html, self.SOLUTIONS_INDEX)

        # 按分类路径排序
        links.sort(key=lambda x: x.get("category_path", ""))

        elapsed_time = time.time() - start_time
        logger.info(f"爬取完成，耗时 {elapsed_time:.2f} 秒")
        logger.info(f"共找到 {len(links)} 个解决方案链接")

        return links

    def save_results(self, links: List[Dict]) -> None:
        """保存为 CSV 和 JSON。"""
        logger.info(f"保存结果到目录: {self.OUTPUT_DIR}")

        # 保存CSV
        try:
            with open(self.CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=["url", "title", "category_path", "source_url", "crawl_time"])
                writer.writeheader()
                writer.writerows(links)
            logger.info(f"已保存CSV: {self.CSV_FILE} ({len(links)} 行)")
        except Exception as e:
            logger.error(f"保存CSV失败: {e}")

        # 保存JSON
        try:
            with open(self.JSON_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "metadata": {
                        "total_count": len(links),
                        "crawl_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "source_url": self.SOLUTIONS_INDEX
                    },
                    "links": links
                }, f, ensure_ascii=False, indent=2)
            logger.info(f"已保存JSON: {self.JSON_FILE}")
        except Exception as e:
            logger.error(f"保存JSON失败: {e}")

        # 创建README文件
        readme_file = os.path.join(self.OUTPUT_DIR, "README.md")
        try:
            with open(readme_file, "w", encoding="utf-8") as f:
                f.write(f"""# Analog Devices 解决方案链接

## 基本信息
- 爬取时间: {time.strftime("%Y-%m-%d %H:%M:%S")}
- 源URL: {self.SOLUTIONS_INDEX}
- 链接总数: {len(links)}

## 文件说明
- `{os.path.basename(self.CSV_FILE)}`: CSV格式的链接数据
- `{os.path.basename(self.JSON_FILE)}`: JSON格式的链接数据（含元数据）
- `solution_crawler.log`: 爬取日志

## 数据字段说明
1. **url**: 解决方案详情页的完整URL
2. **title**: 页面标题/链接文本
3. **category_path**: 分类路径（从URL提取并格式化）
4. **source_url**: 源页面URL
5. **crawl_time**: 爬取时间戳

## 使用说明
这些链接可以直接用于详细的解决方案内容爬取。
""")
            logger.info(f"已创建README文件: {readme_file}")
        except Exception as e:
            logger.error(f"创建README文件失败: {e}")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="爬取 Analog Devices 解决方案具体场景链接",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                    # 使用requests爬取
  %(prog)s --selenium         # 使用Selenium爬取（适合动态页面）
  %(prog)s --timeout 120      # 设置超时时间为120秒
        """
    )

    parser.add_argument("--selenium", action="store_true",
                        help="使用 Selenium 获取页面（适合JavaScript渲染的页面）")
    parser.add_argument("--timeout", type=int, default=60,
                        help="请求超时时间（秒，默认: 60）")
    parser.add_argument("--retry", type=int, default=3,
                        help="重试次数（默认: 3）")
    parser.add_argument("--delay", type=float, default=2,
                        help="请求间延迟（秒，默认: 2）")

    args = parser.parse_args()

    # 创建爬虫实例
    crawler = SolutionCrawler()

    # 更新配置
    crawler.REQUEST_TIMEOUT = args.timeout
    crawler.RETRY_COUNT = args.retry
    crawler.DELAY_BETWEEN_REQUESTS = args.delay

    logger.info(
        f"配置: timeout={crawler.REQUEST_TIMEOUT}s, retry={crawler.RETRY_COUNT}, delay={crawler.DELAY_BETWEEN_REQUESTS}s")

    # 爬取链接
    links = crawler.crawl_all_solution_links(use_selenium=args.selenium)

    if not links:
        logger.warning("未获取到任何链接")
        print("\n⚠️  警告：未获取到任何链接，请检查：")
        print("  1. 网络连接是否正常")
        print("  2. 网站是否可以访问")
        print("  3. 尝试使用 --selenium 参数")
        print("  4. 查看日志文件 solution_crawler.log")
        return

    # 保存结果
    crawler.save_results(links)

    # 打印摘要
    print("\n" + "=" * 60)
    print("爬取完成！")
    print("=" * 60)
    print(f"链接总数: {len(links)}")
    print(f"输出目录: {os.path.abspath(crawler.OUTPUT_DIR)}")
    print(f"CSV文件: {os.path.basename(crawler.CSV_FILE)}")
    print(f"JSON文件: {os.path.basename(crawler.JSON_FILE)}")
    print(f"日志文件: solution_crawler.log")
    print("\n前10个链接:")
    for i, link in enumerate(links[:10], 1):
        print(f"  {i:2d}. {link['title'][:50]}...")
        print(f"      {link['url']}")
    if len(links) > 10:
        print(f"  ... 还有 {len(links) - 10} 个链接")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
        logger.info("程序被用户中断")
    except Exception as e:
        logger.exception(f"程序运行异常: {e}")
        print(f"\n❌ 程序运行异常: {e}")
        print("请查看日志文件 solution_crawler.log 获取详细信息") 