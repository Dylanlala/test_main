# 与 lina_code_new 一致：对每个方案用 LLM 按四类提取关键词，保存为 JSON
import os
import re
import json
from typing import Dict, Any, Optional
from datetime import datetime
from .config import KEYWORD_EXTRACTION_DIR
from .collect_solutions import collect_solutions


# 与 lina 相同的四类关键词提取 prompt（技术方案描述 -> 解决方案类型/技术类型/核心组件/性能指标）
KEYWORD_EXTRACTION_PROMPT = """你是一名专业的电子工程师，负责分析技术方案文档并将其核心信息结构化。请严格遵循以下指令。

# 任务：
请从"技术方案描述"中提取所有相关关键词，并将它们分配到以下四个固定分类中。每个关键词只分配到一个分类。
1. 解决方案类型：该技术方案所实现的具体功能或解决的特定工程问题。通常是一个完整的解决方案名称或应用导向的描述（例如："便携式3D扫描系统"、"电源转换方案"）。避免使用过于技术性的术语，而是聚焦于方案的整体目的。**注意：提取不能包含"参考设计"这4个字**。
2. 技术类型：方案中采用的核心技术、方法、架构或功能（如：升压转换、同步整流）。
3. 核心组件：方案中提及的具体物理实体或芯片型号、名称（如：LM5122, TAS5611D2, MOSFET）。**注意：如果文中没有提及具体型号，仅描述了功能单元（如"转换器"、"放大器"），则此分类应为空数组。**
4. 性能指标：方案的关键电气参数、性能特征和量化指标（如：100W功率, 95%效率, 12V输出，低功耗，<1μA待机电流）。

# 提取原则：
1.  **高覆盖度**：要尽可能全面地捕捉所有核心信息点。
2.  **分类精准性**：必须严格遵守四个分类的定义边界，确保每个分类的纯粹性。
3.  **参数与上下文绑定**：所有关键参数（数值、频率、电压等）必须与它们所修饰的实体或状态完整结合。
4.  **保持术语完整且精确**：不要拆分专业术语。有数量或参数时必须与名词结合。
5.  **避免泛化词汇**：仅提取描述中明确出现或高度特定的技术概念。
6.  **严格去冗余和合并同义词**：如果描述中用不同说法指代同一事物，选择最标准的术语作为关键词。
7.  **捕获所有关键限定词和模式**：不要忽略"超过"、"高达"、"较低"、"标称"等限定词和模式描述。
8.  **解决方案类型精炼**：确保解决方案类型的关键词简洁、无冗余，且是高层概括。

# 输出格式：
请严格输出一个JSON对象，且只包含一个名为`keywords`的键，值为对象，键为分类名称，值为该分类下的关键词数组。例如 {{"keywords": {{"解决方案类型": ["音频系统"], "技术类型": ["升压转换"], "核心组件": [], "性能指标": []}}}}。数组内按重要性降序列出提取出的关键词字符串。

# 技术方案描述：
{input_text}
"""


def _parse_keywords_from_response(content: str) -> Optional[Dict[str, list]]:
    """从 LLM 回复中解析出 keywords 字典。"""
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    content = content.strip()
    try:
        data = json.loads(content)
        if "keywords" in data and isinstance(data["keywords"], dict):
            return data["keywords"]
    except json.JSONDecodeError:
        pass
    start = content.find("{")
    end = content.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            data = json.loads(content[start:end])
            if "keywords" in data and isinstance(data["keywords"], dict):
                return data["keywords"]
        except json.JSONDecodeError:
            pass
    return None


def extract_keywords_for_solution(
    input_text: str,
    scheme_id: str,
    client,  # OpenAI-compatible client
    model: str = "bot-20250618131857-l9ffp",
) -> Dict[str, Any]:
    """
    对单个方案的 input_text 调用 LLM 提取四类关键词。
    client: openai.OpenAI 兼容实例（如 server_wb 的 base_client）。
    """
    if not input_text or not input_text.strip():
        return {
            "scheme_id": scheme_id,
            "extracted_keywords": json.dumps({"keywords": {"解决方案类型": [], "技术类型": [], "核心组件": [], "性能指标": []}}),
            "keywords": {"解决方案类型": [], "技术类型": [], "核心组件": [], "性能指标": []},
        }
    prompt = KEYWORD_EXTRACTION_PROMPT.format(input_text=input_text[:12000])
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1024,
        )
        content = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"LLM 调用失败 scheme_id={scheme_id}: {e}")
        return {
            "scheme_id": scheme_id,
            "extracted_keywords": "",
            "keywords": {"解决方案类型": [], "技术类型": [], "核心组件": [], "性能指标": []},
        }
    keywords = _parse_keywords_from_response(content)
    if not keywords:
        keywords = {"解决方案类型": [], "技术类型": [], "核心组件": [], "性能指标": []}
    return {
        "scheme_id": scheme_id,
        "extracted_keywords": content,
        "keywords": keywords,
        "extraction_time": datetime.now().isoformat(),
    }


def run_keyword_extraction(
    client,
    model: str = "bot-20250618131857-l9ffp",
    analog_root: str = None,
    output_dir: str = None,
    skip_existing: bool = True,
) -> list:
    """
    扫描 analog_test1，对每个方案提取关键词并保存 JSON。
    返回所有方案的提取结果列表（用于后续 embed）。
    """
    output_dir = output_dir or KEYWORD_EXTRACTION_DIR
    os.makedirs(output_dir, exist_ok=True)
    solutions = collect_solutions(analog_root)
    if not solutions:
        print("未找到任何包含 complete_data.json 的解决方案目录")
        return []

    results = []
    for sol in solutions:
        scheme_id = sol["scheme_id"]
        out_file = os.path.join(output_dir, f"{scheme_id}_extraction.json")
        if skip_existing and os.path.isfile(out_file):
            try:
                with open(out_file, "r", encoding="utf-8") as f:
                    results.append(json.load(f))
            except Exception:
                pass
            continue
        print(f"正在提取关键词: {scheme_id}")
        out = extract_keywords_for_solution(
            sol["input_text"],
            scheme_id,
            client=client,
            model=model,
        )
        out["scheme_name"] = sol.get("scheme_name", scheme_id)
        results.append(out)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    return results
