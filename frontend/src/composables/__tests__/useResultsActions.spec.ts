import { computed, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useResultsActions } from '../useResultsActions'
import type { PendingItem } from '../../types'

function makeOptions() {
  const notifyItem: PendingItem = { key: 'n1', source: '通知页面', handle: '@notify', content: 'hello' }
  const tweetItem: PendingItem = { key: 't1', source: 'tweet', handle: '@tweet', content: 'world', status_url: 'https://x.com/demo/status/1' }

  const results = {
    markDone: vi.fn().mockResolvedValue(undefined),
    retryNotify: vi.fn().mockResolvedValue({ status: 'ok', msg: '重试成功' }),
    sendReply: vi.fn().mockResolvedValue({ status: 'ok' }),
    syncNotifyFlow: vi.fn().mockResolvedValue(undefined),
    clear: vi.fn().mockResolvedValue(undefined),
    clearAllBlocklist: vi.fn().mockResolvedValue({ status: 'ok' }),
  }
  const toast = { push: vi.fn() }
  const replyTemplates = ref(['老板我私信您了'])
  const dmTemplates = ref(['您好，欢迎了解更多产品信息'])
  const selectedReplyByKey = ref<Record<string, string>>({})
  const selectedDmByKey = ref<Record<string, string>>({})
  const filteredNotifyItems = computed(() => [notifyItem])
  const filteredTweetItems = computed(() => [tweetItem])
  const selectedNotifyByKey = ref<Record<string, boolean>>({ n1: true })
  const selectedTweetByKey = ref<Record<string, boolean>>({ t1: true })
  const deselectNotifyKey = vi.fn()
  const deselectTweetKey = vi.fn()

  const actions = useResultsActions({
    results,
    toast,
    replyTemplates,
    dmTemplates,
    selectedReplyByKey,
    selectedDmByKey,
    filteredNotifyItems,
    filteredTweetItems,
    selectedNotifyByKey,
    selectedTweetByKey,
    deselectNotifyKey,
    deselectTweetKey,
  })

  return {
    actions,
    results,
    toast,
    replyTemplates,
    dmTemplates,
    selectedReplyByKey,
    selectedDmByKey,
    filteredNotifyItems,
    filteredTweetItems,
    selectedNotifyByKey,
    selectedTweetByKey,
    deselectNotifyKey,
    deselectTweetKey,
    notifyItem,
    tweetItem,
  }
}

describe('useResultsActions', () => {
  const confirmSpy = vi.spyOn(window, 'confirm')
  const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)

  beforeEach(() => {
    confirmSpy.mockReset()
    openSpy.mockClear()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('applies default templates to selected item', () => {
    const { actions, selectedReplyByKey, selectedDmByKey, notifyItem } = makeOptions()

    actions.applyDefaultTemplate(notifyItem, 'reply')
    actions.applyDefaultTemplate(notifyItem, 'dm')

    expect(selectedReplyByKey.value[notifyItem.key]).toBe('老板我私信您了')
    expect(selectedDmByKey.value[notifyItem.key]).toBe('您好，欢迎了解更多产品信息')
  })

  it('bulk marks visible notify items as done', async () => {
    const { actions, results, toast, deselectNotifyKey, deselectTweetKey } = makeOptions()

    await actions.handleBulkMarkDone('notify')

    expect(results.markDone).toHaveBeenCalledWith('n1', '@notify')
    expect(deselectNotifyKey).toHaveBeenCalledWith('n1')
    expect(deselectTweetKey).toHaveBeenCalledWith('n1')
    expect(toast.push).toHaveBeenCalledWith('已批量处理 1 条记录', 'success', 4200)
  })

  it('clears blocklist after confirmation and opens status url when available', async () => {
    const { actions, results, toast, tweetItem } = makeOptions()
    confirmSpy.mockReturnValue(true)

    await actions.handleClearBlocklist()
    actions.openTweetSource(tweetItem)

    expect(results.clearAllBlocklist).toHaveBeenCalledTimes(1)
    expect(toast.push).toHaveBeenCalledWith('黑名单已清空', 'success')
    expect(openSpy).toHaveBeenCalledWith('https://x.com/demo/status/1', '_blank', 'noopener,noreferrer')
  })

  it('shows validation toast when reply or dm template is missing', async () => {
    const { actions, toast, notifyItem, replyTemplates, dmTemplates } = makeOptions()
    replyTemplates.value = []
    dmTemplates.value = []

    await actions.handleNotifyReply(notifyItem)

    expect(toast.push).toHaveBeenCalledWith('请先选择评论回复和私信模板', 'error', 4200)
  })

  it('does not clear blocklist when confirmation is rejected', async () => {
    const { actions, results } = makeOptions()
    confirmSpy.mockReturnValue(false)

    await actions.handleClearBlocklist()

    expect(results.clearAllBlocklist).not.toHaveBeenCalled()
  })
})
