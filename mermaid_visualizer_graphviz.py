from graphviz import Digraph
import re
import os
from graphviz import Digraph
import re
import os
import cv2
import numpy as np
import sys
from PIL import ImageFont, ImageDraw, Image

# ================== SVG 转 DrawIO 转换器 ==================
# 定义图形类型常量
FORM_RECT = 1
FORM_ROUNDED_RECT = 2
FORM_POLYGON = 3
FORM_ELBOW = 4
FORM_TEXT = 5

# 全局缩放因子
GLOBAL_SCALE_FACTOR = 0.5


def apply_global_scale(value):
    return value * GLOBAL_SCALE_FACTOR


def get_text_dimensions(text, font_size, font_family, inv_scale):
    """获取文本尺寸 - 针对中文标题优化宽度计算"""
    try:
        font_paths = [
            f"{font_family}.ttf",
            "simkai.ttf",
            "simsun.ttc",
            "arial.ttf"
        ]
        font = None
        for path in font_paths:
            try:
                font = ImageFont.truetype(path, int(font_size * GLOBAL_SCALE_FACTOR * 1.5))
                break
            except IOError:
                continue
        if font is None:
            font = ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    temp_img = Image.new('RGB', (1000, 1000), (255, 255, 255))
    draw = ImageDraw.Draw(temp_img)

    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    ascent = -bbox[1]

    chinese_factor = 1.0
    if any('\u4e00' <= char <= '\u9fff' for char in text):
        chinese_factor = 1.8

    width = width * chinese_factor * 1.5
    width = width * inv_scale * GLOBAL_SCALE_FACTOR
    height = height * inv_scale * GLOBAL_SCALE_FACTOR
    ascent = ascent * inv_scale * GLOBAL_SCALE_FACTOR

    return width, height, ascent


def generate_mxcell(shape_type, idx, txt, x, y, w=None, h=None, style_ext=""):
    styles = {
        FORM_RECT: "rounded=0;whiteSpace=wrap;html=1;fillColor=#e0ffff;strokeColor=black;",
        FORM_ROUNDED_RECT: "rounded=1;whiteSpace=wrap;html=1;fillColor=#f5f5dc;strokeColor=black;strokeDasharray=5,2;dashed=1;",
        FORM_POLYGON: "shape=rhombus;whiteSpace=wrap;html=1;",
        FORM_ELBOW: "edgeStyle=elbowEdgeStyle;html=1;rounded=1;strokeWidth=1;strokeColor=#4169e1;",
        FORM_TEXT: "shape=text;html=1;whiteSpace=nowrap;fontFamily=KaiTi;fontSize=14;fontColor=navy;align=center;verticalAlign=middle;strokeColor=none;fillColor=none;fontStyle=1"
    }

    style = styles.get(shape_type, "")
    if style_ext:
        style += style_ext

    res = f'\n<mxCell id="{idx}" value="{txt}" style="{style}" parent="1" vertex="1">'
    if w and h:
        res += f'\n  <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>'
    else:
        res += f'\n  <mxGeometry x="{x}" y="{y}" as="geometry"/>'
    res += '\n</mxCell>'
    return res


def parse_transform(transform_str):
    """解析SVG变换参数"""
    sx, sy = 1.0, 1.0
    tx, ty = 0.0, 0.0
    rotation = 0.0

    scale_match = re.search(r'scale\(([\d\.\-]+)[,\s]([\d\.\-]+)\)', transform_str)
    translate_match = re.search(r'translate\(([\d\.\-]+)[,\s]([\d\.\-]+)\)', transform_str)
    rotate_match = re.search(r'rotate\(([\d\.\-]+)', transform_str)

    if scale_match:
        sx = float(scale_match.group(1))
        sy = float(scale_match.group(2))

    if translate_match:
        tx = float(translate_match.group(1))
        ty = float(translate_match.group(2))

    if rotate_match:
        rotation = float(rotate_match.group(1))

    inv_sx = 1 / sx if sx != 0 else 1
    inv_sy = 1 / sy if sy != 0 else 1

    return sx, sy, tx, ty, inv_sx, inv_sy, rotation


def hex_to_rgba(hex_color, opacity=1.0):
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join([c * 2 for c in hex_color])
    return f'#{hex_color}{int(opacity * 255):02x}' if opacity < 1.0 else f'#{hex_color}'


def convert_svg_to_drawio(svg_file):
    xml_header = '''<mxfile host="www.diagrams.net">
        <diagram name="Page-1">
          <mxGraphModel dx="100" dy="100" grid="1" gridSize="10">
            <root>
              <mxCell id="0"/>
              <mxCell id="1" parent="0"/>'''
    xml_footer = '''\n            </root>
          </mxGraphModel>
        </diagram>
      </mxfile>'''

    rounded_rects = []
    other_shapes = []
    text_elements = []
    edges = []
    idx_counter = 2
    node_id_map = {}

    sx, sy, tx, ty, inv_sx, inv_sy, rotation = 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0
    viewbox = [0, 0, 1000, 1000]

    with open(f"{svg_file}.svg", 'r', encoding='utf-8') as f:
        svg_content = f.read()

        viewbox_match = re.search(r'viewBox="([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)"', svg_content)
        if viewbox_match:
            viewbox = list(map(float, viewbox_match.groups()))

        graph_match = re.search(r'<g[^>]*transform="([^"]*)"', svg_content)
        if graph_match:
            sx, sy, tx, ty, inv_sx, inv_sy, rotation = parse_transform(graph_match.group(1))

        for cluster in re.finditer(r'<path\s+[^>]*fill="#f5f5dc"[^>]*d="([^"]*)"', svg_content):
            path_data = cluster.group(1)
            points = re.findall(r'([\d\.\-]+),([\d\.\-]+)', path_data)
            if len(points) >= 4:
                x_coords = []
                y_coords = []
                for x, y in points:
                    x_val, y_val = float(x), float(y)
                    x_val = apply_global_scale((x_val - tx) * inv_sx)
                    y_val = apply_global_scale((y_val - ty) * inv_sy)
                    x_coords.append(x_val)
                    y_coords.append(y_val)

                x_min, x_max = min(x_coords), max(x_coords)
                y_min, y_max = min(y_coords), max(y_coords)

                rounded_rects.append(generate_mxcell(
                    FORM_ROUNDED_RECT,
                    idx_counter,
                    "",
                    x_min,
                    y_min,
                    x_max - x_min,
                    y_max - y_min
                ))
                idx_counter += 1

        for node in re.finditer(
                r'<g id="node\d+"[^>]*>.*?<title>(.*?)</title>.*?<polygon[^>]*fill="#e0ffff"[^>]*points="([^"]*)"',
                svg_content, re.DOTALL):
            node_title = node.group(1).strip()
            points = node.group(2).split()
            if len(points) >= 4:
                coords = []
                for pair in points:
                    x, y = map(float, pair.split(','))
                    x = apply_global_scale((x - tx) * inv_sx)
                    y = apply_global_scale((y - ty) * inv_sy)
                    coords.extend([x, y])

                x_coords = coords[::2]
                y_coords = coords[1::2]
                x_min, x_max = min(x_coords), max(x_coords)
                y_min, y_max = min(y_coords), max(y_coords)

                node_id_map[node_title] = idx_counter

                other_shapes.append(generate_mxcell(
                    FORM_RECT,
                    idx_counter,
                    "",
                    x_min,
                    y_min,
                    x_max - x_min,
                    y_max - y_min
                ))
                idx_counter += 1

        text_pattern = r'<text\s+[^>]*text-anchor="([^"]*)"[^>]*x="([\d\.\-]+)"\s+y="([\d\.\-]+)"[^>]*font-family="([^"]*)"[^>]*font-size="([\d\.]+)"[^>]*>(.*?)</text>'
        for text in re.finditer(text_pattern, svg_content):
            anchor, x, y, font_family, font_size, text_content = text.groups()
            x, y = float(x), float(y)
            font_size = float(font_size)

            if any(char in text_content for char in ['电源', '管理', '主控', '单元', '信号', '处理', '通信', '接口']):
                font_size *= 1.2

            x = apply_global_scale((x - tx) * inv_sx)
            y = apply_global_scale((y - ty) * inv_sy)

            text_content = re.sub(r'\s+', ' ', text_content.strip())

            width, height, ascent = get_text_dimensions(text_content, font_size, font_family, inv_sy)

            if anchor == "middle":
                x -= width / 2
            elif anchor == "end":
                x -= width

            y_adjusted = y - ascent

            text_elements.append(generate_mxcell(
                FORM_TEXT,
                idx_counter,
                text_content,
                x,
                y_adjusted,
                width,
                height
            ))
            idx_counter += 1

        edge_pattern = r'<g id="edge\d+"[^>]*>.*?<title>(.*?)&#45;&gt;(.*?)</title>.*?<path[^>]*stroke="#4169e1"[^>]*d="([^"]*)"'
        for edge in re.finditer(edge_pattern, svg_content, re.DOTALL):
            source_node = edge.group(1).strip()
            target_node = edge.group(2).strip()
            path_data = edge.group(3)

            source_id = node_id_map.get(source_node)
            target_id = node_id_map.get(target_node)

            if source_id and target_id:
                edges.append(f'''
<mxCell id="{idx_counter}" value="" style="edgeStyle=elbowEdgeStyle;html=1;rounded=1;strokeWidth=1;strokeColor=#4169e1;" edge="1" parent="1" source="{source_id}" target="{target_id}">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>''')
                idx_counter += 1

    xml_body = "".join(rounded_rects) + "".join(other_shapes) + "".join(text_elements) + "".join(edges)
    full_xml = xml_header + xml_body + xml_footer
    with open(f"{svg_file}.drawio", 'w', encoding="utf-8") as fw:
        fw.write(full_xml)


# ========== 修改节点属性以解决标签显示不全问题 ==========
def dict_to_mermaid(input_dict, direction="LR"):
    mermaid_lines = [f"graph {direction}"]
    modules = input_dict.get('模块', {})
    connections = input_dict.get('连接关系', [])
    node_id_map = {}

    for module_name, nodes in modules.items():
        mermaid_lines.append(f"    subgraph {module_name}")
        for node_str in nodes:
            if '#' in node_str:
                node_name, node_id = node_str.split('#', 1)
                node_id_map[node_id] = node_name.strip()
                mermaid_lines.append(f"        {node_id}[{node_name.strip()}]")
            else:
                node_id = node_str.replace(' ', '_')
                node_id_map[node_id] = node_str
                mermaid_lines.append(f"        {node_id}[{node_str}]")
        mermaid_lines.append("    end")

    for conn in connections:
        if '->' in conn:
            parts = conn.split('->')
            if len(parts) == 2:
                source = parts[0].strip()
                target_part = parts[1]
                if ':' in target_part:
                    target, label = target_part.split(':', 1)
                    target = target.strip()
                    label = label.strip()
                    mermaid_lines.append(f"    {source} --> |{label}| {target}")
                else:
                    target = target_part.strip()
                    mermaid_lines.append(f"    {source} --> {target}")
    return "\n".join(mermaid_lines)


def parse_mermaid_line(line):
    line = line.strip()
    label_match = re.match(r'(\w+)\s*-->\s*\|([^|]+)\|\s*(\w+)', line)
    if label_match:
        from_node, label, to_node = label_match.groups()
        return from_node, to_node, label, True
    nolabel_match = re.match(r'(\w+)\s*-->\s*(\w+)', line)
    if nolabel_match:
        from_node, to_node = nolabel_match.groups()
        return from_node, to_node, None, False
    return None, None, None, False


def mermaid_to_graphviz(
        input_data,
        output_format='png',
        output_pixel=(1920, 1080),
        bg_color='#F0F8FF',
        canvas_size=None,
        node_fillcolor='#E0FFFF',
        font_color='navy',
        edge_color='#4169E1',
        subgraph_fillcolor='#F5F5DC',
        node_border_style='solid',
        subgraph_border_style='dashed',
        subgraph_opacity=0.7,
        output_path='./power_system',
        font_family='KaiTi',
        subgraph_font_bold=True,
        node_font_bold=False,
        subgraph_rankdir='TB',
        force_size=False,
        generate_drawio=True,
        xlabel_fontsize=8,
        vertical_label_rotation=90,
        horizontal_label_rotation=0,
):
    output_dir = os.path.dirname(output_path) or '.'
    os.makedirs(output_dir, exist_ok=True)

    # rankdir = re.search(r'graph\s+(LR|TD|TB|BT|RL)',
    #                     input_data if isinstance(input_data, str) else '') or 'TB'
    # rankdir = rankdir if isinstance(rankdir, str) else rankdir.group(1)
    rankdir = 'LR'  # 强制设置为LR

    # ---------- 1. 全局 dot 属性 ----------
    graph_attr = {
        'rankdir': rankdir,
        'splines': 'ortho',  # 必须 ortho
        'nodesep': '0.5',
        'ranksep': '1.0',
        'compound': 'true',
        'fontname': font_family,
        'bgcolor': bg_color,
        'style': 'dashed',
        'penwidth': '2',
        # 'newrank': 'true'
    }
    if output_pixel:
        dpi = 300
        inch_w, inch_h = output_pixel[0] / dpi, output_pixel[1] / dpi
        graph_attr.update(size=f'{inch_w},{inch_h}', dpi=str(dpi))
    elif canvas_size:
        graph_attr['size'] = canvas_size

    node_border_attrs = {'style': 'dashed,filled', 'stroke-dasharray': '5,5'} \
        if node_border_style == 'dashed' else {'style': 'filled'}
    node_font_attrs = {'fontweight': 'bold'} if node_font_bold else {}

    # ---------- 2. 解析 mermaid ----------
    mermaid_code = (dict_to_mermaid(input_data, rankdir)
                    if isinstance(input_data, dict) else input_data)
    lines = mermaid_code.strip().split('\n')

    # 修改节点属性 - 增加节点尺寸以适应中文标签
    COMMON_NODE_ATTR = {
        'fontname': font_family,
        'fontcolor': font_color,
        'fontsize': '12',  # 增加字体大小
        'shape': 'box',
        'style': 'rounded,filled',
        'fillcolor': node_fillcolor,
        'margin': '0.15,0.10',  # 增加边距
        'width': '1.5',  # 增加最小宽度
        'height': '0.9',  # 增加最小高度
        'fixedsize': 'false',  # 允许节点根据内容调整大小
        **node_border_attrs,
        **node_font_attrs,
    }

    # ---------- 3. 第一次构建（仅用于布局） ----------
    dot = Digraph(
        comment='Power System Architecture',
        engine='dot',
        encoding='utf-8',
        graph_attr=graph_attr,
        node_attr=COMMON_NODE_ATTR,
        edge_attr={
            'fontname': font_family,
            'fontcolor': font_color,
            'color': edge_color,
            'labelfontsize': str(xlabel_fontsize),
            'fontsize': str(xlabel_fontsize),
        },
    )

    declared_nodes, edges_info = set(), []
    subgraphs, sg_nodes = {}, {}  # sg_nodes 记录每个 cluster 的节点
    current_sg = None

    for line in lines:
        line = line.strip()
        if not line or line.startswith(('linkStyle', '/*', '//', 'graph')):
            continue
        if line.startswith('subgraph'):
            m = re.match(r'subgraph\s+([^\s/*]+)', line)
            if m:
                sg_name = m.group(1)
                cluster_name = f'cluster_{sg_name}'
                sg_attr = {
                    'label': sg_name,
                    'style': 'rounded,dashed,filled',
                    'stroke-dasharray': '5,5',
                    'color': 'black',
                    'fontsize': '14',  # 增加子图字体大小
                    'fontname': font_family,
                    'rankdir': subgraph_rankdir,
                    'fillcolor': hex_to_rgba(subgraph_fillcolor.lstrip('#'), subgraph_opacity),
                }
                if subgraph_font_bold:
                    sg_attr['fontweight'] = 'bold'
                subgraphs[sg_name] = Digraph(name=cluster_name, graph_attr=sg_attr)
                sg_nodes[sg_name] = set()
                current_sg = sg_name
            continue
        if line == 'end' and current_sg:
            if not sg_nodes[current_sg]:  # 空 cluster 直接丢弃
                subgraphs.pop(current_sg)
            else:
                dot.subgraph(subgraphs[current_sg])
            current_sg = None
            continue

        # 节点
        m = re.match(r'(\w+)\[([^\]]+)\]', line)
        if m:
            node_id, node_label = m.groups()
            declared_nodes.add(node_id)
            target = subgraphs[current_sg] if current_sg else dot
            # 移除固定尺寸设置，让节点自动调整大小
            target.node(node_id, label=node_label)
            if current_sg:
                sg_nodes[current_sg].add(node_id)
            continue

        # 边
        from_node, to_node, label, is_edge = parse_mermaid_line(line)
        if is_edge:
            for n in (from_node, to_node):
                if n not in declared_nodes:
                    declared_nodes.add(n)
                    dot.node(n, n)
            edges_info.append((from_node, to_node, label))
            dot.edge(from_node, to_node, xlabel=label or '')
    # ---------- 4. 第一次渲染 ----------
    temp_svg_path = dot.render(filename=output_path + '_temp', format='svg', cleanup=True)

    # ---------- 5. 第二次构建（带 lhead/ltail） ----------
    new_dot = Digraph(
        comment='Power System Architecture Optimized',
        engine='dot',
        encoding='utf-8',
        graph_attr=graph_attr,
        node_attr=COMMON_NODE_ATTR,
        edge_attr=dot.edge_attr,
    )

    # 把节点/子图原样搬进 new_dot
    for n in declared_nodes:
        new_dot.node(n, n)
    for sg in subgraphs.values():
        new_dot.subgraph(sg)

    # 边的 lhead/ltail 自动补全
    def _find_sg(node):
        for sg_name, nodes in sg_nodes.items():
            if node in nodes:
                return f'cluster_{sg_name}'
        return None

    for from_node, to_node, label in edges_info:
        attrs = {}
        if label:
            attrs['xlabel'] = label
        fs = _find_sg(from_node)
        ts = _find_sg(to_node)
        if fs and ts and fs != ts:  # 跨 cluster
            attrs['ltail'] = fs
            attrs['lhead'] = ts
        new_dot.edge(from_node, to_node, **attrs)

    # ---------- 6. 最终渲染 ----------
    generated_path = new_dot.render(filename=output_path, format=output_format, cleanup=True)
    with open(f'{output_path}.dot', 'w', encoding='utf-8') as f:
        f.write(new_dot.source)

    # ---------- 7. 可选 SVG → DrawIO ----------
    if generate_drawio:
        try:
            new_dot.render(filename=output_path, format='svg', cleanup=False)
            convert_svg_to_drawio(output_path)
            print(f'DrawIO 文件已生成: {output_path}.drawio')
        except Exception as e:
            print(f'SVG 转 DrawIO 失败: {e}')

    # 清理
    if os.path.exists(temp_svg_path):
        os.remove(temp_svg_path)

    return new_dot, generated_path, (mermaid_code if isinstance(input_data, dict) else input_data)


# ================== 测试入口 ==================

if __name__ == "__main__":
    input_data = {
        "模块": {
            "电源": ["DC-DC稳压器#U1", "LDO稳压器#U2"],
            "主控": ["MCU#U3"],
            "信号采集": ["数据转换ADC/DAC#U4"],
            "通信和接口": ["UART#U5"],
            "控制驱动": ["电机驱动#U6", "栅极驱动器#U7"]
        },
        "连接关系": [
            "U1->U2:PWR",
            "U2->U3:PWR",
            "U3->U4:I2C",
            "U3->U5:UART",
            "U3->U6:SPI",
            "U3->U7:PWM",
            "U4->U6:ANALOG",
            "U7->U6:DRIVE"
        ]
    }

    dot, img_path, code = mermaid_to_graphviz(
        input_data,
        output_path='./power_system',
        node_border_style='dashed',
        subgraph_border_style='dashed',
        xlabel_fontsize=7,
        font_family='SimHei',
        vertical_label_rotation=90,  # 垂直边标签旋转90度
        horizontal_label_rotation=0  # 水平边标签不旋转
    ) 