#!/usr/bin/env python3
"""
测试 SGM 意图分类器在测试数据集上的表现
"""
import asyncio
import csv
import json
import sys
from pathlib import Path
from functools import partial
from datetime import datetime
from enum import Enum

from nanoai.utils.async_utils import amap

from projects.SGM.core import IntentClassifier, ClassificationResult

# 配置：并发数（可根据需要调整）
# 可以通过命令行参数覆盖：python run_test.py 50
MAX_CONCURRENT = int(sys.argv[1]) if len(sys.argv) > 1 else 30


class ResultState(str, Enum):
    """分类结果状态"""
    CORRECT = "正确"
    WRONG = "错误"
    ERROR = "异常"


def load_test_data(csv_path: str) -> list[tuple[str, str]]:
    """从 CSV 文件加载测试数据
    
    Returns:
        list[tuple[str, str]]: (query, expected_category) 列表
    """
    test_data = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            query = row['query'].strip()
            result = row['result'].strip()
            if query and result:  # 跳过空行
                test_data.append((query, result))
    return test_data


async def classify_query(classifier: IntentClassifier, query: str) -> ClassificationResult | Exception:
    """对单个查询进行分类
    
    Returns:
        ClassificationResult | Exception: 分类结果对象或异常
    """
    try:
        result = await classifier.run(query)
        return result
    except Exception as e:
        return e


def extract_intent_type(result: ClassificationResult | Exception) -> str | None:
    """从分类结果中提取 intent_type
    
    Returns:
        str | None: 分类结果的 intent_type，如果出错返回 None
    """
    if isinstance(result, Exception):
        return None
    
    # 如果 prompt_result 存在，说明被判定为自定义类别或复杂意图
    # prompt_result 现在是字符串类型（类别名称）
    if result.prompt_result:
        return result.prompt_result
    
    # 否则使用 API 返回的 intent_type
    if not result.api_result.reject and result.api_result.intent:
        return result.api_result.intent.intent_type
    
    return None


def analyze_results(
    queries: list[str], 
    expected: list[str], 
    results: list[ClassificationResult | Exception],
    target_category: str | None = None
):
    """分析分类结果并生成详细信息
    
    Args:
        queries: 查询列表
        expected: 期望结果列表
        results: 分类结果列表
        target_category: 目标类别，如果指定则只统计该类别；None 表示统计所有
    """
    total = len(queries)
    correct = 0
    target_correct = 0  # 目标类别的正确数
    target_total = 0    # 期望为目标类别的总数
    
    errors = []
    detailed_results = []
    
    for i, (query, exp, result) in enumerate(zip(queries, expected, results)):
        # 如果指定了目标类别，只处理该类别的数据
        if target_category and exp != target_category:
            continue
        
        # 提取预测结果
        pred = extract_intent_type(result)
        
        # 判断结果状态
        if isinstance(result, Exception):
            state = ResultState.ERROR
            reason = str(result)
        elif pred == exp:
            state = ResultState.CORRECT
            reason = "分类正确"
        else:
            state = ResultState.WRONG
            reason = "分类错误"
        
        # 提取详细信息
        if isinstance(result, Exception):
            result_detail = {
                "query": query,
                "expected": exp,
                "predicted": None,
                "state": state.value,
                "reason": reason,
                "error": str(result),
            }
        else:
            # 提取分类理由
            classification_reason = ""
            if result.api_result.intent:
                classification_reason = result.api_result.intent.message or ""
            
            # 处理 rag_result（需要转换为字典）
            rag_result_dict = None
            if result.rag_result:
                rag_result_dict = {
                    "query": result.rag_result.query,
                    "max_similarity": result.rag_result.max_similarity,
                    "is_multi_intent": result.rag_result.is_multi_intent,
                }
            
            result_detail = {
                "query": query,
                "expected": exp,
                "predicted": pred,
                "state": state.value,
                "reason": reason,
                "classification_reason": classification_reason,
                "prompt_result": result.prompt_result,  # 现在是字符串
                "llm_raw_result": result.llm_raw_result,  # 现在是字符串
                "api_intent_type": result.api_result.intent.intent_type if result.api_result.intent else None,
                "is_reject": result.api_result.reject,
                "vehicle_check": result.vehicle_check,  # 现在是布尔值
                "rag_result": rag_result_dict,
            }
        
        detailed_results.append(result_detail)
        
        # 统计
        is_target = exp == target_category if target_category else True
        if is_target:
            target_total += 1
        
        if state == ResultState.CORRECT:
            correct += 1
            if is_target:
                target_correct += 1
        elif state == ResultState.WRONG:
            errors.append((i, query, exp, pred))
    
    # 如果指定了目标类别，total 应该等于该类别的总数
    if target_category:
        total = target_total
    
    return {
        'total': total,
        'correct': correct,
        'accuracy': correct / total if total > 0 else 0,
        'target_category': target_category or "全部",
        'target_total': target_total,
        'target_correct': target_correct,
        'target_accuracy': target_correct / target_total if target_total > 0 else 0,
        'errors': errors,
        'detailed_results': detailed_results,
    }


def save_results_to_json(analysis: dict, output_path: Path, category_name: str = "全部"):
    """将结果保存为 JSON 文件，按状态分组
    
    Args:
        analysis: 分析结果字典
        output_path: 输出文件路径
        category_name: 类别名称，用于显示
    """
    from collections import defaultdict
    
    detailed_results = analysis['detailed_results']
    
    # 按状态分组
    grouped_results = defaultdict(list)
    for result in detailed_results:
        state = result['state']
        grouped_results[state].append(result)
    
    # 构建输出结构
    output_data = []
    for state, results in grouped_results.items():
        output_data.append({
            "result_state": f"{state} : ({len(results)}) 条",
            "list": results
        })
    
    # 添加统计信息
    summary = {
        "类别": category_name,
        "总样本数": analysis['total'],
        "正确分类数": analysis['correct'],
        "总体准确率": f"{analysis['accuracy']:.2%}",
        "测试时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    
    final_output = {
        "summary": summary,
        "results_by_state": output_data,
    }
    
    # 保存到文件
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, indent=2, ensure_ascii=False)
    
    print(f"  - {category_name}: {output_path}")


async def main():
    """主测试函数"""
    import time
    from collections import Counter
    start_time = time.time()
    
    # 根据命令行参数选择测试文件
    # python run_test.py [并发数] [test|must]
    test_file = sys.argv[2] if len(sys.argv) > 2 else "test"
    if test_file == "must":
        csv_path = Path(__file__).parent / "datasets" / "must.csv"
    else:
        csv_path = Path(__file__).parent / "datasets" / "test.csv"
    
    print(f"加载测试数据: {csv_path}")
    
    test_data = load_test_data(str(csv_path))
    queries = [q for q, _ in test_data]
    expected = [e for _, e in test_data]
    
    # 统计所有类别
    category_counts = Counter(expected)
    
    print(f"测试样本数: {len(test_data)}")
    for category, count in category_counts.most_common():
        print(f"  - {category}: {count} 条")
    print(f"并发数: {MAX_CONCURRENT}")
    print("\n开始测试...\n")
    
    # 创建分类器
    classifier = IntentClassifier()
    
    # 批量分类（带进度条）
    # 使用配置的并发数，适合 I/O 密集型任务（LLM API 调用）
    classify_fn = partial(classify_query, classifier)
    results, stats = await amap(classify_fn, queries, progress=True, max_concurrent=MAX_CONCURRENT)
    
    stats.print()
    
    # 分析结果
    print("\n分析结果中...")
    
    # 获取所有类别
    all_categories = sorted(category_counts.keys())
    analyses = {}
    
    # 对每个类别进行分析
    for category in all_categories:
        print(f"  分析{category}数据...")
        analyses[category] = analyze_results(queries, expected, results, target_category=category)
    
    # 保存详细结果到 JSON 文件
    print("\n保存结果到 JSON 文件:")
    
    for category in all_categories:
        output_path = Path(__file__).parent / f"test_results_{category}.json"
        save_results_to_json(analyses[category], output_path, category)
    
    # 打印总耗时和统计信息
    total_time = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"总耗时: {total_time:.2f} 秒")
    print(f"平均每个 query: {total_time / len(queries):.3f} 秒")
    print(f"\n各类别准确率:")
    for category in all_categories:
        analysis = analyses[category]
        print(f"  {category}: {analysis['correct']}/{analysis['total']} (准确率: {analysis['accuracy']:.2%})")
    print(f"{'='*60}")
    
    # 清理资源：关闭所有 HTTP 会话
    from projects.SGM.common.rag import close_rag_session
    from projects.SGM.common.engine_api import close_volcengine_session
    await close_rag_session()
    await close_volcengine_session()


if __name__ == "__main__":
    asyncio.run(main())

