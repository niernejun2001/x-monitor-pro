import { computed, defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useResultsHotkeys } from '../useResultsHotkeys'
import type { PendingItem } from '../../types'

function mountHarness(overrides: Partial<Parameters<typeof useResultsHotkeys>[0]> = {}) {
  const notifyItem: PendingItem = { key: 'n1', source: '通知页面', handle: '@notify', content: 'hello' }
  const tweetItem: PendingItem = { key: 't1', source: 'tweet', handle: '@tweet', content: 'world' }

  const spies = {
    focusNotifySearch: vi.fn(),
    focusTweetSearch: vi.fn(),
    selectNotifyByOffset: vi.fn(),
    selectTweetByOffset: vi.fn(),
    toggleNotifyDetails: vi.fn(),
    toggleNotifySelected: vi.fn(),
    toggleTweetSelected: vi.fn(),
    handleNotifyReply: vi.fn(),
    handleRetry: vi.fn(),
    handleMarkDone: vi.fn(),
    openTweetSource: vi.fn(),
  }

  const options = {
    activeTab: ref<'notify' | 'tweet'>('notify'),
    filteredNotifyItems: computed(() => [notifyItem]),
    filteredTweetItems: computed(() => [tweetItem]),
    selectedNotifyItem: computed(() => notifyItem),
    selectedTweetItem: computed(() => tweetItem),
    ...spies,
    ...overrides,
  }

  const Harness = defineComponent({
    setup() {
      useResultsHotkeys(options)
      return () => null
    },
  })

  const wrapper = mount(Harness)
  return { wrapper, options, spies, notifyItem, tweetItem }
}

describe('useResultsHotkeys', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('routes notify hotkeys to notify handlers', async () => {
    const { wrapper, spies } = mountHarness()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: '/' }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'e' }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))

    expect(spies.focusNotifySearch).toHaveBeenCalledTimes(1)
    expect(spies.toggleNotifyDetails).toHaveBeenCalledWith('n1')
    expect(spies.handleNotifyReply).toHaveBeenCalledTimes(1)

    wrapper.unmount()
  })

  it('routes tweet hotkeys to tweet handlers and ignores editable targets', async () => {
    const input = document.createElement('input')
    document.body.appendChild(input)

    const { wrapper, options, spies } = mountHarness({
      activeTab: ref<'notify' | 'tweet'>('tweet'),
    })

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'o' }))
    expect(spies.openTweetSource).toHaveBeenCalledTimes(1)

    const editableEvent = new KeyboardEvent('keydown', { key: 'x', bubbles: true })
    Object.defineProperty(editableEvent, 'target', { value: input })
    window.dispatchEvent(editableEvent)

    expect(spies.toggleTweetSelected).not.toHaveBeenCalled()

    wrapper.unmount()
    document.body.removeChild(input)
  })
})
