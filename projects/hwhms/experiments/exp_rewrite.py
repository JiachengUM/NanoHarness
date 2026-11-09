import asyncio
import json
from pathlib import Path
import sys
from typing import override
import pandas as pd

sys.path.append(str(Path(__file__).parent.parent.parent.parent))
from nanoai.model.config import ModelName
from projects.hwhms.car_a.run_test import judge_wrapper, load_samples, save_samples_results, rewrite_with_sample, judge_rewrite_result
from projects.hwhms.car_a.core_rewrite import QueryRewrite, RewriteResult
from projects.hwhms.datasets import DATASET_ROOT, Sample
from nanoai.utils.async_utils import amap
from functools import partial
        

def rewrite_and_save(file_path: str):
    rewrite = QueryRewrite()
    samples = load_samples(file_path)

    print(f"运行rewrite，样本数量: {len(samples)}")    
    results, stats = asyncio.run(amap(partial(rewrite_with_sample, rewrite=rewrite), samples, progress=True))
    stats.print()

    print(f"运行judge，样本数量: {len(samples)}")
    judge_results, stats = asyncio.run(amap(judge_wrapper, zip(samples, results), progress=True))
    stats.print()

    output_path = DATASET_ROOT / "hwhms_rewrite_1017_res.json"
    save_samples_results(samples, results, judge_results, output_path)
    print(f"已导出 {len(samples)} 条结果到 {output_path}")


if __name__ == "__main__": 
    # 新的config模块不再需要switch_model，模型配置在core.py中直接设置
    filepath = DATASET_ROOT / "1017" / "rewrite.xlsx"
    rewrite_and_save(str(filepath))
