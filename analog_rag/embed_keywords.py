# 与 lina_code_new 一致：将各方案的关键词向量化，保存 npy + csv；并生成 scheme_details.json 供检索结果展示
import os
import re
import json
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from .config import KEYWORD_EXTRACTION_DIR, EMBEDDINGS_OUTPUT_DIR, ANALOG_TEST1_ROOT
from .collect_solutions import collect_solutions


def extract_keywords_from_extraction(extraction: Dict[str, Any]) -> Optional[Dict[str, list]]:
    """从单条 extraction JSON 中解析出 keywords 字典。"""
    if "keywords" in extraction and isinstance(extraction["keywords"], dict):
        return extraction["keywords"]
    raw = extraction.get("extracted_keywords") or ""
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if "keywords" in data:
            return data["keywords"]
    except json.JSONDecodeError:
        pass
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start:end])
            if "keywords" in data:
                return data["keywords"]
        except json.JSONDecodeError:
            pass
    return None


def load_all_extractions(extraction_dir: str) -> List[Dict[str, Any]]:
    """加载 KEYWORD_EXTRACTION_DIR 下所有 *_extraction.json。"""
    if not os.path.isdir(extraction_dir):
        return []
    records = []
    for f in os.listdir(extraction_dir):
        if f.endswith("_extraction.json"):
            path = os.path.join(extraction_dir, f)
            try:
                with open(path, "r", encoding="utf-8") as fp:
                    records.append(json.load(fp))
            except Exception as e:
                print(f"Warning: 无法加载 {path}: {e}")
    return records


def build_scheme_details(solutions: List[Dict]) -> Dict[str, Dict[str, Any]]:
    """从 collect_solutions 结果构建 scheme_id -> {title, description, characteristic, signal_chain_parts} 供 format_cases_for_llm。"""
    out = {}
    for sol in solutions:
        scheme_id = sol["scheme_id"]
        complete = sol.get("complete_data") or {}
        page = complete.get("page_info") or {}
        value = complete.get("value_and_benefits") or {}
        chars = value.get("characteristics") or []
        if isinstance(chars, list):
            characteristic = "；".join(chars) if chars else ""
        else:
            characteristic = str(chars) if chars else ""
        device_parts = sol.get("device_parts_summary") or []
        signal_chain_parts_text = _format_device_parts_for_llm(device_parts)
        out[scheme_id] = {
            "title": page.get("title") or scheme_id,
            "description": page.get("description") or value.get("contents") or "",
            "characteristic": characteristic,
            "scheme_name": scheme_id,
            "signal_chain_parts": signal_chain_parts_text,
        }
    return out


def _format_device_parts_for_llm(device_parts_list: List[Dict], max_chars: int = 2000) -> str:
    """将 device_parts_summary 格式化为一段文本，供 LLM 参考（模块→可选型号与参数）。"""
    if not device_parts_list:
        return ""
    parts = []
    for item in device_parts_list:
        device = item.get("device") or ""
        chain_id = item.get("chain_id") or ""
        summary = item.get("summary") or ""
        if not summary and item.get("parts"):
            from .csv_reader import format_parts_for_text
            summary = format_parts_for_text(item["parts"][:10], sep="; ")
        if device and summary:
            parts.append(f"信号链{chain_id} 模块【{device}】可选型号与参数: {summary}")
    s = "\n".join(parts)
    return s[:max_chars] if len(s) > max_chars else s


def run_embed(
    extraction_dir: str = None,
    output_dir: str = None,
    embedding_model_name: str = "aspire/acge_text_embedding",
    local_files_only: bool = True,
    analog_root: str = None,
) -> tuple:
    """
    读取所有提取 JSON，按关键词展开并向量化，保存：
    - keyword_embeddings.npy
    - keyword_metadata.csv (scheme_id, category, keyword)
    - scheme_details.json (scheme_id -> title, description, characteristic)
    返回 (embeddings_array, metadata_df, scheme_details_dict)。
    """
    extraction_dir = extraction_dir or KEYWORD_EXTRACTION_DIR
    output_dir = output_dir or EMBEDDINGS_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError("请安装 sentence-transformers: pip install sentence-transformers")

    model = SentenceTransformer(embedding_model_name, local_files_only=local_files_only)

    records = load_all_extractions(extraction_dir)
    if not records:
        print("未找到任何 *_extraction.json，请先运行关键词提取")
        return np.array([]), pd.DataFrame(), {}

    all_scheme_ids = []
    all_categories = []
    all_keywords = []
    for rec in records:
        scheme_id = rec.get("scheme_id", "")
        keywords_dict = extract_keywords_from_extraction(rec)
        if not keywords_dict:
            continue
        for cat, kws in keywords_dict.items():
            if not isinstance(kws, list):
                continue
            for kw in kws:
                if kw and isinstance(kw, str) and kw.strip():
                    all_scheme_ids.append(scheme_id)
                    all_categories.append(cat)
                    all_keywords.append(kw.strip())

    if not all_keywords:
        print("没有有效关键词可向量化")
        return np.array([]), pd.DataFrame(), {}

    embeddings = model.encode(all_keywords, show_progress_bar=True)
    embeddings = np.array(embeddings, dtype=np.float32)

    metadata_df = pd.DataFrame({
        "scheme_id": all_scheme_ids,
        "category": all_categories,
        "keyword": all_keywords,
    })
    np.save(os.path.join(output_dir, "keyword_embeddings.npy"), embeddings)
    metadata_df.to_csv(os.path.join(output_dir, "keyword_metadata.csv"), index=False, encoding="utf-8-sig")

    solutions = collect_solutions(analog_root or ANALOG_TEST1_ROOT)
    scheme_details = build_scheme_details(solutions)
    details_path = os.path.join(output_dir, "scheme_details.json")
    with open(details_path, "w", encoding="utf-8") as f:
        json.dump(scheme_details, f, ensure_ascii=False, indent=2)

    print(f"已保存: {output_dir}, 关键词数={len(all_keywords)}, 方案数={len(set(all_scheme_ids))}")
    return embeddings, metadata_df, scheme_details
