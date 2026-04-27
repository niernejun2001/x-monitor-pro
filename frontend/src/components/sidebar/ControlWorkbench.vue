<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed } from 'vue'
import { useAppStore } from '../../stores/app'
import { useToastStore } from '../../stores/toast'

const app = useAppStore()
const toast = useToastStore()

const {
  token,
  tokenConfigured,
  isRunning,
  notificationMonitoring,
  headlessMode,
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
  serverAudioMeta,
  browserProxyMeta,
  notificationScheduleMeta,
} = storeToRefs(app)

const statusPill = computed(() => {
  if (isRunning.value) return '运行中'
  if (tokenConfigured.value) return '已就绪'
  return '待配置'
})

const audioSummary = computed(() => {
  if (serverAudioMeta.value.enabled) return `服务端 / ${serverAudioMeta.value.player}`
  return notifyTtsEnabled.value ? '浏览器播放' : '浏览器兜底'
})

const aiSummary = computed(() => {
  if (!llmFilterEnabled.value) return '规则优先'
  return llmModel.value?.trim() || '模型已启用'
})

const notificationScheduleTone = computed(() => {
  if (notificationScheduleMeta.value.pendingFullRefresh) return 'border-amber-400/25 bg-amber-400/10 text-amber-700'
  if (notificationScheduleMeta.value.mode === '提速') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-700'
  if (notificationScheduleMeta.value.mode === '降频') return 'border-emerald-200/90 bg-white/80 text-emerald-700'
  return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-700'
})

const compactStatusCards = computed(() => [
  {
    label: 'Token',
    value: tokenConfigured.value ? '已保存' : '缺失',
    tone: tokenConfigured.value ? 'border-emerald-400/20 text-emerald-700' : 'border-amber-400/20 text-amber-700',
  },
  {
    label: '通知',
    value: notificationMonitoring.value ? '开启' : '关闭',
    tone: notificationMonitoring.value ? 'border-emerald-400/30 text-emerald-700' : 'border-emerald-100/90 text-emerald-700/80',
  },
  {
    label: '浏览器',
    value: headlessMode.value ? '无头' : '有头',
    tone: 'border-emerald-100/90 text-emerald-800',
  },
  {
    label: 'AI',
    value: aiSummary.value,
    tone: llmFilterEnabled.value ? 'border-emerald-400/20 text-emerald-700' : 'border-emerald-100/90 text-emerald-700/80',
  },
])

const voiceStatusText = computed(() => {
  if (!notifyTtsEnabled.value) return '当前关闭，使用浏览器兜底播报'
  return serverAudioMeta.value.enabled
    ? `豆包已启用，服务端播放器: ${serverAudioMeta.value.player}`
    : '豆包已启用，当前由浏览器播放测试音频'
})

const aiStatusText = computed(() => {
  if (!llmFilterEnabled.value) return '规则优先，LLM 过滤关闭'
  return `${llmModel.value || '未命名模型'} · 超时 ${llmTimeoutSec.value}s`
})

async function handleStartStop(run: boolean) {
  try {
    if (run) await app.start()
    else await app.stop()
  } catch (error: any) {
    toast.push(error?.message || '操作失败', 'error', 4200)
  }
}

async function handleNotificationToggle() {
  try {
    await app.saveNotificationSwitch()
  } catch (error: any) {
    toast.push(error?.message || '切换通知监控失败', 'error', 4200)
  }
}

async function handleHeadlessToggle() {
  try {
    await app.saveHeadlessSwitch()
  } catch (error: any) {
    toast.push(error?.message || '切换浏览器模式失败', 'error', 4200)
  }
}

async function handleTestVoice() {
  try {
    await app.testNotifyVoice()
  } catch (error: any) {
    toast.push(error?.message || '测试播报失败', 'error', 4200)
  }
}

async function handleSaveNotifyTts() {
  try {
    await app.saveNotifyTts()
  } catch (error: any) {
    toast.push(error?.message || '保存豆包配置失败', 'error', 4200)
  }
}

async function handleSaveLlm() {
  try {
    await app.saveLlmConfig()
  } catch (error: any) {
    toast.push(error?.message || '保存 LLM 配置失败', 'error', 4200)
  }
}

async function handleTestLlm() {
  try {
    await app.testLlm()
  } catch (error: any) {
    toast.push(error?.message || '模型测试失败', 'error', 4200)
  }
}

async function handleAnalyzeIntent() {
  try {
    await app.analyzeIntentInput()
  } catch (error: any) {
    toast.push(error?.message || '评论分析失败', 'error', 4200)
  }
}
</script>

<template>
  <section class="space-y-4">
    <div class="rounded-3xl border border-emerald-400/30 bg-gradient-to-br from-emerald-300/35 via-white/85 to-lime-200/35 p-4 shadow-[0_18px_46px_rgba(16,185,129,0.14)]">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="font-mono text-[11px] uppercase tracking-[0.12em] text-emerald-600">Today</div>
          <h3 class="mt-1 text-lg font-semibold text-emerald-950">今日操作</h3>
          <p class="mt-1 text-xs leading-5 text-emerald-700/80">启动、通知、播报这几个高频动作集中在这里。</p>
        </div>
        <div
          class="rounded-full border px-3 py-1 text-xs font-semibold"
          :class="isRunning ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-700' : 'border-emerald-200/90 bg-emerald-50/80 text-emerald-700'"
        >
          {{ statusPill }}
        </div>
      </div>

      <label class="mt-4 block space-y-2">
        <span class="text-[11px] font-medium uppercase tracking-[0.12em] text-emerald-700/60">启动 Token</span>
        <input
          v-model="token"
          type="password"
          aria-label="启动 Token"
          :placeholder="tokenConfigured ? '已保存，留空沿用已存 Token' : '输入 auth_token 后启动'"
          class="w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15"
        />
      </label>

      <button
        type="button"
        class="mt-4 w-full rounded-3xl px-5 py-4 text-base font-semibold shadow-[0_16px_32px_rgba(16,185,129,0.18)] transition"
        :class="isRunning ? 'bg-rose-500 text-white hover:brightness-105' : 'bg-gradient-to-r from-emerald-400 to-lime-300 text-emerald-950 hover:brightness-105'"
        @click="handleStartStop(!isRunning)"
      >
        {{ isRunning ? '停止监控' : '启动监控' }}
      </button>

      <div class="mt-4 grid gap-2">
        <label class="flex cursor-pointer items-center justify-between gap-3 rounded-2xl border border-emerald-100/90 bg-white/75 px-4 py-3">
          <div>
            <div class="text-sm font-semibold text-emerald-950">通知捕获</div>
            <div class="text-xs text-emerald-700/60">{{ notificationToggleBusy ? '切换中' : notificationMonitoring ? '正在捕获通知' : '已暂停通知捕获' }}</div>
          </div>
          <input
            v-model="notificationMonitoring"
            :disabled="notificationToggleBusy"
            type="checkbox"
            class="h-5 w-5 accent-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
            @change="handleNotificationToggle"
          />
        </label>

        <button
          type="button"
          class="rounded-2xl border border-emerald-200/90 bg-white/75 px-4 py-3 text-sm font-semibold text-emerald-950 transition hover:border-emerald-400"
          @click="handleTestVoice"
        >
          测试播报声音
        </button>
      </div>
    </div>

    <div class="rounded-3xl border border-emerald-100/90 bg-white/75 p-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="font-mono text-[11px] uppercase tracking-[0.12em] text-emerald-600">Status</div>
          <h3 class="mt-1 text-sm font-semibold text-emerald-950">当前状态</h3>
          <p class="mt-1 text-xs leading-5 text-emerald-700/60">只显示判断运行是否正常需要看的信息。</p>
        </div>
        <label class="flex cursor-pointer items-center gap-2 rounded-full border border-emerald-100/90 bg-emerald-50/80 px-3 py-2 text-xs text-emerald-700">
          <span>{{ headlessMode ? '无头' : '有头' }}</span>
          <input v-model="headlessMode" type="checkbox" class="h-4 w-4 accent-emerald-400" @change="handleHeadlessToggle" />
        </label>
      </div>

      <div class="mt-4 grid grid-cols-2 gap-2">
        <div
          v-for="card in compactStatusCards"
          :key="card.label"
          class="rounded-2xl border bg-white/70 px-3 py-3"
          :class="card.tone"
        >
          <div class="font-mono text-[10px] uppercase tracking-[0.12em] opacity-70">{{ card.label }}</div>
          <div class="mt-2 truncate text-sm font-semibold">{{ card.value }}</div>
        </div>
      </div>

      <div class="mt-4 rounded-2xl border px-4 py-3" :class="notificationScheduleTone">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="font-mono text-[10px] uppercase tracking-[0.12em] opacity-70">Scheduler</div>
            <div class="mt-1 text-sm font-semibold">
              {{ notificationScheduleMeta.period }} · {{ notificationScheduleMeta.mode }}
            </div>
          </div>
          <div class="text-right font-mono text-[11px] opacity-80">
            {{ notificationScheduleMeta.scanInterval.toFixed(0) }}s / {{ notificationScheduleMeta.refreshInterval.toFixed(0) }}s
          </div>
        </div>
        <div class="mt-3 grid grid-cols-3 gap-2 text-[11px]">
          <div class="rounded-xl border border-white/10 bg-black/10 px-2 py-2">
            <div class="opacity-60">下次扫描</div>
            <div class="mt-1 font-mono">{{ notificationScheduleMeta.nextScanIn }}s</div>
          </div>
          <div class="rounded-xl border border-white/10 bg-black/10 px-2 py-2">
            <div class="opacity-60">下次刷新</div>
            <div class="mt-1 font-mono">{{ notificationScheduleMeta.nextRefreshIn }}s</div>
          </div>
          <div class="rounded-xl border border-white/10 bg-black/10 px-2 py-2">
            <div class="opacity-60">空转</div>
            <div class="mt-1 font-mono">{{ notificationScheduleMeta.idleScanStreak }}</div>
          </div>
        </div>
        <details class="group mt-2">
          <summary class="cursor-pointer list-none text-[11px] text-emerald-700 transition hover:text-emerald-950">
            查看调度细节
          </summary>
          <div class="mt-2 grid grid-cols-2 gap-2 text-[11px] opacity-85">
            <div class="rounded-xl border border-white/10 bg-black/10 px-2 py-2">
              <div class="opacity-60">扫描倍率</div>
              <div class="mt-1 font-mono">{{ notificationScheduleMeta.scanMultiplier.toFixed(2) }}x</div>
            </div>
            <div class="rounded-xl border border-white/10 bg-black/10 px-2 py-2">
              <div class="opacity-60">刷新倍率</div>
              <div class="mt-1 font-mono">{{ notificationScheduleMeta.refreshMultiplier.toFixed(2) }}x</div>
            </div>
            <div class="rounded-xl border border-white/10 bg-black/10 px-2 py-2">
              <div class="opacity-60">上次扫描</div>
              <div class="mt-1 font-mono">{{ notificationScheduleMeta.lastScanAge }}s</div>
            </div>
            <div class="rounded-xl border border-white/10 bg-black/10 px-2 py-2">
              <div class="opacity-60">上次刷新</div>
              <div class="mt-1 font-mono">{{ notificationScheduleMeta.lastRefreshAge }}s</div>
            </div>
          </div>
        </details>
        <div v-if="notificationScheduleMeta.pendingFullRefresh" class="mt-3 rounded-xl border border-amber-300/20 bg-black/10 px-3 py-2 text-xs">
          私信关键区轻扫 {{ notificationScheduleMeta.lightScanCount }} 次，退出后补完整刷新
        </div>
      </div>
    </div>

    <details class="group rounded-3xl border border-emerald-100/90 bg-white/70 p-4">
      <summary class="cursor-pointer list-none">
        <div class="flex items-center justify-between gap-3">
          <div>
            <div class="font-mono text-[11px] uppercase tracking-[0.12em] text-emerald-600">Advanced</div>
            <h3 class="mt-1 text-sm font-semibold text-emerald-950">高级配置</h3>
          </div>
          <span class="rounded-full border border-emerald-100/90 px-3 py-1 text-xs text-emerald-700/80 group-open:hidden">展开</span>
          <span class="hidden rounded-full border border-emerald-100/90 px-3 py-1 text-xs text-emerald-700/80 group-open:inline">收起</span>
        </div>
        <p class="mt-2 text-xs leading-5 text-emerald-700/60">账号、语音、AI、代理等低频配置都放在这里。</p>
      </summary>

      <div class="mt-4 space-y-4">
        <details class="rounded-2xl border border-emerald-100/90 bg-white/70 p-4">
          <summary class="cursor-pointer list-none text-sm font-medium text-emerald-950">
            语音播报
            <span class="ml-2 text-xs text-emerald-700/60">{{ audioSummary }}</span>
          </summary>
          <div class="mt-4 space-y-4">
            <label class="flex items-center justify-between gap-3 rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3">
              <div>
                <div class="text-sm font-medium text-emerald-950">启用豆包 TTS</div>
                <div class="text-xs text-emerald-700/60">{{ voiceStatusText }}</div>
              </div>
              <input v-model="notifyTtsEnabled" type="checkbox" class="h-5 w-5 accent-emerald-400" />
            </label>
            <div class="grid gap-3 sm:grid-cols-2">
              <input v-model="notifyTtsAppId" type="text" aria-label="豆包 App ID" placeholder="App ID" class="w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15" />
              <input v-model="notifyTtsVoiceType" type="text" aria-label="豆包音色" placeholder="音色" class="w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15" />
            </div>
            <details class="rounded-2xl border border-emerald-100/90 bg-white/70 p-4">
              <summary class="cursor-pointer list-none text-sm font-medium text-emerald-950">密钥</summary>
              <div class="mt-4 space-y-3">
                <input v-model="notifyTtsAccessToken" type="password" aria-label="豆包 Access Token" :placeholder="notifyTtsAccessTokenConfigured ? 'Access Token 已保存' : 'Access Token'" class="w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15" />
                <input v-model="notifyTtsSecretKey" type="password" aria-label="豆包 Secret Key" :placeholder="notifyTtsSecretKeyConfigured ? 'Secret Key 已保存' : 'Secret Key（可选）'" class="w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15" />
              </div>
            </details>
            <div class="grid gap-3 sm:grid-cols-2">
              <button type="button" class="rounded-2xl bg-gradient-to-r from-emerald-400 to-teal-400 px-4 py-3 text-sm font-semibold text-emerald-950" @click="handleSaveNotifyTts">保存语音配置</button>
              <button type="button" class="rounded-2xl border border-emerald-200/90 bg-emerald-50/80 px-4 py-3 text-sm font-semibold text-emerald-800" @click="handleTestVoice">立即试播</button>
            </div>
            <pre class="max-h-[150px] overflow-auto rounded-2xl border border-emerald-100/90 bg-white/80 p-4 font-mono text-[11px] leading-6 text-emerald-700/80">{{ notifyTtsResult }}</pre>
          </div>
        </details>

        <details class="rounded-2xl border border-emerald-100/90 bg-white/70 p-4">
          <summary class="cursor-pointer list-none text-sm font-medium text-emerald-950">
            AI 与私信文案
            <span class="ml-2 text-xs text-emerald-700/60">{{ aiStatusText }}</span>
          </summary>
          <div class="mt-4 space-y-4">
            <label class="flex items-center justify-between gap-3 rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3">
              <div>
                <div class="text-sm font-medium text-emerald-950">启用 LLM 过滤</div>
                <div class="text-xs text-emerald-700/60">规则未命中时调用模型判断</div>
              </div>
              <input v-model="llmFilterEnabled" type="checkbox" class="h-5 w-5 accent-emerald-400" />
            </label>
            <div class="grid gap-3">
              <input v-model="llmBaseUrl" type="text" aria-label="LLM Base URL" placeholder="Base URL" class="w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15" />
              <div class="grid gap-3 sm:grid-cols-2">
                <input v-model="llmModel" type="text" aria-label="LLM 模型名" placeholder="模型名，例如 qwen3.5:4b" class="w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15" />
                <input v-model="llmTimeoutSec" type="number" min="2" :max="llmTimeoutMaxSec" aria-label="LLM 超时秒数" class="w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15" />
              </div>
              <div class="grid gap-3 sm:grid-cols-2">
                <input v-model="llmRetryCount" type="number" min="0" max="4" aria-label="LLM 重试次数" class="w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15" />
                <input v-model="llmRetryBackoffSec" type="number" min="0.05" max="5" step="0.05" aria-label="LLM 重试退避秒数" class="w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15" />
              </div>
              <input v-model="llmApiKey" type="password" aria-label="LLM API Key" :placeholder="llmApiKeyConfigured ? 'API Key 已保存' : 'API Key（无则填 EMPTY）'" class="w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15" />
            </div>
            <label class="flex items-center justify-between gap-3 rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3">
              <div>
                <div class="text-sm font-medium text-emerald-950">第二条私信启用 LLM 改写</div>
                <div class="text-xs text-emerald-700/60">基于模板生成轻度变化话术</div>
              </div>
              <input v-model="dmLlmRewriteEnabled" type="checkbox" class="h-5 w-5 accent-emerald-400" />
            </label>
            <details class="rounded-2xl border border-emerald-100/90 bg-white/70 p-4">
              <summary class="cursor-pointer list-none text-sm font-medium text-emerald-950">Prompt 与屏蔽词</summary>
              <div class="mt-4 space-y-3">
                <textarea v-model="dmLlmRewritePromptTemplate" aria-label="第二条私信改写 Prompt" placeholder="私信改写 Prompt，支持 {template}" class="min-h-[100px] w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15" />
                <textarea v-model="notifyVoiceBlockKeywords" aria-label="通知不播报关键词" placeholder="通知播报屏蔽词，逗号或换行分隔" class="min-h-[88px] w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15" />
                <textarea v-model="llmIntentPromptTemplate" aria-label="意向分析 Prompt" placeholder="意向分析 Prompt，支持 {content}" class="min-h-[88px] w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15" />
                <textarea v-model="llmFilterPromptTemplate" aria-label="内容过滤 Prompt" placeholder="内容过滤 Prompt，支持 {content}" class="min-h-[88px] w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15" />
              </div>
            </details>
            <label class="space-y-2">
              <span class="text-[11px] font-medium uppercase tracking-[0.12em] text-emerald-700/60">测试评论</span>
              <textarea v-model="llmIntentInput" aria-label="评论意向分析输入" placeholder="输入评论内容，例如：老板 想了解下" class="min-h-[88px] w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15" />
            </label>
            <div class="grid gap-3 sm:grid-cols-3">
              <button type="button" class="rounded-2xl bg-gradient-to-r from-emerald-400 to-teal-400 px-4 py-3 text-sm font-semibold text-emerald-950" @click="handleSaveLlm">保存 AI 配置</button>
              <button type="button" :disabled="llmTestBusy" class="rounded-2xl border border-emerald-200/90 bg-emerald-50/80 px-4 py-3 text-sm font-semibold text-emerald-800 disabled:cursor-not-allowed disabled:opacity-50" @click="handleTestLlm">{{ llmTestBusy ? '测试中...' : '测试模型' }}</button>
              <button type="button" class="rounded-2xl bg-emerald-400 px-4 py-3 text-sm font-semibold text-emerald-950" @click="handleAnalyzeIntent">分析评论</button>
            </div>
            <pre class="max-h-[180px] overflow-auto rounded-2xl border border-emerald-100/90 bg-white/80 p-4 font-mono text-[11px] leading-6 text-emerald-700/80">{{ llmIntentResult }}</pre>
          </div>
        </details>

        <div class="rounded-2xl border border-emerald-100/90 bg-white/70 px-4 py-3 text-xs leading-5 text-emerald-700/80">
          网络代理: <span class="text-emerald-800">{{ browserProxyMeta.configured ? `${browserProxyMeta.source || 'ENV'} · ${browserProxyMeta.display || '已配置'}` : '未配置' }}</span>
        </div>
      </div>
    </details>
  </section>
</template>
