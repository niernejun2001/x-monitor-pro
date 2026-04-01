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
      text: 'text-emerald-300',
    }
  }
  return {
    badge: 'border-sky-400/30 bg-sky-400/10',
    text: 'text-sky-300',
  }
}
</script>

<template>
  <div class="flex flex-col gap-4 border-b border-slate-800/80 px-5 py-5 xl:flex-row xl:items-center xl:justify-between">
    <div class="flex items-center gap-3">
      <div
        class="grid h-11 w-11 place-items-center rounded-2xl border font-mono text-xs font-bold tracking-[0.18em] text-slate-50"
        :class="toneClasses(props.tone).badge"
      >
        {{ code }}
      </div>
      <div>
        <h3 class="text-base font-semibold text-slate-50">{{ title }}</h3>
        <p class="text-xs text-slate-500">{{ subtitle }}</p>
      </div>
      <span
        class="rounded-full border px-3 py-1 font-mono text-xs text-slate-100"
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
        class="min-w-[220px] rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10"
        @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      />
      <slot name="actions">
        <button
          type="button"
          class="rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm font-semibold text-slate-200"
          @click="emit('clear')"
        >
          清空
        </button>
      </slot>
    </div>
  </div>
</template>
