<template>
  <div class="bt-wrap">
    <!-- 顶栏：标题 + 自动接管开关 + 状态说明 -->
    <div class="bt-topbar">
      <div class="bt-title">🧲 BT 下载</div>
      <div class="bt-topbar-right">
        <span class="bt-auto-label">磁力链接自动接管</span>
        <n-switch
          size="small"
          :value="autoTakeover"
          title="开启后，磁力站页面点击磁力链接将跳过确认弹窗直接开始下载"
          @update:value="onToggleAutoTakeover"
        />
      </div>
      <div class="bt-hint">粘贴磁力链接 / 拖入 .torrent 种子即可下载 · 进度与「下载管理」实时同步</div>
    </div>

    <!-- 输入区：批量磁力 / 种子地址 -->
    <div class="bt-card">
      <div class="bt-card-title">批量提交</div>
      <n-input
        v-model:value="magnetText"
        type="textarea"
        :rows="6"
        placeholder="每行一条磁力链接（magnet:?xt=urn:btih:…）或 .torrent 种子地址，支持一次粘贴多行批量下载"
      />
      <div class="bt-card-actions">
        <n-button type="primary" :disabled="!magnetText.trim()" @click="submitBatch">批量下载</n-button>
      </div>
    </div>

    <!-- 拖拽区：本地 .torrent 种子文件 -->
    <div
      class="bt-drop"
      :class="{ 'bt-drop-over': dragOver }"
      @dragover.prevent="dragOver = true"
      @dragleave.prevent="dragOver = false"
      @drop.prevent="onDrop"
    >
      <div class="bt-drop-icon">🧲</div>
      <div class="bt-drop-text">把 .torrent 种子文件拖到这里</div>
      <div class="bt-drop-sub">可一次拖入多个种子文件，自动解析并加入下载</div>
    </div>

    <!-- 任务列表：album_id 以 bt: 开头的下载任务 -->
    <div class="bt-card">
      <div class="bt-card-title">BT 任务（{{ btTasks.length }}）</div>
      <div v-if="!btTasks.length" class="bt-empty">暂无 BT 任务——粘贴磁力链接或拖入 .torrent 种子开始</div>
      <div v-for="t in btTasks" :key="t.id" class="bt-task">
        <div class="bt-task-main">
          <div class="bt-task-name" :title="taskName(t)">{{ taskName(t) }}</div>
          <n-tag size="small" :type="statusType(t.status)" :bordered="false">{{ statusLabel(t.status) }}</n-tag>
        </div>
        <n-progress
          type="line"
          :percentage="taskPct(t)"
          :height="6"
          :show-indicator="false"
          :status="t.status === 'failed' ? 'error' : (t.status === 'completed' ? 'success' : 'default')"
          class="bt-task-bar"
        />
        <div class="bt-task-foot">
          <span class="bt-task-pct">{{ taskPct(t) }}%</span>
          <span class="bt-task-files" :title="taskFileList(t)">{{ taskFileSummary(t) }}</span>
          <span class="bt-task-spacer" />
          <n-button
            v-if="t.status === 'completed'"
            size="tiny" quaternary
            title="在文件管理器中打开该任务的保存位置"
            @click="openTaskFolder(t)"
          >📂 打开文件夹</n-button>
          <n-button
            size="tiny" quaternary type="warning"
            title="删除该任务记录（不删除已下载的文件）"
            @click="removeTask(t)"
          >删除</n-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { NSwitch, NInput, NButton, NTag, NProgress, useMessage } from 'naive-ui'

const message = useMessage()

// ---------- 顶栏：自动接管开关（localStorage 持久化，默认关） ----------
// 磁力站页面点击磁力链接时，主窗口/嗅探窗的确认弹窗读取该偏好：
// 开启 = 跳过确认直接提交 bt_download（跨窗口同源 localStorage 共享）
const autoTakeover = ref(localStorage.getItem('bt_auto_takeover') === '1')
function onToggleAutoTakeover(v) {
  autoTakeover.value = !!v
  try { localStorage.setItem('bt_auto_takeover', v ? '1' : '0') } catch (e) { /* 忽略 */ }
  message.info(v ? '已开启自动接管：点击磁力链接将直接开始下载' : '已关闭自动接管：点击磁力链接会先弹窗确认')
}

// ---------- 输入区：批量磁力 / .torrent 种子地址 ----------
const magnetText = ref('')
function submitBatch() {
  const lines = magnetText.value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
  if (!lines.length) {
    message.warning('请先粘贴磁力链接或 .torrent 种子地址')
    return
  }
  for (const line of lines) {
    window.api && window.api.sendCommand({ cmd: 'bt_download', url: line, album: 'BT 下载' })
  }
  message.success(`已提交 ${lines.length} 条 BT 任务`)
  magnetText.value = ''
}

// ---------- 拖拽区：本地 .torrent → base64 → bt_download_file ----------
const dragOver = ref(false)
function onDrop(e) {
  dragOver.value = false
  const files = Array.from((e.dataTransfer && e.dataTransfer.files) || [])
  const torrents = files.filter((f) => /\.torrent$/i.test(f.name || ''))
  if (!torrents.length) {
    message.warning('未发现 .torrent 种子文件')
    return
  }
  for (const f of torrents) submitTorrentFile(f)
}

async function submitTorrentFile(file) {
  try {
    const buf = await file.arrayBuffer()
    const bytes = new Uint8Array(buf)
    // Uint8Array 分块构造二进制字符串再 btoa（一次性 apply 大数组会爆栈）
    let bin = ''
    const CHUNK = 0x8000
    for (let i = 0; i < bytes.length; i += CHUNK) {
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK))
    }
    const b64 = btoa(bin)
    window.api && window.api.sendCommand({ cmd: 'bt_download_file', b64, album: 'BT 下载' })
    message.success(`种子「${file.name}」已提交`)
  } catch (err) {
    message.error(`读取种子文件失败: ${(err && err.message) || err}`)
  }
}

// ---------- 任务列表：tasks_snapshot 过滤 album_id 以 bt: 开头 ----------
const btTasks = ref([])
const STATUS_LABELS = {
  pending: '待开始',
  downloading: '下载中',
  running: '下载中',
  paused: '已暂停',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}
function statusLabel(s) { return STATUS_LABELS[s] || (s || '未知') }
function statusType(s) {
  if (s === 'completed') return 'success'
  if (s === 'failed') return 'error'
  if (s === 'paused' || s === 'cancelled') return 'warning'
  return 'info'
}
function taskName(t) {
  return (t.files && t.files[0] && t.files[0].filename) || t.album || t.album_id || 'BT 任务'
}
function taskPct(t) {
  const c = t.files && t.files[0] ? Number(t.files[0].completed) || 0 : 0
  return Math.max(0, Math.min(100, Math.round(c)))
}
function taskFileSummary(t) {
  const files = t.files || []
  if (!files.length) return ''
  const names = files.map((f) => f.filename).filter(Boolean)
  if (names.length === 1) return names[0]
  return `${names[0]} 等 ${names.length} 个文件`
}
function taskFileList(t) {
  return (t.files || []).map((f) => f.filename).filter(Boolean).join('\n') || ''
}

let snapLogged = false
function applySnapshot(ev) {
  // 快照数组在 ev.tasks（兜底：事件顶层即数组）；console 打印一次确认结构
  const list = Array.isArray(ev && ev.tasks) ? ev.tasks : (Array.isArray(ev) ? ev : [])
  if (!snapLogged) {
    snapLogged = true
    try {
      console.log('[BT] tasks_snapshot 首包 · 顶层键:', ev && Object.keys(ev), '· 首任务样例:', list[0] || null)
    } catch (e) { /* 忽略 */ }
  }
  btTasks.value = list.filter((t) => String((t && t.album_id) || '').startsWith('bt:'))
}

function openTaskFolder(t) {
  const fp = t.files && t.files[0] && t.files[0]._final_path
  if (fp && window.api && window.api.showInFolder) {
    window.api.showInFolder(fp)
    return
  }
  if (t.save_dir && window.api && window.api.openPath) {
    window.api.openPath(t.save_dir)
    return
  }
  message.warning('暂无保存位置')
}

function removeTask(t) {
  window.api && window.api.sendCommand({ cmd: 'remove_task', task_id: t.id, delete_files: false })
  btTasks.value = btTasks.value.filter((x) => x.id !== t.id)
  message.success('已删除该任务记录（文件保留）')
}

// ---------- 后端事件订阅 ----------
let offEvent = null
function handleEvent(ev) {
  const name = (ev && ev.event) || ''
  if (name === 'tasks_snapshot') {
    applySnapshot(ev)
  } else if (name === 'bt_result') {
    if (ev.ok) message.success(ev.message || 'BT 任务已提交')
    else message.error(ev.message || 'BT 任务提交失败')
  }
}

onMounted(() => {
  if (window.api && window.api.onEvent) offEvent = window.api.onEvent(handleEvent)
})
onBeforeUnmount(() => {
  if (offEvent) offEvent()
  offEvent = null
})
</script>

<style scoped>
.bt-wrap {
  height: 100%;
  box-sizing: border-box;
  padding: 18px 22px 28px;
  background: #16161a;
  color: #dcdce4;
  overflow-y: auto;
}
.bt-topbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 14px;
  margin-bottom: 16px;
}
.bt-title {
  font-size: 20px;
  font-weight: 700;
  color: #f2f2f7;
  white-space: nowrap;
}
.bt-topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}
.bt-auto-label {
  font-size: 12px;
  color: #9a9aa8;
}
.bt-hint {
  flex-basis: 100%;
  font-size: 12px;
  color: #6f6f80;
}
.bt-card {
  background: #1d1d24;
  border: 1px solid #2a2a33;
  border-radius: 10px;
  padding: 14px 16px;
  margin-bottom: 14px;
}
.bt-card-title {
  font-size: 13px;
  font-weight: 600;
  color: #b9b9c8;
  margin-bottom: 10px;
}
.bt-card-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 10px;
}
.bt-drop {
  border: 2px dashed #3a3a48;
  border-radius: 10px;
  padding: 22px 16px;
  text-align: center;
  margin-bottom: 14px;
  background: #1a1a21;
  transition: border-color 0.15s, background 0.15s;
  cursor: pointer;
}
.bt-drop-over {
  border-color: #63e2b7;
  background: #1f2a26;
}
.bt-drop-icon {
  font-size: 26px;
  margin-bottom: 6px;
}
.bt-drop-text {
  font-size: 14px;
  color: #dcdce4;
}
.bt-drop-sub {
  font-size: 12px;
  color: #6f6f80;
  margin-top: 4px;
}
.bt-empty {
  font-size: 13px;
  color: #6f6f80;
  text-align: center;
  padding: 18px 0;
}
.bt-task {
  padding: 10px 2px;
  border-bottom: 1px solid #26262e;
}
.bt-task:last-child {
  border-bottom: none;
}
.bt-task-main {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}
.bt-task-name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: #e8e8f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bt-task-bar {
  margin-bottom: 6px;
}
.bt-task-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: #9a9aa8;
}
.bt-task-pct {
  min-width: 42px;
  color: #63e2b7;
  font-variant-numeric: tabular-nums;
}
.bt-task-files {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bt-task-spacer {
  flex: 0;
}
</style>
