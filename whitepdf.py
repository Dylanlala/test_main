import json
import math
import markdown
import requests
from weasyprint import HTML, Document
from datetime import datetime, timedelta
from openai import OpenAI
from io import BytesIO
import re
from PIL import Image, ImageDraw, ImageFont
import os
import urllib.parse
import sys
from volcenginesdkarkruntime import Ark
from PyPDF2 import PdfMerger

base_url = "https://ark.cn-beijing.volces.com/api/v3/bots"
base_model = "bot-20250618131857-l9ffp"
with open('./static/key1.txt', 'r', encoding='utf-8') as f:
    llmkey = f.read()
client = OpenAI(
    base_url=base_url,
    api_key=llmkey
)

imgclient = Ark(
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    api_key=llmkey,
)

# 优化后的模板，简化第4章结构，移除固定数量限制
template_whitepaper = '''
# 角色与任务
你是一名资深的半导体行业技术方案架构师。你的任务是根据用户提供的需求和信息，撰写一份专业、详实、可直接用于交付或评审的技术方案书。方案书应聚焦于技术实现，包含清晰的系统架构、具体的器件选型、深入的性能分析和供应链信息。

# 输入信息
*   **用户需求与意图:** {intention}
*   **系统模块划分:** {system_block}
*   **核心器件清单（BOM）:** {bom}
*   **方案详细描述:** {description}
*   **选型依据与备注:** {selection_notes}

# 内容与风格要求
1.  **专业严谨:** 使用专业术语，数据准确，逻辑清晰，避免模糊和营销性语言。
2.  **结构完整:** 遵循标准技术方案书结构，包括摘要、需求分析、架构设计、器件选型、实现详解、测试验证等。
3.  **深度与细节:** 对关键技术和器件的分析要有深度，提供型号、供应商、关键参数和选型理由。
4.  **数据支撑:** 尽可能用表格、数据对比来呈现信息，例如性能指标对比、技术参数等。
5.  **供应链意识:** 在器件选型中体现对供应商、国产化替代、供货稳定性的考量。
6.  **规避价格:** 方案书内容不涉及任何具体价格、成本或投资回报信息。
7.  **格式清晰:** 使用副标题和适当的分段，确保内容层次分明，易于阅读。
8.  **纯文本描述:** 所有技术实现必须使用描述性文本说明，禁止使用代码、伪代码、编程语言标识符或技术缩写符号。
9.  **段落化表达:** 使用完整的段落描述技术流程，避免使用点号列表格式，确保内容流畅自然。
10. **章节完整性:** 确保每个章节都完整生成。
11. **占位符保留:** 必须保留所有标记为<!--SYSTEM_DIAGRAM_HERE-->和<!--CIRCUIT_HERE-->的占位符，这些占位符用于后续插入图表。

---
以下为 方案书固定结构 与 正文Markdown 模板，注意，Markdown正文中不要出现"[1]"、"（参考摘要2）"这种引用文章或网络检索的字样

# {{标题,反映项目核心内容的一句话，20个字以内}}  
## {{简要设计目标}}
#### **日期：{{当前日期，格式如2025-09-03}}** 

==封面分割线==(此行为固定形式分割线，不可修改)

# 1. 项目概述 

## 1.1 需求背景

### 用户原始需求
{intention}

### 技术挑战
{{根据实际情况描述主要技术挑战，可以是一个或多个}}

### 项目目标
{{根据方案特点描述具体的技术目标，包含可量化的性能指标}}

## 1.2 方案核心价值

### 技术先进性
{{描述方案的技术创新点和先进性}}

### 性能优势
{{对比传统方案或竞品，描述本方案的性能优势}}

### 应用前景
{{描述方案的主要应用场景和潜在扩展领域}}

# 2. 设计需求与指标  

## 2.1 功能需求分析
| 需求ID | 功能描述 | 优先级 | 备注 |
| :--- | :--- | :--- | :--- |
| {{根据实际情况填写功能需求表格}} |

## 2.2 技术性能指标
| 指标类别 | 参数名称 | 目标值 | 测试条件 | 备注 |
| :--- | :--- | :--- | :--- | :--- |
| {{根据方案特点填写技术性能指标表格}} |

# 3. 系统架构设计 

## 3.1 系统框图
<!--SYSTEM_DIAGRAM_HERE-->

## 3.2 模块功能描述
| 模块名称 | 核心功能 | 关键器件/技术 | 性能要求 |
| :--- | :--- | :--- | :--- |
| {{根据系统模块划分填写模块功能描述}} |

# 4. 关键器件选型与分析  

{{基于提供的BOM清单和方案描述，详细分析关键器件的选型依据、技术参数和供应商选择。重点说明核心控制器、传感器、功率器件等关键部件的选型理由和技术优势。}}

{{使用表格形式展示关键器件选型信息：}}

| 器件类型 | 推荐型号 | 供应商 | 关键参数 | 选型理由 | 备选方案 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| {{根据BOM清单填写关键器件选型表格}} |

<!--CIRCUIT_HERE-->

# 5. 实现方案详解

## 5.1 硬件实现

### PCB设计
详细描述印刷电路板的层数设计、关键高速信号线的布线策略、电源完整性规划、电磁兼容性防护措施，以及阻抗匹配方案。

### 散热设计
阐述系统采用的散热技术路径，包括散热材料选择、散热器结构设计、风道规划或液冷方案，并提供热仿真分析的关键结论。

### 结构接口
说明电子系统与机械结构的物理连接方式，包括接插件选型、安装固定方案、防震防松措施，以及维护时的拆卸便利性设计。

## 5.2 软件与算法

### 核心控制算法
详细解释采用的控制理论方法，如磁场定向控制、模型预测控制或比例积分微分控制等算法的实现原理，以及参数整定策略和稳定性保障措施。使用完整的段落描述算法流程，避免使用点号列表格式。

### 通信协议
描述系统内部各模块间采用的通信总线类型及其协议栈架构，包括物理层规范、数据链路层机制和应用层协议设计。

### 系统软件
说明嵌入式操作系统选型理由、驱动程序开发框架、中间件集成方案，以及系统启动流程和实时性保障机制。

## 5.3 创新点与技术优势

### 创新点
{{详细阐述方案的技术创新点和实现原理}}

### 技术优势
{{对比竞品或传统方案，总结本方案的核心竞争力}}

# 6. 测试与验证方案

本章节概述为确保本方案性能指标达成而规划的验证思路与方法。验证工作将分为单元测试、系统集成测试和可靠性测试三个阶段进行。单元测试将针对核心功能模块，如主控制器、传感器接口和功率驱动电路，使用示波器、逻辑分析仪和程控电源等标准仪器进行功能性验证。系统集成测试将聚焦于整机性能，验证第2章中定义的所有技术性能指标是否达标，例如在额定负载下测试输出功率和效率，在高低温实验箱中验证工作温度范围。可靠性测试将包含连续长时间的老化测试和必要的应力测试，以确保产品的长期稳定性。本验证方案旨在全面覆盖设计需求，为后续的详细设计阶段提供信心保障。

# 7. 主题关键词
{{用2~3个主题关键词总结方案书的关键词，英文输出。使用英文逗号分隔，示例：solar panel, roof, modern house}}

# 8. 图像提示词
{{生成一句英文提示词，≤50词，完整描述封面图像要求：
- 整个图像为纯白色背景(RGB 255,255,255)，无渐变、无纹理、无文字、无logo、无器件型号
- 图像下半部分包含上述方案设计相关场景，使用冷色柔和阴影，极简科技感风格
- 图像上半部分完全为空，保持与下半部分完全相同的纯白色背景
- 上下部分之间无任何可见分界线或颜色差异
- 整个图像不要出现任何字符
- 整体呈现无缝、统一的纯白色背景效果}}
'''


class WhitepaperGenerator:
    def __init__(self, openai_api_key, unsplash_api_key=None, output="./result"):
        self.openai_api_key = openai_api_key
        self.unsplash_api_key = unsplash_api_key
        self.template = template_whitepaper
        self.output = output

        # 检查WeasyPrint依赖
        self._check_dependencies()

    def _check_dependencies(self):
        """检查WeasyPrint所需依赖"""
        try:
            from weasyprint import HTML
            print("WeasyPrint导入成功")
        except ImportError as e:
            print(f"WeasyPrint导入失败: {e}")
            print("请确保已安装所需依赖:")
            print("Windows: 可能需要安装GTK3运行时环境")
            print("Linux: sudo apt-get install libpango1.0-dev libcairo2-dev")
            print("Mac: brew install pango cairo")
            sys.exit(1)

    def extract_image_prompt(self, content):
        """从生成的内容中提取图像提示词"""
        # 使用正则表达式查找图像提示词部分
        pattern = r'# 8\. 图像提示词\s*\n(.*?)(?:\s*\n\s*\n|\n#|\Z)'
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            image_prompt = match.group(1).strip()
            # 从内容中移除图像提示词部分
            content = re.sub(pattern, '', content, flags=re.DOTALL | re.IGNORECASE)
            return image_prompt, content
        return None, content

    def generate_whitepaper_content(self, intention, system_block, bom, description, selection_notes):
        """使用LLM生成白皮书内容（包含图像提示词）"""
        prompt = self.template.format(
            intention=intention,
            system_block=json.dumps(system_block, ensure_ascii=False),
            bom=json.dumps(bom, ensure_ascii=False),
            description=description,
            selection_notes=json.dumps(selection_notes, ensure_ascii=False)
        )

        response = client.chat.completions.create(
            model="bot-20250618131857-l9ffp",
            messages=[
                {"role": "user", "content": prompt},
            ],
            stream=False,
            max_tokens=8000
        )
        savecontent = response.choices[0].message.content
        with open(f'{self.output}/message_pdf.txt', 'w') as f:
            f.write(savecontent)
        md_content = response.choices[0].message.content
        md_content = re.sub(r'(?m)^\s*```(?:markdown)?\s*\n?', '', md_content)

        # 去掉结尾的 ```（整行，前后允许空白）
        md_content = re.sub(r'(?m)\n?\s*```\s*$', '', md_content)

        # 提取图像提示词
        image_prompt, md_content = self.extract_image_prompt(md_content)

        return md_content, image_prompt

    def resize_image(self, img: Image.Image, title: str, max_cell_w: int, max_cell_h: int):
        """
        返回一张上下结构的图：
        [白底黑字标题栏, 等比缩放后的原图]
        整张图宽度 = max_cell_w，高度自动，但保证能放进 max_cell_h。
        """
        # 1. 标题栏
        try:
            font = ImageFont.truetype("SimHei.ttf", 48)  # 可适当调
        except:
            font = ImageFont.load_default()
        padding_title = 20
        dummy = ImageDraw.Draw(Image.new("RGB", (1, 1), 0))
        bbox = dummy.textbbox((0, 0), title, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        title_h = th + padding_title * 2
        title_bar = Image.new("RGB", (max_cell_w, title_h), (255, 255, 255))
        ImageDraw.Draw(title_bar).text(
            ((max_cell_w - tw) // 2, padding_title),
            title, fill="black", font=font
        )

        # 2. 图片等比缩放
        img_w, img_h = img.size
        avail_h = max_cell_h - title_h  # 留给图的最大高度
        scale = min(max_cell_w / img_w, avail_h / img_h, 1.0)
        new_size = (int(img_w * scale), int(img_h * scale))
        resized_img = img.resize(new_size, Image.LANCZOS)

        # 3. 上下拼接
        total_h = title_h + resized_img.height
        out = Image.new("RGB", (max_cell_w, total_h), (255, 255, 255))
        out.paste(title_bar, (0, 0))
        out.paste(resized_img, ((max_cell_w - resized_img.width) // 2, title_h))
        return out

    def merge_circuit_images(self, circuit_path: dict, cols=2, output="typical_circuit_diagram.png"):
        """
        布局算法不变，唯一区别：
        现在 scaled_images 里每张图已经是「标题+图片」的完整大图，
        画布直接 paste，不再额外留白居中。
        """
        max_width_per_col = 800
        max_height_per_row = 600
        scaled_images = []
        for title, path in circuit_path.items():
            try:
                im = Image.open(path).convert("RGB")
                scaled_images.append(self.resize_image(im, title, max_width_per_col, max_height_per_row))
            except Exception as e:
                print(f"处理 {title} 失败: {e}")

        if not scaled_images:
            return None

        # 以下与原代码完全相同，仅删除「再次居中」的偏移量即可
        rows = math.ceil(len(scaled_images) / cols)
        row_heights = [max(img.height for img in scaled_images[r * cols:(r + 1) * cols])
                       for r in range(rows)]
        total_h = sum(row_heights) + 20 * (rows - 1)
        total_w = max_width_per_col * cols + 20 * (cols - 1)
        canvas = Image.new("RGB", (total_w, total_h), (255, 255, 255))

        y = 0
        for r in range(rows):
            row_imgs = scaled_images[r * cols:(r + 1) * cols]
            x = 0
            for img in row_imgs:
                # 直接贴，不再 (max_width_per_col-img.width)//2
                canvas.paste(img, (x, y))
                x += max_width_per_col + 20
            y += row_heights[r] + 20

        save_path = f'{self.output}/typical_circuit_diagram.png'  # os.path.join(self.temp_dir, output)
        canvas.save(save_path)
        print("典型电路图已合成:", save_path)
        return save_path

    def ensure_placeholders(self, content):
        """确保内容中包含必要的占位符"""
        # 检查系统框图占位符
        if '<!--SYSTEM_DIAGRAM_HERE-->' not in content:
            # 在第3章系统架构设计部分插入占位符
            system_diagram_pattern = r'(# 3\. 系统架构设计[^#]*)'
            system_diagram_replacement = r'\1\n\n## 3.1 系统框图\n<!--SYSTEM_DIAGRAM_HERE-->\n\n'
            content = re.sub(system_diagram_pattern, system_diagram_replacement, content, flags=re.DOTALL)

        # 检查电路图占位符
        if '<!--CIRCUIT_HERE-->' not in content:
            # 在第4章末尾插入电路图占位符
            circuit_pattern = r'(# 4\. 关键器件选型与分析[^#]*)'
            circuit_replacement = r'\1\n\n<!--CIRCUIT_HERE-->\n\n'
            content = re.sub(circuit_pattern, circuit_replacement, content, flags=re.DOTALL)

            # 如果上面的替换没找到，尝试在更宽泛的位置插入
            if '<!--CIRCUIT_HERE-->' not in content:
                # 在第4章和第五章之间插入
                chapter_pattern = r'(# 4\. 关键器件选型与分析.*?)(?=# 5\.)'
                chapter_replacement = r'\1\n\n<!--CIRCUIT_HERE-->\n\n'
                content = re.sub(chapter_pattern, chapter_replacement, content, flags=re.DOTALL)

                # 如果还是没找到，在文档末尾插入
                if '<!--CIRCUIT_HERE-->' not in content:
                    content += '\n\n<!--CIRCUIT_HERE-->\n\n'

        return content

    def replace_image_placeholders(self, content,
                                   system_diagram_path,
                                   theme_image_path,
                                   circuit_path):
        """
        替换图片占位符，使用新的锚点 <!--CIRCUIT_HERE-->
        """
        # 1. 公司 logo（右上角用）
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "logo.png")
        if os.path.exists(logo_path):
            logo_uri = "file://" + urllib.parse.quote(os.path.abspath(logo_path).replace(os.sep, "/"))
            content = f"![Logo]({logo_uri})\n" + content

        # 2. 系统框图：两张图 + 图注
        if isinstance(system_diagram_path, list) and len(system_diagram_path) >= 2:
            uri1 = "file://" + urllib.parse.quote(os.path.abspath(system_diagram_path[0]).replace(os.sep, "/"))
            uri2 = "file://" + urllib.parse.quote(os.path.abspath(system_diagram_path[1]).replace(os.sep, "/"))
            replacement = (
                f"![系统框图]({uri1})\n\n"
                "<center>图1：九宫格模块划分图</center>\n\n"
                f"![系统框图]({uri2})\n\n"
                "<center>图2：模块互连拓扑图</center>"
            )
            # 使用更宽松的匹配模式
            content = re.sub(r'<!--SYSTEM_DIAGRAM_HERE-->',
                             replacement,
                             content,
                             count=1)

        # 3. 典型电路图 - 使用新的锚点 <!--CIRCUIT_HERE-->
        if circuit_path:
            uri = "file://" + urllib.parse.quote(os.path.abspath(circuit_path).replace(os.sep, "/"))
            # 使用新的锚点替换，去掉4.1标题，直接在图片下方添加标题
            replacement = f"![典型电路图]({uri})\n\n<center>核心器件典型电路图</center>"
            # 使用更宽松的匹配模式
            content = re.sub(r'<!--CIRCUIT_HERE-->',
                             replacement,
                             content,
                             count=1)

        return content

    # 1. 生成整页 A4 背景图（上半纯白，下半主题）
    def _generate_full_page_theme(self, llm_prompt: str) -> str:
        DPI = 300
        px_w = int(210 * DPI / 25.4)  # A4 宽
        px_h = int(297 * DPI / 25.4)  # A4 高

        full_prompt = llm_prompt
        response = imgclient.images.generate(
            model="doubao-seedream-3-0-t2i-250415",
            prompt=full_prompt,
            size="1024x1024",
            response_format="url",
            watermark=False
        )
        # print(response, 111111111111)
        img_url = response.data[0].url
        theme = Image.open(BytesIO(requests.get(img_url, timeout=30).content)).convert("RGB")
        theme.save('tmp.png', quality=95)
        # 2. 等比缩放至「最短边顶满」
        scale = max(px_w / theme.width, px_h / theme.height)  # 放大系数
        new_sz = (int(theme.width * scale), int(theme.height * scale))
        theme = theme.resize(new_sz, Image.LANCZOS)

        # 3. 居中粘贴（会超出画布，但无白边）
        paste_x = (px_w - theme.width) // 2
        paste_y = (px_h - theme.height) // 2
        bg = Image.new("RGB", (px_w, px_h), (255, 255, 255))
        bg.paste(theme, (paste_x, paste_y))

        # 4. 保存
        out_path = f"{self.output}/full_cover_theme.jpg"
        bg.save(out_path, quality=95)
        bg.save('tmp1.png', quality=95)
        return "file://" + urllib.parse.quote(os.path.abspath(out_path).replace(os.sep, "/"))

    # 2. 生成 PDF（整页背景直接当封面背景）
    def generate_pdf(self, markdown_content, output_path, theme_bg_path):
        """theme_bg_path: 整页背景图路径（file://...）"""
        # 去掉分页线
        markdown_content = '\n'.join(
            line for line in markdown_content.splitlines()
            if not re.fullmatch(r'\s*-{3,}\s*', line)
        )
        parts = re.split(r'\n==封面分割线==\s*\n', markdown_content, 1)
        cover_md = parts[0].strip() if len(parts) > 1 else ''
        body_md = parts[1].strip() if len(parts) > 1 else markdown_content

        # 解析封面四要素
        cover_md = re.sub(r'!\[Logo\]\([^)]*\)', '', cover_md).strip()
        lines = [L.strip() for L in cover_md.splitlines() if L.strip()]
        title = lines[0].lstrip('#').strip() if lines else '技术方案书'
        subtitle = lines[1].lstrip('#').strip() if len(lines) > 1 else ''
        date_str = (datetime.now() + timedelta(hours=8)).strftime("%Y-%m-%d")

        # Logo 路径
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "logo.png")
        logo_uri = "file://" + urllib.parse.quote(os.path.abspath(logo_path).replace(os.sep, "/"))

        # 背景透明度设置 (0.0-1.0，值越小越透明)
        background_opacity = 0.5  # 30% 不透明度

        # 封面 HTML（使用CSS设置背景透明度）
        cover_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <title>技术方案书</title>
          <style>
            @page{{margin:0;size:A4 portrait}}
            html,body{{margin:0;padding:0;height:100%;font-family:"Helvetica Neue",Arial,sans-serif}}

            /* 使用伪元素创建带透明度的背景 */
            .cover-container {{
              position: relative;
              width: 100%;
              height: 100%;
              overflow: hidden;
            }}

            .cover-container::before {{
              content: '';
              position: absolute;
              top: 0;
              left: 0;
              width: 100%;
              height: 100%;
              background-image: url("{theme_bg_path}");
              background-size: cover;
              background-position: center;
              opacity: {background_opacity}; /* 设置背景透明度 */
              z-index: -1;
            }}

            .cover{{
              width:100%;
              height:100%;
              display:flex;
              flex-direction:column;
              align-items:center;
              justify-content:flex-start;
              padding-top:50mm;
              box-sizing:border-box;
              position: relative;
              z-index: 1;
            }}

            .logo{{
              width:120mm;
              height:auto;
              margin-bottom:10mm;
              display:block;
              margin-left:auto;
              margin-right:auto;
            }}

            .title{{
              font-size:42px;
              font-weight:bold;
              margin-bottom:8mm;
              text-align:center;
              color: #333; /* 确保文字在透明背景下仍然可见 */
              text-shadow: 1px 1px 2px rgba(255,255,255,0.7); /* 添加文字阴影增强可读性 */
            }}

            .subtitle{{
              font-size:28px;
              font-weight:bold;
              color:#333;
              margin-bottom:6mm;
              text-align:center;
              text-shadow: 1px 1px 2px rgba(255,255,255,0.7);
            }}

            .date{{
              font-size:20px;
              font-weight:bold;
              color:#333;
              text-align:center;
              text-shadow: 1px 1px 2px rgba(255,255,255,0.7);
            }}
          </style>
        </head>
        <body>
          <div class="cover-container">
            <div class="cover">
              <img class="logo" src="{logo_uri}" alt="Logo">
              <div class="title">{title}</div>
              <div class="subtitle">{subtitle}</div>
              <div class="date">{date_str}</div>
            </div>
          </div>
        </body>
        </html>"""

        # 正文 HTML（右上角 Logo）
        body_html = markdown.markdown(body_md, extensions=['tables', 'fenced_code', 'toc'])
        # 使用 @page 和 running header 实现每页右上角的 Logo
        body_full_html = f"""
                   <!DOCTYPE html>
                   <html>
                   <head>
                       <meta charset="utf-8">
                       <title>技术方案书</title>
                       <style>
                           @page {{
                               margin: 10mm 10mm;
                               @top-right {{
                                   content: element(header);
                               }}
                           }}

                           #header {{
                               position: running(header);
                               text-align: right;
                               width: 100%;
                           }}

                           .header-logo {{
                               width: 20mm;
                               height: auto;
                           }}

                           html,body{{
                               margin:0;
                               padding:0;
                               font-family:"Helvetica Neue",Arial,sans-serif;
                               line-height:1.6;
                           }}

                           h1,h2,h3{{
                               color:#2c3e50;
                           }}

                           table{{
                               border-collapse:collapse;
                               width:100%;
                               margin-bottom:20px;
                           }}

                           th,td{{
                               border:1px solid #ddd;
                               padding:8px;
                               text-align:left;
                           }}

                           th{{
                               background:#f2f2f2;
                               font-weight:bold;
                           }}

                           img{{
                               max-width:80%;
                               height:auto;
                               display:block;
                               margin:0 auto;
                           }}

                           .body-content{{
                               margin: 0 0 10mm 0;
                           }}

                           .body-content img{{
                               display:block;
                               margin:0 auto;
                               max-width:80%;
                               height:auto;
                           }}

                           /* 页脚 */
                           .footer{{
                               margin-top:40px;
                               font-size:0.8em;
                               color:#7f8c8d;
                               text-align:center;
                           }}
                       </style>
                   </head>
                   <body>
                       <div id="header">
                           <img src="{logo_uri}" class="header-logo"/>
                       </div>

                       <div class="body-content">
                           {body_html}
                       </div>
                   </body>
                   </html>
                   """

        # 渲染 & 合并
        cover_pdf = f"{self.output}/cover.pdf"
        body_pdf = f"{self.output}/body.pdf"
        HTML(string=cover_html).write_pdf(cover_pdf)
        HTML(string=body_full_html, base_url=self.output).write_pdf(body_pdf)

        merger = PdfMerger()
        merger.append(cover_pdf)
        merger.append(body_pdf)
        merger.write(output_path)
        merger.close()
        print(f"PDF 生成成功（带透明背景）: {output_path}")

    def extract_kw_and_truncate(self, md_text: str):
        """
        返回 (keywords_list, new_md_text)
        正则匹配：# 8 主题关键词
        """
        try:
            # 1. 宽松匹配：允许前导空格、任意标点、大小写
            pattern = re.compile(r'^\s*#\s*7\b[．.\s]*主题关键词\s*\n(.*)', re.S | re.I | re.M)
            m = list(pattern.finditer(md_text))[-1]  # 取最后一个
            if m:
                kw_block = m.group(1)
                truncate_pos = m.start()
            else:
                # 截取最后一行空行到文末段落：
                blank_line_pat = re.compile(r'(?:^|\n)\s*\n(.*?)\Z', re.S)
                m2 = blank_line_pat.search(md_text)
                if not m2:
                    kw_block = md_text
                    truncate_pos = 0
                else:
                    kw_block = m2.group(1)
                    truncate_pos = m2.start()

            # 2. 提取关键词
            kw_list = [k.strip() for k in kw_block.split(',') if k.strip()]
            new_text = md_text[:truncate_pos].rstrip()
            return kw_list, new_text
        except Exception as e:
            print('提取关键词失败，返回默认关键词["technology", "circuit"]')
            return ["technology", "circuit"], md_text

    def generate_whitepaper(self, intention, system_block, bom, description, selection_notes, circuit_path,
                            output_path="./result/whitepaper.pdf"):
        """生成完整白皮书"""
        try:
            output_path = f"{self.output}/whitepaper.pdf"
            # 生成内容（包含图像提示词）
            content, image_prompt = self.generate_whitepaper_content(intention, system_block, bom, description,
                                                                     selection_notes)

            # 保存原始内容用于调试
            with open(f"{self.output}/whitepdf_content_with_prompt.txt", "w", encoding='utf-8') as f:
                f.write(f"图像提示词: {image_prompt}\n\n白皮书内容:\n{content}")

            # 提取主题关键词
            theme_keywords, content = self.extract_kw_and_truncate(content)

            # 确保占位符存在
            content = self.ensure_placeholders(content)

            # 保存确保占位符后的内容用于调试
            with open(f"{self.output}/whitepdf_content_with_placeholders.txt", "w", encoding='utf-8') as f:
                f.write(f"确保占位符后的内容:\n{content}")

            bg_uri = self._generate_full_page_theme(image_prompt)
            # 系统框图地址
            system_diagram_path = [f"{self.output}/block_system.png", f"{self.output}/apply_system.png"]

            # 典型电路图合成
            merge_circuit_path = self.merge_circuit_images(circuit_path)

            # 替换图片占位符
            content = self.replace_image_placeholders(content, system_diagram_path, None, merge_circuit_path)

            # 保存最终Markdown文件用于调试
            md_path = output_path.replace('.pdf', '.md')
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Markdown文件已保存: {md_path}")

            # 生成PDF，传入主题图片路径
            self.generate_pdf(content, output_path, bg_uri)

            return output_path
        except Exception as e:
            print(f"生成白皮书时出错: {e}")
            import traceback
            traceback.print_exc()
            return None


if __name__ == "__main__":
    intention = '''
        FOC电调，BLDC电调方案.
        要求：
        1,供电5V~12V;
        2, MCU能带2路FOC马达驱动，马达转速8000~13000RPM, 无感马达
        3, 持续电流3A
        5，带串口通信，反馈电机电流，电压，功率，转速等信息
    '''
    system_block = {
        "电源": [
            "电池管理#U1",
            "DC-DC稳压器#U2"
        ],
        "主控": [
            "MCU#U3"
        ],
        "信号采集": [
            "数据转换ADC/DAC#U4"
        ],
        "通信和接口": [
            "I2C#U5",
            "UART#U6"
        ],
        "人机界面": [
            "按键/开关#U7",
            "Mipi/Lvds/Edp/Hdmi/RGB/SPI屏#U8"
        ],
        "控制驱动": [
            "栅极驱动器#U9",
            "MOSFET#U10"
        ],
        "其他": [
            "雾化器#U11"
        ]
    }
    bom = [
        {
            "元件ID": "U1",
            "型号": "BQ25601D",
            "零件名称": "电池管理",
            "规格描述": "I2C控制，支持3.7V锂电池充电管理",
            "单机用量": 1,
            "默认供应商": "TI",
            "用户指定": False
        },
        {
            "元件ID": "U2",
            "型号": "TPS63020",
            "零件名称": "DC-DC稳压器",
            "规格描述": "2.5-5.5V输入，3.3V/2A输出",
            "单机用量": 1,
            "默认供应商": "TI",
            "用户指定": False
        },
        {
            "元件ID": "U3",
            "型号": "HC32F005C6PA",
            "零件名称": "MCU",
            "规格描述": "Cortex-M0+@32MHz, 32KB Flash, 4KB RAM, LQFP-48",
            "单机用量": 1,
            "默认供应商": "XHSC|小华半导体",
            "用户指定": True
        },
        {
            "元件ID": "U4",
            "型号": "ADS1115",
            "零件名称": "数据转换ADC/DAC",
            "规格描述": "16位精度，860SPS采样率，I2C接口",
            "单机用量": 1,
            "默认供应商": "TI",
            "用户指定": False
        },
        {
            "元件ID": "U5",
            "型号": "PCA9306",
            "零件名称": "I2C",
            "规格描述": "I2C电平转换器，1.8V-5V",
            "单机用量": 1,
            "默认供应商": "NXP|恩智浦",
            "用户指定": False
        },
        {
            "元件ID": "U6",
            "型号": "MAX3232",
            "零件名称": "UART",
            "规格描述": "RS232电平转换器，3V-5.5V",
            "单机用量": 1,
            "默认供应商": "MAXIC|美芯晟",
            "用户指定": False
        },
        {
            "元件ID": "U7",
            "型号": "TS-1187A-B-A-B",
            "零件名称": "按键/开关",
            "规格描述": "6x6mm贴片按键，50万次寿命",
            "单机用量": 3,
            "默认供应商": "MOLEX|莫仕",
            "用户指定": False
        },
        {
            "元件ID": "U8",
            "型号": "SSD1306",
            "零件名称": "Mipi/Lvds/Edp/Hdmi/RGB/SPI屏",
            "规格描述": "0.96寸OLED, 128x64, SPI接口",
            "单机用量": 1,
            "默认供应商": "SOLOMON|晶门",
            "用户指定": False
        },
        {
            "元件ID": "U9",
            "型号": "TC4427",
            "零件名称": "栅极驱动器",
            "规格描述": "1.5A峰值输出，5-18V供电",
            "单机用量": 1,
            "默认供应商": "Microchip|微芯",
            "用户指定": False
        },
        {
            "元件ID": "U10",
            "型号": "IRLML6402",
            "零件名称": "MOSFET",
            "规格描述": "P沟道, -4.3A, -20V, SOT-23",
            "单机用量": 1,
            "默认供应商": "Nexperia|安世",
            "用户指定": False
        },
        {
            "元件ID": "U11",
            "型号": "Custom",
            "零件名称": "雾化器",
            "规格描述": "陶瓷芯雾化器, 1.5ohm",
            "单机用量": 1,
            "默认供应商": "其他",
            "用户指定": False
        }
    ]
    description = "本电子烟方案采用小华半导体HC32F005系列MCU作为主控，实现基于PID算法的闭环恒温控制与恒压控制。系统通过LTC2487 16位高精度ADC（采样率15SPS）实时采集雾化器温度信号，经I2C接口传输至MCU进行数字滤波处理。MCU根据预设温度曲线与实时采样值的偏差，通过PWM调制输出（频率1kHz）控制TC4427栅极驱动器，驱动NVR4501NT1G MOSFET（Rds(on)=80mΩ@4.5V）实现对陶瓷芯雾化器的精确加热控制，温度控制精度可达±1℃。\n\n电源管理系统采用SGM41511锂电池充电IC（3.9-13.5V输入，4.624V截止）与MIC2205-1.8YMLTR同步降压转换器（2.7-5.5V输入，1.8V/2A输出）构成两级供电架构，为系统提供稳定工作电压。其中MCU与ADC由LDO二次稳压供电，确保模拟电路电源纯净度。\n\n人机交互界面采用SSD1306 OLED显示屏（SPI接口）与TL3301NF100QG触觉开关（寿命10万次）组合，支持温度设定、功率模式切换及实时状态显示。系统通过UART接口预留调试端口，便于生产校准与固件升级。\n\n关键设计注意事项：\n1. LTC2487 ADC采样率（15SPS）较低，需优化软件滤波算法补偿动态响应\n2. 雾化器驱动链需增加电流采样保护电路（未在BOM体现）\n3. MIC2205输出1.8V需验证是否满足MCU最低工作电压需求\n4. SGM41511的I2C地址需避免与LTC2487冲突\n\n本方案符合PMTA认证要求，通过ISO 9001质量体系验证，EMC性能满足EN55032 Class B标准。"
    selection_notes = {}

    # 典型电路图地址
    circuit_paths = {'MAX16935BAUES/V+': '/data/alg/fae/new_version_1/result/MAX16935BAUES/V+_0.jpg', 'BL1117C': '/data/alg/fae/new_version_1/result/BL1117C_0.jpg', 'MAX22208': '/data/alg/fae/new_version_1/result/MAX22208_0.jpg', 'MAX3232': '/data/alg/fae/new_version_1/result/MAX3232_0.jpg'}

    generator = WhitepaperGenerator(
        openai_api_key=llmkey,
        unsplash_api_key="o4kgIGFSfAkLN_E8vn8I1fE6TebtCq3ERvb5M4nDErM"  # 替换为你的实际密钥
    )

    # 生成白皮书
    whitepaper_path = generator.generate_whitepaper(
        intention, system_block, bom, description, selection_notes, circuit_paths,
    )

    if whitepaper_path:
        print(f"白皮书已生成: {whitepaper_path}")
    else:
        print("白皮书生成失败")