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
  { key: 'control', label: '控制中心' },
  { key: 'task', label: '监控目标' },
  { key: 'template', label: '文案管理' },
] as const

const sidebarSnapshot = computed(() => [
  {
    label: '引擎',
    value: isRunning.value ? '运行中' : '待机',
    tone: isRunning.value ? 'text-emerald-300 border-emerald-400/20 bg-emerald-400/8' : 'text-rose-300 border-rose-400/20 bg-rose-400/8',
  },
  {
    label: '通知',
    value: notificationMonitoring.value ? '已启用' : '已关闭',
    tone: notificationMonitoring.value ? 'text-sky-300 border-sky-400/20 bg-sky-400/8' : 'text-slate-400 border-slate-800 bg-slate-950/70',
  },
  {
    label: '任务',
    value: String(tasks.value.length),
    tone: 'text-slate-100 border-slate-800 bg-slate-950/70',
  },
  {
    label: '结果',
    value: `${notifyItems.value.length}/${tweetItems.value.length}`,
    tone: 'text-slate-100 border-slate-800 bg-slate-950/70',
  },
])

function switchPanel(panel: 'control' | 'task' | 'template') {
  activePanel.value = panel
}
</script>

<template>
  <aside class="rounded-[24px] border border-slate-800 bg-slate-950/80 shadow-[0_24px_80px_rgba(2,6,23,0.42)] xl:sticky xl:top-5">
    <div class="border-b border-slate-800/80 px-5 py-5">
      <div class="mb-4 flex items-center gap-3">
        <div class="grid h-11 w-11 place-items-center rounded-2xl border border-sky-400/25 bg-sky-400/10 font-mono text-xs font-bold tracking-[0.2em] text-slate-50">
          OP
        </div>
        <div>
          <div class="font-mono text-[11px] uppercase tracking-[0.14em] text-sky-300">Operations</div>
          <h2 class="mt-1 text-base font-semibold text-slate-50">控制与配置</h2>
        </div>
      </div>

      <div class="grid grid-cols-3 gap-2">
        <button
          v-for="button in panelButtons"
          :key="button.key"
          type="button"
          class="rounded-2xl border px-3 py-2 text-xs font-medium transition"
          :class="button.key === activePanel
            ? 'border-sky-400/35 bg-sky-400/12 text-slate-50'
            : 'border-slate-800 bg-slate-900/70 text-slate-400 hover:border-slate-700 hover:text-slate-200'"
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
