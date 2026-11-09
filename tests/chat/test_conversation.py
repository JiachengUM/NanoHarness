import pytest

from nanoai.chat.conversation import Conversation, Round, ConversationInfo, conversations_to_html


def test_round_creation_and_format():
    """测试Round的创建和格式化功能"""
    print("=== 测试Round创建和格式化 ===")
    
    # 创建一个Round实例
    round_data = Round(
        message_a="你好，我是用户",
        think_a="我应该礼貌地打招呼",
        message_b="你好！我是AI助手，很高兴为您服务",
        think_b="用户很友好，我应该热情回应"
    )
        
    # 测试格式化输出
    formatted_custom = round_data.format("A", "B", "think")
    print(formatted_custom)


def test_conversation_creation_and_operations():
    """测试Conversation的创建和基本操作"""
    print("\n=== 测试Conversation创建和操作 ===")

    # 测试空对话处理
    print("\n--- 测试空对话处理 ---")
    empty_conversation = Conversation()
    print(f"空对话长度: {len(empty_conversation)}")
    formatted_empty = empty_conversation.format()
    print(f"空对话格式化结果: '{formatted_empty}'")
    
    
    # 创建Conversation实例
    conversation = Conversation()
    
    # 添加几个Round
    round1 = Round(
        message_a="你好！我是一名编程初学者，最近在学习Python编程语言。\n我想了解一下Python的基础知识和学习方法，希望能得到一些建议。",
        think_a="用户看起来很真诚，对Python学习有热情。\n我应该先了解他们的背景，然后给出合适的学习建议。\n要鼓励他们，不要让他们觉得编程太难。",
        message_b="你好！很高兴见到你！Python确实是一个非常适合初学者的编程语言。\n\n让我先了解一下你的情况：\n1. 你之前有编程经验吗？\n2. 你学习Python的目标是什么？\n3. 你每天能投入多少时间来学习？\n\n这样我可以为你制定更合适的学习计划。",
        think_b="用户是初学者，需要从基础开始。\n我应该先了解他们的具体情况，然后给出个性化的建议。\n要让他们感受到Python学习的乐趣和实用性。"
    )
    
    round2 = Round(
        message_a="我之前完全没有编程经验，这是第一次接触编程。\n\n我的学习目标主要有两个：\n1. 能够独立编写一些简单的程序\n2. 为将来的数据分析工作做准备\n\n关于时间安排，我每天可以抽出2-3小时来学习，周末时间会更多一些。\n\n另外，我比较喜欢动手实践，不太喜欢纯理论的学习方式。",
        think_a="用户很坦诚，说明了他们的真实情况。\n他们需要从零开始，但目标很明确。\n喜欢实践是个好习惯，我可以推荐一些项目练习。\n数据分析方向也很有前景，可以重点介绍相关库。",
        message_b="非常好的学习态度！你的目标很明确，时间安排也很合理。\n\n基于你的情况，我建议按以下步骤学习：\n\n**第一阶段：Python基础（2-3周）**\n- 变量、数据类型、运算符\n- 条件语句和循环\n- 函数定义和调用\n- 列表、字典等数据结构\n\n**第二阶段：实践项目（3-4周）**\n- 简单计算器程序\n- 文件读写操作\n- 简单的数据处理脚本\n\n**第三阶段：数据分析入门（4-6周）**\n- NumPy库基础\n- Pandas数据处理\n- 数据可视化基础\n\n你觉得这个学习计划怎么样？我们可以先从第一个项目开始。",
        think_b="给出了清晰的学习路径，符合用户的需求。\n强调了实践的重要性，符合用户的学习偏好。\n时间安排合理，不会让用户感到压力。\n为后续的数据分析学习打下了基础。"
    )
    
    round3 = Round(
        message_a="这个学习计划听起来很棒！特别是实践项目的部分。\n\n我想问几个具体问题：\n1. 你推荐使用什么开发环境？\n2. 有没有适合初学者的在线练习平台？\n3. 如果遇到问题，有哪些好的资源可以求助？\n\n另外，我注意到你提到了NumPy和Pandas，这些库具体是用来做什么的？\n\n我希望能尽快开始第一个项目，感觉这样学习会更有成就感。",
        think_a="用户对学习计划很满意，这很好。\n他们提出了很实际的问题，说明在认真思考学习过程。\n对NumPy和Pandas感兴趣，可以详细介绍。\n想要快速开始项目，说明学习积极性很高。",
        message_b="很高兴你对这个计划感兴趣！让我来回答你的问题：\n\n**开发环境推荐：**\n- **PyCharm Community Edition**：功能强大，适合初学者\n- **VS Code**：轻量级，插件丰富\n- **Jupyter Notebook**：交互式编程，特别适合数据分析\n\n**在线练习平台：**\n- **LeetCode**：编程题目练习\n- **HackerRank**：Python专项练习\n- **Codewars**：游戏化编程挑战\n\n**学习资源：**\n- **官方文档**：Python.org\n- **Stack Overflow**：问题解答社区\n- **GitHub**：开源项目参考\n\n**NumPy和Pandas简介：**\n- **NumPy**：数值计算库，处理数组和矩阵运算\n- **Pandas**：数据分析库，处理表格数据，类似Excel但更强大\n\n让我们从第一个项目开始吧！我建议先做一个简单的计算器，这样可以巩固基础语法。",
        think_b="回答了用户的所有问题，给出了具体的建议。\n推荐了多种选择，让用户可以根据自己的喜好选择。\n解释了NumPy和Pandas的作用，满足了用户的好奇心。\n最后引导用户开始实践，保持学习动力。"
    )
    
    round4 = Round(
        message_a="太棒了！我已经下载了PyCharm，感觉界面很友好。\n\n关于第一个项目，我想先确认一下：\n1. 计算器需要支持哪些运算？\n2. 界面是命令行还是图形界面？\n3. 大概需要多长时间能完成？\n\n我计划今天晚上就开始动手，希望能在这个周末完成。\n\n另外，我在安装Python时遇到了一些问题，系统提示需要配置环境变量，这个该怎么处理？",
        think_a="用户已经开始行动了，这很好！\n他们对项目细节很关心，说明在认真规划。\n遇到了环境配置问题，需要详细指导。\n时间安排很合理，周末完成是可行的。",
        message_b=(
            "很好！你已经迈出了第一步。让我来帮你规划这个项目：\n\n"
            "**计算器项目规划：**\n\n"
            "**功能要求：**\n"
            "- 支持加、减、乘、除四则运算\n"
            "- 支持小数运算\n"
            "- 处理除零错误\n"
            "- 支持连续计算\n\n"
            "**界面选择：**\n"
            "- 建议先从命令行开始，专注于逻辑实现\n"
            "- 后续可以升级为图形界面\n\n"
            "**预计时间：**\n"
            "- 基础版本：2-3小时\n"
            "- 完善版本：4-6小时\n"
            "- 周末完成完全没问题！\n\n"
            "**环境变量配置（Windows）：**\n"
            "1. 右键\"此电脑\" → 属性 → 高级系统设置\n"
            "2. 环境变量 → 系统变量 → Path\n"
            "3. 添加Python安装目录（如：C:\\Python39\\）\n"
            "4. 添加Scripts目录（如：C:\\Python39\\Scripts\\）\n"
            "5. 重启命令提示符，输入 `python --version` 验证\n\n"
            "如果还有问题，我们可以一步步解决。准备好开始编码了吗？"
        ),
        think_b="给出了详细的项目规划，让用户有清晰的目标。\n提供了环境配置的具体步骤，解决了用户的实际问题。\n时间估计合理，不会让用户感到压力。\n最后鼓励用户开始编码，保持学习热情。"
    )
    
    round5 = Round(
        message_a="环境变量已经配置好了！Python可以正常运行了。\n\n我按照你的建议，先实现了一个基础版本的计算器，支持四则运算。\n\n现在遇到几个问题：\n1. 如何处理用户输入错误（比如输入字母）？\n2. 如何让程序循环运行，而不是每次都要重新启动？\n3. 如何美化输出格式，让结果更易读？\n\n我的代码大概有50行，感觉还可以优化。\n\n另外，我发现编程真的很有趣！虽然遇到了一些问题，但解决后很有成就感。",
        think_a="用户已经成功完成了基础版本，这很棒！\n他们遇到了实际编程中的常见问题，这是很好的学习机会。\n对编程产生了兴趣，这是最重要的。\n代码长度合理，说明实现得不错。",
        message_b=(
            "太棒了！你已经成功完成了第一个项目，这值得庆祝！\n\n"
            "让我来帮你解决这些问题：\n\n"
            "**1. 错误处理：**\n"
            "```python\n"
            "try:\n"
            "    num = float(input(\"请输入数字: \"))\n"
            "except ValueError:\n"
            "    print(\"输入错误！请输入有效的数字。\")\n"
            "    continue\n"
            "```\n\n"
            "**2. 循环运行：**\n"
            "```python\n"
            "while True:\n"
            "    # 你的计算器代码\n"
            "    choice = input(\"是否继续计算？(y/n): \")\n"
            "    if choice.lower() != 'y':\n"
            "        break\n"
            "```\n\n"
            "**3. 美化输出：**\n"
            "```python\n"
            "print(\"=\" * 30)\n"
            "print(f\"计算结果: {result:.2f}\")\n"
            "print(\"=\" * 30)\n"
            "```\n\n"
            "**代码优化建议：**\n"
            "- 将计算逻辑封装成函数\n"
            "- 添加输入验证\n"
            "- 使用常量定义菜单选项\n"
            "- 添加注释说明\n\n"
            "你的学习进度很快！接下来想挑战什么项目？\n"
            "我建议可以尝试：文件操作、简单游戏、或者数据处理脚本。"
        ),
        think_b="给出了具体的代码示例，帮助用户解决问题。\n提供了代码优化建议，提升代码质量。\n肯定了用户的学习成果，增强信心。\n为下一步学习提供了方向，保持学习连续性。"
    )
    
    # 添加到对话中
    conversation.append(round1)
    conversation.append(round2)
    conversation.append(round3)
    conversation.append(round4)
    conversation.append(round5)
    
    print(f"对话总轮数: {len(conversation)}")
    
    # 测试列表操作
    print(f"第一轮对话: {conversation[0].message_a} -> {conversation[0].message_b}")
    print(f"最后一轮对话: {conversation[-1].message_a} -> {conversation[-1].message_b}")
    
    # 测试格式化整个对话
    print("\n完整对话格式化:")
    formatted_conversation = conversation.format()
    print(formatted_conversation)
    
    # 测试不同名称的格式化
    print("\n--- 测试不同名称的格式化 ---")
    formatted_en = conversation.format("Alice", "Bob", "thinking")
    print("使用英文名称格式化:")
    print(formatted_en)
    
    # 测试to_json和from_json方法
    print("\n--- 测试to_json和from_json方法 ---")
    try:
        # 测试保存为JSON
        json_filename = "test_conversation.json"
        conversation.to_json(json_filename)
        print(f"✅ 对话已保存为JSON文件: {json_filename}")
        
        # 测试从JSON加载
        loaded_conversation = Conversation.from_json(json_filename)
        print(f"✅ 从JSON文件加载对话成功，轮数: {len(loaded_conversation)}")
        
        # 验证加载的数据是否正确
        assert len(loaded_conversation) == len(conversation), "加载的对话轮数不匹配"
        
        # 验证第一轮对话内容
        original_first = conversation[0]
        loaded_first = loaded_conversation[0]
        assert original_first.message_a == loaded_first.message_a, "第一轮用户消息不匹配"
        assert original_first.message_b == loaded_first.message_b, "第一轮助手消息不匹配"
        assert original_first.think_a == loaded_first.think_a, "第一轮用户思考不匹配"
        assert original_first.think_b == loaded_first.think_b, "第一轮助手思考不匹配"
        
        print("✅ 加载的对话内容验证通过")
        
        # 测试空对话的JSON保存和加载
        print("\n--- 测试空对话的JSON操作 ---")
        empty_conversation.to_json("test_empty_conversation.json")
        loaded_empty = Conversation.from_json("test_empty_conversation.json")
        assert len(loaded_empty) == 0, "空对话加载后长度应该为0"
        print("✅ 空对话JSON操作测试通过")
        
        # 测试包含中文的对话
        print("\n--- 测试包含中文的对话JSON操作 ---")
        chinese_round = Round(
            message_a="你好，世界！",
            think_a="用中文打招呼",
            message_b="你好！很高兴见到你！",
            think_b="用中文回应"
        )
        chinese_conversation = Conversation([chinese_round])
        chinese_conversation.to_json("test_chinese_conversation.json")
        
        loaded_chinese = Conversation.from_json("test_chinese_conversation.json")
        assert loaded_chinese[0].message_a == "你好，世界！", "中文消息保存失败"
        print("✅ 中文对话JSON操作测试通过")
        
    except Exception as e:
        print(f"❌ JSON操作测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 测试to_html方法
    print("\n--- 测试to_html方法 ---")
    try:
        # 测试基本的to_html调用
        conversation.to_html(
            filename="test_conversation.html",
            title="测试对话",
            scenario="Python编程咨询",
            user_info="编程初学者",
            topic="Python基础学习"
        )
        print("✅ to_html方法调用成功，生成了test_conversation.html文件")
        
        # 测试自定义样式
        conversation.to_html(
            filename="test_conversation_custom.html",
            title="自定义样式对话",
            scenario="角色扮演",
            user_info="测试用户",
            topic="测试主题",
            styling={"theme_color": "linear-gradient(135deg, #28a745 0%, #20c997 100%)"},
            name_a="小明",
            name_b="AI老师",
            show_thinking=False
        )
        print("✅ 自定义样式to_html调用成功，生成了test_conversation_custom.html文件")
        
        # 测试宽度设置
        conversation.to_html(
            filename="test_conversation_width.html",
            title="宽度设置测试",
            scenario="宽度控制测试",
            user_info="测试用户",
            topic="宽度参数测试",
            styling={
                "theme_color": "linear-gradient(135deg, #6c757d 0%, #adb5bd 100%)",
                "container_width": "100%",
                "chat_width": "95%",
                "min_width": "600px"
            },
            name_a="测试用户",
            name_b="测试助手",
            show_thinking=True
        )
        print("✅ 宽度设置测试成功，生成了test_conversation_width.html文件")
        
    except Exception as e:
        print(f"❌ to_html测试失败: {e}")
        import traceback
        traceback.print_exc()


def test_multi_conversation_creation_and_operations():
    """测试多对话对比功能"""
    print("\n=== 测试多对话对比功能 ===")
    
    # 创建3组相似的对话，每组3轮
    # 对话1：正式风格的技术支持
    conv1_round1 = Round(
        message_a="您好，我在使用Python时遇到了一个错误，希望能得到您的帮助。",
        think_a="用户遇到了技术问题，需要专业的帮助。",
        message_b="您好！我很乐意帮助您解决Python相关的问题。请详细描述一下您遇到的错误信息。",
        think_b="需要了解具体的错误信息才能提供准确的帮助。"
    )
    
    conv1_round2 = Round(
        message_a="错误信息显示：'NameError: name 'variable' is not defined'。我检查了代码，但找不到问题所在。",
        think_a="这是一个常见的变量未定义错误，需要帮助用户理解作用域问题。",
        message_b="这是一个变量作用域的问题。请检查变量是否在正确的位置定义，以及是否在定义之前就被使用了。",
        think_b="提供了基本的解决思路，用户应该能够理解。"
    )
    
    conv1_round3 = Round(
        message_a="谢谢您的指导！我重新检查了代码，发现变量确实在函数外部定义，但在函数内部使用时出现了问题。",
        think_a="用户理解了问题所在，可以给出更具体的解决方案。",
        message_b="很好！您已经找到了问题的根源。建议使用global关键字或者在函数内部重新定义变量。",
        think_b="问题已经解决，用户学到了新的知识。"
    )
    
    conversation1 = Conversation([conv1_round1, conv1_round2, conv1_round3])
    
    # 对话2：友好风格的学习指导
    conv2_round1 = Round(
        message_a="嗨！我刚开始学Python，遇到了一个让我困惑的问题，能帮帮我吗？",
        think_a="用户是初学者，需要耐心和鼓励。",
        message_b="当然可以！学习编程遇到问题是完全正常的，我们一起来解决它。请告诉我具体是什么问题？",
        think_b="用友好的语气鼓励用户，让他们感到轻松。"
    )
    
    conv2_round2 = Round(
        message_a="我写了一个简单的程序，但是运行时出现了'NameError: name 'variable' is not defined'这个错误。",
        think_a="同样的错误，但需要用更通俗易懂的方式解释。",
        message_b="哦，这个错误很常见！简单来说，就是Python找不到你提到的那个变量。就像你叫一个人的名字，但这个人不在房间里一样。",
        think_b="用比喻的方式让初学者更容易理解。"
    )
    
    conv2_round3 = Round(
        message_a="哈哈，这个比喻很有趣！我明白了，我的变量确实没有在正确的地方定义。",
        think_a="用户理解了，可以给出具体的解决方法。",
        message_b="太棒了！你理解得很快。现在只需要把变量放在正确的位置，或者使用global关键字就可以了。",
        think_b="继续鼓励用户，让他们保持学习的热情。"
    )
    
    conversation2 = Conversation([conv2_round1, conv2_round2, conv2_round3])
    
    # 对话3：简洁风格的问题解决
    conv3_round1 = Round(
        message_a="Python报错：NameError: name 'variable' is not defined。",
        think_a="用户直接描述了问题，需要快速给出解决方案。",
        message_b="变量未定义错误。检查变量定义位置和作用域。",
        think_b="简洁明了地指出问题所在。"
    )
    
    conv3_round2 = Round(
        message_a="变量在函数外定义，函数内使用时报错。",
        think_a="问题很明确，直接给出解决方案。",
        message_b="使用global关键字或在函数内重新定义变量。",
        think_b="提供直接的解决方案。"
    )
    
    conv3_round3 = Round(
        message_a="已解决，谢谢。",
        think_a="问题已解决，简单确认即可。",
        message_b="不客气，有问题随时联系。",
        think_b="简洁地结束对话。"
    )
    
    conversation3 = Conversation([conv3_round1, conv3_round2, conv3_round3])
    
    # 创建对话信息，通过summary体现差异
    conversations = [
        (conversation1, ConversationInfo(
            summary="正式技术支持风格：使用敬语，详细解释技术问题，提供专业建议",
            name_a="用户",
            name_b="技术支持"
        )),
        (conversation2, ConversationInfo(
            summary="友好学习指导风格：使用亲切语言，用比喻解释概念，鼓励学习",
            name_a="初学者",
            name_b="编程导师"
        )),
        (conversation3, ConversationInfo(
            summary="简洁问题解决风格：直接描述问题，快速给出解决方案，高效沟通",
            name_a="开发者",
            name_b="技术顾问"
        ))
    ]
    
    print(f"创建了 {len(conversations)} 组对话，每组 {len(conversation1)} 轮")
    
    # 测试conversations_to_html
    print("\n--- 测试conversations_to_html方法 ---")
    try:
        # 基本调用
        conversations_to_html(
            conversations=conversations,
            filename="test_conversations_comparison.html",
            title="对话风格对比测试",
            show_thinking=True
        )
        print("✅ conversations_to_html基本调用成功，生成了test_conversations_comparison.html文件")
        
        # 自定义样式调用
        conversations_to_html(
            conversations=conversations,
            filename="test_conversations_custom.html",
            title="自定义样式对话对比",
            styling={
                "theme_color": "linear-gradient(135deg, #ff6b6b 0%, #4ecdc4 100%)",
                "border_radius": "12px",
                "container_width": "100%",
                "chat_width": "90%",
                "min_width": "500px"
            },
            show_thinking=False
        )
        print("✅ conversations_to_html自定义样式调用成功，生成了test_conversations_custom.html文件")
        
        # 验证对话长度一致性
        for i, (conv, info) in enumerate(conversations):
            assert len(conv) == 3, f"对话{i+1}的长度应该是3轮，实际是{len(conv)}轮"
            print(f"✅ 对话{i+1}长度验证通过：{len(conv)}轮")
        
        print("✅ 所有对话长度验证通过")
        
        # 验证对话内容
        for i, (conv, info) in enumerate(conversations):
            print(f"对话{i+1}摘要：{info.summary}")
            print(f"对话{i+1}参与者：{info.name_a} vs {info.name_b}")
        
        print("✅ conversations_to_html测试完成")
        
    except Exception as e:
        print(f"❌ conversations_to_html测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("开始测试Conversation和Round类...")
    print("=" * 60)
    
    # 运行所有测试
    # test_round_creation_and_format()
    # test_conversation_creation_and_operations()
    test_multi_conversation_creation_and_operations()
    
    print("\n" + "=" * 60)
    print("所有测试完成！")
    