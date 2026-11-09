"""
文本润色任务评估Demo

本文件演示如何：
- 定义一个文本润色任务（Task）
- 设计同步和异步的评估指标（CaseCriterion/DatumCriterion）
- 批量评测多个案例，自动生成美观的HTML评估报告
- 自定义单元格样式和内容格式化
- 支持同步/异步LLM调用，支持自定义样式自动检测

适用人群：
- 想用大模型自动评测文本任务的开发者
- 想批量生成可视化评估报告的产品/算法/教学人员
- 想学习如何用Python优雅地做评测和报表的开发者

主要学习点：
1. 任务定义
2. 同步/异步评测指标
3. 批量评测
4. 可视化报告生成
5. 自定义样式和格式化

"""

from nanoai.task import Task, JudgeResult, compare_judge, judge, acompare_judge, ajudge, CaseCriterion, TaskCaseGT, evaluate_dataset, aevaluate_dataset
from nanoai.task.eval import evaluation_results_to_df
from nanoai.utils.metric import DatumCriterion
from nanoai.utils.text_utils import df_to_html, CellStyle
from nanoai.utils.nl_repr import nl_repr

# 1. 定义任务（Task）
# -------------------
# 任务描述：对输入文本进行不改变语义的改写和润色
TASK_REWRITE = Task(
    brief="对于输入的文本进行不改变语义的改写和润色。",
    input_criteria=[
        "为中文。包含完整句子或段落。有明确可理解的含义。",
    ],
    output_criteria=[
        "和原文长度大致相等。",
        "保持原文的语义、逻辑、事实。",
        "保持原文的语气和风格。",
        "原文中的口语转化为书面语，非专业的词汇转化为专业的词汇。",
        "没有语法错误和错别字。逻辑通常。简明不啰嗦。",
    ],
)

# 2. 定义基础评测函数
# -------------------
def is_length_roughly_equal(text: str, text_ref: str, ratio: float) -> JudgeResult:
    """检查两个文本长度是否大致相等"""
    len_diff = abs(len(text) - len(text_ref))
    if len_diff <= len(text_ref) * ratio:
        return JudgeResult(judgment=True, reason=f"长度差为{len_diff}，大致相等。")
    else:
        return JudgeResult(judgment=False, reason=f"长度差为{len_diff}，超出{ratio*100:.2f}%的范围。")

# 3. 定义同步评测指标（适合初步调试）
# -----------------------------------
# 这些指标都是同步的，适合本地/小模型/快速测试
TASK_REWRITE_METRICS = [
    CaseCriterion[str, str, JudgeResult](
        description="和原文长度大致相等。",
        metric=lambda c: is_length_roughly_equal(c.output, c.input, 0.2),
    ),
    CaseCriterion[str, str, JudgeResult](
        description="保持原文的语义、逻辑、事实。",
        metric=lambda c: compare_judge(c.output, c.input, "判断两者的语义、逻辑、事实是否相同"),
    ),
    CaseCriterion[str, str, JudgeResult](
        description="保持原文的语气和风格。",
        metric=lambda c: compare_judge(c.output, c.input, "判断两者的语气和风格是否相同"),
    ),
    CaseCriterion[str, str, JudgeResult](
        description="原文中的口语转化为书面语，非专业的词汇转化为专业的词汇。",
        metric=lambda c: compare_judge(
            c.output, c.input, "判断后者中的口语和非专业词汇是否在前者中转化为书面语和专业词汇"
        ),
    ),
    DatumCriterion[str, JudgeResult](
        description="没有语法错误和错别字。逻辑通常。简明不啰嗦。",
        metric=lambda x: judge(x, "没有语法错误和错别字。逻辑通常。简明不啰嗦。"),
    ),
]

# 4. 定义异步评测指标（适合大模型/云端/并发加速）
# ---------------------------------------------
# 这些指标用async/await，适合大模型API并发评测
async def acompare_judge_semantic(c):
    return await acompare_judge(c.output, c.input, "判断两者的语义、逻辑、事实是否相同")

async def acompare_judge_style(c):
    return await acompare_judge(c.output, c.input, "判断两者的语气和风格是否相同")

async def acompare_judge_formal(c):
    return await acompare_judge(
        c.output, c.input, "判断后者中的口语和非专业词汇是否在前者中转化为书面语和专业词汇"
    )

async def ajudge_grammar(x):
    return await ajudge(x, "没有语法错误和错别字。逻辑通常。简明不啰嗦。")

async def acompare_judge_gt(c):
    if c.gt is not None:
        return await acompare_judge(c.output, c.gt)
    else:
        return JudgeResult(judgment=None, reason="无GT数据")

TASK_REWRITE_METRICS_ASYNC = [
    CaseCriterion[str, str, JudgeResult](
        description="和原文长度大致相等。",
        metric=lambda c: is_length_roughly_equal(c.output, c.input, 0.2),
    ),
    CaseCriterion[str, str, JudgeResult](
        description="保持原文的语义、逻辑、事实。",
        metric=acompare_judge_semantic,
    ),
    CaseCriterion[str, str, JudgeResult](
        description="保持原文的语气和风格。",
        metric=acompare_judge_style,
    ),
    CaseCriterion[str, str, JudgeResult](
        description="原文中的口语转化为书面语，非专业的词汇转化为专业的词汇。",
        metric=acompare_judge_formal,
    ),
    DatumCriterion[str, JudgeResult](
        description="没有语法错误和错别字。逻辑通常。简明不啰嗦。",
        metric=ajudge_grammar,
    ),
]

# 5. 定义评测案例（支持正例/反例/注释）
# -----------------------------------
# 支持gt（标准答案）和comment（说明）
REWRITE_CASES = [
    TaskCaseGT(
        input="我对这个问题很感兴苏，希望能找到解决方案。",
        output="我对这个问题很感兴趣，希望能够找到解决方案。",
        gt="我对这个问题很感兴趣，希望能找到解决方案。",
        comment="修正错别字：'感兴苏'改为'感兴趣'",
    ),
    TaskCaseGT(
        input="昨天我去了商场买东西，感到很开心买了很多。",
        output="昨天我去商场购物，买了很多东西，感到很开心。",
        # gt="昨天我去商场买东西，买了很多，感到很开心。",
        comment="调整语序，使表达更加流畅自然",
    ),
    TaskCaseGT(
        input="这个方案看起来还不错，咱们就这么干吧！",
        output="该方案具有可行性，建议采纳并实施。",
        gt="该方案较为可行，建议采纳实施。",
        comment="口语转化为书面语，提高表达的专业性",
    ),
    TaskCaseGT(
        input="公司的钱变多了，这个季度赚了不少。",
        output="公司收益显著增长，本季度利润表现良好。",
        gt="公司的收益增长显著，本季度利润可观。",
        comment="非专业词汇转化为专业财务术语",
    ),
    TaskCaseGT(
        input="这个系统能让活干得贼快！",
        output="该系统能够显著提升工作效率。",
        gt="该系统能显著提高工作效率。",
        comment="口语化表达转化为书面语，提高专业性",
    ),
]
REWRITE_CASES_BAD = [
    TaskCaseGT(
        input="我对这个问题很感兴苏，希望能找到解决方案。",
        output="我对这个问题超级感兴去，真心希望能找到个好的解决方案啦！",
        gt="我对这个问题很感兴趣，希望能找到解决方案。",
        comment="过度口语化，使用了不恰当的语气词和感叹号，还有错别字'感兴去'",
    ),
    TaskCaseGT(
        input="昨天我去了商场买东西，感到很开心买了很多。",
        output="我们应该去动物园玩，因为昨天买了很多东西。",
        gt="昨天我去商场买东西，买了很多，感到很开心。",
        comment="完全改变了原文的语义和主题，逻辑混乱",
    ),
    TaskCaseGT(
        input="这个方案看起来还不错，咱们就这么干吧！",
        output="这系统能让活干得贼快！能大幅提升工作效驴。",
        gt="该方案较为可行，建议采纳实施。",
        comment="改变了原文的主题，从方案讨论变成了系统效率，逻辑混乱，还有错别字'效驴'",
    ),
    TaskCaseGT(
        input="这个系统能让活干得贼快！",
        output="该系统能够大幅提升工作效能，实现效率的质的飞跃，让工作变得更快。",
        gt="该系统能显著提高工作效率。",
        comment="过度修饰，使用了不必要的复杂表达，重复冗余",
    ),
    TaskCaseGT(
        input="这个项目做起来有点困难，但是值得一做。",
        output="该项目实施难度较大，但具有重要的战略意义和深远影响，所以值得一做。",
        gt="该项目实施难度较大，但值得进行。",
        comment="过度修饰，添加了原文没有的信息，逻辑混乱",
    ),
]

# 6. 定义gt评测标准（可选）
# ------------------------
gt_criterion = CaseCriterion[str, str, JudgeResult](
    description="判断两者是否相同",
    metric=lambda c: compare_judge(c.output, c.gt) if c.gt is not None else JudgeResult(judgment=None, reason="无GT数据"),
)
gt_criterion_async = CaseCriterion[str, str, JudgeResult](
    description="判断两者是否相同",
    metric=acompare_judge_gt,
)

# 7. 评测主流程（同步/异步自动切换）
# --------------------------------
def demo_rewrite_eval():
    """
    评测主流程：
    - 选择案例（正例/反例）
    - 选择同步/异步评测指标
    - 自动调用evaluate_dataset批量评测
    - 自动生成美观的HTML评估报告
    """
    use_bad_cases = True  # True用bad案例，False用正例
    if use_bad_cases:
        cases = REWRITE_CASES_BAD
    else:
        cases = REWRITE_CASES

    use_async = True  # True用异步指标，False用同步指标
    if use_async:
        metrics = TASK_REWRITE_METRICS_ASYNC
        gt_metric = gt_criterion_async
    else:
        metrics = TASK_REWRITE_METRICS
        gt_metric = gt_criterion

    import time

    start_time = time.time()
    if use_async:
        import asyncio
        eval_results, case_info, gt_results, stats_row = asyncio.run(aevaluate_dataset(cases, metrics, gt_metric))
    else:
        eval_results, case_info, gt_results, stats_row = evaluate_dataset(cases, metrics, gt_metric)
    end_time = time.time()
    print(f"评估样例数量: {len(cases)}，评估指标数量: {len(metrics)}，评估耗时: {end_time - start_time:.2f}秒")

    results = evaluation_results_to_df(case_info, metrics, eval_results, gt_results, stats_row, gt_metric)

    # 8. 自定义单元格样式和内容格式化
    # -----------------------------
    # 你可以根据自己的业务需求自定义cell_styler和cell_formatter
    def eval_cell_styler(val):
        """为评估结果设置单元格样式"""
        if isinstance(val, bool):
            return CellStyle.SUCCESS if val else CellStyle.ERROR
        elif isinstance(val, JudgeResult):
            judgement = val.judgment
            if judgement is True:
                return CellStyle.SUCCESS
            elif judgement is False:
                return CellStyle.ERROR
            elif judgement is None:
                return CellStyle.WARNING
        elif isinstance(val, (int, float)):
            return CellStyle.INFO
        return CellStyle.NEUTRAL

    # 9. 生成HTML评估报告（自动检测样式/自定义主题）
    # ----------------------------------------
    df_to_html(
        results,
        f"eval_results_{'bad' if use_bad_cases else 'good'}.html",
        title="文本润色任务评估结果",
        summary_info={
            "总案例数": str(len(results) - 1),  # 减去统计行
            "评估指标数": str(len(metrics)),
            "数据类型": "JudgeResult, 布尔值, 统计信息"
        },
        styling={"theme": "green"},  # 使用绿色主题，适合评估结果
        cell_styler=eval_cell_styler,
        cell_formatter=nl_repr,
        show_text_length=50,
    )


if __name__ == "__main__":
    demo_rewrite_eval()
