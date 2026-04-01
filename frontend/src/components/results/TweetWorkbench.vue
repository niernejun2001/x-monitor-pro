<script setup lang="ts">
import { ref } from 'vue'
import type { PendingItem } from '../../types'
import ResultsSectionHeader from '../shared/ResultsSectionHeader.vue'
import TweetQueueItem from './TweetQueueItem.vue'
import TweetResultCard from './TweetResultCard.vue'
import WorktableCommandBar from '../shared/WorktableCommandBar.vue'

interface CommandAction {
  key: string
  label: string
  tone?: 'neutral' | 'accent' | 'success' | 'warning'
  disabled?: boolean
}

const props = defineProps<{
  tweetCount: number
  searchText: string
  metrics: {
    total: number
    uniqueHandles: number
    withStatus: number
  }
  commandActions: CommandAction[]
  commandHints: string[]
  allItemsCount: number
  filteredItems: PendingItem[]
  selectedIndex: number
  selectedVisibleCount: number
  selectedItem: PendingItem | null
  isSelected: (key: string) => boolean
}>()

const emit = defineEmits<{
  (e: 'update:searchText', value: string): void
  (e: 'clear'): void
  (e: 'clear-blocklist'): void
  (e: 'command', key: string): void
  (e: 'select-item', key: string): void
  (e: 'toggle-item-select', key: string): void
  (e: 'open'): void
  (e: 'mark-done'): void
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
      tone="emerald"
      code="TW"
      title="推文捕获"
      subtitle="Task watcher output"
      :count="tweetCount"
      :model-value="searchText"
      placeholder="筛选 @用户 / 关键词"
      @update:model-value="emit('update:searchText', $event)"
      @clear="emit('clear')"
    >
      <template #actions>
        <div class="flex flex-col gap-3 sm:flex-row">
          <button type="button" class="rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm font-semibold text-slate-200" @click="emit('clear')">清空</button>
          <button type="button" class="rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm font-semibold text-slate-200" @click="emit('clear-blocklist')">清空黑名单</button>
        </div>
      </template>
    </ResultsSectionHeader>

    <div class="space-y-3 p-4">
      <div class="grid gap-3 lg:grid-cols-3">
        <div class="rounded-2xl border border-slate-800 bg-slate-950/55 px-4 py-3">
          <div class="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-500">Visible</div>
          <div class="mt-2 font-mono text-2xl font-semibold text-slate-50">{{ metrics.total }}</div>
        </div>
        <div class="rounded-2xl border border-slate-800 bg-slate-950/55 px-4 py-3">
          <div class="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-500">Handles</div>
          <div class="mt-2 font-mono text-2xl font-semibold text-slate-50">{{ metrics.uniqueHandles }}</div>
        </div>
        <div class="rounded-2xl border border-slate-800 bg-slate-950/55 px-4 py-3">
          <div class="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-500">Status Linked</div>
          <div class="mt-2 font-mono text-2xl font-semibold text-slate-50">{{ metrics.withStatus }}</div>
        </div>
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
          <TweetQueueItem
            v-for="item in filteredItems"
            :key="item.key"
            :item="item"
            :active="selectedItem?.key === item.key"
            :selected="isSelected(item.key)"
            @select="emit('select-item', item.key)"
            @toggle-select="emit('toggle-item-select', item.key)"
          />
        </div>

        <div class="xl:sticky xl:top-5">
          <TweetResultCard
            v-if="selectedItem"
            :item="selectedItem"
            @open="emit('open')"
            @mark-done="emit('mark-done')"
          />
        </div>
      </div>

      <div v-if="allItemsCount && !filteredItems.length" class="grid min-h-[180px] place-items-center rounded-[22px] border border-dashed border-slate-800 bg-slate-950/40 text-center">
        <div>
          <div class="text-sm text-slate-400">当前筛选下没有匹配的推文</div>
          <button type="button" class="mt-4 rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-2 text-xs font-semibold text-slate-200" @click="emit('update:searchText', '')">
            清空筛选
          </button>
        </div>
      </div>

      <div v-else-if="!allItemsCount" class="grid min-h-[220px] place-items-center text-center">
        <div>
          <div class="mx-auto mb-4 grid h-16 w-16 place-items-center rounded-2xl border border-emerald-400/20 bg-emerald-400/10 text-2xl text-emerald-300">💬</div>
          <div class="text-sm text-slate-400">暂无推文捕获</div>
        </div>
      </div>
    </div>
  </div>
</template>
