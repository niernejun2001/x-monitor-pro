<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed } from 'vue'
import ControlWorkbench from './ControlWorkbench.vue'
import TaskWorkbench from './TaskWorkbench.vue'
import TemplateWorkbench from './TemplateWorkbench.vue'
import { useAppStore } from '../../stores/app'
import { useResultsStore } from '../../stores/results'
import { useTasksStore } from '../../stores/tasks'

const app = useAppStore()
const resultsStore = useResultsStore()
const tasksStore = useTasksStore()

const { activePanel, isRunning, notificationMonitoring } = storeToRefs(app)
const { notifyItems, tweetItems } = storeToRefs(resultsStore)
const { tasks } = storeToRefs(tasksStore)

const panelButtons = [
  { key: 'control', label: '操作' },
  { key: 'task', label: '目标' },
  { key: 'template', label: '文案' },
] as const

const sidebarSnapshot = computed(() => [
  {
    label: '引擎',
    value: isRunning.value ? '运行中' : '待机',
    tone: isRunning.value ? 'text-emerald-600 border-emerald-400/20 bg-emerald-400/10' : 'text-rose-300 border-rose-400/20 bg-rose-400/10',
  },
  {
    label: '通知',
    value: notificationMonitoring.value ? '已启用' : '已关闭',
    tone: notificationMonitoring.value ? 'text-emerald-600 border-emerald-400/30 bg-emerald-400/10' : 'text-emerald-700/80 border-emerald-100/90 bg-white/70',
  },
  {
    label: '任务',
    value: String(tasks.value.length),
    tone: 'text-emerald-950 border-emerald-100/90 bg-white/70',
  },
  {
    label: '结果',
    value: `${notifyItems.value.length}/${tweetItems.value.length}`,
    tone: 'text-emerald-950 border-emerald-100/90 bg-white/70',
  },
])

function switchPanel(panel: 'control' | 'task' | 'template') {
  activePanel.value = panel
}
</script>

<template>
  <aside class="rounded-[24px] border border-emerald-100/90 bg-white/80 shadow-[0_24px_80px_rgba(16,185,129,0.16)] xl:sticky xl:top-5">
    <div class="border-b border-emerald-100/90 px-5 py-5">
      <div class="mb-4 flex items-center gap-3">
        <div class="grid h-11 w-11 place-items-center rounded-2xl border border-emerald-400/40 bg-emerald-400/12 font-mono text-xs font-bold tracking-[0.2em] text-emerald-950">
          OP
        </div>
        <div>
          <div class="font-mono text-[11px] uppercase tracking-[0.14em] text-emerald-600">Operations</div>
          <h2 class="mt-1 text-base font-semibold text-emerald-950">操作管理</h2>
        </div>
      </div>

      <div class="grid grid-cols-3 gap-2">
        <button
          v-for="button in panelButtons"
          :key="button.key"
          type="button"
          class="rounded-2xl border px-3 py-3 text-sm font-semibold transition"
          :class="button.key === activePanel
            ? 'border-emerald-400/50 bg-emerald-400/15 text-emerald-950'
            : 'border-emerald-100/90 bg-emerald-50/80 text-emerald-700/80 hover:border-emerald-200/90 hover:text-emerald-800'"
          @click="switchPanel(button.key)"
        >
          {{ button.label }}
        </button>
      </div>

      <div class="mt-4 grid grid-cols-2 gap-2">
        <div
          v-for="card in sidebarSnapshot"
          :key="card.label"
          class="rounded-2xl border px-3 py-3"
          :class="card.tone"
        >
          <div class="font-mono text-[10px] uppercase tracking-[0.14em] opacity-70">{{ card.label }}</div>
          <div class="mt-2 text-sm font-semibold">{{ card.value }}</div>
        </div>
      </div>
    </div>

    <div class="max-h-[calc(100vh-10rem)] overflow-y-auto px-5 py-5">
      <ControlWorkbench v-if="activePanel === 'control'" />
      <TaskWorkbench v-else-if="activePanel === 'task'" />
      <TemplateWorkbench v-else />
    </div>
  </aside>
</template>
