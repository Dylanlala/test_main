import requests
from bs4 import BeautifulSoup
import time
import json
import os
from datetime import datetime

import re
import logger



# 要爬取的网址列表
urls = [
    #"https://www.analog.com/cn/products/adm2895e-1.html",
    #"https://www.analog.com/cn/products/adar4002.html"
    "https://www.analog.com/cn/products/ad2433w.html"
    # 可以添加更多网址
    # "https://www.analog.com/cn/products/adar4002.html"
]

# 设置请求头，模拟浏览器访问
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}


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


def scrape_adi_product_page(url):
    """爬取单个ADI产品页面"""
    print(f"\n正在抓取: {url}")

    try:
        # 发送HTTP GET请求
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # 检查请求是否成功
        response.encoding = 'utf-8'  # 设置编码

        # 使用BeautifulSoup解析HTML
        soup = BeautifulSoup(response.text, 'html.parser')

        # 提取产品标题 (通常位于h1标签)
        title_tag = soup.find('h1')
        product_title = title_tag.text.strip() if title_tag else "未找到标题"

        # 查找"概述"部分 (策略：寻找包含"概述"的标签，并获取其后的内容)
        overview = ""

        # 方法1：直接查找特性面板
        features_panel = soup.find('div', id='tab-panel-features')

        if features_panel:
            print("找到特性面板")

            # 获取所有列
            columns = features_panel.find_all('div', class_='col-md-6')

            if columns:
                print(f"找到 {len(columns)} 列")
                all_items = []

                for column in columns:
                    # 获取该列中的所有li
                    lis = column.find_all('li')
                    for li in lis:
                        text = li.text.strip()
                        if text and text not in all_items:
                            all_items.append(text)

                overview = ' | '.join(all_items)
            else:
                # 如果没有列，直接查找所有li
                lis = features_panel.find_all('li')
                all_items = [li.text.strip() for li in lis if li.text.strip()]
                overview = ' | '.join(all_items)
        else:
            # 方法2：如果没找到特性面板，使用原有方法查找概述
            for tag in soup.find_all(['h2']):
                if '概述' in tag.text:
                    print("找到概述标题")

                    # 查找最近的ul
                    ul_elem = tag.find_next('ul')
                    if ul_elem:
                        # 获取ul中的所有li
                        lis = ul_elem.find_all('li')
                        all_items = [li.text.strip() for li in lis if li.text.strip()]
                        overview = ' | '.join(all_items)
                    else:
                        # 如果没有ul，尝试其他元素
                        p_elem = tag.find_next('p')
                        li_elem = tag.find_next('li')
                        div_elem = tag.find_next('div')

                        if p_elem:
                            overview = p_elem.text.strip()
                        elif li_elem:
                            overview = li_elem.text.strip()
                        elif div_elem:
                            # 查找div中的所有li
                            lis = div_elem.find_all('li')
                            all_items = [li.text.strip() for li in lis if li.text.strip()]
                            overview = ' | '.join(all_items)

                    break

        # 打印结果摘要
        print(f"产品标题: {product_title}")
        print(f"概述长度: {len(overview)} 字符")
        print(f"前200字符: {overview[:200]}...")

        # 返回数据
        return {
            'url': url,
            'title': product_title,
            'overview': overview,
            'crawl_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    except requests.RequestException as e:
        print(f"请求出错: {e}")
        return None
    except Exception as e:
        print(f"解析过程出错: {e}")
        return None


def save_to_json(data, filename=None):
    """将数据保存为JSON文件"""
    if not data:
        print("没有数据可保存")
        return

    # 如果没有指定文件名，使用默认文件名
    if filename is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"adi_products_{timestamp}.json"

    try:
        # 确保目录存在
        os.makedirs('data', exist_ok=True)

        # 完整路径
        filepath = os.path.join('data', filename)

        # 保存为JSON格式，确保中文字符正确保存
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"\n数据已保存到: {filepath}")
        print(f"总计 {len(data)} 个产品数据")

        return filepath
    except Exception as e:
        print(f"保存JSON文件时出错: {e}")
        return None


def scrape_and_save_json(urls):
    """爬取所有URL并保存为JSON"""
    all_products_data = []

    print(f"开始爬取 {len(urls)} 个产品页面...")

    for i, url in enumerate(urls, 1):
        print(f"\n{'=' * 60}")
        print(f"进度: {i}/{len(urls)}")

        product_data = scrape_adi_product_page(url)
        if product_data:
            all_products_data.append(product_data)
            print(f"✓ 成功抓取: {product_data['title']}")
        else:
            print(f"✗ 抓取失败: {url}")

        # 礼貌延迟，避免对服务器造成压力
        if i < len(urls):
            time.sleep(2)

    print(f"\n{'=' * 60}")
    print(f"爬取完成！共成功抓取 {len(all_products_data)}/{len(urls)} 个产品页面")

    # 保存为JSON
    if all_products_data:
        save_to_json(all_products_data)
    else:
        print("没有成功抓取到任何数据")

    return all_products_data


# 优化版本：提取更详细的数据
def scrape_adi_detailed(url):
    """爬取ADI产品页面的详细信息"""
    print(f"\n正在抓取: {url}")

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response.encoding = 'utf-8'

        soup = BeautifulSoup(response.text, 'html.parser')

        # 提取产品标题
        title_tag = soup.find('h1')
        product_title = title_tag.text.strip() if title_tag else "未找到标题"

        # 查找特性面板
        features_panel = soup.find('div', id='tab-panel-features')

        features = []

        if features_panel:
            print("找到特性面板，提取内容...")

            # 查找所有列
            columns = features_panel.find_all('div', class_='col-md-6')

            if columns:
                for column in columns:
                    # 查找该列中的所有li
                    lis = column.find_all('li')
                    for li in lis:
                        text = li.text.strip()
                        if text and text not in features:
                            features.append(text)

        # 查找产品详情
        details_panel = soup.find('div', id='tab-panel-details')
        details = ""

        if details_panel:
            # 获取所有段落
            paragraphs = details_panel.find_all('p')
            detail_texts = [p.text.strip() for p in paragraphs if p.text.strip()]
            details = ' '.join(detail_texts)

        # 查找型号信息（如果存在）
        model_info = []
        model_section = soup.find(['div', 'section'], class_=lambda x: x and 'model' in str(x).lower())
        if model_section:
            models = model_section.find_all(['li', 'span', 'div'])
            for model in models:
                text = model.text.strip()
                if text and len(text) < 50:  # 假设型号不会太长
                    model_info.append(text)

        # 构造产品数据
        product_data = {
            'url': url,
            'title': product_title,
            'features': features,
            'details': details,
            'models': model_info if model_info else [],
            'features_count': len(features),
            'crawl_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        print(f"✓ 产品: {product_title}")
        print(f"  特性数量: {len(features)}")
        print(f"  详情长度: {len(details)} 字符")

        return product_data

    except Exception as e:
        print(f"出错: {e}")
        return None


def scrape_detailed_and_save(urls):
    """爬取详细信息并保存为JSON"""
    all_products = []

    print(f"开始详细爬取 {len(urls)} 个产品页面...")

    for i, url in enumerate(urls, 1):
        print(f"\n{'=' * 60}")
        print(f"进度: {i}/{len(urls)}")

        product_data = scrape_adi_detailed(url)
        if product_data:
            all_products.append(product_data)
            print(f"✓ 成功抓取: {product_data['title']}")
        else:
            print(f"✗ 抓取失败: {url}")

        # 礼貌延迟
        if i < len(urls):
            time.sleep(2)

    print(f"\n{'=' * 60}")
    print(f"详细爬取完成！共成功抓取 {len(all_products)}/{len(urls)} 个产品页面")

    # 保存为JSON
    if all_products:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"adi_products_detailed_{timestamp}.json"
        save_to_json(all_products, filename)

    return all_products


# 主函数
if __name__ == "__main__":
    print("ADI产品信息爬取工具")
    print("=" * 60)

    data = scrape_detailed_and_save(urls)
    extract_navigation_from_html(data)


    # 显示数据摘要
    if data:
        print("\n" + "=" * 60)
        print("数据摘要:")
        for i, product in enumerate(data, 1):
            print(f"\n{i}. {product['title']}")

            if 'overview' in product:
                overview = product['overview']
                if len(overview) > 150:
                    print(f"   概述: {overview[:150]}...")
                else:
                    print(f"   概述: {overview}")

            if 'features' in product:
                print(f"   特性数量: {product['features_count']}")

                # 显示前几个特性
                features = product['features']
                if features:
                    for j, feature in enumerate(features[:3], 1):
                        if len(feature) > 80:
                            print(f"     {j}. {feature[:80]}...")
                        else:
                            print(f"     {j}. {feature}")

                    if len(features) > 3:
                        print(f"     ... 还有 {len(features) - 3} 个特性")

        print("\n所有数据已保存为JSON格式，可用于大模型分析。")  