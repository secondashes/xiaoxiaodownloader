<template>
  <div v-if="visible" class="dl-manager">
    <!-- 顶部工具栏 -->
    <div class="dl-toolbar">
      <div class="dl-toolbar-left">
        <n-button size="small" quaternary @click="$emit('close')">← 返回</n-button>
        <div class="dl-title">
          <n-icon size="18"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></svg></n-icon>
          <span>下载管理</span>
        </div>
        <span class="dl-stats">{{ statsText }}</span>
      </div>
      <div class="dl-toolbar-actions">
        <n-button v-if="hasPaused" size="small" quaternary @click="$emit('resume-all')">全部继续</n-button>
        <div class="dl-shutdown">
          <n-switch size="small" :value="shutdownOn" @update:value="v => $emit('toggle-shutdown', v)" />
          <span class="dl-shutdown-label">下载完关机</span>
        </div>
      </div>
    </div>

    <!-- 任务树列表（母文件夹 → 任务 → 文件） -->
    <div class="dl-body">
      <div v-if="groups.length === 0" class="dl-empty">
        <div class="dl-empty-icon">⬇️</div>
        <div>暂无下载任务</div>
        <div class="dl-empty-hint">去搜索或解析相册，点击下载后会出现在这里</div>
      </div>

      <div
        v-for="g in groups"
        :key="g.key"
        class="dl-group"
        :data-group-key="g.key"
        :class="{ 'dl-group-focus': g.tasks.some(t => t.id === focusTaskId) }"
      >
        <!-- 母文件夹头（点击展开/收起该组全部任务） -->
        <div class="dl-group-header" @click="toggleGroup(g.key)">
          <span class="dl-chevron" :class="{ 'is-open': expandedGroups.has(g.key) }">▸</span>
          <span class="dl-folder-icon">📁</span>
          <span class="dl-group-name" :title="g.name">{{ trTitle(g.name) }}</span>
          <span class="dl-group-meta">{{ g.tasks.length }} 个任务 · {{ g.done }}/{{ g.total }} 个文件</span>
          <n-progress
            type="line"
            class="dl-group-progress"
            :percentage="groupPercent(g)"
            :height="4"
            :show-indicator="false"
            :status="groupStatus(g)"
          />
        </div>

        <!-- 组内任务列表（父文件夹级） -->
        <div v-show="expandedGroups.has(g.key)" class="dl-group-tasks">
          <div
            v-for="task in g.tasks"
            :key="task.id"
            class="dl-task"
            :data-task-id="task.id"
            :class="{ 'dl-task-focus': task.id === focusTaskId }"
          >
            <div class="dl-task-header">
              <div class="dl-task-title" @click="toggleTask(task.id)">
                <span class="dl-chevron small" :class="{ 'is-open': expandedTasks.has(task.id) }">▸</span>
                <n-tag size="small" :type="statusType(task.status)" round>{{ statusText(task.status) }}</n-tag>
                <span class="dl-album" :title="task.album">{{ trTitle(task.album) }}</span>
                <span class="dl-count">{{ task.done }}/{{ task.total }}</span>
              </div>
              <div class="dl-task-actions" @click.stop>
                <n-button
                  v-if="task.status === 'running' || task.status === 'pending'"
                  size="tiny" quaternary @click="$emit('pause', task.id)"
                >暂停</n-button>
                <n-button
                  v-else-if="task.status === 'paused'"
                  size="tiny" quaternary type="primary" @click="$emit('resume', task.id)"
                >继续</n-button>
                <n-button
                  size="tiny" quaternary
                  title="在文件管理器中打开该任务的保存文件夹"
                  @click="$emit('open-folder', task)"
                >📂 打开文件夹</n-button>
                <n-button size="tiny" quaternary type="error" @click="$emit('remove', task.id)">删除</n-button>
              </div>
            </div>

            <n-progress
              type="line"
              :percentage="taskPercent(task)"
              :height="6"
              :show-indicator="false"
              style="margin: 6px 0"
            />

            <!-- 文件列表（子文件级，点击任务标题展开/收起） -->
            <div v-show="expandedTasks.has(task.id)" class="dl-files">
              <div v-for="f in task.files" :key="f.item_page" class="dl-file">
                <div class="dl-file-line">
                  <span class="dl-file-name" :title="f.filename">{{ trTitle(f.filename) }}</span>
                  <span class="dl-file-meta">
                    <span class="dl-file-size">{{ formatSize(f.size) }}</span>
                    <span v-if="f.speed" class="dl-file-speed">{{ formatSpeed(f.speed) }}</span>
                    <span class="dl-file-status" :class="'st-' + f.status">{{ fileStatusText(f.status) }}</span>
                    <button
                      class="dl-file-folder"
                      title="在文件管理器中定位该文件"
                      @click.stop="$emit('locate-file', f)"
                    >📂</button>
                  </span>
                </div>
                <n-progress
                  type="line"
                  :percentage="filePercent(f)"
                  :height="3"
                  :show-indicator="false"
                  :status="f.status === 'failed' ? 'error' : (f.status === 'completed' ? 'success' : 'default')"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, watch, nextTick, ref } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  tasks: { type: Array, default: () => [] },
  shutdownOn: { type: Boolean, default: false },
  focusTaskId: { type: String, default: null },
  // 翻译映射（与 RightPanel 的 translatedTitles 一致，无译文时直通）
  translatedTitles: { type: Object, default: () => ({}) },
})

const emit = defineEmits([
  'close', 'pause', 'resume', 'resume-all', 'cancel', 'remove', 'toggle-shutdown',
  'open-folder', 'locate-file',
])

// 展开状态（母组 / 任务两级，点击头部切换）
const expandedGroups = ref(new Set())
const expandedTasks = ref(new Set())
const seenTaskIds = ref(new Set())

function trTitle(text) {
  if (!text) return ''
  return props.translatedTitles[text] || text
}

// 任务分组：batch_parent_folder 相同的批量任务归入同一"母文件夹"组；
// 普通任务各自成组（组名 = 任务名）
const groups = computed(() => {
  const byParent = new Map()
  for (const t of props.tasks) {
    const parent = ((t.options || {}).batch_parent_folder || '').trim()
    if (parent) {
      if (!byParent.has(parent)) byParent.set(parent, [])
      byParent.get(parent).push(t)
    }
  }
  const result = []
  for (const [parent, tasks] of byParent) {
    result.push(makeGroup(`batch:${parent}`, parent, tasks))
  }
  for (const t of props.tasks) {
    const parent = ((t.options || {}).batch_parent_folder || '').trim()
    if (!parent) {
      result.push(makeGroup(`task:${t.id}`, t.album || '下载任务', [t]))
    }
  }
  return result
})

function makeGroup(key, name, tasks) {
  let done = 0, total = 0
  for (const t of tasks) {
    done += t.done || 0
    total += t.total || 0
  }
  return { key, name, tasks, done, total }
}

const hasPaused = computed(() => props.tasks.some(t => t.status === 'paused'))

const statsText = computed(() => {
  const running = props.tasks.filter(t => t.status === 'running' || t.status === 'pending').length
  const paused = props.tasks.filter(t => t.status === 'paused').length
  const done = props.tasks.filter(t => t.status === 'completed').length
  const parts = []
  if (running) parts.push(`${running} 个下载中`)
  if (paused) parts.push(`${paused} 个已暂停`)
  if (done) parts.push(`${done} 个已完成`)
  return parts.length ? parts.join(' · ') : '暂无进行中的任务'
})

// 新任务出现时默认展开（运行中任务所在组和任务本身）
watch(() => props.tasks, (tasks) => {
  for (const t of tasks) {
    if (!seenTaskIds.value.has(t.id)) {
      seenTaskIds.value.add(t.id)
      const parent = ((t.options || {}).batch_parent_folder || '').trim()
      expandedGroups.value.add(parent ? `batch:${parent}` : `task:${t.id}`)
      if (t.status === 'running' || t.status === 'pending' || t.status === 'paused') {
        expandedTasks.value.add(t.id)
      }
    }
  }
}, { immediate: true })

// 从悬浮窗/其他视图跳转过来时：展开并滚动定位到对应任务
watch(() => props.focusTaskId, async (id) => {
  if (!id) return
  const task = props.tasks.find(t => t.id === id)
  if (task) {
    const parent = ((task.options || {}).batch_parent_folder || '').trim()
    expandedGroups.value.add(parent ? `batch:${parent}` : `task:${task.id}`)
    expandedTasks.value.add(task.id)
  }
  await nextTick()
  const el = document.querySelector(`[data-task-id="${id}"]`)
  if (el) {
    el.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }
}, { immediate: true })

function toggleGroup(key) {
  const s = expandedGroups.value
  if (s.has(key)) s.delete(key)
  else s.add(key)
}

function toggleTask(taskId) {
  const s = expandedTasks.value
  if (s.has(taskId)) s.delete(taskId)
  else s.add(taskId)
}

function groupPercent(g) {
  const total = g.total || 1
  return Math.round(((g.done || 0) / total) * 100)
}

function groupStatus(g) {
  const anyFailed = g.tasks.some(t => t.status === 'failed')
  const allDone = g.tasks.every(t => t.status === 'completed')
  if (anyFailed) return 'error'
  if (allDone) return 'success'
  return 'default'
}

function statusType(status) {
  const map = {
    pending: 'info', running: 'info', paused: 'warning',
    completed: 'success', cancelled: 'default', failed: 'error',
  }
  return map[status] || 'default'
}

function statusText(status) {
  const map = {
    pending: '等待中', running: '下载中', paused: '已暂停',
    completed: '已完成', cancelled: '已取消', failed: '失败',
  }
  return map[status] || status
}

function fileStatusText(status) {
  const map = {
    pending: '等待', downloading: '下载中', paused: '暂停',
    completed: '完成', failed: '失败',
  }
  return map[status] || status
}

function taskPercent(task) {
  const total = task.total || 1
  const done = task.done || 0
  return Math.round((done / total) * 100)
}

function filePercent(f) {
  if (f.status === 'completed') return 100
  return f.completed || 0
}

function formatSpeed(bytesPerSecond) {
  if (!bytesPerSecond || bytesPerSecond <= 0) return ''
  return `${formatSize(bytesPerSecond)}/s`
}

function formatSize(bytes) {
  if (bytes == null) return '未知'
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}
</script>

<style scoped>
.dl-manager {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
  flex: 1;
  background: #1c1c21;
  overflow: hidden;
}

.dl-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid #2d2d33;
  background: #202026;
  flex-shrink: 0;
}

.dl-toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.dl-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #e0e0e6;
}

.dl-stats {
  font-size: 12px;
  color: #7f7f7f;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dl-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.dl-shutdown {
  display: flex;
  align-items: center;
  gap: 6px;
}

.dl-shutdown-label {
  font-size: 12px;
  color: #a0a0a8;
}

.dl-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
}

.dl-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #5f5f5f;
  font-size: 13px;
  gap: 8px;
}

.dl-empty-icon {
  font-size: 40px;
  opacity: 0.5;
}

.dl-empty-hint {
  font-size: 12px;
  color: #47474e;
}

/* ---- 母文件夹组 ---- */
.dl-group {
  background: #232329;
  border: 1px solid #2d2d33;
  border-radius: 8px;
  margin-bottom: 10px;
  overflow: hidden;
}

.dl-group-focus {
  border-color: #63e2b7;
  box-shadow: 0 0 0 1px rgba(99, 226, 183, 0.4);
}

.dl-group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  user-select: none;
  background: #26262c;
}

.dl-group-header:hover {
  background: #2b2b32;
}

.dl-chevron {
  display: inline-block;
  color: #7f7f7f;
  font-size: 12px;
  transition: transform 0.15s ease;
  flex-shrink: 0;
}

.dl-chevron.is-open {
  transform: rotate(90deg);
}

.dl-chevron.small {
  font-size: 10px;
}

.dl-folder-icon {
  font-size: 15px;
  flex-shrink: 0;
}

.dl-group-name {
  font-size: 13px;
  font-weight: 600;
  color: #e0e0e6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 320px;
}

.dl-group-meta {
  font-size: 12px;
  color: #7f7f7f;
  flex-shrink: 0;
}

.dl-group-progress {
  flex: 1;
  min-width: 60px;
  max-width: 180px;
}

.dl-group-tasks {
  padding: 8px 10px 10px;
  border-top: 1px solid #2a2a30;
}

/* ---- 任务（父文件夹） ---- */
.dl-task {
  background: #26262b;
  border: 1px solid #2d2d33;
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 8px;
}

.dl-task:last-child {
  margin-bottom: 0;
}

.dl-task-focus {
  border-color: #63e2b7;
  box-shadow: 0 0 0 1px rgba(99, 226, 183, 0.4);
}

.dl-task-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.dl-task-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  cursor: pointer;
  user-select: none;
}

.dl-album {
  font-size: 13px;
  color: #e0e0e6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 260px;
}

.dl-count {
  font-size: 12px;
  color: #7f7f7f;
  flex-shrink: 0;
}

.dl-task-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

/* ---- 文件（子文件） ---- */
.dl-files {
  margin-top: 4px;
  max-height: 260px;
  overflow-y: auto;
}

.dl-file {
  padding: 4px 0;
}

.dl-file-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.dl-file-name {
  font-size: 12px;
  color: #a0a0a8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.dl-file-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.dl-file-size {
  font-size: 11px;
  color: #7f7f7f;
  font-family: monospace;
}

.dl-file-speed {
  font-size: 11px;
  color: #63e2b7;
  font-family: monospace;
}

.dl-file-status {
  font-size: 11px;
  color: #7f7f7f;
}

.dl-file-folder {
  border: none;
  background: transparent;
  color: #7f7f7f;
  font-size: 13px;
  cursor: pointer;
  padding: 0 2px;
  line-height: 1;
}

.dl-file-folder:hover {
  color: #63e2b7;
}

.st-downloading { color: #63e2b7; }
.st-completed { color: #18a058; }
.st-failed { color: #d03050; }
.st-paused { color: #f0a020; }
</style>
