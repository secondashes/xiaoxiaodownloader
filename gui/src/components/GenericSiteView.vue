<template>
  <!-- 通用站点视图（模块化架构 m4）：配置驱动 + 单命令总线 + 单状态回流。
       新站前端零新代码：siteConfigs.js 加配置 + 后端 site_template.py 复制填规则。
       命令上行：emit('gs-command', {site, cmd, ...payload}) → App 拼成 `${site}_${cmd}` 发后端；
       状态下行：props.state = App.gsStates[site]（后端 gs_state 事件写入）。 -->
  <div class="gs-view">
    <!-- 工具条（配置按钮/下拉 + 站点专属扩展插槽）；无 state 也渲染（切站首屏可点按钮触发加载） -->
    <div v-if="config && (!state || state.view === 'list')" class="gs-toolbar">
      <n-button
        v-for="(b, bi) in (config.toolbar.buttons || [])"
        :key="'b' + bi"
        size="tiny"
        :type="b.type || 'default'"
        :loading="b.cmd === 'home' && !!state && !!state.loading"
        :title="b.title"
        @click="sendCmd(b.cmd, b.args || {})"
      >{{ b.label }}</n-button>
      <n-select
        v-for="(sel, si) in (config.toolbar.selects || [])"
        :key="'s' + si"
        size="tiny"
        class="gs-ctl-select"
        :value="(state && state.toolbar && state.toolbar[sel.key] != null) ? state.toolbar[sel.key] : (sel.value != null ? sel.value : (sel.options[0] && sel.options[0].value))"
        :options="sel.options"
        :title="sel.label"
        @update:value="v => sendCmd(sel.cmd, { [sel.key]: v })"
      />
      <template v-if="batchEnabled && !(state && state.error)">
        <n-button
          class="batch-cta"
          size="small"
          :type="batch.mode.value ? 'warning' : 'primary'"
          :title="batch.mode.value ? '退出勾选模式' : '点击后当前列表进入勾选模式，勾选要下载的项目'"
          @click="batch.toggle()"
        >{{ batch.mode.value ? '取消勾选' : '批量下载' }}</n-button>
        <n-button
          v-if="batch.mode.value"
          size="tiny" type="error"
          :disabled="!batch.count.value"
          :loading="batch.running.value"
          title="开始下载勾选的项目"
          @click="startBatch"
        >开始下载{{ batch.count.value ? `(${batch.count.value})` : '' }}</n-button>
        <template v-if="batch.mode.value">
          <n-button size="tiny" title="勾选当前列表全部项目" @click="batch.selectAll(currentIds)">全选</n-button>
          <n-button size="tiny" title="勾选状态反转" @click="batch.invert(currentIds)">反选</n-button>
          <n-button size="tiny" title="清空全部勾选" @click="batch.clearChecked()">清空</n-button>
        </template>
        <span v-if="batch.running.value" class="gs-batch-progress">
          {{ (state && state.batchProgress && state.batchProgress.message) || '准备中...' }}（{{ (state && state.batchProgress && state.batchProgress.done) || 0 }}/{{ (state && state.batchProgress && state.batchProgress.total) || 0 }}）
        </span>
      </template>
      <slot name="toolbar-extra" />
      <input
        v-if="config.search"
        v-model="searchDraft"
        class="gs-search-input"
        :placeholder="config.search.placeholder || '搜索…'"
        @keyup.enter="doSearch"
      />
      <n-button v-if="config.search" size="tiny" type="primary" :loading="!!(state && state.loading)" @click="doSearch">搜索</n-button>
      <span v-if="state && state.total != null" class="gs-count">{{ formatCount(state.total) }} 个结果</span>
    </div>

    <!-- 列表视图：统一卡片网格（与工具条并存：两者同条件独立 v-if，v-else-if 会被工具条短路导致列表永不出） -->
    <n-scrollbar v-if="config && (!state || state.view === 'list')" class="gs-body" trigger="none">
      <div v-if="state && state.error" class="tw-follow-error">{{ state.error }}</div>
      <div v-else-if="state && state.loading && !(state.items || []).length" class="tw-follow-empty">
        <n-spin size="medium" />
        <span>正在获取内容...</span>
      </div>
      <div v-else-if="!((state && state.items) || []).length" class="tw-follow-empty">{{ config.list.empty }}</div>
      <div v-else class="search-grid">
          <div v-if="((state && state.items) || []).length && state && state.hasMore && config.list.loadMore" class="tw-browse-more" style="grid-column: 1 / -1; padding: 0 0 6px">
            <n-button size="tiny" quaternary block :loading="!!(state && state.loading)" @click="sendCmd('load-more', { page: ((state && state.page) || 1) + 1 })"
            >加载更多</n-button>
          </div>
        <div
          v-for="item in state.items"
          :key="item.album_url || item.video_id"
          class="search-card iw-card"
          :title="`${item.album_name}\n${item.author || ''}`"
          @click="batchEnabled && batch.mode.value ? batch.toggleItem(item[config.batch.idKey]) : sendCmd('open-detail', { item })"
        >
          <div class="thumb-wrapper">
            <img :src="item.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name" />
            <span v-if="item.duration" class="iw-thumb-duration">{{ item.duration }}</span>
            <div class="iw-thumb-stats">
              <span v-if="item.views != null">⬇ {{ formatCount(item.views) }}</span>
              <span v-if="item.rating">★ {{ item.rating }}</span>
            </div>
            <span
              v-if="batchEnabled && batch.mode.value"
              class="iw-batch-check"
              :class="{ checked: batch.checked.value.has(item[config.batch.idKey]) }"
            >{{ batch.checked.value.has(item[config.batch.idKey]) ? '✓' : '' }}</span>
            <button v-else class="card-favorite-btn" title="快速收藏到本地" @click.stop="sendCmd('favorite', { item })">♥</button>
          </div>
          <div class="card-name" :title="item.album_name">{{ trTitle(item.album_name) }}</div>
          <div class="iw-card-meta">
            <span v-if="config.card.showAuthor !== false && item.author" class="iw-card-author" :title="item.author">{{ item.author }}</span>
            <span v-if="config.card.showPosted !== false && item.posted" class="iw-card-time">{{ item.posted }}</span>
          </div>
          <slot name="card-extra" :item="item" />
        </div>
      </div>
      <div v-if="((state && state.items) || []).length && state && state.hasMore && config.list.loadMore" class="tw-browse-more">
        <n-button quaternary block :loading="!!(state && state.loading)" @click="sendCmd('load-more', { page: ((state && state.page) || 1) + 1 })">加载更多</n-button>
      </div>
    </n-scrollbar>

    <!-- 详情视图：返回 + 详情头 + 标签 + 文件列表 + 下载选中 -->
    <template v-if="config && state && state.view === 'detail'">
      <div class="tw-follow-toolbar">
        <n-button size="small" quaternary type="primary" @click="sendCmd(config.detail.backCmd, {})">← 返回</n-button>
        <span class="tw-follow-title iw-detail-title" :title="state.detail && state.detail.album_name">{{ state.detail && state.detail.album_name }}</span>
      </div>
      <n-scrollbar class="gs-body">
        <div v-if="state.error" class="tw-follow-error">{{ state.error }}</div>
        <template v-else-if="state.detail">
          <div class="iw-video-area" v-if="state.detail.play_url">
            <video
              :src="state.detail.play_url"
              :poster="state.detail.thumbnail"
              controls
              preload="metadata"
            />
          </div>
          <div v-else-if="state.detail.play_error" class="tw-follow-error">{{ state.detail.play_error }}</div>
          <div class="iw-video-area" v-else-if="state.detail.thumbnail">
            <img :src="state.detail.thumbnail" referrerpolicy="no-referrer" :alt="state.detail.album_name" />
          </div>
          <div v-if="state.detail.is_sample" class="gs-desc" title="匿名观看只有sample剪辑，完整版需登录FC2账号">
            ⚠ 当前为 sample 预览片段（付费/会员内容），完整版需登录 FC2 账号
          </div>
          <div class="iw-detail-stats">
            <span v-if="state.detail.author" class="gs-detail-author" title="查看上传者全部视频" @click="sendCmd('user', { user_id: state.detail.author_id || '', url: state.detail.author_url })">👤 {{ state.detail.author }}</span>
            <span v-if="state.detail.posted">📅 {{ state.detail.posted }}</span>
            <span v-if="state.detail.duration">⏱ {{ state.detail.duration }}</span>
            <span v-if="state.detail.quality">🎞 {{ state.detail.quality === 'sample' ? 'sample' : state.detail.quality.toUpperCase() }}</span>
          </div>
          <div v-if="state.detail.description" class="gs-desc">{{ state.detail.description }}</div>
          <div v-if="config.detail.showTags !== false && state.detail.tags && state.detail.tags.length" class="iw-tags">
            <n-tag
              v-for="t in state.detail.tags"
              :key="t"
              size="small" round type="info" class="iw-tag"
              title="点击搜索该标签"
              @click="sendCmd(config.detail.tagCmd, { tag: t })"
            >{{ t }}</n-tag>
          </div>
          <!-- 文件列表（与全站下载兼容的通用形状） -->
          <div class="gs-files-title">文件<template v-if="(state.files || []).length">（{{ state.files.length }}）</template></div>
          <div v-if="!(state.files || []).length" class="iw-comments-empty">暂无文件</div>
          <div v-for="(f, fi) in (state.files || [])" :key="fi" class="gs-file-row">
            <input type="checkbox" class="gs-file-check" v-model="checked" :value="fi" />
            <span class="gs-file-icon">{{ f.type === 'video' ? '🎬' : (f.type === 'audio' ? '♪' : '📄') }}</span>
            <span class="gs-file-name" :title="f.filename">{{ f.filename }}</span>
            <span v-if="f.size" class="gs-file-size">{{ formatCount(f.size) }}</span>
          </div>
          <div class="gs-download-bar">
            <span class="gs-selected">已选 {{ checked.length }} 个文件</span>
            <n-button
              size="small" type="primary"
              :disabled="!checked.length"
              @click="sendCmd(config.detail.downloadCmd, { files: checked.map(i => state.files[i]) }); checked = []"
            >下载选中 ({{ checked.length }})</n-button>
          </div>
          <!-- 相关推荐（设计稿必须区块）：点击链式开详情 -->
          <template v-if="(state.detail.related || []).length">
            <div class="gs-files-title">相关推荐</div>
            <div class="search-grid">
              <div
                v-for="r in state.detail.related"
                :key="r.video_id"
                class="search-card iw-card"
                :title="r.album_name"
                @click="sendCmd('open-detail', { item: r })"
              >
                <div class="thumb-wrapper">
                  <img :src="r.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="r.album_name" />
                  <span v-if="r.duration" class="iw-thumb-duration">{{ r.duration }}</span>
                </div>
                <div class="card-name" :title="r.album_name">{{ trTitle(r.album_name) }}</div>
              </div>
            </div>
          </template>
          <slot name="detail-extra" :detail="state.detail" />
        </template>
      </n-scrollbar>
    </template>

    <!-- 空态（有配置但 state 的 view 既非 list 也非 detail 的过渡态；list/detail 均已独立 v-if 渲染） -->
    <div v-if="config && state && state.view !== 'list' && state.view !== 'detail'" class="tw-follow-empty">{{ config.empty }}</div>
  </div>
</template>

<script setup>
// 通用站点视图组件（模块化架构 m4）。共用工具本地内置（PixivPanel/XhView 先例）。
import { ref } from 'vue'
import { NButton, NSelect, NTag, NSpin, NScrollbar } from 'naive-ui'
import { gsConfigFor } from '../siteConfigs.js'
import { useBatchSelection } from '../useBatchSelection.js'
import { computed } from 'vue'

const props = defineProps({
  site: { type: String, required: true },
  state: { type: Object, default: null },   // App.gsStates[site]
  translatedTitles: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['gs-command'])

const config = computed(() => gsConfigFor(props.site))

// 通用批量勾选（m7）：config.batch 配置时启用（交互规范见 useBatchSelection.js 头注释）
const batch = useBatchSelection()
const batchEnabled = computed(() => !!(config.value && config.value.batch))
// 当前列表全部可勾选 id（全选/反选用）
const currentIds = computed(() => {
  const st = state.value
  return (st && (st.items || []))
    .filter(it => it && it[config.value.batch.idKey] != null && it[config.value.batch.idKey] !== '')
    .map(it => it[config.value.batch.idKey])
})

// 文件勾选（详情视图；切详情时由 key 重挂载/状态覆盖自然复位）
const checked = ref([])

// 站内搜索（config.search 配置时工具条出现输入框）
const searchDraft = ref('')
function doSearch() {
  const q = (searchDraft.value || '').trim()
  if (!q) return
  sendCmd((config.value.search && config.value.search.cmd) || 'search', { query: q, page: 1 })
}

function sendCmd(cmd, payload = {}) {
  // 必须带 site：App.handleGsCommand 以 evt.site 拼 `${site}_${cmd}`（缺失会被首行守卫丢弃）
  emit('gs-command', { site: props.site, cmd, ...payload })
}

// 批量开始：收集当前列表勾选的完整卡片发后端（通用 gs_batch_download 按 site 分发；
// 各站 batch.downloadCmd 统一 'batch_download'，handleGsCommand 拼 `${site}_batch_download`）
function startBatch() {
  const chosen = (state.value && state.value.items || [])
    .filter(i => batch.checked.value.has(String(i[config.value.batch.idKey])))
  const cmd = (config.value.batch && config.value.batch.downloadCmd) || 'batch_download'
  const out = batch.start(() => chosen.map(i => String(i[config.value.batch.idKey])))
  if (out) sendCmd(cmd, { items: chosen })
}

function trTitle(name) {
  if (!name) return '未命名'
  return props.translatedTitles[name] || name
}

function formatCount(n) {
  if (n == null || n === '') return ''
  const v = Number(n)
  if (!v || v <= 0) return '0'
  if (v >= 10000) return (v / 10000).toFixed(1).replace(/\.0$/, '') + '万'
  return Number(v).toLocaleString('zh-CN')
}
</script>

<style scoped>
/* 通用站点视图样式（共用类本地副本：search-grid/search-card/tw-follow-* 等，RightPanel 为 scoped） */
.gs-view {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.gs-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 6px 12px;
}

.gs-ctl-select {
  width: 150px;
}

.gs-batch-progress {
  font-size: 12px;
  color: #f0a020;
  white-space: nowrap;
}

.gs-count {
  margin-left: auto;
  font-size: 12px;
  color: #7a7a85;
}

.gs-body {
  flex: 1;
  min-height: 0;
}

.gs-count {
  margin-left: auto;
}
.gs-search-input {
  width: 200px;
  padding: 2px 8px;
  border: 1px solid var(--n-border-color, #555);
  border-radius: 4px;
  background: transparent;
  color: inherit;
  font-size: 12px;
}
.gs-detail-author {
  cursor: pointer;
}
.gs-detail-author:hover {
  text-decoration: underline;
}
.gs-desc {
  margin: 0 14px 10px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: #d0d0d6;
  white-space: pre-wrap;
  word-break: break-word;
}

.gs-files-title {
  padding: 6px 14px 8px;
  font-size: 13px;
  font-weight: 600;
  color: #e0e0e6;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.gs-file-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  font-size: 12.5px;
  color: #d0d0d6;
}

.gs-file-row:hover {
  background: rgba(255, 255, 255, 0.03);
}

.gs-file-check {
  flex-shrink: 0;
}

.gs-file-icon {
  flex-shrink: 0;
}

.gs-file-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gs-file-size {
  flex-shrink: 0;
  color: #7a7a85;
  font-size: 11px;
}

.gs-download-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px 14px;
}

.gs-selected {
  font-size: 12px;
  color: #8f8f98;
}

/* 共用类副本（与 RightPanel 同源，保持两处同步） */
.search-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 12px;
  padding: 4px 16px 10px;
}

.search-card {
  background: #1e1e22;
  border: 1px solid #2d2d33;
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.15s, transform 0.15s;
}

.search-card:hover {
  border-color: #63e2b7;
  transform: translateY(-2px);
}

.thumb-wrapper {
  position: relative;
  aspect-ratio: 4 / 3;
  background: #26262b;
  overflow: hidden;
}

.thumb-wrapper img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.card-name {
  padding: 8px 10px;
  font-size: 12.5px;
  color: #e0e0e6;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}

.iw-card-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px 8px 8px;
  font-size: 11px;
  color: #8f8f98;
}

.iw-card-author {
  color: #63e2b7;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.iw-card-time {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.iw-thumb-duration {
  position: absolute;
  left: 6px;
  bottom: 6px;
  background: rgba(0, 0, 0, 0.65);
  color: #e0e0e6;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
}

.iw-thumb-stats {
  position: absolute;
  right: 6px;
  bottom: 6px;
  display: flex;
  gap: 8px;
  background: rgba(0, 0, 0, 0.55);
  color: #e0e0e6;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
}

.card-favorite-btn {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #ffffff;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s, transform 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.search-card:hover .card-favorite-btn {
  opacity: 1;
}

.card-favorite-btn:hover {
  color: #ff6b81;
  transform: scale(1.15);
}

.iw-video-area {
  background: #000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.iw-video-area img {
  width: 100%;
  max-height: 52vh;
  object-fit: contain;
  display: block;
}

.iw-detail-stats {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding: 8px 14px 2px;
  font-size: 12px;
  color: #8f8f98;
}

.iw-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 14px 10px;
}

.iw-tag {
  cursor: pointer;
}

.iw-comments-empty {
  padding: 0 14px 14px;
  font-size: 12px;
  color: #7a7a85;
}

.tw-follow-error {
  margin: 12px;
  padding: 10px 14px;
  border-radius: 6px;
  background: rgba(233, 68, 75, 0.12);
  color: #ff7d86;
  font-size: 13px;
  line-height: 1.6;
}

.tw-follow-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 48px 16px;
  color: #5f5f5f;
  font-size: 13px;
}

.tw-browse-more {
  padding: 6px 12px 16px;
}

.tw-follow-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 2px 0;
}

.tw-follow-title {
  font-size: 14px;
  font-weight: 600;
  color: #ddd;
}

.iw-detail-title {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
