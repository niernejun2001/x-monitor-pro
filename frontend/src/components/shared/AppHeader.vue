<script setup lang="ts">
defineProps<{
  statusText: string
  running: boolean
}>()
</script>

<template>
  <header class="rounded-[28px] border border-emerald-200/80 bg-white/80 shadow-[0_24px_80px_rgba(16,185,129,0.18)] backdrop-blur">
    <div class="grid gap-6 px-6 py-7 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
      <div class="flex items-start gap-4">
        <div class="grid h-14 w-14 place-items-center rounded-2xl border border-emerald-400/40 bg-gradient-to-br from-emerald-300/30 to-lime-300/30 font-mono text-lg font-bold tracking-[0.2em] text-emerald-950">
          XM
        </div>
        <div>
          <span class="mb-2 inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-emerald-600">
            <span class="h-px w-7 bg-current/60" />
            Realtime Ops Console
          </span>
          <h1 class="text-3xl font-semibold tracking-tight text-emerald-950 md:text-4xl">X Monitor Pro</h1>
          <p class="mt-2 max-w-3xl text-sm leading-6 text-emerald-700/80">
            评论、通知、私信和语音播报统一调度面板。保留当前后端逻辑，前端重构为更易维护的单页控制台。
          </p>
        </div>
      </div>

      <div class="flex flex-col items-start gap-3 md:items-end">
        <div class="inline-flex items-center gap-3 rounded-full border border-emerald-200/70 bg-white/70 px-4 py-3 text-sm text-emerald-800">
          <span
            class="h-3 w-3 rounded-full shadow-[0_0_18px_currentColor]"
            :class="running ? 'bg-emerald-400 text-emerald-400' : 'bg-rose-500 text-rose-7000'"
          />
          <span class="font-mono">{{ statusText }}</span>
        </div>
        <div class="flex flex-wrap gap-2 md:justify-end">
          <span class="rounded-full border border-emerald-100/90 bg-emerald-50/80 px-3 py-1.5 font-mono text-[11px] text-emerald-700/80">Notify Watch</span>
          <span class="rounded-full border border-emerald-100/90 bg-emerald-50/80 px-3 py-1.5 font-mono text-[11px] text-emerald-700/80">Reply Ops</span>
          <span class="rounded-full border border-emerald-100/90 bg-emerald-50/80 px-3 py-1.5 font-mono text-[11px] text-emerald-700/80">DM Flow</span>
        </div>
      </div>
    </div>
  </header>
</template>
