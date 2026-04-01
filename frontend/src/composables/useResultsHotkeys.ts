import { onBeforeUnmount, onMounted, type ComputedRef, type Ref } from 'vue'
import type { PendingItem } from '../types'

type PanelTab = 'notify' | 'tweet'

interface UseResultsHotkeysOptions {
  activeTab: Ref<PanelTab>
  filteredNotifyItems: ComputedRef<PendingItem[]>
  filteredTweetItems: ComputedRef<PendingItem[]>
  selectedNotifyItem: ComputedRef<PendingItem | null>
  selectedTweetItem: ComputedRef<PendingItem | null>
  focusNotifySearch: () => void
  focusTweetSearch: () => void
  selectNotifyByOffset: (delta: number) => void
  selectTweetByOffset: (delta: number) => void
  toggleNotifyDetails: (key: string) => void
  toggleNotifySelected: (key: string) => void
  toggleTweetSelected: (key: string) => void
  handleNotifyReply: (item: PendingItem) => void | Promise<void>
  handleRetry: (item: PendingItem) => void | Promise<void>
  handleMarkDone: (item: PendingItem) => void | Promise<void>
  openTweetSource: (item: PendingItem) => void
}

function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName
  return target.isContentEditable || tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
}

export function useResultsHotkeys(options: UseResultsHotkeysOptions) {
  function handlePanelHotkeys(event: KeyboardEvent) {
    if (isEditableTarget(event.target)) return

    if (options.activeTab.value === 'notify') {
      if (!options.filteredNotifyItems.value.length) return

      if (event.key === '/' && !event.metaKey && !event.ctrlKey && !event.altKey) {
        event.preventDefault()
        options.focusNotifySearch()
        return
      }

      if (event.key === 'j' || event.key === 'ArrowDown') {
        event.preventDefault()
        options.selectNotifyByOffset(1)
        return
      }

      if (event.key === 'k' || event.key === 'ArrowUp') {
        event.preventDefault()
        options.selectNotifyByOffset(-1)
        return
      }

      const item = options.selectedNotifyItem.value
      if (!item) return

      if (event.key === 'e') {
        event.preventDefault()
        options.toggleNotifyDetails(item.key)
        return
      }

      if (event.key === 'x') {
        event.preventDefault()
        options.toggleNotifySelected(item.key)
        return
      }

      if (event.key === 'd') {
        event.preventDefault()
        void options.handleMarkDone(item)
        return
      }

      if (event.key === 'r') {
        event.preventDefault()
        void options.handleRetry(item)
        return
      }

      if (event.key === 'Enter') {
        event.preventDefault()
        void options.handleNotifyReply(item)
      }
      return
    }

    if (options.activeTab.value !== 'tweet' || !options.filteredTweetItems.value.length) return

    if (event.key === '/' && !event.metaKey && !event.ctrlKey && !event.altKey) {
      event.preventDefault()
      options.focusTweetSearch()
      return
    }

    if (event.key === 'j' || event.key === 'ArrowDown') {
      event.preventDefault()
      options.selectTweetByOffset(1)
      return
    }

    if (event.key === 'k' || event.key === 'ArrowUp') {
      event.preventDefault()
      options.selectTweetByOffset(-1)
      return
    }

    const item = options.selectedTweetItem.value
    if (!item) return

    if (event.key === 'x') {
      event.preventDefault()
      options.toggleTweetSelected(item.key)
      return
    }

    if (event.key === 'd') {
      event.preventDefault()
      void options.handleMarkDone(item)
      return
    }

    if (event.key === 'Enter' || event.key === 'o') {
      event.preventDefault()
      options.openTweetSource(item)
    }
  }

  onMounted(() => {
    window.addEventListener('keydown', handlePanelHotkeys)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('keydown', handlePanelHotkeys)
  })
}
