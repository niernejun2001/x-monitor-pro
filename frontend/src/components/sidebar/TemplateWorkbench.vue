<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'
import { useTemplatesStore } from '../../stores/templates'
import { useToastStore } from '../../stores/toast'

const templatesStore = useTemplatesStore()
const toast = useToastStore()
const { replyTemplates, dmTemplates, editIndex } = storeToRefs(templatesStore)

const replyInput = ref('')
const dmInput = ref('')
const templateSection = ref<'reply' | 'dm'>('reply')
const selectedIndex = ref(0)

const templateSectionButtons = [
  { key: 'reply', label: '评论模板' },
  { key: 'dm', label: '私信模板' },
] as const

const activeTemplates = computed(() => (
  templateSection.value === 'reply' ? replyTemplates.value : dmTemplates.value
))

const activeInput = computed({
  get: () => (templateSection.value === 'reply' ? replyInput.value : dmInput.value),
  set: (value: string) => {
    if (templateSection.value === 'reply') replyInput.value = value
    else dmInput.value = value
  },
})

const activeEditIndex = computed(() => editIndex.value[templateSection.value])
const selectedTemplate = computed(() => activeTemplates.value[selectedIndex.value] || '')

watch([templateSection, activeTemplates], () => {
  if (!activeTemplates.value.length) {
    selectedIndex.value = 0
    return
  }
  if (selectedIndex.value >= activeTemplates.value.length) selectedIndex.value = 0
}, { immediate: true })

function beginTemplateEdit(type: 'reply' | 'dm', index: number) {
  templatesStore.setEdit(type, index)
  selectedIndex.value = index
  if (type === 'reply') replyInput.value = replyTemplates.value[index] || ''
  else dmInput.value = dmTemplates.value[index] || ''
}

function cancelTemplateEdit(type: 'reply' | 'dm') {
  templatesStore.cancelEdit(type)
  if (type === 'reply') replyInput.value = ''
  else dmInput.value = ''
}

async function submitTemplate(type: 'reply' | 'dm') {
  const content = (type === 'reply' ? replyInput.value : dmInput.value).trim()
  if (!content) {
    toast.push('模板内容不能为空', 'error', 3200)
    return
  }
  try {
    if (editIndex.value[type] >= 0) {
      await templatesStore.update(type, editIndex.value[type], content)
      selectedIndex.value = editIndex.value[type] >= 0 ? editIndex.value[type] : selectedIndex.value
    } else {
      await templatesStore.add(type, content)
      const list = type === 'reply' ? replyTemplates.value : dmTemplates.value
      selectedIndex.value = Math.max(0, list.length - 1)
    }
    if (type === 'reply') replyInput.value = ''
    else dmInput.value = ''
    toast.push('模板已保存', 'success')
  } catch (error: any) {
    toast.push(error?.message || '模板保存失败', 'error', 4200)
  }
}

async function removeTemplate(type: 'reply' | 'dm', index: number) {
  if (!window.confirm('确定删除这条模板吗？')) return
  try {
    await templatesStore.remove(type, index)
    if (selectedIndex.value > 0 && selectedIndex.value >= activeTemplates.value.length) {
      selectedIndex.value -= 1
    }
    toast.push('模板已删除', 'success')
  } catch (error: any) {
    toast.push(error?.message || '删除模板失败', 'error', 4200)
  }
}
</script>

<template>
  <section class="space-y-4">
    <div class="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="font-mono text-[11px] uppercase tracking-[0.12em] text-sky-300">Templates</div>
          <div class="mt-1 text-sm font-medium text-slate-100">文案集中管理</div>
          <div class="mt-2 text-xs leading-6 text-slate-500">左侧只保留模板队列，编辑器固定在上方，避免每条模板都展开占满侧栏。</div>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <button
            v-for="button in templateSectionButtons"
            :key="button.key"
            type="button"
            class="rounded-2xl border px-3 py-2 text-xs font-medium transition"
            :class="button.key === templateSection
              ? 'border-sky-400/35 bg-sky-400/12 text-slate-50'
              : 'border-slate-800 bg-slate-900/70 text-slate-400 hover:border-slate-700 hover:text-slate-200'"
            @click="templateSection = button.key"
          >
            {{ button.label }}
            <span class="ml-1 font-mono text-[10px] opacity-70">
              {{ button.key === 'reply' ? replyTemplates.length : dmTemplates.length }}
            </span>
          </button>
        </div>
      </div>

      <div class="mt-4 grid gap-3">
        <label class="space-y-2">
          <span class="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">
            {{ templateSection === 'reply' ? '评论回复文案' : '私信文案' }}
          </span>
          <textarea
            v-model="activeInput"
            :aria-label="templateSection === 'reply' ? '评论模板编辑器' : '私信模板编辑器'"
            :placeholder="templateSection === 'reply' ? '输入评论回复文案...' : '输入私信文案...'"
            class="w-full rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400/45 focus:ring-4 focus:ring-sky-400/10"
            :class="templateSection === 'reply' ? 'min-h-[104px]' : 'min-h-[132px]'"
          />
        </label>

        <div class="grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            class="rounded-2xl bg-sky-400 px-4 py-3 text-sm font-semibold text-slate-950"
            @click="submitTemplate(templateSection)"
          >
            {{ activeEditIndex >= 0 ? '保存修改' : '添加模板' }}
          </button>
          <button
            v-if="activeEditIndex >= 0"
            type="button"
            class="rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm font-semibold text-slate-200"
            @click="cancelTemplateEdit(templateSection)"
          >
            取消修改
          </button>
          <div
            v-else
            class="rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-500"
          >
            当前为新增模式
          </div>
        </div>
      </div>
    </div>

    <div class="grid gap-4">
      <div class="rounded-2xl border border-slate-800 bg-slate-950/55 p-3">
        <div class="mb-3 flex items-center justify-between gap-3 px-1">
          <div class="text-sm font-medium text-slate-100">模板队列</div>
          <div class="text-xs text-slate-500">点击查看 / 编辑</div>
        </div>
        <div v-if="activeTemplates.length" class="max-h-[360px] space-y-2 overflow-y-auto pr-1">
          <button
            v-for="(item, index) in activeTemplates"
            :key="`${templateSection}-${index}`"
            type="button"
            class="w-full rounded-2xl border px-3 py-3 text-left transition"
            :class="selectedIndex === index
              ? 'border-sky-400/35 bg-sky-400/10'
              : 'border-slate-800 bg-slate-950/70 hover:border-slate-700 hover:bg-slate-950/90'"
            @click="selectedIndex = index"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="text-[11px] uppercase tracking-[0.12em] text-slate-500">#{{ index + 1 }}</div>
              <div class="rounded-full border border-slate-800 px-2 py-0.5 text-[10px] text-slate-500">
                {{ templateSection === 'reply' ? '回复' : '私信' }}
              </div>
            </div>
            <div class="mt-2 text-sm leading-6 text-slate-200">{{ item }}</div>
          </button>
        </div>
        <div v-else class="rounded-2xl border border-dashed border-slate-800 bg-slate-950/70 px-4 py-6 text-center text-sm text-slate-500">
          当前分组还没有模板
        </div>
      </div>

      <div class="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="font-mono text-[11px] uppercase tracking-[0.12em] text-sky-300">Detail</div>
            <div class="mt-1 text-sm font-medium text-slate-100">当前选中模板</div>
          </div>
          <div class="rounded-full border border-slate-800 px-2.5 py-1 text-[11px] text-slate-400">
            {{ activeTemplates.length ? `${selectedIndex + 1}/${activeTemplates.length}` : '空' }}
          </div>
        </div>

        <div v-if="activeTemplates.length" class="mt-4 space-y-4">
          <div class="rounded-2xl border border-slate-800 bg-slate-950/80 p-4">
            <div class="text-[11px] uppercase tracking-[0.12em] text-slate-500">内容预览</div>
            <div class="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-200">{{ selectedTemplate }}</div>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <button
              type="button"
              class="rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm font-semibold text-slate-200"
              @click="beginTemplateEdit(templateSection, selectedIndex)"
            >
              编辑当前模板
            </button>
            <button
              type="button"
              class="rounded-2xl bg-rose-500 px-4 py-3 text-sm font-semibold text-white"
              @click="removeTemplate(templateSection, selectedIndex)"
            >
              删除当前模板
            </button>
          </div>
        </div>
        <div v-else class="mt-4 rounded-2xl border border-dashed border-slate-800 bg-slate-950/70 px-4 py-6 text-center text-sm text-slate-500">
          从上方新建一条模板开始
        </div>
      </div>
    </div>
  </section>
</template>
