#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析 analog_test1 下某个方案目录的所有文件与内容，并结合「图转文」描述，用 LLM 生成结构化分析报告。
便于人工审阅方案定位、信号链、选型表覆盖、描述与 CSV 对应关系等。

用法:
  python analyze_solution_dir.py "下一代气象雷达"
  python analyze_solution_dir.py "analog_test1/下一代气象雷达"
  python analyze_solution_dir.py "analog_test1/下一代气象雷达" --max-chars 15000 --out report.md
"""
import argparse
import csv
import json
import os
import sys
from typing import Any, Dict, List, Optional

# 项目根 = fae_main
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 默认方案数据根
ANALOG_TEST1_ROOT = os.path.join(PROJECT_ROOT, "analog_test1")
SIGNAL_CHAIN_DESCRIPTIONS_FILENAME = "output.txt"
MAX_CONTEXT_CHARS = 14000  # 发给 LLM 的上下文上限（可配置）


def get_llm_client():
    """使用与 adi_rag_pipeline 一致的 LLM 配置（豆包 Ark / OpenAI 兼容）。"""
    try:
        from adi_rag_pipeline.config import get_llm_api_key, LLM_BASE_URL
        api_key = get_llm_api_key()
    except Exception:
        api_key = ""
        key_path = os.path.join(PROJECT_ROOT, "static", "static/key1.txt")
        if os.path.isfile(key_path):
            with open(key_path, "r", encoding="utf-8") as f:
                api_key = f.read().strip()
        if not api_key:
            api_key = os.getenv("LLM_API_KEY", "") or os.getenv("MAIN_API_KEY", "")
    if not api_key:
        raise ValueError("未配置 API Key：请设置 static/key1.txt 或环境变量 LLM_API_KEY / ARK_API_KEY")
    try:
        from adi_rag_pipeline.config import LLM_BASE_URL
        base_url = LLM_BASE_URL
    except Exception:
        base_url = os.getenv("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3/bots")
    from openai import OpenAI
    return OpenAI(base_url=base_url, api_key=api_key)


def get_llm_model() -> str:
    try:
        from adi_rag_pipeline.config import LLM_MODEL
        return LLM_MODEL or "doubao-seed-2-0-pro-260215"
    except Exception:
        return os.getenv("LLM_MODEL", "doubao-seed-2-0-pro-260215")


def list_dir_tree(root: str, prefix: str = "", max_files: int = 200) -> List[str]:
    """列出目录结构（扁平化，带相对路径），最多 max_files 条。"""
    lines = []
    try:
        for name in sorted(os.listdir(root))[:50]:
            path = os.path.join(root, name)
            rel = os.path.join(prefix, name)
            if os.path.isfile(path):
                lines.append(rel)
                if len(lines) >= max_files:
                    return lines
            else:
                lines.append(rel + "/")
                sub = list_dir_tree(path, rel, max_files - len(lines))
                lines.extend(sub[: max_files - len(lines)])
                if len(lines) >= max_files:
                    return lines
    except Exception:
        pass
    return lines


def read_json_safe(path: str) -> Optional[Dict]:
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def summarize_complete_data(data: Dict) -> str:
    """从 complete_data.json 提取摘要（页面信息、产品数量、信号链列表）。"""
    parts = []
    page = data.get("page_info") or {}
    parts.append("【页面信息】")
    parts.append(f"  标题: {page.get('title', '')}")
    parts.append(f"  导航: {page.get('navigation_path', '')}")
    parts.append(f"  关键词: {page.get('keywords', '')}")
    parts.append(f"  描述: {(page.get('description') or '')[:300]}")
    parts.append(f"  概述: {(page.get('component_overview') or '')[:400]}")

    for key in ("hardware_products", "evaluation_products", "reference_products"):
        arr = data.get(key) or []
        if arr:
            parts.append(f"【{key}】共 {len(arr)} 条")
            for i, p in enumerate(arr[:8]):
                if isinstance(p, dict):
                    model = p.get("model") or p.get("model_name") or ""
                    desc = (p.get("description") or "")[:80]
                    parts.append(f"  - {model}: {desc}")

    sc = data.get("signal_chains") or {}
    chains = sc.get("chains") or []
    parts.append(f"【信号链】共 {len(chains)} 条")
    for c in chains:
        cid = c.get("chain_id") or ""
        name = c.get("list_name") or ""
        hotspots = c.get("signal_chain_hotspots") or []
        parts.append(f"  - chain_id={cid}, list_name={name}, 热点数={len(hotspots)}")
        for h in hotspots[:5]:
            comp = h.get("component_name") or ""
            mod = h.get("module_name") or ""
            parts.append(f"      {comp} -> {mod}")
        if len(hotspots) > 5:
            parts.append(f"      ... 共 {len(hotspots)} 个热点")

    return "\n".join(parts)


def summarize_products_csv(path: str, max_rows: int = 15) -> str:
    """读取 products_list.csv 前几行与列名。"""
    if not os.path.isfile(path):
        return "(无此文件)"
    lines = ["【products_list.csv】"]
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)
        if not rows:
            return "\n".join(lines) + "\n(空表)"
        lines.append("列: " + " | ".join(rows[0]))
        for row in rows[1:max_rows]:
            lines.append("  " + " | ".join((str(c)[:40] for c in row)))
        if len(rows) > max_rows:
            lines.append(f"  ... 共 {len(rows)} 行")
    except Exception as e:
        lines.append(f"(读取失败: {e})")
    return "\n".join(lines)


def list_csv_files(exports_dir: str, max_list: int = 80) -> str:
    """列出 exports_signal_chain_csv 下的 CSV，按 chain 或文件名分组简述。"""
    if not os.path.isdir(exports_dir):
        return "(无 exports_signal_chain_csv 目录)"
    files = [f for f in os.listdir(exports_dir) if f.endswith(".csv")]
    files.sort()
    lines = [f"【exports_signal_chain_csv】共 {len(files)} 个 CSV"]
    # 按前缀 (chain_id) 分组
    by_prefix: Dict[str, List[str]] = {}
    for f in files:
        prefix = f.split("_")[0] if "_" in f else ""
        by_prefix.setdefault(prefix, []).append(f)
    for prefix in sorted(by_prefix.keys()):
        names = by_prefix[prefix]
        lines.append(f"  chain/前缀 {prefix}: {len(names)} 个文件")
        for n in names[:12]:
            lines.append(f"    - {n}")
        if len(names) > 12:
            lines.append(f"    ... 其余 {len(names) - 12} 个")
    return "\n".join(lines)


def load_signal_chain_descriptions(path: str) -> str:
    """读取 signal_chain_descriptions.json 全文（用于图转文描述）。"""
    if not os.path.isfile(path):
        return "(本方案暂无 output.txt，图转文描述需另行生成)"
    data = read_json_safe(path)
    if not data:
        return "(文件为空或非 JSON)"
    chains = data.get("chains") or []
    if not chains:
        return "(chains 为空)"
    parts = ["【信号链图转文描述 output.txt】"]
    for c in chains:
        name = c.get("list_name") or c.get("chain_id") or ""
        desc = (c.get("description") or "").strip()
        parts.append(f"\n--- 信号链: {name} ---\n{desc[:2500]}")
        if len(desc) > 2500:
            parts.append("\n...(描述已截断)")
    return "\n".join(parts)


def load_mapping_md(dir_path: str) -> str:
    """若目录下有 *description_to_csv_mapping.md 或 *mapping*.md，读取摘要。"""
    parts = []
    try:
        for name in os.listdir(dir_path):
            if "mapping" in name.lower() and name.endswith(".md"):
                path = os.path.join(dir_path, name)
                if os.path.isfile(path):
                    with open(path, "r", encoding="utf-8") as f:
                        raw = f.read()
                    parts.append(f"【{name}】\n{raw[:2000]}")
                    if len(raw) > 2000:
                        parts.append("\n...(已截断)")
    except Exception:
        pass
    return "\n".join(parts) if parts else ""


def build_context(solution_dir: str, max_chars: int = MAX_CONTEXT_CHARS) -> str:
    """汇总目录内所有需要分析的内容，供 LLM 使用。"""
    parts = [f"# 方案目录: {os.path.basename(solution_dir)}\n路径: {solution_dir}\n"]

    # 1. 目录结构
    tree = list_dir_tree(solution_dir, prefix="", max_files=120)
    parts.append("\n## 1. 目录与文件列表\n" + "\n".join(tree))

    # 2. complete_data.json 摘要
    complete_path = os.path.join(solution_dir, "complete_data.json")
    data = read_json_safe(complete_path)
    if data:
        parts.append("\n## 2. complete_data.json 摘要\n" + summarize_complete_data(data))
    else:
        parts.append("\n## 2. complete_data.json\n(无或无法解析)")

    # # 3. products_list.csv
    # products_path = os.path.join(solution_dir, "products_list.csv")
    # parts.append("\n## 3. " + summarize_products_csv(products_path))

    # 4. exports_signal_chain_csv
    exports_dir = os.path.join(solution_dir, "exports_signal_chain_csv")
    parts.append("\n## 4. " + list_csv_files(exports_dir))

    # 5. 图转文描述
    sc_desc_path = os.path.join(solution_dir, SIGNAL_CHAIN_DESCRIPTIONS_FILENAME)
    parts.append("\n## 5. " + load_signal_chain_descriptions(sc_desc_path))

    # 6. 描述与 CSV 映射文档（若有）
    mapping_text = load_mapping_md(solution_dir)
    if mapping_text:
        parts.append("\n## 6. 描述与 CSV 对应关系\n" + mapping_text)

    full = "\n".join(parts)
    if len(full) > max_chars:
        full = full[: max_chars] + "\n\n...(上下文已截断，超出字符上限)"
    return full


# ANALYSIS_PROMPT = """你是一位 ADI 解决方案与信号链分析专家。请根据下面「某方案目录的汇总内容」进行结构化分析，输出一份便于人工审阅的报告。
#
# ## 输入说明
# - 目录内包含：complete_data.json（页面信息、产品列表、信号链元数据）、products_list.csv、exports_signal_chain_csv（各信号链热点的选型表 CSV）、以及可能存在的 signal_chain_descriptions.json（框图图转文描述）和描述与 CSV 的映射文档。
#
# ## 请按以下结构输出分析报告（使用 Markdown，中文）
#
# ### 1. 方案定位与概述
# - 方案名称、应用场景、技术领域
# - 核心价值与关键特性（从 page_info / value_and_benefits 归纳）
#
# ### 2. 产品与器件覆盖
# - 硬件产品/评估板数量与代表性型号
# - 与信号链的对应关系（若有）
#
# ### 3. 信号链与选型表
# - 共有几条信号链、每条链的名称与 chain_id
# - 各链涉及的模块/组件类型（如 ADC、DAC、隔离、电源等）
# - exports_signal_chain_csv 的覆盖情况：是否与 complete_data 中的热点一致、是否有缺失或多余
#
# ### 4. 图转文描述与 CSV 对应
# - 若存在 signal_chain_descriptions.json：概括各条链的「图转文」描述要点（架构、模块、信号流）
# - 若存在描述↔CSV 映射文档：说明描述中的功能块与 CSV 选型表是否一一对应、一对多或缺失
# - 若暂无图转文描述：建议可对哪些信号链做图转文以提升 RAG/检索效果
#
# ### 5. 建议与注意点
# - 数据完整性：缺文件、缺描述、CSV 空行等
# - 后续可改进：如补全 signal_chain_descriptions、统一命名、选型表去重等
#
# 请直接输出上述分析报告，不要输出「输入内容」本身。"""

ANALYSIS_PROMPT = """你是一位 ADI 解决方案与信号链分析专家。请根据下面「某方案目录的汇总内容」进行结构化分析，输出一份csv文件的映射。

## 输入说明
- 目录内包含：complete_data.json（页面信息、产品列表、信号链元数据）、output.txt、exports_signal_chain_csv（各信号链热点的选型表 CSV）和描述与 CSV 的映射文档。

## 请按以下结构输出分析报告（使用 Markdown，中文）


图转文描述与 CSV 对应
exports_signal_chain_csv目录下有文件，请你根据生成的描述output.txt与其建立一一对应的关系。
- 若存在描述↔CSV 映射文档：说明描述中的功能块与 CSV 选型表是否一一对应、一对多或缺失

重点是图中的描述与CSV文件之间的映射建立。
请直接输出上述分析，不要输出「输入内容」本身。"""


def run_llm_analysis(context: str, client, model: str) -> str:
    """调用 LLM 生成分析报告。"""
    prompt = f"{ANALYSIS_PROMPT}\n\n---\n\n# 方案目录汇总内容（供分析）\n\n{context}"
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
        stream=False,
    )
    return (resp.choices[0].message.content or "").strip()


def main():
    parser = argparse.ArgumentParser(description="分析 analog_test1 下方案目录并用 LLM 生成分析报告")
    parser.add_argument(
        "solution",
        type=str,
        help="方案目录名或相对路径，如 '下一代气象雷达' 或 'analog_test1/下一代气象雷达'",
    )
    parser.add_argument(
        "--data-root",
        type=str,
        default=ANALOG_TEST1_ROOT,
        help="方案根目录，默认 analog_test1",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=MAX_CONTEXT_CHARS,
        help="发给 LLM 的上下文最大字符数",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="",
        help="分析报告输出路径，默认写在方案目录下的 solution_analysis_report.md",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="仅生成汇总上下文并保存为 solution_context.txt，不调用 LLM",
    )
    args = parser.parse_args()

    # 解析方案目录
    solution = args.solution.strip().replace("\\", "/")
    if solution.startswith("analog_test1/"):
        solution = solution.split("analog_test1/")[-1]
    solution_dir = os.path.join(args.data_root, solution)
    if not os.path.isdir(solution_dir):
        print(f"错误：目录不存在: {solution_dir}")
        sys.exit(1)

    print(f"方案目录: {solution_dir}")
    context = build_context(solution_dir, max_chars=args.max_chars)
    context_path = os.path.join(solution_dir, "solution_context.txt")
    with open(context_path, "w", encoding="utf-8") as f:
        f.write(context)
    print(f"已写入上下文: {context_path} ({len(context)} 字符)")

    if args.no_llm:
        print("已跳过 LLM 调用 (--no-llm)。")
        return

    print("正在调用 LLM 生成分析报告...")
    try:
        client = get_llm_client()
        model = get_llm_model()
        report = run_llm_analysis(context, client, model)
    except Exception as e:
        print(f"LLM 调用失败: {e}")
        sys.exit(1)

    out_path = args.out.strip() or os.path.join(solution_dir, "solution_analysis_report.md")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"已写入报告: {out_path}")
    print("\n--- 报告摘要（前 800 字）---\n")
    print(report[:800])
    if len(report) > 800:
        print("\n...")


if __name__ == "__main__":
    main()