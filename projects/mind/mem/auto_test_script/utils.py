import re

from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.messages.base import BaseMessage
from langchain_core.tools.base import BaseTool

from projects.mind.mem.volc_api import Message


def convert_langchain_history_to_volc_format(history: list[BaseMessage]) -> list[Message]:
    """
    将langchain的对话记录转换为火山的对话记录格式
    """
    volc_history = []
    for message in history:
        if isinstance(message, HumanMessage):
            role = "user"
            volc_history.append(
                Message(role=role, content=message.content))
        elif isinstance(message, AIMessage) and message.content != "":
            role = "assistant"
            volc_history.append(
                Message(role=role, content=message.content))
        elif isinstance(message, SystemMessage):
            role = "system"
            volc_history.append(
                Message(role=role, content=message.content))
        else:
            continue
    return volc_history


def parse_score(query: str) -> int:
    """
    解析评分字符串，返回整数评分
    """
    # 从“谢谢，退下吧，我给你打X分”中提取X，并且校验分数是否在1-5分内，否则返回0
    match = re.search(r"我给你打(\d+)分", query)
    if match:
        score = int(match.group(1))
        if 1 <= score <= 5:
            return score
    return 0


def convert_tools_to_tools_info(tools: list[BaseTool]) -> str:
    """
    将工具列表转换为工具描述字符串
    """
    return "\n".join(["工具名称：" + tool.name + " 工具描述：" + tool.description for tool in tools])
