import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ResultsPanel from '../ResultsPanel.vue'
import { useResultsStore } from '../../../stores/results'
import { useTemplatesStore } from '../../../stores/templates'
import { useToastStore } from '../../../stores/toast'

vi.mock('../../../composables/useResultsHotkeys', () => ({
  useResultsHotkeys: () => undefined,
}))

describe('ResultsPanel', () => {
  let pinia: ReturnType<typeof createPinia>

  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)

    const results = useResultsStore()
    const templates = useTemplatesStore()
    const toast = useToastStore()

    toast.items = []
    templates.hydrate({
      notify_reply_templates: ['老板我私信您了'],
      dm_message_templates: ['您好，欢迎了解更多产品信息'],
    })
    results.hydrate([
      {
        key: 'n1',
        source: '通知页面',
        handle: '@notify',
        content: '老板 想了解下',
        time: '12:00:00',
        notify_retry_time: '',
      },
      {
        key: 't1',
        source: 'tweet',
        handle: '@tweet',
        content: '任务推文',
        time: '11:59:00',
        status_id: '123',
      },
    ], 0)
  })

  it('shows notify overview by default and switches to tweet overview', async () => {
    const wrapper = mount(ResultsPanel, {
      global: {
        plugins: [pinia],
        stubs: {
          NotifyWorkbench: { template: '<div data-testid="notify-workbench">notify</div>' },
          TweetWorkbench: { template: '<div data-testid="tweet-workbench">tweet</div>' },
        },
      },
    })

    expect(wrapper.text()).toContain('待处理')
    expect(wrapper.text()).toContain('重试')
    expect(wrapper.find('[data-testid="notify-workbench"]').exists()).toBe(true)

    const tweetTab = wrapper.findAll('button').find((button) => button.text().includes('推文捕获'))
    if (!tweetTab) throw new Error('tweet tab missing')
    await tweetTab.trigger('click')

    expect(wrapper.text()).toContain('用户数')
    expect(wrapper.text()).toContain('已关联')
    expect(wrapper.find('[data-testid="tweet-workbench"]').exists()).toBe(true)
  })
})
