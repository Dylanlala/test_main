from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from fuzzywuzzy import fuzz
import os
import json
import re
from collections import Counter
import copy
import cv2
import requests
import fitz
from scipy.spatial.distance import cosine
import shutil


# def clean_old_files(RESULT_DIR, hours=0.01):
#     """自动清理旧文件，默认保留2小时内的文件"""
#     now = datetime.now()
#     for filename in os.listdir(RESULT_DIR):
#         file_path = os.path.join(RESULT_DIR, filename)
#         if os.path.isfile(file_path):
#             file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
#             if (now - file_time) > timedelta(hours=hours):
#                 os.remove(file_path)
#                 # print(f"Deleted old file: {filename}")
#     print("旧文件清理完毕")
#

def clean_old_files(RESULT_DIR):
    now = datetime.now()
    try:
        # 删除整个目录（包括所有内容和子目录）
        if os.path.exists(RESULT_DIR):
            shutil.rmtree(RESULT_DIR)
            # print(f"已删除目录: {RESULT_DIR}")

        # 重新创建空目录
        os.makedirs(RESULT_DIR, exist_ok=True)
        print("目录已完全清理并重新创建")

    except Exception as e:
        print(f"完全清理目录失败: {e}")

def cv2_add_chinese_text(img, text, position, font, color, center=False):
    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    if center:
        x = position[0] - text_width // 2
        y = position[1] - text_height // 2
        position = (x, y)
    draw.text(position, text, font=font, fill=color)
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)


def displayblockimgs(imgpathlist, blockname, font, visualNcolumns=2, gap=50, hgap=30, title_height=100):
    if len(imgpathlist) > 1:
        max_height = 0
        max_width = 0
        images = []
        for path in imgpathlist:
            img = cv2.imread(path)
            if img is not None:
                images.append(img)
                max_height = max(max_height, img.shape[0])
                max_width = max(max_width, img.shape[1])

        total_width = visualNcolumns * (max_width + gap) + gap
        allimg = []
        Nrows = int(np.ceil(len(images) / visualNcolumns))

        for i in range(Nrows):
            startidx = i * visualNcolumns
            endidx = min((i + 1) * visualNcolumns, len(images))
            row_images = images[startidx:endidx]
            row_names = blockname[startidx:endidx]

            title_row = np.ones((title_height, total_width, 3), dtype=np.uint8) * 255  # 白色背景
            for j, name in enumerate(row_names):
                x_center = gap + j * (max_width + gap) + max_width // 2
                y_center = title_height // 2
                title_row = cv2_add_chinese_text(
                    title_row, name,
                    (x_center, y_center),
                    font=font, color=(0, 0, 0), center=True
                )
            allimg.append(title_row)
            row_img = np.ones((max_height, total_width, 3), dtype=np.uint8) * 255
            for j, img in enumerate(row_images):
                x_offset = gap + j * (max_width + gap)
                y_offset = (max_height - img.shape[0]) // 2
                row_img[y_offset:y_offset + img.shape[0], x_offset:x_offset + img.shape[1]] = img
            allimg.append(row_img)
            if i < Nrows - 1:
                spacing = np.ones((hgap, total_width, 3), dtype=np.uint8) * 255
                allimg.append(spacing)
        final_img = np.concatenate(allimg, axis=0)
        cv2.imwrite('./result/final_netlist.png', final_img)
        return './result/final_netlist.png'
    return imgpathlist[0]


def extract_target(text):
    pattern = r'(?:^\|.*?\|.*?\|)?([^\s|$$$$]+)(?:$$.*$$)?'
    matches = re.findall(pattern, text)
    return [m for m in matches if m]


def remove_nested_brackets(text):
    stack = []
    result = []
    for char in text:
        if char == '[':
            stack.append(char)
        elif char == ']' and stack:
            stack.pop()
        elif not stack:
            result.append(char)
    return ''.join(result)


# def processdiagram(data):
#     newgraph = 'graph LR\nlinkStyle default stroke: #00BFFF\n'
#     pattern1 = r'subgraph[^\n]*\n(.*?)\n\s*end'
#     pattern2 = r'^\s*([^-\s].*?)\s*-->\s*(.*?)$'
#     matches1 = re.findall(pattern1, data, flags=re.DOTALL)
#     subgraph_names = re.findall(r'subgraph\s+([^\n]+)', data)
#     difelements = []
#     difcontents = []
#     subgraph_elems = {}
#     for i in range(len(matches1)):
#         elements = []
#         matches2 = re.findall(pattern2, matches1[i], flags=re.MULTILINE)
#         for j in range(len(matches2)):
#             for k in range(len(matches2[j])):
#                 targetstr = extract_target(matches2[j][k])
#                 if targetstr:
#                     targetstr = remove_nested_brackets(targetstr[-1])
#                     if targetstr:
#                         if targetstr not in elements:
#                             elements.append(targetstr)
#         ###check###
#         flag = 1
#         if all(elem in ''.join(difelements) for elem in elements):
#             flag = 0
#             idx = None
#             for index, elems_list in subgraph_elems.items():
#                 if any(elem for elem in elements if elem in elems_list):
#                     idx = index
#                     break
#             rawcontent = difcontents[idx]
#             changecontent = difcontents[idx] + '\n' + matches1[i]
#             newgraph = newgraph.replace(rawcontent, changecontent)
#
#         if flag:
#             tmpelements = []
#             for ele in elements:
#                 flag = 1
#                 for k, v in subgraph_elems.items():
#                     if ele in v:
#                         flag = 0
#                 if flag:
#                     tmpelements.append(ele)
#             tmpline = "subgraph %s\n%s\nend\n" % (subgraph_names[i], matches1[i])
#             newgraph += tmpline
#             difelements += elements
#             subgraph_elems[i] = tmpelements
#             difcontents.append(matches1[i])
#
#     return newgraph

def sortgraph(data):
    # 提取全局样式
    style_match = re.search(r'linkStyle default stroke: #00BFFF', data)
    global_style = 'graph LR\nlinkStyle default stroke: #00BFFF\n' if style_match else 'graph LR\n'

    # 正则表达式提取子图和内容
    pattern1 = r'subgraph[^\n]*\n(.*?)\n\s*end'
    pattern2 = r'^\s*([^-\s].*?)\s*-->\s*(.*?)$'
    subgraph_names = re.findall(r'subgraph\s+([^\n]+)', data)
    matches1 = re.findall(pattern1, data, flags=re.DOTALL)

    # 存储子图信息和节点定义
    subgraph_data = []
    node_definitions = {}
    node_dependencies = {}

    # 处理每个子图
    for i, content in enumerate(matches1):
        # 提取子图中的节点定义
        defined_nodes = re.findall(r'(\w+)\[[^\]]+\]', content)
        # 提取所有使用的节点
        used_nodes = re.findall(r'\b(\w+)\b', content)
        # 记录子图信息
        subgraph_data.append({
            'name': subgraph_names[i],
            'content': content,
            'defines': defined_nodes,
            'uses': set(used_nodes) - set(defined_nodes)
        })
        # 注册节点定义
        for node in defined_nodes:
            node_definitions[node] = i

    # 建立依赖关系
    for i, data in enumerate(subgraph_data):
        dependencies = set()
        for node in data['uses']:
            if node in node_definitions:
                dependencies.add(node_definitions[node])
        node_dependencies[i] = dependencies

    # 拓扑排序
    sorted_indices = []
    visited = set()

    def visit(index):
        if index in visited:
            return
        visited.add(index)
        for dep in node_dependencies[index]:
            visit(dep)
        sorted_indices.append(index)

    for i in range(len(subgraph_data)):
        visit(i)

    # 按排序结果构建新图
    newgraph = global_style
    for idx in sorted_indices:
        sg = subgraph_data[idx]
        newgraph += f"subgraph {sg['name']}\n{sg['content']}\nend\n"

    return newgraph


def processdiagram(data):
    data = sortgraph(data)
    newgraph = 'graph LR\nlinkStyle default stroke: #00BFFF\n'
    pattern1 = r'subgraph[^\n]*\n(.*?)\n\s*end'
    pattern2 = r'^\s*([^-\s].*?)\s*-->\s*(.*?)$'
    pattern3 = r'^\s*([^-\s].*?)\[[^\]]+\]$'  # 新添加的模式：匹配单个节点定义

    matches1 = re.findall(pattern1, data, flags=re.DOTALL)
    subgraph_names = re.findall(r'subgraph\s+([^\n]+)', data)
    difelements = []
    difcontents = []
    subgraph_elems = {}

    for i in range(len(matches1)):
        elements = []
        content = matches1[i]

        # 匹配关系（A --> B）
        matches2 = re.findall(pattern2, content, flags=re.MULTILINE)
        for j in range(len(matches2)):
            for k in range(len(matches2[j])):
                targetstr = extract_target(matches2[j][k])
                if targetstr:
                    targetstr = remove_nested_brackets(targetstr[-1])
                    if targetstr and targetstr not in elements:
                        elements.append(targetstr)

        # 匹配单个节点定义（A[描述]）
        matches3 = re.findall(pattern3, content, flags=re.MULTILINE)
        for match in matches3:
            targetstr = extract_target(match)
            if targetstr:
                targetstr = remove_nested_brackets(targetstr[-1])
                if targetstr and targetstr not in elements:
                    elements.append(targetstr)

        # 如果没有匹配到任何元素（空子图），则跳过
        if not elements:
            continue

        ###check###
        flag = 1
        if all(elem in ''.join(difelements) for elem in elements):
            for k, v in subgraph_elems.items():
                if any(elem in ''.join(v) for elem in elements):
                    idx = k
            flag = 0
            rawcontent = difcontents[idx]
            changecontent = difcontents[idx] + '\n' + matches1[i]
            newgraph = newgraph.replace(rawcontent, changecontent)

        if flag:
            tmpelements = []
            for ele in elements:
                flag = 1
                for k, v in subgraph_elems.items():
                    if ele in v:
                        flag = 0
                if flag:
                    tmpelements.append(ele)
            tmpline = "subgraph %s\n%s\nend\n" % (subgraph_names[i], matches1[i])
            newgraph += tmpline
            difelements += elements
            subgraph_elems[i] = tmpelements
            difcontents.append(matches1[i])
    return newgraph

def parse_node(line):
    edge_label_match = re.match(r'^\s*\|\s*([^|]+)\s*\|\s*(.*)$', line)
    edge_label = None
    if edge_label_match:
        edge_label = edge_label_match.group(1).strip()
        line = edge_label_match.group(2).strip()
    patterns = [
        (r'^\s*(\w+)\$\$"((?:[^"\$\\]|\\.)*)"\]', "box"),
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



def checkbom(bom, mermaid_code, partdis=True):
    error = ''
    ####SYStem ids###
    # 修改的箭头模式列表 - 添加空模式来处理无箭头情况
    arrow_patterns = [
        (r'<-->', True),  # 双向箭头
        (r'-->', False),  # 单向箭头
        (r'->', False),  # 短单向箭头
        (r'^', False)  # 空模式，处理无箭头情况
    ]

    lines = mermaid_code.strip().split('\n')
    systemnodenamedict = {}
    blocknamedict = {}

    for line in lines:
        line = line.strip()
        found_arrow = True

        for arrow_pattern, is_bidirectional in arrow_patterns:
            # 特殊处理空模式：它永远匹配，但只处理单个节点
            if arrow_pattern == r'^':
                # 对于空模式，parts始终是单元素列表
                parts = [line.strip('; ')]
                found_arrow = False

            # 处理其他箭头模式
            elif arrow_pattern in line and found_arrow:
                found_arrow = False
                parts = re.split(r'\s*' + re.escape(arrow_pattern) + r'\s*', line)

            # 如果设置了parts，开始处理节点
            if 'parts' in locals():
                # 对于空模式，我们只需要处理一个节点（parts[0]）
                if arrow_pattern == r'^' or len(parts) >= 1:
                    # 处理第一个节点（来自节点）
                    from_part = parts[0].strip('; ')
                    from_node_id, from_node, from_shape, edge_label = parse_node(from_part)
                    blocknamefrom = copy.deepcopy(from_node_id)
                    if '#' in from_node:
                        rawnode = copy.deepcopy(from_node)
                        from_node = from_node[from_node.index('#') + 1:]
                        blocknamefrom = rawnode[:rawnode.index('#')]
                        systemnodenamedict[from_node_id] = from_node.upper()
                        blocknamedict[from_node.upper()] = blocknamefrom

                # 对于非空模式，还需要处理第二个节点（目标节点）
                if arrow_pattern != r'^' and len(parts) >= 2:
                    # 处理第二个节点（目标节点）
                    to_part = parts[1].strip('; ')
                    to_node_id, to_node, to_shape, _ = parse_node(to_part)
                    blocknameto = copy.deepcopy(to_node_id)
                    if '#' in to_node:
                        rawnode = copy.deepcopy(to_node)
                        to_node = to_node[to_node.index('#') + 1:]
                        blocknameto = rawnode[:rawnode.index('#')]
                        systemnodenamedict[to_node_id] = to_node.upper()
                        blocknamedict[to_node.upper()] = blocknameto

                # 重置parts并跳出循环
                del parts
                break

    ######check bom### (这部分保持不变)
    namedict = {}
    newbom = {'bom': []}
    newbomnodelist = []
    for i in range(len(bom["bom"])):
        bomnodes = bom["bom"][i]["元件ID"]
        maxnum = 0
        if ',' in bomnodes:
            bomnodes = bomnodes.strip().split(',')
        else:
            bomnodes = [bomnodes]
        for bomnode in bomnodes:
            if partdis:
                if 'U' in bomnode.upper():
                    if bomnode.upper() in list(systemnodenamedict.values()):
                        if maxnum < 1:
                            newbom['bom'].append(bom["bom"][i])
                            maxnum += 1
                        newbomnodelist.append(bomnode)
            else:
                if bomnode.upper() in list(systemnodenamedict.values()):
                    if maxnum < 1:
                        newbom['bom'].append(bom["bom"][i])
                        maxnum += 1
                    newbomnodelist.append(bomnode)

    for node in list(systemnodenamedict.values()):
        if partdis:
            if 'U' in node.upper() or 'Q' in node.upper() or 'D' in node.upper():
                if node not in newbomnodelist:
                    error += 'bom表中缺少id为%s的器件，请结合系统框图，在bom表中添加对应的器件' % node
        else:
            if node not in newbomnodelist:
                error += 'bom表中缺少id为%s的器件，请结合系统框图，在bom表中添加对应的器件' % node

    return newbom, error, systemnodenamedict, blocknamedict


def download_pdf(url, save_path):
    try:
        # 设置请求头模拟浏览器访问
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept-Language': 'en-US,en;q=0.9'
        }

        # 发送GET请求（启用流式下载）
        with requests.get(url, headers=headers, stream=True, timeout=10) as response:
            response.raise_for_status()  # 检查HTTP错误

            # 创建保存目录（如果不存在）
            os.makedirs(os.path.dirname(save_path), exist_ok=True)

            # 分块写入文件（节省内存）
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:  # 过滤保持活动的块
                        f.write(chunk)
        print(f"文件已下载到：{save_path}")
        return 1

    except requests.exceptions.RequestException as e:
        # print(f"网络错误：{e}")
        return 0
    except IOError as e:
        # print(f"文件写入错误：{e}")
        return 0


#
# def circuitdisplayimgs(imgpathlist,blockname,font,visualNcolumns = 3,wgap=500,hgap=200):
#     png_path = imgpathlist[0]
#     if len(imgpathlist) > 1:
#         Nrows = int(np.ceil(len(imgpathlist)/visualNcolumns))
#         allimg = []
#         wshape = []
#         wcolumns = []
#         for i in range(len(imgpathlist)):
#             img = cv2.imread(imgpathlist[i])
#             wshape.append(img.shape[1])
#         ranklist = [imgpathlist[index] for index in np.argsort(wshape)[::-1]]
#         rankblockname = [blockname[index] for index in np.argsort(wshape)[::-1]]
#         wrangelist = []
#         for i in range(Nrows):
#             startidx = int(i*visualNcolumns)
#             endidx = min(int(i*visualNcolumns+visualNcolumns),len(ranklist))
#             tmplist = ranklist[startidx:endidx]
#             tmplist = [cv2.imread(p) for p in tmplist]
#             wlist = [img.shape[1] for img in tmplist]
#             wrange = np.sum(wlist)
#             wrangelist.append(wrange)
#             if i==0:
#                 wcolumns += [img.shape[1] for img in tmplist]
#         block_w = int(np.max(wrangelist)+wgap*(visualNcolumns))
#         for i in range(Nrows):
#             startidx = int(i*visualNcolumns)
#             endidx = min(int(i*visualNcolumns+visualNcolumns),len(ranklist))
#             tmplist = ranklist[startidx:endidx]
#             tmplist = [cv2.imread(p) for p in tmplist]
#             hlist = [img.shape[0] for img in tmplist]
#             wlist = [img.shape[1] for img in tmplist]
#             tmph = max(hlist)
#             tmpblockimg = (np.ones((tmph+hgap, block_w, 3)) * 255).astype(np.uint8)
#             startw = 0
#             for j in range(len(tmplist)):
#                 starth = int((tmph-tmplist[j].shape[0])/2)
#                 tmpblockimg[starth+hgap:starth+hlist[j]+hgap,startw+wgap+int((wcolumns[j]-wlist[j])/2):wlist[j]+int((wcolumns[j]-wlist[j])/2)+startw+wgap,:] = tmplist[j]
#                 position = (100+startw, 10)  # (10, int(tmplist[j].shape[0] / 2))
#                 tmpblockimg = cv2_add_chinese_text(tmpblockimg, rankblockname[startidx + j], position, font=font,color=(0, 0, 0))
#                 startw += wcolumns[j]
#                 startw += wgap
#             allimg.append(tmpblockimg)
#         allimg = np.concatenate(allimg,axis=0)
#         cv2.imwrite(png_path, allimg)
#     return png_path


def circuitdisplayimgs(imgpathlist, blockname, font, visualNcolumns=3, wgap=500, hgap=200):
    png_path = imgpathlist[0]
    if len(imgpathlist) > 1:
        images = []
        img_sizes = []
        for path in imgpathlist:
            img = cv2.imread(path)
            images.append(img)
            img_sizes.append(img.shape)
        num_images = len(images)
        Nrows = int(np.ceil(num_images / visualNcolumns))
        col_widths = [0] * visualNcolumns
        row_img_heights = [0] * Nrows
        for idx, (h, w, _) in enumerate(img_sizes):
            row_idx = idx // visualNcolumns
            col_idx = idx % visualNcolumns
            if w > col_widths[col_idx]:
                col_widths[col_idx] = w
            if h > row_img_heights[row_idx]:
                row_img_heights[row_idx] = h
        title_height = 80
        title_img_gap = 40
        top_margin = 50
        bottom_margin = 50
        side_margin = 50

        row_total_heights = [
            title_height + title_img_gap + img_h
            for img_h in row_img_heights
        ]

        total_width = sum(col_widths) + wgap * (visualNcolumns - 1) + 2 * side_margin
        total_height = sum(row_total_heights) + hgap * (Nrows - 1) + top_margin + bottom_margin

        canvas = np.ones((total_height, total_width, 3), dtype=np.uint8) * 255

        current_y = top_margin

        for row in range(Nrows):
            current_x = side_margin
            row_img_height = row_img_heights[row]

            for col in range(visualNcolumns):
                idx = row * visualNcolumns + col
                if idx >= num_images:
                    break

                img = images[idx]
                img_h, img_w, _ = img.shape
                x_pos = current_x + (col_widths[col] - img_w) // 2
                y_pos = current_y + title_height + title_img_gap + (row_img_height - img_h) // 2
                canvas[y_pos:y_pos + img_h, x_pos:x_pos + img_w] = img
                text_x = current_x + col_widths[col] // 2
                text_y = current_y + title_height // 2
                canvas = cv2_add_chinese_text(
                    canvas,
                    blockname[idx],
                    (int(text_x), int(text_y)),
                    font=font,
                    color=(0, 0, 0),
                    center=True
                )
                current_x += col_widths[col] + wgap
            current_y += row_total_heights[row] + hgap
        cv2.imwrite(png_path, canvas)
    return png_path


def is_pdf_valid(file_path):
    try:
        doc = fitz.open(file_path)
        return len(doc) > 0
    except Exception as e:
        return False


def preprocessbrand(name):
    cleaned = re.sub(r'[^a-zA-Z0-9]', ' ', name).lower()
    abbrev = ''.join([w[0] for w in cleaned.split() if w])
    return f"{abbrev}"


def enhanced_similarity(query, target, model):
    q_proc = preprocessbrand(query)
    t_proc = preprocessbrand(target)
    lev = fuzz.ratio(q_proc, t_proc)
    q_tokens = set(q_proc.split())
    t_tokens = set(t_proc.split())
    jaccard = len(q_tokens & t_tokens) / len(q_tokens | t_tokens) * 100
    tfidf = 0
    for w in q_tokens:
        if w in t_tokens:
            tfidf += 1
    query_proc = query
    t_proc = preprocessbrand(target)
    query_emb = model.encode(query_proc)
    target_emb = model.encode(t_proc)
    semantic = 1 - cosine(query_emb, target_emb)
    return 0.2 * lev + 0.2 * jaccard + 0.2 * tfidf + 0.4 * semantic


def find_best_match(query, brand_list, model):
    max_score = -1
    best_match = None
    for brand in brand_list:
        score = enhanced_similarity(query, brand, model)
        if score > max_score:
            max_score = score
            best_match = brand
    return best_match, max_score


def generateinterface(data):
    signal_id_counter = 3824
    pattern1 = r'subgraph[^\n]*\n(.*?)\n\s*end'
    pattern2 = r'^\s*([^-\s].*?)\s*-->\s*(.*?)$'
    matches1 = re.findall(pattern1, data, flags=re.DOTALL)
    connections = []
    targetlist = []
    rawlist = []
    for i in range(len(matches1)):
        matches2 = re.findall(pattern2, matches1[i].replace(" ", ""), flags=re.MULTILINE)
        for j in range(len(matches2)):
            newpair = []
            for k in range(len(matches2[j])):
                targetstr = extract_target(matches2[j][k])
                if targetstr:
                    targetname = ''
                    if '#' in targetstr[-1]:
                        targetname = targetstr[-1][int(targetstr[-1].find('#')) + 1:-1]
                    targetstr = remove_nested_brackets(targetstr[-1])
                    if targetname:
                        rawlist.append(targetstr)
                        targetlist.append(targetname)
                    newpair.append(targetstr)
            connections.append(newpair)
    interfaces = {}
    for i in range(len(connections)):
        for j in range(len(connections[i])):
            if connections[i][j] not in interfaces:
                targetname = targetlist[rawlist.index(connections[i][j])]
                interfaces[targetname] = {"input": [], "output": []}
    for i in range(len(connections)):
        source_name = targetlist[rawlist.index(connections[i][0])]
        target_name = targetlist[rawlist.index(connections[i][1])]
        signal_desc = f"{str(signal_id_counter)}"
        interfaces[source_name]["output"].append(f"{signal_desc}->{target_name}")
        interfaces[target_name]["input"].append(f"{signal_desc}<-{source_name}")
        signal_id_counter += 1
    return interfaces


def extraid(s):
    pattern = r'(?<=\d)(?:(?=->)|(?=<-))|(\d+)(?=\s*[<-][->])'
    matches = re.findall(pattern, s)
    result = ''
    if len(matches):
        result = matches[0]
    return result


def processnetlist(rawdata, interface):
    data = list(rawdata['modules'].values())[0]
    ports = data['ports']
    cells = data['cells']
    ######
    chipid = list(rawdata['modules'].keys())[0]
    trueports = interface[str(chipid)]
    trueportsids = []
    if 'input' in trueports.keys():
        for i in range(len(trueports['input'])):
            inputid = extraid(trueports['input'][i])
            trueportsids.append(inputid)
    if 'output' in trueports.keys():
        for i in range(len(trueports['output'])):
            outputid = extraid(trueports['output'][i])
            trueportsids.append(outputid)
    trueportsids = ''.join(trueportsids)
    changenames = []
    for k, v in ports.items():
        v['bits'] = [v['bits'][0]]
        portbitID = v['bits'][0]
        # if (str(portbitID) not in trueportsids) and ('_' in k):
        #     tmpid0,tmpid1 = k.split('_')[-1],k.split('_')[0]
        #     if (str(tmpid0) not in trueportsids) and (str(tmpid1) not in trueportsids):
        #         newname = k.split('_')[0]
        #         changenames.append([newname,k])
        if (str(portbitID) not in trueportsids):
            if '_' not in k:
                changenames.append([k, k])
            else:
                tmpid0, tmpid1 = k.split('_')[-1], k.split('_')[0]
                if (str(tmpid0) not in trueportsids) and (str(tmpid1) not in trueportsids):
                    newname = k.split('_')[0]
                    changenames.append([newname, k])
    for i in range(len(changenames)):
        #     ports[changenames[i][0]] = ports.pop(changenames[i][1])
        ports.pop(changenames[i][1])
    connectIDS = []
    for k, v in cells.items():
        connections = v['connections']
        for kc, vc in connections.items():
            if len(vc):
                v['connections'][kc] = [vc[0]]
    ###port_directions和connections###校准####
    for k, v in cells.items():
        if 'U' in k.upper():
            port_directions = v['port_directions']
            connections = v['connections']
            delkp, delkc = [], []
            for kp, vp in port_directions.items():
                if kp not in list(connections.keys()):
                    delkp.append(kp)
            for kc, vc in connections.items():
                if kc not in list(port_directions.keys()):
                    delkc.append(kc)
            for kp in delkp:
                del port_directions[kp]
            for kc in delkc:
                del connections[kc]
            # print(len(v['port_directions']),len(v['connections']))
    ##### 收集所有连接到的端口ID和其它元件的连接ID #####
    # 添加ports的bitID
    for k, v in ports.items():
        portbitID = v['bits'][0]
        if portbitID not in connectIDS:
            connectIDS.append(portbitID)
    # 添加非U类型元件的所有连接ID
    for k, v in cells.items():
        if 'U' not in k.upper():
            nested_list = list(v['connections'].values())
            PbitIDs = [item for sublist in nested_list for item in sublist]
            for id in PbitIDs:
                if id not in connectIDS:
                    connectIDS.append(id)

    ##### 处理U类型芯片的连接和端口 #####
    for k, v in cells.items():
        if 'U' in k.upper():
            # 初始化新的连接和端口方向字典
            new_u_connections = {}
            new_port_directions = {}

            # 获取原始连接和端口方向
            u_connections = v['connections']
            port_directions = v['port_directions']

            # 遍历芯片的每个端口
            for port_name, conn_ids in u_connections.items():
                # 检查该端口是否连接到有效网络
                if any(cid in connectIDS for cid in conn_ids):
                    new_u_connections[port_name] = conn_ids
                    new_port_directions[port_name] = port_directions[port_name]
            ###美观防止pin太少
            for port_name, conn_ids in u_connections.items():
                if len(new_u_connections) <= 3:
                    if all(cid not in connectIDS for cid in conn_ids):
                        new_u_connections[port_name] = conn_ids
                        new_port_directions[port_name] = port_directions[port_name]

            # 更新芯片的连接和端口方向
            v['connections'] = new_u_connections
            v['port_directions'] = new_port_directions

    return rawdata


def calbitsID(rawdata, interface):
    data = list(rawdata['modules'].values())[0]
    cells = data['cells']
    UbitIDs = []
    PbitIDs = []
    interportsbitsID = []
    ######check ports###############
    chipid = list(rawdata['modules'].keys())[0]
    trueports = interface[str(chipid)]
    if 'input' in trueports.keys():
        for i in range(len(trueports['input'])):
            inputid = extraid(trueports['input'][i])
            interportsbitsID.append(int(inputid))
    if 'output' in trueports.keys():
        for i in range(len(trueports['output'])):
            outputid = extraid(trueports['output'][i])
            interportsbitsID.append(int(outputid))
    ##################################
    for k, v in cells.items():
        nested_list = list(v['connections'].values())
        if ('U' in k.upper()) or len(k)>4:
            # if len(v['connections']) == len(v['port_directions']):
            UbitIDs += [item for sublist in nested_list for item in sublist]
        else:
            tmpid = [item for sublist in nested_list for item in sublist]
            PbitIDs += list(dict.fromkeys(tmpid))
    interportsbitsID = [item for item in interportsbitsID if item not in PbitIDs + UbitIDs]
    tmp = interportsbitsID + PbitIDs + UbitIDs
    counter = Counter(tmp)
    backupbitsID = []
    for k, v in counter.items():
        if k in interportsbitsID + PbitIDs:
            if v >= 2:
                backupbitsID.append(k)
        else:
            backupbitsID.append(k)
    backupbitsID = list(dict.fromkeys(backupbitsID))
    return backupbitsID


def checknetlist2(rawdata, interface):
    data = list(rawdata['modules'].values())[0]
    backupbitsID = calbitsID(rawdata, interface)
    ports = data['ports']
    cells = data['cells']
    UbitIDs = []
    inputids = []
    outputids = []
    PbitIDs = []
    portIDs = []
    PbitNames = []
    UbitNames = []
    error = ''
    errorid = 1
    ######check ports###############
    chipid = list(rawdata['modules'].keys())[0]
    trueports = interface[str(chipid)]
    if 'input' in trueports.keys():
        for i in range(len(trueports['input'])):
            inputid = extraid(trueports['input'][i])
            if inputid not in inputids:
                inputids.append(int(inputid))
            flag = 0
            for k, v in ports.items():
                portdirection = v['direction']
                portbitID = v['bits'][0]
                if str(inputid) == str(portbitID):
                    if portdirection == 'input':
                        flag = 1
                    else:
                        flag = 1
                        v['direction'] = 'input'
                        # error.append(['ports中bitID为%s的端口%s，对应的direction有误，应该是input\n' % (portbitID, k)])
            if not flag:
                ports['%s' % inputid] = {"direction": "input", "bits": [int(inputid)]}
                if int(inputid) in backupbitsID:
                    backupbitsID.append(int(inputid))
                # error += 'ports中缺少input端口，其bitID为%s\n' % (inputid)
    if 'output' in trueports.keys():
        for i in range(len(trueports['output'])):
            outputid = extraid(trueports['output'][i])
            if outputid not in outputids:
                outputids.append(int(outputid))
            flag = 0
            for k, v in ports.items():
                portdirection = v['direction']
                portbitID = v['bits'][0]
                if str(outputid) == str(portbitID):
                    if portdirection == 'output':
                        flag = 1
                    else:
                        flag = 1
                        v['direction'] = 'output'
                        # error += 'ports中bitID为%s的端口%s，对应的direction有误，应该是output\n' % (portbitID, k)
            if not flag:
                ports['%s' % outputid] = {"direction": "output", "bits": [int(outputid)]}
                if int(outputid) in backupbitsID:
                    backupbitsID.append(int(outputid))
                # error += 'ports中缺少output端口，其bitID为%s\n' % (outputid)
    ##################################
    for k, v in cells.items():
        nested_list = list(v['connections'].values())
        name_list = list(v['connections'].keys())
        if ('U' in k.upper()) or len(k)>4:
            UbitIDs += [sublist[0] for sublist in nested_list]
            UbitNames += [sublist for sublist in name_list]
            if len(v['connections']) != len(v['port_directions']):
                error += '%s.主芯片的connections和port_directions长度不一致\n' % errorid
                errorid += 1
            for pin in v['connections']:
                if pin not in v['port_directions']:
                    error += '%s.主芯片的connections中%s的引脚未出现在port_directions中\n' % (errorid, pin)
                    errorid += 1
            for pin in v['port_directions']:
                if pin not in v['connections']:
                    error += '%s.主芯片的port_directions中%s的引脚未出现在connections中\n' % (errorid, pin)
                    errorid += 1
        else:
            PbitIDs.append([item for sublist in nested_list for item in sublist])
            PbitNames.append([k + '的%s端口' % item for sublist in name_list for item in sublist])
            ShortCircuitCheck = [item[0] for item in nested_list]
            if len(ShortCircuitCheck) != len(set(ShortCircuitCheck)):
                tmpbackupids = copy.deepcopy(backupbitsID)
                if ShortCircuitCheck[0] in tmpbackupids:
                    tmpbackupids = [x for x in tmpbackupids if x != ShortCircuitCheck[0]]
                # error += '被动元器件%s的不同端口bitsID相同，存在短接情况\n' % k
                error += '%s.将被动元器件%s的B端口bitsID，由原来的%s,从列表%s中选择一个替换\n' % (
                errorid, k, ShortCircuitCheck[1], str(list(dict.fromkeys(tmpbackupids))))
                errorid += 1
    allbitIDs = UbitIDs + [item for items in PbitIDs for item in items]
    #####check ports##
    for k, v in ports.items():
        portbitID = v['bits'][0]
        if portbitID not in portIDs:
            portIDs.append(portbitID)
        if portbitID not in UbitIDs + [item for items in PbitIDs for item in items]:
            if v["direction"] == "input":
                tmplist = [item for item in backupbitsID if item not in outputids]
            else:
                tmplist = [item for item in backupbitsID if item not in inputids]
            tmperror = '%s.将ports中%s的端口bitsID，由原来的%s，从列表%s中选择一个替换\n' % (
            errorid, k, portbitID, str(tmplist))
            error += tmperror
            errorid += 1
            if v["direction"] == "input" and portbitID in inputids:
                inputids.remove(portbitID)
            if v["direction"] == "output" and portbitID in outputids:
                outputids.remove(portbitID)
    allbitIDs += portIDs
    ####p check#####
    for i in range(len(PbitIDs)):
        for j in range(len(PbitIDs[i])):
            bit, name = PbitIDs[i][j], PbitNames[i][j]
            count = allbitIDs.count(bit)
            if count < 2:
                tmpbackupids = copy.deepcopy(backupbitsID)
                tmpbackupids = [x for x in tmpbackupids if x not in PbitIDs[i]]
                tmperror = '%s.将被动元器件的端口%s的bitsID，由原来的%s，从列表%s中选择一个替换\n' % (
                errorid, name, bit, str(tmpbackupids))
                # tmperror = 'bitIDs为%s对应的被动元器件的端口%s在其对应的cells中只出现了1次，需要继续连接其他元器件保证电路图完毕\n' % (
                # bit, name)
                error += tmperror
                errorid += 1

    #####重复ports####
    pbitscount = []
    for k, v in ports.items():
        portbitID = v['bits'][0]
        pbitscount.append(portbitID)
    pbitnames = {p: [] for p in pbitscount}
    for k, v in ports.items():
        portbitID = v['bits'][0]
        for kp, vp in pbitnames.items():
            if portbitID == kp:
                vp.append(k)
    counter = Counter(pbitscount)
    for k, v in counter.items():
        if v >= 4:
            error += '%s.在ports中,bitsID为%s的端口一共出现了%s次，这些端口名称是%s，请仔细核对，删除不重要或者没意义的端口，最多只能保留其中3个\n' % (
            errorid, k, v, str(pbitnames[k]))
            errorid += 1
            # error += '在ports中,bitsID为%s的端口一共出现了%s次，这些端口名称是%s，请仔细核对，删除这些端口中一部分\n' % (k, v,str(pbitnames[k]))
            # error += 'bitIDs为%s的端口在ports中重复出现了%s次，请核对是否需要删除部分该bitsID的ports端口\n' % (k, v)

    #####重复Uports####
    pbitnames = {p: [] for p in UbitIDs}
    for i in range(len(UbitIDs)):
        portbitID = UbitIDs[i]
        pbitnames[portbitID].append(UbitNames[i])
    counter = Counter(UbitIDs)
    for k, v in counter.items():
        if v >= 4:
            error += '%s.在主芯片配置中,port_directions和connections中bitsID为%s的端口一共出现了%s次，这些端口名称是%s，请仔细核对，从port_directions和connections中同时删除不重要或者没意义的端口，最多只能保留其中3个\n' % (
            errorid, k, v, str(pbitnames[k]))
            errorid += 1
            # error += '在ports中,bitsID为%s的端口一共出现了%s次，这些端口名称是%s，请仔细核对，删除这些端口中一部分\n' % (k, v,str(pbitnames[k]))
            # error += 'bitIDs为%s的端口在ports中重复出现了%s次，请核对是否需要删除部分该bitsID的ports端口\n' % (k, v)

    return error, rawdata
