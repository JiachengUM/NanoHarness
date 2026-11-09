import nunjucks from 'nunjucks'
import { OpenAI, invoke, createClient } from '@eval-platform/llm'

interface HintsInput {
  profile?: string
  scene?: string
  history?: string
}

const HINTS_SYSTEM_PROMPT = `
你是一个智能对话助手。根据用户提供的人设信息、对话场景及对话历史，预测用户接下来最可能说的下一句话。

请分析对话的上下文和逻辑走向，生成3-5个最合理的用户下一句可能的发言（hints）。

要求：
1. 每个hint必须是用户（user）可能说的话
2. hints要符合对话逻辑和自然语言习惯
3. hints要有一定的多样性（可以是不同表达方式，或不同方向）
`

const HINTS_PROMPT_TEMPLATE = `
人设信息：
{{ profile }}

对话场景：
{{ scene }}

对话记录：
{{ history }}
`

// 定义 LLM 输出格式，要求输出符合 string[] 的 JSON 结构
const HINTS_TEXT: OpenAI.Responses.ResponseTextConfig = {
  format: {
    type: 'json_schema',
    name: 'hints',
    strict: true,
    schema: {
      type: 'array',
      items: {
        type: 'string',
      },
    },
  },
}

/**
 * Hints 模块负责根据对话历史和场景生成用户可能的下一句发言（hints），为评测过程提供多样化的输入选择。
 */
export default class Hints<T extends Record<string, any> = HintsInput> {
  private systemPrompt: string
  private hintsPromptTemplate: string
  private hintsText: OpenAI.Responses.ResponseTextConfig
  private client: OpenAI

  /**
   * 构造函数
   * @param systemPrompt 系统提示词
   * @param hintsPromptTemplate Hints提示词模板
   * @param hintsText 输出格式配置
   * @param client LLM 客户端实例
   */
  constructor(
    systemPrompt: string = HINTS_SYSTEM_PROMPT,
    hintsPromptTemplate: string = HINTS_PROMPT_TEMPLATE,
    hintsText: OpenAI.Responses.ResponseTextConfig = HINTS_TEXT,
    client: OpenAI = createClient(),
  ) {
    this.systemPrompt = systemPrompt
    this.hintsPromptTemplate = hintsPromptTemplate
    this.hintsText = hintsText
    this.client = client
  }

  /**
   * 根据输入生成多个hints
   * @param input HintsInput 包含人设信息、对话场景和对话历史等内容
   * @returns 符合输入上下文的多个用户下一句可能的发言（hints）列表
   */
  async generate(input: T): Promise<string[]> {
    const hintsPrompt = nunjucks.renderString(this.hintsPromptTemplate, input)

    const params: OpenAI.Responses.ResponseCreateParamsNonStreaming = {
      instructions: this.systemPrompt,
      input: hintsPrompt,
      text: this.hintsText,
    }

    const response = await invoke(this.client, params)

    return JSON.parse(response.output_text) as string[]
  }

  /**
   * 根据输入生成一个随机选择的hint
   * @param input T 包含人设信息、对话场景和对话历史等内容
   * @returns 随机选择的hint字符串
   */
  async generateOne(input: T): Promise<string> {
    const hints = await this.generate(input)
    return hints[Math.floor(Math.random() * hints.length)] || ''
  }
}
