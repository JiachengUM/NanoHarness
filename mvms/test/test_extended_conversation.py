#!/usr/bin/env python3
"""扩展对话测试：验证MemoryChatWorker在复杂场景下的记忆能力"""

import time
import asyncio
import argparse
import datetime
from typing import List
from nanoai.chat.define import ChatAgentProfile, ChatTask
from nanoai.chat.worker import ChatWorker
from nanoai.memory.memory_chat_worker import MemoryChatWorker
from nanoai.task.eval import TaskCaseGT, CaseCriterion, JudgeResult
from nanoai.task.engine import execute
from nanoai.task.define import Task


class MemoryOnlyChatWorker(MemoryChatWorker):
    """禁用messages的MemoryChatWorker，只使用memory blocks作为上下文"""
    
    def execute(self, input: str, /) -> str:
        """重写execute方法，禁用messages历史，使用memory blocks作为上下文"""
        original_input = input
        
        # 获取记忆上下文
        memory_summary = self.core_memory.compile_to_prompt()
        
        # 构建包含记忆上下文的输入
        if memory_summary.strip():
            enhanced_input = f"{input}\n\n记忆上下文：{memory_summary}"
        else:
            enhanced_input = input
        
        # 注意：不调用 _think 方法，避免存储到 messages
        # 直接使用增强后的输入调用 LLM
        
        try:
            from nanoai.model.llm import llm
            self._result = llm(
                enhanced_input,  # 使用增强后的输入（包含记忆上下文）
                self._sys_prompt,  # 系统提示词保持不变
                model=self.model, 
                client=self.client, 
                **self.llm_params
            )
        except Exception as e:
            self._status = "ERROR"
            raise e
        
        # 添加对话到记忆
        self.memory_manager.add_conversation(original_input, self._result.output)
        return self._result.output


def setup_workers():
    """设置两个worker"""
    task = ChatTask(
        brief="为用户提供个性化的服务，记住用户的基础信息。",
        agent_profile=ChatAgentProfile(name="个性化AI助手", role="个性化AI助手")
    )
    
    # MemoryChatWorker
    print("设置MemoryChatWorker...")
    memory_worker = MemoryOnlyChatWorker(task, batch_size=1, enable_llm_analysis=True)
    
    # 普通ChatWorker
    print("设置普通ChatWorker...")
    regular_worker = ChatWorker(task)
    
    # 对话学习
    conversations = [
        ("以后跟你互动要记好我的基础信息哦，别搞混啦～", "放心！你先说说基本的身份信息吧，比如名字、常用昵称这些？"),
        ("我大名叫林晓冉，平时大家都叫我冉冉，今年 28 岁，是一家互联网公司的产品经理，已经工作 5 年了，老家在江苏苏州，现在定居在上海浦东。", "好的，我记住了！"),
        ("那家里人相关的信息方便说说吗？比如是否有家人一起住？", "那家里人相关的信息方便说说吗？比如是否有家人一起住？"),
        ("我和老公结婚 2 年了，他叫周明宇，是做建筑设计的，我们还没孩子，养了一只叫 \"糯米\" 的银渐层猫，今年 1 岁半；我爸妈还在苏州，爸爸是中学老师，妈妈退休前是护士，周末偶尔会视频通话。", "明白了！"),
        ("生活里有没有固定的习惯或重要信息呀？比如生日、过敏情况？", "生活里有没有固定的习惯或重要信息呀？比如生日、过敏情况？"),
        ("我的生日是 3 月 12 日，双鱼座；对芒果和海鲜过敏，吃了会皮肤发痒，所以平时聚餐都避开这些；作息比较规律，每天早上 7 点起床，晚上 11 点前睡觉，不熬夜；通勤靠地铁，公司在静安区，每天上班要花 40 分钟左右。", "记住了！"),
        ("有没有其他需要记住的关键事实？比如学历、爱好相关的基础信息？", "有没有其他需要记住的关键事实？比如学历、爱好相关的基础信息？"),
        ("我本科读的是南京大学的市场营销专业，后来在职考了复旦大学的 MBA，去年刚毕业；平时喜欢做手工，尤其是拼乐高，已经拼完 3 个大型套装了，还喜欢周末去上海的公园散步，常去的是世纪公园，因为离我家近。", "了解了！"),
        ("还有没提到的重要基础信息吗？比如联系方式偏好、特殊需求？", "还有没提到的重要基础信息吗？比如联系方式偏好、特殊需求？"),
        ("我不喜欢别人叫我全名，认准 \"冉冉\" 这个昵称就好；平时联系优先发微信，手机号是 1381782XXXX（末尾四位可以记成 5678，方便回忆）；因为工作需要，每周三下午要开部门例会，这个时间回复消息会慢一点；另外，我有轻微近视，平时戴框架眼镜，只有开会或见客户时戴隐形眼镜。", "好的，我记住了！"),
    ]
    
    for i, (user_input, _) in enumerate(conversations, 1):
        print(f"第{i}轮对话: {user_input[:50]}...")
        memory_worker.memory_manager.add_conversation(user_input, "助手回复")
        regular_worker.execute(user_input)
    
    return memory_worker, regular_worker


def create_test_cases() -> List[TaskCaseGT]:
    """创建测试用例"""
    test_cases = []
    
    # 身份与职业信息：8 题
    identity_questions = [
        ("我大名叫什么？", "林晓冉"),
        ("我平时常用的昵称是什么？", "冉冉"),
        ("我今年多大年纪？", "28 岁"),
        ("我的职业是什么？", "互联网公司产品经理"),
        ("我已经工作多少年了？", "5 年"),
        ("我现在定居在哪个城市的哪个区域？", "上海浦东"),
        ("我的老家在哪里？", "江苏苏州"),
        ("我公司在上海的哪个区域？", "静安区"),
    ]
    
    # 家庭相关信息：10 题
    family_questions = [
        ("我老公叫什么名字？", "周明宇"),
        ("我老公的职业是什么？", "建筑设计"),
        ("我和老公结婚多久了？", "2 年"),
        ("我家养的宠物叫什么名字？", "糯米"),
        ("我家宠物是什么品种的猫？", "银渐层"),
        ("我家宠物今年多大了？", "1 岁半"),
        ("我爸妈现在住在哪个城市？", "江苏苏州"),
        ("我爸爸的职业是什么？", "中学老师"),
        ("我妈妈退休前是做什么的？", "护士"),
        ("我和爸妈平时怎么联系？多久联系一次？", "周末偶尔视频通话"),
    ]
    
    # 个人健康与作息信息：8 题
    health_questions = [
        ("我的生日是哪一天？", "3 月 12 日"),
        ("我是什么星座？", "双鱼座"),
        ("我对哪些食物过敏？", "芒果、海鲜"),
        ("我过敏后会有什么症状？", "皮肤发痒"),
        ("我每天早上几点起床？", "7 点"),
        ("我晚上通常几点前睡觉？", "11 点前"),
        ("我平时是否熬夜？", "不熬夜"),
        ("我平时戴眼镜的习惯是什么？", "平时戴框架眼镜，开会或见客户时戴隐形眼镜"),
    ]
    
    # 通勤与工作习惯信息：7 题
    work_questions = [
        ("我每天怎么通勤去公司？", "靠地铁"),
        ("我每天上班需要花多长时间？", "40 分钟左右"),
        ("我每周哪一天下午有固定会议？", "每周三下午"),
        ("开会时我的消息回复会有什么特点？", "回复会慢一点"),
        ("我不喜欢别人怎么称呼我？", "不喜欢别人叫我全名（林晓冉）"),
        ("我平时优先用什么方式联系？", "微信"),
        ("我的手机号末尾四位可以记成什么？", "5678"),
    ]
    
    # 学历与爱好基础信息：9 题
    education_questions = [
        ("我本科就读的大学和专业是什么？", "南京大学，市场营销专业"),
        ("我在职考的 MBA 是哪所大学的？", "复旦大学"),
        ("我 MBA 什么时候毕业的？", "去年"),
        ("我平时喜欢的手工爱好是什么？", "拼乐高"),
        ("我已经拼完多少个乐高大型套装了？", "3 个"),
        ("我周末喜欢去上海的哪个公园散步？", "世纪公园"),
        ("我喜欢去世纪公园的原因是什么？", "离我家近"),
        ("我本科大学在哪个城市？", "南京（南京大学位于南京）"),
        ("我读 MBA 的大学在哪个城市？", "上海（复旦大学位于上海）"),
    ]
    
    # 综合事实验证：8 题
    comprehensive_questions = [
        ("我现在定居的城市和老家分别是哪里？", "定居上海浦东，老家江苏苏州"),
        ("我老公的职业和我家宠物的名字分别是什么？", "老公是建筑设计，宠物叫糯米"),
        ("我避免吃的食物和喜欢的周末活动分别是什么？", "避免芒果、海鲜，喜欢去世纪公园散步"),
        ("我上班的区域、通勤方式和时间分别是什么？", "公司在静安区，地铁通勤，40 分钟左右"),
        ("我爸妈的职业和现居地分别是什么？", "爸爸是中学老师，妈妈退休前是护士，现居江苏苏州"),
        ("我的学历经历（本科 + MBA）分别是什么？", "本科南京大学市场营销，MBA 复旦大学（去年毕业）"),
        ("我每天的作息时间（起床 + 睡觉）和戴眼镜习惯分别是什么？", "7 点起床、11 点前睡觉，平时框架、开会 / 见客户隐形"),
        ("我常用的昵称、年龄和职业分别是什么？", "昵称冉冉，28 岁，互联网公司产品经理"),
    ]
    
    all_questions = (
        identity_questions + family_questions + health_questions + 
        work_questions + education_questions + comprehensive_questions
    )
    
    for i, (question, expected_answer) in enumerate(all_questions, 1):
        if i <= 8:
            category = "身份与职业信息"
        elif i <= 18:
            category = "家庭相关信息"
        elif i <= 26:
            category = "个人健康与作息信息"
        elif i <= 33:
            category = "通勤与工作习惯信息"
        elif i <= 42:
            category = "学历与爱好基础信息"
        else:
            category = "综合事实验证"
        
        case = TaskCaseGT(
            input=question,
            output="",
            gt=expected_answer,
            comment=f"测试记忆准确性 - {category}"
        )
        test_cases.append(case)
    
    return test_cases


async def create_async_evaluator(worker, worker_type: str, batch_size: int = 10):
    """创建异步评估器"""
    
    async def evaluate_batch(cases: List[TaskCaseGT]) -> List[JudgeResult]:
        """批量评估"""
        print(f"开始异步批量评估，总用例数: {len(cases)}，批次大小: {batch_size}")
        results = []
        
        for i in range(0, len(cases), batch_size):
            batch = cases[i:i + batch_size]
            batch_num = i//batch_size + 1
            total_batches = (len(cases) + batch_size - 1)//batch_size
            print(f"\n处理批次 {batch_num}/{total_batches} (用例 {i+1}-{min(i+batch_size, len(cases))})")
            
            # 创建异步任务
            batch_tasks = []
            for case in batch:
                task = evaluate_single_case(worker, case)
                batch_tasks.append(task)
            
            # 并发执行批次任务
            try:
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                print(f"批次 {batch_num} 并发执行完成")
            except Exception as e:
                print(f"批次 {batch_num} 执行出错: {e}")
                batch_results = []
                for case in batch:
                    try:
                        result = await evaluate_single_case(worker, case)
                        batch_results.append(result)
                    except Exception as case_error:
                        print(f"用例执行出错: {case_error}")
                        batch_results.append(JudgeResult(judgment=False, reason=f"执行出错: {str(case_error)}"))
            
            # 处理结果
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    print(f"批次 {batch_num} 第 {j+1} 个用例评估出错: {result}")
                    results.append(JudgeResult(judgment=False, reason=f"评估出错: {str(result)}"))
                else:
                    results.append(result)
            
            completed = min(i + batch_size, len(cases))
            print(f"已完成: {completed}/{len(cases)} ({completed/len(cases)*100:.1f}%)")
        
        print(f"\n异步批量评估完成，总结果数: {len(results)}")
        return results
    
    async def evaluate_single_case(worker, case: TaskCaseGT) -> JudgeResult:
        """评估单个测试用例"""
        try:
            question = case.input
            expected_answer = case.gt
            
            test_input = f"请根据记忆回答：{question}"
            response = worker.execute(test_input)
            case.output = response
            
            # 使用LLM评估答案准确性
            eval_task = Task(
                brief="""你是一个记忆准确性评估专家。评估AI助手的回答是否准确。

评估标准：
1. 答案必须包含标准答案中的关键信息
2. 允许表达方式不同，但语义必须一致
3. 忽略格式差异（如空格、标点符号等）
4. 考虑同义词和近义词（如"中学老师"和"中学教师"）
5. 如果AI回答包含了标准答案的所有关键信息，即使有额外内容，也应判定为正确
6. 重点关注核心事实是否准确，不要因为表达方式或额外信息而误判

请仔细对比AI回答和标准答案，判断是否包含相同的核心信息。""",
                output_criteria=[
                    "以JSON格式返回评估结果",
                    "包含judgment字段（true/false）",
                    "包含reason字段（评估理由）"
                ]
            )
            
            eval_input = f"""问题：{question}
标准答案：{expected_answer}
AI回答：{response}

请评估AI的回答是否准确。重点关注AI回答是否包含了标准答案中的关键信息。"""
            
            eval_result = execute(eval_input, eval_task, JudgeResult)
            return eval_result
            
        except Exception as e:
            print(f"单个用例评估出错: {e}")
            return JudgeResult(judgment=False, reason=f"评估出错: {str(e)}")
    
    return CaseCriterion(
        description=f"异步记忆准确性评估（{worker_type}）",
        metric=evaluate_batch
    )


async def test_memory_worker_only(batch_size: int = 10):
    """只测试MemoryChatWorker的准确率"""
    start_time = time.time()
    
    print("MemoryChatWorker 记忆准确性测试")
    print(f"使用异步处理加速 (批次大小: {batch_size})")
    print("=" * 60)
    
    # 设置MemoryChatWorker
    print("设置MemoryChatWorker...")
    memory_worker = MemoryOnlyChatWorker(
        ChatTask(
            brief="为用户提供个性化的服务，记住用户的基础信息。",
            agent_profile=ChatAgentProfile(name="个性化AI助手", role="个性化AI助手")
        ), 
        batch_size=1, 
        enable_llm_analysis=True
    )
    
    # 对话学习
    conversations = [
        ("以后跟你互动要记好我的基础信息哦，别搞混啦～", "放心！你先说说基本的身份信息吧，比如名字、常用昵称这些？"),
        ("我大名叫林晓冉，平时大家都叫我冉冉，今年 28 岁，是一家互联网公司的产品经理，已经工作 5 年了，老家在江苏苏州，现在定居在上海浦东。", "好的，我记住了！"),
        ("那家里人相关的信息方便说说吗？比如是否有家人一起住？", "那家里人相关的信息方便说说吗？比如是否有家人一起住？"),
        ("我和老公结婚 2 年了，他叫周明宇，是做建筑设计的，我们还没孩子，养了一只叫 \"糯米\" 的银渐层猫，今年 1 岁半；我爸妈还在苏州，爸爸是中学老师，妈妈退休前是护士，周末偶尔会视频通话。", "明白了！"),
        ("生活里有没有固定的习惯或重要信息呀？比如生日、过敏情况？", "生活里有没有固定的习惯或重要信息呀？比如生日、过敏情况？"),
        ("我的生日是 3 月 12 日，双鱼座；对芒果和海鲜过敏，吃了会皮肤发痒，所以平时聚餐都避开这些；作息比较规律，每天早上 7 点起床，晚上 11 点前睡觉，不熬夜；通勤靠地铁，公司在静安区，每天上班要花 40 分钟左右。", "记住了！"),
        ("有没有其他需要记住的关键事实？比如学历、爱好相关的基础信息？", "有没有其他需要记住的关键事实？比如学历、爱好相关的基础信息？"),
        ("我本科读的是南京大学的市场营销专业，后来在职考了复旦大学的 MBA，去年刚毕业；平时喜欢做手工，尤其是拼乐高，已经拼完 3 个大型套装了，还喜欢周末去上海的公园散步，常去的是世纪公园，因为离我家近。", "了解了！"),
        ("还有没提到的重要基础信息吗？比如联系方式偏好、特殊需求？", "还有没提到的重要基础信息吗？比如联系方式偏好、特殊需求？"),
        ("我不喜欢别人叫我全名，认准 \"冉冉\" 这个昵称就好；平时联系优先发微信，手机号是 1381782XXXX（末尾四位可以记成 5678，方便回忆）；因为工作需要，每周三下午要开部门例会，这个时间回复消息会慢一点；另外，我有轻微近视，平时戴框架眼镜，只有开会或见客户时戴隐形眼镜。", "好的，我记住了！"),
    ]
    
    for i, (user_input, _) in enumerate(conversations, 1):
        print(f"第{i}轮对话: {user_input[:50]}...")
        memory_worker.memory_manager.add_conversation(user_input, "助手回复")
    
    # 创建测试用例
    test_cases = create_test_cases()
    print(f"\n创建了 {len(test_cases)} 个测试用例")
    
    # 测试MemoryChatWorker
    print("\n开始测试MemoryChatWorker...")
    memory_start_time = time.time()
    
    memory_evaluator = await create_async_evaluator(memory_worker, "MemoryChatWorker", batch_size)
    memory_results = await memory_evaluator.metric(test_cases)
    
    memory_time = time.time() - memory_start_time
    print(f"MemoryChatWorker测试完成，耗时: {memory_time:.2f}秒")
    
    # 生成报告
    total_time = time.time() - start_time
    print(f"\nMemoryChatWorker 测试报告 (总耗时: {total_time:.2f}秒)")
    print("=" * 60)
    
    # 计算准确率
    memory_correct = sum(1 for result in memory_results if isinstance(result, JudgeResult) and result.judgment)
    memory_accuracy = memory_correct / len(memory_results) if memory_results else 0
    
    print(f"MemoryChatWorker准确率: {memory_accuracy:.2%} ({memory_correct}/{len(memory_results)})")
    
    # 错误分析
    memory_errors = [(i+1, r) for i, r in enumerate(memory_results) if isinstance(r, JudgeResult) and not r.judgment]
    if memory_errors:
        print(f"\n错误案例 ({len(memory_errors)}个):")
        for case_num, result in memory_errors:
            test_case = test_cases[case_num-1]
            print(f"\n  错误案例 {case_num}:")
            print(f"    问题: {test_case.input}")
            print(f"    标准答案: {test_case.gt}")
            print(f"    错误原因: {result.reason}")
    
    # 性能统计
    print(f"\n性能统计:")
    print(f"  测试时间: {memory_time:.2f}秒")
    print(f"  总时间: {total_time:.2f}秒")
    print(f"  平均每个测试用例: {memory_time/len(test_cases):.2f}秒")
    
    # 保存结果
    save_memory_only_results(test_cases, memory_results)
    
    return memory_accuracy


def save_memory_only_results(test_cases, memory_results, output_file="memory_worker_test_results.txt"):
    """保存MemoryChatWorker测试结果到文件"""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("MemoryChatWorker 记忆准确性测试结果\n")
        f.write("=" * 80 + "\n\n")
        
        f.write("测试用例总数: {len(test_cases)}\n")
        f.write("测试时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("详细结果:\n")
        f.write("-" * 40 + "\n")
        
        memory_correct = 0
        for i, result in enumerate(memory_results):
            test_case = test_cases[i]
            status = "✓" if isinstance(result, JudgeResult) and result.judgment else "✗"
            f.write(f"{i+1:2d}. [{status}] {test_case.input}\n")
            f.write(f"    标准答案: {test_case.gt}\n")
            f.write(f"    AI回答: {test_case.output}\n")
            if isinstance(result, JudgeResult):
                f.write(f"    评估结果: {result.judgment} - {result.reason}\n")
            f.write("\n")
            if isinstance(result, JudgeResult) and result.judgment:
                memory_correct += 1
        
        f.write(f"总体准确率: {memory_correct}/{len(memory_results)} ({memory_correct/len(memory_results)*100:.2f}%)\n\n")
        
        # 错误分析
        memory_errors = [(i+1, r) for i, r in enumerate(memory_results) if isinstance(r, JudgeResult) and not r.judgment]
        if memory_errors:
            f.write(f"错误案例分析 ({len(memory_errors)}个):\n")
            f.write("-" * 40 + "\n")
            for case_num, result in memory_errors:
                test_case = test_cases[case_num-1]
                f.write(f"  问题{case_num}: {test_case.input}\n")
                f.write(f"    标准答案: {test_case.gt}\n")
                f.write(f"    AI回答: {test_case.output}\n")
                f.write(f"    错误原因: {result.reason}\n\n")
    
    print(f"\n详细结果已保存到: {output_file}")


async def main():
    """主函数"""
    try:
        parser = argparse.ArgumentParser(description="MemoryChatWorker 记忆准确性测试")
        parser.add_argument("--batch-size", type=int, default=10, help="异步处理的批次大小（默认: 10）")
        
        args = parser.parse_args()
        batch_size = args.batch_size
        
        print("配置选项:")
        print(f"  异步处理: 启用")
        print(f"  批次大小: {batch_size}")
        print(f"  测试目标: MemoryChatWorker 记忆准确性")
        print()
        
        memory_accuracy = await test_memory_worker_only(batch_size=batch_size)
        
        print(f"\nMemoryChatWorker 记忆准确性测试完成！")
        print(f"最终准确率: {memory_accuracy:.2%}")
        
    except KeyboardInterrupt:
        print("\n测试被用户中断")
    except Exception as e:
        print(f"\n测试出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
