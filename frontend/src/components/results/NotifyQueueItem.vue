<script setup lang="ts">
import type { PendingItem } from '../../types'

defineProps<{
  item: PendingItem
  active: boolean
  selected: boolean
  replied: boolean
  flowLabel: string
  flowTone: string
  intentLabel: string
  intentTone: string
}>()

const emit = defineEmits<{
  (e: 'select'): void
  (e: 'toggle-select'): void
}>()
</script>

<template>
  <div
    class="w-full rounded-[20px] border p-4 text-left transition"
    :class="active
      ? 'border-emerald-400/50 bg-emerald-400/10 shadow-[0_14px_28px_rgba(14,165,233,0.08)]'
      : 'border-emerald-100/90 bg-white/70 hover:border-emerald-200/90 hover:bg-white/80'"
  >
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            class="grid h-5 w-5 place-items-center rounded-md border transition"
            :class="selected
              ? 'border-emerald-400 bg-emerald-400/20 text-emerald-700'
              : 'border-emerald-200/90 bg-white/70 text-transparent hover:border-emerald-300'"
            @click.stop="emit('toggle-select')"
          >
            ✓
          </button>
          <span class="font-mono text-sm font-semibold text-emerald-600">{{ item.handle || '-' }}</span>
          <span class="rounded-full border border-emerald-100/90 bg-white/70 px-2 py-0.5 font-mono text-[10px] text-emerald-700/80">{{ item.time || '-' }}</span>
        </div>
        <button type="button" class="mt-2 block w-full text-left" @click="emit('select')">
          <div class="line-clamp-2 text-sm leading-6 text-emerald-800">{{ item.content || '-' }}</div>
        </button>
      </div>
      <span class="mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full" :class="replied ? 'bg-emerald-400' : (item.notify_retry_time ? 'bg-amber-400' : 'bg-emerald-200')" />
    </div>

    <button type="button" class="mt-3 flex w-full flex-wrap gap-2 text-left" @click="emit('select')">
      <span class="rounded-full border px-2 py-1 font-mono text-[10px]" :class="intentTone">{{ intentLabel }}</span>
      <span class="rounded-full border px-2 py-1 font-mono text-[10px]" :class="flowTone">{{ flowLabel }}</span>
      <span v-if="item.notify_flow_error_code" class="rounded-full border border-rose-400/20 bg-rose-400/10 px-2 py-1 font-mono text-[10px] text-rose-700">{{ item.notify_flow_error_code }}</span>
      <span v-if="item.notify_retry_time" class="rounded-full border border-amber-400/20 bg-amber-400/10 px-2 py-1 font-mono text-[10px] text-amber-700">重试中</span>
    </button>
  </div>
</template>
