import { get, post, put, del, BASE_URL } from '@/request/https'

export default {
  user: {
    page: (params?: PageParams<User>) => get<PageList<User>>(`${BASE_URL}/users/page`, params),
    list: (params?: User) => get<User[]>(`${BASE_URL}/users/list`, params),
    create: (data: User) => post<User>(`${BASE_URL}/users`, data),
    update: (data: User) => put<User>(`${BASE_URL}/users/${data.id}`, data),
    del: (id: string) => del<void>(`${BASE_URL}/users/${id}`),
  },
  vehicleState: {
    page: (params?: PageParams<VehicleState>) => get<PageList<VehicleState>>(`${BASE_URL}/vehicle_state/page`, params),
    list: (params?: VehicleState) => get<VehicleState[]>(`${BASE_URL}/vehicle_state/list`, params),
    create: (data: VehicleState) => post<VehicleState>(`${BASE_URL}/vehicle_state`, data),
    update: (data: VehicleState) => put<VehicleState>(`${BASE_URL}/vehicle_state/${data.id}`, data),
    del: (id: string) => del<void>(`${BASE_URL}/vehicle_state/${id}`),
  },
  worldInfo: {
    page: (params?: PageParams<WorldInfo>) => get<PageList<WorldInfo>>(`${BASE_URL}/world_info/page`, params),
    list: (params?: WorldInfo) => get<WorldInfo[]>(`${BASE_URL}/world_info/list`, params),
    create: (data: WorldInfo) => post<WorldInfo>(`${BASE_URL}/world_info`, data),
    update: (data: WorldInfo) => put<WorldInfo>(`${BASE_URL}/world_info/${data.id}`, data),
    del: (id: string) => del<void>(`${BASE_URL}/world_info/${id}`),
  },
  memory: {
    page: (params?: PageParams<EpisodicMemory>) => get<PageList<EpisodicMemory>>(`${BASE_URL}/memory/page`, params),
    list: (params?: EpisodicMemory) => get<EpisodicMemory[]>(`${BASE_URL}/memory/list`, params),
    create: (data: EpisodicMemory) => post<EpisodicMemory>(`${BASE_URL}/memory`, data),
    update: (data: EpisodicMemory) => put<EpisodicMemory>(`${BASE_URL}/memory/${data.id}`, data),
    del: (id: string) => del<void>(`${BASE_URL}/memory/${id}`),
  },
  visualExt: {
    page: (params?: PageParams<VisualExterior>) => get<PageList<VisualExterior>>(`${BASE_URL}/visual_ext/page`, params),
    list: (params?: VisualExterior) => get<VisualExterior[]>(`${BASE_URL}/visual_ext/list`, params),
    create: (data: VisualExterior) => post<VisualExterior>(`${BASE_URL}/visual_ext`, data),
    update: (data: VisualExterior) => put<VisualExterior>(`${BASE_URL}/visual_ext/${data.id}`, data),
    del: (id: string) => del<void>(`${BASE_URL}/visual_ext/${id}`),
  },
  visualInt: {
    page: (params?: PageParams<VisualInterior>) => get<PageList<VisualInterior>>(`${BASE_URL}/visual_int/page`, params),
    list: (params?: VisualInterior) => get<VisualInterior[]>(`${BASE_URL}/visual_int/list`, params),
    create: (data: VisualInterior) => post<VisualInterior>(`${BASE_URL}/visual_int`, data),
    update: (data: VisualInterior) => put<VisualInterior>(`${BASE_URL}/visual_int/${data.id}`, data),
    del: (id: string) => del<void>(`${BASE_URL}/visual_int/${id}`),
  },
  contextLog: {
    page: (params?: PageParams<ContextLog>) => get<PageList<ContextLog>>(`${BASE_URL}/context-log/page`, params),
    list: (params?: ContextLog) => get<ContextLog[]>(`${BASE_URL}/context-log/list`, params),
  },
}
