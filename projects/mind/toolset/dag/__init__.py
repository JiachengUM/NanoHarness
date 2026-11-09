"""
复杂推理默认工具集：对应原 complex_reasoning_agent subagent 的 Tool 形态。
需火山 call_fc 的工具（车控、媒体、导航、天气）需传入 chat_id。
"""
from aicore.v1.experiments.agent import SystemPrompt
from projects.mind.toolset.dag.car_control import CarControlTool
from projects.mind.toolset.dag.compact import compact_tool_output
from projects.mind.toolset.dag.media import MediaTool
from projects.mind.toolset.dag.memory import MemoryTool
from projects.mind.toolset.dag.navigate_v2 import NavigateTool
from projects.mind.toolset.dag.poi_search import (
    SGMPoiWorker,
    poi_search_tool
)
from projects.mind.toolset.dag.web_search import WebsearchTool
from projects.mind.toolset.dag.music_search_v2 import (
    qq_music_song_search_tool,
    qq_music_playlist_search_tool,
    qq_music_album_search_tool
)


__all__ = [
    "CarControlTool",
    "MediaTool",
    "MemoryTool",
    "NavigateTool",
    "poi_search_tool",
    "qq_music_song_search_tool",
    "qq_music_playlist_search_tool",
    "qq_music_album_search_tool",
    "WebsearchTool",
    "get_default_tools",
    "get_prompt",
]


def get_default_tools(chat_id: str):
    """返回默认工具列表。chat_id 用于需请求火山的工具（车控、媒体、导航）。

    5 个 search 工具的 worker 输出会走 ``compact_dict + to_toon``（注册式：``compact._COMPACT_OUTPUT_TOOLS`` frozenset）。
    compact 包装是纯函数：返回 tool 副本，不修改原 tool。
    """
    tools = [
        CarControlTool(chat_id=chat_id),
        MediaTool(chat_id=chat_id),
        MemoryTool(),
        NavigateTool(chat_id=chat_id),
        qq_music_song_search_tool(),
        qq_music_playlist_search_tool(),
        qq_music_album_search_tool(),
        poi_search_tool(),
        WebsearchTool(),
    ]
    # 注册表内 tool 走 compact 包装；其余原样返回
    return [compact_tool_output(t) for t in tools]


def get_prompt():
    '''
    系统提示词内容可以被打包成AGENT.md放到对应项目下，
    系统提示词优化是harness工程的一部分，优化思路是将具体badcase内容抽象成四种情况：
    【不可以做xxx】、【可以做xxx】、【当xxx时，可以做】，【当xxx时，不可以做】
    评估准则：
    1. 用户搜索目标和工具输出之间的因果关系
    2. 用户输入是否合理结构化成了工具输入，筛选条件是否全部结构化进criteria
    3. 工具输入和工具输出之间因果关系与相关性
    4.
    5.
    '''
    return SystemPrompt(
    role="""你是车载助手，完全遵循用户要求，回复时保持极简极简极简极简。我在上海市徐汇滨江城开中心T2楼，今天是2026年6月12日。""",
        guidelines=[
            # "注意区分地点类型和店名"
            # "调用工具前，简短回复打算做什么",

            # TODO music
            #  如果没有提供记忆，需要合理询问获取相关信息，本质是记忆和其它工具能力边界问题，harness做法是将需要检索记忆的内容打包成一个工具场景作为记忆消费的结构化方式做动态生成/FC，
            #    记忆消费场景的工具入参需要结合记忆生产时候的结构化schema、poi和music筛选项【我昨晚一直在听啥，是谁唱的呀，来点差不多风格的，重新放这首】，已修，待测
            #  结合记忆做筛选【想找找能延续我常听风格的近期全新曲目】，已修，待测
            #  qq_music_search工具入参奇怪能搜出最近的歌【我最近听了什么歌，谁唱的，他还有什么歌，播放最新的，换最近听的那个首】，已修，待测
            #  推荐歌曲时，如果未指定具体数量，默认数量大于等于3【最近有什么好听的新歌推荐】，已修
            #  模糊时间必须取默认的时间【帮我挖掘下近期发行、适合我循环播放的歌曲】，已修

            # TODO media
            #  websearch搜不出内容，说明联网搜不是一个通用搜索引擎接口【车内太干，看点车内养生知识，查看日常调理贴士，筛选换季专属内容，逐条语音朗读，收藏整套资讯 - 车内养生知识 日常调理贴士 换季专属内容】


            # TODO poi_search
            #  is_around在搜附近时无传入参数（arg_schema或提示词来解耦is_around和criteria），没有复现成功，均显示正例
            #  只有明确地址才走直接导航，否则算推荐（通过提示词写入逻辑），已修
            #  确认navigation的合法输入，检查poi_search输出的地址合法性（导航逆查询只对查询精确地址验证有效，模糊地址返回多个经纬度并且不准确，逆差查询无效（tool场景的worker封装））


            # TODO music_search
            #  时间转换不对【最近最火的歌曲是啥-2024年最近最火的歌曲】，已修
            #  联网搜需要用小模型压一下？【陈奕迅是几零后】
            #  没有调用为啥就保存了？音乐有这个功能？【我听歌就听陈奕迅（永久保留）】，属于记忆
            #  对于特定目的地有些常识需要走默认，比如我要去xx地方去接人，不同xx地方类型都会有默认的入口，比如地下停车场、学校大门口，
            #  如果具体地址没有精确到入口，需要有地址类别的默认入口，如果非具体地址，测一下高德是否能达到导航到合适入口。默认地址结合记忆更新
            #  接某人的常用地址【我要去幼儿园接我老婆】
            # TODO 最终结论/过程？必须从上下文中推理出来，不能从上下文之外的地方拿来
            # TODO POI搜索换搜索条件，测试和验证各种筛选条件是否全部满足，模型需要判断是否满足【当不满足时，告知用户不满足原因并返回部分满足筛选项的内容】
            "criteria是除了query之外的任何其它描述",
            # TODO poi搜索是扩大范围还是缩小范围？【哈雷摩托车普陀店的评分和人均消费多少】
            "模糊时间和地点先转化为具体日期和地址",
            "需要用到个人信息作为搜索条件时，不能直接调websearch",
            "当音乐推荐未指定具体推荐数量，默认尽可能多推荐",
            # "criteria列表和其它入参可以重叠",
            # TODO 显示筛选结果的原因，显示智能，已优化
            # "如果结果经过筛选，说明筛选原因",
            # TODO 【评测skill优化，N个模糊意图是否都同时满足】已修复长文本含有出行需求未关注到的问题
            "出行和自媒体相关的都需要被合理回复",
            "音乐场景可以利用车辆状态和用户偏好进行适当联想和关联，推荐但不执行",
            "别忘了音乐执行控制和推荐理由",
            # "qq_music_song_search歌手不能超过3个",
            "周边搜索必须提供地址",
            # TODO 【评测skill优化，时间不敏感】增加了出发时间，修复了【我明天去xxx地方】，Navigation的输入有出发时间，接口识别‘今天’并返回正确的date作为出发日期，已优化
            "有目的地和触发时间时直接导航，否则搜索结果只能作为推荐或未来规划",
            "歌曲播放支持单首，歌单包含多首歌曲",
            "当搜出多首歌曲均满足筛选条件时，通过媒体工具整理成歌单",
            "最新歌曲或榜单指的是最近public_time",
            # TODO 测下注掉部分影响
            # "联网检索时不做模糊POI检索、垂直领域（电商、本地生活攻略）",
            # TODO 语气上强调了调用工具前询问的必要性，期望避免不必要的调用，与planner功能可能重复，去掉试试，待测
            "调用工具前，必须思考上下文是否提供了必备参数，如缺失必备参数或信息，就必须先礼貌简短地询问用户获取缺失信息，询问时不要罗列工具细节",
            # "调用工具后，严格按照下面筛选逻辑和顺序：当有多个筛选项并且不能同时满足时，可按照顺序尝试："
            # "1. 多跳检索：通过多个步骤、跨越多个数据源或中间结果才能找到最终答案的检索方式。"
            # "2. 迭代检索：强调重复调用同一检索接口，每次用上一次的结果优化或重构下一次的查询，直到满足目标。"
            # "当全部尝试超过多次均无法满足筛选项，满足部分关键筛选条件也可以作为推荐建议返回，但需要说明原因。"
            # TODO websearch 未找到结果时需要搜几次？待优化
            # TODO 优化了工具参数缺失直接跳过调用，增加【如缺失，就不要调用】
        ]
    )
