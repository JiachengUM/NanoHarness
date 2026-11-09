import { describe, it, expect } from 'vitest'
import OpenAI from 'openai'
import { invoke, stream } from '../src/responses'
import { createClient } from '../src/client'

describe('response', () => {
  const query = '王小明，23岁，性别男，喜欢编程'

  describe('invoke', () => {
    it('should return a response with json_schema format', async () => {
      const client = createClient()

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

      expect(response).toBeDefined()
      expect(response.output_text).toBeDefined()

      const parsed = JSON.parse(response.output_text)
      expect(parsed).toHaveProperty('name')
      expect(parsed).toHaveProperty('age')
      expect(typeof parsed.name).toBe('string')
      expect(typeof parsed.age).toBe('number')
    })
  })

  describe('stream', () => {
    it('should return stream events', async () => {
      const client = createClient()
      const params = {
        instructions: '你是一个智能助手',
        input: query,
      }

      const events = await stream(client, params)

      let eventCount = 0
      for await (const event of events) {
        expect(event).toBeDefined()
        expect(event.type).toBeDefined()
        eventCount++
      }

      expect(eventCount).toBeGreaterThan(0)
    })
  })
})
