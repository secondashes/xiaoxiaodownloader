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
        <!-- 同时删除本地文件：对所有删除操作生效（单个删除 / 清除所有任务）；
             首次勾选后执行删除会额外弹一次确认（确认后记入 localStorage 不再重复询问） -->
        <n-checkbox size="small" class="dl-del-files"
                    :checked="deleteFiles"
                    @update:checked="v => (deleteFiles = v)">同时删除本地文件</n-checkbox>
        <n-button size="small" quaternary type="error" :disabled="!tasks.length"
                  title="清除列表中的全部下载任务"
                  @click="onClearAll">清除所有任务</n-button>
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
                <span class="dl-task-created" :title="'任务创建于 ' + formatDateTime(task.created_at)">{{ formatDateTime(task.created_at) }}</span>
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
                  v-if="task.status === 'failed' || (task.failed || 0) > 0"
                  size="tiny" quaternary type="warning"
                  title="重试该任务的失败文件（失败项重置为待下载并重新开始）"
                  @click="$emit('retry', task.id)"
                >↻ 重试</n-button>
                <n-button
                  size="tiny" quaternary
                  title="在文件管理器中打开该任务的保存文件夹"
                  @click="$emit('open-folder', task)"
                >📂 打开文件夹</n-button>
                <n-button
                  v-if="task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled'"
                  size="tiny" quaternary type="warning"
                  title="把该任务的文件夹整体移动到其他位置（迁移/集中资源）"
                  @click="moveTaskFolder(task)"
                >📁 移动文件夹</n-button>
                <n-button size="tiny" quaternary type="error" @click="onDeleteTask(task.id)">删除</n-button>
              </div>
            </div>

            <!-- 迅雷式详情行：创建时间 / 大小 / 速度 / 剩余时间 / 状态明细 -->
            <div class="dl-task-info">
              <span title="任务创建时间">🕐 {{ formatDateTime(task.created_at) }}</span>
              <span v-if="taskSize(task)" title="总大小（按已完成比例估算已下载量）">📦 {{ fmtDone(task) }} / {{ formatSize(taskSize(task)) }}</span>
              <span v-if="taskSpeed(task)" class="dl-info-speed" title="当前总速度（所有下载中文件合计）">⚡ {{ formatSpeed(taskSpeed(task)) }}</span>
              <span v-if="taskEta(task)" title="按当前速度估算的剩余时间">⏳ 剩余约 {{ taskEta(task) }}</span>
              <span class="dl-info-failed" v-if="(task.failed || 0) > 0" title="失败文件数">⚠ 失败 {{ task.failed }}</span>
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
                    <span v-if="f.hls_total" class="dl-file-seg"
                          :title="'流媒体任务：分片下载完成后自动合并为 MP4'">
                      {{ f.hls_phase === 'merging' ? '合并中…' : `分片 ${f.hls_done || 0}/${f.hls_total}` }}
                    </span>
                    <span class="dl-file-size">{{ formatSize(f.size) }}</span>
                    <span v-if="f.speed" class="dl-file-speed">{{ formatSpeed(f.speed) }}</span>
                    <span v-if="f.finished_at" class="dl-file-time" :title="'完成于 ' + formatDateTime(f.finished_at)">{{ formatClock(f.finished_at) }}</span>
                    <span class="dl-file-status" :class="'st-' + f.status">{{ fileStatusText(f.status) }}</span>
                    <button
                      v-if="f.status === 'failed'"
                      class="dl-file-retry"
                      title="重试该文件（其他文件不受影响）"
                      @click.stop="$emit('retry-file', { taskId: task.id, itemPage: f.item_page })"
                    >↻</button>
                    <button
                      class="dl-file-folder"
                      title="在文件管理器中定位该文件"
                      @click.stop="$emit('locate-file', { file: f, task })"
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
import { useDialog } from 'naive-ui'

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
  'open-folder', 'locate-file', 'retry', 'retry-file', 'clear-all',
])

// ---------- 删除时同步删除本地文件 ----------
// 勾选后对所有删除操作生效（单个删除 / 清除所有任务）；首次执行额外弹一次确认，
// 确认后记入 localStorage（delete_files_confirmed），之后不再重复询问
const dialog = useDialog()
const deleteFiles = ref(false)
const DELETE_FILES_CONFIRM_KEY = 'delete_files_confirmed'

function _deleteFilesConfirmed() {
  try {
    return localStorage.getItem(DELETE_FILES_CONFIRM_KEY) === '1'
  } catch {
    return false
  }
}

function requestDelete(run) {
  if (!deleteFiles.value) {
    run(false)
    return
  }
  if (_deleteFilesConfirmed()) {
    run(true)
    return
  }
  dialog.warning({
    title: '确认同时删除本地文件？',
    content: '将把这些任务已下载到磁盘的文件和文件夹一并删除（不可恢复）。'
      + '确认一次后，之后勾选「同时删除本地文件」执行删除时不再询问。',
    positiveText: '确认删除，不再提醒',
    negativeText: '取消',
    onPositiveClick: () => {
      try {
        localStorage.setItem(DELETE_FILES_CONFIRM_KEY, '1')
      } catch {}
      run(true)
    },
  })
}

async function moveTaskFolder(task) {
  if (!window.api || !window.api.pickDirectory) return
  const pick = await window.api.pickDirectory()
  if (!pick || pick.ok === false || !pick.path) return
  window.api.sendCommand({
    cmd: 'move_task_folder',
    task_id: task.id,
    dest_dir: pick.path,
  })
}

function onDeleteTask(taskId) {
  requestDelete(df => emit('remove', taskId, df))
}

function onClearAll() {
  requestDelete(df => emit('clear-all', df))
}

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

// ---------- 迅雷式详情（创建时间/大小/速度/剩余时间） ----------
function formatDateTime(ts) {
  if (!ts) return '—'
  const d = new Date(typeof ts === 'number' && ts < 1e12 ? ts * 1000 : ts)  // 后端秒 / 前端毫秒
  if (isNaN(d.getTime())) return '—'
  const p2 = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`
}

function formatClock(ts) {
  const dt = typeof ts === 'number' && ts < 1e12 ? ts * 1000 : ts
  const d = new Date(dt)
  if (isNaN(d.getTime())) return ''
  const p2 = n => String(n).padStart(2, '0')
  return `${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`
}

function taskSize(task) {
  return (task.files || []).reduce((acc, f) => acc + (Number(f.size) || 0), 0)
}

function taskDoneBytes(task) {
  // 按各文件完成百分比估算已下载字节；流媒体任务直接用后端报的分片累计字节
  return (task.files || []).reduce((acc, f) => {
    const realBytes = Number(f.completed_bytes) || 0
    if (realBytes > 0) return acc + realBytes
    const sz = Number(f.size) || 0
    if (!sz) return acc
    const pct = Math.min(100, Math.max(0, Number(f.completed) || (f.status === 'completed' ? 100 : 0)))
    return acc + sz * pct / 100
  }, 0)
}

function taskSpeed(task) {
  return (task.files || []).reduce((acc, f) => acc + (Number(f.speed) || 0), 0)
}

function fmtDone(task) {
  return formatSize(taskDoneBytes(task))
}

function taskEta(task) {
  const speed = taskSpeed(task)
  if (speed <= 0) return ''
  const remain = taskSize(task) - taskDoneBytes(task)
  if (remain <= 0) return ''
  const sec = Math.round(remain / speed)
  if (sec < 60) return `${sec} 秒`
  if (sec < 3600) return `${Math.round(sec / 60)} 分钟`
  return `${(sec / 3600).toFixed(1)} 小时`
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
/* 进度条平滑稳定增长：宽度变化加过渡，字节级高频更新不再跳动 */
:deep(.n-progress-graph-line-indicator) {
  transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}

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

.dl-del-files {
  margin: 0 4px;
  white-space: nowrap;
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

/* 流媒体任务的分片进度（一个视频几百片，进度单位不是字节） */
.dl-file-seg {
  font-size: 11px;
  color: #f0a020;
  font-family: monospace;
}

.dl-task-created { color: #8a8a92; font-size: 11px; }
.dl-task-info {
  display: flex; gap: 14px; flex-wrap: wrap; padding: 2px 0 4px;
  font-size: 11.5px; color: #8a8a92;
}
.dl-info-speed { color: #63e2b7; }
.dl-info-failed { color: #e88080; }
.dl-file-time { color: #8a8a92; }
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

/* 单文件重试按钮（仅失败文件显示） */
.dl-file-retry {
  border: none;
  background: transparent;
  color: #d03050;
  font-size: 13px;
  cursor: pointer;
  padding: 0 2px;
  line-height: 1;
}

.dl-file-retry:hover {
  color: #f0a020;
}

.st-downloading { color: #63e2b7; }
.st-completed { color: #18a058; }
.st-failed { color: #d03050; }
.st-paused { color: #f0a020; }
</style>
