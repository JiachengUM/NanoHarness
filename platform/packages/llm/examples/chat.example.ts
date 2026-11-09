import { Chat } from '../src/chat'

export async function chatExample() {
  const queryList = ['你好，我是王小明，今年23岁，喜欢编程', '你还记得我吗？']
  const queryList2 = ['我是谁？']

  const chat = new Chat()

  console.log('=== 第一次对话 ===')
  for (const query of queryList) {
    console.log('User:', query)
    const response = await chat.invoke(query)
    console.log('Assistant:', response)
  }

  const history = chat.getHistory()
  console.log('对话历史:', history)

  chat.newSession()

  console.log('\n=== 第二次对话 ===')
  for (const query of queryList2) {
    console.log('User:', query)
    const response = await chat.invoke(query)
    console.log('Assistant:', response)
  }

  const history2 = chat.getHistory()
  console.log('对话历史:', history2)
}

export async function chatStreamExample() {
  const queryList = ['你好，我是王小明，今年23岁，喜欢编程', '你还记得我吗？']
  const queryList2 = ['我是谁？']

  const chat = new Chat()

  console.log('=== 第一次对话 ===')
  for (const query of queryList) {
    console.log('\nUser:', query)
    console.log('Assistant (stream):')
    for await (const data of chat.stream(query)) {
      process.stdout.write(data) // 实时输出增量数据,不换行
    }
  }

  const history = chat.getHistory()
  console.log('\n对话历史:', history)

  chat.newSession()

  console.log('\n=== 第二次对话 ===')
  for (const query of queryList2) {
    console.log('\nUser:', query)
    console.log('Assistant (stream):')
    for await (const data of chat.stream(query)) {
      process.stdout.write(data) // 实时输出增量数据，不换行
    }
  }

  const history2 = chat.getHistory()
  console.log('\n对话历史:', history2)
}

chatStreamExample()
