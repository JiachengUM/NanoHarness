import asyncio
from collections import defaultdict
from functools import partial
from itertools import groupby
import json
from operator import itemgetter
from pathlib import Path
import sys
from typing import override
from openpyxl import load_workbook
import pandas as pd
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from projects.hwhms.common.domain.traditional import navigation_cat
from projects.hwhms.common.domain.travel_assistant import travel_cat

from projects.hwhms.common.domain.car_assistant import vehicle_other_cat
from projects.hwhms.common.domain.navigation_treval import poi_navigation_cat, poi_travel_cat

from projects.hwhms.common.constants import Domain
from projects.hwhms.common.rag import rag_search_traditional
from projects.hwhms.datasets import Sample
from nanoai.utils.data_concept import ClsResult
from nanoai.utils.nl_repr import nl_repr
from nanoai.utils.async_utils import amap
from projects.hwhms.car_a.core import DecisionPath, IntentClassifier, IntentClsResult, intent_cls, map_category_to_domain
from projects.hwhms.car_a.run_test import evaluate_classifier_new, parse_multi_round_data

SHEET_NAMES = ["搜索助手多轮跨域", "出行助手多轮跨域", "用车助手多轮跨域", "趣味助手多轮跨域"]

class IntentClassifierNew(IntentClassifier):
    def __init__(self):
        super().__init__()


    @override
    async def poi_cls(self, query: str, history: list[str] = [], output_structure: bool = False) -> tuple[str, ClsResult | str]:
        """
        POI 分类方法
        
        Returns:
            tuple[str, PoiClsResult | str]: (大类名称, 细分类别结果)
        """
        intent_categories = [poi_travel_cat, poi_navigation_cat]
        self.llm_params["model"] = "doubao-seed-1-6-flash-250828"
        # 统一处理 history 参数：转换为 list[str] 格式
        if history is None:
            history_list = []
        elif isinstance(history, str):
            history_list = [history] if history else []
        else:
            history_list = history
        if output_structure:
            return await intent_cls(
                query, 
                intent_categories, 
                history=history_list,
                output_type=ClsResult,
                output_hint="如果用户输入信息中包含指代内容(例如：这个、那个、它、第一个、这样 等),请根据历史对话，完成指代内容的填充之后，再进行意图分类。若用户在当前对话中针对上一轮已确定的目标（如地点、功能或信息）进行追问或操作，应直接继承上一轮的意图分类，不重新分类。请返回类别名称，判断的理由。",
                **self.llm_params)
        else:
            return await intent_cls(query, intent_categories, history=history_list, output_hint="如果用户输入信息中包含指代内容(例如：这个、那个、它、第一个、这样 等),请根据历史对话，完成指代内容的填充之后，再进行意图分类。若用户在当前对话中针对上一轮已确定的目标（如地点、功能或信息）进行追问或操作，应直接继承上一轮的意图分类，不重新分类。请返回类别名称。", **self.llm_params)
    
    @override
    async def run(self, query: str, history: list[str] = [], output_structure: bool = False,) -> IntentClsResult:
        """
        固定的对外接口，并行运行RAG判别和传统判别，RAG优先决定传统垂域
        
        Returns:
            IntentClsResult: 包含分类结果和决策路径的完整结果
        """

        # 统一处理 history 参数：转换为 list[str] 格式
        self.llm_params["model"] = "doubao-seed-1-6-flash-250715"
        if history is None:
            history_list = []
        elif isinstance(history, str):
            history_list = [history] if history else []
        else:
            history_list = history
        
        intent_categories = self.all_categories

        # 同时启动三个异步任务
        rag_task = asyncio.create_task(rag_search_traditional(query))
        
        if output_structure:
            intent_task = asyncio.create_task(intent_cls(
                query, 
                intent_categories, 
                history=history_list,
                output_hint="如果用户输入信息中包含指代内容(例如：这个、那个、它、第一个、这样 等),请根据历史对话，完成指代内容的填充之后，再进行意图分类。若用户在当前对话中针对上一轮已确定的目标（如地点、功能或信息）进行追问或操作，应直接继承上一轮的意图分类，不重新分类。请返回类别名称以及判断的理由。", 
                output_type=ClsResult,
                **self.llm_params))
        else:
            intent_task = asyncio.create_task(intent_cls(query, intent_categories, history=history_list, output_hint="如果用户输入信息中包含指代内容(例如：这个、那个、它、第一个、这样 等),请根据历史对话，完成指代内容的填充之后，再进行意图分类。若用户在当前对话中针对上一轮已确定的目标（如地点、功能或信息）进行追问或操作，应直接继承上一轮的意图分类，不重新分类。请返回类别名称。", **self.llm_params))

        poi_task = asyncio.create_task(self.poi_cls(query, history=history_list, output_structure=output_structure))

        # 将所有任务放入集合中，设置总超时时间
        # 将所有任务放入集合中，设置总超时时间
        tasks = {rag_task, intent_task, poi_task}
        rag_result = None
        output = None
        poi_cls_result_output = None
        pending_tasks = set()  # 在外部定义，避免作用域问题

        try:
            # 循环等待任务完成
            while tasks:
                # return_when=asyncio.FIRST_COMPLETED: 指定函数返回的条件。asyncio.FIRST_COMPLETED表示当第一个任务完成时（或超时，不是异常导致的）就返回。
                # done: 一个集合，包含已经完成的任务（即已经执行完毕或抛出异常的任务）。
                # pending: 一个集合，包含未完成的任务（即还在运行的任务）。
                # 超时时间20s。是因为本地测试环境，跑的很慢，平均时间十几秒
                # 如果任务发生了异常，会被放到done集合中，其他任务继续进行
                done, pending_tasks = await asyncio.wait(tasks, timeout=20.0, return_when=asyncio.FIRST_COMPLETED)
                
                if not done:
                    # 超时处理：取消所有未完成的任务
                    for task in pending_tasks:
                        task.cancel()
                    raise TimeoutError(f"任务执行超时（20秒）: query={query}")
                
                # 检查完成的任务
                for task in done:
                    tasks.remove(task)
                    if task == rag_task:
                        rag_result = task.result()
                        # 如果 RAG 判定为传统垂域，立即取消其他任务并返回
                        if rag_result.is_traditional:
                            for t in pending_tasks:
                                t.cancel()
                            return IntentClsResult(
                                domain=Domain.TRADITIONAL,
                                decision_path=DecisionPath.BY_RAG_TRADITIONAL,
                                category="传统垂域",
                                reason=f"RAG相似度 {rag_result.max_similarity:.3f} 超过阈值 0.92"
                            )
                    elif task == intent_task:
                        output = task.result()
                    elif task == poi_task:
                        poi_cls_result_output = task.result()

        except TimeoutError:  # 改为 TimeoutError
            # 超时处理：取消所有未完成的任务
            for task in pending_tasks:  # 使用外部定义的变量
                task.cancel()
            raise  # 重新抛出异常
        except Exception:
            # 其他异常也需要清理任务
            for task in tasks:
                if not task.done():
                    task.cancel()
            raise

        # RAG判断为非传统垂域，使用传统分类方法
        # 优先判断poi_cls_result_output
        if output_structure:
            if map_category_to_domain(poi_cls_result_output.category) in [Domain.TRADITIONAL, Domain.TRAVEL] and map_category_to_domain(output.category) in [Domain.TRADITIONAL, Domain.TRAVEL]:
                domain = map_category_to_domain(poi_cls_result_output.category)
                detailed_category = poi_cls_result_output
                decision_path = DecisionPath.BY_POI_CLS
            else:
                # 使用全类别分类结果
                domain = map_category_to_domain(output.category)
                detailed_category = output
                decision_path = DecisionPath.BY_ALL_CATEGORY_CLS
        else:
            if poi_cls_result_output in [Domain.TRADITIONAL, Domain.TRAVEL] and output in [Domain.TRADITIONAL, Domain.TRAVEL]:
                domain = map_category_to_domain(poi_cls_result_output)
                detailed_category = poi_cls_result_output
                decision_path = DecisionPath.BY_POI_CLS
            else:
                # 使用全类别分类结果
                domain = map_category_to_domain(output)
                detailed_category = output
                decision_path = DecisionPath.BY_ALL_CATEGORY_CLS
        

        # 构建最终结果
        if output_structure:
            # 结构化输出时，detailed_category是ClsResult对象
            category = getattr(detailed_category, 'category', None)
            reason = getattr(detailed_category, 'reason', None)
            decision_path = DecisionPath.BY_ALL_CATEGORY_CLS
        else:
            # 非结构化输出时，detailed_category是字符串（Domain枚举值）
            category = str(detailed_category) if detailed_category else None
            reason = None
            decision_path = DecisionPath.BY_ALL_CATEGORY_CLS
        
        result = IntentClsResult(
            domain=domain,
            decision_path=decision_path,
            category=category,
            reason=reason
        )
        
        return result
        


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

            if sheet_name not in SHEET_NAMES:
                continue
            # 获取当前 Sheet
            ws = wb[sheet_name]

            # 遍历每一行
            for index, row in df.iterrows():

                ## 多轮跨域
                if sheet_name.__contains__("多轮跨域"):
                    # 解析多轮对话数据
                    query, intent, history = parse_multi_round_data(row)
                    ## 组装数据  循环history的内容，将q和a组装成一句话
                    history_str = ""
                    for h in history:
                        history_str += f"'用户:'{h['q']}, '助手:'{h['a']}\n"
                    queries.append(Sample(query=query, history=history_str, expected=intent))
                    continue           

    except FileNotFoundError:
        print(f"错误: 文件 '{file_path}' 不存在")
    except PermissionError:
        print(f"权限错误: 无法访问文件或目录，请检查权限设置")
    except Exception as e:
        print(f"处理过程中发生错误: {str(e)}")

    return queries

def compare_and_validate():
    ## classifier_new = IntentClassifierNew()
    classifier = IntentClassifier()

    # step 1: 读取想要测试的数据，通常不是完整的测试集，而是“想要对比的部分，这个实验的改动可能影响的部分”。
    dataset_path = Path(".") / "projects" / "hwhms" / "datasets"    
    filepath = dataset_path / "1028" / "hwhms_multi_rounds.xlsx"
    queries: list[Sample] = load_query_from_excel_multi_rounds(filepath)

    ## 对queries进行分组，每个组包含相同的历史记录
    evaluate_classifier_new([classifier], queries, label="多轮跨域", output_structure=False)


       

if __name__ == "__main__":
    compare_and_validate()
