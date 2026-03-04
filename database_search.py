from elasticsearch import Elasticsearch
import re
import json
from langchain.prompts import ChatPromptTemplate
from openai import OpenAI
from json_repair import repair_json
import html
import hashlib

template_randk = '''
   # 角色：电子元器件领域专家

    # 任务目标
    从数据库中检索与用户设计需求最匹配的型号，输出该方案的ID和参数。

    # 输入参数
    1. **设计需求**： ##{intention}###
    2. **数据库**： ##{database}###
       数据结构：Python字典  
       - Key：型号ID（int格式）  
       - Value：参数描述（文本）  

    # 参数匹配规则
    1. **参数名称可能不同但含义相同**：数据库中参数名称可能与设计需求不同，但代表相同含义。例如：
        - "Fclock(HZ)" 等同于 "主频"
        - "RAM(kB)" 等同于 "内存"
        - "Core" 等同于 "内核"
        - "Flash memory(KB)" 等同于 "闪存"
        - "ADC (bit)" 等同于 "ADC位数"
        - 其他类似参数请根据上下文判断其含义

    2. **参数值匹配规则**：
        - 数字参数：选择数值最接近或等于设计需求的型号
        - 范围参数：选择包含设计需求数值的型号
        - 枚举参数：选择与设计需求完全一致的型号
        - 兼容性参数：当没有完全匹配时，选择参数兼容的器件

    3. **封装匹配规则**：
        - 封装信息必须完全一致（忽略大小写和特殊字符）
        - 例如：设计需求中的 "TSSOP20" 应匹配数据库中的 "TSSOP20" 或 "TSSOP-20"

    # 处理要求
    1. 进行参数匹配：设计需求中会有一些具体参数，从数据库中找到最满足这个参数的型号  
    2. 检索规则：从数据库中参数最满足的型号  

    # 输出前验证
    1. 如果设计需求中有封装的信息，输出的型号必须满足封装信息完全一致
    2. 输出型号的参数性能，必须满足设计需求的其他参数要求
    3. 数据库中如果没有参数完全一致的，可以选择参数兼容的器件
    4. 如果没有满足要求的型号，返回空

    #结果输出： 
       ```json
       {{
         "id": 型号ID, 
         "参数": 型号参数
       }}```
    如果是空则返回：
    ```json
       {{
       }}```
'''
prompt_template_rank = ChatPromptTemplate.from_template(template_randk)
client = OpenAI(
    base_url="https://api.deepseek.com",
    api_key='sk-3a577de0656e40158cfc145a942c04e2'
)
json_pattern = r'```json(.*?)```'

# 最大候选数量
MAX_CANDIDATES = 5000


def model_rank(description, candidates):
    message_search = prompt_template_rank.format_messages(intention=description, database=candidates)
    response_search = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "user", "content": message_search[0].content},
        ],
        stream=False
    )
    savecontent = response_search.choices[0].message.content
    with open('./tmp_%s.txt'%str(candidates[0])[:10], 'w') as f:
        f.write(savecontent)
    savecontent = message_search[0].content
    with open('./tmp_%s_1.txt' % str(candidates[0])[:10], 'w') as f:
        f.write(savecontent)
    matches_system = re.findall(json_pattern, response_search.choices[0].message.content, re.DOTALL)
    if matches_system:
        json_str = matches_system[0].strip()
        json_str = str(repair_json(json_str=json_str, return_objects=False))
        return json.loads(json_str)
    return None


def escape_query(text):
    if not text:
        return ""
    return re.sub(r'([\+\-=&|!(){}[\]^"~*?:\\/])', r'\\\1', html.escape(text))


def get_document_hash(doc):
    unique_str = f"{doc.get('title', '')}_{doc.get('brandName', '')}_{doc.get('officialJson', '')}"
    return hashlib.md5(unique_str.encode()).hexdigest()


# 封装前缀列表（用于识别有效封装信息）
PACKAGE_PREFIXES = [
    'QFN', 'QFP', 'LQFP', 'TQFP', 'BGA', 'SOP', 'SOIC', 'DIP', 'SOT', 'DFN',
    'LGA', 'TSSOP', 'SSOP', 'VQFN', 'WLCSP', 'PDIP', 'TO', 'CLCC', 'CPGA',
    'CQFP', 'PLCC', 'PQFP', 'TSOP', 'VSOP', 'SC-', 'SOT-', 'TO-', 'BQFP', 'CSP'
]


def extract_package(desc):
    if not desc:
        return None
    pattern = r'\b([A-Za-z]+[\s\-]*\d+[A-Za-z]*)\b'
    matches = re.findall(pattern, desc)
    if matches:
        for match in matches:
            std_str = re.sub(r'[^A-Za-z0-9]', '', match).upper()
            for prefix in PACKAGE_PREFIXES:
                if std_str.startswith(prefix.upper()):
                    return std_str
    return None


def process_candidates(candidates, package_std, description):
    if package_std:
        filtered_candidates = []
        for cand in candidates:
            if cand.get('packing') and cand.get('pdfUrl'):
                cand_packing = re.sub(r'[^A-Za-z0-9]', '', cand['packing']).upper()
                if package_std in cand_packing and len(cand['pdfUrl']):
                    filtered_candidates.append(cand)
        if filtered_candidates:
            candidates = filtered_candidates
    else:
        filtered_candidates = []
        for cand in candidates:
            if cand.get('pdfUrl'):
                if len(cand['pdfUrl']):
                    filtered_candidates.append(cand)
        if filtered_candidates:
            candidates = filtered_candidates
    if not candidates:
        return []

    model_json = {}
    model_input_length = 0
    for idx, cand in enumerate(candidates):
        official_json = cand.get('officialJson', '')
        paramJson = cand.get('paramJson')
        if official_json and official_json.strip() and official_json.strip() != '{}':
            json_str = str(cand['officialJson'])
            if package_std:
                json_str += str(cand.get('packing', ''))
            if model_input_length + len(json_str) < 15000:
                model_json[idx] = json_str
                model_input_length += len(json_str)
            else:
                break
        else:
            if paramJson:
                json_str = str(cand['paramJson'])
                if len(json_str.strip()) > 5:
                    if package_std:
                        json_str += str(cand.get('packing', ''))
                    # 检查是否超过大模型输入限制
                    if model_input_length + len(json_str) < 15000:  # 留有余量
                        model_json[idx] = json_str
                        model_input_length += len(json_str)
                    else:
                        break

    if description and model_json:
        enhanced_desc = description
        if package_std:
            enhanced_desc += f" [必须满足封装: {package_std}]"
        model_json = json.dumps(model_json,indent=2, ensure_ascii=False)
        ranked_candidate = model_rank(enhanced_desc, model_json)
        if ranked_candidate:
            best_idx = ranked_candidate['id']
            if best_idx < len(candidates):
                return [candidates[best_idx]]
    return []


def get_title_url(title, brandname, description=''):
    es = Elasticsearch(
        [
            "http://10.10.40.103:9200",
            "http://10.10.40.104:9200",
            "http://10.10.40.105:9200",
            "http://10.10.40.138:9200",
            "http://10.10.40.139:9200",
            "http://10.10.40.140:9200",
            "http://10.10.40.169:9200",
            "http://10.10.40.170:9200",
            "http://10.10.40.179:9200"
        ],
        http_auth=("App-FAE", "97zQUZQCy4NcYrJ3nS"),
    )
    if not es.ping():
        es.close()
        return []

    mapping = es.indices.get_mapping(index="xcc_ware_detail")
    propertites = mapping['xcc_ware_detail_new_20250627']["mappings"]["properties"].keys()
    index_name = ["xcc_ware_detail", "xcc_ware_detail_*"]
    source_fields = list(propertites)
    package_std = extract_package(description) if description else None

    # ===== 策略1=====
    if title:
        query_exact = {
            "query": {"match": {"title": title}},
            "_source": source_fields,
            "size": 10
        }
        response = es.search(index=index_name, body=query_exact)
        if response["hits"]["total"]["value"] > 0:
            candidates = []
            seen_hashes = set()
            for hit in response["hits"]["hits"]:
                doc = hit["_source"]
                doc_hash = get_document_hash(doc)
                if doc_hash not in seen_hashes:
                    candidates.append(doc)
                    seen_hashes.add(doc_hash)
            result = process_candidates(candidates, package_std, description)
            if result:
                return result

    # ===== 策略2=====
    if title:
        base_query = {
            "bool": {
                "must": [{"wildcard": {"title": f"{title.lower()}*"}}],
                "filter": []
            }
        }
        if description:
            escaped_desc = description
            base_query["bool"]["must"].append({
                "multi_match": {
                    "query": escaped_desc,
                    "fields": ["paramJson^3", "description^2", "title"],
                    "type": "best_fields"
                }
            })
        if brandname:
            base_query["bool"]["filter"].append({
                "bool": {
                    "should": [
                        {"term": {"brandName": brandname}},
                        {"term": {"nickBrandName": brandname}},
                        {"term": {"brandNameCn": brandname}}
                    ]
                }
            })
        query_prefix = {
            "query": base_query,
            "_source": source_fields,
            "size": 100
        }
        prefix_results = es.search(index=index_name, body=query_prefix)
        if prefix_results["hits"]["total"]["value"] > 0:
            candidates = []
            seen_hashes = set()
            for hit in prefix_results["hits"]["hits"]:
                doc = hit["_source"]
                doc_hash = get_document_hash(doc)
                if doc_hash not in seen_hashes:
                    candidates.append(doc)
                    seen_hashes.add(doc_hash)

    # ===== 策略3=====
    base_query = {
        "bool": {
            "must": [],
            "filter": []
        }
    }
    if description:
        escaped_desc = description
        base_query["bool"]["must"].append({
            "multi_match": {
                "query": escaped_desc,
                "fields": ["paramJson^3", "description^2"],
                "type": "best_fields"
            }
        })
    query_prefix = {
        "query": base_query,
        "_source": source_fields,
        "size": 100
    }
    prefix_results = es.search(index=index_name, body=query_prefix)
    if prefix_results["hits"]["total"]["value"] > 0:
        seen_hashes = set()
        for hit in prefix_results["hits"]["hits"]:
            doc = hit["_source"]
            doc_hash = get_document_hash(doc)
            if doc_hash not in seen_hashes:
                candidates.append(doc)
                seen_hashes.add(doc_hash)
    if candidates:
        result = process_candidates(candidates, package_std, description)
        if result:
            return result
    return []


if __name__ == '__main__':
    test_cases = [
        ("HC32F005", "小华半导体", "TSSOP20 Cortex-M0+ 48MHz 32KB Flash"),#TSSOP20
        ("LM2596S", "TI", "3A 150kHz 降压型 TO-263封装")  # TSSOP20
    ]

    for title, brand, desc in test_cases:
        print(f"\n{'=' * 50}")
        print(f"测试用例: {title} | {brand} | {desc}")
        results = get_title_url(title, brand, desc)
        if results:
            print(f"返回 {len(results)} 个结果")
            for idx, doc in enumerate(results):
                print(f"\n#{idx + 1} 型号: {doc.get('title')}")
                print(f"品牌: {doc.get('brandName')} | {doc.get('nickBrandName')}")
                param_json = doc.get('officialJson', '{}')
                print(f"参数: {param_json}...")
                print(f"PDF: {doc.get('pdfUrl')}")
        else:
            print("未找到匹配结果")