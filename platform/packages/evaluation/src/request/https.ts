import axios from 'axios'
import type { AxiosInstance, AxiosResponse, AxiosError } from 'axios'

export const BASE_URL = '/api'

const http: AxiosInstance = axios.create({
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.request.use(
  (config) => {
    return config
  },
  (error: AxiosError | Error) => {
    return Promise.reject(error)
  },
)

http.interceptors.response.use(
  <T>(response: AxiosResponse<T>) => {
    return response.data
  },
  async (error: AxiosError | Error) => {
    return Promise.reject(error)
  },
)
