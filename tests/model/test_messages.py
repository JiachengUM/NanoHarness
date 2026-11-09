from typing import cast

import pytest
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionFunctionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionUserMessageParam,
)

from nanoai.model.messages import QAList


def test_empty_messages():
    """测试空消息列表"""
    print("测试空消息列表")
    messages = []
    qa_list = QAList.from_messages(messages)
    assert len(qa_list) == 0
    assert qa_list.format() == ""


def test_single_qa_pair():
    """测试单个问答对"""
    print("测试单个问答对")
    messages = [
        ChatCompletionUserMessageParam(role="user", content="你好"),
        ChatCompletionAssistantMessageParam(role="assistant", content="你好！有什么可以帮助你的吗？"),
    ]
    qa_list = QAList.from_messages(messages)
    assert len(qa_list) == 1
    assert qa_list[0] == ("你好", "你好！有什么可以帮助你的吗？")


def test_multiple_qa_pairs():
    """测试多个问答对"""
    print("测试多个问答对")
    messages = [
        ChatCompletionUserMessageParam(role="user", content="什么是AI？"),
        ChatCompletionAssistantMessageParam(role="assistant", content="AI是人工智能的缩写"),
        ChatCompletionUserMessageParam(role="user", content="AI有什么用途？"),
        ChatCompletionAssistantMessageParam(role="assistant", content="AI可以用于自动化、数据分析等"),
    ]
    qa_list = QAList.from_messages(messages)
    assert len(qa_list) == 2
    assert qa_list[0] == ("什么是AI？", "AI是人工智能的缩写")
    assert qa_list[1] == ("AI有什么用途？", "AI可以用于自动化、数据分析等")


def test_system_messages_ignored():
    """测试系统消息被忽略"""
    print("测试系统消息被忽略")
    messages = [
        ChatCompletionSystemMessageParam(role="system", content="你是一个助手"),
        ChatCompletionUserMessageParam(role="user", content="你好"),
        ChatCompletionAssistantMessageParam(role="assistant", content="你好！"),
    ]
    qa_list = QAList.from_messages(messages)
    assert len(qa_list) == 1
    assert qa_list[0] == ("你好", "你好！")


def test_unknown_roles_ignored():
    """测试未知角色被忽略"""
    print("测试未知角色被忽略")
    messages = [
        ChatCompletionUserMessageParam(role="user", content="问题1"),
        ChatCompletionFunctionMessageParam(role="function", content="函数调用结果", name="test_function"),
        ChatCompletionAssistantMessageParam(role="assistant", content="回答1"),
        ChatCompletionToolMessageParam(role="tool", content="工具输出", tool_call_id="tool_123"),
        ChatCompletionUserMessageParam(role="user", content="问题2"),
        ChatCompletionAssistantMessageParam(role="assistant", content="回答2"),
    ]
    qa_list = QAList.from_messages(messages)
    assert len(qa_list) == 2
    assert qa_list[0] == ("问题1", "回答1")
    assert qa_list[1] == ("问题2", "回答2")


def test_incomplete_qa_pair_user_only():
    """测试不完整的问答对（只有用户消息）"""
    print("测试不完整的问答对（只有用户消息）")
    messages = [
        ChatCompletionUserMessageParam(role="user", content="问题1"),
        ChatCompletionAssistantMessageParam(role="assistant", content="回答1"),
        ChatCompletionUserMessageParam(role="user", content="问题2"),  # 没有对应的assistant回答
    ]
    qa_list = QAList.from_messages(messages)
    assert len(qa_list) == 1
    assert qa_list[0] == ("问题1", "回答1")


def test_format_custom_prefixes():
    """测试自定义前缀格式化"""
    print("测试自定义前缀格式化")
    messages = [
        ChatCompletionUserMessageParam(role="user", content="问题"),
        ChatCompletionAssistantMessageParam(role="assistant", content="回答"),
    ]
    qa_list = QAList.from_messages(messages)
    formatted = qa_list.format(user_prefix="Human", assistant_prefix="AI")
    expected = "Human: 问题\nAI: 回答"
    assert formatted == expected


def test_assertion_error_assistant_without_user():
    """测试断言错误：遇到assistant消息时user_msg为None"""
    print("测试断言错误：遇到assistant消息时user_msg为None")
    messages = [ChatCompletionAssistantMessageParam(role="assistant", content="没有对应用户消息的助手消息")]
    with pytest.raises(AssertionError):
        QAList.from_messages(messages)


def test_complex_conversation_flow():
    """测试复杂对话流程"""
    print("测试复杂对话流程")
    messages = [
        ChatCompletionSystemMessageParam(role="system", content="你是一个助手"),
        ChatCompletionUserMessageParam(role="user", content="介绍一下Python"),
        ChatCompletionAssistantMessageParam(role="assistant", content="Python是一种编程语言"),
        ChatCompletionFunctionMessageParam(role="function", content="函数调用", name="get_info"),
        ChatCompletionUserMessageParam(role="user", content="Python有什么特点？"),
        ChatCompletionAssistantMessageParam(role="assistant", content="Python简洁易读"),
        ChatCompletionToolMessageParam(role="tool", content="工具输出", tool_call_id="tool_456"),
        ChatCompletionUserMessageParam(role="user", content="如何学习Python？"),
        ChatCompletionAssistantMessageParam(role="assistant", content="可以从基础语法开始"),
    ]
    qa_list = QAList.from_messages(messages)
    assert len(qa_list) == 3
    assert qa_list[0] == ("介绍一下Python", "Python是一种编程语言")
    assert qa_list[1] == ("Python有什么特点？", "Python简洁易读")
    assert qa_list[2] == ("如何学习Python？", "可以从基础语法开始")


def main():
    # 调用所有test function
    test_empty_messages()
    test_single_qa_pair()
    test_multiple_qa_pairs()
    test_system_messages_ignored()
    test_unknown_roles_ignored()
    test_incomplete_qa_pair_user_only()
    test_format_custom_prefixes()
    test_assertion_error_assistant_without_user()
    test_complex_conversation_flow()
    print("所有测试函数执行完成")


if __name__ == "__main__":
    main()
