import { describe, it, expect } from 'vitest'
import { Chat } from '../src/chat'

describe('Chat', () => {
  describe('invoke', () => {
    it('should maintain conversation context across multiple turns', async () => {
      const chat = new Chat()
      const queryList = ['你好，我是王小明，今年23岁，喜欢编程', '你还记得我吗？']

      let response: string
      for (const query of queryList) {
        response = await chat.invoke(query)
        expect(response).toBeDefined()
        expect(typeof response).toBe('string')
        expect(response.length).toBeGreaterThan(0)
      }

      const history = chat.getHistory()
      expect(history.length).toBe(4)
      expect(history[0].role).toBe('user')
      expect(history[1].role).toBe('assistant')
    })

    it('should reset context when new_session is called', async () => {
      const chat = new Chat()

      await chat.invoke('你好，我是王小明，今年23岁，喜欢编程')
      expect(chat.getHistory().length).toBe(2)

      chat.newSession()
      expect(chat.getHistory().length).toBe(0)

      const response = await chat.invoke('我是谁？')
      expect(response).toBeDefined()
      expect(chat.getHistory().length).toBe(2)
    })
  })

  describe('stream', () => {
    it('should stream response chunks', async () => {
      const chat = new Chat()
      const queryList = ['你好，我是王小明，今年23岁，喜欢编程', '你还记得我吗？']

      for (const query of queryList) {
        const chunks: string[] = []
        for await (const chunk of chat.stream(query)) {
          chunks.push(chunk)
          expect(typeof chunk).toBe('string')
        }
        expect(chunks.length).toBeGreaterThan(0)
      }

      const history = chat.getHistory()
      expect(history.length).toBe(4)
    })

    it('should reset context when newSession is called', async () => {
      const chat = new Chat()

      for await (const _ of chat.stream('你好，我是王小明')) {
        // consume stream
      }
      expect(chat.getHistory().length).toBe(2)

      chat.newSession()
      expect(chat.getHistory().length).toBe(0)

      for await (const _ of chat.stream('我是谁？')) {
        // consume stream
      }
      expect(chat.getHistory().length).toBe(2)
    })
  })
})
