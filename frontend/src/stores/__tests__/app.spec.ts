import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAppStore } from '../app'
import * as api from '../../api/services'

vi.mock('../../api/services', () => ({
  fetchState: vi.fn(),
  startMonitor: vi.fn(),
  stopMonitor: vi.fn(),
  toggleNotification: vi.fn(),
  toggleHeadless: vi.fn(),
  setDelegatedAccount: vi.fn(),
  openRepliesPage: vi.fn(),
  saveNotifyTtsConfig: vi.fn(),
  synthesizeTts: vi.fn(),
  saveLlmFilterConfig: vi.fn(),
  testLlmModel: vi.fn(),
  analyzeIntent: vi.fn(),
}))

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('app store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.useRealTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('hydrates llm retry settings from state payload', () => {
    const store = useAppStore()
    store.hydrate({
      tasks: [],
      is_running: false,
      pending: [],
      updates_last_seq: 0,
      updates_buffer_size: 0,
      notification_monitoring: false,
      notification_schedule_snapshot: {
        period_label: 'active',
        boost_active: true,
        idle_active: false,
        scan_multiplier: 0.72,
        refresh_multiplier: 0.79,
        idle_scan_streak: 2,
        boost_age_sec: 23,
      },
      notification_schedule_text: 'period=active mode=boost scanX=0.72 refreshX=0.79 idleStreak=2 boostAge=23s',
      notification_refresh_interval: 88,
      notification_last_refresh_at: Date.now() / 1000 - 12,
      notification_next_refresh_at: Date.now() / 1000 + 76,
      notification_scan_interval: 9,
      notification_last_scan_at: Date.now() / 1000 - 4,
      notification_next_scan_at: Date.now() / 1000 + 5,
      notification_idle_scan_streak: 2,
      notification_full_refresh_pending: true,
      notification_full_refresh_reason: 'dm_critical_scan',
      notification_dm_light_scan_count: 3,
      delegated_account: '',
      delegated_enabled: false,
      headless_mode: true,
      notify_reply_templates: [],
      dm_message_templates: [],
      llm_filter_enabled: true,
      llm_filter_base_url: 'http://127.0.0.1:11434/v1',
      llm_filter_model: 'qwen',
      llm_filter_timeout_sec: 8,
      llm_filter_timeout_max_sec: 120,
      llm_filter_retry_count: 3,
      llm_filter_retry_backoff_sec: 0.5,
      llm_filter_prompt_template: '',
      llm_intent_prompt_template: '',
      dm_llm_rewrite_enabled: false,
      dm_llm_rewrite_prompt_template: '',
      dm_llm_rewrite_max_chars: 260,
      dm_llm_rewrite_temperature: 0.35,
      dm_llm_rewrite_max_regen: 1,
      dm_llm_rewrite_dedupe_size: 200,
      notify_voice_block_keywords_text: '',
      notification_reply_only_mode: true,
    } as any)

    expect(store.llmRetryCount).toBe(3)
    expect(store.llmRetryBackoffSec).toBe(0.5)
    expect(store.notificationScheduleMeta.mode).toBe('提速')
    expect(store.notificationScheduleMeta.scanInterval).toBe(9)
    expect(store.notificationScheduleMeta.nextScanIn).toBeGreaterThanOrEqual(0)
    expect(store.notificationScheduleMeta.lastScanAge).toBeGreaterThanOrEqual(0)
    expect(store.notificationScheduleMeta.nextRefreshIn).toBeGreaterThanOrEqual(0)
    expect(store.notificationScheduleMeta.lastRefreshAge).toBeGreaterThanOrEqual(0)
    expect(store.notificationScheduleMeta.pendingFullRefresh).toBe(true)
    expect(store.notificationScheduleMeta.lightScanCount).toBe(3)
  })

  it('notification countdowns react to internal clock ticks', () => {
    const store = useAppStore()
    store.clockNowSec = 100
    store.hydrate({
      tasks: [],
      is_running: false,
      pending: [],
      updates_last_seq: 0,
      updates_buffer_size: 0,
      notification_monitoring: false,
      notification_schedule_snapshot: {
        period_label: 'active',
        boost_active: false,
        idle_active: false,
        scan_multiplier: 1,
        refresh_multiplier: 1,
        idle_scan_streak: 0,
        boost_age_sec: null,
      },
      notification_refresh_interval: 80,
      notification_last_refresh_at: 90,
      notification_next_refresh_at: 170,
      notification_scan_interval: 10,
      notification_last_scan_at: 95,
      notification_next_scan_at: 110,
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

    expect(store.notificationScheduleMeta.nextScanIn).toBe(10)
    expect(store.notificationScheduleMeta.nextRefreshIn).toBe(70)

    store.clockNowSec = 104

    expect(store.notificationScheduleMeta.nextScanIn).toBe(6)
    expect(store.notificationScheduleMeta.lastScanAge).toBe(9)
    expect(store.notificationScheduleMeta.nextRefreshIn).toBe(66)
    expect(store.notificationScheduleMeta.lastRefreshAge).toBe(14)
  })

  it('startClock creates one timer and stopClock clears it', () => {
    vi.useFakeTimers()
    const setSpy = vi.spyOn(window, 'setInterval')
    const clearSpy = vi.spyOn(window, 'clearInterval')
    const store = useAppStore()

    store.startClock()
    store.startClock()
    expect(setSpy).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(1100)
    expect(store.clockNowSec).toBeGreaterThan(0)

    store.stopClock()
    store.stopClock()
    expect(clearSpy).toHaveBeenCalledTimes(1)
  })

  it('saveNotificationSwitch toggles busy while request is in flight', async () => {
    const store = useAppStore()
    store.hydrate({
      tasks: [],
      is_running: false,
      pending: [],
      updates_last_seq: 0,
      updates_buffer_size: 0,
      notification_monitoring: false,
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
    store.notificationMonitoring = true
    const d = deferred<any>()
    vi.mocked(api.toggleNotification).mockReturnValue(d.promise as any)

    const pending = store.saveNotificationSwitch()
    expect(store.notificationToggleBusy).toBe(true)

    d.resolve({ status: 'ok' } as any)
    await pending
    expect(store.notificationToggleBusy).toBe(false)
  })

  it('saveNotificationSwitch rolls back toggle on request failure', async () => {
    const store = useAppStore()
    store.hydrate({
      tasks: [],
      is_running: false,
      pending: [],
      updates_last_seq: 0,
      updates_buffer_size: 0,
      notification_monitoring: false,
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
    store.notificationMonitoring = true
    vi.mocked(api.toggleNotification).mockRejectedValue(new Error('network down'))

    await expect(store.saveNotificationSwitch()).rejects.toThrow('network down')

    expect(store.notificationMonitoring).toBe(false)
    expect(store.notificationToggleBusy).toBe(false)
  })

  it('testLlm exposes busy state and pending message', async () => {
    const store = useAppStore()
    store.llmBaseUrl = 'http://127.0.0.1:11434/v1'
    store.llmModel = 'qwen'
    const d = deferred<any>()
    vi.mocked(api.testLlmModel).mockReturnValue(d.promise as any)

    const pending = store.testLlm()
    expect(store.llmTestBusy).toBe(true)
    expect(store.llmIntentResult).toContain('正在测试模型连通性')

    d.resolve({ status: 'ok', model: 'qwen', latency_ms: 123, endpoint: 'http://127.0.0.1:11434/chat/completions' } as any)
    await pending

    expect(store.llmTestBusy).toBe(false)
    expect(store.llmIntentResult).toContain('模型可用')
  })

  it('testLlm writes request failures into result text', async () => {
    const store = useAppStore()
    store.llmBaseUrl = 'http://127.0.0.1:11434/v1'
    store.llmModel = 'qwen'
    vi.mocked(api.testLlmModel).mockRejectedValue(new Error('HTTP 500'))

    await expect(store.testLlm()).rejects.toThrow('HTTP 500')

    expect(store.llmTestBusy).toBe(false)
    expect(store.llmIntentResult).toContain('测试失败: HTTP 500')
  })

  it('saveLlmConfig submits retry settings', async () => {
    const store = useAppStore()
    vi.mocked(api.saveLlmFilterConfig).mockResolvedValue({ status: 'ok' } as any)
    vi.mocked(api.fetchState).mockResolvedValue({
      tasks: [],
      is_running: false,
      pending: [],
      updates_last_seq: 0,
      updates_buffer_size: 0,
      notification_monitoring: false,
      delegated_account: '',
      delegated_enabled: false,
      headless_mode: true,
      notify_reply_templates: [],
      dm_message_templates: [],
      llm_filter_enabled: true,
      llm_filter_base_url: 'http://127.0.0.1:11434/v1',
      llm_filter_model: 'qwen',
      llm_filter_timeout_sec: 8,
      llm_filter_timeout_max_sec: 120,
      llm_filter_retry_count: 4,
      llm_filter_retry_backoff_sec: 0.6,
      llm_filter_prompt_template: '',
      llm_intent_prompt_template: '',
      dm_llm_rewrite_enabled: false,
      dm_llm_rewrite_prompt_template: '',
      dm_llm_rewrite_max_chars: 260,
      dm_llm_rewrite_temperature: 0.35,
      dm_llm_rewrite_max_regen: 1,
      dm_llm_rewrite_dedupe_size: 200,
      notify_voice_block_keywords_text: '',
      notification_reply_only_mode: true,
    } as any)

    store.llmFilterEnabled = true
    store.llmBaseUrl = 'http://127.0.0.1:11434/v1'
    store.llmModel = 'qwen'
    store.llmRetryCount = 4
    store.llmRetryBackoffSec = 0.6

    await store.saveLlmConfig()

    expect(vi.mocked(api.saveLlmFilterConfig)).toHaveBeenCalledWith(
      expect.objectContaining({
        retry_count: 4,
        retry_backoff_sec: 0.6,
      }),
    )
  })
})
