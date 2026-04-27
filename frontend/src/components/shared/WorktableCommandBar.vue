<script setup lang="ts">
export interface CommandAction {
  key: string
  label: string
  tone?: 'neutral' | 'accent' | 'success' | 'warning'
  disabled?: boolean
}

const props = defineProps<{
  statusLabel: string
  statusValue: string
  secondaryLabel?: string
  secondaryValue?: string
  actions: CommandAction[]
  hints: string[]
}>()

const emit = defineEmits<{
  (e: 'action', key: string): void
}>()

function toneClass(tone: CommandAction['tone']) {
  if (tone === 'accent') return 'border-emerald-400/30 bg-emerald-400/12 text-emerald-700'
  if (tone === 'success') return 'border-emerald-400/20 bg-emerald-400/10 text-emerald-700'
  if (tone === 'warning') return 'border-amber-400/20 bg-amber-400/10 text-amber-700'
  return 'border-emerald-100/90 bg-white/80 text-emerald-700'
}
</script>

<template>
  <div class="grid gap-3 rounded-[22px] border border-emerald-100/90 bg-white/60 p-3 lg:grid-cols-[minmax(0,1fr)_auto]">
    <div class="flex flex-wrap items-center gap-2 text-xs text-emerald-700/80">
      <span class="rounded-full border border-emerald-100/90 bg-white/80 px-3 py-1 font-mono text-emerald-800">
        {{ statusLabel }} {{ statusValue }}
      </span>
      <span v-if="secondaryLabel && secondaryValue" class="rounded-full border border-emerald-100/90 bg-white/80 px-3 py-1 font-mono text-emerald-800">
        {{ secondaryLabel }} {{ secondaryValue }}
      </span>
      <button
        v-for="action in props.actions"
        :key="action.key"
        type="button"
        class="rounded-full border px-3 py-1 font-mono text-xs disabled:opacity-40"
        :class="toneClass(action.tone)"
        :disabled="action.disabled"
        @click="emit('action', action.key)"
      >
        {{ action.label }}
      </button>
    </div>

    <div class="flex flex-wrap items-center gap-2 text-xs text-emerald-700/60">
      <span v-for="hint in props.hints" :key="hint" class="rounded-full border border-emerald-100/90 bg-white/70 px-3 py-1">
        {{ hint }}
      </span>
    </div>
  </div>
</template>
