import asyncio
import json
import sys
from collections import defaultdict
from functools import partial
from pathlib import Path

import pandas as pd
from openai import AsyncOpenAI
from openpyxl import load_workbook
from pydantic import BaseModel, Field

sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from projects.hwhms.common.volcengine_api import HistoryItem

from nanoai.model.llm import allm_output
from nanoai.utils.nl_repr import nl_repr
from nanoai.utils.data_concept import ClsResult
from nanoai.utils.async_utils import amap

from projects.hwhms.common.client import get_openai_client
from projects.hwhms.car_a.core_rewrite import QueryRewrite, RewriteResult
from projects.hwhms.car_a.core import IntentClassifier
from projects.hwhms.common.cls_analyze import ClsMetric, ResultState, cls_evaluate, cls_evaluate_twice
from projects.hwhms.datasets import Sample, DATASET_ROOT, DATASET_RELEASE_ROOT


sys.path.append(str(Path(__file__).parent.parent.parent.parent))

SHEET_NAMES = ['传统垂域', '出行助手', '搜索助手', '趣味助手', '用车助手']

st_4500_file_path = DATASET_RELEASE_ROOT / "单轮意图分类_4500.xlsx"
mt_7000_file_path = DATASET_RELEASE_ROOT / "多轮意图分类_7000.xlsx"
hw_must_pass_file_path = DATASET_ROOT / '1018' / "hwhms_must_pass_datasets.xlsx"

rewrite_file_path = DATASET_ROOT / "rewrite.xlsx"

CATEGORY_INDEX = {
    "传统垂域": 0,
    "出行助手": 1,
    "搜索助手": 2,
    "用车助手": 3,
    "趣味助手": 4,
}

CATEGORY_INDEX_CAR_B = {
    "传统垂域": 0,
    "百科闲聊": 1,
}


def load_dataset_from_excel(file_path: str, sheet_names: list[str], query_column: int = 0, history_column: int = 1, expected_column: int = 2) -> list[Sample]:
    queries: list[Sample] = []

    sheets = pd.read_excel(file_path, sheet_name=None)

    for sheet_name, df in sheets.items():
        if sheet_name not in sheet_names:
            continue

        # 获取当前 Sheet
        for index, row in df.iterrows():
            print(row.iloc[query_column], row.iloc[history_column], row.iloc[expected_column])
            history_str=row.iloc[history_column] if not pd.isna(row.iloc[history_column]) else None
            queries.append(Sample(query=row.iloc[query_column], history=history_str if history_str else None, expected=row.iloc[expected_column]))

    return queries

def load_dataset_from_excel_hwhms_must_pass(file_path: str, sheet_names: list[str]) -> list[Sample]:
    queries: list[Sample] = []
    sheets = pd.read_excel(file_path, sheet_name=None)

    for sheet_name, df in sheets.items():
        if sheet_name not in sheet_names:
            continue

        for index, row in df.iterrows():
            history_str = row.iloc[1];
            history = ""
            if pd.isna(history_str):
                history = ""
            else:
                try:
                    history_list = json.loads(history_str)
                    for his in history_list:
                        # 跳过空字符串
                        if not his:
                            continue
                        # 如果his是字符串，需要再解析一次
                        if isinstance(his, str):
                            try:
                                his = json.loads(his)
                            except json.JSONDecodeError as e:
                                print(f"警告: 无法解析历史记录字符串: {his[:100]}, 错误: {e}")
                                continue
                        # 确保his是字典且包含必要的键
                        if isinstance(his, dict) and 'q' in his and 'a' in his:
                            history += f"'用户:'{his['q']}, '助手:'{his['a']}\n"
                except json.JSONDecodeError as e:
                    print(f"警告: 无法解析历史记录: {history_str[:100]}, 错误: {e}")
                    history = ""
            queries.append(Sample(query=row.iloc[0], history=history, expected=row.iloc[2]))
    
    return queries

def parse_multi_round_data(row: pd.Series) -> tuple[str, str, list[dict]]:
    """解析多轮对话数据
    
    :param row: DataFrame的一行数据
    :return: (当前query, 当前intent, 历史记录列表)
    
    Excel 列结构：
    - iloc[1,2]: q1, q1_intent
    - iloc[3,4]: q2, q2_intent
    - iloc[5,6]: q3, q3_intent
    - iloc[7,8]: q4, q4_intent
    - iloc[9,10]: q5, q5_intent
    """
    # 提取所有轮次的问题和意图（支持最多5轮对话）
    rounds = [
        (row.iloc[1], row.iloc[2]),   # q1, q1_intent_type
        (row.iloc[3], row.iloc[4]),   # q2, q2_intent_type
        (row.iloc[5], row.iloc[6]),   # q3, q3_intent_type
        (row.iloc[7], row.iloc[8]),   # q4, q4_intent_type
        (row.iloc[9], row.iloc[10]),  # q5, q5_intent_type
    ]
    
    # 找到最后一个有效的轮次（非空的问题）
    current_round_idx = 0
    for i, (q, _) in enumerate(rounds):
        if not pd.isna(q):
            current_round_idx = i
        else:
            break
    
    # 设置当前query和intent（最后一轮的数据）
    query = rounds[current_round_idx][0]
    intent = rounds[current_round_idx][1]
    
    # 构建历史记录（当前轮次之前的所有问题，answer为空）
    history = [
        {"q": rounds[i][0], "a": ""}
        for i in range(current_round_idx)
    ]
    
    return query, intent, history

def load_query_from_excel_multi_rounds(file_path: str):
    """
    解析excel内容，提取query和讯飞的语义
    """
    queries: list[Sample] = []
    try:
        ## 解析excel
        wb = load_workbook(file_path)
        sheets = pd.read_excel(file_path, sheet_name=None)

        for sheet_name, df in sheets.items():
            # 获取当前 Sheet
            ws = wb[sheet_name]

            # 遍历每一行
            for index, row in df.iterrows():

                ## 多轮跨域
                if sheet_name.__contains__("多轮跨域"):
                    # 解析多轮对话数据
                    query, intent, history = parse_multi_round_data(row)
                    ## 组装数据  循环history的内容，将q和a组装成一句话
                    # history_str = ""
                    # for h in history:
                    #     history_str += f"'用户:'{h['q']}, '助手:'{h['a']}\n"
                    queries.append(Sample(query=query, history=history, expected=intent))
                    continue           

    except FileNotFoundError:
        print(f"错误: 文件 '{file_path}' 不存在")
    except PermissionError:
        print(f"权限错误: 无法访问文件或目录，请检查权限设置")
    except Exception as e:
        print(f"处理过程中发生错误: {str(e)}")

    return queries

def load_samples(file_path: str) -> list[Sample]:
    samples: list[Sample] = []

    sheets = pd.read_excel(file_path, sheet_name=None)

    for sheet_name, df in sheets.items():
        # 获取当前 Sheet
        for index, row in df.iterrows():
            samples.append(Sample(query=row.iloc[5], history=row.iloc[4], expected=row.iloc[6]))

    return samples

async def judge_wrapper(pair: tuple[Sample, RewriteResult]):
    query = pair[0].query
    history = pair[0].history
    history_list = [history] if isinstance(history, str) else history
    gt_label = pair[0].expected
    model_output = pair[1].result
    
    return await judge_rewrite_result(
        query,
        history_list,
        gt_label,
        model_output,
    )

def run_classifier_and_collect_results(classifier, samples: list[Sample], output_structure: bool = True) -> tuple[list[int | None], list[int]]:
    """
    运行分类器并收集预测结果和真实标签
    
    Args:
        classifier: 分类器实例
        samples: 待测试的样本列表
        output_structure: 是否使用结构化输出
    
    Returns:
        tuple[list[int | None], list[int]]: (预测结果列表, 真实标签列表)
            - 预测结果列表：每个元素是类别索引或None（如果出错）
            - 真实标签列表：每个元素是真实类别的索引
    """
    # 创建异步包装函数，将query和对应的history一起传递
    def process_history(history):
        """处理 history 参数，确保格式正确"""
        if history is None:
            return None
        elif isinstance(history, str):
            try:
                # 尝试将 JSON 字符串解析为列表
                history_data = json.loads(history)
                
                # 确保解析出来的是列表
                if not isinstance(history_data, list):
                    print(f"⚠️  警告: history 不是列表类型: {type(history_data)}")
                    return None
                
                # 转换为 HistoryItem 对象列表
                history_list = []
                for item in history_data:
                    if isinstance(item, dict) and 'q' in item and 'a' in item:
                        history_list.append(HistoryItem(**item))
                    else:
                        print(f"⚠️  警告: history 项格式不正确: {item}")
                
                return history_list if history_list else None
                
            except json.JSONDecodeError as e:
                print(f"⚠️  JSON 解析失败: {e}, 原始数据: {history[:100]}...")
                return None
            except Exception as e:
                print(f"⚠️  处理 history 时出错: {e}")
                return None
        elif isinstance(history, list):
            # 如果已经是列表，检查是否需要转换
            if history and isinstance(history[0], dict):
                return [HistoryItem(**h) for h in history]
            return history
        else:
            return history
        
    
    async def run_with_history(params):
        query, hist = params
        return await classifier.run(query, hist, output_structure=output_structure)
    
    # 将samples转换为参数列表（只传递必要的参数）
    params_list = [(s.query, process_history(s.history)) for s in samples]
    
    res, stats = asyncio.run(amap(
        run_with_history, 
        params_list, 
        progress=True,
        max_concurrent=100  # 增加并发数
    ))
    stats.print()
    
    pred: list[int | None] = []
    result: list[str | ClsResult | None] = []
    
    for i, sample in enumerate(samples):
        # 检查结果是否是异常
        if isinstance(res[i], Exception):
            print(f"调用错误: query={sample.query}, error={nl_repr(res[i])}")
            pred.append(None)
            result.append(None)
            continue
        
        # 处理IntentClsResult对象
        intent_result = res[i]
        
        # 检查是否是异常
        if isinstance(intent_result, Exception):
            print(f"分类错误: query={sample.query}, error={nl_repr(intent_result)}")
            pred.append(None)
            result.append(None)
            continue
        
        # 从IntentClsResult中提取domain和category
        domain = intent_result.domain
        category = intent_result.category
        
        pred.append(CATEGORY_INDEX[domain])
        result.append(intent_result)
    
    return pred, result

def save_cls_metrics(cls_metrics: ClsMetric, samples: list[Sample], results: list[list[str | ClsResult | None]], output_path: Path):
    """
    将分类指标保存到json文件
    """
    json_list = []
    result_state_list: list[ResultState] = cls_metrics.states
    for i in range(len(result_state_list)):
        json_data = {
            "query": samples[i].query,
            "history": samples[i].history,
            "expected": samples[i].expected,
            "result_state": result_state_list[i].value,
        }
        # 处理IntentClsResult对象
        if hasattr(results[0][i], 'domain'):
            # IntentClsResult对象
            json_data["result1"] = results[0][i].category
            json_data["result_reason1"] = results[0][i].reason or ""
            json_data["decision_path1"] = results[0][i].decision_path
        elif isinstance(results[0][i], ClsResult):
            json_data["result1"] = results[0][i].category
            json_data["result_reason1"] = results[0][i].reason or "unknown"
        else:
            json_data["result1"] = results[0][i]
            json_data["result_reason1"] = ""

        if len(results) > 1:
            if hasattr(results[1][i], 'domain'):
                # IntentClsResult对象
                json_data["result2"] = results[1][i].category
                json_data["result_reason2"] = results[1][i].reason or ""
                json_data["decision_path2"] = results[1][i].decision_path
            elif isinstance(results[1][i], ClsResult):
                json_data["result2"] = results[1][i].category
                json_data["result_reason2"] = results[1][i].reason or "unknown"
            else:
                json_data["result2"] = results[1][i]
                json_data["result_reason2"] = ""
        json_list.append(json_data)

    ## 根据json_list的result_state进行分组
    json_list_grouped = defaultdict(list)
    for json_data in json_list:
        json_list_grouped[json_data["result_state"]].append(json_data)

    json_list_grouped_result = []
    for result_state, json_data_list in json_list_grouped.items():
        json_list_grouped_result.append({
            "result_state": f"{result_state} : ({len(json_data_list)}) 条",
            "list": json_data_list
        })
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(json_list_grouped_result, f, indent=4, ensure_ascii=False)

def evaluate_classifier_new(list_classifier: list[IntentClassifier], samples : list[Sample],  label: str = "分类器", output_structure: bool = True):
    """
    通用的分类器评估函数
    
    Args:
        classifier: 分类器实例
        samples: 待测试的样本列表
        label: 分类器标签（用于打印）
        output_structure: 是否使用结构化输出
    
    Returns:
        ClsMetric: 分类指标对象，包含准确率、混淆矩阵、召回率、精确率等
    """
    # 运行分类器并收集结果
    gt: list[int] = [CATEGORY_INDEX[sample.expected] for sample in samples]
    cls_metrics: list[ClsMetric] = []
    results: list[list[str | ClsResult | None]] = []
    for classifier in list_classifier:
        pred, result = run_classifier_and_collect_results(classifier, samples, output_structure)
        cls_metrics.append(pred)
        results.append(result)

    if len(list_classifier) == 2:
        ## 计算两次分类结果的指标，用于分析分类算法输出结果不稳定的情况。
        cls_metric_diff = cls_evaluate_twice(cls_metrics[0], cls_metrics[1], gt, num_classes=len(CATEGORY_INDEX))
        cls_metric_diff.print(["传统垂域", "出行助手", "搜索助手", "用车助手", "趣味助手"])
        save_cls_metrics(cls_metric_diff, samples, results, DATASET_ROOT / "1203" / f"hwhms_data_cls_1021_results_{label}.json")
    else:
        cls_metric = cls_evaluate(cls_metrics[0], gt, num_classes=len(CATEGORY_INDEX))
        cls_metric.print(["传统垂域", "出行助手", "搜索助手", "用车助手", "趣味助手"])
        save_cls_metrics(cls_metric, samples, results, DATASET_ROOT / "1203" / f"hwhms_data_cls_1021_results_{label}.json")
    return cls_metrics

def run_single_turn_test(output_structure):
    """
    这里运行所有单轮对话数据集的测试。
    """
    classifier = IntentClassifier()
    # 使用intent_cls.xlsx文件
    queries = load_dataset_from_excel(str(st_4500_file_path), SHEET_NAMES)
    evaluate_classifier_new([classifier], queries, label="intent_cls", output_structure=output_structure)


def run_multi_turn_test(output_structure):
    """
    这里运行所有多轮对话数据集的测试。
    """
    classifier = IntentClassifier()
    queries = load_query_from_excel_multi_rounds(str(mt_7000_file_path))
    evaluate_classifier_new([classifier], queries, label=None, output_structure=output_structure)


def run_rewrite_test():
    """
    这里运行所有query重写数据集的测试。
    """
    rewrite = QueryRewrite()
    samples = load_samples(rewrite_file_path)

    print(f"运行rewrite，样本数量: {len(samples)}")    
    results, stats = asyncio.run(amap(partial(rewrite_with_sample, rewrite=rewrite), samples, progress=True))
    stats.print()

    print(f"运行judge，样本数量: {len(samples)}")
    judge_results, stats = asyncio.run(amap(judge_wrapper, zip(samples, results), progress=True))
    stats.print()

    output_path = DATASET_ROOT / "hwhms_rewrite_res.json"
    save_samples_results(samples, results, judge_results, output_path)
    print(f"已导出 {len(samples)} 条结果到 {output_path}")

def run_hwhms_must_pass_test(output_structure):
    """
    这里运行所有hwhms-must-pass数据集的测试。
    """
    classifier = IntentClassifier()
    queries = load_dataset_from_excel_hwhms_must_pass(str(hw_must_pass_file_path), SHEET_NAMES)
    evaluate_classifier_new([classifier], queries, label=None, output_structure=output_structure)
    

async def rewrite_with_sample(sample: Sample, rewrite: QueryRewrite) -> RewriteResult | str:
    return await rewrite.run(sample.query, sample.history, output_structure=True)

class BoolResult(BaseModel):
    """判断对错的结果。"""

    judgment: bool = Field(..., title="判断", description="判断对错的结果, True or False")
    reason: str = Field(..., title="原因", description="判断的原因。")

    def __nl_repr__(self) -> str:
        return f"{nl_repr(self.judgment)}。{self.reason}"


async def judge_rewrite_result(
    query: str,
    history: list[str],
    gt: str,
    model_output: str,
    /,
    client: AsyncOpenAI = get_openai_client(),
    **llm_params,
) -> BoolResult:

    with_gt = True

    if with_gt:
    
        prompt_template = """
如下是用户指令改写的任务。

输入为对话历史如下：
{his_str}

以及用户指令如下：
{query}

需要按照以下标准改写用户的指令：
- 改写后的用户指令是语义完整的句子, 脱离历史对话也完全可以理解
- 保持原表述的核心意图, 关键动作等信息，去除所有非必要内容
- 如果有"它"、"这个"、"那个"之类的指代词，将其替换为对话历史中指代的的具体实体
- 补全被省略的主语、宾语、动词等关键信息, 使得改写后的句子完整
- 去掉"好像"、"可能"、"大概"、"应该"等意图模糊的词
- 去掉"你"、"帮我"、"能不能"、"可以吗"、"吧"等客套语
- 去掉"不对"、"其实"、"更正"等澄清标记词

改写结果为：
{model_output}

标准答案为：
{gt}

请仔细理解上述输入的对话历史和用户指令，根据改写标准，判断改写的结果和标准答案是否相符。

请以json格式返回判断结果和判断理由。
"""
        prompt = prompt_template.format(
            query=query,
            his_str="\n".join(history),
            gt=gt,
            model_output=model_output,
        )
    else:
        prompt_template = """
如下是用户指令改写的任务。

输入为对话历史如下：
{his_str}

以及用户指令如下：
{query}

需要按照以下标准改写用户的指令：
- 改写后的用户指令是语义完整的句子, 脱离历史对话也完全可以理解
- 保持原表述的核心意图, 关键动作等信息，去除所有非必要内容
- 如果有"它"、"这个"、"那个"之类的指代词，将其替换为对话历史中指代的的具体实体
- 补全被省略的主语、宾语、动词等关键信息, 使得改写后的句子完整
- 去掉"好像"、"可能"、"大概"、"应该"等意图模糊的词
- 去掉"你"、"帮我"、"能不能"、"可以吗"、"吧"等客套语
- 去掉"不对"、"其实"、"更正"等澄清标记词

改写结果为：
{model_output}

请仔细理解上述输入的对话历史和用户指令，根据改写标准，判断改写的结果是否正确。

请以json格式返回判断结果和判断理由。
"""
        prompt = prompt_template.format(
            query=query,
            his_str="\n".join(history),
            model_output=model_output,
        )

    res = await allm_output(prompt, output_type=BoolResult, client=client, **llm_params)
    return res.output


def save_samples_results(samples: list[Sample], results: list, judge_results: list, output_path: Path):
    """将结果导出为JSON文件"""

    assert len(results) == len(samples), "results和samples的长度不一致"
    assert len(judge_results) == len(samples), "judge_results和samples的长度不一致"

    all_data = []

    for s, r, j in zip(samples, results, judge_results):
        if not isinstance(r, Exception):
            r = r.model_dump()
        else:
            r = str(r)

        if not isinstance(j, Exception):
            j = j.model_dump()
        else:
            j = str(j)

        all_data.append((s.model_dump(), r, j))
    
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=4)

def evaluate_classifier_new_car_b(list_classifier: list[IntentClassifier], samples : list[Sample],  label: str = "分类器", output_structure: bool = True):
    """
    通用的分类器评估函数
    
    Args:
        classifier: 分类器实例
        samples: 待测试的样本列表
        label: 分类器标签（用于打印）
        output_structure: 是否使用结构化输出
    
    Returns:
        ClsMetric: 分类指标对象，包含准确率、混淆矩阵、召回率、精确率等
    """
    # 运行分类器并收集结果
    gt: list[int] = [CATEGORY_INDEX_CAR_B[sample.expected] for sample in samples]
    cls_metrics: list[ClsMetric] = []
    results: list[list[str | ClsResult | None]] = []
    for classifier in list_classifier:
        pred, result = run_classifier_and_collect_results(classifier, samples, output_structure)
        cls_metrics.append(pred)
        results.append(result)

    if len(list_classifier) == 2:
        ## 计算两次分类结果的指标，用于分析分类算法输出结果不稳定的情况。
        cls_metric_diff = cls_evaluate_twice(cls_metrics[0], cls_metrics[1], gt, num_classes=len(CATEGORY_INDEX_CAR_B))
        cls_metric_diff.print(["传统垂域", "百科闲聊"])
        save_cls_metrics(cls_metric_diff, samples, results, DATASET_ROOT / "1126" / f"hwhms_data_cls_1021_results_{label}.json")
    else:
        cls_metric = cls_evaluate(cls_metrics[0], gt, num_classes=len(CATEGORY_INDEX_CAR_B))
        cls_metric.print(["传统垂域", "百科闲聊"])
        save_cls_metrics(cls_metric, samples, results, DATASET_ROOT / "1126" / f"hwhms_data_cls_1021_results_{label}.json")
    return cls_metrics


if __name__ == "__main__":

    # run_single_turn_test(False)
    run_multi_turn_test(False)
    ##run_rewrite_test()
    #run_hwhms_must_pass_test(False)
