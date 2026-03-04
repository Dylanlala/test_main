from elasticsearch import Elasticsearch


def get_title_url(title):
    es = Elasticsearch([
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
    mapping = es.indices.get_mapping(index="xcc_ware_detail")
    print(mapping.keys(),555555555555555)
    propertites = mapping['xcc_ware_detail_new_20251108']["mappings"]["properties"].keys()
    print(propertites,66666)


    if es.ping():
        print("Connected to Elasticsearch!")
    else:
        print("Failed to connect to Elasticsearch!")
        es.close()

    index_name = ["xcc_ware_detail", "xcc_ware_detail_*"]

    query_body = {
        "query": {
            "match": {
                "title": title
            }
        },
        "_source":list(propertites)#["title", "brandName", "brandId", "pdfUrl"]
    }
    response = es.search(index=index_name, body=query_body)
    hits = response["hits"]["hits"]
    docs = []
    for document in hits:
        doc = document["_source"]
        docs.append(doc)
    return docs


def auto_correct_missing_items(missing_items):
    es = Elasticsearch([
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
    suggestions = {}
    for model in missing_items:
        # 使用模糊查询检索近似物料
        query = {"query": {"match": {"title": {"query": model, "fuzziness": "AUTO"}}}}
        response = es.search(index="xcc_ware_detail", body=query)
        if response['hits']['hits']:
            suggestions[model] = [hit['_source']['title'] for hit in response['hits']['hits'][:3]]
    return suggestions

if __name__ == '__main__':
    title = "MOC3063SR2M"
    data = get_title_url(title)
    print(data)
    # suggestions = auto_correct_missing_items(["HC32F005"])
    # print("HC32F005",suggestions)
    for d in data:
        print(d.get('brandId'))
