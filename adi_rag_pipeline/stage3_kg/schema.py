"""
Neo4j 知识图谱 schema。
实体：Solution, Product, Parameter, Category, SignalChain
关系：Solution -[:CONTAINS]-> Product, Product -[:HAS_PARAM]-> Parameter, Product -[:IN_CATEGORY]-> Category,
      Solution -[:HAS_SIGNAL_CHAIN]-> SignalChain
"""

# 节点标签
LABEL_SOLUTION = "Solution"
LABEL_PRODUCT = "Product"
LABEL_PARAMETER = "Parameter"
LABEL_CATEGORY = "Category"
LABEL_SIGNAL_CHAIN = "SignalChain"

# 关系类型
REL_CONTAINS = "CONTAINS"
REL_HAS_PARAM = "HAS_PARAM"
REL_IN_CATEGORY = "IN_CATEGORY"
REL_HAS_SIGNAL_CHAIN = "HAS_SIGNAL_CHAIN"

# Solution 属性
SOLUTION_ID = "solution_id"  # 唯一，如目录名
SOLUTION_TITLE = "title"
SOLUTION_PAGE_URL = "page_url"
SOLUTION_DESCRIPTION = "description"
SOLUTION_OVERVIEW = "overview"
SOLUTION_NAV_PATH = "navigation_path"

# Product 属性
PRODUCT_ID = "product_id"  # 唯一，可用 model 或 model+solution_id
PRODUCT_MODEL = "model"
PRODUCT_LINK = "product_link"
PRODUCT_DESCRIPTION = "description"

# Parameter 属性（从 extracted_params 来）
PARAM_NAME = "name"
PARAM_VALUE = "value"

# Category 属性
CATEGORY_NAME = "name"

# SignalChain 属性（来自 signal_chain_descriptions.json）
SIGNAL_CHAIN_ID = "chain_id"  # 唯一：solution_id::chain_id
SIGNAL_CHAIN_NAME = "list_name"
SIGNAL_CHAIN_DESCRIPTION = "description"
SIGNAL_CHAIN_IMAGE_URL = "image_url"
