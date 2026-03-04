"""
根据产品页 markdown/html 内容，用 LLM 抽取结构化参数。
输出字段：工作电压、工作温度、封装、接口类型、通道数、分辨率、带宽、功耗、典型应用 等。
"""
import json
import os
import re
import sys
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from adi_rag_pipeline.config import get_llm_api_key, LLM_BASE_URL, LLM_MODEL, MAX_PAGE_CHARS_FOR_EXTRACT

try:
    from json_repair import repair_json
except ImportError:
    repair_json = None

EXTRACT_PROMPT = """你是一名电子元器件专家。请从下面「产品页内容」中抽取关于该型号（{model}）的所有技术信息和关系，并以**严格的JSON格式**输出。不要其他解释或 markdown 代码块。
**必须输出的 JSON 结构**（字段名保持如下）：

{{
  "items": [
    {{
      "model_name": "产品型号",
      "brand_cn": "亚德诺",
      "brand_en": "ADI",
      "summary": "一段50字以内的摘要，包含型号、类别、关键参数和主要应用，用于检索",
      "product_category": "产品类别（如ADC/DAC/接口收发器等）",
      "lifecycle_status": "量产/过期，**严格规则**：仅当页面内容中明确出现中文'量产'或英文'In Production'等表示量产的词汇时，才填写'量产'；其他任何情况（包括'推荐用于新设计'、'预发布'、'新设计推荐'等）均填写null。",
      "new_design_statue": "推荐/不推荐，该型号是否推荐用于新设计，过期或者停产则为不推荐",
      "datasheet_url": "数据手册的下载链接（如页面中有明确链接），否则为null",
      "related_products": [
        {{
          "model": "相关型号",
          "relation": "关系描述，如'替代型号'、'配套使用'、'兼容型号'等，没有则不填写，不要编造"
        }}
      ],
      "core_params": [
        {{ "name": "参数名", "value": "参数值", "unit": "单位或空字符串" }}
      ],
      "key_features": ["关键特性1", "关键特性2"],
      "applications": ["应用领域1", "应用领域2"],
      "source_url": "产品页面URL",
      "product_image_url": "产品的图片URL"
    }}
  ]
}}

**抽取规则**：
- `model` 从标题提取；
- `core_params` 从特性中提取电压、电流、温度、频率、接口、封装、引脚数量等，5-15 条核心参数，确保包含常见的核心参数，用于产品选型时参考；
- `product_category` 是什么产品，如ADC、接口收发器等；
- `key_features` 3-5 条；
- `datasheet_url` 如果页面中有“数据手册”或“datasheet”链接，提取完整URL；若没有或不确定，则设为null；
- `lifecycle_status` 按上述严格规则填写；
- `related_products` 如果页面提及了其他型号并描述了关系（如“与ADxxxx兼容”、“推荐搭配ADyyyy使用”,"是ADxxxx的替代料”），则提取成列表；否则为空列表；
- `summary` 结合型号、产品类别、关键参数（最重要的5个参数）和典型应用生成简洁摘要；
- 只从提供信息提取，不编造。

**特别注意**：请严格遵守每一条规则，尤其是对于 lifecycle_status，必须进行字面匹配，不得根据上下文推断。

产品型号：{model}
产品页内容（节选）：
---
{content}
---

只输出上述 JSON，不要 markdown 代码块包裹，不要前后多余文字。"""


def extract_params_with_llm(model: str, content: str) -> Dict[str, Any]:
    if not content or len(content.strip()) < 50:
        return {}
    content = content[:MAX_PAGE_CHARS_FOR_EXTRACT]
    api_key = get_llm_api_key()
    if not api_key:
        return {}

    from openai import OpenAI
    client = OpenAI(base_url=LLM_BASE_URL, api_key=api_key)
    prompt = EXTRACT_PROMPT.format(model=model, content=content)
    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            stream=False,
        )
        text = (resp.choices[0].message.content or "").strip()
    except Exception:
        return {}

    # 去掉可能的 ```json ... ```
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            text = m.group(1).strip()
    if repair_json:
        try:
            obj = json.loads(repair_json(text, return_objects=True))
        except Exception:
            try:
                obj = json.loads(str(repair_json(text, return_objects=False)))
            except Exception:
                return {}
    else:
        try:
            obj = json.loads(text)
        except Exception:
            return {}
    return obj if isinstance(obj, dict) else {}


def extract_params_from_cache(cache_dir: str, url: str, model: str) -> Dict[str, Any]:
    """从缓存读取该 URL 的内容并调用 LLM 抽取。"""
    from adi_rag_pipeline.stage1_enrich.crawl_products import get_cached_content
    content = get_cached_content(cache_dir, url)
    if not content:
        return {}
    return extract_params_with_llm(model, content)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="AD3300")
    ap.add_argument("--content-file", default=None, help="本地文件中的页面内容")
    args = ap.parse_args()
    if args.content_file and os.path.isfile(args.content_file):
        with open(args.content_file, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = "Sample: 3.3V supply, -40°C to +85°C, LFCSP-32, I2C, 16-bit ADC."
    out = extract_params_with_llm(args.model, content)
    print(json.dumps(out, ensure_ascii=False, indent=2))