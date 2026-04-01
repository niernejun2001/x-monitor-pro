import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as api from '../api/services'

export const useTemplatesStore = defineStore('templates', () => {
  const replyTemplates = ref<string[]>([])
  const dmTemplates = ref<string[]>([])
  const editIndex = ref<{ reply: number; dm: number }>({ reply: -1, dm: -1 })

  function hydrate(payload: { notify_reply_templates?: string[]; dm_message_templates?: string[] }) {
    replyTemplates.value = Array.isArray(payload.notify_reply_templates) ? [...payload.notify_reply_templates] : []
    dmTemplates.value = Array.isArray(payload.dm_message_templates) ? [...payload.dm_message_templates] : []
  }

  function setEdit(type: 'reply' | 'dm', index: number) {
    editIndex.value[type] = index
  }

  function cancelEdit(type: 'reply' | 'dm') {
    editIndex.value[type] = -1
  }

  async function add(type: 'reply' | 'dm', content: string) {
    const data = await api.templateAdd(type, content)
    hydrate(data)
    cancelEdit(type)
    return data
  }

  async function update(type: 'reply' | 'dm', index: number, content: string) {
    const data = await api.templateUpdate(type, index, content)
    hydrate(data)
    cancelEdit(type)
    return data
  }

  async function remove(type: 'reply' | 'dm', index: number) {
    const data = await api.templateDelete(type, index)
    hydrate(data)
    cancelEdit(type)
    return data
  }

  return { replyTemplates, dmTemplates, editIndex, hydrate, setEdit, cancelEdit, add, update, remove }
})
