import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import * as api from '../api/services'
import type { StatePayload } from '../types'
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
  const llmIntentPromptTemplate = ref('')
  const llmFilterPromptTemplate = ref('')
  const dmLlmRewriteEnabled = ref(false)
  const dmLlmRewritePromptTemplate = ref('')
  const notifyVoiceBlockKeywords = ref('')
  const llmIntentInput = ref('')
  const llmIntentResult = ref('等待测试或分析...')

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

  function hydrate(payload: StatePayload) {
    state.value = payload
    token.value = ''
    tokenConfigured.value = !!(payload.token_configured || payload.token)
    isRunning.value = !!payload.is_running
    notificationMonitoring.value = !!payload.notification_monitoring
    headlessMode.value = payload.headless_mode !== false
    delegatedAccount.value = payload.delegated_account || ''

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
    llmIntentPromptTemplate.value = payload.llm_intent_prompt_template || ''
    llmFilterPromptTemplate.value = payload.llm_filter_prompt_template || ''
    dmLlmRewriteEnabled.value = payload.dm_llm_rewrite_enabled !== false
    dmLlmRewritePromptTemplate.value = payload.dm_llm_rewrite_prompt_template || ''
    notifyVoiceBlockKeywords.value = payload.notify_voice_block_keywords_text || ''

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
    await api.toggleNotification(notificationMonitoring.value)
    toast.push(`通知监控已${notificationMonitoring.value ? '启用' : '禁用'}`, 'success')
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
    const payload: Record<string, unknown> = {
      base_url: llmBaseUrl.value,
      model: llmModel.value,
      timeout_sec: llmTimeoutSec.value,
    }
    if (llmApiKey.value.trim()) payload.api_key = llmApiKey.value.trim()
    const data = await api.testLlmModel(payload)
    llmIntentResult.value = data.status === 'ok'
      ? `模型可用: ${data.model || '-'}\n延迟: ${data.latency_ms || 0}ms\n接口: ${data.endpoint || '-'}`
      : `测试失败: ${data.msg || '未知错误'}`
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

  return {
    state,
    activePanel,
    token,
    tokenConfigured,
    isRunning,
    notificationMonitoring,
    headlessMode,
    delegatedAccount,
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
    llmIntentPromptTemplate,
    llmFilterPromptTemplate,
    dmLlmRewriteEnabled,
    dmLlmRewritePromptTemplate,
    notifyVoiceBlockKeywords,
    llmIntentInput,
    llmIntentResult,
    statusText,
    serverAudioMeta,
    browserProxyMeta,
    hydrate,
    bootstrap,
    start,
    stop,
    saveNotificationSwitch,
    saveHeadlessSwitch,
    saveDelegation,
    jumpToReplies,
    saveNotifyTts,
    testNotifyVoice,
    saveLlmConfig,
    testLlm,
    analyzeIntentInput,
  }
})
