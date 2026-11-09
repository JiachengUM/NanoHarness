"""
任务定义模块 (Task Definition)

这个模块提供了任务系统的核心数据结构定义，用于描述、管理和执行各种任务。

主要功能：
1. 任务定义：提供Task类用于描述任务的基本信息、输入输出要求等
2. 测试用例：提供TaskCase类用于定义任务的输入输出示例
3. 模板系统：支持参数化任务模板，可以动态实例化具体任务
4. 类型安全：基于Pydantic提供数据验证和类型检查

核心类：
- Task: 通用任务定义类，包含任务描述、输入输出标准、示例等
- TaskCase: 任务测试用例，包含输入、输出和说明
- _TaskT: 带类型信息的任务类（实验性功能）

主要特性：
1. 不可变性：Task对象创建后不可修改，确保数据一致性
2. 模板化：支持参数化模板，可以动态生成具体任务
3. 结构化描述：通过多个字段结构化描述任务的各个方面
4. 缓存机制：利用cached_property优化性能
5. 自然语言表示：支持nl_repr协议，便于人类阅读

使用示例：
    # 基本任务定义
    task = Task(
        brief="文本摘要任务",
        input_criteria=["输入文本长度大于100字", "文本语言为中文"],
        output_criteria=["摘要长度不超过原文的30%", "保持原文核心信息"],
        examples_pos=[
            TaskCase(
                input="这是一篇关于人工智能的长文章...",
                output="本文介绍了人工智能的发展历程和未来趋势..."
            )
        ]
    )
    
    # 模板化任务
    template = Task(
        brief="对{content_type}进行{operation}",
        input_criteria=["{content_type}格式正确", "内容非空"],
        template_defaults={"content_type": "文本", "operation": "分析"}
    )
    
    # 实例化模板
    specific_task = template.instantiate(
        content_type="代码",
        operation="语法检查"
    )

设计理念：
- 结构化：将任务描述分解为多个结构化字段
- 可扩展：支持模板化和参数化，便于批量生成任务
- 类型安全：基于Pydantic提供完整的类型检查
- 性能优化：使用缓存机制提升重复计算性能
- 人类友好：支持自然语言表示，便于调试和理解
"""

from functools import cached_property
from typing import Any

from pydantic import BaseModel, Field

from nanoai.utils._concept_meta import Concept
from nanoai.utils.text_utils import extract_params, format_template

__all__ = [
    "TaskCase",
    "Task",
]


class TaskCase[IT, OT](BaseModel):
    """一个测试用例数据。"""

    # TODO: 增加下述属性： name, category, priority

    input: IT = Field(..., title="输入", description="任务的输入")

    output: OT = Field(..., title="输出", description="任务的输出")
    """TODO: 改为gt？ 类型改为 OT | None"""

    comment: str | None = Field(
        default=None,
        title="说明",
        description="该case的补充说明。给人使用的。例如，其体现了什么问题。",
    )


class Task(BaseModel):
    """
    通用的任务定义。基础概念，用途广泛:
    - 任务的精确描述和控制
    - 和llm prompt的转换
    """

    model_config = {"frozen": True}
    """任务不能修改，确保数据的一致性，有很多好处。例如：模板功能的缓存机制实现依赖于这一点。"""

    # name: str | None = Field(
    #     default=None,
    #     description="任务的唯一标识符，用于任务管理和引用。必须是有效的Python标识符。"
    # )
    # """任务名称，用于在任务注册表中唯一标识任务。
    # 这个字段对于任务管理、依赖分析和工作流编排非常重要。
    # """

    brief: str = Field(
        ...,
        title="任务简述",
        description="任务的简要描述。能大致说明要做什么，输入和输出是什么即可。不要包括'怎么做'和'输入输出的详细描述'。不要换行。",
    )
    """最重要的属性。描述"是什么"。原则上，其它的属性都可以由此推导出来。
    在关于task的各种元任务中，输入是task，需要根据其各个字段做一些判断。
    此时不易直接使用description，因为可能太复杂，导致最终的prompt难以理解。
    通常使用brief即可。这种情况下，brief通常简明一些比较好。
    更加细节的任务描述需要以结构化的方式放在其它字段中，例如input_criteria, output_criteria, examples等。"""

    # output_type: Concept = Field(..., description="任务输出数据的概念定义。")
    # TODO: output_type放在这里是可以在generate_task中生成的。

    input_criteria: list[str] | None = Field(
        default=None,
        title="对于输入的要求(共{len_list}条)",
        description="关于输入的描述。列表中的每一条标准都可以衡量好坏并量化。",
    )
    """用于input的合法性检查，意图识别等。
    注意这里DatumCriterion的类型是input type（目前还没有，缺省为str），不能是R。
    """

    output_criteria: list[str] = Field(
        default_factory=list,
        title="对于输出的要求(共{len_list}条)",
        description="关于所期望的输出结果的描述。列表中的每一条标准都可以衡量好坏并量化。",
    )
    """对于Worker, Evaluator等实现很有用，是其prompt的一部分。对于task output的消费者也有用, 可以判断这个task是否适用。"""

    detail: str | None = Field(
        default=None,
        title="任务详述",
        description="关于各种任务细节的描述。其它字段不能描述的内容都可以放在这里。",
    )
    """这个字段用于做各种任务描述的定制化。例如，一步一步怎么做的详细说明。
    TODO: 足够通用重要的内容可以放在新的字段中。例如，"怎么做"可以变为how_to字段，将来用于子任务的拆解和连接。
    """

    examples_pos: list[TaskCase] | None = Field(
        default=None, title="正例(共{len_list}条)", description="若干典型的正例。"
    )
    examples_neg: list[TaskCase] | None = Field(
        default=None, title="反例(共{len_list}条)", description="若干典型的反例。"
    )

    """下面是Task模版的实现。支持参数替换和实例化。
    支持在构造函数中设置默认参数值，用于在实例化时提供默认的参数值。
    只有有默认值的参数才需要在template_defaults中声明。
    # TODO: 这部分功能可以独立出来成为TaskTemplate类，并继承自_TaskBase。目前写在_TaskBase中，是因为这样写简单，但设计上可能会有些问题。暂时还想不清楚。
    """

    template_defaults: dict[str, Any] = Field(
        default_factory=dict,
        description="模板默认值字典，只包含有默认值的参数",
        repr=False,
    )
    # TODO: value的type目前是Any。语义上，应该是nl representable。

    @property
    def template_description(self) -> str | None:
        """返回模板的自然语言描述。
        如果param_names不为空，则self是一个template，返回其说明。
        """
        if not self.param_names:
            return None

        # 列举param_names中的所有参数，并生成其说明。
        desc = "这是一个Task模板，可以通过如下参数实例化。"
        for param_name in self.param_names:
            desc += f"\n{param_name}: {self.template_defaults.get(param_name, '未设置')}"

        return desc

    def instantiate(self, **param_values) -> "Task":
        """使用参数值实例化模板，返回新的 Task 实例。
        会合并默认参数值和传入的参数值，传入的值会覆盖默认值。
        这里的实现非常简单，就是对于每个参数做其value的字符串替换。
        如果每个param_name仅在一个字段（例如brief）中出现，完全可以让用户自行构造Task对象，不需要模版。
        然而，这里的实现仍然有意义。出于以下原因：
        1. 如果param_name会在多个字段中出现。例如，content_category字段同时出现在brief, details和input_criteria中。这里的实现能确保一致性，以及做一些错误检查。
        2. 如果需要更复杂的实现，可以继承_TaskBase，重写instantiate方法。
        3. TaskTemplate本身是一个足够重要基础的概念。库里需要有。即使当前的实现比较naive，也需要基于其迭代。
        4. 将来可以提供更加结构化的写法。例如，每个task.param_name可以有类型。根据其类型决定如何参数化brief, details等字段。
        """
        # 获取模板中所有参数名称
        param_names = self.param_names
        if not param_names:
            raise RuntimeError("param_names不能为空，否则instantiate没有意义。")

        # 验证传入的参数值是否有效
        invalid_keys = set(param_values.keys()) - param_names
        if invalid_keys:
            raise ValueError(
                f"无效的参数: {', '.join(sorted(invalid_keys))}. " f"有效的参数: {', '.join(sorted(param_names))}"
            )

        # 合并默认值和传入值，传入值优先
        merged_values = {**self.template_defaults, **param_values}

        # 验证所有参数都有值
        missing = param_names - set(merged_values.keys())
        if missing:
            raise KeyError(f"缺少参数: {', '.join(sorted(missing))}")

        # 处理brief
        processed_brief = format_template(self.brief, merged_values)

        # 处理detail
        processed_detail = format_template(self.detail, merged_values) if self.detail else None

        # 处理input_criteria
        # TODO: 需要补充item是DatumCriterion的情况。
        processed_input_criteria = []
        if self.input_criteria:
            for item in self.input_criteria:
                if isinstance(item, str):
                    processed_input_criteria.append(format_template(item, merged_values))
                else:
                    processed_input_criteria.append(item)

        # 处理output_criteria
        # TODO: 需要补充item是DatumCriterion的情况。
        processed_output_criteria = []
        if self.output_criteria:
            for item in self.output_criteria:
                if isinstance(item, str):
                    processed_output_criteria.append(format_template(item, merged_values))
                else:
                    processed_output_criteria.append(item)

        # 生成的必须是Task instance, 不是template, 所以不能包括default_placeholders。
        return Task(
            brief=processed_brief,
            detail=processed_detail,
            input_criteria=processed_input_criteria,
            output_criteria=processed_output_criteria,
            examples_pos=self.examples_pos,
            examples_neg=self.examples_neg,
        )

    @cached_property
    def param_names(self) -> set[str]:
        """获取模板中所有的参数名集合，包含所有字段中 {param_name} 形式的参数。

        设计考虑：
        1. 缓存机制：
           - 使用 @cached_property 而非手动缓存，利用 Python 标准库的可靠性。以及线程安全。
           - 第一次访问时计算并缓存结果，后续访问直接返回缓存值
           - 缓存存储在对象上，对象销毁时自动清理

        2. 不可变性约束：
           - Task 设置了 model_config = {"frozen": True}，确保了不可变性
           - 不可变性是缓存机制安全性的前提，避免了缓存失效问题
        """
        param_names = set()
        param_names.update(extract_params(self.brief))
        if self.detail:
            param_names.update(extract_params(self.detail))
        if self.input_criteria:
            for item in self.input_criteria:
                if isinstance(item, str):
                    param_names.update(extract_params(item))
        if self.output_criteria:
            for item in self.output_criteria:
                if isinstance(item, str):
                    param_names.update(extract_params(item))
        return param_names


class _TaskT(Task):
    """具有输入输出类型信息的Task。暂时只是用于内部的探索实验。实践中能怎么用还不清楚。"""

    input_type: Concept = Field(..., description="任务输入数据的概念定义。")
    output_type: Concept = Field(..., description="任务输出数据的概念定义。")
    """type字段不能是真的python type。否则无法生成json schema。
    暂时先用Concept。
    TODO: 类型可以扩充为int, bool, list, ...。参见Task.output_type的注释。
    增加nl前缀，变成str类型。增加output_type属性，通过eval变为Type。
    TODO: 无法被generate_task生成。需要理解structure output的底层原因。
    """

    # 下面的input(output)_schema(concept)字段目前只是用于一些内容功能的尝试和验证。对于外部用户并无实际作用，不用理会。
    # input_schema: dict[str, Any] = Field(
    #     default={},
    #     description="输入数据的JSON Schema定义，用于验证输入数据的格式和结构",
    #     examples = [
    #         {
    #             "type": "object",
    #             "properties": {
    #                 "text": {"type": "string", "description": "要处理的文本"},
    #                 "max_length": {"type": "integer", "minimum": 1, "maximum": 1000}
    #             },
    #             "required": ["text"]
    #         }
    #     ]
    # )

    # output_schema: dict[str, Any] = Field(
    #     default={},
    #     description="输出数据的JSON Schema定义，用于验证输出数据的格式和结构",
    #     examples = [
    #         {
    #             "type": "object",
    #             "properties": {
    #                 "summary": {"type": "string", "description": "生成的摘要"},
    #                 "word_count": {"type": "integer", "description": "摘要字数"}
    #             },
    #             "required": ["summary", "word_count"]
    #         }
    #     ]
    # )
