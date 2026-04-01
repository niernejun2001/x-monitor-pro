import { computed, ref, watch, type Ref } from 'vue'

interface QueueItemLike {
  key: string
}

export function useSelectableQueue<T extends QueueItemLike>(items: Ref<T[]>) {
  const selectedKey = ref('')

  const selectedItem = computed(() => {
    const currentItems = items.value
    if (!currentItems.length) return null
    const found = currentItems.find((item) => item.key === selectedKey.value)
    return found || currentItems[0]
  })

  const selectedIndex = computed(() => {
    if (!selectedItem.value) return -1
    return items.value.findIndex((item) => item.key === selectedItem.value?.key)
  })

  watch(
    items,
    (nextItems) => {
      if (!nextItems.length) {
        selectedKey.value = ''
        return
      }
      if (!nextItems.some((item) => item.key === selectedKey.value)) {
        selectedKey.value = nextItems[0].key
      }
    },
    { immediate: true },
  )

  function selectByOffset(delta: number) {
    const currentItems = items.value
    if (!currentItems.length) return
    const currentIndex = selectedIndex.value >= 0 ? selectedIndex.value : 0
    const nextIndex = Math.min(currentItems.length - 1, Math.max(0, currentIndex + delta))
    selectedKey.value = currentItems[nextIndex].key
  }

  return {
    selectedKey,
    selectedItem,
    selectedIndex,
    selectByOffset,
  }
}
