from projects.mind.mem.auto_test_script.langchain_models import doubao_model, qwen_model

csv_str = ''''''

if __name__ == "__main__":
    input = '''
下面三重反引号里是个存放着大量涉及记忆相关测试case内容的CSV文件的内容：

```
{{ csv_str }}
```

把上述csv文件里所有的case,按照你的理解，转化成如下schema的jsnl文件（以下是其中一个case的schema及其例子）：
{
    "creator": "窦梓瑜",
// case_id是你直接给这个case取的名字。
    "case_id": "测试跨多轮闲聊",
// context_config 智能体的其他配置，没有的话就空着
    "context_config": {},
    "max_round": 5,
// user_query_lists是多次多轮对话列表，但是每次多轮对话只保存user说的第一句话
    "user_query_lists": [ 
      [
        {
          "role": "user",
          "content": "你说电影《星际穿越》为什么黑洞周围除了吸积盘以外，还有一圈光晕呀？"
        }
      ],
      [
        {
          "role": "user",
          "content": "本周就要把测试平台做好了，咋办啊，忙死了。"
        }
      ],
      [
        {
          "role": "user",
          "content": "之前我们聊了什么？"
        }
      ]
    ],
//  expected_script一个大概的本case期望展现出来的对话剧本。
    "expected_script": "用户：你说电影《星际穿越》为什么黑洞周围除了吸积盘以外，还有一圈光晕呀？\n助手：因为黑洞强大的引力实际上是空间弯曲的表现，弯曲的空间导致黑洞背后的光能够从黑洞背后绕过事件视界到你的眼睛里让你看到。\n（……重启一次新的对话）\n用户：本周就要把测试平台做好了，咋办啊，忙死了。\n助手：没事，不要急，一步步来。\n（……重启一次新的对话）\n用户：之前我们聊了什么？\n助手：我们聊了星际穿越里的黑洞为什么有一圈光晕以及你向我吐槽了一下本周要把测试平台做好，太忙了。",
// nl_assertion自然语言描写的通过标准
    "nl_assertion": [
      "期望第三次对话中应该可以看到助手成功记住了前两次对话的大致内容并做出了合适的回答。",
      "实际上助手回答的具体内容前后能对上即可，不一定和剧本中一致。"
    ],
// case_description 这个case的一些相关其他信息
    "case_description": "原来id 4是测试上周的对话内容隔一周后能否继续记住，但是现阶段暂时无法测试时序剧本，所以改成了测试对前两次对话内容的总结和记忆以及使用。",
// 标签，是字符串的列表，你需要对每个case打上一系列标签，注意不要太细，只需要评测一个车载助手所需的最基础的标签。
    "tags": []
  }
'''.format(csv_str=csv_str)

    # 为langchain invoke加上
    print("正在调用模型...")
    result = qwen_model.invoke(input)
    print("模型调用完成")

    # 结果是json字符串，写入"D:\\yitu_projects\\nanoai\\projects\\mind\\mem\\auto_test_script\\js_files\\navigation_cases_updated.json"
    with open("D:\\yitu_projects\\nanoai\\projects\\mind\\mem\\auto_test_script\\js_files\\navigation_cases_updated.json", "w", encoding="utf-8") as f:
        f.write(result.content)
