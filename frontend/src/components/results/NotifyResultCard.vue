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

const detailRows = computed(() => [
  { label: '意向', value: props.intentLabel },
  { label: '流程', value: props.flowLabel },
  { label: '回复状态', value: props.isReplied ? `已完成${props.item.notify_reply_time ? ` · ${props.item.notify_reply_time}` : ''}` : '未回复' },
  { label: '状态链接', value: props.item.status_url ? '已获取' : '缺失' },
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
  <article class="rounded-[22px] border border-emerald-100/90 bg-white/75 p-4 shadow-[0_16px_42px_rgba(16,185,129,0.12)]">
    <div class="flex flex-col gap-4">
      <div class="min-w-0 space-y-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <a
            :href="`https://x.com/${String(item.handle || '').replace('@', '')}/with_replies`"
            target="_blank"
            class="font-mono text-base font-semibold text-emerald-600 hover:text-emerald-700"
          >
            {{ item.handle || '-' }}
          </a>
          <div class="flex flex-wrap gap-2">
            <span class="rounded-full border border-emerald-100/90 bg-white/80 px-2.5 py-1 font-mono text-[11px] text-emerald-700/80">{{ item.time || '-' }}</span>
            <span class="rounded-full border px-2.5 py-1 font-mono text-[11px]" :class="flowTone">{{ flowLabel }}</span>
          </div>
        </div>

        <div class="rounded-2xl border border-emerald-100/90 bg-white/90 px-4 py-4 text-base leading-7 text-emerald-950">
          {{ item.content || '-' }}
        </div>

        <div class="flex flex-wrap gap-2 text-[11px] text-emerald-700/60">
          <span v-if="item.notification_type" class="rounded-full border border-emerald-100/90 bg-white/70 px-2.5 py-1 font-mono">{{ item.notification_type }}</span>
          <span v-if="item.notify_retry_time" class="rounded-full border border-amber-400/20 bg-amber-400/10 px-2.5 py-1 font-mono text-amber-700">重试 {{ item.notify_retry_time }}</span>
          <span v-if="item.notify_flow_error_code" class="rounded-full border border-rose-400/20 bg-rose-400/10 px-2.5 py-1 font-mono text-rose-700">{{ item.notify_flow_error_code }}</span>
        </div>
      </div>

      <div class="rounded-2xl border border-emerald-100/90 bg-white/80 p-3">
        <div class="grid gap-2 sm:grid-cols-2">
          <div class="rounded-xl border border-emerald-100/90 bg-white/75 px-3 py-2.5">
            <div class="mb-1 flex items-center justify-between gap-3">
              <span class="font-mono text-[10px] uppercase tracking-[0.12em] text-emerald-700/60">Reply</span>
              <button type="button" class="text-[10px] font-semibold text-emerald-600" @click="emit('apply-default', 'reply')">默认</button>
            </div>
            <div class="line-clamp-2 text-xs leading-6 text-emerald-700">{{ previewText('reply') }}</div>
          </div>

          <div class="rounded-xl border border-emerald-100/90 bg-white/75 px-3 py-2.5">
            <div class="mb-1 flex items-center justify-between gap-3">
              <span class="font-mono text-[10px] uppercase tracking-[0.12em] text-emerald-700/60">DM</span>
              <button type="button" class="text-[10px] font-semibold text-emerald-600" @click="emit('apply-default', 'dm')">默认</button>
            </div>
            <div class="line-clamp-2 text-xs leading-6 text-emerald-700">{{ previewText('dm') }}</div>
          </div>
        </div>

        <div class="mt-3 grid gap-2 sm:grid-cols-3">
          <button type="button" class="rounded-2xl bg-amber-400 px-3 py-3 text-sm font-semibold text-emerald-950" @click="emit('reply')">
            {{ isReplied ? '再次回复' : '回复并私信' }}
          </button>
          <button type="button" class="rounded-2xl border border-emerald-200/90 bg-emerald-50/80 px-3 py-3 text-sm font-semibold text-emerald-800" @click="emit('mark-done')">已处理</button>
          <button
            type="button"
            class="rounded-2xl border border-emerald-200/90 bg-white/75 px-3 py-3 text-sm font-semibold text-emerald-700"
            @click="emit('toggle-details')"
          >
            {{ expanded ? '收起详情' : '详情' }}
          </button>
        </div>
      </div>

      <div v-if="expanded" class="grid gap-4 border-t border-emerald-100/90 pt-4 xl:grid-cols-[minmax(0,1fr)_minmax(280px,360px)]">
        <div class="space-y-4">
          <div v-if="errorText" class="break-words rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 font-mono text-[11px] leading-6 text-rose-700">
            {{ errorText }}
          </div>
          <div v-if="item.notify_retry_time" class="rounded-2xl border border-amber-400/20 bg-amber-400/10 px-4 py-3 font-mono text-[11px] text-amber-700">
            下次重试: {{ item.notify_retry_time }}
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <div
              v-for="row in detailRows"
              :key="row.label"
              class="rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3"
            >
              <div class="font-mono text-[10px] uppercase tracking-[0.12em] text-emerald-700/60">{{ row.label }}</div>
              <div class="mt-2 break-all text-sm text-emerald-800">{{ row.value }}</div>
            </div>
          </div>
          <div v-if="dmGeneratedPreview" class="rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3">
            <div class="font-mono text-[10px] uppercase tracking-[0.12em] text-emerald-700/60">最近私信文案</div>
            <div class="mt-2 whitespace-pre-wrap text-sm leading-6 text-emerald-800">{{ dmGeneratedPreview }}</div>
          </div>
        </div>

        <div class="space-y-3 rounded-2xl border border-emerald-100/90 bg-white/80 p-4">
          <div class="font-mono text-[10px] uppercase tracking-[0.12em] text-emerald-700/60">Flow Composer</div>
          <div class="grid gap-3 xl:grid-cols-1">
            <div class="grid gap-3">
              <select
                :value="selectedReply"
                class="w-full rounded-2xl border border-emerald-100/90 bg-white/90 px-3 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15"
                @change="emit('update:selectedReply', ($event.target as HTMLSelectElement).value)"
              >
                <option value="">选择回复内容...</option>
                <option v-for="option in replyTemplates" :key="option" :value="option">{{ option }}</option>
              </select>
              <select
                :value="selectedDm"
                class="w-full rounded-2xl border border-emerald-100/90 bg-white/90 px-3 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15"
                @change="emit('update:selectedDm', ($event.target as HTMLSelectElement).value)"
              >
                <option value="">选择私信内容...</option>
                <option v-for="option in dmTemplates" :key="option" :value="option">{{ option }}</option>
              </select>
            </div>
          </div>
          <button type="button" class="w-full rounded-2xl border border-emerald-200/90 bg-emerald-50/80 px-3 py-2.5 text-xs font-semibold text-emerald-800" @click="emit('retry')">重试当前流程</button>
        </div>
      </div>
    </div>
  </article>
</template>
