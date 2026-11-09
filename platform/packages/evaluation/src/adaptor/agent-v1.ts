import { sseStream } from '../request/sse'
import AgentAdaptor from './base'

interface Params {
  session_id: string
  query: string
  config: unknown // todo: 待定义
}

interface EventBase {
  type: string
  event_id?: string
  timestamp?: string
}

interface TextDoneEvent extends EventBase {
  type: 'react.text.done'
  text: string
}

interface ToolCallStartEvent extends EventBase {
  type: 'react.tool_call.start'
  name: string
  arguments: string
  round: number
}

interface ToolCallsDoneEvent extends EventBase {
  type: 'react.tool_results.done'
  tool_results: string[]
  round: number
}

interface ReActFinishEvent extends EventBase {
  type: 'react.finish'
  response: unknown
  round: number
  forced: boolean
  reason: string
}

interface ReActErrorEvent extends EventBase {
  type: 'react.error'
  reason: string
}

type AgentV1Event = TextDoneEvent | ToolCallStartEvent | ToolCallsDoneEvent | ReActFinishEvent | ReActErrorEvent

const AGENT_V1_URL = 'https://ai-mind-web-dev.extour-inc.com/api/complex_reasoning_run/base_agent_stream'
const AGENT_V1_METHOD = 'POST'

const DEFAULT_AGENT_CONFIG = {
  model: 'SEED_1_8_251228',
  params: {
    temperature: 0.3,
    top_p: 0.7,
    thinking: {
      type: 'disabled',
    },
    caching: {
      type: 'disabled',
    },
  },
  tools: [
    'car_control',
    'media',
    'navigation',
    'qq_music_song_search',
    'qq_music_playlist_search',
    'qq_music_album_search',
    'poi_search',
    'weather_agent',
    'websearch',
  ],
  max_turns: 5,
  system_prompt: {
    role: '你是车载助手，完全遵循用户要求，回复时保持极简极简极简极简。',
    guidelines: [
      '音乐场景可以利用车辆状态和用户偏好进行适当联想和关联',
      '别忘了音乐执行控制和推荐理由',
      '周边搜索必须提供地址',
      '有明确导航意图并且有目的地时直接导航',
      '歌曲播放支持单首，歌单包含多首歌曲',
      '当用户询问歌单时，将歌曲整理成歌单',
      '最新歌曲或榜单指的是最近public_time',
      '联网检索时不做模糊POI检索、垂直领域（电商、本地生活攻略）',
      '打算调用工具前，请仔细思考用户是否提供了足够调用工具的信息。如缺失，请礼貌地询问用户。询问要简短，不要罗列工具细节',
    ],
  },
  memory_config: {
    user_info: {
      user_id: 'dzy_SGM交付测试员',
      user_name: '窦',
      assistant_id: 'Jarvis',
      assistant_name: '贾维斯',
    },
    producer_config: {
      collection_id: {
        collection_name: 'test_prompt',
      },
      memory_type: ['steward_note_book', 'event_v1'],
    },
    consumer_config: {
      collection_id: {
        collection_name: 'test_prompt',
      },
      system_prompt_profile_types: ['steward_note_book'],
      search_profile_types: ['skills'],
      event_types: ['event_v1'],
      profile_limit: 10,
      event_limit: 10,
    },
    session_size: 5,
  },
  user_profile: {
    user_type: '单身职场女性',
    personal_status: ['单身', '可能有稳定伴侣但未同居', '无子女'],
    residence: '上海市浦东新区陆家嘴滨江住宅区（高端公寓）',
    career_identity: ['互联网公司产品设计师/UI设计师', '工作地点：浦东新区世纪大道1000号'],
    daily_behavior: [
      '通勤时间：07:00-09:00',
      '工作时间：09:00-18:00',
      '健身时间：18:00-20:00',
      '社交时间：20:00-24:00',
      '夜生活活跃',
    ],
    personality_traits: ['外向开放', '注重自我投资', '追求品质生活', '社交活跃', '文艺气质', '独立自主'],
    interests_hobbies: [
      '独立音乐/民谣（网易云音乐）',
      '健身/瑜伽',
      '社交/夜生活',
      '购物/时尚',
      '旅行/摄影',
      '可能有宠物',
    ],
    travel_pattern: ['通勤占约25%', '社交购物娱乐占约75%', '以个人享受为中心的都市生活方式'],
    vehicle_usage: ['空调温度均值25.2℃', '风量2.8档', '车控依赖度28%', '对舒适度较敏感'],
    media_preference: ['网易云音乐占比32%', '流行音乐、独立音乐', '常听艺人：陈粒、苏打绿、告五人、田馥甄、房东的猫'],
  },
}

class AgentV1Adaptor extends AgentAdaptor {
  private url = AGENT_V1_URL
  private method = AGENT_V1_METHOD

  constructor() {
    super()
  }

  public async invoke(query: string) {
    const params: Params = {
      session_id: this.getSessionId(),
      query,
      config: DEFAULT_AGENT_CONFIG,
    }

    this.addHistory('user', query)

    try {
      for await (const e of sseStream<Params, AgentV1Event>(this.url, this.method, params)) {
        switch (e.type) {
          case 'react.text.done':
            this.addHistory('assistant', e.text)

            console.log('react.text.done:', e.text)
            break
          case 'react.tool_call.start':
            this.addHistory('tool_call', {
              name: e.name,
              arguments: e.arguments,
            })

            // console.log('react.tool_call.start:', e)
            break
          case 'react.tool_results.done':
            this.addHistory('tool_results', {
              tool_results: e.tool_results,
            })
            // console.log('react.tool_results.done:', e)
            break
          // case 'react.finish':
          //   console.log('Received finish event:', e)
          //   break
          case 'react.error':
            // console.log('react.error:', e)
            this.addHistory('react_error', `Error: ${e.reason}`)
            break
          default:
          // console.log('Unknown event type:', e)
        }
      }
    } finally {
      console.log('SSE connection closed')
    }

    return this.history
  }
}

export default AgentV1Adaptor
