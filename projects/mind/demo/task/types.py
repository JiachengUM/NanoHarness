from enum import StrEnum

from pydantic import Field

from projects.mind.intent.intent_data.category import IntentCategory as IntentCategoryBase

class TaskType(StrEnum):
    """任务类型枚举"""
    NAVIGATION = "navigation"  # 导航任务
    VEHICLE_CONTROL = "vehicle_control"  # 车辆控制任务
    MEDIA_CONTROL = "media_control"  # 媒体控制任务
    INFORMATION_QUERY = "information_query"  # 信息查询任务
    SYSTEM = "system"  # 系统任务
    OTHER = "other"  # 其他任务

class IntentCategory(IntentCategoryBase):
    """意图类别元数据"""

    keywords: list[str] | None = Field(default=None, title="关键词列表", description="关键词列表，用于意图识别", repr=False)
    """repr=False，不要干扰IntentCategoryBase的提示词生成"""


# 任务类别实例
NAVIGATION_CATEGORY = IntentCategory(
    name=TaskType.NAVIGATION.value,
    definition="处理路线规划、导航指引等相关任务",
    keywords=["导航", "去", "路线", "加油站", "停车场", "机场", "公司", "回家", "地图", "位置"],
    example=[
        "导航到北京首都机场",
        "去最近的加油站",
        "规划回家的路线",
        "附近有停车场吗"
    ]
)

VEHICLE_CONTROL_CATEGORY = IntentCategory(
    name=TaskType.VEHICLE_CONTROL.value,
    definition="处理车辆相关的控制任务，如空调、车窗、座椅等",
    keywords=["空调", "温度", "车窗", "座椅", "天窗", "雨刷", "灯光", "车门", "后视镜", "方向盘"],
    example=[
        "打开空调",
        "把温度调到26度",
        "关闭车窗",
        "调整座椅位置"
    ]
)

MEDIA_CONTROL_CATEGORY = IntentCategory(
    name=TaskType.MEDIA_CONTROL.value,
    definition="处理媒体播放相关的控制任务，如音乐、广播等",
    keywords=["播放", "音乐", "音量", "暂停", "下一首", "歌单", "电台", "静音", "上一首", "单曲循环"],
    example=[
        "播放周杰伦的歌曲",
        "调高音量",
        "暂停播放",
        "下一首"
    ]
)

INFORMATION_QUERY_CATEGORY = IntentCategory(
    name=TaskType.INFORMATION_QUERY.value,
    definition="处理各种信息查询任务，如天气、新闻、餐厅等",
    keywords=["天气", "新闻", "餐厅", "咖啡店", "时间", "日期", "股票", "汇率", "限行", "路况"],
    example=[
        "今天天气怎么样",
        "北京的新闻",
        "附近的餐厅",
        "明天限行吗"
    ]
)

CHAT_CATEGORY = IntentCategory(
    name=TaskType.OTHER.value,
    definition="用户提出的问题无法归类到其他类别，作为兜底分类。",
    keywords=[],
    example=[
        "问候语,如: 你好, 你好呀, 早上好, 晚上好",
        "寒暄对话,如: 随便聊聊, 最近怎么样, 在干嘛呢",
        "无明确意图的表达,如: 嗯, 好的, 知道了, 谢谢"
    ]
)

ALL_CATEGORIES = [
    NAVIGATION_CATEGORY,
    VEHICLE_CONTROL_CATEGORY,
    MEDIA_CONTROL_CATEGORY,
    INFORMATION_QUERY_CATEGORY,
    CHAT_CATEGORY,
]

# 任务类别映射
TASK_CATEGORIES = {
    TaskType.NAVIGATION: NAVIGATION_CATEGORY,
    TaskType.VEHICLE_CONTROL: VEHICLE_CONTROL_CATEGORY,
    TaskType.MEDIA_CONTROL: MEDIA_CONTROL_CATEGORY,
    TaskType.INFORMATION_QUERY: INFORMATION_QUERY_CATEGORY,
    TaskType.OTHER: CHAT_CATEGORY,
}
