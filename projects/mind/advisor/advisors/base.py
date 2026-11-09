from typing import cast

from nanoai.model.config import create_client, AsyncOpenAI
from nanoai.utils.nl_repr import nl_repr
from nanoai.model.llm import allm, allm_output_by_schema

from projects.mind.advisor.task_data import AdvisorInput, AdvisorParam, AdviserOutput, AdvisorRunResult


class Adviser[P]:
    '''
    advisor基类。根据用户、车辆状态、外部视觉信息和内部视觉信息提供基于特定目标的建议。

    P: 算法param的类型。必须继承自AdvisorParam。
    '''

    def __init__(self, param: P):
        assert isinstance(param, AdvisorParam), "param必须是AdvisorParam的实例"
        
        self._param = param
        
        self.client, self.model = create_client(self._param.model, AsyncOpenAI)


    @property
    def param(self) -> P:
        return self._param


    def sys_prompt(self) -> str:
        ''''''
        assert isinstance(self.param, AdvisorParam), "param必须是AdvisorParam的实例"

        # 外部传入的sys_prompt优先级更高
        if self.param.sys_prompt:
            return self.param.sys_prompt

        # TODO: 是否值得提供一个缺省实现？想不清楚。

        raise NotImplementedError("sys_prompt未定义")


    def user_prompt(self, event: str, context: str) -> str:
        '''
        user prompt和sys prompt有本质区别。处理方式也不一样。
        缺省实现非常简单。要修改的话, 直接在param中重写user_prompt即可。
        TODO: 涉及到rag时可能需要继承和重写。
        '''
        assert isinstance(self.param, AdvisorParam), "param必须是AdvisorParam的实例"

        if self.param.user_prompt:
            # 外部传入的user_prompt优先级最高. 假设user_prompt可以通过event和context来生成实例
            # TODO: 如何检查这个约束条件？
            return self.param.user_prompt.format(event=nl_repr(event), context=nl_repr(context))

        
        prompt = f"""\n当前发生了下述事件:\n{event}"""
        prompt += f"""\n上下文信息如下:\n{context}"""
        prompt += f"""\n请提出建议。"""

        return prompt
        

    async def run(self, input: AdvisorInput) -> tuple[AdviserOutput, AdvisorRunResult]:
        '''
        缺省实现非常简单。通常需要继承重新实现。
        '''
        assert isinstance(self.param, AdvisorParam), "param必须是AdvisorParam的实例"

        prompt = self.user_prompt(event=nl_repr(input.event), context=nl_repr(input.context))
        # 输出格式单独放在末尾
        prompt += f"""\n{AdviserOutput.model_output_prompt()}"""

        sys_prompt = self.sys_prompt()
        
        res = await allm_output_by_schema(
            prompt,
            sys_prompt,
            output_type=AdviserOutput,
            client=self.client,
            model=self.model,
        )

        output = cast(AdviserOutput, res.output)

        run_result = AdvisorRunResult(
            sys_prompt=sys_prompt,
            user_prompt=prompt,
        )

        return output, run_result
