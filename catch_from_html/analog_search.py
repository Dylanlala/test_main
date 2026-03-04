import requests
import os
import json
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
from typing import Dict, List, Optional, Set
import logging
import mimetypes
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import pandas as pd

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class EnhancedAnalogDevicesScraper:
    def __init__(self, base_url: str, base_dir: Optional[str] = None):
        """
        初始化增强型爬虫

        Args:
            base_url: 目标网页URL
            base_dir: 可选，数据保存根目录；不传则使用 'analog_devices_data'
        """
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        
        # 使用Selenium来获取动态内容
        self.driver = self.setup_selenium_driver()
        
        # 存储数据结构
        self.data = {
            'page_info': {
                'url': base_url,
                'title': '',
                'description': '',
                'crawl_time': time.strftime('%Y-%m-%d %H:%M:%S'),
                'navigation_path': ''  # 新增：专门存储导航路径
            },
            'sections': [],
            'product_tables': [],
            'table_images': [],  # 专门存储表格下方的图片
            'all_images': [],
            'resources': []
        }

        # 创建存储目录（支持外部指定，便于全站爬虫按分类/场景分目录）
        self.base_dir = base_dir if base_dir is not None else 'analog_devices_data'
        self.images_dir = os.path.join(self.base_dir, 'images')
        self.table_images_dir = os.path.join(self.base_dir, 'table_images')
        self.resources_dir = os.path.join(self.base_dir, 'resources')
        os.makedirs(self.images_dir, exist_ok=True)
        os.makedirs(self.table_images_dir, exist_ok=True)
        os.makedirs(self.resources_dir, exist_ok=True)

    def setup_selenium_driver(self):
        """设置Selenium WebDriver来获取动态内容"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # 无头模式
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        
        # 模拟真实浏览器
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        driver = webdriver.Chrome(options=chrome_options)
        return driver

    def fetch_page_with_selenium(self) -> Optional[str]:
        """使用Selenium获取完整页面内容"""
        try:
            logger.info(f"使用Selenium获取页面: {self.base_url}")
            self.driver.get(self.base_url)
            
            # 等待页面加载完成
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 等待可能存在的动态内容
            time.sleep(2)
            
            # 获取完整的页面HTML
            full_html = self.driver.page_source
            
            # 特别提取导航路径
            self.extract_navigation_path()
            
            return full_html
            
        except Exception as e:
            logger.error(f"Selenium获取页面失败: {e}")
            return None

    def extract_navigation_path(self):
        """提取导航路径：主页/解决方案概要/精密技术解决方案/高速精密解决方案"""
        try:
            # 查找导航元素 - 可能的选择器
            navigation_selectors = [
                '.breadcrumb',
                '.breadcrumbs',
                '.navigation-path',
                '.page-nav',
                '.path',
                'nav[aria-label="breadcrumb"]',
                'nav ol',
                '.site-map',
                '[class*="breadcrumb"]',
                '[class*="nav"]'
            ]
            
            navigation_text = ""
            
            for selector in navigation_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        nav_element = elements[0]
                        navigation_text = nav_element.text.strip()
                        
                        # 清理导航文本
                        navigation_text = re.sub(r'\s+>\s+', '/', navigation_text)
                        navigation_text = re.sub(r'\n+', '/', navigation_text)
                        
                        logger.info(f"找到导航路径: {navigation_text}")
                        break
                except:
                    continue
            
            # 如果找不到，尝试通过XPath查找
            if not navigation_text:
                try:
                    # 查找包含"主页"或"首页"的导航元素
                    xpaths = [
                        '//*[contains(text(), "主页") or contains(text(), "首页")]/..',
                        '//*[contains(@class, "nav")]//*[contains(text(), "主页")]',
                        '//*[@id="breadcrumb"]',
                        '//nav',
                    ]
                    
                    for xpath in xpaths:
                        try:
                            elements = self.driver.find_elements(By.XPATH, xpath)
                            if elements:
                                navigation_text = elements[0].text.strip()
                                break
                        except:
                            continue
                except:
                    pass
            
            # 如果没有找到导航，使用默认路径
            if not navigation_text:
                navigation_text = "主页/解决方案概要/精密技术解决方案/高速精密解决方案"
                logger.info(f"使用默认导航路径: {navigation_text}")
            
            self.data['page_info']['navigation_path'] = navigation_text
            
        except Exception as e:
            logger.error(f"提取导航路径失败: {e}")
            self.data['page_info']['navigation_path'] = "主页/解决方案概要/精密技术解决方案/高速精密解决方案"

    def extract_page_info(self, soup: BeautifulSoup):
        """提取页面基本信息"""
        # 标题
        title_tag = soup.find('h1') or soup.find('title')
        if title_tag:
            self.data['page_info']['title'] = title_tag.get_text(strip=True)
            logger.info(f"页面标题: {self.data['page_info']['title']}")

        # 描述
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            self.data['page_info']['description'] = meta_desc.get('content', '')
        else:
            # 提取第一段作为描述
            first_p = soup.find('p')
            if first_p:
                self.data['page_info']['description'] = first_p.get_text(strip=True)[:200]

    def extract_all_content(self, html_content: str):
        """提取页面所有内容"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 1. 提取页面基本信息
        self.extract_page_info(soup)
        
        # 2. 提取导航路径（如果Selenium没提取到，尝试从HTML提取）
        if not self.data['page_info']['navigation_path']:
            self.extract_navigation_from_html(soup)
        
        # 3. 提取所有章节内容（直到"开发人员工具和资源"之前）
        self.extract_all_sections_until_resources(soup)
        
        # 4. 提取产品表格（重点）
        self.extract_product_tables_with_context(soup)
        
        # 5. 提取表格下方的图片（重点）
        self.extract_table_images(soup)
        
        # 6. 提取开发工具和资源
        self.extract_developer_resources(soup)
        
        # 7. 提取所有图片
        self.extract_and_download_all_images(soup)

    def extract_navigation_from_html(self, soup: BeautifulSoup):
        """从HTML中提取导航路径"""
        try:
            # 查找常见的导航元素
            nav_elements = soup.find_all(['nav', 'div', 'ol', 'ul'], 
                                         class_=re.compile(r'breadcrumb|navigation|nav|path', re.IGNORECASE))
            
            for nav in nav_elements:
                nav_text = nav.get_text(strip=True)
                if any(keyword in nav_text for keyword in ['主页', '首页', 'Home', '解决方案', '精密技术']):
                    # 清理文本
                    nav_text = re.sub(r'\s+>\s+', '/', nav_text)
                    nav_text = re.sub(r'\n+', '/', nav_text)
                    nav_text = re.sub(r'\s+', ' ', nav_text)
                    
                    if len(nav_text) > 10 and len(nav_text) < 200:
                        self.data['page_info']['navigation_path'] = nav_text
                        logger.info(f"从HTML提取导航路径: {nav_text}")
                        return
            
            # 如果没有找到，使用默认值
            self.data['page_info']['navigation_path'] = "主页/解决方案概要/精密技术解决方案/高速精密解决方案"
            
        except Exception as e:
            logger.error(f"从HTML提取导航失败: {e}")

    def extract_all_sections_until_resources(self, soup: BeautifulSoup):
        """提取直到'开发人员工具和资源'之前的所有章节（完整正文）"""
        try:
            # 获取页面主要内容区域
            main_content = soup.find('main') or soup.find(id='main-content') or soup.body
            if not main_content:
                main_content = soup

            # 查找停止点：用 get_text() 匹配，支持标题内嵌套标签
            stop_keywords = ['开发人员工具和资源', '开发工具', '资源', 'Developer Tools', 'Resources']
            stop_element = None
            for tag in main_content.find_all(['h2', 'h3', 'h4', 'h5']):
                title_text = tag.get_text(strip=True)
                for keyword in stop_keywords:
                    if keyword in title_text or (keyword.lower() in title_text.lower()):
                        stop_element = tag
                        logger.info(f"找到停止点: {keyword} -> {title_text}")
                        break
                if stop_element:
                    break

            if stop_element:
                # 按文档顺序收集“停止点之前”的所有块级元素
                doc_order = list(main_content.find_all(True))
                try:
                    stop_idx = doc_order.index(stop_element)
                except ValueError:
                    stop_idx = len(doc_order)
                block_tags = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'div']
                all_elements = [e for e in main_content.find_all(block_tags)
                                if e in doc_order and doc_order.index(e) < stop_idx]
                self.organize_sections_from_elements(all_elements)
            else:
                logger.warning("未找到'开发人员工具和资源'标题，提取全部内容")
                all_headings = main_content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                self.organize_sections_from_headings(all_headings)

        except Exception as e:
            logger.error(f"提取章节内容失败: {e}")

    def _get_text_from_element(self, elem) -> List[str]:
        """从单个元素递归提取所有段落/列表文本（用于 div 等容器），避免重复"""
        if not elem or not hasattr(elem, 'name') or not elem.name:
            return []
        out = []
        if elem.name == 'p':
            t = elem.get_text(strip=True)
            if t:
                out.append(t)
            return out
        if elem.name in ['ul', 'ol']:
            for li in elem.find_all('li', recursive=False) or elem.find_all('li'):
                t = li.get_text(strip=True)
                if t:
                    out.append(f"• {t}")
            return out
        if elem.name == 'div':
            # 先收直接子元素中的 p / ul / ol，再收 div 内无子块时的整段文本
            for child in elem.children:
                if not hasattr(child, 'name') or not child.name:
                    continue
                if child.name in ['p', 'ul', 'ol']:
                    out.extend(self._get_text_from_element(child))
                elif child.name == 'div':
                    out.extend(self._get_text_from_element(child))
            # 若 div 内没有 p/ul/ol 但有文字，整段取出
            if not out and elem.get_text(strip=True):
                out.append(elem.get_text(separator='\n', strip=True))
            return out
        return out

    def organize_sections_from_elements(self, elements: List):
        """从元素列表组织章节，完整提取正文（含 div 内所有段落与列表）"""
        current_section = None
        # 已由某个 div 覆盖的节点，其内部 p/ul/ol 不再单独计入，避免重复
        covered = set()

        for elem in elements:
            if elem in covered:
                continue
            if elem.name and elem.name.startswith('h'):
                current_section = {
                    'level': elem.name,
                    'title': elem.get_text(strip=True),
                    'content': [],
                    'images': []
                }
                self.data['sections'].append(current_section)
            elif current_section:
                if elem.name == 'p':
                    text = elem.get_text(strip=True)
                    if text:
                        current_section['content'].append(text)
                elif elem.name in ['ul', 'ol']:
                    for item in elem.find_all('li'):
                        text = item.get_text(strip=True)
                        if text:
                            current_section['content'].append(f"• {text}")
                elif elem.name == 'div':
                    parts = self._get_text_from_element(elem)
                    current_section['content'].extend(parts)
                    for d in elem.descendants:
                        if getattr(d, 'name', None):
                            covered.add(d)

    def organize_sections_from_headings(self, headings: List):
        """从标题列表组织章节，收集到下一个标题为止的所有内容（含 div 内全文）"""
        main_content = headings[0].parent if headings else None
        while main_content and main_content.name not in ['main', 'body', 'div']:
            main_content = getattr(main_content, 'parent', None)
        if not main_content:
            main_content = headings[0].parent

        for i, heading in enumerate(headings):
            section = {
                'level': heading.name,
                'title': heading.get_text(strip=True),
                'content': [],
                'images': []
            }
            # 下一个同级标题为止的所有兄弟（含跨层 div 内的 p/ul/ol）
            next_heading = headings[i + 1] if i + 1 < len(headings) else None
            curr = heading.find_next_sibling()
            while curr and curr != next_heading:
                if getattr(curr, 'name', None) and curr.name.startswith('h'):
                    break
                if curr.name == 'p':
                    t = curr.get_text(strip=True)
                    if t:
                        section['content'].append(t)
                elif curr.name in ['ul', 'ol']:
                    for li in curr.find_all('li'):
                        t = li.get_text(strip=True)
                        if t:
                            section['content'].append(f"• {t}")
                elif curr.name == 'div':
                    section['content'].extend(self._get_text_from_element(curr))
                curr = curr.find_next_sibling()
            self.data['sections'].append(section)

    def get_table_title(self, table) -> str:
        """获取表格标题"""
        # 查找前面的标题元素
        for tag_name in ['h3', 'h4', 'h5', 'strong', 'b']:
            prev = table.find_previous(tag_name)
            if prev:
                text = prev.get_text(strip=True)
                if text and len(text) < 100:
                    return text

        # 查找父元素中的标题
        parent = table.parent
        for i in range(3):  # 向上查找3层
            if parent:
                heading = parent.find(['h2', 'h3', 'h4', 'h5'])
                if heading:
                    return heading.get_text(strip=True)
                parent = parent.parent

        return "未命名表格"

    def extract_product_tables_with_context(self, soup: BeautifulSoup):
        """提取产品表格及其上下文信息"""
        # 查找所有表格
        tables = soup.find_all('table')

        if not tables:
            logger.warning("未找到表格，尝试其他方式提取产品信息")
            self.extract_products_from_text(soup)
            return

        for i, table in enumerate(tables):
            table_data = {
                'id': f"table_{i + 1:03d}",
                'title': '',
                'category': '',
                'context': '',
                'headers': [],
                'rows': [],
                'products': [],
                'related_images': []
            }

            # 1. 获取表格标题和上下文
            table_data['title'] = self.get_table_title(table)
            table_data['category'] = self.determine_table_category(table)
            table_data['context'] = self.get_table_context(table)

            # 2. 提取表头
            headers = table.find_all('th')
            if headers:
                table_data['headers'] = [h.get_text(strip=True) for h in headers]

            # 3. 提取表格行和产品信息
            rows = table.find_all('tr')
            for row_idx, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                if cells:
                    row_data = []
                    for cell_idx, cell in enumerate(cells):
                        cell_text = cell.get_text('\n', strip=True)
                        row_data.append(cell_text)

                        # 提取产品信息
                        products_in_cell = self.extract_products_from_cell(cell, table_data['category'])
                        table_data['products'].extend(products_in_cell)

                    table_data['rows'].append(row_data)

            # 4. 查找与表格相关的图片
            table_data['related_images'] = self.find_images_near_table(table)

            self.data['product_tables'].append(table_data)
            logger.info(f"提取表格 {i + 1}: {table_data['title']} - {len(table_data['products'])} 个产品")

    def determine_table_category(self, table) -> str:
        """确定表格类别"""
        title = self.get_table_title(table).lower()

        categories = {
            '密度优化': ['密度', 'density'],
            '功耗优化型': ['功耗', '功率', 'power'],
            '噪声和带宽优化': ['噪声', '带宽', 'noise', 'bandwidth'],
            '针对灵活性优化': ['灵活', 'flexibility'],
            '针对噪声进行优化': ['噪声优化', 'noise optimization'],
            '电流或电压测量': ['电流', '电压', 'current', 'voltage'],
            '光测量': ['光测量', 'optical']
        }

        for category, keywords in categories.items():
            if any(keyword in title for keyword in keywords):
                return category

        # 从表格内容判断
        table_text = table.get_text().lower()
        if any(word in table_text for word in ['adg5421f', '保护']):
            return '保护器件表格'
        elif any(word in table_text for word in ['ltc6373', '增益']):
            return '增益器件表格'

        return '其他产品表格'

    def get_table_context(self, table) -> str:
        """获取表格上下文描述"""
        context = []

        # 查找表格前面的段落
        prev_elem = table.previous_sibling
        for _ in range(5):  # 查找前5个兄弟元素
            if not prev_elem:
                break

            if hasattr(prev_elem, 'name') and prev_elem.name == 'p':
                text = prev_elem.get_text(strip=True)
                if text and len(text) > 20 and len(text) < 500:
                    context.append(text)

            prev_elem = prev_elem.previous_sibling if hasattr(prev_elem, 'previous_sibling') else None

        return " | ".join(context) if context else ""

    def extract_products_from_cell(self, cell, category: str) -> List[Dict]:
        """从表格单元格提取产品信息"""
        products = []

        # 获取单元格内所有文本行
        lines = [line.strip() for line in cell.get_text('\n').split('\n') if line.strip()]

        for line in lines:
            # 检查是否包含产品型号
            if self.is_product_model(line):
                product = {
                    'model': self.extract_model(line),
                    'description': line,
                    'category': category,
                    'cell_content': cell.get_text('\n', strip=True)
                }
                products.append(product)

        return products

    def is_product_model(self, text: str) -> bool:
        """判断文本是否包含产品型号"""
        # ADI产品型号模式
        patterns = [
            r'^AD[AGNQRVXZ][A-Z0-9]{3,}',  # ADxxxx
            r'^LTC[0-9]{4,}',  # LTCxxxx
            r'^ADAQ?[0-9]{5,}',  # ADAxxxx
            r'^AD[0-9]{4,}',  # AD数字
            r'^LT[0-9]{4,}',  # LT数字
        ]

        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False

    def extract_model(self, text: str) -> str:
        """从文本中提取产品型号"""
        # 查找型号模式
        patterns = [
            r'([A-Z]{2,}[0-9A-Z\-]+)',  # 通用模式
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)

        return text.split()[0] if text.split() else text

    def find_images_near_table(self, table) -> List[Dict]:
        """查找表格附近的图片"""
        related_images = []

        # 1. 查找表格内的图片
        img_tags = table.find_all('img')
        for img in img_tags:
            img_info = self.extract_image_info(img, 'table_internal')
            if img_info:
                related_images.append(img_info)

        # 2. 查找表格前后的图片（附近区域）
        # 查找表格后5个兄弟元素中的图片
        next_elem = table.next_sibling
        for _ in range(5):
            if not next_elem:
                break

            if hasattr(next_elem, 'find_all'):
                imgs = next_elem.find_all('img')
                for img in imgs:
                    img_info = self.extract_image_info(img, 'table_adjacent')
                    if img_info and img_info not in related_images:
                        related_images.append(img_info)

            next_elem = next_elem.next_sibling if hasattr(next_elem, 'next_sibling') else None

        return related_images

    def extract_table_images(self, soup: BeautifulSoup):
        """专门提取表格下方的图片"""
        logger.info("开始提取表格下方的图片...")
        
        # 查找所有表格
        tables = soup.find_all('table')
        
        for i, table in enumerate(tables):
            table_title = self.get_table_title(table)
            logger.info(f"处理表格 {i+1}: {table_title}")
            
            # 查找表格下方（后面）的图片
            next_elem = table.next_sibling
            
            # 最多查看后面10个元素
            for _ in range(10):
                if not next_elem:
                    break
                
                if hasattr(next_elem, 'name'):
                    # 查找图片
                    img_tags = next_elem.find_all('img') if next_elem.name else []
                    
                    for img in img_tags:
                        img_info = self.extract_image_info(img, f"table_{i+1}")
                        if img_info:
                            # 标记与表格的关联
                            img_info['table_index'] = i + 1
                            img_info['table_title'] = table_title
                            img_info['position'] = 'below_table'
                            
                            # 下载图片
                            downloaded_path = self.download_table_image(img_info['src'], img_info['filename'])
                            if downloaded_path:
                                img_info['local_path'] = downloaded_path
                                self.data['table_images'].append(img_info)
                                logger.info(f"  找到表格下方图片: {img_info['filename']}")
                
                next_elem = next_elem.next_sibling if hasattr(next_elem, 'next_sibling') else None

    def download_table_image(self, img_url: str, filename: str) -> Optional[str]:
        """下载表格相关的图片"""
        try:
            # 使用requests下载
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': self.base_url
            }
            
            response = requests.get(img_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # 确定文件扩展名
            content_type = response.headers.get('content-type', '')
            ext = mimetypes.guess_extension(content_type) or '.jpg'
            
            # 确保文件名有正确扩展名
            if not filename.lower().endswith(ext.lower()):
                base_name = os.path.splitext(filename)[0]
                filename = f"{base_name}{ext}"
            
            # 确保文件名唯一
            counter = 1
            original_filename = filename
            while os.path.exists(os.path.join(self.table_images_dir, filename)):
                name_part, ext_part = os.path.splitext(original_filename)
                filename = f"{name_part}_{counter}{ext_part}"
                counter += 1
            
            # 保存文件
            filepath = os.path.join(self.table_images_dir, filename)
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            return filepath
            
        except Exception as e:
            logger.error(f"下载表格图片失败 {img_url}: {e}")
            return None

    def extract_and_download_all_images(self, soup: BeautifulSoup):
        """提取并下载所有图片"""
        img_tags = soup.find_all('img')
        logger.info(f"找到 {len(img_tags)} 个图片标签")
        
        for i, img in enumerate(img_tags):
            try:
                img_info = self.extract_image_info(img, 'page_image')
                if img_info:
                    # 检查是否已经在表格图片中
                    is_table_image = any(t_img['src'] == img_info['src'] for t_img in self.data['table_images'])
                    
                    if not is_table_image:
                        # 下载图片
                        downloaded_path = self.download_image(img_info['src'], img_info['filename'])
                        if downloaded_path:
                            img_info['local_path'] = downloaded_path
                            self.data['all_images'].append(img_info)
                            
            except Exception as e:
                logger.error(f"处理图片失败: {e}")

    def download_image(self, img_url: str, filename: str) -> Optional[str]:
        """下载普通图片"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': self.base_url
            }
            
            response = requests.get(img_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # 确定文件扩展名
            content_type = response.headers.get('content-type', '')
            ext = mimetypes.guess_extension(content_type) or '.jpg'
            
            if not filename.lower().endswith(ext.lower()):
                base_name = os.path.splitext(filename)[0]
                filename = f"{base_name}{ext}"
            
            # 确保文件名唯一
            counter = 1
            original_filename = filename
            while os.path.exists(os.path.join(self.images_dir, filename)):
                name_part, ext_part = os.path.splitext(original_filename)
                filename = f"{name_part}_{counter}{ext_part}"
                counter += 1
            
            # 保存文件
            filepath = os.path.join(self.images_dir, filename)
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            return filepath
            
        except Exception as e:
            logger.error(f"下载图片失败 {img_url}: {e}")
            return None

    def extract_image_info(self, img_tag, source_type: str) -> Optional[Dict]:
        """提取图片信息"""
        src = img_tag.get('src') or img_tag.get('data-src')
        if not src:
            return None
        
        # 补全图片URL
        full_url = urljoin(self.base_url, src)
        
        # 获取图片信息
        alt = img_tag.get('alt', '')
        title = img_tag.get('title', '')
        
        # 生成文件名
        parsed_url = urlparse(full_url)
        filename = os.path.basename(parsed_url.path)
        
        if not filename or '.' not in filename:
            # 使用alt或标题作为文件名
            name_source = alt or title or 'image'
            safe_name = re.sub(r'[^\w\-_]', '_', name_source)[:50]
            filename = f"{safe_name}_{int(time.time())}.jpg"
        
        return {
            'src': full_url,
            'alt': alt,
            'title': title,
            'filename': filename,
            'source_type': source_type,
            'url': full_url
        }

    def extract_developer_resources(self, soup: BeautifulSoup):
        """提取开发人员工具和资源"""
        # 查找资源相关章节
        resource_headings = soup.find_all(['h2', 'h3', 'h4'], string=re.compile(r'工具|资源|支持|开发', re.IGNORECASE))

        for heading in resource_headings:
            resource_section = {
                'title': heading.get_text(strip=True),
                'resources': []
            }

            # 查找该标题下的资源列表
            next_elem = heading.next_sibling
            while next_elem:
                if hasattr(next_elem, 'name'):
                    if next_elem.name == 'ul':
                        items = next_elem.find_all('li')
                        for item in items:
                            text = item.get_text(strip=True)
                            links = item.find_all('a')
                            for link in links:
                                href = link.get('href')
                                if href:
                                    resource_section['resources'].append({
                                        'text': text,
                                        'url': urljoin(self.base_url, href),
                                        'link_text': link.get_text(strip=True)
                                    })

                    # 遇到下一个标题时停止
                    elif next_elem.name and next_elem.name.startswith('h'):
                        break

                next_elem = next_elem.next_sibling if hasattr(next_elem, 'next_sibling') else None

            if resource_section['resources']:
                self.data['resources'].append(resource_section)

    def extract_products_from_text(self, soup: BeautifulSoup):
        """从文本中提取产品信息（备用方法）"""
        # 查找所有可能包含产品信息的文本
        all_text = soup.get_text()

        # 匹配产品型号模式
        patterns = [
            r'(AD[AGNQRVXZ][A-Z0-9\-]+)',  # AD系列
            r'(LTC[0-9A-Z\-]+)',  # LTC系列
            r'(ADAQ?[0-9A-Z\-]+)',  # ADAQ系列
        ]

        found_products = set()

        for pattern in patterns:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            found_products.update(matches)

        if found_products:
            table_data = {
                'id': 'text_extracted',
                'title': '从文本提取的产品',
                'category': '文本提取',
                'headers': ['产品型号'],
                'rows': [[product] for product in sorted(found_products)],
                'products': [{'model': p, 'description': ''} for p in sorted(found_products)]
            }
            self.data['product_tables'].append(table_data)

    def save_data(self):
        """保存所有数据"""
        # 1. 保存JSON数据
        json_file = os.path.join(self.base_dir, 'complete_data.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        logger.info(f"数据已保存到: {json_file}")
        
        # 2. 保存导航路径
        nav_file = os.path.join(self.base_dir, 'navigation.txt')
        with open(nav_file, 'w', encoding='utf-8') as f:
            f.write(self.data['page_info'].get('navigation_path', ''))

        # 2.5 保存完整正文（到「资源」之前的所有文字）
        full_text_parts = [
            self.data['page_info'].get('title', ''),
            self.data['page_info'].get('navigation_path', ''),
            ''
        ]
        for sec in self.data.get('sections', []):
            full_text_parts.append(sec.get('title', ''))
            for line in sec.get('content', []):
                full_text_parts.append(line)
            full_text_parts.append('')
        full_body_file = os.path.join(self.base_dir, 'full_body_text.txt')
        with open(full_body_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(full_text_parts))
        logger.info(f"完整正文已保存到: {full_body_file}")
        
        # 3. 保存表格图片清单
        if self.data['table_images']:
            table_images_data = []
            for img in self.data['table_images']:
                table_images_data.append({
                    'table_index': img.get('table_index'),
                    'table_title': img.get('table_title'),
                    'image_filename': img.get('filename'),
                    'image_url': img.get('src'),
                    'local_path': img.get('local_path'),
                    'alt_text': img.get('alt', '')
                })
            
            df_table_images = pd.DataFrame(table_images_data)
            table_images_csv = os.path.join(self.base_dir, 'table_images_list.csv')
            df_table_images.to_csv(table_images_csv, index=False, encoding='utf-8-sig')
            logger.info(f"表格图片清单已保存到: {table_images_csv}")
        
        # 4. 生成README文件
        self.generate_readme()

    def generate_readme(self):
        """生成README文件说明"""
        readme_content = f"""# Analog Devices 数据爬取结果

## 基本信息
- 源URL: {self.data['page_info']['url']}
- 爬取时间: {self.data['page_info']['crawl_time']}
- 页面标题: {self.data['page_info'].get('title', 'N/A')}
- 导航路径: {self.data['page_info'].get('navigation_path', 'N/A')}

## 数据内容
1. 章节数量: {len(self.data['sections'])}
2. 产品表格数量: {len(self.data['product_tables'])}
3. 表格下方图片数量: {len(self.data['table_images'])}
4. 所有图片数量: {len(self.data['all_images'])}
5. 资源章节数量: {len(self.data['resources'])}

## 表格图片关联信息
{chr(10).join(f"- 表格 '{img.get('table_title', '未知')}': {img.get('filename', '未知')} (URL: {img.get('src', '未知')})" 
              for img in self.data['table_images'][:10])}
{chr(10) + f"... 还有 {len(self.data['table_images']) - 10} 张表格图片" if len(self.data['table_images']) > 10 else ""}

## 文件结构
- `complete_data.json`: 完整数据（JSON格式）
- `navigation.txt`: 导航路径文本
- `table_images_list.csv`: 表格图片关联清单
- `table_images/`: 表格下方的图片文件
- `images/`: 其他图片文件
- `README.md`: 本说明文件

## 使用说明
1. 表格图片已按关联表格分类，可通过table_images_list.csv查看关联关系
2. 导航路径已单独保存到navigation.txt
3. 所有文字内容（直到"开发人员工具和资源"之前）已提取到sections中
"""

        readme_file = os.path.join(self.base_dir, 'README.md')
        with open(readme_file, 'w', encoding='utf-8') as f:
            f.write(readme_content)

    def run(self):
        """运行爬虫"""
        logger.info("开始爬取Analog Devices页面...")
        
        # 1. 使用Selenium获取页面
        html_content = self.fetch_page_with_selenium()
        if not html_content:
            logger.error("无法获取页面内容")
            return False
        
        # 2. 提取所有内容
        self.extract_all_content(html_content)
        
        # 3. 关闭Selenium驱动
        self.driver.quit()
        
        # 4. 保存数据
        self.save_data()
        
        # 5. 显示摘要
        self.display_summary()
        
        return True

    def display_summary(self):
        """显示爬取结果摘要"""
        print("\n" + "=" * 70)
        print("ANALOG DEVICES 数据爬取完成")
        print("=" * 70)
        
        print(f"\n📄 页面信息:")
        print(f"   标题: {self.data['page_info'].get('title', 'N/A')}")
        print(f"   导航路径: {self.data['page_info'].get('navigation_path', 'N/A')}")
        
        print(f"\n📊 数据统计:")
        print(f"   章节数量: {len(self.data['sections'])}")
        print(f"   产品表格: {len(self.data['product_tables'])}")
        print(f"   表格下方图片: {len(self.data['table_images'])}")
        print(f"   所有图片: {len(self.data['all_images'])}")
        
        print(f"\n📋 表格图片关联:")
        if self.data['table_images']:
            for img in self.data['table_images'][:5]:
                table_title = img.get('table_title', '未知表格')
                filename = img.get('filename', '未知')
                url = img.get('src', '未知')
                print(f"   📍 表格: {table_title[:30]}...")
                print(f"     图片: {filename}")
                print(f"     URL: {url[:50]}...")
        else:
            print("   未找到表格下方图片")
        
        print(f"\n💾 保存的文件:")
        print(f"   完整数据: {self.base_dir}/complete_data.json")
        print(f"   导航路径: {self.base_dir}/navigation.txt")
        print(f"   表格图片清单: {self.base_dir}/table_images_list.csv")
        print(f"   表格图片目录: {self.base_dir}/table_images/")
        
        print("\n" + "=" * 70)


# 使用示例
if __name__ == "__main__":
    # 目标URL
    url = "https://www.analog.com/cn/solutions/precision-technology/fast-precision.html"
    
    # 创建爬虫实例
    scraper = EnhancedAnalogDevicesScraper(url)
    
    # 运行爬虫
    success = scraper.run()
    
    if success:
        print("\n✅ 爬取完成！所有数据已保存到 'analog_devices_data' 目录")
        print("   特别注意:")
        print("   1. 表格下方的图片已单独保存在 'table_images' 目录")
        print("   2. 图片与表格的关联关系记录在 'table_images_list.csv'")
        print("   3. 导航路径已保存到 'navigation.txt'")
    else:
        print("\n❌ 爬取失败，请检查网络连接或URL")