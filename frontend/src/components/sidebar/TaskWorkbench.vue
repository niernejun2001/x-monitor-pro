<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { ref } from 'vue'
import { useTasksStore } from '../../stores/tasks'
import { useToastStore } from '../../stores/toast'

const tasksStore = useTasksStore()
const toast = useToastStore()
const { tasks } = storeToRefs(tasksStore)
const newTaskUrl = ref('')

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
    <div class="rounded-3xl border border-emerald-100/90 bg-white/75 p-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="font-mono text-[11px] uppercase tracking-[0.12em] text-emerald-600">Targets</div>
          <div class="mt-1 text-base font-semibold text-emerald-950">监控目标</div>
          <div class="mt-2 text-xs leading-6 text-emerald-700/60">粘贴推文链接即可添加，已有目标在下方直接管理。</div>
        </div>
        <div class="rounded-2xl border border-emerald-100/90 bg-white/80 px-3 py-2 text-right">
          <div class="font-mono text-[10px] uppercase tracking-[0.12em] text-emerald-700/60">Total</div>
          <div class="mt-1 text-lg font-semibold text-emerald-950">{{ tasks.length }}</div>
        </div>
      </div>

      <div class="mt-4 grid gap-3">
        <label class="space-y-2">
          <span class="text-[11px] font-medium uppercase tracking-[0.12em] text-emerald-700/60">推文链接</span>
          <input
            v-model="newTaskUrl"
            type="text"
            aria-label="监控推文链接"
            placeholder="粘贴推文链接..."
            class="w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15"
          />
        </label>
        <button
          type="button"
          class="w-full rounded-2xl bg-emerald-400 px-4 py-3 text-sm font-semibold text-emerald-950"
          @click="handleAddTask"
        >
          添加目标
        </button>
      </div>
    </div>

    <div class="rounded-3xl border border-emerald-100/90 bg-white/70 p-3">
      <div class="mb-3 flex items-center justify-between gap-3 px-1">
        <div class="text-sm font-semibold text-emerald-950">已添加目标</div>
        <div class="text-xs text-emerald-700/60">{{ tasks.length }} 条</div>
      </div>

      <div v-if="tasks.length" class="max-h-[520px] space-y-2 overflow-y-auto pr-1">
        <article
          v-for="task in tasks"
          :key="task.url"
          class="rounded-2xl border border-emerald-100/90 bg-white/75 p-3"
        >
          <div class="break-all font-mono text-xs leading-5 text-emerald-700">{{ task.url }}</div>
          <div class="mt-3 flex items-center justify-between gap-3">
            <span class="rounded-full border border-emerald-100/90 bg-emerald-50/80 px-2.5 py-1 text-[11px] text-emerald-700/70">
              上次检查: {{ task.last_check || '等待' }}
            </span>
            <button
              type="button"
              class="rounded-full bg-rose-500 px-3 py-1.5 text-xs font-semibold text-white"
              @click="handleRemoveTask(task.url)"
            >
              删除
            </button>
          </div>
        </article>
      </div>

      <div v-else class="rounded-2xl border border-dashed border-emerald-100/90 bg-white/70 px-4 py-8 text-center text-sm text-emerald-700/60">
        还没有监控目标
      </div>
    </div>
  </section>
</template>
