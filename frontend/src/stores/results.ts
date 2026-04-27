import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { PendingItem } from '../types'
import * as api from '../api/services'
import { useAppStore } from './app'

type FilterKind = 'notify' | 'tweet'

function isNotify(item: PendingItem) {
  return item.source === '通知页面'
}

function parseTime(text: string | undefined) {
  const m = String(text || '').match(/^(\d{1,2}):(\d{1,2}):(\d{1,2})$/)
  if (!m) return -1
  return Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3])
}

export const useResultsStore = defineStore('results', () => {
  const items = ref<PendingItem[]>([])
  const updatesLastSeq = ref(0)
  const filterText = ref<Record<FilterKind, string>>({ notify: '', tweet: '' })
  const selectedReplyByKey = ref<Record<string, string>>({})
  const selectedDmByKey = ref<Record<string, string>>({})
  const polling = ref<{ updates: number | null; sync: number | null; state: number | null }>({ updates: null, sync: null, state: null })
  let rowSeq = 0

  function assignRow(item: PendingItem) {
    return {
      ...item,
      _rowSeq: typeof item._rowSeq === 'number' ? item._rowSeq : ++rowSeq,
    }
  }

  function hydrate(pending: PendingItem[] = [], seq = 0) {
    rowSeq = 0
    items.value = (Array.isArray(pending) ? pending : []).map(assignRow)
    updatesLastSeq.value = Number(seq || 0)
  }

  function mergeItem(next: PendingItem) {
    const key = String(next.key || '')
    const existingIndex = items.value.findIndex((item) => item.key === key)
    if (existingIndex >= 0) {
      items.value[existingIndex] = {
        ...items.value[existingIndex],
        ...next,
      }
      return
    }
    items.value.unshift(assignRow(next))
  }

  function removeByKey(key: string) {
    items.value = items.value.filter((item) => item.key !== key)
  }

  const notifyItems = computed(() =>
    items.value
      .filter(isNotify)
      .filter((item) => {
        const q = filterText.value.notify.trim().toLowerCase()
        if (!q) return true
        return `${item.handle || ''} ${item.content || ''}`.toLowerCase().includes(q)
      })
      .sort((a, b) => {
        const ta = parseTime(a.time)
        const tb = parseTime(b.time)
        if (tb !== ta) return tb - ta
        return Number(b._rowSeq || 0) - Number(a._rowSeq || 0)
      }),
  )

  const tweetItems = computed(() =>
    items.value
      .filter((item) => !isNotify(item))
      .filter((item) => {
        const q = filterText.value.tweet.trim().toLowerCase()
        if (!q) return true
        return `${item.handle || ''} ${item.content || ''}`.toLowerCase().includes(q)
      }),
  )

  async function pollUpdates() {
    const data = await api.fetchUpdates(updatesLastSeq.value)
    if (Array.isArray(data.new_items)) {
      data.new_items.forEach((item: PendingItem) => mergeItem(item))
    }
    updatesLastSeq.value = Math.max(updatesLastSeq.value, Number(data.last_seq || 0))
  }

  async function syncNotifyFlow() {
    const data = await api.fetchNotifyReplies()
    if (Array.isArray(data.items)) {
      data.items.forEach((item: PendingItem) => mergeItem(item))
    }
  }

  async function syncAppState() {
    const app = useAppStore()
    const payload = await api.fetchState()
    app.hydrate(payload)
  }

  function startPolling() {
    stopPolling()
    polling.value.updates = window.setInterval(() => {
      pollUpdates().catch(() => undefined)
    }, 1000)
    polling.value.sync = window.setInterval(() => {
      syncNotifyFlow().catch(() => undefined)
    }, 6000)
    polling.value.state = window.setInterval(() => {
      syncAppState().catch(() => undefined)
    }, 5000)
  }

  function stopPolling() {
    if (polling.value.updates) window.clearInterval(polling.value.updates)
    if (polling.value.sync) window.clearInterval(polling.value.sync)
    if (polling.value.state) window.clearInterval(polling.value.state)
    polling.value = { updates: null, sync: null, state: null }
  }

  async function markDone(key: string, handle = '') {
    await api.markDone(key, handle)
    removeByKey(key)
  }

  async function retryNotify(key: string) {
    const data = await api.retryNotifyReply(key)
    const target = data.key ? data : { key, ...data }
    mergeItem(target as PendingItem)
    return data
  }

  async function sendReply(key: string, message: string, dm_message: string) {
    const data = await api.sendNotifyReply(key, message, dm_message)
    mergeItem({ key, ...data } as PendingItem)
    return data
  }

  async function clear(kind: FilterKind) {
    await api.clearResults(kind)
    items.value = items.value.filter((item) => (kind === 'notify' ? !isNotify(item) : isNotify(item)))
  }

  async function clearAllBlocklist() {
    return api.clearBlocklist()
  }

  return {
    items,
    updatesLastSeq,
    filterText,
    selectedReplyByKey,
    selectedDmByKey,
    notifyItems,
    tweetItems,
    hydrate,
    mergeItem,
    startPolling,
    stopPolling,
    markDone,
    retryNotify,
    sendReply,
    clear,
    clearAllBlocklist,
    syncNotifyFlow,
    syncAppState,
  }
})
