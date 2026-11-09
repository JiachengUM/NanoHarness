from typing import Self, Sequence, cast

from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionUserMessageParam,
)


class QAList(list[tuple[str, str]]):
    """(user message, assistant message)的列表。最简易形式的对话数据。"""

    @classmethod
    def from_messages(cls, messages: Sequence[ChatCompletionMessageParam]) -> Self:
        # 扫描messages，生成(user message, assistant message)的列表。
        # 通过role判断消息类型属于user或assistant。跳过其它role。

        qa_pairs: list[tuple[str, str]] = []

        user_msg = None
        assistant_msg = None
        for message in messages:
            # role = message.get("role", "")
            role = message["role"]

            if role == "user":
                message = cast(ChatCompletionUserMessageParam, message)
                user_msg = message["content"]
                assert assistant_msg is None, "遇到user_msg时，assistant_msg不能存在"
            elif role == "assistant":
                message = cast(ChatCompletionAssistantMessageParam, message)
                if "content" in message:
                    assistant_msg = message["content"]
                else:
                    # TODO: 此时有tool_calls。需要处理么？
                    assistant_msg = ""
                assert user_msg is not None, "遇到assistant_msg时，user_msg不能为空"

                assert isinstance(user_msg, str), "user_msg必须是str"
                assert isinstance(assistant_msg, str), "assistant_msg必须是str"

                qa_pairs.append((user_msg, assistant_msg))
                user_msg = None
                assistant_msg = None
            else:
                # TODO: 其它role的消息，暂时跳过。
                continue

        return cls(qa_pairs)

    def format(self, user_prefix: str = "user", assistant_prefix: str = "assistant") -> str:
        return "\n".join(
            [f"{user_prefix}: {user_msg}\n{assistant_prefix}: {assistant_msg}" for user_msg, assistant_msg in self]
        )
