import OpenAI from 'openai'
import { invoke, stream } from '../src/responses'
import { createClient } from '../src/client'

export async function invokeExample(query: string) {
  const client = await createClient()

  const params: OpenAI.Responses.ResponseCreateParamsNonStreaming = {
    instructions: '你是一个智能助手',
    input: query,
    text: {
      format: {
        type: 'json_schema',
        name: 'person',
        strict: true,
        schema: {
          type: 'object',
          properties: {
            name: {
              type: 'string',
              minLength: 1,
            },
            age: {
              type: 'number',
              minimum: 0,
              maximum: 130,
            },
            hobbies: {
              type: 'array',
              items: {
                type: 'string',
              },
            },
          },
          required: ['name', 'age'],
          additionalProperties: false,
        },
      },
    },
  }

  const response = await invoke(client, params)
  console.log(response)
}

export async function streamExample(query: string) {
  const client = await createClient()
  const params = {
    instructions: '你是一个智能助手',
    input: query,
  }

  const events = await stream(client, params)

  for await (const event of events) {
    console.log(event)
  }

  console.log('LLM response test completed.')
}

function main() {
  const query = '王小明，23岁，性别男，喜欢编程'
  invokeExample(query)
  // streamExample(query)
}

main()
