"""
RAG检索功能测试脚本
用于验证RAG检索器是否正常工作
"""

import os
import sys
from langchain_community.embeddings import HuggingFaceEmbeddings
from rag_expert_search import create_rag_retriever

def test_rag_retriever():
    """测试RAG检索器功能"""
    
    print("=" * 60)
    print("RAG专家知识库检索功能测试")
    print("=" * 60)
    
    # 1. 初始化向量化模型
    print("\n[步骤1] 初始化向量化模型...")
    try:
        embedding_model = HuggingFaceEmbeddings(
            model_name='../paraphrase-multilingual-MiniLM-L12-v2',
            cache_folder='/data/alg/fae/paraphrase-multilingual-MiniLM-L12-v2',
            model_kwargs={'local_files_only': True}
        )
        print("✓ 向量化模型初始化成功")
    except Exception as e:
        print(f"✗ 向量化模型初始化失败: {e}")
        print("提示: 请检查模型路径是否正确")
        return False
    
    # 2. 创建RAG检索器
    print("\n[步骤2] 创建RAG检索器...")
    data_path = './all_data_20.json'
    index_path = './expert_case_index'
    
    if not os.path.exists(data_path):
        print(f"✗ 数据文件不存在: {data_path}")
        return False
    
    try:
        # 首次运行设为 rebuild_index=True，后续可以设为 False
        rebuild = not os.path.exists(index_path) or not os.path.exists(
            os.path.join(index_path, 'index.faiss')
        )
        
        if rebuild:
            print("  首次运行，将构建索引（可能需要几分钟）...")
        else:
            print("  索引已存在，直接加载...")
        
        retriever = create_rag_retriever(
            embedding_model=embedding_model,
            data_path=data_path,
            index_path=index_path,
            rebuild_index=rebuild
        )
        
        if not retriever:
            print("✗ RAG检索器创建失败")
            return False
        
        print("✓ RAG检索器创建成功")
        
    except Exception as e:
        print(f"✗ RAG检索器创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 3. 测试检索功能
    print("\n[步骤3] 测试检索功能...")
    test_queries = [
        "需要设计一个医疗设备，使用STM32主控，12V输入3.3V输出",
        "设计一个电池管理系统，支持多节电池",
        "需要CAN通信接口的工业控制板",
        "设计一个信号采集系统，需要高精度ADC",
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n--- 测试查询 {i} ---")
        print(f"查询: {query}")
        
        try:
            similar_cases = retriever.retrieve_similar_cases(
                query=query,
                top_k=3,
                similarity_threshold=0.5
            )
            
            print(f"检索到 {len(similar_cases)} 个相似方案:")
            for j, case in enumerate(similar_cases, 1):
                print(f"  [{j}] {case['project_name']} (相似度: {case['similarity']:.2%})")
                print(f"      项目编号: {case['project_number']}")
                print(f"      模块数量: {len(case['module_details'])}")
            
            # 格式化输出
            formatted = retriever.format_cases_for_llm(similar_cases, max_tokens=500)
            if formatted:
                print("\n格式化后的文本（前200字符）:")
                print(formatted[:200] + "...")
            
        except Exception as e:
            print(f"✗ 检索失败: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = test_rag_retriever()
    sys.exit(0 if success else 1)
