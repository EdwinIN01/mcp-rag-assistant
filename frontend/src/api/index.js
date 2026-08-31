import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import router from '../router'

// axios 实例：自动携带 JWT，401 统一登出
const api = axios.create({ baseURL: '/api/v1', timeout: 180000 })

api.interceptors.request.use((cfg) => {
  const auth = useAuthStore()
  if (auth.token) cfg.headers.Authorization = `Bearer ${auth.token}`
  return cfg
})

api.interceptors.response.use(
  (resp) => resp,
  (err) => {
    const status = err.response?.status
    if (status === 401) {
      const auth = useAuthStore()
      auth.logout()
      ElMessage.error('登录已失效，请重新登录')
      router.push({ name: 'login' })
    } else {
      const detail = err.response?.data?.detail
      ElMessage.error(typeof detail === 'string' ? detail : `请求失败（${status || '网络错误'}）`)
    }
    return Promise.reject(err)
  }
)

export default api
