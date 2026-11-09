"""
Jev（TypeSafe AI System One）决策模型实验 demo1（异步版）：验证 Choice / Score / Noul 三原语。

Jev 不生成文字，直接输出类型化的概率决策：
- Choice: 从一组选项里选一个，返回选中项、完整概率分布、置信度
- Score: 沿有序量表打分，返回分数（可落在两档之间）、概率分布、置信度
- Noul: 判断一个陈述是否成立，返回 0-1 概率

核心要点：
1. 一次 system_one 调用 = 一份 state + 多个问题。
   所有问题共享同一份 state，彼此并行、独立评估，互看不到对方的答案。
   加问题几乎不增加延迟，也避免了"多轮对话导致的上下文污染"。
2. 输出是强类型的：代码拿到就能直接写 if 分支，
   不需要解析自然语言、不需要防御 JSON 格式错误（无幻觉问题）。
3. probabilities 是完整概率分布（各项加和为 1），
   confidence 衡量"分布有多尖"（选项之间分得开不开），
   两者的区别见各字段注释。
"""
import asyncio
from pathlib import Path

from dotenv import load_dotenv
from typesafe_sdk import AsyncTypeSafeClient, Choice, Score, Noul

# 加载本脚本所在目录下的 .env（不覆盖已存在的进程环境变量）。
# .env 中存放 TYPESAFE_API_KEY，已被 .gitignore 排除，不会进版本库。
load_dotenv(Path(__file__).parent / ".env")


async def main() -> None:
    # 异步客户端：async with 保证退出时 aclose() 释放网络资源
    async with AsyncTypeSafeClient() as client:
        # state：被判断的"状态"，即模型要审视的数据。
        # 可以是纯字符串，也可以是结构化 dict（本例），dict 的 key 也会被模型读到。
        # 官方限制：上下文共 64k token，其中 state + 最长问题占 32k。
        state = {
            "message": (
                "I've been trying to connect my Stripe account for three days. "
                "The integration keeps failing and I'm losing sales. "
                "Please fix this ASAP."
            )
        }

        # questions：问题集合。key 是问题 ID（程序侧索引，模型只看 instructions/criteria），
        # value 是三种原语之一。三种类型可在同一请求中混用。
        # 唯一的异步差异：调用前加 await。
        response = await client.system_one(
            state=state,
            questions={
                # ── 原语 1：Choice（单选）────────────────────────────────
                # 适用：分类、路由、分派。最多 255 个选项。
                # instructions：问什么（一个问题只问一件事，要原子化）。
                # criteria：选项 key → 描述。注意：选项描述会作为提示词的一部分
                #   到达模型——选项本身就是 prompt，描述写得越互斥、分布越干净。
                "department": Choice(
                    instructions="Which team should handle this customer request?",
                    criteria={
                        "billing": "Payment, refund, invoice, or subscription issue",
                        "technical": "Bug, integration, API, or technical issue",
                        "sales": "Pricing, plan, or purchase question",
                    },
                ),

                # ── 原语 2：Score（量表打分）─────────────────────────────
                # 适用：程度类判断：情绪、紧急度、质量、风险。2-10 档，从低到高有序。
                # criteria 是有序数组：下标 0 = 最低档，最后一项 = 最高档。
                # 注意：score 是概率加权平均，可以落在两档之间（如 1.7），
                #   若要"选定档位"应对 probabilities 取 argmax 而不是四舍五入——
                #   偏斜分布下四舍五入会指错档位。
                "frustration": Score(
                    instructions="How frustrated does the customer appear?",
                    criteria=[
                        "Calm",                    # 档位 0：平静
                        "Somewhat frustrated",     # 档位 1：有些不满
                        "Very frustrated",         # 档位 2：非常不满
                    ],
                ),

                # ── 原语 3：Noul（是非判断）────────────────────────────────
                # 适用：真伪/存在性判断。返回一个 0-1 概率：
                #   0.98 = 强烈的"是"；0.02 = 强烈的"否"；0.5 附近 = 两可（证据对半）。
                # Noul 没有 confidence 字段——概率本身就是答案（校准过的）。
                # 可选 criteria 可以给 true/false 各写一段判据描述，帮助模型对齐边界。
                "urgent": Noul(
                    instructions="Does this request require urgent attention?"
                ),
            },
        )

    # answers：每个问题 ID 对应一个类型化答案对象，按原语类型取字段：
    # - ChoiceAnswer: .choice（选中项）/ .probabilities / .confidence
    # - ScoreAnswer:  .score / .probabilities / .legend / .confidence
    # - NoulAnswer:   .noul（0-1 概率）
    # （消费答案的代码完全在 async with 外也不受影响——response 是纯数据对象）
    department = response.answers["department"]
    frustration = response.answers["frustration"]
    urgent = response.answers["urgent"]

    # ── Choice 结果解读 ──────────────────────────────────────────────
    # choice     ：概率最高的选项（官方定义即"答案"）。
    # probabilities：完整分布，各项加和为 1。即使只消费 choice，
    #               分布也透露了次优选项的相对强度（如 technical=0.8, billing=0.18
    #               说明 billing 是有实质竞争的次优解，可用于"边缘案例转人工"策略）。
    # confidence ：分布的"尖锐程度"。1.0 = 概率质量全压在一个选项上；
    #               低 confidence ≠ 模型不确定答案，而是选项没分开
    #               （问题有争议 / 选项互相重叠 / state 信息不足三种原因要区分）。
    print("department =", department.choice)
    print("department probabilities =", department.probabilities)
    print("department confidence =", department.confidence)

    print()

    # ── Score 结果解读 ───────────────────────────────────────────────
    # score        ：概率加权平均分，落在 [0, 最高档下标] 区间，可以是小数（两档之间）。
    # probabilities：每个档位的概率。判断"实际档位"应对它取 argmax。
    # confidence  ：分布尖锐度，同上。
    print("frustration score =", frustration.score)
    print("frustration probabilities =", frustration.probabilities)
    print("frustration confidence =", frustration.confidence)

    print()

    # ── Noul 结果解读 ───────────────────────────────────────────────
    # noul：单一 0-1 概率，无需其他字段。
    # 工程上常配阈值使用：如 >0.8 视为"是"、<0.2 视为"否"、中间区间走兜底逻辑。
    print("urgent probability =", urgent.noul)


if __name__ == "__main__":
    asyncio.run(main())
