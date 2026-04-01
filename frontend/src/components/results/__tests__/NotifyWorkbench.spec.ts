import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import NotifyWorkbench from '../NotifyWorkbench.vue'
import type { PendingItem } from '../../../types'

const sampleItem: PendingItem = {
  key: 'notify-1',
  source: '通知页面',
  handle: '@demo',
  content: '老板 想了解下',
  time: '1m',
}

describe('NotifyWorkbench', () => {
  it('emits status filter and command actions', async () => {
    const wrapper = mount(NotifyWorkbench, {
      props: {
        notifyCount: 1,
        searchText: '',
        statusFilter: 'all',
        statusButtons: [
          { key: 'all', label: '全部', count: 1 },
          { key: 'retry', label: '重试中', count: 0 },
        ],
        commandActions: [
          { key: 'bulk_done', label: '批量已处理' },
        ],
        commandHints: ['Enter 回复'],
        allItemsCount: 1,
        filteredItems: [sampleItem],
        selectedIndex: 0,
        selectedVisibleCount: 0,
        selectedItem: sampleItem,
        selectedReply: '',
        selectedDm: '',
        expanded: false,
        replyTemplates: ['老板我私信您了'],
        dmTemplates: ['您好'],
        isReplied: () => false,
        flowLabel: () => '等待回复',
        flowTone: () => 'tone-flow',
        intentLabel: () => 'HIGH 88',
        intentTone: () => 'tone-intent',
        isSelected: () => false,
      },
      global: {
        stubs: {
          NotifyQueueItem: { template: '<button data-testid="queue-item" @click="$emit(\'select\')">queue</button>' },
          NotifyResultCard: { template: '<div data-testid="result-card">card</div>' },
        },
      },
    })

    const retryButton = wrapper.findAll('button').find((button) => button.text().includes('重试中'))
    if (!retryButton) throw new Error('retry button missing')
    await retryButton.trigger('click')

    const commandButton = wrapper.findAll('button').find((button) => button.text().includes('批量已处理'))
    if (!commandButton) throw new Error('command button missing')
    await commandButton.trigger('click')

    expect(wrapper.emitted('update:statusFilter')?.[0]).toEqual(['retry'])
    expect(wrapper.emitted('command')?.[0]).toEqual(['bulk_done'])
  })

  it('shows empty state action when filtered list is empty', async () => {
    const wrapper = mount(NotifyWorkbench, {
      props: {
        notifyCount: 2,
        searchText: 'demo',
        statusFilter: 'retry',
        statusButtons: [
          { key: 'all', label: '全部', count: 2 },
          { key: 'retry', label: '重试中', count: 0 },
        ],
        commandActions: [],
        commandHints: [],
        allItemsCount: 2,
        filteredItems: [],
        selectedIndex: 0,
        selectedVisibleCount: 0,
        selectedItem: null,
        selectedReply: '',
        selectedDm: '',
        expanded: false,
        replyTemplates: [],
        dmTemplates: [],
        isReplied: () => false,
        flowLabel: () => '',
        flowTone: () => '',
        intentLabel: () => '',
        intentTone: () => '',
        isSelected: () => false,
      },
    })

    const showAllButton = wrapper.findAll('button').find((button) => button.text().includes('查看全部'))
    if (!showAllButton) throw new Error('show all button missing')
    await showAllButton.trigger('click')

    expect(wrapper.emitted('update:statusFilter')?.[0]).toEqual(['all'])
  })
})
