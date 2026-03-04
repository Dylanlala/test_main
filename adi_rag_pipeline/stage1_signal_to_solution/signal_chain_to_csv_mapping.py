#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
信号链图片 → 器件+信号流向（豆包视觉）→ 器件与 exports_signal_chain_csv 映射（LLM）。
用于 RAG 构建：按图中器件/模块检索对应选型表 CSV。

两阶段均输出 JSON：
  - Step1：方案目录下 signal_chain_descriptions/{图片名}_fast.json（器件列表 + 信号流向 + 应用场景）
  - Step2：方案目录下 signal_chain_{chain_id}_description_to_csv_mapping.json（器件↔CSV 映射）
  - 汇总：signal_chain_mapping_for_rag.json（供 RAG 索引）
"""
import argparse
import base64
import glob
import json
import os
import re
import sys

# 项目根 = fae_main
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from adi_rag_pipeline.config import (
    ANALOG_DATA_ROOT,
    get_llm_api_key,
    MAIN_API_KEY,
    STEP2_FALLBACK_MODEL,
    STEP2_FALLBACK_BASE_URL,
    STEP2_FALLBACK_API_KEY,
)

# ========== 与 analyze_signal_chains.py 完全一致：视觉 API 配置（硬编码 Key，保证与 analyze_signal_chains 同源）==========
API_KEY = os.getenv("ARK_API_KEY", "88632c3b-7c51-4517-83a1-c77957720f11")  # 与 analyze_signal_chains.py 相同，可选 ARK_API_KEY 覆盖
ARK_BASE_URL = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
VISION_MODEL = os.getenv("VISION_MODEL", "doubao-seed-2-0-pro-260215")
# ==========================================================================================================

# ========== Step2 与 analyze_llm_to_signal 一致：对话用 config 的 LLM_BASE_URL（/api/v3/bots）+ LLM_MODEL（bot-xxx）==========
try:
    from adi_rag_pipeline.config import LLM_BASE_URL as CONFIG_LLM_BASE_URL, LLM_MODEL as CONFIG_LLM_MODEL
except Exception:
    CONFIG_LLM_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/bots"
    CONFIG_LLM_MODEL = "doubao-seed-2-0-pro-260215"
CHAT_BASE_URL = os.getenv("LLM_BASE_URL", CONFIG_LLM_BASE_URL or "https://ark.cn-beijing.volces.com/api/v3/bots")
CHAT_MODEL = os.getenv("LLM_MODEL", CONFIG_LLM_MODEL or "doubao-seed-2-0-pro-260215")

DESCRIPTION_SUBDIR = "signal_chain_descriptions"
MAPPING_JSON_FILENAME = "signal_chain_mapping_for_rag.json"


def get_vision_client():
    """与 analyze_signal_chains.py 完全相同：使用同一 API_KEY 和 base_url，不读 config。"""
    from openai import OpenAI
    return OpenAI(base_url=ARK_BASE_URL, api_key=API_KEY)


def get_chat_client():
    """Step2 与 analyze_llm_to_signal 一致：使用 config 的 LLM_BASE_URL（/api/v3/bots）与 LLM_MODEL（bot-xxx），Key 从 key1.txt/env 读。"""
    from openai import OpenAI
    key = get_llm_api_key() or os.getenv("LLM_API_KEY") or (MAIN_API_KEY if MAIN_API_KEY else "")
    if not key:
        raise ValueError("未配置 API Key：请设置 static/key1.txt 或环境变量 LLM_API_KEY / MAIN_API_KEY")
    return OpenAI(base_url=CHAT_BASE_URL, api_key=key)


def get_chat_client_fallback():
    """Step2 主模型失败时用的客户端：若配置了 STEP2_FALLBACK_BASE_URL 则用该 endpoint + STEP2_FALLBACK_API_KEY，否则返回 None（用主 client 换 model 即可）。"""
    if not (STEP2_FALLBACK_BASE_URL and STEP2_FALLBACK_BASE_URL.strip()):
        return None
    from openai import OpenAI
    key = (STEP2_FALLBACK_API_KEY or get_llm_api_key() or os.getenv("LLM_API_KEY") or (MAIN_API_KEY if MAIN_API_KEY else "")).strip()
    if not key:
        return None
    return OpenAI(base_url=STEP2_FALLBACK_BASE_URL.strip(), api_key=key)


def _get_message_text_safe(message) -> str:
    """从 message 中安全取文本，避免 KeyError（部分 API 键名为 '\\n  \"mapping\"' 等）。"""
    try:
        c = getattr(message, "content", None)
        if c is not None:
            if isinstance(c, str):
                return c
            if isinstance(c, list) and c:
                for part in c:
                    t = getattr(part, "text", None)
                    if t:
                        return t
                return str(c[0])
    except KeyError as e:
        if e.args and hasattr(message, "get"):
            v = message.get(e.args[0])
            if isinstance(v, str) and len(v) > 10:
                return v
    try:
        if hasattr(message, "get"):
            c = message.get("content")
            if isinstance(c, str):
                return c
            for _k, v in (getattr(message, "items", lambda: ())() or ()):
                if isinstance(v, str) and len(v) > 20:
                    return v
    except (KeyError, TypeError):
        pass
    return ""


def _extract_content_from_resp_raw(resp) -> str:
    """通过 model_dump()/dict 从响应取文本，用于 KeyError 时的兜底。"""
    try:
        if hasattr(resp, "model_dump"):
            d = resp.model_dump()
        elif hasattr(resp, "model_dump_json"):
            d = json.loads(resp.model_dump_json())
        else:
            d = getattr(resp, "__dict__", None) or {}
        choices = d.get("choices", []) if isinstance(d, dict) else []
        if not choices:
            return ""
        msg = choices[0]
        message = msg.get("message") if isinstance(msg, dict) else getattr(msg, "message", None)
        if message is None:
            return ""
        if not isinstance(message, dict) and hasattr(message, "model_dump"):
            message = message.model_dump()
        if isinstance(message, dict):
            for _k, v in message.items():
                if isinstance(v, str) and len(v) > 20:
                    return v
            return ""
        return _get_message_text_safe(message)
    except Exception:
        return ""


def extract_content(resp):
    """从火山引擎 API 响应中提取最终文本（兼容 choices/output/reasoning，并避免 KeyError）。"""
    if hasattr(resp, "error") and resp.error:
        return f"API Error: {resp.error}"
    if hasattr(resp, "choices") and resp.choices:
        choice = resp.choices[0]
        try:
            msg = getattr(choice, "message", None)
        except KeyError:
            msg = None
        if msg is None and isinstance(choice, dict):
            for _k, v in choice.items():
                if isinstance(v, str) and len(v) > 20:
                    return v
                if v is not None and (hasattr(v, "content") or isinstance(v, dict)):
                    t = _get_message_text_safe(v)
                    if t:
                        return t
            return ""
        if msg is not None:
            text = _get_message_text_safe(msg)
            if text:
                return text
            try:
                c = getattr(msg, "content", None)
            except KeyError:
                c = None
            if isinstance(c, str):
                return c
            if isinstance(c, list) and c and hasattr(c[0], "text"):
                return getattr(c[0], "text", "")
        return ""
    if hasattr(resp, "output") and resp.output:
        for item in resp.output:
            if hasattr(item, "type"):
                if item.type == "message" and hasattr(item, "role") and item.role == "assistant":
                    if hasattr(item, "content"):
                        content = item.content
                        if isinstance(content, list):
                            for part in content:
                                if hasattr(part, "type") and part.type == "output_text":
                                    return part.text
                                if hasattr(part, "text"):
                                    return part.text
                            if content:
                                return str(content[0])
                        elif hasattr(content, "text"):
                            return content.text
                        else:
                            return str(content)
                elif item.type == "reasoning" and hasattr(item, "summary") and item.summary:
                    s = item.summary
                    if isinstance(s, list) and len(s) > 0 and hasattr(s[0], "text"):
                        return s[0].text
                    if hasattr(s, "text"):
                        return s.text
        if len(resp.output) > 0:
            item = resp.output[0]
            if hasattr(item, "content") and item.content:
                if isinstance(item.content, list) and len(item.content) > 0:
                    return item.content[0].text
                elif hasattr(item.content, "text"):
                    return item.content.text
                else:
                    return str(item.content)
            else:
                return str(item)
        return "No output content"
    return str(resp)


def get_image_files(directory):
    """获取目录下所有常见格式的图片文件。"""
    if not directory or not os.path.isdir(directory):
        return []
    exts = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif"]
    files = []
    for ext in exts:
        files.extend(glob.glob(os.path.join(directory, ext)))
    return sorted(files)


def ensure_signal_chain_images_from_complete_data(solution_dir: str, signal_chains_dir: str) -> int:
    """
    若 signal_chains 目录为空，从 complete_data.json 的 chains[].image_info.img_url 下载图片到 signal_chains_dir。
    返回下载的图片数量（0 表示未下载或失败）。
    """
    images = get_image_files(signal_chains_dir)
    if images:
        return 0
    complete_path = os.path.join(solution_dir, "complete_data.json")
    if not os.path.isfile(complete_path):
        return 0
    try:
        with open(complete_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return 0
    chains = (data.get("signal_chains") or {}).get("chains") or []
    os.makedirs(signal_chains_dir, exist_ok=True)
    try:
        import urllib.request
    except ImportError:
        return 0
    downloaded = 0
    for c in chains:
        info = c.get("image_info") or {}
        url = info.get("img_url") or info.get("image_url")
        fname = info.get("filename") or (f"signal_chain_{c.get('chain_id', '')}.png")
        if not url:
            continue
        out_path = os.path.join(signal_chains_dir, fname)
        if os.path.isfile(out_path):
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                with open(out_path, "wb") as f:
                    f.write(resp.read())
            downloaded += 1
            print(f"  已下载: {fname}")
        except Exception as e:
            print(f"  下载失败 {fname}: {e}")
    return downloaded


def encode_image_to_base64(image_path):
    with open(image_path, "rb") as f:
        img_data = f.read()
    ext = os.path.splitext(image_path)[1].lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".bmp": "image/bmp", ".gif": "image/gif"}.get(
        ext, "image/png"
    )
    b64 = base64.b64encode(img_data).decode("utf-8")
    return f"data:{mime};base64,{b64}"


PROMPT_STEP1_DEVICES_AND_FLOW = """你是专业的信号链框图分析专家，请严格按照以下要求分析输入的信号链图片，**仅输出符合要求的纯JSON文本，不要输出任何其他内容，不要加Markdown代码块标记，不要加解释说明文字**：

【输出字段要求】
1. "devices"：数组，每个元素为{"name": "器件名称", "description": "专业技术用语描述功能，一句话"}，严格按照信号从输入到输出的流向排序，不能遗漏任何图中标注的模块/器件。
2. "signal_flow"：对象，必须包含：
   - "main"字段：字符串，用" -> "连接器件，收发分开写，清晰标注主路径；
   - "branches"数组（可选）：每个元素为路径描述字符串，包含所有本振、时钟、控制、电源等分支路径。
3. "application_scene"：字符串，准确匹配图片的应用场景，为名词性短语。

【格式约束】
- 禁止输出任何思考过程、注释、Markdown标记，仅输出JSON对象；
- 所有特殊字符自动正确转义，保证JSON可直接解析；
- 器件名称和图中标注完全一致，功能描述专业准确。

【示例输出】
{
  "devices": [
    {"name": "LNA", "description": "低噪声放大器，对接收的射频信号进行低噪声放大，提升信噪比。"},
    {"name": "Mixer", "description": "下变频混频器，将射频信号与本振信号混频得到中频信号。"},
    {"name": "ADC", "description": "模数转换器，将模拟中频信号转换为数字信号传输给基带处理单元。"}
  ],
  "signal_flow": {
    "main": "接收天线 -> LNA -> 混频器 -> 中频放大器 -> ADC -> FPGA -> DAC -> 上变频混频器 -> 功率放大器 -> 发射天线",
    "branches": ["本振路径：参考时钟 -> PLL -> 频率倍增链 -> 混频器本振输入端", "控制路径：FPGA -> 伺服控制模块 -> 天线伺服电机"]
  },
  "application_scene": "相控阵气象雷达收发信号链"
}

请直接输出 JSON。"""



def validate_json_structure(data):
    """校验 JSON 是否包含必需的字段"""
    required_fields = ["devices", "signal_flow", "application_scene"]
    for field in required_fields:
        if field not in data:
            print(f"  缺失必填字段：{field}")
            return False
    if not isinstance(data["signal_flow"], dict):
        print("  signal_flow 不是对象")
        return False
    if "main" not in data["signal_flow"]:
        print("  signal_flow 缺失 main 字段")
        return False
    return True



def _normalize_mapping_response(json_data: dict) -> dict:
    """从 LLM 返回的 JSON 中安全取出 mapping/summary/note，兼容键名带换行或空格（如 '\\n  \"mapping\"'）。"""
    if not isinstance(json_data, dict):
        return {"mapping": [], "summary": "", "note": ""}
    out = {}
    for raw_key, val in json_data.items():
        k = raw_key.strip().replace("\n", "").replace("\r", "").replace('"', "").strip()
        if k == "mapping":
            out["mapping"] = val if isinstance(val, list) else []
        elif k == "summary":
            out["summary"] = val if isinstance(val, str) else ""
        elif k == "note":
            out["note"] = val if isinstance(val, str) else ""
    out.setdefault("mapping", [])
    out.setdefault("summary", "")
    out.setdefault("note", "")
    return out


def clean_and_validate_json(raw_text: str):
    """
    清理模型输出，提取可能的 JSON 部分（去除 Markdown 代码块、前后废话），并尝试解析。
    返回 (parsed_dict, cleaned_text)，若解析失败则返回 (None, cleaned_text)。
    """
    if not raw_text:
        return None, ""
    text = raw_text.strip()
    # 去除可能的 ```json ... ``` 包裹
    if text.startswith("```json"):
        text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
    elif text.startswith("```"):
        text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
    text = text.strip()

    # 尝试解析 JSON
    try:
        data = json.loads(text)
        return data, text
    except json.JSONDecodeError:
        # 若失败，可能含有额外文字，尝试查找第一个 { 和最后一个 }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end+1]
            try:
                data = json.loads(candidate)
                return data, candidate
            except:
                pass
        return None, text


def extract_clean_description(raw_text: str) -> str:
    """
    从 Step1 模型原始输出中只保留规范三部分，去掉开头推理/口语和结尾自检。
    保留：从第一个「### 1. 器件与模块列表」到「### 3. 应用场景」后的第一行（应用场景短语）结束。
    用于彻底避免推理口语写入 description 文件，批量处理 50+ 方案时保证一致性。
    """
    if not (raw_text and raw_text.strip()):
        return raw_text or ""
    text = raw_text.strip()
    # 从第一个「### 1. 器件与模块列表」开始
    start_marker = "### 1. 器件与模块列表"
    start = text.find(start_marker)
    if start == -1:
        for alt in ("### 1.  器件与模块列表", "## 1. 器件与模块列表"):
            start = text.find(alt)
            if start != -1:
                start_marker = alt
                break
    if start == -1:
        return text

    # 到「### 3. 应用场景」及其后第一行（应用场景短语）结束
    end_marker = "### 3. 应用场景"
    end_idx = text.find(end_marker, start)
    if end_idx == -1:
        segment = text[start:]
    else:
        after_sec3 = end_idx + len(end_marker)
        rest = text[after_sec3:]
        # 第一行非空内容 = 应用场景短语
        for i, ch in enumerate(rest):
            if ch == "\n":
                continue
            if ch.isspace():
                continue
            break
        else:
            segment = text[start:after_sec3]
            return segment.strip()
        line_end = rest.find("\n", i)
        if line_end == -1:
            end_pos = len(text)
        else:
            end_pos = after_sec3 + line_end + 1
        # 若该行像推理口语（哦对、是不是…）则不包含，只到 ### 3 标题行为止
        app_line = rest[i : line_end if line_end != -1 else None].strip()
        if re.match(r"^(哦对|不对|首先|然后|是不是|不要任何多余|就按这个输出|检查有没有漏)", app_line):
            segment = text[start:end_idx]
        else:
            segment = text[start:end_pos]
    clean = segment.strip()

    # 去掉末尾明显的推理/自检行
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


def step1_analyze_image(image_path, client, retries=2):
    """调用豆包视觉模型：从信号链图片提取器件列表 + 信号流向。返回 (json_dict, cleaned_text) 或 (None, None)。"""
    try:
        image_data_url = encode_image_to_base64(image_path)
    except Exception as e:
        print(f"  图片编码失败: {e}")
        return None, None
    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model=VISION_MODEL,
                messages=[
                    {
                        "role":"user",
                        "content":[
                            {"type":"image_url","image_url": {"url":image_data_url}},
                            {"type":"text","text":PROMPT_STEP1_DEVICES_AND_FLOW}
                        ]
                    }
                ],
                max_tokens=4096,
                temperature=0
            )
            content = extract_content(response)
            if not content:
                return None, None
            json_data, cleaned = clean_and_validate_json(content)  # 使用原解析函数提取JSON对象
            if json_data is not None and validate_json_structure(json_data):
                return json_data, cleaned
            else:
                print(f"  第 {attempt + 1} 次调用返回的内容无法通过字段校验，原始内容: {content[:200]}...")
                if attempt == retries:
                    return None, cleaned
        except Exception as e:
            err_str = str(e)
            print(f"  第 {attempt + 1} 次调用失败: {e}")
            if "ModelNotOpen" in err_str or "404" in err_str:
                print("  提示：当前账户未开通该视觉模型。请到火山引擎Ark控制台开通模型，或设置环境变量 VISION_MODEL=已开通的模型ID。")
            if attempt == retries:
                return None, None
    return None, None


def run_step1(solution_dir: str, signal_chains_dir: str, descriptions_dir: str, try_download: bool = True) -> list:
    """
    遍历 signal_chains 下所有图片，生成器件+流向描述，保存到 descriptions_dir（JSON 格式）。
    返回 [(image_basename, description_path, chain_id), ...]
    """
    os.makedirs(descriptions_dir, exist_ok=True)
    # 获取图片文件列表（补全缺失的行）
    images = get_image_files(signal_chains_dir)

    if not images and try_download:
        print(f"  signal_chains 为空，尝试从 complete_data.json 下载图片到: {signal_chains_dir}")
        n = ensure_signal_chain_images_from_complete_data(solution_dir, signal_chains_dir)
        if n:
            images = get_image_files(signal_chains_dir)
    if not images:
        print(f"未找到图片。请将信号链图片放入: {signal_chains_dir}")
        print("  或从 complete_data.json 中 image_info.img_url 下载到该目录；也可使用 --step2-only 并准备 signal_chain_descriptions/*_fast.json")
        return []

    client = get_vision_client()
    results = []
    for img_path in images:
        basename = os.path.basename(img_path)
        name_no_ext = os.path.splitext(basename)[0]
        match = re.search(r"signal_chain[_\s\-]*(\d+)", name_no_ext, re.I)
        chain_id = match.group(1) if match else name_no_ext

        print(f"  [Step1] 处理图片: {basename} ...")
        json_data, cleaned_text = step1_analyze_image(img_path, client)
        if json_data is None:
            print(f" 分析失败或返回内容非 JSON，原始内容已保存为 .txt 以供调试")
            debug_path = os.path.join(descriptions_dir, f"{name_no_ext}_debug.txt")
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(cleaned_text or "(空)")
            continue

        # 保存为格式化的 JSON 文件，使用 _fast.json 后缀
        out_path = os.path.join(descriptions_dir, f"{name_no_ext}_fast.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        print(f"    ✅ 已保存 JSON: {out_path}")
        results.append((basename, out_path, chain_id))
    return results

# ---------- Step 2: 器件描述 + CSV 列表 → 映射 ----------

PROMPT_STEP2_MAPPING = """你是一位 ADI 信号链选型专家。下面给出一段「信号链框图的文字描述」（包含器件/模块列表与信号流向），以及**仅属于本信号链**的 CSV 文件名列表（文件名均以同一 chain_id 开头，例如 0477_xxx.csv 只属于链 0477）。

请完成**映射**：将描述中的每个器件/功能模块与下面列表中的 CSV 文件建立对应关系。

要求：
1. **仅使用**下面「本链可用的 CSV 文件名列表」中的文件，不要编造、不要引用其他 chain_id 的 CSV。
2. 一个器件/模块可对应 0 个、1 个或多个 CSV（一对多常见），多个 CSV 用英文逗号分隔。
3. 若某器件在图中出现但在列表中无对应项，对应CSV文件列填「无」或留空，说明列可写“无对应CSV”。

请**严格按以下 Markdown 表格**输出，表头不可改，不要输出 JSON 或代码块：

| 器件/模块 | 对应CSV文件 | 说明 |
|-----------|-------------|------|
| 器件名1 | 文件名A.csv, 文件名B.csv | 可选说明 |
| 器件名2 | 无 | 无对应CSV |

表格之后可另起一行写一句「覆盖情况说明」（主路径/分支是否有对应选型表等），作为总结。

---
## 信号链描述（供映射参考）

{description}

---
## 本链可用的 CSV 文件名列表（仅限本链，勿使用列表外文件）

{csv_list}

请直接输出上述表格（表头为：器件/模块 | 对应CSV文件 | 说明），不要输出 JSON。"""


def _parse_mapping_markdown_table(text: str, valid_csv_set: set) -> dict:
    """将 Step2 的 Markdown 表格解析为 RAG 所需的 JSON 结构：mapping + summary + note。"""
    mapping = []
    summary_parts = []
    if not text or not text.strip():
        return {"mapping": [], "summary": "", "note": ""}
    lines = text.strip().split("\n")
    in_table = False
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            if in_table:
                in_table = False
            continue
        if s.startswith("|") and "|" in s[1:]:
            if re.match(r"^\|[\s\-:]+\|", s):
                in_table = True
                continue
            if "器件" in s or "模块" in s or "对应CSV" in s:
                in_table = True
                continue
            cells = [c.strip() for c in s.split("|") if c.strip() != ""]
            if len(cells) >= 1:
                device = cells[0].strip()
                csv_col = cells[1].strip() if len(cells) > 1 else ""
                comment = cells[2].strip() if len(cells) > 2 else ""
                csv_files = []
                if csv_col and csv_col.lower() not in ("无", "无对应", "-", "—", ""):
                    for part in re.split(r"[,，、\s]+", csv_col):
                        part = part.strip()
                        if part in valid_csv_set:
                            csv_files.append(part)
                        elif part.endswith(".csv") and part not in csv_files:
                            csv_files.append(part)
                mapping.append({"device": device, "csv_files": csv_files, "comment": comment})
            in_table = True
        else:
            if in_table or (not mapping and len(summary_parts) == 0):
                summary_parts.append(s)
    summary = " ".join(summary_parts).strip() if summary_parts else ""
    return {"mapping": mapping, "summary": summary, "note": ""}


def load_description_text(desc_path: str) -> str:
    """
    根据描述文件加载文本描述（用于 Prompt）。
    若为 .json 文件，则解析并重构为文本格式；若为 .txt，直接返回内容。
    """
    if desc_path.endswith('.json'):
        try:
            with open(desc_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 重构为文本描述（模仿旧版 Markdown 格式）
            lines = []
            lines.append("### 1. 器件与模块列表")
            for dev in data.get('devices', []):
                lines.append(f"- **{dev.get('name', '')}**：{dev.get('description', '')}")
            lines.append("\n### 2. 信号流向")
            flow = data.get('signal_flow', {})
            lines.append(f"- 主路径：{flow.get('main', '')}")
            for branch in flow.get('branches', []):
                lines.append(f"- {branch}")
            lines.append("\n### 3. 应用场景")
            lines.append(data.get('application_scene', ''))
            return "\n".join(lines)
        except Exception as e:
            print(f"  警告：解析 JSON 描述文件失败 {desc_path}，将直接读取原始内容。错误：{e}")
            with open(desc_path, 'r', encoding='utf-8') as f:
                return f.read()
    else:
        with open(desc_path, 'r', encoding='utf-8') as f:
            return f.read()



def _step2_mapping_failed(result: dict) -> bool:
    """判断 Step2 是否视为失败（无有效 mapping 且 summary 含异常/失败/无法解析）。"""
    if not result or not isinstance(result, dict):
        return True
    mapping = result.get("mapping")
    if mapping and isinstance(mapping, list) and len(mapping) > 0:
        return False
    summary = (result.get("summary") or "")
    return "异常" in summary or "失败" in summary or "无法解析" in summary or "KeyError" in summary


def step2_build_mapping(description_text: str, csv_filenames: list, chat_client, model: str = None) -> dict:
    """根据描述文本和 CSV 文件名列表，调用 LLM 生成器件↔CSV 映射，返回字典。model 默认 CHAT_MODEL。"""
    model = model or CHAT_MODEL
    csv_list = "\n".join([f"- {n}" for n in sorted(csv_filenames)])
    prompt = PROMPT_STEP2_MAPPING.format(
        description=description_text[:8000],
        csv_list=csv_list[:6000],
    )
    try:
        resp = chat_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
        )
        try:
            content = extract_content(resp)
        except KeyError:
            content = _extract_content_from_resp_raw(resp)
        if not isinstance(content, str):
            content = str(content) if content else ""
        content = (content or "").strip()
        # 解析：先试 JSON，无有效 mapping 时按 Markdown 表格解析（与 signal_chain_image_to_csv_mapping 一致，便于 RAG 统一结构）
        json_data, _ = clean_and_validate_json(content)
        if json_data is not None and isinstance(json_data, dict):
            normalized = _normalize_mapping_response(json_data)
            if normalized["mapping"] is not None and isinstance(normalized["mapping"], list) and len(normalized["mapping"]) > 0:
                return {
                    "mapping": normalized["mapping"],
                    "summary": normalized.get("summary", ""),
                    "note": normalized.get("note", ""),
                }
        valid_csv_set = set(csv_filenames)
        from_md = _parse_mapping_markdown_table(content, valid_csv_set)
        if from_md.get("mapping"):
            return from_md
        if json_data is not None and isinstance(json_data, dict):
            normalized = _normalize_mapping_response(json_data)
            return {
                "mapping": normalized.get("mapping") or [],
                "summary": normalized.get("summary", "") or "LLM返回的JSON缺少有效mapping",
                "note": f"原始输出：{content[:200]}"
            }
        return {
            "mapping": from_md.get("mapping", []),
            "summary": from_md.get("summary", "") or "未解析到表格或JSON",
            "note": f"原始输出：{content[:200]}"
        }
    except Exception as e:
        return {
            "mapping": [],
            "summary": f"LLM调用异常：{str(e)}",
            "note": ""
        }


def run_step2(solution_dir: str, csv_dir: str, step1_results: list, mapping_json_path: str) -> None:
    """
    对每个 step1 结果：按 chain_id 过滤 CSV，调用 LLM 生成映射，写入 .json 并汇总到 JSON。
    step1_results: [(image_basename, description_path, chain_id), ...]
    """
    if not step1_results:
        print("无 Step1 结果，跳过 Step2")
        return

    chat_client = get_chat_client()
    all_csv = [f for f in os.listdir(csv_dir)] if os.path.isdir(csv_dir) else []
    all_csv = [f for f in all_csv if f.endswith(".csv")]

    rag_mapping = {}

    for basename, desc_path, chain_id in step1_results:
        prefix = f"{chain_id}_"
        csv_for_chain = [f for f in all_csv if f.startswith(prefix)]

        # 加载描述文本（JSON 或 TXT 统一转为文本）
        description_text = load_description_text(desc_path)

        print(f"  [Step2] 建立映射 chain_id={chain_id}, 本链 CSV 数={len(csv_for_chain)} ...")
        if not csv_for_chain:
            # 无对应CSV：构造默认映射
            mapping_data = {
                "mapping": [],
                "summary": f"本信号链（chain_id={chain_id}）在 exports_signal_chain_csv 中无对应选型表（即不存在以 `{chain_id}_` 开头的 CSV 文件）。",
                "note": "图中器件与选型表无映射关系。"
            }
            print(f"    ⚠ 本链无 {prefix}*.csv，已写入无对应选型表说明")
        else:
            try:
                mapping_data = step2_build_mapping(description_text, csv_for_chain, chat_client, model=CHAT_MODEL)
                if _step2_mapping_failed(mapping_data) and STEP2_FALLBACK_MODEL:
                    fallback_client = get_chat_client_fallback() or chat_client
                    print(f"    主模型未返回有效映射，改用备用模型 {STEP2_FALLBACK_MODEL} 重试 ...")
                    mapping_data = step2_build_mapping(description_text, csv_for_chain, fallback_client, model=STEP2_FALLBACK_MODEL)
                    if not _step2_mapping_failed(mapping_data):
                        print(f"    ✅ 备用模型返回有效映射")
            except Exception as e:
                print(f"    ❌ LLM 调用失败: {type(e).__name__}: {e}")
                mapping_data = {
                    "mapping": [],
                    "summary": f"映射生成失败：{e}",
                    "note": ""
                }

        # 保存为 JSON 文件
        json_path = os.path.join(solution_dir, f"signal_chain_{chain_id}_description_to_csv_mapping.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(mapping_data, f, ensure_ascii=False, indent=2)
        print(f"    ✅ 已保存: {json_path}")

        rag_mapping[chain_id] = {
            "chain_id": chain_id,
            "image_basename": basename,
            "description_file": os.path.basename(desc_path),
            "description_preview": description_text[:500] + ("..." if len(description_text) > 500 else ""),
            "mapping_json_file": os.path.basename(json_path),
            "csv_files_for_chain": csv_for_chain,
            "mapping_data": mapping_data,   # 直接存储映射字典，便于RAG直接使用
        }

    with open(mapping_json_path, "w", encoding="utf-8") as f:
        json.dump(rag_mapping, f, ensure_ascii=False, indent=2)
    print(f"已写入 RAG 用汇总: {mapping_json_path}")



def main():
    parser = argparse.ArgumentParser(description="信号链图片→器件+流向→器件与CSV映射，供RAG使用（测试数据：analog_test1）")
    parser.add_argument("solution", help="方案目录名，如 下一代气象雷达")
    parser.add_argument("--data-root", default=ANALOG_DATA_ROOT, help="analog 数据根目录，默认 analog_test1")
    parser.add_argument("--images-dir", default="", help="信号链图片目录，默认用 方案目录/signal_chains")
    parser.add_argument("--step1-only", action="store_true", help="仅执行 Step1：图片→器件+流向")
    parser.add_argument("--step2-only", action="store_true", help="仅执行 Step2：用已有描述建映射")
    parser.add_argument("--no-download", action="store_true", help="不尝试从 complete_data.json 下载图片")
    args = parser.parse_args()

    solution_dir = os.path.join(args.data_root, args.solution.strip())
    if not os.path.isdir(solution_dir):
        print(f"错误：方案目录不存在: {solution_dir}")
        sys.exit(1)

    signal_chains_dir = os.path.join(solution_dir, "signal_chains") if not args.images_dir.strip() else args.images_dir.strip()
    csv_dir = os.path.join(solution_dir, "exports_signal_chain_csv")
    descriptions_dir = os.path.join(solution_dir, DESCRIPTION_SUBDIR)
    mapping_json_path = os.path.join(solution_dir, MAPPING_JSON_FILENAME)

    print(f"数据根: {args.data_root}  方案: {args.solution}")
    print(f"图片目录: {signal_chains_dir}  CSV 目录: {csv_dir}")

    step1_results = []

    if not args.step2_only:
        print("Step1: 豆包视觉 — 从信号链图片提取器件列表与信号流向")
        try_download = not args.no_download and not args.images_dir.strip()
        step1_results = run_step1(solution_dir, signal_chains_dir, descriptions_dir, try_download=try_download)
        if args.step1_only:
            print("Step1 完成（已跳过 Step2）")
            return

    if args.step2_only:
        # 从已有 description 文件恢复 step1_results（读取 _fast.json）
        if os.path.isdir(descriptions_dir):
            for fname in os.listdir(descriptions_dir):
                if fname.endswith("_fast.json"):
                    name_no_ext = fname.replace("_fast.json", "")
                    match = re.search(r"signal_chain[_\s\-]*(\d+)", name_no_ext, re.I)
                    chain_id = match.group(1) if match else name_no_ext
                    step1_results.append((fname.replace("_fast.json", "") + ".png",
                                          os.path.join(descriptions_dir, fname), chain_id))
        if not step1_results:
            print("未找到已有描述文件（_fast.json），请先运行 Step1")

    if step1_results:
        print("Step2: LLM — 建立器件/模块与 exports_signal_chain_csv 的映射")
        run_step2(solution_dir, csv_dir, step1_results, mapping_json_path)

    print("完成。")


if __name__ == "__main__":
    main()