import json
import requests
import re
import time

# 火山引擎配置
VOLCENGINE_API_KEY = "88632c3b-7c51-4517-83a1-c77957720f11"
VOLCENGINE_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/bots"
VOLCENGINE_MODEL = "bot-20251202172548-dp7bp"


def call_volcengine_api(prompt, max_tokens=4000, temperature=0.1):

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
        response = requests.post(
            f"{VOLCENGINE_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120  # 长超时
        )

        print(f"API 状态码: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"]
        else:
            print(f"API 错误: {response.status_code}")
            print(f"错误详情: {response.text}")
            return None

    except requests.exceptions.Timeout:
        print("请求超时，请检查网络连接")
        return None
    except Exception as e:
        print(f"请求异常: {e}")
        return None


def main():
    # 1. 加载 JSON 数据
    #json_file = '/data/huangmanling/2026_01_16_fae_rag/fae_batch_replace/analog_devices_data_final/10BASE-T1S_E2B远程控制协议(RCP)/complete_data.json'
    json_file ='/data/huangmanling/2026_01_16_fae_rag/fae_batch_replace/analog_devices_data_final/下一代气象雷达/complete_data.json'
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"数据加载成功，大小: {len(json.dumps(data))} 字符")
    except Exception as e:
        print(f"加载 JSON 文件失败: {e}")
        return

    # 2. 构建提示词
    prompt = f"""
你是一个资深的半导体领域解决方案架构师和知识图谱专家。请基于以下的JSON数据，总结出详细的方案描述。

JSON数据概述：
- 解决方案的标题：{data['page_info']['title']}
- 解决方案的url：{data['page_info']['url']}
- 解决方案的关键词{data['page_info']['keywords']}
- 解决方案描述：{data['page_info']['component_overview']}
- 核心价值与优势：{data['value_and_benefits']['contents']}
- 解决方案的应用场景分类：{data['page_info']['navigation_path']}
- 关键特性：{', '.join(data['value_and_benefits']['characteristics'])}
- 该方案的产品选型：{data['hardware_products']}
- 该方案的评估板：{data['evaluation_products']}
- 该方案的参考设计：{data['reference_products']}

请按以下格式输出分析结果：

### 一、方案核心总结（用于知识图谱节点描述）：
请用一段清晰、专业的文字总结这个解决方案，包含以下要素：
1. 解决方案名称和主要应用场景
2. 涉及的关键技术和核心器件
3. 基于的核心技术标准（如10BASE-T1S、IEEE 802.3等）
4. 解决的核心问题或满足的需求


二、生成一个结构化的JSON对象，方便后续的知识图谱构建，包含以下字段：
{{
  "solution_name": "完整的解决方案名称",
  "soultion_url":"该方案的url"
  "solution_summary": "请用一段清晰、专业的文字总结这个解决方案，包含以下要素：1. 解决方案名称和主要应用场景 2. 涉及的关键技术和核心器件，为什么会考虑这些器件用于该方案 3. 基于的核心技术标准（如10BASE-T1S、IEEE 802.3等）4. 解决的核心问题或满足的需求",
  "keywords":"关键词",
  "key_features": ["特性1", "特性2", "特性3",...],
  "core_advantages": ["优势1", "优势2", "优势3",...],
  "target_applications": ["应用场景1", "应用场景2", "应用场景3",...]
  "hardware_components": [
    {{
      "model": "芯片型号",
      "description": "芯片描述",
      "params":"芯片的核心参数",
      "model_url":"芯片的产品链接",
      "category":"器件类型，如ADC/DAC组合转换器"
      "web_category":"这个器件属于产品特性、评估板还是参考设计",
      "brand":"芯片的厂商“
    }}
  ]
}}

## 输出要求：
1. 只输出JSON对象，不要有任何其他文本
2. JSON必须格式正确，可以直接被解析
3. 基于提供的数据进行总结，不要添加不存在的信息
4. 确保技术术语准确
"""

    print(f"提示词长度: {len(prompt)} 字符")
    print(f"使用模型: {VOLCENGINE_MODEL}")

    # 3. 调用 API
    print("正在调用火山引擎 API...")
    start_time = time.time()

    response_text = call_volcengine_api(prompt, max_tokens=4000)

    if response_text:
        print(f"API 调用成功！耗时: {time.time() - start_time:.2f}秒")
        print("\n" + "=" * 80)
        print("API 响应:")
        print(response_text[:1000])  # 显示前1000字符

        # 4. 保存结果
        with open("volcengine_analysis_result.txt", "w", encoding="utf-8") as f:
            f.write(response_text)
        print("\n结果已保存到: volcengine_analysis_result.txt")

        # 5. 尝试提取 JSON
        try:
            # 查找 JSON 部分
            json_pattern = r'\{[\s\S]*\}'
            match = re.search(json_pattern, response_text)

            if match:
                json_str = match.group()
                # 清理 JSON 字符串
                json_str = json_str.replace("'", '"')  # 单引号转双引号
                json_str = re.sub(r',\s*}', '}', json_str)  # 去除尾随逗号
                json_str = re.sub(r',\s*]', ']', json_str)  # 去除尾随逗号

                # 解析 JSON
                json_data = json.loads(json_str)

                print("\n提取的 JSON 数据:")
                print(json.dumps(json_data, ensure_ascii=False, indent=2))

                # 保存 JSON 到文件
                with open("analysis_result.json", "w", encoding="utf-8") as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)
                print("JSON 结果已保存到: analysis_result.json")

        except json.JSONDecodeError as e:
            print(f"JSON 解析失败: {e}")
            print("保留原始文本结果")
        except Exception as e:
            print(f"处理结果时出错: {e}")
    else:
        print("API 调用失败")


if __name__ == "__main__":
    main()