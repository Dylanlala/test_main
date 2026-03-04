import os
import base64
import glob
import re
from openai import OpenAI

# ========== 配置区域 ==========
API_KEY = "88632c3b-7c51-4517-83a1-c77957720f11"  # 请替换为你的API密钥
BASE_DIR = "../../analog_test1"  # 根目录
SIGNAL_CHAINS_DIR = os.path.join(BASE_DIR, "下一代气象雷达", "signal_chains")
CSV_DIR = os.path.join(BASE_DIR, "下一代气象雷达", "exports_signal_chain_csv")
OUTPUT_DIR = "../stage1_solution_crawl"  # 输出目录
MODEL_NAME = "doubao-seed-2-0-pro-260215"  # 模型名称
# ==============================

# 初始化OpenAI客户端（火山引擎风格）
client = OpenAI(
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    api_key=API_KEY,
)

# 确保输出目录存在
os.makedirs(OUTPUT_DIR, exist_ok=True)


def extract_content(resp):
    """
    从火山引擎API响应中提取最终的文本内容。
    支持标准OpenAI格式和火山引擎responses格式（包含reasoning和message）。
    """
    # 如果有错误字段
    if hasattr(resp, 'error') and resp.error:
        return f"API Error: {resp.error}"

    # 标准OpenAI格式
    if hasattr(resp, 'choices') and resp.choices:
        return resp.choices[0].message.content

    # 火山引擎responses格式
    if hasattr(resp, 'output') and resp.output:
        # 优先找类型为message且角色为assistant的项
        for item in resp.output:
            if hasattr(item, 'type'):
                if item.type == 'message' and hasattr(item, 'role') and item.role == 'assistant':
                    if hasattr(item, 'content'):
                        content = item.content
                        if isinstance(content, list):
                            for part in content:
                                if hasattr(part, 'type') and part.type == 'output_text':
                                    return part.text
                                if hasattr(part, 'text'):
                                    return part.text
                            if content:
                                return str(content[0])
                        elif hasattr(content, 'text'):
                            return content.text
                        else:
                            return str(content)
                # 如果是reasoning项，尝试从summary提取文本
                elif item.type == 'reasoning':
                    if hasattr(item, 'summary') and item.summary:
                        if isinstance(item.summary, list) and len(item.summary) > 0:
                            if hasattr(item.summary[0], 'text'):
                                return item.summary[0].text
                        elif hasattr(item.summary, 'text'):
                            return item.summary.text

        # 如果没找到合适的项，回退到第一个output项的内容
        if len(resp.output) > 0:
            item = resp.output[0]
            if hasattr(item, 'content') and item.content:
                if isinstance(item.content, list) and len(item.content) > 0:
                    return item.content[0].text
                elif hasattr(item.content, 'text'):
                    return item.content.text
                else:
                    return str(item.content)
            else:
                return str(item)
        else:
            return "No output content"

    # 兜底返回字符串
    return str(resp)


def get_image_files(directory):
    """获取目录下所有常见格式的图片文件"""
    exts = ['*.png', '*.jpg', '*.jpeg', '*.bmp', '*.gif']
    files = []
    for ext in exts:
        files.extend(glob.glob(os.path.join(directory, ext)))
    return files


def encode_image_to_base64(image_path):
    """将图片文件转换为Base64编码的data URL"""
    with open(image_path, "rb") as f:
        img_data = f.read()
    ext = os.path.splitext(image_path)[1].lower()
    mime_type = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.bmp': 'image/bmp',
        '.gif': 'image/gif'
    }.get(ext, 'image/png')
    b64 = base64.b64encode(img_data).decode('utf-8')
    return f"data:{mime_type};base64,{b64}"


def analyze_image_for_mapping(image_path, csv_filenames, retries=2):
    """
    调用豆包模型分析图片，提取器件与CSV文件的映射关系。
    返回模型生成的文本（字符串），失败返回None。
    """
    # 构建CSV文件列表文本
    csv_list_text = "\n".join([f"- {name}" for name in csv_filenames])

    # 提示词：要求输出纯文本映射关系
    prompt = f"""
你是一个信号链分析专家。请分析提供的信号链图片，完成以下任务：
1. 识别图片中所有的核心器件（芯片、模块等）
2.列出每个信号链的流向。
3.分析出该信号链图片的应用场景


"""

    # 将图片转为Base64
    try:
        image_data_url = encode_image_to_base64(image_path)
    except Exception as e:
        print(f"  图片编码失败: {e}")
        return None

    for attempt in range(retries + 1):
        try:
            response = client.responses.create(
                model=MODEL_NAME,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_image",
                                "image_url": image_data_url
                            },
                            {
                                "type": "input_text",
                                "text": prompt
                            }
                        ],
                    }
                ]
            )

            # 提取文本内容
            content = extract_content(response)
            print(f"  原始响应片段: {content[:200]}...")  # 调试用

            # 直接返回模型生成的文本
            return content.strip()

        except Exception as e:
            print(f"  第{attempt + 1}次尝试调用失败: {e}")
            if attempt == retries:
                return None


def main():
    # 1. 获取所有图片文件
    image_files = get_image_files(SIGNAL_CHAINS_DIR)
    if not image_files:
        print(f"在 {SIGNAL_CHAINS_DIR} 中未找到图片文件，请检查路径。")
        return

    # 2. 获取所有CSV文件名
    csv_files = [os.path.basename(f) for f in glob.glob(os.path.join(CSV_DIR, "*.csv"))]
    print(f"找到 {len(image_files)} 张图片，{len(csv_files)} 个CSV文件。")

    # 3. 准备汇总文件
    summary_file = os.path.join(OUTPUT_DIR, "all_fast.txt")
    with open(summary_file, "w", encoding="utf-8") as summary_f:
        summary_f.write("信号链器件与CSV文件映射关系汇总\n")
        summary_f.write("=" * 50 + "\n\n")

        # 4. 逐张图片处理
        for img_path in image_files:
            img_name = os.path.basename(img_path)
            print(f"正在处理: {img_name} ...")

            result_text = analyze_image_for_mapping(img_path, csv_files)

            if result_text:
                # 保存每张图片的单独fast文件
                fast_file = os.path.join(OUTPUT_DIR, f"{os.path.splitext(img_name)[0]}_fast.txt")
                with open(fast_file, "w", encoding="utf-8") as f:
                    f.write(result_text)
                print(f"  ✅ 映射已保存至 {fast_file}")

                # 写入汇总文件
                summary_f.write(f"图片: {img_name}\n")
                summary_f.write(result_text)
                summary_f.write("\n\n")
            else:
                print(f"  ❌ 分析失败（多次重试后）")
                summary_f.write(f"图片: {img_name} - 分析失败\n\n")

    print(f"\n所有分析完成，汇总结果保存至 {summary_file}")


if __name__ == "__main__":
    main()