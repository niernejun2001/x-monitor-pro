<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, ref } from 'vue'
import { useAppStore } from '../../stores/app'
import { useTasksStore } from '../../stores/tasks'
import { useToastStore } from '../../stores/toast'

const app = useAppStore()
const tasksStore = useTasksStore()
const toast = useToastStore()
const { tasks } = storeToRefs(tasksStore)
const { dmStatsBusy, dmDailyPushBusy, dmRecentContacts, enterpriseWechatWebhookUrl } = storeToRefs(app)
const newTaskUrl = ref('')

const dmContactsCopyText = computed(() => dmRecentContacts.value?.copy_text || '')
const dmStatsHint = computed(() => {
  const current = dmRecentContacts.value
  if (!current) return '每天早上 9 点会自动统计一次，也可以手动立即统计。'
  const capturedAt = current.captured_at ? `上次: ${current.captured_at}` : '还没有统计时间'
  const nextRunAt = Number(current.next_run_at || 0)
  const nextRun = nextRunAt > 0 ? new Date(nextRunAt * 1000).toLocaleString() : '明早 9 点'
  return `${capturedAt}，下次: ${nextRun}`
})

async function handleAddTask() {
  if (!newTaskUrl.value.trim()) {
    toast.push('请输入推文链接', 'error', 3200)
    return
  }
  try {
    await tasksStore.add(newTaskUrl.value.trim())
    newTaskUrl.value = ''
    toast.push('监控目标已添加', 'success')
  } catch (error: any) {
    toast.push(error?.message || '添加监控失败', 'error', 4200)
  }
}

async function handleRemoveTask(url: string) {
  try {
    await tasksStore.remove(url)
    toast.push('监控目标已移除', 'success')
  } catch (error: any) {
    toast.push(error?.message || '移除失败', 'error', 4200)
  }
}

async function handleDmStats() {
  try {
    await app.fetchDmRecentContacts()
  } catch (error: any) {
    toast.push(error?.message || '统计私信联系人失败', 'error', 4200)
  }
}

async function handleCopyDmContacts() {
  const text = dmContactsCopyText.value.trim()
  if (!text) {
    toast.push('暂无可复制的私信联系人', 'error', 3200)
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    toast.push('私信联系人已复制', 'success')
  } catch {
    toast.push('复制失败，请手动选中文本复制', 'error', 4200)
  }
}

async function handleSaveWechatWebhook() {
  try {
    await app.saveEnterpriseWechatWebhook()
  } catch (error: any) {
    toast.push(error?.message || '保存企业微信 Webhook 失败', 'error', 4200)
  }
}

async function handlePushDailyTest() {
  try {
    await app.pushDailyDmContactsTest()
  } catch (error: any) {
    toast.push(error?.message || '企业微信测试推送失败', 'error', 5200)
  }
}
</script>

<template>
  <section class="space-y-4">
    <div class="rounded-3xl border border-emerald-100/90 bg-white/75 p-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="font-mono text-[11px] uppercase tracking-[0.12em] text-emerald-600">Targets</div>
          <div class="mt-1 text-base font-semibold text-emerald-950">监控目标</div>
          <div class="mt-2 text-xs leading-6 text-emerald-700/60">粘贴推文链接即可添加，已有目标在下方直接管理。</div>
        </div>
        <div class="rounded-2xl border border-emerald-100/90 bg-white/80 px-3 py-2 text-right">
          <div class="font-mono text-[10px] uppercase tracking-[0.12em] text-emerald-700/60">Total</div>
          <div class="mt-1 text-lg font-semibold text-emerald-950">{{ tasks.length }}</div>
        </div>
      </div>

      <div class="mt-4 grid gap-3">
        <label class="space-y-2">
          <span class="text-[11px] font-medium uppercase tracking-[0.12em] text-emerald-700/60">推文链接</span>
          <input
            v-model="newTaskUrl"
            type="text"
            aria-label="监控推文链接"
            placeholder="粘贴推文链接..."
            class="w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15"
          />
        </label>
        <button
          type="button"
          class="w-full rounded-2xl bg-emerald-400 px-4 py-3 text-sm font-semibold text-emerald-950"
          @click="handleAddTask"
        >
          添加目标
        </button>
      </div>
    </div>

    <div class="rounded-3xl border border-emerald-100/90 bg-white/75 p-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="font-mono text-[11px] uppercase tracking-[0.12em] text-emerald-600">DM Stats</div>
          <div class="mt-1 text-base font-semibold text-emerald-950">最近24小时私信用户</div>
          <div class="mt-2 text-xs leading-6 text-emerald-700/60">读取 x.com/i/chat 的会话列表，只统计名称和 @ID，不打开对话、不发送消息。{{ dmStatsHint }}</div>
        </div>
        <div class="rounded-2xl border border-emerald-100/90 bg-white/80 px-3 py-2 text-right">
          <div class="font-mono text-[10px] uppercase tracking-[0.12em] text-emerald-700/60">Users</div>
          <div class="mt-1 text-lg font-semibold text-emerald-950">{{ dmRecentContacts?.count || 0 }}</div>
        </div>
      </div>

      <div class="mt-4 grid gap-3 sm:grid-cols-2">
        <button
          type="button"
          :disabled="dmStatsBusy"
          class="rounded-2xl bg-gradient-to-r from-emerald-400 to-lime-300 px-4 py-3 text-sm font-semibold text-emerald-950 shadow-[0_12px_24px_rgba(16,185,129,0.14)] transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60"
          @click="handleDmStats"
        >
          {{ dmStatsBusy ? '统计中...' : '统计私信用户' }}
        </button>
        <button
          type="button"
          class="rounded-2xl border border-emerald-200/90 bg-white/80 px-4 py-3 text-sm font-semibold text-emerald-800 transition hover:border-emerald-400"
          @click="handleCopyDmContacts"
        >
          复制结果
        </button>
      </div>

      <textarea
        :value="dmContactsCopyText"
        readonly
        aria-label="最近24小时私信用户统计结果"
        placeholder="点击“统计私信用户”后，这里会显示：名称 + @ID"
        class="mt-3 min-h-[140px] w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 font-mono text-xs leading-5 text-emerald-950 outline-none"
      />
      <div v-if="dmRecentContacts?.msg" class="mt-2 text-xs text-emerald-700/60">
        {{ dmRecentContacts.msg }}，扫描行数 {{ dmRecentContacts.scanned_rows || 0 }}
      </div>
      <div v-if="dmRecentContacts?.last_error" class="mt-2 text-xs text-rose-600">
        最近错误: {{ dmRecentContacts.last_error }}
      </div>

      <div class="mt-4 rounded-2xl border border-emerald-100/90 bg-emerald-50/60 p-3">
        <label class="space-y-2">
          <span class="text-[11px] font-medium uppercase tracking-[0.12em] text-emerald-700/60">企业微信 Webhook</span>
          <input
            v-model="enterpriseWechatWebhookUrl"
            type="url"
            aria-label="企业微信 Webhook 地址"
            placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
            class="w-full rounded-2xl border border-emerald-100/90 bg-white/85 px-4 py-3 text-xs text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15"
          />
        </label>
        <div class="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div class="text-xs leading-5 text-emerald-700/60">用于后续推送昨日 9 点到今日 9 点的私信统计，可随时替换。</div>
          <div class="flex shrink-0 gap-2">
            <button
              type="button"
              class="rounded-2xl border border-emerald-200/90 bg-white px-4 py-2.5 text-xs font-semibold text-emerald-800 transition hover:border-emerald-400"
              @click="handleSaveWechatWebhook"
            >
              保存钩子
            </button>
            <button
              type="button"
              :disabled="dmDailyPushBusy"
              class="rounded-2xl bg-emerald-500 px-4 py-2.5 text-xs font-semibold text-white transition hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-60"
              @click="handlePushDailyTest"
            >
              {{ dmDailyPushBusy ? '推送中...' : '测试推送' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="rounded-3xl border border-emerald-100/90 bg-white/70 p-3">
      <div class="mb-3 flex items-center justify-between gap-3 px-1">
        <div class="text-sm font-semibold text-emerald-950">已添加目标</div>
        <div class="text-xs text-emerald-700/60">{{ tasks.length }} 条</div>
      </div>

      <div v-if="tasks.length" class="max-h-[520px] space-y-2 overflow-y-auto pr-1">
        <article
          v-for="task in tasks"
          :key="task.url"
          class="rounded-2xl border border-emerald-100/90 bg-white/75 p-3"
        >
          <div class="break-all font-mono text-xs leading-5 text-emerald-700">{{ task.url }}</div>
          <div class="mt-3 flex items-center justify-between gap-3">
            <span class="rounded-full border border-emerald-100/90 bg-emerald-50/80 px-2.5 py-1 text-[11px] text-emerald-700/70">
              上次检查: {{ task.last_check || '等待' }}
            </span>
            <button
              type="button"
              class="rounded-full bg-rose-500 px-3 py-1.5 text-xs font-semibold text-white"
              @click="handleRemoveTask(task.url)"
            >
              删除
            </button>
          </div>
        </article>
      </div>

      <div v-else class="rounded-2xl border border-dashed border-emerald-100/90 bg-white/70 px-4 py-8 text-center text-sm text-emerald-700/60">
        还没有监控目标
      </div>
    </div>
  </section>
</template>
