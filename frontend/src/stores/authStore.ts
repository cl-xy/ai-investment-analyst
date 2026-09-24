import { create } from 'zustand'
import axios from 'axios'
import { API_BASE, clearSessionToken, getSessionToken, setSessionToken } from '../api/config'

interface AuthStore {
  isAuthenticated: boolean
  error: string | null
  loading: boolean
  login: (username: string, password: string) => Promise<boolean>
  logout: () => void
}

export const useAuthStore = create<AuthStore>((set) => ({
  isAuthenticated: !!getSessionToken(),
  error: null,
  loading: false,

  login: async (username, password) => {
    set({ loading: true, error: null })
    try {
      const response = await axios.post<{ token: string }>(`${API_BASE}/api/auth/login`, {
        username,
        password,
      })
      setSessionToken(response.data.token)
      set({ isAuthenticated: true, loading: false, error: null })
      return true
    } catch {
      set({ isAuthenticated: false, loading: false, error: 'Invalid username or password' })
      return false
    }
  },

  logout: () => {
    clearSessionToken()
    set({ isAuthenticated: false })
  },
}))

// Expired/invalid session token: drop it so the login screen reappears,
// instead of leaving the user stuck on a page full of failed requests.
axios.interceptors.response.use(
  (response) => response,
  (error) => {
    const isLoginRequest = typeof error.config?.url === 'string' && error.config.url.includes('/api/auth/login')
    if (error.response?.status === 401 && getSessionToken() && !isLoginRequest) {
      useAuthStore.getState().logout()
    }
    return Promise.reject(error)
  }
)
