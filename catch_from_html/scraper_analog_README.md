# Analog.com 高速精密解决方案页面爬虫

## 目标页面

https://www.analog.com/cn/solutions/precision-technology/fast-precision.html

## 功能

1. **导航（面包屑）**：主页 / 解决方案概要 / 精密技术解决方案 / 高速精密解决方案  
2. **正文**：页面中到「资源」之前的所有文字，保存为 `content_before_resources.txt`  
3. **表格**：如「密度优化」下的表格，保存为 `tables.json`（每表为 rows 数组）  
4. **图片**：表格下方及正文中的图片，下载到 `images/`，列表在 `images_list.json`  

## 反爬处理

- 先用 **requests + 浏览器头** 请求；若被拦（403 或内容明显不是正文），自动改用 **Selenium 无头 Chrome**。  
- 需要 Selenium 时请安装：`pip install selenium`，并保证本机有 Chrome/Chromium。  

## 依赖

```bash
pip install requests beautifulsoup4
# 若遇反爬再装
pip install selenium
```

## 运行

```bash
cd e:\fae_main
python scraper_analog_fast_precision.py
```

## 输出目录

默认输出到当前目录下的 `analog_fast_precision_output/`：

- `content_before_resources.txt`：到「资源」前的全部文字  
- `tables.json`：所有表格（每表一个 `rows` 数组）  
- `images/`：下载的图片  
- `images_list.json`：图片 URL、alt、本地路径  
- `summary.json`：本次抓取汇总  

## 若仍被反爬

1. 安装并配置 Selenium + Chrome，脚本会自动尝试。  
2. 在脚本中把 `USE_SELENIUM_FALLBACK = True` 保持为 True。  
3. 若使用代理，可在 `_get_html_requests` 里为 `s.get(...)` 增加 `proxies=...`。  
