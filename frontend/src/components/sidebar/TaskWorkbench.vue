<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'
import { useTasksStore } from '../../stores/tasks'
import { useToastStore } from '../../stores/toast'

const tasksStore = useTasksStore()
const toast = useToastStore()
const { tasks } = storeToRefs(tasksStore)
const newTaskUrl = ref('')
const selectedTaskUrl = ref('')

const selectedTask = computed(() => (
  tasks.value.find((task) => task.url === selectedTaskUrl.value)
  || tasks.value[0]
  || null
))

watch(tasks, (nextTasks) => {
  if (!nextTasks.length) {
    selectedTaskUrl.value = ''
    return
  }
  if (!nextTasks.some((task) => task.url === selectedTaskUrl.value)) {
    selectedTaskUrl.value = nextTasks[0].url
  }
}, { immediate: true, deep: true })

async function handleAddTask() {
  if (!newTaskUrl.value.trim()) {
    toast.push('请输入推文链接', 'error', 3200)
    return
  }
  try {
    await tasksStore.add(newTaskUrl.value.trim())
    newTaskUrl.value = ''
    toast.push('监控目标已添加', 'success')
  } catch (error: any) {
    toast.push(error?.message || '添加监控失败', 'error', 4200)
  }
}

async function handleRemoveTask(url: string) {
  try {
    await tasksStore.remove(url)
    toast.push('监控目标已移除', 'success')
  } catch (error: any) {
    toast.push(error?.message || '移除失败', 'error', 4200)
  }
}
</script>

<template>
  <section class="space-y-4">
    <div class="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="font-mono text-[11px] uppercase tracking-[0.12em] text-sky-300">Targets</div>
          <div class="mt-1 text-sm font-medium text-slate-100">监控目标工作台</div>
          <div class="mt-2 text-xs leading-6 text-slate-500">新增目标保留在上方，已有目标折叠成队列，只在右侧展示当前选中项。</div>
        </div>
        <div class="rounded-2xl border border-slate-800 bg-slate-950/80 px-3 py-2 text-right">
          <div class="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-500">Total</div>
          <div class="mt-1 text-lg font-semibold text-slate-50">{{ tasks.length }}</div>
        </div>
      </div>

      <div class="mt-4 grid gap-3">
        <label class="space-y-2">
          <span class="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">新建监控</span>
          <input
            v-model="newTaskUrl"
            type="text"
            aria-label="监控推文链接"
            placeholder="粘贴推文链接..."
            class="w-full rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10"
          />
        </label>
        <button
          type="button"
          class="w-full rounded-2xl bg-sky-400 px-4 py-3 text-sm font-semibold text-slate-950"
          @click="handleAddTask"
        >
          添加监控
        </button>
      </div>
    </div>

    <div class="grid gap-4">
      <div class="rounded-2xl border border-slate-800 bg-slate-950/55 p-3">
        <div class="mb-3 flex items-center justify-between gap-3 px-1">
          <div class="text-sm font-medium text-slate-100">目标队列</div>
          <div class="text-xs text-slate-500">点击切换详情</div>
        </div>
        <div v-if="tasks.length" class="max-h-[340px] space-y-2 overflow-y-auto pr-1">
          <button
            v-for="task in tasks"
            :key="task.url"
            type="button"
            class="w-full rounded-2xl border px-3 py-3 text-left transition"
            :class="selectedTask?.url === task.url
              ? 'border-sky-400/35 bg-sky-400/10'
              : 'border-slate-800 bg-slate-950/70 hover:border-slate-700 hover:bg-slate-950/90'"
            @click="selectedTaskUrl = task.url"
          >
            <div class="truncate font-mono text-xs text-sky-300">{{ task.url }}</div>
            <div class="mt-2 text-[11px] text-slate-500">上次检查: {{ task.last_check || '等待' }}</div>
          </button>
        </div>
        <div v-else class="rounded-2xl border border-dashed border-slate-800 bg-slate-950/70 px-4 py-6 text-center text-sm text-slate-500">
          还没有监控目标
        </div>
      </div>

      <div class="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="font-mono text-[11px] uppercase tracking-[0.12em] text-sky-300">Detail</div>
            <div class="mt-1 text-sm font-medium text-slate-100">当前选中目标</div>
          </div>
          <div class="rounded-full border border-slate-800 px-2.5 py-1 text-[11px] text-slate-400">
            {{ selectedTask ? '可操作' : '空' }}
          </div>
        </div>

        <div v-if="selectedTask" class="mt-4 space-y-4">
          <div class="rounded-2xl border border-slate-800 bg-slate-950/80 p-4">
            <div class="text-[11px] uppercase tracking-[0.12em] text-slate-500">URL</div>
            <div class="mt-2 break-all font-mono text-xs leading-6 text-slate-200">{{ selectedTask.url }}</div>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <div class="rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3">
              <div class="text-[11px] uppercase tracking-[0.12em] text-slate-500">上次检查</div>
              <div class="mt-2 text-sm font-medium text-slate-100">{{ selectedTask.last_check || '等待首次扫描' }}</div>
            </div>
            <button
              type="button"
              class="rounded-2xl bg-rose-500 px-4 py-3 text-sm font-semibold text-white"
              @click="handleRemoveTask(selectedTask.url)"
            >
              移除当前目标
            </button>
          </div>
        </div>
        <div v-else class="mt-4 rounded-2xl border border-dashed border-slate-800 bg-slate-950/70 px-4 py-6 text-center text-sm text-slate-500">
          从左侧队列选择一个目标查看详情
        </div>
      </div>
    </div>
  </section>
</template>
