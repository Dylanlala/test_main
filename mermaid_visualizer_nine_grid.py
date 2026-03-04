import os
from PIL import Image, ImageDraw, ImageFont
import colorsys
import textwrap

# 定义九宫格布局
GRID_LAYOUT = [
    ["电源", "通信和接口", "人机界面"],
    ["信号采集", "主控", "控制驱动"],
    ["存储", "时钟", "其他"]
]

# 定义每个模块的正常背景颜色（浅色系）
MODULE_COLORS = {
    "电源": "#00BFFF",
    "通信和接口": "#00BFFF",
    "人机界面": "#00BFFF",
    "信号采集": "#00BFFF",
    "主控": "#00BFFF",
    "控制驱动": "#00BFFF",
    "存储": "#00BFFF",
    "时钟": "#00BFFF",
    "其他": "#00BFFF"
}

# 定义每个模块的二级节点框颜色（也用于一级标题文本颜色）
NODE_BOX_COLORS = {
    "电源": "#FF6B6B",  # 红色
    "通信和接口": "#4ECDC4",  # 青色
    "人机界面": "#45B7D1",  # 蓝色
    "信号采集": "#F9A602",  # 橙色
    "主控": "#9F7AEA",  # 紫色
    "控制驱动": "#2ecc71",  # 绿色
    "存储": "#FF9FF3",  # 粉色
    "时钟": "#F368E0",  # 紫红色
    "其他": "#FFEAA7"  # 浅黄色
}

# 自定义节点框颜色
custom_node_box_colors = {
    "电源": "#d581ad",  # 红色
    "通信和接口": "#58c9f3",  # 青色
    "人机界面": "#f59c04",  # 蓝色
    "信号采集": "#6a7c88",  # 橙色
    "主控": "#a4648e",  # 紫色
    "控制驱动": "#8bc455",  # 绿色
    "存储": "#3182a2",  # 粉色
    "时钟": "#9baab9",  # 紫红色
    "其他": "#d72323"  # 浅黄色
}

# 自定义模块背景颜色
custom_module_colors = {
    "电源": "#ebe8e7",  # 浅粉色
    "通信和接口": "#ebe8e7",  # 浅青色
    "人机界面": "#ebe8e7",  # 淡紫色
    "信号采集": "#ebe8e7",  # 柠檬绸色
    "主控": "#ebe8e7",  # 米色
    "控制驱动": "#ebe8e7",  # 蜜瓜色
    "存储": "#ebe8e7",  # 番木瓜色
    "时钟": "#ebe8e7",  # 老花色
    "其他": "#ebe8e7"  # 亮金黄色
}


# 生成暗色版本的颜色
def darken_color(hex_color, factor=0.6):
    """将颜色变暗"""
    # 转换十六进制为RGB
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)

    # 转换为HSV
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)

    # 降低亮度
    v = max(0, min(1, v * factor))

    # 转换回RGB
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    r, g, b = int(r * 255), int(g * 255), int(b * 255)

    # 转换回十六进制
    return f"#{r:02x}{g:02x}{b:02x}"


# 创建暗色版本的颜色字典
DARK_MODULE_COLORS = {k: darken_color(v) for k, v in MODULE_COLORS.items()}
DARK_NODE_BOX_COLORS = {k: darken_color(v) for k, v in NODE_BOX_COLORS.items()}


def get_text_dimensions(text, font):
    """获取文本的尺寸"""
    try:
        # 新方法
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except:
        try:
            # 旧方法
            return font.getsize(text)
        except:
            # 回退到估计值
            return len(text) * 10, 20


def get_optimal_font_size(text, max_width, max_height, initial_font_size, font_path="SimHei.ttf"):
    """根据文本长度和可用空间计算最佳字体大小"""
    font_size = initial_font_size
    min_font_size = 8  # 最小字体大小

    while font_size >= min_font_size:
        try:
            font = ImageFont.truetype(font_path, font_size)
        except:
            font = ImageFont.load_default()

        text_width, text_height = get_text_dimensions(text, font)

        # 检查文本是否适合给定的宽度和高度
        if text_width <= max_width and text_height <= max_height:
            return font_size, font

        # 如果文本不适合，减小字体大小
        font_size -= 1

    # 如果字体大小已经最小，返回最小字体
    try:
        font = ImageFont.truetype(font_path, min_font_size)
    except:
        font = ImageFont.load_default()

    return min_font_size, font


def calculate_required_height(grid_data, cell_widths, title_height=60, node_box_height=40, node_gap=30,
                              node_box_width_ratio=0.8):
    """计算每个格子需要的高度"""
    required_heights = {}
    max_required_height = 0

    for row_idx, row in enumerate(GRID_LAYOUT):
        for col_idx, title in enumerate(row):
            col_width = cell_widths[col_idx]

            # 获取节点列表
            nodes = grid_data.get(title, [])
            # 去重并保持顺序
            unique_nodes = []
            for node in nodes:
                if node not in unique_nodes:
                    unique_nodes.append(node)

            # 计算节点区域所需高度
            node_area_height = 0
            if unique_nodes:
                node_area_height = len(unique_nodes) * (node_box_height + node_gap) - node_gap

            # 总高度 = 标题区域高度 + 节点区域高度 + 底部边距
            total_height = title_height + node_area_height + 40  # 40为底部边距

            required_heights[title] = total_height
            if total_height > max_required_height:
                max_required_height = total_height

    return required_heights, max_required_height


def create_grid_image(grid_data, output_path,
                      cell_widths=[300, 300, 300], cell_height=300,
                      horizontal_gap=20, vertical_gap=20,
                      title_font_size=28, node_font_size=20,
                      node_gap=30, background_color="#FFFFFF",
                      empty_color=None,
                      node_box_height=40, node_box_width_ratio=0.8,
                      module_colors=None):
    """
    创建九宫格图像
    :param grid_data: 九宫格数据字典
    :param output_path: 输出文件路径
    :param cell_widths: 每列宽度列表（3个元素）
    :param cell_height: 单元格高度
    :param horizontal_gap: 水平间隙
    :param vertical_gap: 垂直间隙
    :param title_font_size: 标题字体大小
    :param node_font_size: 节点字体大小
    :param node_gap: 节点之间的垂直间隙
    :param background_color: 整个画布的背景颜色
    :param empty_color: 无二级节点时的背景颜色（单一颜色或{模块名:颜色}字典）
    :param node_box_height: 节点框高度
    :param node_box_width_ratio: 节点框宽度相对于单元格宽度的比例
    :param module_colors: 非空白模块背景颜色字典，键为模块名，值为颜色代码
    """
    # 确保列宽列表有3个元素
    if len(cell_widths) != 3:
        raise ValueError("cell_widths must be a list of 3 elements")

    # 计算整体图像尺寸
    cols = len(GRID_LAYOUT[0])
    rows = len(GRID_LAYOUT)

    # 计算总宽度和高度
    total_width = sum(cell_widths) + (cols + 1) * horizontal_gap
    total_height = rows * cell_height + (rows + 1) * vertical_gap

    # 创建画布
    img = Image.new('RGB', (total_width, total_height), background_color)
    draw = ImageDraw.Draw(img)

    # 设置字体
    try:
        # 标题字体 - 大号加粗
        title_font = ImageFont.truetype("SimHei.ttf", title_font_size)
    except:
        # 回退到默认字体
        title_font = ImageFont.load_default()

    # 使用自定义模块颜色（如果提供）
    current_module_colors = MODULE_COLORS.copy()
    current_dark_module_colors = DARK_MODULE_COLORS.copy()

    if module_colors:
        current_module_colors.update(module_colors)
        # 重新计算暗色版本
        current_dark_module_colors = {k: darken_color(v) for k, v in current_module_colors.items()}

    # 绘制九宫格
    for row_idx, row in enumerate(GRID_LAYOUT):
        # 计算当前行的Y坐标
        y1 = row_idx * (cell_height + vertical_gap) + vertical_gap
        y2 = y1 + cell_height

        # 初始化X坐标
        x_offset = horizontal_gap

        for col_idx, title in enumerate(row):
            # 获取当前列的宽度
            col_width = cell_widths[col_idx]

            # 计算单元格位置
            x1 = x_offset
            x2 = x1 + col_width
            x_offset = x2 + horizontal_gap  # 更新X偏移量

            # 获取节点列表
            nodes = grid_data.get(title, [])
            # 去重并保持顺序
            unique_nodes = []
            for node in nodes:
                if node not in unique_nodes:
                    unique_nodes.append(node)

            # 根据节点是否为空选择背景颜色
            if unique_nodes:
                # 有节点 - 使用正常颜色
                bg_color = current_module_colors.get(title, "#FFFFFF")
                node_box_color = NODE_BOX_COLORS.get(title, "#FFFFFF")
                title_color = NODE_BOX_COLORS.get(title, "#000000")  # 一级标题使用节点框颜色
            else:
                # 无节点 - 优先使用用户自定义颜色
                if empty_color is None:
                    bg_color = current_dark_module_colors.get(title, "#888888")
                    node_box_color = DARK_NODE_BOX_COLORS.get(title, "#888888")
                    title_color = DARK_NODE_BOX_COLORS.get(title, "#000000")  # 一级标题使用暗色节点框颜色
                elif isinstance(empty_color, dict):
                    # 按模块名指定颜色
                    bg_color = empty_color.get(title, current_dark_module_colors.get(title, "#888888"))
                    node_box_color = DARK_NODE_BOX_COLORS.get(title, "#888888")
                    title_color = DARK_NODE_BOX_COLORS.get(title, "#000000")  # 一级标题使用暗色节点框颜色
                else:
                    # 单一颜色用于所有空模块
                    bg_color = empty_color
                    node_box_color = DARK_NODE_BOX_COLORS.get(title, "#888888")
                    title_color = DARK_NODE_BOX_COLORS.get(title, "#000000")  # 一级标题使用暗色节点框颜色

            # 绘制单元格背景
            draw.rectangle([x1, y1, x2, y2], fill=bg_color)

            # 绘制单元格边框（加粗）
            draw.rectangle([x1, y1, x2, y2], outline=(0, 0, 0), width=3)

            # 绘制标题（加粗居中，使用节点框颜色）
            try:
                # 计算标题尺寸
                title_width, title_height = get_text_dimensions(title, title_font)

                # 居中绘制标题
                title_x = x1 + (col_width - title_width) / 2
                title_y = y1 + 15

                # 绘制标题主体（使用节点框颜色）
                draw.text((title_x, title_y), title, fill=title_color, font=title_font)
            except:
                # 回退到简化方法
                title_width, title_height = get_text_dimensions(title, title_font)
                draw.text(
                    (x1 + (col_width - title_width) / 2, y1 + 15),
                    title,
                    fill=title_color,
                    font=title_font
                )

            # 节点列表起始位置
            y_offset = y1 + 60

            # 计算节点框宽度
            node_box_width = int(col_width * node_box_width_ratio)
            node_box_x = x1 + (col_width - node_box_width) / 2

            # 绘制节点列表
            for node_text in unique_nodes:
                # 绘制节点框
                draw.rectangle(
                    [node_box_x, y_offset, node_box_x + node_box_width, y_offset + node_box_height],
                    fill=node_box_color,
                    outline=(0, 0, 0),
                    width=1
                )

                # 计算文本最大宽度和高度（留出边距）
                max_text_width = node_box_width - 10
                max_text_height = node_box_height - 10

                # 获取最佳字体大小
                optimal_font_size, node_font = get_optimal_font_size(
                    node_text, max_text_width, max_text_height, node_font_size
                )

                # 计算文本尺寸
                text_width, text_height = get_text_dimensions(node_text, node_font)

                # 计算文本位置（居中）
                text_x = node_box_x + (node_box_width - text_width) / 2
                text_y = y_offset + (node_box_height - text_height) / 2

                # 绘制节点文本（白色）
                draw.text(
                    (text_x, text_y),
                    node_text,
                    fill=(255, 255, 255),  # 白色文本
                    font=node_font
                )

                y_offset += node_box_height + node_gap  # 更新Y位置

                # 如果超出单元格，换到下一列
                if y_offset > y2 - 30:
                    break

    # 保存图像
    img.save(f"{output_path}.png")
    return f"{output_path}.png", total_width, total_height


def create_grid_drawio(grid_data, output_path, total_width, total_height,
                       cell_widths=[300, 300, 300], cell_height=300,
                       horizontal_gap=20, vertical_gap=20,
                       title_font_size=28, node_font_size=20,
                       node_gap=30, background_color="#FFFFFF",
                       empty_color=None,
                       node_box_height=40, node_box_width_ratio=0.8,
                       module_colors=None):
    """
    创建九宫格的Drawio文件
    :param grid_data: 九宫格数据
    :param output_path: 输出文件路径
    :param total_width: 图像总宽度
    :param total_height: 图像总高度
    :param cell_widths: 每列宽度列表
    :param cell_height: 单元格高度
    :param horizontal_gap: 水平间隙
    :param vertical_gap: 垂直间隙
    :param title_font_size: 标题字体大小
    :param node_font_size: 节点字体大小
    :param node_gap: 节点之间的垂直间隙
    :param background_color: 整个画布的背景颜色
    :param empty_color: 无二级节点时的背景颜色（单一颜色或{模块名:颜色}字典）
    :param node_box_height: 节点框高度
    :param node_box_width_ratio: 节点框宽度相对于单元格宽度的比例
    :param module_colors: 非空白模块背景颜色字典，键为模块名，值为颜色代码
    """
    # 创建Drawio XML内容
    xml_header = f'''<mxfile host="app.diagrams.net" modified="2023-08-13T14:15:12.000Z" agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36" etag="dL1HX5T7xqFzFwUfYqyW" version="15.7.3" type="device">
  <diagram name="Page-1" id="0" background="{background_color}">
    <mxGraphModel dx="1000" dy="1000" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="850" pageHeight="1100" math="0" shadow="0">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <!-- 添加背景矩形 -->
        <mxCell id="background" value="" style="shape=rectangle;whiteSpace=wrap;html=1;fillColor={background_color};strokeColor=none;" vertex="1" parent="1">
          <mxGeometry x="0" y="0" width="{total_width + 200}" height="{total_height + 200}" as="geometry" />
        </mxCell>
        <!-- Grid container -->
        <mxCell id="grid-container" value="" style="group" parent="1" vertex="1" connectable="0">
          <mxGeometry x="100" y="100" width="{total_width}" height="{total_height}" as="geometry" />
        </mxCell>
    '''

    xml_footer = '''
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
'''

    # 使用自定义模块颜色（如果提供）
    current_module_colors = MODULE_COLORS.copy()
    current_dark_module_colors = DARK_MODULE_COLORS.copy()

    if module_colors:
        current_module_colors.update(module_colors)
        # 重新计算暗色版本
        current_dark_module_colors = {k: darken_color(v) for k, v in current_module_colors.items()}

    # 生成网格单元格的XML内容
    grid_content = []
    cell_counter = 100  # 起始ID
    node_counter = 1000  # 节点ID起始值

    for row_idx, row in enumerate(GRID_LAYOUT):
        # 计算当前行的Y坐标
        y1 = row_idx * (cell_height + vertical_gap) + vertical_gap
        y2 = y1 + cell_height

        # 初始化X坐标
        x_offset = horizontal_gap

        for col_idx, title in enumerate(row):
            # 获取当前列的宽度
            col_width = cell_widths[col_idx]

            # 计算单元格位置
            x1 = x_offset
            x2 = x1 + col_width
            x_offset = x2 + horizontal_gap

            # 获取节点列表
            nodes = grid_data.get(title, [])
            # 去重并保持顺序
            unique_nodes = []
            for node in nodes:
                if node not in unique_nodes:
                    unique_nodes.append(node)

            # 根据节点是否为空选择背景颜色
            if unique_nodes:
                # 有节点 - 使用正常颜色
                bg_color = current_module_colors.get(title, "#FFFFFF")
                node_box_color = NODE_BOX_COLORS.get(title, "#FFFFFF")
                title_color = NODE_BOX_COLORS.get(title, "#000000")  # 一级标题使用节点框颜色
            else:
                # 无节点 - 优先使用用户自定义颜色
                if empty_color is None:
                    bg_color = current_dark_module_colors.get(title, "#888888")
                    node_box_color = DARK_NODE_BOX_COLORS.get(title, "#888888")
                    title_color = DARK_NODE_BOX_COLORS.get(title, "#000000")  # 一级标题使用暗色节点框颜色
                elif isinstance(empty_color, dict):
                    # 按模块名指定颜色
                    bg_color = empty_color.get(title, current_dark_module_colors.get(title, "#888888"))
                    node_box_color = DARK_NODE_BOX_COLORS.get(title, "#888888")
                    title_color = DARK_NODE_BOX_COLORS.get(title, "#000000")  # 一级标题使用暗色节点框颜色
                else:
                    # 单一颜色用于所有空模块
                    bg_color = empty_color
                    node_box_color = DARK_NODE_BOX_COLORS.get(title, "#888888")
                    title_color = DARK_NODE_BOX_COLORS.get(title, "#000000")  # 一级标题使用暗色节点框颜色

            # 创建单元格XML
            cell_xml = f'''
        <mxCell id="{cell_counter}" value="" style="rounded=0;whiteSpace=wrap;html=1;fillColor={bg_color};strokeColor=#000000;strokeWidth=3;fontSize={title_font_size};" parent="grid-container" vertex="1">
          <mxGeometry x="{x1}" y="{y1}" width="{col_width}" height="{cell_height}" as="geometry" />
        </mxCell>
            '''
            grid_content.append(cell_xml)
            cell_counter += 1

            # 添加标题 - 修复居中问题，使用节点框颜色
            title_xml = f'''
        <mxCell id="{cell_counter}" value="{title}" style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;fontSize={title_font_size};fontColor={title_color};fontStyle=1" parent="grid-container" vertex="1">
          <mxGeometry x="{x1}" y="{y1 + 15}" width="{col_width}" height="30" as="geometry" />
        </mxCell>
            '''
            grid_content.append(title_xml)
            cell_counter += 1

            # 节点列表起始位置 - 增加空隙
            node_y = y1 + 80  # 从80开始而不是60，增加20像素空隙

            # 计算节点框宽度
            node_box_width = int(col_width * node_box_width_ratio)
            node_box_x = x1 + (col_width - node_box_width) / 2

            for node_text in unique_nodes:
                # 添加节点框
                node_box_xml = f'''
        <mxCell id="{node_counter}" value="" style="rounded=0;whiteSpace=wrap;html=1;fillColor={node_box_color};strokeColor=#000000;strokeWidth=1;fontSize={node_font_size};" parent="grid-container" vertex="1">
          <mxGeometry x="{node_box_x}" y="{node_y}" width="{node_box_width}" height="{node_box_height}" as="geometry" />
        </mxCell>
                '''
                grid_content.append(node_box_xml)
                node_counter += 1

                # 添加节点文本（白色）
                node_text_xml = f'''
        <mxCell id="{node_counter}" value="{node_text}" style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;fontSize={node_font_size};fontColor=#FFFFFF;" parent="grid-container" vertex="1">
          <mxGeometry x="{node_box_x}" y="{node_y}" width="{node_box_width}" height="{node_box_height}" as="geometry" />
        </mxCell>
                '''
                grid_content.append(node_text_xml)
                node_counter += 1

                # 更新Y位置
                node_y += node_box_height + node_gap

    # 组合所有XML内容
    xml_content = xml_header + ''.join(grid_content) + xml_footer

    # 保存Drawio文件
    drawio_path = f"{output_path}.drawio"
    with open(drawio_path, "w", encoding="utf-8") as f:
        f.write(xml_content)

    return drawio_path


def generate_nine_grid(grid_data, output_path,
                       base_cell_width=300, base_cell_height=300,
                       horizontal_gap=20, vertical_gap=20,
                       title_font_size=28, node_font_size=20,
                       node_gap=30, background_color="#FFFFFF",
                       empty_color=None,
                       node_box_height=40, node_box_width_ratio=0.8,
                       node_box_colors=custom_node_box_colors,
                       module_colors=custom_module_colors):
    """
    生成九宫格图像主函数
    :param grid_data: 九宫格数据字典
    :param output_path: 输出文件路径
    :param base_cell_width: 基础单元格宽度
    :param base_cell_height: 基础单元格高度
    :param horizontal_gap: 水平间隙
    :param vertical_gap: 垂直间隙
    :param title_font_size: 标题字体大小
    :param node_font_size: 节点字体大小
    :param node_gap: 节点之间的垂直间隙
    :param background_color: 整个画布的背景颜色
    :param empty_color: 无二级节点时的背景颜色（单一颜色或{模块名:颜色}字典）
    :param node_box_height: 节点框高度
    :param node_box_width_ratio: 节点框宽度相对于单元格宽度的比例
    :param node_box_colors: 节点框颜色字典，键为模块名，值为颜色代码
    :param module_colors: 非空白模块背景颜色字典，键为模块名，值为颜色代码
    """
    # 如果提供了自定义节点框颜色，更新默认颜色
    if node_box_colors:
        for module, color in node_box_colors.items():
            if module in NODE_BOX_COLORS:
                NODE_BOX_COLORS[module] = color
                DARK_NODE_BOX_COLORS[module] = darken_color(color)

    # 清理节点数据（移除可能存在的注释）
    for k, v in grid_data.items():
        for i in range(len(v)):
            if '#' in v[i]:
                v[i] = v[i].split('#')[0]

    # 计算每个格子需要的高度
    cell_widths = [base_cell_width, base_cell_width, base_cell_width]
    required_heights, max_cell_height = calculate_required_height(
        grid_data, cell_widths,
        title_height=60,
        node_box_height=node_box_height,
        node_gap=node_gap,
        node_box_width_ratio=node_box_width_ratio
    )

    # 使用计算出的最大高度作为所有格子的高度，确保不低于基础高度
    cell_height = max(max_cell_height, base_cell_height)

    # 计算原始高宽比，并按照比例调整宽度
    aspect_ratio = base_cell_width / base_cell_height
    adjusted_cell_width = int(cell_height * aspect_ratio)

    # 使用调整后的宽度
    cell_widths = [adjusted_cell_width, adjusted_cell_width, adjusted_cell_width]

    # print(f"基础尺寸: {base_cell_width}x{base_cell_height}")
    # print(f"计算出的最大高度: {max_cell_height}")
    # print(f"使用的单元格高度: {cell_height}")
    # print(f"按照高宽比调整后的宽度: {adjusted_cell_width}")
    # print(f"最终单元格尺寸: {adjusted_cell_width}x{cell_height}")

    # for title, height in required_heights.items():
    #     print(f"模块 '{title}' 需要高度: {height}")

    # 创建九宫格图像
    image_path, total_width, total_height = create_grid_image(
        grid_data,
        output_path,
        cell_widths=cell_widths,
        cell_height=cell_height,
        horizontal_gap=horizontal_gap,
        vertical_gap=vertical_gap,
        title_font_size=title_font_size,
        node_font_size=node_font_size,
        node_gap=node_gap,
        background_color=background_color,
        empty_color=empty_color,
        node_box_height=node_box_height,
        node_box_width_ratio=node_box_width_ratio,
        module_colors=module_colors
    )

    # 生成对应的Drawio文件
    drawio_path = create_grid_drawio(
        grid_data,
        output_path,
        total_width,
        total_height,
        cell_widths=cell_widths,
        cell_height=cell_height,
        horizontal_gap=horizontal_gap,
        vertical_gap=vertical_gap,
        title_font_size=title_font_size,
        node_font_size=node_font_size,
        node_gap=node_gap,
        background_color=background_color,
        empty_color=empty_color,
        node_box_height=node_box_height,
        node_box_width_ratio=node_box_width_ratio,
        module_colors=module_colors
    )

    # print(f"九宫格图像已生成: {image_path}")
    # print(f"Drawio文件已生成: {drawio_path}")
    return image_path, drawio_path


if __name__ == "__main__":
    result_json = {
        "电源": [
            "DC-DC转换器#U1",
            "LDO稳压器#U2",
            "LDO稳压器#U3",
            "LDO稳压器#U4"
        ],
        "主控": [
            "8K超高清视频解码芯片#U5"
        ],
        "存储": [
            "DDR4内存#U6",
            "SPI NOR Flash#U7",
            "eMMC存储#U8"
        ],
        "通信和接口": [
            "HDMI接口#J1",
            "MIPI DSI接口#J2",
            "USB3.1 Host接口#J3",
            "USB2.0接口#J4",
            "SDIO接口#J5",
            "SATA接口#J6",
            "SPI接口#J7",
            "UART接口#J8",
            "I2C接口#J9",
            "IR接口#J10",
            "GPIO接口#J11"
        ],
        "时钟": [
            "高精度时钟#Y1"
        ],
        "人机界面": [
            "CVBS输出#J12",
            "音频输出#J13"
        ],
        "控制驱动": [
            "LED驱动#U9",
            "按键驱动#U10"
        ],
        "其他": [
            "LED指示灯#D1",
            "按键#K1"
        ]
    }

    _, _ = generate_nine_grid(
        result_json,
        f"./block_system_adaptive",
        base_cell_width=300,  # 基础单元格宽度
        base_cell_height=300,  # 基础单元格高度
        horizontal_gap=30,  # 水平间隙
        vertical_gap=25,  # 垂直间隙
        title_font_size=38,  # 标题字体大小
        node_font_size=32,  # 节点字体大小
        node_gap=15,  # 节点之间的垂直间隙
        background_color="#ffffff",  # 设置背景颜色
        empty_color="#ebe8e7",  # 自定义空模块背景色
        node_box_height=50,  # 节点框高度
        node_box_width_ratio=0.85
    )   