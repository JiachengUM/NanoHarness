import Api from '@/apis/domain-data'
import { useOptions } from './options'
import { useMemo } from 'react'

type AdvisorDomainOptions = {
  vehicle_state: OptionItem<string>[]
  world_info: OptionItem<string>[]
  user: OptionItem<string>[]
  memory: OptionItem<string>[]
  visual_ext: OptionItem<string>[]
  visual_int: OptionItem<string>[]
}

export const useAdvisorDomainOptions = (): AdvisorDomainOptions => {
  const [vehicleStateOptions] = useOptions<VehicleState>(Api.vehicleState.list, {}, (item) => {
    return { label: item.brief, value: item.id, data: item.entity }
  })

  const [worldInfoOptions] = useOptions<WorldInfo>(Api.worldInfo.list, {}, (item) => {
    return { label: item.brief, value: item.id, data: item.entity }
  })

  const [userOptions] = useOptions<User>(Api.user.list, {}, (item) => {
    return { label: item.brief, value: item.id, data: item.entity }
  })

  const [memoryOptions] = useOptions<EpisodicMemory>(Api.memory.list, {}, (item) => {
    return { label: item.brief, value: item.id, data: item.entity }
  })

  const [visualExtOptions] = useOptions<VisualExterior>(Api.visualExt.list, {}, (item) => {
    return { label: item.brief, value: item.id, data: item.entity }
  })

  const [visualIntOptions] = useOptions<VisualInterior>(Api.visualInt.list, {}, (item) => {
    return { label: item.brief, value: item.id, data: item.entity }
  })

  const options = useMemo(
    () => ({
      vehicle_state: vehicleStateOptions || [],
      world_info: worldInfoOptions || [],
      user: userOptions || [],
      memory: memoryOptions || [],
      visual_ext: visualExtOptions || [],
      visual_int: visualIntOptions || [],
    }),
    [vehicleStateOptions, worldInfoOptions, userOptions, memoryOptions, visualExtOptions, visualIntOptions]
  )

  return options
}
