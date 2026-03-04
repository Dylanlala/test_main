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


# ================== Mermaid 转 Graphviz 和 DrawIO ==================
def changename(name):
    if '#' in name:
        newname = name[:name.index('#')]
    else:
        newname = name
    return newname


def hex_to_rgba(hex_color, opacity=1.0):
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join([c * 2 for c in hex_color])
    return f'#{hex_color}{int(opacity * 255):02x}' if opacity < 1.0 else f'#{hex_color}'


def parse_node(line):
    edge_label_match = re.match(r'^\s*\|\s*([^|]+)\s*\|\s*(.*)$', line)
    edge_label = None
    if edge_label_match:
        edge_label = edge_label_match.group(1).strip()
        line = edge_label_match.group(2).strip()

    patterns = [
        (r'^\s*(\w+)\$\$"((?:[^"\$\\]|\\.)*)"', "box"),
        (r'^\s*(\w+)\$\$([^\$\]]+)\]', "box"),
        (r'^\s*(\w+)$$([^$$]+)\]', "round"),
        (r'^\s*(\w+)$([^)]+)$', "circle"),
        (r'^\s*(\w+)\{([^}]+)\}', "diamond"),
        (r'^\s*(\w+)\$\$$$([^$$]+)\]\]', "subroutine"),
        (r'^\s*(\w+)\$\$\$([^)]+)\$\$\$', "cylinder"),
        (r'^\s*(\w+)\{\{([^}]+)\}\}', "hexagon"),
        (r'^\s*(\w+)$', "box")
    ]

    for pattern, shape in patterns:
        try:
            match = re.match(pattern, line)
            if match:
                node_id = match.group(1)
                node_text = match.group(2) if len(match.groups()) > 1 else node_id
                return node_id, node_text, shape, edge_label
        except re.error:
            continue

    if '[' in line and ']' in line:
        parts = line.split('[', 1)
        node_id = parts[0].strip()
        node_text = parts[1].split(']', 1)[0].strip()
        return node_id, node_text, "box", edge_label

    if line.strip():
        node_id = re.sub(r'[<>\|]', '', line.strip())
        return node_id, node_id, "box", edge_label

    return None, None, None, edge_label


def mermaid_to_graphviz(
        mermaid_code,
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
        generate_drawio=True
):
    output_dir = os.path.dirname(output_path) or '.'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    direction = re.search(r'graph\s+(LR|TD)', mermaid_code)
    rankdir = 'LR' if direction and direction.group(1) == 'LR' else 'TB'

    graph_attr = {
        'rankdir': rankdir,
        'splines': 'ortho',
        'nodesep': '0.5',
        'ranksep': '1.0',
        'compound': 'true',
        'fontname': font_family,
        'bgcolor': bg_color,
    }

    if output_pixel:
        target_dpi = 300
        inch_width = output_pixel[0] / target_dpi
        inch_height = output_pixel[1] / target_dpi
        graph_attr['size'] = f"{inch_width},{inch_height}"
        graph_attr['dpi'] = str(target_dpi)
    elif canvas_size:
        graph_attr['size'] = canvas_size

    node_border_attrs = {'style': 'dashed,filled', 'stroke-dasharray': '5,5'} \
        if node_border_style == 'dashed' else {'style': 'filled'}
    node_font_attrs = {'fontweight': 'bold'} if node_font_bold else {}

    dot = Digraph(
        comment='Mermaid Conversion',
        engine='dot',
        encoding='utf-8',
        graph_attr=graph_attr,
        node_attr={
            'fontname': font_family,
            'fontcolor': font_color,
            'shape': 'box',
            **node_border_attrs,
            'fillcolor': node_fillcolor,
            **node_font_attrs
        },
        edge_attr={
            'fontname': font_family,
            'fontcolor': font_color,
            'color': edge_color
        }
    )

    current_subgraph = None
    declared_nodes = set()
    subgraphs = {}
    subgraph_node_order = {}
    subgraph_nodes = {}
    explicit_subgraph_nodes = {}  # 记录显式定义的节点及其所属子图

    nodenamedict = {}
    existing_edges = set()

    arrow_patterns = [
        (r'<-->', True),
        (r'-->', False),
        (r'->', False)
    ]

    lines = mermaid_code.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith(('linkStyle', '/*', '//', 'graph')) or not line:
            continue

        if line.startswith('subgraph'):
            match = re.match(r'subgraph\s+([^\s/*]+)', line)
            if match:
                subgraph_name = match.group(1)
                cluster_name = f'cluster_{subgraph_name}'
                subgraph_attrs = {
                    'label': subgraph_name,
                    'style': 'rounded,filled',
                    'color': 'black',
                    'fontsize': '12',
                    'fontname': font_family,
                    'rankdir': subgraph_rankdir
                }

                if subgraph_font_bold:
                    subgraph_attrs['fontweight'] = 'bold'

                if subgraph_opacity < 1.0:
                    subgraph_attrs['fillcolor'] = hex_to_rgba(
                        subgraph_fillcolor.lstrip('#'), subgraph_opacity
                    )
                else:
                    subgraph_attrs['fillcolor'] = subgraph_fillcolor

                if subgraph_border_style == 'dashed':
                    subgraph_attrs['style'] = 'rounded,dashed,filled'
                    subgraph_attrs['stroke-dasharray'] = '5,5'

                subgraphs[subgraph_name] = Digraph(
                    name=cluster_name,
                    graph_attr=subgraph_attrs
                )
                current_subgraph = subgraph_name
                subgraph_node_order[subgraph_name] = []
                subgraph_nodes[subgraph_name] = []

        elif line == 'end' and current_subgraph:
            # 处理子图中未连接的单个节点
            for node_id in subgraph_nodes[current_subgraph]:
                if node_id not in declared_nodes:
                    declared_nodes.add(node_id)
                    node_attrs = {
                        'label': nodenamedict.get(node_id, node_id),
                        'shape': 'box',
                        'fontname': font_family,
                        'fontcolor': font_color,
                        'fillcolor': node_fillcolor,
                        **({'fontweight': 'bold'} if node_font_bold else {})
                    }
                    if node_border_style == 'dashed':
                        node_attrs['style'] = 'dashed,filled'
                        node_attrs['stroke-dasharray'] = '极5,5'
                    else:
                        node_attrs['style'] = 'filled'

                    # 检查节点是否显式定义在当前子图
                    if explicit_subgraph_nodes.get(node_id) == current_subgraph:
                        subgraphs[current_subgraph].node(node_id, **node_attrs)
                    else:
                        dot.node(node_id, **node_attrs)

            # 处理顺序
            nodes = subgraph_node_order[current_subgraph]
            if len(nodes) > 1:
                for i in range(len(nodes) - 1):
                    with subgraphs[current_subgraph].subgraph() as s:
                        s.attr(rank='same')
                        s.edge(nodes[i], nodes[i + 1], style='invis', constraint='true')

            dot.subgraph(subgraphs[current_subgraph])
            current_subgraph = None

        else:
            found_arrow = False
            for arrow_pattern, is_bidirectional in arrow_patterns:
                if arrow_pattern in line:
                    found_arrow = True
                    parts = re.split(r'\s*' + re.escape(arrow_pattern) + r'\s*', line)
                    if len(parts) < 2:
                        continue

                    from_part = parts[0].strip('; ')
                    to_part = parts[1].strip('; ')

                    from_node_id, from_text, from_shape, edge_label = parse_node(from_part)
                    to_node_id, to_text, to_shape, _ = parse_node(to_part)
                    if not from_node_id or not to_node_id:
                        continue

                    from_label = changename(from_text) if from_text else from_node_id
                    to_label = changename(to_text) if to_text else to_node_id

                    # 检查并更新节点标签字典
                    if from_node_id in nodenamedict:
                        if from_label and from_label != from_node_id:
                            nodenamedict[from_node_id] = from_label
                    else:
                        nodenamedict[from_node_id] = from_label

                    if to_node_id in nodenamedict:
                        if to_label and to_label != to_node_id:
                            nodenamedict[to_node_id] = to_label
                    else:
                        nodenamedict[to_node_id] = to_label

                    # 确保节点已创建并带有最新标签
                    for node_id, label, shape in [(from_node_id, nodenamedict[from_node_id], from_shape),
                                                  (to_node_id, nodenamedict[to_node_id], to_shape)]:
                        # 如果节点已经声明过，更新其标签
                        if node_id in declared_nodes:
                            # 更新节点属性
                            node_attrs = {
                                'label': label,
                                'shape': shape,
                                'fontname': font_family,
                                'fontcolor': font_color,
                                'fillcolor': node_fillcolor,
                                **({'fontweight': 'bold'} if node_font_bold else {})
                            }
                            if node_border_style == 'dashed':
                                node_attrs['style'] = 'dashed,filled'
                                node_attrs['stroke-dasharray'] = '5,5'
                            else:
                                node_attrs['style'] = 'filled'

                            # 更新节点
                            if current_subgraph:
                                subgraphs[current_subgraph].node(node_id, **node_attrs)
                            else:
                                dot.node(node_id, **node_attrs)
                        else:
                            # 节点尚未声明，创建新节点
                            declared_nodes.add(node_id)
                            node_attrs = {
                                'label': label,
                                'shape': shape,
                                'fontname': font_family,
                                'fontcolor': font_color,
                                'fillcolor': node_fillcolor,
                                **({'fontweight': 'bold'} if node_font_bold else {})
                            }
                            if node_border_style == 'dashed':
                                node_attrs['style'] = 'dashed,filled'
                                node_attrs['stroke-dasharray'] = '5,5'
                            else:
                                node_attrs['style'] = 'filled'

                            # 如果当前在子图中且节点是显式定义（有方括号）
                            if current_subgraph and '[' in line and ']' in line:
                                explicit_subgraph_nodes[node_id] = current_subgraph
                                subgraphs[current_subgraph].node(node_id, **node_attrs)
                                subgraph_node_order[current_subgraph].append(node_id)
                                subgraph_nodes[current_subgraph].append(node_id)
                            else:
                                dot.node(node_id, **node_attrs)

                    # 创建边
                    edges_to_create = []
                    if is_bidirectional:
                        edges_to_create.append((from_node_id, to_node_id))
                        edges_to_create.append((to_node_id, from_node_id))
                    else:
                        edges_to_create.append((from_node_id, to_node_id))

                    for src, dst in edges_to_create:
                        edge_key = (src, dst)
                        if edge_key in existing_edges:
                            continue
                        existing_edges.add(edge_key)
                        edge_attrs = {'arrowhead': 'normal'}
                        if edge_label:
                            edge_attrs['label'] = edge_label

                        for sg_name, sg in subgraphs.items():
                            if src in [n for n in sg.body if n.startswith('\t')]:
                                edge_attrs['ltail'] = f'cluster_{sg_name}'
                            if dst in [n for n in sg.body if n.startswith('\t')]:
                                edge_attrs['lhead'] = f'cluster_{sg_name}'

                        dot.edge(src, dst, **edge_attrs)

                    break

            if not found_arrow:
                node_id, node_text, shape, _ = parse_node(line)
                if node_id and node_text:
                    # 更新节点标签字典
                    if node_id in nodenamedict:
                        if node_text and node_text != node_id:
                            nodenamedict[node_id] = changename(node_text)
                    else:
                        nodenamedict[node_id] = changename(node_text)

                    # 创建或更新节点
                    if node_id in declared_nodes:
                        # 更新现有节点
                        node_attrs = {
                            'label': nodenamedict[node_id],
                            'shape': shape,
                            'fontname': font_family,
                            'fontcolor': font_color,
                            'fillcolor': node_fillcolor,
                            **({'fontweight': 'bold'} if node_font_bold else {})
                        }
                        if node_border_style == 'dashed':
                            node_attrs['style'] = 'dashed,filled'
                            node_attrs['stroke-dasharray'] = '5,5'
                        else:
                            node_attrs['style'] = 'filled'

                        if current_subgraph:
                            subgraphs[current_subgraph].node(node_id, **node_attrs)
                        else:
                            dot.node(node_id, **node_attrs)
                    else:
                        # 创建新节点
                        declared_nodes.add(node_id)
                        node_attrs = {
                            'label': nodenamedict[node_id],
                            'shape': shape,
                            'fontname': font_family,
                            'fontcolor': font_color,
                            'fillcolor': node_fillcolor,
                            **({'fontweight': 'bold'} if node_font_bold else {})
                        }
                        if node_border_style == 'dashed':
                            node_attrs['style'] = 'dashed,filled'
                            node_attrs['stroke-dasharray'] = '5,5'
                        else:
                            node_attrs['style'] = 'filled'

                        # 如果当前在子图中且节点是显式定义（有方括号）
                        if current_subgraph and '[' in line and ']' in line:
                            explicit_subgraph_nodes[node_id] = current_subgraph
                            subgraphs[current_subgraph].node(node_id, **node_attrs)
                            subgraph_node_order[current_subgraph].append(node_id)
                            subgraph_nodes[current_subgraph].append(node_id)
                        else:
                            dot.node(node_id, **node_attrs)

    # 生成图像
    generated_path = dot.render(
        filename=output_path,
        format=output_format,
        cleanup=True
    )

    if force_size and output_pixel and generated_path:
        target_width, target_height = output_pixel
        img = cv2.imread(generated_path)
        if img is not None:
            original_height, original_width = img.shape[:2]
            ratio = min(target_width / original_width, target_height / original_height)
            new_width = int(original_width * ratio)
            new_height = int(original_height * ratio)
            resized_img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)

            bg_bgr = (255, 255, 255)
            if bg_color.startswith('#'):
                hex_color = bg_color.lstrip('#')
                if len(hex_color) == 3:
                    hex_color = ''.join(c * 2 for c in hex_color)
                if len(hex_color) == 6:
                    b = int(hex_color[4:6], 16)
                    g = int(hex_color[2:4], 16)
                    r = int(hex_color[0:2], 16)
                    bg_bgr = (b, g, r)
            canvas = np.full((target_height, target_width, 3), bg_bgr, dtype=np.uint8)

            x_offset = (target_width - new_width) // 2
            y_offset = (target_height - new_height) // 2
            canvas[y_offset:y_offset + new_height, x_offset:x_offset + new_width] = resized_img
            cv2.imwrite(generated_path, canvas)

    if generate_drawio:
        svg_path = dot.render(
            filename=output_path,
            format='svg',
            cleanup=False
        )
        try:
            convert_svg_to_drawio(output_path)
            print(f"DrawIO文件已生成: {output_path}.drawio")
        except Exception as e:
            print(f"SVG转DrawIO转换失败: {str(e)}")
            import traceback
            traceback.print_exc()

    return dot, generated_path


# ================== 测试入口 ==================
if __name__ == "__main__":
    mermaid_code = '''
    graph LR
    linkStyle default stroke: #00BFFF
    subgraph 电源管理
        PWR[电源输入#J1] --> LDO[LDO稳压器#U1]
        LDO -->|VCC| MCU
    end
    subgraph 主控单元
        MCU[MCU#U2]
    end
    subgraph 信号处理
        SENSOR[温度传感器#U3] -->|信号| AMP[信号放大器#U4]
        AMP --> ADC[ADC#U5]
        ADC -->|数字信号| MCU
    end
    subgraph 通信接口
        MCU -->|4-20mA| DAC[DAC#U6]
        DAC --> OUT[标准输出#J2]
    end
    '''
    graph, image_path = mermaid_to_graphviz(
        mermaid_code,
        output_format='png',
        output_pixel=(1920, 1080),
        bg_color='#F0F8FF',
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
        generate_drawio=True
    )

    print(f"图像已生成: {image_path}") 