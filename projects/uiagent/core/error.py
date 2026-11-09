from typing import Any

#class UIAgentError:
class UIAgentError(Exception):
    '''智能体运行时错误。'''
    def __init__(self, info: Any, reason: str, /):
        """info: 错误相关信息。reason: 错误原因。"""
        self.info = info       # 给开发者看的
        self.reason = reason   # 给用户看的

    def __str__(self) -> str:
        return f"{self.__class__.__name__}, UIAgent错误信息: {self.info}，错误现象: {self.reason}"


class UIAgentIntentError(UIAgentError):
    '''意图识别错误。'''
    pass


class UIAgentInfoTaskError(UIAgentError):
    '''信息搜集错误。'''
    def __init__(self, info_task: str, query: str, reason: str):
        super().__init__((info_task, query), f"信息提取任务 {info_task} 执行失败 for query: {query}, error: {reason}")


class UIAgentInfoInvalidError(UIAgentError):
    '''信息校验错误。'''
    def __init__(self, info_obj: Any, reason: str):
        super().__init__(info_obj, f"关于信息{info_obj}的校验失败, error: {reason}")


if __name__ == "__main__":
    err = UIAgentInfoTaskError("test_task", "test_query", "test_reason")
    print(err)