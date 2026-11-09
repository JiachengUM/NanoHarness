import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
// import { CACHING_TYPE_OPTIONS, THINK_TYPE_OPTIONS } from '@/constants/agent'
import { useOptions } from '@/hooks/options'
import Api from '@/apis/task-data'
import { Button, Radio } from 'antd'
import { DEFAULT_AGENT_CONFIG } from '@/constants/agent'

type Props = {
  value?: AgentConfig
  disabled?: boolean
  modelList?: { name: string; value: string }[]
  memoryType?: 'user_profile' | 'memory_config'
  setMemoryType?: (value: 'user_profile' | 'memory_config') => void
  onChange?: (value: AgentConfig) => void
  onCancel?: () => void
}

const App = (props: Props) => {
  const { memoryType, setMemoryType } = props
  const [formData, setFormData] = useState<AgentConfig>({})
  const [systemPrompt, setSystemPrompt] = useState<SystemPrompt>()
  const isInternalChange = useRef(false)
  const [toolOptions] = useOptions<string>(Api.complexReasoning.tools, undefined, (e) => ({ label: e, value: e }))

  const modelOptions = useMemo(
    () => props.modelList?.map((e) => ({ label: e.name, value: e.name })) || [],
    [props.modelList]
  )

  const formList: FormItem[] = useMemo(() => {
    const list: FormItem[] = [
      {
        label: '模型名称',
        name: 'model',
        type: 'autoComplete',
        placeholder: '请输入模型名称',
        options: modelOptions,
        col: 2,
      },
      {
        label: '最大轮次',
        name: 'max_turns',
        type: 'number',
        props: { min: 1, precision: 0 },
      },
      {
        label: '工具列表',
        name: 'tools',
        type: 'select',
        placeholder: '请选择使用工具',
        options: toolOptions,
        props: {
          mode: 'multiple',
        },
        col: 2,
      },
      {
        label: '模型参数',
        name: 'params',
        type: 'title',
      },
      {
        label: 'temperature',
        name: ['params', 'temperature'],
        type: 'number',
      },
      {
        label: 'top_p',
        name: ['params', 'top_p'],
        type: 'number',
      },
      // {
      //   label: '深度思考',
      //   name: ['params', 'thinking', 'type'],
      //   type: 'radio',
      //   options: THINK_TYPE_OPTIONS,
      // },
      // {
      //   label: '启用缓存',
      //   name: ['params', 'caching', 'type'],
      //   type: 'radio',
      //   options: CACHING_TYPE_OPTIONS,
      //   col: 2,
      // },
      // {
      //   label: '结果存储',
      //   name: ['params', 'store'],
      //   type: 'switch',
      // },
      // {
      //   label: '最大输出token',
      //   name: ['params', 'max_output_tokens'],
      //   type: 'number',
      // },
      // {
      //   label: '模型指令',
      //   name: ['params', 'instructions'],
      //   type: 'textarea',
      //   col: 2,
      // },
      { label: '系统提示词', name: 'system_prompt', type: 'title', col: 2 },
      {
        label: '角色提示词',
        name: ['system_prompt', 'role'],
        type: 'textarea',
        placeholder: '请输入角色提示词',
        col: 2,
      },
      {
        label: '提示词指令',
        name: ['system_prompt', 'guidelines'],
        type: 'arrayInput',
        placeholder: '请输入提示词指令',
        props: { textarea: true },
        col: 2,
      },
      {
        label: '',
        name: 'memory_config',
        type: 'title',
        col: 2,
        children: (
          <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
            <b>记忆配置</b>
            <Radio.Group
              value={memoryType}
              options={[
                { label: '用户画像', value: 'user_profile' },
                { label: '记忆配置', value: 'memory_config' },
              ]}
              size="small"
              optionType="button"
              buttonStyle="solid"
              onChange={(e) => setMemoryType?.(e.target.value)}
            />
          </div>
        ),
      },
    ]

    const userProfileList: FormItem[] = [{ label: '用户画像信息', name: 'user_profile', type: 'json', col: 2 }]

    const memoryConfigList: FormItem[] = [
      { label: 'session_size', name: ['memory_config', 'session_size'], type: 'number', col: 2 },
      { label: 'user_info', name: ['memory_config', 'user_info'], type: 'json', col: 2 },
      { label: 'producer', name: ['memory_config', 'producer_config'], type: 'json', col: 2 },
      { label: 'consumer', name: ['memory_config', 'consumer_config'], type: 'json', col: 2 },
    ]

    return memoryType === 'user_profile' ? [...list, ...userProfileList] : [...list, ...memoryConfigList]
  }, [modelOptions, toolOptions, memoryType, setMemoryType])

  const reset = () => {
    const config = {
      ...DEFAULT_AGENT_CONFIG,
      system_prompt: systemPrompt,
      tools: toolOptions.map((e) => e.value || ''),
    }
    props.onChange?.(config)
  }

  const getSystemPrompt = async () => {
    const prompt = await Api.complexReasoning.systemPrompt()
    setSystemPrompt(prompt)
  }

  useEffect(() => {
    if (isInternalChange.current) {
      isInternalChange.current = false
      return
    }
    setFormData(props.value || {})
  }, [props.value])

  useEffect(() => {
    getSystemPrompt()
  }, [])

  const formpProps: FormProps<AgentConfig> = {
    formList,
    formData,
    setFormData,
    labelWidth: 100,
    showAction: false,
    disabled: props.disabled,
    cols: 2,
    onValuesChange: (_changed, all) => {
      isInternalChange.current = true
      console.log('all', all)
      props.onChange?.(all)
    },
    onCancel: props.onCancel,
  }

  return (
    <>
      <Button type="primary" style={{ position: 'absolute', top: 10, right: 12 }} onClick={reset}>
        重置
      </Button>
      <ExForm<AgentConfig> {...formpProps} />
    </>
  )
}

export default App
