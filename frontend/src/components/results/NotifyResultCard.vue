<script setup lang="ts">
import { computed } from 'vue'
import type { PendingItem } from '../../types'

const props = defineProps<{
  item: PendingItem
  expanded: boolean
  isReplied: boolean
  flowLabel: string
  flowTone: string
  intentLabel: string
  intentTone: string
  replyTemplates: string[]
  dmTemplates: string[]
  selectedReply: string
  selectedDm: string
}>()

const emit = defineEmits<{
  (e: 'toggle-details'): void
  (e: 'mark-done'): void
  (e: 'reply'): void
  (e: 'retry'): void
  (e: 'apply-default', type: 'reply' | 'dm'): void
  (e: 'update:selectedReply', value: string): void
  (e: 'update:selectedDm', value: string): void
}>()

function previewText(type: 'reply' | 'dm') {
  if (type === 'reply') return props.selectedReply || String(props.item.notify_reply_text || '未选择')
  return props.selectedDm || String(props.item.notify_dm_text || '未选择')
}

const statusCards = computed(() => [
  {
    label: '意向',
    value: props.intentLabel,
    tone: props.intentTone,
  },
  {
    label: '流程',
    value: props.flowLabel,
    tone: props.flowTone,
  },
  {
    label: '回复',
    value: props.isReplied ? `已完成${props.item.notify_reply_time ? ` · ${props.item.notify_reply_time}` : ''}` : '未回复',
    tone: props.isReplied ? 'border-emerald-400/20 bg-emerald-400/10 text-emerald-200' : 'border-slate-800 bg-slate-950/70 text-slate-400',
  },
  {
    label: '状态链接',
    value: props.item.status_url ? '已获取' : '缺失',
    tone: props.item.status_url ? 'border-sky-400/20 bg-sky-400/10 text-sky-200' : 'border-slate-800 bg-slate-950/70 text-slate-400',
  },
])

const detailRows = computed(() => [
  { label: '通知类型', value: String(props.item.notification_type || '-') },
  { label: '通知来源', value: String(props.item.source || '-') },
  { label: '目标状态', value: String(props.item.status_handle || props.item.status_id || '-') },
  { label: '重试时间', value: String(props.item.notify_retry_time || '-') },
].filter((row) => row.value && row.value !== '-'))

const errorText = computed(() => {
  if (props.item.notify_flow_error_code || props.item.notify_flow_error_detail || props.item.notify_flow_error) {
    return `${props.item.notify_flow_error_code || '错误'} ${props.item.notify_flow_error_detail || props.item.notify_flow_error || ''}`.trim()
  }
  return ''
})

const dmGeneratedPreview = computed(() => (
  String(props.item.notify_dm_text_generated || props.item.notify_dm_text || '').trim()
))
</script>

<template>
  <article class="rounded-[22px] border border-slate-800 bg-slate-950/55 p-4 shadow-[0_16px_42px_rgba(2,6,23,0.28)]">
    <div class="flex flex-col gap-4">
      <div class="min-w-0 space-y-3">
        <div class="flex flex-wrap items-center gap-2">
          <a
            :href="`https://x.com/${String(item.handle || '').replace('@', '')}/with_replies`"
            target="_blank"
            class="font-mono text-sm font-semibold text-sky-300 hover:text-sky-200"
          >
            {{ item.handle || '-' }}
          </a>
          <span class="rounded-full border border-slate-800 bg-slate-950/80 px-2.5 py-1 font-mono text-[11px] text-slate-400">{{ item.time || '-' }}</span>
          <span class="rounded-full border px-2.5 py-1 font-mono text-[11px]" :class="intentTone">{{ intentLabel }}</span>
          <span class="rounded-full border px-2.5 py-1 font-mono text-[11px]" :class="flowTone">{{ flowLabel }}</span>
        </div>

        <div class="rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-4 text-sm leading-7 text-slate-200">
          {{ item.content || '-' }}
        </div>

        <div class="flex flex-wrap gap-2 text-[11px] text-slate-500">
          <span v-if="item.notification_type" class="rounded-full border border-slate-800 bg-slate-950/70 px-2.5 py-1 font-mono">{{ item.notification_type }}</span>
          <span v-if="item.notify_retry_time" class="rounded-full border border-amber-400/20 bg-amber-400/10 px-2.5 py-1 font-mono text-amber-200">重试 {{ item.notify_retry_time }}</span>
          <span v-if="item.notify_flow_error_code" class="rounded-full border border-rose-400/20 bg-rose-400/10 px-2.5 py-1 font-mono text-rose-200">{{ item.notify_flow_error_code }}</span>
        </div>
      </div>

      <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div
            v-for="card in statusCards"
            :key="card.label"
            class="rounded-2xl border px-3 py-3"
            :class="card.tone"
          >
            <div class="font-mono text-[10px] uppercase tracking-[0.12em] opacity-70">{{ card.label }}</div>
            <div class="mt-2 text-sm font-semibold">{{ card.value }}</div>
          </div>
        </div>

        <div class="rounded-2xl border border-slate-800 bg-slate-950/80 p-3">
          <div class="mb-3 flex items-center justify-between gap-3">
            <div class="text-xs" :class="isReplied ? 'font-semibold text-emerald-400' : 'text-slate-500'">
              {{ isReplied ? `已回复${item.notify_reply_time ? ` (${item.notify_reply_time})` : ''}` : '未回复' }}
            </div>
            <button
              type="button"
              class="rounded-xl border border-slate-700 bg-slate-900/70 px-3 py-2 text-[11px] font-semibold text-slate-300"
              @click="emit('toggle-details')"
            >
              {{ expanded ? '收起' : '展开' }}
            </button>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <button type="button" class="rounded-2xl bg-amber-400 px-3 py-2.5 text-xs font-semibold text-slate-950" @click="emit('reply')">
              {{ isReplied ? '再次回复' : '回复' }}
            </button>
            <button type="button" class="rounded-2xl border border-slate-700 bg-slate-900/70 px-3 py-2.5 text-xs font-semibold text-slate-200" @click="emit('mark-done')">已处理</button>
          </div>

          <div class="mt-3 grid gap-2 sm:grid-cols-2">
            <div class="rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2.5">
              <div class="mb-1 flex items-center justify-between gap-3">
                <span class="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-500">Reply</span>
                <button type="button" class="text-[10px] font-semibold text-sky-300" @click="emit('apply-default', 'reply')">默认模板</button>
              </div>
              <div class="line-clamp-2 text-xs leading-6 text-slate-300">{{ previewText('reply') }}</div>
            </div>

            <div class="rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2.5">
              <div class="mb-1 flex items-center justify-between gap-3">
                <span class="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-500">DM</span>
                <button type="button" class="text-[10px] font-semibold text-sky-300" @click="emit('apply-default', 'dm')">默认模板</button>
              </div>
              <div class="line-clamp-2 text-xs leading-6 text-slate-300">{{ previewText('dm') }}</div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="expanded" class="grid gap-4 border-t border-slate-800 pt-4 xl:grid-cols-[minmax(0,1fr)_minmax(280px,360px)]">
        <div class="space-y-4">
          <div v-if="errorText" class="break-words rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 font-mono text-[11px] leading-6 text-rose-200">
            {{ errorText }}
          </div>
          <div v-if="item.notify_retry_time" class="rounded-2xl border border-amber-400/20 bg-amber-400/10 px-4 py-3 font-mono text-[11px] text-amber-200">
            下次重试: {{ item.notify_retry_time }}
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <div
              v-for="row in detailRows"
              :key="row.label"
              class="rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3"
            >
              <div class="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-500">{{ row.label }}</div>
              <div class="mt-2 break-all text-sm text-slate-200">{{ row.value }}</div>
            </div>
          </div>
          <div v-if="dmGeneratedPreview" class="rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3">
            <div class="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-500">最近私信文案</div>
            <div class="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-200">{{ dmGeneratedPreview }}</div>
          </div>
        </div>

        <div class="space-y-3 rounded-2xl border border-slate-800 bg-slate-950/80 p-4">
          <div class="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-500">Flow Composer</div>
          <div class="grid gap-3 xl:grid-cols-1">
            <div class="grid gap-3">
              <select
                :value="selectedReply"
                class="w-full rounded-2xl border border-slate-800 bg-slate-950/90 px-3 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10"
                @change="emit('update:selectedReply', ($event.target as HTMLSelectElement).value)"
              >
                <option value="">选择回复内容...</option>
                <option v-for="option in replyTemplates" :key="option" :value="option">{{ option }}</option>
              </select>
              <select
                :value="selectedDm"
                class="w-full rounded-2xl border border-slate-800 bg-slate-950/90 px-3 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10"
                @change="emit('update:selectedDm', ($event.target as HTMLSelectElement).value)"
              >
                <option value="">选择私信内容...</option>
                <option v-for="option in dmTemplates" :key="option" :value="option">{{ option }}</option>
              </select>
            </div>
          </div>
          <button type="button" class="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-3 py-2.5 text-xs font-semibold text-slate-200" @click="emit('retry')">重试当前流程</button>
        </div>
      </div>
    </div>
  </article>
</template>
