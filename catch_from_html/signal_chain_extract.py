"""
信号链提取模块 - 根据 Analog Devices 页面结构提取信号链内容与图片。
"""
import os
import re
import logging
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import csv

logger = logging.getLogger(__name__)


class SignalChainExtractor:
    def __init__(self, base_dir, base_url):
        self.base_dir = base_dir
        self.base_url = base_url
        self.data = {}

    def extract_signal_chains(self, soup: BeautifulSoup):
        """提取信号链模块 - 通用版本"""
        try:
            # 1. 查找信号链容器 - 多种可能的查找方式
            signal_chains_container = self._find_signal_chains_container(soup)
            if not signal_chains_container:
                logger.info("页面中未找到信号链模块")
                return None

            # 2. 创建存储目录
            signal_chain_dir = os.path.join(self.base_dir, 'signal_chains')
            os.makedirs(signal_chain_dir, exist_ok=True)

            # 3. 初始化数据结构
            signal_chains_data = {
                'module_title': '信号链',
                'total_count': 0,
                'active_chain_id': None,
                'chains': []
            }

            # 4. 提取模块标题和总数
            self._extract_module_title_and_count(signal_chains_container, signal_chains_data)

            # 5. 提取选项列表
            options_list = self._find_options_list(signal_chains_container)

            if options_list:
                # 6. 提取所有信号链的基本信息
                chains = self._extract_chain_basic_info(options_list)

                # 7. 查找所有信号链容器
                all_containers = self._find_all_signal_chain_containers(signal_chains_container)

                # 8. 为每个信号链查找图片和热点
                for chain in chains:
                    chain_id = chain.get('chain_id')
                    if chain_id:
                        # 查找对应的容器
                        chain_container = self._find_chain_container_by_id(all_containers, chain_id)

                        if chain_container:
                            # 提取图片信息
                            image_info = self._extract_image_info(chain_container, chain_id, signal_chain_dir)
                            chain['image_info'] = image_info
                            # 提取热点信息（仅用于内部处理，不会输出到JSON）
                            hotspots = self._extract_hotspots(chain_container, chain_id)
                            chain['_hotspots'] = hotspots  # 使用下划线前缀表示内部字段
                            # 检查是否为当前活跃的信号链
                            if 'display: block' in str(chain_container) or 'style=""' in str(chain_container):
                                signal_chains_data['active_chain_id'] = chain_id
                                chain['is_active'] = True

                        # 若页面上未找到该链的图片节点，仍按规则生成图片 URL（每条链都有对应图片）
                        if not chain.get('image_info') and chain_id:
                            chain['image_info'] = self._build_image_info_for_chain_id(chain_id, signal_chain_dir)
                        if '_hotspots' not in chain:
                            chain['_hotspots'] = []

                        # 尝试下载图片
                        self._download_chain_image(chain, signal_chain_dir)

                signal_chains_data['chains'] = chains

                # 9. 尝试提取表格数据（含已渲染表格与隐藏容器内表格）
                self._extract_tables_data(signal_chains_container, signal_chains_data)

                # 10. 从 scd-view-renderer > scd-partsSelected 提取「模块名 + 表格名称数组 + 表格内容」，一表一 CSV
                # 注意：这部分数据不会保存到最终的signal_chains_data中，只会导出CSV
                self._extract_module_tables_from_renderer(signal_chains_container, signal_chains_data)

                # 11. 提取隐藏/模板表格结构（script#scd-view），便于查找
       #         self._extract_template_table_schema(signal_chains_container, signal_chains_data)

            # 12. 清理不需要的字段，返回精简的结构
            cleaned_signal_chains_data = self._clean_signal_chains_data(signal_chains_data)

            # 13. 保存到主数据结构
            self.data['signal_chains'] = cleaned_signal_chains_data

            # 14. 导出为CSV文件（含按表格名称分文件导出、模板表格结构CSV）
            # 注意：这部分导出不会影响JSON结构
            self._export_signal_chains_to_csv(signal_chains_data)

            logger.info(f"信号链提取完成: 共找到 {len(cleaned_signal_chains_data.get('chains', []))} 个信号链")
            return cleaned_signal_chains_data

        except Exception as e:
            logger.error(f"提取信号链模块失败: {e}", exc_info=True)
            return None

    def _clean_signal_chains_data(self, signal_chains_data):
        """清理信号链数据，移除不需要的字段"""
        cleaned_data = {
            'module_title': signal_chains_data.get('module_title', '信号链'),
            'total_count': signal_chains_data.get('total_count', 0),
            'active_chain_id': signal_chains_data.get('active_chain_id'),
            'chains': []
        }

        # 清理每个chain，只保留需要的字段
        for chain in signal_chains_data.get('chains', []):
            cleaned_chain = {
                'list_name': chain.get('list_name', ''),
                'data_target': chain.get('data_target', ''),
                'chain_id': chain.get('chain_id', ''),
                'is_active': chain.get('is_active', False),
                'is_more_option': chain.get('is_more_option', False),
                'image_info': chain.get('image_info', {}),
                # signal_chain_hotspots 将由主爬虫添加，这里只保留空列表
                'signal_chain_hotspots': []
            }

            # 移除None值
            cleaned_chain = {k: v for k, v in cleaned_chain.items() if v is not None}
            cleaned_data['chains'].append(cleaned_chain)

        return cleaned_data

    # 其他方法保持不变，只是修改导出逻辑...

    def _export_signal_chains_to_csv(self, signal_chains_data):
        """导出信号链数据到CSV。所有 CSV 均在此目录：{base_dir}/exports"""
        try:
            csv_dir = os.path.join(self.base_dir, 'exports_signal_chain_csv')
            os.makedirs(csv_dir, exist_ok=True)
            csv_dir_abs = os.path.abspath(csv_dir)
            logger.info(f"信号链 CSV 导出目录: {csv_dir_abs}")

            # 注意：这里导出的是静态解析的表格，不是Selenium点击的表格
            # Selenium点击的表格由主爬虫导出

            # 3.3 模块表格（scd-view-renderer 触发）：保存模块名 + 表格名称数组，一表一 CSV
            module_tables = signal_chains_data.get('module_tables', [])
            if not module_tables:
                logger.debug(
                    "未发现 scd-view-renderer 内模块表格，跳过 module_*_table_*.csv 导出（需页面已触发热点后才有）")
                return

            for block in module_tables:
                module_name = block.get('module_name', '') or '未命名模块'
                table_names = block.get('table_names', [])
                tables = block.get('tables', [])
                # 与 complete_data.json 的 table_name 一致：{chain_id}_{COMPONENT_NAME}_table_{idx+1}_{safe_title}.csv
                chain_id = block.get('chain_id', '') or 'unknown'
                component_name = block.get('component_name', '') or module_name
                hotspot_unique_id = block.get('hotspot_unique_id', '')
                hotspot_safe = re.sub(r'[^\w\u4e00-\u9fff\-]','_',hotspot_unique_id)[:30].replace('-','_') if hotspot_unique_id else ''
                component_safe = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', component_name)[:60].replace('-', '_')

                for idx, table in enumerate(tables):
                    title = table.get('title', '').strip() or '未命名表格'
                    safe_title = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', title)[:60]
                    if hotspot_safe:
                        if not safe_title or safe_title == '_':
                            fname = f'{chain_id}_{component_safe}_{hotspot_safe}_table_{idx + 1}.csv'
                        else:
                            fname = f'{chain_id}_{component_safe}_{hotspot_safe}_table_{idx + 1}_{safe_title}.csv'
                    else:
                        if not safe_title or safe_title == '_':
                            fname = f'{chain_id}_{component_safe}_table_{idx + 1}.csv'
                        else:
                            fname = f'{chain_id}_{component_safe}_table_{idx + 1}_{safe_title}.csv'

                    per_file = os.path.join(csv_dir, fname)
                    headers = table.get('headers', [])

                    with open(per_file, 'w', newline='', encoding='utf-8-sig') as f:
                        writer = csv.writer(f)
                        writer.writerow(['组件名称', module_name])
                        writer.writerow(['模块名称', title])

                        # 添加产品链接列头
                        if headers:
                            writer.writerow(headers + ['产品链接'])

                        # 简洁版本：只提取文本，URL放在行末
                        for row in table.get('rows', []):
                            # 提取所有文本内容
                            row_texts = []
                            # 存储所有URL
                            row_urls = []

                            for cell in row:
                                if isinstance(cell, dict):
                                    # 提取文本
                                    text = cell.get('text', '') or cell.get('value', '')
                                    row_texts.append(text)

                                    # 提取URL
                                    url = cell.get('url', '') or cell.get('link', '')
                                    if url:
                                        row_urls.append(url)
                                else:
                                    row_texts.append(str(cell))

                            # 将URL添加到行末尾
                            row_data = row_texts + row_urls
                            writer.writerow(row_data)

                    logger.info(f"模块表格已导出: {per_file}")

        except Exception as e:
            logger.error(f"导出CSV文件失败: {e}")

    # 其他辅助方法保持不变...

    def _find_signal_chains_container(self, soup):
        """查找信号链容器 - 通用方法"""
        # 方法1: 通过ID查找
        container = soup.find('div', id='rd-signalchains')
        if container:
            return container

        # 方法2: 通过类名查找
        container = soup.find('div', class_='adi-scd-isc')
        if container:
            return container

        # 方法3: 通过脚本查找
        script = soup.find('script', src=re.compile(r'adi\.isc'))
        if script:
            parent = script.find_parent('div')
            if parent:
                return parent

        # 方法4: 通过文本内容查找
        signal_chains_text = soup.find(text=re.compile(r'信号链'))
        if signal_chains_text:
            # 向上查找包含完整结构的父元素
            for parent in signal_chains_text.parents:
                if parent.name == 'div' and parent.find('ul', class_=re.compile(r'options-list')):
                    return parent

        # 方法5: 查找 legacy-component-content
        container = soup.find('div', class_='legacy-component-content')
        if container:
            return container

        return None

    def _extract_module_title_and_count(self, container, data_dict):
        """提取模块标题和总数"""
        try:
            # 查找标题区域
            section_heading = container.find('div', class_='section-heading')
            if not section_heading:
                # 尝试其他可能的类名
                section_heading = container.find('div', class_=re.compile(r'heading'))

            if section_heading:
                # 查找所有h3标签
                h3_tags = section_heading.find_all('h3')
                for h3 in h3_tags:
                    text = h3.get_text(strip=True)
                    if '信号链' in text:
                        data_dict['module_title'] = text
                        # 提取括号中的数字
                        match = re.search(r'\((\d+)\)', text)
                        if match:
                            data_dict['total_count'] = int(match.group(1))
                    elif '(' in text and ')' in text:
                        # 单独的数字标签
                        match = re.search(r'\((\d+)\)', text)
                        if match:
                            data_dict['total_count'] = int(match.group(1))

            # 如果没找到，尝试从整个容器文本中提取
            if data_dict['total_count'] == 0:
                all_text = container.get_text()
                match = re.search(r'信号链\s*\((\d+)\)', all_text)
                if match:
                    data_dict['total_count'] = int(match.group(1))

        except Exception as e:
            logger.error(f"提取模块标题和总数失败: {e}")

    def _find_options_list(self, container):
        """查找选项列表"""
        # 尝试多种可能的类名
        selectors = [
            'ul.options-list',
            'ul.list-unstyled',
            'ul.tabAccordion',
            'ul[class*="options"]'
        ]

        for selector in selectors:
            try:
                if '.' in selector:
                    # 按类名查找
                    class_part = selector.split('.')[1]
                    if ' ' in class_part:
                        class_part = class_part.split(' ')[0]
                    ul = container.find('ul', class_=class_part)

                else:
                    # 通用查找
                    ul = container.select_one(selector)
                if ul:
                    return ul
            except Exception as e:
                logger.debug(f"使用选择器{selector}失败:{e}")
                continue

        # 查找包含ISC-的ul
        uls = container.find_all('ul')
        for ul in uls:
            if ul.find('a', attrs={'data-target': re.compile(r'ISC-')}):
                return ul

        return None

    def _extract_chain_basic_info(self, options_list):
        """从选项列表提取信号链基本信息；名称优先取自子元素 <h3>（与样例一致）"""
        chains = []

        for li in options_list.find_all('li'):
            a_tag = li.find('a')
            if not a_tag:
                continue

            # 名称：样例中在 <a><h3>航空航天与防务、雷达</h3></a>，优先取 h3 文本
            h3 = a_tag.find('h3')
            list_name = h3.get_text(strip=True) if h3 else a_tag.get_text(strip=True)
            data_target = a_tag.get('data-target', '')

            # 从data_target提取chain_id
            chain_id = None
            if data_target.startswith('ISC-'):
                chain_id = data_target.replace('ISC-', '')

            # 检查是否活跃
            is_active = 'active' in li.get('class', [])

            # 检查是否是"更多"选项
            is_more = 'more-options' in li.get('class', [])

            chain_info = {
                'list_name': list_name,
                'data_target': data_target,
                'chain_id': chain_id,
                'is_active': is_active,
                'is_more_option': is_more
            }

            chains.append(chain_info)

        return chains

    def _find_all_signal_chain_containers(self, container):
        """查找所有信号链容器"""
        containers = []

        # 方法1: 通过类名查找
        chain_containers = container.find_all('div', class_='signal-chain-container')
        containers.extend(chain_containers)

        # 方法2: 通过ID模式查找
        pattern = re.compile(r'waveformGenerator_isc-\d+')
        divs = container.find_all('div', id=pattern)
        for div in divs:
            if div not in containers:
                containers.append(div)

        return containers

    def _find_chain_container_by_id(self, containers, chain_id):
        """根据 chain_id 查找对应容器（id 形如 waveformGenerator_isc-0001），严格匹配 isc-{chain_id}"""
        want = f'isc-{chain_id}'
        for container in containers:
            cid = container.get('id', '') or ''
            if want in cid or cid.endswith(want):
                return container
        for container in containers:
            cid = container.get('id', '') or ''
            if re.search(re.escape(f'isc-{chain_id}'), cid, re.IGNORECASE):
                return container
        return None

    def _extract_image_info(self, chain_container, chain_id, save_dir):
        """提取图片信息"""
        try:
            # 查找图片元素
            img = chain_container.find('img', class_='mapster_el')
            if not img:
                # 查找任何img标签
                img = chain_container.find('img')

            if not img:
                return None

            # 获取图片URL
            img_src = img.get('src') or img.get('data-src', '')
            if not img_src:
                return None

            # 构建完整URL
            if img_src.startswith('//'):
                img_url = 'https:' + img_src
            elif img_src.startswith('/'):
                img_url = urljoin(self.base_url, img_src)
            elif not img_src.startswith(('http://', 'https://')):
                img_url = urljoin(self.base_url, img_src)
            else:
                img_url = img_src

            # 生成文件名和本地路径（不输出 img_src，仅保留 img_url）
            img_filename = f"signal_chain_{chain_id}.png"
            local_path = os.path.join(save_dir, img_filename)

            image_info = {
                'img_url': img_url,
                'filename': img_filename,
                'local_path': local_path,
                'chain_id': chain_id
            }

            return image_info

        except Exception as e:
            logger.error(f"提取图片信息失败 (chain_id={chain_id}): {e}")
            return None

    def _build_image_info_for_chain_id(self, chain_id, save_dir):
        """按站点规则为 chain_id 生成图片信息（每条链都有对应 isc-{chain_id}.png）"""
        img_url = urljoin(self.base_url, f'/packages/isc/v2824/zh/isc-{chain_id}.png')
        img_filename = f"signal_chain_{chain_id}.png"
        local_path = os.path.join(save_dir, img_filename)
        return {
            'img_url': img_url,
            'filename': img_filename,
            'local_path': local_path,
            'chain_id': chain_id
        }

    def _extract_hotspots(self, chain_container, chain_id):
        """提取热点信息（内部使用，不会输出到JSON）"""
        hotspots = []

        try:
            # 方法1: 在容器内查找map
            map_element = chain_container.find('map')

            # 方法2: 如果容器内没有，查找name属性匹配的map
            if not map_element:
                map_name = f'isc-{chain_id}'
                map_element = chain_container.find_next('map', attrs={'name': map_name})

            # 方法3: 查找任何包含chain_id的map
            if not map_element:
                all_maps = chain_container.find_all_next('map')
                for map_elem in all_maps:
                    if map_elem.get('name', '').endswith(chain_id):
                        map_element = map_elem
                        break

            if map_element:
                # 提取所有area标签
                for area in map_element.find_all('area'):
                    hotspot_info = {
                        'alt': area.get('alt', ''),
                        'shape': area.get('shape', ''),
                        'coords': area.get('coords', ''),
                        'data_key': area.get('data-mapster-key', ''),
                        'href': area.get('href', ''),
                        'component_name': self._extract_component_name_from_alt(area.get('alt', ''))
                    }
                    hotspots.append(hotspot_info)

        except Exception as e:
            logger.error(f"提取热点信息失败 (chain_id={chain_id}): {e}")

        return hotspots

    def _extract_component_name_from_alt(self, alt_text):
        """从alt属性中提取部件名称"""
        try:
            # alt格式类似: "adc_241f6396-2aab-fd70-1434-4d981b723440"
            # 提取下划线前的部分作为部件类型
            if '_' in alt_text:
                parts=alt_text.split('_')
                if parts:
                    component_type = parts[0]
                    return component_type.upper()
            return alt_text.upper() if alt_text else ''
        except Exception as e:
            logger.debug(f"提取名称失败：{e}")
            return alt_text.upper() if alt_text else ''



    def _download_chain_image(self, chain_info, save_dir):
        """下载信号链图片"""
        try:
            if not chain_info.get('image_info'):
                return

            img_url = chain_info['image_info'].get('img_url')
            local_path = chain_info['image_info'].get('local_path')

            if img_url and local_path and not os.path.exists(local_path):
                import requests
                response = requests.get(img_url, timeout=10)
                if response.status_code == 200:
                    with open(local_path, 'wb') as f:
                        f.write(response.content)
                    logger.info(f"已下载图片: {local_path}")
                else:
                    logger.warning(f"无法下载图片: {img_url} (HTTP {response.status_code})")

        except Exception as e:
            logger.error(f"下载图片失败: {e}")

    def _extract_tables_data(self, container, signal_chains_data):
        """提取表格数据（含 scd-view-renderer、scd-partsSelected 及任意隐藏样式内的 scd-partTable）"""
        try:
            tables_data = []
            seen_titles = set()

            for table_elem in container.find_all('div', class_='scd-partTable'):
                table_info = self._extract_table_info(table_elem)
                if not table_info:
                    continue
                title = table_info.get('title', '').strip() or '未命名表格'
                if title in seen_titles:
                    continue
                seen_titles.add(title)
                tables_data.append(table_info)

            if tables_data:
                signal_chains_data['tables'] = tables_data
                logger.info(f"提取到 {len(tables_data)} 个表格（含隐藏样式）")

        except Exception as e:
            logger.error(f"提取表格数据失败: {e}")

    def _extract_module_tables_from_renderer(self, container, signal_chains_data):
        """在 legacy-component-container 内找 #scd-view-renderer，再从其下 scd-partsSelected 提取模块名、表格名称数组、表格内容；一模块可多表。"""
        try:
            # 在 legacy-component-container 内查找 #scd-view-renderer
            leg = container.find_parent('div', class_='legacy-component-container')
            search_root = leg if leg else container
            renderer = search_root.find('div', id='scd-view-renderer')
            if not renderer:
                return
            # 支持多个 scd-partsSelected（不同模块）
            parts_list = renderer.find_all('div', class_='scd-partsSelected')
            if not parts_list:
                return

            module_tables_list = []
            for parts_el in parts_list:
                # 模块名称：scd-partTitle，去掉末尾 X、+ 等
                part_title_el = parts_el.find('div', class_='scd-partTitle')
                module_name = ''
                if part_title_el:
                    module_name = part_title_el.get_text(strip=True)
                    module_name = re.sub(r'\s*X\s*$', '', module_name)
                    module_name = re.sub(r'\s*\+\s*$', '', module_name)
                    module_name = module_name.strip()

                table_names = []
                tables = []
                for table_elem in parts_el.find_all('div', class_='scd-partTable'):
                    table_info = self._extract_table_info(table_elem)
                    if not table_info:
                        continue
                    title = (table_info.get('title') or '').strip() or '未命名表格'
                    table_names.append(title)
                    tables.append(table_info)

                if module_name or tables:
                    module_tables_list.append({
                        'module_name': module_name or '未命名模块',
                        'table_names': table_names,
                        'tables': tables
                    })

            if module_tables_list:
                signal_chains_data['module_tables'] = module_tables_list
                total_tables = sum(len(m['tables']) for m in module_tables_list)
                logger.info(f"从 scd-view-renderer 提取到 {len(module_tables_list)} 个模块、共 {total_tables} 个表格")
        except Exception as e:
            logger.error(f"提取 scd-view-renderer 模块表格失败: {e}")


    def _extract_table_info(self, table_elem):
        """提取单个表格信息"""
        try:
            table_info = {
                'title': '',
                'headers': [],
                'rows': []
            }

            # 提取表格标题
            title_elem = table_elem.find('div', class_='scd-tablename')
            if title_elem:
                table_info['title'] = title_elem.get_text(strip=True)

            # 提取表头
            table = table_elem.find('table')
            if table:
                # 提取表头行
                header_row = table.find('tr')
                if header_row:
                    headers = []
                    for th in header_row.find_all('th'):
                        header_text = th.get_text(strip=True)
                        # 清理换行和多余空格
                        header_text = ' '.join(header_text.split())
                        headers.append(header_text)
                    table_info['headers'] = headers

                # 提取数据行（含无 scd-part-row 的 tr，兼容不同样式）
                rows = []
                for tr in table.find_all('tr')[1:]:  # 跳过表头行
                    if tr.find('th'):
                        continue
                    row_data = []
                    for td in tr.find_all('td'):
                        link = td.find('a')
                        if link:
                            cell_data = {'text': link.get_text(strip=True), 'url': link.get('href', '')}
                        else:
                            cell_data = {'text': td.get_text(strip=True), 'url': None}
                        row_data.append(cell_data)
                    if row_data:
                        rows.append(row_data)

                table_info['rows'] = rows

            return table_info if table_info['headers'] or table_info['rows'] else None

        except Exception as e:
            logger.error(f"提取表格信息失败: {e}")
            return None