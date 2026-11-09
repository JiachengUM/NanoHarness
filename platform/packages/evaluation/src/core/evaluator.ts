import AgentAdaptor from '../adaptor/base'
import { DatasetItem } from '@eval-platform/database'
import { nlRepr } from '@eval-platform/shared'
import Judge, { type JudgeResult } from './judge'
import Hints from './hints'
import PQueue from 'p-queue'

type UserQueryList = DatasetItem['user_query_lists'][0]

interface EvaluateResult extends JudgeResult {
  datasetItem: DatasetItem
}

const CONCURRENCY_LIMIT = 10

export class Evaluator<T extends AgentAdaptor> {
  private adaptor: T
  private judge: Judge
  private hints: Hints

  constructor(adaptor: T) {
    this.adaptor = adaptor
    this.judge = new Judge()
    this.hints = new Hints()
  }

  /**
   * 从user_query_list中获取初始输入，并开始对话
   * @param userQueryList 从user_query_list中获取初始输入，并开始对话
   * @returns
   */
  private getStartQuery(userQueryList: UserQueryList): string {
    const input = Array.isArray(userQueryList)
      ? (userQueryList[0].content as string)
      : (userQueryList.user_query_list?.[0]?.content as string)

    return input
  }

  /**
   * 对单个测试用例进行执行并评测：
   * @param datasetItem 测试用例
   * @returns 评测结果
   */
  public async evaluate(datasetItem: DatasetItem): Promise<EvaluateResult> {
    const userQueryLists = datasetItem.user_query_lists || []

    let judgeHistory: string = ''

    for (const userQueryList of userQueryLists) {
      // 每次对话开始前重置会话状态
      this.adaptor.newSession()
      let chatRound = 1
      judgeHistory += `\n=== 第 ${chatRound} 次对话历史 ===\n`

      while (chatRound <= datasetItem.max_round) {
        let input

        if (chatRound === 1) {
          // 第一轮对话使用测试用例中的初始输入
          input = this.getStartQuery(userQueryList)
        } else {
          // 从第二轮开始，根据当前对话历史生成hints，选择一个hint作为下一轮输入
          const messages = this.adaptor.getMessages()
          input = await this.hints.generateOne({ scene: datasetItem.expected_script, history: nlRepr(messages) })
        }

        if (!input) break

        console.log('用户输入: ', input)
        await this.adaptor.invoke(input)

        chatRound++
      }

      judgeHistory += `${nlRepr(this.adaptor.getHistory())}\n`
    }

    // 3. 使用Judge进行评测，得到评测结果
    const judgeResult = await this.judge.judge({
      history: judgeHistory,
      nl_assertion: nlRepr(datasetItem.nl_assertion),
    })

    return {
      ...judgeResult,
      datasetItem,
    }
  }

  /**
   * 并发评测多个测试用例，返回评测结果列表
   * @param datasetItems 待评测的测试用例列表
   * @param concurrency 并发数量，默认为10
   * @returns 评测结果列表
   */
  public async evaluateConcurrency(
    datasetItems: DatasetItem[],
    concurrency: number = CONCURRENCY_LIMIT,
  ): Promise<EvaluateResult[]> {
    const queue = new PQueue({ concurrency })
    const results: EvaluateResult[] = []

    for (const datasetItem of datasetItems) {
      queue.add(async () => {
        const result = await this.evaluate(datasetItem)
        results.push({ ...result, datasetItem })
      })
    }

    await queue.onIdle()
    return results
  }
}
