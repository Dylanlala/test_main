# 从选型表 CSV 中读取型号(Part#)与参数(Description 等)，供 RAG 索引与检索结果使用
import os
import re
from typing import List, Dict, Any, Optional

try:
    import pandas as pd
except ImportError:
    pd = None


def _detect_header_row(csv_path: str) -> int:
    """检测表头行：含 Part# 或 型号 或 Description 的行。"""
    if not pd:
        return 0
    try:
        for i in range(4):
            df = pd.read_csv(csv_path, encoding="utf-8", nrows=0, skiprows=i, header=0)
            cols = " ".join(str(c).lower() for c in df.columns)
            if "part" in cols or "型号" in cols or "description" in cols or "描述" in cols:
                return i
    except Exception:
        pass
    return 2  # 常见：前两行是 组件名称/模块名称，第三行是 Part #, Description, ...


def _find_column(df, *candidates: str) -> Optional[str]:
    """在 DataFrame 列名中查找第一个包含 candidates 之一的列。"""
    for c in candidates:
        for col in df.columns:
            if c.lower() in str(col).lower():
                return col
    return None


def read_csv_parts(
    csv_path: str,
    max_parts: int = 30,
    max_desc_len: int = 200,
    param_columns: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    读取选型表 CSV，返回型号与参数列表。
    支持表头在第 0/1/2 行，自动识别 Part#/型号、Description/Product Description/描述 等列。
    """
    if not pd or not os.path.isfile(csv_path):
        return []
    try:
        header_row = _detect_header_row(csv_path)
        df = pd.read_csv(csv_path, encoding="utf-8", header=header_row)
        if df.empty:
            return []
        part_col = _find_column(df, "part #", "part#", "型号", "part")
        desc_col = _find_column(df, "description", "product description", "描述", "说明")
        if not part_col:
            return []
        out = []
        for _, row in df.iterrows():
            if len(out) >= max_parts:
                break
            part_num = row.get(part_col)
            if pd.isna(part_num) or not str(part_num).strip():
                continue
            part_num = str(part_num).strip()
            if re.match(r"^https?://", part_num):
                continue
            desc = ""
            if desc_col:
                d = row.get(desc_col)
                if not pd.isna(d) and str(d).strip():
                    desc = str(d).strip()[:max_desc_len]
            param_parts = []
            for col in df.columns:
                if col in (part_col, desc_col):
                    continue
                v = row.get(col)
                if pd.isna(v) or not str(v).strip():
                    continue
                s = str(v).strip()
                if len(s) > 60 or s.startswith("http"):
                    continue
                param_parts.append(f"{col}:{s}")
            params_str = " ".join(param_parts[:6]) if param_parts else ""
            out.append({
                "part_number": part_num,
                "description": desc,
                "params_preview": params_str,
            })
        return out
    except Exception as e:
        return []


def format_parts_for_text(parts: List[Dict[str, Any]], sep: str = "; ") -> str:
    """将 read_csv_parts 的结果格式化为一段文本，用于拼入 RAG 输入或检索结果。"""
    if not parts:
        return ""
    bits = []
    for p in parts[:20]:
        line = p.get("part_number", "")
        if p.get("description"):
            line += f" ({p['description']}"
            if p.get("params_preview"):
                line += f", {p['params_preview']}"
            line += ")"
        elif p.get("params_preview"):
            line += f" ({p['params_preview']})"
        bits.append(line)
    return sep.join(bits)
