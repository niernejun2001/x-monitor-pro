<script setup lang="ts">
import { ref } from 'vue'
import type { PendingItem } from '../../types'
import NotifyQueueItem from './NotifyQueueItem.vue'
import NotifyResultCard from './NotifyResultCard.vue'

interface CommandAction {
  key: string
  label: string
  tone?: 'neutral' | 'accent' | 'success' | 'warning'
  disabled?: boolean
}

const props = defineProps<{
  notifyCount: number
  searchText: string
  statusFilter: 'all' | 'todo' | 'retry' | 'done'
  statusButtons: Array<{ key: string; label: string; count: number }>
  commandActions: CommandAction[]
  commandHints: string[]
  allItemsCount: number
  filteredItems: PendingItem[]
  selectedIndex: number
  selectedVisibleCount: number
  selectedItem: PendingItem | null
  selectedReply: string
  selectedDm: string
  expanded: boolean
  replyTemplates: string[]
  dmTemplates: string[]
  isReplied: (item: PendingItem) => boolean
  flowLabel: (item: PendingItem) => string
  flowTone: (item: PendingItem) => string
  intentLabel: (item: PendingItem) => string
  intentTone: (item: PendingItem) => string
  isSelected: (key: string) => boolean
}>()

const emit = defineEmits<{
  (e: 'update:searchText', value: string): void
  (e: 'update:statusFilter', value: 'all' | 'todo' | 'retry' | 'done'): void
  (e: 'clear'): void
  (e: 'command', key: string): void
  (e: 'select-item', key: string): void
  (e: 'toggle-item-select', key: string): void
  (e: 'toggle-details'): void
  (e: 'mark-done'): void
  (e: 'reply'): void
  (e: 'retry'): void
  (e: 'apply-default', type: 'reply' | 'dm'): void
  (e: 'update:selectedReply', value: string): void
  (e: 'update:selectedDm', value: string): void
}>()

const containerRef = ref<HTMLElement | null>(null)

function focusSearch() {
  const input = containerRef.value?.querySelector('input[type="text"]') as HTMLInputElement | null
  input?.focus()
  input?.select()
}

defineExpose({ focusSearch })
</script>

<template>
  <div ref="containerRef" class="rounded-[24px] border border-emerald-100/90 bg-white/80 shadow-[0_24px_80px_rgba(16,185,129,0.16)]">
    <div class="border-b border-emerald-100/90 px-5 py-5">
      <div class="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <div class="font-mono text-[11px] uppercase tracking-[0.12em] text-emerald-600">Notifications</div>
          <h3 class="mt-1 text-lg font-semibold text-emerald-950">通知捕获</h3>
          <p class="mt-1 text-xs text-emerald-700/60">筛选一条通知，右侧直接回复或标记处理。</p>
        </div>
        <div class="rounded-2xl border border-emerald-100/90 bg-emerald-50/80 px-4 py-3 text-right">
          <div class="font-mono text-[10px] uppercase tracking-[0.12em] text-emerald-700/60">Total</div>
          <div class="mt-1 text-2xl font-semibold text-emerald-950">{{ notifyCount }}</div>
        </div>
      </div>

      <div class="mt-4 grid gap-3 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
        <input
          :value="searchText"
          type="text"
          placeholder="筛选 @用户 / 关键词"
          class="w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15"
          @input="emit('update:searchText', ($event.target as HTMLInputElement).value)"
        />
        <button type="button" class="rounded-2xl border border-emerald-200/90 bg-emerald-50/80 px-4 py-3 text-sm font-semibold text-emerald-800" @click="emit('clear')">
          清空
        </button>
      </div>

      <div class="mt-3 flex flex-wrap gap-2">
        <button
          v-for="button in statusButtons"
          :key="button.key"
          type="button"
          class="rounded-full border px-3 py-2 text-xs font-medium transition"
          :class="statusFilter === button.key
            ? 'border-emerald-400/50 bg-emerald-400/15 text-emerald-950'
            : 'border-emerald-100/90 bg-white/70 text-emerald-700/80 hover:border-emerald-200/90 hover:text-emerald-800'"
          @click="emit('update:statusFilter', button.key as 'all' | 'todo' | 'retry' | 'done')"
        >
          {{ button.label }}
          <span class="ml-1 font-mono text-[10px] opacity-70">{{ button.count }}</span>
        </button>
      </div>
    </div>

    <div class="space-y-3 p-4">
      <div v-if="filteredItems.length" class="grid gap-4 xl:grid-cols-[minmax(280px,360px)_minmax(0,1fr)]">
        <div class="space-y-3 xl:max-h-[calc(100vh-16rem)] xl:overflow-y-auto xl:pr-1">
          <div class="flex items-center justify-between gap-3 px-1 text-xs text-emerald-700/60">
            <span>当前 {{ selectedIndex + 1 }}/{{ filteredItems.length }}</span>
            <span v-if="selectedVisibleCount">已选 {{ selectedVisibleCount }}</span>
          </div>
          <NotifyQueueItem
            v-for="item in filteredItems"
            :key="item.key"
            :item="item"
            :active="selectedItem?.key === item.key"
            :selected="isSelected(item.key)"
            :replied="isReplied(item)"
            :flow-label="flowLabel(item)"
            :flow-tone="flowTone(item)"
            :intent-label="intentLabel(item)"
            :intent-tone="intentTone(item)"
            @select="emit('select-item', item.key)"
            @toggle-select="emit('toggle-item-select', item.key)"
          />
        </div>

        <div class="xl:sticky xl:top-5">
          <NotifyResultCard
            v-if="selectedItem"
            :item="selectedItem"
            :expanded="expanded"
            :is-replied="isReplied(selectedItem)"
            :flow-label="flowLabel(selectedItem)"
            :flow-tone="flowTone(selectedItem)"
            :intent-label="intentLabel(selectedItem)"
            :intent-tone="intentTone(selectedItem)"
            :reply-templates="replyTemplates"
            :dm-templates="dmTemplates"
            :selected-reply="selectedReply"
            :selected-dm="selectedDm"
            @toggle-details="emit('toggle-details')"
            @mark-done="emit('mark-done')"
            @reply="emit('reply')"
            @retry="emit('retry')"
            @apply-default="emit('apply-default', $event)"
            @update:selected-reply="emit('update:selectedReply', $event)"
            @update:selected-dm="emit('update:selectedDm', $event)"
          />
        </div>
      </div>

      <div v-if="allItemsCount && !filteredItems.length" class="grid min-h-[180px] place-items-center rounded-[22px] border border-dashed border-emerald-100/90 bg-white/60 text-center">
        <div>
          <div class="text-sm text-emerald-700/80">当前筛选下没有匹配的通知</div>
          <button type="button" class="mt-4 rounded-2xl border border-emerald-200/90 bg-emerald-50/80 px-4 py-2 text-xs font-semibold text-emerald-800" @click="emit('update:statusFilter', 'all')">
            查看全部
          </button>
        </div>
      </div>

      <div v-else-if="!allItemsCount" class="grid min-h-[220px] place-items-center text-center">
        <div>
          <div class="mx-auto mb-4 grid h-16 w-16 place-items-center rounded-2xl border border-emerald-400/30 bg-emerald-400/12 text-2xl text-emerald-600">📬</div>
          <div class="text-sm text-emerald-700/80">暂无通知捕获</div>
        </div>
      </div>
    </div>
  </div>
</template>
