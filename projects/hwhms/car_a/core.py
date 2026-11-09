import asyncio
import json
import logging
import time
from enum import StrEnum
from typing import Any, Optional, Type

from jinja2 import Template
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from nanoai.model.llm import allm, allm_output
from nanoai.utils.data_concept import ClsResult
from nanoai.utils.nl_repr import nl_repr
from projects.hwhms.common.category import Category
from projects.hwhms.common.client import get_openai_client
from projects.hwhms.common.constants import Domain
from projects.hwhms.common.domain.car_assistant import vehicle_cat, vehicle_other_cat, vehicle_system_cat
from projects.hwhms.common.domain.fun_assistant import chat_cat
from projects.hwhms.common.domain.navigation_treval import poi_navigation_cat, poi_travel_cat
from projects.hwhms.common.domain.search_assistant import encyclopedia_cat, long_tail_tricks_cat, news_cat
from projects.hwhms.common.domain.traditional import call_cat, car_control_cat, car_home_cat, media_cat, navigation_cat, \
    other_cat, schedule_cat, system_setting_cat, vehicle_status_cat
from projects.hwhms.common.domain.travel_assistant import travel_cat
from projects.hwhms.common.rag import RAG_TRADITIONAL_THRESHOLD, rag_search_must_pass, rag_search_traditional
from projects.hwhms.common.volcengine_api import HistoryItem

logger = logging.getLogger(__name__)

# ===================== 类别映射配置 =====================
# 根据 category name 映射到所属的大类
CATEGORY_NAME_TO_DOMAIN = {
    # 用车助手（car_assistant）
    "车机系统知识": "用车助手",
    "车辆知识": "用车助手", 
    "车辆其他知识": "用车助手",
    "车辆法规与车辆知识问答": "用车助手",
    
    # 搜索助手（search_assistant）
    "新闻搜索": "搜索助手",
    "百科问答": "搜索助手",
    "多功能助手": "搜索助手",
    
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
    
    # 出行助手（travel_assistant）
    "地点推荐查询": "出行助手",
}



class PoiQueryResult(BaseModel):
    """判断poi的结果。"""

    result: Optional[bool] = Field(None, title="判断", description="判断是否属于吃喝玩乐相关的地点的结果, True or False")
    poi_list: Optional[list[str]] = Field(None, title="匹配到的地点列表", description="匹配到的地点列表。")

    def __nl_repr__(self) -> str:
        return f"{nl_repr(self.judgment)}。{self.reason}"

async def is_entertainment_poi_query(query: str,
                                    client: AsyncOpenAI = get_openai_client(), 
                                    **llm_params) -> bool | tuple[bool, list[str]]:
    """
    判断query中是否包含吃喝玩乐相关的地点。
    
    Args:
        query: 用户输入的查询文本
        return_matched: 是否返回匹配到的地点列表，默认False
        
    Returns:
        结果和匹配到的地点名称。
    """
    from nanoai.model.config import get_default_model
    
    prompt_template = """
你是一个地点识别助手。请判断用户输入是否包含具体地点(不包含城市名)。

如果用户输入提到了地点, result字段返回true, 并返回地点列表。
如果用户输入没有提到地点, result字段返回false, poi_list为空数组。

当前用户输入："{user_input}"

请以json格式返回地点列表
"""
    prompt = prompt_template.format(
        user_input=query,
    )
    
    # 直接调用底层API获取文本响应
    res = await allm_output(prompt, client=client, output_type=PoiQueryResult, **llm_params)
    response_text = res.output
    
    # 手动解析和修正JSON
    try:
        data = json.loads(response_text)
        
        # 如果LLM错误地包装了properties层，解包它
        if isinstance(data, dict) and "properties" in data and len(data) == 1:
            data = data["properties"]
        
        # 使用修正后的数据创建对象
        result = PoiQueryResult(**data)
        return result
        
    except (json.JSONDecodeError, TypeError) as e:
        ##print(f"JSON解析失败: {response_text}, error: {e}")
        response_str = res.response
        tool_calls = response_str.tool_calls
        tool_call = tool_calls[0]
        function_args = json.loads(tool_call.function.arguments)
        properties = function_args.get("properties", {})
        result = properties.get("result", False)
        poi_list = properties.get("poi_list", [])
        return PoiQueryResult(result=result, poi_list=poi_list)


def map_category_to_domain(category_name: str) -> str:
    """
    将细分类别名称映射到所属的大类
    
    Args:
        category_name: 细分类别的名称，如 "车机系统知识"、"导航" 等
        
    Returns:
        大类名称，如 "用车助手"、"传统垂域" 等。如果找不到映射，返回 "其它"
        
    Examples:
        >>> map_category_to_domain("车机系统知识")
        "用车助手"
        >>> map_category_to_domain("导航")
        "传统垂域"
        >>> map_category_to_domain("地点推荐查询")
        "出行助手"
    """
    return CATEGORY_NAME_TO_DOMAIN.get(category_name, "趣味助手")


async def intent_cls[T](
    query: str,
    intent_categories: list[Category],
    /,
    *,
    history: list[str] = [],
    client: AsyncOpenAI = get_openai_client(),
    expert_role: str = "汽车专家",
    output_type: Type[T] = str,
    output_hint: str = "请仅仅返回类别名称。",
    **llm_params,
    ) -> str:
    """
    通用的意图分类函数，使用大语言模型对用户查询进行意图分类。
    
    该函数使用 Jinja2 模板动态生成系统提示词，支持自定义意图类别和专家角色，
    提供灵活的输入输出类型支持。
    
    Args:
        query: 用户输入的查询文本，需要进行意图分类
        intent_categories: 意图类别列表，定义所有可能的分类选项
        history: 历史对话，用于生成系统提示词中的历史对话
        client: OpenAI 客户端实例，用于调用大语言模型
        expert_role: 专家角色描述，用于生成系统提示词中的专家身份
        output_type: 输出类型，支持 str（简单字符串）或 Pydantic 模型（结构化输出）
        output_hint: 输出提示，指导模型如何格式化输出结果
        
    Returns:
        tuple[str, T]: 元组 (大类名称, 细分类别结果)
            - 第一个元素是大类名称（如 "用车助手"、"传统垂域" 等）
            - 第二个元素是原始分类结果，类型由 output_type 参数决定
    """
    start_time = time.perf_counter()
    logger.info(f"🚀 intent_cls 开始执行")
    # 预先将意图类别转换为字符串表示
    intent_categories_str = [nl_repr(category) for category in intent_categories]
    logger.info(f"✅ nl_repr 完成，耗时: {time.perf_counter() - start_time:.3f}秒")
    
    # 使用 Jinja2 模板生成系统提示词
    # 模板支持动态渲染专家角色、意图类别列表和输出提示
    template_str = """
你是一个{{ expert_role }}，需要判断用户意图的类别。以下是各个类别的描述：

{% for category_str in intent_categories_str %}
{{ category_str }}

{% endfor %}
不属于上述类别的，归类为"其它"。

历史对话：
{% for his in history %}
{{ his }}

{% endfor %}

{{ output_hint }}
"""
    
    # 渲染模板，传入所有必要的变量和函数
    template_start = time.perf_counter()
    template = Template(template_str)
    sys_prompt = template.render(
        expert_role=expert_role,
        intent_categories_str=intent_categories_str,
        output_hint=output_hint,
        history=history,
    )
    logger.info(f"✅ 模板渲染完成，耗时: {time.perf_counter() - template_start:.3f}秒")

    ##print(f"sys_prompt : {sys_prompt}")

    logger.info(f"✅ intent_cls 同步代码完成，总耗时: {time.perf_counter() - start_time:.3f}秒，准备调用LLM")
    # 根据输出类型选择不同的调用方式
    if output_type is str:
        # 简单字符串输出，适用于生产环境
        response = await allm(
            query,
            sys_prompt,
            client=client,
            **llm_params,
        )
    else: 
        # 结构化输出，得到更多信息用于分析，调试时使用，上线时关闭
        # 返回 Pydantic 模型对象，包含分类结果和详细原因
        response = await allm_output(
            query,
            sys_prompt,
            output_type=output_type,
            client=client,
            **llm_params,
        )
    
    # 提取输出结果
    output = response.output
    logger.info(f"✅ intent_cls 完成，耗时: {time.perf_counter() - start_time:.3f}秒")
    return output
    


class PoiClsResult(BaseModel):
    category: str = Field(..., title="类别", description="分类的类别名称。")
    reason: str = Field(..., title="原因", description="判断为该类别的原因。")
    poi: Optional[str] = Field(None, title="地点描述", description="地点描述。可以是具体的，如北京酒店，或者模糊的，如吃饭的地方。")

    def __nl_repr__(self, **kwargs) -> str:
        return f"{self.category}。{self.reason}。{self.poi}。"


class DecisionPath(StrEnum):
    BY_RAG_TRADITIONAL = "被RAG分类为传统垂域"
    BY_POI_CLS = "被POI分类为出行或者导航，跟所有类别结果确实不同"
    BY_ALL_CATEGORY_CLS = "所有类别的分类结果"
    BY_RAG_MUST_PASS = "被RAG分类到其他垂域"

class IntentClsResult(BaseModel):
    domain: Domain = Field(..., description="分类的意图域。")
    decision_path: DecisionPath = Field(..., description="对于用户意图分类的决策路径。")
    category: str | None = Field(default=None, description="细分类别名称。")
    reason: str | None = Field(default=None, description="判断为该类别的原因。")

class IntentClassifier:
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
        # 定义所有类别列表，按大类分组，方便后续使用
        self.all_categories = [
            # 用车助手
            vehicle_system_cat, vehicle_cat, vehicle_other_cat,
            # 搜索助手
            news_cat, encyclopedia_cat, long_tail_tricks_cat,
            # 传统垂域
            navigation_cat, car_control_cat, call_cat, 
            media_cat, vehicle_status_cat, schedule_cat, other_cat, car_home_cat, system_setting_cat,
            # 出行助手
            travel_cat, 
            # 趣味助手
            chat_cat,
        ]


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


    async def run(self, query: str, 
        history: list[HistoryItem] | str | None = None,
        output_structure: bool = False,
        ) -> IntentClsResult:
        """
        固定的对外接口，并行运行RAG判别和传统判别，RAG优先决定传统垂域
        
        Returns:
            IntentClsResult: 包含分类结果和决策路径的完整结果
        """
        start_time = time.time()
        # 统一处理 history 参数：转换为 list[str] 格式
        self.llm_params["model"] = "doubao-seed-1-6-flash-250715"
        his_user_questions = ""
        
        if history is None:
            history_list = []
        elif isinstance(history, list) and history:
            # 检查是 HistoryItem 对象还是字典
            if isinstance(history[0], HistoryItem):
                # 将每个历史记录格式化为字符串，然后作为列表元素
                history_list = [f"用户：{h.q}\n助手: {h.a}" for h in history]
                his_user_questions = "-".join([f"{h.q}" for h in history])
            elif isinstance(history[0], dict):
                # 处理字典列表（从 api.py 传入的 history_dict_list）
                history_list = [f"用户：{h['q']}\n助手: {h['a']}" for h in history]
                his_user_questions = "-".join([f"{h['q']}" for h in history])
            else:
                # 其他类型的列表（如 list[str]）
                history_list = history
        elif isinstance(history, str):
            history_list = [history] if history else []
        else:
            history_list = history
        
        intent_categories = self.all_categories
        logger.info(f"构建数据完成，耗时: {time.time() - start_time:.2f}秒")

        # 同时启动三个异步任务
        task_create_start = time.time()
        rag_task = asyncio.create_task(rag_search_traditional(query))
        logger.info(f"✅ rag_task 创建完成，耗时: {time.time() - task_create_start:.3f}秒")
        
        rag_must_pass_task = asyncio.create_task(rag_search_must_pass(" :" + his_user_questions + "-" + query if his_user_questions else  " :" + query))
        logger.info(f"✅ rag_must_pass_task 创建完成，耗时: {time.time() - task_create_start:.3f}秒")
        
        if output_structure:
            intent_task = asyncio.create_task(intent_cls(
                query, 
                intent_categories, 
                history=history_list,
                output_hint="""如果用户输入信息中包含指代内容(例如：这个、那个、它、第一个、这样 等),请根据历史对话，完成指代内容的填充之后，再进行意图分类。
                                若用户在当前对话中针对上一轮已确定的目标（如地点、功能或信息）进行追问或操作，应直接继承上一轮的意图分类，不重新分类。
                                当用户的问题可能同时属于多个类别时，优先顺序为：导航>地点推荐查询>车控>通话>播控>车况查询>日程>车家互联>系统设置>兜底操作>新闻搜索>多功能助手>百科问答>车机系统知识>车辆知识>车辆法规与车辆知识问答>其他
                                请返回类别名称以及判断的理由。""", 
                output_type=ClsResult,
                **self.llm_params))
        else:
            intent_task = asyncio.create_task(intent_cls(query, intent_categories, history=history_list, output_hint="如果用户输入信息中包含指代内容(例如：这个、那个、它、第一个、这样 等),请根据历史对话，完成指代内容的填充之后，再进行意图分类。若用户在当前对话中针对上一轮已确定的目标（如地点、功能或信息）进行追问或操作，应直接继承上一轮的意图分类，不重新分类。请仅仅返回类别名称。", **self.llm_params))

        poi_task = asyncio.create_task(self.poi_cls(query, history=history_list, output_structure=output_structure))
        logger.info(f"✅ poi_task 创建完成，耗时: {time.time() - task_create_start:.3f}秒")

        # 将所有任务放入集合中，设置总超时时间
        tasks = {rag_task, intent_task, poi_task, rag_must_pass_task}
        rag_result = None
        output = None
        poi_cls_result_output = None
        pending_tasks = set()  # 在外部定义，避免作用域问题
        
        # 🚀 性能优化：立即让出控制权，让事件循环调度任务开始执行
        # 这样可以减少从创建任务到真正执行的延迟（约0.6秒）
        yield_start = time.time()
        await asyncio.sleep(0)  # 让出控制权，让任务立即开始执行
        logger.info(f"✅ 让出控制权完成，耗时: {time.time() - yield_start:.3f}秒，任务创建总耗时: {time.time() - task_create_start:.3f}秒")
        
        wait_start = time.time()
        logger.info(f"📋 准备 await asyncio.wait()，耗时: {time.time() - start_time:.3f}秒")
        try:
            # 循环等待任务完成
            while tasks:
                # return_when=asyncio.FIRST_COMPLETED: 指定函数返回的条件。asyncio.FIRST_COMPLETED表示当第一个任务完成时（或超时，不是异常导致的）就返回。
                # done: 一个集合，包含已经完成的任务（即已经执行完毕或抛出异常的任务）。
                # pending: 一个集合，包含未完成的任务（即还在运行的任务）。
                # 超时时间20s。是因为本地测试环境，跑的很慢，平均时间十几秒
                # 如果任务发生了异常，会被放到done集合中，其他任务继续进行
                wait_loop_start = time.time()
                done, pending_tasks = await asyncio.wait(tasks, timeout=20.0, return_when=asyncio.FIRST_COMPLETED)
                wait_loop_time = time.time() - wait_loop_start
                logger.info(f"📝 等待任务完成，总耗时: {time.time() - start_time:.2f}秒，本次wait耗时: {wait_loop_time:.3f}秒，done: {len(done)}个，pending: {len(pending_tasks)}个")
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
                        while not rag_must_pass_task.done():
                            await asyncio.sleep(0.1)
                        if rag_must_pass_task.exception():
                            raise rag_must_pass_task.exception()
                        rag_must_pass_result = rag_must_pass_task.result()
                        if rag_must_pass_result.max_similarity >= RAG_TRADITIONAL_THRESHOLD:
                            for t in pending_tasks:
                                t.cancel()
                            return IntentClsResult(
                                domain=rag_must_pass_result.ground_truth,
                                decision_path=DecisionPath.BY_RAG_MUST_PASS,
                                category=rag_must_pass_result.ground_truth,
                                reason=f"RAG Must Pass相似度 {rag_must_pass_result.max_similarity:.3f} 超过阈值 {RAG_TRADITIONAL_THRESHOLD}"
                            )
                        # 如果 RAG 判定为传统垂域，立即取消其他任务并返回
                        if rag_result.is_traditional:
                            for t in pending_tasks:
                                t.cancel()
                            return IntentClsResult(
                                domain=Domain.TRADITIONAL,
                                decision_path=DecisionPath.BY_RAG_TRADITIONAL,
                                category="传统垂域",
                                reason=f"RAG相似度 {rag_result.max_similarity:.3f} 超过阈值 {RAG_TRADITIONAL_THRESHOLD}"
                            )
                    elif task == rag_must_pass_task:
                        # ## 需要等 rag_task完成之后，才能进行RAG Must Pass的判断
                        # while not rag_task.done():
                        #     await asyncio.sleep(0.1)
                        # if rag_task.exception():
                        #     raise rag_task.exception()
                        # rag_result = rag_task.result()
                        # if rag_result.is_traditional:
                        #     for t in pending_tasks:
                        #         t.cancel()
                        #     return IntentClsResult(
                        #         domain=Domain.TRADITIONAL,
                        #         decision_path=DecisionPath.BY_RAG_TRADITIONAL,
                        #         category="传统垂域",
                        #         reason=f"RAG相似度 {rag_result.max_similarity:.3f} 超过阈值 {RAG_TRADITIONAL_THRESHOLD}"
                        #     )
                        rag_must_pass_result = task.result()
                        max_similarity = rag_must_pass_result.max_similarity
                        ground_truth = rag_must_pass_result.ground_truth
                        if max_similarity >= RAG_TRADITIONAL_THRESHOLD:
                            for t in pending_tasks:
                                t.cancel()
                            return IntentClsResult(
                                domain=ground_truth,
                                decision_path=DecisionPath.BY_RAG_MUST_PASS,
                                category=ground_truth,
                                reason=f"RAG相似度 {max_similarity:.3f} 超过阈值 {RAG_TRADITIONAL_THRESHOLD}"
                            )

                    elif task == intent_task:
                        output = task.result()
                    elif task == poi_task:
                        poi_cls_result_output = task.result()

        except TimeoutError:  # 改为 TimeoutError
            # 超时处理：取消所有未完成的任务
            logger.error(f"任务执行超时（2秒）: query={query}")
            for task in pending_tasks:  # 使用外部定义的变量
                task.cancel()
            raise  # 重新抛出异常
        except Exception as e:
            # 其他异常也需要清理任务
            logger.error(f"任务执行异常: query={query}, 异常信息: {str(e)}")
            for task in tasks:
                if not task.done():
                    task.cancel()
            raise
        logger.info(f"任务执行完成，耗时: {time.time() - start_time:.2f}秒")
        logger.info(f"模型返回结果：output: {output}, poi_cls_result_output: {poi_cls_result_output}")
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
            if map_category_to_domain(poi_cls_result_output) in [Domain.TRADITIONAL, Domain.TRAVEL] and map_category_to_domain(output) in [Domain.TRADITIONAL, Domain.TRAVEL]:
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
        else:
            # 非结构化输出时，detailed_category是字符串（Domain枚举值）
            category = str(detailed_category) if detailed_category else None
            reason = None
        
        result = IntentClsResult(
            domain=domain,
            decision_path=decision_path,
            category=category,
            reason=reason
        )
        logger.info(f"函数运行完成，耗时: {time.time() - start_time:.2f}秒， result: {result}")
        
        return result

