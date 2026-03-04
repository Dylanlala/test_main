"""
从 analog_test1（或指定数据根）各 solution 的 complete_data.json + signal_chain_mapping_for_rag.json
+ signal_chain_descriptions/*.txt 构建 RAG 文档列表。

Chunk 设计：
- 方案级：每个 solution 一条，含 page_info、产品列表、本方案含 N 条信号链及 chain_id/list_name。
- 信号链级：每条链一条，含 chain_id、list_name、描述正文（器件+流向+应用场景）、器件↔CSV 映射。
写入前对 description 做规范截取（仅保留 ### 1～### 3），避免推理口语污染检索。
"""
import json
import os
import re
import sys
from typing import List, Dict, Any, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from adi_rag_pipeline.config import ANALOG_DATA_ROOT, RAG_BUILD_DOCS_PATH

MAPPING_JSON_FILENAME = "signal_chain_mapping_for_rag.json"
DESCRIPTION_SUBDIR = "signal_chain_descriptions"
COMPLETE_DATA_FILENAME = "complete_data.json"


def _extract_clean_description(raw_text: str) -> str:
    """只保留从「### 1. 器件与模块列表」到「### 3. 应用场景」后第一行，去掉推理/口语。"""
    if not (raw_text and raw_text.strip()):
        return raw_text or ""
    text = raw_text.strip()
    start_marker = "### 1. 器件与模块列表"
    start = text.find(start_marker)
    if start == -1:
        for alt in ("### 1.  器件与模块列表", "## 1. 器件与模块列表"):
            start = text.find(alt)
            if start != -1:
                break
    if start == -1:
        return text
    end_marker = "### 3. 应用场景"
    end_idx = text.find(end_marker, start)
    if end_idx == -1:
        segment = text[start:]
    else:
        after_sec3 = end_idx + len(end_marker)
        rest = text[after_sec3:]
        i = 0
        for i, ch in enumerate(rest):
            if not (ch == "\n" or ch.isspace()):
                break
        else:
            return text[start:after_sec3].strip()
        line_end = rest.find("\n", i)
        if line_end == -1:
            end_pos = len(text)
        else:
            end_pos = after_sec3 + line_end + 1
        app_line = rest[i : line_end if line_end != -1 else None].strip()
        if re.match(r"^(哦对|不对|首先|然后|是不是|不要任何多余|就按这个输出|检查有没有漏)", app_line):
            segment = text[start:end_idx]
        else:
            segment = text[start:end_pos]
    clean = segment.strip()
    lines = clean.split("\n")
    while lines:
        last = lines[-1].strip()
        if not last:
            lines.pop()
            continue
        if re.search(r"^(哦对|不对|首先|然后|是不是|不要任何多余|就按这个输出|检查有没有漏)", last):
            lines.pop()
            continue
        break
    return "\n".join(lines).strip() or clean


def _build_solution_chunk(solution_dir: str, solution_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """构建方案级 chunk：page_info + 产品概要 + 信号链列表。"""
    page_info = data.get("page_info") or {}
    title = page_info.get("title", solution_id)
    nav = page_info.get("navigation_path", "")
    keywords = page_info.get("keywords", "")
    description = page_info.get("description", "")
    overview = page_info.get("component_overview", "")
    page_url = page_info.get("url", "")

    value_and_benefits = data.get("value_and_benefits") or {}
    benefits_content = value_and_benefits.get("contents", "")
    benefits_list = value_and_benefits.get("characteristics") or []

    products_text = []
    for key in ("hardware_products", "evaluation_products", "reference_products"):
        for p in data.get(key) or []:
            if isinstance(p, dict):
                model = p.get("model") or p.get("model_name", "")
                desc = p.get("description", "")
                if model:
                    products_text.append(f"型号 {model}：{desc}")

    chains = data.get("signal_chains", {}).get("chains") or []
    chain_summary_parts = []
    for c in chains:
        cid = c.get("chain_id", "")
        name = c.get("list_name", "")
        if cid or name:
            chain_summary_parts.append(f"链 {cid}：{name}" if cid else name)

    text_parts = [
        f"方案名称：{title}",
        f"导航路径：{nav}",
        f"关键词：{keywords}",
        f"描述：{description}",
        f"概述：{overview}",
    ]
    if benefits_content:
        text_parts.append(f"价值与收益：{benefits_content}")
    if benefits_list:
        text_parts.append("特点：" + "；".join(benefits_list))
    text_parts.append("产品与型号：" + ("\n".join(products_text) if products_text else "（无）"))
    if chain_summary_parts:
        text_parts.append("本方案信号链：" + "；".join(chain_summary_parts))

    text = "\n".join(text_parts)
    if not text.strip():
        return None
    return {
        "text": text,
        "metadata": {
            "solution_id": solution_id,
            "source": "solution",
            "title": title,
            "page_url": page_url,
        },
    }


def _build_chain_chunk(
    solution_id: str,
    chain_id: str,
    list_name: str,
    description_text: str,
    mapping_content: str,
    csv_files_for_chain: List[str],
    description_clean: bool = True,
) -> Dict[str, Any]:
    """构建信号链级 chunk：描述 + 器件↔CSV 映射。"""
    if description_clean and description_text.strip():
        description_text = _extract_clean_description(description_text)
    parts = [f"信号链 {chain_id}：{list_name}", "", "【器件与信号流向】", description_text.strip() or "（无描述）"]
    if mapping_content:
        parts.append("")
        parts.append("【器件与选型表映射】")
        parts.append(mapping_content.strip())
    if csv_files_for_chain:
        parts.append("")
        parts.append("本链选型表 CSV：" + "；".join(csv_files_for_chain[:20]))
        if len(csv_files_for_chain) > 20:
            parts[-1] += f" 等共 {len(csv_files_for_chain)} 个文件"
    text = "\n".join(parts)
    return {
        "text": text,
        "metadata": {
            "solution_id": solution_id,
            "chain_id": chain_id,
            "list_name": list_name,
            "source": "signal_chain",
            "has_csv": len(csv_files_for_chain) > 0,
            "csv_count": len(csv_files_for_chain),
            "csv_files_for_chain": csv_files_for_chain,
        },
    }


def build_docs_for_solution(solution_dir: str, solution_id: str) -> List[Dict[str, Any]]:
    """单个方案目录下生成所有 chunk（1 个方案级 + N 个信号链级）。"""
    docs = []
    complete_path = os.path.join(solution_dir, COMPLETE_DATA_FILENAME)
    data = {}
    if os.path.isfile(complete_path):
        try:
            with open(complete_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass

    solution_chunk = _build_solution_chunk(solution_dir, solution_id, data)
    if solution_chunk:
        docs.append(solution_chunk)

    mapping_path = os.path.join(solution_dir, MAPPING_JSON_FILENAME)
    desc_dir = os.path.join(solution_dir, DESCRIPTION_SUBDIR)
    if not os.path.isfile(mapping_path):
        return docs

    try:
        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping_data = json.load(f)
    except Exception:
        return docs

    chains_info = data.get("signal_chains", {}).get("chains") or []
    chain_name_by_id = {str(c.get("chain_id", "")): c.get("list_name", "") for c in chains_info if isinstance(c, dict)}

    for cid, info in mapping_data.items():
        if not isinstance(info, dict):
            continue
        list_name = info.get("list_name") or chain_name_by_id.get(cid, "")
        if not list_name and "description_file" in info:
            list_name = f"信号链 {cid}"
        description_file = info.get("description_file", "")
        mapping_content = info.get("mapping_content", "")
        csv_files = info.get("csv_files_for_chain") or []

        description_text = ""
        if description_file and os.path.isdir(desc_dir):
            desc_path = os.path.join(desc_dir, description_file)
            if not os.path.isfile(desc_path):
                desc_path = os.path.join(desc_dir, f"signal_chain_{cid}_description.txt")
            if os.path.isfile(desc_path):
                try:
                    with open(desc_path, "r", encoding="utf-8") as f:
                        description_text = f.read()
                except Exception:
                    pass

        chain_chunk = _build_chain_chunk(
            solution_id=solution_id,
            chain_id=cid,
            list_name=list_name,
            description_text=description_text,
            mapping_content=mapping_content,
            csv_files_for_chain=csv_files,
            description_clean=True,
        )
        docs.append(chain_chunk)

    return docs


def build_all_docs(data_root: str) -> List[Dict[str, Any]]:
    """遍历数据根下所有方案目录，生成 RAG 文档列表。"""
    docs = []
    if not os.path.isdir(data_root):
        return docs
    for name in sorted(os.listdir(data_root)):
        solution_dir = os.path.join(data_root, name)
        if not os.path.isdir(solution_dir):
            continue
        if not os.path.isfile(os.path.join(solution_dir, COMPLETE_DATA_FILENAME)):
            continue
        docs.extend(build_docs_for_solution(solution_dir, name))
    return docs


def run_build_and_save(data_root: str = None, out_path: str = None) -> List[Dict[str, Any]]:
    """生成文档列表并写入 JSON。"""
    data_root = data_root or ANALOG_DATA_ROOT
    out_path = out_path or RAG_BUILD_DOCS_PATH
    docs = build_all_docs(data_root)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)
    print(f"Built {len(docs)} documents -> {out_path}")
    return docs


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="构建信号链 RAG 文档列表（方案级+信号链级）")
    ap.add_argument("--data-root", default=ANALOG_DATA_ROOT, help="方案数据根目录，默认 analog_test1")
    ap.add_argument("--out", default=None, help="输出 JSON 路径")
    args = ap.parse_args()
    run_build_and_save(args.data_root, args.out)
