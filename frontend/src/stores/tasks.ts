import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { TaskItem } from '../types'
import * as api from '../api/services'

export const useTasksStore = defineStore('tasks', () => {
  const tasks = ref<TaskItem[]>([])

  function hydrate(nextTasks: TaskItem[] = []) {
    tasks.value = Array.isArray(nextTasks) ? [...nextTasks] : []
  }

  async function add(url: string) {
    const data = await api.addTask(url)
    tasks.value = Array.isArray(data.tasks) ? [...data.tasks] : []
    return data
  }

  async function remove(url: string) {
    const data = await api.removeTask(url)
    tasks.value = Array.isArray(data.tasks) ? [...data.tasks] : []
    return data
  }

  return { tasks, hydrate, add, remove }
})
