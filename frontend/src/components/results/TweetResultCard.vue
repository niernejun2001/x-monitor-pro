<script setup lang="ts">
import { computed } from 'vue'
import type { PendingItem } from '../../types'

const props = defineProps<{
  item: PendingItem
}>()

const emit = defineEmits<{
  (e: 'mark-done'): void
  (e: 'open'): void
}>()

const statusCards = computed(() => [
  {
    label: '来源状态',
    value: props.item.status_url ? '可打开' : '缺失',
    tone: props.item.status_url ? 'border-sky-400/20 bg-sky-400/10 text-sky-200' : 'border-slate-800 bg-slate-950/70 text-slate-400',
  },
  {
    label: '状态绑定',
    value: props.item.status_id ? '已关联' : '未关联',
    tone: props.item.status_id ? 'border-emerald-400/20 bg-emerald-400/10 text-emerald-200' : 'border-slate-800 bg-slate-950/70 text-slate-400',
  },
  {
    label: '作者',
    value: String(props.item.handle || '-'),
    tone: 'border-slate-800 bg-slate-950/70 text-slate-200',
  },
  {
    label: '捕获时间',
    value: String(props.item.time || '-'),
    tone: 'border-slate-800 bg-slate-950/70 text-slate-200',
  },
])

const detailRows = computed(() => [
  { label: '推文来源', value: String(props.item.source || '-') },
  { label: '状态 ID', value: String(props.item.status_id || '-') },
  { label: '状态地址', value: String(props.item.status_url || '-') },
  { label: '状态作者', value: String(props.item.status_handle || '-') },
].filter((row) => row.value && row.value !== '-'))
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
        </div>
        <div class="rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-4 text-sm leading-7 text-slate-200">
          {{ item.content || '-' }}
        </div>
        <div class="flex flex-wrap gap-2 text-[11px] text-slate-500">
          <span v-if="item.status_id" class="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2.5 py-1 font-mono text-emerald-200">已关联状态</span>
          <span v-if="item.status_url" class="rounded-full border border-slate-800 bg-slate-950/70 px-2.5 py-1 font-mono">可打开来源</span>
        </div>
      </div>

      <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_160px]">
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div
            v-for="card in statusCards"
            :key="card.label"
            class="rounded-2xl border px-4 py-3"
            :class="card.tone"
          >
            <div class="font-mono text-[10px] uppercase tracking-[0.12em] opacity-70">{{ card.label }}</div>
            <div class="mt-2 break-all text-sm font-semibold">{{ card.value }}</div>
          </div>
        </div>

        <div class="grid gap-2">
          <button type="button" class="rounded-2xl bg-emerald-400 px-4 py-2.5 text-xs font-semibold text-slate-950" @click="emit('open')">打开来源</button>
          <button type="button" class="rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-2.5 text-xs font-semibold text-slate-200" @click="emit('mark-done')">已处理</button>
        </div>
      </div>

      <div v-if="detailRows.length" class="grid gap-3 sm:grid-cols-2">
        <div
          v-for="row in detailRows"
          :key="row.label"
          class="rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3"
        >
          <div class="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-500">{{ row.label }}</div>
          <div class="mt-2 break-all text-sm text-slate-200">{{ row.value }}</div>
        </div>
      </div>
    </div>
  </article>
</template>
