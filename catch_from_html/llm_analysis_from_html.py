import json
import re
import os
import glob
from typing import List, Dict, Any, Optional
from datetime import datetime

# 火山引擎配置
VOLCENGINE_API_KEY = "88632c3b-7c51-4517-83a1-c77957720f11"
VOLCENGINE_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/bots"
VOLCENGINE_MODEL = "bot-20251202172548-dp7bp"


def call_volcengine_api(prompt, max_tokens=2000, temperature=0.1):
    """调用火山引擎API"""
    import requests

    headers = {
        "Authorization": f"Bearer {VOLCENGINE_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": VOLCENGINE_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    try:
        print(f"发送请求到火山引擎API，prompt长度: {len(prompt)}")
        response = requests.post(
            f"{VOLCENGINE_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )
        print(f"API状态码：{response.status_code}")
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"]
        else:
            print(f"请求失败，状态码：{response.status_code}")
            print(f"响应内容：{response.text}")
            return None
    except requests.exceptions.Timeout:
        print("请求超时，请检查网络连接")
        return None
    except Exception as e:
        print(f"请求异常: {e}")
        return None


def load_adi_json_file(filepath):
    """加载ADI爬取的JSON文件"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"成功加载JSON文件: {filepath}")
        print(f"包含 {len(data)} 个产品")
        return data
    except Exception as e:
        print(f"加载JSON文件失败: {e}")
        return None


def analyze_adi_product_data(product_data, max_chars: int = 6000):
    """
    构造提示词：从ADI官网爬取的数据中提取知识图谱用核心参数。
    :param product_data: ADI产品的字典数据
    :param max_chars: 截断后传入模型的文本长度上限
    :return: prompt 字符串
    """
    # 准备产品信息字符串
    product_info = f"产品标题: {product_data.get('title', '')}\n"

    # 添加特性信息
    if 'features' in product_data and product_data['features']:
        product_info += "产品特性:\n"
        for i, feature in enumerate(product_data['features'], 1):
            product_info += f"  {i}. {feature}\n"
    elif 'overview' in product_data:
        product_info += f"产品概述: {product_data['overview']}\n"

    # 添加详情信息
    if 'details' in product_data and product_data['details']:
        product_info += f"产品详情: {product_data['details'][:500]}...\n"

    # 添加型号信息
    if 'models' in product_data and product_data['models']:
        product_info += f"相关型号: {', '.join(product_data['models'])}\n"

    # 添加URL
    product_info += f"产品URL: {product_data.get('url', '')}\n"

    # 截断处理
    if len(product_info) > max_chars:
        product_info = product_info[:max_chars - 50] + "\n...(已截断)"

    prompt = f"""你是一个电子元器件专家，专门从ADI(亚德诺半导体)的产品信息中提取核心参数用于构建知识图谱。

请从以下ADI产品信息中**直接提取**可用于构建知识图谱的核心参数，并**只输出一个合法的 JSON 对象**，不要其他解释或 markdown 代码块。

**必须输出的 JSON 结构**（字段名保持如下，便于后续入库）：
{{
  "items": [
    {{
      "model": "产品型号（从标题中提取，如ADM2895E-1）",
      "title": "产品完整标题",
      "brand_cn": "亚德诺",
      "brand_en": "ADI",
      "description": "产品简介",
      "category": "产品类型（如：MCU、ADC、DAC等）",
      "core_params": [
        {{ "name": "参数名", "value": "参数值", "unit": "单位（如：V、A、Hz等，若无单位则空字符串）" }}
      ],
      "key_features": [
        "关键特性1",
        "关键特性2"
      ],
      "applications": [
        "应用领域1",
        "应用领域2"
      ],
      "source_url": "产品页面URL"
    }}
  ]
}}

**抽取规则**：
1. **model**：从产品标题中提取核心型号，通常以AD开头，如"ADM2895E-1"。
2. **core_params**：从产品特性中提取核心电气参数，重点关注：
   - 电压参数（工作电压、供电电压、隔离电压等）
   - 电流参数（工作电流、静态电流等）
   - 温度范围（工作温度、存储温度等）
   - 频率/速率参数（数据速率、采样率、带宽等）
   - 接口类型（RS-485、SPI、I2C等）
   - 封装信息（封装类型、引脚数等）
   - 其他关键规格参数
3. 每个参数必须有明确的**name**和**value**，如果有单位请填入**unit**字段。
4. **key_features**：从特性中提取3-5个最突出的关键特性。
5. **applications**：从描述中提取主要应用领域，如果没有明确信息则根据产品类型推断（如：工业自动化、通信设备、医疗设备等）。
6. **category**：根据产品描述和特性判断产品品类（ADC/DAC/放大器/接口芯片/电源管理等）。

**注意**：
- 只从提供的信息中提取，不要编造不存在的信息。
- 保持参数的准确性和专业性。
- core_params数量以5-15条为宜，优先提取最重要的参数。

**ADI产品信息**：
{product_info}

请直接输出上述结构的 JSON，不要包裹在 ```json 中，不要前后多余文字。"""
    return prompt


def parse_extracted_json(llm_output: str) -> Optional[Dict[str, Any]]:
    """
    从 LLM 返回文本中解析出「提取结果」JSON。
    兼容被 markdown 代码块包裹或带前后说明的情况。
    """
    if not llm_output or not llm_output.strip():
        return None
    raw = llm_output.strip()
    # 去掉可能的 ```json ... ```
    if "```" in raw:
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError as e:
        print(f"JSON解析失败: {e}")
        return None


def extract_core_params_from_adi_json(json_filepath):
    """
    从ADI JSON文件中提取核心参数的主函数
    """
    # 1. 加载JSON数据
    products = load_adi_json_file(json_filepath)
    if not products:
        return None

    all_results = []

    # 2. 对每个产品调用大模型分析
    for i, product in enumerate(products, 1):
        print(f"\n{'=' * 60}")
        print(f"分析第 {i}/{len(products)} 个产品: {product.get('title', '未知')}")

        # 构造prompt
        prompt = analyze_adi_product_data(product)

        # 调用大模型
        print("正在调用大模型分析...")
        result = call_volcengine_api(prompt, max_tokens=3000, temperature=0.1)

        if result:
            # 解析结果
            parsed = parse_extracted_json(result)
            if parsed and parsed.get("items"):
                extracted_item = parsed["items"][0]
                # 添加原始数据引用
                extracted_item["original_data_ref"] = {
                    "title": product.get("title"),
                    "url": product.get("url"),
                    "crawl_time": product.get("crawl_time")
                }
                all_results.append(extracted_item)
                print(f"✓ 成功提取: {extracted_item.get('model')}")
                # 显示提取的核心参数数量
                core_params_count = len(extracted_item.get('core_params', []))
                print(f"  提取到 {core_params_count} 个核心参数")
            else:
                print(f"✗ 解析失败，保存原始回复")
                # 保存原始回复供调试
                with open(f"debug_product_{i}.txt", "w", encoding="utf-8") as f:
                    f.write(f"原始回复:\n{result}\n\nPrompt:\n{prompt}")
        else:
            print("✗ 大模型调用失败")

        # 延迟以避免API限制
        if i < len(products):
            import time
            time.sleep(1)

    # 3. 保存结果
    if all_results:
        # 生成输出文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"adi_core_params_{timestamp}.json"

        # 构建最终输出结构
        final_output = {
            "extraction_time": datetime.now().isoformat(),
            "source_file": os.path.basename(json_filepath),
            "total_products": len(all_results),
            "items": all_results
        }

        # 保存到文件
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(final_output, f, ensure_ascii=False, indent=2)

        print(f"\n{'=' * 60}")
        print(f"核心参数提取完成！")
        print(f"共处理 {len(products)} 个产品，成功提取 {len(all_results)} 个产品的核心参数")
        print(f"结果已保存到: {output_filename}")

        # 显示摘要
        print("\n提取结果摘要:")
        for i, item in enumerate(all_results, 1):
            model = item.get("model", "未知型号")
            category = item.get("category", "未知类别")
            params_count = len(item.get("core_params", []))
            print(f"{i}. {model} - {category} ({params_count}个参数)")

        return final_output
    else:
        print("没有成功提取到任何核心参数")
        return None


def find_latest_adi_json():
    """在当前目录查找最新的ADI JSON文件"""
    # 查找所有可能的ADI JSON文件
    json_patterns = [
        "adi_products*.json",
        "adi_products_detailed*.json",
        "data/adi_products*.json",
        "data/adi_products_detailed*.json"
    ]

    all_files = []
    for pattern in json_patterns:
        all_files.extend(glob.glob(pattern))

    # 按修改时间排序，最新的在前
    if all_files:
        all_files.sort(key=os.path.getmtime, reverse=True)
        print(f"找到 {len(all_files)} 个ADI JSON文件:")
        for i, file in enumerate(all_files[:5], 1):  # 只显示前5个
            mtime = datetime.fromtimestamp(os.path.getmtime(file))
            print(f"  {i}. {file} (修改时间: {mtime.strftime('%Y-%m-%d %H:%M:%S')})")

        return all_files[0]  # 返回最新的文件
    else:
        print("未找到ADI JSON文件")
        return None


def main():
    print("ADI产品核心参数提取工具")
    print("=" * 60)
    print("功能：从ADI官网爬取的JSON数据中提取核心参数")

    # 查找最新的JSON文件
    json_file = find_latest_adi_json()

    if not json_file:
        print("请确保您已经运行了爬虫脚本，生成了ADI JSON文件")
        print("或者您可以直接将JSON文件路径作为参数传入:")
        print("  python llm_analysis_from_html.py <json_file_path>")
        return

    print(f"\n使用最新的JSON文件: {json_file}")

    # 确认是否处理该文件
    choice = input(f"\n是否处理此文件？(y/n): ").strip().lower()
    if choice != 'y':
        print("操作取消")
        return

    # 处理文件
    extract_core_params_from_adi_json(json_file)


if __name__ == "__main__":
    import sys

    # 如果有命令行参数，使用指定的文件
    if len(sys.argv) > 1:
        json_file = sys.argv[1]
        if os.path.exists(json_file):
            extract_core_params_from_adi_json(json_file)
        else:
            print(f"文件不存在: {json_file}")
            main()
    else:
        main()