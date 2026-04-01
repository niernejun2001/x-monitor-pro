<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, ref } from 'vue'
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
  serverAudioMeta,
  browserProxyMeta,
} = storeToRefs(app)

const jumpHandle = ref('')
const controlSection = ref<'delegation' | 'voice' | 'ai'>('delegation')
const aiSection = ref<'connection' | 'rewrite' | 'analysis'>('connection')

const controlSectionButtons = [
  { key: 'delegation', label: '委派', hint: '账号与跳转' },
  { key: 'voice', label: '语音', hint: '播报与声音' },
  { key: 'ai', label: 'AI', hint: '过滤与改写' },
] as const

const aiSectionButtons = [
  { key: 'connection', label: '连接' },
  { key: 'rewrite', label: '改写' },
  { key: 'analysis', label: '分析' },
] as const

const controlSectionSummary = computed<Record<'delegation' | 'voice' | 'ai', string>>(() => ({
  delegation: delegatedAccount.value?.trim() ? delegatedAccount.value.trim() : '未绑定',
  voice: notifyTtsEnabled.value ? (notifyTtsVoiceType.value?.trim() || '已启用') : '浏览器兜底',
  ai: llmFilterEnabled.value ? (llmModel.value?.trim() || '模型已启用') : '过滤关闭',
}))

const engineCards = computed(() => [
  {
    label: '运行状态',
    value: isRunning.value ? '运行中' : '待机',
    tone: isRunning.value ? 'border-emerald-400/20 bg-emerald-400/8 text-emerald-200' : 'border-rose-400/20 bg-rose-400/8 text-rose-200',
  },
  {
    label: '通知扫描',
    value: notificationMonitoring.value ? '已启用' : '已关闭',
    tone: notificationMonitoring.value ? 'border-sky-400/20 bg-sky-400/8 text-sky-200' : 'border-slate-800 bg-slate-950/80 text-slate-400',
  },
  {
    label: '浏览器模式',
    value: headlessMode.value ? '无头' : '有头',
    tone: 'border-slate-800 bg-slate-950/80 text-slate-200',
  },
  {
    label: '语音输出',
    value: serverAudioMeta.value.enabled ? `服务端/${serverAudioMeta.value.player}` : '浏览器前端',
    tone: 'border-slate-800 bg-slate-950/80 text-slate-200',
  },
  {
    label: '网络代理',
    value: browserProxyMeta.value.configured
      ? `${browserProxyMeta.value.source || 'ENV'} · ${browserProxyMeta.value.display || '已配置'}`
      : '未配置',
    tone: browserProxyMeta.value.configured
      ? 'border-emerald-400/20 bg-emerald-400/8 text-emerald-200'
      : 'border-amber-400/20 bg-amber-400/8 text-amber-200',
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

async function handleDelegationSave() {
  try {
    await app.saveDelegation()
  } catch (error: any) {
    toast.push(error?.message || '保存委派账户失败', 'error', 4200)
  }
}

async function handleJump() {
  if (!jumpHandle.value.trim()) return
  try {
    await app.jumpToReplies(jumpHandle.value.trim())
  } catch (error: any) {
    toast.push(error?.message || '打开用户回复页失败', 'error', 4200)
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
    <div class="rounded-2xl border border-sky-400/20 bg-gradient-to-br from-sky-400/10 to-emerald-400/5 p-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="font-mono text-[11px] uppercase tracking-[0.12em] text-sky-300">Quick Actions</div>
          <p class="mt-2 text-xs leading-6 text-slate-400">高频控制放在最上面，长配置收进分组，减少来回滚动。</p>
        </div>
        <div class="rounded-2xl border border-sky-400/25 bg-sky-400/10 px-3 py-2 text-right">
          <div class="font-mono text-[10px] uppercase tracking-[0.12em] text-sky-200/80">Token</div>
          <div class="mt-1 text-sm font-semibold text-slate-50">{{ tokenConfigured ? '已配置' : '缺失' }}</div>
        </div>
      </div>

      <div class="mt-4 grid gap-3 sm:grid-cols-2">
        <label class="sm:col-span-2 space-y-2">
          <span class="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">启动 Token</span>
          <input
            v-model="token"
            type="password"
            aria-label="启动 Token"
            :placeholder="tokenConfigured ? '已保存，留空则沿用已存 Token' : '输入 auth_token 后启动监控'"
            class="w-full rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10"
          />
        </label>
        <button
          type="button"
          class="rounded-2xl px-4 py-3 text-sm font-semibold transition"
          :class="isRunning ? 'bg-rose-500 text-white hover:bg-rose-400' : 'bg-emerald-400 text-slate-950 hover:bg-emerald-300'"
          @click="handleStartStop(!isRunning)"
        >
          {{ isRunning ? '停止监控' : '启动监控' }}
        </button>
        <button
          type="button"
          class="rounded-2xl border border-slate-700 bg-slate-950/70 px-4 py-3 text-sm font-semibold text-slate-100 transition hover:border-slate-600"
          @click="handleTestVoice"
        >
          测试播报
        </button>
      </div>

      <div class="mt-4 grid grid-cols-2 gap-2">
        <div
          v-for="card in engineCards"
          :key="card.label"
          class="rounded-2xl border px-3 py-3"
          :class="card.tone"
        >
          <div class="font-mono text-[10px] uppercase tracking-[0.12em] opacity-70">{{ card.label }}</div>
          <div class="mt-2 text-sm font-semibold">{{ card.value }}</div>
        </div>
      </div>

      <div class="mt-4 grid gap-3 sm:grid-cols-2">
        <label class="flex items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3">
          <div>
            <div class="text-sm font-medium text-slate-100">通知扫描</div>
            <div class="text-xs text-slate-500">控制通知标签页抓取开关</div>
          </div>
          <input v-model="notificationMonitoring" type="checkbox" class="h-5 w-5 accent-emerald-400" @change="handleNotificationToggle" />
        </label>
        <label class="flex items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3">
          <div>
            <div class="text-sm font-medium text-slate-100">浏览器模式</div>
            <div class="text-xs text-slate-500">切换有头 / 无头执行</div>
          </div>
          <input v-model="headlessMode" type="checkbox" class="h-5 w-5 accent-emerald-400" @change="handleHeadlessToggle" />
        </label>
      </div>
    </div>

    <div class="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
      <div class="mb-4 flex items-center justify-between gap-3">
        <div>
          <div class="font-mono text-[11px] uppercase tracking-[0.12em] text-sky-300">Workbench</div>
          <div class="mt-1 text-sm font-medium text-slate-100">控制中心分组</div>
        </div>
        <div class="rounded-full border border-slate-800 px-2.5 py-1 text-[11px] text-slate-400">
          {{ controlSectionSummary[controlSection] }}
        </div>
      </div>

      <div class="grid grid-cols-3 gap-2">
        <button
          v-for="button in controlSectionButtons"
          :key="button.key"
          type="button"
          class="rounded-2xl border px-3 py-2 text-left transition"
          :class="button.key === controlSection
            ? 'border-sky-400/35 bg-sky-400/12 text-slate-50'
            : 'border-slate-800 bg-slate-900/70 text-slate-400 hover:border-slate-700 hover:text-slate-200'"
          @click="controlSection = button.key"
        >
          <div class="text-xs font-semibold">{{ button.label }}</div>
          <div class="mt-1 text-[10px] text-slate-500">{{ button.hint }}</div>
        </button>
      </div>

      <div v-if="controlSection === 'delegation'" class="mt-4 space-y-4">
        <div class="rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-xs leading-6 text-slate-400">
          当前委派账户: <span class="font-mono text-slate-100">{{ controlSectionSummary.delegation }}</span>
        </div>
        <div class="grid gap-3">
          <label class="space-y-2">
            <span class="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">委派账户</span>
            <input
              v-model="delegatedAccount"
              type="text"
              aria-label="委派账户"
              placeholder="@username"
              class="w-full rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10"
            />
          </label>
          <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_140px]">
            <label class="space-y-2">
              <span class="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">快速跳转回复页</span>
              <input
                v-model="jumpHandle"
                type="text"
                aria-label="推特用户 ID"
                placeholder="输入 @ID，回车打开该用户回复页"
                class="w-full rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10"
                @keydown.enter.prevent="handleJump"
              />
            </label>
            <button type="button" class="mt-auto rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm font-semibold text-slate-200" @click="handleJump">打开回复页</button>
          </div>
          <button type="button" class="w-full rounded-2xl bg-sky-400 px-4 py-3 text-sm font-semibold text-slate-950" @click="handleDelegationSave">保存账户配置</button>
        </div>
      </div>

      <div v-else-if="controlSection === 'voice'" class="mt-4 space-y-4">
        <label class="flex items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3">
          <div>
            <div class="text-sm font-medium text-slate-100">启用豆包 TTS</div>
            <div class="text-xs text-slate-500">服务端播报失败时仍可用浏览器兜底</div>
          </div>
          <input v-model="notifyTtsEnabled" type="checkbox" class="h-5 w-5 accent-emerald-400" />
        </label>

        <div class="rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-300">
          {{ voiceStatusText }}
        </div>

        <div class="grid gap-3 sm:grid-cols-2">
          <label class="space-y-2">
            <span class="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">App ID</span>
            <input v-model="notifyTtsAppId" type="text" aria-label="豆包 App ID" placeholder="AppID" class="w-full rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10" />
          </label>
          <label class="space-y-2">
            <span class="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">音色</span>
            <input v-model="notifyTtsVoiceType" type="text" aria-label="豆包音色" placeholder="例如 zh_female_vv_uranus_bigtts" class="w-full rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10" />
          </label>
        </div>

        <details class="group rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
          <summary class="cursor-pointer list-none text-sm font-medium text-slate-100">
            认证与密钥
            <span class="ml-2 text-xs text-slate-500 group-open:hidden">展开后配置 Access Token / Secret</span>
          </summary>
          <div class="mt-4 space-y-3">
            <input v-model="notifyTtsAccessToken" type="password" aria-label="豆包 Access Token" :placeholder="notifyTtsAccessTokenConfigured ? '已保存，留空保持不变' : 'Access Token'" class="w-full rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10" />
            <input v-model="notifyTtsSecretKey" type="password" aria-label="豆包 Secret Key" :placeholder="notifyTtsSecretKeyConfigured ? '已保存，留空保持不变' : 'Secret Key（可选）'" class="w-full rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10" />
          </div>
        </details>

        <div class="grid gap-3 sm:grid-cols-2">
          <button type="button" class="rounded-2xl bg-sky-400 px-4 py-3 text-sm font-semibold text-slate-950" @click="handleSaveNotifyTts">保存豆包配置</button>
          <button type="button" class="rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm font-semibold text-slate-200" @click="handleTestVoice">立即试播</button>
        </div>

        <details class="group rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
          <summary class="cursor-pointer list-none text-sm font-medium text-slate-100">
            最近播报结果
            <span class="ml-2 text-xs text-slate-500 group-open:hidden">展开查看返回文本</span>
          </summary>
          <pre class="mt-4 max-h-[180px] overflow-auto rounded-2xl border border-slate-800 bg-slate-950/80 p-4 font-mono text-[11px] leading-6 text-slate-400">{{ notifyTtsResult }}</pre>
        </details>
      </div>

      <div v-else class="mt-4 space-y-4">
        <div class="rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-300">
          {{ aiStatusText }}
        </div>

        <div class="grid grid-cols-3 gap-2">
          <button
            v-for="button in aiSectionButtons"
            :key="button.key"
            type="button"
            class="rounded-2xl border px-3 py-2 text-xs font-medium transition"
            :class="button.key === aiSection
              ? 'border-sky-400/35 bg-sky-400/12 text-slate-50'
              : 'border-slate-800 bg-slate-900/70 text-slate-400 hover:border-slate-700 hover:text-slate-200'"
            @click="aiSection = button.key"
          >
            {{ button.label }}
          </button>
        </div>

        <div v-if="aiSection === 'connection'" class="space-y-4">
          <label class="flex items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3">
            <div>
              <div class="text-sm font-medium text-slate-100">启用 LLM 过滤</div>
              <div class="text-xs text-slate-500">规则未命中时调用小模型判定</div>
            </div>
            <input v-model="llmFilterEnabled" type="checkbox" class="h-5 w-5 accent-emerald-400" />
          </label>

          <div class="grid gap-3">
            <label class="space-y-2">
              <span class="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">Base URL</span>
              <input v-model="llmBaseUrl" type="text" aria-label="LLM Base URL" placeholder="Base URL" class="w-full rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10" />
            </label>
            <div class="grid gap-3 sm:grid-cols-2">
              <label class="space-y-2">
                <span class="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">模型名</span>
                <input v-model="llmModel" type="text" aria-label="LLM 模型名" placeholder="例如 qwen3.5:4b" class="w-full rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10" />
              </label>
              <label class="space-y-2">
                <span class="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">超时秒数</span>
                <input v-model="llmTimeoutSec" type="number" min="2" :max="llmTimeoutMaxSec" aria-label="LLM 超时秒数" class="w-full rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10" />
              </label>
            </div>
          </div>

          <details class="group rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
            <summary class="cursor-pointer list-none text-sm font-medium text-slate-100">
              鉴权与连通性
              <span class="ml-2 text-xs text-slate-500 group-open:hidden">展开配置 API Key 并测试</span>
            </summary>
            <div class="mt-4 space-y-3">
              <input v-model="llmApiKey" type="password" aria-label="LLM API Key" :placeholder="llmApiKeyConfigured ? '已保存，留空保持不变' : 'API Key（无则填 EMPTY）'" class="w-full rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10" />
              <div class="grid gap-3 sm:grid-cols-2">
                <button type="button" class="rounded-2xl bg-sky-400 px-4 py-3 text-sm font-semibold text-slate-950" @click="handleSaveLlm">保存配置</button>
                <button type="button" class="rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm font-semibold text-slate-200" @click="handleTestLlm">测试模型</button>
              </div>
            </div>
          </details>
        </div>

        <div v-else-if="aiSection === 'rewrite'" class="space-y-4">
          <label class="flex items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3">
            <div>
              <div class="text-sm font-medium text-slate-100">第二条私信启用 LLM 改写</div>
              <div class="text-xs text-slate-500">基于模板生成轻度变化的话术</div>
            </div>
            <input v-model="dmLlmRewriteEnabled" type="checkbox" class="h-5 w-5 accent-emerald-400" />
          </label>

          <label class="space-y-2">
            <span class="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">改写 Prompt</span>
            <textarea v-model="dmLlmRewritePromptTemplate" aria-label="第二条私信改写 Prompt" placeholder="支持 {template} 占位" class="min-h-[120px] w-full rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10" />
          </label>

          <details class="group rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
            <summary class="cursor-pointer list-none text-sm font-medium text-slate-100">
              通知播报屏蔽词
              <span class="ml-2 text-xs text-slate-500 group-open:hidden">展开维护关键词</span>
            </summary>
            <textarea v-model="notifyVoiceBlockKeywords" aria-label="通知不播报关键词" placeholder="逗号或换行分隔" class="mt-4 min-h-[120px] w-full rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10" />
          </details>

          <button type="button" class="w-full rounded-2xl bg-sky-400 px-4 py-3 text-sm font-semibold text-slate-950" @click="handleSaveLlm">保存改写配置</button>
        </div>

        <div v-else class="space-y-4">
          <label class="space-y-2">
            <span class="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">测试评论</span>
            <textarea v-model="llmIntentInput" aria-label="评论意向分析输入" placeholder="输入评论内容，例如：老板 想了解下" class="min-h-[112px] w-full rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10" />
          </label>
          <button type="button" class="w-full rounded-2xl bg-emerald-400 px-4 py-3 text-sm font-semibold text-slate-950" @click="handleAnalyzeIntent">分析评论意向</button>

          <details class="group rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
            <summary class="cursor-pointer list-none text-sm font-medium text-slate-100">
              分析 Prompt
              <span class="ml-2 text-xs text-slate-500 group-open:hidden">展开编辑两个 Prompt 模板</span>
            </summary>
            <div class="mt-4 space-y-3">
              <textarea v-model="llmIntentPromptTemplate" aria-label="意向分析 Prompt" placeholder="意向分析 Prompt（支持 {content} 占位）" class="min-h-[120px] w-full rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10" />
              <textarea v-model="llmFilterPromptTemplate" aria-label="内容过滤 Prompt" placeholder="内容过滤 Prompt（支持 {content} 占位）" class="min-h-[120px] w-full rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10" />
              <button type="button" class="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm font-semibold text-slate-200" @click="handleSaveLlm">保存分析配置</button>
            </div>
          </details>

          <details class="group rounded-2xl border border-slate-800 bg-slate-950/70 p-4" open>
            <summary class="cursor-pointer list-none text-sm font-medium text-slate-100">
              分析结果
              <span class="ml-2 text-xs text-slate-500 group-open:hidden">展开查看输出</span>
            </summary>
            <pre class="mt-4 max-h-[220px] overflow-auto rounded-2xl border border-slate-800 bg-slate-950/80 p-4 font-mono text-[11px] leading-6 text-slate-400">{{ llmIntentResult }}</pre>
          </details>
        </div>
      </div>
    </div>
  </section>
</template>
