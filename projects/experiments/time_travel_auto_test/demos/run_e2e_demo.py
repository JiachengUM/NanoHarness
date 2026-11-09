"""端到端真实 LLM 测试 demo：协议封装待测 agent + 内置 case + 自动跑测 + Judge 评判。

直接运行（在 demos 目录下或仓库根目录均可）：

    python run_e2e_demo.py

修改下方 ==== 配置区域 ==== 的变量即可切换 case 和参数，无需命令行。

也支持命令行参数（优先级高于文件配置）：

    --case builtin        跑内置的简单 case（默认，固定台词）
    --case builtin-accel   跑内置的时间加速 case
    --case llm-speak       跑内置的 LLM 自主对话 case（content=None，假人自主生成台词）
    --case interrupt       跑内置的插话重叠测试 case（非 fast_mode，验证中立观察者模型）
    --case scheduled       跑内置的定时任务 case（快进不跳过 + 主动提醒）
    --case complex         跑内置的综合 case（插话重叠 + 定时任务 + 快进 + 记忆 + 恢复轮）
    --case navigation      跑内置的多条件导航 case（长耗时导航工具 + 中途改目的地）
    --case trip-mixed      跑内置的行程混编 case（导航 + POI + 音乐，同步工具 + 异步回灌）
    --case fixture         跑 test/cases/fixture_cases.json 中的 case-001
    --case-id case-001    指定 fixture 中的 case id（配合 --case fixture 使用）
    --no-judge            跳过 Judge 评判，只打印 trace
    --no-streaming        关闭流式回复（关闭后无 chunk 级时间戳）
    --fast-mode           开启 fast_mode（跳过锚点的真实时间等待，仅用于快速演示）

本 demo 展示完整链路：
1. 代码内定义一个 TestCase（或从 fixture_cases.json 加载）
2. 用 TestedAssistant（协议封装的真实 LLM 待测 agent）
3. 用 CaseRunner 跑自动测试（含时间加速 / 插话重叠 / 主动智能）
4. 用 Judge 评判 trace + 断言，输出打分与每条断言结果
5. 打印完整 trace 文本与 verdict
"""

from __future__ import annotations

import argparse
import asyncio
import io
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 确保无论从哪个目录运行都能找到 projects 包
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Windows 控制台默认 GBK 编码无法打印 ✓/✗ 等 Unicode 字符，强制改 UTF-8。
# 注意：仅在 main() 里调用（import 不能有副作用——pytest capture 等会被炸掉）。
def setup_windows_utf8_console() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
            )
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
            )
        except Exception:
            pass

# ========================================================================
# 配置区域 —— 直接改这里的变量即可切换 case 和参数
# ========================================================================
ACTIVE_CASE: str = "scheduled"            # builtin | builtin-accel | time-aware | llm-speak | interrupt | scheduled | fixture
FIXTURE_CASE_ID: str = "case-001"      # 配合 ACTIVE_CASE = "fixture" 使用
ENABLE_JUDGE: bool = True              # True = 跑 Judge 评判，False = 只跑不评分
USE_STREAMING: bool = True             # True = 流式回复，False = 非流式
FAST_MODE: bool = False                # True = 跳过锚点时间等待
# ========================================================================

from projects.experiments.time_travel_auto_test.case_runner.runner import (
    CaseRunner,
    RunnerConfig,
)
from projects.experiments.time_travel_auto_test.case_schema import (
    FakePersonInfo,
    TestCase,
    VirtualCarInfo,
    load_test_cases_from_json_file,
)
from projects.experiments.time_travel_auto_test.demos.v2_agent_to_test.tested_assistant import (
    TestedAssistant,
)
from projects.experiments.time_travel_auto_test.fake_person.models import (
    FakePersonSpeakArgs,
    FakePersonSpeakPerformAction,
)
from projects.experiments.time_travel_auto_test.judge.judge import (
    Judge,
    build_judge_input_from_run_result,
)
from projects.experiments.time_travel_auto_test.judge.prompt import render_timeline_text
from projects.experiments.time_travel_auto_test.script_events.script_event import (
    FakePersonScriptEvent,
    VirtualCarPerformScriptEvent,
    VirtualCarSetStateArgs,
    VirtualCarSetStatePerformAction,
    VirtualCarStateCheckAction,
    VirtualCarStateCheckArgs,
    VirtualCarStateCheckScriptEvent,
)


# ---------------- 内置 case ----------------


def build_builtin_case() -> TestCase:
    """构造一个内置的简单 case：开空调 + 短静默 + 状态检查。

    特点：
    - 固定台词（不依赖假人 LLM）
    - t0 用 datetime.now() 让虚拟时间和真实时间对齐
    - 单假人、单轮对话、单 state_check
    - 不触发时间加速（锚点间隔 45s < 默认阈值 60s）
    """
    return TestCase(
        id="builtin-simple-ac",
        case_name="内置_开空调_状态检查",
        case_description=(
            "主驾用固定台词请求开空调；车辆静止。"
            "空调是否开启须由被测助手调用车控接口改变虚拟车状态，"
            "剧本不直接 set_state 代开。"
        ),
        tags=["空调", "固定台词", "静止", "内置demo"],
        fake_persons=[
            FakePersonInfo(
                role_id="driver",
                profile="李明，32岁，互联网公司产品经理，说话直接",
            )
        ],
        virtual_car=VirtualCarInfo(
            car_info={
                "车辆当前行驶速度": "0 km/h（静止）",
                "车辆当前档位": "P档（驻车档）",
                "车辆点火状态": "通电",
                "手刹状态": "拉起",
                "车内温度": "29摄氏度",
                "车外温度": "35°C",
                "空调开启状态及模式": "关闭中",
                "主驾是否有人": "有人",
                "副驾是否有人": "没人",
                "多媒体播放状态": "停止中",
                "导航状态": "未导航",
                "氛围灯": "关闭",
                "当前位置": "上海平金中心地下停车场B2",
            }
        ),
        script_events=[
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content="你好小涂，有点热，把空调打开吧。"
                    ),
                ),
            ),
        ],
        virtual_car_state_check_assertions=[
            VirtualCarStateCheckScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=45),
                target="car",
                action=VirtualCarStateCheckAction(
                    args=VirtualCarStateCheckArgs(
                        expected_fields={"空调开启状态及模式": "制冷中"}
                    ),
                ),
            ),
        ],
        text_script=(
            "用户：你好小涂，有点热，把空调打开吧。\n"
            "助手：好的，已为您打开空调并调至舒适温度。"
        ),
        must_pass_assertions=[
            "助手应理解用户觉得热并开启或调节空调",
            "车辆静止时不应拒绝合理的空调控制请求",
        ],
        bonus_assertions=[
            "助手应主动询问用户期望的温度",
        ],
    )


def build_builtin_god_view_case() -> TestCase:
    """构造上帝视角改车态的内置 case：剧本 set_state 与助手车控混合来源。

    特点：
    - T0: 假人请助手开空调（助手车控路径，car_set_state source=assistant）
    - T0+20s: 剧本上帝视角 set_state（起步行驶：速度/档位/车外温度，
      car_set_state source=script）
    - T0+45s: state_check 同时验证助手改的空调字段与剧本改的车速
    - 供可视化验证车态变更来源三色区分（金色=剧本 / 红色=助手）
      与时间线未来区预设事件竖线（script_plan 预览）
    """
    return TestCase(
        id="builtin-god-view",
        case_name="内置_上帝视角改车态_混合来源",
        case_description=(
            "假人请助手开空调（助手改车态），随后剧本以上帝视角直接 set_state "
            "让车辆起步行驶。state_check 验证两种来源的字段混合后的最终状态。"
        ),
        tags=["上帝视角", "剧本set_state", "混合来源", "内置demo"],
        fake_persons=[
            FakePersonInfo(
                role_id="driver",
                profile="李明，32岁，互联网公司产品经理，说话直接",
            )
        ],
        virtual_car=VirtualCarInfo(
            car_info={
                "车辆当前行驶速度": "0 km/h（静止）",
                "车辆当前档位": "P档（驻车档）",
                "车内温度": "29摄氏度",
                "车外温度": "35°C",
                "空调开启状态及模式": "关闭中",
                "主驾是否有人": "有人",
                "多媒体播放状态": "停止中",
                "导航状态": "未导航",
                "当前位置": "上海平金中心地下停车场B2",
            }
        ),
        script_events=[
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content="你好小涂，有点热，把空调打开吧。"
                    ),
                ),
            ),
            VirtualCarPerformScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=20),
                target="car",
                action=VirtualCarSetStatePerformAction(
                    args=VirtualCarSetStateArgs(
                        fields={
                            "车辆当前行驶速度": "40 km/h",
                            "车辆当前档位": "D档（前进档）",
                            "车外温度": "33°C",
                        }
                    ),
                ),
            ),
        ],
        virtual_car_state_check_assertions=[
            VirtualCarStateCheckScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=45),
                target="car",
                action=VirtualCarStateCheckAction(
                    args=VirtualCarStateCheckArgs(
                        expected_fields={
                            "空调开启状态及模式": "制冷中",
                            "车辆当前行驶速度": "40 km/h",
                        }
                    ),
                ),
            ),
        ],
        text_script=(
            "用户：你好小涂，有点热，把空调打开吧。\n"
            "助手：好的，已为您打开空调并调至舒适温度。\n"
            "（20秒后剧本上帝视角：车辆起步，40 km/h 巡航）"
        ),
        must_pass_assertions=[
            "助手应理解用户觉得热并开启或调节空调",
        ],
    )


def build_builtin_case_with_acceleration() -> TestCase:
    """构造一个触发时间加速的内置 case：用户告诉地址 → 1 天后追问记忆。

    特点：
    - T0: 假人说"记住，我家在浦江镇"
    - 助手确认记录
    - T0 + 1 天：时间加速 → _maybe_accelerate → aupdate_context 通知助手
    - T0 + 1 天：假人追问"昨天跟你说过我家在哪，还记得吗？"
    - 验证跨天时间加速 + 助手上下文记忆保持
    """
    return TestCase(
        id="builtin-acceleration",
        case_name="内置_时间加速_跨天记忆追问",
        case_description=(
            "用户告诉助手家庭地址后，1 天后追问是否还记得。"
            "1 天的时间间隔远大于 60s 默认阈值，会触发 Runner 时间加速。"
            "验证跨天时间加速 + 助手上下文记忆保持。"
        ),
        tags=["时间加速", "跨天", "记忆", "内置demo"],
        fake_persons=[
            FakePersonInfo(
                role_id="driver",
                profile="李明，32岁，互联网公司产品经理，说话直接",
            )
        ],
        virtual_car=VirtualCarInfo(
            car_info={
                "车辆当前行驶速度": "0 km/h（静止）",
                "车辆当前档位": "P档（驻车档）",
                "主驾是否有人": "有人",
                "副驾是否有人": "没人",
                "多媒体播放状态": "播放中",
                "正在播放的歌曲名": "晚风",
                "正在播放的歌手名": "伍佰",
                "正在播放的歌单名": "华语经典",
                "音量": "30%",
                "导航状态": "未导航",
                "当前位置": "上海平金中心地下停车场B2",
            }
        ),
        script_events=[
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content="记住，我家住在浦江镇。",
                    ),
                ),
            ),
            # T+1天：触发时间加速
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(days=1),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content="昨天跟你说过我家在哪，还记得吗？",
                    ),
                ),
            ),
        ],
        text_script=(
            "用户：记住，我家住在浦江镇。\n"
            "助手：好的，已记录您的家庭地址。\n"
            "[1天后]\n"
            "用户：昨天跟你说过我家在哪，还记得吗？"
        ),
        must_pass_assertions=[
            "助手应确认收到用户的家庭地址信息",
            "1 天后用户追问时，助手应记住之前说过的浦江镇地址",
        ],
        bonus_assertions=[
            "助手在跨天追问后应主动确认地址信息无需更新",
        ],
    )


def build_builtin_time_awareness_case() -> TestCase:
    """构造一个专门验证时间快进后助手时间感知的 case。

    T0: 假人先问"现在几点？" → 助手回答 T0 时间
    T+2h: 时间加速 → aupdate_context 注入当前时间
    假人再问"现在几点？" → 助手应回答加速后的时间（比上次晚 2h）

    验证：
    - 时间快进后 aupdate_context 正确注入当前时间
    - 助手两次回答的时间差恰好等于快进的时间跨度
    """
    return TestCase(
        id="builtin-time-awareness",
        case_name="内置_时间快进_时间感知验证",
        case_description=(
            "T0 假人问现在几点，助手回答。2小时后触发时间加速，假人再问现在几点。"
            "验证助手通过 aupdate_context 感知到时间已推进 2 小时。"
        ),
        tags=["时间加速", "时间感知", "快进验证", "内置demo"],
        fake_persons=[
            FakePersonInfo(
                role_id="driver",
                profile="李明，32岁，互联网公司产品经理，说话直接",
            )
        ],
        virtual_car=VirtualCarInfo(
            car_info={
                "车辆当前行驶速度": "0 km/h（静止）",
                "车辆当前档位": "P档（驻车档）",
                "主驾是否有人": "有人",
                "多媒体播放状态": "暂停中",
                "导航状态": "未导航",
                "当前位置": "上海平金中心地下停车场B2",
            }
        ),
        script_events=[
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content="现在几点了？",
                    ),
                ),
            ),
            # T+2h：触发时间加速
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(hours=2),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content="现在几点了？",
                    ),
                ),
            ),
        ],
        text_script=(
            "用户：现在几点了？\n"
            "助手：现在是XXXX年X月X日XX点XX分。\n"
            "[2小时后，时间加速]\n"
            "用户：现在几点了？"
        ),
        must_pass_assertions=[
            "第一次问时间时，助手应回答当前时间",
            "2 小时后第二次问时间时，助手应回答比第一次晚 2 小时的时间，"
            "证明时间快进后助手感知到了时间推进",
        ],
        bonus_assertions=[
            "助手两次回答的时间格式应清晰易读",
        ],
    )


def build_builtin_llm_speak_case() -> TestCase:
    """构造一个假人 LLM 自主对话的 case：高温车内 → 假人主动要求开空调。

    特点：
    - content=None：假人不拿固定台词，靠 LLM 自主理解剧本意图 + 车态 + 人设生成第一句话
    - llm_speak_directives 注入 system prompt，引导假人判断意图、识别前置依赖、理解硬件不可语音传递
    - 以 __LLM_SPEAK_OPEN__ 信号触发开场
    - 剧本只描述场景和期望效果，不写死具体台词
    """
    return TestCase(
        id="builtin-llm-speak-ac",
        case_name="内置_LLM自主对话_高温开空调",
        case_description=(
            "假人上车，车内温度29°C、空调关闭。"
            "假人通过 LLM 自主理解场景意图，主动说出第一句话请求开空调。"
            "助手应理解并执行，改变虚拟车空调状态。"
        ),
        tags=["空调", "LLM自主", "真实对话", "内置demo"],
        fake_persons=[
            FakePersonInfo(
                role_id="driver",
                profile="李明，32岁，互联网公司产品经理，说话直接不客套，热了就直说",
            )
        ],
        virtual_car=VirtualCarInfo(
            car_info={
                "车辆当前行驶速度": "0 km/h（静止）",
                "车辆当前档位": "P档（驻车档）",
                "车内温度": "29摄氏度",
                "车外温度": "35°C",
                "空调开启状态及模式": "关闭中",
                "主驾是否有人": "有人",
                "副驾是否有人": "没人",
                "主驾座椅通风": "关闭",
                "多媒体播放状态": "停止中",
                "导航状态": "未导航",
                "当前位置": "上海平金中心地下停车场B2",
            }
        ),
        script_events=[
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content=None)  # LLM 自主发挥
                ),
            ),
        ],
        virtual_car_state_check_assertions=[
            VirtualCarStateCheckScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=45),
                target="car",
                action=VirtualCarStateCheckAction(
                    args=VirtualCarStateCheckArgs(
                        expected_fields={"空调开启状态及模式": "制冷中"}
                    ),
                ),
            ),
        ],
        text_script=(
            "用户上车后觉得太热，请求打开空调。\n"
            "助手应理解并执行，打开空调制冷。"
        ),
        must_pass_assertions=[
            "助手应理解用户觉得热并开启或调节空调",
        ],
        bonus_assertions=[
            "助手回复应简洁自然，不要啰嗦",
        ],
    )


def build_builtin_interrupt_case() -> TestCase:
    """构造插话重叠测试 case：助手正在说长回复 → 假人插话 → 双方重叠（如实记录）。

    中立观察者模型（框架不打断被测助手）：
    - 非 fast_mode：锚点按真实时间等待，插话按锚点时刻如实开口
    - T0：假人问"给我讲个笑话" → 助手纯 LLM 回复（不触发工具，立刻开始生成文本）
    - T0+6.5s：假人插话"算了，先开空调吧" → 与助手回复时间重叠
      （插话时机按"上一句假人说完毕后 6 秒"构造：假人 8 字台词约 0.5s 说完，
      助手思考 3-5s 才开口，T0+6.5s 时助手已说出一些字——打断的是"正在说话"
      而非"思考期"；插话时机是用例构造问题，与框架无关）
      （trace 记录"双方同时说话"窗口；框架不打断助手，回复完整说完）
    - 插话语句说完即投（即时投喂）：不等助手空闲 → 助手（不支持打断）两条流
      并行，均如实记录；插话指令由第二条流处理 → 响应开空调
    - T0+120s：时间加速 2 分钟 → _maybe_accelerate → aupdate_context 被调用
    - T0+120s：假人追问"空调开了吗" → 验证上下文记忆
    - T0+135s：state_check 验证空调 = 制冷中
    """
    return TestCase(
        id="builtin-interrupt",
        case_name="内置_插话重叠_笑话转空调",
        case_description=(
            "假人先让助手讲笑话（助手开始流式回复），假人说完 6 秒后插话说'算了，先开空调吧'，"
            "此时助手已说出一些字，插话与助手回复在时间上重叠——框架是中立观察者，不打断助手，"
            "trace 如实记录双方同时说话的重叠窗口；插话说完即投（不等助手空闲），"
            "助手（不支持打断）两条流并行，均如实记录，插话指令应被处理（开空调）。"
            "2 分钟后追问空调状态。"
            "验证插话重叠记录 + 即时投喂并发流 + 时间加速 + 上下文记忆。"
        ),
        tags=["插话重叠", "双方同时说话", "中立观察者", "时间加速", "内置demo"],
        fake_persons=[
            FakePersonInfo(
                role_id="driver",
                profile="李明，32岁，互联网公司产品经理，说话直接，容易改变主意",
            )
        ],
        virtual_car=VirtualCarInfo(
            car_info={
                "车辆当前行驶速度": "0 km/h（静止）",
                "车辆当前档位": "P档（驻车档）",
                "车内温度": "29摄氏度",
                "车外温度": "35°C",
                "空调开启状态及模式": "关闭中",
                "主驾是否有人": "有人",
                "副驾是否有人": "没人",
                "多媒体播放状态": "停止中",
                "导航状态": "未导航",
                "当前位置": "上海平金中心地下停车场B2",
            }
        ),
        script_events=[
            # T0: 要求讲笑话（纯 LLM 回复，不触发工具，立刻开始生成文本）
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="给我讲个笑话吧。"),
                ),
            ),
            # T0+6.5s: 插话，转开空调（假人说完约 T0+0.5s + 6s，此时助手已开口说话）
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=6.5),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="算了，不听笑话了，打开空调吧。"),
                ),
            ),
            # T0+120s: 时间加速后追问（2 分钟 > 60s 阈值 → 触发快进 + aupdate_context）
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=120),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(content="对了，刚才让你开空调，开了吗？"),
                ),
            ),
        ],
        virtual_car_state_check_assertions=[
            VirtualCarStateCheckScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=135),
                target="car",
                action=VirtualCarStateCheckAction(
                    args=VirtualCarStateCheckArgs(
                        expected_fields={"空调开启状态及模式": "制冷中"}
                    ),
                ),
            ),
        ],
        text_script=(
            "用户：给我讲个笑话吧。\n"
            "助手：（开始讲笑话……）\n"
            "用户：（插话，与助手回复重叠）算了，先不管笑话了，打开空调吧。\n"
            "助手：（说完笑话后）好的，已为您打开空调。\n"
            "[2分钟后]\n"
            "用户：对了，刚才让你开空调，开了吗？\n"
            "助手：是的，空调已经开着了。"
        ),
        must_pass_assertions=[
            "助手应正确响应'打开空调'的指令（插话即时投喂后仍被处理）",
            "2 分钟后追问时，助手应记住已开空调",
        ],
        bonus_assertions=[
            "助手收到插话后应转向处理空调指令，不再继续输出笑话内容",
        ],
    )


def build_builtin_scheduled_task_case() -> TestCase:
    """构造一个验证时间快进不会跳过定时任务的 case。

    T0: 假人说"提醒我30分钟后喝水" → Agent 设置提醒（T0+30min）
    T0+2h: 假人说话触发时间快进 → 多步快进在 T0+30min 触发点停靠
    → 定时任务到期，助手主动提醒"该喝水了"（主动智能）
    → 继续快进到 T0+2h
    T0+2h: 假人追问"我刚才让你提醒我什么来着？" → Agent 应记得已提醒

    验证：
    - 多步快进在定时任务触发点停靠，任务不会被快进跳过
    - 到期任务由助手主动开口提醒
    """
    return TestCase(
        id="builtin-scheduled-task",
        case_name="内置_定时任务_时间快进不跳过",
        case_description=(
            "T0 假人让助手设置30分钟后喝水提醒。2小时后假人说话触发时间快进，"
            "多步快进在30分钟提醒触发点停靠，助手主动提醒喝水（不被快进跳过），"
            "随后继续快进到2小时。"
        ),
        tags=["定时任务", "时间加速", "aupdate_context", "主动智能", "内置demo"],
        fake_persons=[
            FakePersonInfo(
                role_id="driver",
                profile="李明，32岁，互联网公司产品经理，说话直接",
            )
        ],
        virtual_car=VirtualCarInfo(
            car_info={
                "车辆当前行驶速度": "0 km/h（静止）",
                "车辆当前档位": "P档（驻车档）",
                "主驾是否有人": "有人",
                "副驾是否有人": "没人",
                "多媒体播放状态": "播放中",
                "正在播放的歌曲名": "晴天",
                "正在播放的歌手名": "周杰伦",
                "正在播放的歌单名": "我的最爱",
                "音量": "25%",
                "导航状态": "未导航",
                "当前位置": "上海平金中心地下停车场B2",
            }
        ),
        script_events=[
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content="提醒我30分钟后喝水",
                    ),
                ),
            ),
            # T+2h：触发时间快进（间隔 > 60s）
            # 多步快进在 T0+30min 提醒触发点停靠 → 到期任务主动触发 → 继续快进
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(hours=2),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content="我刚才让你提醒我什么来着？",
                    ),
                ),
            ),
        ],
        text_script=(
            "用户：提醒我30分钟后喝水。\n"
            "助手：好的，已为您设置30分钟后的喝水提醒。\n"
            "[时间快进：在30分钟提醒触发点停靠]\n"
            "助手应主动提醒：该喝水了。\n"
            "[继续快进到2小时后]\n"
            "用户：我刚才让你提醒我什么来着？\n"
            "助手应记得刚才提醒过喝水。"
        ),
        must_pass_assertions=[
            "助手应设置30分钟后的喝水提醒",
            "时间快进经过30分钟提醒触发点时，助手应主动提醒用户喝水"
            "（定时任务到期触发，不因快进被跳过）",
            "假人追问时，助手应记得刚刚提醒过喝水（说明定时任务已触发）",
        ],
        bonus_assertions=[
            "助手主动提醒的语气应自然友好",
        ],
    )


def build_builtin_complex_case() -> TestCase:
    """构造综合 case：闲聊 + 插话重叠（承载定时任务+车控指令）+ 时间快进 + 定时任务主动触发 + 记忆验证 + 恢复轮。

    三要素协同的时间线（中立观察者模型，框架不打断助手）：
    - T0: 假人随意闲聊开场（纯 LLM 流式回复，不调工具，助手思考 3-5s 后开口）
    - T0+7.5s: 假人插话（假人 24 字台词约 1.5s 说完 + 6s——助手已说出一些字，
      双方同时说话，如实记录重叠窗口），
      插话承载双指令：35 分钟后提醒拿快递 + 开空调
      → 插话说完即投（即时投喂，不等助手空闲）：助手（不支持打断）两条流并行
      → 助手调 set_reminder + 车控工具，回复期间创建定时任务
      → WorldTick 锚点注入（trigger - 5s 提前抵达）
    - 快进段1: → 锚点停靠（记"WorldTick 锚点到达"）→ drain 静默推进 5s
    - T0+35m±: 定时任务到期，助手主动提醒拿快递（主动智能）
    - 快进段2: → T0+1h
    - T0+1h: 假人说快递已拿到 + 关空调（验证记忆 + 恢复轮）
    - T0+1h+2m: state_check 验证空调已关闭（gap > 60s 触发快进段3）

    插话时机按"上一句假人说完毕后 6 秒"构造（假人说完约 T0+1.5s，助手思考
    3-5s 才开口，T0+7.5s 时助手正在说话）；插话时机是用例构造问题，与框架无关。
    """
    return TestCase(
        id="builtin-complex-combo",
        case_name="内置_综合_插话重叠定时任务快进",
        case_description=(
            "假人闲聊开场，假人说完 6 秒后在助手回复期间插话（此时助手已说出一些字，"
            "双方同时说话，框架不打断助手），"
            "插话承载 35 分钟拿快递提醒 + 开空调双指令，说完即投后由助手处理（并发流如实记录）。"
            "快进 35 分钟时定时任务主动触发提醒，1 小时后假人确认 "
            "快递已拿到并关闭空调（恢复轮），2 分钟后 state_check 验证空调关闭。"
            "验证插话重叠处理 + 定时任务不因重叠和快进丢失 + 主动智能 + 跨时记忆。"
        ),
        tags=["插话重叠", "定时任务", "时间加速", "主动智能", "记忆", "恢复轮", "内置demo"],
        fake_persons=[
            FakePersonInfo(
                role_id="driver",
                profile="李明，32岁，互联网公司产品经理，说话随意不客套，想到什么说什么",
            )
        ],
        virtual_car=VirtualCarInfo(
            car_info={
                "车辆当前行驶速度": "0 km/h（静止）",
                "车辆当前档位": "P档（驻车档）",
                "车内温度": "29摄氏度",
                "车外温度": "33°C",
                "空调开启状态及模式": "关闭中",
                "主驾是否有人": "有人",
                "副驾是否有人": "没人",
                "二排左侧是否有人": "没人",
                "二排右侧是否有人": "没人",
                "多媒体播放状态": "停止中",
                "导航状态": "未导航",
                "当前位置": "上海平金中心地下停车场B2",
            }
        ),
        script_events=[
            # T0: 随意闲聊开场（纯 LLM 回复，流式输出中）
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content="哎，今天跑了一天客户，累得不行，你陪我唠两句呗。"
                    ),
                ),
            ),
            # T0+7.5s: 插话（假人说完约 T0+1.5s + 6s，助手已开口说话，双方重叠），承载定时任务 + 车控双指令
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=7.5),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content=(
                            "哦对了，先别唠了，帮我定个35分钟的闹钟，"
                            "到点提醒我去楼下拿快递。顺手把空调也打开呗，车里有点闷。"
                        )
                    ),
                ),
            ),
            # T0+1h: 快进 2 段后（锚点停靠 + 任务触发），验证记忆 + 恢复轮
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(hours=1),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content=(
                            "快递拿到啦，多亏你提醒！行了我要上楼了，"
                            "把空调关了吧，别费电了。"
                        )
                    ),
                ),
            ),
        ],
        virtual_car_state_check_assertions=[
            # T0+1h+2m: 验证空调已关（gap > 60s 触发快进；末轮回复约 5-8s，60s 边界不够稳）
            VirtualCarStateCheckScriptEvent(
                event_t0_plus_timedelta=timedelta(hours=1, minutes=2),
                target="car",
                action=VirtualCarStateCheckAction(
                    args=VirtualCarStateCheckArgs(
                        expected_fields={"空调开启状态及模式": "关闭中"}
                    ),
                ),
            ),
        ],
        text_script=(
            "用户：哎，今天跑了一天客户，累得不行，你陪我唠两句呗。\n"
            "助手：（开始闲聊回应……）\n"
            "用户：（插话，与助手回复重叠）哦对了，先别唠了，帮我定个35分钟的闹钟，"
            "到点提醒我去楼下拿快递。顺手把空调也打开呗，车里有点闷。\n"
            "助手：（说完闲聊后）好的，已设置35分钟后的拿快递提醒，空调马上打开。\n"
            "[35分钟后，时间快进，定时任务触发]\n"
            "助手：35分钟到啦，该去楼下拿快递咯~\n"
            "[1小时后]\n"
            "用户：快递拿到啦，多亏你提醒！行了我要上楼了，把空调关了吧，别费电了。\n"
            "助手：好的，空调已关闭，慢走~"
        ),
        must_pass_assertions=[
            "假人插话与闲聊回复时间重叠时，助手应在收到插话后转向处理新指令（定闹钟+开空调），不应完全忽略插话内容",
            "助手应设置35分钟后的拿快递提醒并打开空调（插话即时投喂不丢指令）",
            "35分钟后时间快进时，助手应主动提醒用户去拿快递（定时任务不因重叠和快进丢失）",
            "1小时后假人说快递已拿到时，助手应记得提醒过快递并关闭空调",
        ],
        bonus_assertions=[
            "助手处理插话指令后的衔接应自然，不重复已说过的闲聊内容",
            "主动提醒的语气应自然友好",
        ],
    )


def build_builtin_navigation_case() -> TestCase:
    """构造多条件导航 case：长耗时导航工具 + 中途改目的地。

    特点：
    - 多条件导航请求（避开收费/避开拥堵/途经星巴克/时间约束/电量考虑）——
      条件越多导航工具跑得越久，工具执行区间在时间线/对话流全程可见
    - 中途改目的地（虹桥 → 浦东）触发第二次长耗时路线规划
    - 全近距锚点（T+20s / T+45s，均 < 60s 阈值不快进），非 fast_mode 下
      按 mock 助手真实节奏（nav_tool_delay 默认 6s：第一轮约 T+11s 收流，
      第二轮约 T+30s 收流）留足余量，适合实时观察工具区间
    - state_check 验证最终导航目的地（mock 助手确定性写入；v2 真实运行
      时以 trace 观察为主，state_check 结果取决于真实工具写入的目的地）
    - 注意：run_case 传大 nav_tool_delay（>10s）时需相应后移两个锚点
    """
    return TestCase(
        id="builtin-navigation-multi-condition",
        case_name="内置_多条件导航_长耗时工具",
        case_description=(
            "主驾发起多条件导航请求（去虹桥机场T2、避开收费路段、避开拥堵、"
            "途经星巴克买咖啡、五点半的飞机要留够时间），导航工具需逐项满足条件，"
            "执行耗时较长；随后中途改目的地为浦东机场T2并追加途经充电站条件，"
            "触发第二次路线规划。最终 state_check 验证导航目的地为浦东机场T2。"
            "验证多条件指令不丢条件 + 长耗时工具区间如实呈现 + 改目的地后重新规划。"
        ),
        tags=["多条件导航", "长耗时工具", "工具区间", "改目的地", "内置demo"],
        fake_persons=[
            FakePersonInfo(
                role_id="driver",
                profile="李明，32岁，互联网公司产品经理，赶飞机时间紧，说话快、条件多",
            )
        ],
        virtual_car=VirtualCarInfo(
            car_info={
                "车辆当前行驶速度": "0 km/h（静止）",
                "车辆当前档位": "P档（驻车档）",
                "车内温度": "26摄氏度",
                "空调开启状态及模式": "关闭中",
                "主驾是否有人": "有人",
                "副驾是否有人": "没人",
                "多媒体播放状态": "停止中",
                "导航状态": "未导航",
                "电池电量": "45%",
                "剩余续航里程（新能源车）": "180 km",
                "充电状态": "未充电",
                "当前位置": "上海平金中心地下停车场B2",
            }
        ),
        script_events=[
            # T0: 多条件导航请求（第一轮长耗时路线规划）
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content=(
                            "帮我导航去虹桥机场T2，别走收费路段，尽量避开拥堵，"
                            "路上最好能途经一家星巴克，我买杯咖啡带上飞机，"
                            "我五点半的飞机，得给我留够时间啊。"
                        )
                    ),
                ),
            ),
            # T+20s: 第一轮规划完成后（T+11s 收流 + 余量），中途改目的地 + 追加充电站条件（第二轮长耗时）
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=20),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content=(
                            "哦对了改一下，还是去浦东机场T2吧，刚才那些条件都要，"
                            "另外电量不太够，路上再找个带充电桩的星巴克。"
                        )
                    ),
                ),
            ),
        ],
        virtual_car_state_check_assertions=[
            # T+45s: 第二轮规划完成后（T+30s 收流 + 余量）检查最终目的地
            VirtualCarStateCheckScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=45),
                target="car",
                action=VirtualCarStateCheckAction(
                    args=VirtualCarStateCheckArgs(
                        expected_fields={"导航目的地": "上海浦东国际机场T2航站楼"}
                    ),
                ),
            ),
        ],
        text_script=(
            "用户：帮我导航去虹桥机场T2，别走收费路段，尽量避开拥堵，路上最好能途经一家星巴克，"
            "我买杯咖啡带上飞机，我五点半的飞机，得给我留够时间啊。\n"
            "助手：（调导航工具逐项筛选条件，耗时较长）好的，已按您的条件规划好路线。\n"
            "用户：哦对了改一下，还是去浦东机场T2吧，刚才那些条件都要，另外电量不太够，"
            "路上再找个带充电桩的星巴克。\n"
            "助手：（重新规划路线，耗时较长）好的，已改去浦东机场T2并加上充电站条件。"
        ),
        must_pass_assertions=[
            "助手应根据多条件导航请求规划路线（避开收费路段、避开拥堵、途经星巴克、满足五点半前到达的时间要求），不应丢失任何一项条件",
            "用户中途改目的地为浦东机场T2并追加充电站条件时，助手应重新规划路线并更新导航目的地",
            "导航目的地应最终更新为上海浦东国际机场T2航站楼",
        ],
        bonus_assertions=[
            "助手在路线规划期间应先给出承接语（告知正在按条件筛选），而不是长时间静默",
            "路线规划完成后应汇报满足各项条件的路线摘要（里程/耗时/途经点）",
        ],
    )


def build_builtin_multi_search_case() -> TestCase:
    """构造多轮信息查询 case：网页搜索 + POI 兴趣点搜索 + 音乐搜索（一次对话三连问）。

    特点：
    - 三个工具都走真实执行逻辑（websearch=火山ArkBot / POI=高德 / 音乐=QQ音乐开放API），
      均为"信息查询"而非"设备控制"，结果不落虚拟车状态，故无 state_check
    - 顺序多轮：第2/3轮用大跨度锚点（T+90s / T+180s，均 > 60s 加速阈值）触发时间加速。
      加速前 Runner 会先等上一轮助手回复收完（_wait_assistant_idle），从而保证上一轮
      工具结果回完后再开启下一轮，避免三个工具耗时不等导致锚点重叠或插话打断。
      （边界驱动 None 会让三轮紧挨着立即触发，打断助手回复，故弃用）
    - 每轮信息充分，降低 clarify 提问概率，保证流程顺畅
    """
    return TestCase(
        id="builtin-multi-search",
        case_name="内置_多轮_网页POI音乐搜索",
        case_description=(
            "一次对话中主驾依次发起三类信息查询：联网检索周末亲子展览（网页搜索）、"
            "上海博物馆周边评分高且人均100内的本帮菜馆（POI周边搜索）、"
            "周杰伦节奏轻快的歌（音乐搜索）。三个工具均走真实执行逻辑返回真实结果，"
            "验证 LLM 能正确路由到不同查询工具并基于真实结果回复。"
        ),
        tags=["多轮对话", "网页搜索", "POI搜索", "音乐搜索", "信息查询", "内置demo"],
        fake_persons=[
            FakePersonInfo(
                role_id="driver",
                profile="李明，32岁，互联网公司产品经理，周末带家人出门，需求具体爱规划",
            )
        ],
        virtual_car=VirtualCarInfo(
            car_info={
                "车辆当前行驶速度": "0 km/h（静止）",
                "车辆当前档位": "P档（驻车档）",
                "主驾是否有人": "有人",
                "副驾是否有人": "没人",
                "多媒体播放状态": "停止中",
                "导航状态": "未导航",
                "当前位置": "上海平金中心地下停车场B2",
            }
        ),
        script_events=[
            # T0: 联网检索（网页搜索）
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content=(
                            "帮我查一下，这个周末上海有哪些适合带娃的展览或者亲子活动，"
                            "把时间和地点都告诉我。"
                        )
                    ),
                ),
            ),
            # T+90s: 时间加速后，POI 周边搜索（加速前已等上一轮网页搜索回复收完）
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=90),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content=(
                            "看完展差不多中午了，帮我在上海博物馆附近找一家评分高的本帮菜馆，"
                            "人均一百以内吧。"
                        )
                    ),
                ),
            ),
            # T+180s: 时间加速后，音乐搜索（加速前已等上一轮 POI 搜索回复收完）
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=180),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content="回去路上帮我搜几首周杰伦的歌，节奏轻快一点的。"
                    ),
                ),
            ),
        ],
        text_script=(
            "用户：帮我查一下，这个周末上海有哪些适合带娃的展览或者亲子活动，把时间和地点都告诉我。\n"
            "助手：（调用联网搜索）这个周末上海有几场适合亲子的展览，分别是……\n"
            "用户：看完展差不多中午了，帮我在上海博物馆附近找一家评分高的本帮菜馆，人均一百以内吧。\n"
            "助手：（调用地点搜索）帮您找到几家评分高的本帮菜馆……\n"
            "用户：回去路上帮我搜几首周杰伦的歌，节奏轻快一点的。\n"
            "助手：（调用音乐搜索）搜到几首周杰伦节奏轻快的歌……"
        ),
        must_pass_assertions=[
            "第一轮用户请求查周末亲子展览时，助手应调用联网搜索工具并给出时间地点",
            "第二轮用户请求在上海博物馆附近找评分高、人均100内的本帮菜馆时，助手应调用地点搜索工具并按条件筛选",
            "第三轮用户请求搜周杰伦节奏轻快的歌时，助手应调用音乐搜索工具并给出歌曲",
        ],
        bonus_assertions=[
            "助手应基于真实搜索结果具体回复（含展览名/餐厅名/歌名等），而非泛泛而谈",
            "多轮衔接应自然连贯，不丢失前文上下文",
        ],
    )


def build_builtin_trip_mixed_case() -> TestCase:
    """构造「导航 + POI + 音乐」混编行程 case：同步导航工具 + 异步查询回灌。

    特点：
    - 一趟行程里混编三类工具：导航（同步、结果落虚拟车状态）+ POI（异步、真实
      结果回灌）+ 音乐（异步、真实结果回灌），验证 LLM 在同步/异步工具共存时的
      正确路由与回灌时序
    - 导航是同步工具：T0 请求后直接规划完成并把目的地写入虚拟车，state_check
      在 T+45s 验证导航已落盘（导航状态=导航中）；不写死目的地全称，规避 FC
      归一化简称/全称的口径差异
    - POI / 音乐走异步回灌：第 2/3 轮沿用 multi-search 已验证的大跨度锚点
      （T+90s / T+180s，>60s 触发时间加速），加速前 _wait_assistant_idle 等上一轮
      收完，避免打断
    """
    return TestCase(
        id="builtin-trip-mixed",
        case_name="内置_行程_导航POI音乐混编",
        case_description=(
            "主驾周末带家人去豫园玩，一趟行程内依次：导航去豫园（避开拥堵，结果落虚拟车）、"
            "逛完在豫园附近找评分高且人均150内的本帮菜馆（POI 周边搜索）、"
            "饭后回去路上搜几首周杰伦节奏轻快的歌（音乐搜索）。"
            "验证三类工具混编时 LLM 正确路由，同步导航工具落虚拟车状态、"
            "异步 POI/音乐真实结果回灌并生成自然回复。"
        ),
        tags=["导航", "POI搜索", "音乐搜索", "同步异步混编", "工具回灌", "内置demo"],
        fake_persons=[
            FakePersonInfo(
                role_id="driver",
                profile="李明，32岁，互联网公司产品经理，周末带家人出游，需求多爱规划",
            )
        ],
        virtual_car=VirtualCarInfo(
            car_info={
                "车辆当前行驶速度": "0 km/h（静止）",
                "车辆当前档位": "P档（驻车档）",
                "主驾是否有人": "有人",
                "副驾是否有人": "没人",
                "多媒体播放状态": "停止中",
                "导航状态": "未导航",
                "当前位置": "上海平金中心地下停车场B2",
            }
        ),
        script_events=[
            # T0: 导航去豫园（同步工具，结果落虚拟车导航状态）
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content="帮我导航去豫园，尽量避开拥堵路段。"
                    ),
                ),
            ),
            # T+90s: 时间加速后，POI 周边搜索（异步，真实结果回灌）
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=90),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content=(
                            "逛完豫园差不多中午了，帮我在豫园附近找一家评分高的本帮菜馆，"
                            "人均一百五以内吧。"
                        )
                    ),
                ),
            ),
            # T+180s: 时间加速后，音乐搜索（异步，真实结果回灌）
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=180),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content="吃完饭回去路上帮我搜几首周杰伦的歌，节奏轻快一点的。"
                    ),
                ),
            ),
        ],
        virtual_car_state_check_assertions=[
            # T+45s: 导航同步完成后检查导航已落虚拟车状态（不写死目的地规避 FC 口径）
            VirtualCarStateCheckScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=45),
                target="car",
                action=VirtualCarStateCheckAction(
                    args=VirtualCarStateCheckArgs(
                        expected_fields={"导航状态": "导航中"}
                    ),
                ),
            ),
        ],
        text_script=(
            "用户：帮我导航去豫园，尽量避开拥堵路段。\n"
            "助手：（调导航工具）好的，已为您规划去豫园的路线，已避开拥堵路段。\n"
            "用户：逛完豫园差不多中午了，帮我在豫园附近找一家评分高的本帮菜馆，人均一百五以内吧。\n"
            "助手：（调地点搜索）帮您找到几家豫园附近评分高的本帮菜馆……\n"
            "用户：吃完饭回去路上帮我搜几首周杰伦的歌，节奏轻快一点的。\n"
            "助手：（调音乐搜索）搜到几首周杰伦节奏轻快的歌……"
        ),
        must_pass_assertions=[
            "第一轮助手应调用导航工具并开始导航，将导航状态落到虚拟车（导航状态为导航中）",
            "第二轮助手应调用地点搜索工具，按评分高、人均150内的条件筛选豫园附近本帮菜馆",
            "第三轮助手应调用音乐搜索工具并给出周杰伦节奏轻快的歌曲",
        ],
        bonus_assertions=[
            "各轮助手应基于真实结果具体回复（含餐厅名/歌名等），而非泛泛而谈",
            "多轮衔接应自然连贯，不丢失前文上下文",
            "导航期间助手应先给出承接语，避免长时间静默",
        ],
    )


def build_builtin_parallel_tools_case() -> TestCase:
    """构造单轮四工具并行 case：一句话同时触发网页搜索 + POI + 音乐 + 导航。

    特点：
    - 单轮冷启动一句话包含四个独立意图（查展览 / 找餐馆 / 搜歌 / 导航），
      验证被测 agent 能否在同一次回复内并行调用多个工具。
    - 四个工具都走 TaskManager 异步执行：网页搜索、POI、音乐、导航（导航结果
      落虚拟车导航状态），工具泳道可见四个工具并行区间。
    - 导航异步回灌后落态，T+30s state_check 验证导航状态=导航中（不写死目的地，
      规避 FC 归一化简称/全称口径差异）；30s < 60s 加速阈值，不快进，完整呈现并行时段。
    """
    return TestCase(
        id="builtin-parallel-tools",
        case_name="内置_单轮_四工具并行",
        case_description=(
            "主驾一句话同时下达四个独立任务：查上海周末适合带娃的亲子展览（网页搜索）、"
            "上海博物馆附近评分高的本帮菜（POI 周边搜索）、周杰伦节奏轻快的歌（音乐搜索）、"
            "导航去上海博物馆（导航）。验证被测 agent 在单次回复内并行调用四个不同工具，"
            "工具泳道可见四个工具并行执行与真实结果回灌。"
        ),
        tags=["单轮", "并行工具", "网页搜索", "POI搜索", "音乐搜索", "导航", "内置demo"],
        fake_persons=[
            FakePersonInfo(
                role_id="driver",
                profile="李明，32岁，互联网公司产品经理，周末带家人出游，喜欢一次性把行程安排清楚",
            )
        ],
        virtual_car=VirtualCarInfo(
            car_info={
                "车辆当前行驶速度": "0 km/h（静止）",
                "车辆当前档位": "P档（驻车档）",
                "主驾是否有人": "有人",
                "副驾是否有人": "没人",
                "多媒体播放状态": "停止中",
                "导航状态": "未导航",
                "当前位置": "上海平金中心地下停车场B2",
            }
        ),
        script_events=[
            # T0: 一句话四任务并行（网页搜索 + POI + 音乐 + 导航）
            FakePersonScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=0),
                target="driver",
                action=FakePersonSpeakPerformAction(
                    args=FakePersonSpeakArgs(
                        content=(
                            "帮我一起安排下周末：先查查上海这周末有哪些适合带娃的展览，"
                            "再在上海博物馆附近找一家评分高的本帮菜，顺便搜几首周杰伦节奏轻快的歌，"
                            "最后直接导航去上海博物馆。"
                        )
                    ),
                ),
            ),
        ],
        virtual_car_state_check_assertions=[
            # T+30s: 验证导航异步回灌后已落虚拟车状态（不写死目的地规避 FC 口径）
            VirtualCarStateCheckScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=30),
                target="car",
                action=VirtualCarStateCheckAction(
                    args=VirtualCarStateCheckArgs(
                        expected_fields={"导航状态": "导航中"}
                    ),
                ),
            ),
        ],
        text_script=(
            "用户：帮我一起安排下周末：先查查上海这周末有哪些适合带娃的展览，再在上海博物馆附近找一家评分高的本帮菜，顺便搜几首周杰伦节奏轻快的歌，最后直接导航去上海博物馆。\n"
            "助手：（并行调用网页搜索、地点搜索、音乐搜索、导航四个工具）已为您查到：本周末上海的亲子展览有……；上海博物馆附近评分高的本帮菜有……；周杰伦节奏轻快的歌有……；并已开始导航去上海博物馆。"
        ),
        must_pass_assertions=[
            "助手应调用网页搜索工具查询上海周末适合带娃的亲子展览",
            "助手应调用地点搜索工具查询上海博物馆附近评分高的本帮菜",
            "助手应调用音乐搜索工具搜索周杰伦节奏轻快的歌",
            "助手应调用导航工具并开始导航，导航状态落到虚拟车（导航中）",
        ],
        bonus_assertions=[
            "四个工具应在同一次回复中并行调用，工具泳道呈现并行区间",
            "助手应基于各工具真实结果具体回复（含展览名/餐厅名/歌名等），而非泛泛而谈",
        ],
    )


# ---------------- fixture case 加载 ----------------


FIXTURE_CASES_FILE = (
    Path(__file__).resolve().parent.parent / "test" / "cases" / "fixture_cases.json"
)


def load_fixture_case(case_id: str = "case-001") -> TestCase:
    """从 test/cases/fixture_cases.json 加载指定 case。"""
    cases = load_test_cases_from_json_file(FIXTURE_CASES_FILE)
    for c in cases:
        if c.id == case_id:
            return c
    available = [c.id for c in cases]
    raise SystemExit(
        f"未找到 case_id={case_id!r}，可选 case: {available}"
    )


# ---------------- 主流程 ----------------


def print_separator(title: str) -> None:
    print(f"\n{'=' * 20} {title} {'=' * 20}")


def print_case_brief(case: TestCase) -> None:
    print_separator("Case 概览")
    print(f"  id          : {case.id}")
    print(f"  name        : {case.case_name}")
    print(f"  description : {case.case_description}")
    print(f"  fake_persons: {[p.role_id for p in case.fake_persons]}")
    print(f"  script_events 数量: {len(case.script_events)}")
    print(f"  state_check 数量  : {len(case.virtual_car_state_check_assertions)}")
    print(f"  must_pass 数量    : {len(case.must_pass_assertions)}")
    print(f"  bonus 数量        : {len(case.bonus_assertions)}")
    print(f"  text_script:\n{_indent(case.text_script, 4)}")


def _indent(text: str, n: int) -> str:
    pad = " " * n
    return "\n".join(pad + line for line in text.splitlines())


def print_trace(runner: CaseRunner) -> None:
    print_separator("Trace 文本（时间线）")
    timeline_text = render_timeline_text(runner.trace)
    print(timeline_text)


def print_summary(run_result) -> None:
    print_separator("RunResult 摘要")
    print(f"  case_id            : {run_result.case_id}")
    print(f"  started_at         : {run_result.started_at.isoformat()}")
    print(f"  finished_at        : {run_result.finished_at.isoformat()}")
    print(f"  耗时(秒)           : {(run_result.finished_at - run_result.started_at).total_seconds():.2f}")
    print(f"  error              : {run_result.error}")
    summary = run_result.trace_summary
    print(f"  total_utterances   : {summary.get('total_utterances', 0)}")
    print(f"  total_state_checks : {summary.get('total_state_checks', 0)}")
    print(f"  state_checks_passed: {summary.get('state_checks_passed', 0)}")
    print(f"  state_checks_failed: {summary.get('state_checks_failed', 0)}")
    print(f"  has_partial_utterance: {summary.get('has_partial_utterance', False)}")
    print(f"  state_check_passed : {run_result.state_check_passed}")


def print_verdict(verdict) -> None:
    print_separator("Judge 评判结果")
    print(f"  case_id        : {verdict.case_id}")
    print(f"  overall_passed : {verdict.overall_passed}")
    print(f"  score          : {verdict.score:.1f} / 100")
    bd = verdict.score_breakdown
    print(
        f"  打分明细        : "
        f"必过 {bd.must_pass_passed}/{bd.must_pass_total}, "
        f"加分 {bd.bonus_passed}/{bd.bonus_total}, "
        f"状态检查 {bd.state_check_passed}/{bd.state_check_total}"
    )
    print(f"  summary        : {verdict.summary}")
    print("\n  各断言结果：")
    for i, ar in enumerate(verdict.assertion_results, 1):
        flag = "✓" if ar.passed else "✗"
        atype = "必过" if ar.assertion_type.value == "must_pass" else "加分"
        print(f"    {i}. [{flag}] [{atype}] {ar.assertion}")
        if ar.reasoning:
            print(f"       reasoning: {ar.reasoning}")
        if ar.evidence:
            print(f"       evidence : {ar.evidence}")
    if verdict.raw_response:
        print(f"\n  [raw_response]: {verdict.raw_response[:500]}")


async def run_one_case(
    case: TestCase,
    *,
    enable_judge: bool,
    use_streaming: bool,
    fast_mode: bool,
    show_prompt: bool = False,
) -> None:
    """跑一个 case 的完整链路：TestedAssistant + CaseRunner + 可选 Judge。"""
    print_case_brief(case)

    # 1. 构造被测助手（协议封装的真实 LLM agent）
    assistant = TestedAssistant()

    # 2. 构造 Runner
    config = RunnerConfig(
        use_streaming=use_streaming,
        fast_mode=fast_mode,
        # 真实 LLM 比较慢，把超时调大
        assistant_timeout=120.0,
        fake_person_timeout=60.0,
        # 时间加速保持默认启用（fast_mode=True 时自动跳过）
        enable_acceleration=True,
    )
    runner = CaseRunner(assistant=assistant, config=config)

    # 3. 跑 case
    print_separator("开始运行 CaseRunner")
    # t0 用 datetime.now() 对齐真实时间，避免 scheduler 计算 wait_seconds 出错
    t0 = datetime.now().replace(microsecond=0)
    run_result = await runner.run(case, t0=t0)

    # 4. 打印 trace + 摘要
    print_trace(runner)
    print_summary(run_result)

    if run_result.error:
        print(f"\n[!] Runner 出错，跳过 Judge 评判: {run_result.error}")
        return

    # 5. Judge 评判
    if not enable_judge:
        print("\n[--no-judge] 跳过 Judge 评判。")
        return

    print_separator("调用 Judge 评判")
    try:
        assistant_history = await assistant.adump_history()
    except Exception as e:
        print(f"[!] 导出助手历史失败: {e!r}")
        assistant_history = []

    judge_input = build_judge_input_from_run_result(
        case=case,
        recorder=runner.trace,
        run_result=run_result,
        assistant_history=assistant_history,
    )
    judge = Judge()
    if show_prompt:
        print_separator("Judge 完整 prompt（发给 LLM 的真实上下文）")
        print(judge._build_prompt(judge_input))
    try:
        verdict = await judge.ajudge(judge_input)
    except Exception as e:
        print(f"[!] Judge 评判失败: {e!r}")
        return

    print_verdict(verdict)


# ---------------- 命令行入口 ----------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="端到端真实 LLM 测试 demo（TestedAssistant + CaseRunner + Judge）",
    )
    parser.add_argument(
        "--case",
        choices=["builtin", "builtin-accel", "llm-speak", "interrupt", "scheduled", "complex", "navigation", "multi-search", "trip-mixed", "fixture"],
        default="builtin",
        help="选择 case 来源：内置简单case / 内置时间加速case / LLM自主对话case / 插话重叠case / 定时任务case / 综合case / fixture_cases.json",
    )
    parser.add_argument(
        "--case-id",
        default="case-001",
        help="配合 --case fixture 使用，指定要跑的 case id（默认 case-001）",
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="跳过 Judge 评判，只跑 Runner 并打印 trace",
    )
    parser.add_argument(
        "--no-streaming",
        action="store_true",
        help="关闭流式回复（关闭后无 chunk 级时间戳）",
    )
    parser.add_argument(
        "--fast-mode",
        action="store_true",
        help="开启 fast_mode（跳过锚点的真实时间等待，仅用于快速演示）",
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="打印 Judge 收到的完整 prompt（发给裁判 LLM 的真实上下文）",
    )
    return parser.parse_args()


def main() -> None:
    # 无命令行参数时，直接用文件顶部的配置变量
    if len(sys.argv) <= 1:
        case_name = ACTIVE_CASE
        fixture_id = FIXTURE_CASE_ID
        enable_judge = ENABLE_JUDGE
        use_streaming = USE_STREAMING
        fast_mode = FAST_MODE
        show_prompt = False
    else:
        args = parse_args()
        case_name = args.case
        fixture_id = args.case_id
        enable_judge = not args.no_judge
        use_streaming = not args.no_streaming
        fast_mode = args.fast_mode
        show_prompt = args.show_prompt

    if case_name == "builtin":
        case = build_builtin_case()
    elif case_name == "builtin-accel":
        case = build_builtin_case_with_acceleration()
    elif case_name == "time-aware":
        case = build_builtin_time_awareness_case()
    elif case_name == "llm-speak":
        case = build_builtin_llm_speak_case()
    elif case_name == "interrupt":
        case = build_builtin_interrupt_case()
    elif case_name == "scheduled":
        case = build_builtin_scheduled_task_case()
    elif case_name == "complex":
        case = build_builtin_complex_case()
    elif case_name == "navigation":
        case = build_builtin_navigation_case()
    elif case_name == "multi-search":
        case = build_builtin_multi_search_case()
    elif case_name == "trip-mixed":
        case = build_builtin_trip_mixed_case()
    else:
        case = load_fixture_case(fixture_id)

    asyncio.run(
        run_one_case(
            case,
            enable_judge=enable_judge,
            use_streaming=use_streaming,
            fast_mode=fast_mode,
            show_prompt=show_prompt,
        )
    )


if __name__ == "__main__":
    main()
