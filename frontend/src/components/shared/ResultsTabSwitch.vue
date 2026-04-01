<script setup lang="ts">
defineProps<{
  activeTab: 'notify' | 'tweet'
  notifyCount: number
  tweetCount: number
}>()

const emit = defineEmits<{
  (e: 'update:activeTab', value: 'notify' | 'tweet'): void
}>()
</script>

<template>
  <div class="rounded-[24px] border border-slate-800 bg-slate-950/80 p-2 shadow-[0_24px_80px_rgba(2,6,23,0.42)]">
    <div class="grid grid-cols-2 gap-2">
      <button
        type="button"
        class="flex items-center justify-between rounded-[20px] border px-4 py-3 text-left transition"
        :class="activeTab === 'notify'
          ? 'border-sky-400/35 bg-sky-400/12 text-slate-50'
          : 'border-slate-800 bg-slate-900/70 text-slate-400 hover:border-slate-700 hover:text-slate-200'"
        @click="emit('update:activeTab', 'notify')"
      >
        <div>
          <div class="font-mono text-[11px] uppercase tracking-[0.14em] text-sky-300">Notifications</div>
          <div class="mt-1 text-sm font-semibold">通知捕获</div>
        </div>
        <span class="rounded-full border border-sky-400/30 bg-sky-400/10 px-3 py-1 font-mono text-xs text-slate-100">{{ notifyCount }}</span>
      </button>
      <button
        type="button"
        class="flex items-center justify-between rounded-[20px] border px-4 py-3 text-left transition"
        :class="activeTab === 'tweet'
          ? 'border-emerald-400/35 bg-emerald-400/12 text-slate-50'
          : 'border-slate-800 bg-slate-900/70 text-slate-400 hover:border-slate-700 hover:text-slate-200'"
        @click="emit('update:activeTab', 'tweet')"
      >
        <div>
          <div class="font-mono text-[11px] uppercase tracking-[0.14em] text-emerald-300">Tasks</div>
          <div class="mt-1 text-sm font-semibold">推文捕获</div>
        </div>
        <span class="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 font-mono text-xs text-slate-100">{{ tweetCount }}</span>
      </button>
    </div>
  </div>
</template>
