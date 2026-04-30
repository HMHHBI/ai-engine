import { defineStore } from 'pinia'
import { getProfileApi } from '@/api'

export const useUserStore = defineStore('user', {
  state: () => ({
    user: JSON.parse(localStorage.getItem('user')) || null,
    token: localStorage.getItem('token') || null,
    loading: false,
  }),

  getters: {
    isAuthenticated: (state) => !!state.token,
    userPlan: (state) => state.user?.plan || 'FREE',
  },

  actions: {
    async fetchProfile() {
      if (!this.token) return
      try {
        const data = await getProfileApi(this.token)
        this.user = data
        localStorage.setItem('user', JSON.stringify(data))
      } catch (error) {
        console.error('Profile fetch failed:', error)
        this.logout()
      }
    },

    setToken(token) {
      this.token = token
      localStorage.setItem('token', token)
    },

    logout() {
      this.user = null
      this.token = null
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    },
  },
})
