"""
项目常量定义
统一管理所有硬编码的字符串常量，避免拼写错误和不一致问题
"""
from enum import StrEnum


class Domain(StrEnum):
    """意图域枚举
    
    继承str是为了让枚举值可以直接用于字符串比较和JSON序列化
    """
    TRADITIONAL = "传统垂域"      # 导航、车控、通话、播控等传统功能
    TRAVEL = "出行助手"           # 地点推荐查询
    VEHICLE = "用车助手"          # 车辆知识、车机系统知识
    SEARCH = "搜索助手"           # 新闻搜索、百科问答、多功能助手
    FUN = "趣味助手"              # 闲聊等趣味功能
    OTHER = "其它"                # 其他未分类
    KNOWLEDGE = "百科闲聊"        # 闲聊、新闻搜索、百科问答、多功能助手
    
    @classmethod
    def values(cls) -> list[str]:
        """返回所有域名的值列表"""
        return [domain.value for domain in cls]
    
    @classmethod
    def get_main_domains(cls) -> list[str]:
        """返回主要域名（排除'其它'）"""
        return [domain.value for domain in cls if domain != cls.OTHER]
    

class CategoryName(StrEnum):
    """细分类别名称枚举"""
    # 用车助手
    VEHICLE_SYSTEM = "车机系统知识"
    VEHICLE_KNOWLEDGE = "车辆知识"
    VEHICLE_OTHER = "车辆相关杂项知识"
    
    # 搜索助手
    NEWS_SEARCH = "新闻搜索"
    ENCYCLOPEDIA = "百科问答"
    LONG_TAIL = "多功能助手"
    
    # 传统垂域
    NAVIGATION = "导航"
    CAR_CONTROL = "车控"
    CALL = "通话"
    MEDIA = "播控"
    VEHICLE_STATUS = "车况查询"
    SCHEDULE = "日程"
    DAILY_OPERATION = "日常操作指令"
    CAR_HOME = "车家互联"
    SYSTEM_SETTING = "系统设置"
    OTHER_OPERATION = "兜底操作"
    
    # 出行助手
    POI_RECOMMENDATION = "地点推荐查询"


# 为了兼容性，也提供常量形式
DOMAIN_TRADITIONAL = Domain.TRADITIONAL.value
DOMAIN_TRAVEL = Domain.TRAVEL.value
DOMAIN_VEHICLE = Domain.VEHICLE.value
DOMAIN_SEARCH = Domain.SEARCH.value
DOMAIN_FUN = Domain.FUN.value
DOMAIN_OTHER = Domain.OTHER.value

# 所有域名列表（用于数据集等）
ALL_DOMAINS = Domain.values()
MAIN_DOMAINS = Domain.get_main_domains()

