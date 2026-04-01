<script setup lang="ts">
defineProps<{
  running: boolean
  taskCount: number
  notifyCount: number
  tweetCount: number
  audioLabel: string
}>()
</script>

<template>
  <section class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
    <div class="rounded-2xl border border-slate-800 bg-slate-950/75 p-4 shadow-[0_18px_48px_rgba(2,6,23,0.32)]">
      <div class="font-mono text-[11px] uppercase tracking-[0.12em] text-sky-300">Engine</div>
      <div class="mt-3 flex items-center gap-3">
        <span
          class="h-3 w-3 rounded-full shadow-[0_0_18px_currentColor]"
          :class="running ? 'bg-emerald-400 text-emerald-400' : 'bg-rose-500 text-rose-500'"
        />
        <strong class="text-sm font-semibold text-slate-50">{{ running ? '运行中' : '待机中' }}</strong>
      </div>
    </div>

    <div class="rounded-2xl border border-slate-800 bg-slate-950/75 p-4 shadow-[0_18px_48px_rgba(2,6,23,0.32)]">
      <div class="font-mono text-[11px] uppercase tracking-[0.12em] text-sky-300">Tasks</div>
      <div class="mt-3 flex items-end justify-between gap-3">
        <strong class="font-mono text-3xl font-semibold tracking-tight text-slate-50">{{ taskCount }}</strong>
        <span class="text-xs text-slate-500">监控目标</span>
      </div>
    </div>

    <div class="rounded-2xl border border-slate-800 bg-slate-950/75 p-4 shadow-[0_18px_48px_rgba(2,6,23,0.32)]">
      <div class="font-mono text-[11px] uppercase tracking-[0.12em] text-sky-300">Results</div>
      <div class="mt-3 grid grid-cols-2 gap-3">
        <div>
          <div class="font-mono text-2xl font-semibold text-slate-50">{{ notifyCount }}</div>
          <div class="text-xs text-slate-500">通知</div>
        </div>
        <div>
          <div class="font-mono text-2xl font-semibold text-slate-50">{{ tweetCount }}</div>
          <div class="text-xs text-slate-500">推文</div>
        </div>
      </div>
    </div>

    <div class="rounded-2xl border border-slate-800 bg-slate-950/75 p-4 shadow-[0_18px_48px_rgba(2,6,23,0.32)]">
      <div class="font-mono text-[11px] uppercase tracking-[0.12em] text-sky-300">Audio</div>
      <div class="mt-3 text-sm font-semibold text-slate-50">{{ audioLabel }}</div>
      <div class="mt-1 text-xs leading-6 text-slate-500">语音播报主链路概览</div>
    </div>
  </section>
</template>
