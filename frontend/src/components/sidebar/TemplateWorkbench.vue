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
const templateModeText = computed(() => (activeEditIndex.value >= 0 ? `正在编辑 #${activeEditIndex.value + 1}` : '新增模板'))

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
    <div class="rounded-3xl border border-emerald-100/90 bg-white/75 p-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="font-mono text-[11px] uppercase tracking-[0.12em] text-emerald-600">Templates</div>
          <div class="mt-1 text-base font-semibold text-emerald-950">文案管理</div>
          <div class="mt-2 text-xs leading-6 text-emerald-700/60">先选择类型，再新增或点列表里的模板进行编辑。</div>
        </div>
        <div class="rounded-full border border-emerald-100/90 bg-emerald-50/80 px-3 py-1 text-xs text-emerald-700">
          {{ templateModeText }}
        </div>
      </div>

      <div class="mt-4 grid grid-cols-2 gap-2">
        <button
          v-for="button in templateSectionButtons"
          :key="button.key"
          type="button"
          class="rounded-2xl border px-3 py-3 text-sm font-semibold transition"
          :class="button.key === templateSection
            ? 'border-emerald-400/50 bg-emerald-400/15 text-emerald-950'
            : 'border-emerald-100/90 bg-emerald-50/80 text-emerald-700/80 hover:border-emerald-200/90 hover:text-emerald-800'"
          @click="templateSection = button.key"
        >
          {{ button.label }}
          <span class="ml-1 font-mono text-[10px] opacity-70">
            {{ button.key === 'reply' ? replyTemplates.length : dmTemplates.length }}
          </span>
        </button>
      </div>

      <div class="mt-4 grid gap-3">
        <label class="space-y-2">
          <span class="text-[11px] font-medium uppercase tracking-[0.12em] text-emerald-700/60">
            {{ templateSection === 'reply' ? '评论回复文案' : '私信文案' }}
          </span>
          <textarea
            v-model="activeInput"
            :aria-label="templateSection === 'reply' ? '评论模板编辑器' : '私信模板编辑器'"
            :placeholder="templateSection === 'reply' ? '输入评论回复文案...' : '输入私信文案...'"
            class="w-full rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-sm text-emerald-950 outline-none transition focus:border-emerald-400/60 focus:ring-4 focus:ring-emerald-400/15"
            :class="templateSection === 'reply' ? 'min-h-[104px]' : 'min-h-[132px]'"
          />
        </label>

        <div class="grid gap-2 sm:grid-cols-2">
          <button
            type="button"
            class="rounded-2xl bg-emerald-400 px-4 py-3 text-sm font-semibold text-emerald-950"
            @click="submitTemplate(templateSection)"
          >
            {{ activeEditIndex >= 0 ? '保存修改' : '添加模板' }}
          </button>
          <button
            v-if="activeEditIndex >= 0"
            type="button"
            class="rounded-2xl border border-emerald-200/90 bg-emerald-50/80 px-4 py-3 text-sm font-semibold text-emerald-800"
            @click="cancelTemplateEdit(templateSection)"
          >
            取消修改
          </button>
          <div
            v-else
            class="rounded-2xl border border-emerald-100/90 bg-white/80 px-4 py-3 text-center text-sm text-emerald-700/60"
          >
            输入内容后点击添加
          </div>
        </div>
      </div>
    </div>

    <div class="rounded-3xl border border-emerald-100/90 bg-white/70 p-3">
      <div class="mb-3 flex items-center justify-between gap-3 px-1">
        <div class="text-sm font-semibold text-emerald-950">已有模板</div>
        <div class="text-xs text-emerald-700/60">{{ activeTemplates.length }} 条</div>
      </div>

      <div v-if="activeTemplates.length" class="max-h-[520px] space-y-2 overflow-y-auto pr-1">
        <article
          v-for="(item, index) in activeTemplates"
          :key="`${templateSection}-${index}`"
          class="rounded-2xl border p-3 transition"
          :class="selectedIndex === index
            ? 'border-emerald-400/50 bg-emerald-400/10'
            : 'border-emerald-100/90 bg-white/75'"
        >
          <button type="button" class="w-full text-left" @click="selectedIndex = index">
            <div class="flex items-start justify-between gap-3">
              <div class="text-[11px] uppercase tracking-[0.12em] text-emerald-700/60">#{{ index + 1 }}</div>
              <div class="rounded-full border border-emerald-100/90 px-2 py-0.5 text-[10px] text-emerald-700/60">
                {{ templateSection === 'reply' ? '回复' : '私信' }}
              </div>
            </div>
            <div class="mt-2 line-clamp-3 text-sm leading-6 text-emerald-800">{{ item }}</div>
          </button>
          <div class="mt-3 grid grid-cols-2 gap-2">
            <button
              type="button"
              class="rounded-2xl border border-emerald-200/90 bg-emerald-50/80 px-3 py-2 text-xs font-semibold text-emerald-800"
              @click="beginTemplateEdit(templateSection, index)"
            >
              编辑
            </button>
            <button
              type="button"
              class="rounded-2xl bg-rose-500 px-3 py-2 text-xs font-semibold text-white"
              @click="removeTemplate(templateSection, index)"
            >
              删除
            </button>
          </div>
        </article>
      </div>

      <div v-else class="rounded-2xl border border-dashed border-emerald-100/90 bg-white/70 px-4 py-8 text-center text-sm text-emerald-700/60">
        当前分组还没有模板
      </div>
    </div>
  </section>
</template>
