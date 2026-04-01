import type { ComputedRef, Ref } from 'vue'
import type { PendingItem } from '../types'

interface UseResultsActionsOptions {
  results: {
    markDone: (key: string, handle?: string) => Promise<void>
    retryNotify: (key: string) => Promise<any>
    sendReply: (key: string, message: string, dmMessage: string) => Promise<any>
    syncNotifyFlow: () => Promise<void>
    clear: (kind: 'notify' | 'tweet') => Promise<void>
    clearAllBlocklist: () => Promise<any>
  }
  toast: {
    push: (message: string, tone?: string, duration?: number) => void
  }
  replyTemplates: Ref<string[]>
  dmTemplates: Ref<string[]>
  selectedReplyByKey: Ref<Record<string, string>>
  selectedDmByKey: Ref<Record<string, string>>
  filteredNotifyItems: ComputedRef<PendingItem[]>
  filteredTweetItems: ComputedRef<PendingItem[]>
  selectedNotifyByKey: Ref<Record<string, boolean>>
  selectedTweetByKey: Ref<Record<string, boolean>>
  deselectNotifyKey: (key: string) => void
  deselectTweetKey: (key: string) => void
}

export function useResultsActions(options: UseResultsActionsOptions) {
  function applyDefaultTemplate(item: PendingItem, type: 'reply' | 'dm') {
    const value = type === 'reply' ? options.replyTemplates.value[0] : options.dmTemplates.value[0]
    if (!value) {
      options.toast.push(type === 'reply' ? '暂无评论模板' : '暂无私信模板', 'error', 3200)
      return
    }
    if (type === 'reply') options.selectedReplyByKey.value[item.key] = value
    else options.selectedDmByKey.value[item.key] = value
  }

  function openTweetSource(item: PendingItem) {
    const statusUrl = String(item.status_url || '').trim()
    if (statusUrl) {
      window.open(statusUrl, '_blank', 'noopener,noreferrer')
      return
    }
    const handle = String(item.handle || '').replace('@', '').trim()
    if (!handle) return
    window.open(`https://x.com/${handle}/with_replies`, '_blank', 'noopener,noreferrer')
  }

  async function handleMarkDone(item: PendingItem) {
    try {
      await options.results.markDone(item.key, String(item.handle || ''))
      options.deselectNotifyKey(item.key)
      options.deselectTweetKey(item.key)
      options.toast.push('记录已处理', 'success')
    } catch (error: any) {
      options.toast.push(error?.message || '操作失败', 'error', 4200)
    }
  }

  async function handleBulkMarkDone(kind: 'notify' | 'tweet') {
    const items = (kind === 'notify' ? options.filteredNotifyItems.value : options.filteredTweetItems.value)
      .filter((item) => (kind === 'notify' ? options.selectedNotifyByKey.value[item.key] : options.selectedTweetByKey.value[item.key]))
    if (!items.length) {
      options.toast.push('请先勾选要批量处理的记录', 'error', 3200)
      return
    }

    let successCount = 0
    let failedCount = 0
    for (const item of items) {
      try {
        await options.results.markDone(item.key, String(item.handle || ''))
        options.deselectNotifyKey(item.key)
        options.deselectTweetKey(item.key)
        successCount += 1
      } catch {
        failedCount += 1
      }
    }

    if (successCount) {
      options.toast.push(`已批量处理 ${successCount} 条记录`, failedCount ? 'info' : 'success', 4200)
    }
    if (failedCount) {
      options.toast.push(`${failedCount} 条记录处理失败`, 'error', 4200)
    }
  }

  async function handleNotifyReply(item: PendingItem) {
    const replyText = options.selectedReplyByKey.value[item.key] || String(item.notify_reply_text || options.replyTemplates.value[0] || '')
    const dmText = options.selectedDmByKey.value[item.key] || String(item.notify_dm_text || options.dmTemplates.value[0] || '')
    if (!replyText || !dmText) {
      options.toast.push('请先选择评论回复和私信模板', 'error', 4200)
      return
    }
    try {
      const data = await options.results.sendReply(item.key, replyText, dmText)
      if (data.status === 'retry_waiting') {
        options.toast.push(data.msg || '已加入重试队列', 'info', 4200)
        await options.results.syncNotifyFlow()
        return
      }
      options.toast.push('通知回复已提交', 'success')
      await options.results.syncNotifyFlow()
    } catch (error: any) {
      options.toast.push(error?.message || '回复失败', 'error', 4200)
    }
  }

  async function handleRetry(item: PendingItem) {
    try {
      const data = await options.results.retryNotify(item.key)
      options.toast.push(data.msg || '重试已触发', data.status === 'ok' ? 'success' : 'info', 4200)
      await options.results.syncNotifyFlow()
    } catch (error: any) {
      options.toast.push(error?.message || '重试失败', 'error', 4200)
    }
  }

  async function handleClear(kind: 'notify' | 'tweet') {
    if (!window.confirm(`确定要清空${kind === 'notify' ? '通知' : '推文'}捕获结果吗？`)) return
    try {
      await options.results.clear(kind)
      options.toast.push('结果已清空', 'success')
    } catch (error: any) {
      options.toast.push(error?.message || '清空失败', 'error', 4200)
    }
  }

  async function handleClearBlocklist() {
    if (!window.confirm('确定要清空黑名单吗？')) return
    try {
      await options.results.clearAllBlocklist()
      options.toast.push('黑名单已清空', 'success')
    } catch (error: any) {
      options.toast.push(error?.message || '清空失败', 'error', 4200)
    }
  }

  return {
    applyDefaultTemplate,
    openTweetSource,
    handleMarkDone,
    handleBulkMarkDone,
    handleNotifyReply,
    handleRetry,
    handleClear,
    handleClearBlocklist,
  }
}
