import anyio

from rich import print

from aicore.v2.tools.task_manage_bocong import WeatherTaskCancelTool, POITaskCancelTool, TaskManager

from aicore.models.responses import astream, ainvoke_output_by_json, ModelParams, EasyInputMessageParam, system_msg, \
    user_msg, assistant_msg
from aicore.models.credentials import ModelName

from aicore.agents._react_core import _response_to_react_event
from aicore.events.react import ToolCallStartEvent, ReActEventPrinter

from aicore.tools import base_tool_to_param
from aicore.utils.data_concept import JudgeResult

model_params = ModelParams(model=ModelName.SEED_1_8_251228)

CASES: list[tuple[list[EasyInputMessageParam], str]] = [
    (  # 简单测试
        [
            system_msg(content="你是车机助手"),
        ],
        "北京天气如何",
    ),
    (  # 测试任务取消。自动调用工具非常不稳定，很多错误。改成明确的意图判断之后(test_cancel_intent)全对了。
        [
            system_msg(content="你是AI助手，完全遵循用户要求，先理解一遍用户需求，仅当POI查询和天气查询时回复结尾展示最新运行详情"),
            # system_msg(content="你是车机助手，完全遵循用户要求，对话过程中必须留意用户对历史任务的增删改的意图，工具的必传参数缺失时询问用户"),
            # 居然可能导致cancel工具参数出现 city: 北京。也是见了鬼了。
            user_msg(content="帮我查询一下北京的天气"),
            assistant_msg(content='好的。正在为您查询北京的天气，请稍候。任务运行详情如下： {"task_name":"天气查询","task_state":"正在查询"}'), # id不要用简单数字，会出现幻觉
            user_msg(content="帮我搜下上海平金中心1号楼附近有什么好玩的，适合带小孩的"),
            assistant_msg(content='好的。正在为您搜索平金中心1号楼附近的室内游乐场。任务运行详情如下： [{"task_name":"POI查询","task_state":"正在查询"},{"task_name":"天气查询", "task_state":"已查询完成"}]'), # id不要用简单数字，会出现幻觉
            # 稍候等有了查询结果会回复您。
        ],
        # "算了这个先别查了"  # 取消最近任务
        # "算了别查了"  # 取消最近任务
        # "算了，都别查了"  # 取消全部任务
        # "没时间了，POI查询继续、天气立刻返回" # 部分任务结果立即返回
        # "不对，我要查上海的天气"  # 修改任务
        # "我要先去幼儿园接小孩", # 更新任务
        # "上海的也查一下"  # 新增任务
        # "还有上海的也查一下" # 新增任务
        # "讲个笑话。"   # 讲笑话
        "讲个笑话。继续查天气"  # 这样居然也会调用cancel工具，见了鬼了。
        # "我要去上海了"
    ),
]


async def test_task_cancel_tool():
    # tools = [WeatherTaskCancelTool(), POITaskCancelTool()]
    tools = [TaskManager()]

    messages, query = CASES[1]

    # print("消息历史")
    # print(messages)
    # print(f"用户查询: {query}")

    # tools = None

    final_stream_result = await astream(
        query,
        messages,
        client=model_params.client,
        model=model_params.model,
        tools=[base_tool_to_param(t) for t in tools] if tools else None,
        params=model_params.params,
    )

    printer = ReActEventPrinter()

    # 流式返回事件
    async for raw_event in final_stream_result:
        event = _response_to_react_event(raw_event, 1)
        if event is None:
            continue

        match event:
            case ToolCallStartEvent():
                args_dict = event.arguments
                # result = await tools.arun(args_dict)

        printer(event)

    # 获取最终响应
    final_response = final_stream_result.response


async def test_cancel_intent():
    messages, query = CASES[1]

    print("消息历史")
    print(messages)
    print(f"用户查询: {query}")

    query = f"""消息历史如下:
{messages}
用户当前查询为: {query}
请判断用户的意图是否为取消当前正在执行的任务。请给出判断结果和原因。
"""

    result, _ = await ainvoke_output_by_json(
        query,
        output_type=JudgeResult,
        client=model_params.client,
        model=model_params.model,
        params=model_params.params,
    )

    print(result)


if __name__ == "__main__":
    for _ in range(10):
        anyio.run(test_task_cancel_tool)
        print("-"*50)
