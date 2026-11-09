from crewai_tools import SerperDevTool
from crewai.tools import tool

# 搜索工具
search_tool = SerperDevTool(n_results=2)


# 计算器工具函数
@tool
def calculator_tool(expression: str) -> str:
    """
    计算数学表达式的结果
    
    Args:
        expression: 数学表达式
    
    Returns:
        计算结果
    """
    try:
        result = eval(expression)
        return f"计算结果: {result}"
    except Exception as e:
        return f"计算错误: {str(e)}"

# 天气工具函数
@tool
def weather_tool(city: str) -> str:
    """
    获取指定城市的天气信息
    
    Args:
        city: 城市名称
    
    Returns:
        天气信息
    """
    weather_data = {
        "北京": "晴天，温度20-25℃",
        "上海": "多云，温度18-23℃",
        "广州": "雨天，温度22-28℃",
        "深圳": "晴天，温度23-29℃"
    }
    if city in weather_data:
        return f"{city}的天气: {weather_data[city]}"
    else:
        return f"抱歉，暂不支持查询{city}的天气信息"

# 美食工具函数
@tool
def food_tool(query: str, location: str = "附近") -> str:
    """
    检索餐厅信息
    
    Args:
        query: 餐厅查询条件
        location: 位置，默认为"附近"
    
    Returns:
        餐厅信息
    """
    return f"正在为您检索{location}的{query}，请稍候..."

# 景点工具函数
@tool
def attractions_tool(query: str, location: str = "附近") -> str:
    """
    检索景点信息
    
    Args:
        query: 景点查询条件
        location: 位置，默认为"附近"
    
    Returns:
        景点信息
    """
    return f"正在为您检索{location}的{query}，请稍候..."

# 娱乐工具函数
@tool
def entertainment_tool(query: str, location: str = "附近") -> str:
    """
    检索娱乐地点信息
    
    Args:
        query: 娱乐地点查询条件
        location: 位置，默认为"附近"
    
    Returns:
        娱乐地点信息
    """
    return f"正在为您检索{location}的{query}，请稍候..."

# 住宿工具函数
@tool
def accommodation_tool(query: str, location: str = "附近") -> str:
    """
    检索酒店住宿信息
    
    Args:
        query: 酒店住宿查询条件
        location: 位置，默认为"附近"
    
    Returns:
        酒店住宿信息
    """
    return f"正在为您检索{location}的{query}，请稍候..."

# 导航工具函数
@tool
def navigation_tool(destination: str, waypoints: list = None) -> str:
    """
    导航操作
    
    Args:
        destination: 目的地
        waypoints: 途径点列表
    
    Returns:
        导航信息
    """
    if waypoints:
        waypoints_str = "，顺便路过" + "、".join(waypoints)
    else:
        waypoints_str = ""
    return f"正在为您规划前往{destination}{waypoints_str}的路线，请稍候..."

# 短视频工具函数
@tool
def douyin_video_tool(query: str) -> str:
    """
    检索和播放短视频
    
    Args:
        query: 短视频查询条件
    
    Returns:
        短视频信息
    """
    return f"正在为您查找{query}的短视频，请稍候..."

# 媒体工具函数
@tool
def media_tool(query: str) -> str:
    """
    播放音乐、有声、电台等媒体
    
    Args:
        query: 媒体查询条件
    
    Returns:
        媒体播放信息
    """
    return f"正在为您播放{query}，请稍候..."

# 新闻工具函数
@tool
def news_tool(query: str) -> str:
    """
    检索和播放新闻
    
    Args:
        query: 新闻查询条件
    
    Returns:
        新闻信息
    """
    return f"正在为您查找{query}，请稍候..."

# 日报工具函数
@tool
def daily_news_tool(category: str = "综合") -> str:
    """
    检索和播放日报
    
    Args:
        category: 日报类别，默认为"综合"
    
    Returns:
        日报信息
    """
    return f"正在为您播放{category}日报，请稍候..."

# 车控工具函数
@tool
def vehicle_control_tool(command: str) -> str:
    """
    控制车辆硬件和软件系统
    
    Args:
        command: 控制命令
    
    Returns:
        控制结果
    """
    return f"正在执行车辆控制命令: {command}，请稍候..."

# 车辆状态查询工具函数
@tool
def vehicle_state_tool(query: str) -> str:
    """
    查询车辆状态
    
    Args:
        query: 状态查询条件
    
    Returns:
        车辆状态信息
    """
    return f"正在为您查询车辆{query}，请稍候..."

# 应用工具函数
@tool
def app_tool(command: str) -> str:
    """
    控制车内应用
    
    Args:
        command: 应用控制命令
    
    Returns:
        应用控制结果
    """
    return f"正在执行应用控制命令: {command}，请稍候..."

# 电话工具函数
@tool
def call_tool(command: str) -> str:
    """
    控制蓝牙电话
    
    Args:
        command: 电话控制命令
    
    Returns:
        电话控制结果
    """
    return f"正在执行电话控制命令: {command}，请稍候..."

# 风险工具函数
@tool
def risk_tool(query: str) -> str:
    """
    风控识别
    
    Args:
        query: 需要识别的内容
    
    Returns:
        风控识别结果
    """
    return f"正在进行风控识别，请稍候..."

# 车推荐工具函数
@tool
def car_recommended_tool(query: str) -> str:
    """
    推荐汽车
    
    Args:
        query: 汽车推荐条件
    
    Returns:
        汽车推荐信息
    """
    return f"正在为您推荐{query}，请稍候..."

# 联网工具函数
@tool
def browsing_tool(query: str) -> str:
    """
    查询信息
    
    Args:
        query: 信息查询内容
    
    Returns:
        信息查询结果
    """
    return f"正在为您查询{query}，请稍候..."

# 所有工具的列表
all_tools = [
    search_tool,
    calculator_tool,
    weather_tool,
    food_tool,
    attractions_tool,
    entertainment_tool,
    accommodation_tool,
    navigation_tool,
    douyin_video_tool,
    media_tool,
    news_tool,
    daily_news_tool,
    vehicle_control_tool,
    vehicle_state_tool,
    app_tool,
    call_tool,
    risk_tool,
    car_recommended_tool,
    browsing_tool
]
