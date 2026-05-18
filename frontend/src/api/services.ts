import { apiGet, apiPost } from './client'
import type { DmRecentContactsPayload, StatePayload } from '../types'

export const fetchState = () => apiGet<StatePayload>('/api/state')
export const startMonitor = (token: string) => apiPost('/api/start', { token })
export const stopMonitor = () => apiPost('/api/stop', {})
export const toggleNotification = (enabled: boolean) => apiPost('/api/toggle_notification', { enabled })
export const toggleHeadless = (enabled: boolean) => apiPost('/api/toggle_headless', { enabled })
export const setDelegatedAccount = (account: string) => apiPost('/api/set_delegated_account', { account })
export const setEnterpriseWechatWebhook = (webhookUrl: string) =>
  apiPost('/api/set_enterprise_wechat_webhook', { webhook_url: webhookUrl })
export const openRepliesPage = (handle: string) => apiPost('/api/open_user_replies_page', { handle })
export const addTask = (url: string) => apiPost('/api/task/add', { url })
export const removeTask = (url: string) => apiPost('/api/task/remove', { url })
export const clearResults = (type: 'notify' | 'tweet' | 'all') => apiPost('/api/clear_results', { type })
export const clearBlocklist = () => apiPost('/api/clear_blocklist', {})
export const fetchUpdates = (sinceSeq: number) => apiGet(`/api/updates?since_seq=${encodeURIComponent(String(sinceSeq || 0))}`)
export const fetchNotifyReplies = (limit = 2000) => apiGet(`/api/notify_replies?limit=${limit}`)
export const sendNotifyReply = (key: string, message: string, dm_message: string) =>
  apiPost('/api/notify_reply', { key, message, dm_message })
export const retryNotifyReply = (key: string, message = '', dm_message = '') =>
  apiPost('/api/notify_retry', { key, message, dm_message })
export const markDone = (key: string, handle = '') => apiPost('/api/mark_done', { key, handle })
export const templateAdd = (type: 'reply' | 'dm', content: string) => apiPost('/api/template/add', { type, content })
export const templateUpdate = (type: 'reply' | 'dm', index: number, content: string) =>
  apiPost('/api/template/update', { type, index, content })
export const templateDelete = (type: 'reply' | 'dm', index: number) => apiPost('/api/template/delete', { type, index })
export const saveNotifyTtsConfig = (payload: Record<string, unknown>) => apiPost('/api/set_notify_tts_config', payload)
export const testNotifyTtsConfig = (text: string) => apiPost('/api/notify_tts/test', { text })
export const synthesizeTts = (text: string) => apiPost('/api/tts/synthesize', { text, source: 'notify_voice' })
export const saveLlmFilterConfig = (payload: Record<string, unknown>) => apiPost('/api/set_llm_filter_config', payload)
export const testLlmModel = (payload: Record<string, unknown>) => apiPost('/api/llm_filter/test', payload)
export const analyzeIntent = (payload: Record<string, unknown>) => apiPost('/api/llm_filter/analyze', payload)
export const getRecentDmContacts = () => apiGet<DmRecentContactsPayload>('/api/dm/recent_contacts')
export const fetchRecentDmContacts = (windowHours = 24) =>
  apiPost<DmRecentContactsPayload>('/api/dm/recent_contacts', { window_hours: windowHours })
export const pushDailyDmContactsTest = () => apiPost('/api/dm/recent_contacts/push_daily_test', {})
