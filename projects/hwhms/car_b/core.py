import asyncio
from typing import Any

from nanoai.utils.data_concept import ClsResult
from projects.hwhms.car_a.core import DecisionPath, IntentClsResult, intent_cls
from projects.hwhms.common.constants import Domain
from projects.hwhms.common.domain.navigation_treval import poi_navigation_cat, poi_travel_cat
from projects.hwhms.common.domain.traditional import call_cat, car_control_cat, car_home_cat, media_cat, other_cat, \
    schedule_cat, system_setting_cat, vehicle_status_cat
from projects.hwhms.common.rag import rag_search_traditional

CATEGORY_NAME_TO_DOMAIN_CAR_B = {
    
    # 百科闲聊 （复用car_a的搜索助手和趣味助手）
    "闲聊": "百科闲聊",
    # 搜索助手
    "新闻搜索": "百科闲聊",
    "百科问答": "百科闲聊",
    "多功能助手": "百科闲聊",
    
    # 传统垂域（traditional）
    "导航": "传统垂域",
    "车控": "传统垂域",
    "通话": "传统垂域",
    "播控": "传统垂域",
    "车况查询": "传统垂域",
    "日程": "传统垂域",
    "日常操作指令": "传统垂域",
    "车家互联": "传统垂域",
    "系统设置": "传统垂域",
    "兜底操作": "传统垂域",
    "地点推荐查询": "传统垂域",

}


class IntentClassifierCarB:
    def __init__(self):

        self.llm_params: dict[str, Any] = {
            "model": "doubao-seed-1-6-flash-250715",
            "stream": False,
            "temperature": 0.7,  # 降低温度，提高响应速度
            "top_p": 0.7,
            "max_tokens": 4000,  # 增加token限制
            "extra_body": {
                "thinking": {
                    "type": "disabled",
                }
            },
        }
        ## 在此新增car_b的新需求 prompt

        ## 知识库 是否需要替换成car_b的？

        ## 必过集合干预(传统垂域+出行助手+百科闲聊)


        # 定义所有类别列表，按大类分组，方便后续使用
        self.all_categories = [
            # 传统垂域
            car_control_cat, call_cat, 
            media_cat, vehicle_status_cat, schedule_cat, other_cat, car_home_cat, system_setting_cat,
            poi_travel_cat, poi_navigation_cat,
            # 百科闲聊 （复用car_a的搜索助手和趣味助手）
            #chat_cat,
            # 搜索助手
            #news_cat, encyclopedia_cat, long_tail_tricks_cat,
        ]


    async def run(self, query: str, 
        history: list[str] | str | None = None,
        output_structure: bool = False,
        ) -> IntentClsResult:
        """
        固定的对外接口，并行运行RAG判别和传统判别，RAG优先决定传统垂域
        
        Returns:
            IntentClsResult: 包含分类结果和决策路径的完整结果
        """

        # 统一处理 history 参数：转换为 list[str] 格式
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
                output_hint="如果用户输入信息中包含指代内容(例如：这个、那个、它、第一个、这样 等),请根据历史对话，完成指代内容的填充之后，再进行意图分类。请返回类别名称以及判断的理由。", 
                output_type=ClsResult,
                **self.llm_params))
        else:
            intent_task = asyncio.create_task(intent_cls(query, intent_categories, history=history_list, **self.llm_params))

        # 将所有任务放入集合中，设置总超时时间
        tasks = {rag_task, intent_task}
        rag_result = None
        output = None
        pending_tasks = set()  # 在外部定义，避免作用域问题

        try:
            # 循环等待任务完成
            while tasks:
                # return_when=asyncio.FIRST_COMPLETED: 指定函数返回的条件。asyncio.FIRST_COMPLETED表示当第一个任务完成时（或超时）就返回。
                # done: 一个集合，包含已经完成的任务（即已经执行完毕或抛出异常的任务）。
                # pending: 一个集合，包含未完成的任务（即还在运行的任务）。
                ## 超时时间20s。是因为本地测试环境，跑的很慢，平均时间十几秒
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
        # 构建最终结果
        if output_structure:
            # 结构化输出时，detailed_category是ClsResult对象
            domain = CATEGORY_NAME_TO_DOMAIN_CAR_B.get(output.category, "百科闲聊")
            category = getattr(output, 'category', None)
            reason = getattr(output, 'reason', None)
            decision_path = DecisionPath.BY_ALL_CATEGORY_CLS
        else:
            # 非结构化输出时，detailed_category是字符串（Domain枚举值）
            domain = CATEGORY_NAME_TO_DOMAIN_CAR_B.get(output, "百科闲聊")
            category = str(output) if output else None
            decision_path = DecisionPath.BY_ALL_CATEGORY_CLS
            reason = None
        
        result = IntentClsResult(
            domain=domain,
            decision_path=decision_path,
            category=category,
            reason=reason
        )
        
        return result