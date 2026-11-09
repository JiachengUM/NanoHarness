export const THINK_TYPE_OPTIONS = [
  { label: '启用', value: 'enabled' },
  { label: '禁用', value: 'disabled' },
]

export const CACHING_TYPE_OPTIONS = [
  { label: '启用', value: 'enabled' },
  { label: '禁用', value: 'disabled' },
  { label: '自动', value: 'auto' },
]

export const DEFAULT_AGENT_CONFIG: AgentConfig = {
  model: 'SEED_1_8_251228',
  params: {
    temperature: 0.3,
    top_p: 0.7,
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

export const TASK_CONFIG: AgentInstanceDump = {
  system_prompt: DEFAULT_AGENT_CONFIG.system_prompt,
  run_params: {
    model: 'doubao-seed-1-8-251228',
    params: DEFAULT_AGENT_CONFIG.params,
    max_turns: DEFAULT_AGENT_CONFIG.max_turns,
  },
  tools_names: DEFAULT_AGENT_CONFIG.tools,
  memory: DEFAULT_AGENT_CONFIG.memory_config,
  user_profile: DEFAULT_AGENT_CONFIG.user_profile,
}
