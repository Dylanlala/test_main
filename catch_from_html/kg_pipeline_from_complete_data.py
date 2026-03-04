#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识图谱数据管线：
从 analog_devices_data_test 前 N 个子目录的 complete_data.json 收集产品链接
→ 爬取产品页 → LLM 抽取产品核心参数 → LLM 生成方案总结+方案 JSON → 合并输出供知识图谱使用
"""

import json
import re
import os
import time
import glob
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

# ---------------------------- 配置 ----------------------------
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analog_devices_data_test")
TOP_N_SUBDIRS = 10
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output_kg")
CRAWL_DELAY_SEC = 2
LLM_DELAY_SEC = 1

# 火山引擎（与 llm_analysis_from_html / llm_analysis_to_json 一致）
VOLCENGINE_API_KEY = "88632c3b-7c51-4517-83a1-c77957720f11"
VOLCENGINE_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/bots"
VOLCENGINE_MODEL = "bot-20251202172548-dp7bp"

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


# ---------------------------- 步骤1：收集产品链接 ----------------------------
def get_first_n_subdirs(base_dir: str, n: int) -> List[str]:
    """取前 n 个子目录（仅目录，且存在 complete_data.json 的优先排序后取前 n 个）。"""
    if not os.path.isdir(base_dir):
        return []
    all_subdirs = sorted(
        [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    )
    result = []
    for d in all_subdirs:
        path = os.path.join(base_dir, d)
        if os.path.isfile(os.path.join(path, "complete_data.json")):
            result.append(d)
            if len(result) >= n:
                break
    return result


def collect_product_links_from_complete_data(
    base_dir: str, subdirs: List[str]
) -> List[Dict[str, Any]]:
    """
    从多个子目录的 complete_data.json 中收集 (model, product_link, web_category, solution_dir)。
    按 product_link 去重，保留首次出现的 solution 信息。
    """
    seen_links = set()
    collected = []

    for subdir in subdirs:
        json_path = os.path.join(base_dir, subdir, "complete_data.json")
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  [跳过] 无法加载 {json_path}: {e}")
            continue

        # hardware_products
        for item in data.get("hardware_products") or []:
            link = (item.get("product_link") or "").strip()
            if link and link not in seen_links:
                seen_links.add(link)
                collected.append({
                    "model": (item.get("model") or "").strip(),
                    "product_link": link,
                    "web_category": "硬件产品",
                    "solution_dir": subdir,
                    "description": (item.get("description") or "").strip()[:200],
                })

        # evaluation_products
        for item in data.get("evaluation_products") or []:
            link = (item.get("product_link") or "").strip()
            if link and link not in seen_links:
                seen_links.add(link)
                collected.append({
                    "model": (item.get("model") or "").strip(),
                    "product_link": link,
                    "web_category": "评估板",
                    "solution_dir": subdir,
                    "description": (item.get("description") or "").strip()[:200],
                })

        # reference_products
        for item in data.get("reference_products") or []:
            link = (item.get("product_link") or "").strip()
            if link and link not in seen_links:
                seen_links.add(link)
                collected.append({
                    "model": (item.get("model") or "").strip(),
                    "product_link": link,
                    "web_category": "参考设计",
                    "solution_dir": subdir,
                    "description": (item.get("description") or "").strip()[:200],
                })

        # satellite_components[].main_products (model_name, model_url)
        for comp in data.get("satellite_components") or []:
            for mp in comp.get("main_products") or []:
                link = (mp.get("model_url") or "").strip()
                if link and link not in seen_links:
                    seen_links.add(link)
                    collected.append({
                        "model": (mp.get("model_name") or "").strip(),
                        "product_link": link,
                        "web_category": "航天组件",
                        "solution_dir": subdir,
                        "description": "",
                    })

    return collected


# ---------------------------- 步骤2：爬取产品页 ----------------------------
def scrape_adi_product(url: str) -> Optional[Dict[str, Any]]:
    """爬取单个 ADI 产品页，返回 title, features, details, models, url（与 pachong_from_adi 逻辑一致）。"""
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
        response.raise_for_status()
        response.encoding = "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        title_tag = soup.find("h1")
        product_title = title_tag.text.strip() if title_tag else "未找到标题"

        features = []
        features_panel = soup.find("div", id="tab-panel-features")
        if features_panel:
            columns = features_panel.find_all("div", class_="col-md-6")
            if columns:
                for col in columns:
                    for li in col.find_all("li"):
                        t = li.text.strip()
                        if t and t not in features:
                            features.append(t)
            else:
                for li in features_panel.find_all("li"):
                    t = li.text.strip()
                    if t and t not in features:
                        features.append(t)

        details = ""
        details_panel = soup.find("div", id="tab-panel-details")
        if details_panel:
            ps = details_panel.find_all("p")
            details = " ".join(p.text.strip() for p in ps if p.text.strip())

        model_info = []
        model_section = soup.find(
            ["div", "section"], class_=lambda x: x and "model" in str(x).lower()
        )
        if model_section:
            for node in model_section.find_all(["li", "span", "div"]):
                t = node.text.strip()
                if t and len(t) < 50:
                    model_info.append(t)

        return {
            "url": url,
            "title": product_title,
            "features": features,
            "details": details,
            "models": model_info,
            "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as e:
        print(f"  爬取失败 {url}: {e}")
        return None


# ---------------------------- 步骤3：LLM 抽取产品核心参数 ----------------------------
def call_volcengine(prompt: str, max_tokens: int = 3000, temperature: float = 0.1) -> Optional[str]:
    try:
        response = requests.post(
            f"{VOLCENGINE_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {VOLCENGINE_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": VOLCENGINE_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=120,
        )
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        print(f"  API 错误: {response.status_code} {response.text[:200]}")
        return None
    except Exception as e:
        print(f"  请求异常: {e}")
        return None


def build_product_prompt(product_data: Dict[str, Any], max_chars: int = 6000) -> str:
    """构造产品核心参数抽取的 prompt（与 llm_analysis_from_html 一致）。"""
    product_info = f"产品标题: {product_data.get('title', '')}\n"
    if product_data.get("features"):
        product_info += "产品特性:\n"
        for i, f in enumerate(product_data["features"], 1):
            product_info += f"  {i}. {f}\n"
    elif product_data.get("overview"):
        product_info += f"产品概述: {product_data['overview']}\n"
    if product_data.get("details"):
        product_info += f"产品详情: {product_data['details'][:500]}...\n"
    if product_data.get("models"):
        product_info += f"相关型号: {', '.join(product_data['models'])}\n"
    product_info += f"产品URL: {product_data.get('url', '')}\n"
    if len(product_info) > max_chars:
        product_info = product_info[: max_chars - 50] + "\n...(已截断)"

    return f"""你是一个电子元器件专家，专门从ADI(亚德诺半导体)的产品信息中提取核心参数用于构建知识图谱。
请从以下ADI产品信息中**直接提取**可用于构建知识图谱的核心参数，并**只输出一个合法的 JSON 对象**，不要其他解释或 markdown 代码块。

**必须输出的 JSON 结构**（字段名保持如下）：
{{
  "items": [
    {{
      "model": "产品型号（从标题中提取）",
      "title": "产品完整标题",
      "brand_cn": "亚德诺",
      "brand_en": "ADI",
      "description": "产品简介",
      "category": "产品类型（如ADC/DAC/接口芯片等）",
      "core_params": [
        {{ "name": "参数名", "value": "参数值", "unit": "单位或空字符串" }}
      ],
      "key_features": ["关键特性1", "关键特性2"],
      "applications": ["应用领域1", "应用领域2"],
      "source_url": "产品页面URL"
    }}
  ]
}}

**抽取规则**：model 从标题提取；core_params 从特性中提取电压、电流、温度、频率、接口、封装等，5-15 条；key_features 3-5 条；applications 根据描述推断。只从提供信息提取，不编造。

**ADI产品信息**：
{product_info}

请直接输出上述结构的 JSON，不要包裹在 ```json 中，不要前后多余文字。"""


def parse_json_from_llm(text: str) -> Optional[Dict]:
    if not text or not text.strip():
        return None
    raw = text.strip()
    if "```" in raw:
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return None


# ---------------------------- 步骤4：LLM 方案总结 + 方案 JSON ----------------------------
def build_solution_prompt(data: Dict[str, Any]) -> str:
    """根据 complete_data.json 构造方案总结+方案 JSON 的 prompt（与 llm_analysis_to_json 一致，修正拼写）。"""
    page = data.get("page_info") or {}
    val = data.get("value_and_benefits") or {}
    chars = val.get("characteristics") or []
    return f"""你是一个资深的半导体领域解决方案架构师和知识图谱专家。请基于以下的JSON数据，总结出详细的方案描述。

JSON数据概述：
- 解决方案的标题：{page.get('title', '')}
- 解决方案的url：{page.get('url', '')}
- 解决方案的关键词：{page.get('keywords', '')}
- 解决方案描述：{page.get('component_overview', '')}
- 核心价值与优势：{val.get('contents', '')}
- 解决方案的应用场景分类：{page.get('navigation_path', '')}
- 关键特性：{', '.join(chars) if isinstance(chars, list) else chars}
- 该方案的产品选型：{data.get('hardware_products', [])}
- 该方案的评估板：{data.get('evaluation_products', [])}
- 该方案的参考设计：{data.get('reference_products', [])}

请**只输出一个结构化的 JSON 对象**，不要「一、方案核心总结」等文字，方便后续知识图谱构建。字段如下：
{{
  "solution_name": "完整的解决方案名称",
  "solution_url": "该方案的url",
  "solution_summary": "一段清晰、专业的方案总结：1.方案名称与主要应用场景 2.关键技术与核心器件 3.核心技术标准 4.解决的核心问题或需求",
  "keywords": "关键词，逗号分隔",
  "key_features": ["特性1", "特性2", "特性3"],
  "core_advantages": ["优势1", "优势2", "优势3"],
  "target_applications": ["应用场景1", "应用场景2", "应用场景3"],
  "hardware_components": [
    {{
      "model": "芯片型号",
      "description": "芯片描述",
      "params": "芯片的核心参数简述",
      "model_url": "芯片的产品链接",
      "category": "器件类型",
      "web_category": "产品特性/评估板/参考设计",
      "brand": "ADI"
    }}
  ]
}}

要求：只输出 JSON，不要 markdown 代码块包裹，不要前后多余文字。基于提供的数据总结，不添加不存在的信息。"""


def parse_solution_json_from_llm(text: str) -> Optional[Dict]:
    if not text or not text.strip():
        return None
    raw = text.strip()
    if "```" in raw:
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    try:
        s = m.group()
        s = s.replace("'", '"')
        s = re.sub(r",\s*}", "}", s)
        s = re.sub(r",\s*]", "]", s)
        return json.loads(s)
    except json.JSONDecodeError:
        return None


# ---------------------------- 步骤5：合并输出 ----------------------------
def merge_core_params_into_solution(
    solution_json: Dict,
    link_to_core_params: Dict[str, Dict],
) -> Dict:
    """将已抽取的产品 core_params 挂到 solution 的 hardware_components 上（按 model_url 匹配）。"""
    comps = solution_json.get("hardware_components") or []
    for c in comps:
        url = (c.get("model_url") or "").strip()
        if url and url in link_to_core_params:
            c["core_params"] = link_to_core_params[url].get("core_params") or []
            c["key_features"] = link_to_core_params[url].get("key_features") or []
    solution_json["hardware_components"] = comps
    return solution_json


# ---------------------------- 主流程 ----------------------------
def run_pipeline(
    base_dir: str = BASE_DIR,
    top_n: int = TOP_N_SUBDIRS,
    output_dir: str = OUTPUT_DIR,
    skip_crawl: bool = False,
    skip_product_llm: bool = False,
    skip_solution_llm: bool = False,
):
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ---------- 步骤1：收集产品链接 ----------
    print("=" * 60)
    print("步骤1：从 complete_data.json 收集产品链接")
    subdirs = get_first_n_subdirs(base_dir, top_n)
    if not subdirs:
        print(f"未找到至少 1 个含 complete_data.json 的子目录，路径: {base_dir}")
        return
    print(f"使用前 {len(subdirs)} 个子目录: {subdirs}")

    product_links = collect_product_links_from_complete_data(base_dir, subdirs)
    print(f"共收集到 {len(product_links)} 个唯一产品链接")

    # 保存链接列表供排查
    links_path = os.path.join(output_dir, f"product_links_{timestamp}.json")
    with open(links_path, "w", encoding="utf-8") as f:
        json.dump(product_links, f, ensure_ascii=False, indent=2)
    print(f"链接列表已保存: {links_path}")

    # ---------- 步骤2：爬取产品页 ----------
    crawled = {}
    if not skip_crawl:
        print("\n" + "=" * 60)
        print("步骤2：爬取产品页")
        for i, rec in enumerate(product_links, 1):
            url = rec["product_link"]
            print(f"  [{i}/{len(product_links)}] {url[:60]}...")
            data = scrape_adi_product(url)
            if data:
                crawled[url] = data
            if i < len(product_links):
                time.sleep(CRAWL_DELAY_SEC)
        print(f"成功爬取 {len(crawled)}/{len(product_links)} 个产品页")
        crawl_path = os.path.join(output_dir, f"crawled_products_{timestamp}.json")
        with open(crawl_path, "w", encoding="utf-8") as f:
            json.dump(crawled, f, ensure_ascii=False, indent=2)
        print(f"爬取结果已保存: {crawl_path}")
    else:
        # 尝试加载已有爬取结果
        pattern = os.path.join(output_dir, "crawled_products_*.json")
        existing = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
        if existing:
            with open(existing[0], "r", encoding="utf-8") as f:
                crawled = json.load(f)
            print(f"已加载已有爬取结果: {existing[0]}，共 {len(crawled)} 条")
        else:
            print("skip_crawl=True 且未找到已有 crawled_products_*.json，将跳过步骤3 产品 LLM")

    # ---------- 步骤3：LLM 抽取产品核心参数 ----------
    product_core_params_list = []
    link_to_core_params = {}
    if not skip_product_llm and crawled:
        print("\n" + "=" * 60)
        print("步骤3：LLM 抽取产品核心参数")
        for i, (url, raw) in enumerate(crawled.items(), 1):
            print(f"  [{i}/{len(crawled)}] {raw.get('title', url)[:50]}...")
            prompt = build_product_prompt(raw)
            out = call_volcengine(prompt, max_tokens=3000)
            if i < len(crawled):
                time.sleep(LLM_DELAY_SEC)
            if not out:
                continue
            parsed = parse_json_from_llm(out)
            if parsed and parsed.get("items"):
                item = parsed["items"][0]
                item["source_url"] = item.get("source_url") or url
                product_core_params_list.append(item)
                link_to_core_params[url] = item
                print(f"    ✓ {item.get('model', '')}")
            else:
                print(f"    解析失败，跳过")

        if product_core_params_list:
            out_path = os.path.join(output_dir, f"product_core_params_{timestamp}.json")
            payload = {
                "extraction_time": datetime.now().isoformat(),
                "total_products": len(product_core_params_list),
                "items": product_core_params_list,
            }
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            print(f"产品核心参数已保存: {out_path}")

    # ---------- 步骤4：LLM 方案总结 + 方案 JSON ----------
    solution_results = []
    if not skip_solution_llm:
        print("\n" + "=" * 60)
        print("步骤4：LLM 方案总结 + 方案 JSON")
        for subdir in subdirs:
            json_path = os.path.join(base_dir, subdir, "complete_data.json")
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                print(f"  [跳过] {subdir}: {e}")
                continue
            print(f"  处理方案: {subdir}")
            prompt = build_solution_prompt(data)
            out = call_volcengine(prompt, max_tokens=4000)
            time.sleep(LLM_DELAY_SEC)
            if not out:
                solution_results.append({"solution_dir": subdir, "error": "API 无返回"})
                continue
            sol_json = parse_solution_json_from_llm(out)
            if sol_json:
                sol_json["solution_dir"] = subdir
                if link_to_core_params:
                    sol_json = merge_core_params_into_solution(sol_json, link_to_core_params)
                solution_results.append(sol_json)
                print(f"    ✓ {sol_json.get('solution_name', subdir)[:40]}...")
            else:
                solution_results.append({"solution_dir": subdir, "raw_response": out[:500]})
                print("    解析 JSON 失败")

        if solution_results:
            out_path = os.path.join(output_dir, f"solution_summaries_{timestamp}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(solution_results, f, ensure_ascii=False, indent=2)
            print(f"方案结果已保存: {out_path}")

    # ---------- 步骤5：汇总说明 ----------
    index_path = os.path.join(output_dir, f"index_{timestamp}.json")
    index = {
        "pipeline_time": datetime.now().isoformat(),
        "base_dir": base_dir,
        "subdirs": subdirs,
        "product_links_count": len(product_links),
        "crawled_count": len(crawled),
        "product_core_params_count": len(product_core_params_list),
        "solution_count": len([r for r in solution_results if "solution_name" in r]),
        "product_links_file": os.path.basename(links_path),
        "output_dir": output_dir,
    }
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print("\n" + "=" * 60)
    print("管线完成。索引: " + index_path)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="知识图谱数据管线：complete_data → 爬产品 → 产品核心参数 → 方案 JSON")
    parser.add_argument("--base-dir", default=BASE_DIR, help="analog_devices_data_test 所在目录")
    parser.add_argument("--top-n", type=int, default=TOP_N_SUBDIRS, help="取前 N 个子目录")
    parser.add_argument("--output-dir", default=OUTPUT_DIR, help="输出目录")
    parser.add_argument("--skip-crawl", action="store_true", help="跳过爬取，使用已有 crawled_products_*.json")
    parser.add_argument("--skip-product-llm", action="store_true", help="跳过产品核心参数 LLM")
    parser.add_argument("--skip-solution-llm", action="store_true", help="跳过方案总结 LLM")
    args = parser.parse_args()
    run_pipeline(
        base_dir=args.base_dir,
        top_n=args.top_n,
        output_dir=args.output_dir,
        skip_crawl=args.skip_crawl,
        skip_product_llm=args.skip_product_llm,
        skip_solution_llm=args.skip_solution_llm,
    )
