import os
import base64
from volcenginesdkarkruntime import Ark

# 可选：如果系统没有安装 cairosvg，需要先安装：pip install cairosvg
try:
    import cairosvg
except ImportError:
    print("请安装 cairosvg: pip install cairosvg")
    exit(1)

# 从环境变量读取火山引擎配置
VOLCENGINE_API_KEY = "88632c3b-7c51-4517-83a1-c77957720f11"
VOLCENGINE_BASE_URL ="https://ark.cn-beijing.volces.com/api/v3"
VOLCENGINE_MODEL = "doubao-seed-2-0-pro-260215"

if not VOLCENGINE_API_KEY:
    print("错误：环境变量 VOLCENGINE_API_KEY 未设置")
    exit(1)

# 本地 SVG 图片路径
image_path = "blockdiagram.svg"
if not os.path.exists(image_path):
    print(f"错误：本地图片文件不存在: {image_path}")
    exit(1)

# 将 SVG 转换为 PNG 字节流
try:
    png_data = cairosvg.svg2png(url=image_path)
except Exception as e:
    print(f"SVG 转换 PNG 失败: {e}")
    exit(1)

# 编码为 Base64
image_base64 = base64.b64encode(png_data).decode("utf-8")
data_uri = f"data:image/png;base64,{image_base64}"

# 创建客户端
client = Ark(base_url=VOLCENGINE_BASE_URL, api_key=VOLCENGINE_API_KEY)

# 调用 API
response = client.responses.create(
    model=VOLCENGINE_MODEL,
    input=[
        {
            "role": "user",
            "content": [
                {
                    "type": "input_image",
                    "image_url": data_uri
                },
                {
                    "type": "input_text",
                    "text": """请你详细分析图中的信号采集链路框图，并按以下要求输出：

1. **器件列表**：按照信号流向从左到右的顺序，列出图中所有的器件/模块（包括虚线框标注的模块）。对于每个器件，请说明其名称和核心功能。如核心器件有：ADC、MCU等。

2. **连接关系**：描述每个器件之间的信号连接关系（例如：差分输入信号 -> Protection -> Gain -> Filter -> ADC Drive -> REF -> ADC -> Isolation -> 后端处理单元）。如果存在分支或特殊连接，请一并说明。

3. **应用相关说明**：图中部分模块用虚线框标注了“Application Dependent”（应用相关），请解释这些模块的含义，并说明它们在整个链路中的作用以及为什么需要根据应用定制。

4. **信号流向**：简要总结整个信号链路的完整流程，从输入到输出。

请用清晰的结构输出，例如分点列出，确保信息准确完整。不要输出多余文字"""
                }
            ]
        }
    ]
)

# 处理响应并保存
output_dir = "../stage1_solution_crawl"
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "output.txt")

try:
    if hasattr(response, 'choices') and len(response.choices) > 0:
        content = response.choices[0].message.content
    elif hasattr(response, 'output') and len(response.output) > 0:
        output_item = response.output[0]
        if hasattr(output_item, 'content') and len(output_item.content) > 0:
            content = output_item.content[0].text
        else:
            content = str(output_item)
    else:
        content = str(response)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 输出已保存到 {output_path}")
except Exception as e:
    print(f"❌ 保存文件时出错: {e}")
    backup_path = os.path.join(output_dir, "output_error.txt")
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(str(response))
    print(f"已将原始响应保存到 {backup_path}")