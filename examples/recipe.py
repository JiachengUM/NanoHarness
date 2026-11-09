"""
菜谱生成任务演示

这个示例展示了如何使用NanoAI框架来创建和执行AI任务。
我们将创建一个菜谱生成系统，演示从简单到复杂的任务设计。

主要学习点：
1. 基本任务执行
2. 输入验证
3. 结构化输出
4. 批量任务执行
5. 结果可视化
"""

from pydantic import BaseModel, Field

from nanoai.task import Task, execute, execute_batch, aexecute_batch, LMWorker, judge, JudgeResult
from nanoai.task.engine import batch_results_to_df
from nanoai.utils.text_utils import df_to_html


# 定义任务的基本描述
task_brief = "根据用户的输入生成菜谱。"


def demo_basic():
    """
    演示1：基本任务执行

    这是最简单的用法，直接调用execute函数执行任务。
    只需要提供输入和任务描述，就能得到AI的回复。
    """
    print("\n=== 演示1：基本任务执行 ===")
    print("这是最简单的用法，直接调用execute函数执行任务")

    # 用户输入：想要生成菜谱的菜品名称
    input = "番茄炒蛋"

    # 执行任务：将输入和任务描述传给AI，得到菜谱
    res = execute(input, task_brief)

    print(f"输入: {input}")
    print(f"结果: {res}")


def demo_check_input():
    """
    演示2：输入验证

    在实际应用中，我们需要验证用户输入是否合法。
    这里展示了如何创建自定义的输入验证器。
    """
    print("\n=== 演示2：输入验证 ===")
    print("在实际应用中，我们需要验证用户输入是否合法")

    def input_validator(input: str) -> JudgeResult:
        """
        自定义输入验证器

        这个函数检查用户输入是否满足要求：
        1. 长度不超过20个字符
        2. 必须是食物或菜品的描述
        """
        # 检查输入长度
        if len(input) > 20:
            return JudgeResult(judgment=False, reason="输入长度超过20个字符。")

        # 使用内置的judge函数检查是否为食物描述
        return judge(input, "是食物或者菜的描述。")

    # 创建一个无效的输入来测试验证器
    invalid_input = "硫酸土豆"

    # 创建Worker：这是更高级的任务执行方式，可以自定义输入验证
    worker = LMWorker(
        Task(
            brief=task_brief,  # 任务描述
            input_criteria=[  # 输入标准（用于文档）
                "输入必须是食物或菜品的名称",
                "输入长度不超过20个字符",
            ],
        ),
        str,  # 输出类型：字符串
        input_criterion=input_validator,  # 自定义输入验证器
    )

    # 尝试执行任务，应该会抛出异常
    try:
        result = worker.execute(invalid_input)
        print(result)
    except Exception as e:
        print(f"验证失败: {e}")


# 定义数据结构：用于结构化输出
class Step(BaseModel):
    """
    菜谱步骤的基础模型

    每个步骤包含一个操作说明。
    """

    description: str = Field(description="菜谱每个步骤的操作说明。")


class StepMore(Step):
    """
    扩展的菜谱步骤模型

    在基础步骤上增加了时间估计。
    """

    time_estimate: str = Field(title="时间估计", description="每个步骤的完成时间估计。")


class Recipe(BaseModel):
    """
    完整的菜谱模型

    包含简介、材料列表和详细步骤。
    """

    intro: str = Field(description="关于这个菜的简介。")
    ingredients: list[str] = Field(title="材料", description="菜谱的食材、调料等。需要事先准备好的。")
    steps: list[StepMore] = Field(title="烹饪步骤", description="菜谱的步骤。")


def demo_compare_tasks():
    """
    演示3：任务复杂度对比

    这个演示展示了如何设计不同复杂度的任务：
    1. 简单任务：只返回文本
    2. 中等任务：返回结构化列表
    3. 复杂任务：返回完整的结构化对象

    同时演示了批量执行多个任务，并可视化结果。
    """
    print("\n=== 演示3：任务复杂度对比 ===")
    print("展示如何设计不同复杂度的任务，并批量执行")

    # 定义输出标准：告诉AI应该如何输出结果
    output_criteria = [
        "输出应该是菜谱的步骤，每个步骤应该包含具体的操作说明、食材用量信息、烹饪时间估计。",
    ]

    # 定义三个不同复杂度的任务
    tasks: list[tuple[str | Task, type]] = [
        # 任务1：最简单的任务，只返回字符串
        (task_brief, str),
        # 任务2：中等复杂度，返回结构化列表
        (Task(brief=task_brief, output_criteria=output_criteria), list[Step]),
        # 任务3：最复杂，返回完整的结构化对象
        (
            Task(
                brief=task_brief,
                output_criteria=output_criteria,
                detail="""
            本任务要求根据用户输入的食物或菜品名称，生成详细的菜谱步骤。
            注意事项：
            - 步骤应该具体可操作，避免模糊描述
            - 应该考虑食材的合理搭配和烹饪顺序
            - 对于复杂菜品，可以适当增加步骤数量
            - 应该包含基本的烹饪技巧说明
            """,
            ),
            Recipe,
        ),
    ]

    # 定义测试用例：多个菜品名称
    queries = ["番茄炒蛋", "宫保鸡丁", "麻婆豆腐"]

    print(f"将使用 {len(queries)} 个测试用例执行 {len(tasks)} 个任务")
    print("测试用例:", queries)
    print("任务类型: 简单文本 -> 结构化列表 -> 完整对象")

    # 批量执行所有任务：每个输入都会执行所有任务
    print("\n开始批量执行...")
    async_mode = True
    if async_mode:
        import asyncio
        all_results = asyncio.run(aexecute_batch(queries, tasks))
    else:
        all_results = execute_batch(queries, tasks)

    # 将结果转换为DataFrame，便于查看和比较
    print("整理结果...")
    df = batch_results_to_df(queries, [task for task, _ in tasks], all_results)

    # 生成HTML报告，便于在浏览器中查看
    print("生成HTML报告...")
    # 第一列自适应，剩余列等宽
    n_cols = len(df.columns)
    assert n_cols > 1, "至少需要两个列"
    remaining_width = f"{100 // (n_cols - 1)}%"
    column_widths: dict[str | int, str] = {
        0: "minmax(100px, 25%)",  # 第一列自适应，最小100px，最大25%
        **{i: remaining_width for i in range(1, n_cols)}  # 剩余列等宽
    }
    
    df_to_html(
        df,
        "recipe_results.html",
        title="🍳 菜谱任务结果对比",
        summary_info={"总任务数": str(len(df.columns) - 1), "测试用例数": str(len(df))},
        column_widths=column_widths,
    )

    print("完成！请打开 recipe_results.html 查看详细结果")


if __name__ == "__main__":
    """
    主程序入口

    按顺序执行三个演示：
    1. 基本任务执行
    2. 输入验证
    3. 任务复杂度对比
    """
    print("🍳 菜谱生成任务演示")
    print("=" * 50)

    # 演示1：基本用法
    demo_basic()

    # 演示2：输入验证
    demo_check_input()

    # 演示3：复杂度对比
    demo_compare_tasks()

    print("\n" + "=" * 50)
    print("演示完成！")
    print("生成的 recipe_results.html 文件包含了所有任务的详细对比结果。")
