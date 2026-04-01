<script setup lang="ts">
import { ref } from 'vue'
import type { PendingItem } from '../../types'
import NotifyQueueItem from './NotifyQueueItem.vue'
import NotifyResultCard from './NotifyResultCard.vue'
import ResultsSectionHeader from '../shared/ResultsSectionHeader.vue'
import WorktableCommandBar from '../shared/WorktableCommandBar.vue'

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
  <div ref="containerRef" class="rounded-[24px] border border-slate-800 bg-slate-950/80 shadow-[0_24px_80px_rgba(2,6,23,0.42)]">
    <ResultsSectionHeader
      tone="sky"
      code="NT"
      title="通知捕获"
      subtitle="Reply-to-you stream"
      :count="notifyCount"
      :model-value="searchText"
      placeholder="筛选 @用户 / 关键词"
      @update:model-value="emit('update:searchText', $event)"
      @clear="emit('clear')"
    >
      <template #actions>
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
          <span class="rounded-full border border-slate-800 bg-slate-950/80 px-3 py-2 font-mono text-[11px] text-slate-400">
            {{ statusButtons.find((button) => button.key === statusFilter)?.label || '全部' }}
          </span>
          <button type="button" class="rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm font-semibold text-slate-200" @click="emit('clear')">清空</button>
        </div>
      </template>
    </ResultsSectionHeader>

    <div class="space-y-3 p-4">
      <div class="flex flex-wrap gap-2">
        <button
          v-for="button in statusButtons"
          :key="button.key"
          type="button"
          class="rounded-full border px-3 py-2 text-xs font-medium transition"
          :class="statusFilter === button.key
            ? 'border-sky-400/35 bg-sky-400/12 text-slate-50'
            : 'border-slate-800 bg-slate-950/70 text-slate-400 hover:border-slate-700 hover:text-slate-200'"
          @click="emit('update:statusFilter', button.key as 'all' | 'todo' | 'retry' | 'done')"
        >
          {{ button.label }}
          <span class="ml-1 font-mono text-[10px] opacity-70">{{ button.count }}</span>
        </button>
      </div>

      <WorktableCommandBar
        v-if="filteredItems.length"
        status-label="当前"
        :status-value="`${selectedIndex + 1}/${filteredItems.length}`"
        secondary-label="已选"
        :secondary-value="String(selectedVisibleCount)"
        :actions="commandActions"
        :hints="commandHints"
        @action="emit('command', $event)"
      />

      <div v-if="filteredItems.length" class="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)] 2xl:grid-cols-[340px_minmax(0,1fr)]">
        <div class="space-y-3 xl:max-h-[calc(100vh-17rem)] xl:overflow-y-auto xl:pr-1">
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

      <div v-if="allItemsCount && !filteredItems.length" class="grid min-h-[180px] place-items-center rounded-[22px] border border-dashed border-slate-800 bg-slate-950/40 text-center">
        <div>
          <div class="text-sm text-slate-400">当前筛选下没有匹配的通知</div>
          <button type="button" class="mt-4 rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-2 text-xs font-semibold text-slate-200" @click="emit('update:statusFilter', 'all')">
            查看全部
          </button>
        </div>
      </div>

      <div v-else-if="!allItemsCount" class="grid min-h-[220px] place-items-center text-center">
        <div>
          <div class="mx-auto mb-4 grid h-16 w-16 place-items-center rounded-2xl border border-sky-400/20 bg-sky-400/10 text-2xl text-sky-300">📬</div>
          <div class="text-sm text-slate-400">暂无通知捕获</div>
        </div>
      </div>
    </div>
  </div>
</template>
