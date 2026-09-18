<template>
  <!-- Hanime1 (H站) 搜索选项栏：分类 + 排序 + 主页/用户中心（分类浏览复刻原版分类按钮） -->
  <div v-if="mode === 'options'" class="ex-search-options">
    <div class="ex-cats">
      <span class="ex-cats-label">分类：</span>
      <button
        class="ex-cat-chip"
        :class="{ on: !settings.hanime_genre }"
        title="全部分类（回到主页分区）"
        @click="setHaGenre('')"
      >全部</button>
      <button
        v-for="g in haGenres"
        :key="g"
        class="ex-cat-chip"
        :class="{ on: settings.hanime_genre === g }"
        :title="`按「${g}」分类浏览`"
        @click="setHaGenre(g)"
      >{{ g }}</button>
      <div class="ex-filter-item ha-sort-item">
        <span class="ex-filter-label">排序</span>
        <n-select
          :value="settings.hanime_sort"
          :options="haSortOptions"
          size="tiny"
          class="ha-sort-select"
          placeholder="默認"
          @update:value="v => setHaSort(v || '')"
        />
      </div>
    </div>
    <div class="ex-cats">
      <n-button
        size="tiny"
        :type="haView === 'home' ? 'primary' : 'default'"
        :loading="haHomeLoading && haView === 'home'"
        title="回到主页各分区（最新上市/最新上傳 + 分类）"
        @click="$emit('ha-home')"
      >主页</n-button>
      <n-button
        size="tiny"
        :type="haView === 'user' && haUserTab === 'history' ? 'primary' : 'default'"
        :loading="haUserLoading && haView === 'user' && haUserTab === 'history'"
        title="我看过的视频（需登录）"
        @click="$emit('hanime-user-videos', 'history')"
      >觀看紀錄</n-button>
      <n-button
        size="tiny"
        :type="haView === 'user' && haUserTab === 'saves' ? 'primary' : 'default'"
        :loading="haUserLoading && haView === 'user' && haUserTab === 'saves'"
        title="收藏（稍後觀看）的视频（需登录）"
        @click="$emit('hanime-user-videos', 'saves')"
      >稍後觀看</n-button>
      <n-button
        size="tiny"
        :type="haView === 'user' && haUserTab === 'likes' ? 'primary' : 'default'"
        :loading="haUserLoading && haView === 'user' && haUserTab === 'likes'"
        title="我点赞过的视频（需登录）"
        @click="$emit('hanime-user-videos', 'likes')"
      >讚好的影片</n-button>
      <n-button
        size="tiny"
        :type="haView === 'user' && haUserTab === 'uploaded' ? 'primary' : 'default'"
        :loading="haUserLoading && haView === 'user' && haUserTab === 'uploaded'"
        title="我上传的视频（需登录）"
        @click="$emit('hanime-user-videos', 'uploaded')"
      >上傳的影片</n-button>
      <n-button
        size="tiny"
        :type="haView === 'user' && haUserTab === 'uploading' ? 'primary' : 'default'"
        :loading="haUserLoading && haView === 'user' && haUserTab === 'uploading'"
        title="审核中的视频（需登录）"
        @click="$emit('hanime-user-videos', 'uploading')"
      >審核中</n-button>
      <n-button
        class="batch-cta"
        size="small"
        :type="haBatchMode ? 'warning' : 'primary'"
        :title="haBatchMode ? '退出勾选模式' : '点击后当前列表进入勾选模式，勾选要下载的视频'"
        @click="$emit('toggle-ha-batch')"
      >{{ haBatchMode ? '取消勾选' : '批量下载' }}</n-button>
      <n-button
        v-if="haBatchMode"
        size="tiny"
        type="error"
        :disabled="!haBatchChecked.size"
        :loading="haBatchRunning"
        :title="`开始下载勾选的 ${haBatchChecked.size} 个视频（自动取最高画质）`"
        @click="$emit('start-ha-batch')"
      >开始下载{{ haBatchChecked.size ? `(${haBatchChecked.size})` : '' }}</n-button>
      <template v-if="haBatchMode">
        <n-button size="tiny" title="勾选当前列表全部视频" @click="$emit('select-ha-batch', 'all')">全选</n-button>
        <n-button size="tiny" title="勾选状态反转" @click="$emit('select-ha-batch', 'invert')">反选</n-button>
        <n-button size="tiny" title="清空全部勾选" @click="$emit('select-ha-batch', 'clear')">清空</n-button>
      </template>
      <span v-if="haBatchRunning" class="iw-batch-progress ha-batch-progress">
        {{ haBatchProgress.message || '准备中...' }}（{{ haBatchProgress.done }}/{{ haBatchProgress.total }}）
      </span>
    </div>
  </div>

  <!-- 主视图：详情 / 主页分区 / 用户中心（与拆分前 v-else-if 链同序） -->
  <div v-else-if="haView === 'detail'" class="iw-detail">
    <div v-if="haDetailLoading && !haDetail" class="tw-follow-empty">
      <n-spin size="medium" />
      <span>正在获取视频详情...</span>
    </div>
    <template v-else-if="haDetail">
      <div class="tw-follow-toolbar">
        <n-button size="small" quaternary type="primary" @click="$emit('ha-detail-back')">← 返回</n-button>
        <span class="tw-follow-title iw-detail-title" :title="haDetail.album_name">{{ haDetail.album_name }}</span>
        <n-button
          size="tiny"
          tertiary
          type="primary"
          title="解析视频文件并加入下载列表"
          @click="$emit('open-album', haDetail)"
        >解析下载</n-button>
      </div>
      <n-scrollbar class="iw-detail-scroll">
        <div class="iw-video-area">
          <!-- 视频走本地媒体代理（带 H站代理转发） -->
          <video
            v-if="haDetail.video_url"
            :src="proxied(haDetail.video_url)"
            controls
            preload="metadata"
            :poster="haDetail.thumbnail"
          />
          <img v-else :src="haDetail.thumbnail" referrerpolicy="no-referrer" :alt="haDetail.album_name" />
        </div>
        <div class="iw-detail-stats">
          <span v-if="haDetail.views">👁 {{ haDetail.views }}</span>
          <span v-if="haDetail.rating">👍 {{ haDetail.rating }}</span>
          <span v-if="haDetail.duration">⏱ {{ haDetail.duration }}</span>
          <span v-if="haDetail.post_date">{{ haDetail.post_date }}</span>
        </div>
        <!-- 上传者 + 收藏（稍後觀看） -->
        <div class="iw-author-row">
          <span class="iw-author-name ha-uploader">上传者：{{ haDetail.uploader || '未知' }}</span>
          <n-button
            size="tiny"
            ghost
            :type="haDetail.saved ? 'warning' : 'primary'"
            :title="haDetail.saved ? '已收藏（点击取消稍後觀看）' : '加入稍後觀看（需登录）'"
            @click="$emit('hanime-save-video', haDetail.video_id, !haDetail.saved)"
          >{{ haDetail.saved ? '★ 已收藏' : '☆ 收藏' }}</n-button>
        </div>
        <div v-if="haDetail.description" class="iw-body">{{ haDetail.description }}</div>
        <div v-if="haDetail.tags && haDetail.tags.length" class="iw-tags">
          <n-tag
            v-for="t in haDetail.tags"
            :key="t"
            size="small"
            round
            type="info"
            class="iw-tag"
            title="点击搜索该标签"
            @click="$emit('hanime-search-tag', t)"
          >{{ t }}</n-tag>
        </div>
        <!-- 评论区（发表评论需登录） -->
        <div class="iw-comments-title">评论<template v-if="haComments.length">（{{ haComments.length }}）</template></div>
        <div class="ha-comment-input-row">
          <n-input
            v-model:value="haCommentInput"
            size="small"
            type="textarea"
            :rows="2"
            maxlength="500"
            placeholder="发表评论（需登录）..."
          />
          <n-button
            size="small"
            type="primary"
            :disabled="!haCommentInput.trim()"
            :loading="haCommentPosting"
            @click="postHaComment"
          >发表</n-button>
        </div>
        <div v-if="!haComments.length" class="iw-comments-empty">暂无评论</div>
        <div
          v-for="(c, i) in haComments"
          :key="c.id || i"
          class="iw-comment"
          :class="{ 'ha-comment-reply': c.is_reply }"
        >
          <img v-if="c.avatar" class="iw-comment-avatar" :src="c.avatar" referrerpolicy="no-referrer" alt="" />
          <span v-else class="iw-comment-avatar iw-comment-avatar-empty">@</span>
          <div class="iw-comment-main">
            <div class="iw-comment-head">
              <span class="iw-comment-name">{{ c.username || '匿名' }}</span>
              <span class="iw-comment-time">{{ c.posted }}</span>
            </div>
            <div class="iw-comment-body">{{ c.text }}</div>
          </div>
        </div>
        <!-- 相关推荐（watch 页「相關影片」标签页；后端详情一次带全，点击链式开详情可逐级返回） -->
        <div v-if="haRelated.length" class="ha-related">
          <div class="iw-comments-title">相关推荐</div>
          <div class="search-grid ha-related-grid">
            <div
              v-for="item in haRelated"
              :key="item.video_id"
              class="search-card iw-card"
              :title="`${item.album_name}\n点击查看详情`"
              @click="$emit('ha-open-detail', item)"
            >
              <div class="thumb-wrapper">
                <img :src="item.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name" />
                <span v-if="item.duration" class="iw-thumb-duration">{{ item.duration }}</span>
                <button class="card-favorite-btn" title="快速收藏到本地" @click.stop="handleQuickFavorite(item)">♥</button>
              </div>
              <div class="card-name" :title="item.album_name">{{ trTitle(item.album_name) }}</div>
              <div class="iw-card-meta">
                <span class="iw-card-author">{{ item.author || '未知' }}</span>
              </div>
            </div>
          </div>
        </div>
      </n-scrollbar>
    </template>
  </div>

  <div v-else-if="haView === 'home'" class="tw-follow-view">
    <div class="tw-follow-toolbar">
      <span class="tw-follow-title">Hanime1 · 主页</span>
      <span v-if="haSections.length" class="tw-follow-count">{{ haSections.length }} 个分区</span>
      <n-button size="tiny" quaternary :loading="haHomeLoading" @click="$emit('ha-home')">刷新</n-button>
    </div>
    <n-scrollbar class="tw-follow-scroll">
      <div v-if="haHomeError" class="tw-follow-error">{{ haHomeError }}</div>
      <div v-else-if="haHomeLoading && !haSections.length" class="tw-follow-empty">
        <n-spin size="medium" />
        <span>正在获取主页内容...</span>
      </div>
      <div v-else-if="!haSections.length" class="tw-follow-empty">暂无内容</div>
      <div v-else class="ha-sections">
        <div v-for="(sec, si) in haSections" :key="si" class="ha-section">
          <div class="ha-section-title">
            <span>{{ sec.title }}</span>
            <n-button
              v-if="haGenres.includes(sec.title)"
              size="tiny"
              quaternary
              type="primary"
              :title="`查看「${sec.title}」分类的更多视频`"
              @click="setHaGenre(sec.title)"
            >查看更多 →</n-button>
          </div>
          <div class="search-grid ha-section-grid">
            <div
              v-for="item in sec.items"
              :key="item.video_id || item.album_url"
              class="search-card iw-card"
              :class="{ 'iw-batch-checked': haBatchMode && haBatchChecked.has(item.video_id) }"
              :title="`${item.album_name}\n${haBatchMode ? '点击勾选/取消勾选' : '点击查看完整信息'}`"
              @click="haBatchMode ? $emit('toggle-ha-batch-item', item.video_id) : $emit('ha-open-detail', item)"
            >
              <div class="thumb-wrapper">
                <img :src="item.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name" />
                <span v-if="item.duration" class="iw-thumb-duration">{{ item.duration }}</span>
                <div class="iw-thumb-stats">
                  <span v-if="item.views">👁 {{ item.views }}</span>
                  <span v-if="item.rating">👍 {{ item.rating }}</span>
                </div>
                <span v-if="haBatchMode" class="iw-batch-check" :class="{ checked: haBatchChecked.has(item.video_id) }">{{ haBatchChecked.has(item.video_id) ? '✓' : '' }}</span>
                <button v-if="!haBatchMode" class="card-favorite-btn" title="快速收藏到本地" @click.stop="handleQuickFavorite(item)">♥</button>
              </div>
              <div class="card-name" :title="item.album_name">{{ trTitle(item.album_name) }}</div>
              <div class="iw-card-meta">
                <span class="iw-card-author">{{ item.author || '未知' }}</span>
                <span v-if="item.posted" class="iw-card-time">{{ item.posted }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </n-scrollbar>
  </div>

  <div v-else-if="haView === 'user'" class="tw-follow-view">
    <div class="tw-follow-toolbar">
      <n-button size="small" quaternary type="primary" @click="$emit('ha-home')">← 返回</n-button>
      <span class="tw-follow-title">{{ haUserLabel || '用户中心' }}</span>
      <span v-if="haUserItems.length" class="tw-follow-count">
        {{ haUserItems.length }} 个视频<template v-if="haUserHasMore">（可继续加载）</template>
      </span>
      <n-button
        size="tiny"
        quaternary
        :loading="haUserLoading"
        title="刷新当前列表"
        @click="$emit('hanime-user-videos', haUserTab)"
      >刷新</n-button>
    </div>
    <n-scrollbar class="tw-follow-scroll">
      <div v-if="haUserLoading && !haUserItems.length" class="tw-follow-empty">
        <n-spin size="medium" />
        <span>正在获取列表...</span>
      </div>
      <div v-else-if="!haUserItems.length" class="tw-follow-empty">暂无视频</div>
      <div v-else class="search-grid">
          <div v-if="haUserItems.length && haUserHasMore" class="tw-browse-more" style="grid-column: 1 / -1; padding: 0 0 6px">
            <n-button size="tiny" quaternary block :loading="haUserLoading" @click="$emit('hanime-user-videos', haUserTab, haUserPage + 1)"
            >加载更多</n-button>
          </div>
        <div
          v-for="item in haUserItems"
          :key="item.video_id || item.album_url"
          class="search-card iw-card"
          :class="{ 'iw-batch-checked': haBatchMode && haBatchChecked.has(item.video_id) }"
          :title="`${item.album_name}\n${haBatchMode ? '点击勾选/取消勾选' : '点击查看完整信息'}`"
          @click="haBatchMode ? $emit('toggle-ha-batch-item', item.video_id) : $emit('ha-open-detail', item)"
        >
          <div class="thumb-wrapper">
            <img :src="item.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name" />
            <span v-if="item.duration" class="iw-thumb-duration">{{ item.duration }}</span>
            <div class="iw-thumb-stats">
              <span v-if="item.views">👁 {{ item.views }}</span>
              <span v-if="item.rating">👍 {{ item.rating }}</span>
            </div>
            <span v-if="haBatchMode" class="iw-batch-check" :class="{ checked: haBatchChecked.has(item.video_id) }">{{ haBatchChecked.has(item.video_id) ? '✓' : '' }}</span>
            <button v-if="!haBatchMode" class="card-favorite-btn" title="快速收藏到本地" @click.stop="handleQuickFavorite(item)">♥</button>
          </div>
          <div class="card-name" :title="item.album_name">{{ trTitle(item.album_name) }}</div>
          <div class="iw-card-meta">
            <span class="iw-card-author">{{ item.author || '未知' }}</span>
            <span v-if="item.posted" class="iw-card-time">{{ item.posted }}</span>
          </div>
        </div>
      </div>
      <div v-if="haUserItems.length && haUserHasMore" class="tw-browse-more">
        <n-button
          quaternary
          block
          :loading="haUserLoading"
          @click="$emit('hanime-user-videos', haUserTab, haUserPage + 1)"
        >加载更多</n-button>
      </div>
    </n-scrollbar>
  </div>
</template>

<script setup>
// Hanime1 (H站) 视图组件（从 RightPanel.vue 拆出，重构 f3，沿用 PixivPanel/XhView/ExhentaiView 模式）。
// 批量勾选状态（haBatchMode/haBatchChecked）被 工具栏/主视图/搜索结果网格 三处共用 → 留守
// RightPanel，经 props 下发 + toggle-ha-batch / toggle-ha-batch-item / start-ha-batch 事件上行。
import { ref, computed } from 'vue'
import { NButton, NInput, NSelect, NTag, NSpin, NScrollbar } from 'naive-ui'

const props = defineProps({
  mode: { type: String, default: 'main' },               // options=搜索选项栏 | main=主视图
  site: { type: String, default: 'bunkr' },
  settings: { type: Object, default: () => ({}) },        // ha-genre/ha-sort 读取
  haView: { type: String, default: '' },                // ''=空态 | home | detail | user
  haDetail: { type: Object, default: null },
  haDetailLoading: { type: Boolean, default: false },
  haComments: { type: Array, default: () => [] },
  haSections: { type: Array, default: () => [] },   // 主页分区 [{title, items: []}]
  haHomeLoading: { type: Boolean, default: false },
  haHomeError: { type: String, default: '' },
  haGenres: { type: Array, default: () => [] },     // 分类列表（裏番/3DCG/...）
  haSorts: { type: Array, default: () => [] },      // 排序列表（后端 HANIME_SORTS）
  haUserItems: { type: Array, default: () => [] },
  haUserLoading: { type: Boolean, default: false },
  haUserHasMore: { type: Boolean, default: false },
  haUserPage: { type: Number, default: 1 },
  haUserLabel: { type: String, default: '' },       // 当前 tab 中文名
  haUserTab: { type: String, default: 'history' },
  haBatchMode: { type: Boolean, default: false },   // 批量勾选模式（状态在 RightPanel）
  haBatchChecked: { type: Set, default: () => new Set() }, // 勾选的 video_id（状态在 RightPanel）
  haBatchRunning: { type: Boolean, default: false },
  haBatchProgress: { type: Object, default: () => ({ done: 0, total: 0, message: '' }) },
  translatedTitles: { type: Object, default: () => ({}) },     // {原标题: 译文}，展示时回填
  mediaProxyPort: { type: Number, default: 0 },             // 媒体代理端口（详情视频走本地代理）
})

const emit = defineEmits([
  'ha-home', 'ha-detail-back', 'ha-open-detail', 'hanime-user-videos', 'hanime-save-video',
  'hanime-search-tag', 'hanime-add-comment', 'open-album', 'update:ha-search', 'add-favorite', 'select-ha-batch',
  'toggle-ha-batch', 'toggle-ha-batch-item', 'start-ha-batch',
])

// ---------- 共用工具（PixivPanel/XhView 先例：本地内置，不依赖 RightPanel 作用域） ----------
// 远端直链 → 本地代理 URL（走 cookie/代理，国内可播）
function proxied(url) {
  if (!url) return ''
  if (!props.mediaProxyPort) return url
  if (url.startsWith('thumb://') || url.startsWith('http://127.0.0.1')) return url
  return `http://127.0.0.1:${props.mediaProxyPort}/media?url=${encodeURIComponent(url)}`
}

// 自动翻译：把原标题替换为译文（无译文回退原标题；空值返回 '未命名'）
function trTitle(name) {
  if (!name) return '未命名'
  return props.translatedTitles[name] || name
}

// 快速收藏到本地（卡片爱心按钮）
function handleQuickFavorite(item) {
  emit('add-favorite', {
    type: item.type || 'gallery',
    title: item.album_name || item.title || '',
    url: item.album_url || item.url || '',
    site: item.site || props.site,
    search_query: '',
    thumbnail: item.thumbnail || '',
  })
}

// 相关推荐（后端 hanime_video_detail 一次带全；无则整块不渲染）
const haRelated = computed(() => (props.haDetail && props.haDetail.related) || [])

// ============================
// Hanime1 (H站) 搜索选项 / 评论
// ============================
// 排序下拉选项（后端 HANIME_SORTS）
const haSortOptions = computed(() => (props.haSorts || []).map(s => ({ label: s, value: s })))

// 分类/排序切换（发给 App.vue 存设置并决定 搜索/分类浏览/主页）
function setHaGenre(genre) {
  emit('update:ha-search', { genre: genre || '', sort: props.settings.hanime_sort || '' })
}

function setHaSort(sort) {
  emit('update:ha-search', { genre: props.settings.hanime_genre || '', sort: sort || '' })
}

// 详情页发表评论（需登录；结果事件由 App.vue 弹提示并自动刷新评论）
const haCommentInput = ref('')
const haCommentPosting = ref(false)

function postHaComment() {
  const text = (haCommentInput.value || '').trim()
  if (!text || !props.haDetail || !props.haDetail.video_id) return
  haCommentPosting.value = true
  emit('hanime-add-comment', { video_id: props.haDetail.video_id, text })
  haCommentInput.value = ''
  // 提交状态由评论结果事件驱动，超时兜底复位
  setTimeout(() => { haCommentPosting.value = false }, 5000)
}
</script>

<style scoped>
/* HanimeView 样式：ha-* 自 RightPanel 迁出；其余为共用类副本（RightPanel 仍被其他站点使用），保持原级联顺序 */

.search-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 12px;
}
/* ========== ExHentai 搜索选项栏（复刻原版搜索页过滤按钮） ========== */
.ex-search-options {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 12px;
  background: #191a1d;
  border-bottom: 1px solid #2d2d33;
}
/* 分类复选按钮（原版分类复选框的按钮化样式） */
.ex-cat-chip {
  background: #2d2d33;
  color: #b8b8b8;
  border: 1px solid #3d3d45;
  border-radius: 4px;
  font-size: 11px;
  padding: 2px 8px;
  cursor: pointer;
  line-height: 1.5;
  transition: background 0.1s ease, color 0.1s ease, border-color 0.1s ease;
}
.ex-cat-chip:hover {
  background: #3d3d45;
  color: #fff;
}
.ex-cat-chip.on {
  background: #4a7c3a;
  border-color: #5a9c46;
  color: #dff5cf;
}
/* Iwara 视频卡片：作者 + 播放/点赞/日期 元信息行 */
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
/* Iwara 缩略图角标：时长 / R-18 / 播放与爱心 */
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
/* Iwara 视频详情页 */
.iw-detail {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;  /* ASMR 悬浮播放器锚点 */
}
.iw-detail-title {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.iw-detail-scroll {
  flex: 1;
  min-height: 0;
}
.iw-video-area {
  background: #000;
  display: flex;
  align-items: center;
  justify-content: center;
}
.iw-video-area video,
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
.iw-author-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
}
.iw-author-name {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  font-weight: 600;
  color: #63e2b7;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.iw-body {
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
.iw-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 14px 10px;
}
.iw-tag {
  cursor: pointer;
}
.iw-comments-title {
  padding: 6px 14px 8px;
  font-size: 13px;
  font-weight: 600;
  color: #e0e0e6;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}
.iw-comments-empty {
  padding: 0 14px 14px;
  font-size: 12px;
  color: #7a7a85;
}
.iw-comment {
  display: flex;
  gap: 10px;
  padding: 8px 14px;
}
.iw-comment:hover {
  background: rgba(255, 255, 255, 0.03);
}
.iw-comment-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  object-fit: cover;
  cursor: pointer;
  flex-shrink: 0;
}
.iw-comment-main {
  flex: 1;
  min-width: 0;
}
.iw-comment-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.iw-comment-name {
  font-size: 12px;
  font-weight: 600;
  color: #63e2b7;
  cursor: pointer;
}
.iw-comment-time {
  font-size: 11px;
  color: #7a7a85;
}
.iw-comment-body {
  margin-top: 3px;
  font-size: 13px;
  color: #d0d0d6;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
/* Iwara 批量解析下载：勾选框与选中态 */
.iw-batch-check {
  position: absolute;
  right: 6px;
  top: 6px;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  border: 1.5px solid rgba(255, 255, 255, 0.8);
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  line-height: 18px;
  text-align: center;
  z-index: 5;
}
.iw-batch-check.checked {
  background: #18a058;
  border-color: #36ad6a;
}
.iw-batch-checked {
  outline: 2px solid #18a058;
  outline-offset: -2px;
}
.iw-batch-progress {
  color: #f0a020;
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
/* 搜索卡片爱心收藏按钮（悬浮显示"快速收藏到本地"） */
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
/* 点击反馈：卡片/行按下时立即有视觉响应（消除"不知道点没点上"的感觉） */
.ex-tr:active,
.search-card:active {
  transform: scale(0.985);
  transition: transform 0.08s ease;
  filter: brightness(1.15);
}
.tw-follow-view {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.tw-follow-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  flex-shrink: 0;
}
.tw-follow-title {
  font-size: 14px;
  font-weight: 600;
  color: #e0e0e6;
}
.tw-follow-count {
  font-size: 12px;
  color: #7a7a85;
}
.tw-follow-scroll {
  flex: 1;
  min-height: 0;
}
/* 浏览模式"加载更多"区域 */
.tw-browse-more {
  padding: 6px 12px 16px;
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
/* JavDB 详情演员/标签可点击 */
.iw-tag.iw-tag-click { cursor: pointer; }
.iw-tag.iw-tag-click:hover { opacity: 0.75; }
/* ==================== Hanime1 (H站) 专属样式 ==================== */
/* 详情页：上传者行 */
.ha-uploader {
  font-size: 13px;
}
/* 详情页：发表评论输入行 */
.ha-comment-input-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 0 14px 10px;
}
.ha-comment-input-row .n-input {
  flex: 1;
}
/* 楼中楼回复缩进 */
.ha-comment-reply {
  padding-left: 46px;
  border-left: 2px solid rgba(99, 226, 183, 0.25);
  margin-left: 14px;
}
/* 搜索选项栏：排序下拉 */
.ha-sort-item {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: 10px;
}
.ha-sort-select {
  width: 130px;
}
/* 主页分区列表 */
.ha-sections {
  padding: 10px 14px 20px;
}
.ha-section {
  margin-bottom: 18px;
}
.ha-section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #e0e0e6;
}
.ha-section-grid {
  margin-top: 0;
}

/* 详情页相关推荐（对齐 AsmrView gs-related 的尺寸与留白） */
.ha-related {
  margin-top: 4px;
}

.ha-related-grid {
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  padding: 0 14px 10px;
}
/* 批量下载进度（复用 iw-batch-progress 样式） */
.ha-batch-progress {
  margin-left: 4px;
}
/* 日间模式适配 */
html.light-mode .ha-section-title,
html.light-mode .ha-uploader {
  color: #333;
}
html.light-mode .ha-comment-reply {
  border-left-color: rgba(0, 128, 90, 0.25);
}
</style>
