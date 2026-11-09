"""
摘要任务模板演示

这个示例展示了如何使用NanoAI框架的模板任务功能。
我们将创建一个摘要任务模板，然后基于这个模板生成不同类型的摘要任务。

主要学习点：
1. 任务模板的设计
2. 枚举类型的使用
3. 模板实例化
4. 批量任务执行
5. 不同摘要类型和格式的对比

核心概念：
- 模板任务：一个可配置的任务框架，可以根据参数生成不同的具体任务
- 枚举类型：预定义的选项集合，确保参数的有效性
- 实例化：根据具体参数创建具体的任务实例
"""

from enum import StrEnum
from typing_extensions import assert_never

from nanoai.task import Task, execute_batch, aexecute_batch
from nanoai.task.engine import batch_results_to_df

from nanoai.utils.text_utils import df_to_html


class SummaryContent(StrEnum):
    """
    摘要内容类型枚举
    
    定义了三种不同的摘要内容类型，每种类型适合不同的使用场景：
    - OVERVIEW: 概览型，突出核心要点，适合快速了解文章主旨
    - ANALYTICAL: 分析型，包含深度分析和观点，适合学术研究和专业分析
    - EXECUTIVE: 执行型，聚焦决策要点和价值评估，适合商业决策
    """
    OVERVIEW = "概览型"
    ANALYTICAL = "分析型"
    EXECUTIVE = "执行型"


class SummaryFormat(StrEnum):
    """
    摘要格式枚举
    
    定义了四种不同的摘要格式，每种格式适合不同的阅读需求：
    - PARAGRAPH: 段落格式，连贯叙述，适合完整阅读
    - BULLET_POINTS: 要点格式，列表形式，适合快速扫描
    - STRUCTURED: 结构化格式，层次分明，适合深入分析
    - DETAILED: 详细格式，全面覆盖，适合技术实施
    """
    PARAGRAPH = "段落"
    BULLET_POINTS = "要点"
    STRUCTURED = "结构化"
    DETAILED = "详细"


class SummarizationTask(Task):
    """
    摘要任务模板类
    
    这是一个可配置的任务模板，用于创建各种类型的摘要任务。
    通过传入不同的参数（内容类型、格式、长度比例等），可以生成不同的具体任务。
    
    模板的优势：
    1. 避免重复编写相似的任务描述
    2. 确保任务描述的一致性和完整性
    3. 支持灵活的参数配置
    4. 便于维护和扩展
    """

    def __init__(self, length_ratio: float = 0.20):
        """
        初始化摘要任务模板
        
        Args:
            length_ratio: 摘要长度占原文的比例，默认15%
        """
        super().__init__(
            brief="根据输入的原文生成摘要。",
            output_criteria=[
                "摘要应该准确反映原文的主要内容和观点",
                "摘要长度不超过原文的{length_ratio}",
                "摘要的内容风格为:{content}",
                "摘要的格式风格为:{format}",
            ],
            detail="关于{content}内容风格的要求如下：{content_detail}\n关于{format}格式风格的要求如下：{format_detail}\n",
            template_defaults={"length_ratio": length_ratio},
        )

    @staticmethod
    def _content_detail(content: SummaryContent) -> str:
        """
        获取内容类型的详细说明
        
        这个方法为每种内容类型提供详细的描述，帮助AI更好地理解任务要求。
        """
        match content:
            case SummaryContent.OVERVIEW:
                return "突出核心要点，适合快速了解文章主旨。"
            case SummaryContent.ANALYTICAL:
                return "包含深度分析和观点，适合学术研究和专业分析。"
            case SummaryContent.EXECUTIVE:
                return "聚焦决策要点和价值评估，适合商业决策。"
            case _:
                assert_never(content)

    @staticmethod
    def _format_detail(format: SummaryFormat) -> str:
        """
        获取格式类型的详细说明
        
        这个方法为每种格式类型提供详细的描述，帮助AI生成符合要求的格式。
        """
        match format:
            case SummaryFormat.PARAGRAPH:
                return "采用连贯的叙述方式，语言流畅自然，适合完整阅读和理解。每个段落围绕一个主题展开，逻辑清晰，便于读者把握文章的整体脉络和核心观点。"
            case SummaryFormat.BULLET_POINTS:
                return "以列表形式呈现关键信息，每个要点简洁明了，便于快速扫描和记忆。适合时间紧迫的场景，能够帮助读者在短时间内获取最重要的信息点。"
            case SummaryFormat.STRUCTURED:
                return "按照逻辑层次组织内容，包含明确的标题、子标题和分类。便于深入分析和研究，支持学术引用和进一步讨论。结构清晰，便于查找特定信息。"
            case SummaryFormat.DETAILED:
                return "提供全面的信息覆盖，包含具体的数据、案例和操作步骤。适合技术实施和方案设计，为后续工作提供充分的参考依据和操作指导。"
            case _:
                assert_never(format)

    def instantiate(
        self,
        content: SummaryContent,
        format_type: SummaryFormat,
        length_ratio: float = 0.20,
    ) -> Task:
        """
        实例化摘要任务
        
        根据传入的参数创建具体的摘要任务实例。
        这是模板的核心方法，将抽象的模板转换为具体的任务。
        
        Args:
            content: 摘要内容类型
            format_type: 摘要格式类型
            length_ratio: 摘要长度比例（可选，使用模板默认值）
            
        Returns:
            具体的Task实例
        """
        # 调用父类方法实例化，传入模板参数
        instance = super().instantiate(
            content=content,
            content_detail=self._content_detail(content),
            format=format_type,
            format_detail=self._format_detail(format_type),
            length_ratio=length_ratio,
        )

        # 返回完整的任务实例
        return Task(
            brief=instance.brief,
            detail=instance.detail,
            input_criteria=instance.input_criteria,
            output_criteria=instance.output_criteria,
            examples_pos=instance.examples_pos,
            examples_neg=instance.examples_neg,
        )


# 技术文章示例：用于演示摘要任务
articles = ["""人工智能技术在医疗领域的应用正在快速发展，为医疗行业带来了革命性的变化。机器学习算法能够分析大量的医疗数据，包括患者病历、影像资料、基因信息等，从而提供更准确的诊断和治疗建议。
在医学影像诊断方面，深度学习技术已经达到了与人类专家相当甚至更高的准确率。例如，在肺部CT扫描的肺癌检测中，AI系统能够识别出微小的病变，这些病变可能被人类医生忽略。在眼科疾病诊断中，AI系统能够通过分析眼底照片来检测糖尿病视网膜病变、青光眼等疾病。
在药物研发领域，人工智能正在加速新药的发现过程。传统的药物研发需要数年甚至数十年的时间，而AI技术可以通过分析分子结构、预测药物与靶点的相互作用，大大缩短研发周期。同时，AI还能够帮助优化临床试验设计，提高试验效率。
在个性化医疗方面，AI技术能够根据患者的基因信息、生活习惯、病史等数据，制定个性化的治疗方案。这种精准医疗的方法能够提高治疗效果，减少副作用，降低医疗成本。
然而，AI在医疗领域的应用也面临着一些挑战。首先是数据隐私和安全问题，医疗数据涉及患者隐私，需要严格的安全保护措施。其次是算法的可解释性问题，医生和患者需要理解AI决策的依据。此外，还需要建立完善的监管体系，确保AI医疗产品的安全性和有效性。
尽管存在这些挑战，但人工智能在医疗领域的应用前景依然广阔。随着技术的不断进步和监管体系的完善，AI将成为医疗行业的重要工具，为患者提供更好的医疗服务。
""",

"""随着人工智能技术的不断进步，智能体（Agent）开发成为推动自动化和智能化应用的重要方向。智能体是一种能够自主感知环境、做出决策并采取行动的软件实体，广泛应用于对话系统、自动驾驶、智能推荐、金融分析等领域。
在智能体开发过程中，首先需要明确智能体的目标和任务。例如，客服智能体的目标是高效解答用户问题，而自动驾驶智能体则需要在复杂环境中安全行驶。开发者通常会采用模块化设计，将感知、决策、执行等功能分离，便于系统的扩展和维护。
感知模块负责收集和处理环境信息，常用技术包括自然语言处理、计算机视觉和传感器数据融合。决策模块则基于感知结果，利用规则引擎、机器学习或强化学习算法，选择最优的行动方案。执行模块将决策转化为具体操作，如生成回复、控制机器人动作等。
近年来，基于大语言模型（LLM）的智能体开发受到广泛关注。开发者可以通过Prompt Engineering、工具调用（Tool Use）、多智能体协作等方式，构建具备复杂推理和任务分解能力的智能体。例如，结合外部API和知识库，智能体能够完成信息检索、数据分析、自动化办公等任务。
智能体开发还面临诸多挑战，包括多轮对话的上下文管理、长期记忆的实现、任务规划与分解、异常处理和安全性保障等。为此，业界提出了如Agent Framework、Memory Module、Task Orchestration等一系列技术方案，推动智能体系统向更高的智能水平演进。
未来，随着算法、算力和数据的持续提升，智能体将更加智能和自主，成为各行各业数字化转型的重要驱动力。
""",
]


def demo_summarization():
    """
    演示摘要任务模板的使用
    
    这个函数展示了如何：
    1. 创建一个摘要任务模板
    2. 基于模板生成不同类型的摘要任务
    3. 批量执行这些任务
    4. 对比不同任务的结果
    
    Args:
        input_text: 需要摘要的文本内容
    """
    # 创建摘要任务模板
    template = SummarizationTask()
    print("=== 摘要任务模板演示 ===")
    print("模板描述:", template.template_description)
    print("\n将基于这个模板生成3种不同类型的摘要任务...")

    # 基于模板生成不同类型的摘要任务
    summary_tasks = [
        # 任务1：概览型段落摘要 - 适合快速了解文章大意
        template.instantiate(
            content=SummaryContent.OVERVIEW, 
            format_type=SummaryFormat.PARAGRAPH
        ),
        
        # 任务2：分析型结构化摘要 - 适合深入研究和技术分析
        template.instantiate(
            content=SummaryContent.ANALYTICAL,
            format_type=SummaryFormat.STRUCTURED
        ),
        
        # 任务3：执行型要点摘要 - 适合商业决策和价值评估
        template.instantiate(
            content=SummaryContent.EXECUTIVE,
            format_type=SummaryFormat.BULLET_POINTS
        ),
    ]

    print(f"生成了 {len(summary_tasks)} 个不同的摘要任务")
    print("任务类型:")
    print("1. 概览型段落摘要 - 适合快速阅读和理解")
    print("2. 分析型结构化摘要 - 适合深入研究和分析")
    print("3. 执行型要点摘要 - 适合快速决策和行动")

    # 批量执行所有摘要任务
    print("\n开始批量执行摘要任务...")
    async_mode = True
    if async_mode:
        import asyncio
        all_results = asyncio.run(aexecute_batch(articles, [(task, str) for task in summary_tasks]))
    else:
        all_results = execute_batch(articles, [(task, str) for task in summary_tasks])

    # 将结果转换为DataFrame，便于查看和比较
    print("整理结果...")
    df = batch_results_to_df(articles, [task for task in summary_tasks], all_results)

    # 生成HTML报告，便于在浏览器中查看
    print("生成HTML报告...")
    # 让所有列等宽
    n_cols = len(df.columns)
    assert n_cols > 1, "至少需要两个列"
    col_width = f"{100 // n_cols}%"
    column_widths: dict[str | int, str] = {i: col_width for i in range(n_cols)}

    df_to_html(
        df,
        "summarization_results.html",
        title="📝 摘要任务结果对比",
        summary_info={"总任务数": str(len(df.columns) - 1), "测试用例数": str(len(df))},
        column_widths=column_widths,
    )
    
    print("完成！请打开 summarization_results.html 查看详细结果")
    print("\n=== 模板任务的优势 ===")
    print("1. 代码复用：一个模板生成多个任务")
    print("2. 一致性：所有任务都有统一的结构")
    print("3. 灵活性：可以轻松调整参数")
    print("4. 可维护性：修改模板即可影响所有相关任务")


if __name__ == "__main__":
    """
    主程序入口
    
    演示摘要任务模板的完整流程：
    1. 创建任务模板
    2. 生成不同类型的任务
    3. 批量执行
    4. 结果对比
    """
    print("📝 摘要任务模板演示")
    print("=" * 60)
    print("这个演示展示了如何使用任务模板来生成不同类型的摘要任务")
    print("我们将对一篇关于AI医疗应用的文章生成3种不同风格的摘要")
    print("=" * 60)
    
    # 执行摘要演示
    demo_summarization()
    
    print("\n" + "=" * 60)
    print("演示完成！")
    print("生成的 summarization_results.html 文件包含了所有摘要任务的详细对比结果。")
    print("你可以看到不同内容类型和格式对摘要结果的影响。")
