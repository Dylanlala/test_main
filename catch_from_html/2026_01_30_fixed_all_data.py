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
import hashlib


from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import pandas as pd

from signal_chain_extract import SignalChainExtractor

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

        #保存layout_type，我已经发现规律了 layout_type=1,没有表格；layout_type=2,有表格
        self.layout_type=''

        self.hotspots_by_chain={}


        # 存储数据结构
        self.data = {
            'page_info': {
                'url': base_url,
                'title': '',
                'keywords':'',
                'description': '',
                'component_overview':'',
              #  'crawl_time': time.strftime('%Y-%m-%d %H:%M:%S'),
                'navigation_path': ''  # 新增：专门存储导航路径

            },
            'value_and_benefits':{
                'title':'',
                'contents':'',
                'characteristics':[]
            },
            # 'sections': [],
            # 'product_tables': [],
            # 'table_images': [],  # 专门存储表格下方的图片
            # 'all_images': [],
            # 'resources': [],
            # 'layout2_modules': []  # layout_type=layout2 时：各 spotlight 模块名、描述、表格、图片
        }

        # 创建存储目录（支持外部指定，便于全站爬虫按分类/场景分目录）
        self.base_dir = base_dir if base_dir is not None else 'analog_devices_data_new'
        # self.images_dir = os.path.join(self.base_dir, 'images')
        # self.table_images_dir = os.path.join(self.base_dir, 'table_images')
        # self.resources_dir = os.path.join(self.base_dir, 'resources')
        # os.makedirs(self.images_dir, exist_ok=True)
        # os.makedirs(self.table_images_dir, exist_ok=True)
        # os.makedirs(self.resources_dir, exist_ok=True)




    def setup_selenium_driver(self):
        """设置Selenium WebDriver来获取动态内容。优先使用项目内 chromedriver.exe，避免 SeleniumManager 子进程卡住或过慢。"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # 无头模式
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')


        # 添加反反爬设置
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        # 模拟真实浏览器
        # 随机User-Agent
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        import random
        chrome_options.add_argument(f'--user-agent={random.choice(user_agents)}')

        # 添加语言和编码设置
        chrome_options.add_argument('--accept-language=zh-CN,zh;q=0.9,en;q=0.8')
        chrome_options.add_argument(
            '--accept=text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8')

        # 优先使用项目目录下的 chromedriver.exe，避免 SeleniumManager 子进程卡住（网络/首次下载导致 KeyboardInterrupt）
        base_dir = os.path.dirname(os.path.abspath(__file__))
        local_driver = os.path.join(base_dir, 'chromedriver.exe')
        if os.path.isfile(local_driver):
            try:
                from selenium.webdriver.chrome.service import Service
                driver = webdriver.Chrome(service=Service(executable_path=local_driver), options=chrome_options)
                return driver
            except Exception as e:
                logger.warning(f"使用本地 chromedriver.exe 失败: {e}，回退到默认方式")
        driver = webdriver.Chrome(options=chrome_options)
        return driver


    def _dismiss_onetrust_banner(self):
        """关闭 OneTrust Cookie/隐私横幅（遮罩会拦截信号链 tab 点击）。先尝试点接受按钮，否则用 JS 隐藏遮罩。"""
        try:
            time.sleep(1)
            # 1) 尝试点击常见 OneTrust「接受」按钮
            for sel in [
                '#onetrust-accept-btn-handler',
                '.onetrust-close-btn-handler',
                'button[id*="onetrust-accept"]',
                '[id*="OneTrust"] button',
                'button[class*="accept"]',
            ]:
                try:
                    btns = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for b in btns:
                        if b.is_displayed():
                            self.driver.execute_script('arguments[0].click();', b)
                            logger.info("已点击 OneTrust 接受按钮关闭横幅")
                            time.sleep(1.5)
                            return
                except Exception:
                    continue
            # 2) 用 JS 隐藏遮罩与横幅容器，避免拦截点击
            self.driver.execute_script("""
                var sel = '.onetrust-pc-dark-filter, #onetrust-consent-sdk, [id^="onetrust"], .ot-pc-dark-filter';
                document.querySelectorAll(sel).forEach(function(el) { el.style.setProperty('display', 'none'); });
            """)
            logger.info("已用 JS 隐藏 OneTrust 遮罩")
            time.sleep(0.8)
        except Exception as e:
            logger.debug(f"关闭 OneTrust 横幅时出错: {e}")

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
            time.sleep(5)

            # 关闭 OneTrust Cookie/隐私横幅，避免遮罩拦截信号链 tab 点击
            self._dismiss_onetrust_banner()

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
            #
            # # 如果没有找到导航，使用默认路径
            # if not navigation_text:
            #     navigation_text = "主页/解决方案概要/精密技术解决方案/高速精密解决方案"
            #     logger.info(f"使用默认导航路径: {navigation_text}")

            self.data['page_info']['navigation_path'] = navigation_text

        except Exception as e:
            logger.error(f"提取导航路径失败: {e}")
            # self.data['page_info']['navigation_path'] = "主页/解决方案概要/精密技术解决方案/高速精密解决方案"

    def _collect_module_tables_from_dom(self) -> List[Dict]:
        """从当前 DOM 的 scd-partsSelected 提取模块名和表格（Selenium 用），优先 #scd-view-renderer 内"""
        out = []
        try:
            # 在 legacy-component-container 内找 #scd-view-renderer（点击热点后表格在此渲染）
            try:
                renderer = self.driver.find_element(By.CSS_SELECTOR, '.legacy-component-container #scd-view-renderer')
                parts = renderer.find_elements(By.CSS_SELECTOR, '.scd-partsSelected')
            except Exception:
                parts = []
            if not parts:
                parts = self.driver.find_elements(By.CSS_SELECTOR, '.scd-partsSelected')
            for el in parts:
                module_name = ''
                try:
                    title_el = el.find_element(By.CSS_SELECTOR, '.scd-partTitle')
                    module_name = title_el.text.strip()
                    module_name = re.sub(r'\s*X\s*$', '', module_name)
                    module_name = re.sub(r'\s*\+\s*$', '', module_name)
                    module_name = module_name.strip()
                except Exception:
                    pass
                table_names = []
                tables = []
                for table_el in el.find_elements(By.CSS_SELECTOR, '.scd-partTable'):
                    try:
                        title = ''
                        try:
                            tn = table_el.find_element(By.CSS_SELECTOR, '.scd-tablename')
                            title = tn.text.strip()
                        except Exception:
                            pass
                        table_names.append(title or '未命名表格')
                        headers = []
                        rows = []
                        tbl = table_el.find_element(By.CSS_SELECTOR, 'table')
                        trs = tbl.find_elements(By.TAG_NAME, 'tr')
                        if trs:
                            for th in trs[0].find_elements(By.TAG_NAME, 'th'):
                                headers.append(th.text.strip().replace('\n', ' '))
                        for tr in trs[1:]:
                            if 'scd-part-row' not in (tr.get_attribute('class') or ''):
                                continue
                            row = []
                            for td in tr.find_elements(By.TAG_NAME, 'td'):
                                a = td.find_elements(By.TAG_NAME, 'a')
                                row.append({'text': (a[0].text.strip() if a else td.text.strip()), 'url': (a[0].get_attribute('href') or None) if a else None})
                            if row:
                                rows.append(row)
                        tables.append({'title': title or '未命名表格', 'headers': headers, 'rows': rows})
                    except Exception as e:
                        logger.debug(f"单表提取失败: {e}")
                if module_name or tables:
                    out.append({'module_name': module_name or '未命名模块', 'table_names': table_names, 'tables': tables})
        except Exception as e:
            logger.debug(f"从 DOM 提取模块表格失败: {e}")
        return out

    def _dispatch_click_on_canvas_at_map_coords(self, container_el, img_el, cx_map: int, cy_map: int) -> bool:
        """在 canvas 上按「地图坐标」派发原生鼠标事件，模拟真实点击。返回是否执行成功。"""
        try:
            return self.driver.execute_script("""
                var cont = arguments[0], img = arguments[1], cx = arguments[2], cy = arguments[3];
                var wrap = cont.querySelector ? cont.querySelector('[id^="mapster_wrap"]') : null;
                if (!wrap) return false;
                var canvas = wrap.querySelector('canvas');
                if (!canvas) return false;
                var rect = canvas.getBoundingClientRect();
                var nw = img.naturalWidth || img.width || rect.width, nh = img.naturalHeight || img.height || rect.height;
                if (!nw || !nh) return false;
                var scaleX = rect.width / nw, scaleY = rect.height / nh;
                var x = rect.left + cx * scaleX, y = rect.top + cy * scaleY;
                var opts = { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y };
                canvas.dispatchEvent(new MouseEvent('mousedown', opts));
                canvas.dispatchEvent(new MouseEvent('mouseup', opts));
                canvas.dispatchEvent(new MouseEvent('click', opts));
                return true;
            """, container_el, img_el, cx_map, cy_map)
        except Exception:
            return False

    def _area_coords_center(self, area_el) -> Optional[tuple]:
        """从 <area> 的 shape/coords 解析出点击中心 (x, y)。"""
        try:
            shape = (area_el.get_attribute('shape') or 'rect').lower()
            coords = area_el.get_attribute('coords') or ''
            parts = re.split(r'[\s,]+', coords.strip())
            nums = []
            for p in parts:
                if not p:
                    continue
                try:
                    nums.append(int(p))
                except ValueError:
                    pass
            if not nums:
                return None
            if shape == 'rect' and len(nums) >= 4:
                x1, y1, x2, y2 = nums[0], nums[1], nums[2], nums[3]
                return ((x1 + x2) // 2, (y1 + y2) // 2)
            if shape == 'circle' and len(nums) >= 3:
                return (nums[0], nums[1])
            if shape == 'poly' and len(nums) >= 6:
                xs = nums[0::2]
                ys = nums[1::2]
                return (sum(xs) // len(xs), sum(ys) // len(ys))
            return (nums[0], nums[1]) if len(nums) >= 2 else None
        except Exception:
            return None

    def _generate_hotspot_unique_id(self,area_element,alt_text,index):
        try:
            if '_' in alt_text:
                parts = alt_text.split('_')
                if len(parts)>=2:
                    uuid_part=parts[1]
                    if len(uuid_part)>=8:
                        return uuid_part[:12]
            coords = area_element.get_attribute('coords') or ''
            if coords:
                coords_hash = hashlib.md5(coords.encode()).hexdigest()[:8]
                return f"coord_{coords_hash}"

            return f"hotspot_{index+1}"
        except Exception:
            return f"hotspot_{index+1}"




    def trigger_signal_chain_hotspots_and_collect_tables(self) -> List[Dict]:
        """用 Selenium 依次点击信号链热点，收集每个模块的表格"""
        collected = []
        try:
            # 触发热点前再次关闭 OneTrust 遮罩
            self._dismiss_onetrust_banner()

            # 清空热点存储
            self.hotspots_by_chain = {}

            # 查找信号链区域
            root = None
            for sel in ['#rd-signalchains', '.adi-scd-isc']:
                try:
                    els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    if els:
                        root = els[0]
                        break
                except Exception:
                    continue

            if not root:
                logger.info("页面未找到信号链区域，跳过热点触发")
                return collected

            # 查找所有信号链tab
            tab_links = root.find_elements(By.CSS_SELECTOR, 'ul.options-list li a[data-target^="ISC-"]')
            if not tab_links:
                tab_links = self.driver.find_elements(By.CSS_SELECTOR, 'ul.options-list li a[data-target^="ISC-"]')

            if not tab_links:
                logger.info("未找到信号链选项，跳过热点触发")
                return collected

            logger.info(f"开始触发热点收集表格：共 {len(tab_links)} 个信号链 tab")

            for tab_index, tab_link in enumerate(tab_links):
                try:
                    data_target = tab_link.get_attribute('data-target') or ''
                    if not data_target.startswith('ISC-'):
                        continue

                    chain_id = data_target.replace('ISC-', '')

                    # 初始化该chain_id的热点列表
                    self.hotspots_by_chain[chain_id] = []

                    try:
                        self.driver.execute_script('arguments[0].scrollIntoView({block:"center"});', tab_link)
                        time.sleep(0.5)
                    except Exception:
                        pass

                    tab_link.click()
                    time.sleep(2)

                    # 等待当前链的容器出现
                    try:
                        WebDriverWait(self.driver, 5).until(
                            EC.visibility_of_element_located((By.CSS_SELECTOR, f'#waveformGenerator_isc-{chain_id}'))
                        )
                    except Exception:
                        pass

                    time.sleep(0.5)

                    # 查找图片容器
                    try:
                        cont = self.driver.find_element(By.CSS_SELECTOR, f'#waveformGenerator_isc-{chain_id}')
                    except Exception:
                        logger.debug(f"未找到容器: #waveformGenerator_isc-{chain_id}")
                        continue

                    # 查找图片
                    img = None
                    try:
                        imgs = cont.find_elements(By.CSS_SELECTOR, 'img.mapster_el[src*="isc-"]')
                        if imgs:
                            img = imgs[0]
                    except Exception:
                        pass

                    if not img:
                        try:
                            img = cont.find_element(By.CSS_SELECTOR, 'img.mapster_el')
                        except Exception:
                            pass

                    if not img:
                        logger.debug(f"tab {chain_id} 未找到可见图片，跳过")
                        continue

                    try:
                        self.driver.execute_script('arguments[0].scrollIntoView({block:"center"});', img)
                        time.sleep(0.3)
                    except Exception:
                        pass

                    # 查找对应的map元素
                    try:
                        map_el = self.driver.find_element(By.CSS_SELECTOR, f'map[name="isc-{chain_id}"]')
                    except Exception:
                        logger.debug(f"tab {chain_id} 无 map，跳过")
                        continue

                    areas = map_el.find_elements(By.TAG_NAME, 'area')
                    if not areas:
                        logger.debug(f"tab {chain_id} 无热点 area，跳过")
                        continue

                    logger.info(f"tab {chain_id} 共 {len(areas)} 个热点，开始依次点击")

                    for area_index, area in enumerate(areas):
                        try:
                            alt = (area.get_attribute('alt') or '')[:40]
                            component_name = self._extract_component_name_from_alt(alt)

                            hotspot_unique_id=self._generate_hotspot_unique_id(area,alt,area_index)

                            # 获取坐标中心点
                            center = self._area_coords_center(area)

                            # 使用JS点击area
                            self.driver.execute_script('arguments[0].click();', area)
                            logger.info(f"已点击热点 [{area_index + 1}/{len(areas)}] {alt} (JS点击)")
                            time.sleep(2.0)

                            # 等待表格出现
                            try:
                                WebDriverWait(self.driver, 6).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR,
                                                                    '.scd-partsSelected .scd-partTable, .scd-partsSelected .scd-partTitle'))
                                )
                            except Exception:
                                pass

                            # 如果未出现表格且能计算中心点，尝试其他点击方式
                            block_after_js = self._collect_module_tables_from_dom()
                            if (not block_after_js or not any(b.get('tables') for b in block_after_js)) and center:
                                # 尝试在canvas上派发原生点击
                                if self._dispatch_click_on_canvas_at_map_coords(cont, img, center[0], center[1]):
                                    logger.info(f"已点击热点 [{area_index + 1}/{len(areas)}] {alt} (canvas 原生事件)")
                                    time.sleep(2.0)

                            # 收集表格信息
                            time.sleep(1.5)
                            try:
                                WebDriverWait(self.driver, 8).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR,
                                                                    '.scd-partsSelected .scd-partTable, .scd-partsSelected .scd-partTitle'))
                                )
                            except Exception:
                                pass

                            time.sleep(1.0)

                            # 确保scd-view-renderer可见
                            try:
                                self.driver.execute_script(
                                    "var r=document.querySelector('.legacy-component-container #scd-view-renderer'); if(r){ r.style.setProperty('display','block'); }"
                                )
                                time.sleep(0.8)
                            except Exception:
                                pass

                            # 收集模块表格
                            block = self._collect_module_tables_from_dom()

                            for b in block:
                                if b.get('tables'):
                                    # 写入 chain_id / component_name，供导出 CSV 时与 complete_data.json 命名一致
                                    b['chain_id'] = chain_id
                                    b['component_name'] = component_name
                                    b['hotspot_unique_id'] = hotspot_unique_id
                                    component_safe = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', component_name)[:60].replace('-', '_')
                                    hotspot_safe = re.sub(r'[^\w\u4e00-\u9fff\-]','_',hotspot_unique_id)[:30].replace('-', '_')
                                    module_name = b.get('module_name', '')
                                    for idx, table in enumerate(b.get('tables', [])):
                                        table_title = table.get('title', '未命名表格')
                                        safe_title = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', table_title)[:60]
                                        # 与 complete_data.json 一致：{chain_id}_{COMPONENT_NAME}_table_{idx+1}_{safe_title}.csv
                                        if not safe_title or safe_title == '_':
                                            table_filename = f"{chain_id}_{component_safe}_{hotspot_safe}_table_{idx + 1}.csv"
                                        else:
                                            table_filename = f"{chain_id}_{component_safe}_{hotspot_safe}_table_{idx + 1}_{safe_title}.csv"
                                        table_path = os.path.join('exports_signal_chain_csv', table_filename)
                                        hotspot_info = {
                                            'chain_id': chain_id,
                                            'component_name': component_name,
                                            'module_name': table_title,
                                            'table_name': table_filename,
                                            'table_path': table_path
                                        }
                                        self.hotspots_by_chain.setdefault(chain_id, []).append(hotspot_info)
                                        logger.info(f"保存热点信息: {component_name} -> {table_filename}")
                                    collected.append(b)
                                    logger.info(f"已收集模块: {b.get('module_name', '')}，表格数: {len(b.get('tables', []))}")

                        except Exception as e:
                            logger.warning(f"点击 area {area_index} ({alt}) 失败: {e}")
                            continue

                except Exception as e:
                    logger.warning(f"处理 tab {tab_index} 失败: {e}")
                    continue

            logger.info(f"热点触发结束，共收集 {len(collected)} 个模块表格块")
            return collected

        except Exception as e:
            logger.error(f"触发热点收集表格失败: {e}", exc_info=True)
            return collected





    def extract_page_info(self, soup: BeautifulSoup):
        """提取页面基本信息"""
        # 标题
        title_tag = soup.find('h1') or soup.find('title')
        if title_tag:
            self.data['page_info']['title'] = title_tag.get_text(strip=True)
            logger.info(f"页面标题: {self.data['page_info']['title']}")

        # 关键词
        keyword = soup.find('meta', attrs={'name': 'keywords'})
        if keyword:
            self.data['page_info']['keywords'] = keyword.get('content', '')
        else:
            all_text1 = ''
            self.data['page_info']['keywords'] = all_text1 if all_text1 else ''
        logger.info(f"关键词：{self.data['page_info']['keywords']}")

        # 描述
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            self.data['page_info']['description'] = meta_desc.get('content', '')
        else:
            all_text=''
            self.data['page_info']['description'] = all_text if all_text else ''

        logger.info(f"页面描述：{self.data['page_info']['description']}")

        component_overview = soup.find('div',class_='adi-rte')
        if component_overview:
            overview_text =component_overview.get_text(strip=True,separator=' ')
        else:
            first_p=soup.find('p')
            if first_p:
                overview_text = first_p.get_text(strip=True)

        self.data['page_info']['component_overview'] = overview_text
        logger.info(f"概述：{self.data['page_info']['component_overview']}")




    def extract_all_content(self, html_content: str, collected_module_tables: Optional[List[Dict]] = None):
        """提取页面所有内容。collected_module_tables 为 Selenium 触发热点后收集的模块表格，会合并到 signal_chains 并导出 CSV。"""
        soup = BeautifulSoup(html_content, 'html.parser')

        # 1. 提取页面基本信息
        self.extract_page_info(soup)

        # 提取价值和优势部分
        self._get_all_from_benefits(soup)

        # 2. 提取导航路径（如果Selenium没提取到，尝试从HTML提取）
        if not self.data['page_info']['navigation_path']:
            self.extract_navigation_from_html(soup)

        # 提取所有面板的型号、描述、图片
        self.extract_hardware_and_evaluation_products(soup)

        # 提取信号链（使用当前页 base_dir/base_url，结果写入同一目录并合并到 self.data）
        signal_chain_extractor = SignalChainExtractor(base_dir=self.base_dir, base_url=self.base_url)
        result = signal_chain_extractor.extract_signal_chains(soup)

        if result is not None:
            # 清理不需要的字段（保留 result 用于后续合并与导出）
            if 'module_tables' in result:
                del result['module_tables']
            if 'tables' in result:
                del result['tables']
            if 'template_table_schema' in result:
                del result['template_table_schema']

            # 合并 Selenium 触发热点收集的模块表格并导出 module_*_table_*.csv
            if collected_module_tables:
                self._export_signal_chains_with_chain_id(collected_module_tables)
                # 将收集的表格并入 result，再调用统一导出，否则 _export_signal_chains_to_csv 收不到 module_tables 会打「未发现」并跳过
                result_for_export = {**result, 'module_tables': collected_module_tables}
                signal_chain_extractor._export_signal_chains_to_csv(result_for_export)
                logger.info(f"已合并 {len(collected_module_tables)} 个模块表格并导出 module_*_table_*.csv")

            # 合并热点信息到每个信号链
            if hasattr(self, 'hotspots_by_chain') and self.hotspots_by_chain:
                for chain in result.get('chains', []):
                    chain_id = chain.get('chain_id')
                    if not chain_id:
                        # 尝试从data_target提取chain_id
                        data_target = chain.get('data_target', '')
                        if data_target.startswith('ISC-'):
                            chain_id = data_target.replace('ISC-', '')

                    if chain_id and chain_id in self.hotspots_by_chain:
                        # 添加热点信息到该链，并确保每个热点都有 chain_id
                        hotspots_with_chain_id = []
                        for hotspot in self.hotspots_by_chain[chain_id]:
                            hotspot['chain_id'] = chain_id
                            hotspots_with_chain_id.append(hotspot)
                        chain['signal_chain_hotspots'] = hotspots_with_chain_id
                        logger.info(f"为信号链 {chain_id} 添加了 {len(hotspots_with_chain_id)} 个热点信息")
                    else:
                        # 如果没有热点信息，添加空列表
                        chain['signal_chain_hotspots'] = []

                    # 清理不需要的 hotspots 字段（HTML解析的静态热点）
                    if 'hotspots' in chain:
                        del chain['hotspots']

            # 保存到主数据结构
            self.data['signal_chains'] = result
            logger.info(f"信号链已合并到 self.data，共 {len(result.get('chains', []))} 条链")
        else:
            logger.info("当前页面未检测到信号链模块")

        print("信号链提取结果:", "成功" if result else "未找到信号链模块")



    def _export_signal_chains_with_chain_id(self, collected_module_tables: List[Dict]):
        """导出带有 chain_id 的 CSV 文件"""
        try:
            csv_dir = os.path.join(self.base_dir, 'exports_signal_chain_csv')
            os.makedirs(csv_dir, exist_ok=True)

            for module_table in collected_module_tables:
                # 这里需要从 module_table 中提取 chain_id
                # 由于 collected_module_tables 是从 Selenium 点击获得的，我们需要跟踪哪个 chain_id
                # 实际实现中，需要确保在 trigger_signal_chain_hotspots_and_collect_tables 中
                # 为每个表格块记录 chain_id
                pass

        except Exception as e:
            logger.error(f"导出带有 chain_id 的 CSV 失败: {e}")



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




    """mlhuang:2026_01_29新增写法，价值这栏格式很固定，直接从div里面提取要的元素，格式还整齐"""

    def _get_all_from_benefits(self, soup: BeautifulSoup):
        """提取价值和优势"""
        try:
            result = {
                'title': '',
                'contents': '',
                'characteristics': [],
              #  'layout_type': 'none'
            }

            # 尝试布局1
            container = soup.find('div', class_='value-prop-component__content-wrapper')
            if container:
                self.layout_type= 'layout1'
                # 标题
                h3 = container.find('h3', class_='content-title')
                if h3:
                    result['title'] = h3.get_text(strip=True)
                # 内容
                p = container.find('p', class_='value-para')
                if p:
                    result['contents'] = p.get_text(strip=True)
                # 特性
                for item in container.find_all('p', class_='benefits-para'):
                    text = item.get_text(strip=True)
                    if text:
                        result['characteristics'].append(text)

            # 尝试布局2
            elif soup.find('section', class_='spotlight'):
                self.layout_type = 'layout2'
                spotlight = soup.find('section', class_='spotlight')
                # 标题（保留原逻辑：第一个 spotlight 用于 value_and_benefits）
                h2 = spotlight.find('h2', class_='spotlight__heading')
                h3 = spotlight.find('h3', class_=lambda c: c and 'spotlight__heading' in (c or ''))
                if h2:
                    result['title'] = h2.get_text(strip=True)
                elif h3:
                    result['title'] = h3.get_text(strip=True)
                # 内容
                content_div = spotlight.find('div', class_='spotlight__introduction__content')
                if content_div:
                    texts = []
                    for p in content_div.find_all('p'):
                        text = p.get_text(strip=True)
                        if text:
                            texts.append(text)
                    if texts:
                        result['contents'] = ' '.join(texts)
                if not result['contents']:
                    for column in spotlight.find_all('div', class_='spotlight__container__column__content'):
                        p = column.find('p')
                        if p:
                            result['contents'] = p.get_text(strip=True)
                            break
                # 特性
                for column in spotlight.find_all('div', class_='spotlight__container__column__content'):
                    text = column.get_text(strip=True)
                    if text:
                        clean_text = text.replace('Thumbs Up', '').strip()
                        if clean_text:
                            result['characteristics'].append(clean_text)
                # layout2 时额外提取所有 spotlight 模块（模块名、描述、表格、图片）
                self.data['layout2_modules'] = self._extract_layout2_modules(soup)

            # 保存结果
            for key in ['title', 'contents', 'characteristics']:
                self.data['value_and_benefits'][key] = result[key]

            #记录一下当前的版面类型


            # 日志

            if result['characteristics']:
                logger.info(f"找到{len(result['characteristics'])}个特性")

            return result

        except Exception as e:
            logger.error(f"提取失败：{e}")
            return None

    def _extract_layout2_modules(self, soup: BeautifulSoup) -> list:
        """当 layout_type 为 layout2 时，提取所有 section.spotlight 的模块名、描述、表格、图片。其他代码不动。"""
        from urllib.parse import urljoin
        modules = []
        try:
            spotlights = soup.find_all('section', class_='spotlight')
            base_url = self.data.get('page_info', {}).get('url', '') or self.base_url or 'https://www.analog.com'
            if not base_url.startswith('http'):
                base_url = urljoin('https://www.analog.com', base_url)
            layout2_img_dir = os.path.join(self.base_dir, 'layout2_images')
            os.makedirs(layout2_img_dir, exist_ok=True)

            for idx, section in enumerate(spotlights):
                mod = {'module_name': '', 'description': '', 'table': {'headers': [], 'rows': []}, 'images': []}
                # 模块名：h3 或 h2.spotlight__heading
                heading = section.find('h3', class_=lambda c: c and 'spotlight__heading' in (c or '')) or section.find('h2', class_=lambda c: c and 'spotlight__heading' in (c or ''))
                if heading:
                    mod['module_name'] = heading.get_text(strip=True)
                # 描述：第一个 spotlight__container__column__content 下的 p
                content_div = section.find('div', class_='spotlight__container__column__content')
                if content_div:
                    p_el = content_div.find('p')
                    if p_el:
                        mod['description'] = p_el.get_text(strip=True)
                    # 若该 div 内有 table，则表格属于本模块
                    tbl = content_div.find('table')
                    if tbl:
                        header_row = tbl.find('tr', class_='analog-table-headers') or tbl.find('tr')
                        if header_row:
                            for cell in header_row.find_all(['td', 'th']):
                                mod['table']['headers'].append(cell.get_text(strip=True))
                        for tr in tbl.find_all('tr', class_='analog-table-data') or tbl.find_all('tr')[1:]:
                            if tr.get('class') and 'analog-table-headers' in tr.get('class', []):
                                continue
                            row_cells = []
                            for td in tr.find_all(['td', 'th']):
                                cell_text = td.get_text(separator=' ', strip=True)
                                links = []
                                for a in td.find_all('a', href=True):
                                    links.append({'text': a.get_text(strip=True), 'url': urljoin(base_url, a['href'])})
                                row_cells.append({'text': cell_text, 'links': links})
                            if row_cells:
                                mod['table']['rows'].append(row_cells)
                # 本 section 内图片
                for img in section.find_all('img', src=True):
                    src = img.get('src', '')
                    if not src:
                        continue
                    full_url = urljoin(base_url, src)
                    img_info = {'url': full_url, 'alt': (img.get('alt') or '').strip()}
                    try:
                        fname = os.path.basename(src.split('?')[0]) or f'module_{idx}_{len(mod["images"])}.jpg'
                        safe = re.sub(r'[^\w.\-]', '_', fname)[:80]
                        local_path = os.path.join(layout2_img_dir, safe)
                        if not os.path.isfile(local_path):
                            r = requests.get(full_url, timeout=10)
                            if r.ok:
                                with open(local_path, 'wb') as f:
                                    f.write(r.content)
                        img_info['local_path'] = local_path
                    except Exception:
                        img_info['local_path'] = ''
                    mod['images'].append(img_info)
                modules.append(mod)
                logger.info(f"layout2 模块[{idx+1}]: {mod['module_name'] or '(无标题)'}, 表头{len(mod['table']['headers'])}, 行{len(mod['table']['rows'])}, 图{len(mod['images'])}")
        except Exception as e:
            logger.error(f"layout2 多模块提取失败: {e}", exc_info=True)
        return modules

    """2026_01_29:mlhuang
    几个页面的风格不完全统一，只能分为两个块做处理，确保有表格的数据和对应的图片都能扒下来；没表格的对应的型号和描述还有图片也能扒下来
    """

    def _extract_products_by_component(self, soup: BeautifulSoup, products_list: list, save_dir: str,
                                       component_class: str, title_keywords: list, product_type_name: str):
        """
        通用产品提取函数 - 根据组件类名和标题关键词提取产品

        :param soup: BeautifulSoup对象
        :param products_list: 存储提取结果的列表
        :param save_dir: 图片保存目录
        :param component_class: 要查找的组件类名（如'SolutionProductCard'）
        :param title_keywords: 标题关键词列表
        :param product_type_name: 产品类型名称（用于日志）
        """
        try:
            # 1. 查找所有指定类型的组件
            components = soup.find_all('div', class_=lambda c: c and f'component {component_class}' in c)

            if not components:
                logger.warning(f"未找到{component_class}组件")
                return

            logger.info(f"找到 {len(components)} 个{component_class}组件")

            total_extracted = 0

            for component in components:
                # 2. 在组件内部查找内容区块
                content_article = component.find('article', class_='tech-solutions-resources')
                if not content_article:
                    logger.warning(f"在{component_class}组件内未找到tech-solutions-resources内容区块")
                    continue

                # 3. 提取区块标题
                title_elem = content_article.find(['h2', 'p'], class_='title-Large')
                if not title_elem:
                    logger.warning("未找到区块标题")
                    continue

                section_title = title_elem.get_text(strip=True)

                # 4. 验证标题是否包含指定关键词
                if not any(keyword in section_title for keyword in title_keywords):
                    logger.debug(f"标题 '{section_title}' 不包含{product_type_name}关键词，跳过")
                    continue

                logger.info(f"处理{product_type_name}区块: {section_title}")

                # 5. 查找产品卡片容器
                cards_section = content_article.find('div', class_='tech-solutions-resources__cards-section')

                if not cards_section:
                    # 尝试其他可能的容器
                    cards_section = content_article.find('div', class_='tech-solutions-resources__container__desktop')

                if cards_section:
                    # 6. 提取所有产品卡片，排除隐藏的卡片
                    product_cards = []
                    all_cards = cards_section.find_all('article', class_='buy-sample-product-card')

                    for card in all_cards:
                        # 检查卡片是否被隐藏（有hide类）
                        if 'hide' not in card.get('class', []):
                            product_cards.append(card)

                    # 7. 提取产品信息
                    product_count = 0
                    for card in product_cards:
                        product_info = self._extract_product_card_info(card, section_title, save_dir)
                        if product_info:
                            # 添加产品类型标记
                         #   product_info['product_category'] = product_type_name
                        #    product_info['component_type'] = component_class
                            products_list.append(product_info)
                            product_count += 1

                    logger.info(f"从 '{section_title}' 中提取到 {product_count} 个{product_type_name}")
                    total_extracted += product_count
                else:
                    logger.warning(f"在 '{section_title}' 区块中未找到产品卡片容器")

            logger.info(f"{product_type_name}提取完成，总计 {total_extracted} 个产品")

        except Exception as e:
            logger.error(f"提取{product_type_name}失败: {e}", exc_info=True)

    def _extract_hardware_products(self, soup: BeautifulSoup, products_list: list, save_dir: str):
        """提取硬件产品部分 - 调用通用提取函数"""
        self._extract_products_by_component(
            soup,
            products_list,
            save_dir,
            component_class='SolutionProductCard',
            title_keywords=['硬件产品', '产品特性'],
            product_type_name='硬件产品'
        )

    def _extract_evaluation_products(self, soup: BeautifulSoup, products_list: list, save_dir: str):
        """提取评估板部分 - 调用通用提取函数"""
        self._extract_products_by_component(
            soup,
            products_list,
            save_dir,
            component_class='SolutionEvaluationBoardsCard',
            title_keywords=['评估板', '评估版', '评估套件', '评估工具'],
            product_type_name='评估板'
        )

    def _deduplicate_products(self, products: list) -> list:
        """去重产品列表"""
        unique_products = []
        seen_models = set()
        for product in products:
            model = product.get('model', '')
            if model and model not in seen_models:
                seen_models.add(model)
                unique_products.append(product)
            elif model in seen_models:
                logger.warning(f"重复产品跳过：{model}")
        logger.info(f"去重处理：原{len(products)},去重后：{len(unique_products)}")
        return unique_products

    def extract_hardware_and_evaluation_products(self, soup: BeautifulSoup):
        """提取硬件产品和评估板信息"""
        try:
            # 1. 初始化数据结构
            hardware_products = []
            evaluation_products = []

            # 2. 创建产品图片目录
            product_images_dir = os.path.join(self.base_dir, 'product_images')
            os.makedirs(product_images_dir, exist_ok=True)

            # 3. 提取硬件产品
            self._extract_products_by_component(
                soup,
                hardware_products,
                product_images_dir,
                component_class='SolutionProductCard',
                title_keywords=['硬件产品', '产品特性'],
                product_type_name='硬件产品'
            )

            # 4. 提取评估板
            self._extract_products_by_component(
                soup,
                evaluation_products,
                product_images_dir,
                component_class='SolutionEvaluationBoardsCard',
                title_keywords=['评估板', '评估版', '评估套件', '评估工具'],
                product_type_name='评估板'
            )

            hardware_products = self._deduplicate_products(hardware_products)
            evaluation_products = self._deduplicate_products(evaluation_products)

            # 5. 保存到主数据结构
            self.data['hardware_products'] = hardware_products
            self.data['evaluation_products'] = evaluation_products

            # 6. 记录统计信息
            total_products = len(hardware_products) + len(evaluation_products)
            logger.info(
                f"产品提取完成: 硬件产品 {len(hardware_products)} 个，评估板 {len(evaluation_products)} 个，总计 {total_products} 个")

            return {
                'hardware_products': hardware_products,
                'evaluation_products': evaluation_products
            }

        except Exception as e:
            logger.error(f"提取产品信息失败: {e}")
            return None

    def _extract_product_card_info(self, card, category: str, save_dir: str) -> dict:
        """从单个产品卡片中提取信息"""
        try:
            # 提取产品型号
            model_element = card.find('a', class_='title-extraSmall')
            if not model_element:
                return None

            model = model_element.get_text(strip=True)

            # 提取产品描述
            desc_element = card.find('div', class_='body-medium')
            description = desc_element.get_text(strip=True) if desc_element else ''

            # 查找图片元素 - 只在当前卡片内查找
            img_element = None
            img_url = None

            # 1. 首先尝试最常见的类名
            img_element = card.find('img', class_='buy-sample-product-card__container__header__image-wrapper__image')

            # 2. 如果没找到，尝试其他可能的类名
            if not img_element:
                img_element = card.find('img', class_=lambda c: c and 'buy-sample-product-card' in c)

            # 3. 查找image-wrapper内的图片
            if not img_element:
                image_wrapper = card.find('div', class_='buy-sample-product-card__container__header__image-wrapper')
                if image_wrapper:
                    img_element = image_wrapper.find('img')

            # 4. 查找卡片内的任何img元素
            if not img_element:
                img_element = card.find('img')

            # 如果找到了图片元素，提取URL
            if img_element:
                img_src = img_element.get('src')
                if img_src:
                    img_url = urljoin(self.base_url, img_src)

            # 获取图片文件名和本地路径
            img_filename = None
            local_img_path = None

            if img_url:
                # 生成文件名
                img_filename = self._generate_product_image_filename(img_url, model)

                # 下载图片
                local_img_path = self._download_product_image(img_url, img_filename, save_dir)
            else:
                # 如果没有img_url，尝试在本地目录中查找已存在的图片
                img_filename = self._find_existing_image_filename(model, save_dir)
                if img_filename:
                    local_img_path = os.path.join(save_dir, img_filename)

            # 提取产品链接
            product_link = model_element.get('href', '')
            if product_link and not product_link.startswith('http'):
                product_link = urljoin(self.base_url, product_link)

            # 构建产品信息
            product_info = {
                'category': category,
                'model': model,
                'description': description,
                'image_url': img_url if img_url else '',
                'image_filename': img_filename if img_filename else '',
                'local_image_path': local_img_path if local_img_path else '',
                'product_link': product_link,
            }

            # 记录调试信息
            if local_img_path and not img_url:
                logger.debug(f"产品 {model} 有本地图片但未找到图片URL: {local_img_path}")
            elif not local_img_path and img_url:
                logger.debug(f"产品 {model} 有图片URL但未下载成功: {img_url}")

            logger.debug(f"提取产品: {model} - {description[:50]}...")

            return product_info

        except Exception as e:
            logger.error(f"提取产品卡片信息失败: {e}")
            return None

    def _find_existing_image_filename(self, model: str, save_dir: str) -> str:
        """在本地目录中查找已存在的图片文件名"""
        try:
            if not os.path.exists(save_dir):
                return None

            # 清理型号用于匹配
            clean_model = re.sub(r'[^\w]', '', model).lower()

            # 遍历目录查找匹配的图片文件
            for filename in os.listdir(save_dir):
                # 检查文件名是否包含产品型号
                clean_filename = re.sub(r'[^\w]', '', filename).lower()
                if clean_model in clean_filename:
                    return filename

            return None
        except Exception as e:
            logger.error(f"查找已存在图片失败: {e}")
            return None

    def _generate_product_image_filename(self, img_url: str, model: str) -> str:
        """生成产品图片文件名"""
        try:
            # 从URL中提取原始文件名
            parsed_url = urlparse(img_url)
            original_filename = os.path.basename(parsed_url.path)

            # 清理文件名：移除查询参数
            if '?' in original_filename:
                original_filename = original_filename.split('?')[0]

            # 如果没有扩展名，添加.jpg
            if '.' not in original_filename:
                original_filename = f"{original_filename}.jpg"

            # 清理文件名：移除特殊字符，使用产品型号作为前缀
            safe_model = re.sub(r'[^\w\-]', '_', model)
            safe_filename = re.sub(r'[^\w\-.]', '_', original_filename)

            # 检查是否已经存在相同文件名的文件
            if os.path.exists(os.path.join(self.base_dir, 'product_images', safe_filename)):
                return safe_filename

            # 如果原始文件名中已经包含型号，直接使用清理后的文件名
            model_clean = model.lower().replace('-', '').replace('_', '')
            filename_clean = safe_filename.lower().replace('-', '').replace('_', '')

            if model_clean in filename_clean:
                return safe_filename
            else:
                # 否则添加型号前缀
                return f"{safe_model}_{safe_filename}"

        except Exception as e:
            logger.error(f"生成图片文件名失败: {e}")
            return f"{model}_product_image.jpg"

    def _download_product_image(self, img_url: str, filename: str, save_dir: str) -> str:
        """下载产品图片"""
        try:
            filepath = os.path.join(save_dir, filename)

            # 检查文件是否已存在
            if os.path.exists(filepath):
                logger.debug(f"图片已存在，跳过下载: {filename}")
                return filepath

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': self.base_url
            }

            # 尝试下载图片
            response = requests.get(img_url, headers=headers, timeout=10)
            response.raise_for_status()

            # 检查文件大小
            if len(response.content) < 100:  # 如果文件太小，可能是错误页面
                logger.warning(f"下载的图片文件过小，可能无效: {filename}")
                return None

            # 保存文件
            with open(filepath, 'wb') as f:
                f.write(response.content)

            logger.info(f"下载产品图片成功: {filename} ({len(response.content)} bytes)")
            return filepath

        except requests.exceptions.RequestException as e:
            logger.error(f"下载产品图片失败（网络错误）: {e}")
            return None
        except Exception as e:
            logger.error(f"下载产品图片失败: {e}")
            return None

    def extract_signal_chains(self, soup: BeautifulSoup):
        """提取信号链模块"""
        try:
            # 1. 查找信号链容器
            signal_chains_container = soup.find('div', class_='legacy-component-content')
            if not signal_chains_container:
                logger.info("页面中未找到信号链模块")
                return None

            # 2. 创建信号链存储目录
            signal_chain_dir = os.path.join(self.base_dir, 'signal_chains')
            os.makedirs(signal_chain_dir, exist_ok=True)

            # 3. 初始化数据结构
            signal_chains_data = {
                'module_title': '',
                'total_count': 0,
                'chains': []
            }

            # 4. 提取模块标题
            section_heading = signal_chains_container.find('div', class_='section-heading')
            if section_heading:
                h3_tags = section_heading.find_all('h3')
                if h3_tags:
                    signal_chains_data['module_title'] = h3_tags[0].get_text(strip=True)
                    # 提取总数（括号中的数字）
                    if len(h3_tags) > 1:
                        count_text = h3_tags[1].get_text(strip=True)
                        import re
                        match = re.search(r'\((\d+)\)', count_text)
                        if match:
                            signal_chains_data['total_count'] = int(match.group(1))

            # 5. 提取列表选项（信号链类别）
            options_list = signal_chains_container.find('ul', class_='options-list')
            if not options_list:
                logger.warning("未找到信号链选项列表")
                return signal_chains_data

            # 6. 直接查找所有可能的信号链图片URL
            all_signal_chain_urls = self._find_all_signal_chain_urls(soup)

            # 7. 提取所有列表项
            chains = []
            for li in options_list.find_all('li'):
                a_tag = li.find('a')
                if a_tag:
                    list_name = a_tag.get_text(strip=True)
                    data_target = a_tag.get('data-target', '')
                    is_active = 'active' in li.get('class', [])

                    # 8. 从data_target中提取chain_id
                    chain_id = None
                    if data_target and data_target.startswith('ISC-'):
                        chain_id = data_target.replace('ISC-', '')

                    # 9. 查找对应的图片信息
                    image_info = None
                    if chain_id:
                        image_info = self._find_image_info_for_chain_id(chain_id, all_signal_chain_urls,
                                                                        signal_chain_dir)

                    chain_data = {
                        'list_name': list_name,
                        'data_target': data_target,
                        'is_active': is_active,
                        'image_info': image_info
                    }

                    # 10. 如果有图片信息，提取热点和表格
                    if image_info:
                        # 添加热点信息
                        chain_data['hotspots'] = image_info.get('hotspots', [])

                        # 尝试提取表格信息
                        chain_data['hotspot_tables'] = self._extract_hotspot_tables(signal_chains_container)

                    chains.append(chain_data)

            signal_chains_data['chains'] = chains

            # 11. 保存到主数据结构
            self.data['signal_chains'] = signal_chains_data

            logger.info(f"信号链提取完成: 共找到 {len(chains)} 个信号链类型")

            # 12. 导出为CSV文件
            self._export_signal_chains_to_csv(signal_chains_data)

            return signal_chains_data

        except Exception as e:
            logger.error(f"提取信号链模块失败: {e}", exc_info=True)
            return None





    def _find_all_signal_chain_urls(self, soup):
        """查找所有可能的信号链图片URL"""
        urls_dict = {}

        try:
            # 方法1: 直接扫描所有img标签的src
            all_img_tags = soup.find_all('img')

            for img in all_img_tags:
                src = img.get('src') or img.get('data-src', '')
                if not src:
                    continue

                # 检查是否是信号链图片
                if 'isc-' in src.lower():
                    # 从URL中提取chain_id
                    match = re.search(r'isc-(\d+)', src, re.IGNORECASE)
                    if match:
                        chain_id = match.group(1)

                        # 构建完整的URL
                        if src.startswith('//'):
                            full_url = 'https:' + src
                        elif src.startswith('/'):
                            full_url = urljoin(self.base_url, src)
                        else:
                            full_url = src

                        urls_dict[chain_id] = full_url

            # 方法2: 查找所有包含isc-的文本
            all_text = str(soup)
            pattern = r'https?://[^\s"\']*isc-\d+[^\s"\']*\.(?:png|jpg|jpeg|gif)'
            matches = re.findall(pattern, all_text, re.IGNORECASE)

            for url in matches:
                match = re.search(r'isc-(\d+)', url, re.IGNORECASE)
                if match:
                    chain_id = match.group(1)
                    urls_dict[chain_id] = url

            logger.info(f"找到 {len(urls_dict)} 个可能的信号链图片URL")

        except Exception as e:
            logger.error(f"查找信号链图片URL失败: {e}")

        return urls_dict

    def _extract_hotspots_for_chain_id(self, chain_id):
        """根据chain_id提取热点信息"""
        hotspots = []

        # 由于我们可能没有完整的HTML结构，这里需要模拟提取热点
        # 在实际应用中，您可能需要从其他地方获取热点信息
        try:
            # 这里只是一个示例，实际需要根据页面结构提取
            # 您可以尝试从map标签中提取
            logger.info(f"提取chain_id {chain_id} 的热点信息")

        except Exception as e:
            logger.error(f"提取chain_id {chain_id} 的热点信息失败: {e}")

        return hotspots

    def _find_all_signal_chain_images(self, container, save_dir):
        """查找所有信号链图片"""
        all_chains = []

        try:
            # 1. 查找所有signal-chain-container
            signal_containers = container.find_all('div', class_='signal-chain-container')

            # 2. 如果没有找到，尝试其他可能的类名
            if not signal_containers:
                signal_containers = container.find_all('div', class_=lambda c: c and 'signal' in c and 'chain' in c)

            for s_container in signal_containers:
                # 获取容器ID
                container_id = s_container.get('id', '')
                if not container_id:
                    continue

                # 从ID中提取chain_id
                chain_id = None
                if 'isc-' in container_id.lower():
                    # 匹配 pattern: waveformGenerator_isc-XXXX
                    match = re.search(r'isc-(\d+)', container_id, re.IGNORECASE)
                    if match:
                        chain_id = match.group(1)

                if not chain_id:
                    continue

                # 查找图片元素
                img_element = None

                # 尝试多种查找方式
                img_candidates = s_container.find_all('img')
                for img in img_candidates:
                    src = img.get('src') or img.get('data-src')
                    if src and ('isc-' in src.lower() or chain_id in src):
                        img_element = img
                        break

                # 如果没找到，取第一个img
                if not img_element and img_candidates:
                    img_element = img_candidates[0]

                if not img_element:
                    continue

                img_src = img_element.get('src') or img_element.get('data-src', '')
                if not img_src:
                    continue

                # 构建完整的图片URL
                if img_src.startswith('//'):
                    img_url = 'https:' + img_src
                elif img_src.startswith('/'):
                    img_url = urljoin(self.base_url, img_src)
                elif not img_src.startswith(('http://', 'https://')):
                    img_url = urljoin(self.base_url, img_src)
                else:
                    img_url = img_src

                # 生成文件名
                img_filename = f"signal_chain_{chain_id}.png"

                # 下载图片到本地
                local_path = self._download_signal_chain_image(img_url, img_filename, save_dir)

                # 查找对应的map元素
                map_element = None
                map_name = f'isc-{chain_id}'

                # 在当前容器附近查找map
                next_elem = s_container.find_next_sibling()
                for _ in range(10):  # 向后查找10个兄弟元素
                    if next_elem and next_elem.name == 'map' and next_elem.get('name') == map_name:
                        map_element = next_elem
                        break
                    if next_elem:
                        next_elem = next_elem.find_next_sibling()
                    else:
                        break

                hotspots = []
                if map_element:
                    hotspots = self._extract_hotspot_info(map_element)

                all_chains.append({
                    'chain_id': chain_id,
                    'img_src': img_url,
                    'filename': img_filename,
                    'local_path': local_path,
                    'hotspots': hotspots
                })

        except Exception as e:
            logger.error(f"查找所有信号链图片失败: {e}")

        logger.info(f"找到 {len(all_chains)} 个信号链图片")
        return all_chains

    def _find_all_signal_chain_images_direct(self):
        """直接查找所有信号链图片（使用预定义的URL模式）"""
        all_images = []

        try:
            # 预定义的信号链ID列表（从页面中获取）
            chain_ids = ['0118', '0412', '0413', '0415', '0414']

            # 基础URL模板
            base_url_template = "https://www.analog.com/packages/isc/v2824/zh/isc-{}.png"

            for chain_id in chain_ids:
                img_url = base_url_template.format(chain_id)

                # 检查URL是否有效
                try:
                    response = requests.head(img_url, timeout=5)
                    if response.status_code == 200:
                        # 下载图片
                        img_filename = f"signal_chain_{chain_id}.png"
                        local_path = self._download_signal_chain_image(
                            img_url,
                            img_filename,
                            os.path.join(self.base_dir, 'signal_chains')
                        )

                        if local_path:
                            all_images.append({
                                'chain_id': chain_id,
                                'img_src': img_url,
                                'filename': img_filename,
                                'local_path': local_path,
                                'hotspots': []
                            })
                            logger.info(f"找到并下载信号链图片: {chain_id}")
                        else:
                            logger.warning(f"无法下载信号链图片: {chain_id}")
                    else:
                        logger.warning(f"信号链图片不存在: {chain_id} (HTTP {response.status_code})")

                except Exception as e:
                    logger.error(f"检查信号链图片失败 {chain_id}: {e}")

            logger.info(f"直接查找完成，找到 {len(all_images)} 个信号链图片")

        except Exception as e:
            logger.error(f"直接查找信号链图片失败: {e}")

        return all_images


    def _find_signal_chain_image(self, container, data_target):
        """根据data_target查找对应的信号链图片"""
        try:
            # 移除"ISC-"前缀获取ID
            chain_id = data_target.replace('ISC-', '')

            # 方法1：直接通过ID查找对应的图片容器
            img_container_id = f"waveformGenerator_isc-{chain_id}"
            img_container = container.find('div', id=img_container_id)

            # 方法2：如果找不到，尝试查找所有signal-chain-container
            if not img_container:
                all_containers = container.find_all('div', class_='signal-chain-container')
                for cont in all_containers:
                    if f"isc-{chain_id}" in cont.get('id', ''):
                        img_container = cont
                        break

            # 方法3：如果还是找不到，尝试查找所有图片
            if not img_container:
                # 查找所有可能的图片容器
                possible_containers = container.find_all('div', class_=lambda c: c and 'signal-chain' in (c or ''))
                for cont in possible_containers:
                    if chain_id in str(cont):
                        img_container = cont
                        break

            if not img_container:
                logger.warning(f"未找到信号链图片容器: {data_target} (ID: {chain_id})")
                return None

            # 查找图片元素
            img_element = None

            # 尝试多种方式查找图片
            img_selectors = [
                ('img', {'class_': 'mapster_el'}),
                ('img', {}),  # 任何img标签
                ('img', {'class_': lambda c: c and 'mapster' in c}),
            ]

            for tag_name, kwargs in img_selectors:
                img_element = img_container.find(tag_name, **kwargs) if kwargs else img_container.find(tag_name)
                if img_element:
                    break

            if not img_element:
                logger.warning(f"在容器中未找到图片元素: {data_target}")
                return None

            img_src = img_element.get('src', '')
            if not img_src:
                # 尝试data-src属性
                img_src = img_element.get('data-src', '')

            if not img_src:
                logger.warning(f"图片元素没有src或data-src属性: {data_target}")
                return None

            # 构建完整的图片URL
            if img_src.startswith('//'):
                img_url = 'https:' + img_src
            elif img_src.startswith('/'):
                img_url = urljoin(self.base_url, img_src)
            elif not img_src.startswith(('http://', 'https://')):
                # 可能是相对路径
                img_url = urljoin(self.base_url, img_src)
            else:
                img_url = img_src

            # 生成文件名
            img_filename = f"signal_chain_{chain_id}.png"

            # 查找对应的map元素 - 改进查找方式
            map_element = None
            map_selectors = [
                ('map', {'name': f'isc-{chain_id}'}),
                ('map', {'name': lambda n: n and f'isc-{chain_id}' in n}),
                ('map', {}),  # 任何map标签
            ]

            for tag_name, kwargs in map_selectors:
                map_element = container.find(tag_name, **kwargs) if kwargs else container.find(tag_name)
                if map_element:
                    break

            hotspots = []
            if map_element:
                hotspots = self._extract_hotspot_info(map_element)
            else:
                logger.debug(f"未找到地图元素: isc-{chain_id}")

            return {
                'chain_id': chain_id,
                'img_src': img_url,
                'filename': img_filename,
                'hotspots': hotspots
            }

        except Exception as e:
            logger.error(f"查找信号链图片失败 {data_target}: {e}", exc_info=True)
            return None

    def _extract_hotspot_info(self, map_element):
        """提取热点区域信息"""
        hotspots = []
        try:
            if map_element:
                for area in map_element.find_all('area'):
                    component_name = self._extract_component_name_from_alt(area.get('alt', ''))
                    hotspot_info = {
                        'component_name': component_name,
                        'table_name': [],
                        'table_path': []
                    }
                    hotspots.append(hotspot_info)

            logger.info(f"提取到 {len(hotspots)} 个热点区域")

        except Exception as e:
            logger.error(f"提取热点信息失败: {e}")

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


    def _extract_hotspot_tables(self, component_details):
        """提取热点对应的表格内容"""
        tables_data = []
        try:
            # 查找所有表格
            table_elements = component_details.find_all('div', class_='scd-partTable')

            for table_elem in table_elements:
                table_info = self._extract_signal_chain_table(table_elem)
                if table_info:
                    tables_data.append(table_info)

            logger.info(f"提取到 {len(tables_data)} 个热点表格")

        except Exception as e:
            logger.error(f"提取热点表格失败: {e}")

        return tables_data

    def _extract_all_signal_chain_tables(self, container, signal_chains_data):
        """提取所有信号链的表格数据（从script模板中）"""
        try:
            # 查找script模板
            script_template = container.find('script', {'id': 'scd-view'})
            if not script_template:
                return

            # 查找已经渲染的表格内容
            parts_selected = container.find('div', class_='scd-partsSelected')
            if parts_selected:
                # 提取组件标题
                part_title = parts_selected.find('div', class_='scd-partTitle')
                if part_title:
                    title_text = part_title.get_text(strip=True)
                    # 清理按钮文本
                    title_text = re.sub(r'\s+X\s*$', '', title_text)
                    title_text = re.sub(r'\s+\+\s*$', '', title_text)
                    signal_chains_data['current_component'] = title_text

                # 提取表格
                tables = self._extract_all_tables_from_container(parts_selected)
                if tables:
                    signal_chains_data['current_tables'] = tables

        except Exception as e:
            logger.error(f"提取所有表格数据失败: {e}")

    def _extract_all_tables_from_container(self, container):
        """从容器中提取所有表格"""
        tables = []
        try:
            table_elements = container.find_all('div', class_='scd-partTable')

            for table_elem in table_elements:
                table_info = self._extract_detailed_table(table_elem)
                if table_info:
                    tables.append(table_info)

        except Exception as e:
            logger.error(f"提取容器表格失败: {e}")

        return tables

    def _extract_detailed_table(self, table_elem):
        """提取详细的表格数据"""
        try:
            table_info = {}

            # 提取表格标题
            table_title_elem = table_elem.find('div', class_='scd-tablename')
            if table_title_elem:
                table_info['table_title'] = table_title_elem.get_text(strip=True)

            # 提取表格数据
            table = table_elem.find('table')
            if table:
                # 提取表头
                headers = []
                header_row = table.find('tr')
                if header_row:
                    for th in header_row.find_all('th'):
                        header_text = th.get_text(strip=True)
                        # 清理换行符
                        header_text = ' '.join(header_text.split())
                        headers.append(header_text)

                table_info['headers'] = headers

                # 提取数据行
                rows = []
                data_rows = table.find_all('tr')[1:]  # 跳过表头

                for row in data_rows:
                    row_data = []
                    cells = row.find_all('td')

                    for cell in cells:
                        # 检查是否有链接
                        link = cell.find('a')
                        if link:
                            cell_text = link.get_text(strip=True)
                            cell_href = link.get('href', '')
                            cell_data = {
                                'text': cell_text,
                                'link': urljoin(self.base_url, cell_href) if cell_href else None
                            }
                        else:
                            cell_text = cell.get_text(strip=True)
                            cell_data = {'text': cell_text, 'link': None}

                        row_data.append(cell_data)

                    if row_data:
                        rows.append(row_data)

                table_info['rows'] = rows

            return table_info if table_info else None

        except Exception as e:
            logger.error(f"提取详细表格失败: {e}")
            return None

    def _export_signal_chains_to_csv(self, signal_chains_data):
        """将信号链数据导出为CSV文件"""
        try:
            # 1. 导出信号链列表信息
            chains_list = []
            for chain in signal_chains_data.get('chains', []):
                chains_list.append({
                    'list_name': chain.get('list_name', ''),
                    'data_target': chain.get('data_target', ''),
                    'is_active': chain.get('is_active', False),
                    'image_filename': chain['image_info'].get('filename', '') if chain.get('image_info') else '',
                    'image_url': chain['image_info'].get('img_src', '') if chain.get('image_info') else '',
                    'local_image_path': chain.get('local_image_path', ''),
                    'hotspot_count': len(chain.get('hotspots', []))
                })

            # if chains_list:
            #     df_chains = pd.DataFrame(chains_list)
            #     chains_csv = os.path.join(self.base_dir, 'signal_chains_list.csv')
            #     df_chains.to_csv(chains_csv, index=False, encoding='utf-8-sig')
            #     logger.info(f"信号链列表已保存到: {chains_csv}")

            # # 2. 导出热点信息
            # hotspots_list = []
            # for chain in signal_chains_data.get('chains', []):
            #     chain_name = chain.get('list_name', '')
            #     for hotspot in chain.get('hotspots', []):
            #         hotspots_list.append({
            #             'chain_name': chain_name,
            #             'component_name': hotspot.get('component_name', ''),
            #             'alt': hotspot.get('alt', ''),
            #             'shape': hotspot.get('shape', ''),
            #             'data_key': hotspot.get('data_key', ''),
            #             'coords': hotspot.get('coords', '')
            #         })
            #
            # if hotspots_list:
            #     df_hotspots = pd.DataFrame(hotspots_list)
            #     hotspots_csv = os.path.join(self.base_dir, 'signal_chains_hotspots.csv')
            #     df_hotspots.to_csv(hotspots_csv, index=False, encoding='utf-8-sig')
            #     logger.info(f"信号链热点信息已保存到: {hotspots_csv}")

            # 3. 导出表格数据
            tables_list = []
            for chain in signal_chains_data.get('chains', []):
                chain_name = chain.get('list_name', '')
                tables = chain.get('hotspot_tables', [])

                for table_idx, table in enumerate(tables):
                    table_title = table.get('table_title', f'Table_{table_idx + 1}')

                    # 提取表头
                    headers = table.get('headers', [])

                    # 提取行数据
                    rows = table.get('rows', [])
                    for row_idx, row in enumerate(rows):
                        row_data = {'chain_name': chain_name, 'table_title': table_title, 'row_index': row_idx + 1}

                        # 将每个单元格数据添加到行数据中
                        for col_idx, cell in enumerate(row):
                            if col_idx < len(headers):
                                header = headers[col_idx]
                                row_data[f'{header}_text'] = cell.get('text', '')
                                if cell.get('link'):
                                    row_data[f'{header}_link'] = cell.get('link')

                        tables_list.append(row_data)

            # 4. 导出当前显示的表格数据
            if signal_chains_data.get('current_tables'):
                current_tables = signal_chains_data['current_tables']
                for table_idx, table in enumerate(current_tables):
                    table_title = table.get('table_title', f'Current_Table_{table_idx + 1}')
                    component_name = signal_chains_data.get('current_component', 'Unknown')

                    headers = table.get('headers', [])
                    rows = table.get('rows', [])

                    for row_idx, row in enumerate(rows):
                        row_data = {'component_name': component_name, 'table_title': table_title,
                                    'row_index': row_idx + 1}

                        for col_idx, cell in enumerate(row):
                            if col_idx < len(headers):
                                header = headers[col_idx]
                                row_data[f'{header}_text'] = cell.get('text', '')
                                if cell.get('link'):
                                    row_data[f'{header}_link'] = cell.get('link')

                        tables_list.append(row_data)

            # if tables_list:
            #     df_tables = pd.DataFrame(tables_list)
            #     tables_csv = os.path.join(self.base_dir, 'signal_chains_tables.csv')
            #     df_tables.to_csv(tables_csv, index=False, encoding='utf-8-sig')
            #     logger.info(f"信号链表格数据已保存到: {tables_csv}")

            # 5. 创建汇总报告
            self._create_signal_chains_summary(signal_chains_data)

        except Exception as e:
            logger.error(f"导出信号链数据到CSV失败: {e}")

    def _create_signal_chains_summary(self, signal_chains_data):
        """创建信号链数据汇总报告"""
        try:
            summary_content = f"""# 信号链数据汇总报告

    ## 基本信息
    - 模块标题: {signal_chains_data.get('module_title', 'N/A')}
    - 总数量: {signal_chains_data.get('total_count', 0)}
    - 提取时间: {time.strftime('%Y-%m-%d %H:%M:%S')}

    ## 信号链列表
    """

            for chain in signal_chains_data.get('chains', []):
                summary_content += f"\n### {chain.get('list_name', 'N/A')}\n"
                summary_content += f"- 数据目标: {chain.get('data_target', 'N/A')}\n"
                summary_content += f"- 是否激活: {'是' if chain.get('is_active') else '否'}\n"

                if chain.get('image_info'):
                    img_info = chain['image_info']
                    summary_content += f"- 图片文件: {img_info.get('filename', 'N/A')}\n"
                    summary_content += f"- 图片URL: {img_info.get('img_src', 'N/A')}\n"

                summary_content += f"- 本地图片路径: {chain.get('local_image_path', 'N/A')}\n"
                summary_content += f"- 热点数量: {len(chain.get('hotspots', []))}\n"

                # 列出热点
                hotspots = chain.get('hotspots', [])
                if hotspots:
                    summary_content += "  热点列表:\n"
                    for hotspot in hotspots:
                        summary_content += f"  - {hotspot.get('component_name', 'N/A')} (alt: {hotspot.get('alt', 'N/A')})\n"

            summary_file = os.path.join(self.base_dir, 'signal_chains_summary.md')
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(summary_content)

            logger.info(f"信号链汇总报告已保存到: {summary_file}")

        except Exception as e:
            logger.error(f"创建信号链汇总报告失败: {e}")


    def _extract_signal_chain_basic_info(self, container, save_dir):
        """提取信号链基本信息"""
        try:
            data = {
                'module_title': '',
                'total_count': 0,
                'current_chain': {},
                'all_chains': [],
                'chains': []
            }

            # 提取模块总标题
            section_heading = container.find('div', class_='section-heading')
            if section_heading:
                h3_tags = section_heading.find_all('h3')
                if len(h3_tags) >= 1:
                    data['module_title'] = h3_tags[0].get_text(strip=True)
                    # 提取总数：从"(5)"这样的格式中提取数字
                    if len(h3_tags) >= 2:
                        count_text = h3_tags[1].get_text(strip=True)
                        import re
                        match = re.search(r'\((\d+)\)', count_text)
                        if match:
                            data['total_count'] = int(match.group(1))

            # 提取当前激活的信号链信息
            current_title_elem = container.find('h3', id='signalChaintitle')
            if current_title_elem:
                current_title = current_title_elem.get_text(strip=True)
                # 提取当前页码
                pager_elem = container.find('div', class_='textpager')
                current_page = 1
                total_pages = data['total_count']

                if pager_elem:
                    pager_text = pager_elem.get_text(strip=True)
                    match = re.search(r'(\d+)\s+of\s+(\d+)', pager_text)
                    if match:
                        current_page = int(match.group(1))
                        total_pages = int(match.group(2))

                data['current_chain'] = {
                    'title': current_title,
                    'current_page': current_page,
                    'total_pages': total_pages
                }

            # 提取所有信号链选项
            options_list = container.find('ul', class_='options-list')
            if options_list:
                all_chains = []
                for li in options_list.find_all('li'):
                    a_tag = li.find('a')
                    if a_tag:
                        chain_title = a_tag.get_text(strip=True)
                        data_target = a_tag.get('data-target', '')
                        is_active = 'active' in li.get('class', [])

                        chain_info = {
                            'title': chain_title,
                            'data_target': data_target,
                            'is_active': is_active
                        }
                        all_chains.append(chain_info)

                data['all_chains'] = all_chains

            return data

        except Exception as e:
            logger.error(f"提取信号链基本信息失败: {e}")
            return {}

    def _extract_signal_chain_images(self, container, save_dir, signal_chains_data):
        """提取信号链图片"""
        try:
            # 查找所有信号链图片容器
            signal_containers = container.find_all('div', class_='signal-chain-container')

            chains = []

            for s_container in signal_containers:
                # 获取信号链ID（从id属性中提取）
                container_id = s_container.get('id', '')
                if not container_id.startswith('waveformGenerator_isc-'):
                    continue

                signal_chain_id = container_id.replace('waveformGenerator_isc-', '')

                # 查找图片
                img_element = s_container.find('img', class_='mapster_el')
                if not img_element:
                    continue

                img_src = img_element.get('src', '')
                if not img_src:
                    continue

                # 构建完整的图片URL
                if img_src.startswith('//'):
                    img_url = 'https:' + img_src
                elif img_src.startswith('/'):
                    img_url = urljoin(self.base_url, img_src)
                else:
                    img_url = img_src

                # 生成文件名
                img_filename = f"signal_chain_{signal_chain_id}.png"
                filepath = os.path.join(save_dir, img_filename)

                # 下载图片
                local_img_path = self._download_signal_chain_image(img_url, img_filename,save_dir)

                # 提取对应的信号链标题
                chain_title = self._find_chain_title_for_id(signal_chain_id, signal_chains_data.get('all_chains', []))

                # 保存信号链信息
                chain_info = {
                    'chain_id': signal_chain_id,
                    'title': chain_title,
                    'image_url': img_url,
                    'image_filename': img_filename,
                    'local_image_path': local_img_path,
                    'is_currently_displayed': 'style=""' in str(s_container) or 'style="display: block;"' in str(
                        s_container)
                }

                # 提取热点区域信息（如果有）
                map_element = s_container.find_next('map')
                if map_element:
                    areas = []
                    for area in map_element.find_all('area'):
                        area_info = {
                            'alt': area.get('alt', ''),
                            'shape': area.get('shape', ''),
                            'coords': area.get('coords', ''),
                            'data_key': area.get('data-mapster-key', '')
                        }
                        areas.append(area_info)

                    if areas:
                        chain_info['hotspots'] = areas

                chains.append(chain_info)

            signal_chains_data['chains'] = chains

            logger.info(f"提取到 {len(chains)} 个信号链图片")

        except Exception as e:
            logger.error(f"提取信号链图片失败: {e}")

    def _find_chain_title_for_id(self, chain_id, all_chains):
        """根据ID查找对应的信号链标题"""
        # 尝试从数据目标中匹配
        for chain in all_chains:
            if chain.get('data_target') == f"ISC-{chain_id}":
                return chain.get('title', '')

        # 如果没有匹配，尝试从ID推断
        # 这里可以根据实际情况添加更多匹配逻辑
        return f"信号链 {chain_id}"

    def _download_signal_chain_image(self, img_url, filename, save_dir=None):
        """下载信号链图片"""
        try:
            # 构建完整的文件路径
            if save_dir:
                filepath = os.path.join(save_dir, filename)
            else:
                # 如果没有提供save_dir，假设filename已经是完整路径
                filepath = filename

            # 检查文件是否已存在
            if os.path.exists(filepath):
                logger.debug(f"信号链图片已存在: {os.path.basename(filepath)}")
                return filepath

            # 确保目录存在
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            # 下载图片
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': self.base_url
            }

            response = requests.get(img_url, headers=headers, timeout=15)
            response.raise_for_status()

            # 检查文件大小
            if len(response.content) < 1024:  # 小于1KB可能不是有效图片
                logger.warning(f"下载的图片文件过小，可能无效: {filename} ({len(response.content)} bytes)")
                return None

            # 保存文件
            with open(filepath, 'wb') as f:
                f.write(response.content)

            file_size = os.path.getsize(filepath)
            logger.info(f"下载信号链图片: {filename} ({file_size} bytes)")

            return filepath

        except requests.exceptions.RequestException as e:
            logger.error(f"下载信号链图片失败（网络错误） {img_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"下载信号链图片失败 {img_url}: {e}")
            return None

    def extract_signal_chains(self, soup: BeautifulSoup):
        """提取信号链模块"""
        try:
            # 1. 查找信号链容器
            signal_chains_container = soup.find('div', class_='legacy-component-content')
            if not signal_chains_container:
                logger.info("页面中未找到信号链模块")
                return None

            # 2. 创建信号链存储目录
            signal_chain_dir = os.path.join(self.base_dir, 'signal_chains')
            os.makedirs(signal_chain_dir, exist_ok=True)

            # 3. 初始化数据结构
            signal_chains_data = {
                'module_title': '',
                'total_count': 0,
                'chains': []
            }

            # 4. 提取模块标题
            section_heading = signal_chains_container.find('div', class_='section-heading')
            if section_heading:
                h3_tags = section_heading.find_all('h3')
                if h3_tags:
                    signal_chains_data['module_title'] = h3_tags[0].get_text(strip=True)
                    # 提取总数（括号中的数字）
                    if len(h3_tags) > 1:
                        count_text = h3_tags[1].get_text(strip=True)
                        import re
                        match = re.search(r'\((\d+)\)', count_text)
                        if match:
                            signal_chains_data['total_count'] = int(match.group(1))

            # 5. 提取列表选项（信号链类别）
            options_list = signal_chains_container.find('ul', class_='options-list')
            if not options_list:
                logger.warning("未找到信号链选项列表")
                return signal_chains_data

            # 6. 提取所有列表项
            all_direct_images=self._find_all_signal_chain_images_direct()
            chains = []
            for li in options_list.find_all('li'):
                a_tag = li.find('a')
                if a_tag:
                    list_name = a_tag.get_text(strip=True)
                    data_target = a_tag.get('data-target', '')
                    is_active = 'active' in li.get('class', [])

                    # 8. 从data_target中提取chain_id
                    chain_id = None
                    if data_target and data_target.startswith('ISC-'):
                        chain_id = data_target.replace('ISC-', '')

                    # 9. 从直接查找的结果中查找对应的图片信息
                    image_info = None
                    if chain_id:
                        for img_info in all_direct_images:
                            if img_info.get('chain_id') == chain_id:
                                image_info = img_info
                                break

                    chain_data = {
                        'list_name': list_name,
                        'data_target': data_target,
                        'is_active': is_active,
                        'image_info': image_info
                    }

                    # 8. 如果有图片信息，提取热点和表格
                    if image_info:
                        # 添加热点信息
                        chain_data['hotspots'] = image_info.get('hotspots', [])

                        # 尝试提取表格信息
                        chain_data['hotspot_tables'] = self._extract_hotspot_tables(signal_chains_container)

                    chains.append(chain_data)

            signal_chains_data['chains'] = chains

            # 9. 保存到主数据结构
            self.data['signal_chains'] = signal_chains_data

            logger.info(f"信号链提取完成: 共找到 {len(chains)} 个信号链类型")

            # 10. 导出为CSV文件
            self._export_signal_chains_to_csv(signal_chains_data)

            return signal_chains_data

        except Exception as e:
            logger.error(f"提取信号链模块失败: {e}", exc_info=True)
            return None

    def _extract_signal_chain_image_info(self, container, data_target, save_dir):
        """提取信号链图片信息"""
        try:
            # 从data_target中提取chain_id（例如从"ISC-0001"中提取"0001"）
            if not data_target or not data_target.startswith('ISC-'):
                logger.warning(f"无效的data_target: {data_target}")
                return None

            chain_id = data_target.replace('ISC-', '')

            # 查找图片容器 - 直接通过ID查找
            img_container_id = f"waveformGenerator_isc-{chain_id}"
            img_container = container.find('div', id=img_container_id)

            if not img_container:
                logger.warning(f"未找到图片容器: {img_container_id}")
                return None

            # 查找图片元素 - 尝试多个可能的类名
            img_element = None
            img_candidates = img_container.find_all('img')

            for img in img_candidates:
                # 检查是否有src属性
                if img.get('src') or img.get('data-src'):
                    img_element = img
                    break

            if not img_element:
                logger.warning(f"在容器 {img_container_id} 中未找到图片元素")
                return None

            # 获取图片URL
            img_src = img_element.get('src') or img_element.get('data-src', '')
            if not img_src:
                logger.warning(f"图片元素没有src属性: {data_target}")
                return None

            # 构建完整的图片URL
            if img_src.startswith('//'):
                img_url = 'https:' + img_src
            elif img_src.startswith('/'):
                img_url = urljoin(self.base_url, img_src)
            else:
                img_url = img_src

            # 生成文件名
            img_filename = f"signal_chain_{chain_id}.png"

            # 下载图片
            local_path = self._download_signal_chain_image(img_url, img_filename, save_dir)

            # 提取热点信息
            hotspots = self._extract_hotspots_for_chain(container, chain_id)

            return {
                'chain_id': chain_id,
                'img_src': img_url,
                'filename': img_filename,
                'local_path': local_path,
                'hotspots': hotspots
            }

        except Exception as e:
            logger.error(f"提取信号链图片信息失败 {data_target}: {e}")
            return None

    def _extract_hotspots_for_chain(self, container, chain_id):
        """提取特定信号链的热点信息"""
        hotspots = []
        try:
            # 查找对应的map元素
            map_element = container.find('map', {'name': f'isc-{chain_id}'})

            if not map_element:
                logger.debug(f"未找到地图元素: isc-{chain_id}")
                return hotspots

            # 提取所有area元素
            for area in map_element.find_all('area'):
                alt = area.get('alt', '')
                component_name = self._extract_component_name_from_alt(alt)

                hotspot_info = {
                    'component_name': component_name,
                    'module_name': '',  # 初始为空，点击后填充
                    'table_name': '',  # 初始为空，点击后填充
                    'table_path': ''  # 初始为空，点击后填充
                }
                hotspots.append(hotspot_info)

            logger.info(f"提取到 {len(hotspots)} 个热点区域 (isc-{chain_id})")

        except Exception as e:
            logger.error(f"提取热点信息失败 (isc-{chain_id}): {e}")

        return hotspots


    def _extract_all_signal_chain_images_directly(self, soup, save_dir):
        """直接查找所有信号链图片"""
        all_chains = []

        try:
            # 查找所有包含'signal_chain'或'isc-'的图片
            all_images = soup.find_all('img')

            for img in all_images:
                src = img.get('src') or img.get('data-src', '')
                if not src:
                    continue

                # 检查是否是信号链图片
                if 'isc-' in src.lower() and '.png' in src.lower():
                    # 从URL中提取chain_id
                    match = re.search(r'isc-(\d+)', src, re.IGNORECASE)
                    if match:
                        chain_id = match.group(1)

                        # 构建完整的图片URL
                        if src.startswith('//'):
                            img_url = 'https:' + src
                        elif src.startswith('/'):
                            img_url = urljoin(self.base_url, src)
                        else:
                            img_url = src

                        # 生成文件名
                        img_filename = f"signal_chain_{chain_id}.png"

                        # 下载图片
                        local_path = self._download_signal_chain_image(img_url, img_filename, save_dir)

                        # 查找对应的map元素
                        hotspots = self._extract_hotspots_for_chain_directly(soup, chain_id)

                        all_chains.append({
                            'chain_id': chain_id,
                            'img_src': img_url,
                            'filename': img_filename,
                            'local_path': local_path,
                            'hotspots': hotspots
                        })

            logger.info(f"直接查找到 {len(all_chains)} 个信号链图片")

        except Exception as e:
            logger.error(f"直接查找信号链图片失败: {e}")

        return all_chains

    def _extract_hotspots_for_chain_directly(self, soup, chain_id):
        """直接查找特定信号链的热点信息"""
        hotspots = []
        try:
            # 查找对应的map元素
            map_element = soup.find('map', {'name': f'isc-{chain_id}'})

            if not map_element:
                # 尝试其他可能的name格式
                map_element = soup.find('map', {'name': lambda n: n and f'isc-{chain_id}' in n})

            if map_element:
                for area in map_element.find_all('area'):
                    alt = area.get('alt', '')
                    component_name = self._extract_component_name_from_alt(alt)

                    hotspot_info = {
                        'component_name': component_name,
                        'table_name': [],
                        'table_path': []
                    }
                    hotspots.append(hotspot_info)

                logger.info(f"直接提取到 {len(hotspots)} 个热点区域 (isc-{chain_id})")

        except Exception as e:
            logger.error(f"直接提取热点信息失败 (isc-{chain_id}): {e}")

        return hotspots

    def _extract_signal_chain_details(self, container, signal_chains_data):
        """提取信号链详细组件信息（点击热点后显示的内容）"""
        try:
            # 查找组件详情区域
            parts_selected = container.find('div', class_='scd-partsSelected')

            if not parts_selected:
                logger.debug("未找到信号链组件详情区域")
                return

            details = {}

            # 提取组件标题
            part_title_elem = parts_selected.find('div', class_='scd-partTitle')
            if part_title_elem:
                # 移除关闭按钮和展开按钮
                title_text = part_title_elem.get_text(strip=True)
                # 清理文本
                title_text = re.sub(r'\s+X\s*$', '', title_text)  # 移除X按钮
                title_text = re.sub(r'\s+\+\s*$', '', title_text)  # 移除+按钮
                details['component_title'] = title_text

            # 提取所有产品表格
            tables = []
            table_elements = parts_selected.find_all('div', class_='scd-partTable')

            for table_elem in table_elements:
                table_info = self._extract_signal_chain_table(table_elem)
                if table_info:
                    tables.append(table_info)

            if tables:
                details['tables'] = tables
                signal_chains_data['component_details'] = details
                logger.info(f"提取到 {len(tables)} 个组件详情表格")

        except Exception as e:
            logger.error(f"提取信号链组件详情失败: {e}")

    def _extract_signal_chain_table(self, table_elem):
        """提取单个组件表格信息"""
        try:
            table_info = {}

            # 提取表格标题
            table_title_elem = table_elem.find('div', class_='scd-tablename')
            if table_title_elem:
                table_info['table_title'] = table_title_elem.get_text(strip=True)

            # 提取表格数据
            table_data = []
            table_body = table_elem.find('table')

            if table_body:
                # 提取表头
                headers = []
                header_row = table_body.find('tr')
                if header_row:
                    for th in header_row.find_all('th'):
                        header_text = th.get_text(strip=True)
                        # 清理换行符和多余空格
                        header_text = re.sub(r'\s+', ' ', header_text)
                        headers.append(header_text)

                table_info['headers'] = headers

                # 提取数据行
                data_rows = []
                rows = table_body.find_all('tr')[1:]  # 跳过表头行

                for row in rows:
                    # 跳过页脚行
                    if 'tfoot' in str(row.parent) or 'hide' in row.get('class', []):
                        continue

                    row_data = []
                    cells = row.find_all('td')

                    for cell in cells:
                        # 检查是否有链接
                        link = cell.find('a')
                        if link:
                            cell_text = link.get_text(strip=True)
                            cell_href = link.get('href', '')
                            cell_info = {
                                'text': cell_text,
                                'link': cell_href if cell_href else None
                            }
                        else:
                            cell_text = cell.get_text(strip=True)
                            cell_info = {'text': cell_text, 'link': None}

                        row_data.append(cell_info)

                    if row_data:
                        data_rows.append(row_data)

                table_info['rows'] = data_rows

            return table_info if table_info else None

        except Exception as e:
            logger.error(f"提取组件表格失败: {e}")
            return None



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

    #
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




    def _clean_data_for_json(self):
        """清理数据中的非JSON可序列化对象，并移除不需要的字段"""

        def clean(obj):
            if isinstance(obj, dict):
                # 移除不需要的字段
                if 'module_tables' in obj:
                    del obj['module_tables']
                if 'tables' in obj:
                    del obj['tables']
                if 'template_table_schema' in obj:
                    del obj['template_table_schema']
                if 'hotspots' in obj:
                    del obj['hotspots']

                # 清理嵌套对象
                return {k: clean(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean(item) for item in obj]
            elif hasattr(obj, '__class__') and obj.__class__.__name__ == 'Tag':
                return str(obj)
            elif hasattr(obj, '__dict__'):
                try:
                    return clean(obj.__dict__)
                except:
                    return str(obj)
            else:
                return obj

        self.data = clean(self.data)



    def save_data(self):
        """保存所有数据"""
        self._clean_data_for_json()
        # 1. 保存JSON数据
        json_file = os.path.join(self.base_dir, 'complete_data.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        logger.info(f"数据已保存到: {json_file}")

        # # 2. 保存导航路径
        # nav_file = os.path.join(self.base_dir, 'navigation.txt')
        # with open(nav_file, 'w', encoding='utf-8') as f:
        #     f.write(self.data['page_info'].get('navigation_path', ''))

        # 3. 保存完整正文（到「资源」之前的所有文字）
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
        # full_body_file = os.path.join(self.base_dir, 'full_body_text.txt')
        # with open(full_body_file, 'w', encoding='utf-8') as f:
        #     f.write('\n'.join(full_text_parts))
        # logger.info(f"完整正文已保存到: {full_body_file}")

        # 4. 保存产品信息清单
        if self.data.get('hardware_products') or self.data.get('evaluation_products'):
            product_data = []

            # 硬件产品
            for product in self.data.get('hardware_products', []):
                product_data.append({
                    '类型': '硬件产品',
                    '型号': product.get('model', ''),
                    '描述': product.get('description', ''),
                    '图片文件名': product.get('image_filename', ''),
                    '本地图片路径': product.get('local_image_path', ''),
                    '产品链接': product.get('product_link', '')
                })

            # 评估板
            for product in self.data.get('evaluation_products', []):
                product_data.append({
                    '类型': '评估板',
                    '型号': product.get('model', ''),
                    '描述': product.get('description', ''),
                    '图片文件名': product.get('image_filename', ''),
                    '本地图片路径': product.get('local_image_path', ''),
                    '产品链接': product.get('product_link', '')
                })

            if product_data:
                df_products = pd.DataFrame(product_data)
                products_csv = os.path.join(self.base_dir, 'products_list.csv')
                df_products.to_csv(products_csv, index=False, encoding='utf-8-sig')
                logger.info(f"产品清单已保存到: {products_csv}")

        # # 5. 保存表格图片清单
        # if self.data['table_images']:
        #     table_images_data = []
        #     for img in self.data['table_images']:
        #         table_images_data.append({
        #             'table_index': img.get('table_index'),
        #             'table_title': img.get('table_title'),
        #             'image_filename': img.get('filename'),
        #             'image_url': img.get('src'),
        #             'local_path': img.get('local_path'),
        #             'alt_text': img.get('alt', '')
        #         })
        #
        #     df_table_images = pd.DataFrame(table_images_data)
        #     table_images_csv = os.path.join(self.base_dir, 'table_images_list.csv')
        #     df_table_images.to_csv(table_images_csv, index=False, encoding='utf-8-sig')
        #     logger.info(f"表格图片清单已保存到: {table_images_csv}")




    def run(self):
        """运行爬虫"""
        logger.info("开始爬取Analog Devices页面...")

        # 1. 使用Selenium获取页面
        html_content = self.fetch_page_with_selenium()
        if not html_content:
            logger.error("无法获取页面内容")
            return False

        # 2. 触发热点并收集模块表格（LOG AMP DETECTORS 等）
        collected_module_tables = self.trigger_signal_chain_hotspots_and_collect_tables()

        # 3. 提取所有内容（含信号链；若已收集到模块表格则合并并导出）
        self.extract_all_content(html_content, collected_module_tables=collected_module_tables)



        # 4. 关闭Selenium驱动
        self.driver.quit()

        # 5. 保存数据
        self.save_data()

        # 6. 显示摘要
        # self.display_summary()

        return True
    #
    # def display_summary(self):
    #     """显示爬取结果摘要"""
    #     print("\n" + "=" * 70)
    #     print("ANALOG DEVICES 数据爬取完成")
    #     print("=" * 70)
    #
    #     print(f"\n 页面信息:")
    #     print(f"   标题: {self.data['page_info'].get('title', 'N/A')}")
    #     print(f"   导航路径: {self.data['page_info'].get('navigation_path', 'N/A')}")
    #
    #     print(f"\n 数据统计:")
    #     print(f"   章节数量: {len(self.data['sections'])}")
    #     print(f"   产品表格: {len(self.data['product_tables'])}")
    #     print(f"   表格下方图片: {len(self.data['table_images'])}")
    #     print(f"   所有图片: {len(self.data['all_images'])}")
    #
    #     print(f"\n 表格图片关联:")
    #     if self.data['table_images']:
    #         for img in self.data['table_images'][:5]:
    #             table_title = img.get('table_title', '未知表格')
    #             filename = img.get('filename', '未知')
    #             url = img.get('src', '未知')
    #             print(f"    表格: {table_title[:30]}...")
    #             print(f"     图片: {filename}")
    #             print(f"     URL: {url[:50]}...")
    #     else:
    #         print("   未找到表格下方图片")
    #
    #     print(f"\n 保存的文件:")
    #     print(f"   完整数据: {self.base_dir}/complete_data.json")
    #     print(f"   导航路径: {self.base_dir}/navigation.txt")
    #     print(f"   表格图片清单: {self.base_dir}/table_images_list.csv")
    #     print(f"   表格图片目录: {self.base_dir}/table_images/")
    #
    #     print("\n" + "=" * 70)


def parse_scd_view_renderer_html(html_content: str) -> List[Dict]:
    """
    从 HTML 字符串中解析 scd-view-renderer 内的所有表格内容（无需 Selenium）。
    适用于你提供的 VIDEO PROCESSING 等模块的 HTML 片段或完整页面。

    结构：div#scd-view-renderer > div.scd-partsSelected > div.scd-partTitle（模块名）
         + 多个 div.scd-partTable（每个含 .scd-tablename 与 table）。

    返回：与 collected_module_tables 相同结构
        [ { 'module_name': str, 'table_names': [str], 'tables': [ { 'title', 'headers', 'rows' } ] }, ... ]
    每个单元格为 { 'text': str, 'link': str|None }。
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    out = []

    # 优先从 #scd-view-renderer 内找 .scd-partsSelected
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

        # 表头：第一个 tr 的 th
        header_row = table.find('tr')
        if header_row:
            for th in header_row.find_all('th'):
                h = th.get_text(strip=True)
                table_info['headers'].append(re.sub(r'\s+', ' ', h))

        # 数据行：跳过表头、跳过 tfoot 和 class=hide 的 tr
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
    except Exception as e:
        logger.debug(f"解析单表失败: {e}")
        return None


def export_parsed_tables_to_csv(module_tables_list: List[Dict], base_dir: str, include_links: bool = True):
    """
    将 parse_scd_view_renderer_html 的返回结果导出为 CSV。
    - 每个表格一个文件：module_模块名_table_表格名.csv
    - 可选一个合并表：signal_chains_tables_parsed.csv（与现有 signal_chains_tables 格式一致）
    """
    import csv
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
                w.writerow(['组件名称', module_name])
                w.writerow(['模块名称', title])
                w.writerow(headers)
                for row in rows:
                    w.writerow([c.get('text', '') for c in row])
            logger.info(f"已导出: {path}")

            for row_idx, row in enumerate(rows):
                row_data = {'module_name': module_name, 'table_title': title, 'row_index': row_idx + 1}
                for col_idx, cell in enumerate(row):
                    if col_idx < len(headers):
                        h = headers[col_idx]
                        row_data[f'{h}_text'] = cell.get('text', '')
                        if include_links and cell.get('link'):
                            row_data[f'{h}_link'] = cell.get('link')
                tables_flat.append(row_data)

    if tables_flat:
        df = pd.DataFrame(tables_flat)
        combined = os.path.join(csv_dir, 'signal_chains_tables_parsed.csv')
        df.to_csv(combined, index=False, encoding='utf-8-sig')
        logger.info(f"合并表格已导出: {combined}")


#
# if __name__ == "__main__":
#     import sys
#     # 若传入一个 .html 文件路径，则只解析该 HTML 中的 scd-view-renderer 表格并导出 CSV
#     if len(sys.argv) > 1 and sys.argv[1].lower().endswith(('.html', '.htm')):
#         html_path = sys.argv[1]
#         out_dir = sys.argv[2] if len(sys.argv) > 2 else 'parsed_tables_output'
#         with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
#             html_content = f.read()
#         parsed = parse_scd_view_renderer_html(html_content)
#         print(f"解析到 {len(parsed)} 个模块、共 {sum(len(b.get('tables', [])) for b in parsed)} 个表格")
#         if parsed:
#             os.makedirs(out_dir, exist_ok=True)
#             export_parsed_tables_to_csv(parsed, out_dir)
#             # 同时导出 JSON 便于程序读取
#             json_path = os.path.join(out_dir, 'signal_chains', 'module_tables_parsed.json')
#             os.makedirs(os.path.dirname(json_path), exist_ok=True)
#             # 转为可序列化格式（保持 text/link）
#             with open(json_path, 'w', encoding='utf-8') as jf:
#                 json.dump(parsed, jf, ensure_ascii=False, indent=2)
#             print(f"CSV 与 JSON 已保存到: {out_dir}/signal_chains/")
#         sys.exit(0)
#
#     # 目标URL
#     #url="https://www.analog.com/cn/solutions/industrial-vision/3d-time-of-flight.html"
#     #url="https://www.analog.com/cn/solutions/industrial-automation/programmable-logic-controllers-plc-and-distributed-control-systems-dcs/analog-input-output-module.html"
#    # url="https://www.analog.com/cn/solutions/aerospace-and-defense/avionics/next-gen-weather-radar.html"
#     #url="https://www.analog.com/cn/solutions/industrial-automation/programmable-logic-controllers-plc-and-distributed-control-systems-dcs/analog-input-output-module.html"
#     #url="https://www.analog.com/cn/solutions/aerospace-and-defense/avionics/next-gen-weather-radar.html"
#     #url="https://www.analog.com/cn/solutions/industrial-automation/programmable-logic-controllers-plc-and-distributed-control-systems-dcs/analog-input-output-module.html"
#     #url="https://www.analog.com/cn/solutions/precision-technology/fast-precision.html"
#    # url="https://www.analog.com/cn/solutions/industrial-connectivity-technology/rs-485-can-solutions.html"
#    # url="https://www.analog.com/cn/solutions/precision-technology/ultra-precision.html"
#    # url="https://www.analog.com/cn/solutions/aerospace-and-defense/avionics/inflight-entertainment.html"
#     url="https://www.analog.com/cn/solutions/aerospace-and-defense/avionics/next-gen-weather-radar.html"
#     # 创建爬虫实例
#     scraper = EnhancedAnalogDevicesScraper(url)
#
#     # 运行爬虫
#     success = scraper.run()
#
#     if success:
#         print("\n✅ 爬取完成！所有数据已保存到 'analog_devices_data_new' 目录")
#         print("   特别注意:")
#         print("   1. 表格下方的图片已单独保存在 'table_images' 目录")
#         print("   2. 图片与表格的关联关系记录在 'table_images_list.csv'")
#         print("   3. 导航路径已保存到 'navigation.txt'")
#     else:
#         print("\n❌ 爬取失败，请检查网络连接或URL")
# 使用示例
if __name__ == "__main__":
    import sys
    import argparse

    # 创建参数解析器
    parser = argparse.ArgumentParser(description='Analog Devices 详细爬虫')
    parser.add_argument('--url', type=str, required=True, help='要爬取的URL')
    parser.add_argument('--output-dir', type=str, required=True, help='输出目录')
    parser.add_argument('--html-file', type=str, help='本地HTML文件路径（解析表格模式）')

    args = parser.parse_args()

    # 如果指定了 html-file，则使用解析表格模式
    if args.html_file:
        print(f"解析本地HTML文件: {args.html_file}")
        out_dir = args.output_dir if args.output_dir else 'parsed_tables_output'

        try:
            with open(args.html_file, 'r', encoding='utf-8', errors='replace') as f:
                html_content = f.read()

            parsed = parse_scd_view_renderer_html(html_content)
            print(f"解析到 {len(parsed)} 个模块、共 {sum(len(b.get('tables', [])) for b in parsed)} 个表格")

            if parsed:
                os.makedirs(out_dir, exist_ok=True)
                export_parsed_tables_to_csv(parsed, out_dir)

                # 同时导出 JSON 便于程序读取
                json_path = os.path.join(out_dir, 'signal_chains', 'module_tables_parsed.json')
                os.makedirs(os.path.dirname(json_path), exist_ok=True)

                # 转为可序列化格式（保持 text/link）
                with open(json_path, 'w', encoding='utf-8') as jf:
                    json.dump(parsed, jf, ensure_ascii=False, indent=2)

                print(f"CSV 与 JSON 已保存到: {out_dir}/signal_chains/")
        except Exception as e:
            print(f"解析HTML文件失败: {e}")
            sys.exit(1)

    else:
        # 完整的爬虫模式
        if not args.url:
            print("错误：必须提供 --url 参数")
            parser.print_help()
            sys.exit(1)

        print(f"开始爬取 URL: {args.url}")
        print(f"输出目录: {args.output_dir}")

        # 创建爬虫实例
        try:
            scraper = EnhancedAnalogDevicesScraper(args.url, args.output_dir)

            # 运行爬虫
            success = scraper.run()

            if success:
                print(f"\n 爬取完成！所有数据已保存到: {args.output_dir}")
                print("   特别注意:")
                print("   1. 表格下方的图片已单独保存在 'table_images' 目录")
                print("   2. 图片与表格的关联关系记录在 'table_images_list.csv'")
                print("   3. 导航路径已保存到 'navigation.txt'")
            else:
                print("\n 爬取失败，请检查网络连接或URL")
                sys.exit(1)

        except Exception as e:
            print(f"\n 爬虫运行异常: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)