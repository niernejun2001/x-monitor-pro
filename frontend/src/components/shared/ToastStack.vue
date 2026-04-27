<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useToastStore } from '../../stores/toast'

const store = useToastStore()
const { items } = storeToRefs(store)
</script>

<template>
  <div class="pointer-events-none fixed right-4 top-4 z-50 flex w-[320px] max-w-[calc(100vw-2rem)] flex-col gap-3">
    <transition-group name="toast">
      <div
        v-for="item in items"
        :key="item.id"
        class="pointer-events-auto rounded-2xl border px-4 py-3 shadow-2xl backdrop-blur"
        :class="{
          'border-emerald-400/50 bg-white/95 text-emerald-950': item.type === 'info',
          'border-emerald-400/35 bg-emerald-500/10 text-emerald-800': item.type === 'success',
          'border-rose-400/35 bg-rose-500/10 text-rose-700': item.type === 'error'
        }"
      >
        <div class="text-sm leading-6">{{ item.message }}</div>
      </div>
    </transition-group>
  </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.18s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
