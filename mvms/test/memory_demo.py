"""
这个demo主要是为了展示记忆的更新和保存功能，以及记忆vs无记忆回答的巨大差异。但目前记忆更新慢，需要我这边加油。
"""
from openai import APITimeoutError

from nanoai.memory import MemoryManager
from nanoai.model.llm import llm
from nanoai.model.config import switch_model


def demo_llm_driven_memory_update():
    switch_model("doubao")
    """演示 LLM 驱动的记忆更新"""
    print("=== LLM 驱动记忆更新演示 ===")

    print()
    
    manager = MemoryManager(batch_size=2)
    
    print("1. 初始记忆状态:")
    print(manager.core_memory.compile_to_prompt())
    print()
    
    # 模拟多轮用户输入（助手回复由真实LLM生成）
    user_inputs = [
        "你好，我想学习Python",
        "我听说Python在数据科学方面很强大，我想以后做数据分析工作",
        "我更喜欢通过实际项目来学习，而不是只看理论",
        "我已经学会了Python的基础语法，现在想学习pandas",
        "我希望能做一些实际的数据分析项目来练习",
        "我想学习数据可视化，有什么推荐的工具吗？",
        "我对机器学习也很感兴趣，应该从哪里开始？",
        "我想做一个完整的项目来练习，有什么建议？",
        "谢谢你的建议，我会按照这个计划来学习",
    ]
    
    print("2. 开始多轮对话:")
    print("=" * 50)
    
    for i, user_input in enumerate(user_inputs, 1):
        print(f"\n--- 第{i}轮对话 ---")
        print(f"用户: {user_input}")
        # 使用当前记忆编译为系统提示，驱动真实LLM生成回复
        sys_prompt = (
            "你是一个耐心、专业的学习助手，请结合下述'核心记忆'为用户提供简洁、具体、可执行的建议。\n\n"
            f"核心记忆:\n{manager.core_memory.compile_to_prompt()}\n"
        )
        try:
            # TODO: 这里有bug。并没有维护对话历史。因此每次实际上只能处理一条消息。
            # 目前llm API还不能处理sys_prompt会变化的情况。暂时先这样。晚些用ChatWorker替代llm。
            res = llm(user_input, sys_prompt, timeout=30)
            assistant_response = res.output
        except APITimeoutError:
            # LLM调用超时，使用占位回答
            assistant_response = "我的脑子好像短路了。请稍后再问我。"
        except Exception as e:
            # LLM调用失败，使用占位回答
            assistant_response = "我会根据你的情况给出学习建议。"

        print(f"助手: {assistant_response}")
        
        manager.add_conversation(user_input, assistant_response)
        
        # 显示当前记忆状态
        print(f"\n第{i}轮对话后的记忆状态:")
        print(manager.core_memory.compile_to_prompt())
        
        # 如果是批处理完成，显示分析完成信息
        if i % manager.batch_size == 0 or i == len(user_inputs):
            print(f"\n第{i//manager.batch_size + 1}次记忆分析完成:")
            print("-" * 30)
    
    print("3. 最终记忆状态:")
    print(manager.core_memory.compile_to_prompt())
    print()


def demo_save_memory_to_json():
    """演示将记忆保存到JSON文件"""
    print("\n=== 记忆保存到JSON演示 ===")
    
    # 创建一个记忆管理器并添加一些对话来建立记忆
    manager = MemoryManager(batch_size=2)
    
    # 模拟一些对话来建立记忆
    training_conversations = [
        "我想学习Python编程",
        "我对数据分析很感兴趣", 
        "我更喜欢通过项目来学习",
        "我想学习pandas"
    ]
    
    print("1. 建立记忆:")
    for user_input in training_conversations:
        # 由真实LLM生成助手回复
        sys_prompt = (
            "你是一个学习顾问，请基于用户长期偏好提供具体建议。"
            f"\n\n核心记忆:\n{manager.core_memory_compile()}\n"
        )
        try:
            res = llm(user_input, sys_prompt)
            assistant_response = res.output
        except Exception:
            assistant_response = "(LLM调用失败，占位回复)"
        manager.add_conversation(user_input, assistant_response)
    
    print("   记忆状态:")
    print(manager.core_memory_compile())
    print()
    
    # 保存记忆到JSON文件
    json_file_path = "test_memory.json"
    print(f"2. 保存记忆到: {json_file_path}")
    
    # 获取记忆的完整信息
    memory_data = {
        "core_memory": manager.core_memory.to_dict(),
        "statistics": manager.get_statistics(),
        "conversation_history": manager.conversation_history,
        "settings": {
            "batch_size": manager.batch_size,
            "enable_llm_analysis": manager.enable_llm_analysis,
            "enable_llm_formatting": manager.enable_llm_formatting
        }
    }
    
    # 保存到JSON文件
    import json
    with open(json_file_path, 'w', encoding='utf-8') as f:
        json.dump(memory_data, f, ensure_ascii=False, indent=2)
    
    print(f"   记忆已保存到: {json_file_path}")
    print(f"   文件大小: {len(json.dumps(memory_data, ensure_ascii=False))} 字符")
    print()
    
    # 读取并验证JSON文件
    print("3. 读取并验证JSON文件:")
    with open(json_file_path, 'r', encoding='utf-8') as f:
        loaded_memory_data = json.load(f)
    
    print("   读取成功！")
    print(f"   核心记忆块数量: {len(loaded_memory_data['core_memory']['blocks'])}")
    print(f"   对话历史数量: {len(loaded_memory_data['conversation_history'])}")
    print(f"   自动更新设置: {loaded_memory_data['settings']['auto_update_core_memory']}")
    print()
    
    # 显示JSON文件的结构
    print("4. JSON文件结构:")
    print("   - core_memory: 核心记忆内容")
    print("     - blocks: 记忆块字典")
    print("     - prompt_template: 提示模板")
    print("   - statistics: 统计信息")
    print("   - conversation_history: 对话历史")
    print("   - settings: 配置设置")
    print()
    
    print("5. 记忆内容预览:")
    for block_name, block_data in loaded_memory_data['core_memory']['blocks'].items():
        print(f"   {block_name}: {block_data['value'][:100]}{'...' if len(block_data['value']) > 100 else ''}")
    
    print(f"\n记忆保存演示完成！文件位置: {json_file_path}")


def demo_memory_vs_no_memory():
    """演示有记忆vs无记忆回答的巨大差异"""
    print("\n=== 记忆 vs 无记忆对比演示 ===")
    
    # 创建有记忆的管理器
    manager_with_memory = MemoryManager()
    manager_with_memory.auto_update_core_memory = True
    manager_with_memory.batch_size = 2
    
    # 创建无记忆的管理器
    manager_no_memory = MemoryManager()
    manager_no_memory.auto_update_core_memory = False
    manager_no_memory.batch_size = 10000  # 设置很大，避免触发记忆更新
    
    print("1. 建立用户记忆:")
    # 模拟一些对话来建立记忆
    conversations = [
        "我想学习Python编程",
        "我对数据分析很感兴趣", 
        "我更喜欢通过项目来学习",
        "我想学习pandas"
    ]
    
    for user_input in conversations:
        # 由真实LLM生成助手回复
        sys_prompt = (
            "你是一个学习顾问，请基于用户长期偏好提供具体建议。"
            f"\n\n核心记忆:\n{manager_with_memory.core_memory_compile()}\n"
        )
        try:
            res = llm(user_input, sys_prompt)
            assistant_response = res.output
        except Exception:
            assistant_response = "(LLM调用失败，占位回复)"
        manager_with_memory.add_conversation(user_input, assistant_response)
    
    print("   记忆建立完成！")
    print(f"   记忆内容: {manager_with_memory.core_memory_compile()}")
    print()
    
    # 测试问题
    test_question = "我应该从哪里开始学习？"
    print(f"2. 测试问题: {test_question}")
    print()
    
    # 有记忆的回答
    print("3. 有记忆的回答:")
    try:
        memory_context = manager_with_memory.core_memory_compile()
        res = llm(test_question, f"你是学习助手，请结合下述核心记忆给出个性化、具体建议。\n\n{memory_context}")
        print(f"   回答: {res.output}")
    except Exception:
        print("   回答: (LLM调用失败)")
    print()
    
    # 无记忆的回答
    print("4. 无记忆的回答:")
    try:
        res = llm(test_question, "你是学习助手，请给出通用的、清晰的入门建议。")
        print(f"   回答: {res.output}")
    except Exception:
        print("   回答: (LLM调用失败)")
    print()
    
    # 后续问题演示
    follow_up_question = "我已经学会了基础语法，接下来学什么？"
    print(f"5. 后续问题: {follow_up_question}")
    print()
    
    print("   有记忆的回答:")
    try:
        res = llm(follow_up_question, f"你是学习助手，请结合下述核心记忆给出个性化、具体建议。\n\n{manager_with_memory.core_memory_compile()}")
        print(f"   回答: {res.output}")
    except Exception:
        print("   回答: (LLM调用失败)")
    print()
    
    print("   无记忆的回答:")
    try:
        res = llm(follow_up_question, "你是学习助手，请给出通用的、清晰的下一步建议。")
        print(f"   回答: {res.output}")
    except Exception:
        print("   回答: (LLM调用失败)")
    print()
    
    print("6. 对比总结:")
    print("   有记忆: 个性化、连贯、针对性强的建议")
    print("   无记忆: 通用、缺乏个性化、每次对话独立")
    print("   记忆的价值: 提供更好的用户体验和对话连贯性")


def main():
    """主演示函数"""
    print("LLM 驱动记忆更新演示")
    print("=" * 60)
    
    try:
        demo_llm_driven_memory_update()
        #demo_save_memory_to_json()
        #demo_memory_vs_no_memory()
        
        print("\nLLM 驱动记忆更新演示完成！")
        
        
    except Exception as e:
        print(f"演示过程中出现错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
