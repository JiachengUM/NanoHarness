from pydantic import BaseModel, Field

import asyncio

from rich import print

from aicore.tools import BaseTool, tool, base_tool_to_param

__all__ = [
    "get_weather",
    "ControlACInput",
    "ControlACTool",
    "VehicleStatusInput",
    "VehicleStatusTool",
    "NavigationInput",
    "NavigationTool",
    "MultimediaInput",
    "MultimediaTool",
    "SeatControlInput",
    "SeatControlTool",
]

@tool
def get_weather(location: str) -> dict[str, str | int]:
    """获取指定城市的当前天气"""
    return {"location": location, "temperature": 30, "unit": "C"}

class ControlACInput(BaseModel):
    mode: str = Field(description="空调模式，如 'cool', 'heat', 'auto'")
    temperature: int = Field(description="目标温度（摄氏度）", ge=16, le=30)


class ControlACTool(BaseTool):
    name: str = "control_ac"
    description: str = "控制车载空调"
    args_schema: type[BaseModel] = ControlACInput

    def _run(self, mode: str, temperature: int) -> dict:
        return {"status": "success", "action": f"Set AC to {mode} at {temperature}°C"}


# 3. 车辆状态工具
class VehicleStatusInput(BaseModel):
    status_types: list[str] = Field(description="要获取的状态类型列表，如 ['battery', 'fuel', 'tires', 'doors']")


class VehicleStatusTool(BaseTool):
    name: str = "vehicle_status"
    description: str = "获取车辆当前状态信息，包括电池、油量、胎压等"
    args_schema: type[BaseModel] = VehicleStatusInput

    base_status: dict = {
        "battery": {"level": 85, "status": "normal"},
        "fuel": {"level": 60, "range": 450, "unit": "km"},
        "tires": {
            "front_left": 2.3,
            "front_right": 2.4,
            "rear_left": 2.3,
            "rear_right": 2.3,
            "unit": "bar"
        },
        "doors": {
            "driver": "closed",
            "passenger": "closed",
            "rear_left": "closed",
            "rear_right": "closed"
        },
        "lights": {
            "headlights": "off",
            "taillights": "off",
            "interior": "on"
        },
        "windows": {
            "driver": "closed",
            "passenger": "closed",
            "rear_left": "closed",
            "rear_right": "closed"
        }
    }

    def _run(self, status_types: list[str]) -> dict:
        """获取车辆状态信息
        
        Args:
            status_types: 可选，指定要获取的状态类型列表
                - battery: 电池状态
                - fuel: 燃油状态
                - tires: 胎压状态
                - doors: 车门状态
                - lights: 灯光状态
                - windows: 车窗状态
        """
        
        filtered_status = {k: v for k, v in self.base_status.items() if k in status_types}
        return {"status": "success", "data": filtered_status}
    

# 4. 导航系统工具
class NavigationInput(BaseModel):
    destination: str | None = Field(default=None, description="目的地地址或名称")
    origin: str | None = Field(default=None, description="起点地址或名称")
    mode: str = Field(default="fastest", description="导航模式，如 'fastest', 'shortest', 'eco'")
    avoid_tolls: bool = Field(default=False, description="是否避开收费路段")
    avoid_highways: bool = Field(default=False, description="是否避开高速公路")


class NavigationTool(BaseTool):
    name: str = "navigation"
    description: str = "提供导航相关功能，包括路线规划、导航状态查询等"
    args_schema: type[BaseModel] = NavigationInput

    def _run(self, destination: str | None = None, origin: str | None = None, mode: str = "fastest", 
             avoid_tolls: bool = False, avoid_highways: bool = False) -> dict:
        """提供导航功能
        
        Args:
            destination: 目的地地址或名称
            origin: 起点地址或名称，默认为当前位置
            mode: 导航模式，可选值：fastest（最快）, shortest（最短）, eco（经济）
            avoid_tolls: 是否避开收费路段
            avoid_highways: 是否避开高速公路
        """
        if not destination:
            return {
                "status": "error", 
                "message": "请提供目的地"
            }
        
        # 模拟导航结果
        return {
            "status": "success",
            "origin": origin or "当前位置",
            "destination": destination,
            "mode": mode,
            "distance": 15.5,
            "distance_unit": "km",
            "estimated_time": 25,
            "time_unit": "minutes",
            "route": [
                "从当前位置出发",
                "沿建国路向东行驶2公里",
                "左转进入长安街",
                "沿长安街行驶8公里",
                "右转进入东三环",
                "沿东三环行驶5公里",
                "到达目的地"
            ],
            "traffic_info": "路况良好，预计25分钟到达",
            "avoid_tolls": avoid_tolls,
            "avoid_highways": avoid_highways
        }


# 5. 多媒体系统工具
class MultimediaInput(BaseModel):
    action: str = Field(description="操作类型，如 'play', 'pause', 'next', 'previous', 'volume_up', 'volume_down', 'switch_source'")
    media_type: str = Field(default="music", description="媒体类型，如 'music', 'radio', 'video'")
    content: str | None = Field(default=None, description="具体内容，如歌曲名称、电台频率、视频名称")
    volume: int | None = Field(default=None, description="音量级别（0-100）", ge=0, le=100)


class MultimediaTool(BaseTool):
    name: str = "multimedia"
    description: str = "控制车内多媒体设备，包括音乐、广播、视频等"
    args_schema: type[BaseModel] = MultimediaInput

    def _run(self, action: str, media_type: str = "music", content: str | None = None, volume: int | None = None) -> dict:
        """控制多媒体系统
        
        Args:
            action: 操作类型
                - play: 播放
                - pause: 暂停
                - next: 下一首/下一个
                - previous: 上一首/上一个
                - volume_up: 音量增加
                - volume_down: 音量减少
                - switch_source: 切换音源
            media_type: 媒体类型，可选值：music（音乐）, radio（广播）, video（视频）
            content: 具体内容，如歌曲名称、电台频率、视频名称
            volume: 音量级别（0-100），仅在设置音量时使用
        """
        # 模拟当前播放状态
        current_state = {
            "music": {
                "title": "Summer Day",
                "artist": "Various Artists",
                "album": "Summer Collection",
                "duration": "3:45",
                "current_time": "1:20"
            },
            "radio": {
                "station": "FM 103.9",
                "name": "北京交通广播",
                "genre": "新闻资讯"
            },
            "video": {
                "title": "Car Tutorial",
                "duration": "15:30",
                "current_time": "5:20"
            }
        }
        
        # 处理不同操作
        if action in ["play", "pause"]:
            return {
                "status": "success",
                "action": f"{action.capitalize()} {media_type}",
                "current_state": current_state.get(media_type, {})
            }
        elif action in ["next", "previous"]:
            return {
                "status": "success",
                "action": f"{action.capitalize()} track",
                "next_state": {
                    "title": "Next Song" if action == "next" else "Previous Song",
                    "artist": "Various Artists"
                }
            }
        elif action in ["volume_up", "volume_down"]:
            return {
                "status": "success",
                "action": action,
                "new_volume": 60  # 模拟音量值
            }
        elif action == "switch_source":
            return {
                "status": "success",
                "action": f"Switch to {media_type}",
                "current_state": current_state.get(media_type, {})
            }
        else:
            return {
                "status": "error",
                "message": f"Unknown action: {action}"
            }


# 6. 座椅控制工具
class SeatControlInput(BaseModel):
    position: str = Field(description="座椅位置，如 'driver', 'passenger', 'rear_left', 'rear_right'")
    adjustment: str = Field(description="调整类型，如 'forward', 'backward', 'up', 'down', 'recline', 'massage'")
    level: int | None = Field(default=None, description="调整级别或力度（1-10）", ge=1, le=10)
    massage_mode: str | None = Field(default=None, description="按摩模式，如 'relax', 'invigorate', 'wave'")


class SeatControlTool(BaseTool):
    name: str = "seat_control"
    description: str = "控制座椅的位置、角度、按摩功能等"
    args_schema: type[BaseModel] = SeatControlInput

    def _run(self, position: str, adjustment: str, level: int | None = None, massage_mode: str | None = None) -> dict:
        """控制座椅
        
        Args:
            position: 座椅位置
                - driver: 驾驶员座椅
                - passenger: 副驾驶座椅
                - rear_left: 后排左侧座椅
                - rear_right: 后排右侧座椅
            adjustment: 调整类型
                - forward: 向前移动
                - backward: 向后移动
                - up: 向上调整
                - down: 向下调整
                - recline: 调整靠背角度
                - massage: 按摩功能
            level: 调整级别或力度（1-10）
            massage_mode: 按摩模式，可选值：relax（放松）, invigorate（活力）, wave（波浪）
        """
        # 处理不同调整类型
        if adjustment == "massage":
            if not massage_mode:
                return {
                    "status": "error",
                    "message": "请指定按摩模式"
                }
            return {
                "status": "success",
                "action": f"Set {position} seat massage to {massage_mode} mode",
                "intensity": level or 5
            }
        else:
            return {
                "status": "success",
                "action": f"Adjust {position} seat {adjustment}",
                "level": level or 5
            }


def test_base_tool_to_param():
    for t in [ControlACTool(), VehicleStatusTool(), NavigationTool(), MultimediaTool(), SeatControlTool()]:
        tool_param = base_tool_to_param(t)    
        print(tool_param)


# 测试ControlACTool

def test_control_ac_tool():
    """测试空调控制工具"""
    tool = ControlACTool()
    
    # 测试正常情况
    args_dict = {"mode": "cool", "temperature": 24}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert "Set AC to cool at 24°C" in result["action"]
    
    # 测试加热模式
    args_dict = {"mode": "heat", "temperature": 28}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert "Set AC to heat at 28°C" in result["action"]
    
    # 测试自动模式
    args_dict = {"mode": "auto", "temperature": 22}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert "Set AC to auto at 22°C" in result["action"]


# 测试VehicleStatusTool

def test_vehicle_status_tool():
    """测试车辆状态工具"""
    tool = VehicleStatusTool()
    
    # 测试获取单个状态
    args_dict = {"status_types": ["battery"]}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert "battery" in result["data"]
    assert "level" in result["data"]["battery"]
    
    # 测试获取多个状态
    args_dict = {"status_types": ["battery", "fuel"]}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert "battery" in result["data"]
    assert "fuel" in result["data"]
    
    # 测试获取所有状态
    all_status_types = ["battery", "fuel", "tires", "doors", "lights", "windows"]
    args_dict = {"status_types": all_status_types}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    for status_type in all_status_types:
        assert status_type in result["data"]
    
    # 测试空列表
    args_dict = {"status_types": []}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert result["data"] == {}


# 测试NavigationTool

def test_navigation_tool():
    """测试导航工具"""
    tool = NavigationTool()

    # 测试正常情况：仅提供目的地
    args_dict = {'destination': '北京故宫'}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert result["destination"] == "北京故宫"
    assert result["origin"] == "当前位置"
    assert "route" in result
    assert isinstance(result["route"], list)

    aresult = asyncio.run(tool.arun(args_dict))
    assert result == aresult
    
    # 测试错误情况：未提供目的地
    args_dict = {'destination': None}
    result = tool.run(args_dict)
    assert result["status"] == "error"
    assert "请提供目的地" in result["message"]
    
    # 测试正常情况：仅提供目的地
    args_dict = {"destination": "北京市朝阳区建国路88号"}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert result["destination"] == "北京市朝阳区建国路88号"
    assert result["origin"] == "当前位置"
    assert "route" in result
    assert isinstance(result["route"], list)
    
    # 测试不同导航模式
    args_dict = {"destination": "北京市海淀区中关村", "mode": "shortest"}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert result["mode"] == "shortest"
    
    args_dict = {"destination": "北京市海淀区中关村", "mode": "eco"}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert result["mode"] == "eco"
    
    # 测试避开收费路段和高速公路
    args_dict = {
        "destination": "北京市海淀区中关村",
        "avoid_tolls": True,
        "avoid_highways": True
    }
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert result["avoid_tolls"] == True
    assert result["avoid_highways"] == True


# 测试MultimediaTool

def test_multimedia_tool():
    """测试多媒体工具"""
    tool = MultimediaTool()
    
    # 测试播放操作
    args_dict = {"action": "play", "media_type": "music"}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert "Play music" in result["action"]
    assert "current_state" in result
    
    # 测试暂停操作
    args_dict = {"action": "pause", "media_type": "radio"}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert "Pause radio" in result["action"]
    assert "current_state" in result
    
    # 测试下一首操作
    args_dict = {"action": "next", "media_type": "music"}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert "Next track" in result["action"]
    assert "next_state" in result
    
    # 测试上一首操作
    args_dict = {"action": "previous", "media_type": "music"}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert "Previous track" in result["action"]
    assert "next_state" in result
    
    # 测试音量增加
    args_dict = {"action": "volume_up"}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert "volume_up" in result["action"]
    assert "new_volume" in result
    
    # 测试音量减少
    args_dict = {"action": "volume_down"}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert "volume_down" in result["action"]
    assert "new_volume" in result
    
    # 测试切换音源
    args_dict = {"action": "switch_source", "media_type": "video"}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert "Switch to video" in result["action"]
    assert "current_state" in result
    
    # 测试未知操作
    args_dict = {"action": "unknown"}
    result = tool.run(args_dict)
    assert result["status"] == "error"
    assert "Unknown action" in result["message"]


# 测试SeatControlTool

def test_seat_control_tool():
    """测试座椅控制工具"""
    tool = SeatControlTool()
    
    # 测试正常的座椅位置调整
    args_dict = {"position": "driver", "adjustment": "forward", "level": 3}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert "Adjust driver seat forward" in result["action"]
    assert result["level"] == 3
    
    # 测试不同的调整类型
    args_dict = {"position": "passenger", "adjustment": "recline", "level": 7}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert "Adjust passenger seat recline" in result["action"]
    assert result["level"] == 7
    
    # 测试按摩功能（带模式）
    args_dict = {"position": "driver", "adjustment": "massage", "massage_mode": "relax", "level": 5}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert "Set driver seat massage to relax mode" in result["action"]
    assert result["intensity"] == 5
    
    # 测试错误情况：按摩功能未提供模式
    args_dict = {"position": "driver", "adjustment": "massage"}
    result = tool.run(args_dict)
    assert result["status"] == "error"
    assert "请指定按摩模式" in result["message"]
    
    # 测试不同座椅位置
    args_dict = {"position": "rear_left", "adjustment": "up", "level": 2}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert "Adjust rear_left seat up" in result["action"]
    
    args_dict = {"position": "rear_right", "adjustment": "down", "level": 4}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert "Adjust rear_right seat down" in result["action"]
    
    # 测试默认级别（未指定level）
    args_dict = {"position": "driver", "adjustment": "backward"}
    result = tool.run(args_dict)
    assert result["status"] == "success"
    assert result["level"] == 5  # 默认值


TOOLS = [
    ControlACTool(),
    VehicleStatusTool(),
    NavigationTool(),
    MultimediaTool(),
    SeatControlTool(),
]


def main():

    # for t in TOOLS:
    #     print(t)

    # return

    test_base_tool_to_param()
    test_control_ac_tool()
    test_vehicle_status_tool()
    test_navigation_tool()
    test_multimedia_tool()
    test_seat_control_tool()

if __name__ == "__main__":
    #test_navigation_tool()
    main()
