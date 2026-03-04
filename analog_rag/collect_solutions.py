# 扫描 analog_test1，收集方案文本（含 complete_data、signal_chain_descriptions、CSV 选型表）
import os
import json
import glob
from typing import List, Dict, Any, Optional
from .config import ANALOG_TEST1_ROOT
from .csv_reader import read_csv_parts, format_parts_for_text


def load_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: 无法读取 {path}: {e}")
        return None


def _collect_signal_chain_and_csv(
    dir_path: str,
    chain_id: str,
    mapping_list: List[Dict],
    csv_subdir: str = "exports_signal_chain_csv",
) -> tuple:
    """
    根据 mapping（device -> csv_files）读取各 CSV，返回 (用于 input_text 的字符串, 用于 scheme_details 的 device_parts 列表)。
    """
    csv_dir = os.path.join(dir_path, csv_subdir)
    text_parts = []
    device_parts_list = []
    for item in mapping_list:
        device = item.get("device") or ""
        csv_files = item.get("csv_files") or []
        if not device or not csv_files:
            continue
        all_parts = []
        for csv_name in csv_files[:5]:
            csv_path = os.path.join(csv_dir, csv_name)
            parts = read_csv_parts(csv_path, max_parts=15, max_desc_len=150)
            all_parts.extend(parts)
        if not all_parts:
            text_parts.append(f"信号链 {chain_id} 模块 {device}: 无选型表数据")
            device_parts_list.append({"device": device, "chain_id": chain_id, "parts": [], "summary": ""})
            continue
        summary = format_parts_for_text(all_parts[:15], sep="; ")
        text_parts.append(f"信号链 {chain_id} 模块 {device} 可选型号与参数: {summary}")
        device_parts_list.append({
            "device": device,
            "chain_id": chain_id,
            "parts": all_parts[:20],
            "summary": summary[:800],
        })
    return "\n".join(text_parts), device_parts_list


def collect_solutions(root: str = None) -> List[Dict[str, Any]]:
    """
    扫描方案根目录，返回每个解决方案的 scheme_id、路径、用于关键词提取的合并文本，
    以及信号链模块→CSV 型号/参数摘要（供检索结果返回）。
    """
    root = root or ANALOG_TEST1_ROOT
    if not os.path.isdir(root):
        print(f"Warning: 方案根目录不存在: {root}")
        return []

    solutions = []
    for name in os.listdir(root):
        dir_path = os.path.join(root, name)
        if not os.path.isdir(dir_path):
            continue
        complete_path = os.path.join(dir_path, "complete_data.json")
        if not os.path.isfile(complete_path):
            continue

        complete_data = load_json(complete_path)
        if not complete_data:
            continue

        scheme_id = name
        text_parts = []

        # ---------- 1. complete_data.json ----------
        page_info = complete_data.get("page_info") or {}
        if page_info.get("title"):
            text_parts.append(f"方案名称/标题: {page_info['title']}")
        if page_info.get("description"):
            text_parts.append(f"方案描述: {page_info['description']}")
        if page_info.get("keywords"):
            text_parts.append(f"关键词: {page_info['keywords']}")
        if page_info.get("navigation_path"):
            text_parts.append(f"分类路径: {page_info['navigation_path']}")

        value_and_benefits = complete_data.get("value_and_benefits") or {}
        if value_and_benefits.get("title"):
            text_parts.append(f"价值与优势标题: {value_and_benefits['title']}")
        if value_and_benefits.get("contents"):
            text_parts.append(f"价值与优势内容: {value_and_benefits['contents']}")
        if value_and_benefits.get("characteristics"):
            chars = value_and_benefits["characteristics"]
            if isinstance(chars, list):
                text_parts.append("特性: " + "；".join(chars))
            else:
                text_parts.append(f"特性: {chars}")

        # ---------- 2. signal_chain_mapping_for_rag.json（描述摘要）----------
        rag_mapping_path = os.path.join(dir_path, "signal_chain_mapping_for_rag.json")
        if os.path.isfile(rag_mapping_path):
            rag_mapping = load_json(rag_mapping_path)
            if isinstance(rag_mapping, dict):
                for cid, chain_info in rag_mapping.items():
                    if isinstance(chain_info, dict) and chain_info.get("description_preview"):
                        text_parts.append(f"信号链 {cid} 描述摘要: {chain_info['description_preview'][:2000]}")

        # ---------- 3. signal_chain_descriptions/*.json + description_to_csv_mapping + CSV ----------
        desc_dir = os.path.join(dir_path, "signal_chain_descriptions")
        mapping_glob = os.path.join(dir_path, "signal_chain_*_description_to_csv_mapping.json")
        all_device_parts = []

        for mapping_path in glob.glob(mapping_glob):
            base = os.path.basename(mapping_path)
            # signal_chain_0004_description_to_csv_mapping.json -> 0004
            if "signal_chain_" in base and "_description_to_csv_mapping.json" in base:
                chain_id = base.replace("signal_chain_", "").replace("_description_to_csv_mapping.json", "").strip()
            else:
                continue
            mapping_data = load_json(mapping_path)
            mapping_list = mapping_data.get("mapping") if isinstance(mapping_data, dict) else []
            if not mapping_list:
                continue

            # 3.1 该信号链的 devices + signal_flow + application_scene
            fast_path = os.path.join(desc_dir, f"signal_chain_{chain_id}_fast.json")
            if os.path.isfile(fast_path):
                fast_data = load_json(fast_path)
                if fast_data:
                    devices = fast_data.get("devices") or []
                    for d in devices:
                        nm = d.get("name") or ""
                        desc = d.get("description") or ""
                        if nm or desc:
                            text_parts.append(f"信号链 {chain_id} 器件 {nm}: {desc}")
                    flow = fast_data.get("signal_flow") or {}
                    if flow.get("main"):
                        text_parts.append(f"信号链 {chain_id} 主信号流: {flow['main'][:1500]}")
                    if flow.get("branches"):
                        text_parts.append(f"信号链 {chain_id} 分支: {'; '.join(flow['branches'][:5])}")
                    if fast_data.get("application_scene"):
                        text_parts.append(f"信号链 {chain_id} 应用场景: {fast_data['application_scene']}")

            # 3.2 模块→CSV 选型表：读取型号与参数
            chain_text, device_parts_list = _collect_signal_chain_and_csv(dir_path, chain_id, mapping_list)
            text_parts.append(chain_text)
            all_device_parts.extend(device_parts_list)

        input_text = "\n\n".join(text_parts) if text_parts else ""

        solutions.append({
            "scheme_id": scheme_id,
            "scheme_name": name,
            "dir_path": dir_path,
            "complete_data": complete_data,
            "input_text": input_text,
            "complete_path": complete_path,
            "device_parts_summary": all_device_parts,  # 供 scheme_details 和 format_cases 返回型号/参数
        })
    return solutions
