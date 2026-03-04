#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
mlhuang: 用于抓取ADI解决方案页面，提取结构化信息并保存为JSON
"""

import asyncio
import json
import os
import re
import sys
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import requests
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from adi_rag_pipeline.config import get_llm_api_key, LLM_BASE_URL, LLM_MODEL, MAX_PAGE_CHARS_FOR_EXTRACT

try:
    from json_repair import repair_json
except ImportError:
    repair_json = None

REQUEST_TIMEOUT = 120


# EXTRACT_PROMPT = """你是一名电子元器件专家。下面是一个ADI解决方案页面的Markdown内容，其中包含多个测量场景（如电流电压测量、电流电压驱动、光测量等）。每个场景用三级标题（###）标识，并在标题后可能有一段描述文本（介绍该场景的用途、特点等）。每个场景下有多个优化方向（如密度优化、功耗优化、噪声和带宽优化等），用四级标题（####）标识。每个优化方向下有一个表格，表格列出了该方向下各个功能模块（如保护、增益、ADC驱动器、ADC、基准电压源、隔离、DAC、输出驱动器等）对应的器件型号、简要描述和产品页面URL。
#
# 请按照以下要求提取所有信息，并以清晰的Markdown格式输出，不要添加额外解释，不要包含代码块包裹。
#
# ### 输出格式要求：
# - 按场景分组，每个场景以三级标题（###）开头。
# - 三级标题之后，立即添加一行 **场景描述**，格式为：`描述: <提取的描述文本>`。描述文本通常位于三级标题后、四级标题或表格之前，如果存在则提取，否则留空。
# - 场景下每个优化方向以四级标题（####）开头。
# - 优化方向下，用列表形式列出各个功能模块，格式为：`- **模块名称**: 器件型号: 简要描述；产品链接：URL`。
# - 如果某个模块没有产品链接，则只写描述，不写URL。
# - 在每个优化方向下，如果有对应的框图图片，请单独一行列出图片URL，格式为：`- **框图**: URL`。
# - 在场景末尾，如果有该场景相关的LTspice仿真下载链接、电源解决方案PDF链接或应用页面链接，请以列表形式列出，格式为：`- **LTspice仿真**: [名称](URL)`、`- **电源解决方案**: [名称](URL)`、`- **应用**: [名称](URL)`。如果多个，每个单独一行。
# - 如果页面中存在多个相同场景，则全部提取；如果某个字段缺失，留空或注明“无”。
# - 参考资料不必列出。
#
# 请严格按此格式提取，确保信息完整准确。
#
# 页面内容：
# {content}"""



EXTRACT_PROMPT = """你是一名电子元器件专家。下面是一个ADI解决方案页面的Markdown内容，其中包含多个测量场景（如电流电压测量、电流电压驱动、光测量等）。请根据页面内容提取所有信息，并严格按照以下JSON格式输出，不要添加任何额外文字或Markdown标记。

### JSON Schema
{{
  "scenarios": [
    {{
      "title": "场景标题（三级标题文本）",
      "description": "场景描述文本（如有，否则为空字符串）",
      "optimizations": [
        {{
          "direction": "优化方向标题（四级标题文本）",
          "modules": [
            {{
              "name": "模块名称（如保护、增益等）",
              "part": "器件型号",
              "description": "简要描述",
              "url": "产品页面URL（若无则null）"
            }}
          ],
          "block_diagram_url": "框图图片URL（若无则null）"
        }}
      ],
      "resources": {{
        "ltspice": [{{"name": "仿真名称", "url": "URL"}}] | null,
        "power_solution": [{{"name": "方案名称", "url": "URL"}}] | null,
        "application_page": [{{"name": "页面名称", "url": "URL"}}] | null
      }}
    }}
  ]
}}

### 提取规则：
- 每个三级标题（###）定义一个场景。
- 三级标题后紧跟的描述文本（若有）填入该场景的 description 字段。
- 每个四级标题（####）定义一个优化方向，填入 optimizations[].direction。
- 四级标题后的表格中，每一行对应一个功能模块，按表格列顺序提取：模块名称、器件型号、简要描述、产品URL。若表格列顺序不同，请根据上下文判断。产品URL可能以链接形式存在，提取完整的URL。
- 优化方向下如果存在框图图片，其URL通常以 `![...](...)` 或 `<img>` 形式出现，提取并填入 block_diagram_url。
- 场景末尾的LTspice仿真、电源解决方案、应用页面链接分别填入 resources 对应数组。每个资源为包含 name 和 url 的对象。若无则填 null 或空数组。
- 如果某个字段缺失，按 schema 中的默认值处理（null 或空字符串/数组）。
- 不要遗漏任何场景和优化方向。

页面内容：
{content}
"""


# ==================== 精简后的提示词（要求输出JSON）====================

# ======================================================

async def fetch_page_markdown(url: str) -> Optional[str]:
    """使用 crawl4ai 抓取指定 URL 的页面内容，返回 Markdown 格式文本，启用缓存。"""
    try:
        config = CrawlerRunConfig(
            cache_mode=CacheMode.ENABLED,
            verbose=True,
            page_timeout=60000,
            delay_before_return_html=1.0,
            word_count_threshold=5,
            excluded_selector='.resources, #support, .developer-tools, .training, .files, .downloads, footer, nav'
        )
        async with AsyncWebCrawler(verbose=True) as crawler:
            result = await crawler.arun(url=url, config=config)
        if not result.success:
            print(f"爬取失败: {result.error_message or '未知错误'}", file=sys.stderr)
            return None
        content = getattr(result, "markdown", None) or getattr(result, "cleaned_html", None) or ""
        if not content:
            print("警告：页面内容为空")
            return None
        return content
    except Exception as e:
        print(f"爬取页面时发生异常: {e}")
        return None

def extract_with_llm(content: str) -> Optional[dict]:
    """调用 LLM 从页面内容中抽取信息，返回解析后的 JSON 对象。"""
    if not content or len(content.strip()) < 50:
        print("内容过短，无法提取")
        return None
    max_chars = MAX_PAGE_CHARS_FOR_EXTRACT if isinstance(MAX_PAGE_CHARS_FOR_EXTRACT, int) else 15000
    content = content[:max_chars]

    api_key = get_llm_api_key()
    if not api_key:
        print("未找到 LLM API Key，请检查配置")
        return None

    from openai import OpenAI
    client = OpenAI(base_url=LLM_BASE_URL, api_key=api_key)

    prompt = EXTRACT_PROMPT.format(content=content)
    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=16384,
            stream=False,
        )
        text = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"LLM 调用异常: {e}")
        return None

    # 尝试多种方式提取JSON
    data = None

    def try_parse(candidate: str, label: str):
        """尝试解析 JSON，若失败则用 json_repair 再试一次。"""
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            if repair_json:
                try:
                    repaired = repair_json(candidate)
                    return json.loads(repaired)
                except Exception:
                    pass
        return None

    # 若响应以 ```json 或 ``` 开头，先剥掉前缀，便于后续用首尾大括号截取（应对被截断的无闭合```）
    normalized = text.strip()
    if normalized.startswith("```"):
        first_newline = normalized.find("\n")
        if first_newline != -1:
            normalized = normalized[first_newline + 1 :].strip()

    # 方法1：直接解析（LLM可能直接返回JSON；先试剥掉 ``` 后的内容）
    for candidate in (normalized, text):
        data = try_parse(candidate, "直接解析")
        if data:
            print("直接解析JSON成功")
            return data

    # 方法2：提取Markdown代码块中的JSON（含闭合的 ```）
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text, re.DOTALL)
    if m:
        candidate = m.group(1).strip()
        data = try_parse(candidate, "代码块")
        if data:
            print("从代码块中解析JSON成功")
            return data

    # 方法3：无闭合 ``` 时，用剥掉前缀后的内容；否则用原文。再按首尾 { } 截取
    for source in (normalized, text):
        start = source.find("{")
        end = source.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = source[start : end + 1]
            data = try_parse(candidate, "大括号截取")
            if data:
                print("通过大括号截取解析JSON成功")
                return data

    # 方法4：对整段响应做 json_repair（含截断的 JSON）
    if repair_json:
        try:
            repaired = repair_json(normalized if normalized != text else text)
            data = json.loads(repaired)
            print("使用 json_repair 修复成功")
            return data
        except Exception as e2:
            print(f"json_repair 失败: {e2}")

    print(f"JSON 解析失败，原始响应预览: {text[:200]}")
    return None

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="爬取 ADI 解决方案页面并提取结构化 JSON 信息")
    parser.add_argument("url", help="解决方案页面 URL")
    parser.add_argument("--output", "-o", default="output.json", help="输出 JSON 文件路径（默认 output.json）")
    args = parser.parse_args()

    url = args.url
    print(f"🌐 开始抓取: {url}")
    markdown = await fetch_page_markdown(url)
    if not markdown:
        print("❌ 抓取失败或页面内容为空，请检查 URL 是否有效。")
        sys.exit(1)
    print(f"✅ 抓取成功，获取到 {len(markdown)} 字符的 Markdown 内容")

    result = extract_with_llm(markdown)
    if not result:
        print("❌ 提取失败，未获得有效 JSON 内容")
        sys.exit(1)

    try:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"✅ 提取结果已保存到 {args.output}")
    except Exception as e:
        print(f"❌ 保存文件失败: {e}")
        sys.exit(1)

    # 打印预览
    preview = json.dumps(result, ensure_ascii=False, indent=2)[:500]
    print(f"📄 提取结果预览（前500字符）：\n{preview}...")

if __name__ == "__main__":
    asyncio.run(main())