import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

interface SystemStore {
  username?: string
  currentUser?: FeishuUser
  setUsername: (username: string) => void
  setCurrentUser: (user?: FeishuUser) => void
  clearCurrentUser: () => void
}

// Only persist these keys
const persistKeys: string[] = ['username', 'currentUser']
const useSystemStore = create<SystemStore>()(
  persist(
    (set) => ({
      username: undefined,
      currentUser: undefined,
      setUsername: (username: string) => {
        set({ username })
      },
      setCurrentUser: (user?: FeishuUser) => {
        set({ currentUser: user, username: user?.name })
      },
      clearCurrentUser: () => {
        set({ currentUser: undefined, username: undefined })
      },
    }),
    {
      name: 'system',
      partialize: (state) => Object.fromEntries(Object.entries(state).filter(([key]) => persistKeys.includes(key))),
      storage: createJSONStorage(() => localStorage),
    }
  )
)

export default useSystemStore
