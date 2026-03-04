import copy
import time
from collections.abc import Mapping
import pandas as pd
from elasticsearch import Elasticsearch
from langchain.prompts import ChatPromptTemplate
from json_repair import repair_json
import json
import textwrap
import re
import logging
from typing import List, Dict, Any, Optional, Tuple, Union
import concurrent.futures
import difflib

# ================= 配置与初始化 =================

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

json_pattern = r'```json(.*?)```'

# --- [配置参数] ---
LLM_INTERNAL_BATCH_SIZE = 4
MAX_WORKERS = 16

# 加载分类数据
try:
    with open("./all_categories.json", "r", encoding="utf-8") as f:
        all_categories = json.load(f)
    categories = list(set(all_categories.values()))
except Exception as e:
    logger.warning(f"加载分类文件失败: {e}")
    all_categories = {}
    categories = []

base_model = "bot-20250827135630-2rprd"
output_dir = "./result"

# 代理品牌信息
try:
    cecport_agent = pd.read_csv("./cecport_agent_brand.csv", encoding="gbk")
    cecport_agent = cecport_agent.fillna('')
    agent_brands = [str(brand_id) for brand_id in cecport_agent['品牌ID'].tolist() if pd.notna(brand_id)]
except Exception as e:
    logger.warning(f"加载代理品牌文件失败: {e}")
    cecport_agent = pd.DataFrame()
    agent_brands = []

# 创建品牌名称映射
brand_name_mapping = {}
if not cecport_agent.empty:
    for _, row in cecport_agent.iterrows():
        brand_id = str(row['品牌ID'])
        brand_name = row['品牌英文名称'] + '|' + row['品牌中文名称'] + '|' + row['品牌中文简称'] + '|' + row[
            '品牌英文简称']
        if not brand_name:
            brand_name = f"品牌ID:{brand_id}"
        brand_name_mapping[brand_id] = brand_name

agent_brand_names = [name for name in brand_name_mapping.values() if name]
agent_brand_ids = []
for brand_id in agent_brands:
    try:
        agent_brand_ids.append(int(brand_id))
    except ValueError:
        continue

# 品牌别名映射
brand_alias_mapping = {
    'TI': 'Texas Instruments',
    'Texas Instruments': 'TI',
    'ST': 'STMicroelectronics',
    'STMicroelectronics': 'ST',
    'NXP': 'NXP Semiconductors',
    'NXP Semiconductors': 'NXP',
    'Infineon': 'Infineon Technologies',
    'Infineon Technologies': 'Infineon',
    'ADI': 'Analog Devices',
    'Analog Devices': 'ADI',
    'MICROCHIP': 'Microchip Technology',
    'LEGENDSEMI': 'Legendsemi',
    '领慧立芯': 'Legendsemi'
}

brand_name_to_id = {}
if not cecport_agent.empty:
    for _, row in cecport_agent.iterrows():
        brand_id = str(row['品牌ID'])
        if pd.notna(row['品牌中文名称']) and row['品牌中文名称'].strip():
            brand_name_to_id[row['品牌中文名称'].strip().upper()] = int(brand_id)
        if pd.notna(row['品牌英文名称']) and row['品牌英文名称'].strip():
            brand_name_to_id[row['品牌英文名称'].strip().upper()] = int(brand_id)
        if pd.notna(row['品牌中文简称']) and row['品牌中文简称'].strip():
            brand_name_to_id[row['品牌中文简称'].strip().upper()] = int(brand_id)
        if pd.notna(row['品牌英文简称']) and row['品牌英文简称'].strip():
            brand_name_to_id[row['品牌英文简称'].strip().upper()] = int(brand_id)
        combined_name = f"{row['品牌英文名称']}|{row['品牌中文名称']}|{row['品牌中文简称']}|{row['品牌英文简称']}".upper()
        brand_name_to_id[combined_name] = int(brand_id)

for alias, official in brand_alias_mapping.items():
    if official.upper() in brand_name_to_id:
        brand_name_to_id[alias.upper()] = brand_name_to_id[official.upper()]


# ================= 工具函数 =================
def resolve_brand_id_fuzzy(user_input_brand: str) -> Optional[int]:
    if not user_input_brand or not user_input_brand.strip():
        return None
    clean_input = user_input_brand.strip().upper()
    if clean_input in brand_name_to_id:
        return brand_name_to_id[clean_input]
    if '|' in clean_input:
        parts = clean_input.split('|')
        for part in parts:
            p_strip = part.strip()
            if p_strip in brand_name_to_id:
                return brand_name_to_id[p_strip]
            if p_strip in brand_alias_mapping:
                official = brand_alias_mapping[p_strip].upper()
                if official in brand_name_to_id:
                    return brand_name_to_id[official]
    if clean_input in brand_alias_mapping:
        official = brand_alias_mapping[clean_input].upper()
        if official in brand_name_to_id:
            return brand_name_to_id[official]
    all_keys = list(brand_name_to_id.keys())
    matches = difflib.get_close_matches(clean_input, all_keys, n=1, cutoff=0.8)
    if matches:
        return brand_name_to_id[matches[0]]
    return None


def get_brand_id_from_es(es, index_name: str, brand_input: str) -> Optional[int]:
    if not brand_input: return None
    clean_input = brand_input.replace("|", " ")
    query = {
        "query": {
            "bool": {
                "should": [
                    {"multi_match": {
                        "query": clean_input,
                        "fields": [
                            "brandName",
                            "brandNameCn",
                            "abbrCnName",
                            "abbrEnName"
                        ],
                        "type": "phrase"
                    }},
                    {
                        "bool": {
                            "must": [
                                {"bool": {
                                    "should": [
                                        {"term": {"abbrEnName": clean_input}},
                                        {"match": {"abbrEnName.text": clean_input}}
                                    ]
                                }},
                                {"bool": {
                                    "should": [
                                        {"term": {"brandNameCn": clean_input}},
                                        {"term": {"abbrCnName": clean_input}},
                                        {"match": {"brandNameCn.text": clean_input}}
                                    ]
                                }}
                            ],
                            "boost": 3.0
                        }
                    },
                    {"multi_match": {
                        "query": clean_input,
                        "fields": [
                            "brandName.text^2",
                            "brandNameCn.text^2",
                            "abbrCnName.text^2",
                            "abbrEnName.text^2"
                        ],
                        "type": "cross_fields",
                        "operator": "and"
                    }}
                ]
            }
        },
        "size": 1,
        "_source": ["brandId", "brandName", "brandNameCn"],
        "sort": [
            {"_score": {"order": "desc"}}
        ]
    }
    try:
        resp = es.search(index=index_name, body=query)
        if resp['hits']['hits']:
            src = resp['hits']['hits'][0]['_source']
            b_id = src.get('brandId')
            if b_id:
                return int(b_id)
    except Exception as e:
        logger.warning(f"ES Brand Search Failed: {e}")
    return None


def safe_parse_float(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    val_str = str(value).strip()
    if '/' in val_str:
        try:
            parts = val_str.split('/')
            if len(parts) == 2:
                num, den = float(parts[0]), float(parts[1])
                if den != 0: return num / den
        except:
            pass
    try:
        return float(val_str)
    except ValueError:
        match = re.search(r"[-+]?\d*\.\d+|\d+", val_str)
        if match:
            try:
                return float(match.group())
            except:
                pass
    return 0.0


def normalize_to_dict(obj) -> Dict:
    if isinstance(obj, Mapping): return dict(obj)
    if isinstance(obj, list):
        flat = {}
        for d in obj:
            if isinstance(d, Mapping): flat.update(d)
        return flat
    return {}


def extract_package(pack: str) -> str:
    if pack:
        letters = ''.join(re.findall(r'[A-Za-z]+', pack))
        numbers = ''.join(re.findall(r'\d+', pack))
        return (letters + numbers).upper()
    return ""


def extract_scene_guidance(design_intention: str) -> str:
    intention_lower = design_intention.lower()
    guidance_rules = [
        {"keywords": ["电子烟", "vape", "手机", "充电宝", "蓝牙耳机", "智能手表", "消费", "便携", "电池供电", "低成本"],
         "guidance": "场景:消费级. 策略:低成本,通用型号. 避开AEC-Q100."},
        {"keywords": ["汽车", "车载", "车规", "aec-q100", "发动机", "adas"],
         "guidance": "场景:汽车. 策略:高可靠,AEC-Q100认证. 成本非首要."},
        {"keywords": ["工业", "工控", "PLC", "变频器", "伺服", "机器人", "自动化"],
         "guidance": "场景:工业. 策略:平衡性能成本,工业温宽."},
        {"keywords": ["医疗", "医用", "医疗器械", "病人监护"],
         "guidance": "场景:医疗. 策略:绝对可靠,医疗认证."}
    ]
    for rule in guidance_rules:
        if any(keyword in intention_lower for keyword in rule["keywords"]):
            return rule["guidance"]
    return "场景:通用. 策略:平衡性能成本."


def is_consumer_scene(design_intention: str) -> bool:
    intention_lower = design_intention.lower()
    consumer_keywords = ["电子烟", "vape", "手机", "充电宝", "蓝牙耳机", "智能手表", "消费", "便携", "电池供电",
                         "低成本", "家用", "娱乐", "个人"]
    return any(keyword in intention_lower for keyword in consumer_keywords)


def sort_by_completeness(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def score(item: Dict[str, Any]) -> int:
        s = 0
        check_keys = ['title', 'xccCategoryName', 'brandName', 'brandNameCn', "secondCategoryId",
                      'description', 'packing', 'pdfUrl', 'series', 'xccCategoryNames', 'lifecycleStatus']
        for k in check_keys:
            val = item.get(k)
            if val:
                if k == 'lifecycleStatus' and val == '量产':
                    s += 3
                elif isinstance(val, str) and val.strip():
                    s += 1
                elif isinstance(val, list) and len(val) > 0:
                    s += 1
                else:
                    s += 1
        if item.get('brandId'): s += 1
        if item.get('xccCategoryId'): s += 1
        ai = item.get('attrInfo') or []
        if ai: s += 1 + len(ai)
        return s

    return sorted(data, key=score, reverse=True)


def sort_agent_brands_by_priority(data):
    if not data: return data
    agent_items, other_items = [], []
    for item in data:
        if item.get("brandId") in agent_brand_ids:
            agent_items.append(item)
        else:
            other_items.append(item)
    return sort_by_completeness(agent_items) + sort_by_completeness(other_items)


def relax_parameters_for_consumer(query_data: List[Dict]) -> List[Dict]:
    relaxed_data = []
    for condition in query_data:
        require = condition.get('require', '')
        nvs_values = condition.get('nvs', [])
        attr_name = condition.get('attrCnName', '').lower()
        if nvs_values and attr_name not in ['marking code', 'code', '型号']:
            relaxed_condition = condition.copy()
            if require == '大于等于' and nvs_values:
                relaxed_condition['nvs'] = [safe_parse_float(nvs) * 0.8 for nvs in nvs_values]
            elif require == '小于等于' and nvs_values:
                relaxed_condition['nvs'] = [safe_parse_float(nvs) * 1.2 for nvs in nvs_values]
            elif require == '等于' and nvs_values:
                relaxed_condition['require'] = '约等于'
            relaxed_data.append(relaxed_condition)
        else:
            relaxed_data.append(condition)
    return relaxed_data


def simplify_attrs(attr_info: Union[List[Dict], str]) -> str:
    if not attr_info: return ""
    if isinstance(attr_info, str): return attr_info
    if isinstance(attr_info, list):
        simplified = []
        seen = set()
        for item in attr_info:
            if isinstance(item, dict):
                name = item.get('attrCnName', '').strip()
                val = str(item.get('attrValues', '')).strip()
                if name.lower() in ['rohs', 'reach', '包装', 'series', 'status']: continue
                entry = f"{name}:{val}" if name else val
                if entry and entry not in seen:
                    simplified.append(entry)
                    seen.add(entry)
        return ";".join(simplified[:8])
    return str(attr_info)


def build_compact_candidate_info(item: Dict, for_replacement: bool = False) -> str:
    """
    [优化] 使用极简缩写构建候选项信息，大幅减少Token占用。
    M:Model, B:Brand, C:xccCategoryName, A:Attr, P:Pack, D:Desc, Ag:Agent
    """
    brand = item.get("brandNameCn") or item.get("brandName") or "Unk"
    desc_raw = str(item.get("description", "")).replace("\n", " ").replace("\r", "")
    desc = desc_raw[:50]  # 进一步缩短描述
    params = simplify_attrs(item.get("attrInfo", []))
    pack = item.get("packing", "")
    category = item.get("xccCategoryName", "")

    parts = [f"M:{item.get('title', 'Unk')}"]
    if brand: parts.append(f"B:{brand}")
    if category: parts.append(f"C:{category}")
    if desc: parts.append(f"D:{desc}")
    if params: parts.append(f"A:{params}")
    if pack: parts.append(f"P:{pack}")

    is_agent = "YES" if item.get("brandId") in agent_brand_ids else "NO"
    parts.append(f"Ag:{is_agent}")

    return "|".join(parts)


# ================= 搜索构建函数 =================

def build_dynamic_query(query_data, category_ids, package, packet_set, keywords=[],
                        replace: bool = False, assigned_brand_id: Optional[int] = None,
                        consumer_scene: bool = False, strict_category: bool = True,
                        domestic_only: bool = False, lifecycle: bool = False,
                        strict_brand: bool = False) -> Dict:
    """
    增加了 strict_brand 参数：
    - True: 强制过滤 brandId (Phase 3 优先搜索)
    - False: 如果有 assigned_brand_id，仅做 boost 加权 (Phase 3 全网兜底搜索)
    """
    if not isinstance(category_ids, list): category_ids = [category_ids]
    base_filter = [{"term": {"showFlag": 1}}]

    # 国内品牌过滤
    if domestic_only:
        base_filter.append({"terms": {"brandRegion": [1, 2, 158, 344]}})
    cat_query_part = []

    if category_ids:
        if strict_category:
            base_filter.append({"terms": {"xccCategoryIds": category_ids}})
        else:
            cat_query_part.append({"terms": {"xccCategoryIds": category_ids, "boost": 5}})

    # --- 品牌处理逻辑 ---
    if assigned_brand_id is not None:
        if strict_brand:
            base_filter.append({"term": {"brandId": assigned_brand_id}})
        # 如果不是strict，后续加boost
    elif replace and agent_brands:
        base_filter.append({"terms": {"brandId": agent_brand_ids}})

    query = {
        "query": {
            "bool": {
                "filter": base_filter,
                "should": cat_query_part,
                "minimum_should_match": 1 if not base_filter else 0
            }
        },
        "size": 50,
        "track_total_hits": False
    }

    # 非严格模式下的品牌加权
    if assigned_brand_id is not None and not strict_brand:
        query["query"]["bool"]["should"].append({
            "constant_score": {"filter": {"term": {"brandId": assigned_brand_id}}, "boost": 50}
        })
    elif not replace and agent_brand_ids and assigned_brand_id is None:
        query["query"]["bool"]["should"].append({
            "constant_score": {"filter": {"terms": {"brandId": agent_brand_ids}}, "boost": 20}
        })

    if lifecycle:
        query["query"]["bool"]["should"].append({
            "constant_score": {"filter": {"terms": {"lifecycleStatus": ["量产"]}}, "boost": 12}
        })
        query["query"]["bool"]["should"].append({
            "constant_score": {"filter": {"terms": {"lifecycleStatus": ["试产", "衰退期", "逐步淘汰"]}}, "boost": 6}
        })

    if keywords:
        kw_query = {
            "constant_score": {
                "filter": {
                    "multi_match": {
                        "query": " ".join(keywords),
                        "fields": ["description", "paramJson", "title", "xccCategoryName"],
                        "operator": "or", "type": "best_fields"
                    }
                }, "boost": 6
            }
        }
        query["query"]["bool"]["should"].append(kw_query)

    processed_query_data = query_data
    if consumer_scene and query_data:
        processed_query_data = relax_parameters_for_consumer(query_data)

    value_query = {"nested": {"path": "categoryAttrInfo", "query": {"bool": {"should": [], "minimum_should_match": 1}}}}
    has_nested_query = False

    for condition in processed_query_data:
        attr_value = condition.get('attrValues', '').strip()
        if not attr_value: continue
        nvs_values = condition.get('nvs') or []
        unit = condition.get('attrUnit', "")

        value_format = [attr_value.lower(), attr_value.replace(" ", "").lower()]
        if nvs_values and unit:
            value_format.append(f"{nvs_values[0]}{unit}".lower())

        nested_conditions = {"terms": {"categoryAttrInfo.attrValues.ignoreCaseField": list(set(value_format))}}
        value_query["nested"]["query"]["bool"]["should"].append(nested_conditions)
        has_nested_query = True

        if nvs_values and unit:
            base_val = safe_parse_float(nvs_values[0])
            range_conditions = {"range": {
                "categoryAttrInfo.nvs": {"gte": base_val * 0.7, "lte": base_val * 1.3}}} if base_val != 0 else {}
            if range_conditions:
                range_query_part = {
                    "bool": {"must": [{"term": {"categoryAttrInfo.attrUnit": f"{unit}"}}, range_conditions]}}
                value_query["nested"]["query"]["bool"]["should"].append(range_query_part)

        params_text_query = {
            "constant_score": {
                "filter": {
                    "multi_match": {
                        "query": attr_value,
                        "fields": ["description", "paramJson", "title"],
                        "type": "phrase"
                    }
                }, "boost": 2
            }
        }
        query["query"]["bool"]["should"].append(params_text_query)

    if has_nested_query:
        query["query"]["bool"]["should"].append(value_query)
    if not strict_category and not base_filter:
        query["query"]["bool"]["minimum_should_match"] = 1
    return query


def search_agent_recall_query(keywords: List[str], desc_str: str, domestic_only: bool = False) -> Dict:
    search_text = " ".join(keywords) + " " + desc_str
    filters = [{"terms": {"brandId": agent_brand_ids}}, {"term": {"showFlag": 1}}]

    if domestic_only:
        filters.append({"terms": {"brandRegion": [1, 2, 158, 344]}})
    return {
        "query": {
            "bool": {
                "filter": filters,
                "should": [{"multi_match": {"query": search_text,
                                            "fields": ["title^3", "description", "xccCategoryName", "paramJson"],
                                            "operator": "or"}}],
                "minimum_should_match": 1
            }
        }, "size": 30
    }


def search_by_desc(es, index: str, query: Dict, assigned_brand_id: Optional[int] = None) -> List[Dict]:
    try:
        response = es.search(index=index, body=query)
        hits_data = response["hits"]["hits"]
        search_data = []
        if hits_data:
            for hit in hits_data:
                info = hit["_source"]
                try:
                    key_list = ["title", "xccCategoryId", "xccCategoryName", "brandId", "brandName", "brandNameCn",
                                "description", "packing", "pdfUrl", 'xccCategoryIds', 'series', 'xccCategoryNames',
                                "lifecycleStatus"]
                    res = {k: (info[k] if info.get(k) is not None else "") for k in key_list}
                    if not res.get("brandNameCn"): res["brandNameCn"] = res.get("brandName", "")
                    if res.get('xccCategoryIds') and len(res['xccCategoryIds']) >= 2:
                        res["secondCategoryId"] = res['xccCategoryIds'][1]
                    attr_info_raw = info.get("categoryAttrInfo", [])
                    res["attrInfo"] = []
                    if attr_info_raw:
                        valid_attrs = [
                            {k: v for k, v in attr.items() if k in ["attrCnName", "attrValues"]}
                            for attr in attr_info_raw if attr.get("attrValues") and attr.get("coreFlag")]
                        valid_attrs = [attr for attr in valid_attrs if
                                       not bool(re.search(r'[\u4e00-\u9fff]', attr.get("attrValues", "")))]
                        res["attrInfo"].extend(valid_attrs)
                    else:
                        # 优先官方参数
                        officialJson = json.loads(info.get("officialJson", "{}")) if info.get("officialJson",
                                                                                              "{}") else {}
                        param_json = normalize_to_dict(officialJson)
                        if not param_json:
                            # 次选其他参数
                            param_data = json.loads(info.get("paramJson", "{}")) if info.get("paramJson", "{}") else {}
                            param_json = normalize_to_dict(param_data)
                        if param_json:
                            attr_other = []
                            for param, value in param_json.items():
                                if not bool(re.search(r'[\u4e00-\u9fff]', value)):
                                    attr_other.append({"attrCnName": param, "attrValues": value})
                            res["attrInfo"].extend(attr_other)
                    search_data.append(res)
                except Exception:
                    continue

        if assigned_brand_id is None:
            search_data = sort_agent_brands_by_priority(search_data)
        if assigned_brand_id is not None:
            search_data = [h for h in search_data if h.get("brandId") == assigned_brand_id]

        return search_data
    except Exception as e:
        logger.error(f"描述搜索失败: {e}")
        return []


def get_title_info(es, index_name: str, title: str, assigned_brand_id: Optional[int] = None,
                   domestic_only: bool = False) -> Tuple[bool, List[Dict]]:
    """
        如果 domestic_only=True，即使是精确查找 title，也只返回国产的。
    """
    title_infos = []
    precise = True
    common_filter = []
    if assigned_brand_id is not None:
        common_filter.append({"term": {"brandId": assigned_brand_id}})

    if domestic_only:
        common_filter.append({"terms": {"brandRegion": [1, 2, 158, 344]}})

    exact_query = {
        "query": {
            "bool": {"must": [{"term": {"title": title}}, {"term": {"showFlag": 1}}], "filter": common_filter}},
        "size": 10
    }
    response = es.search(index=index_name, body=exact_query)

    if response["hits"]["total"]["value"] <= 0:
        # 前缀匹配
        precise = False
        query_term = {
            "query": {
                "bool": {
                    "must": [
                        {"match": {"title.autocomplete": title}},
                        {"term": {"showFlag": 1}},
                    ],
                    "filter": common_filter,
                }
            },
            "size": 25,
        }
        response = es.search(index=index_name, body=query_term)

    try:
        if response["hits"]["total"]["value"] <= 0: return precise, []
        hits = response["hits"]["hits"]
        for hit in hits:
            info = hit["_source"]
            try:
                key_list = ["title", "xccCategoryId", "xccCategoryName", "brandId", "brandName", "brandNameCn",
                            "description", "packing", "pdfUrl", 'xccCategoryIds', 'series', 'xccCategoryNames',
                            "lifecycleStatus"]
                res = {k: (info[k] if info.get(k) is not None else "") for k in key_list}
                if not res.get("brandNameCn"): res["brandNameCn"] = res.get("brandName", "")
                attr_info = info.get("categoryAttrInfo", [])
                category_ids = info.get('xccCategoryIds', [])
                if category_ids and len(category_ids) >= 2:
                    res["secondCategoryId"] = info.get('xccCategoryIds')[1]
                res["attrInfo"] = []
                if attr_info:
                    valid_attrs = [
                        {k: v for k, v in attr.items() if k in ["attrCnName", "attrValues"]}
                        for attr in attr_info if attr.get("attrValues") and attr.get("coreFlag")]
                    valid_attrs = [attr for attr in valid_attrs if
                                   not bool(re.search(r'[\u4e00-\u9fff]', attr.get("attrValues", "")))]
                    res["attrInfo"].extend(valid_attrs)
                else:
                    officialJson = json.loads(info.get("officialJson", "{}")) if info.get("officialJson", "{}") else {}
                    param_json = normalize_to_dict(officialJson)
                    if not param_json:
                        param_data = json.loads(info.get("paramJson", "{}")) if info.get("paramJson", "{}") else {}
                        param_json = normalize_to_dict(param_data)
                    if param_json:
                        attr_other = []
                        for param, value in param_json.items():
                            if not bool(re.search(r'[\u4e00-\u9fff]', value)):
                                attr_other.append({"attrCnName": param, "attrValues": value})
                        res["attrInfo"].extend(attr_other)
                title_infos.append(res)
            except Exception:
                continue
    except Exception as e:
        logger.error(f"ES查询失败: {e}")
        return precise, []

    groups = {}
    for item in title_infos:
        key = (item.get('title'), item.get('brandId'))
        if key not in groups: groups[key] = item
    final_list = list(groups.values())
    if assigned_brand_id is None:
        final_list = sort_agent_brands_by_priority(final_list)
    return precise, final_list


def processing_hits(hits):
    result = []
    for hit in hits:
        info = hit["_source"]
        try:
            key_list = ["title", "xccCategoryId", "xccCategoryName", "brandId", "brandName", "brandNameCn",
                        "description", "packing", "pdfUrl", 'xccCategoryIds', 'series', 'xccCategoryNames',
                        "lifecycleStatus"]
            res = {k: (info[k] if info.get(k) is not None else "") for k in key_list}

            if not res.get("brandNameCn"): res["brandNameCn"] = res.get("brandName", "")
            attr_info = info.get("categoryAttrInfo", [])
            res["attrInfo"] = []
            if attr_info:
                valid_attrs = [
                    {k: v for k, v in attr.items() if k in ["attrCnName", "attrValues"]}
                    for attr in attr_info if attr.get("attrValues") and attr.get("coreFlag")]
                valid_attrs = [attr for attr in valid_attrs if
                               not bool(re.search(r'[\u4e00-\u9fff]', attr.get("attrValues", "")))]
                res["attrInfo"].extend(valid_attrs)
            result.append(res)
        except Exception:
            continue
    return result


# ================= 批量化 LLM 处理函数 =================
def batch_llm_extract_values_from_desc(task_map: Dict[int, Dict], ds_chat, design_intention: str) -> Dict[int, Dict]:
    """
    [Stage 2] 提取参数
    """
    if not task_map: return {}
    scene_guidance = extract_scene_guidance(design_intention)
    all_task_ids = list(task_map.keys())
    chunks = []

    for i in range(0, len(all_task_ids), LLM_INTERNAL_BATCH_SIZE):
        chunk_ids = all_task_ids[i:i + LLM_INTERNAL_BATCH_SIZE]
        chunks.append({"ids": chunk_ids, "data": {tid: task_map[tid] for tid in chunk_ids}})

    def process_chunk(chunk_info):
        chunk_task_map = chunk_info["data"]
        batch_input_str = ""
        for idx, data in chunk_task_map.items():
            batch_input_str += f"\n--- ID: {idx} ---\nInfo: {data['desc'][:300]}\n"
            if data.get('brandassign'): batch_input_str += f"Brand: {data['brandassign']}\n"
            if data.get('category'): batch_input_str += f"Cat: {data['category']}\n"

        template = '''
            # 任务：批量提取电子元件参数。
            # 场景：{scene_guidance}
            # 代理品牌：{agent_brands}
            # 输入：
            {batch_input}
            # 参考分类(Top)：{categories}

            # 要求：
            1. 提取封装(pkg)、引脚数(pins)、3个关键词(kws)。
            2. 提取5个关键参数(params)。params格式必须为二维数组：[["属性名", "属性值", 数值(无则null), "单位", "比较符(等于/大于/小于)"]]。
            3. 输出 JSON，Key=ID。
            4. 提取分类category必须是参考分类中的完整分类名称。

            # 输出示例：
            {{
                "1": {{
                    "category": "电容", "pkg": "0603", "pins": "2", "kws": ["滤波"], "matched_brand_id": null,
                    "params": [["容值", "10uF", 10, "uF", "等于"], ["电压", "16V", 16, "V", "大于等于"]]
                }}
            }}
        '''
        prompt_template = ChatPromptTemplate.from_template(textwrap.dedent(template).strip())
        messages = prompt_template.format_messages(
            scene_guidance=scene_guidance,
            agent_brands=", ".join(agent_brand_names[:15]),
            batch_input=batch_input_str,
            categories=str(categories)
        )
        chunk_results = {}
        with open(f"{output_dir}/attr_prompt.txt", "w", encoding="utf-8") as f:
            f.write(messages[0].content)
        try:
            response = ds_chat.chat.completions.create(
                model=base_model,
                messages=[
                    {"role": "user", "content": messages[0].content},
                ],
                stream=False,
                response_format="json",
                timeout=30
            )
            content = response.choices[0].message.content
            with open(f"{output_dir}/attr_response.txt", "w", encoding="utf-8") as f:
                f.write(content)
            match = re.findall(json_pattern, content, re.DOTALL)
            json_str = match[0].strip() if match else content
            result = json.loads(str(repair_json(json_str=json_str, return_objects=False)))

            for k, v in result.items():
                idx = int(k)
                compact_params = v.get("params", [])
                expanded_desc = []
                if isinstance(compact_params, list):
                    for p in compact_params:
                        if isinstance(p, list) and len(p) >= 2:
                            item = {
                                "attrCnName": str(p[0]), "attrValues": str(p[1]),
                                "nvs": [p[2]] if len(p) > 2 and p[2] is not None else [],
                                "attrUnit": str(p[3]) if len(p) > 3 else "",
                                "require": str(p[4]) if len(p) > 4 else "等于"
                            }
                            expanded_desc.append(item)

                v["description"] = expanded_desc
                v["封装"] = v.get("pkg")
                v["引脚数"] = v.get("pins")
                v["关键词"] = v.get("kws")
                chunk_results[idx] = v
        except Exception as e:
            logger.error(f"LLM提取异常: {e}")
        return chunk_results

    final_results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_chunk, chunk) for chunk in chunks]
        for future in concurrent.futures.as_completed(futures): final_results.update(future.result())
    return final_results


def batch_search_data_rerank(task_map: Dict[int, Dict], ds_chat, design_intention: str) -> Dict[int, Dict]:
    """
    [Stage 4 优化]
    提示词逻辑升级：强制类别一致，优先指定品牌，兜底其他品牌。
    """
    if not task_map: return {}
    all_task_ids = list(task_map.keys())
    chunks = []
    for i in range(0, len(all_task_ids), LLM_INTERNAL_BATCH_SIZE):
        chunk_ids = all_task_ids[i:i + LLM_INTERNAL_BATCH_SIZE]
        chunks.append({"ids": chunk_ids, "data": {tid: task_map[tid] for tid in chunk_ids}})

    def process_chunk(chunk_info):
        chunk_task_map = chunk_info["data"]
        chunk_ids = chunk_info["ids"]
        chunk_results = {}
        batch_input_str = ""
        for idx, data in chunk_task_map.items():
            cand_list = list(data['database'].items())[:20]
            cand_list_str = "\n".join([f"[{k}] {v}" for k, v in cand_list])

            # 获取用户指定的品牌（如果有）
            user_assigned_brand = data.get('user_assigned_brand_name', '无')

            batch_input_str += f"\n--- ID: {idx} ---\nTarget Brand: {user_assigned_brand}\nReq: {data['desc'][:100]}\nCands:\n{cand_list_str}\n"

        template = '''
           # 任务：为目标器件寻找最佳匹配。
           # 【优先级决策树】：
           1. **功能/类别检查 (Hard Constraint)**：候选器件的 Function/Category 必须与 Req 描述一致。如果不一致（如需求MCU却选了放大器），**直接淘汰**，无论品牌是否匹配。
           2. **品牌匹配 (High Priority)**：
              - 如果 User 指定了 "Target Brand" (非"无")：
              - **必须优先**选择该品牌的候选（只要功能对得上）。
              - 即使该品牌候选的参数（如精度、带宽）比其他品牌稍差，也要选它。
              - **只有当**该品牌下完全没有功能匹配的器件时，才允许选择其他品牌。
           3. **代理优先 (Medium Priority)**：如果没指定品牌，优先选 Ag:YES。
           4. **参数匹配**：最后考虑参数的精确度。

           # 格式：M:Model, B:Brand, C:Category(元器件类别), D:Description(器件描述), A:Attr(参数), P:Pack(封装), Ag:Agent(是否代理)

           # 输出 JSON (Key=ID)。
           # 输出示例：
           {{ "2": {{ "id": 0, "evaluate": "功能一致，品牌符合，参数稍宽但可用", "核心标签": ""Cortex-M7核心,16bit ADC,LQFP封装"" }} }}

           # 输入：
           {batch_input}
        '''
        prompt_template = ChatPromptTemplate.from_template(textwrap.dedent(template).strip())
        messages = prompt_template.format_messages(batch_input=batch_input_str)
        with open(f"{output_dir}/best_prompt.txt", "w", encoding="utf-8") as f:
            f.write(messages[0].content)
        try:
            response = ds_chat.chat.completions.create(
                model=base_model,
                messages=[
                    {"role": "user", "content": messages[0].content},
                ],
                stream=False,
                response_format="json",
                timeout=30
            )
            content = response.choices[0].message.content
            with open(f"{output_dir}/best_response.txt", "w", encoding="utf-8") as f:
                f.write(content)
            match = re.findall(json_pattern, content, re.DOTALL)
            json_str = match[0].strip() if match else content
            result = json.loads(str(repair_json(json_str=json_str, return_objects=False)))
            for k, v in result.items(): chunk_results[int(k)] = v
        except Exception:
            for tid in chunk_ids:
                if chunk_task_map[tid]['database']:
                    first_key = list(chunk_task_map[tid]['database'].keys())[0]
                    chunk_results[tid] = {"id": first_key, "evaluate": "Timeout-Auto", "核心参数": "Default"}
        return chunk_results

    final_results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_chunk, chunk) for chunk in chunks]
        for future in concurrent.futures.as_completed(futures): final_results.update(future.result())
    return final_results


def batch_replace_data_rerank(task_map: Dict[int, Dict], ds_chat, design_intention: str) -> Dict[int, List[Dict]]:
    """
    [Stage 5] 替代料筛选
    """
    if not task_map: return {}
    scene_guidance = extract_scene_guidance(design_intention)
    consumer_scene = is_consumer_scene(design_intention)
    all_task_ids = list(task_map.keys())
    chunks = []
    for i in range(0, len(all_task_ids), LLM_INTERNAL_BATCH_SIZE):
        chunk_ids = all_task_ids[i:i + LLM_INTERNAL_BATCH_SIZE]
        chunks.append({"ids": chunk_ids, "data": {tid: task_map[tid] for tid in chunk_ids}})

    def process_chunk(chunk_info):
        chunk_task_map = chunk_info["data"]
        chunk_results = {}
        batch_input_str = ""
        for idx, data in chunk_task_map.items():
            cand_list = list(data['database'].items())[:12]
            cand_list_str = "\n".join([f"[{k}] {v}" for k, v in cand_list])
            batch_input_str += f"\n--- ID: {idx} ---\nTarget: {data['desc'][:120]}\nCands:\n{cand_list_str}\n"

        template = '''
            # 任务：选出每个ID的最多10个最佳替代, 给出简要替代理由，从D、A、P中总结提取3个性能参数的核心标签。
            # 场景：{scene_guidance}
            # 优先：Ag:YES (代理) > Ag:NO。消费级({is_consumer})偏好低成本。
            # 核心原则：替代料的功能分类必须与Target一致。
            # 输入格式：[候选id],M:Model, B:Brand,C:Category(器件类别),D:Description(器件描述), A:Attr(参数), P:Pack(封装), Ag:Agent
            # 输出格式：JSON (Key=ID, Value=[[ID, "Reason", "CoreTags"], ... ])，格式如下:
            {{"0":[ ["候选id1", "简要的可替代理由(20字内)", "核心标签1,核心标签2,核心标签3"],...],...}}
            # 输出示例:
            {{"0":[ ["3", "功能参数匹配，性能强", "Cortex-M7核心,16bit ADC,LQFP封装"],...],...}}

            # 输入：
            {batch_input}
        '''
        prompt_template = ChatPromptTemplate.from_template(textwrap.dedent(template).strip())
        messages = prompt_template.format_messages(scene_guidance=scene_guidance,
                                                   is_consumer="是" if consumer_scene else "否",
                                                   batch_input=batch_input_str)
        with open(f"{output_dir}/rep_prompt.txt", "w", encoding="utf-8") as f:
            f.write(messages[0].content)
        try:
            response = ds_chat.chat.completions.create(
                model=base_model,
                messages=[
                    {"role": "user", "content": messages[0].content},
                ],
                stream=False,
                response_format="json",
                timeout=30
            )
            content = response.choices[0].message.content
            with open(f"{output_dir}/rep_response.txt", "w", encoding="utf-8") as f:
                f.write(content)
            match = re.findall(json_pattern, content, re.DOTALL)
            json_str = match[0].strip() if match else content
            result = json.loads(str(repair_json(json_str=json_str, return_objects=False)))
            for k, v in result.items(): chunk_results[int(k)] = v
        except Exception:
            pass
        return chunk_results

    final_results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_chunk, chunk) for chunk in chunks]
        for future in concurrent.futures.as_completed(futures): final_results.update(future.result())
    return final_results


# ================= 核心主函数 (Optimized) =================
def get_alternate_materials_batch(
        titles: List[str],
        descriptions: List[str],
        replace_list: List[bool],
        auto_replace_list: List[bool],
        brandassign_list: List[str],
        domestic_sub_list: List[bool],
        ds_chat,
        design_intention: str,
        output: str = "./result"
) -> List[Dict]:
    global output_dir
    output_dir = output

    original_count = len(titles)

    # 简单的参数长度校验，避免index error
    if len(domestic_sub_list) != original_count:
        logger.warning(
            f"domestic_sub_list length ({len(domestic_sub_list)}) mismatch titles ({original_count}), filling False.")
        domestic_sub_list = domestic_sub_list + [False] * (original_count - len(domestic_sub_list))

    # --- ES 连接 ---
    es_hosts = [
        "http://10.10.40.103:9200", "http://10.10.40.104:9200", "http://10.10.40.105:9200",
        "http://10.10.40.138:9200", "http://10.10.40.139:9200", "http://10.10.40.140:9200",
        "http://10.10.40.169:9200", "http://10.10.40.170:9200", "http://10.10.40.179:9200"
    ]
    es = Elasticsearch(
        es_hosts, timeout=60, maxsize=25,
        http_auth=("App-FAE", "97zQUZQCy4NcYrJ3nS")
    )

    if not es.ping():
        logger.error("数据库连接失败")
        return [{"error": "DB Fail"}] * original_count

    index_name = ["xcc_ware_detail"]

    # --- 任务去重 ---
    unique_tasks_map = {}
    task_signature_to_orig_indices = {}
    unique_titles, unique_descriptions, unique_replace, unique_auto, unique_brand, unique_brand_ids, unique_domestic = [], [], [], [], [], [], []

    for i in range(original_count):
        sig = (
            titles[i], descriptions[i], replace_list[i], auto_replace_list[i], brandassign_list[i],
            domestic_sub_list[i])
        if sig not in task_signature_to_orig_indices:
            task_signature_to_orig_indices[sig] = []
            unique_tasks_map[sig] = len(unique_titles)
            unique_titles.append(titles[i])
            unique_descriptions.append(descriptions[i])
            unique_replace.append(replace_list[i])
            unique_auto.append(auto_replace_list[i])
            unique_brand.append(brandassign_list[i])
            unique_domestic.append(domestic_sub_list[i])

            brand_str = brandassign_list[i]
            b_id = resolve_brand_id_fuzzy(brand_str)
            if b_id is None and brand_str and brand_str.strip():
                logger.info(f"Local brand map failed for '{brand_str}', searching ES...")
                b_id = get_brand_id_from_es(es, index_name, brand_str)
                if b_id is None: b_id = -999
            unique_brand_ids.append(b_id)
        task_signature_to_orig_indices[sig].append(i)

    count = len(unique_titles)
    logger.info(f"Batch Processing: Original {original_count} -> Unique {count} items.")

    final_results_unique = [None] * count
    rerank_tasks = {}
    extraction_tasks = {}
    replace_rerank_tasks = {}
    matched_data_store = {}

    start_time = time.time()

    # ================= Phase 1: 本地 ES 搜索 =================
    logger.info("Batch Stage 1: Local ES Search")
    st = time.time()
    for i in range(count):
        title = unique_titles[i].upper()
        desc = unique_descriptions[i]
        brand_assign = unique_brand[i]
        assigned_id = unique_brand_ids[i]

        has_brand_assigned = bool(brand_assign and brand_assign.strip())
        is_auto_replace_mode = unique_auto[i]
        is_domestic_required = unique_domestic[i]

        apply_domestic_filter = False
        if not has_brand_assigned and is_auto_replace_mode and is_domestic_required:
            apply_domestic_filter = True

        if assigned_id == -999:
            final_results_unique[i] = {"id": -1, "source": "brand_not_found", "match_data": {}, "replace_data": [],
                                       "evaluate": f"指定品牌 '{brand_assign}' 在数据库中未找到"}
            continue

        # 在 Phase 1 中也应用过滤
        precise_match, info_list = get_title_info(es, index_name, title, assigned_id,
                                                  domestic_only=apply_domestic_filter)

        if precise_match and info_list:
            best_match = info_list[0]
            matched_data_store[i] = best_match

            # 【核心策略调整】如果是自动替换模式(Auto Replace)，说明Title是AI生成的，可能不准。
            # 不要立即锁定结果，而是将其作为候选，强制进入后续提取和搜索流程进行校验。
            if not is_auto_replace_mode:
                base_res = {"id": 0, "source": "title_exact_match", "match_data": best_match, "replace_data": [],
                            "evaluate": "型号完全匹配"}
                final_results_unique[i] = base_res

                # 即使完全匹配，如果需要替代，也需要提取参数来搜索替代品
                full_desc = desc + f"\nModel:{best_match['title']}, Pkg:{best_match.get('packing')}, Attr:{simplify_attrs(best_match.get('attrInfo'))}"
                extraction_tasks[i] = {"desc": full_desc, "category": best_match.get("xccCategoryName", ""),
                                       "brandassign": brand_assign, "apply_domestic": apply_domestic_filter}

                cand_db = {str(idx): build_compact_candidate_info(item, for_replacement=False) for idx, item in
                           enumerate(info_list)}
                rerank_tasks[i] = {"desc": f"{title}. {desc}", "database": cand_db, "raw_list": info_list,
                                   "is_desc_search": False, "user_assigned_brand_name": brand_assign}  # 传入品牌
            else:
                # 自动替换模式：保留 Exact Match 备用，但不锁定。进入提取流程。
                extraction_tasks[i] = {"desc": desc, "category": "", "brandassign": brand_assign,
                                       "apply_domestic": apply_domestic_filter}

        elif not precise_match and info_list:
            cand_db = {str(idx): build_compact_candidate_info(item, for_replacement=False) for idx, item in
                       enumerate(info_list)}
            rerank_tasks[i] = {"desc": f"{title}. {desc}", "database": cand_db, "raw_list": info_list,
                               "is_desc_search": False, "user_assigned_brand_name": brand_assign}
        else:
            extraction_tasks[i] = {"desc": f"{title} {desc}", "category": "", "brandassign": brand_assign,
                                   "apply_domestic": apply_domestic_filter}
    logger.info(f"Batch Stage 1耗时: ({time.time() - st})")
    with open(f"{output_dir}/final_results_unique_1.json", "w", encoding="utf-8") as f:
        json.dump(final_results_unique, f, ensure_ascii=False, indent=2)

    # ================= Phase 2: 批量参数提取 =================
    st = time.time()
    if extraction_tasks:
        logger.info(f"Batch Stage 2: LLM Extraction ({len(extraction_tasks)})")
        extracted_results = batch_llm_extract_values_from_desc(extraction_tasks, ds_chat, design_intention)

        # ================= Phase 3: 基于提取参数的级联搜索 (强化版) =================
        for idx, ex_data in extracted_results.items():
            if unique_brand_ids[idx] == -999: continue

            # 获取是否应用国产过滤
            apply_domestic_filter = extraction_tasks[idx].get("apply_domestic", False)

            # 判断当前是“替代搜索”还是“描述搜索”
            is_replace_search = (idx in final_results_unique and final_results_unique[idx] is not None)

            orig_title = unique_titles[idx] if not is_replace_search else matched_data_store[idx]['title']
            need_auto = unique_auto[idx]
            do_replace_search = True if is_replace_search else (unique_replace[idx] or need_auto)

            cat_name = ex_data.get("category", "")
            cat_ids = []
            if cat_name:
                for k, v in all_categories.items():
                    if v == cat_name or (cat_name in v): cat_ids.append(k.split("||")[1])
            cat_ids = list(set(cat_ids))

            package_std = (ex_data.get("封装类型", "").upper(), ex_data.get("引脚数", "")) if ex_data.get(
                "封装类型") else ("", "")
            package = ex_data.get("封装", "").upper() if ex_data.get("封装") else ''
            keywords = ex_data.get("关键词", [])
            desc_data = ex_data.get("description", [])

            target_brand_id = unique_brand_ids[idx]
            if target_brand_id is None and ex_data.get("matched_brand_id"):
                try:
                    target_brand_id = int(ex_data.get("matched_brand_id"))
                except:
                    pass

            # --- 确定用户是否指定了品牌 ---
            has_assigned_brand = (target_brand_id is not None and target_brand_id != -999)
            assigned_brand_name = unique_brand[idx] if has_assigned_brand else "无"

            search_res = []

            # === 搜索策略 A：优先搜索指定品牌 (Strict) ===
            if has_assigned_brand:
                query_strict_brand = build_dynamic_query(
                    desc_data, cat_ids, package, package_std, keywords,
                    replace=do_replace_search,
                    assigned_brand_id=target_brand_id,
                    consumer_scene=is_consumer_scene(design_intention),
                    strict_category=True,
                    domestic_only=apply_domestic_filter,
                    lifecycle=True,
                    strict_brand=True  # 强制限制品牌
                )
                res_brand = search_by_desc(es, index_name, query_strict_brand, target_brand_id)
                search_res.extend(res_brand)

            # === 搜索策略 B：结果不足时，自动全网降级搜索 (Fallback) ===
            # 条件：没有指定品牌，或者指定品牌搜索结果太少
            if len(search_res) < 5:
                # 稍微放宽分类限制（如果已有部分结果）
                strict_cat_flag = True if len(search_res) == 0 else False

                query_global = build_dynamic_query(
                    desc_data, cat_ids, package, package_std, keywords,
                    replace=do_replace_search,
                    assigned_brand_id=None,  # 不指定ID，全网搜
                    consumer_scene=is_consumer_scene(design_intention),
                    strict_category=strict_cat_flag,
                    domestic_only=apply_domestic_filter,
                    lifecycle=True,
                    strict_brand=False
                )
                res_global = search_by_desc(es, index_name, query_global, None)

                # 去重合并
                existing_titles = {item['title'] for item in search_res}
                for item in res_global:
                    if item['title'] not in existing_titles:
                        search_res.append(item)
                        existing_titles.add(item['title'])

            # Agent Brand Recall (if needed)
            if agent_brand_ids and do_replace_search and not has_assigned_brand:
                desc_str = extraction_tasks[idx]['desc']
                agent_query = search_agent_recall_query(keywords, desc_str, domestic_only=apply_domestic_filter)
                agent_res = search_by_desc(es, index_name, agent_query)
                existing_titles = {item['title'] for item in search_res}
                count_added = 0
                for item in agent_res:
                    if item['title'] not in existing_titles and item.get('brandId') in agent_brand_ids:
                        search_res.insert(count_added, item)
                        count_added += 1
                        existing_titles.add(item['title'])

            # 候选排序
            search_res = sort_agent_brands_by_priority(search_res)

            # 【核心】：将Phase 1中跳过的 Exact Match (可能类别不对) 加回来，让LLM去甄别
            if idx in matched_data_store and final_results_unique[idx] is None:
                exact_cand = matched_data_store[idx]
                if exact_cand['title'] not in [x['title'] for x in search_res]:
                    search_res.insert(0, exact_cand)

            if search_res:
                if is_replace_search:
                    # 替代搜索逻辑
                    filtered_res = [x for x in search_res if x['title'] != orig_title]

                    # 默认填充
                    replacements_default = []
                    for item in filtered_res[:5]:
                        replacements_default.append({
                            "id": -1, "evaluate": "参数近似搜索", "核心参数": str(desc_data), "replace_data": item
                        })
                    if idx in final_results_unique and final_results_unique[idx]:
                        final_results_unique[idx]['replace_data'] = replacements_default
                        final_results_unique[idx]['match_data']['xcl核心参数'] = str(desc_data)

                    if filtered_res:
                        cand_db = {str(ri): build_compact_candidate_info(item, for_replacement=True) for ri, item in
                                   enumerate(filtered_res[:20])}
                        replace_rerank_tasks[idx] = {
                            "desc": unique_descriptions[idx], "database": cand_db, "raw_list": filtered_res[:20],
                            "title_std": re.sub(r'[^a-zA-Z0-9]', '', orig_title)
                        }
                else:
                    # 描述搜索逻辑
                    cand_db = {str(k): build_compact_candidate_info(item, for_replacement=False) for k, item in
                               enumerate(search_res)}
                    rerank_tasks[idx] = {
                        "desc": f"Desc Search: {extraction_tasks[idx]['desc']}",
                        "database": cand_db,
                        "raw_list": search_res,
                        "is_desc_search": True,
                        "user_assigned_brand_name": assigned_brand_name  # 传入品牌名给 LLM
                    }
                    extraction_tasks[idx]['extracted_param_str'] = str(desc_data)
            else:
                if not is_replace_search and idx not in final_results_unique:
                    final_results_unique[idx] = {"id": -1, "source": "search_fail", "match_data": {},
                                                 "replace_data": [], "evaluate": "参数搜索无结果"}
    logger.info(f"Batch Stage 2耗时: ({time.time() - st})")
    with open(f"{output_dir}/final_results_unique_23.json", "w", encoding="utf-8") as f:
        json.dump(final_results_unique, f, ensure_ascii=False, indent=2)

    # ================= Phase 4: 批量方案重排 (优化版) =================
    st = time.time()

    # 确保 rerank_results 即使为空也不会报错
    rerank_results = {}
    if rerank_tasks:
        logger.info(f"Batch Stage 4: LLM Match Rerank ({len(rerank_tasks)})")
        rerank_results = batch_search_data_rerank(rerank_tasks, ds_chat, design_intention)
        with open(f"{output_dir}/rerank_results.json", "w", encoding="utf-8") as f:
            json.dump(rerank_results, f, ensure_ascii=False, indent=2)
        with open(f"{output_dir}/rerank_tasks.json", "w", encoding="utf-8") as f:
            json.dump(rerank_tasks, f, ensure_ascii=False, indent=2)

    processing_indices = set(rerank_results.keys()) | set(
        i for i, res in enumerate(final_results_unique) if res and res.get('source') == 'title_exact_match'
    )
    with open(f"{output_dir}/processing_indices.txt", "w", encoding="utf-8") as f:
        for idx in processing_indices:
            f.write(f'{idx}\n')

    for idx in processing_indices:
        # 获取 Match Data
        best_match = None

        # Case A: 来源于 LLM Rerank
        if idx in rerank_results and idx in rerank_tasks:
            task_info = rerank_tasks[idx]
            raw_list = task_info['raw_list']
            res = rerank_results[idx]
            selected_id = -1
            try:
                selected_id = int(res.get('id'))
            except:
                pass

            if (selected_id < 0 or selected_id >= len(raw_list)) and raw_list:
                # 只有当 LLM 明确选了 ID 时才通过。如果 LLM 认为都不行(-1)，则不强行指定
                if selected_id == -1:
                    final_results_unique[idx] = {"id": -1, "source": "no_match_by_llm", "match_data": {},
                                                 "replace_data": [], "evaluate": "LLM判断无匹配器件"}
                    continue

                # Fallback to Top 1 if ID invalid but list exists (Unlikely with logic above)
                selected_id = 0
                res['evaluate'] = "自动选择(Top1)"
                res['核心参数'] = "Top Match"

            if 0 <= selected_id < len(raw_list):
                best_match = raw_list[selected_id]
                best_match['xcl核心参数'] = str(res.get('核心标签', ''))
                best_match['核心参数'] = str(res.get('核心标签', ''))
                if task_info.get("is_desc_search") and idx in extraction_tasks:
                    best_match['xcl核心参数'] = extraction_tasks[idx].get('extracted_param_str', '')

                final_results_unique[idx] = {
                    "id": selected_id,
                    "source": "description_search" if task_info.get("is_desc_search") else "title_rerank",
                    "match_data": best_match,
                    "replace_data": [],
                    "evaluate": res.get("evaluate", "")
                }

        # Case B: 来源于精确匹配
        if idx < len(final_results_unique) and final_results_unique[idx] is not None:
            best_match = final_results_unique[idx]['match_data']

        # 既不是LLM的有效返回，也不是精确匹配（说明是纯幻觉ID），直接跳过
        else:
            continue

        # --- [关键优化] 无论来源如何，如果需要寻找替代且余量不足，强制执行扩展搜索 ---
        if best_match:
            matched_data_store[idx] = best_match
            # 复用之前的逻辑判断 apply_domestic_filter
            has_brand_assigned = bool(unique_brand[idx] and unique_brand[idx].strip())
            is_auto_replace_mode = unique_auto[idx]
            is_domestic_required = unique_domestic[idx]
            apply_domestic_filter = False
            if not has_brand_assigned and is_auto_replace_mode and is_domestic_required:
                apply_domestic_filter = True
            # 获取已有的 raw_list 用于排除
            raw_list = rerank_tasks[idx]['raw_list'] if idx in rerank_tasks else [best_match]
            remainder_list = [x for x in raw_list if x['title'] != best_match['title']]

            # 只有当候选列表不足 且 (用户要求替换 或 自动替换) 时才触发
            in_agent = best_match.get("brandId") in agent_brand_ids
            need_auto = unique_auto[idx] and not in_agent
            do_replace = unique_replace[idx] or need_auto

            # 如果 remainder_list 足够，直接推入 Stage 5
            if len(remainder_list) >= 2:
                cand_db = {str(ri): build_compact_candidate_info(item, for_replacement=True) for ri, item in
                           enumerate(remainder_list[:20])}
                replace_rerank_tasks[idx] = {
                    "desc": unique_descriptions[idx], "database": cand_db, "raw_list": remainder_list[:20],
                    "title_std": re.sub(r'[^a-zA-Z0-9]', '', best_match['title'])
                }
                # 设置保底
                default_replacements = []
                for item in remainder_list[:5]:
                    default_replacements.append({
                        "id": -1, "evaluate": "同批次搜索结果", "核心参数": best_match.get('xcl核心参数', ''),
                        "replace_data": item
                    })
                final_results_unique[idx]['replace_data'] = default_replacements

            # 如果不足，且需要寻找替代，则强制触发扩展搜索 (Expanded Search)
            elif do_replace:
                try:
                    # 构建扩展查询
                    should_clauses = [{"terms": {"xccCategoryIds": best_match.get("xccCategoryIds", [])}}]

                    # 尝试从attrInfo中提取关键词
                    desc_kws = [kv['attrValues'] for kv in best_match.get('attrInfo', [])[:5] if
                                len(str(kv.get('attrValues', ''))) < 20]
                    if desc_kws:
                        kw_str = " ".join(desc_kws)
                        should_clauses.append({"match": {"description": kw_str}})
                        should_clauses.append({"match": {"paramJson": kw_str}})

                    filter_clauses = [{"term": {"showFlag": 1}}]
                    if apply_domestic_filter:
                        filter_clauses.append({"terms": {"brandRegion": [1, 2, 158, 344]}})
                    should_clauses.append(
                        {"constant_score": {"filter": {"terms": {"brandId": agent_brand_ids}}, "boost": 20}})
                    should_clauses.append(
                        {"constant_score": {"filter": {"terms": {"lifecycleStatus": ["量产"]}}, "boost": 12}})
                    should_clauses.append(
                        {"constant_score": {"filter": {"terms": {"lifecycleStatus": ["试产", "衰退期", "逐步淘汰"]}},
                                            "boost": 6}})

                    q_body = {"query": {
                        "bool": {"must": filter_clauses, "should": should_clauses, "minimum_should_match": 1}},
                        "size": 30}

                    search_raw = es.search(index=index_name, body=q_body)
                    # hits_sorted = sort_agent_brands_by_priority(
                    #     [h['_source'] for h in search_raw['hits']['hits']])
                    hits_sorted = sort_agent_brands_by_priority(processing_hits(search_raw['hits']['hits']))
                    # 过滤掉自己
                    filtered = [h for h in hits_sorted if h['title'] != best_match['title']]

                    if filtered:
                        cand_db = {str(ri): build_compact_candidate_info(item, for_replacement=True) for
                                   ri, item in enumerate(filtered[:20])}
                        replace_rerank_tasks[idx] = {
                            "desc": unique_descriptions[idx], "database": cand_db, "raw_list": filtered[:20],
                            "title_std": re.sub(r'[^a-zA-Z0-9]', '', best_match['title'])
                        }
                        # 设置保底
                        default_replacements = []
                        for item in filtered[:5]:
                            default_replacements.append({
                                "id": -1, "evaluate": "扩展搜索结果", "核心参数": best_match.get('xcl核心参数', ''),
                                "replace_data": item
                            })
                        if 'replace_data' in final_results_unique[idx]:
                            final_results_unique[idx]['replace_data'].extend(default_replacements)
                        else:
                            final_results_unique[idx]['replace_data'] = default_replacements
                except Exception as e:
                    logger.error(f"Expanded search failed for ID {idx}: {e}")

    logger.info(f"Batch Stage 4耗时: ({time.time() - st})")

    # ================= Phase 5: 批量替代料筛选 (优化版) =================
    st = time.time()
    with open(f"{output_dir}/final_results_unique.json", "w", encoding="utf-8") as f:
        json.dump(final_results_unique, f, ensure_ascii=False, indent=2)
    if replace_rerank_tasks:
        logger.info(f"Batch Stage 5: LLM Replace Rerank ({len(replace_rerank_tasks)})")
        with open(f"{output_dir}/rep_rerank.json", "w", encoding="utf-8") as f:
            json.dump(replace_rerank_tasks, f, ensure_ascii=False, indent=2)
        rep_results = batch_replace_data_rerank(replace_rerank_tasks, ds_chat, design_intention)
        with open(f"{output_dir}/rep_result.json", "w", encoding="utf-8") as f:
            json.dump(rep_results, f, ensure_ascii=False, indent=2)
        for idx, res_list in rep_results.items():
            if not final_results_unique[idx]: continue

            task = replace_rerank_tasks[idx]
            raw = task['raw_list']
            replacements = []

            for item in res_list:
                if isinstance(item, List) and len(item) == 3:
                    rid = int(item[0])
                    evaluate = item[1].strip()
                    core_tags = item[2].strip()
                    if 0 <= rid < len(raw):
                        replacements.append({
                            "id": rid,
                            "evaluate": evaluate if evaluate else "LLM推荐",
                            "核心参数": core_tags,
                            "replace_data": raw[rid]
                        })

            # [优化]: 如果 LLM 返回了有效结果，则覆盖保底数据
            if replacements:
                final_results_unique[idx]['replace_data'] = replacements

            match_data = final_results_unique[idx].get('match_data', {})
            in_agent = match_data.get("brandId") in agent_brand_ids

            # 自动替换逻辑：如果 LLM 推荐了更好的（通常是代理品牌），则进行交换
            if unique_auto[idx] and not in_agent and replacements:
                print(f"开启自动替换:")
                top_rep = replacements[0]
                new_match = top_rep['replace_data']
                new_match['xcl核心参数'] = top_rep['核心参数']
                new_match['is_auto_replaced'] = True
                new_match['original_title'] = match_data.get('title')
                final_results_unique[idx]['match_data'] = new_match
                final_results_unique[idx]['evaluate'] = f"自动替换: {top_rep['evaluate']}"
                final_results_unique[idx]['replace_data'] = replacements[1:]

    with open(f"{output_dir}/final_results_rep.json", "w", encoding="utf-8") as f:
        json.dump(final_results_unique, f, ensure_ascii=False, indent=2)
    final_output = [None] * original_count
    for i in range(count):
        if final_results_unique[i] is None:
            final_results_unique[i] = {"id": -1, "source": "no_result", "match_data": {}, "replace_data": [],
                                       "evaluate": "未找到匹配"}

    for sig, indices in task_signature_to_orig_indices.items():
        unique_idx = unique_tasks_map[sig]
        result = final_results_unique[unique_idx]
        for orig_i in indices:
            final_output[orig_i] = result

    logger.info(f"Batch Stage 5耗时: ({time.time() - st})")
    logger.info(f"Batch Process Finished. Total Time: {time.time() - start_time:.2f}s")
    return final_output