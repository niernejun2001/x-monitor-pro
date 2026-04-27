import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useResultsStore } from '../results'
import { useAppStore } from '../app'
import * as api from '../../api/services'

vi.mock('../../api/services', () => ({
  fetchState: vi.fn(),
  fetchUpdates: vi.fn(),
  fetchNotifyReplies: vi.fn(),
  markDone: vi.fn(),
  retryNotifyReply: vi.fn(),
  sendNotifyReply: vi.fn(),
  clearResults: vi.fn(),
  clearBlocklist: vi.fn(),
}))

describe('results store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('hydrates and filters notify/tweet items separately', () => {
    const store = useResultsStore()
    store.hydrate([
      { key: 'n1', source: '通知页面', handle: '@notify', content: '老板 想了解下', time: '12:00:02' },
      { key: 'n2', source: '通知页面', handle: '@notify2', content: '普通评论', time: '12:00:03' },
      { key: 't1', source: 'tweet', handle: '@tweet', content: '任务推文', time: '11:59:00' },
    ], 8)

    expect(store.updatesLastSeq).toBe(8)
    expect(store.notifyItems.map((item) => item.key)).toEqual(['n2', 'n1'])
    expect(store.tweetItems.map((item) => item.key)).toEqual(['t1'])

    store.filterText.notify = '老板'
    store.filterText.tweet = '@tweet'

    expect(store.notifyItems.map((item) => item.key)).toEqual(['n1'])
    expect(store.tweetItems.map((item) => item.key)).toEqual(['t1'])
  })

  it('merges updates, retries and reply payloads into existing rows', async () => {
    const store = useResultsStore()
    store.hydrate([
      { key: 'n1', source: '通知页面', handle: '@notify', content: '原始内容', time: '12:00:00' },
    ], 0)

    vi.mocked(api.retryNotifyReply).mockResolvedValue({ status: 'retry_waiting', flow_stage: 'retry_waiting' } as any)
    vi.mocked(api.sendNotifyReply).mockResolvedValue({ status: 'ok', flow_stage: 'done' } as any)

    await store.retryNotify('n1')
    expect(store.items.find((item) => item.key === 'n1')?.flow_stage).toBe('retry_waiting')

    await store.sendReply('n1', '回复内容', '私信内容')
    expect(store.items.find((item) => item.key === 'n1')?.flow_stage).toBe('done')
  })

  it('polls updates and notify flow on intervals, then stops cleanly', async () => {
    vi.useFakeTimers()
    const store = useResultsStore()
    const app = useAppStore()
    vi.mocked(api.fetchState).mockResolvedValue({
      tasks: [],
      is_running: true,
      pending: [],
      updates_last_seq: 9,
      updates_buffer_size: 0,
      notification_monitoring: true,
      notification_scan_interval: 11,
      delegated_account: '',
      delegated_enabled: false,
      headless_mode: true,
      notify_reply_templates: [],
      dm_message_templates: [],
      llm_filter_enabled: false,
      llm_filter_base_url: '',
      llm_filter_model: '',
      llm_filter_timeout_sec: 8,
      llm_filter_timeout_max_sec: 120,
      llm_filter_prompt_template: '',
      llm_intent_prompt_template: '',
      dm_llm_rewrite_enabled: false,
      dm_llm_rewrite_prompt_template: '',
      notify_voice_block_keywords_text: '',
      notification_reply_only_mode: true,
    } as any)
    vi.mocked(api.fetchUpdates).mockResolvedValue({
      new_items: [
        { key: 'n3', source: '通知页面', handle: '@new', content: '新通知', time: '12:00:05' },
      ],
      last_seq: 9,
    } as any)
    vi.mocked(api.fetchNotifyReplies).mockResolvedValue({
      items: [
        { key: 'n3', source: '通知页面', handle: '@new', content: '新通知', time: '12:00:05', notify_retry_time: '13:00:00' },
      ],
    } as any)

    store.startPolling()
    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(5000)
    await vi.advanceTimersByTimeAsync(6000)

    expect(vi.mocked(api.fetchUpdates)).toHaveBeenCalled()
    expect(vi.mocked(api.fetchNotifyReplies)).toHaveBeenCalled()
    expect(vi.mocked(api.fetchState)).toHaveBeenCalled()
    expect(store.updatesLastSeq).toBe(9)
    expect(store.items.find((item) => item.key === 'n3')?.notify_retry_time).toBe('13:00:00')
    expect(app.notificationMonitoring).toBe(true)
    expect(app.notificationScheduleMeta.scanInterval).toBe(11)

    store.stopPolling()
    vi.clearAllTimers()
    vi.useRealTimers()
  })

  it('marks done and clears by kind', async () => {
    const store = useResultsStore()
    store.hydrate([
      { key: 'n1', source: '通知页面', handle: '@notify', content: '通知', time: '12:00:00' },
      { key: 't1', source: 'tweet', handle: '@tweet', content: '推文', time: '11:59:00' },
    ], 0)

    vi.mocked(api.markDone).mockResolvedValue({ status: 'ok' } as any)
    vi.mocked(api.clearResults).mockResolvedValue({ status: 'ok' } as any)

    await store.markDone('n1', '@notify')
    expect(store.items.map((item) => item.key)).toEqual(['t1'])

    await store.clear('tweet')
    expect(store.items).toHaveLength(0)
  })
})
