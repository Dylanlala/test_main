"""
使用 crawl4ai 爬取网页（v0.8.x API）。
默认爬取 ADI 产品页，可修改 URL 或通过命令行传入。
"""
import asyncio
import sys

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode


async def crawl(url: str, verbose: bool = True) -> None:
    """爬取单个 URL，输出 Markdown 或 HTML。"""
    run_config = CrawlerRunConfig(
        verbose=verbose,
        cache_mode=CacheMode.BYPASS,  # 每次重新抓取，不用缓存
        page_timeout=60000,  # 页面超时 60 秒
        delay_before_return_html=1.0,  # 等待 1 秒再取 HTML，便于动态内容加载
        word_count_threshold=5,  # 过滤过短的文本块
    )

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=run_config)

    if not result.success:
        print(f"爬取失败: {result.error_message or '未知错误'}", file=sys.stderr)
        if getattr(result, "status_code", None):
            print(f"HTTP 状态码: {result.status_code}", file=sys.stderr)
        return

    # 优先输出 markdown，若无则输出 cleaned_html
    content = getattr(result, "markdown", None) or getattr(result, "cleaned_html", None) or ""
    if content:
        print(content)
    else:
        print("(无正文内容)")


async def main() -> None:
    url = "https://www.analog.com/cn/products/ad3300.html"
    if len(sys.argv) > 1:
        url = sys.argv[1].strip()
    await crawl(url)


if __name__ == "__main__":
    asyncio.run(main())
