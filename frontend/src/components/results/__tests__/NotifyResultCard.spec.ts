import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import NotifyResultCard from '../NotifyResultCard.vue'
import type { PendingItem } from '../../../types'

function findButtonByText(wrapper: ReturnType<typeof mount>, text: string) {
  const button = wrapper.findAll('button').find((candidate) => candidate.text().includes(text))
  if (!button) throw new Error(`button not found: ${text}`)
  return button
}

describe('NotifyResultCard', () => {
  it('renders summary cards and expanded diagnostics', async () => {
    const item: PendingItem = {
      key: 'notify-1',
      handle: '@demo',
      time: '1m',
      content: '老板 想了解下',
      notification_type: 'reply_to_you',
      source: '通知页面',
      status_id: '123456',
      status_url: 'https://x.com/demo/status/123456',
      notify_retry_time: '2026-03-31 12:00:00',
      notify_flow_error_code: 'E_DM_EDITOR_NOT_FOUND',
      notify_flow_error_detail: '编辑器未找到',
      notify_reply_time: '10:00',
      notify_dm_text_generated: '这是一条生成后的私信文案',
    }

    const wrapper = mount(NotifyResultCard, {
      props: {
        item,
        expanded: true,
        isReplied: false,
        flowLabel: '等待重试',
        flowTone: 'border-amber-400/20 bg-amber-400/10 text-amber-700',
        intentLabel: 'HIGH 88',
        intentTone: 'border-emerald-400/20 bg-emerald-400/10 text-emerald-700',
        replyTemplates: ['老板我私信您了'],
        dmTemplates: ['您好，欢迎了解更多产品信息'],
        selectedReply: '老板我私信您了',
        selectedDm: '您好，欢迎了解更多产品信息',
      },
    })

    expect(wrapper.text()).toContain('回复并私信')
    expect(wrapper.text()).toContain('详情')
    expect(wrapper.text()).toContain('最近私信文案')
    expect(wrapper.text()).toContain('状态链接')
    expect(wrapper.text()).toContain('E_DM_EDITOR_NOT_FOUND')
    expect(wrapper.text()).toContain('这是一条生成后的私信文案')

    await findButtonByText(wrapper, '重试当前流程').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })
})
