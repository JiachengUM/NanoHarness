"""toy tool。极简实现。没有实际用处，仅用于最简单的测试。"""

from typing import Any

class BaseTool:
    """工具基类，定义标准化接口"""
    def __init__(self, name: str, description: str):
        self.name = name  # 工具名称（用于行动解析）
        self.description = description  # 工具功能描述（用于模型理解）
        
    def run(self, params: Any) -> str:
        """核心执行方法，子类必须实现，返回结构化观察结果"""
        raise NotImplementedError("所有工具子类必须实现run方法")

# 航班查询工具实现示例（调用模拟航班查询接口）
class FlightSearchTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="flight_search",
            description="用于查询指定条件的航班信息，参数格式为'出发地,目的地,日期,时段'，时段支持'上午/下午/晚上'"
        )

    def run(self, params: str) -> str:
        """模拟航班查询工具执行逻辑，实际场景替换为真实航班API调用"""
        try:
            # 解析参数（出发地,目的地,日期,时段）
            dep, arr, date, time_period = params.split(',')
            # 模拟符合条件的航班搜索结果
            flight_map = {
            "深圳,海南,明天,晚上": "符合条件航班列表：1. HU7089（深圳宝安→海口美兰，20:15-21:45，票价480元）；2. CZ6753（深圳宝安→三亚凤凰，21:30-23:05，票价620元）；3. MU2478（深圳宝安→海口美兰，19:40-21:10，票价550元）"
            }
            return flight_map.get(f"{dep},{arr},{date},{time_period}", f"未检索到{dep}到{arr}{date}{time_period}的相关航班信息")
        except Exception as e:
            return f"航班查询工具调用失败：{str(e)[:50]}"

# 航班预订工具实现示例（调用模拟航班预订接口）
class FlightBookTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="flight_book",
            description="用于预订指定航班，参数格式为'航班号,乘客姓名,身份证号'"
        )
    def run(self, params: str) -> str:
        """模拟航班预订工具执行逻辑，实际场景替换为真实预订API调用"""
        try:
        # 解析参数（航班号,乘客姓名,身份证号）
            flight_no, name, id_card = params.split(',')
            # 模拟预订成功反馈
            return f"航班预订成功：航班号{flight_no}，乘客{name}（身份证号：{id_card[-4:]}），请携带有效证件提前2小时到机场办理登机手续"
        except Exception as e:
            return f"航班预订失败：{str(e)[:50]}"
