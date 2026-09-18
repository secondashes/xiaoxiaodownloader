<template>
  <!-- 手动抓取（资源嗅探）主体：左=内置浏览器（persist:sniffer 会话），右=实时捕获的媒体资源列表。
       复刻 res-downloader：浏览即抓取；提交走后端 sniff_download 通用下载管线。
       必须挂在 SnifferWindow.vue 的 Provider 内（本组件使用 useMessage）。 -->
  <div class="sniff-root">
    <!-- 顶部工具栏：标题行（里世界特色：品牌+监听状态）与筛选行（表世界移植能力）分开，
         窄窗时筛选行自动换行，不再把品牌/状态挤成竖排文字 -->
    <div class="sniff-toolbar">
      <span class="sniff-brand">🎯 手动抓取</span>
      <span class="sniff-dot" :class="{ on: listening }" />
      <span class="sniff-state">{{ listening ? '监听中 · 浏览网页即可捕获媒体' : '就绪' }}</span>
      <n-button
        size="tiny"
        quaternary
        type="primary"
        :loading="exportingWord"
        title="把左侧浏览器当前页面的正文（含图片/表格原位）导出为 Word 文档"
        @click="exportPageWord"
      >📄 存为 Word</n-button>
      <n-button
        size="tiny"
        quaternary
        type="warning"
        title="粘贴磁力链接或 .torrent 地址，用内置 aria2 内核下载（Motrix 同款）；在磁力站页面直接点磁力链接也会弹出下载"
        @click="btPromptSubmit"
      >🧲 BT 下载</n-button>
      <span
        class="sniff-hint"
        title="仅捕获公网 http/https 媒体；下载走通用下载管线（可暂停/续传）"
      >公网媒体 · 下载可暂停/续传</span>
    </div>
    <!-- 筛选行：类型筛选 + 排序 + 批量操作（flex-wrap，窄窗自动折行） -->
    <div class="sniff-filter-bar">
      <n-radio-group v-model:value="filter" size="small">
        <n-radio-button value="all">全部（{{ items.length }}）</n-radio-button>
        <n-radio-button value="video">视频（{{ countOf('video') }}）</n-radio-button>
        <n-radio-button value="audio">音频（{{ countOf('audio') }}）</n-radio-button>
        <n-radio-button value="image">图片（{{ countOf('image') }}）</n-radio-button>
        <n-radio-button value="hls">视频流（{{ countOf('hls') }}）</n-radio-button>
        <!-- 分片（TS/m4s）单列：一个视频上百条，混在「全部」里会把正片挤出上限 -->
        <n-radio-button value="hlsseg">分片（{{ countOf('hlsseg') }}）</n-radio-button>
        <n-radio-button v-if="countOf('doc')" value="doc">文档（{{ countOf('doc') }}）</n-radio-button>
        <n-radio-button v-if="countOf('archive')" value="archive">压缩包（{{ countOf('archive') }}）</n-radio-button>
      </n-radio-group>
      <!-- 排序：默认「媒体优先」——页面装饰图动辄几十张，会把唯一那条视频/流压到底部 -->
      <n-select
        v-model:value="sortKey"
        size="small"
        class="sniff-sort"
        :options="SORT_OPTIONS"
        title="列表排序方式"
      />
      <n-button size="small" quaternary type="primary" :disabled="!filtered.length" @click="downloadAll">下载全部</n-button>
      <n-button size="small" quaternary :disabled="!filtered.length" @click="copyAll">复制全部</n-button>
      <n-button size="small" quaternary type="error" :disabled="!items.length && !segTotal" @click="clearAll">清空</n-button>
    </div>

    <!-- 抓取模式条：应用内（默认）+ 系统代理（抓外部浏览器 Chrome/Edge 的请求） -->
    <div class="sniff-mode-bar">
      <span class="sniff-mode-label">抓取范围：</span>
      <n-tag size="small" :bordered="false" type="success">应用内浏览器（本窗口）</n-tag>
      <n-tag size="small" :bordered="false" :type="proxyRunning ? 'info' : 'default'">
        外部浏览器 · mitm {{ proxyRunning ? `运行中 :${proxyPort}` : '未启动' }}
      </n-tag>
      <n-button size="tiny" :loading="caInstalling" :type="caInstalled ? 'default' : 'warning'" @click="caInstall">
        {{ caInstalled ? '信任证书已安装' : '① 安装信任证书' }}
      </n-button>
      <n-button size="tiny" :type="proxyRunning ? 'error' : 'primary'" @click="toggleProxy">
        {{ proxyRunning ? '② 停止代理' : '② 启动代理' }}
      </n-button>
      <n-button size="tiny" :type="sysproxyOn ? 'error' : 'info'" :disabled="!proxyRunning" @click="toggleSysproxy">
        {{ sysproxyOn ? '③ 恢复系统代理' : '③ 接管系统代理' }}
      </n-button>
      <n-button
        size="tiny"
        :type="tapOn ? 'error' : 'warning'"
        :loading="tapToggling"
        title="实验性：强制解密 QQ/微信等流量可能触发其风控，导致功能受限甚至账号风险——建议小号测试，主号慎用"
        @click="toggleTap"
      >
        {{ tapOn ? '④ 关闭强制重定向' : '④ 抓聊天工具（实验·慎用）' }}
      </n-button>
      <span class="sniff-mode-hint">
        {{ tapOn ? '透明重定向运行中：QQ/微信等不走代理的应用流量已强制接入（QUIC 已阻断）。⚠ 实验性：部分聊天工具有证书绑定会连不上或触发风控，主号慎用，测完尽快关闭' : '三步后，外部浏览器（Chrome/Edge）里打开的网页媒体也会被抓到；④为实验性，谨慎使用' }}
      </span>
    </div>

    <!-- 主体：左浏览器 + 右资源列表 -->
    <div class="sniff-body">
      <!-- 左：内置浏览器 -->
      <div class="sniff-browser">
        <div class="sniff-nav">
          <n-button size="tiny" quaternary @click="nav('back')" title="后退">←</n-button>
          <n-button size="tiny" quaternary @click="nav('forward')" title="前进">→</n-button>
          <n-button size="tiny" quaternary @click="nav('reload')" title="刷新">↻</n-button>
          <n-button size="tiny" quaternary @click="nav('home')" title="回到空白页">🏠</n-button>
          <n-input
            v-model:value="addressDraft"
            size="small"
            class="sniff-address"
            placeholder="输入网址回车开始浏览，页面中的媒体将自动捕获到右侧"
            @keyup.enter="navigateAddress"
          >
            <template #prefix><span style="color:#63e2b7">🔒</span></template>
          </n-input>
        </div>
        <div class="sniff-stage">
          <webview
            ref="wvRef"
            src="about:blank"
            partition="persist:sniffer"
            :useragent="wvUserAgent"
            class="sniff-webview"
            @did-navigate="onNav"
            @did-navigate-in-page="onNav"
            @did-start-loading="loading = true"
            @did-stop-loading="loading = false"
          />
        </div>
      </div>

      <!-- 右：实时资源列表 -->
      <div class="sniff-list">
        <n-scrollbar style="flex: 1; min-height: 0">
          <!-- B站专属解析卡（表世界同款）：进入 B站视频页自动页内解析（登录态/清晰度/音视频分离合并）。
               B站走 DASH 分轨，抓不到 m3u8（视频流恒 0），这张卡是此类站唯一的"下载完整视频"入口 -->
          <div v-if="bili.visible" class="sn-bili" :class="{ loading: bili.loading }">
            <div class="sn-bili-head">
              <span class="sn-bili-badge">B站解析</span>
              <span v-if="bili.loading" class="sn-bili-state">解析中…</span>
              <span v-else-if="bili.error" class="sn-bili-err">{{ bili.error }}</span>
              <span v-else class="sn-bili-owner">{{ bili.owner }}</span>
              <n-button size="tiny" quaternary @click="bili.visible = false">收起</n-button>
            </div>
            <template v-if="!bili.loading && !bili.error">
              <div class="sn-bili-title" :title="bili.title">{{ bili.title }}</div>
              <div v-if="(bili.pages || []).length > 1" class="sn-bili-pages">
                <button
                  v-for="(pg, i) in bili.pages"
                  :key="pg.cid"
                  class="sn-p-chip"
                  :class="{ on: bili.pageIdx === i }"
                  :title="pg.part"
                  @click="bili.pageIdx = i"
                >P{{ pg.page }}</button>
              </div>
              <div class="sn-bili-row">
                <span class="sn-bili-label">清晰度</span>
                <select v-model="bili.qualityId" class="sn-bili-select">
                  <option v-for="q in bili.qualities" :key="q.id" :value="q.id">
                    {{ q.label }}（{{ q.sizeText }}）
                  </option>
                </select>
              </div>
              <div class="sn-bili-row">
                <span class="sn-bili-label">音频</span>
                <span class="sn-bili-audio">{{ bili.audioLabel }}</span>
              </div>
              <div class="sn-bili-actions">
                <button class="sn-dl" @click="downloadBili('merge')">下载 MP4（音视频合并）</button>
                <button class="sn-mini" @click="downloadBili('video')">仅视频</button>
                <button class="sn-mini" @click="downloadBili('audio')">仅音频</button>
              </div>
            </template>
          </div>
          <div v-if="!filtered.length" class="sniff-empty">
            <div style="font-size: 40px">🎯</div>
            <div style="margin: 8px 0 4px">暂无捕获资源</div>
            <div style="font-size: 12px; opacity: 0.6">在左侧浏览网页，视频/音频/图片会实时出现在这里</div>
          </div>
          <div
            v-for="it in filtered"
            :key="it.url"
            class="sniff-item"
            :class="{ 'sniff-item-dl': downloaded.has(it.url), 'sniff-item-ad': it.verdict === 'ad' }"
          >
            <span class="sniff-badge" :class="'sniff-badge-' + it.type">{{ typeLabel(it.type) }}</span>
            <div class="sniff-item-main">
              <div class="sniff-name" :title="it.url">{{ it.filename }}</div>
              <div class="sniff-meta">
                <span
                  v-if="it.verdict"
                  class="sniff-verdict"
                  :class="'sniff-verdict-' + it.verdict"
                  :title="verdictTip(it)"
                >{{ verdictLabel(it.verdict) }}</span>
                {{ hostOf(it.url) }}<template v-if="it.durationText"> · ⏱ {{ it.durationText }}</template><template v-if="it.size"> · {{ fmtSize(it.size) }}</template> · {{ fmtTime(it.ts) }}
              </div>
              <!-- 疑似广告：内联显示判定依据，不用悬浮也能看懂为什么沉底 -->
              <div v-if="it.verdict === 'ad' && it.probeReasons && it.probeReasons.length" class="sniff-why">
                {{ it.probeReasons.join('；') }}
              </div>
            </div>
            <n-button
              v-if="isTorrentItem(it)"
              size="tiny"
              type="warning"
              title="用 aria2 内核下载这个种子（磁力/BT 任务，进度在下载管理看）"
              @click="submitBt(it.url)"
            >BT</n-button>
            <n-button size="tiny" type="primary" :disabled="hlsBusy.has(it.url)"
                      :title="it.type === 'hls' ? '下载整片：加入下载管理，分片下载完成后合并为 MP4（可暂停/继续/重试）' : '下载此资源'"
                      @click="downloadOne(it)">{{ it.type === 'hls' ? (hlsBusy.has(it.url) ? (hlsBusy.get(it.url) || '提交中…') : (it.verdict === 'ad' ? '仍要下载' : '下载整片')) : '下载' }}</n-button>
            <n-button size="tiny" quaternary title="复制链接" @click="copyOne(it.url)">复制</n-button>
            <span v-if="downloaded.has(it.url)" class="sniff-done">已提交</span>
          </div>
        </n-scrollbar>
      </div>
    </div>

    <!-- BT 下载弹窗：替代 window.prompt（Electron 不支持 prompt，调用会静默失败） -->
    <n-modal v-model:show="btShow" preset="dialog" title="🧲 BT 下载（磁力链接 / 种子）" style="width: 580px">
      <div class="sn-bt-body">
        <n-input v-model:value="btText" type="textarea" :rows="6"
                 placeholder="每行一条磁力链接（magnet:?xt=urn:btih:…）或 .torrent 种子地址，支持多行批量" />
        <div class="sn-bt-drop" @dragover.prevent @drop.prevent="onBtDrop">
          🧲 把 .torrent 种子文件拖到这里提交（可多个）
        </div>
        <div class="sn-bt-foot">
          <label class="sn-bt-auto" title="开启后，在网页里点磁力链接不再弹确认，直接加入下载">
            <n-switch v-model:value="btAuto" size="small" />
            自动接管磁力链接
          </label>
          <n-button type="primary" @click="submitBtBatch">批量下载</n-button>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import {
  NButton, NInput, NModal, NRadioButton, NRadioGroup, NScrollbar, NSelect, NSwitch, NTag, useMessage,
} from 'naive-ui'

const message = useMessage()
const items = ref([])          // 捕获列表（最新在前）
// TS/m4s 分片单列：一个视频播放要请求上百个分片，混进 items 会把真正的正片（m3u8）
// 挤出 MAX_ITEMS 上限被截掉。这里只留前 SEG_KEEP 条备查，总数单独计数。
const segItems = ref([])
const segTotal = ref(0)
const SEG_KEEP = 50
const filter = ref('all')
const listening = ref(true)
const loading = ref(false)
const addressDraft = ref('')
const currentUrl = ref('')
const wvRef = ref(null)
const downloaded = ref(new Set()) // 已提交下载的 URL
const MAX_ITEMS = 500
// 截尾一次性提醒：首次触发截尾时弹一次（之后静默截断，不刷屏）
let truncatedHinted = false

// 系统代理模式（mitm）状态
const proxyRunning = ref(false)
const proxyPort = ref(0)
const caInstalled = ref(false)
const caInstalling = ref(false)
const sysproxyOn = ref(false)
// 透明重定向（WinDivert 强制抓聊天工具）状态
const tapOn = ref(false)
const tapToggling = ref(false)

// webview UA：去 Electron 标记（与主窗登录套件同款）
const wvUserAgent = (navigator.userAgent || '').replace(/\sElectron\/[\d.]+/i, '').trim()

// ---- 排序（与美好世界同口径）----
// 媒体优先：视频/流/音频/文档/压缩包排在页面装饰图片之前。一个页面动辄几十张缩略图，
// 会把唯一那条视频/流压到列表底部，用户于是以为"根本没抓到"——这正是美好世界踩过的坑。
const sortKey = ref('media')
const SORT_OPTIONS = [
  { label: '媒体优先', value: 'media' },
  { label: '最新捕获', value: 'time' },
  { label: '按时长', value: 'duration' },
  { label: '按大小', value: 'size' },
  { label: '按类型', value: 'type' },
]
const TYPE_RANK = { video: 0, hls: 0, audio: 1, doc: 2, archive: 3, hlsseg: 7, other: 8, image: 9 }
// 同类里再按判决排：正片 < 存疑 < 未判定 < 疑似广告（广告沉底，避免顶掉正片位置）
function verdictRank(it) {
  if (it.verdict === 'content') return 0
  if (it.verdict === 'unknown') return 1
  if (it.verdict === 'ad') return 3
  return 2
}

const filtered = computed(() => {
  let list
  if (filter.value === 'hlsseg') list = segItems.value.slice()
  else if (filter.value === 'all') list = items.value.slice()
  else list = items.value.filter(i => i.type === filter.value)
  if (sortKey.value === 'size') list.sort((a, b) => (b.size || 0) - (a.size || 0))
  else if (sortKey.value === 'duration') list.sort((a, b) => (b.duration || 0) - (a.duration || 0))
  else if (sortKey.value === 'type') list.sort((a, b) => (a.type || '').localeCompare(b.type || ''))
  else if (sortKey.value === 'media') list.sort((a, b) => {
    const ra = TYPE_RANK[a.type] === undefined ? 8 : TYPE_RANK[a.type]
    const rb = TYPE_RANK[b.type] === undefined ? 8 : TYPE_RANK[b.type]
    if (ra !== rb) return ra - rb
    const va = verdictRank(a)
    const vb = verdictRank(b)
    return va === vb ? (b.ts || 0) - (a.ts || 0) : va - vb
  })
  else list.sort((a, b) => (b.ts || 0) - (a.ts || 0))
  return list
})

// ---- 智能判决（后端 hls_probe 回流）：content=正片 / unknown=存疑 / ad=疑似广告 ----
function verdictLabel(v) {
  return { content: '正片', ad: '疑似广告', unknown: '存疑' }[v] || ''
}
function verdictTip(it) {
  const head = {
    content: '识别为正片',
    ad: '识别为疑似广告（「下载全部」会自动跳过它）',
    unknown: '无法确定是正片还是广告',
  }[it.verdict] || ''
  const lines = []
  if (it.durationText) lines.push(`时长：${it.durationText}`)
  if (it.segCount) lines.push(`分片：${it.segCount} 段`)
  const why = (it.probeReasons || []).join('；')
  if (why) lines.push(`依据：${why}`)
  if (it.probeNote) lines.push(`注意：${it.probeNote}`)
  return [head].concat(lines).filter(Boolean).join('\n')
}
// 时长文案（与后端 web_hls_fmt_dur 同规格）
function fmtDur(sec) {
  const s = Math.round(Number(sec) || 0)
  if (s <= 0) return ''
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = s % 60
  const p = n => String(n).padStart(2, '0')
  return h ? `${h}:${p(m)}:${p(ss)}` : `${m}:${p(ss)}`
}

function countOf(t) {
  if (t === 'hlsseg') return segTotal.value   // 分片只留前 SEG_KEEP 条，计数用总数
  return items.value.filter(i => i.type === t).length
}
function typeLabel(t) {
  const m = { video: '视频', audio: '音频', image: '图片', hls: '视频流', hlsseg: '分片', doc: '文档', archive: '压缩包' }
  return m[t] || '其他'
}
function hostOf(u) {
  try { return new URL(u).hostname } catch (e) { return '' }
}
function fmtSize(n) {
  if (!n || n <= 0) return ''
  if (n >= 1024 ** 3) return (n / 1024 ** 3).toFixed(2) + ' GB'
  if (n >= 1024 ** 2) return (n / 1024 ** 2).toFixed(1) + ' MB'
  if (n >= 1024) return (n / 1024).toFixed(0) + ' KB'
  return n + ' B'
}
function fmtTime(ts) {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}
function filenameFromUrl(u) {
  try {
    const p = new URL(u).pathname.split('/').filter(Boolean).pop() || ''
    const name = decodeURIComponent(p)
    return name.length > 80 ? name.slice(-80) : (name || '')
  } catch (e) { return '' }
}

// 主进程 webRequest 捕获 → 入列（URL 去重，最新在前）
function newItem(data, type) {
  return {
    url: data.url,
    type,
    size: data.size || 0,
    page_url: data.page_url || '',
    ts: data.ts || Date.now(),
    filename: filenameFromUrl(data.url) || hostOf(data.url),
    duration: 0, durationText: '',
    // 智能判决字段（hls_probe_result 回流填充）
    verdict: '', probeReasons: [], probeNote: '', segCount: 0,
  }
}

function addItem(data) {
  if (!data || !data.url) return
  // TS/m4s 分片单列（见 segItems 处说明）：不入主列表，避免把 m3u8 正片挤出上限。
  // 分片只有几秒，逐条探测时长纯属浪费——所以这里也不发探测命令。
  if ((data.type || '') === 'hlsseg') {
    segTotal.value++
    if (segItems.value.length < SEG_KEEP && !segItems.value.some(i => i.url === data.url)) {
      segItems.value.unshift(newItem(data, 'hlsseg'))
    }
    return
  }
  if (items.value.some(i => i.url === data.url)) return
  items.value.unshift(newItem(data, data.type || 'other'))
  // 与美好世界同款探测：视频流读播放清单（毫秒级，顺带判正片/广告）；
  // 普通 mp4 走 ffprobe 远程读时长（结果经 duration_result 回流）。
  if ((data.type || '') === 'hls') {
    window.api && window.api.sendCommand({
      cmd: 'hls_probe', url: data.url, referer: currentUrl.value || '',
    })
  } else if ((data.type || '') === 'video') {
    window.api && window.api.sendCommand({
      cmd: 'probe_duration', url: data.url, referer: currentUrl.value || '',
    })
  }
  if (items.value.length > MAX_ITEMS) {
    items.value.length = MAX_ITEMS
    if (!truncatedHinted) {
      truncatedHinted = true
      message.info('捕获已超过 500 条，早前的条目已被移除；需要的话请及时下载或用「复制全部」备份', { duration: 6000 })
    }
  }
}

onMounted(() => {
  if (window.api && window.api.onSnifferResource) {
    window.api.onSnifferResource(addItem)
  }
  // 提交结果回流（后端 sniff_download_result）+ mitm 模式状态事件
  if (window.api && window.api.onEvent) {
    window.api.onEvent((ev) => {
      if (!ev || !ev.event) return
      if (ev.event === 'sniff_capture') {
        // mitm 系统代理捕获（外部浏览器流量）——与应用内捕获同列表
        addItem(ev)
        return
      }
      if (ev.event === 'sniff_download_result') {
        if (ev.ok) {
          message.success(ev.message || '下载已提交')
          const urls = ev.urls || []
          if (urls.length) downloaded.value = new Set([...downloaded.value, ...urls])
        } else {
          message.error(ev.message || '提交失败')
        }
      } else if (ev.event === 'word_result') {
        // 存为 Word 收尾（成功/失败都有提示，超时兜底在 exportPageWord 的 wordTimer）
        if (wordTimer) { clearTimeout(wordTimer); wordTimer = null }
        exportingWord.value = false
        if (ev.ok) {
          const line = ev.message
            || `Word 已导出${ev.filename ? '：' + ev.filename : ''}${ev.dir ? ' · 保存于 ' + ev.dir : ''}`
          message.success(line, { duration: 10000 })
        } else {
          message.error(ev.message || 'Word 导出失败', { duration: 8000 })
        }
      } else if (ev.event === 'bili_download_result') {
        if (ev.ok) message.success(ev.message || 'B站下载已提交')
        else message.error(ev.message || 'B站下载提交失败')
      } else if (ev.event === 'bt_result') {
        if (ev.ok) message.success(ev.message || 'BT 任务已提交')
        else message.error(ev.message || 'BT 提交失败')
      } else if (ev.event === 'hls_probe_result') {
        // 智能判决回流：填时长/分片数/判决徽标 + 判定依据（列表内联展示）
        const hit = items.value.find(i => i.url === ev.url)
        if (!hit) return
        if (!ev.ok) {
          hit.probeNote = ev.message || '播放清单探测失败'
          return
        }
        hit.verdict = ev.verdict || ''
        hit.probeReasons = ev.reasons || []
        hit.probeNote = ev.note || ''
        hit.segCount = ev.segCount || 0
        if (ev.duration > 0) {
          hit.duration = ev.duration
          hit.durationText = fmtDur(ev.duration)
        }
        if (ev.verdict === 'content' && !contentHinted) {
          contentHinted = true
          message.success(`识别到正片${ev.durationText ? '（' + ev.durationText + '）' : ''}：点这条右侧「下载整片」保存 MP4`, { duration: 8000 })
        }
      } else if (ev.event === 'duration_result') {
        // 普通 mp4 直链的 ffprobe 时长回流（与美好世界同款）
        const hit = items.value.find(i => i.url === ev.url)
        if (hit && ev.duration > 0) {
          hit.duration = ev.duration
          hit.durationText = fmtDur(ev.duration)
        }
      } else if (ev.event === 'hls_submit_result') {
        const busy = hlsBusy.value.has(ev.url)
        if (busy) {
          hlsBusy.value.delete(ev.url)
          hlsBusy.value = new Map(hlsBusy.value)
        }
        if (ev.ok) {
          if (ev.url) downloaded.value = new Set([...downloaded.value, ev.url])
          // 提交时后端也会解析清单：把时长/判决回填（hls_probe 失败或未回的兜底）
          const hit = items.value.find(i => i.url === ev.url)
          if (hit) {
            if (ev.duration > 0 && !hit.durationText) {
              hit.duration = ev.duration
              hit.durationText = fmtDur(ev.duration)
            }
            if (ev.verdict && !hit.verdict) hit.verdict = ev.verdict
          }
          message.success(ev.message || '已加入下载管理')
        } else {
          message.error(ev.message || '流媒体提交失败')
        }
      } else if (ev.event === 'hls_progress') {
        if (hlsBusy.value.has(ev.url) && ev.total > 0) {
          hlsBusy.value.set(ev.url, `分片 ${ev.done}/${ev.total}`)
          hlsBusy.value = new Map(hlsBusy.value)
        }
        // 拼接时后端也会解析清单：时长/判决/加密方式回填到列表项
        if (ev.phase === 'analyzed') {
          const hit = items.value.find(i => i.url === ev.url)
          if (hit) {
            if (ev.duration > 0 && !hit.durationText) {
              hit.duration = ev.duration
              hit.durationText = fmtDur(ev.duration)
            }
            if (ev.verdict && !hit.verdict) hit.verdict = ev.verdict
            if (ev.encrypted) hit.probeNote = 'AES-128 加密流（下载时自动解密）'
            else if (ev.fmp4) hit.probeNote = 'fMP4 分片'
          }
        }
      } else if (ev.event === 'hls_result') {
        const busy = hlsBusy.value.has(ev.url)
        if (busy) {
          hlsBusy.value.delete(ev.url)
          hlsBusy.value = new Map(hlsBusy.value)
        }
        if (ev.ok) {
          if (ev.url) downloaded.value = new Set([...downloaded.value, ev.url])
          message.success(ev.message || '流媒体已合并完成')
        } else if (busy) {
          message.error(ev.message || '流媒体拼接失败')
        }
      } else if (ev.event === 'sniff_proxy_state') {
        proxyRunning.value = !!ev.running
        proxyPort.value = ev.port || 0
      } else if (ev.event === 'sniff_ca_state') {
        caInstalled.value = !!ev.installed
      } else if (ev.event === 'sniff_ca_result') {
        caInstalling.value = false
        if (ev.ok) {
          caInstalled.value = true
          message.success(ev.message || '证书已安装')
        } else {
          message.error(ev.message || '证书安装失败')
        }
      } else if (ev.event === 'sniff_sysproxy_state') {
        sysproxyOn.value = !!ev.on
      } else if (ev.event === 'sniff_tap_state') {
        tapToggling.value = false
        tapOn.value = !!ev.on
        if (ev.message) {
          if (ev.on) message.success(ev.message)
          else message.info(ev.message)
        }
      }
    })
    // 启动即查一次证书/代理状态
    window.api.sendCommand({ cmd: 'sniff_ca_check' })
    window.api.sendCommand({ cmd: 'sniff_proxy_status' })
    window.api.sendCommand({ cmd: 'sniff_tap_status' })
  }
})

// 系统代理模式操作
function caInstall() {
  caInstalling.value = true
  window.api && window.api.sendCommand({ cmd: 'sniff_ca_install' })
}
function toggleProxy() {
  if (!window.api) return
  if (proxyRunning.value) {
    // 停代理前先恢复系统代理（避免外部浏览器断网）
    if (sysproxyOn.value) window.api.sendCommand({ cmd: 'sniff_sysproxy_off' })
    window.api.sendCommand({ cmd: 'sniff_proxy_stop' })
  } else {
    window.api.sendCommand({ cmd: 'sniff_proxy_start' })
  }
}
function toggleSysproxy() {
  if (!window.api) return
  window.api.sendCommand({ cmd: sysproxyOn.value ? 'sniff_sysproxy_off' : 'sniff_sysproxy_on' })
}
function toggleTap() {
  if (!window.api || tapToggling.value) return
  tapToggling.value = true
  // 关闭透明重定向时同时恢复系统代理（避免外部断网）
  if (tapOn.value) {
    if (sysproxyOn.value) window.api.sendCommand({ cmd: 'sniff_sysproxy_off' })
    window.api.sendCommand({ cmd: 'sniff_tap_off' })
  } else {
    window.api.sendCommand({ cmd: 'sniff_tap_on' })
  }
}

// 浏览器导航
function onNav(e) {
  const url = e.url || ''
  if (!url || url === 'about:blank') return
  addressDraft.value = url
  currentUrl.value = url
  // B站视频页自动弹出解析卡（表世界同款：防抖 800ms，非视频页自动收起）
  scheduleBiliParse(url)
}
function navigateAddress() {
  let u = (addressDraft.value || '').trim()
  if (!u) return
  if (!/^https?:\/\//i.test(u)) u = 'https://' + u
  currentUrl.value = u
  try { wvRef.value && wvRef.value.loadURL(u) } catch (e) { /* webview 未就绪 */ }
}
function nav(action) {
  const wv = wvRef.value
  if (!wv) return
  try {
    if (action === 'back') wv.goBack()
    else if (action === 'forward') wv.goForward()
    else if (action === 'reload') wv.reload()
    else if (action === 'home') { wv.loadURL('about:blank'); currentUrl.value = ''; addressDraft.value = '' }
  } catch (e) { /* 忽略 */ }
}

// ===== 当前页面存为 Word（表世界同款：页内提取正文，图片/表格按原位置写入文档） =====
// 落盘：不带 world → 后端落 ~/Downloads/Word导出/（里世界规则，结果经 word_result 回流）
const exportingWord = ref(false)
let wordTimer = null   // 导出超时兜底（结果事件未回来时解除按钮锁定）

async function exportPageWord() {
  if (exportingWord.value || !wvRef.value) return
  exportingWord.value = true
  message.info && message.info('正在提取正文并导出 Word…')
  const finish = (fn, msg) => {
    if (wordTimer) { clearTimeout(wordTimer); wordTimer = null }
    exportingWord.value = false
    fn && fn(msg)
  }
  wordTimer = setTimeout(() => {
    finish(message.warning, 'Word 导出超时：未收到后端结果，请重试或查看日志')
  }, 150000)
  try {
    // 先滚动触发懒加载（单独一次 evaluate：SPA 滚动过程中若发生导航/跳转，
    // 不会连累后面的正文提取——此前整段一起执行会因"执行上下文被销毁"直接失败）
    const scrollJs = `(async () => {
      const sleep = ms => new Promise(r => setTimeout(r, ms));
      try {
        for (let i = 0; i < 6; i++) { window.scrollBy(0, Math.round(window.innerHeight * 0.8)); await sleep(320); }
        window.scrollTo(0, 0); await sleep(200);
      } catch (e) { /* 页面跳转/销毁：忽略，继续执行后面的提取 */ }
      return true;
    })()`
    try { await wvRef.value.executeJavaScript(scrollJs, false) } catch (e) { /* 忽略滚动失败 */ }

    const js = `(async () => {
      const clean = s => (s || '').replace(/\\s+/g, ' ').trim();
      const BAD = new Set(['script','style','noscript','svg','template','iframe','form','button','select','textarea']);
      const NOISE_SEL = 'nav,footer,aside,header,.nav,.footer,.sidebar,.comment,#comments,.ad,.advert';

      const visible = el => {
        try {
          const s = getComputedStyle(el);
          if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity || '1') < 0.05) return false;
          const r = el.getBoundingClientRect();
          return r.width > 0 || r.height > 0;
        } catch (e) { return true; }
      };
      const nodes = [];
      const seen = new Set();
      let imgCount = 0;
      const push = node => {
        if (nodes.length >= 1200) return;
        const key = node.t + '|' + (node.text || node.src || node.html || '');
        if (seen.has(key)) return;
        seen.add(key);
        nodes.push(node);
      };
      const root = document.querySelector('main, article, [role=main]') || document.body;

      // ---- 第一轮：语义标签（标题/段落/列表/引用/代码块/表格/图片） ----
      const inNoise = el => { try { return !!(el.closest && el.closest(NOISE_SEL)) } catch (e) { return false } };
      root.querySelectorAll('h1,h2,h3,h4,h5,h6,p,li,blockquote,pre,table,figure,img').forEach(el => {
        const tag = el.tagName.toLowerCase();
        if (BAD.has(tag)) return;
        if (tag === 'img') {
          if (imgCount >= 40) return;
          const src = el.currentSrc || el.src || el.getAttribute('data-src') || el.getAttribute('data-original') || '';
          if (!src || src.indexOf('data:') !== 0 && !/^https?:\\/\\//i.test(src)) return;
          const w = el.naturalWidth || el.getBoundingClientRect().width || 0;
          if (w && w < 80) return;             // 图标/像素占位忽略
          imgCount++; push({ t: 'img', src: src.slice(0, 2000) });
          return;
        }
        if (!visible(el) || inNoise(el)) return;
        if (tag === 'table') {
          const txt = clean(el.innerText || el.textContent || '');
          if (!txt) return;
          push({ t: 'table', html: (el.outerHTML || '').slice(0, 300000), text: txt.slice(0, 20000) });
          return;
        }
        const txt = clean(el.innerText || el.textContent || '');
        if (!txt || txt.length < (tag.startsWith('h') ? 2 : 6)) return;   // 太短的碎片（导航项、按钮文案）丢掉
        push({ t: tag, text: txt.slice(0, 20000) });
      });

      // ---- 第二轮兜底：div/span 型站点（多数 SPA 没有 <p>）——取叶子文本节点按父元素聚合 ----
      const textLen = nodes.filter(n => n.t !== 'img').reduce((s, n) => s + (n.text || '').length, 0);
      if (textLen < 300) {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
          acceptNode(n) {
            const t = clean(n.nodeValue || '');
            if (!t || t.length < 20) return NodeFilter.FILTER_REJECT;
            const p = n.parentElement;
            if (!p || BAD.has(p.tagName.toLowerCase())) return NodeFilter.FILTER_REJECT;
            if (!visible(p) || inNoise(p)) return NodeFilter.FILTER_REJECT;
            return NodeFilter.FILTER_ACCEPT;
          }
        });
        let lastParent = null;
        let node;
        while ((node = walker.nextNode())) {
          const t = clean(node.nodeValue);
          if (!t) continue;
          if (node.parentElement === lastParent && nodes.length) {
            const last = nodes[nodes.length - 1];
            if (last.t && !last.t.startsWith('h') && last.t !== 'img' && last.t !== 'table') {
              last.text = (last.text + ' ' + t).slice(0, 20000);
              continue;
            }
          }
          lastParent = node.parentElement;
          push({ t: 'p', text: t });
        }
      }
      return {
        title: (document.title || (document.querySelector('h1') || {}).innerText || '网页导出').slice(0, 120),
        elements: nodes,
        rounds: nodes.length,
      };
    })()`
    // 提取可能因页面跳转（B站等 SPA 常自动重定向）导致"执行上下文被销毁"，
    // 失败后等 1.2s 重试一次，仍失败才报错
    let data = null
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        data = await wvRef.value.executeJavaScript(js, false)
        break
      } catch (e) {
        if (attempt === 1) throw e
        await new Promise(r => setTimeout(r, 1200))
      }
    }
    if (!data || !data.elements || !data.elements.length) {
      finish(message.error, '未识别到可导出的正文（纯图/视频页或内容在框架内无法读取）')
      return
    }
    window.api && window.api.sendCommand({
      cmd: 'web_to_word',
      title: data.title,
      doc_title: data.title,
      page_url: currentUrl.value || '',
      elements: data.elements,
      // 不带 world：落 ~/Downloads/Word导出/（里世界口径）
      album: hostOf(currentUrl.value || '') || '网页导出',
    })
    // 结果由 word_result 事件收尾（成功/失败都有提示，不再假成功）
  } catch (e) {
    finish(message.error, 'Word 导出失败：' + ((e && e.message) || '未知错误'))
  }
}

// ===== B站专属解析（表世界同款：页内 fetch 带登录态/真实指纹，绕开对脚本端的风控） =====
// B站走 DASH 分轨（m4s），抓不到 m3u8 —— 视频流恒 0，这张卡是"下载完整视频"的唯一入口。
const BILI_Q = {
  127: '8K 超高清', 126: '杜比视界', 125: 'HDR 真彩', 120: '4K 超清',
  116: '1080P 60帧', 112: '1080P 高码率', 100: '智能修复',
  80: '1080P 高清', 74: '720P 60帧', 64: '720P 高清', 32: '480P 清晰', 16: '360P 流畅',
}
const BILI_A = { 30280: '320kbps', 30232: '128kbps', 30216: '64kbps' }
const bili = reactive({
  visible: false, loading: false, error: '',
  title: '', owner: '', bvid: '',
  pages: [], pageIdx: 0,
  qualities: [], qualityId: 0,
  audioLabel: '', audioUrl: '',
})
let biliParseTimer = null
let biliSeq = 0

function scheduleBiliParse(url) {
  const m = String(url || '').match(/bilibili\.com\/video\/(BV[0-9A-Za-z]{8,12})/i)
  if (!m) { bili.visible = false; return }
  bili.visible = true
  bili.loading = true
  bili.error = ''
  const bvid = m[1]
  const pMatch = String(url).match(/[?&]p=(\d+)/)
  const seq = ++biliSeq
  if (biliParseTimer) clearTimeout(biliParseTimer)
  biliParseTimer = setTimeout(() => parseBili(bvid, pMatch ? parseInt(pMatch[1], 10) : 1, seq), 800)
}

async function parseBili(bvid, page, seq) {
  try {
    const wv = wvRef.value
    if (!wv) throw new Error('浏览器未就绪')
    // 页内 fetch：自动带 B站登录 cookie 与真实浏览器指纹（后端直连会被 412 风控）
    const j = await wv.executeJavaScript(
      `fetch('https://api.bilibili.com/x/web-interface/view?bvid=${bvid}',{credentials:'include'}).then(r=>r.json())`, false)
    if (seq !== biliSeq) return
    if (!j || j.code !== 0) throw new Error((j && j.message) || '解析失败')
    const d = j.data || {}
    const pages = (d.pages || []).map(p => ({ page: p.page, part: p.part || '', cid: p.cid }))
    const cur = pages.find(p => p.page === page) || pages[0] || { cid: d.cid, page: 1, part: '' }
    const j2 = await wv.executeJavaScript(
      `fetch('https://api.bilibili.com/x/player/playurl?bvid=${bvid}&cid=${cur.cid}&qn=127&fnval=4048&fourk=1',{credentials:'include'}).then(r=>r.json())`, false)
    if (seq !== biliSeq) return
    if (!j2 || j2.code !== 0) throw new Error((j2 && j2.message) || '取播放流失败')
    const pd = j2.data || {}
    const dash = pd.dash || {}
    const aq = pd.accept_quality || []
    const ad = pd.accept_description || []
    const labelOf = (id) => {
      const i = aq.indexOf(id)
      return (i >= 0 ? ad[i] : '') || BILI_Q[id] || `${id}`
    }
    // 同一清晰度多种编码（avc/hevc/av01）取体积最大的一条
    const byId = new Map()
    for (const v of (dash.video || [])) {
      const prev = byId.get(v.id)
      if (!prev || (v.size || 0) > (prev.size || 0)) byId.set(v.id, v)
    }
    const qualities = [...byId.values()]
      .sort((a, b) => (b.id || 0) - (a.id || 0))
      .map(v => ({
        id: v.id,
        label: labelOf(v.id),
        sizeText: v.size ? `${(v.size / 1048576).toFixed(0)}MB` : '—',
        url: v.base_url || (v.backup_url && v.backup_url[0]) || '',
      }))
    const auds = (dash.audio || []).slice().sort((a, b) => (b.id || 0) - (a.id || 0))
    const aud = auds[0]
    Object.assign(bili, {
      loading: false, error: '',
      title: d.title || '未知标题',
      owner: `UP：${(d.owner || {}).name || '未知'}`,
      bvid: d.bvid || bvid,
      pages,
      pageIdx: Math.max(0, pages.findIndex(p => p.page === (cur.page || 1))),
      qualities,
      qualityId: qualities[0] ? qualities[0].id : 0,
      audioLabel: aud ? `${BILI_A[aud.id] || '音频'}${aud.size ? `（${(aud.size / 1048576).toFixed(1)}MB）` : ''}` : '无',
      audioUrl: aud ? (aud.base_url || '') : '',
    })
  } catch (e) {
    if (seq !== biliSeq) return
    Object.assign(bili, { loading: false, error: (e && e.message) || '解析失败（请先在浏览器中打开本视频页）' })
  }
}

function downloadBili(mode) {
  const q = bili.qualities.find(x => x.id === bili.qualityId) || bili.qualities[0]
  if (!q || !q.url) { message.error('未解析到可用的视频流'); return }
  if (mode in { merge: 1, audio: 1 } && !bili.audioUrl) { message.error('未解析到音频流'); return }
  const pg = bili.pages[bili.pageIdx] || {}
  window.api && window.api.sendCommand({
    cmd: 'bili_download',
    album: '哔哩哔哩',
    item: {
      video_url: q.url,
      audio_url: bili.audioUrl,
      mode,
      quality_label: q.label,
      title: bili.title,
      page: pg.page || 1,
      page_part: pg.part || '',
      page_url: currentUrl.value,
      bvid: bili.bvid,
    },
  })
}

// 下载：直链走后端 sniff_download；HLS 走「下载整片」（hls_submit）——
// 提交为下载任务（分片落盘、可暂停/续传/重试），进度到下载管理里看
const hlsBusy = ref(new Map())
const HLS_GENERIC_NAME = /^(index|playlist|master|video|live|hls|stream|main|manifest|getm3u8|get|play|api)([-_.]?\d*)?(\.m3u8)?$/i
const HLS_HASH_NAME = /^[0-9a-f]{16,}$/i
// 「识别到正片」提示只弹一次（不逐条刷屏）
let contentHinted = false

function downloadOne(it) {
  if (it.type === 'hls') {
    if (hlsBusy.value.has(it.url)) return
    // 被判为疑似广告：先确认一次（「下载全部」会自动跳过它们，手动点则是明确意愿）
    if (it.verdict === 'ad') {
      const why = (it.probeReasons || []).slice(0, 2).join('；') || '时长过短或含广告标记'
      if (!window.confirm(`这条流被判定为疑似广告：\n\n${why}\n\n确定仍要下载吗？`)) return
    }
    const name = hlsDisplayName(it)
    hlsBusy.value.set(it.url, '提交中…')
    hlsBusy.value = new Map(hlsBusy.value)
    window.api && window.api.sendCommand({
      cmd: 'hls_submit',
      url: it.url,
      referer: it.page_url || currentUrl.value || '',
      album: hostOf(it.page_url || currentUrl.value || '') || '手动抓取',
      filename: name,
    })
    return
  }
  submitItems([it])
}
// 流媒体文件名：接口名/哈希/无扩展名末段一律回退「抓取流_时间戳」
// （很多站把 m3u8 藏在 /nby/m3u8/getM3u8 这类接口路径里，末段根本不是文件名）
function hlsDisplayName(it) {
  const orig = it.filename || ''
  const raw = orig.replace(/\.m3u8$/i, '')
  const unusable = !raw || raw.length < 2
    || HLS_GENERIC_NAME.test(orig)
    || HLS_HASH_NAME.test(raw)
    || !orig.includes('.')
  if (!unusable) return raw
  const ts = new Date()
  const pad = n => String(n).padStart(2, '0')
  return `抓取流_${ts.getFullYear()}${pad(ts.getMonth() + 1)}${pad(ts.getDate())}-${pad(ts.getHours())}${pad(ts.getMinutes())}${pad(ts.getSeconds())}`
}

function downloadAll() {
  if (!filtered.value.length) return
  // 分片只是视频的一小段：既拼不出整片，也绝不能当直链提交（旧版提示归提示、照样提交）
  if (filter.value === 'hlsseg') {
    message.info('分片只是视频的一小段，单独下载拼不出整片；要正片请切到「视频流」下载 m3u8 那一条', { duration: 8000 })
    return
  }
  // 已被智能判决为疑似广告的流自动跳过（要下就单独点它的「仍要下载」）——
  // 一个页面通常同时抓到正片清单和贴片广告清单，全下会把广告一起拖下来。
  const direct = []
  let skippedAds = 0
  for (const it of filtered.value) {
    if (it.type === 'hls') {
      if (it.verdict === 'ad') { skippedAds++; continue }
      downloadOne(it)
      continue
    }
    direct.push(it)
  }
  if (skippedAds) {
    message.info(`已自动跳过 ${skippedAds} 条疑似广告流（时长过短或含广告标记）；确实要下就单独点它的「仍要下载」`, { duration: 8000 })
  }
  submitItems(direct)
}
function submitItems(list) {
  if (!list.length) return
  const page = currentUrl.value || (list[0] && list[0].page_url) || ''
  window.api && window.api.sendCommand({
    cmd: 'sniff_download',
    album: hostOf(page) || '手动抓取',
    items: list.map(i => ({
      url: i.url,
      filename: i.filename,
      media_type: i.type,
      size: i.size || 0,
      page_url: page || i.page_url,
    })),
  })
}

// ===== BT 下载（磁力链接/.torrent）：aria2 内核，进度走下载管理 =====
// 捕获到 .torrent 种子文件的条目（主进程把它归 doc 类）→ 显示「BT」按钮
function isTorrentItem(it) {
  return !!it && /\.torrent(\?|#|$)/i.test(it.url || '')
}
function submitBt(url) {
  const u = (url || '').trim()
  if (!u) return
  window.api && window.api.sendCommand({
    cmd: 'bt_download',
    url: u,
    album: btAlbum(),
  })
}
function btAlbum() {
  return hostOf(currentUrl.value || '') || 'BT 下载'
}
// ---- BT 弹窗：Electron 不支持 window.prompt（调用会静默失败），改用 n-modal ----
// 里世界口径：不带 world 字段（任务落 Downloads），album 用当前页 host
const btShow = ref(false)
const btText = ref('')
function btPromptSubmit() {
  btShow.value = true
}
// 自动接管磁力链接：开启后网页里点 magnet: 不再弹确认，直接提交（偏好持久化）
const btAuto = ref(false)
try { btAuto.value = localStorage.getItem('bt_auto_takeover') === '1' } catch (e) { /* 隐私模式 */ }
watch(btAuto, v => {
  try { localStorage.setItem('bt_auto_takeover', v ? '1' : '0') } catch (e) { /* 隐私模式 */ }
})
function submitBtBatch() {
  const lines = (btText.value || '').split('\n').map(s => s.trim()).filter(Boolean)
  if (!lines.length) {
    message.warning('请先粘贴至少一条磁力链接或种子地址')
    return
  }
  lines.forEach(u => submitBt(u))
  message.success(`已提交 ${lines.length} 条 BT 任务`)
  btText.value = ''
  btShow.value = false
}
// .torrent 种子文件拖拽：读文件 → base64 → bt_download_file
async function onBtDrop(e) {
  const files = Array.from((e.dataTransfer && e.dataTransfer.files) || [])
  const torrents = files.filter(f => /\.torrent$/i.test(f.name || ''))
  if (!torrents.length) {
    message.warning('请拖入 .torrent 种子文件（磁力链接请粘贴到上方输入框）')
    return
  }
  for (const f of torrents) {
    try {
      const bytes = new Uint8Array(await f.arrayBuffer())
      let bin = ''
      const CHUNK = 0x8000
      for (let i = 0; i < bytes.length; i += CHUNK) {
        bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK))
      }
      window.api && window.api.sendCommand({
        cmd: 'bt_download_file',
        b64: btoa(bin),
        album: btAlbum(),
      })
      message.success(`已提交种子：${f.name}`)
    } catch (err) {
      message.error(`读取种子失败：${f.name}`)
    }
  }
}
// 磁力站页面点击 magnet: 链接（主进程协议拦截转发）
// → 开启「自动接管」直接提交；否则确认后进 BT 下载
if (window.api && window.api.onBtMagnetClick) {
  window.api.onBtMagnetClick(({ url }) => {
    if (!url) return
    let auto = false
    try { auto = localStorage.getItem('bt_auto_takeover') === '1' } catch (e) { /* 隐私模式 */ }
    if (auto) {
      submitBt(url)
      message.success('已自动加入 BT 下载（进度在下载管理查看）')
      return
    }
    if (window.confirm(`检测到磁力链接，加入 BT 下载？\n\n${url.slice(0, 120)}`)) submitBt(url)
  })
}
function copyOne(u) {
  navigator.clipboard.writeText(u).then(() => message.success('链接已复制'))
}
function copyAll() {
  const txt = filtered.value.map(i => i.url).join('\n')
  navigator.clipboard.writeText(txt).then(() => message.success(`已复制 ${filtered.value.length} 条链接`))
}
function clearAll() {
  items.value = []
  segItems.value = []
  segTotal.value = 0
  downloaded.value = new Set()
}
</script>

<style scoped>
.sniff-root {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #16161a;
  color: #fff;
  overflow: hidden;
}
/* 顶部标题行：品牌/状态/提示各归其位，一律禁止收缩换行（防竖排文字挤压变形） */
.sniff-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px 6px;
  flex-shrink: 0;
  min-width: 0;
}
/* 筛选行：类型筛选 + 排序 + 批量操作；窄窗自动折行，不挤压标题行 */
.sniff-filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  row-gap: 6px;
  padding: 4px 14px 10px;
  border-bottom: 1px solid #2d2d33;
  flex-shrink: 0;
  min-width: 0;
}
/* 极窄窗口：筛选按钮组自身也允许折行 */
.sniff-filter-bar :deep(.n-radio-group) {
  flex-wrap: wrap;
  row-gap: 4px;
}
/* 抓取模式条（应用内 + 系统代理 mitm） */
.sniff-mode-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  row-gap: 6px;
  padding: 8px 14px;
  border-bottom: 1px solid #26262c;
  background: rgba(99, 226, 183, 0.04);
  flex-shrink: 0;
}
.sniff-mode-label { font-size: 12px; color: #888; }
.sniff-mode-hint { font-size: 11px; color: #666; margin-left: auto; }
.sniff-brand { font-weight: 600; font-size: 15px; white-space: nowrap; flex-shrink: 0; }
.sniff-dot { width: 8px; height: 8px; border-radius: 50%; background: #555; flex-shrink: 0; }
.sniff-dot.on { background: #63e2b7; box-shadow: 0 0 6px #63e2b7; }
.sniff-state {
  font-size: 12px;
  color: #aaa;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.sniff-hint {
  font-size: 11px;
  color: #666;
  margin-left: auto;
  white-space: nowrap;
  flex-shrink: 0;
}
.sniff-body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 10px;
  padding: 10px 14px 14px;
}
.sniff-browser {
  flex: 1.6;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sniff-nav { display: flex; align-items: center; gap: 6px; }
.sniff-address { flex: 1; }
.sniff-stage { flex: 1; min-height: 0; position: relative; }
.sniff-webview {
  width: 100%;
  height: 100%;
  border: 1px solid #2d2d33;
  border-radius: 6px;
  background: #fff;
}
.sniff-list {
  flex: 1;
  min-width: 380px;
  display: flex;
  flex-direction: column;
  border: 1px solid #2d2d33;
  border-radius: 6px;
  background: #1b1b20;
  overflow: hidden;
}
.sniff-empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #888;
  text-align: center;
  padding: 20px;
}
.sniff-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid #26262c;
}
.sniff-item-dl { opacity: 0.55; }
/* 疑似广告整条压暗：一个页面常同时抓到正片与贴片广告，视觉上必须区分开 */
.sniff-item-ad { opacity: 0.5; }
.sniff-sort { width: 108px; flex-shrink: 0; }
/* 智能判决徽标（后端 hls_probe 回流） */
.sniff-verdict {
  display: inline-block;
  font-size: 10px;
  padding: 0 5px;
  border-radius: 3px;
  margin-right: 4px;
  vertical-align: 1px;
}
.sniff-verdict-content { background: rgba(99, 226, 183, 0.18); color: #63e2b7; }
.sniff-verdict-unknown { background: rgba(255, 255, 255, 0.1); color: #aaa; }
.sniff-verdict-ad { background: rgba(208, 48, 48, 0.22); color: #ff7d86; }
.sniff-why { font-size: 10px; color: #b06a6a; margin-top: 2px; }
.sniff-badge {
  flex-shrink: 0;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  color: #fff;
}
.sniff-badge-video { background: #d3416f; }
.sniff-badge-audio { background: #3a7fd5; }
.sniff-badge-image { background: #2f9e6e; }
.sniff-badge-hls { background: #d08a2e; }
.sniff-badge-hlsseg { background: #8a8f99; }
.sniff-badge-other { background: #666; }
.sniff-item-main { flex: 1; min-width: 0; }
.sniff-name {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sniff-meta { font-size: 11px; color: #888; margin-top: 2px; }
.sniff-done { font-size: 11px; color: #63e2b7; flex-shrink: 0; }

/* ---------- B站解析卡（表世界同款逻辑，暗色适配嗅探窗主题） ---------- */
.sn-bili {
  border-bottom: 1px solid #2d2d33;
  background: linear-gradient(150deg, rgba(251, 113, 133, 0.10), rgba(106, 123, 255, 0.08));
  padding: 12px 12px;
}
.sn-bili.loading { opacity: 0.75; }
.sn-bili-head { display: flex; align-items: center; gap: 8px; }
.sn-bili-badge {
  font-size: 11px; font-weight: 700; color: #fff;
  background: linear-gradient(135deg, #fb7299, #ff9eb5);
  padding: 3px 9px; border-radius: 999px;
  flex-shrink: 0;
}
.sn-bili-state { font-size: 12px; color: #8a8f9e; }
.sn-bili-err { font-size: 12px; color: #ff7d86; }
.sn-bili-owner { font-size: 11.5px; color: #9aa0b2; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sn-bili-title {
  font-size: 13px; font-weight: 600; margin-top: 8px; color: #e8e8ee;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.sn-bili-pages { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 8px; max-height: 58px; overflow-y: auto; }
.sn-p-chip {
  border: 1px solid #3a3a44; cursor: pointer;
  font-size: 11px; color: #aab;
  background: #26262c;
  padding: 3px 8px; border-radius: 8px;
}
.sn-p-chip.on { background: #fb7299; color: #fff; border-color: #fb7299; font-weight: 600; }
.sn-bili-row { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.sn-bili-label { font-size: 11.5px; color: #8a8f9e; flex-shrink: 0; }
.sn-bili-select {
  flex: 1; height: 30px;
  border: 1px solid #3a3a44; border-radius: 9px;
  background: #26262c; color: #e0e0e6;
  font-size: 12px; padding: 0 8px; outline: none;
}
.sn-bili-audio { font-size: 12px; color: #c8cad4; font-weight: 500; }
.sn-bili-actions { display: flex; align-items: center; gap: 8px; margin-top: 10px; }
.sn-dl {
  border: none; cursor: pointer;
  font-size: 11.5px; font-weight: 600; color: #fff;
  background: linear-gradient(135deg, #ff5f8f, #ff8a5f);
  padding: 8px 10px; border-radius: 9px;
  flex: 1;
}
.sn-mini {
  border: none; cursor: pointer;
  font-size: 11.5px; color: #9aa0b2;
  background: transparent;
  padding: 6px 6px; border-radius: 8px;
  flex-shrink: 0;
}
.sn-mini:hover { background: rgba(255, 255, 255, 0.08); }

/* BT 下载弹窗（暗色风格，对齐嗅探窗配色） */
.sn-bt-body { display: flex; flex-direction: column; gap: 10px; }
.sn-bt-drop {
  border: 1.5px dashed #3a3a44; border-radius: 10px;
  padding: 14px 10px; text-align: center;
  font-size: 12.5px; color: #9aa0b2;
  background: #1d1d24; cursor: pointer;
  transition: border-color .2s, background .2s;
}
.sn-bt-drop:hover { border-color: #5a5a6e; background: #23232c; }
.sn-bt-foot { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.sn-bt-auto { display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: #b9bdc9; cursor: pointer; }
</style>
