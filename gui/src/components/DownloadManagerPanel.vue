<template>
  <div v-if="visible" class="dl-overlay" @click.self="$emit('close')">
    <div class="dl-panel" :style="panelStyle">
      <!-- 头部 -->
      <div class="dl-header">
        <div class="dl-title">
          <n-icon size="18"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></svg></n-icon>
          <span>下载管理</span>
        </div>
        <div class="dl-header-actions">
          <n-button v-if="hasPaused" size="small" quaternary @click="$emit('resume-all')">全部继续</n-button>
          <div class="dl-shutdown">
            <n-switch size="small" :value="shutdownOn" @update:value="v => $emit('toggle-shutdown', v)" />
            <span class="dl-shutdown-label">下载完关机</span>
          </div>
          <n-button size="small" quaternary @click="$emit('close')">关闭</n-button>
        </div>
      </div>

      <!-- 任务列表 -->
      <div class="dl-body">
        <div v-if="tasks.length === 0" class="dl-empty">
          <div class="dl-empty-icon">⬇️</div>
          <div>暂无下载任务</div>
        </div>

        <div v-for="task in tasks" :key="task.id" class="dl-task" :data-task-id="task.id" :class="{ 'dl-task-focus': task.id === focusTaskId }">
          <div class="dl-task-header">
            <div class="dl-task-title">
              <n-tag size="small" :type="statusType(task.status)" round>{{ statusText(task.status) }}</n-tag>
              <span class="dl-album" :title="task.album">{{ task.album }}</span>
              <span class="dl-count">{{ task.done }}/{{ task.total }}</span>
            </div>
            <div class="dl-task-actions">
              <n-button
                v-if="task.status === 'running'"
                size="tiny" quaternary @click="$emit('pause', task.id)"
              >暂停</n-button>
              <n-button
                v-else-if="task.status === 'paused'"
                size="tiny" quaternary type="primary" @click="$emit('resume', task.id)"
              >继续</n-button>
              <n-button
                v-if="['running', 'paused', 'pending'].includes(task.status)"
                size="tiny" quaternary type="warning" @click="$emit('cancel', task.id)"
              >取消</n-button>
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

          <!-- 文件列表 -->
          <div class="dl-files">
            <div v-for="f in task.files" :key="f.item_page" class="dl-file">
              <div class="dl-file-line">
                <span class="dl-file-name" :title="f.filename">{{ f.filename }}</span>
                <span class="dl-file-meta">
                  <span class="dl-file-size">{{ formatSize(f.size) }}</span>
                  <span v-if="f.speed" class="dl-file-speed">{{ formatSpeed(f.speed) }}</span>
                  <span class="dl-file-status" :class="'st-' + f.status">{{ fileStatusText(f.status) }}</span>
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
</template>

<script setup>
import { computed, watch, nextTick } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  tasks: { type: Array, default: () => [] },
  shutdownOn: { type: Boolean, default: false },
  anchor: { type: Object, default: null },
  focusTaskId: { type: String, default: null },
})

const emit = defineEmits([
  'close', 'pause', 'resume', 'resume-all', 'cancel', 'remove', 'toggle-shutdown',
])

const hasPaused = computed(() => props.tasks.some(t => t.status === 'paused'))

// 从下载管理窗口跳转过来时，滚动到对应任务并高亮
watch(() => props.focusTaskId, async (id) => {
  if (!id) return
  await nextTick()
  const el = document.querySelector(`[data-task-id="${id}"]`)
  if (el) {
    el.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }
}, { immediate: true })

// 双击悬浮窗打开时，面板定位在悬浮窗附近；否则居中
const panelStyle = computed(() => {
  if (!props.anchor) return {}
  const vw = window.innerWidth || 1200
  const vh = window.innerHeight || 800
  const x = Math.max(8, Math.min(props.anchor.x, vw - 740))
  const y = Math.max(8, Math.min(props.anchor.y, vh - 520))
  return { position: 'absolute', left: x + 'px', top: y + 'px' }
})

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
.dl-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
}

.dl-panel {
  width: 720px;
  max-width: 92vw;
  height: 80vh;
  background: rgba(30, 30, 34, 0.92);
  border: 1px solid #3a3a44;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(8px);
}

.dl-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid #2d2d33;
}

.dl-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #e0e0e6;
}

.dl-header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
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
  padding: 12px 16px;
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

.dl-task {
  background: #26262b;
  border: 1px solid #2d2d33;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 10px;
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
}

.dl-album {
  font-size: 13px;
  color: #e0e0e6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 280px;
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

.dl-files {
  margin-top: 4px;
  max-height: 200px;
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

.st-downloading { color: #63e2b7; }
.st-completed { color: #18a058; }
.st-failed { color: #d03050; }
.st-paused { color: #f0a020; }
</style>
