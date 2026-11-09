import nunjucks from 'nunjucks'
import { createClient, invoke, OpenAI } from '@eval-platform/llm'

export interface JudgeInput {
  history: string
  nl_assertion: string
  [key: string]: unknown
}

export interface JudgeResult {
  is_pass: boolean
  reason: string
}

const JUDGE_SYSTEM_PROMPT = `你是一个评测专家，负责根据用户与智能体的交互历史和评测断言来判断智能体的表现是否符合预期。`

const JUDGE_PROMPT_TEMPLATE = `
请根据以下会话历史及评测断言进行评判，并给出是否通过的结论以及理由：
<会话历史>{{history}}</会话历史>
<评测断言>{{nl_assertion}}</评测断言>
`

// 定义 LLM 输出格式，要求输出符合 JudgeResult 的 JSON 结构
const EVALUATE_RESULT_TEXT: OpenAI.Responses.ResponseTextConfig = {
  format: {
    type: 'json_schema',
    name: 'evaluate_result',
    strict: true,
    schema: {
      type: 'object',
      properties: {
        is_pass: {
          type: 'boolean',
        },
        reason: {
          type: 'string',
        },
      },
      required: ['is_pass'],
      additionalProperties: false,
    },
  },
}

/**
 * 评测工具类
 */
export default class Judge {
  private systemPrompt: string
  private judgePromptTemplate: string
  private evaluateResultText: OpenAI.Responses.ResponseTextConfig
  private client: OpenAI

  constructor() {
    this.client = createClient()
    this.systemPrompt = JUDGE_SYSTEM_PROMPT
    this.judgePromptTemplate = JUDGE_PROMPT_TEMPLATE
    this.evaluateResultText = EVALUATE_RESULT_TEXT
  }

  /**
   * 评测接口，输入包含会话历史和自然语言评测断言，输出评测结果
   * @param input 评测输入，包含会话历史和自然语言评测断言
   * @returns 评测结果，包含是否通过和理由
   */
  async judge(input: JudgeInput): Promise<JudgeResult> {
    const judgeInput = nunjucks.renderString(this.judgePromptTemplate, input)

    console.log('Judge input:', judgeInput)

    const params: OpenAI.Responses.ResponseCreateParamsNonStreaming = {
      instructions: this.systemPrompt,
      input: judgeInput,
      text: this.evaluateResultText,
    }

    const response = await invoke(this.client, params)

    return JSON.parse(response.output_text) as JudgeResult
  }

  setClient(client: OpenAI) {
    this.client = client
  }

  setSystemPrompt(prompt: string) {
    this.systemPrompt = prompt
  }

  setJudgePromptTemplate(promptTemplate: string) {
    this.judgePromptTemplate = promptTemplate
  }

  setEvaluateResultText(config: OpenAI.Responses.ResponseTextConfig) {
    this.evaluateResultText = config
  }
}
