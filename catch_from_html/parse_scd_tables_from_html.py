"""
从 HTML 中解析 scd-view-renderer 内的所有表格（VIDEO PROCESSING 等）。
不依赖 Selenium，只需 BeautifulSoup 和 pandas。

用法:
  python parse_scd_tables_from_html.py <html文件或包含HTML片段的文件> [输出目录]
  python parse_scd_tables_from_html.py sample_scd_view_renderer.html parsed_test

或作为模块:
  from parse_scd_tables_from_html import parse_scd_view_renderer_html, export_parsed_tables_to_csv
  data = parse_scd_view_renderer_html(html_string)
  export_parsed_tables_to_csv(data, "output_dir")
"""
import os
import re
import json
import csv
import sys
from typing import Dict, List, Optional
from bs4 import BeautifulSoup

try:
    import pandas as pd
except ImportError:
    pd = None


def parse_scd_view_renderer_html(html_content: str) -> List[Dict]:
    """
    从 HTML 字符串中解析 scd-view-renderer 内的所有表格内容。

    返回：[ { 'module_name', 'table_names', 'tables': [ { 'title', 'headers', 'rows' } ] }, ... ]
    每个单元格为 { 'text': str, 'link': str|None }。
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    out = []

    renderer = soup.find('div', id='scd-view-renderer')
    root = renderer if renderer else soup
    parts_list = root.find_all('div', class_='scd-partsSelected')
    if not parts_list:
        parts_list = soup.find_all('div', class_='scd-partsSelected')

    for parts_el in parts_list:
        module_name = ''
        part_title_el = parts_el.find('div', class_='scd-partTitle')
        if part_title_el:
            module_name = part_title_el.get_text(strip=True)
            # 去掉末尾的关闭/展开图标文字 "X"、"+" 及空格
            module_name = re.sub(r'\s*[X+\s]*$', '', module_name)
            module_name = re.sub(r'\s+', ' ', module_name).strip()

        table_names = []
        tables = []
        for table_elem in parts_el.find_all('div', class_='scd-partTable'):
            table_info = _parse_single_scd_table(table_elem)
            if not table_info:
                continue
            title = (table_info.get('title') or '').strip() or '未命名表格'
            table_names.append(title)
            tables.append(table_info)

        if module_name or tables:
            out.append({
                'module_name': module_name or '未命名模块',
                'table_names': table_names,
                'tables': tables
            })
    return out


def _parse_single_scd_table(table_elem) -> Optional[Dict]:
    """解析单个 .scd-partTable：标题、表头、数据行（含链接）。"""
    try:
        table_info = {'title': '', 'headers': [], 'rows': []}
        title_el = table_elem.find('div', class_='scd-tablename')
        if title_el:
            table_info['title'] = title_el.get_text(strip=True)

        table = table_elem.find('table')
        if not table:
            return table_info if table_info.get('title') else None

        header_row = table.find('tr')
        if header_row:
            for th in header_row.find_all('th'):
                h = th.get_text(strip=True)
                table_info['headers'].append(re.sub(r'\s+', ' ', h))

        for tr in table.find_all('tr')[1:]:
            if tr.parent and tr.parent.name == 'tfoot':
                continue
            if 'hide' in (tr.get('class') or []):
                continue
            if tr.find('th'):
                continue
            row_data = []
            for td in tr.find_all('td'):
                a = td.find('a')
                if a:
                    cell = {'text': a.get_text(strip=True), 'link': a.get('href') or None}
                else:
                    cell = {'text': td.get_text(strip=True), 'link': None}
                row_data.append(cell)
            if row_data:
                table_info['rows'].append(row_data)

        return table_info if table_info.get('headers') or table_info.get('rows') else None
    except Exception:
        return None


def export_parsed_tables_to_csv(module_tables_list: List[Dict], base_dir: str):
    """将解析结果导出为 CSV：每表一文件 + 一个合并表。"""
    csv_dir = os.path.join(base_dir, 'signal_chains')
    os.makedirs(csv_dir, exist_ok=True)
    tables_flat = []

    for block in module_tables_list:
        module_name = block.get('module_name', '') or '未命名模块'
        tables = block.get('tables', [])
        safe_module = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', module_name)[:60]
        for idx, table in enumerate(tables):
            title = (table.get('title') or '').strip() or '未命名表格'
            safe_title = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', title)[:60]
            if not safe_title or safe_title == '_':
                safe_title = str(idx)
            fname = f'module_{safe_module}_table_{safe_title}.csv'
            path = os.path.join(csv_dir, fname)
            headers = table.get('headers', [])
            rows = table.get('rows', [])

            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f)
                w.writerow(['模块名称', module_name])
                w.writerow(['表格名称', title])
                w.writerow(headers)
                for row in rows:
                    w.writerow([c.get('text', '') for c in row])
            print(f"  已导出: {path}")

            for row_idx, row in enumerate(rows):
                row_data = {'module_name': module_name, 'table_title': title, 'row_index': row_idx + 1}
                for col_idx, cell in enumerate(row):
                    if col_idx < len(headers):
                        h = headers[col_idx]
                        row_data[f'{h}_text'] = cell.get('text', '')
                        if cell.get('link'):
                            row_data[f'{h}_link'] = cell.get('link')
                tables_flat.append(row_data)

    if tables_flat and pd is not None:
        df = pd.DataFrame(tables_flat)
        combined = os.path.join(csv_dir, 'signal_chains_tables_parsed.csv')
        df.to_csv(combined, index=False, encoding='utf-8-sig')
        print(f"  合并表: {combined}")
    elif tables_flat and pd is None:
        combined = os.path.join(csv_dir, 'signal_chains_tables_parsed.csv')
        with open(combined, 'w', newline='', encoding='utf-8-sig') as f:
            # 简单写表头 + 行
            all_keys = set()
            for r in tables_flat:
                all_keys.update(r.keys())
            keys = ['module_name', 'table_title', 'row_index'] + sorted(k for k in all_keys if k not in ('module_name', 'table_title', 'row_index'))
            w = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
            w.writeheader()
            w.writerows(tables_flat)
        print(f"  合并表: {combined}")


def main():
    if len(sys.argv) < 2:
        print("用法: python parse_scd_tables_from_html.py <html文件> [输出目录]")
        sys.exit(1)
    html_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else 'parsed_tables_output'

    with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
        html_content = f.read()

    parsed = parse_scd_view_renderer_html(html_content)
    n_modules = len(parsed)
    n_tables = sum(len(b.get('tables', [])) for b in parsed)
    n_rows = sum(len(t.get('rows', [])) for b in parsed for t in b.get('tables', []))

    print(f"解析到 {n_modules} 个模块、{n_tables} 个表格、共 {n_rows} 行数据")
    if not parsed:
        print("未发现 scd-partsSelected 表格，请确认 HTML 包含 div#scd-view-renderer 或 div.scd-partTable")
        sys.exit(0)

    os.makedirs(out_dir, exist_ok=True)
    export_parsed_tables_to_csv(parsed, out_dir)

    json_path = os.path.join(out_dir, 'signal_chains', 'module_tables_parsed.json')
    with open(json_path, 'w', encoding='utf-8') as jf:
        json.dump(parsed, jf, ensure_ascii=False, indent=2)
    print(f"  JSON: {json_path}")


if __name__ == '__main__':
    main()
