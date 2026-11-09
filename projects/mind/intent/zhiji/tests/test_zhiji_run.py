"""
测试run方法(自定义意图+ 火山意图)的所有if分支,mock数据测试
测试run方法，接口返回真实数据
"""
import asyncio
from unittest.mock import AsyncMock, patch
from rich import print
from typing import Any

from projects.mind.intent.zhiji import IntentClassifier, ClassificationResult
from projects.mind.intent.task_data.message import Message
from projects.mind.intent.alg.volc_intent import (
    VolcengineIntentResult,
    IntentData,
    DebugInfo,
)
from nanoai.utils.data_concept import ClsResult
from nanoai.utils.async_utils import amap
from projects.mind.intent.zhiji.intent_data.category import chat, complex_navigation
from projects.mind.intent.alg.volc_intent import close_volcengine_session


# ==================== 测试用例定义 ====================

# Case 1: LLM异常，API正常（有结果且不为拒识）
test_case_1 = {
    "name": "LLM异常，API正常有结果",
    "llm_result": Exception("LLM调用失败"),
    "api_result": VolcengineIntentResult(
        intent=IntentData(
            message="test",
            domain="navigation",
            intent_type="navigation",
            input="导航到北京",
            slot_data=None,
            origin_intent_type=None,
            next_process=None,
        ),
        question_id="q123",
        reject=False,
        debug_info=DebugInfo(),
        byte_intent_type=None,
    ),
    "query": "导航到北京",
    "expected": {
        "final_intent": None,  # LLM异常，final_intent为None
        "llm_raw_result_category": "",  # 错误时的空category
        "api_reject": False,
        "api_intent_type": "navigation",  # API原始类型保持不变
    },
}

# Case 2: LLM正常（分类为"聊天"），API正常（有结果且不为拒识）
test_case_2 = {
    "name": "LLM分类为聊天，API正常有结果",
    "llm_result": ClsResult(category=chat.name, reason="这是问候语"),
    "api_result": VolcengineIntentResult(
        intent=IntentData(
            message="test",
            domain="chat",
            intent_type="chat",
            input="你好",
            slot_data=None,
            origin_intent_type=None,
            next_process=None,
        ),
        question_id="q123",
        reject=False,
        debug_info=DebugInfo(),
        byte_intent_type=None,
    ),
    "query": "你好",
    "expected": {
        "final_intent": None,  # 聊天被清除，交给API处理
        "llm_raw_result_category": chat.name,
        "api_reject": False,
        "api_intent_type": "chat",  # API原始类型保持不变
    },
}

# Case 3: LLM正常（分类为"复杂导航"），API正常（有结果且不为拒识）
test_case_3 = {
    "name": "LLM分类为复杂导航，API正常有结果",
    "llm_result": ClsResult(
        category=complex_navigation.name, reason="需要搜索确定目的地"
    ),
    "api_result": VolcengineIntentResult(
        intent=IntentData(
            message="test",
            domain="navigation",
            intent_type="navigation",  # API原始类型
            input="导航",
            slot_data=None,
            origin_intent_type=None,
            next_process=None,
        ),
        question_id="q123",
        reject=False,
        debug_info=DebugInfo(),
        byte_intent_type=None,
    ),
    "query": "看看附近最近的海底捞然后导航过去",
    "expected": {
        "final_intent": complex_navigation.name,
        "llm_raw_result_category": complex_navigation.name,
        "api_reject": False,
        "api_intent_type": complex_navigation.name,  # 被LLM覆盖
    },
}

# Case 4: LLM正常（分类为"复杂导航"），API正常（有结果且不为拒识），但input为空
test_case_4 = {
    "name": "LLM分类为复杂导航，API正常但input为空",
    "llm_result": ClsResult(
        category=complex_navigation.name, reason="需要搜索确定目的地"
    ),
    "api_result": VolcengineIntentResult(
        intent=IntentData(
            message="test",
            domain="navigation",
            intent_type="navigation",
            input=None,  # input为空
            slot_data=None,
            origin_intent_type=None,
            next_process=None,
        ),
        question_id="q123",
        reject=False,
        debug_info=DebugInfo(),
        byte_intent_type=None,
    ),
    "query": "看看附近最近的海底捞然后导航过去",
    "expected": {
        "final_intent": complex_navigation.name,
        "llm_raw_result_category": complex_navigation.name,
        "api_reject": False,
        "api_intent_type": complex_navigation.name,
        "api_intent_input": "看看附近最近的海底捞然后导航过去",  # 应该被补充
    },
}

# Case 5: LLM正常（分类为"复杂导航"），API拒识
test_case_5 = {
    "name": "LLM分类为复杂导航，API拒识",
    "llm_result": ClsResult(
        category=complex_navigation.name, reason="需要搜索确定目的地"
    ),
    "api_result": VolcengineIntentResult(
        intent=None,
        question_id="q123",
        reject=True,  # API拒识
        debug_info=DebugInfo(),
        byte_intent_type=None,
    ),
    "query": "看看附近最近的海底捞然后导航过去",
    "expected": {
        "final_intent": complex_navigation.name,
        "llm_raw_result_category": complex_navigation.name,
        "api_reject": False,  # 应该被设置为False
        "api_intent_type": complex_navigation.name,  # 应该创建新intent
        "api_intent_input": "看看附近最近的海底捞然后导航过去",
    },
}

# Case 6: LLM正常（分类为"复杂导航"），API正常但intent为None
test_case_6 = {
    "name": "LLM分类为复杂导航，API正常但intent为None",
    "llm_result": ClsResult(
        category=complex_navigation.name, reason="需要搜索确定目的地"
    ),
    "api_result": VolcengineIntentResult(
        intent=None,  # intent为None
        question_id="q123",
        reject=False,
        debug_info=DebugInfo(),
        byte_intent_type=None,
    ),
    "query": "看看附近最近的海底捞然后导航过去",
    "expected": {
        "final_intent": complex_navigation.name,
        "llm_raw_result_category": complex_navigation.name,
        "api_reject": False,
        "api_intent_type": complex_navigation.name,  # 应该创建新intent
        "api_intent_input": "看看附近最近的海底捞然后导航过去",
    },
}

# Case 7: LLM异常，API异常
test_case_7 = {
    "name": "LLM异常，API异常",
    "llm_result": Exception("LLM调用失败"),
    "api_result": Exception("API调用失败"),
    "query": "测试查询",
    "expected": {
        "final_intent": None,
        "llm_raw_result_category": "",
        "api_reject": True,  # API异常时创建拒识结果
        "api_intent": None,
    },
}

# Case 8: LLM正常（分类为"复杂导航"），API正常（有结果且不为拒识），input已有值
test_case_8 = {
    "name": "LLM分类为复杂导航，API正常且input已有值",
    "llm_result": ClsResult(
        category=complex_navigation.name, reason="需要搜索确定目的地"
    ),
    "api_result": VolcengineIntentResult(
        intent=IntentData(
            message="test",
            domain="navigation",
            intent_type="navigation",
            input="已有输入",  # input已有值
            slot_data=None,
            origin_intent_type=None,
            next_process=None,
        ),
        question_id="q123",
        reject=False,
        debug_info=DebugInfo(),
        byte_intent_type=None,
    ),
    "query": "看看附近最近的海底捞然后导航过去",
    "expected": {
        "final_intent": complex_navigation.name,
        "llm_raw_result_category": complex_navigation.name,
        "api_reject": False,
        "api_intent_type": complex_navigation.name,
        "api_intent_input": "已有输入",  # 应该保持不变
    },
}

# Case 9: LLM正常（分类为chat），API正常（有结果且不为拒识）
test_case_9 = {
    "name": "LLM分类为None，API正常有结果",
    "llm_result": ClsResult(category=chat.name, reason="无法分类"),  # category为空字符串
    "api_result": VolcengineIntentResult(
        intent=IntentData(
            message="test",
            domain="navigation",
            intent_type="navigation",
            input="导航",
            slot_data=None,
            origin_intent_type=None,
            next_process=None,
        ),
        question_id="q123",
        reject=False,
        debug_info=DebugInfo(),
        byte_intent_type=None,
    ),
    "query": "测试查询",
    "expected": {
        "final_intent": None,  # 会被设置为None
        "llm_raw_result_category": chat.name,
        "api_reject": False,
        "api_intent_type": "navigation",  # 会被设置为navigation
    },
}

# Case 10: LLM正常（分类为"聊天"），API拒识
test_case_10 = {
    "name": "LLM分类为聊天，API拒识",
    "llm_result": ClsResult(category=chat.name, reason="这是问候语"),
    "api_result": VolcengineIntentResult(
        intent=None,
        question_id="q123",
        reject=True,  # API拒识
        debug_info=DebugInfo(),
        byte_intent_type=None,
    ),
    "query": "你好",
    "expected": {
        "final_intent": None,  # 聊天被清除
        "llm_raw_result_category": chat.name,
        "api_reject": True,  # 保持拒识状态（因为llm_cls被清除，不会进入else分支创建intent）
        "api_intent": None,
    },
}


# ==================== 测试执行函数 ====================

async def run_single_test_mocked_api(
    classifier: IntentClassifier, test_case: dict[str, Any]
) -> tuple[bool, ClassificationResult, list[str]]:
    """执行单个测试用例"""
    query = test_case["query"]
    llm_result = test_case["llm_result"]
    api_result = test_case["api_result"]

    # Mock _run_llm_cls 和 _run_api
    with patch.object(
        classifier, "_run_llm_cls", new_callable=AsyncMock
    ) as mock_llm, patch.object(
        classifier, "_run_api", new_callable=AsyncMock
    ) as mock_api:
        # 设置mock返回值
        if isinstance(llm_result, Exception):
            mock_llm.side_effect = llm_result
        else:
            mock_llm.return_value = llm_result

        if isinstance(api_result, Exception):
            mock_api.side_effect = api_result
        else:
            mock_api.return_value = api_result

        # 执行run方法
        result = await classifier.run(query)

        # 验证结果
        expected = test_case["expected"]
        passed = True
        errors: list[str] = []

        # 检查final_intent
        if result.final_intent != expected.get("final_intent"):
            passed = False
            errors.append(
                f"final_intent: 预期={expected.get('final_intent')}, 实际={result.final_intent}"
            )

        # 检查llm_raw_result
        if (
            result.llm_raw_result.category
            != expected.get("llm_raw_result_category")
        ):
            passed = False
            errors.append(
                f"llm_raw_result.category: 预期={expected.get('llm_raw_result_category')}, 实际={result.llm_raw_result.category}"
            )

        # 检查api_result
        api = result.volc_api_result
        if api.reject != expected.get("api_reject"):
            passed = False
            errors.append(
                f"api.reject: 预期={expected.get('api_reject')}, 实际={api.reject}"
            )

        if "api_intent_type" in expected:
            if api.intent is None:
                passed = False
                errors.append("api.intent为None，但预期有intent_type")
            elif api.intent.intent_type != expected["api_intent_type"]:
                passed = False
                errors.append(
                    f"api.intent.intent_type: 预期={expected['api_intent_type']}, 实际={api.intent.intent_type}"
                )

        if "api_intent_input" in expected:
            if api.intent is None:
                passed = False
                errors.append("api.intent为None，但预期有input")
            elif api.intent.input != expected["api_intent_input"]:
                passed = False
                errors.append(
                    f"api.intent.input: 预期={expected['api_intent_input']}, 实际={api.intent.input}"
                )

        if "api_intent" in expected and api.intent != expected["api_intent"]:
            passed = False
            errors.append(
                f"api.intent: 预期={expected['api_intent']}, 实际={api.intent}"
            )

        return passed, result, errors


async def test_run_method_all_branches():
    """测试run方法的所有分支"""
    classifier = IntentClassifier()

    test_cases = [
        test_case_1,
        test_case_2,
        test_case_3,
        test_case_4,
        test_case_5,
        test_case_6,
        test_case_7,
        test_case_8,
        test_case_9,
        test_case_10,
    ]

    print("\n[bold cyan]开始测试 run 方法的所有分支...[/bold cyan]\n")

    for i, test_case in enumerate(test_cases, 1):
        print(f"[yellow]测试用例 {i}: {test_case['name']}[/yellow]")
        passed, result, errors = await run_single_test_mocked_api(classifier, test_case)

        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  状态: {status}")
        if not passed:
            print(f"  错误: {errors}")

        print(f"  查询: {test_case['query']}")
        print(f"  final_intent: {result.final_intent}")
        print(f"  llm_raw_result.category: {result.llm_raw_result.category}")
        print(f"  api.reject: {result.volc_api_result.reject}")
        if result.volc_api_result.intent:
            print(
                f"  api.intent.intent_type: {result.volc_api_result.intent.intent_type}"
            )
            print(f"  api.intent.input: {result.volc_api_result.intent.input}")
        print()

# 测试用例：无历史
test_cases_basic = [
    # 复杂导航类
    (
        "看看附近最近的海底捞然后导航过去",
        [
            Message(role="user", content="外面天气怎么样？"),
            Message(role="assistant", content="外面天气很好，适合出门游玩")
        ],
        "复杂导航"
    ),
    
    # 聊天类（兜底）
    (
        "你好",
        [
            Message(role="user", content="外面天气怎么样？"),
            Message(role="assistant", content="外面天气很好，适合出门游玩")
        ],
        "字节结果"
    ),
]

async def run_tests(test_cases: list[tuple[str, list[Message], str]] | list[tuple[str, str]]) -> None:
    """统一的测试函数，处理有历史和无历史两种情况"""
    async def run(params: tuple[str, list[Message], str] | tuple[str, str]) -> ClassificationResult:
        # 判断参数格式：2元组(无历史) 或 3元组(有历史)
        if len(params) == 2:
            query, expected = params
            messages: list[Message] | None = None
        else:
            query, messages, expected = params
        
        result = await IntentClassifier().run(query, messages)
        return result

    res, stats = await amap(run, test_cases, progress=False)

    for i ,result in enumerate(res):
        print(f"[yellow]测试用例 {i+1}: {test_cases[i][0]}[/yellow]")
        print(result)

    # 清理资源：关闭所有 HTTP 会话
    await close_volcengine_session()
    stats.print()

def main():
    """运行所有测试"""
    # 测试run方法的所有分支,mock数据测试
    # asyncio.run(test_run_method_all_branches())

    # 测试run方法，接口返回真实数据
    asyncio.run(run_tests(test_cases_basic))


if __name__ == "__main__":
    main()