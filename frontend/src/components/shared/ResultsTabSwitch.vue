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
  <div class="rounded-[24px] border border-emerald-100/90 bg-white/80 p-2 shadow-[0_24px_80px_rgba(16,185,129,0.16)]">
    <div class="grid grid-cols-2 gap-2">
      <button
        type="button"
        class="flex items-center justify-between rounded-[20px] border px-4 py-3 text-left transition"
        :class="activeTab === 'notify'
          ? 'border-emerald-400/50 bg-emerald-400/15 text-emerald-950'
          : 'border-emerald-100/90 bg-emerald-50/80 text-emerald-700/80 hover:border-emerald-200/90 hover:text-emerald-800'"
        @click="emit('update:activeTab', 'notify')"
      >
        <div>
          <div class="font-mono text-[11px] uppercase tracking-[0.14em] text-emerald-600">Notifications</div>
          <div class="mt-1 text-sm font-semibold">通知捕获</div>
        </div>
        <span class="rounded-full border border-emerald-400/40 bg-emerald-400/12 px-3 py-1 font-mono text-xs text-emerald-950">{{ notifyCount }}</span>
      </button>
      <button
        type="button"
        class="flex items-center justify-between rounded-[20px] border px-4 py-3 text-left transition"
        :class="activeTab === 'tweet'
          ? 'border-emerald-400/35 bg-emerald-400/12 text-emerald-950'
          : 'border-emerald-100/90 bg-emerald-50/80 text-emerald-700/80 hover:border-emerald-200/90 hover:text-emerald-800'"
        @click="emit('update:activeTab', 'tweet')"
      >
        <div>
          <div class="font-mono text-[11px] uppercase tracking-[0.14em] text-emerald-600">Tasks</div>
          <div class="mt-1 text-sm font-semibold">推文捕获</div>
        </div>
        <span class="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 font-mono text-xs text-emerald-950">{{ tweetCount }}</span>
      </button>
    </div>
  </div>
</template>
