from typing import Type

from pydantic import BaseModel, Field

from nanoai.task.define import Task
from nanoai.task.engine import LMWorker, execute
from nanoai.utils._concept_meta import Concept
from nanoai.utils.nl_repr import nl_repr


class AnswerWithCotResult(BaseModel):
    """回答问题并给出思考过程的结果。"""

    answer: str = Field(..., title="回答", description="问题的答案。")
    steps: list[str] = Field(..., title="思考过程", description="思考过程。列表的每个元素是思考的一个步骤。")


def answer_with_cot(question: str, /, **kwargs) -> AnswerWithCotResult:
    """根据问题给出回答，并给出思考过程。"""

    task = Task(
        brief="请回答用户的问题并给出思考过程。",
        output_criteria=[
            "请以json格式返回结构化的结果。",
        ],
    )

    return execute(question, task, AnswerWithCotResult, **kwargs)


class TextComparer[R](LMWorker[R]):
    """通用的文本比较任务Worker。"""

    def __init__(self, criteria: list[str], output_type: Type[R], /, **kwargs):
        # TODO: 目前Task的写法显然不够通用，会需要各种扩充。
        super().__init__(
            Task(brief="对输入的两段文本进行比较", output_criteria=criteria),
            output_type,
            **kwargs,
        )

    def _prepare_input(self, text1: str, text2: str) -> str:
        return f"文本1: {text1}\n文本2: {text2}\n"


class ConceptInstanceGenerator(LMWorker[BaseModel]):
    def __init__(self, concept: Concept, /, **kwargs):
        self.concept = concept

        super().__init__(
            Task(
                brief=f"""给定一个概念的定义如下:
            {nl_repr(self.concept)}
            根据用户的输入提示, 生成这个概念的一个实例，以结构化的形式输出。""",
            ),
            self.concept.to_pydantic_model(),
            **kwargs,
        )
