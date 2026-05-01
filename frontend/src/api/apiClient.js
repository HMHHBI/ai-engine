import axios from 'axios'
import { useUserStore } from '@/stores/userStore'
import { useUIStore } from '@/stores/uiStore'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
})

// REQUEST INTERCEPTOR: Har request se pehle token khud lagaye ga
apiClient.interceptors.request.use((config) => {
  const userStore = useUserStore()
  if (userStore.token) {
    config.headers.Authorization = `Bearer ${userStore.token}`
  }
  return config
})

// RESPONSE INTERCEPTOR: 401 aur 429 ko aik hi jagah handle karega
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const userStore = useUserStore()
    const uiStore = useUIStore()

    // 1. Agar 401 (Unauthorized) aaye -> Logout
    if (error.response?.status === 401) {
      uiStore.addToast('Session expired. Logging out...', 'error')
      userStore.logout()
    }

    // 2. Agar 429 (Rate Limit) aaye -> Friendly Message
    if (error.response?.status === 429) {
      uiStore.addToast('AI is busy (Rate Limit). Please wait a few seconds.', 'error')
    }

    return Promise.reject(error)
  },
)

export default apiClient
