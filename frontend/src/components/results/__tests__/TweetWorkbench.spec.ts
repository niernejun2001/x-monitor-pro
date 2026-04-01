import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TweetWorkbench from '../TweetWorkbench.vue'
import type { PendingItem } from '../../../types'

const sampleItem: PendingItem = {
  key: 'tweet-1',
  source: 'tweet',
  handle: '@taskdemo',
  content: '任务推文内容',
  time: '2m',
}

describe('TweetWorkbench', () => {
  it('emits clear-blocklist and command actions', async () => {
    const wrapper = mount(TweetWorkbench, {
      props: {
        tweetCount: 1,
        searchText: '',
        metrics: { total: 1, uniqueHandles: 1, withStatus: 0 },
        commandActions: [
          { key: 'bulk_done', label: '批量已处理' },
        ],
        commandHints: ['Enter / O 打开'],
        allItemsCount: 1,
        filteredItems: [sampleItem],
        selectedIndex: 0,
        selectedVisibleCount: 0,
        selectedItem: sampleItem,
        isSelected: () => false,
      },
      global: {
        stubs: {
          TweetQueueItem: { template: '<button data-testid="queue-item" @click="$emit(\'select\')">queue</button>' },
          TweetResultCard: { template: '<div data-testid="result-card">card</div>' },
        },
      },
    })

    const blocklistButton = wrapper.findAll('button').find((button) => button.text().includes('清空黑名单'))
    if (!blocklistButton) throw new Error('clear blocklist button missing')
    await blocklistButton.trigger('click')

    const commandButton = wrapper.findAll('button').find((button) => button.text().includes('批量已处理'))
    if (!commandButton) throw new Error('command button missing')
    await commandButton.trigger('click')

    expect(wrapper.emitted('clear-blocklist')).toHaveLength(1)
    expect(wrapper.emitted('command')?.[0]).toEqual(['bulk_done'])
  })

  it('emits clear search from empty-filter state', async () => {
    const wrapper = mount(TweetWorkbench, {
      props: {
        tweetCount: 2,
        searchText: 'boss',
        metrics: { total: 0, uniqueHandles: 0, withStatus: 0 },
        commandActions: [],
        commandHints: [],
        allItemsCount: 2,
        filteredItems: [],
        selectedIndex: 0,
        selectedVisibleCount: 0,
        selectedItem: null,
        isSelected: () => false,
      },
    })

    const clearFilterButton = wrapper.findAll('button').find((button) => button.text().includes('清空筛选'))
    if (!clearFilterButton) throw new Error('clear filter button missing')
    await clearFilterButton.trigger('click')

    expect(wrapper.emitted('update:searchText')?.[0]).toEqual([''])
  })
})
