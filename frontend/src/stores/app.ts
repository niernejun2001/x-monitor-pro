import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import * as api from '../api/services'
import type { DmRecentContactsPayload, StatePayload } from '../types'
import { useTasksStore } from './tasks'
import { useTemplatesStore } from './templates'
import { useResultsStore } from './results'
import { useToastStore } from './toast'

function buildIntentLines(analysis: Record<string, any>) {
  const signals = Array.isArray(analysis.signals) ? analysis.signals.join(', ') : ''
  return [
    `意向等级: ${analysis.intent_level || '-'} (${analysis.intent_score ?? 0}分)`,
    `是否意向用户: ${analysis.is_intent_user ? '是' : '否'}`,
    `是否语音播报: ${analysis.voice_should_notify ? '是' : '否'}`,
    `规则分: ${analysis.rule_score ?? '-'} | LLM分: ${analysis.llm_score ?? '-'}`,
    `LLM是否参与: ${analysis.llm_used ? '是' : '否'}`,
    `识别信号: ${signals || '-'}`,
    `判定依据(最终): ${analysis.reason || '-'}`,
    `判定依据(LLM): ${analysis.llm_reason || '-'}`,
    analysis.llm_error ? `LLM异常: ${analysis.llm_error}` : '',
  ]
    .filter(Boolean)
    .join('\n')
}

export const useAppStore = defineStore('app', () => {
  const toast = useToastStore()
  const tasksStore = useTasksStore()
  const templatesStore = useTemplatesStore()
  const resultsStore = useResultsStore()

  const state = ref<StatePayload | null>(null)
  const activePanel = ref<'control' | 'task' | 'template'>('control')

  const token = ref('')
  const tokenConfigured = ref(false)
  const isRunning = ref(false)
  const notificationMonitoring = ref(false)
  const headlessMode = ref(true)
  const delegatedAccount = ref('')
  const enterpriseWechatWebhookUrl = ref('')

  const notifyTtsEnabled = ref(false)
  const notifyTtsAppId = ref('')
  const notifyTtsAccessToken = ref('')
  const notifyTtsSecretKey = ref('')
  const notifyTtsVoiceType = ref('')
  const notifyTtsResult = ref('等待配置...')
  const notifyTtsAccessTokenConfigured = ref(false)
  const notifyTtsSecretKeyConfigured = ref(false)

  const llmFilterEnabled = ref(false)
  const llmBaseUrl = ref('')
  const llmModel = ref('')
  const llmApiKey = ref('')
  const llmApiKeyConfigured = ref(false)
  const llmTimeoutSec = ref(8)
  const llmTimeoutMaxSec = ref(120)
  const llmRetryCount = ref(2)
  const llmRetryBackoffSec = ref(0.35)
  const llmIntentPromptTemplate = ref('')
  const llmFilterPromptTemplate = ref('')
  const dmLlmRewriteEnabled = ref(false)
  const dmLlmRewritePromptTemplate = ref('')
  const notifyVoiceBlockKeywords = ref('')
  const llmIntentInput = ref('')
  const llmIntentResult = ref('等待测试或分析...')
  const notificationToggleBusy = ref(false)
  const llmTestBusy = ref(false)
  const dmStatsBusy = ref(false)
  const dmDailyPushBusy = ref(false)
  const dmRecentContacts = ref<DmRecentContactsPayload | null>(null)
  const clockNowSec = ref(Date.now() / 1000)
  const clockTimer = ref<number | null>(null)

  const statusText = computed(() => (isRunning.value ? '运行中' : '系统待机'))
  const serverAudioMeta = computed(() => ({
    enabled: !!state.value?.notify_server_audio_enabled,
    ready: !!state.value?.notify_server_audio_ready,
    player: state.value?.notify_server_audio_player || '-',
  }))
  const browserProxyMeta = computed(() => ({
    configured: !!state.value?.browser_proxy_configured,
    source: state.value?.browser_proxy_source || '',
    display: state.value?.browser_proxy_display || '',
  }))
  const notificationScheduleMeta = computed(() => {
    const snapshot = state.value?.notification_schedule_snapshot || {}
    const mode = snapshot.boost_active ? '提速' : snapshot.idle_active ? '降频' : '常规'
    const period = snapshot.period_label === 'quiet' ? '夜间' : '白天'
    const scanMultiplier = Number(snapshot.scan_multiplier || 1)
    const refreshMultiplier = Number(snapshot.refresh_multiplier || 1)
    const nowSec = clockNowSec.value
    const nextScanAt = Number(state.value?.notification_next_scan_at || 0)
    const lastScanAt = Number(state.value?.notification_last_scan_at || 0)
    const scanInterval = Number(state.value?.notification_scan_interval || 0)
    const nextRefreshAt = Number(state.value?.notification_next_refresh_at || 0)
    const lastRefreshAt = Number(state.value?.notification_last_refresh_at || 0)
    const nextScanIn = nextScanAt > 0 ? Math.max(0, Math.round(nextScanAt - nowSec)) : 0
    const lastScanAge = lastScanAt > 0 ? Math.max(0, Math.round(nowSec - lastScanAt)) : 0
    const nextRefreshIn = nextRefreshAt > 0 ? Math.max(0, Math.round(nextRefreshAt - nowSec)) : 0
    const lastRefreshAge = lastRefreshAt > 0 ? Math.max(0, Math.round(nowSec - lastRefreshAt)) : 0
    return {
      period,
      mode,
      text: state.value?.notification_schedule_text || '-',
      scanMultiplier,
      refreshMultiplier,
      scanInterval,
      nextScanAt,
      nextScanIn,
      lastScanAt,
      lastScanAge,
      nextRefreshAt,
      nextRefreshIn,
      lastRefreshAt,
      lastRefreshAge,
      idleScanStreak: Number(state.value?.notification_idle_scan_streak ?? snapshot.idle_scan_streak ?? 0),
      refreshInterval: Number(state.value?.notification_refresh_interval || 0),
      pendingFullRefresh: !!state.value?.notification_full_refresh_pending,
      pendingReason: state.value?.notification_full_refresh_reason || '',
      lightScanCount: Number(state.value?.notification_dm_light_scan_count || 0),
    }
  })

  function hydrate(payload: StatePayload) {
    state.value = payload
    token.value = ''
    tokenConfigured.value = !!(payload.token_configured || payload.token)
    isRunning.value = !!payload.is_running
    notificationMonitoring.value = !!payload.notification_monitoring
    headlessMode.value = payload.headless_mode !== false
    delegatedAccount.value = payload.delegated_account || ''
    enterpriseWechatWebhookUrl.value = payload.enterprise_wechat_webhook_url || ''

    notifyTtsEnabled.value = !!payload.notify_tts_enabled
    notifyTtsAppId.value = payload.notify_tts_app_id || ''
    notifyTtsAccessTokenConfigured.value = !!payload.notify_tts_access_token_configured
    notifyTtsSecretKeyConfigured.value = !!payload.notify_tts_secret_key_configured
    notifyTtsAccessToken.value = ''
    notifyTtsSecretKey.value = ''
    notifyTtsVoiceType.value = payload.notify_tts_voice_type || ''
    notifyTtsResult.value = `当前状态: ${payload.notify_tts_ready ? '已就绪' : '未就绪'}\n音色: ${payload.notify_tts_voice_type || '-'}\n编码: ${payload.notify_tts_encoding || '-'}`

    llmFilterEnabled.value = !!payload.llm_filter_enabled
    llmBaseUrl.value = payload.llm_filter_base_url || ''
    llmModel.value = payload.llm_filter_model || ''
    llmApiKeyConfigured.value = !!payload.llm_filter_api_key_configured
    llmApiKey.value = ''
    llmTimeoutSec.value = Number(payload.llm_filter_timeout_sec || 8)
    llmTimeoutMaxSec.value = Number(payload.llm_filter_timeout_max_sec || 120)
    llmRetryCount.value = Number(payload.llm_filter_retry_count || 2)
    llmRetryBackoffSec.value = Number(payload.llm_filter_retry_backoff_sec || 0.35)
    llmIntentPromptTemplate.value = payload.llm_intent_prompt_template || ''
    llmFilterPromptTemplate.value = payload.llm_filter_prompt_template || ''
    dmLlmRewriteEnabled.value = payload.dm_llm_rewrite_enabled !== false
    dmLlmRewritePromptTemplate.value = payload.dm_llm_rewrite_prompt_template || ''
    notifyVoiceBlockKeywords.value = payload.notify_voice_block_keywords_text || ''
    dmRecentContacts.value = payload.dm_recent_contacts || dmRecentContacts.value

    tasksStore.hydrate(payload.tasks || [])
    templatesStore.hydrate(payload)
    resultsStore.hydrate(payload.pending || [], payload.updates_last_seq || 0)
  }

  async function bootstrap() {
    const payload = await api.fetchState()
    hydrate(payload)
    return payload
  }

  async function start() {
    await api.startMonitor(token.value)
    tokenConfigured.value = true
    token.value = ''
    isRunning.value = true
    toast.push('监控已启动', 'success')
  }

  async function stop() {
    await api.stopMonitor()
    isRunning.value = false
    toast.push('监控已停止', 'info')
  }

  async function saveNotificationSwitch() {
    const requestedValue = notificationMonitoring.value
    const previousValue = !!state.value?.notification_monitoring
    notificationToggleBusy.value = true
    try {
      await api.toggleNotification(requestedValue)
      notificationMonitoring.value = requestedValue
      if (state.value) state.value.notification_monitoring = requestedValue
      toast.push(`通知监控已${requestedValue ? '启用' : '禁用'}`, 'success')
    } catch (error: any) {
      notificationMonitoring.value = previousValue
      if (state.value) state.value.notification_monitoring = previousValue
      throw error
    } finally {
      notificationToggleBusy.value = false
    }
  }

  async function saveHeadlessSwitch() {
    await api.toggleHeadless(headlessMode.value)
    toast.push(`浏览器模式已切换为${headlessMode.value ? '无头' : '有头'}`, 'success')
  }

  async function saveDelegation() {
    const data = await api.setDelegatedAccount(delegatedAccount.value)
    delegatedAccount.value = String(data.delegated_account || '')
    toast.push(data.delegated_enabled ? '委派账户已保存' : '委派账户已清除', 'success')
  }

  async function saveEnterpriseWechatWebhook() {
    const data = await api.setEnterpriseWechatWebhook(enterpriseWechatWebhookUrl.value.trim())
    enterpriseWechatWebhookUrl.value = String((data as any).enterprise_wechat_webhook_url || '')
    if (state.value) state.value.enterprise_wechat_webhook_url = enterpriseWechatWebhookUrl.value
    toast.push(enterpriseWechatWebhookUrl.value ? '企业微信 Webhook 已保存' : '企业微信 Webhook 已清空', 'success')
  }

  async function jumpToReplies(handle: string) {
    const data = await api.openRepliesPage(handle)
    toast.push(`已打开 ${data.handle || handle} 的回复页`, 'success')
  }

  async function saveNotifyTts() {
    const payload: Record<string, unknown> = {
      enabled: notifyTtsEnabled.value,
      app_id: notifyTtsAppId.value,
      voice_type: notifyTtsVoiceType.value,
    }
    if (notifyTtsAccessToken.value.trim()) payload.access_token = notifyTtsAccessToken.value.trim()
    if (notifyTtsSecretKey.value.trim()) payload.secret_key = notifyTtsSecretKey.value.trim()
    const data = await api.saveNotifyTtsConfig(payload)
    notifyTtsResult.value = data.status === 'ok' ? '豆包配置已保存' : `保存失败: ${data.msg || '未知错误'}`
    await bootstrap()
  }

  async function testNotifyVoice() {
    const data = await api.synthesizeTts('评论内容：这是一条测试评论内容')
    if (data.status !== 'ok' || !data.audio_base64) throw new Error(data.msg || '语音合成失败')
    const audio = new Audio(`data:${data.mime || 'audio/mpeg'};base64,${data.audio_base64}`)
    await audio.play()
    toast.push('测试播报已开始', 'success')
  }

  async function saveLlmConfig() {
    const payload: Record<string, unknown> = {
      enabled: llmFilterEnabled.value,
      base_url: llmBaseUrl.value,
      model: llmModel.value,
      timeout_sec: llmTimeoutSec.value,
      retry_count: llmRetryCount.value,
      retry_backoff_sec: llmRetryBackoffSec.value,
      llm_intent_prompt_template: llmIntentPromptTemplate.value,
      llm_filter_prompt_template: llmFilterPromptTemplate.value,
      dm_llm_rewrite_enabled: dmLlmRewriteEnabled.value,
      dm_llm_rewrite_prompt_template: dmLlmRewritePromptTemplate.value,
      notify_voice_block_keywords_text: notifyVoiceBlockKeywords.value,
    }
    if (llmApiKey.value.trim()) payload.api_key = llmApiKey.value.trim()
    await api.saveLlmFilterConfig(payload)
    toast.push('LLM 配置已保存', 'success')
    await bootstrap()
  }

  async function testLlm() {
    llmTestBusy.value = true
    llmIntentResult.value = '正在测试模型连通性...'
    const payload: Record<string, unknown> = {
      base_url: llmBaseUrl.value,
      model: llmModel.value,
      timeout_sec: llmTimeoutSec.value,
    }
    if (llmApiKey.value.trim()) payload.api_key = llmApiKey.value.trim()
    try {
      const data = await api.testLlmModel(payload)
      llmIntentResult.value = data.status === 'ok'
        ? `模型可用: ${data.model || '-'}\n延迟: ${data.latency_ms || 0}ms\n接口: ${data.endpoint || '-'}`
        : `测试失败: ${data.msg || '未知错误'}`
    } catch (error: any) {
      llmIntentResult.value = `测试失败: ${error?.message || '请求异常'}`
      throw error
    } finally {
      llmTestBusy.value = false
    }
  }

  async function analyzeIntentInput() {
    const payload: Record<string, unknown> = {
      base_url: llmBaseUrl.value,
      model: llmModel.value,
      timeout_sec: llmTimeoutSec.value,
      content: llmIntentInput.value,
      analyze_source: 'manual_panel',
    }
    if (llmApiKey.value.trim()) payload.api_key = llmApiKey.value.trim()
    const data = await api.analyzeIntent(payload)
    llmIntentResult.value = buildIntentLines((data as any).analysis || {})
  }

  async function fetchDmRecentContacts() {
    dmStatsBusy.value = true
    try {
      const data = await api.fetchRecentDmContacts(24)
      dmRecentContacts.value = data
      if (data.status !== 'ok') throw new Error(data.msg || '私信统计失败')
      toast.push(`已统计最近24小时私信联系人 ${data.count || 0} 个`, 'success')
      return data
    } finally {
      dmStatsBusy.value = false
    }
  }

  async function refreshDmRecentContacts() {
    const data = await api.getRecentDmContacts()
    dmRecentContacts.value = data
    return data
  }

  async function pushDailyDmContactsTest() {
    dmDailyPushBusy.value = true
    try {
      const data = await api.pushDailyDmContactsTest()
      toast.push(`企业微信测试推送成功，人数 ${Number((data as any).count || 0)} 个`, 'success')
      return data
    } finally {
      dmDailyPushBusy.value = false
    }
  }

  function startClock() {
    if (clockTimer.value !== null) return
    clockNowSec.value = Date.now() / 1000
    clockTimer.value = window.setInterval(() => {
      clockNowSec.value = Date.now() / 1000
    }, 1000)
  }

  function stopClock() {
    if (clockTimer.value !== null) {
      window.clearInterval(clockTimer.value)
      clockTimer.value = null
    }
  }

  return {
    state,
    activePanel,
    token,
    tokenConfigured,
    isRunning,
    notificationMonitoring,
    headlessMode,
    delegatedAccount,
    enterpriseWechatWebhookUrl,
    notifyTtsEnabled,
    notifyTtsAppId,
    notifyTtsAccessToken,
    notifyTtsSecretKey,
    notifyTtsVoiceType,
    notifyTtsResult,
    notifyTtsAccessTokenConfigured,
    notifyTtsSecretKeyConfigured,
    llmFilterEnabled,
    llmBaseUrl,
    llmModel,
    llmApiKey,
    llmApiKeyConfigured,
    llmTimeoutSec,
    llmTimeoutMaxSec,
    llmRetryCount,
    llmRetryBackoffSec,
    llmIntentPromptTemplate,
    llmFilterPromptTemplate,
    dmLlmRewriteEnabled,
    dmLlmRewritePromptTemplate,
    notifyVoiceBlockKeywords,
    llmIntentInput,
    llmIntentResult,
    notificationToggleBusy,
    llmTestBusy,
    dmStatsBusy,
    dmDailyPushBusy,
    dmRecentContacts,
    clockNowSec,
    statusText,
    serverAudioMeta,
    browserProxyMeta,
    notificationScheduleMeta,
    hydrate,
    bootstrap,
    start,
    stop,
    saveNotificationSwitch,
    saveHeadlessSwitch,
    saveDelegation,
    saveEnterpriseWechatWebhook,
    jumpToReplies,
    saveNotifyTts,
    testNotifyVoice,
    saveLlmConfig,
    testLlm,
    analyzeIntentInput,
    fetchDmRecentContacts,
    refreshDmRecentContacts,
    pushDailyDmContactsTest,
    startClock,
    stopClock,
  }
})
