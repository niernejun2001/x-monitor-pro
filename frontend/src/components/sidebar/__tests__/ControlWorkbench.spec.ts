import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ControlWorkbench from '../ControlWorkbench.vue'
import { useAppStore } from '../../../stores/app'
import { useToastStore } from '../../../stores/toast'


describe('ControlWorkbench', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useToastStore().items = []
  })

  function mountWorkbench() {
    return mount(ControlWorkbench, {
      global: {
        plugins: [createPinia()],
      },
    })
  }

  async function openAdvancedAi(wrapper: ReturnType<typeof mount>) {
    const advanced = wrapper.findAll('summary').find((summary) => summary.text().includes('高级配置'))
    if (!advanced) throw new Error('advanced summary missing')
    await advanced.trigger('click')
    const aiSummary = wrapper.findAll('summary').find((summary) => summary.text().includes('AI 与私信文案'))
    if (!aiSummary) throw new Error('ai summary missing')
    await aiSummary.trigger('click')
  }

  it('shows notification toggle busy state', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const app = useAppStore()
    app.notificationToggleBusy = true
    app.notificationMonitoring = true

    const wrapper = mount(ControlWorkbench, {
      global: {
        plugins: [pinia],
      },
    })

    expect(wrapper.text()).toContain('切换中')
    const checkbox = wrapper.find('input[aria-label="启动 Token"]').element
    expect(checkbox).toBeTruthy()
    const toggles = wrapper.findAll('input[type="checkbox"]')
    expect(toggles[0].attributes('disabled')).toBeDefined()
  })

  it('shows llm test busy label when testing', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const app = useAppStore()
    app.llmTestBusy = true
    app.llmFilterEnabled = true
    app.llmBaseUrl = 'http://127.0.0.1:11434/v1'
    app.llmModel = 'qwen'

    const wrapper = mount(ControlWorkbench, {
      global: {
        plugins: [pinia],
      },
    })

    await openAdvancedAi(wrapper)

    const testButton = wrapper.findAll('button').find((button) => button.text().includes('测试中'))
    if (!testButton) throw new Error('test button missing')
    expect(testButton.text()).toContain('测试中...')
    expect(testButton.attributes('disabled')).toBeDefined()
  })

  it('renders llm retry settings in connection section', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const app = useAppStore()
    app.llmRetryCount = 3
    app.llmRetryBackoffSec = 0.5

    const wrapper = mount(ControlWorkbench, {
      global: {
        plugins: [pinia],
      },
    })

    await openAdvancedAi(wrapper)

    const numberInputs = wrapper.findAll('input[type="number"]')
    expect(numberInputs.some((input) => (input.element as HTMLInputElement).value === '3')).toBe(true)
    expect(numberInputs.some((input) => (input.element as HTMLInputElement).value === '0.5')).toBe(true)
  })

  it('renders notification scheduler status', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const app = useAppStore()
    app.hydrate({
      tasks: [],
      is_running: true,
      pending: [],
      updates_last_seq: 0,
      updates_buffer_size: 0,
      notification_monitoring: true,
      notification_schedule_snapshot: {
        period_label: 'active',
        boost_active: true,
        idle_active: false,
        scan_multiplier: 0.72,
        refresh_multiplier: 0.79,
        idle_scan_streak: 2,
      },
      notification_refresh_interval: 88,
      notification_idle_scan_streak: 2,
      notification_full_refresh_pending: true,
      notification_dm_light_scan_count: 3,
      delegated_account: '',
      delegated_enabled: false,
      headless_mode: false,
      notify_reply_templates: [],
      dm_message_templates: [],
      llm_filter_enabled: false,
      llm_filter_base_url: '',
      llm_filter_model: '',
      llm_filter_timeout_sec: 8,
      llm_filter_timeout_max_sec: 120,
      llm_filter_prompt_template: '',
      llm_intent_prompt_template: '',
      dm_llm_rewrite_enabled: false,
      dm_llm_rewrite_prompt_template: '',
      dm_llm_rewrite_max_chars: 260,
      dm_llm_rewrite_temperature: 0.35,
      dm_llm_rewrite_max_regen: 1,
      dm_llm_rewrite_dedupe_size: 200,
      notify_voice_block_keywords_text: '',
      notification_reply_only_mode: true,
    } as any)

    const wrapper = mount(ControlWorkbench, {
      global: {
        plugins: [pinia],
      },
    })

    expect(wrapper.text()).toContain('Scheduler')
    expect(wrapper.text()).toContain('白天 · 提速')
    expect(wrapper.text()).toContain('私信关键区轻扫 3 次')
  })
})
