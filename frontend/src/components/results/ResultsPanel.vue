<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, ref } from 'vue'
import NotifyWorkbench from './NotifyWorkbench.vue'
import ResultsTabSwitch from '../shared/ResultsTabSwitch.vue'
import TweetWorkbench from './TweetWorkbench.vue'
import { useResultsActions } from '../../composables/useResultsActions'
import { useResultsHotkeys } from '../../composables/useResultsHotkeys'
import { useSelectableQueue } from '../../composables/useSelectableQueue'
import { useVisibleSelection } from '../../composables/useVisibleSelection'
import { useAppStore } from '../../stores/app'
import { useResultsStore } from '../../stores/results'
import { useTemplatesStore } from '../../stores/templates'
import { useToastStore } from '../../stores/toast'
import type { PendingItem } from '../../types'

const app = useAppStore()
const results = useResultsStore()
const templates = useTemplatesStore()
const toast = useToastStore()

const { delegatedAccount } = storeToRefs(app)
const { notifyItems, tweetItems, filterText, selectedReplyByKey, selectedDmByKey } = storeToRefs(results)
const { replyTemplates, dmTemplates } = storeToRefs(templates)

const flowLabels: Record<string, string> = {
  reply_pending: '等待回复',
  match_card: '定位评论',
  share_link_ready: '链接就绪',
  reply_sent: '首评已发',
  dm_opening: '打开私信',
  dm_link_sent: '私信链接已发',
  dm_text_generating: '生成私信文案',
  dm_text_sent: '私信文案已发',
  dm_closed_confirmed: '私信关闭已确认',
  retry_waiting: '等待重试',
  done: '流程完成',
}

const notifyCount = computed(() => notifyItems.value.length)
const tweetCount = computed(() => tweetItems.value.length)
const activeTab = ref<'notify' | 'tweet'>('notify')
const notifyStatusFilter = ref<'all' | 'todo' | 'retry' | 'done'>('all')
const expandedNotifyKeys = ref<Record<string, boolean>>({})
const notifyWorkbenchRef = ref<{ focusSearch: () => void } | null>(null)
const tweetWorkbenchRef = ref<{ focusSearch: () => void } | null>(null)
const jumpHandle = ref('')

const notifyMetrics = computed(() => {
  const total = notifyItems.value.length
  const done = notifyItems.value.filter((item) => isReplied(item)).length
  const retry = notifyItems.value.filter((item) => !!item.notify_retry_time).length
  const todo = Math.max(total - done - retry, 0)
  return { total, todo, retry, done }
})

const filteredNotifyItems = computed(() =>
  notifyItems.value.filter((item) => {
    if (notifyStatusFilter.value === 'retry') return !!item.notify_retry_time
    if (notifyStatusFilter.value === 'done') return isReplied(item)
    if (notifyStatusFilter.value === 'todo') return !isReplied(item) && !item.notify_retry_time
    return true
  }),
)

const notifyStatusButtons = computed(() => [
  { key: 'all', label: '全部', count: notifyMetrics.value.total },
  { key: 'todo', label: '待处理', count: notifyMetrics.value.todo },
  { key: 'retry', label: '重试中', count: notifyMetrics.value.retry },
  { key: 'done', label: '已回复', count: notifyMetrics.value.done },
] as const)

const notifyCommandActions = computed(() => [
  { key: 'prev', label: 'K / ↑ 上一条' },
  { key: 'next', label: 'J / ↓ 下一条' },
  { key: 'search', label: '/ 搜索' },
  { key: 'select_all', label: '全选可见' },
  { key: 'clear_selection', label: '清空选择' },
  { key: 'bulk_done', label: '批量已处理', tone: 'warning' as const, disabled: !selectedVisibleNotifyCount.value },
])

const notifyCommandHints = ['Enter 回复', 'E 展开', 'R 重试', 'D 已处理', 'X 勾选']

const filteredTweetItems = computed(() => tweetItems.value)
const tweetMetrics = computed(() => {
  const handles = new Set(
    filteredTweetItems.value
      .map((item) => String(item.handle || '').trim())
      .filter(Boolean),
  )
  const withStatus = filteredTweetItems.value.filter((item) => !!String(item.status_id || '').trim()).length
  return {
    total: filteredTweetItems.value.length,
    uniqueHandles: handles.size,
    withStatus,
  }
})

const tweetCommandActions = computed(() => [
  { key: 'prev', label: 'K / ↑ 上一条' },
  { key: 'next', label: 'J / ↓ 下一条' },
  { key: 'search', label: '/ 搜索' },
  { key: 'select_all', label: '全选可见' },
  { key: 'clear_selection', label: '清空选择' },
  { key: 'bulk_done', label: '批量已处理', tone: 'success' as const, disabled: !selectedVisibleTweetCount.value },
])

const tweetCommandHints = ['Enter / O 打开', 'D 已处理', 'X 勾选']

const {
  selectedKey: selectedNotifyKey,
  selectedItem: selectedNotifyItem,
  selectedIndex: selectedNotifyIndex,
  selectByOffset: selectNotifyByOffset,
} = useSelectableQueue(filteredNotifyItems)

const {
  selectedByKey: selectedNotifyByKey,
  selectedVisibleCount: selectedVisibleNotifyCount,
  toggleSelected: toggleNotifySelected,
  selectAllVisible: selectAllVisibleNotify,
  clearVisibleSelection: clearVisibleNotifySelection,
  deselectKey: deselectNotifyKey,
  isSelected: isNotifySelected,
} = useVisibleSelection(filteredNotifyItems)

const {
  selectedKey: selectedTweetKey,
  selectedItem: selectedTweetItem,
  selectedIndex: selectedTweetIndex,
  selectByOffset: selectTweetByOffset,
} = useSelectableQueue(filteredTweetItems)

const {
  selectedByKey: selectedTweetByKey,
  selectedVisibleCount: selectedVisibleTweetCount,
  toggleSelected: toggleTweetSelected,
  selectAllVisible: selectAllVisibleTweet,
  clearVisibleSelection: clearVisibleTweetSelection,
  deselectKey: deselectTweetKey,
  isSelected: isTweetSelected,
} = useVisibleSelection(filteredTweetItems)

const activeOverview = computed(() => {
  if (activeTab.value === 'notify') {
    return [
      { label: '当前可见', value: String(filteredNotifyItems.value.length), tone: 'text-emerald-700 border-emerald-400/30 bg-emerald-400/10' },
      { label: '已选', value: String(selectedVisibleNotifyCount.value), tone: 'text-emerald-950 border-emerald-100/90 bg-white/80' },
      { label: '待处理', value: String(notifyMetrics.value.todo), tone: 'text-amber-700 border-amber-400/20 bg-amber-400/10' },
      { label: '重试', value: String(notifyMetrics.value.retry), tone: 'text-rose-700 border-rose-400/20 bg-rose-400/10' },
    ]
  }
  return [
    { label: '当前可见', value: String(filteredTweetItems.value.length), tone: 'text-emerald-700 border-emerald-400/20 bg-emerald-400/10' },
    { label: '已选', value: String(selectedVisibleTweetCount.value), tone: 'text-emerald-950 border-emerald-100/90 bg-white/80' },
    { label: '用户数', value: String(tweetMetrics.value.uniqueHandles), tone: 'text-emerald-700 border-emerald-400/30 bg-emerald-400/10' },
    { label: '已关联', value: String(tweetMetrics.value.withStatus), tone: 'text-emerald-700 border-emerald-400/20 bg-emerald-400/10' },
  ]
})

function isReplied(item: PendingItem) {
  return !!(item.notify_replied || item.reply_checked)
}

function flowLabel(item: PendingItem) {
  const key = String(item.notify_flow_stage || '').trim().toLowerCase()
  return flowLabels[key] || (key || '未开始')
}

async function handleDelegationSave() {
  try {
    await app.saveDelegation()
  } catch (error: any) {
    toast.push(error?.message || '保存委派账户失败', 'error', 4200)
  }
}

async function handleJump() {
  const handle = jumpHandle.value.trim()
  if (!handle) return
  try {
    await app.jumpToReplies(handle)
  } catch (error: any) {
    toast.push(error?.message || '打开用户回复页失败', 'error', 4200)
  }
}

function toggleNotifyDetails(key: string) {
  expandedNotifyKeys.value[key] = !expandedNotifyKeys.value[key]
}

function handleNotifyCommandAction(key: string) {
  if (key === 'prev') {
    selectNotifyByOffset(-1)
    return
  }
  if (key === 'next') {
    selectNotifyByOffset(1)
    return
  }
  if (key === 'search') {
    focusNotifySearch()
    return
  }
  if (key === 'select_all') {
    selectAllVisibleNotify()
    return
  }
  if (key === 'clear_selection') {
    clearVisibleNotifySelection()
    return
  }
  if (key === 'bulk_done') {
    void handleBulkMarkDone('notify')
  }
}

function focusNotifySearch() {
  notifyWorkbenchRef.value?.focusSearch()
}

function focusTweetSearch() {
  tweetWorkbenchRef.value?.focusSearch()
}

function handleTweetCommandAction(key: string) {
  if (key === 'prev') {
    selectTweetByOffset(-1)
    return
  }
  if (key === 'next') {
    selectTweetByOffset(1)
    return
  }
  if (key === 'search') {
    focusTweetSearch()
    return
  }
  if (key === 'select_all') {
    selectAllVisibleTweet()
    return
  }
  if (key === 'clear_selection') {
    clearVisibleTweetSelection()
    return
  }
  if (key === 'bulk_done') {
    void handleBulkMarkDone('tweet')
  }
}

function intentLabel(item: PendingItem) {
  const level = String(item.intent_level || '').trim().toLowerCase()
  if (!level) return '未分析'
  const score = Number(item.intent_score || 0)
  return `${level.toUpperCase()} ${Number.isFinite(score) ? score : 0}`
}

function intentTone(item: PendingItem) {
  const level = String(item.intent_level || '').trim().toLowerCase()
  if (level === 'high' || level === 'medium') return 'border-emerald-400/20 bg-emerald-400/10 text-emerald-700'
  if (level === 'low') return 'border-amber-400/20 bg-amber-400/10 text-amber-700'
  return 'border-emerald-100/90 bg-white/70 text-emerald-700/80'
}

function flowTone(item: PendingItem) {
  if (item.notify_flow_error_code || item.notify_flow_error_detail || item.notify_flow_error) {
    return 'border-rose-400/20 bg-rose-400/10 text-rose-700'
  }
  if (item.notify_retry_time) {
    return 'border-amber-400/20 bg-amber-400/10 text-amber-700'
  }
  if (isReplied(item)) {
    return 'border-emerald-400/20 bg-emerald-400/10 text-emerald-700'
  }
  return 'border-emerald-100/90 bg-white/70 text-emerald-700/80'
}

const {
  applyDefaultTemplate,
  openTweetSource,
  handleMarkDone,
  handleBulkMarkDone,
  handleNotifyReply,
  handleRetry,
  handleClear,
  handleClearBlocklist,
} = useResultsActions({
  results,
  toast,
  replyTemplates,
  dmTemplates,
  selectedReplyByKey,
  selectedDmByKey,
  filteredNotifyItems,
  filteredTweetItems,
  selectedNotifyByKey,
  selectedTweetByKey,
  deselectNotifyKey,
  deselectTweetKey,
})

useResultsHotkeys({
  activeTab,
  filteredNotifyItems,
  filteredTweetItems,
  selectedNotifyItem,
  selectedTweetItem,
  focusNotifySearch,
  focusTweetSearch,
  selectNotifyByOffset,
  selectTweetByOffset,
  toggleNotifyDetails,
  toggleNotifySelected,
  toggleTweetSelected,
  handleNotifyReply,
  handleRetry,
  handleMarkDone,
  openTweetSource,
})
</script>

<template>
  <section class="space-y-6">
    <div class="rounded-3xl border border-emerald-300/50 bg-gradient-to-br from-white/95 via-emerald-50/95 to-lime-100/80 p-4 shadow-[0_18px_46px_rgba(16,185,129,0.12)]">
      <div class="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2">
            <div class="font-mono text-[11px] uppercase tracking-[0.12em] text-emerald-600">Account</div>
            <span class="rounded-full border border-emerald-300/40 bg-white/80 px-3 py-1 text-xs font-semibold text-emerald-700">
              当前 {{ delegatedAccount?.trim() || '未绑定' }}
            </span>
          </div>
          <h2 class="mt-2 text-lg font-semibold text-emerald-950">账号与跳转</h2>
          <p class="mt-1 text-xs leading-5 text-emerald-700/70">常用账户和跳转入口放在捕获列表上方，处理通知前先确认身份。</p>
        </div>

        <div class="grid min-w-0 flex-1 gap-3 lg:grid-cols-[minmax(180px,0.85fr)_minmax(240px,1fr)] xl:max-w-3xl">
          <div class="grid gap-2 sm:grid-cols-[minmax(0,1fr)_96px]">
            <input
              v-model="delegatedAccount"
              type="text"
              aria-label="委派账户"
              placeholder="@username"
              class="w-full rounded-2xl border border-emerald-100/90 bg-white/85 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15"
            />
            <button
              type="button"
              class="rounded-2xl bg-gradient-to-r from-emerald-400 to-lime-300 px-4 py-3 text-sm font-semibold text-emerald-950 shadow-[0_12px_24px_rgba(16,185,129,0.14)] transition hover:brightness-105"
              @click="handleDelegationSave"
            >
              保存
            </button>
          </div>

          <div class="grid gap-2 sm:grid-cols-[minmax(0,1fr)_96px]">
            <input
              v-model="jumpHandle"
              type="text"
              aria-label="推特用户 ID"
              placeholder="输入 @ID，回车打开回复页"
              class="w-full rounded-2xl border border-emerald-100/90 bg-white/85 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15"
              @keydown.enter.prevent="handleJump"
            />
            <button
              type="button"
              class="rounded-2xl border border-emerald-200/90 bg-white/85 px-4 py-3 text-sm font-semibold text-emerald-800 transition hover:border-emerald-400 hover:bg-emerald-50"
              @click="handleJump"
            >
              打开
            </button>
          </div>
        </div>
      </div>
    </div>

    <ResultsTabSwitch
      :active-tab="activeTab"
      :notify-count="notifyCount"
      :tweet-count="tweetCount"
      @update:active-tab="activeTab = $event"
    />

    <div class="grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
      <div
        v-for="card in activeOverview"
        :key="`${activeTab}-${card.label}`"
        class="rounded-2xl border px-4 py-3"
        :class="card.tone"
      >
        <div class="font-mono text-[10px] uppercase tracking-[0.12em] opacity-70">{{ card.label }}</div>
        <div class="mt-2 text-lg font-semibold">{{ card.value }}</div>
      </div>
    </div>

    <NotifyWorkbench
      v-if="activeTab === 'notify'"
      ref="notifyWorkbenchRef"
      :notify-count="notifyCount"
      :search-text="filterText.notify"
      :status-filter="notifyStatusFilter"
      :status-buttons="notifyStatusButtons"
      :command-actions="notifyCommandActions"
      :command-hints="notifyCommandHints"
      :all-items-count="notifyItems.length"
      :filtered-items="filteredNotifyItems"
      :selected-index="selectedNotifyIndex"
      :selected-visible-count="selectedVisibleNotifyCount"
      :selected-item="selectedNotifyItem"
      :selected-reply="selectedNotifyItem ? (selectedReplyByKey[selectedNotifyItem.key] || '') : ''"
      :selected-dm="selectedNotifyItem ? (selectedDmByKey[selectedNotifyItem.key] || '') : ''"
      :expanded="!!(selectedNotifyItem && expandedNotifyKeys[selectedNotifyItem.key])"
      :reply-templates="replyTemplates"
      :dm-templates="dmTemplates"
      :is-replied="isReplied"
      :flow-label="flowLabel"
      :flow-tone="flowTone"
      :intent-label="intentLabel"
      :intent-tone="intentTone"
      :is-selected="isNotifySelected"
      @update:search-text="filterText.notify = $event"
      @update:status-filter="notifyStatusFilter = $event"
      @clear="handleClear('notify')"
      @command="handleNotifyCommandAction"
      @select-item="selectedNotifyKey = $event"
      @toggle-item-select="toggleNotifySelected($event)"
      @toggle-details="selectedNotifyItem && toggleNotifyDetails(selectedNotifyItem.key)"
      @mark-done="selectedNotifyItem && handleMarkDone(selectedNotifyItem)"
      @reply="selectedNotifyItem && handleNotifyReply(selectedNotifyItem)"
      @retry="selectedNotifyItem && handleRetry(selectedNotifyItem)"
      @apply-default="selectedNotifyItem && applyDefaultTemplate(selectedNotifyItem, $event)"
      @update:selected-reply="selectedNotifyItem && (selectedReplyByKey[selectedNotifyItem.key] = $event)"
      @update:selected-dm="selectedNotifyItem && (selectedDmByKey[selectedNotifyItem.key] = $event)"
    />

    <TweetWorkbench
      v-else
      ref="tweetWorkbenchRef"
      :tweet-count="tweetCount"
      :search-text="filterText.tweet"
      :metrics="tweetMetrics"
      :command-actions="tweetCommandActions"
      :command-hints="tweetCommandHints"
      :all-items-count="tweetItems.length"
      :filtered-items="filteredTweetItems"
      :selected-index="selectedTweetIndex"
      :selected-visible-count="selectedVisibleTweetCount"
      :selected-item="selectedTweetItem"
      :is-selected="isTweetSelected"
      @update:search-text="filterText.tweet = $event"
      @clear="handleClear('tweet')"
      @clear-blocklist="handleClearBlocklist()"
      @command="handleTweetCommandAction"
      @select-item="selectedTweetKey = $event"
      @toggle-item-select="toggleTweetSelected($event)"
      @open="selectedTweetItem && openTweetSource(selectedTweetItem)"
      @mark-done="selectedTweetItem && handleMarkDone(selectedTweetItem)"
    />
  </section>
</template>
