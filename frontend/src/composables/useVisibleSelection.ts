import { computed, ref, type Ref } from 'vue'

interface QueueItemLike {
  key: string
}

export function useVisibleSelection<T extends QueueItemLike>(items: Ref<T[]>) {
  const selectedByKey = ref<Record<string, boolean>>({})

  const selectedVisibleCount = computed(() =>
    items.value.filter((item) => !!selectedByKey.value[item.key]).length,
  )

  function toggleSelected(key: string) {
    selectedByKey.value[key] = !selectedByKey.value[key]
  }

  function selectAllVisible() {
    const next = { ...selectedByKey.value }
    items.value.forEach((item) => {
      next[item.key] = true
    })
    selectedByKey.value = next
  }

  function clearVisibleSelection() {
    const next = { ...selectedByKey.value }
    items.value.forEach((item) => {
      delete next[item.key]
    })
    selectedByKey.value = next
  }

  function deselectKey(key: string) {
    if (!(key in selectedByKey.value)) return
    const next = { ...selectedByKey.value }
    delete next[key]
    selectedByKey.value = next
  }

  function isSelected(key: string) {
    return !!selectedByKey.value[key]
  }

  return {
    selectedByKey,
    selectedVisibleCount,
    toggleSelected,
    selectAllVisible,
    clearVisibleSelection,
    deselectKey,
    isSelected,
  }
}
