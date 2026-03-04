import copy
import os
import time
from collections.abc import Mapping
import concurrent.futures
import pandas as pd
from elasticsearch import Elasticsearch
from langchain.prompts import ChatPromptTemplate
from json_repair import repair_json
from itertools import groupby
import json
import re
import ast
from difflib import SequenceMatcher
import logging
from typing import List, Dict, Any, Optional, Tuple

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

json_pattern = r'```json(.*?)```'
with open("./all_categories.json", "r", encoding="utf-8") as f:
    all_categories = json.load(f)
categories = list(set(all_categories.values()))
base_model = "bot-20250618131857-l9ffp"
output_dir = "./result"

# 代理品牌信息 - 增强处理
cecport_agent = pd.read_csv("./cecport_agent_brand.csv", encoding="gbk")
cecport_agent = cecport_agent.fillna('')
agent_brands = [str(brand_id) for brand_id in cecport_agent['品牌ID'].tolist() if pd.notna(brand_id)]

# 创建品牌名称映射
brand_name_mapping = {}
for _, row in cecport_agent.iterrows():
    brand_id = str(row['品牌ID'])
    # brand_name = row['品牌中文名称'] if row['品牌中文名称'] else row['品牌英文名称']
    brand_name = row['品牌英文名称'] + '|' + row['品牌中文名称']
    if not brand_name:
        brand_name = f"品牌ID:{brand_id}"
    brand_name_mapping[brand_id] = brand_name

agent_brand_names = [name for name in brand_name_mapping.values() if name]
agent_brand_ids = []
for brand_id in agent_brands:
    try:
        agent_brand_ids.append(int(brand_id))
    except ValueError:
        logger.warning(f"Invalid brand ID: {brand_id}")
        continue

# 添加品牌别名映射
brand_alias_mapping = {
    'TI': 'Texas Instruments',
    'Texas Instruments': 'TI',
    'ST': 'STMicroelectronics',
    'STMicroelectronics': 'ST',
    'NXP': 'NXP Semiconductors',
    'NXP Semiconductors': 'NXP',
    'Infineon': 'Infineon Technologies',
    'Infineon Technologies': 'Infineon',
    # 添加更多品牌别名...
}


# 添加品牌-型号兼容性检查
def check_brand_model_compatibility(model: str, brand: str) -> bool:
    """检查型号与品牌的兼容性"""
    # 已知兼容规则
    compatibility_rules = {
        'STM32': ['ST', 'GD', 'Nuvoton', 'STMicroelectronics'],
        'ESP32': ['Espressif', 'WCH', 'GD', 'Espressif Systems'],
        'ATSAMD': ['Microchip', 'Atmel'],
        'NRF': ['Nordic', 'Nordic Semiconductor'],
        'LM': ['TI', 'Texas Instruments', 'National Semiconductor'],
        'TL': ['TI', 'Texas Instruments'],
        'MCP': ['Microchip'],
        'AT': ['Atmel', 'Microchip'],
        'MAX': ['Maxim', 'Analog Devices'],
        'LTC': ['Linear Technology', 'Analog Devices'],
        # 添加更多规则...
    }

    # 检查品牌别名
    brand_normalized = brand_alias_mapping.get(brand, brand)

    # 提取型号前缀
    model_prefix = re.match(r'^[A-Za-z]+', model).group() if re.match(r'^[A-Za-z]+', model) else ""

    if model_prefix in compatibility_rules:
        compatible_brands = compatibility_rules[model_prefix]
        # 检查品牌或其别名是否在兼容列表中
        return brand_normalized in compatible_brands or any(
            brand_alias_mapping.get(b, b) in compatible_brands for b in [brand, brand_normalized]
        )

    return True  # 未知型号默认兼容


def normalize_to_dict(obj) -> Dict:
    """
    把 dict / list[dict] / None / "" 统一成 dict
    """
    if isinstance(obj, Mapping):
        return dict(obj)
    if isinstance(obj, list):
        flat = {}
        for d in obj:
            if isinstance(d, Mapping):
                flat.update(d)
        return flat
    return {}


MAX_CANDIDATES = 1000


def extract_package(pack: str) -> str:
    # 按字母+数字顺序标准化
    if pack:
        letters = ''.join(re.findall(r'[A-Za-z]+', pack))
        numbers = ''.join(re.findall(r'\d+', pack))
        pack_std = letters + numbers
        return pack_std.upper()
    else:
        return ""


def extract_values_from_desc(desc: str) -> List[str]:
    pattern = r'(\d+(?:\.\d+)?[xX]?\d*(?:\.\d+)?[a-zA-ZμΩ°%]*\b)'
    matches = re.findall(pattern, desc)
    filtered_values = []
    for value in matches:
        if re.match(r'^\d{1,4}$', value):
            continue
        if value.lower() in ['v1', 'v2', 'v3', '2023', '2024', '2025']:
            continue
        filtered_values.append(value)
    return list(set(filtered_values))


def llm_extract_values_from_desc(desc: str, ds_chat, category: str = "") -> Dict:
    if not category:
        search_prompt = """
            # 你是一名电子元器件应用工程师。
            # 任务：根据用户提供的“型号 + 品牌 + 基础描述”，结合实时网络搜索，给出如下输出：
            1. 实时搜索官方资料与数据手册;
            2. 一段话总结该器件（≤ 50 字），重点是总结：元器件类别及典型应用。
            # 输入：
            ### {information} ###
            # 输出：
            直接输出器件总结，不输出搜索内容和推理过程！！！
        """
        search_template = ChatPromptTemplate.from_template(search_prompt)
        messages = search_template.format_messages(
            information=desc,
        )
        response = ds_chat.chat.completions.create(
            model=base_model,
            messages=[
                {"role": "user", "content": messages[0].content},
            ],
            stream=False,
            response_format="json",
            timeout=30
        )
        web_search = response.choices[0].message.content
        desc += "\n网络实时搜索结果\n" + web_search
    template = '''
        # 角色：你是一位经验丰富的电子工程师，擅长从自然语言中提取电子元器件的关键参数，生成可用于查询元器件替代的 JSON 格式数据。

        # 任务：
        1. 读取【categories】中分类名，结合网络搜索型号、品牌，并根据【information】描述的精确关键词匹配、功能描述吻合度提取出完整的分类，不可将【categories】中分类进行拆分组合。
        2. 提取元器件的封装类型、引脚数量，若存在则以 {{"封装":"完整封装名","封装类型": "提取的封装类型", "引脚数": "提取的引脚数"}} 形式返回，例如SOT-23 封装为’SOT-23‘，封装类型为’SOT‘，引脚数为’23‘, 注意引脚数和其他数字的区别。
        3. 提取不超过 3组(中英文为一组)元器件的关键词，只提取核心单词或词语(动/名词)，不提取描述形容词或参数数据，比如"N-Ch 40V Fast Switching MOSFETs"，提取格式：{{"关键词":["N-Ch","N沟道","Switching","开关"]}}
        4. 提取查找元器件替代时的前5个最关键电气属性参数, 提取的参数必须是用户输入【information】中准确出现的，不得提取网络搜索或推断的参数。
        5. 判断该类元器件的参数，寻找与参数相同或更好的元器件时，其参数条件"require"应该为大于还是小于该参数值，将require填入下面的字典。
        6. 将参数构建成字典，格式如下：
           ▪ {{'attrCnName': '参数名', 'attrValues': '参数值', 'nvs': [数值列表], 'attrUnit': '单位', "require": "条件"}}
           ▪ 示例：
             ▪ "阻抗 70 mΩ" → {{'attrCnName': '阻抗', 'attrValues': '70mΩ', 'nvs': [70], 'attrUnit': 'mΩ', "require": "小于等于"}}
             ▪ "电流 2 安" → {{'attrCnName': '电流', 'attrValues': '2A', 'nvs': [2], 'attrUnit': 'A', "require": "大于等于"}}
             ▪ "Marking Code Y1" → {{'attrCnName': 'Marking Code', 'attrValues': 'Y1', "require": "等于"}}
             ▪ "电压 2.7V~5V" → [{{'attrCnName': '最小电压', 'attrValues': '2.7V', 'nvs': [2.7], 'attrUnit': 'V', "require": "大于等于"}},{{'attrCnName': '最大电压', 'attrValues': '5V', 'nvs': [5], 'attrUnit': 'V', "require": "小于等于"}}]
        7. 将所有提取的参数放入 "description" 列表中，返回 JSON 格式数据。
        8. 将中文单位需转为英文，将单位转化为最常出现的最简单的单位形式。
        9. JSON 格式必须合法，键值对用双引号包裹。
        10. 不臆造参数，不重复提取，确保参数明确出现。

        # 输入：
        # - 【information】: 元器件的描述信息，为用户输入的自然语言及 ES 数据库中的JSON数据。
        ### {information} ###
        # - 【categories】：元器件分类的列表，不可将列表中分类进行拆分组合，必须保证完整性！
        ### {categories} ###

        # 输出示例：
        不需要输出推理过程，直接输出JSON结果！！！
        ```json
        {{
          "category": "匹配的分类名",
          "封装": "SOT-23", 
          "封装类型": "SOT", 
          "引脚数": "23",
          "关键词": ["N-Ch","N沟道","Fast Switching","快速开关"],
          "description": [
            {{'attrCnName': '最小电压', 'attrValues': '2.7V', 'nvs': [2.7], 'attrUnit': 'V', "require": "大于等于"}},{{'attrCnName': '最大电压', 'attrValues': '5V', 'nvs': [5], 'attrUnit': 'V', "require": "小于等于"}}
          ]
        }}
        ```
        # 注意:
        1. 提取的参数必须是用户输入【information】中准确出现的，不得将网络搜索或推断的参数进行提取！！！
        2. 输出的description中最多只能输出该类电子元器件最重要的5个参数,必须是小于等于5个！！！！
        3. 提取的内容严格遵循原文的技术参数表述格式，翻译成中文时采用中文电子元器件领域通用术语。
    '''
    if category:
        # category_list = [name for ids, name in all_categories.items() if category in ids]
        category_list = []
    else:
        category_list = categories

    prompt_template = ChatPromptTemplate.from_template(template)
    messages = prompt_template.format_messages(
        information=desc,
        categories=category_list
    )

    try:
        st = time.time()
        response = ds_chat.chat.completions.create(
            model=base_model,
            messages=[
                {"role": "user", "content": messages[0].content},
            ],
            stream=False,
            response_format="json",
            timeout=30
        )
        logger.info(f"LLM提取耗时: {time.time() - st:.2f}s")

        match = re.findall(json_pattern, response.choices[0].message.content, re.DOTALL)
        if match:
            json_str = match[0].strip()
            json_str = str(repair_json(json_str=json_str, return_objects=False))
            result_json = json.loads(json_str)
            return result_json
        else:
            # 尝试直接解析JSON
            try:
                json_str = str(repair_json(json_str=response.choices[0].message.content, return_objects=False))
                result_json = json.loads(json_str)
                return result_json
            except:
                logger.warning("LLM返回格式异常，无法提取JSON")
                return {}
    except Exception as e:
        logger.error(f"LLM提取失败: {e}")
        return {}


def search_data_rerank(desc: str, search_data: Dict, ds_chat) -> Dict:
    """使用LLM从标题中提取信息"""
    template = '''
       # 角色：电子元器件领域专家

        # 任务目标
        1.从方案数据库中检索与用户设计需求最匹配的方案，输出该方案的ID和完整描述（最多一个）。
        2.优先选择与用户设计需求明确要求型号方案的最匹配的方案。
        3.如果功能不同不能替换或无法确定是否存在匹配方案，必须返回空字典
        输出格式示例：{{'rerank':rerank}}

        # 输入参数
        1. 设计需求： ###{intention}###
        2. 方案数据库： ###{database}###
           数据结构：Python字典  
           ▪ Key：方案ID（int格式）  
           ▪ Value：方案描述（文本）  

        #输出格式
            结果按照下面json的格式输出,不需要其他推理信息！！
            ```json
             {{'rerank':{{
             "id": 方案ID, （int格式）
             "evaluate": 方案评价,评价语言需专业且符合电子元器件领域术语！
             "核心参数": 文本描述（原始参数与用户需求相关的参数）
            }}}}
            ```
        当无匹配方案时，必须输出：```json{{'rerank':{{}}}}```
    '''
    prompt_template = ChatPromptTemplate.from_template(template)
    messages = prompt_template.format_messages(intention=desc, database=search_data)

    try:
        st = time.time()
        response = ds_chat.chat.completions.create(
            model=base_model,
            messages=[
                {"role": "user", "content": messages[0].content},
            ],
            stream=False,
            response_format="json",
            timeout=30
        )
        logger.info(f"搜索重排耗时: {time.time() - st:.2f}s")

        with open(f'{output_dir}/search_data_rank_by_llm.txt', 'w') as f:
            f.write(response.choices[0].message.content)
        match = re.findall(json_pattern, response.choices[0].message.content, re.DOTALL)
        if match:
            json_str = match[0].strip()
            json_str = str(repair_json(json_str=json_str, return_objects=False))
            result_json = json.loads(json_str)
            return result_json.get('rerank', {})
        else:
            # 尝试直接解析JSON
            try:
                json_str = str(repair_json(json_str=response.choices[0].message.content, return_objects=False))
                result_json = json.loads(json_str)
                return result_json.get('rerank', {})
            except:
                logger.warning("搜索重排返回格式异常")
                return {}
    except Exception as e:
        logger.error(f"搜索重排失败: {e}")
        return {}


def replace_data_rerank(desc: str, search_data: Dict, ds_chat, title_std: str) -> List[Dict]:
    """使用LLM从标题中提取信息 - 优化版本，添加品牌优先级"""
    template = '''
        # 角色：电子元器件领域专家

        # 任务：
        1.从候选物料中选择最适合替代的3-5个方案
        2.优先选择'brandNameCn'字段值在代理品牌内：{agent_brands}
        3.考虑品牌-型号兼容性：{compatibility_rules}
        4.物料的封装信息可以忽略匹配，此替代不需要考虑封装信息及端子数量
        5.如果功能不同不能替换或实在没有匹配方案，返回空list

        # 输入：
        ▪ 需求：{intention}
        ▪ 候选物料database：{database}

        # 输出要求：
        1. 直接输出JSON，不要解释
        2. 选择3-5个最匹配的方案，优先选择代理品牌
        3. 每个方案包含id和简要评价
        4. 如果功能不同不能替换或实在没有匹配方案，必须严格输出{{'rerank':[]}}

        # 严格按照json格式输出：
        ```json
        {{'rerank':[{{
          "id": 方案ID(database中对应的key值),
          "evaluate": 匹配度评价（注明品牌优势）,
          "核心参数": "关键参数对比",
          "品牌优势": "代理品牌优先"
        }}]}}
        ```
    '''

    # 简化候选物料描述
    simplified_search_data = {}
    for idx, item in search_data.items():
        brand_id = item.get("brandId")
        is_agent_brand = brand_id in agent_brand_ids

        simplified_item = {
            "title": item.get("title", ""),
            "brand": item.get("brandNameCn", "") or item.get("brandName", ""),
            "category": item.get("xccCategoryName", ""),
            "packing": item.get("packing", ""),
            "key_params": str(item.get("attrInfo", []))[:200],
            "is_agent_brand": is_agent_brand  # 添加代理品牌标记
        }
        simplified_search_data[idx] = str(simplified_item)

    # 提取兼容性规则说明
    compatibility_rules = "STM32系列优先ST/GD/Nuvoton, ESP32系列优先Espressif/WCH/GD等"

    prompt_template = ChatPromptTemplate.from_template(template)
    messages = prompt_template.format_messages(
        intention=desc[:500],
        database=simplified_search_data,
        agent_brands=", ".join(agent_brand_names),
        compatibility_rules=compatibility_rules
    )

    try:
        st = time.time()
        response = ds_chat.chat.completions.create(
            model=base_model,
            messages=[
                {"role": "user", "content": messages[0].content},
            ],
            stream=False,
            timeout=30
        )
        logger.info(f"替代重排耗时: {time.time() - st:.2f}s")

        with open(f'{output_dir}/{title_std}_llm_rank.txt', 'w') as f:
            f.write(response.choices[0].message.content)

        match = re.findall(json_pattern, response.choices[0].message.content, re.DOTALL)
        if match:
            json_str = match[0].strip()
            json_str = str(repair_json(json_str=json_str, return_objects=False))
            result_json = json.loads(json_str)
            result_json = result_json.get('rerank', [])
            if result_json and isinstance(result_json, list) and len(result_json) > 0:
                return result_json[:3]
    except Exception as e:
        logger.error(f"LLM重排失败: {e}")
        # 失败时优先返回代理品牌
        agent_brand_items = []
        for i, item in enumerate(search_data.values()):
            if item.get("brandId") in agent_brand_ids:
                agent_brand_items.append(i)

        if agent_brand_items:
            return [{"id": i, "evaluate": "代理品牌优先", "核心参数": "参数匹配"}
                    for i in agent_brand_items[:3]]

        return [{"id": i, "evaluate": "备选方案", "核心参数": "参数匹配"}
                for i in range(min(3, len(search_data)))]

    return []


def process_candidates(data: List[Dict], package_std: str, description: str, ds_chat, replace: bool = False) -> Dict:
    """处理候选物料，进行封装过滤和重排序 - 优化品牌优先级"""
    # 优先选择代理品牌
    agent_brand_data = []
    other_brand_data = []

    for cand in data:
        if cand.get('brandId') in agent_brand_ids:
            agent_brand_data.append(cand)
        else:
            other_brand_data.append(cand)

    # 优先处理代理品牌数据
    if agent_brand_data:
        data = agent_brand_data
    else:
        data = other_brand_data

    rerank_json = {}
    for i, item in enumerate(data):
        rerank_json[i] = item

    with open(f"{output_dir}/filter_data_by_desc.json", "w", encoding="utf-8") as f:
        json.dump(rerank_json, f, indent=2, ensure_ascii=False)

    rerank_data = search_data_rerank(description, rerank_json, ds_chat)
    # 处理重排序结果
    if not rerank_data or "id" not in rerank_data:
        logger.warning("重排序未找到匹配结果，返回空结果")
        return {}

    rerank_id = int(rerank_data["id"])
    if rerank_id not in rerank_json:
        logger.warning(f"重排序ID {rerank_id} 不在候选列表中，返回空结果")
        return {}

    rerank_data["match_data"] = rerank_json[rerank_id]
    core_params = str(rerank_data.get('核心参数', '')).replace('{', '').replace('}', '')
    rerank_data["match_data"]['xcl核心参数'] = core_params

    return rerank_data


def get_title_info(es, index_name: str, title: str) -> Tuple[bool, List[Dict]]:
    title_infos = []
    # 是否精准匹配判断条件
    precise = True
    common_filter = []

    # title倒切割查询:
    max_cut = 5
    title_cand = copy.deepcopy(title)

    for i in range(min(max_cut, int(len(title) / 2))):
        # 精准匹配型号
        logger.info(f"型号【{title_cand}】查找中，倒排【{i}】字符")
        query_term = {
            "query": {
                "bool": {
                    "must": [
                        {"match": {"title.autocomplete": title_cand}},
                        {"term": {"showFlag": 1}},
                    ],
                    "filter": common_filter,
                }
            },
            "size": 25,
        }
        response = es.search(index=index_name, body=query_term)
        if response["hits"]["total"]["value"] > 0:
            break
        title_cand = title_cand[:-1]
    try:
        if response["hits"]["total"]["value"] <= 0:
            logger.info(f"title: {title} 模糊搜索中...")
            # 模糊匹配
            query_fallback = {
                "query": {
                    "bool": {
                        "must": [
                            {"match": {"title.short_char": title}},
                            {"term": {"showFlag": 1}}
                        ]
                    }
                },
                "size": 50
            }
            precise = False
            response = es.search(index=index_name, body=query_fallback)

        # 对结果进行排序，优先显示代理品牌的物料
        hits = response["hits"]["hits"]
        if agent_brand_ids:
            # 将代理品牌的物料排在前面
            hits.sort(key=lambda x: x["_source"].get("brandId", 0) in agent_brand_ids, reverse=True)

        for hit in hits:
            info = hit["_source"]
            try:
                attr_info = info.get("categoryAttrInfo", [])
                need_field = ["title", "xccCategoryId", "xccCategoryName", "brandId", "brandName", "brandNameCn",
                              "description", "packing", "pdfUrl", 'xccCategoryIds', 'series']
                res = {key: info[key] for key in need_field if key in info}
                if not res.get("brandNameCn", ""):
                    res["brandNameCn"] = res.get("brandName", "")
                category_ids = info.get('xccCategoryIds', [])
                category_names = info.get('xccCategoryNames', [])
                if category_ids and len(category_ids) >= 2:
                    res["secondCategoryId"] = info.get('xccCategoryIds')[1]
                if category_names:
                    res["xccCategoryNames"] = "||".join(category_names)
                param_data = json.loads(info.get("paramJson", "")) if info.get("paramJson", "") else {}
                officialJson = json.loads(info.get("officialJson", "")) if info.get("officialJson", "") else {}
                param_json = normalize_to_dict(param_data) | normalize_to_dict(officialJson)
                res["attrInfo"] = []
                if attr_info:
                    attr_info = [
                        {key: value for key, value in attr.items() if
                         key in ["attrCnName", "attrValues", 'nvs', 'attrUnit']}
                        for attr in attr_info if attr.get("attrValues")]
                    attr_info = [attr for attr in attr_info if
                                 not bool(re.search(r'[\u4e00-\u9fff]', attr.get("attrValues", "")))]
                    res["attrInfo"] += attr_info
                if param_json:
                    attr = []
                    attr_values = [attr.get("attrValues") for attr in attr_info]
                    param_values = {key: str(value) for key, value in param_json.items() if
                                    str(value) != "" and str(value) not in attr_values}
                    for param, value in param_values.items():
                        if not bool(re.search(r'[\u4e00-\u9fff]', value)):
                            attr.append({"attrCnName": param, "attrValues": value})
                    res["attrInfo"] += attr
                title_infos.append(res)
            except Exception as e:
                logger.warning(f"物料{info['title']} 格式失败，已跳过。{e}")
                continue
    except Exception as e:
        logger.error(f"ES查询失败: {e}")
        return precise, []

    groups = {}
    for item in title_infos:
        key = (item['title'], item['brandId'])
        # 如果 key 不存在或当前 attrInfo 更长，就替换
        if key not in groups or len(item['attrInfo']) > len(groups[key]['attrInfo']):
            groups[key] = item

    filter_data = list(groups.values())

    return precise, filter_data


def build_dynamic_query(query_data, category_ids, package, packet_set, keywords=[],
                        replace: bool = False) -> Dict:
    if not isinstance(category_ids, list):
        category_ids = [category_ids]
    common_filter = [
        {"terms": {"xccCategoryIds": category_ids}},
        {"term": {"showFlag": 1}}
    ]
    if replace and agent_brands:
        common_filter.append({"terms": {"brandId": agent_brand_ids}})

    query = {
        "query": {
            "bool": {
                "filter": common_filter,
                "should": [],
                "minimum_should_match": 1
            }
        },
        "size": 50,
        "track_total_hits": False
    }

    # 添加代理品牌优先级
    if not replace and agent_brand_ids:
        # query["query"]["bool"]["should"].append({
        #     "terms": {"brandId": agent_brand_ids}
        # })
        query["query"]["bool"]["should"].append({
            "constant_score": {
                "filter": {
                    "terms": {"brandId": agent_brand_ids}
                },
                "boost": 5
            }
        })

    # 添加关键词查找优先:
    if keywords:
        kw_query = {
            "constant_score": {
                "filter": {
                    "multi_match": {
                        "query": " ".join(keywords),
                        "fields": ["description", "paramJson"],
                        "operator": "or"
                    }
                },
                "boost": 6
            }
        }
        query["query"]["bool"]["should"].append(kw_query)

    value_query = {
        "nested": {
            "path": "categoryAttrInfo",
            "query": {
                "bool": {
                    "should": [],
                    "minimum_should_match": 1
                }
            }
        }
    }

    for condition in query_data:
        require = condition['require']
        attr_value = condition['attrValues'].strip().replace(" ", "").lower()
        nvs_values = condition.get('nvs', [])
        unit = condition.get('attrUnit', "")
        # 值查询
        value_format = [
            f"{nvs}{sep}{unit}".lower()
            for nvs in nvs_values
            for sep in [" ", ""]  # 分别生成有空格和无空格的格式
            if nvs_values and unit
        ]
        value_format.append(attr_value)
        value_format = list(set(value_format))
        conditions = {
            "terms": {
                "categoryAttrInfo.attrValues.ignoreCaseField": value_format
            }
        }
        value_query["nested"]["query"]["bool"]["should"].append(conditions)
        # params查询, officialJson不作为索引，无法查找:
        params_query = {
            "constant_score": {
                "filter": {
                    "multi_match": {
                        "query": attr_value,
                        "fields": ["description", "paramJson"],
                        "type": "phrase"
                    }
                },
                "boost": 3
            }
        }
        query["query"]["bool"]["should"].append(params_query)
        if require in ['大于等于', '小于等于']:
            nested_query = None
            operator = "gte" if require == '大于等于' else "lte"
            if unit and nvs_values:
                unit_condition = {
                    "term": {
                        "categoryAttrInfo.attrUnit": f"{unit}"
                    }
                }
                range_conditions = {
                    "range": {
                        "categoryAttrInfo.nvs": {
                            operator: nvs_values[0]
                        }
                    }
                }
                nested_query = {
                    "constant_score": {
                        "filter": {
                            "bool": {
                                "must": [unit_condition, range_conditions],
                            }
                        },
                        "boost": 5
                    }
                }
            if nested_query:
                value_query["nested"]["query"]["bool"]["should"].append(nested_query)
    query["query"]["bool"]["should"].append(value_query)
    return query


def search_by_desc(es, index: str, query: Dict) -> List[Dict]:
    st = time.time()
    try:
        response = es.search(index=index, body=query)
        search_data = []
        hits_data = response["hits"]["hits"]

        # 对结果进行排序，优先显示代理品牌的物料
        if agent_brand_ids:
            hits_data.sort(key=lambda x: x["_source"].get("brandId", 0) in agent_brand_ids, reverse=True)

        if hits_data:
            for hit in hits_data:
                info = hit["_source"]
                try:
                    attr_info = info.get("categoryAttrInfo", [])
                    need_field = ["title", "xccCategoryId", "xccCategoryName", "brandId", "brandName", "brandNameCn",
                                  "description", "packing", "pdfUrl"]
                    res = {key: info[key] for key in need_field if key in info}
                    if not res.get("brandNameCn", ""):
                        res["brandNameCn"] = res.get("brandName", "")
                    category_ids = info.get('xccCategoryIds', [])
                    if category_ids and len(category_ids) >= 2:
                        res["secondCategoryId"] = info.get('xccCategoryIds')[1]
                    param_data = json.loads(info.get("paramJson", "")) if info.get("paramJson", "") else {}
                    officialJson = json.loads(info.get("officialJson", "")) if info.get("officialJson", "") else {}
                    param_json = normalize_to_dict(param_data) | normalize_to_dict(officialJson)
                    res["attrInfo"] = []
                    if attr_info:
                        attr_info = [
                            {key: value for key, value in attr.items() if
                             key in ["attrCnName", "attrValues", 'nvs', 'attrUnit']}
                            for attr in attr_info]
                        attr_info = [attr for attr in attr_info if
                                     not bool(re.search(r'[\u4e00-\u9fff]', str(attr.get("attrValues"))))]
                        res["attrInfo"] += attr_info
                    if param_json:
                        attr = []
                        attr_values = [attr.get("attrValues") for attr in attr_info]
                        param_values = {key: str(value).strip() for key, value in param_json.items() if
                                        value != "" and value not in attr_values}
                        for param, value in param_values.items():
                            if not bool(re.search(r'[\u4e00-\u9fff]', value)):
                                attr.append({"attrCnName": param, "attrValues": value})
                        res["attrInfo"] += attr
                    search_data.append(res)
                except Exception as e:
                    logger.warning(f"替代料{info['title']} 格式失败，已跳过。{e}")
                    continue
        logger.info(f"描述搜索耗时: {time.time() - st:.2f}s")
        return search_data
    except Exception as e:
        logger.error(f"描述搜索失败: {e}")
        return []


def get_title_replaces(title: str, package: str = "", category_id: str = "", desc: str = "", ds_chat="",
                       searched: bool = False, auto_replace: bool = False) -> Tuple[bool, List[Dict]]:
    index_name = ["xcc_ware_detail"]
    es = Elasticsearch(
        [
            "http://10.10.40.103:9200  ",
            "http://10.10.40.104:9200  ",
            "http://10.10.40.105:9200  ",
            "http://10.10.40.138:9200  ",
            "http://10.10.40.139:9200  ",
            "http://10.10.40.140:9200  ",
            "http://10.10.40.169:9200  ",
            "http://10.10.40.170:9200  ",
            "http://10.10.40.179:9200  "
        ],
        timeout=100,
        http_auth=("App-FAE", "97zQUZQCy4NcYrJ3nS"),
    )
    if not es.ping():
        es.close()
        logger.error("数据库连接失败，请联系工程师确认！")
        return False, []
    try:
        original_info = desc
        if not searched:
            if title:
                title = title.upper()
                match_flag, title_infos = get_title_info(es, index_name, title)
                if title_infos and match_flag:
                    # 优先选择代理品牌的物料
                    agent_brand_items = [item for item in title_infos if item.get("brandId") in agent_brand_ids]
                    if agent_brand_items:
                        best_match = max(agent_brand_items, key=lambda d: len(d.get('attrInfo', [])))
                    else:
                        best_match = max(title_infos, key=lambda d: len(d.get('attrInfo', [])))

                    if not category_id:
                        category_id = best_match.get("secondCategoryId", "")
                    category_names = best_match.get("xccCategoryNames", "")
                    es_desc = best_match.get("description", "")
                    package = best_match.get("packing", "")
                    brand_name = best_match.get("brandName", "") + best_match.get("brandNameCn", "")
                    best_desc = str(
                        {attr.get("attrCnName"): attr.get("attrValues") for attr in
                         best_match.get('attrInfo', [])})
                    original_info += f"\n型号:{title},品牌:{brand_name},分类:{category_names}\n数据库描述:\n" + es_desc + f"\n产品封装:{package}\n数据库核心参数:\n" + best_desc
                else:
                    return match_flag, title_infos

        title_std = re.sub(r'[^a-zA-Z0-9]', '', title)
        with open(f'{output_dir}/{title_std}_desc_composed.txt', 'w') as f:
            f.write(original_info)

        llm_result = llm_extract_values_from_desc(original_info, ds_chat, category_id)
        with open(f'{output_dir}/{title_std}_llm_extracted.json', 'w') as f:
            json.dump(llm_result, f, indent=2, ensure_ascii=False)

        package_std = (llm_result.get("封装类型", "").upper(), llm_result.get("引脚数", ""))
        desc_data = llm_result.get("description", [])
        keyword_desc = llm_result.get("关键词", [])
        if not category_id:
            llm_category = llm_result.get("category", "")
            category_id_search = [key for key, value in all_categories.items() if value == llm_category]
            # 如果查找不到，category_id
            if not category_id_search:
                top_ctg = llm_category.split("||")[0]
                category_id_search = [key for key, value in all_categories.items() if top_ctg in llm_category]

            category_id = [ctg_ids.split("||")[1] for ctg_ids in category_id_search]

        query = build_dynamic_query(desc_data, category_id, package, package_std, keywords=keyword_desc,
                                    replace=auto_replace)
        with open(f'{output_dir}/{title_std}_dynamic_query.json', 'w') as f:
            json.dump(query, f, indent=2, ensure_ascii=False)

        search_data = search_by_desc(es, index_name, query)
        if search_data:
            final_data = replace_process_candidates(
                [data for data in search_data if data["title"] != title],
                title_std,
                original_info,
                ds_chat
            )
            with open(f"{output_dir}/{title_std}_replace_data.json", "w", encoding="utf-8") as f:
                json.dump(final_data, f, indent=2, ensure_ascii=False)
            return True, final_data
    except Exception as e:
        logger.error(f"{title} 查找替代料失败：{e}")

    return False, []


def replace_process_candidates(data: List[Dict], title_std: str, description: str, ds_chat) -> List[Dict]:
    """处理替代料候选 - 优化版本"""
    # 同物料号/品牌保留参数最多的
    groups = {}
    for item in data:
        key = (item['title'], item['brandId'])
        # 如果 key 不存在或当前 attrInfo 更长，就替换
        if key not in groups or len(item['attrInfo']) > len(groups[key]['attrInfo']):
            groups[key] = item

    filter_data = list(groups.values())
    # 优先选择代理品牌
    agent_brand_data = []
    other_brand_data = []

    for cand in filter_data:
        if cand.get('brandId') in agent_brand_ids:
            agent_brand_data.append(cand)
        else:
            other_brand_data.append(cand)

    # 优先处理代理品牌数据
    if agent_brand_data:
        data = agent_brand_data
    else:
        data = other_brand_data

    rerank_json = {}
    for i, item in enumerate(data):
        rerank_json[i] = item

    with open(f"{output_dir}/{title_std}_replace_filter_data.json", "w", encoding="utf-8") as f:
        json.dump(rerank_json, f, indent=2, ensure_ascii=False)

    rerank_data = replace_data_rerank(description, rerank_json, ds_chat, title_std)

    final_results = []
    for item in rerank_data:
        item_id = item.get("id", 0)
        if item_id in rerank_json:
            final_results.append({
                "id": item_id,
                "evaluate": item.get("evaluate", ""),
                "核心参数": item.get("核心参数", ""),
                "replace_data": rerank_json[item_id]
            })

    return final_results


def sort_by_completeness(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    将ES查询的条目按信息完整度排序（attrInfo 条数也加权）
    规则：
      1. 14 个主字段各 1 分
      2. attrInfo 每多 1 条额外 +1 分
    """

    def score(item: Dict[str, Any]) -> int:
        s = 0
        # 字符串字段
        for k in ['title', 'xccCategoryName', 'brandName', 'brandNameCn', "secondCategoryId",
                  'description', 'packing', 'pdfUrl', 'series', 'xccCategoryNames']:
            if item.get(k, '').strip():
                s += 1
        # brandId
        if item.get('brandId'):
            s += 1
        if item.get('xccCategoryId'):
            s += 1
        # 数组字段
        if item.get('xccCategoryIds') and any(item['xccCategoryIds']):
            s += 1
        # attrInfo：先算存在分，再算条数分
        ai = item.get('attrInfo') or []
        if ai:
            s += 1 + len(ai)
        return s

    return sorted(data, key=score, reverse=True)


def get_alternate_materials(title: str = "", description: str = '', output: str = '', ds_chat='', design_intention='',
                            replace: bool = False,
                            auto_replace: bool = False) -> Dict:
    global output_dir
    if output:
        output_dir = output
    logger.info(f"---------型号：{title}搜索中----------")
    start_time = time.time()
    index_name = ["xcc_ware_detail"]
    es = Elasticsearch(
        [
            "http://10.10.40.103:9200  ",
            "http://10.10.40.104:9200  ",
            "http://10.10.40.105:9200  ",
            "http://10.10.40.138:9200  ",
            "http://10.10.40.139:9200  ",
            "http://10.10.40.140:9200  ",
            "http://10.10.40.169:9200  ",
            "http://10.10.40.170:9200  ",
            "http://10.10.40.179:9200  "
        ],
        timeout=100,
        http_auth=("App-FAE", "97zQUZQCy4NcYrJ3nS"),
    )
    if not es.ping():
        es.close()
        logger.error("数据库连接失败，请联系工程师确认！")
        return {"error": "数据库连接失败，请联系工程师确认！"}

    # 品牌优先级评分函数
    def calculate_brand_score(item):
        brand_id = item.get("brandId")
        # 代理品牌获得最高分
        if brand_id in agent_brand_ids:
            return 100
        # 其他品牌根据匹配度评分
        return 0

    category_ids = set()
    package_es = ""
    final_data = []
    # ============== 阶段1: 完全title匹配 ==============
    if title:
        title = title.upper()
        match_flag, title_infos = get_title_info(es, index_name, title)
        title_std = re.sub(r'[^a-zA-Z0-9]', '', title)
        with open(f"{output_dir}/{title_std}_es_data.json", "w", encoding="utf-8") as f:
            json.dump(title_infos, f, indent=2, ensure_ascii=False)
        logger.info(f"Title查询耗时: {time.time() - start_time:.2f}s")
        # original_info = description
        # category_id = ""

        # 1.1 完全匹配成功 -> 直接返回
        if title_infos and match_flag:
            # 对结果按品牌优先级排序
            scored_infos = []
            for item in title_infos:
                score = calculate_brand_score(item)
                scored_infos.append((score, item))
            scored_infos.sort(key=lambda x: x[0], reverse=True)
            title_infos = [item for score, item in scored_infos]

            # 优先选择代理品牌的物料
            agent_brand_items = [item for item in title_infos if item.get("brandId") in agent_brand_ids]
            if agent_brand_items:
                best_match = sort_by_completeness(agent_brand_items)[0]
            else:
                best_match = sort_by_completeness(title_infos)[0]
            # category_id = best_match.get("secondCategoryId", "")
            category_id = best_match.get("xccCategoryId", "")
            category_names = best_match.get("xccCategoryNames", "")
            es_desc = best_match.get("description", "")

            package = best_match.get("packing", "")
            brand_name = best_match.get("brandName", "") + best_match.get("brandNameCn", "")
            best_desc = str(
                {attr.get("attrCnName"): attr.get("attrValues") for attr in
                 best_match.get('attrInfo', [])})
            # 将用户输入的description放在前面，优先考虑desc中的参数
            original_info = description + f"\n型号:{title},品牌:{brand_name},分类:{category_names} \n数据库描述:" + es_desc + f"\n产品封装:{package}\n数据库核心参数:\n" + best_desc

            # 检查是否需要自动替换（auto_replace=True 且当前物料不在代理品牌中）
            should_auto_replace = auto_replace and best_match.get("brandId") not in agent_brand_ids

            # 根据replace参数或自动替换条件决定是否进行替换搜索
            should_replace = replace or should_auto_replace

            # 初始化替换数据
            replace_data = []
            evaluate = "型号完全匹配"
            original_best_match = best_match.copy()  # 保存原始匹配结果

            if should_replace:
                replace_flag, replace_data = get_title_replaces(title, package, category_id, original_info, ds_chat,
                                                                searched=True, auto_replace=should_auto_replace)

                # 如果自动替换开启且找到了替代料，则用最佳替代料替换匹配结果
                if should_auto_replace and replace_data:
                    # 取第一个替代料作为最佳匹配
                    best_replace = replace_data[0]["replace_data"]
                    # 确保包含brandId和pdfUrl字段
                    best_match = best_replace
                    best_match['xcl核心参数'] = replace_data[0].get("核心参数", "").replace('{', '').replace('}', '')
                    best_match['is_auto_replaced'] = True  # 标记为自动替换
                    best_match['original_title'] = title  # 保留原始型号

                    # 更新评价信息
                    evaluate = f"自动替换: {replace_data[0].get('evaluate', '')}"
                # 如果自动替换开启但没有找到替代料，则回退到原始匹配结果
                elif should_auto_replace and not replace_data:
                    best_match = original_best_match  # 回退到原始匹配结果
                    evaluate = "型号完全匹配（自动替换未找到合适替代）"
                    # 清空替换数据，因为自动替换没有找到合适的替代
                    replace_data = []

            # 确保match_data包含xcl核心参数字段
            best_desc = str(
                {attr.get("attrCnName"): attr.get("attrValues") for attr in best_match.get('attrInfo', [])}).replace(
                '{', '').replace('}', '')
            if not best_desc:
                best_desc = best_match.get("description", "")
                if not best_desc:
                    best_desc = description
            best_match['xcl核心参数'] = best_desc

            rm_replace_data, rdnames = [], []
            for rd in replace_data:
                if rd["replace_data"]["title"] not in rdnames:
                    rm_replace_data.append(rd)
                    rdnames.append(rd["replace_data"]["title"])

            # 检查品牌-型号兼容性
            model = title
            brand = best_match.get("brandName", "") or best_match.get("brandNameCn", "")
            if brand and not check_brand_model_compatibility(model, brand):
                evaluate += " (注意: 品牌-型号可能存在兼容性问题)"

            final_json = {
                "id": 0,
                "source": "title_exact_match",
                "match_data": best_match,
                "replace_data": rm_replace_data,  # 自动替换时不再显示其他替代料
                "evaluate": evaluate
            }

            with open(f"{output_dir}/{title_std}_final_data.json", "w", encoding="utf-8") as f:
                json.dump(final_json, f, indent=2, ensure_ascii=False)
            return final_json

    # ============== 阶段2: title前缀匹配 + des精排 ==============
    if title and title_infos:  # 前缀匹配存在候选
        logger.info("方案二，候选物料精排...")
        try:
            # 对结果按品牌优先级排序
            scored_infos = []
            for item in title_infos:
                score = calculate_brand_score(item)
                scored_infos.append((score, item))
            scored_infos.sort(key=lambda x: x[0], reverse=True)
            title_infos = [item for score, item in scored_infos]

            # 2.1 构建精排候选集 {索引: 物料描述}
            rerank_json = {
                idx: f"型号: {item['title']}; 品牌:{item.get('brandName', '') + item.get('brandNameCn', '')}, 元器件分类: {item.get('xccCategoryNames', '')},描述: {item.get('description', '')}"
                for idx, item in enumerate(title_infos)}
            intention = design_intention + "\n" + f"其中一个零件选型方案: {title}。{description}"
            # 2.2 用LLM对候选集+描述进行精排
            rerank_data = search_data_rerank(intention, rerank_json, ds_chat)
            rerank_id = rerank_data.get("id", "")
            if str(rerank_id):
                rerank_id = int(rerank_id)
                matched_data = title_infos[rerank_id]
                matched_title = matched_data.get("title")
                # 构建original_info，优先考虑desc中的参数
                es_desc = matched_data.get("description", "")
                category_names = matched_data.get("xccCategoryNames", "")
                package = matched_data.get("packing", "")
                brand_name = matched_data.get("brandName", "") + matched_data.get("brandNameCn", "")
                best_desc = str(
                    {attr.get("attrCnName"): attr.get("attrValues") for attr in matched_data.get('attrInfo', [])})
                original_info = description + f"\n型号:{matched_title},品牌:{brand_name},分类:{category_names}\n数据库描述:\n" + es_desc + f"\n产品封装:{package}\n数据库核心参数:\n" + best_desc

                # 检查是否需要自动替换（auto_replace=True 且当前物料不在代理品牌中）
                should_auto_replace = auto_replace and matched_data.get("brandId") not in agent_brand_ids

                # 根据replace参数或自动替换条件决定是否进行替换搜索
                should_replace = replace or should_auto_replace
                # 初始化替换数据
                replace_data = []
                evaluate = rerank_data["evaluate"]
                original_matched_data = matched_data.copy()  # 保存原始匹配结果

                if should_replace:
                    replace_flag, replace_data = get_title_replaces(matched_title, package,
                                                                    matched_data.get("secondCategoryId", ""),
                                                                    original_info, ds_chat, searched=True,
                                                                    auto_replace=should_auto_replace)

                    # 如果自动替换开启且找到了替代料，则用最佳替代料替换匹配结果
                    if should_auto_replace and replace_data:
                        # 取第一个替代料作为最佳匹配
                        best_replace = replace_data[0]["replace_data"]
                        # 确保包含brandId和pdfUrl字段
                        matched_data = best_replace
                        matched_data['xcl核心参数'] = replace_data[0].get("核心参数", "").replace('{', '').replace('}',
                                                                                                                   '')
                        matched_data['is_auto_replaced'] = True  # 标记为自动替换
                        matched_data['original_title'] = title  # 保留原始型号

                        # 更新评价信息
                        evaluate = f"自动替换: {replace_data[0].get('evaluate', '')}"
                    # 如果自动替换开启但没有找到替代料，则回退到原始匹配结果
                    elif should_auto_replace and not replace_data:
                        matched_data = original_matched_data  # 回退到原始匹配结果
                        evaluate = f"{rerank_data['evaluate']}（自动替换未找到合适替代）"
                        # 清空替换数据，因为自动替换没有找到合适的替代
                        replace_data = []

                # 确保match_data包含xcl核心参数字段
                matched_data['xcl核心参数'] = str(rerank_data.get('核心参数', '')).replace('{', '').replace('}', '')

                # 检查品牌-型号兼容性
                model = matched_title
                brand = matched_data.get("brandName", "") or matched_data.get("brandNameCn", "")
                if brand and not check_brand_model_compatibility(model, brand):
                    evaluate += " (注意: 品牌-型号可能存在兼容性问题)"

                rm_replace_data, rdnames = [], []
                for rd in replace_data:
                    if rd["replace_data"]["title"] not in rdnames:
                        rm_replace_data.append(rd)
                        rdnames.append(rd["replace_data"]["title"])
                final_json = {
                    "id": rerank_id,
                    "source": "title_prefix_rerank",
                    "match_data": matched_data,
                    "replace_data": rm_replace_data,  # 自动替换时不再显示其他替代料
                    "evaluate": evaluate
                }
                with open(f"{output_dir}/{title_std}_final_data.json", "w", encoding="utf-8") as f:
                    json.dump(final_json, f, indent=2, ensure_ascii=False)
                return final_json
        except Exception as e:
            logger.error("title 无法找到匹配数据, 或报错", e)

    # 如果没有找到匹配的物料，尝试基于描述的参数化搜索
    if description:
        # 使用LLM提取参数
        logger.info("方案三，根据描述查找替代物料中...")
        llm_res = llm_extract_values_from_desc(description, ds_chat)
        if llm_res and "category" in llm_res:
            category_name = llm_res.get("category", "")
            # 查找分类ID

            category_id_search = ''.join(
                [key for key, value in all_categories.items() if value == category_name])
            if category_id_search:
                category_id = category_id_search.split("||")[1]
                if llm_res.get("封装类型", ""):
                    package_std = (llm_res.get("封装类型", "").upper(), llm_res.get("引脚数", ""))
                else:
                    package_std = ('', '')
                if llm_res.get("封装", ""):
                    package = llm_res.get("封装", "").upper()
                else:
                    package = ''
                desc_data = llm_res.get("description", [])
                keyword_desc = llm_res.get("关键词", [])
                # 构建查询 - 优先考虑desc中的参数
                query = build_dynamic_query(desc_data, category_id, package, package_std, keywords=keyword_desc,
                                            replace=replace or auto_replace)
                with open(f'{output_dir}/{title_std}_dynamic_query.json', 'w') as f:
                    json.dump(query, f, indent=2, ensure_ascii=False)
                search_data = search_by_desc(es, index_name, query)

                # 对搜索结果按品牌优先级排序
                scored_data = []
                for item in search_data:
                    score = calculate_brand_score(item)
                    scored_data.append((score, item))
                scored_data.sort(key=lambda x: x[0], reverse=True)
                search_data = [item for score, item in scored_data]

                # 结果精排处理
                if search_data:
                    final_data = process_candidates(
                        [data for data in search_data if data["title"] != title],
                        extract_package(package),
                        description,
                        ds_chat,
                        replace or auto_replace
                    )
                    if final_data:
                        matched_title = final_data["match_data"].get("title")

                        # 检查是否需要自动替换（auto_replace=True 且当前物料不在代理品牌中）
                        should_auto_replace = auto_replace and final_data["match_data"].get(
                            "brandId") not in agent_brand_ids

                        # 根据replace参数或自动替换条件决定是否进行替换搜索
                        should_replace = replace or should_auto_replace

                        # 初始化替换数据
                        replace_data = []
                        evaluate = final_data["evaluate"]
                        original_final_data = final_data.copy()  # 保存原始匹配结果

                        if should_replace:
                            # 构建original_info，优先考虑desc中的参数
                            es_desc = final_data["match_data"].get("description", "")
                            package = final_data["match_data"].get("packing", "")
                            brand_name = final_data["match_data"].get("brandName", "") + final_data["match_data"].get(
                                "brandNameCn", "")
                            best_desc = str({attr.get("attrCnName"): attr.get("attrValues") for attr in
                                             final_data["match_data"].get('attrInfo', [])})
                            original_info = description + f"\n型号:{matched_title},品牌:{brand_name} 数据库描述:\n" + es_desc + f"\n产品封装:{package}\n数据库核心参数:\n" + best_desc

                            replace_flag, replace_data = get_title_replaces(matched_title, package,
                                                                            final_data["match_data"].get(
                                                                                "secondCategoryId",
                                                                                ""), original_info,
                                                                            ds_chat, searched=True,
                                                                            auto_replace=should_auto_replace)

                            # 如果自动替换开启且找到了替代料，则用最佳替代料替换匹配结果
                            if should_auto_replace and replace_data:
                                # 取第一个替代料作为最佳匹配
                                best_replace = replace_data[0]["replace_data"]
                                # 确保包含brandId和pdfUrl字段
                                final_data["match_data"] = best_replace
                                final_data["match_data"]['xcl核心参数'] = replace_data[0].get("核心参数", "").replace(
                                    '{',
                                    '').replace(
                                    '}', '')
                                final_data["match_data"]['is_auto_replaced'] = True  # 标记为自动替换
                                final_data["match_data"]['original_title'] = title  # 保留原始型号

                                # 更新评价信息
                                final_data["evaluate"] = f"自动替换: {replace_data[0].get('evaluate', '')}"
                            # 如果自动替换开启但没有找到替代料，则回退到原始匹配结果
                            elif should_auto_replace and not replace_data:
                                final_data = original_final_data  # 回退到原始匹配结果
                                final_data["evaluate"] = f"{evaluate}（自动替换未找到合适替代）"
                                # 清空替换数据，因为自动替换没有找到合适的替代
                                replace_data = []

                        # 检查品牌-型号兼容性
                        model = matched_title
                        brand = final_data["match_data"].get("brandName", "") or final_data["match_data"].get(
                            "brandNameCn",
                            "")
                        if brand and not check_brand_model_compatibility(model, brand):
                            final_data["evaluate"] += " (注意: 品牌-型号可能存在兼容性问题)"

                        rm_replace_data, rdnames = [], []
                        for rd in replace_data:
                            if rd["replace_data"]["title"] not in rdnames:
                                rm_replace_data.append(rd)
                                rdnames.append(rd["replace_data"]["title"])
                        final_data["replace_data"] = rm_replace_data  # 自动替换时不再显示其他替代料
                        final_data["source"] = "description_search"
                        with open(f"{output_dir}/{title_std}_final_data.json", "w", encoding="utf-8") as f:
                            json.dump(final_data, f, indent=2, ensure_ascii=False)
                        return final_data
    return {
        "id": -1,
        "source": "element_miss_searched",
        "match_data": {},
        "replace_data": [],
        "evaluate": "元器件及相关替代料均未搜索匹配成功"
    }


if __name__ == '__main__':
    from openai import OpenAI

    base_url1 = "https://ark.cn-beijing.volces.com/api/v3/bots"
    base_model1 = "bot-20250618131857-l9ffp"
    with open('./static/key1.txt', 'r', encoding='utf-8') as f:
        llmkey1 = f.read()
    client1 = OpenAI(
        base_url=base_url1,
        api_key=llmkey1
    )
    # design_intention = """
    #     24Ghz毫米波雷达人体感应模块方案：
    #         1.射频芯片选用上海矽杰微的SRK1101射频芯片，频段24Ghz，天线设计采用3dB增益，设计有效距离可调节1m-3m
    #         2.要求输出高电平信号及串口信号
    #         3.供电部分选型采用LDO提供3.3V电压，输出电流600mA，电源纹波抑制比75dB
    #         4.数据处理部分采用BISS0001放大器，通过改变放大阻容设计调节感应阈值，变更有效距离。
    # """
    # desc = "传感器, 24GHz雷达芯片 3dB增益天线, 人体运动检测和距离测量"
    # start_time = time.time()
    # search_res = get_alternate_materials(title="SRK1101", description=desc, ds_chat=client1,
    #                                      design_intention=design_intention, replace=False,
    #                                      auto_replace=False)
    design_intention = """
        """
    desc = ""
    start_time = time.time()
    search_res = get_alternate_materials(title="MAX4892EETX+---", description=desc, ds_chat=client1,
                                         design_intention=design_intention, replace=False,
                                         auto_replace=False)
    print(search_res)
    with open(f"{output_dir}/final_data.json", "w", encoding="utf-8") as f:
        json.dump(search_res, f, indent=2, ensure_ascii=False)
    end_time = time.time()
    logger.info(f"总耗时: {end_time - start_time:.2f}s")
