"""导航/媒体独立工具单元测试（真实 VirtualCar 链路，无 LLM 依赖）。

导航和媒体是独立工具（非车控），操作虚拟车对应状态：
1. NavigationController：设目的地 / 取消 / 查询 / 空 / 无目的地
2. MediaController：播放控制 / 点歌 / 歌单 / 音量 / 音源 / 查询 / 切歌拒绝 / 不支持指令
3. 工具工厂：name 对齐 sgm navigation_v2_tool / media_v2_tool
"""

from __future__ import annotations

import re

import pytest

from projects.experiments.time_travel_auto_test.demos.v2_agent_to_test.tools.media_control import (
    MediaController,
    MediaControlTool,
)
from projects.experiments.time_travel_auto_test.demos.v2_agent_to_test.tools.navigation_control import (
    NavigationController,
    NavigationControlTool,
)
from projects.experiments.time_travel_auto_test.virtual_car.models import VirtualCar
from projects.sgm_prod.tools.Navigation import NavigationOutput


# ---------------- NavigationController ----------------

_DEST_RE = re.compile(
    r"(?:导航到|导航去|带我去|前往|开去|去)\s*(.+?)(?:吧|呗|好吗|谢谢|，|。)?$"
)


class FakeNavWorker:
    """模拟真实 NavigationWorker（火山 FC）的返回，不发网络请求。

    只负责模拟 FC 返回的 function_code + params，验证 NavigationController
    是否把结构化结果正确映射到虚拟车状态。
    """

    async def __call__(self, command: str) -> NavigationOutput:
        cmd = command.strip()
        if not cmd or cmd == "请导航":
            return NavigationOutput(status="error", message="未获取到导航结果")
        if "取消" in cmd:
            return NavigationOutput(
                status="success",
                observation={"functions": [{"function_code": "导航操作", "params": []}]},
            )
        if any(k in cmd for k in ("到哪", "状态", "多久")):
            return NavigationOutput(
                status="success",
                observation={"functions": [{"function_code": "导航目的地查询", "params": []}]},
            )
        m = _DEST_RE.search(cmd)
        if m and m.group(1).strip():
            return NavigationOutput(
                status="success",
                observation={
                    "functions": [
                        {
                            "function_code": "单目的地导航",
                            "params": [{"destination": m.group(1).strip()}],
                        }
                    ]
                },
            )
        return NavigationOutput(status="error", message="未获取到导航结果")


def _controller(car: VirtualCar) -> NavigationController:
    return NavigationController(car, worker=FakeNavWorker())


@pytest.mark.anyio
async def test_navigation_set_destination() -> None:
    car = VirtualCar()
    nav = _controller(car)

    out = await nav.execute("导航到虹桥火车站")
    assert out.status == "success"
    assert car.car_info["导航目的地"] == "虹桥火车站"
    assert car.car_info["导航状态"] == "导航中"
    assert out.observation == {"导航目的地": "虹桥火车站", "导航状态": "导航中"}


@pytest.mark.anyio
async def test_navigation_set_destination_variants() -> None:
    """带我去 / 导航去 / 去 均可设置目的地。"""
    car = VirtualCar()
    nav = _controller(car)

    out = await nav.execute("带我去公司")
    assert out.status == "success"
    assert car.car_info["导航目的地"] == "公司"

    out = await nav.execute("导航去浦东机场")
    assert out.status == "success"
    assert car.car_info["导航目的地"] == "浦东机场"


@pytest.mark.anyio
async def test_navigation_cancel() -> None:
    car = VirtualCar()
    nav = _controller(car)
    await nav.execute("导航到虹桥火车站")

    out = await nav.execute("取消导航")
    assert out.status == "success"
    assert car.car_info["导航状态"] == "未导航"
    assert car.car_info["导航目的地"] == "未设置"


@pytest.mark.anyio
async def test_navigation_query_while_navigating() -> None:
    """查询不改状态，返回当前目的地。"""
    car = VirtualCar()
    nav = _controller(car)
    await nav.execute("导航去浦东机场")

    out = await nav.execute("现在导航到哪了")
    assert out.status == "success"
    assert "浦东机场" in out.message
    assert car.car_info["导航状态"] == "导航中"
    assert car.car_info["导航目的地"] == "浦东机场"


@pytest.mark.anyio
async def test_navigation_query_idle() -> None:
    car = VirtualCar()
    nav = _controller(car)

    out = await nav.execute("导航状态")
    assert out.status == "success"
    assert "未在导航" in out.message


@pytest.mark.anyio
async def test_navigation_invalid_commands() -> None:
    car = VirtualCar()
    nav = _controller(car)

    assert (await nav.execute("")).status == "error"
    assert (await nav.execute("   ")).status == "error"
    # 有导航动词但无目的地：真实 FC 解析失败 → 透传错误
    out = await nav.execute("请导航")
    assert out.status == "error"
    assert "未获取到导航结果" in out.message


# ---------------- MediaController ----------------


@pytest.mark.anyio
async def test_media_play_generic() -> None:
    """泛化播放词不点歌，只置播放状态。"""
    car = VirtualCar()
    media = MediaController(car)

    out = await media.execute("播放音乐")
    assert out.status == "success"
    assert car.car_info["多媒体播放状态"] == "播放中"
    assert car.car_info["正在播放的歌曲名"] == "无"


@pytest.mark.anyio
async def test_media_play_specific_song() -> None:
    car = VirtualCar()
    media = MediaController(car)

    out = await media.execute("播放周杰伦的晴天")
    assert out.status == "success"
    assert car.car_info["正在播放的歌手名"] == "周杰伦"
    assert car.car_info["正在播放的歌曲名"] == "晴天"
    assert car.car_info["多媒体播放状态"] == "播放中"


@pytest.mark.anyio
async def test_media_play_playlist() -> None:
    car = VirtualCar()
    media = MediaController(car)

    out = await media.execute("播放歌单晚安曲")
    assert out.status == "success"
    assert car.car_info["正在播放的歌单名"] == "晚安曲"


@pytest.mark.anyio
async def test_media_pause_resume_stop() -> None:
    car = VirtualCar()
    media = MediaController(car)

    await media.execute("播放音乐")
    await media.execute("暂停")
    assert car.car_info["多媒体播放状态"] == "暂停中"

    await media.execute("继续播放")
    assert car.car_info["多媒体播放状态"] == "播放中"

    await media.execute("停止播放")
    assert car.car_info["多媒体播放状态"] == "停止中"


@pytest.mark.anyio
async def test_media_volume() -> None:
    car = VirtualCar()  # 默认音量 30%
    media = MediaController(car)

    await media.execute("音量调到50%")
    assert car.car_info["音量"] == "50%"

    await media.execute("音量调大")
    assert car.car_info["音量"] == "60%"

    await media.execute("音量调小")
    assert car.car_info["音量"] == "50%"

    # 超界收敛到 [0, 100]
    await media.execute("音量调到200%")
    assert car.car_info["音量"] == "100%"


@pytest.mark.anyio
async def test_media_source_switch() -> None:
    car = VirtualCar()
    media = MediaController(car)

    out = await media.execute("切换到蓝牙音乐")
    assert out.status == "success"
    assert car.car_info["音源"] == "蓝牙音乐"

    await media.execute("切换到收音机")
    assert car.car_info["音源"] == "收音机"


@pytest.mark.anyio
async def test_media_query_now_playing() -> None:
    """查询返回当前歌曲信息，不改状态。"""
    car = VirtualCar()
    media = MediaController(car)
    await media.execute("播放周杰伦的晴天")

    out = await media.execute("现在放的什么歌")
    assert out.status == "success"
    assert "晴天" in out.message
    assert "周杰伦" in out.message
    assert car.car_info["多媒体播放状态"] == "播放中"


@pytest.mark.anyio
async def test_media_next_track_rejected() -> None:
    """切歌诚实拒绝（虚拟车无歌单队列，不编造歌曲）。"""
    car = VirtualCar()
    media = MediaController(car)

    out = await media.execute("下一首")
    assert out.status == "error"
    assert "无法切歌" in out.message


@pytest.mark.anyio
async def test_media_unsupported_command() -> None:
    car = VirtualCar()
    media = MediaController(car)

    out = await media.execute("帮我把歌词投屏")
    assert out.status == "error"


@pytest.mark.anyio
async def test_media_empty_command() -> None:
    car = VirtualCar()
    media = MediaController(car)

    assert (await media.execute("")).status == "error"
    assert (await media.execute("  ")).status == "error"


# ---------------- 工具工厂 ----------------


def test_navigation_tool_factory() -> None:
    tool = NavigationControlTool(VirtualCar())
    assert tool.name == "navigation"
    assert "导航" in tool.description


def test_media_tool_factory() -> None:
    tool = MediaControlTool(VirtualCar())
    assert tool.name == "media"
    assert "媒体" in tool.description


def test_tool_factory_without_car() -> None:
    """未绑定虚拟车时工具仍可创建（懒绑定场景）。"""
    tool = MediaControlTool()
    assert tool.name == "media"

    nav_tool = NavigationControlTool()
    assert nav_tool.name == "navigation"
