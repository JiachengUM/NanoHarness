from projects.mind.toolset.web_search import websearch
from projects.mind.toolset.web_search_v2 import generate_complete_search, WebsearchInput
import asyncio

async def test(cases):
    result = []
    for query, logic_query in cases:
        ret4query = await websearch(query)
        ret4query_logic = await websearch(logic_query)
        result.append({query: ret4query, logic_query: ret4query_logic})
    return result


USER_QUERIES = [
    # 1. 学术研究
    "找关于大语言模型对齐（alignment）的综述或综述类论文，但不要预印本，最好是 2023–2025 年的 PDF。",

    # 2. 技术调研
    "对比 React 和 Vue 的性能，只看官方文档或高质量博客，排除知乎和 CSDN。", #排除CSDN

    # 3. 电商选购
    "找 2000–3000 元的降噪耳机，索尼或 Bose，排除二手和资源机。", #

    # 4. 新闻追踪
    "关于 AI 监管的新闻，只看 BBC 或 Reuters，过去一年，排除 opinion 栏目。", #时间正确

    # 5. 漏洞与运维
    "查找 Nginx 或 Apache 的 CVE 漏洞，排除 2020 年以前的内容，且必须是官方公告。", #时间正确

    # 6. 职场与招聘
    "北京或上海的远程前端岗位，薪资 25k–40k，不要外包公司。"
]

STRUCTURED_EXPRESSIONS = [
    # 1. 学术：综述 或 综述类论文，排除预印本
    {
        "query": {
            "and": [
                {"text": "大语言模型 对齐"},
                {
                    "or": [
                        {"intitle": ["综述"]},
                        {"intitle": ["论文"]}
                    ]
                },
                {"filetype": ["pdf"]},
                {"after": "2023-01-01"},
                {"before": "2025-12-31"},
                {
                    "not": {
                        "or": [
                            {"site": ["arxiv.org"]},
                            {"intext": ["预印本"]}
                        ]
                    }
                }
            ]
        }
    },

    # 2. 技术：React 或 Vue，官方文档 或 高质量博客
    {
        "query": {
            "and": [
                {"text": "React Vue 性能对比"},
                {
                    "or": [
                        {"site": ["react.dev", "vuejs.org"]},
                        {
                            "and": [
                                {"site": ["zhihu.com", "juejin.cn"]},
                                {"intext": ["性能", "压测"]}
                            ]
                        }
                    ]
                },
                {
                    "not": {
                        "or": [
                            {"site": ["csdn.net"]},
                            {"site": ["cnblogs.com"]}
                        ]
                    }
                }
            ]
        }
    },

    # 3. 电商：索尼 或 Bose，非二手
    {
        "query": {
            "and": [
                {"text": "降噪耳机"},
                {"price_filter": "2000..3000"},
                {
                    "or": [
                        {"intext": ["索尼"]},
                        {"intext": ["Bose"]}
                    ]
                },
                {
                    "not": {
                        "or": [
                            {"intext": ["资源机"]},
                            {"intext": ["二手"]},
                            {"intext": ["99新"]}
                        ]
                    }
                }
            ]
        }
    },

    # 4. 新闻：BBC 或 路透社，排除评论
    {
        "query": {
            "and": [
                {"text": "AI 监管"},
                {
                    "or": [
                        {"news_source": "BBC"},
                        {"news_source": "路透社"}
                    ]
                },
                {"after": "2025-05-14"},
                {
                    "not": {
                        "inurl": ["opinion", "comment", "评论"]
                    }
                }
            ]
        }
    },

    # 5. 安全：Nginx 或 Apache 的 CVE
    {
        "query": {
            "and": [
                {
                    "or": [
                        {"text": "Nginx"},
                        {"text": "Apache"}
                    ]
                },
                {"intext": ["CVE", "漏洞"]},
                {"after": "2020-01-01"},
                {
                    "or": [
                        {"site": ["nginx.org"]},
                        {"site": ["apache.org"]}
                    ]
                }
            ]
        }
    },

    # 6. 招聘：北京 或 上海，远程，25k–40k，非外包
    {
        "query": {
            "and": [
                {
                    "or": [
                        {"intext": ["北京"]},
                        {"intext": ["上海"]}
                    ]
                },
                {"intext": ["远程", "前端"]},
                {"range_num": "25000..40000"},
                {
                    "not": {
                        "intext": ["外包", "OD"]
                    }
                }
            ]
        }
    }
]
# USER_QUERIES = [
#     # 1. 双重否定 + 嵌套 OR（人类最爱说，LLM 最爱错）
#     "找深度学习相关的论文，不要那种不是 2023 年以后的，也不要非 PDF 的。",
#
#     # 2. 排他性语义（A 或 B，但不能同时）
#     "找只要北京或上海其中一地的远程工作，不要两地都写的。",
#
#     # 3. 多层级排除（NOT 套 OR 套 AND）
#     "关于电动车电池的新闻，排除比亚迪和宁德时代以外的厂商，也不要自媒体水文。",
#
#     # 4. 范围 + 枚举混合（数值 + 文本 OR）
#     "预算 3000 到 5000 的机械键盘，要樱桃或 TTC 轴，但不要青轴。",
#
#     # 5. 语义重叠导致的冲突
#     "免费的开源项目管理系统，不要 Jira，也不要收费的，最好 GitHub 上星多的。",
#
#     # 6. 时间逻辑陷阱
#     "去年发布的手机，但不是 2024 年上半年发布的。",
#
#     # 7. 模糊 + 精确 + 排除
#     "怎么* Python 性能优化，排除 Python 2，也不要广告。", #广告 {'query': {'and': [{'text': 'Python性能优化'}, {'exclude': ['Python 2', '广告']}]}}
#
#     # 8. 多站点 + 多排除 + 文件类型
#     "机器学习面试题 site:zhihu.com 或 site:juejin.cn，但不要知乎专栏，要 PDF 或 Markdown。"
# ]
#
# STRUCTURED_EXPRESSIONS = [
#     # 1. 双重否定（NOT NOT）
#     {
#         "query": {
#             "and": [
#                 { "text": "深度学习 论文" },
#                 { "filetype": ["pdf"] },
#                 {
#                     "after": "2023-01-01",
#                 }
#             ]
#         }
#     },
#
#     # 2. 排他性 OR（XOR 模拟）
#     {
#         "query": {
#             "and": [
#                 { "text": "远程工作 前端" },
#                 {
#                     "or": [
#                         {
#                             "and": [
#                                 { "intext": ["北京"] },
#                                 { "not": { "intext": ["上海"] } }
#                             ]
#                         },
#                         {
#                             "and": [
#                                 { "intext": ["上海"] },
#                                 { "not": { "intext": ["北京"] } }
#                             ]
#                         }
#                     ]
#                 }
#             ]
#         }
#     },
#
#     # 3. NOT 套 OR 套 AND（非常容易抽错）
#     {
#         "query": {
#             "and": [
#                 { "text": "电动车 电池" },
#                 {
#                     "not": {
#                         "or": [
#                             {
#                                 "and": [
#                                     { "intext": ["比亚迪"] },
#                                     { "intext": ["宁德时代"] }
#                                 ]
#                             },
#                             {
#                                 "and": [
#                                     { "site": ["weixin.qq.com"] },
#                                     { "intext": ["评测", "体验"] }
#                                 ]
#                             }
#                         ]
#                     }
#                 }
#             ]
#         }
#     },
#
#     # 4. 范围 + OR + NOT
#     {
#         "query": {
#             "and": [
#                 { "text": "机械键盘" },
#                 { "range_num": "3000..5000" },
#                 {
#                     "or": [
#                         { "intext": ["樱桃轴"] },
#                         { "intext": ["TTC轴"] }
#                     ]
#                 },
#                 {
#                     "not": { "intext": ["青轴"] }
#                 }
#             ]
#         }
#     },
#
#     # 5. 语义冲突（免费 ≠ 收费，但 LLM 常把 exclude 放错）
#     {
#         "query": {
#             "and": [
#                 { "text": "开源 项目管理" },
#                 { "intext": ["免费"] },
#                 {
#                     "not": {
#                         "or": [
#                             { "intext": ["Jira"] },
#                             { "intext": ["收费"] }
#                         ]
#                     }
#                 },
#                 { "intext": ["GitHub stars"] }
#             ]
#         }
#     },
#
#     # 6. 时间逻辑陷阱
#     {
#         "query": {
#             "and": [
#                 { "text": "手机 发布" },
#                 { "after": "2025-05-14" },
#                 {
#                     "not": {
#                         "and": [
#                             { "after": "2024-01-01" },
#                             { "before": "2024-06-30" }
#                         ]
#                     }
#                 }
#             ]
#         }
#     },
#
#     # 7. 通配符 + 精确排除
#     {
#         "query": {
#             "and": [
#                 { "wildcard": "怎么* Python 性能优化" },
#                 {
#                     "not": {
#                         "or": [
#                             { "intext": ["Python 2"] },
#                             { "intext": ["广告", "推广"] }
#                         ]
#                     }
#                 }
#             ]
#         }
#     },
#
#     # 8. 多站点 + 排除路径 + 文件类型
#     {
#         "query": {
#             "and": [
#                 { "text": "机器学习 面试题" },
#                 {
#                     "or": [
#                         { "site": ["zhihu.com"] },
#                         { "site": ["juejin.cn"] }
#                     ]
#                 },
#                 {
#                     "not": {
#                         "inurl": ["zhuanlan"]
#                     }
#                 },
#                 {
#                     "or": [
#                         { "filetype": ["pdf"] },
#                         { "filetype": ["md"] }
#                     ]
#                 }
#             ]
#         }
#     }
# ]

QUERY_EXPRESSION = [generate_complete_search(WebsearchInput.model_validate(case)) for case in STRUCTURED_EXPRESSIONS]


if __name__ == '__main__':
    asyncio.run(test(zip(USER_QUERIES, QUERY_EXPRESSION)))
