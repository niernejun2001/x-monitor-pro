<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import AppHeader from './components/shared/AppHeader.vue'
import SidebarPanel from './components/sidebar/SidebarPanel.vue'
import ResultsPanel from './components/results/ResultsPanel.vue'
import ToastStack from './components/shared/ToastStack.vue'
import SummaryStrip from './components/shared/SummaryStrip.vue'
import { useAppStore } from './stores/app'
import { useResultsStore } from './stores/results'
import { useTasksStore } from './stores/tasks'
import { useToastStore } from './stores/toast'

const app = useAppStore()
const results = useResultsStore()
const tasks = useTasksStore()
const toast = useToastStore()

const { statusText, isRunning, serverAudioMeta } = storeToRefs(app)
const { tasks: taskItems } = storeToRefs(tasks)
const { notifyItems, tweetItems } = storeToRefs(results)

onMounted(async () => {
  try {
    app.startClock()
    await app.bootstrap()
    results.startPolling()
  } catch (error: any) {
    toast.push(error?.message || '页面初始化失败', 'error', 4200)
  }
})

onBeforeUnmount(() => {
  app.stopClock()
  results.stopPolling()
})
</script>

<template>
  <div class="min-h-screen bg-transparent text-emerald-950">
    <ToastStack />
    <main class="mx-auto flex w-full max-w-[1560px] flex-col gap-6 px-4 py-5 lg:px-6">
      <AppHeader :status-text="statusText" :running="isRunning" />
      <SummaryStrip
        :running="isRunning"
        :task-count="taskItems.length"
        :notify-count="notifyItems.length"
        :tweet-count="tweetItems.length"
        :audio-label="serverAudioMeta.enabled ? `服务端 / ${serverAudioMeta.player}` : '浏览器 / 前端'"
      />
      <div class="grid items-start gap-6 xl:grid-cols-[352px_minmax(0,1fr)] 2xl:grid-cols-[372px_minmax(0,1fr)]">
        <SidebarPanel />
        <ResultsPanel />
      </div>
    </main>
  </div>
</template>
