"""
复杂推理记忆生产/消费自动化测试入口脚本。

用途：
1) 可切换“本地 mock case 模式”与“Mongo 数据集模式”；
2) 统一注入复杂推理服务默认参数；
3) 执行 AutoTestAndRLDataGenerator 并输出 judge_log/report；
4) 在 Windows 下自动切换 UTF-8 控制台，避免 PowerShell 中文乱码。
"""

import asyncio
import os
import re
import sys
import uuid

from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import (
    AutoTestAndRLDataGenerator,
    EVENT_MEMORY_LIMIT,
    EVENT_MEMORY_TYPES,
    MEMORY_COLLECTION_NAME,
    MEMORY_LIMIT,
    MEMORY_TYPES,
    RunAllCasesResult,
    RunCaseResult,
    TEST_ASSISTANT_ID,
)
from projects.mind.mem.auto_test_script.auto_test_demos.complex_reasoning_service_bot import (
    ComplexReasoningServiceBot,
    DEFAULT_AGENT_URL,
    DEFAULT_EVENT_TYPE,
    DEFAULT_HAS_OBSERVATION,
    DEFAULT_IS_SUBMIT_MOCK_INFO,
    DEFAULT_MAIN_ENGINE,
    DEFAULT_MEM_DAY_SUMMARY_URL,
    DEFAULT_MEM_EVENT_MOCK_URL,
    DEFAULT_MEM_MODE,
    DEFAULT_MEM_PROFILE_MOCK_URL,
    DEFAULT_MEM_SUMMARY_QUERY_URL,
    DEFAULT_MEM_WEEK_SUMMARY_URL,
    DEFAULT_MONIQI_MOCK_URL,
    DEFAULT_PROFILE_TYPE,
    DEFAULT_SLEEP_INTERVAL,
    DEFAULT_TEST_MOCK_ID,
)
from projects.mind.mem.auto_test_script.case_schema import DialogueRoundConfig, TestCase
from projects.mind.mem.auto_test_script.auto_test_demos.get_datasets import (
    get_dataset_list,
)
from projects.mind.mem.volc_api import Message


DATASET_NAMES = ["别克NDLB EV复杂推理最终需求边界数据集——记忆生产类"]
USE_LOCAL_MOCK_CASES = True
# 是否在每个 case 开始前清理火山记忆（防止同 user_id 旧记忆干扰）。
USE_VOLC_MEMORY_RESET = True
# 是否在每次多轮对话结束后由自动化框架代替 bot 上传历史到火山记忆。
# 对“被测 bot 本身具备记忆生产/消费能力”的场景，建议保持 False。
USE_UPLOAD_HISTORY_TO_VOLC_MEMORY = False
# 兼容旧开关（仅用于向后兼容；建议改用上面两个独立开关）。
USE_VOLC_MEMORY_PIPELINE = False
# 为 True 时，创建 bot 时会请求模拟器和画像 mock 接口（需网络可达）。
ENABLE_REMOTE_MOCK_SUBMIT = False
REPORT_DIR = r"projects\mind\mem\auto_test_script\auto_test_report"
JUDGE_LOG_PATH = os.path.join(
    REPORT_DIR, "complex_reasoning_memory_production_judge_log.txt"
)
REPORT_MD_PATH = os.path.join(
    REPORT_DIR, "complex_reasoning_memory_production_report.md"
)

DATASET_ALIAS_MAP = {
    "别克NDLB EV复杂推理最终需求边界数据集——记忆生产类": "memory_production",
    "别克NDLB EV复杂推理最终需求边界数据集——媒体类": "media",
    "别克NDLB EV复杂推理最终需求边界数据集——导航类": "navigation",
    "别克NDLB EV复杂推理最终需求边界数据集——闲聊+记忆消费类": "chat_memory_consume",
}


def setup_windows_utf8_console() -> None:
    """
    修复 Windows PowerShell 中文乱码：
    - 切换终端代码页到 UTF-8
    - 强制 Python stdout/stderr 以 UTF-8 输出
    """
    if os.name != "nt":
        return
    os.system("chcp 65001 > nul")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _parse_bool_env(name: str, default: bool) -> bool:
    """
    读取布尔型环境变量（1/true/yes/on 视为 True）。
    """
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_dataset_names_from_env(default: list[str]) -> list[str]:
    """
    读取数据集名：
    - AUTO_TEST_DATASET_NAMES="A||B||C"
    """
    raw = os.getenv("AUTO_TEST_DATASET_NAMES", "").strip()
    if not raw:
        return default
    names = [x.strip() for x in raw.split("||") if x.strip()]
    return names or default


def _build_output_paths(
    dataset_names: list[str],
    default_log_path: str,
    default_report_path: str,
) -> tuple[str, str]:
    """
    生成本次运行输出路径：
    1) 若显式设置 AUTO_TEST_JUDGE_LOG_PATH / AUTO_TEST_REPORT_MD_PATH，则优先使用；
    2) 否则单数据集时自动按别名落盘，避免多次运行互相覆盖；
    3) 其余情况回退默认路径。
    """
    custom_log_path = os.getenv("AUTO_TEST_JUDGE_LOG_PATH", "").strip()
    custom_report_path = os.getenv("AUTO_TEST_REPORT_MD_PATH", "").strip()
    if custom_log_path and custom_report_path:
        return custom_log_path, custom_report_path

    if len(dataset_names) == 1:
        dataset_name = dataset_names[0]
        alias = DATASET_ALIAS_MAP.get(dataset_name, dataset_name)
        alias = re.sub(r"[^\w\-]+", "_", alias).strip("_").lower() or "dataset"
        log_path = os.path.join(REPORT_DIR, f"complex_reasoning_{alias}_judge_log.txt")
        report_path = os.path.join(REPORT_DIR, f"complex_reasoning_{alias}_report.md")
        return custom_log_path or log_path, custom_report_path or report_path

    return custom_log_path or default_log_path, custom_report_path or default_report_path


def patch_cases_default_context(cases):
    """
    给数据集里的 case 注入默认配置，确保复杂推理服务调用参数完整。
    若 case 内已有同名字段，则保留 case 原值。
    """
    for case in cases:
        # 这些字段对应复杂推理服务请求体/扩展参数，确保 case 不完整时也能跑通。
        case.context_config.setdefault("intent_type", "复杂推理")
        case.context_config.setdefault("main_engine", DEFAULT_MAIN_ENGINE)
        case.context_config.setdefault("mem_mode", DEFAULT_MEM_MODE)
        case.context_config.setdefault("is_test", True)
        case.context_config.setdefault("test_mock_id", DEFAULT_TEST_MOCK_ID)
        case.context_config.setdefault("profile_type", DEFAULT_PROFILE_TYPE)
        case.context_config.setdefault("event_type", DEFAULT_EVENT_TYPE)
        case.context_config.setdefault("is_submit_mock_info", DEFAULT_IS_SUBMIT_MOCK_INFO)
        case.context_config.setdefault("has_observation", DEFAULT_HAS_OBSERVATION)
        case.context_config.setdefault("sleep_interval", DEFAULT_SLEEP_INTERVAL)
        case.context_config.setdefault("mem_day_summary_url", DEFAULT_MEM_DAY_SUMMARY_URL)
        case.context_config.setdefault(
            "mem_week_summary_url", DEFAULT_MEM_WEEK_SUMMARY_URL
        )
        case.context_config.setdefault(
            "mem_summary_query_url", DEFAULT_MEM_SUMMARY_QUERY_URL
        )


def isolate_case_user_ids_per_run(cases: list[TestCase]) -> str:
    """
    为本次运行生成唯一run_id，并把每个case的user_id隔离到run维度。
    目的：避免远端长期记忆服务残留数据污染本次case验证。
    """
    run_id = uuid.uuid4().hex[:8]
    for case in cases:
        raw_user_id = str(
            case.context_config.get("user_id")
            or case.case_id
            or "memory_case_user"
        )
        safe_user_id = re.sub(r"[^\w\-]+", "_", raw_user_id).strip("_") or "memory_case_user"
        case.context_config["user_id"] = f"{safe_user_id}_run_{run_id}"
    return run_id


def build_local_mock_cases(enable_volc_memory_fields: bool) -> list[TestCase]:
    """
    本地 mock 用例：都属于“跨多轮先生产记忆，再消费记忆”的场景。
    """
    # 三个 case 共用的基础配置：服务调用参数 + 可选记忆相关配置。
    base_context = {
        "intent_type": "复杂推理",
        "main_engine": DEFAULT_MAIN_ENGINE,
        "mem_mode": DEFAULT_MEM_MODE,
        "is_test": True,
        "test_mock_id": DEFAULT_TEST_MOCK_ID,
        "profile_type": DEFAULT_PROFILE_TYPE,
        "event_type": DEFAULT_EVENT_TYPE,
        # 仅在需要火山记忆配置时注入 collection/assistant/profile/event 等字段。
        "collection_name": MEMORY_COLLECTION_NAME if enable_volc_memory_fields else None,
        "assistant_id": TEST_ASSISTANT_ID if enable_volc_memory_fields else None,
        "profile_types": MEMORY_TYPES if enable_volc_memory_fields else None,
        "event_types": EVENT_MEMORY_TYPES if enable_volc_memory_fields else None,
        "memory_limit": MEMORY_LIMIT if enable_volc_memory_fields else None,
        "event_limit": EVENT_MEMORY_LIMIT if enable_volc_memory_fields else None,
        "is_submit_mock_info": DEFAULT_IS_SUBMIT_MOCK_INFO,
        "has_observation": DEFAULT_HAS_OBSERVATION,
        "sleep_interval": DEFAULT_SLEEP_INTERVAL,
        "mem_day_summary_url": DEFAULT_MEM_DAY_SUMMARY_URL,
        "mem_week_summary_url": DEFAULT_MEM_WEEK_SUMMARY_URL,
        "mem_summary_query_url": DEFAULT_MEM_SUMMARY_QUERY_URL,
        "car_info": "当前在上海市区，车辆静止，空调24摄氏度。",
        "user_profile": "40岁男司机，说话直接。",
    }

    # case1：多次修改“家”的地址，带mock_time+car_info，验证“回家”是否消费最新住址。
    case_home_update = TestCase(
        id="local_mock_1",
        case_id="local_memory_home_update_consume",
        context_config={**base_context, "user_id": "local_memory_user_1"},
        max_round=8,
        user_query_lists=[
            DialogueRoundConfig(
                user_query_list=[Message(role="user", content="记一下，我住在浦东前滩。")],
                mock_time="2026-04-03 18:06:12",
                mock_info={
                    "car_info": (
                        "'当前系统时间': 2026-04-03 18:06:12, "
                        "'当前位置': '上海市浦东新区世纪大道100号', "
                        "'车辆当前档位': 'D档（前进档）', "
                        "'车辆当前行驶速度': '35 km/h（行驶中）'"
                    )
                },
            ),
            DialogueRoundConfig(
                user_query_list=[Message(role="user", content="我搬家了，现在住在嘉定新城。")],
                mock_time="2026-04-10 18:14:39",
                mock_info={
                    "car_info": (
                        "'当前系统时间': 2026-04-10 18:14:39, "
                        "'当前位置': '上海市黄浦区延安东路高架内圈', "
                        "'车辆当前档位': 'D档（前进档）', "
                        "'车辆当前行驶速度': '52 km/h（行驶中）'"
                    )
                },
            ),
            DialogueRoundConfig(
                user_query_list=[Message(role="user", content="我家现在在哪儿？")],
                mock_time="2026-04-17 18:21:05",
                mock_info={
                    "car_info": (
                        "'当前系统时间': 2026-04-17 18:21:05, "
                        "'当前位置': '上海市闵行区虹桥枢纽高架', "
                        "'车辆当前档位': 'D档（前进档）', "
                        "'车辆当前行驶速度': '61 km/h（行驶中）'"
                    )
                },
            ),
        ],
        expected_script="""
用户（第一次多轮对话）：记一下，我住在浦东前滩。
管家：确认“已记录住址=浦东前滩”，不需要展开额外任务。
……（切换到第二次多轮对话）
用户（第二次多轮对话）：我搬家了，现在住在嘉定新城。
管家：确认“已更新住址=嘉定新城”，不需要展开额外任务。
……（切换到第三次多轮对话）
用户（第三次多轮对话）：我家现在在哪儿？
管家：直接回答“你现在记录的家在嘉定新城”（或等价表达），用于验证是否正确消费最新住址记忆。

关键约束（演员必须严格遵守）：
1) 只围绕“住址记录/更新/回家”这条主线，不新增叫车、公共交通、跨城出行等支线剧情；
2) 第三次对话中，演员（用户）无论如何都不能主动提及任何“我家在哪”的地址信息或提示词；
3) 第三次对话必须只测试“对方是否知道我家现在在哪”，不改成“回家/导航回家”任务；
4) 第三次对话必须体现“消费最新记忆”，管家不能回退到“浦东前滩”或其他旧地址；
5) 不要在未被要求时虚构额外背景信息（如用户在外地、航班车次、复杂绕行方案等）。
        """,
        nl_assertion=[
            "第三次对话用户只问“我家现在在哪儿”，未提供任何地址提示；助手应仅基于前两次记忆回答最新地址“嘉定新城”（或等价表达），否则不通过。"
        ],
        case_description="验证住址信息在跨会话中的记忆生产与消费。",
        tags=["本地mock", "记忆生产", "记忆消费", "跨多轮对话"],
    )

    # case2：多次修改音乐偏好，验证最终推荐是否遵循最新偏好。
    case_music_preference = TestCase(
        id="local_mock_2",
        case_id="local_memory_music_preference_update_consume",
        context_config={**base_context, "user_id": "local_memory_user_2"},
        max_round=8,
        user_query_lists=[
            [Message(role="user", content="记住我最近喜欢听周杰伦。")],
            [Message(role="user", content="更新一下，我现在更喜欢陈奕迅。")],
            [Message(role="user", content="按我的偏好推荐三首歌。")],
        ],
        expected_script="""
用户（第一次多轮对话）：记住我最近喜欢听周杰伦。
管家：确认记录“音乐偏好=周杰伦”。
……（切换到第二次多轮对话）
用户（第二次多轮对话）：更新一下，我现在更喜欢陈奕迅。
管家：确认覆盖更新“音乐偏好=陈奕迅（最新）”。
……（切换到第三次多轮对话）
用户（第三次多轮对话）：按我的偏好推荐三首歌。
管家：基于最新偏好“陈奕迅”给出推荐，不应继续按“周杰伦”推荐。

关键约束（演员必须严格遵守）：
1) 推荐阶段要直接体现“最新偏好优先”；
2) 不要把旧偏好和新偏好混在一起作为主要结果；
3) 不要发散到无关话题（比如导航、车控、天气闲聊）。
        """,
        nl_assertion=[
            "最后一轮推荐应体现最新的音乐偏好，而不是旧偏好。"
        ],
        case_description="验证偏好类记忆的覆盖更新与消费。",
        tags=["本地mock", "记忆生产", "记忆消费", "偏好更新"],
    )

    # case3：多次修改公司地址，验证“导航去公司”是否消费最新地址。
    case_company_address = TestCase(
        id="local_mock_3",
        case_id="local_memory_company_address_consume",
        context_config={**base_context, "user_id": "local_memory_user_3"},
        max_round=8,
        user_query_lists=[
            [Message(role="user", content="记一下，我公司在张江。")],
            [Message(role="user", content="我公司搬到徐汇滨江了。")],
            [Message(role="user", content="导航去公司。")],
        ],
        expected_script="""
用户（第一次多轮对话）：记一下，我公司在张江。
管家：确认记录“公司地址=张江”。
……（切换到第二次多轮对话）
用户（第二次多轮对话）：我公司搬到徐汇滨江了。
管家：确认更新“公司地址=徐汇滨江（最新）”。
……（切换到第三次多轮对话）
用户（第三次多轮对话）：导航去公司。
管家：将“公司”解析为“徐汇滨江”并执行导航意图。

关键约束（演员必须严格遵守）：
1) 必须消费最新地址“徐汇滨江”，不能使用“张江”；
2) 对话聚焦公司地址记忆消费，不发散到与目标无关的长篇内容；
3) 不要凭空新增新的公司地址或改写用户给定信息。
        """,
        nl_assertion=[
            "助手应正确消费最新地址记忆，不能仍用旧公司地址。"
        ],
        case_description="验证地点类记忆在导航任务中的消费效果。",
        tags=["本地mock", "记忆生产", "记忆消费", "导航"],
    )

    return [case_home_update, case_music_preference, case_company_address]


async def main():
    """
    脚本主入口：
    1) 初始化 bot 类级配置；
    2) 加载本地 case 或数据库数据集；
    3) 调用自动评测主流程；
    4) 写入 judge log 与 markdown 报告。
    """
    agent_url = os.getenv("COMPLEX_REASONING_URL", DEFAULT_AGENT_URL)
    tenant_id = os.getenv("COMPLEX_REASONING_TENANT_ID", "")
    use_local_mock_cases = _parse_bool_env("AUTO_TEST_USE_LOCAL_MOCK_CASES", USE_LOCAL_MOCK_CASES)
    # 兼容旧开关 AUTO_TEST_USE_VOLC_MEMORY_PIPELINE：
    # - 若用户仅设置了旧开关，则它只作为 memory_reset_mode 的默认值；
    # - upload_history_to_volc_memory 仍默认关闭，避免与“被测 bot 自身记忆能力”冲突。
    old_pipeline_raw = os.getenv("AUTO_TEST_USE_VOLC_MEMORY_PIPELINE")
    old_pipeline_value = (
        _parse_bool_env("AUTO_TEST_USE_VOLC_MEMORY_PIPELINE", USE_VOLC_MEMORY_PIPELINE)
        if old_pipeline_raw is not None
        else USE_VOLC_MEMORY_PIPELINE
    )
    use_volc_memory_reset = _parse_bool_env(
        "AUTO_TEST_MEMORY_RESET_MODE",
        old_pipeline_value if old_pipeline_raw is not None else USE_VOLC_MEMORY_RESET,
    )
    use_upload_history_to_volc_memory = _parse_bool_env(
        "AUTO_TEST_UPLOAD_HISTORY_TO_VOLC_MEMORY",
        USE_UPLOAD_HISTORY_TO_VOLC_MEMORY,
    )
    need_volc_memory_context = (
        use_volc_memory_reset or use_upload_history_to_volc_memory
    )
    enable_remote_mock_submit = _parse_bool_env(
        "AUTO_TEST_ENABLE_REMOTE_MOCK_SUBMIT", ENABLE_REMOTE_MOCK_SUBMIT
    )
    dataset_names = _parse_dataset_names_from_env(DATASET_NAMES)
    judge_log_path, report_md_path = _build_output_paths(
        dataset_names, JUDGE_LOG_PATH, REPORT_MD_PATH
    )
    concurrency_num = int(os.getenv("AUTO_TEST_CONCURRENCY_NUM", "10"))
    case_limit = int(os.getenv("AUTO_TEST_CASE_LIMIT", "1"))

    ComplexReasoningServiceBot.set_up_bot_to_test(
        agent_url=agent_url,
        moniqi_mock_url_template=DEFAULT_MONIQI_MOCK_URL,
        mem_profile_url=DEFAULT_MEM_PROFILE_MOCK_URL,
        mem_event_url=DEFAULT_MEM_EVENT_MOCK_URL,
        tenant_id=tenant_id,
        is_submit_mock_info=enable_remote_mock_submit,
        profile_type=DEFAULT_PROFILE_TYPE,
        event_type=DEFAULT_EVENT_TYPE,
        has_observation=DEFAULT_HAS_OBSERVATION,
        sleep_interval=DEFAULT_SLEEP_INTERVAL,
        mem_day_summary_url=DEFAULT_MEM_DAY_SUMMARY_URL,
        mem_week_summary_url=DEFAULT_MEM_WEEK_SUMMARY_URL,
        mem_summary_query_url=DEFAULT_MEM_SUMMARY_QUERY_URL,
    )

    if use_local_mock_cases:
        all_cases = build_local_mock_cases(
            enable_volc_memory_fields=need_volc_memory_context
        )
    else:
        all_cases = await get_dataset_list(dataset_names)
    # 默认只抽取前2个case快速验证，可通过 AUTO_TEST_CASE_LIMIT 调整。
    if case_limit > 0:
        all_cases = all_cases[:case_limit]
    patch_cases_default_context(all_cases)
    run_id = isolate_case_user_ids_per_run(all_cases)
    if not need_volc_memory_context:
        # 不需要火山记忆能力时，移除相关配置，避免框架初始化火山记忆客户端。
        for case in all_cases:
            for key in [
                "collection_name",
                "assistant_id",
                "profile_types",
                "event_types",
                "memory_limit",
                "event_limit",
            ]:
                case.context_config.pop(key, None)

    auto_test = AutoTestAndRLDataGenerator(
        bot_to_test=ComplexReasoningServiceBot, memory_test_cases=all_cases
    )
    run_all_cases_result: RunAllCasesResult | None = None
    async for item in auto_test.arun_full_auto_judge_test(
        concurrency_mode=True,
        concurrency_num=concurrency_num,
        pause_mode=False,
        memory_reset_mode=use_volc_memory_reset,
        upload_history_to_volc_memory=use_upload_history_to_volc_memory,
    ):
        if isinstance(item, RunCaseResult):
            print(
                f"[STREAM] case已完成: case_id={item.case_id}, "
                f"id={item.id}, is_passed={item.is_passed}"
            )
        elif isinstance(item, RunAllCasesResult):
            run_all_cases_result = item
            print(
                f"[STREAM] 全部完成: total={item.total_case_num}, "
                f"passed={item.passed_case_num}, pass_rate={item.pass_rate:.2%}"
            )
    assert run_all_cases_result is not None, "未收到最终RunAllCasesResult"

    auto_test.write_test_task_judge_log(
        dataset_names=["本地mock记忆生产消费用例"] if use_local_mock_cases else dataset_names,
        total_case_num=run_all_cases_result.total_case_num,
        passed_case_num=run_all_cases_result.passed_case_num,
        pass_rate=run_all_cases_result.pass_rate,
        execution_success_num=run_all_cases_result.execution_success_num,
        execution_success_rate=run_all_cases_result.execution_success_rate,
        tags_correct_number_and_rate=run_all_cases_result.tags_correct_number_and_rate,
        judge_result=run_all_cases_result.result,
        log_file_path=judge_log_path,
    )
    auto_test.write_test_task_report(
        dataset_names=["本地mock记忆生产消费用例"] if use_local_mock_cases else dataset_names,
        result_str=run_all_cases_result.result,
        total_case_num=run_all_cases_result.total_case_num,
        passed_case_num=run_all_cases_result.passed_case_num,
        pass_rate=run_all_cases_result.pass_rate,
        execution_success_num=run_all_cases_result.execution_success_num,
        execution_success_rate=run_all_cases_result.execution_success_rate,
        tags_correct_number_and_rate=run_all_cases_result.tags_correct_number_and_rate,
        report_file_path=report_md_path,
    )

    print(f"数据集: {dataset_names}")
    print(f"测试用例总数: {run_all_cases_result.total_case_num}")
    print(f"通过用例数: {run_all_cases_result.passed_case_num}")
    print(f"通过率: {run_all_cases_result.pass_rate:.2%}")
    print(f"memory_reset_mode: {use_volc_memory_reset}")
    print(f"upload_history_to_volc_memory: {use_upload_history_to_volc_memory}")
    print(f"case_limit: {case_limit}")
    print(f"run_id: {run_id}")
    for detail in run_all_cases_result.details_result_list:
        summary_triggers = []
        for trace in detail.case_traces:
            if isinstance(trace, dict):
                one_trace = trace.get("trace")
                if isinstance(one_trace, list):
                    for one_turn in one_trace:
                        if isinstance(one_turn, dict) and "summary_trigger" in one_turn:
                            summary_triggers.append(one_turn["summary_trigger"])
        if summary_triggers:
            print(f"case={detail.case_id} summary_trigger_count={len(summary_triggers)}")
            for idx, item in enumerate(summary_triggers, 1):
                print(
                    f"  summary[{idx}]: day={item.get('summary_day')}, "
                    f"week={item.get('start_day')}~{item.get('end_day')}, "
                    f"status=({item.get('day_status')}/{item.get('query_status')}/{item.get('week_status')})"
                )
    print(f"judge_log: {judge_log_path}")
    print(f"report_md: {report_md_path}")


if __name__ == "__main__":
    setup_windows_utf8_console()
    asyncio.run(main())
