import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ToastType = 'success' | 'error' | 'info'

export interface ToastItem {
  id: number
  type: ToastType
  message: string
}

export const useToastStore = defineStore('toast', () => {
  const items = ref<ToastItem[]>([])
  let nextId = 1

  function push(message: string, type: ToastType = 'info', ttl = 2800) {
    const id = nextId++
    items.value.push({ id, type, message })
    if (ttl > 0) {
      window.setTimeout(() => remove(id), ttl)
    }
  }

  function remove(id: number) {
    items.value = items.value.filter((item) => item.id !== id)
  }

  return { items, push, remove }
})
