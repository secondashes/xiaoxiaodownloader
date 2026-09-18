<template>
  <!-- ASMR 音声站工具栏：热门作品 / 媒体库（排序+仅带字幕）/ 我的收藏 / 社团·标签·声优索引 / 批量下载 -->
  <div v-if="mode === 'options'" class="ex-search-options">
    <div class="ex-cats">
      <span class="ex-cats-label">分类：</span>
      <n-button
        size="tiny"
        :type="asmrView === 'popular' ? 'primary' : 'default'"
        :loading="asmrListLoading && asmrView === 'popular'"
        title="热门作品（每页 100 个，可加载更多）"
        @click="$emit('asmr-popular', 1)"
      >热门作品</n-button>
      <n-button
        size="tiny"
        :type="asmrView === 'works' && !asmrFilter.id ? 'primary' : 'default'"
        :loading="asmrListLoading && asmrView === 'works'"
        title="媒体库（最新入库 + 排序 + 筛选）"
        @click="$emit('asmr-works', 1)"
      >媒体库</n-button>
      <n-button
        size="tiny"
        :type="asmrView === 'favorites' ? 'primary' : 'default'"
        :loading="asmrListLoading && asmrView === 'favorites'"
        title="我的收藏（需登录）"
        @click="$emit('asmr-favorites', 1)"
      >我的收藏</n-button>
      <div class="ex-filter-item ha-sort-item">
        <span class="ex-filter-label">排序</span>
        <n-select
          :value="settings.asmr_order"
          :options="asmrOrderOptions"
          size="tiny"
          class="ha-sort-select"
          placeholder="最新入库"
          @update:value="v => $emit('update:asmr-search', { asmr_order: v })"
        />
      </div>
      <div class="ex-filter-item asmr-subtitle-item">
        <n-checkbox
          :checked="!!settings.asmr_subtitle"
          size="small"
          title="只显示带中文字幕的作品"
          @update:checked="v => $emit('update:asmr-search', { asmr_subtitle: !!v })"
        >仅带字幕</n-checkbox>
      </div>
    </div>
    <div class="ex-cats">
      <n-button size="tiny" tertiary title="按社团浏览作品" @click="showAsmrIndex('circles')">社团</n-button>
      <n-button size="tiny" tertiary title="按标签浏览作品" @click="showAsmrIndex('tags')">标签</n-button>
      <n-button size="tiny" tertiary title="按声优浏览作品" @click="showAsmrIndex('vas')">声优</n-button>
      <n-button
        class="batch-cta"
        size="small"
        :type="asmrBatchMode ? 'warning' : 'primary'"
        :title="asmrBatchMode ? '退出勾选模式' : '点击后当前列表进入勾选模式，勾选要下载的作品'"
        @click="$emit('toggle-asmr-batch')"
      >{{ asmrBatchMode ? '取消勾选' : '批量下载' }}</n-button>
      <n-button
        v-if="asmrBatchMode"
        size="tiny"
        type="error"
        :disabled="!asmrBatchChecked.size"
        :loading="asmrBatchRunning"
        :title="`开始下载勾选的 ${asmrBatchChecked.size} 个作品（整包下载全部音轨）`"
        @click="$emit('start-asmr-batch')"
      >开始下载{{ asmrBatchChecked.size ? `(${asmrBatchChecked.size})` : '' }}</n-button>
      <template v-if="asmrBatchMode">
        <n-button size="tiny" title="勾选当前列表全部作品" @click="$emit('select-asmr-batch', 'all')">全选</n-button>
        <n-button size="tiny" title="勾选状态反转" @click="$emit('select-asmr-batch', 'invert')">反选</n-button>
        <n-button size="tiny" title="清空全部勾选" @click="$emit('select-asmr-batch', 'clear')">清空</n-button>
      </template>
      <span v-if="asmrBatchRunning" class="iw-batch-progress">
        {{ asmrBatchProgress.message || '准备中...' }}（{{ asmrBatchProgress.done }}/{{ asmrBatchProgress.total }}）
      </span>
      <span v-else class="tw-toolbar-hint">点作品卡片查看音轨列表并在线试听；可按社团/标签/声优筛选</span>
    </div>
    <!-- 社团/标签/声优索引弹窗：点击进入对应筛选列表 -->
    <n-modal
      v-model:show="asmrIndexModal"
      preset="card"
      class="or-tags-modal"
      :title="`ASMR ${asmrIndexTitle}`"
      style="width: 560px; max-width: 92vw"
    >
      <n-input
        v-model:value="asmrIndexFilter"
        size="small"
        clearable
        :placeholder="`🔍 输入文字过滤${asmrIndexTitle}`"
        style="margin-bottom: 8px"
      />
      <div class="or-tags-body">
        <div v-if="asmrIndexLoading && !filteredAsmrIndex.length" class="tw-follow-empty">
          <n-spin size="medium" />
          <span>正在获取{{ asmrIndexTitle }}列表...</span>
        </div>
        <template v-else>
          <span
            v-for="t in filteredAsmrIndex"
            :key="t.id"
            class="or-tag-chip"
            :title="`点击查看「${t.name}」的作品${t.count ? `（共 ${t.count} 部）` : ''}`"
            @click="pickAsmrIndex(t)"
          >{{ t.name }}<span v-if="t.count" class="or-chip-count">{{ t.count }}</span></span>
          <div v-if="!filteredAsmrIndex.length" class="or-tags-empty">没有匹配的{{ asmrIndexTitle}}</div>
        </template>
      </div>
    </n-modal>
  </div>

  <!-- 主视图：列表（热门/媒体库/收藏/筛选共用） / 作品详情（内置音频播放器） -->
  <div v-else-if="asmrView && asmrView !== 'detail'" class="tw-follow-view">
    <div class="tw-follow-toolbar">
      <n-button
        v-if="asmrFilter.id"
        size="small"
        quaternary
        type="primary"
        title="返回媒体库"
        @click="$emit('asmr-works', 1)"
      >← 返回</n-button>
      <n-button
        v-if="!asmrFilter.id && asmrView !== 'popular'"
        size="small"
        quaternary
        type="primary"
        title="返回上一层"
        @click="$emit('site-back', 'asmr')"
      >← 返回</n-button>
      <span class="tw-follow-title">{{ asmrLabel || '热门作品' }}</span>
      <span v-if="asmrItems.length" class="tw-follow-count">
        {{ asmrItems.length }} 个作品<template v-if="asmrHasMore">（可继续加载）</template>
      </span>
      <n-button
        size="tiny"
        quaternary
        :loading="asmrListLoading"
        @click="refreshAsmrView"
      >刷新</n-button>
    </div>
    <n-scrollbar class="tw-follow-scroll">
      <div v-if="asmrError" class="tw-follow-error">{{ asmrError }}</div>
      <div v-else-if="asmrListLoading && !asmrItems.length" class="tw-follow-empty">
        <n-spin size="medium" />
        <span>正在获取作品列表...</span>
      </div>
      <div v-else-if="!asmrItems.length" class="tw-follow-empty">
        {{ asmrView === 'favorites' ? '还没有收藏，登录后在作品详情页点 ☆ 收藏' : '暂无作品' }}
      </div>
      <div v-else class="search-grid">
          <div v-if="asmrItems.length && asmrHasMore" class="tw-browse-more" style="grid-column: 1 / -1; padding: 0 0 6px">
            <n-button size="tiny" quaternary block :loading="asmrListLoading" @click="$emit('asmr-more')"
            >加载更多</n-button>
          </div>
        <div
          v-for="item in asmrItems"
          :key="item.video_id || item.album_url"
          class="search-card iw-card asmr-card"
          :class="{ 'iw-batch-checked': asmrBatchMode && asmrBatchChecked.has(item.video_id) }"
          :title="asmrCardTooltip(item)"
          @click="asmrBatchMode ? $emit('toggle-asmr-batch-item', item.video_id) : $emit('asmr-open-detail', item)"
        >
          <div class="thumb-wrapper">
            <img :src="item.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name" />
            <span v-if="item.duration" class="iw-thumb-duration">{{ item.duration }} 分钟</span>
            <span v-if="item.has_subtitle" class="asmr-thumb-sub">字幕</span>
            <div class="iw-thumb-stats">
              <span v-if="item.views != null" title="下载数">⬇ {{ formatCount(item.views) }}</span>
              <span v-if="item.rating" title="评分">★ {{ item.rating }}</span>
            </div>
            <span v-if="asmrBatchMode" class="iw-batch-check" :class="{ checked: asmrBatchChecked.has(item.video_id) }">{{ asmrBatchChecked.has(item.video_id) ? '✓' : '' }}</span>
            <button v-if="!asmrBatchMode" class="card-favorite-btn" title="快速收藏到本地" @click.stop="handleQuickFavorite(item)">♥</button>
          </div>
          <div class="card-name" :title="item.album_name">{{ trTitle(item.album_name) }}</div>
          <div class="iw-card-meta">
            <span class="iw-card-author" :title="`社团：${item.author || '未知'}`">{{ item.author || '未知社团' }}</span>
            <span v-if="item.post_date" class="iw-card-time">{{ item.post_date }}</span>
          </div>
          <div v-if="item.tags && item.tags.length" class="asmr-card-tags" :title="item.tags.join(' ')">
            {{ item.tags.slice(0, 4).join(' · ') }}<template v-if="item.tags.length > 4"> 等</template>
          </div>
        </div>
      </div>
      <div v-if="asmrItems.length && asmrHasMore" class="tw-browse-more">
        <n-button quaternary block :loading="asmrListLoading" @click="$emit('asmr-more')">加载更多</n-button>
      </div>
      <!-- 收藏页：基于收藏 tags 的推荐流（对齐真实站滚动推荐，2026-09-10） -->
      <div v-if="asmrView === 'favorites' && asmrRecommend.length" class="gs-related">
        <div class="asmr-files-title">根据收藏推荐</div>
        <div class="search-grid gs-related-grid">
          <div
            v-for="r in asmrRecommend"
            :key="'rec-' + r.video_id"
            class="search-card iw-card asmr-card"
            :title="r.album_name"
            @click="$emit('asmr-open-detail', r)"
          >
            <div class="thumb-wrapper">
              <img :src="r.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="r.album_name" />
              <span v-if="r.duration" class="iw-thumb-duration">{{ r.duration }} 分钟</span>
            </div>
            <div class="card-name" :title="r.album_name">{{ trTitle(r.album_name) }}</div>
            <div class="iw-card-meta">
              <span class="iw-card-author">{{ r.author || '未知社团' }}</span>
            </div>
          </div>
        </div>
      </div>
    </n-scrollbar>
  </div>

  <!-- ASMR 作品详情：封面 + 元信息 + 收藏 + 音轨列表（文件夹分组）+ 内置音频播放器；
       音轨列表紧跟详情头（核心内容优先，不再被属性/标签顶到屏外） -->
  <div v-else-if="asmrView === 'detail'" class="iw-detail">
    <div v-if="asmrDetailLoading && !asmrDetail" class="tw-follow-empty">
      <n-spin size="medium" />
      <span>正在获取作品详情...</span>
    </div>
    <template v-else-if="asmrDetail">
      <div class="tw-follow-toolbar">
        <n-button size="small" quaternary type="primary" @click="$emit('asmr-detail-back')">← 返回</n-button>
        <span class="tw-follow-title iw-detail-title" :title="asmrDetail.album_name">{{ asmrDetail.album_name }}</span>
        <n-button
          size="tiny"
          tertiary
          type="primary"
          title="解析作品全部音轨文件并加入下载列表"
          @click="$emit('open-album', asmrDetail)"
        >解析下载</n-button>
            <n-button
              size="tiny"
              ghost
              :type="asmrDetail.saved ? 'warning' : 'primary'"
              :title="asmrDetail.saved ? '已收藏（点击取消）' : '加入收藏（需登录）'"
              @click="$emit('asmr-toggle-favorite', asmrDetail)"
            >{{ asmrDetail.saved ? '★ 已收藏' : '☆ 收藏' }}</n-button>
      </div>
      <n-scrollbar class="iw-detail-scroll">
        <!-- 封面（点击放大查看） -->
        <div class="asmr-cover-wrap">
          <img :src="asmrDetail.thumbnail" referrerpolicy="no-referrer" :alt="asmrDetail.album_name" @click="coverZoom = !coverZoom" />
        </div>
        <div v-if="coverZoom" class="asmr-cover-full" @click="coverZoom = false">
          <img :src="asmrDetail.thumbnail" referrerpolicy="no-referrer" :alt="asmrDetail.album_name" />
        </div>
        <!-- 标签（点击搜索该标签） -->
        <div v-if="asmrDetail.tags && asmrDetail.tags.length" class="iw-tags">
          <n-tag
            v-for="t in asmrDetail.tags"
            :key="t"
            size="small"
            round
            type="info"
            class="iw-tag"
            title="点击搜索该标签"
            @click="$emit('asmr-search-tag', t)"
          >{{ t }}</n-tag>
        </div>
        <!-- 相似作品：同社团最新作品（asmr-100 详情页同款）；置于文件列表上方，长作品免滚动即可见（用户指定 2026-09-09） -->
        <div class="asmr-files-title">相似作品</div>
        <div v-if="!asmrRelated.length" class="iw-comments-empty">{{ asmrRelatedPending ? '标签推荐补齐中…' : '暂无相似作品（网络波动或该作品无同社团数据）' }}</div>
        <div v-else class="search-grid gs-related-grid">
            <div
              v-for="r in asmrRelated"
              :key="r.video_id"
              class="search-card iw-card asmr-card"
              :title="r.album_name"
              @click="$emit('asmr-open-detail', r)"
            >
              <div class="thumb-wrapper">
                <img :src="r.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="r.album_name" />
                <span v-if="r.duration" class="iw-thumb-duration">{{ r.duration }} 分钟</span>
              </div>
              <div class="card-name" :title="r.album_name">{{ r.album_name }}</div>
              <div class="iw-card-meta">
                <span class="iw-card-author">{{ r.author || '未知社团' }}</span>
              </div>
          </div>
        </div>
        <!-- 音轨文件列表：按文件夹路径分组（核心内容，紧跟详情头） -->
        <div class="asmr-files-title">音轨文件<template v-if="asmrFiles.length">（{{ asmrFiles.length }}）</template></div>
        <div v-if="!asmrFiles.length" class="iw-comments-empty">暂无音轨文件</div>
        <div v-for="g in asmrFileGroups" :key="g.path || 'root'" class="asmr-file-group">
          <div v-if="g.path" class="asmr-folder-name" title="文件夹路径">📁 {{ g.path }}</div>
          <!-- 实验版：dropdown 已摘除（诊断行渲染） -->
        <div class="asmr-file-list">
            <div
              v-for="(f, fi) in g.files"
              :key="fi"
              class="asmr-file-row"
              :class="{ active: f === asmrPlayingFile?.raw, text: f.type === 'text' }"
              :title="f.type === 'text' ? '文本文件（无音频）· 右键可下载' : '点击播放 · 右键播放/下载'"
              @click="isAsmrVideo(f) ? $emit('asmr-video-preview', f) : (f.type === 'text' ? null : playAsmrFile(f))"
              @contextmenu="onAsmrFileContextMenu($event, f)"
            >
              <span class="asmr-file-icon">{{ f.type === 'text' ? '📄' : (isAsmrVideo(f) ? '🎬' : (asmrPlayingFile?.raw === f ? '▶' : '♪')) }}</span>
              <span class="asmr-file-name" :title="isAsmrVideo(f) ? '视频文件 · 点击预览播放' : f.title">{{ f.title }}<span v-if="isAsmrVideo(f)" style="color: #63e2b7">（视频）</span></span>
              <span v-if="f.type !== 'text' && f.duration" class="asmr-file-duration">{{ iwDuration(f.duration) }}</span>
              <span v-if="f.size" class="asmr-file-size">{{ formatSize(f.size) }}</span>
            </div>
          </div>
        </div>
        <!-- 作品属性（中文附加信息；数字键/嵌套对象垃圾已降级过滤，仅存干净条目时显示） -->
        <div v-if="asmrDescEntries.length" class="asmr-attrs">
          <div v-for="a in asmrDescEntries" :key="a.key" class="asmr-attr-row">
            <span class="asmr-attr-key">{{ a.key }}</span>
            <span class="asmr-attr-value" :title="a.value">{{ a.value }}</span>
          </div>
        </div>
        <!-- 底部占位（播放器悬浮时不遮挡列表） -->
        <div class="asmr-player-space"></div>
      </n-scrollbar>
      <!-- 右键菜单（根级手动定位；n-dropdown 包裹触发器会吞掉行内容，故不包裹） -->
      <n-dropdown
        placement="bottom-start"
        trigger="manual"
        :show="asmrFileCtx.show"
        :x="asmrFileCtx.x"
        :y="asmrFileCtx.y"
        :options="asmrFileCtxOptions"
        @clickoutside="asmrFileCtx.show = false"
        @select="onAsmrFileCtxSelect"
      />
      <!-- 播放列表（队列全部曲目；当前曲高亮，点击跳播） -->
      <div v-if="asmrPlayingFile && playlistVisible" class="asmr-playlist" @clickoutside="() => {}">
        <div class="asmr-playlist-head">
          <span>播放列表（{{ asmrAudioFiles.length }}）</span>
          <n-button size="tiny" quaternary @click="playlistVisible = false">收起</n-button>
        </div>
        <div class="asmr-playlist-body">
          <div
            v-for="(f, pi) in asmrAudioFiles"
            :key="'pl' + pi"
            :ref="el => setPlaylistRow(el, pi)"
            class="asmr-playlist-row"
            :class="{ active: f === asmrPlayingFile?.raw }"
            @click="playAsmrFile(f)"
          >
            <span class="asmr-playlist-idx">{{ asmrPlayingFile?.raw === f ? '▶' : (pi + 1) }}</span>
            <span class="asmr-playlist-name" :title="f.title">{{ f.title }}</span>
            <span v-if="f.duration" class="asmr-playlist-dur">{{ iwDuration(f.duration) }}</span>
          </div>
        </div>
      </div>
      <!-- 内置音频播放器（悬浮底部）：连续自动播放 + 可拖进度条 + 字幕（贴进度条上方实时滚动）
           状态/音频元素在全局 store（audioPlayer.js 样板），离开详情/切站后台续播（迷你条接管） -->
      <div v-if="asmrPlayingFile" class="asmr-player">
        <div class="asmr-player-main">
          <span class="asmr-player-icon">🎵</span>
          <div class="asmr-player-info">
            <div class="asmr-player-name" :title="asmrPlayingFile.title">{{ asmrPlayingFile.title }}</div>
            <div class="asmr-player-track">
              {{ asmrPlayingIndex + 1 }} / {{ st.queue.length }}<template v-if="asmrPlayingFile.raw?.path"> · {{ asmrPlayingFile.raw.path }}</template>
            </div>
          </div>
          <n-button size="tiny" quaternary title="上一个音轨" :disabled="!asmrHasPrev" @click="playAsmrOffset(-1)">⏮</n-button>
          <n-button size="tiny" quaternary :title="`倒带 ${settings.asmr_seek_back || 5} 秒`" @click="asmrSeekBy(-1)">⏪ {{ settings.asmr_seek_back || 5 }}s</n-button>
          <n-button size="tiny" quaternary :type="asmrAudioPaused ? 'primary' : 'default'" :title="asmrAudioPaused ? '播放' : '暂停'" @click="toggleAsmrPlay">{{ asmrAudioPaused ? '▶' : '⏸' }}</n-button>
          <n-button size="tiny" quaternary :title="`快进 ${settings.asmr_seek_forward || 30} 秒`" @click="asmrSeekBy(1)">⏩ {{ settings.asmr_seek_forward || 30 }}s</n-button>
          <n-button size="tiny" quaternary title="下一个音轨" :disabled="!asmrHasNext" @click="playAsmrOffset(1)">⏭</n-button>
          <n-button size="tiny" quaternary title="静音 / 取消静音（音量已记忆）" @click="toggleAsmrMute">{{ asmrAudioMuted ? '🔇' : '🔊' }}</n-button>
          <input
            class="asmr-volume"
            type="range"
            min="0"
            max="100"
            :value="asmrVolumePercent"
            title="音量（拖动后自动记住）"
            @input="onAsmrVolumeInput"
          />
          <span
            v-if="st.subStatus === 'ready'"
            class="asmr-player-subtoggle"
            :class="{ off: !st.subOn }"
            title="显示 / 隐藏字幕"
            @click="setSubOn(!st.subOn)"
          >字</span>
          <span v-if="st.error" class="asmr-player-time" :title="st.error">{{ st.error }}</span>
          <n-button size="tiny" quaternary :type="playlistVisible ? 'primary' : 'default'" title="播放列表（当前队列全部曲目）" @click="playlistVisible = !playlistVisible">☰</n-button>
          <n-button size="tiny" quaternary type="error" title="关闭播放器" @click="stopAsmrPlayer">✕</n-button>
        </div>
        <!-- 字幕/歌词：贴进度条上方，双行（当前行高亮 + 下一行预览），字号随面板宽度自适应。
             无字幕/加载失败也明确提示，避免"看不到字幕"分不清是没渲染还是没字幕 -->
        <div
          v-if="st.subOn && st.subStatus && st.subStatus !== 'loading'"
          class="asmr-player-sub"
          :class="{ err: st.subStatus === 'error' }"
          :title="st.subText"
        >
          <div v-if="st.subStatus === 'error'" class="sub-cur">（字幕加载失败）</div>
          <div v-else-if="st.subStatus === 'none'" class="sub-none">（本音轨无字幕）</div>
          <template v-else>
            <div class="sub-cur" :class="{ dim: !st.subText }">{{ st.subText || '···' }}</div>
            <div v-if="st.subNext" class="sub-nxt">{{ st.subNext }}</div>
          </template>
        </div>
        <div class="asmr-player-progress">
          <span class="asmr-player-cur">{{ fmtCur }}</span>
          <input
            class="asmr-seek"
            type="range"
            min="0"
            max="1000"
            :value="asmrProgressVal"
            title="播放进度（可拖动）"
            @input="onAsmrProgressInput"
          />
          <span class="asmr-player-cur">{{ fmtDur }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
// ASMR 音声站视图组件（从 RightPanel.vue 拆出，重构 f3）。批量勾选状态四处共用
// （工具栏/列表/详情/搜索结果网格）留守 RightPanel；asmrCardTooltip 留守（结果网格共用）。
import { ref, computed, watch, reactive, nextTick } from 'vue'
import { NButton, NCheckbox, NDropdown, NInput, NModal, NSelect, NTag, NSpin, NScrollbar } from 'naive-ui'
import * as player from '../audioPlayer.js'

const props = defineProps({
  mode: { type: String, default: 'main' },               // options=工具栏+索引弹窗 | main=列表/详情
  site: { type: String, default: 'bunkr' },
  settings: { type: Object, default: () => ({}) },        // asmr_order/asmr_subtitle/asmr_seek_* 读取
  asmrView: { type: String, default: '' },                // ''=空态 | popular | works | favorites | detail
  asmrListLoading: { type: Boolean, default: false },
  asmrError: { type: String, default: '' },
  asmrFilter: { type: Object, default: () => ({ kind: '', id: '', name: '' }) }, // 当前社团/标签/声优筛选
  asmrLabel: { type: String, default: '' },
  asmrItems: { type: Array, default: () => [] },
  asmrHasMore: { type: Boolean, default: false },
  asmrOrders: { type: Object, default: () => ({}) },
  asmrIndexItems: { type: Array, default: () => [] }, // [{id, name, count}]
  asmrIndexLoading: { type: Boolean, default: false },
  asmrDetail: { type: Object, default: null },
  asmrDetailLoading: { type: Boolean, default: false },
  asmrFiles: { type: Array, default: () => [] },
  asmrRelated: { type: Array, default: () => [] },           // 相似作品（同社团随详情下发 + tags 后台补齐合并）
  asmrRelatedPending: { type: Boolean, default: false },     // tags 推荐后台补齐进行中
  asmrRecommend: { type: Array, default: () => [] },         // 收藏页推荐流（收藏 tags 相同标签作品）
  asmrBatchMode: { type: Boolean, default: false },   // 批量勾选模式（状态在 RightPanel）
  asmrBatchChecked: { type: Set, default: () => new Set() }, // 勾选的 video_id（状态在 RightPanel）
  asmrBatchRunning: { type: Boolean, default: false },
  asmrBatchProgress: { type: Object, default: () => ({ done: 0, total: 0, message: '' }) },
  translatedTitles: { type: Object, default: () => ({}) },     // {原标题: 译文}，展示时回填
  haSortItemCopied: { type: Boolean, default: false }, // 占位（无实义，避免空 props 块告警）
})

// 视频文件判定：站方 type=video 或 扩展名命中（ASMR 站部分 mp4/webm 的 type 仍是 audio）
const ASMR_VIDEO_RE = /\.(mp4|m4v|webm|mkv|mov|avi|wmv|flv|ts|mpg|mpeg|3gp|ogv)$/i
function isAsmrVideo(f) {
  if (!f) return false
  if (f.type === 'video') return true
  return ASMR_VIDEO_RE.test(String(f.title || f.path || ''))
}

const emit = defineEmits([
  'asmr-popular', 'asmr-works', 'asmr-favorites', 'asmr-more', 'asmr-video-preview', 'update:asmr-search',
  'asmr-index', 'asmr-index-pick', 'asmr-open-detail', 'asmr-detail-back', 'asmr-open-circle',
  'asmr-open-va', 'asmr-search-tag', 'asmr-toggle-favorite', 'asmr-download-files', 'open-album',
  'add-favorite', 'toggle-asmr-batch', 'toggle-asmr-batch-item', 'start-asmr-batch',
])

// ---------- 共用工具（本地副本：RightPanel 同名函数被多站点共用，留守） ----------
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

// 数字千分位
function formatCount(n) {
  if (!n || n <= 0) return '0'
  return Number(n).toLocaleString('zh-CN')
}

// 秒 → mm:ss（音轨时长展示）
function iwDuration(sec) {
  const s = Math.floor(Number(sec) || 0)
  if (!s) return ''
  const mm = Math.floor(s / 60)
  const ss = String(s % 60).padStart(2, '0')
  return `${mm}:${ss}`
}

// 字节数 → 可读大小
function formatSize(bytes) {
  if (bytes == null) return '未知'
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

// 卡片悬浮提示（社团/评分/下载数/字幕/标签）——本组件副本（RightPanel 原件供结果网格使用）
function asmrCardTooltip(item) {
  const lines = [item.album_name || '未命名']
  if (item.author) lines.push(`社团: ${item.author}`)
  if (item.rating != null) lines.push(`评分: ${item.rating}`)
  if (item.views != null) lines.push(`下载数: ${item.views}`)
  if (item.duration) lines.push(`时长: ${item.duration} 分钟`)
  if (item.has_subtitle) lines.push('带中文字幕')
  if (item.tags && item.tags.length) lines.push(`标签: ${item.tags.join(' ')}`)
  lines.push(props.asmrBatchMode ? '点击勾选/取消勾选' : '点击查看音轨列表并试听')
  return lines.join('\n')
}

// 排序下拉选项（后端 ASMR_ORDERS：release=发售日 create_date=最新入库 dl_count=下载量...）
const asmrOrderOptions = computed(() => {
  const map = props.asmrOrders || {}
  const keys = Object.keys(map)
  if (!keys.length) {
    return [
      { label: '最新入库', value: 'create_date' },
      { label: '发售日', value: 'release' },
      { label: '下载量', value: 'dl_count' },
      { label: '评分', value: 'rate_average_2dp' },
      { label: '价格', value: 'price' },
      { label: '评论数', value: 'review_count' },
    ]
  }
  return keys.map(k => ({ label: map[k], value: k }))
})


// 社团/标签/声优索引弹窗
const asmrIndexModal = ref(false)
const asmrIndexKind = ref('tags')   // 'circles' | 'tags' | 'vas'
const asmrIndexFilter = ref('')
const ASMR_INDEX_TITLES = { circles: '社团', tags: '标签', vas: '声优' }
const asmrIndexTitle = computed(() => ASMR_INDEX_TITLES[asmrIndexKind.value] || '标签')

const filteredAsmrIndex = computed(() => {
  const q = (asmrIndexFilter.value || '').trim().toLowerCase()
  const items = props.asmrIndexItems || []
  if (!q) return items.slice(0, 400)
  return items.filter(t => String(t.name || '').toLowerCase().includes(q)).slice(0, 400)
})

function showAsmrIndex(kind) {
  asmrIndexKind.value = kind
  asmrIndexModal.value = true
  asmrIndexFilter.value = ''
  emit('asmr-index', kind)
}

function pickAsmrIndex(t) {
  if (!t || !t.id) return
  asmrIndexModal.value = false
  emit('asmr-index-pick', asmrIndexKind.value, t.id, t.name)
}

// 刷新当前列表（按当前视图分发）
function refreshAsmrView() {
  if (props.asmrView === 'popular') emit('asmr-popular', 1)
  else if (props.asmrView === 'favorites') emit('asmr-favorites', 1)
  else emit('asmr-works', 1)
}

// 详情作品属性（description 为 dict；站方数据常混入数字索引键/嵌套对象垃圾，渲染降级）
const asmrDescEntries = computed(() => {
  const d = (props.asmrDetail && props.asmrDetail.description) || {}
  if (Array.isArray(d) || !d || typeof d !== 'object') return []
  const out = []
  for (const [rawKey, rawVal] of Object.entries(d)) {
    let k = String(rawKey).trim()
    let v = rawVal
    // 数字索引键：值形如 {key/name, value} 的对象 → 提取真实键值；否则为站方垃圾直接跳过
    if (/^\d+$/.test(k)) {
      if (v && typeof v === 'object' && !Array.isArray(v)) {
        k = String(v.key ?? v.name ?? v.title ?? '').trim()
        v = v.value ?? v.text ?? null
      } else {
        continue
      }
    }
    if (!k || k.length > 30) continue   // 空键/超长哈希样式键跳过
    const value = normAttrVal(v)
    if (value) out.push({ key: k, value })
    if (out.length >= 30) break
  }
  return out
})
function normAttrVal(v) {
  if (v == null) return ''
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  if (typeof v === 'string') { const s = v.trim(); return s.length > 300 ? s.slice(0, 300) + '…' : s }
  if (Array.isArray(v)) {
    const parts = v.map(x => {
      if (x == null) return ''
      if (typeof x === 'object') {
        const s = x.name ?? x.value ?? x.title
        return s != null ? String(s).trim() : ''
      }
      return String(x).trim()
    }).filter(Boolean)
    return parts.join('、').slice(0, 300)
  }
  return ''   // 嵌套对象（站方垃圾结构）不渲染
}

// 音轨文件按文件夹路径分组（保序）
const asmrFileGroups = computed(() => {
  const groups = []
  const index = new Map()
  for (const f of props.asmrFiles) {
    const path = f.path || ''
    if (!index.has(path)) {
      index.set(path, { path, files: [] })
      groups.push(index.get(path))
    }
    index.get(path).files.push(f)
  }
  return groups
})


// ============================
// 内置音频播放器（展示层）：状态/音频元素在全局 store（audioPlayer.js 样板）——
// 离开详情/切站后台续播（迷你条 AsmrMiniPlayer 接管控制），进度条与字幕也由 store 驱动
// ============================
const coverZoom = ref(false)
// 字幕显示开关（store 持久化）
const setSubOn = player.setSubOn
// 播放列表面板 + 当前曲自动滚动
const playlistVisible = ref(false)
const playlistRows = new Map()
function setPlaylistRow(el, pi) {
  if (el) playlistRows.set(pi, el)
  else playlistRows.delete(pi)
}
const st = player.playerState
const asmrPlayingFile = computed(() => st.track)
const asmrPlayingIndex = computed(() => st.index)
const asmrAudioPaused = computed(() => st.paused)
const asmrAudioMuted = computed(() => st.muted)
// 播放列表：切歌/展开面板时自动滚动到当前曲（须在 asmrPlayingFile/Index 声明之后注册）
watch([asmrPlayingFile, asmrPlayingIndex, playlistVisible], () => {
  if (!playlistVisible.value) return
  nextTick(() => {
    const el = playlistRows.get(asmrPlayingIndex.value)
    el?.scrollIntoView({ block: 'nearest' })
  })
})

const asmrVolumePercent = computed(() => Math.round((st.volume || 0) * 100))
// 进度条（0-1000 → 按时长换算秒）
const asmrProgressVal = computed(() => (st.duration ? Math.round((st.currentTime / st.duration) * 1000) : 0))
const fmtCur = computed(() => player.fmtTime(st.currentTime))
const fmtDur = computed(() => player.fmtTime(st.duration))

// 仅音频文件（播放列表展示用；播放队列快照在 store）
const asmrAudioFiles = computed(() => (props.asmrFiles || []).filter(f => f.type === 'audio' && f.play_url))
const asmrHasPrev = computed(() => st.index > 0)
const asmrHasNext = computed(() => st.index < st.queue.length - 1)

// ---------- ASMR → 通用播放器适配层（track 契约见 audioPlayer.js 头注释） ----------
// 音频行 → track：src/fallbackSrc 用本地代理与直链，字幕按"同目录+同基名"在站点层找好
function buildTracks() {
  return (props.asmrFiles || [])
    .filter(f => f.type === 'audio' && (f.play_url || f.stream_url || f.media_url))
    .map(f => {
      const sub = player.findSubtitleFor(f, props.asmrFiles || [])
      const subUrl = sub ? ((sub.play_url || sub.stream_url || sub.media_url) || '') : ''
      // subExt 必须来自字幕「文件名」——播放地址不含扩展名（样板契约，见 audioPlayer.js）
      const subExt = sub ? player.extOf(sub.title) : ''
      return {
        raw: f,
        title: f.title,
        src: (f.play_url || f.stream_url || f.media_url || ''),
        fallbackSrc: f.stream_url || '',
        subtitleSrc: subUrl,
        subExt,
      }
    })
}

// 点击音轨播放（队列=本作品全部可播音轨；音频元素/字幕加载/错误回退都在 store）
function playAsmrFile(file) {
  if (!file || file.type !== 'audio') return
  const tracks = buildTracks()
  const t = tracks.find(x => x.raw === file)
  if (!t || !t.src) return
  player.play(t, { queue: tracks, work: props.asmrDetail })
}

// 进度条拖动：0-1000 换算为秒后 seek
function onAsmrProgressInput(e) {
  player.seekTo((Number(e.target.value) / 1000) * (st.duration || 0))
}

// 音轨右键菜单（播放 / 下载此文件 / 下载整个文件夹）
const asmrFileCtx = reactive({ show: false, x: 0, y: 0, file: null })
const asmrFileCtxOptions = computed(() => {
  const f = asmrFileCtx.file
  if (!f) return []
  const opts = []
  if (f.type === 'audio') opts.push({ label: '▶ 播放此音轨', key: 'play', disabled: !f.play_url })
  opts.push({ label: '⬇ 下载此文件', key: 'download', disabled: !f.media_url })
  opts.push({ label: '⬇ 下载整个文件夹', key: 'download_folder' })
  return opts
})
function onAsmrFileContextMenu(e, f) {
  e.preventDefault()
  asmrFileCtx.show = false
  nextTick(() => {
    asmrFileCtx.file = f
    asmrFileCtx.x = e.clientX
    asmrFileCtx.y = e.clientY
    asmrFileCtx.show = true
  })
}
function onAsmrFileCtxSelect(key) {
  const f = asmrFileCtx.file
  asmrFileCtx.show = false
  if (!f) return
  if (key === 'play') {
    playAsmrFile(f)
  } else if (key === 'download') {
    emit('asmr-download-files', [f])
  } else if (key === 'download_folder') {
    // 同文件夹（含根目录）全部文件
    const list = (props.asmrFiles || []).filter(x => (x.path || '') === (f.path || '') && x.media_url)
    if (list.length) emit('asmr-download-files', list)
  }
}

// 相对当前曲目跳转（-1 上一轨 / +1 下一轨）
function playAsmrOffset(step) {
  player.playOffset(step)
}

// 播放 / 暂停
function toggleAsmrPlay() {
  player.togglePlay()
}

// 快进 / 倒带（秒数来自设置，默认快进 30 秒倒带 5 秒）
function asmrSeekBy(dir) {
  player.seekBy(
    dir,
    Number(props.settings.asmr_seek_back) || 5,
    Number(props.settings.asmr_seek_forward) || 30,
  )
}

// 静音切换（音量/记忆在 store）
function toggleAsmrMute() {
  player.toggleMute()
}

// 拖动音量条：更新音量并记忆；拖离 0 时自动取消静音
function onAsmrVolumeInput(e) {
  player.setVolume(Math.max(0, Math.min(100, Number(e.target.value) || 0)) / 100)
}

// 关闭播放器（彻底停止；后台播放时由迷你条的同款 ✕ 停止）
function stopAsmrPlayer() {
  player.stopPlayer()
}
</script>

<style scoped>
/* AsmrView 样式：asmr 系列自 RightPanel 迁出；ex/ha/tw/iw/or 系列为共用类副本（RightPanel 仍被其他站点使用） */

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
/* 标签索引弹窗 */
.or-tags-body {
  max-height: 52vh;
  overflow-y: auto;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 4px 2px 8px;
}
.or-tag-chip {
  display: inline-block;
  padding: 3px 12px;
  border-radius: 14px;
  background: rgba(99, 226, 183, 0.1);
  border: 1px solid rgba(99, 226, 183, 0.35);
  color: #63e2b7;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.or-tag-chip:hover {
  background: rgba(99, 226, 183, 0.25);
  transform: translateY(-1px);
}
.or-tags-empty {
  width: 100%;
  text-align: center;
  padding: 20px 0;
  font-size: 12px;
  color: #7a7a85;
}
.or-chip-count {
  padding: 0 6px;
  border-radius: 8px;
  background: rgba(99, 226, 183, 0.18);
  font-size: 11px;
  line-height: 16px;
}
html.light-mode .or-tag-chip {
  background: rgba(0, 128, 90, 0.06);
  border-color: rgba(0, 128, 90, 0.35);
  color: #0a7a52;
}
html.light-mode .or-tags-empty {
  color: #888;
}
html.light-mode .or-chip-count {
  background: rgba(0, 128, 90, 0.12);
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
.tw-toolbar-hint {
  font-size: 11px;
  color: #7a7a85;
  margin-left: auto;
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
/* ============================ ASMR 音声站 ============================ */
/* 工具栏"仅带字幕"勾选 */
.asmr-subtitle-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
/* 卡片字幕角标 */
.asmr-thumb-sub {
  position: absolute;
  top: 6px;
  left: 6px;
  padding: 1px 6px;
  border-radius: 8px;
  background: rgba(56, 137, 255, 0.85);
  color: #fff;
  font-size: 10px;
  line-height: 16px;
}
/* 卡片 tags 摘要行 */
.asmr-card-tags {
  font-size: 11px;
  color: #7a7a85;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 0 2px 2px;
}
/* 详情头部：封面 + 信息 */
.asmr-detail-head {
  display: flex;
  gap: 16px;
  padding: 12px 4px 6px;
}
.asmr-detail-cover {
  flex-shrink: 0;
  width: 200px;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
}
.asmr-detail-cover img {
  display: block;
  width: 100%;
  object-fit: cover;
}
.asmr-detail-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.asmr-detail-rid {
  font-size: 12px;
  color: #63e2b7;
}
.asmr-detail-circle {
  font-size: 14px;
  color: #e0e0e6;
  cursor: pointer;
}
.asmr-detail-circle:hover {
  color: #63e2b7;
}
.asmr-detail-stats {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: #9a9aa5;
}
.asmr-detail-meta {
  font-size: 12px;
  color: #7a7a85;
}
.asmr-detail-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
}
/* 作品属性表 */
.asmr-attrs {
  margin: 8px 0;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.03);
}
.asmr-attr-row {
  display: flex;
  gap: 10px;
  padding: 3px 0;
  font-size: 12px;
}
.asmr-attr-key {
  flex-shrink: 0;
  max-width: 45%;
  width: 90px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #63e2b7;
}
.asmr-attr-value {
  flex: 1;
  min-width: 0;
  color: #c8c8d0;
  word-break: break-all;
}
/* 音轨文件列表 */
.asmr-files-title {
  font-size: 13px;
  font-weight: 600;
  color: #e0e0e6;
  margin: 12px 0 6px;
}
.asmr-file-group {
  margin-bottom: 6px;
}
.asmr-folder-name {
  font-size: 12px;
  color: #63e2b7;
  padding: 6px 4px 2px;
  word-break: break-all;
}
.asmr-file-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  color: #c8c8d0;
  transition: background 0.12s ease;
}
.asmr-file-row:hover {
  background: rgba(255, 255, 255, 0.06);
}
.asmr-file-row.active {
  background: rgba(99, 226, 183, 0.14);
  color: #63e2b7;
}
.asmr-file-row.text {
  cursor: default;
  color: #7a7a85;
}
.asmr-file-row.text:hover {
  background: transparent;
}
.asmr-file-icon {
  flex-shrink: 0;
  width: 18px;
  text-align: center;
}
.asmr-file-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.asmr-file-duration,
.asmr-file-size {
  flex-shrink: 0;
  font-size: 11px;
  color: #7a7a85;
}
/* 播放器底部占位（防悬浮播放器遮挡列表） */
.asmr-cover-wrap {
  display: flex;
  justify-content: center;
  padding: 4px 14px 10px;
}

.asmr-cover-wrap img {
  max-width: min(420px, 60%);
  max-height: 46vh;
  object-fit: contain;
  border-radius: 10px;
  cursor: zoom-in;
  box-shadow: 0 4px 18px rgba(0, 0, 0, 0.4);
}

.asmr-cover-full {
  position: fixed;
  inset: 0;
  z-index: 3000;
  background: rgba(0, 0, 0, 0.88);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: zoom-out;
}

.asmr-cover-full img {
  max-width: 94vw;
  max-height: 92vh;
  object-fit: contain;
}

.gs-related {
  margin-top: 4px;
}

.gs-related-grid {
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  padding: 0 14px 10px;
}

.asmr-playlist {
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 64px;
  max-height: 42vh;
  display: flex;
  flex-direction: column;
  background: #1a1a1f;
  border: 1px solid #2d2d33;
  border-radius: 10px;
  box-shadow: 0 -6px 24px rgba(0, 0, 0, 0.5);
  z-index: 20;
}

.asmr-playlist-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 600;
  color: #e0e0e6;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.asmr-playlist-body {
  overflow-y: auto;
  padding: 4px 0 8px;
}

.asmr-playlist-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  font-size: 12px;
  color: #c8c8ce;
  cursor: pointer;
}

.asmr-playlist-row:hover {
  background: rgba(255, 255, 255, 0.04);
}

.asmr-playlist-row.active {
  color: #63e2b7;
  background: rgba(99, 226, 183, 0.08);
}

.asmr-playlist-idx {
  width: 28px;
  text-align: right;
  color: #7a7a85;
  flex-shrink: 0;
}

.asmr-playlist-row.active .asmr-playlist-idx {
  color: #63e2b7;
}

.asmr-playlist-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asmr-playlist-dur {
  flex-shrink: 0;
  color: #7a7a85;
  font-size: 11px;
}

.asmr-player-space {
  height: 132px;
}
/* 内置音频播放器（悬浮底部，锚定详情容器；纵向布局=控制行/字幕/进度行）。
   container-type 供字幕字号用 cqw 随面板宽度自适应缩放 */
.asmr-player {
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 10px;
  z-index: 20;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 8px 12px;
  border-radius: 10px;
  background: rgba(24, 24, 28, 0.96);
  border: 1px solid rgba(99, 226, 183, 0.25);
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(8px);
  container-type: inline-size;
}
.asmr-player-main {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
/* 字幕区（贴进度条上方）：双行=当前行（高亮，可换行）+ 下一行（预览，单行截断）。
   字号用 cqw 随播放器宽度缩放（界面大小自适应），并设上下限 */
.asmr-player-sub {
  display: flex;
  flex-direction: column;
  gap: 1px;
  text-align: center;
  overflow: hidden;
}
.asmr-player-sub .sub-cur {
  font-size: clamp(13px, 3.4cqw, 20px);
  line-height: 1.4;
  color: #63e2b7;
  white-space: pre-line;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.asmr-player-sub .sub-cur.dim {
  color: rgba(99, 226, 183, 0.35);
}
.asmr-player-sub .sub-nxt {
  font-size: clamp(11px, 2.6cqw, 15px);
  line-height: 1.4;
  color: rgba(99, 226, 183, 0.5);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.asmr-player-sub .sub-none {
  font-size: 11px;
  color: #7a7a85;
}
.asmr-player-sub.err .sub-cur {
  color: #e88080;
}
.asmr-player-subtoggle {
  flex-shrink: 0;
  font-size: 11px;
  color: #63e2b7;
  cursor: pointer;
  padding: 0 2px;
  user-select: none;
}
.asmr-player-subtoggle.off {
  color: #7a7a85;
  text-decoration: line-through;
}
/* 进度行：当前时间 — 可拖进度条 — 总时长 */
.asmr-player-progress {
  display: flex;
  align-items: center;
  gap: 8px;
}
.asmr-player-cur {
  flex-shrink: 0;
  font-size: 11px;
  color: #9a9aa5;
  font-variant-numeric: tabular-nums;
  min-width: 30px;
}
.asmr-seek {
  flex: 1;
  height: 4px;
  accent-color: #63e2b7;
  cursor: pointer;
}
.asmr-player-icon {
  flex-shrink: 0;
  font-size: 16px;
}
.asmr-player-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.asmr-player-name {
  font-size: 12px;
  color: #e0e0e6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.asmr-player-track {
  font-size: 10px;
  color: #7a7a85;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.asmr-player-time {
  flex-shrink: 0;
  font-size: 11px;
  color: #9a9aa5;
  font-variant-numeric: tabular-nums;
}
/* 音量条 */
.asmr-volume {
  flex-shrink: 0;
  width: 80px;
  height: 4px;
  accent-color: #63e2b7;
  cursor: pointer;
}
/* ============================ ASMR 日间模式 ============================ */
html.light-mode .asmr-thumb-sub {
  background: rgba(56, 137, 255, 0.9);
}
html.light-mode .asmr-card-tags {
  color: #8a8a95;
}
html.light-mode .asmr-detail-circle {
  color: #333;
}
html.light-mode .asmr-detail-circle:hover {
  color: #18a058;
}
html.light-mode .asmr-detail-stats {
  color: #666;
}
html.light-mode .asmr-detail-meta {
  color: #8a8a95;
}
html.light-mode .asmr-attrs {
  border-color: rgba(0, 0, 0, 0.1);
  background: rgba(0, 0, 0, 0.03);
}
html.light-mode .asmr-attr-key {
  color: #18a058;
}
html.light-mode .asmr-attr-value {
  color: #444;
}
html.light-mode .asmr-files-title {
  color: #333;
}
html.light-mode .asmr-folder-name {
  color: #18a058;
}
html.light-mode .asmr-file-row {
  color: #444;
}
html.light-mode .asmr-file-row:hover {
  background: rgba(0, 0, 0, 0.06);
}
html.light-mode .asmr-file-row.active {
  background: rgba(24, 160, 88, 0.15);
  color: #18a058;
}
html.light-mode .asmr-file-row.text {
  color: #8a8a95;
}
html.light-mode .asmr-file-duration,
html.light-mode .asmr-file-size {
  color: #8a8a95;
}
html.light-mode .asmr-player {
  background: rgba(255, 255, 255, 0.97);
  border-color: rgba(24, 160, 88, 0.35);
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.18);
}
html.light-mode .asmr-player-name {
  color: #333;
}
html.light-mode .asmr-player-track {
  color: #8a8a95;
}
html.light-mode .asmr-player-time {
  color: #666;
}
html.light-mode .asmr-player-sub .sub-cur {
  color: #18a058;
}
html.light-mode .asmr-player-sub .sub-cur.dim {
  color: rgba(24, 160, 88, 0.4);
}
html.light-mode .asmr-player-sub .sub-nxt {
  color: rgba(24, 160, 88, 0.55);
}
html.light-mode .asmr-player-sub .sub-none {
  color: #8a8a95;
}
html.light-mode .asmr-player-sub.err .sub-cur {
  color: #d03050;
}
html.light-mode .asmr-player-subtoggle {
  color: #18a058;
}
html.light-mode .asmr-player-subtoggle.off {
  color: #b0b0b8;
}
html.light-mode .asmr-player-cur {
  color: #666;
}
</style>
