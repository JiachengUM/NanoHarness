"""虚拟车车控工具。

与 projects/mind/toolset/car_control.py 接口保持一致，但操作虚拟车状态而非调用真实车控API。
用于 time_travel_auto_test 场景下的被测 Agent 测试。

设计（对齐车控标签树扩展后的 69 字段虚拟车模型）：
- 指令解析产出 {car_info key: 中文值} 写入集，统一走 VirtualCar.set_field 落盘：
  devices 是唯一真相源，set_field 负责中文值 → devices 字段解析，
  并触发 on_field_change 钩子（Runner 旁路发射 car_set_state 事件，可视化可见）
- 设备覆盖面（车控子树）：空调（开关/模式/温度/风量/风向）、
  座椅（加热/通风/按摩/零重力，四座独立）、方向盘加热、
  车窗/天窗/遮阳帘（开合度，四门独立）、车门/后备箱/门锁、
  阅读灯/氛围灯/大灯、车载电视、车载冰箱（温度/模式）、驾驶（档位/手刹）
- 导航和媒体不是车控：分别由独立工具 NavigationControlTool /
  MediaControlTool 控制（demos/v2_agent_to_test/tools/）
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from aicore.runtime.task import TaskManager
from aicore.v2.tools.factory import create_tool

if TYPE_CHECKING:
    from projects.experiments.time_travel_auto_test.virtual_car.models import VirtualCar

__all__ = ["VirtualCarControlInput", "VirtualCarControlOutput", "VirtualCarControlTool"]

logger = logging.getLogger(__name__)

# 四座前缀（car_info key 前缀）
_SEAT_TARGETS: list[tuple[str, tuple[str, ...]]] = [
    ("主驾", ("主驾", "驾驶位", "主驾驶", "司机")),
    ("副驾", ("副驾", "副驾驶", "副座")),
    ("二排左侧", ("二排左", "后排左", "左后", "后排左侧")),
    ("二排右侧", ("二排右", "后排右", "右后", "后排右侧")),
]

_LIGHT_COLORS = ("红", "橙", "黄", "绿", "蓝", "紫", "粉", "白", "青")


class VirtualCarControlInput(BaseModel):
    """虚拟车控指令参数"""

    command: str = Field(
        description=(
            "车控指令的自然语言描述。\n"
            "支持：\n"
            "- 空调：打开/关闭空调、空调调到N度、制冷/制热/暖风/通风、风量N档/调大/调小/自动、风向吹脸/吹脚/吹脸和脚/自动\n"
            "- 座椅：主驾/副驾/二排左/二排右 加热/通风（开/关/N档/最高）、座椅按摩（轻柔/舒缓/活力）、零重力模式开启/退出\n"
            "- 方向盘：方向盘加热 开/关/N档\n"
            "- 门窗：主驾/副驾/二排车窗 开/关/半开/一条缝（行驶中禁止开窗）、车门上锁/解锁/打开/关上、打开/关闭后备箱\n"
            "- 天窗遮阳帘：天窗开/关/翘起/一半/一条缝、遮阳帘开/关/一半\n"
            "- 灯光：主驾/副驾阅读灯 开/关/亮度N%/调亮/调暗、氛围灯 开/关/颜色（红橙黄绿蓝紫粉白青）/亮度/模式（常亮/呼吸/流动/随音乐律动）、近光灯/远光灯/示廓灯/自动大灯/关闭\n"
            "- 电器：车载电视开/关、车载冰箱开/关/温度N度/零下N度/冷藏/冷冻\n"
            "- 驾驶：挂D档/挂P档、拉手刹/松手刹（行驶中通常模拟驾驶员操作，不通过语音控制）\n"
            "注意：导航和媒体控制不是车控指令，请分别使用导航工具（navigation）和媒体工具（media）。"
        )
    )


class VirtualCarControlOutput(BaseModel):
    """虚拟车控执行结果"""

    status: str = Field(description="执行状态: success / error / partial")
    message: str = Field(description="执行结果描述")
    observation: dict | None = Field(default=None, description="变更后的相关状态")


def _match_targets(cmd: str) -> list[str]:
    """从指令中解析目标座位/门窗前缀（多选；默认主驾）。"""
    targets = [prefix for prefix, kws in _SEAT_TARGETS if any(kw in cmd for kw in kws)]
    if not targets or any(kw in cmd for kw in ("所有", "全部", "全车", "四门", "四窗")):
        targets = [prefix for prefix, _ in _SEAT_TARGETS]
    return targets


def _is_off_cmd(cmd: str) -> bool:
    return any(k in cmd for k in ("关闭", "关掉", "关上", "关一下"))


class VirtualCarController:
    """虚拟车控制器：解析自然语言车控指令 → set_field 写入。"""

    def __init__(self, virtual_car: VirtualCar):
        self.car = virtual_car

    async def execute(self, command: str) -> VirtualCarControlOutput:
        """执行车控指令。"""
        if not command or not command.strip():
            return VirtualCarControlOutput(status="error", message="指令为空")

        cmd = command.strip()
        logger.info("执行虚拟车控指令: %s", cmd)

        writes: dict[str, str] = {}
        message = ""

        # 分发（顺序敏感：方向盘先于座椅加热、天窗先于车窗）
        # 导航/媒体不在车控内——由独立工具 NavigationControlTool /
        # MediaControlTool 处理（见 demos/v2_agent_to_test/tools/）
        if "方向盘" in cmd:
            message = self._control_steering(cmd, writes)
        elif any(kw in cmd for kw in ("座椅", "按摩", "零重力")):
            message = self._control_seat(cmd, writes)
        elif "遮阳帘" in cmd:
            message = self._control_shade(cmd, writes)
        elif "天窗" in cmd:
            message = self._control_sunroof(cmd, writes)
        elif any(kw in cmd for kw in ("车窗", "窗户", "开窗", "关窗")):
            message = self._control_window(cmd, writes)
        elif any(kw in cmd for kw in ("后备箱", "尾箱")):
            message = self._control_trunk(cmd, writes)
        elif any(kw in cmd for kw in ("上锁", "解锁", "锁车", "锁门", "车门", "开车门")):
            message = self._control_door_lock(cmd, writes)
        elif any(kw in cmd for kw in ("阅读灯", "氛围灯", "大灯", "近光", "远光", "示廓", "示宽", "灯光")):
            message = self._control_light(cmd, writes)
        elif "电视" in cmd:
            message = self._control_tv(cmd, writes)
        elif "冰箱" in cmd:
            message = self._control_fridge(cmd, writes)
        elif any(kw in cmd for kw in ("空调", "温度", "冷风", "暖风", "制冷", "制热", "风量", "风速", "风向", "吹脸", "吹脚")):
            message = self._control_ac(cmd, writes)
        else:
            return VirtualCarControlOutput(status="error", message=f"不支持的车控指令: {cmd}")

        if not writes:
            return VirtualCarControlOutput(status="error", message=message or "未识别指令")

        # 统一落盘：set_field 解析中文值 → devices，并触发车态变更钩子（可视化事件）
        for key, value in writes.items():
            self.car.set_field(key, value)
        changes = {key: self.car.get_field(key) for key in writes}
        return VirtualCarControlOutput(
            status="success",
            message=message or f"车控成功：{'；'.join(f'{k}={v}' for k, v in changes.items())}",
            observation=changes,
        )

    # ---------------- 空调 ----------------

    def _control_ac(self, cmd: str, writes: dict) -> str:
        """空调：开关/模式/温度/风量/风向。"""
        if "制冷" in cmd or "冷风" in cmd:
            writes["空调开启状态及模式"] = "制冷中"
        elif "制热" in cmd or "暖风" in cmd:
            writes["空调开启状态及模式"] = "加热中"
        elif _is_off_cmd(cmd):
            writes["空调开启状态及模式"] = "关闭中"
        elif any(k in cmd for k in ("打开", "开启", "开一下", "开空调")):
            writes["空调开启状态及模式"] = "制冷中"

        # 温度：直接设定 / 加减一档
        m = re.search(r'(\d{1,2})\s*度', cmd)
        if m and 16 <= int(m.group(1)) <= 30:
            writes["空调温度"] = f"{int(m.group(1))}°C"
        elif any(k in cmd for k in ("调高", "热一点", "高一点", "暖一点")):
            writes["空调温度"] = f"{min(30, self.car.ac.temperature + 1)}°C"
        elif any(k in cmd for k in ("调低", "冷一点", "低一点")):
            writes["空调温度"] = f"{max(16, self.car.ac.temperature - 1)}°C"

        # 风量
        if "风量" in cmd or "风速" in cmd:
            if "自动" in cmd:
                writes["空调风量"] = "自动"
            else:
                cur = self._current_fan_base()
                m_level = re.search(r'([123])\s*档', cmd)
                if m_level:
                    writes["空调风量"] = f"{m_level.group(1)}档"
                elif any(k in cmd for k in ("调大", "大一点", "最大", "最高")):
                    writes["空调风量"] = f"{min(3, cur + 1)}档"
                elif any(k in cmd for k in ("调小", "小一点", "最低")):
                    writes["空调风量"] = f"{max(1, cur - 1)}档"

        # 风向
        if "风向" in cmd or "吹脸" in cmd or "吹脚" in cmd:
            if "吹脸和脚" in cmd or ("吹脸" in cmd and "吹脚" in cmd):
                writes["空调风向"] = "吹脸和脚"
            elif "吹脸" in cmd:
                writes["空调风向"] = "吹脸"
            elif "吹脚" in cmd:
                writes["空调风向"] = "吹脚"
            elif "自动" in cmd:
                writes["空调风向"] = "自动"

        return ""

    def _current_fan_base(self) -> int:
        """当前风量档位数值（自动按 2 档参与加减）。"""
        cur = str(self.car.get_field("空调风量"))
        if cur == "自动":
            return 2
        if cur == "关闭":
            return 0
        try:
            return int(cur.replace("档", ""))
        except ValueError:
            return 2

    # ---------------- 座椅 / 方向盘 ----------------

    def _control_seat(self, cmd: str, writes: dict) -> str:
        """座椅：加热/通风（档位）、按摩（模式）、零重力模式。"""
        targets = _match_targets(cmd)
        funcs = []
        if "加热" in cmd:
            funcs.append("加热")
        if "通风" in cmd:
            funcs.append("通风")
        if "按摩" in cmd:
            funcs.append("按摩")
        if "零重力" in cmd or "座椅模式" in cmd:
            funcs.append("模式")

        for t in targets:
            for func in funcs:
                key = f"{t}座椅{func}"
                if func == "按摩":
                    if _is_off_cmd(cmd) or "停" in cmd:
                        writes[key] = "关闭"
                    else:
                        writes[key] = next((m for m in ("轻柔", "舒缓", "活力") if m in cmd), "轻柔")
                elif func == "模式":
                    if any(k in cmd for k in ("关闭", "退出", "取消", "恢复", "标准", "坐直")):
                        writes[key] = "标准"
                    else:
                        writes[key] = "零重力"
                else:
                    # 加热/通风：档位
                    if _is_off_cmd(cmd) or "停" in cmd:
                        writes[key] = "关闭"
                    else:
                        m = re.search(r'([123])\s*档', cmd)
                        if m:
                            writes[key] = f"{m.group(1)}档"
                        elif any(k in cmd for k in ("最大", "最高")):
                            writes[key] = "3档"
                        elif "高" in cmd:
                            writes[key] = "3档"
                        elif "中" in cmd:
                            writes[key] = "2档"
                        elif "低" in cmd or "轻" in cmd:
                            writes[key] = "1档"
                        else:
                            writes[key] = "2档"
        return ""

    def _control_steering(self, cmd: str, writes: dict) -> str:
        """方向盘加热。"""
        if _is_off_cmd(cmd):
            writes["方向盘加热"] = "关闭"
        else:
            m = re.search(r'([123])\s*档', cmd)
            if m:
                writes["方向盘加热"] = f"{m.group(1)}档"
            elif any(k in cmd for k in ("最大", "最高", "高")):
                writes["方向盘加热"] = "3档"
            else:
                writes["方向盘加热"] = "2档"
        return ""

    # ---------------- 天窗 / 遮阳帘 / 车窗 ----------------

    def _control_sunroof(self, cmd: str, writes: dict) -> str:
        if "翘起" in cmd:
            writes["天窗状态"] = "翘起"
        elif _is_off_cmd(cmd):
            writes["天窗状态"] = "关闭"
        elif "一半" in cmd or "半开" in cmd:
            writes["天窗状态"] = "半开 (50%)"
        elif "缝" in cmd:
            writes["天窗状态"] = "半开 (15%)"
        else:
            writes["天窗状态"] = "打开"
        return ""

    def _control_shade(self, cmd: str, writes: dict) -> str:
        if _is_off_cmd(cmd):
            writes["遮阳帘开合度"] = "关闭"
        elif "一半" in cmd or "半开" in cmd:
            writes["遮阳帘开合度"] = "半开 (50%)"
        else:
            writes["遮阳帘开合度"] = "打开"
        return ""

    def _control_window(self, cmd: str, writes: dict) -> str:
        # 行驶安全检查
        opening = any(k in cmd for k in ("打开", "开一点", "半开", "一条缝")) or ("开" in cmd and "关" not in cmd)
        if self.car.driving.speed_kmh > 0 and opening:
            return f"行驶中（{self.car.driving.speed_kmh} km/h）无法执行开窗操作"

        for t in _match_targets(cmd):
            key = f"{t}车窗"
            if _is_off_cmd(cmd):
                writes[key] = "关闭"
            elif "一半" in cmd or "半开" in cmd:
                writes[key] = "半开 (50%)"
            elif "缝" in cmd:
                writes[key] = "半开 (15%)"
            else:
                writes[key] = "打开"
        return ""

    # ---------------- 车门 / 后备箱 / 门锁 ----------------

    def _control_trunk(self, cmd: str, writes: dict) -> str:
        if _is_off_cmd(cmd) or "关" in cmd:
            writes["后备箱状态"] = "关闭"
        else:
            if self.car.driving.speed_kmh > 0:
                return f"行驶中（{self.car.driving.speed_kmh} km/h）无法打开后备箱"
            writes["后备箱状态"] = "打开"
        return ""

    def _control_door_lock(self, cmd: str, writes: dict) -> str:
        targets = _match_targets(cmd)
        # 开关车门
        if "门" in cmd and any(k in cmd for k in ("打开", "开车门")):
            if self.car.driving.speed_kmh > 0:
                return f"行驶中（{self.car.driving.speed_kmh} km/h）无法执行开门操作"
            for t in targets:
                writes[f"{t}门状态"] = "打开"
            return ""
        if "门" in cmd and any(k in cmd for k in ("关上", "关门")):
            for t in targets:
                writes[f"{t}门状态"] = "关闭未上锁"
            return ""
        # 锁
        if any(k in cmd for k in ("解锁", "开锁")):
            for t in targets:
                writes[f"{t}门状态"] = "关闭未上锁"
        else:
            for t in targets:
                writes[f"{t}门状态"] = "关闭并上锁"
        return ""

    # ---------------- 灯光 ----------------

    def _control_light(self, cmd: str, writes: dict) -> str:
        if "阅读灯" in cmd:
            targets = _match_targets(cmd)
            for t in targets:
                writes[f"{t}阅读灯"] = "关闭" if _is_off_cmd(cmd) else "开启"
            m = re.search(r'(\d{1,3})\s*%', cmd)
            if m:
                writes["阅读灯亮度"] = f"{min(100, int(m.group(1)))}%"
            elif any(k in cmd for k in ("调亮", "亮一点", "调高")):
                writes["阅读灯亮度"] = f"{min(100, self.car.devices.interior_light.reading_light_brightness + 20)}%"
            elif any(k in cmd for k in ("调暗", "暗一点", "调低")):
                writes["阅读灯亮度"] = f"{max(0, self.car.devices.interior_light.reading_light_brightness - 20)}%"
        elif "氛围灯" in cmd:
            writes["氛围灯"] = "关闭" if _is_off_cmd(cmd) else "开启"
            for color in _LIGHT_COLORS:
                if color in cmd:
                    writes["氛围灯颜色"] = f"{color}色"
                    break
            m = re.search(r'(\d{1,3})\s*%', cmd)
            if m:
                writes["氛围灯亮度"] = f"{min(100, int(m.group(1)))}%"
            elif any(k in cmd for k in ("调亮", "亮一点")):
                writes["氛围灯亮度"] = f"{min(100, self.car.devices.interior_light.ambient_light_brightness + 20)}%"
            elif any(k in cmd for k in ("调暗", "暗一点")):
                writes["氛围灯亮度"] = f"{max(0, self.car.devices.interior_light.ambient_light_brightness - 20)}%"
            if "呼吸" in cmd:
                writes["氛围灯模式"] = "呼吸"
            elif "流动" in cmd:
                writes["氛围灯模式"] = "流动"
            elif "律动" in cmd:
                writes["氛围灯模式"] = "随音乐律动"
            elif "常亮" in cmd:
                writes["氛围灯模式"] = "常亮"
        else:
            # 大灯
            if "近光" in cmd:
                writes["大灯模式"] = "近光灯"
            elif "远光" in cmd:
                writes["大灯模式"] = "远光灯"
            elif "示廓" in cmd or "示宽" in cmd:
                writes["大灯模式"] = "示廓灯"
            elif "自动" in cmd:
                writes["大灯模式"] = "自动"
            elif _is_off_cmd(cmd):
                writes["大灯模式"] = "关闭"
            else:
                writes["大灯模式"] = "近光灯"
        return ""

    # ---------------- 电视 / 冰箱 ----------------

    def _control_tv(self, cmd: str, writes: dict) -> str:
        writes["车载电视"] = "关闭中" if _is_off_cmd(cmd) else "开启中"
        return ""

    def _control_fridge(self, cmd: str, writes: dict) -> str:
        if _is_off_cmd(cmd):
            writes["车载冰箱"] = "关闭中"
        else:
            writes["车载冰箱"] = "开启中"
            m = re.search(r'零下\s*(\d{1,2})\s*度', cmd)
            if m:
                writes["冰箱温度"] = f"-{int(m.group(1))}°C"
            else:
                m = re.search(r'(\d{1,2})\s*度', cmd)
                if m and -20 <= int(m.group(1)) <= 10:
                    writes["冰箱温度"] = f"{int(m.group(1))}°C"
            if "冷冻" in cmd:
                writes["冰箱模式"] = "冷冻"
            elif "冷藏" in cmd:
                writes["冰箱模式"] = "冷藏"
        return ""


def VirtualCarControlTool(
    virtual_car: VirtualCar | None = None,
    task_manager: TaskManager | None = None,
) -> callable:
    """虚拟车控工具工厂。

    Args:
        virtual_car: 要控制的虚拟车实例。如果为None，需要从上下文获取。
        task_manager: 传入时走异步任务化执行（产生 TaskCreatedEvent 工具事件，
                      落到工具泳道/对话流）；不传时同步执行（兼容单测直接调用）。

    Returns:
        可执行的车控工具函数
    """
    controller = VirtualCarController(virtual_car) if virtual_car else None

    async def worker(command: str) -> VirtualCarControlOutput:
        nonlocal controller
        if controller is None:
            # 尝试从线程/上下文获取（实际使用时需要更完善的机制）
            return VirtualCarControlOutput(
                status="error",
                message="虚拟车实例未设置",
                observation=None,
            )
        return await controller.execute(command)

    return create_tool(
        name="car_control",
        description=(
            "控制虚拟车的车载设备：空调（开关/模式/温度/风量/风向）、座椅（四座加热/通风/按摩/零重力）、"
            "方向盘加热、车窗/天窗/遮阳帘、车门/后备箱/门锁、阅读灯/氛围灯/大灯、"
            "车载电视、车载冰箱、档位/手刹。"
            "注意：导航和媒体控制不是车控指令——请分别使用导航工具和媒体工具。"
        ),
        args_schema=VirtualCarControlInput,
        worker=worker,
        timeout=5.0,
        asyncable="async" if task_manager is not None else "sync",
        task_manager=task_manager,
    )
