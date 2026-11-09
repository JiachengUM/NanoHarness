#!/usr/bin/env python3
"""测试 IntentClassifier 性能，自定义意图分类LLM + 火山意图API"""

import asyncio
import time
from statistics import mean, stdev
from typing import Any
from tqdm.asyncio import tqdm
from rich import print
import numpy as np

from projects.mind.intent.zhiji import IntentClassifier
from projects.mind.intent.alg.volc_intent import close_volcengine_session


async def test_single_run(classifier: IntentClassifier, query: str) -> dict[str, float]:
    """单次测试，返回各项耗时"""
    # LLM 分类
    llm_start = time.time()
    await classifier._run_llm_cls(query)
    llm_time = (time.time() - llm_start) * 1000
    
    # 火山引擎 API
    api_start = time.time()
    await classifier._run_api(query=query)
    api_time = (time.time() - api_start) * 1000
    
    # 完整流程（并行）
    full_start = time.time()
    await classifier.run(query)
    full_time = (time.time() - full_start) * 1000
    
    return {
        "llm_time": llm_time,
        "api_time": api_time,
        "full_time": full_time,
    }

def remove_outliers(times: list[float], remove_min_max: bool = True) -> list[float]:
    """去除异常值（最大最小值）
    
    Args:
        times: 时间列表
        remove_min_max: 是否去除最大最小值
        
    Returns:
        处理后的时间列表
    """
    if not remove_min_max or len(times) <= 2:
        return times
    
    sorted_times = sorted(times)
    # 去除最小值和最大值
    return sorted_times[1:-1]

def calculate_stats(times: list[float]) -> dict[str, int]:
    """计算统计信息（平均、标准差、最小、最大）
    
    Args:
        times: 时间列表（毫秒）
        
    Returns:
        包含统计信息的字典
    """
    # 分位数计算（95line/99line，行业常用性能指标）
    # np.percentile返回float，插值方式选linear（默认），保证结果连续
    p95 = np.percentile(times, 95)
    p99 = np.percentile(times, 99)
    return {
        "平均": int(round(mean(times))),
        "标准差": int(round(stdev(times))) if len(times) > 1 else 0,
        "最小": int(round(min(times))),
        "最大": int(round(max(times))),
        "95line": int(round(p95)),
        "99line": int(round(p99)),
    }

async def test_performance(
    query: str = "打开头顶上的那个盖子", 
    test_counts: list[int] = [1, 10, 100],
    remove_min_max: bool = True
) -> dict[str, Any]:
    """性能测试，返回统计结果
    
    Args:
        query: 测试查询
        test_counts: 测试次数列表
        remove_min_max: 是否去除最大最小值
        
    Returns:
        包含各项统计信息的字典
    """
    classifier = IntentClassifier()
    results_summary: dict[str, dict[str, Any]] = {}
    
    for test_count in test_counts:
        # 执行多次测试
        results: list[dict[str, float]] = []
        
        for _ in tqdm(range(test_count), desc=f"测试 {test_count} 次"):
            result = await test_single_run(classifier, query)
            results.append(result)
        
        # 提取各项耗时
        llm_times = [r["llm_time"] for r in results]
        api_times = [r["api_time"] for r in results]
        full_times = [r["full_time"] for r in results]

        # 去除异常值（如果启用）
        if remove_min_max and test_count > 2:
            llm_times = remove_outliers(llm_times, remove_min_max)
            api_times = remove_outliers(api_times, remove_min_max)
            full_times = remove_outliers(full_times, remove_min_max)
        
        # 计算统计信息
        llm_mean = mean(llm_times)
        api_mean = mean(api_times)
        full_mean = mean(full_times)
        
        results_summary[f"{test_count}次"] = {
            "自定义意图分类LLM": calculate_stats(llm_times),
            "火山意图API": calculate_stats(api_times),
            "完整流程": calculate_stats(full_times),
            "性能分析": {
                "串行总耗时": int(round(llm_mean + api_mean)),
                "并行理论耗时": int(round(max(llm_mean, api_mean))),
                "实际并行耗时": int(round(full_mean)),
                "加速比": float(f"{((llm_mean + api_mean) / full_mean):.2f}"),
            },
        }
    
    await close_volcengine_session()
    print(results_summary)
    return results_summary


if __name__ == "__main__":
    # 目前是串行，每次测试独立，不受其他测试影响，避免并发带来的资源竞争
    query = "打开头顶上的那个盖子"
    # 需要统计的次数
    test_counts = [10, ]
    results = asyncio.run(test_performance(query, test_counts))