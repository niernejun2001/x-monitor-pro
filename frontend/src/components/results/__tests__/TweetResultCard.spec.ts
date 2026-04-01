import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TweetResultCard from '../TweetResultCard.vue'
import type { PendingItem } from '../../../types'

function findButtonByText(wrapper: ReturnType<typeof mount>, text: string) {
  const button = wrapper.findAll('button').find((candidate) => candidate.text().includes(text))
  if (!button) throw new Error(`button not found: ${text}`)
  return button
}

describe('TweetResultCard', () => {
  it('renders status summary and emits actions', async () => {
    const item: PendingItem = {
      key: 'tweet-1',
      handle: '@taskdemo',
      time: '2m',
      content: '这是任务推文的内容',
      source: 'tweet',
      status_id: '778899',
      status_url: 'https://x.com/taskdemo/status/778899',
      status_handle: '@boss',
    }

    const wrapper = mount(TweetResultCard, {
      props: { item },
    })

    expect(wrapper.text()).toContain('来源状态')
    expect(wrapper.text()).toContain('状态绑定')
    expect(wrapper.text()).toContain('状态地址')
    expect(wrapper.text()).toContain('https://x.com/taskdemo/status/778899')

    await findButtonByText(wrapper, '打开来源').trigger('click')
    await findButtonByText(wrapper, '已处理').trigger('click')

    expect(wrapper.emitted('open')).toHaveLength(1)
    expect(wrapper.emitted('mark-done')).toHaveLength(1)
  })
})
