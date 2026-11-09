import { get, post, put, del, BASE_URL } from '@/request/https'

export default {
  category: {
    page: (params?: PageParams<Category>) => get<PageList<Category>>(`${BASE_URL}/category/page`, params),
    list: (params?: Category) => get<Category[]>(`${BASE_URL}/category/list`, params),
    create: (data: Category) => post<Category>(`${BASE_URL}/category`, data),
    update: (data: Category) => put<Category>(`${BASE_URL}/category/${data.id}`, data),
    del: (id: string) => del<void>(`${BASE_URL}/category/${id}`),
  },
}
