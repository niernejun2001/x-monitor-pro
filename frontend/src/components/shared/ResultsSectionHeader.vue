<script setup lang="ts">
const props = defineProps<{
  tone: 'sky' | 'emerald'
  code: string
  title: string
  subtitle: string
  count: number
  modelValue: string
  placeholder: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'clear'): void
}>()

function toneClasses(tone: 'sky' | 'emerald') {
  if (tone === 'emerald') {
    return {
      badge: 'border-emerald-400/30 bg-emerald-400/10',
      text: 'text-emerald-600',
    }
  }
  return {
    badge: 'border-emerald-400/40 bg-emerald-400/12',
    text: 'text-emerald-600',
  }
}
</script>

<template>
  <div class="flex flex-col gap-4 border-b border-emerald-100/90 px-5 py-5 xl:flex-row xl:items-center xl:justify-between">
    <div class="flex items-center gap-3">
      <div
        class="grid h-11 w-11 place-items-center rounded-2xl border font-mono text-xs font-bold tracking-[0.18em] text-emerald-950"
        :class="toneClasses(props.tone).badge"
      >
        {{ code }}
      </div>
      <div>
        <h3 class="text-base font-semibold text-emerald-950">{{ title }}</h3>
        <p class="text-xs text-emerald-700/60">{{ subtitle }}</p>
      </div>
      <span
        class="rounded-full border px-3 py-1 font-mono text-xs text-emerald-950"
        :class="toneClasses(props.tone).badge"
      >
        {{ count }}
      </span>
    </div>

    <div class="flex flex-col gap-3 sm:flex-row">
      <input
        :value="modelValue"
        type="text"
        :placeholder="placeholder"
        class="min-w-[220px] rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15"
        @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      />
      <slot name="actions">
        <button
          type="button"
          class="rounded-2xl border border-emerald-200/90 bg-emerald-50/80 px-4 py-3 text-sm font-semibold text-emerald-800"
          @click="emit('clear')"
        >
          清空
        </button>
      </slot>
    </div>
  </div>
</template>
