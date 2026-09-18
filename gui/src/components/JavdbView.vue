<template>
  <!-- JavDB 工具栏：导航 / 热搜 / 标签词库 / 主页推荐（搜索类型折叠卡片在 RightPanel url-bar 内，留守） -->
  <div v-if="mode === 'toolbar'" class="javdb-toolbar">
    <!-- 第一行：导航下拉（加大加粗）+ 用户信息 -->
    <div class="jt-row jt-navrow">
      <span class="jt-label">导航</span>
      <n-dropdown
        v-for="m in javdbNavMenus"
        :key="m.key"
        trigger="click"
        :options="m.options.map(o => ({ label: o.label, key: o.key }))"
        @select="k => onNavPick(m.key, k)"
      >
        <button class="ex-cat-chip">{{ m.label }} ▾</button>
      </n-dropdown>
      <span class="jt-flex"></span>
      <!-- 用户信息下拉：近期浏览/想看/看过/我的清单/收藏 x5（需登录，URL 实测后校准） -->
      <n-dropdown trigger="click" :options="javdbUserMenus.map(m => ({ label: m.label, key: m.key }))" @select="onUserMenuPick">
        <button class="ex-cat-chip" :title="javdbUser ? `已登录：${javdbUser}` : '未登录（点击查看用户中心页面）'">
          👤 {{ javdbUser || '未登录' }} ▾
        </button>
      </n-dropdown>
      <button v-if="javdbUser" class="ex-cat-chip jt-logout" title="退出 JavDB 登录（清除 cookie）" @click="$emit('javdb-logout')">退出</button>
    </div>
    <!-- 第三行：热搜关键词 -->
    <div v-if="javdbHot.length" class="jt-row">
      <span class="jt-label">热搜</span>
      <button v-for="kw in javdbHot" :key="kw" class="ex-cat-chip jt-hot" @click="$emit('javdb-hot', kw)">{{ kw }}</button>
    </div>
    <!-- 第四行：tags 内容页（5 模式 tab 一行；文字词条多选后组合筛选；词条按分组整行排布，超高滚动） -->
    <div v-if="activeVocabMode" class="jt-vocab">
      <div class="jt-row">
        <span class="jt-label">标签页</span>
        <button
          v-for="m in (javdbTagsVocab || [])"
          :key="m.key"
          class="ex-cat-chip jt-mode"
          :class="{ on: activeVocabMode.key === m.key }"
          :title="`切换到「${m.label}」标签页`"
          @click="switchVocabMode(m)"
        >{{ m.label }}</button>
      </div>
      <!-- 已选标签行：全组多选后出现，点「筛选」组合查询 -->
      <div v-if="javdbSelTags.length" class="jt-row jt-selrow">
        <span class="jt-label">已选</span>
        <button
          v-for="s in javdbSelTags"
          :key="'sel:' + s.g + ':' + s.t"
          class="ex-cat-chip jt-tag on"
          :title="`移除「${s.t}」`"
          @click="toggleSelTag(s.g, s.t)"
        >{{ s.t }} ×</button>
        <button class="ex-cat-chip jt-apply" @click="applyTagFilter">筛选 ({{ javdbSelTags.length }})</button>
        <button class="ex-cat-chip" @click="javdbSelTags = []">清空</button>
      </div>
      <div v-for="g in activeVocabMode.groups" :key="g.key" class="jt-group">
        <span class="jt-group-label">{{ g.label }}</span>
        <button
          v-for="t in g.tags"
          :key="g.key + ':' + t"
          class="ex-cat-chip jt-tag"
          :class="{ on: javdbSelTags.some(s => s.g === g.key && s.t === t) }"
          :title="`多选「${t}」（选好点「筛选」组合查询）`"
          @click="onTagChip(activeVocabMode, g, t)"
        >{{ t }}</button>
      </div>
    </div>
    <!-- 第五行：当前 tags 模式（有码/无码/欧美/FC2/动漫）的主要推荐作品 -->
    <div v-if="javdbModeRecommend && javdbModeRecommend.items && javdbModeRecommend.items.length" class="jt-reco-bar">
      <span class="jt-reco-title">{{ javdbModeRecommend.label }}推荐</span>
      <div class="jt-reco-row">
        <div
          v-for="it in javdbModeRecommend.items"
          :key="it.album_url"
          class="jt-reco-card"
          :title="`${it.code || ''} ${it.album_name || ''}`"
          @click="$emit('javdb-open-detail', it)"
        >
          <img :src="it.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="it.album_name" />
          <span v-if="it.code" class="jt-reco-code">{{ it.code }}</span>
          <span class="jt-reco-name">{{ trTitle(it.album_name) }}</span>
        </div>
      </div>
    </div>
  </div>

  <!-- 视频详情：封面大图 + 预览图网格 + 信息面板 + 标签/演员 + 磁力列表 + 下载图片 -->
  <div v-else-if="(javdbDetail || javdbDetailLoading) && mode === 'detail'" class="ex-detail">
    <div v-if="javdbDetailLoading && !javdbDetail" class="tw-follow-empty">
      <n-spin size="medium" />
      <span>正在获取视频详情...</span>
    </div>
    <template v-else-if="javdbDetail">
      <div class="tw-follow-toolbar">
        <n-button size="small" quaternary type="primary" @click="$emit('javdb-detail-back')">← 返回</n-button>
        <span class="tw-follow-title iw-detail-title" :title="javdbDetail.title">{{ javdbDetail.title }}</span>
        <n-button
          size="tiny"
          tertiary
          type="primary"
          title="下载封面 + 全部预览图（直链下载任务）"
          @click="$emit('javdb-download-images')"
        >下载图片</n-button>
        <a
          class="or-iwara-link"
          title="在浏览器打开 JavDB 原页面"
          @click.prevent="openOrExternal(javdbDetail.url)"
        >原站 ↗</a>
      </div>
      <n-scrollbar class="iw-detail-scroll">
        <!-- 播放区域（置顶）：站点网页端无播放源（在线观看为官方 App 专属），封面 + 播放按钮 + 提示；
             信息/磁力/预览图等功能区置于其下 -->
        <div class="javdb-player-area">
          <img
            v-if="javdbDetail.cover"
            :src="javdbDetail.cover"
            class="javdb-player-cover"
            referrerpolicy="no-referrer"
            :alt="javdbDetail.title"
            @click="javdbDetail.cover.startsWith('thumb://') ? null : openOrExternal(javdbDetail.cover)"
          />
          <div class="javdb-player-mask">
            <button
              class="javdb-play-btn"
              title="在线播放为站点官方 App 专属功能，网页端无播放源；点击前往原站"
              @click="openOrExternal(javdbDetail.url)"
            >▶</button>
            <div class="javdb-player-tip">
              站点网页端无播放源（在线观看为官方 App 专属），请通过磁力链接下载观看
              <n-button size="tiny" type="warning" @click="openOrExternal(javdbDetail.url)">点此跳转到原站观看</n-button>
            </div>
          </div>
        </div>
        <!-- 信息面板 -->
        <div v-if="javdbDetail.code || Object.keys(javdbDetail.info || {}).length" class="iw-detail-stats javdb-info-panel">
          <span v-if="javdbDetail.code">🏷️ 番号: {{ javdbDetail.code }}</span>
          <span v-for="(v, k) in javdbDetail.info" :key="k">{{ k }}: {{ v }}</span>
        </div>
        <!-- 演员（可点击 → 该演员全部作品） -->
        <div v-if="javdbDetail.actors && javdbDetail.actors.length" class="iw-tags">
          <n-tag size="small" round type="success" class="iw-tag">演员</n-tag>
          <n-tag
            v-for="(a, ai) in javdbDetail.actors"
            :key="a"
            size="small"
            round
            type="success"
            class="iw-tag iw-tag-click"
            title="点击查看该演员全部作品"
            @click="javdbActorClick(ai, a)"
          >{{ a }}</n-tag>
        </div>
        <!-- 标签（可点击 → 按标签搜索） -->
        <div v-if="javdbDetail.tags && javdbDetail.tags.length" class="iw-tags">
          <n-tag
            v-for="t in javdbDetail.tags"
            :key="t"
            size="small"
            round
            type="info"
            class="iw-tag iw-tag-click"
            title="点击按此标签搜索"
            @click="$emit('javdb-search-tag', t)"
          >{{ t }}</n-tag>
        </div>
        <!-- 磁力链接列表 -->
        <div v-if="javdbDetail.magnets && javdbDetail.magnets.length" class="javdb-magnets">
          <div class="javdb-magnets-title">
            🧲 磁力链接（{{ javdbDetail.magnets.length }} 个，点击复制，用外部种子客户端下载）
            <a
              class="or-iwara-link"
              style="margin-left: 8px"
              title="复制全部磁力链接（逐行，方便导入下载器）"
              @click.prevent="copyJavdbAllMagnets"
            >复制全部</a>
          </div>
          <div
            v-for="(m, idx) in javdbDetail.magnets"
            :key="idx"
            class="javdb-magnet-item"
            title="点击复制磁力链接"
            @click="reverseCopyText(m.link)"
          >
            <span class="javdb-magnet-name">{{ m.name }}</span>
            <span class="javdb-magnet-meta">
              <span v-if="m.size">{{ m.size }}</span>
              <span v-if="m.date">{{ m.date }}</span>
              <n-tag v-for="t in (m.tags || [])" :key="t" size="tiny" round type="warning">{{ t }}</n-tag>
            </span>
          </div>
        </div>
        <div v-else class="or-no-source javdb-comments-tip">
          <span>该影片暂无磁力（部分影片无网友共享磁力属正常情况；「可播放」影片的在线观看为官方 App 专属）</span>
          <n-button size="small" type="warning" @click="openOrExternal(javdbDetail.url)">点此跳转到原站查看</n-button>
        </div>
        <!-- 预览图 -->
        <div v-if="javdbDetail.previews && javdbDetail.previews.length" class="javdb-previews">
          <div class="javdb-magnets-title">🖼️ 预览图（{{ javdbDetail.previews.length }} 张，点击看原图）</div>
          <div class="javdb-preview-grid">
            <img
              v-for="(p, idx) in javdbDetail.previews"
              :key="idx"
              :src="p"
              referrerpolicy="no-referrer"
              loading="lazy"
              @click="p.startsWith('thumb://') ? null : openOrExternal(p)"
            />
          </div>
        </div>
        <!-- 评论区（站点私有接口无法抓取，占位区块 + 异色按钮跳原站查看/发表） -->
        <div class="javdb-comments-area">
          <div class="javdb-magnets-title">💬 评论区</div>
          <div class="javdb-comments-tip">
            <span>评论区内容为站点私有接口，无法在本应用内展示与留言</span>
            <n-button size="small" type="warning" @click="openOrExternal(javdbDetail.url)">点此跳转到原站查看与发表评论</n-button>
          </div>
        </div>
      </n-scrollbar>
    </template>
  </div>
</template>

<script setup>
// JavDB 视图组件（从 RightPanel.vue 拆出，重构 f3）。目录浏览/搜索结果网格/搜索类型折叠卡片
// 留守 RightPanel（共享结果分支与 url-bar）；工具栏标签词库多选状态随工具栏整体迁移。
import { ref, computed } from 'vue'
import { NButton, NDropdown, NTag, NSpin, NScrollbar } from 'naive-ui'

const props = defineProps({
  mode: { type: String, default: 'detail' },             // toolbar=工具栏 | detail=详情
  site: { type: String, default: 'bunkr' },
  javdbUser: { type: String, default: '' },
  javdbHot: { type: Array, default: () => [] },
  javdbTagsVocab: { type: Array, default: () => [] },
  javdbTagsMode: { type: String, default: '' },
  javdbModeRecommend: { type: Object, default: () => ({ mode: '', label: '', items: [] }) },
  javdbDetail: { type: Object, default: null },
  javdbDetailLoading: { type: Boolean, default: false },
  translatedTitles: { type: Object, default: () => ({}) },     // {原标题: 译文}，展示时回填
})

const emit = defineEmits([
  'javdb-logout', 'javdb-hot', 'javdb-mode', 'javdb-open-detail', 'javdb-open-list',
  'javdb-search-tag', 'javdb-open-actor', 'javdb-detail-back', 'javdb-download-images',
])

// ---------- 共用工具（本地副本：RightPanel 同名函数被多站点共用，留守） ----------
function openOrExternal(url) {
  if (!url) return
  if (window.api && window.api.openExternal) window.api.openExternal(url)
  else window.open(url, '_blank')
}

function reverseCopyText(text) {
  if (!text) return
  if (navigator.clipboard) navigator.clipboard.writeText(text)
}

function trTitle(name) {
  if (!name) return '未命名'
  return props.translatedTitles[name] || name
}

// 第二行：下拉导航（类别 / 排行榜）；演员/系列/片商为独立按钮
const javdbNavMenus = [
  {
    key: 'categories', label: '类别',
    options: [
      { label: '有碼影片', key: 'c1' },
      { label: '無碼影片', key: 'c2' },
      { label: '歐美影片', key: 'c3' },
      { label: 'FC2', key: 'fc2' },
      { label: '動漫', key: 'anime' },
    ],
  },
  {
    // 排行榜真实结构（站点导航 HTML 实测 2026-09-01）：
    // /rankings/movies?p={daily|weekly|monthly}&t={censored|uncensored|western|fc2}
    // /rankings/top（TOP250）、/rankings/playback（熱播）、/rankings/fanza_award（FANZA 成人獎）
    key: 'ranking', label: '排行榜',
    options: [
      { label: '每日·有碼', key: 'd-c' },
      { label: '每日·無碼', key: 'd-u' },
      { label: '每日·歐美', key: 'd-w' },
      { label: '每日·FC2', key: 'd-f' },
      { label: '每週·有碼', key: 'w-c' },
      { label: '每週·無碼', key: 'w-u' },
      { label: '每週·歐美', key: 'w-w' },
      { label: '每週·FC2', key: 'w-f' },
      { label: '每月·有碼', key: 'm-c' },
      { label: '每月·無碼', key: 'm-u' },
      { label: '每月·歐美', key: 'm-w' },
      { label: '每月·FC2', key: 'm-f' },
      { label: 'TOP250', key: 'top' },
      { label: '熱播榜', key: 'playback' },
      { label: 'FANZA成人獎', key: 'fanza' },
    ],
  },
  {
    key: 'actors', label: '演员',
    options: [
      { label: '推荐', key: 'all' },
      { label: '有码', key: 'v1' },
      { label: '无码', key: 'v2' },
      { label: '欧美', key: 'v3' },
    ],
  },
  {
    key: 'series', label: '系列',
    options: [
      { label: '有码', key: 'v1' },
      { label: '无码', key: 'v2' },
      { label: '欧美', key: 'v3' },
      { label: 'LUXU', key: 'LUXU' },
      { label: 'ARA', key: 'ARA' },
      { label: 'MAAN', key: 'MAAN' },
      { label: 'MIUM', key: 'MIUM' },
      { label: 'SIRO', key: 'SIRO' },
      { label: 'GANA', key: 'GANA' },
    ],
  },
  {
    key: 'makers', label: '片商',
    options: [
      { label: '有码', key: 'v1' },
      { label: '无码', key: 'v2' },
      { label: '麻豆传媒映画', key: 'madou' },
    ],
  },
]

function onNavPick(menuKey, optKey) {
  if (menuKey === 'categories') {
    // 类别真实结构（站点导航 HTML 实测 2026-09-01）：
    // 有碼/無碼/歐美 = /{censored|uncensored|western}?vft=1（未登录可看）
    // FC2/動漫 = /tags/{fc2|anime}?c10=1 分区（登录后才能看）
    const names = { c1: '有碼影片', c2: '無碼影片', c3: '歐美影片', fc2: 'FC2', anime: '動漫' }
    const segs = { c1: 'censored', c2: 'uncensored', c3: 'western' }
    const seg = segs[optKey]
    if (seg) {
      emit('javdb-open-list', `/${seg}?vft=1`, names[optKey])
    } else if (optKey === 'fc2' || optKey === 'anime') {
      emit('javdb-open-list', `/tags/${optKey}?c10=1`, names[optKey])
    }
  } else if (menuKey === 'ranking') {
    // 排行榜：/rankings/movies?p={period}&t={type}；TOP250/熱播/FANZA獎为独立路径（导航 HTML 证实）
    const specials = {
      top: ['/rankings/top', 'TOP250'],
      playback: ['/rankings/playback', '熱播榜'],
      fanza: ['/rankings/fanza_award', 'FANZA成人獎'],
    }
    if (specials[optKey]) {
      emit('javdb-open-list', specials[optKey][0], specials[optKey][1])
      return
    }
    const periods = { d: ['daily', '每日'], w: ['weekly', '每週'], m: ['monthly', '每月'] }
    const types = { c: ['censored', '有碼'], u: ['uncensored', '無碼'], w: ['western', '歐美'], f: ['fc2', 'FC2'] }
    const [p, t] = optKey.split('-')
    if (periods[p] && types[t]) {
      emit('javdb-open-list', `/rankings/movies?p=${periods[p][0]}&t=${types[t][0]}`, `${periods[p][1]}·${types[t][1]}榜`)
    }
  } else if (menuKey === 'actors') {
    // 演员目录：/actors（推荐）| /actors/{censored|uncensored|western}（导航 HTML 证实为子路径）
    const sub = { all: '', v1: '/censored', v2: '/uncensored', v3: '/western' }
    emit('javdb-dir', 'actors' + (sub[optKey] || ''))
  } else if (menuKey === 'series') {
    // 系列：v1/v2/v3 走分类子路径目录；LUXU 等番号系列走 /video_codes/{CODE}（导航证实）
    const sub = { v1: '/censored', v2: '/uncensored', v3: '/western' }
    if (sub[optKey]) emit('javdb-dir', 'series' + sub[optKey])
    else emit('javdb-open-list', `/video_codes/${optKey}`, `系列:${optKey}`)
  } else if (menuKey === 'makers') {
    if (optKey === 'v1' || optKey === 'v2' || optKey === 'v3') {
      const sub = { v1: '/censored', v2: '/uncensored', v3: '/western' }
      emit('javdb-dir', 'makers' + sub[optKey])
    } else if (optKey === 'madou') {
      // 麻豆傳媒映畫真实 slug（导航 HTML 证实）
      emit('javdb-open-list', '/makers/N73g?f=download', '片商:麻豆傳媒映畫')
    }
  }
}

// 首行：用户信息下拉（近期浏览/想看/看过/我的清单/收藏 x5）
// URL 经 GitHub 校准：想看/看过由「JavDB助手」用户脚本 validUrlPatterns 证实；
// 其余按 /users/xxx_videos · /users/xxx_favorites 站点命名约定推测（待实测校准）
const javdbUserMenus = [
  { label: '近期浏览', key: 'recent' },
  { label: '想看', key: 'want' },
  { label: '看过', key: 'watched' },
  { label: '我的清单', key: 'lists' },
  { label: '收藏的演员', key: 'actor_collections' },
  { label: '收藏的系列', key: 'series_collections' },
  { label: '收藏的片商/卖家', key: 'maker_collections' },
  { label: '收藏的导演', key: 'director_collections' },
  { label: '收藏的番号', key: 'video_collections' },
]
const JAVDB_USER_PATHS = {
  recent: '/users/recent_view_videos',
  want: '/users/want_watch_videos',
  watched: '/users/watched_videos',
  lists: '/users/list_detail',
  actor_collections: '/users/actor_favorites',
  series_collections: '/users/series_favorites',
  maker_collections: '/users/maker_favorites',
  director_collections: '/users/director_favorites',
  video_collections: '/users/video_favorites',
}
function onUserMenuPick(k) {
  const label = (javdbUserMenus.find(m => m.key === k) || {}).label || k
  const path = JAVDB_USER_PATHS[k]
  if (path) emit('javdb-open-list', path, label)
}

// 第四行：当前标签页模式对象（有码/无码/欧美/FC2/动漫）
const activeVocabMode = computed(() => {
  const modes = props.javdbTagsVocab || []
  return modes.find(m => m.key === props.javdbTagsMode) || modes[0] || null
})

// 可组合查询的词条组（文字标签+时长走 /search?q=A,B&f=tag 逗号组合，第五轮实测 AND 语义成立）
const JAVDB_WORD_GROUPS = new Set(['theme', 'role', 'costume', 'body', 'action', 'play', 'category', 'other', 'location', 'tag', 'duration'])

// 基本组词条 → 站点真实过滤参数（导航 HTML 实测：vft 0=全部 1=含磁鏈 2=含字幕 3=含短評；可播放需配 vst=3）
const JAVDB_BASIC_FILTERS = {
  '全部': '',
  '含磁鏈': 'vft=1',
  '含字幕': 'vft=2',
  '含短評': 'vft=3',
  '可播放': 'vft=4&vst=3',
  '中字可播放': 'vft=5&vst=3',
}

// 多选标签状态：[{g: 组key, t: 词条}]（当前模式内生效；切换模式 tab 清空）
const javdbSelTags = ref([])

function switchVocabMode(m) {
  javdbSelTags.value = []
  emit('javdb-mode', m)
}

function toggleSelTag(groupKey, tag) {
  const list = javdbSelTags.value
  const i = list.findIndex(s => s.g === groupKey && s.t === tag)
  if (i >= 0) list.splice(i, 1)
  else list.push({ g: groupKey, t: tag })
}

// 应用多选筛选（按优先级取一类执行；第五轮实测 vy/vtags URL 参数均无效，改走组合搜索）：
// 1) 文字标签/时长 → /search?q=词1,词2&f=tag（逗号 AND 组合）
// 2) 基本项 → vft 单值枚举，多选时取最后选中
// 3) 年份 → 站点无年份 URL 参数，退化为关键词搜索
function applyTagFilter() {
  const mode = activeVocabMode.value
  const sel = javdbSelTags.value
  if (!mode || !sel.length) return
  const words = sel.filter(s => JAVDB_WORD_GROUPS.has(s.g)).map(s => s.t)
  const basics = sel.filter(s => s.g === 'basic').map(s => s.t)
  const years = sel.filter(s => s.g === 'year').map(s => s.t)
  if (words.length) {
    emit('javdb-search-tag', words.join(','))
    return
  }
  if (basics.length) {
    const tag = basics[basics.length - 1]
    const qs = JAVDB_BASIC_FILTERS[tag]
    if (qs) {
      if (mode.vft) emit('javdb-open-list', `/${mode.key}?${qs}`, `${mode.label}影片·${tag}`)
      else emit('javdb-open-list', `/tags/${mode.key}?c10=1&${qs}`, `${mode.label}·${tag}`)
      return
    }
  }
  if (years.length) {
    emit('javdb-search-tag', years[years.length - 1], 'all')
  }
}

function onTagChip(mode, group, tag) {
  if (!mode || !group || !tag) return
  // 「全部」= 清空多选，加载模式基础列表
  if (tag === '全部') { switchVocabMode(mode); return }
  // 全组统一多选：点词条进「已选」，选好点「筛选」组合查询
  toggleSelTag(group.key, tag)
}

// JavDB 详情：点演员 → 演员主页全部作品（优先用后端解析的演员链接，无链接时按名字搜索兜底）
function javdbActorClick(ai, name) {
  const link = props.javdbDetail && props.javdbDetail.actor_links && props.javdbDetail.actor_links[ai]
  if (link && link.url) emit('javdb-open-actor', link.url)
  else if (name) emit('javdb-search-tag', name)
}

// JavDB 详情：复制全部磁力链接（逐行，方便一次性导入种子客户端）
function copyJavdbAllMagnets() {
  const magnets = (props.javdbDetail && props.javdbDetail.magnets) || []
  const text = magnets.map(m => m.link).filter(Boolean).join('\n')
  if (!text) return
  if (navigator.clipboard) navigator.clipboard.writeText(text)
}
</script>

<style scoped>
/* JavdbView 样式：javdb 与 jt 系列自 RightPanel 迁出；ex-detail、tw-follow、iw、or、ex-cat-chip 为共用类副本 */

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
/* ========== ExHentai 画廊详情（复刻原版画廊页信息区） ========== */
.ex-detail {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
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
.iw-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 14px 10px;
}
.iw-tag {
  cursor: pointer;
}
/* 详情页：iwara 原站链接 */
.or-iwara-link {
  font-size: 12px;
  color: #70c0e8;
  cursor: pointer;
}
.or-iwara-link:hover {
  text-decoration: underline;
}
/* 详情页：无 iwara 源提示 */
.or-no-source {
  margin: 10px 14px 14px;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(240, 160, 32, 0.08);
  border: 1px solid rgba(240, 160, 32, 0.3);
  font-size: 12px;
  color: #f2c97d;
}
html.light-mode .or-iwara-link {
  color: #0a6ebd;
}
html.light-mode .or-no-source {
  background: rgba(240, 160, 32, 0.08);
  border-color: rgba(200, 130, 20, 0.35);
  color: #9a6a10;
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
/* JavDB 播放区域（置顶）：封面背景 + 播放按钮 + 提示，功能区置于其下 */
.javdb-player-area {
  position: relative;
  display: flex;
  justify-content: center;
  margin: 8px 0;
  border-radius: 10px;
  overflow: hidden;
  background: #0b0d10;
}
.javdb-player-cover {
  max-width: min(100%, 520px);
  max-height: 440px;
  display: block;
  object-fit: contain;
  cursor: zoom-in;
  opacity: 0.92;
}
.javdb-player-mask {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px;
  background: linear-gradient(180deg, rgba(0, 0, 0, 0) 45%, rgba(0, 0, 0, 0.72) 100%);
  pointer-events: none;
}
.javdb-play-btn {
  width: 64px;
  height: 64px;
  margin-bottom: auto;
  margin-top: auto;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.85);
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 26px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding-left: 4px;
  pointer-events: auto;
  transition: background 0.2s;
}
.javdb-play-btn:hover {
  background: rgba(88, 132, 255, 0.75);
}
.javdb-player-tip {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.88);
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
  text-align: center;
  display: flex;
  align-items: center;
  gap: 10px;
}
/* JavDB 评论区占位（站点私有接口，跳原站查看/发表） */
.javdb-comments-area {
  margin: 10px 0;
  padding: 10px 12px;
  border: 1px dashed var(--n-border-color, rgba(255, 255, 255, 0.18));
  border-radius: 8px;
}
.javdb-comments-tip {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 6px;
  font-size: 12px;
  opacity: 0.85;
}
/* JavDB 信息面板 */
.javdb-info-panel {
  flex-wrap: wrap;
  gap: 6px 14px;
}
/* JavDB 磁力列表 */
.javdb-magnets-title .or-iwara-link { cursor: pointer; }
.javdb-magnets {
  margin: 10px 0;
}
.javdb-magnets-title {
  font-size: 12px;
  font-weight: 600;
  color: #d4d4dc;
  margin: 8px 0 6px;
}
.javdb-magnet-item {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 7px 10px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
  margin-bottom: 5px;
  cursor: pointer;
  transition: background 0.15s;
}
.javdb-magnet-item:hover {
  background: rgba(56, 137, 255, 0.12);
}
.javdb-magnet-name {
  font-size: 12px;
  color: #d4d4dc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 60%;
}
.javdb-magnet-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #7a7a85;
  margin-left: auto;
}
/* JavDB 预览图网格 */
.javdb-preview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 8px;
}
.javdb-preview-grid img {
  width: 100%;
  aspect-ratio: 16/11;
  object-fit: cover;
  border-radius: 6px;
  cursor: zoom-in;
  transition: transform 0.15s;
}
.javdb-preview-grid img:hover {
  transform: scale(1.03);
}
html.light-mode .javdb-magnets-title { color: #333338; }
html.light-mode .javdb-magnet-item { background: rgba(0, 0, 0, 0.04); }
html.light-mode .javdb-magnet-name { color: #333338; }
html.light-mode .javdb-magnet-meta { color: #8a8a93; }
/* ---------- JavDB 五行工具栏 ---------- */
.javdb-toolbar {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 4px 2px;
  border-bottom: 1px solid #2a2a32;
}
.jt-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.jt-label {
  flex: none;
  font-size: 12px;
  color: #888;
  width: 38px;
  text-align: right;
  margin-right: 2px;
}
.jt-flex {
  flex: 1;
}
.jt-user {
  font-size: 12px;
  color: #63e2b7;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.jt-logout {
  color: #e88080;
}
/* 导航行：加大加粗 */
.jt-navrow .jt-label {
  font-size: 13px;
  font-weight: 700;
  color: #9d9da8;
}
.jt-navrow .ex-cat-chip {
  font-size: 14px;
  font-weight: 700;
  padding: 5px 12px;
  border-radius: 6px;
}
/* 第四行：标签词库（模式 tab 一行；每组词条整行排布，超高滚动） */
.jt-vocab {
  max-height: 220px;
  overflow-y: auto;
  padding-right: 4px;
}
.jt-mode {
  color: #63e2b7;
  border-color: #2e5f4e;
}
/* 分组块：抬头固定左侧列（完整显示不截断），词条随后换行排布 */
.jt-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  padding: 2px 0;
}
.jt-group-label {
  flex: none;
  width: 42px;
  font-size: 12px;
  color: #7aa898;
  opacity: 0.9;
  white-space: nowrap;
}
.jt-tag {
  font-size: 12px;
}
/* 词条选中态（多选进行中） */
.jt-tag.on {
  color: #63e2b7;
  border-color: #63e2b7;
  background: rgba(99, 226, 183, 0.12);
}
/* 已选标签行 + 筛选按钮 */
.jt-selrow {
  padding: 2px 0;
  border-bottom: 1px dashed #2e5f4e;
}
.jt-apply {
  color: #f2c97d;
  border-color: #6d5a2e;
}
/* 第五行：当前模式推荐作品横滚条 */
.jt-reco-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 0;
}
.jt-reco-title {
  flex: none;
  font-size: 12px;
  color: #63e2b7;
  font-weight: 600;
}
.jt-reco-row {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 2px;
  flex: 1;
  min-width: 0;
}
.jt-reco-card {
  flex: none;
  width: 108px;
  cursor: pointer;
  position: relative;
  border-radius: 6px;
  overflow: hidden;
  background: #26262e;
  border: 1px solid #33333c;
}
.jt-reco-card img {
  width: 108px;
  height: 72px;
  object-fit: cover;
  display: block;
}
.jt-reco-code {
  position: absolute;
  top: 2px;
  left: 2px;
  font-size: 10px;
  color: #fff;
  background: rgba(0, 0, 0, 0.6);
  border-radius: 3px;
  padding: 0 3px;
}
.jt-reco-name {
  display: block;
  font-size: 11px;
  color: #bbb;
  padding: 2px 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.jt-reco-card:hover {
  border-color: #63e2b7;
}
</style>
