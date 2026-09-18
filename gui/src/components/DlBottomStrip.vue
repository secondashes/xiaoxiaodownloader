<template>
  <div class="bottom-area">
    <n-tabs type="line" size="small" :value="activeTab" @update:value="activeTab = $event">
      <n-tab-pane name="progress" tab="下载进度">
        <div class="progress-list">
          <template v-if="Object.keys(downloadProgress).length === 0">
            <div class="empty-tab">暂无下载任务</div>
          </template>
          <div
            v-for="(item, filename) in downloadProgress"
            :key="filename"
            class="progress-item"
          >
            <div class="progress-item-header">
              <span class="progress-filename" :title="filename">{{ filename }}</span>
              <div class="progress-meta">
                <span
                  v-if="item.status === 'downloading' && item.speed > 0"
                  class="progress-speed"
                >{{ formatSpeed(item.speed) }}</span>
                <n-tag size="tiny" :type="statusTagType(item.status)" round>{{ statusText(item.status) }}</n-tag>
              </div>
            </div>
            <n-progress
              type="line"
              :percentage="item.completed || 0"
              :status="progressStatus(item.status)"
              :show-indicator="false"
              :height="6"
            />
          </div>
        </div>
      </n-tab-pane>
      <n-tab-pane name="logs" tab="日志">
        <div class="log-list">
          <div v-for="(log, i) in logs" :key="i" class="log-item">
            <span class="log-time">{{ log.time }}</span>
            <n-tag size="tiny" :type="logTagType(log.type)" round>{{ log.type }}</n-tag>
            <span class="log-message">{{ log.message }}</span>
          </div>
          <div v-if="logs.length === 0" class="empty-tab">暂无日志</div>
        </div>
      </n-tab-pane>
      <n-tab-pane name="history" tab="历史">
        <div class="history-list">
          <div v-for="item in history" :key="item.id" class="history-item">
            <div class="history-main">
              <span class="history-name" :title="item.path">{{ item.filename }}</span>
              <span class="history-meta">{{ item.time }} · {{ formatSize(item.size) }}</span>
            </div>
            <div class="history-actions">
              <n-button size="tiny" quaternary @click="$emit('open-file', item.path)">打开</n-button>
              <n-button size="tiny" quaternary @click="$emit('show-folder', item.path)">文件夹</n-button>
              <n-button size="tiny" quaternary type="warning" @click="handleDeleteHistory(item, false)">删记录</n-button>
              <n-button size="tiny" quaternary type="error" @click="handleDeleteHistory(item, true)">删文件</n-button>
            </div>
          </div>
          <div v-if="history.length === 0" class="empty-tab">暂无历史任务</div>
        </div>
      </n-tab-pane>
    </n-tabs>

    <!-- 右侧：实时下载（固定列表不滚动：全部下载中文件，各带完整进度条 + 速度） -->
    <div class="dl-ticker">
      <div class="dl-ticker-header">
        <span class="dl-ticker-title">实时下载（{{ tickerItems.length }}）</span>
        <span v-if="tickerTotalSpeedText" class="dl-ticker-total">{{ tickerTotalSpeedText }}</span>
      </div>
      <div class="dl-ticker-viewport">
        <div v-if="tickerItems.length === 0" class="dl-ticker-empty">暂无下载任务</div>
        <div v-else class="dl-ticker-list">
          <div v-for="item in tickerItems" :key="item.name" class="dl-ticker-item">
            <div class="dl-ticker-row">
              <span class="dl-ticker-name" :title="item.name">{{ item.name }}</span>
              <span class="dl-ticker-pct">{{ item.percent }}%</span>
              <span class="dl-ticker-speed">{{ item.speedText }}</span>
            </div>
            <n-progress
              type="line"
              :percentage="item.percent"
              :show-indicator="false"
              :height="4"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
//
// 下载底部条（下载进度 / 日志 / 历史 + 实时下载滚动栏）独立小组件。
//
// 性能（2026-09-13）：此前这块模板内嵌在 RightPanel 巨型组件里，模板直接引用
// downloadProgress/logs/history——每个 file_progress 事件（每文件 0.3s 一个）
// 都会让整个 RightPanel（全站视图）全量重渲染，下载期间切换模块明显卡顿。
// 拆出后高频更新只重渲染本组件，RightPanel 不再受影响。
//
import { ref, computed, watch } from 'vue'

const props = defineProps({
  downloadProgress: { type: Object, required: true },
  logs: { type: Array, required: true },
  history: { type: Array, required: true },
  downloading: { type: Boolean, default: false },
})

const emit = defineEmits(['open-file', 'show-folder', 'delete-history'])

const activeTab = ref('logs')
// 下载开始时切换到进度标签
watch(() => props.downloading, (downloading) => {
  if (downloading) activeTab.value = 'progress'
})

// ============================
// 工具函数
// ============================
function formatSize(bytes) {
  if (bytes == null) return '未知'
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

function formatSpeed(bytesPerSecond) {
  if (!bytesPerSecond || bytesPerSecond <= 0) return ''
  return `${formatSize(bytesPerSecond)}/s`
}

// ============================
// 右侧实时下载滚动栏（下载中的文件：文件名 + 进度 + 速度）
// ============================
const tickerItems = computed(() => {
  const items = []
  for (const [name, p] of Object.entries(props.downloadProgress || {})) {
    if (p && p.status === 'downloading') {
      items.push({
        name,
        percent: Math.round(p.completed || 0),
        speedText: p.speed > 0 ? formatSpeed(p.speed) : '',
      })
    }
  }
  return items
})

// 所有下载中文件的合计速度
const tickerTotalSpeedText = computed(() => {
  let total = 0
  for (const p of Object.values(props.downloadProgress || {})) {
    if (p && p.status === 'downloading') total += p.speed || 0
  }
  return total > 0 ? formatSpeed(total) : ''
})

function handleDeleteHistory(item, deleteFile) {
  const msg = deleteFile
    ? `确定删除记录和文件「${item.filename}」吗？此操作不可恢复。`
    : `确定删除记录「${item.filename}」吗？`
  if (window.confirm(msg)) {
    emit('delete-history', item.id, deleteFile)
  }
}

function statusTagType(status) {
  const map = { downloading: 'info', completed: 'success', failed: 'error' }
  return map[status] || 'default'
}

function statusText(status) {
  const map = { downloading: '下载中', completed: '完成', failed: '失败' }
  return map[status] || status
}

function progressStatus(status) {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'error'
  return 'default'
}

function logTagType(type) {
  const map = {
    '错误': 'error',
    '失败': 'error',
    '完成': 'success',
    '解析': 'info',
    '下载': 'info',
  }
  return map[type] || 'default'
}
</script>

<style scoped>
.bottom-area {
  height: 200px;
  min-height: 200px;
  border-top: 1px solid #2d2d33;
  background: #1e1e22;
  padding: 0 16px;
  overflow: hidden;
  display: flex;
  align-items: stretch;
  gap: 12px;
}

/* 底部 tabs 限宽，右侧让位给实时下载滚动栏 */
.bottom-area > :deep(.n-tabs) {
  flex: 1;
  min-width: 0;
}

.progress-list {
  max-height: 150px;
  overflow-y: auto;
  padding: 4px 0;
}

.progress-item {
  margin-bottom: 8px;
}

.progress-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 3px;
}

.progress-filename {
  font-size: 12px;
  color: #a0a0a8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 80%;
}

.progress-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.progress-speed {
  font-size: 11px;
  color: #63e2b7;
  font-family: monospace;
}

.log-list {
  max-height: 150px;
  overflow-y: auto;
  padding: 4px 0;
}

.log-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
  font-size: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
}

.log-time {
  color: #5f5f5f;
  font-family: monospace;
  min-width: 60px;
}

.log-message {
  color: #a0a0a8;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-tab {
  text-align: center;
  color: #5f5f5f;
  padding: 30px 0;
  font-size: 12px;
}

.history-list {
  max-height: 150px;
  overflow-y: auto;
  padding: 4px 0;
}

.history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
}

.history-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.history-name {
  font-size: 12px;
  color: #e0e0e6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-meta {
  font-size: 11px;
  color: #5f5f5f;
}

.history-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

/* ============ 右侧实时下载滚动栏 ============ */
.dl-ticker {
  width: 300px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-left: 1px solid #2d2d33;
  padding: 6px 0 6px 12px;
  overflow: hidden;
}

.dl-ticker-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  margin-bottom: 4px;
}

.dl-ticker-title {
  font-size: 12px;
  font-weight: 600;
  color: #e0e0e6;
}

.dl-ticker-total {
  font-size: 11px;
  color: #63e2b7;
  font-family: 'Cascadia Code', Consolas, monospace;
}

.dl-ticker-viewport {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  position: relative;
}

.dl-ticker-empty {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: #6c6c75;
}

.dl-ticker-list {
  position: absolute;
  inset: 0;
  overflow-y: auto;
}

.dl-ticker-item {
  padding: 4px 0;
  font-size: 11px;
}

.dl-ticker-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
}

.dl-ticker-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #c9c9d1;
}

.dl-ticker-pct {
  color: #63e2b7;
  font-family: 'Cascadia Code', Consolas, monospace;
  min-width: 34px;
  text-align: right;
}

.dl-ticker-speed {
  color: #63e2b7;
  font-family: 'Cascadia Code', Consolas, monospace;
  min-width: 62px;
  text-align: right;
}

/* 日间模式 */
:global(html.light-mode) .bottom-area {
  border-top-color: #e5e6eb;
  background: #f7f8fa;
}
:global(html.light-mode) .dl-ticker {
  border-left-color: #e5e6eb;
}
:global(html.light-mode) .dl-ticker-title {
  color: #1f2329;
}
:global(html.light-mode) .dl-ticker-name {
  color: #5a5c66;
}
:global(html.light-mode) .dl-ticker-empty {
  color: #8a8d99;
}
</style>
