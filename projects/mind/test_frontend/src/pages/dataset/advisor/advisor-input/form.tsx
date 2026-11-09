import { useEffect, useState } from 'react'
import Api from '@/apis/task-data'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
import { useAdvisorDomainOptions } from '@/hooks/domain-options'

const defaultForm: AdvisorInput = {}

type Props = {
  formData?: AdvisorInput
  onSuccess?: () => void
  onCancel?: () => void
}

const App = (props: Props) => {
  const [formData, setFormData] = useState<AdvisorInput>(defaultForm)
  const options = useAdvisorDomainOptions()

  const formList: FormItem[] = [
    { label: '事件信息', name: 'event', type: 'input', required: true },
    { label: '用户画像', name: ['context', 'user'], type: 'json', options: options.user },
    { label: '记忆信息', name: ['context', 'memory'], type: 'json', options: options.memory },
    { label: '世界信息', name: ['context', 'world_info'], type: 'json', options: options.world_info },
    { label: '车辆状态', name: ['context', 'vehicle_state'], type: 'json', options: options.vehicle_state },
    { label: '外部视觉', name: ['context', 'visual_exterior'], type: 'json', options: options.visual_ext },
    { label: '内部视觉', name: ['context', 'visual_interior'], type: 'json', options: options.visual_int },
  ]

  // const onFinish = (values: AdvisorInput) => {
  //   const context = values.context || ({} as AdvisorContext)
  //   context.user = options.user?.find((item) => item.value === context.user)?.data as User
  //   context.memory = options.memory?.find((item) => item.value === context.memory)?.data as EpisodicMemory
  //   context.world_info = options.world_info?.find((item) => item.value === context.world_info)?.data as WorldInfo
  //   context.vehicle_state = options.vehicle_state?.find((item) => item.value === context.vehicle_state)
  //     ?.data as VehicleState
  //   context.visual_exterior = options.visual_ext?.find((item) => item.value === context.visual_exterior)
  //     ?.data as VisualExterior
  //   context.visual_interior = options.visual_int?.find((item) => item.value === context.visual_interior)
  //     ?.data as VisualInterior
  //   values.context = context

  //   return values
  // }

  useEffect(() => {
    if (!options) return

    const formData = JSON.parse(JSON.stringify(props.formData || defaultForm)) as AdvisorInput

    // if (formData.context?.user)
    //   formData.context.user = options.user?.find((item) => {
    //     console.log(item.data, formData.context?.user)
    //     return JSON.stringify(item.data) === JSON.stringify(formData.context?.user)
    //   })?.value

    // if (formData.context?.memory)
    //   formData.context.memory = options.memory?.find((item) => {
    //     return JSON.stringify(item.data) === JSON.stringify(formData.context?.memory)
    //   })?.value

    // if (formData.context?.world_info)
    //   formData.context.world_info = options.world_info?.find((item) => {
    //     return JSON.stringify(item.data) === JSON.stringify(formData.context?.world_info)
    //   })?.value

    // if (formData.context?.vehicle_state)
    //   formData.context.vehicle_state = options.vehicle_state?.find((item) => {
    //     return JSON.stringify(item.data) === JSON.stringify(formData.context?.vehicle_state)
    //   })?.value

    // if (formData.context?.visual_exterior)
    //   formData.context.visual_exterior = options.visual_ext?.find((item) => {
    //     return JSON.stringify(item.data) === JSON.stringify(formData.context?.visual_exterior)
    //   })?.value

    // if (formData.context?.visual_interior)
    //   formData.context.visual_interior = options.visual_int?.find((item) => {
    //     return JSON.stringify(item.data) === JSON.stringify(formData.context?.visual_interior)
    //   })?.value

    setFormData(formData)
  }, [props.formData, options])

  const formpProps: FormProps<AdvisorInput> = {
    formList,
    formData,
    setFormData,
    createApi: Api.advisorInput.create,
    updateApi: Api.advisorInput.update,
    onCancel: props.onCancel,
    onSuccess: props.onSuccess,
  }

  return (
    <>
      <ExForm<AdvisorInput> {...formpProps} />
    </>
  )
}

export default App
