from projects.mind.intent.intent_data.category import IntentCategory

chat = IntentCategory(
    name="聊天",
    definition=(
        "兜底分类，包含所有不属于「复杂导航」的请求。"
        "包括简单导航、日常寒暄、无明确意图表达等，以及可直接执行、不需额外推理或信息补充的简单指令（含明确地点导航）。"
    ),
    example=[
        "你好",
        "最近怎么样",
        "嗯",
        "好的，谢谢",
        "导航到北京站",
        "去上海虹桥机场",
        "帮我导航到人民广场",
        "打开导航",
        "帮我导航到公司",
    ],
)

complex_navigation = IntentCategory(
    name="复杂导航",
    definition=(
        "当前查询有表达导航/出行的意图，但系统仅基于当前查询、历史对话上下文、业务默认规则或常识假设，仍无法补全执行导航所需的关键信息(如大致位置/区域等)"
        "执行动作所需信息无法简单获取（需要动脑子思考）"

    ),
    example=[
        "我想出去开车兜兜风,有没有比较好的地方推荐啊（有出行导航意图，但需要其他工具获取推荐地点）",
    ],
)
