<template>
  <!-- FC2 站点专属视图（按 FC站-页面设计.txt：底部 Tab 首页/分类/搜索/我的；
       播放页含播放器+相关推荐（必须）；用户页资料+视频列表。
       命令走通用 gs-command 总线（fc2_* 命令表），状态走 gs_state（view 路由）。 -->
  <div class="fc2-view">
    <!-- Header：返回 + 标题 + 搜索 -->
    <div class="fc2-header">
      <n-button
        v-if="pushedView"
        size="tiny" quaternary type="primary"
        @click="goBack"
      >← 返回</n-button>
      <span class="fc2-header-title">{{ headerTitle }}</span>
      <span class="fc2-header-hint">搜索请用顶部通用搜索框</span>
    </div>
      <!-- 批量操作悬浮条：始终悬浮在展示框上方 -->
      <div class="fc2-batch-bar">
        <template v-if="batchEnabled">
          <n-button class="batch-cta" size="small" :type="batch.mode.value ? 'warning' : 'primary'"
                    :title="batch.mode.value ? '退出勾选模式' : '点击后进入勾选模式，勾选要下载的视频'"
                    @click="batch.toggle()">{{ batch.mode.value ? '取消勾选' : '批量下载' }}</n-button>
          <template v-if="batch.mode.value && batchItems.length">
            <n-button size="tiny" title="勾选当前列表全部视频" @click="batchSelectAll">全选</n-button>
            <n-button size="tiny" title="勾选状态反转（已勾的取消、未勾的选上）" @click="batchInvert">反选</n-button>
            <n-button size="tiny" title="清空全部勾选" @click="batchClearChecked">清空</n-button>
          </template>
          <n-button v-if="batch.mode.value" size="tiny" type="error"
                    :disabled="!batch.count.value" :loading="batch.running.value"
                    title="开始下载勾选的视频（后端逐个解析最高画质）"
                    @click="startBatch">开始下载{{ batch.count.value ? `(${batch.count.value})` : '' }}</n-button>
          <span v-if="batch.running.value" class="fc2-batch-progress">
            {{ (state && state.batchProgress && state.batchProgress.message) || '准备中...' }}（{{ (state && state.batchProgress && state.batchProgress.done) || 0 }}/{{ (state && state.batchProgress && state.batchProgress.total) || 0 }}）
          </span>
          <span v-if="batch.mode.value && !batch.running.value" class="fc2-batch-progress">
            勾选模式：点击卡片选择 / 取消，再点开始下载
          </span>
        </template>
      </div>


    <!-- ===== 推入视图：详情（播放页，核心） ===== -->
    <n-scrollbar v-if="state && state.view === 'detail'" class="fc2-body">
      <div v-if="state.error" class="tw-follow-error">{{ state.error }}</div>
      <template v-else-if="state.detail">
        <div class="iw-video-area" v-if="state.detail.play_url">
          <!-- 固定 16:9 容器：任何源比例视频 letterbox 显示，杜绝画面拉伸变形；
               src 由 attachFc2Video 统一赋值：m3u8 走 hls.js（MSE），mp4 直接 el.src -->
          <div class="fc2-player-box">
            <video ref="fc2VideoEl" :poster="state.detail.thumbnail" controls preload="metadata" />
          </div>
        </div>
        <div v-else-if="state.detail.play_error" class="tw-follow-error">{{ state.detail.play_error.startsWith('NEED_LOGIN') ? '该视频需要登录 FC2（左侧登录卡）' : state.detail.play_error }}</div>
        <div class="iw-video-area" v-else-if="state.detail.thumbnail">
          <img :src="state.detail.thumbnail" referrerpolicy="no-referrer" :alt="state.detail.album_name" />
        </div>
        <div v-if="state.detail.is_sample" class="fc2-sample-tip">
          ⚠ 当前为 sample 预览片段（付费/会员内容），完整版需登录 FC2 账号
        </div>
        <div class="iw-detail-stats">
          <span v-if="state.detail.author" class="fc2-author" title="查看上传者全部视频"
                @click="openUser(state.detail)">👤 {{ state.detail.author }}</span>
          <span v-if="state.detail.duration">⏱ {{ state.detail.duration }}</span>
          <span v-if="state.detail.quality">🎞 {{ state.detail.quality.toUpperCase() }}</span>
        </div>
        <div class="iw-detail-title fc2-detail-title" :title="state.detail.album_name">{{ state.detail.album_name }}</div>
        <div v-if="state.detail.description" class="gs-desc">{{ state.detail.description }}</div>
        <div class="gs-download-bar">
          <n-button size="small" type="primary"
                    @click="sendCmd('download-files', { files: state.files || [] })">
            ⬇ 下载本视频（最高画质）
          </n-button>
          <n-button size="small" title="收藏到本地（左侧「本地收藏」可查看）"
                    @click="sendCmd('favorite', { item: { album_url: state.detail.album_url, album_name: state.detail.album_name, thumbnail: state.detail.thumbnail } })">
            ♥ 收藏
          </n-button>
        </div>
        <template v-if="(state.detail.related || []).length">
          <div class="gs-files-title">相关推荐</div>
          <div class="search-grid">
            <div v-for="r in state.detail.related" :key="r.video_id" class="search-card iw-card"
                 :title="r.album_name" @click="openDetail(r)">
              <div class="thumb-wrapper">
                <img :src="r.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="r.album_name" />
                <span v-if="r.duration" class="iw-thumb-duration">{{ r.duration }}</span>
              </div>
              <div class="card-name" :title="r.album_name">{{ r.album_name }}</div>
            </div>
          </div>
        </template>
      </template>
    </n-scrollbar>

    <!-- ===== 推入视图：用户页（资料卡 + 短信/好友/关注按钮 + 视频 Tab） ===== -->
    <n-scrollbar v-else-if="state && state.view === 'user'" class="fc2-body">
      <div v-if="state.error" class="tw-follow-error">
        {{ friendlyError }}
        <div style="margin-top: 8px"><n-button size="small" type="primary" @click="retryLast">重试</n-button></div>
      </div>
      <template v-else>
        <div class="fc2-user-card">
          <div class="fc2-user-head">
            <div class="fc2-user-avatar">
              <img v-if="state.profile.avatar" :src="state.profile.avatar" referrerpolicy="no-referrer" :alt="state.profile.name" />
              <span v-else>👤</span>
            </div>
            <div class="fc2-user-meta">
              <div class="fc2-user-name">
                {{ state.profile.name || state.profile.user_id }}
                <span v-if="state.profile.gender" class="fc2-user-gender">{{ state.profile.gender }}</span>
                <span v-if="state.profile.following" class="fc2-user-following">已关注</span>
              </div>
              <div class="fc2-user-stats">
                <button class="fc2-stat-btn" title="查看 TA 发布的视频"
                        @click="switchUserTab('content')">📹 视频 {{ (state.profile.stats && state.profile.stats['视频发布']) || '—' }}</button>
                <button class="fc2-stat-btn" title="查看 TA 关注的人"
                        @click="openRelations('following')">🔗 关注 {{ (state.profile.stats && state.profile.stats['关注']) || '—' }}</button>
                <button class="fc2-stat-btn" title="查看 TA 的粉丝"
                        @click="openRelations('followers')">👥 粉丝 {{ (state.profile.stats && state.profile.stats['粉丝']) || '—' }}</button>
                <button class="fc2-stat-btn" title="查看 TA 的好友"
                        @click="openRelations('friends')">🤝 好友 {{ (state.profile.stats && state.profile.stats['好友']) || '—' }}</button>
              </div>
            </div>
          </div>
          <div class="fc2-user-btns">
            <n-button size="tiny" title="给 TA 发送站内短消息（FC2 消息接口未开放，浏览器中操作）"
                      @click="openInBrowser(state.profile.follow_url)">✉ 短信息</n-button>
            <n-button size="tiny" title="发送好友申请（FC2 接口未开放，浏览器中操作）"
                      @click="openInBrowser(state.profile.follow_url)">🤝 好友申请</n-button>
            <n-button size="tiny" title="查看我关注的全部上传者（站内）"
                      @click="openMyFollowing">⭐ 关注管理</n-button>
          </div>
          <div v-if="state.profile.intro" class="gs-desc">{{ state.profile.intro }}</div>
        </div>
        <div class="fc2-chips">
          <button class="xh-sort-chip" :class="{ on: userTab === 'content' }"
                  @click="switchUserTab('content')">📹 视频发布{{ countText('video') }}</button>
          <button class="xh-sort-chip" :class="{ on: userTab === 'album' }"
                  @click="switchUserTab('album')">⭐ 收藏{{ countText('album') }}</button>
          <template v-if="userTab === 'content'">
            <button class="xh-sort-chip" :class="{ on: userGroup === 'adult' }"
                    @click="switchUserGroup('adult')">成人{{ countText('adult') }}</button>
            <button class="xh-sort-chip" :class="{ on: userGroup === 'general' }"
                    @click="switchUserGroup('general')">一般{{ countText('general') }}</button>
          </template>
        </div>
        <div v-if="state.loading && !(state.items || []).length" class="tw-follow-empty">
          <n-spin size="medium" /><span>正在获取...</span>
        </div>
        <div v-else-if="!(state.items || []).length" class="tw-follow-empty">该分组暂无视频</div>
        <div v-else class="search-grid">
          <div v-if="state.has_more && (state.items || []).length" class="tw-browse-more" style="grid-column: 1 / -1; padding: 0 0 6px">
            <n-button size="tiny" quaternary block :loading="state.loading"
                      @click="sendCmd('user', { user_id: state.profile.user_id, tab: userTab, page: (state.page || 1) + 1 })"
            >加载更多</n-button>
          </div>
          <div v-for="item in state.items" :key="item.video_id" class="search-card iw-card"
               :class="{ 'iw-batch-checked': batch.mode.value && batch.checked.value.has(item.video_id) }"
               :title="item.album_name"
               @click="batch.mode.value ? batch.toggleItem(item.video_id) : openDetail(item)">
            <div class="thumb-wrapper">
              <img :src="item.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name" />
              <span v-if="item.duration" class="iw-thumb-duration">{{ item.duration }}</span>
              <span v-if="item.posted" class="fc2-thumb-date">{{ item.posted }}</span>
              <span v-if="batch.mode.value" class="iw-batch-check"
                    :class="{ checked: batch.checked.value.has(item.video_id) }">{{ batch.checked.value.has(item.video_id) ? '✓' : '' }}</span>
            </div>
            <div class="card-name" :title="item.album_name">{{ item.album_name }}</div>
          </div>
        </div>
        <div v-if="state.has_more" class="tw-browse-more">
          <n-button quaternary block :loading="state.loading"
                    @click="sendCmd('user', { user_id: state.profile.user_id, tab: userTab, page: (state.page || 1) + 1 })">加载更多</n-button>
        </div>
      </template>
    </n-scrollbar>

    <!-- ===== 推入视图：列表（通用搜索/分类结果） ===== -->
    <n-scrollbar v-else-if="state && state.view === 'list'" class="fc2-body">
      <div class="fc2-chips"><button class="xh-sort-chip on">{{ state.label || '列表' }}</button></div>
      <div v-if="state.error" class="tw-follow-error">{{ friendlyError }}</div>
      <div v-else-if="state.loading && !(state.items || []).length" class="tw-follow-empty">
        <n-spin size="medium" /><span>正在获取...</span>
      </div>
      <div v-else-if="!(state.items || []).length" class="tw-follow-empty">{{ friendlyError || '没有找到相关视频' }}</div>
      <div v-else class="search-grid">
        <div v-if="state.has_more && (state.items || []).length" class="tw-browse-more" style="grid-column: 1 / -1; padding: 0 0 6px">
          <n-button size="tiny" quaternary block :loading="state.loading"
                    @click="sendCmd(lastListCmd, { ...(lastListPayload || {}), page: (state.page || 1) + 1 })"
          >加载更多</n-button>
        </div>
        <div v-for="item in state.items" :key="item.video_id" class="search-card iw-card"
             :class="{ 'iw-batch-checked': batch.mode.value && batch.checked.value.has(item.video_id) }"
             :title="item.album_name"
             @click="batch.mode.value ? batch.toggleItem(item.video_id) : openDetail(item)">
          <div class="thumb-wrapper">
            <img :src="item.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name" />
            <span v-if="item.duration" class="iw-thumb-duration">{{ item.duration }}</span>
            <span v-if="batch.mode.value" class="iw-batch-check"
                  :class="{ checked: batch.checked.value.has(item.video_id) }">{{ batch.checked.value.has(item.video_id) ? '✓' : '' }}</span>
            <span v-if="item.author" class="fc2-thumb-author">👤 {{ item.author }}</span>
          </div>
          <div class="card-name" :title="item.album_name">{{ item.album_name }}</div>
        </div>
      </div>
      <div v-if="state.has_more" class="tw-browse-more">
        <n-button quaternary block :loading="state.loading"
                  @click="sendCmd(lastListCmd, { ...(lastListPayload || {}), page: (state.page || 1) + 1 })">加载更多</n-button>
      </div>
    </n-scrollbar>

    <!-- ===== 推入视图：关系列表（关注/粉丝/好友） ===== -->
    <n-scrollbar v-else-if="state && state.view === 'relations'" class="fc2-body">
      <div class="fc2-chips">
        <button class="xh-sort-chip on" @click="goBack">← {{ state.label || '列表' }}</button>
      </div>
      <div v-if="state.error" class="tw-follow-error">
        {{ friendlyError }}
        <div style="margin-top: 8px"><n-button size="small" type="primary" @click="retryLast">重试</n-button></div>
      </div>
      <div v-else-if="state.loading" class="tw-follow-empty"><n-spin size="medium" /><span>正在获取...</span></div>
      <div v-else-if="!(state.items || []).length" class="tw-follow-empty">暂无数据</div>
      <div v-else class="search-grid">
        <div v-for="u in state.items" :key="u.user_id" class="search-card iw-card fc2-follow-card"
             :title="u.name" @click="sendCmd('user', { user_id: u.user_id, page: 1 })">
          <div class="fc2-follow-avatar">
            <img v-if="u.avatar" :src="u.avatar" loading="lazy" referrerpolicy="no-referrer" :alt="u.name" />
            <span v-else>👤</span>
          </div>
          <div class="card-name">{{ u.name }}</div>
        </div>
      </div>
    </n-scrollbar>

    <!-- ===== 底部 Tab 内容 ===== -->
    <template v-else>
      <!-- 首页：筛选 chips + 网格 -->
      <n-scrollbar v-if="fc2Tab === 'home'" class="fc2-body">
        <div class="fc2-chips">
          <button v-for="c in homeChips" :key="c.key" class="xh-sort-chip"
                  :class="{ on: homeTab === c.key }"
                  @click="switchHome(c.key)">{{ c.label }}</button>
          <button class="xh-sort-chip" title="重新加载当前列表"
                  @click="sendCmd('home', { tab: homeTab, page: 1 })">↻ 刷新</button>
        </div>
        <div v-if="homeView.error && !suppressPush" class="tw-follow-error">
          {{ friendlyError }}
          <div style="margin-top: 8px; display: flex; gap: 8px; justify-content: center">
            <n-button v-if="needLogin" size="small" type="primary" @click="sendCmd('open-login', {})">打开内置浏览器登录</n-button>
            <n-button size="small" @click="retryLast">重试</n-button>
          </div>
        </div>
        <div v-else-if="homeView.loading && !homeView.items.length" class="tw-follow-empty">
          <n-spin size="medium" /><span>正在获取内容...</span>
        </div>
        <div v-else-if="!homeView.items.length" class="tw-follow-empty">暂无内容</div>
        <div v-else class="search-grid">
            <div v-if="homeView.items.length && homeView.has_more && !suppressPush" class="tw-browse-more" style="grid-column: 1 / -1; padding: 0 0 6px">
              <n-button size="tiny" quaternary block :loading="homeView.loading" @click="sendCmd('home', { tab: homeTab, page: (homeView.page || 1) + 1 })"
              >加载更多</n-button>
            </div>
          <div v-for="item in homeView.items" :key="item.video_id" class="search-card iw-card"
               :class="{ 'iw-batch-checked': batch.mode.value && batch.checked.value.has(item.video_id) }"
               :title="item.album_name"
               @click="batch.mode.value ? batch.toggleItem(item.video_id) : openDetail(item)">
            <div class="thumb-wrapper">
              <img :src="item.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name" />
              <span v-if="item.duration" class="iw-thumb-duration">{{ item.duration }}</span>
              <span v-if="item.posted" class="fc2-thumb-date">{{ item.posted }}</span>
              <span v-if="item.author" class="fc2-thumb-author">👤 {{ item.author }}</span>
              <span v-if="batch.mode.value" class="iw-batch-check"
                    :class="{ checked: batch.checked.value.has(item.video_id) }">{{ batch.checked.value.has(item.video_id) ? '✓' : '' }}</span>
              <button v-else class="card-favorite-btn" title="收藏到本地"
                      @click.stop="sendCmd('favorite', { item })">♥</button>
            </div>
            <div class="card-name" :title="item.album_name">{{ item.album_name }}</div>
          </div>
        </div>
        <div v-if="homeView.items.length && homeView.has_more && !suppressPush" class="tw-browse-more">
          <n-button quaternary block :loading="homeView.loading"
                    @click="sendCmd('home', { tab: homeTab, page: (homeView.page || 1) + 1 })">加载更多</n-button>
        </div>
      </n-scrollbar>

      <!-- 分类：网格 → 点击进分类列表 -->
      <n-scrollbar v-else-if="fc2Tab === 'categories'" class="fc2-body">
        <div class="fc2-cat-grid">
          <button v-for="c in catItems" :key="c.id" class="fc2-cat-card"
                  @click="sendCmd('list', { category_id: c.id })">{{ c.name }}</button>
        </div>
      </n-scrollbar>
      <!-- 分类列表结果 -->
      <n-scrollbar v-else-if="fc2Tab === 'categories' && state && state.view === 'list'" class="fc2-body">
        <div class="fc2-chips"><button class="xh-sort-chip on" @click="loadCategories">← 全部分类</button></div>
        <div class="search-grid">
          <div v-for="item in state.items" :key="item.video_id" class="search-card iw-card"
               :title="item.album_name" @click="openDetail(item)">
            <div class="thumb-wrapper">
              <img :src="item.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name" />
              <span v-if="item.duration" class="iw-thumb-duration">{{ item.duration }}</span>
            </div>
            <div class="card-name" :title="item.album_name">{{ item.album_name }}</div>
          </div>
        </div>
      </n-scrollbar>

      <!-- 我的：我的关注（上传者）+ 本地收藏 -->
      <n-scrollbar v-else-if="fc2Tab === 'my'" class="fc2-body">
        <!-- 我的关注：登录后显示关注的上传者，点击进 TA 的用户页 -->
        <div class="fc2-chips">
          <button class="xh-sort-chip on">我的关注</button>
          <button class="xh-sort-chip" @click="sendCmd('following', {})">↻ 刷新</button>
        </div>
        <div v-if="state && state.view === 'following' && state.error" class="tw-follow-error">
          {{ friendlyError }}
          <div style="margin-top: 8px"><n-button size="small" type="primary" @click="retryLast">重试</n-button></div>
        </div>
        <div v-else-if="state && state.view === 'following' && state.loading" class="tw-follow-empty">
          <n-spin size="medium" /><span>正在获取关注列表...</span>
        </div>
        <div v-else-if="state && state.view === 'following' && !(state.items || []).length" class="tw-follow-empty">
          暂无关注的上传者（在视频详情点 👤 进入其主页）
        </div>
        <div v-else-if="state && state.view === 'following'" class="search-grid">
          <div v-for="u in state.items" :key="u.user_id" class="search-card iw-card fc2-follow-card"
               :title="u.name" @click="sendCmd('user', { user_id: u.user_id, page: 1 })">
            <div class="fc2-follow-avatar">
              <img v-if="u.avatar" :src="u.avatar" loading="lazy" referrerpolicy="no-referrer" :alt="u.name" />
              <span v-else>👤</span>
            </div>
            <div class="card-name">{{ u.name }}</div>
          </div>
        </div>
        <div v-else class="tw-follow-empty">切到本页自动加载（需登录）</div>

        <div class="fc2-chips" style="margin-top: 6px"><button class="xh-sort-chip on">我的收藏（本机）</button></div>
        <div v-if="!fc2Favorites.length" class="tw-follow-empty">
          暂无收藏。卡片上的 ♥ 可收藏视频；下载进度请点右上角下载管理图标查看
        </div>
        <div v-else class="search-grid">
          <div v-for="f in fc2Favorites" :key="f.id" class="search-card iw-card" :title="f.title"
               @click="openFavorite(f)">
            <div class="thumb-wrapper">
              <img v-if="f.thumbnail" :src="f.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="f.title" />
            </div>
            <div class="card-name">{{ f.title }}</div>
          </div>
        </div>
      </n-scrollbar>
    </template>

    <!-- 底部 Tab Bar：首页/分类/搜索/我的 -->
    <div class="fc2-tabbar">
      <button v-for="t in tabs" :key="t.key" class="fc2-tab"
              :class="{ on: fc2Tab === t.key }"
              :title="t.title"
              @click="switchTab(t.key)">
        <span class="fc2-tab-icon">{{ t.icon }}</span>
        <span>{{ t.label }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
// FC2 专属视图（2026-09-10）：按 FC站-页面设计.txt 的精简导航实现。
// 数据命令走 gs-command 总线（后端 fc2_* 命令表），状态走 gs_state（view 路由：
// home=首页三 Tab / categories=分类页 / list=搜索与分类结果 / detail=播放页 / user=上传者页）。
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { NButton, NSpin, NScrollbar } from 'naive-ui'
import Hls from 'hls.js'
import { gsConfigFor } from '../siteConfigs.js'
import { useBatchSelection } from '../useBatchSelection.js'

const props = defineProps({
  site: { type: String, default: 'fc2' },
  state: { type: Object, default: null },        // App.gsStates['fc2']
  localFavorites: { type: Array, default: () => [] },
})
const emit = defineEmits(['gs-command', 'gs-restore-state'])

const tabs = [
  { key: 'home', label: '首页', icon: '🏠', title: '推荐 / 新着 / 人气' },
  { key: 'categories', label: '分类', icon: '🗂️', title: '全站分类' },
  { key: 'my', label: '我的', icon: '👤', title: '我的关注 + 本地收藏' },
]
const homeChips = [
  { key: 'recommend', label: '推荐' },
  { key: 'new', label: '新着' },
  { key: 'popular', label: '人气' },
]

const fc2Tab = ref('home')
const homeTab = ref('new')
const searchDraft = ref('')
const lastQuery = ref('')
const lastListCmd = ref('search')
const lastListPayload = ref(null)
const userTab = ref('content')
const userGroup = ref('adult')

function switchUserTab(tab) {
  userTab.value = tab
  const pid = state.value && state.value.profile && state.value.profile.user_id
  if (pid) sendCmd('user', { user_id: pid, tab, group: userGroup.value, page: 1 })
}

function switchUserGroup(group) {
  userGroup.value = group
  const pid = state.value && state.value.profile && state.value.profile.user_id
  if (pid) sendCmd('user', { user_id: pid, tab: 'content', group, page: 1 })
}

function openInBrowser(url) {
  if (url && window.api && window.api.openExternal) window.api.openExternal(url)
}

// 分区数量文本（视频发布/收藏/成人/一般；后端 fc2_user 估算，无数据时不显示）
function countText(key) {
  const c = state.value && state.value.profile && state.value.profile.counts
  const n = c && c[key]
  return (typeof n === 'number') ? ` ${n}` : ''
}

// 关注管理站内化：跳到「我的」Tab 并拉取我的关注列表（不再跳浏览器）
function openMyFollowing() {
  fc2Tab.value = 'my'
  sendCmd('following', {})
}

function openRelations(kind) {
  const pid = state.value && state.value.profile && state.value.profile.user_id
  if (pid) sendCmd('user_relations', { user_id: pid, kind })
}

const state = computed(() => props.state)

// 首页/分类缓存：点进详情后返回时直接恢复，不再重新请求（解决"返回后之前界面没有缓存"）
const homeCache = ref(null)    // {items, page, has_more, total, label, tab}
const catCache = ref(null)     // {items}
watch(() => state.value && state.value.view, (v) => {
  const st = state.value
  if (!st || st.loading) return
  if (v === 'home') homeCache.value = { items: st.items || [], page: st.page, has_more: st.has_more, total: st.total, label: st.label, tab: st.tab }
  if (v === 'categories') catCache.value = { items: st.items || [] }
}, { immediate: true, deep: false })

// 分类兜底（站方 /a/search/video/ 偶发 302 时仍可浏览；2026-09-10 实测抓取）
const FALLBACK_CATS = [
  { id: '18', name: '巨乳・美乳' }, { id: '30', name: '新人・清纯' },
  { id: '36', name: '明星' }, { id: '22', name: '人妻・熟女' },
  { id: '17', name: 'OL' }, { id: '29', name: 'SM・凌辱' },
  { id: '27', name: '恋物癖・变态' }, { id: '19', name: '自拍' },
  { id: '26', name: '自慰' }, { id: '25', name: '野外・露出' },
  { id: '24', name: 'Cosplay・制服' }, { id: '23', name: '美臀・肛门' },
  { id: '31', name: '乱交・3P' }, { id: '21', name: '颜射・体外射精・口内射精' },
  { id: '20', name: '口交' }, { id: '16', name: '体内射精' },
  { id: '40', name: '色情动漫・游戏' }, { id: '32', name: '色情视频' },
  { id: '49', name: '性感的姊姊' },
].map(c => ({ ...c, kind: 'category', site: 'fc2' }))
const catItems = computed(() => {
  const live = (suppressPush.value ? (catCache.value && catCache.value.items) : null)
    || (state.value && state.value.view === 'categories' ? (state.value.items || []) : [])
  return live.length ? live : FALLBACK_CATS
})

// home 视图数据：suppressPush（返回）时用缓存，否则用 state（并写入缓存）
const homeView = computed(() => {
  if (suppressPush.value && homeCache.value) return { loading: false, error: '', ...homeCache.value }
  const st = state.value
  if (st && st.view === 'home') {
    return { items: st.items || [], page: st.page, has_more: st.has_more, total: st.total,
             label: st.label, tab: st.tab, loading: !!st.loading, error: st.error || '' }
  }
  return homeCache.value || { items: [], loading: !!(st && st.loading), error: '' }
})
const suppressPush = ref(false)       // 返回到 Tab 层时置真：直接用本地缓存渲染 Tab 内容
const lastTabBeforePush = ref('home')
const pushedView = computed(() => !suppressPush.value && state.value && ['detail', 'user', 'list', 'relations'].includes(state.value.view))
const fc2Favorites = computed(() => (props.localFavorites || []).filter(f => f.site === 'fc2'))
const headerTitle = computed(() => {
  if (pushedView.value) {
    if (state.value.view === 'detail') return state.value.detail?.album_name || '视频详情'
    if (state.value.view === 'user') return `@${state.value.profile?.name || state.value.profile?.user_id || ''}`
    return state.value.label || '列表'
  }
  return { home: 'FC2', categories: '分类', search: '搜索', my: '我的' }[fc2Tab.value] || 'FC2'
})

const lastCommand = ref(null)   // {cmd, payload}——错误区"重试"按钮复用

// 批量勾选（m7 通用模块）；批量条常驻显示与否取决于站点配置（与 GSV 契约一致）
const batch = useBatchSelection()
const batchEnabled = computed(() => !!(gsConfigFor('fc2') && gsConfigFor('fc2').batch))

// 当前视图可勾选的条目（首页网格 / 用户页 / 列表；详情视图无列表不提供）
const batchItems = computed(() => {
  const st = state.value
  const v = st && st.view
  if (v === 'user' || v === 'list') return (st.items || []).filter(i => i && i.video_id)
  if (!suppressPush.value && fc2Tab.value === 'home') {
    return (homeView.value.items || []).filter(i => i && i.video_id)
  }
  return []
})

function batchSelectAll() {
  batch.checked.value = new Set(batchItems.value.map(i => i.video_id))
}

function batchInvert() {
  const ids = batchItems.value.map(i => i.video_id)
  const next = new Set([...batch.checked.value].filter(id => !ids.includes(id)))
  for (const id of ids) if (!next.has(id)) next.add(id)
  batch.checked.value = next
}

function batchClearChecked() {
  batch.checked.value = new Set()
}

function startBatch() {
  const ids = [...batch.checked.value]
  if (!ids.length) return
  const out = batch.start(() => ids)
  if (out) sendCmd('batch_download', { ids: out })
}

function sendCmd(cmd, payload = {}) {
  suppressPush.value = false
  recordPush(cmd, payload)
  lastCommand.value = { cmd, payload }
  if (cmd === 'search' || cmd === 'list') {
    lastListCmd.value = cmd
    lastListPayload.value = { ...payload }
  }
  emit('gs-command', { site: 'fc2', cmd, ...payload })
}

// ---------- 多级返回栈 ----------
// 推入类命令（详情/用户/关系列表/搜索与分类列表）。元素两种：
//   { state } 二级以上推入时的视图快照——props.state 是后端 emit 的整体对象，新命令
//             到达后 App 会整体替换成新对象，旧引用天然成为不可变快照；
//   { tab }   第一级推入时记录的返回 Tab。
const PUSH_CMDS = { open_detail: 1, user: 1, user_relations: 1, search: 1, list: 1 }
const viewStack = ref([])

function recordPush(cmd, payload) {
  if (!PUSH_CMDS[cmd]) return
  const st = state.value
  const inPushed = pushedView.value || (st && st.view === 'relations')
  if (inPushed) {
    // 同视图刷新/翻页（用户页切 Tab/分组、列表加载更多）不加深返回链
    if (cmd === 'user' && st.profile && String(st.profile.user_id) === String(payload.user_id || '')) return
    if ((cmd === 'search' || cmd === 'list' || cmd === 'user') && Number(payload.page || 1) > 1) return
    viewStack.value.push({ state: st })
  } else {
    lastTabBeforePush.value = fc2Tab.value
    viewStack.value.push({ tab: fc2Tab.value })
  }
}

function retryLast() {
  const c = lastCommand.value
  if (c) sendCmd(c.cmd, c.payload)
}

const friendlyError = computed(() => {
  const e = (state.value && state.value.error) || ''
  if (e.startsWith('NEED_LOGIN')) return '该内容需要登录 FC2——点下方按钮直接打开登录窗口'
  return e
})

const needLogin = computed(() => !!((state.value && state.value.error) || '').startsWith('NEED_LOGIN'))

// ---------- 详情播放器（hls.js，对齐 XhView 模式）----------
// FC2 免费视频 type=2 是 HLS m3u8，Chromium 裸 <video> 播不了（有海报画面但进度条 0:00）。
// play_url 已是媒体代理地址（m3u8 经代理内容重写为分片代理绝对地址），直接喂给 hls.js。
const fc2VideoEl = ref(null)
let fc2Hls = null

function detachFc2Hls() {
  if (fc2Hls) { fc2Hls.destroy(); fc2Hls = null }
}

function attachFc2Video() {
  const el = fc2VideoEl.value
  const d = state.value && state.value.detail
  detachFc2Hls()
  if (!el || !d || !d.play_url) return
  const isHls = String(d.play_type || '') === '2' || (d.play_url || '').toLowerCase().includes('.m3u8')
  if (isHls && Hls.isSupported()) {
    fc2Hls = new Hls()
    fc2Hls.on(Hls.Events.ERROR, (_e, data) => {
      if (data.fatal) console.log('[FC2播放] HLS致命错误:', data.type, data.details)
    })
    fc2Hls.loadSource(d.play_url)
    fc2Hls.attachMedia(el)
    return
  }
  el.src = d.play_url   // mp4 直链（或 Safari 原生 HLS 兜底）
  el.load()
}

watch(() => state.value && state.value.detail, () => { nextTick(attachFc2Video) })
onUnmounted(detachFc2Hls)

function switchTab(key) {
  fc2Tab.value = key
  viewStack.value = []   // 切 Tab = 重新开始浏览，清多级返回链
  if (key === 'home' && !(state.value && (state.value.items || []).length && state.value.view === 'home')) {
    sendCmd('home', { tab: homeTab.value, page: 1 })
  }
  if (key === 'categories' && !(state.value && state.value.view === 'categories')) {
    sendCmd('categories', {})
  }
  if (key === 'my' && !(state.value && state.value.view === 'following')) {
    sendCmd('following', {})
  }
}

function switchHome(key) {
  homeTab.value = key
  sendCmd('home', { tab: key, page: 1 })
}

function submitSearch() {
  const q = (searchDraft.value || '').trim()
  if (!q) return
  lastQuery.value = q
  fc2Tab.value = 'search'
  sendCmd('search', { query: q, page: 1 })
}

function loadCategories() {
  sendCmd('categories', {})
}

function openDetail(item) {
  if (item && item.video_id) sendCmd('open_detail', { item })
}

function openUser(detail) {
  const id = detail.author_id || (detail.author_url || '').match(/account\/(\d+)/)?.[1] || ''
  if (id) sendCmd('user', { user_id: id, page: 1 })
}

function openFavorite(f) {
  // 兼容两种卡片链接形态：免费区 /content/{id} 与成人区 /a/content/{id}
  const m = (f.url || '').match(/\/(?:a\/)?content\/([0-9A-Za-z]{12,20})/)
  if (m) sendCmd('open_detail', { item: { video_id: m[1], album_url: f.url } })
}

function goBack() {
  const st = state.value
  const inPushed = pushedView.value || (st && st.view === 'relations')
  if (inPushed && viewStack.value.length) {
    const snap = viewStack.value.pop()
    if (snap && snap.state) {
      // 多级返回：直接把上一推入视图的状态快照写回站点状态（不重新请求）
      emit('gs-restore-state', { site: props.site || 'fc2', state: snap.state })
      suppressPush.value = false
      return
    }
    // { tab } 层：回到推入前的 Tab（本地缓存恢复，不重新请求）
    suppressPush.value = true
    fc2Tab.value = (snap && snap.tab) || lastTabBeforePush.value || 'home'
    if (fc2Tab.value === 'home' && !homeCache.value) sendCmd('home', { tab: homeTab.value, page: 1 })
    if (fc2Tab.value === 'categories') loadCategories()
    return
  }
  // 兜底：栈空回 Tab
  suppressPush.value = true
  fc2Tab.value = lastTabBeforePush.value || 'home'
  if (fc2Tab.value === 'home' && !homeCache.value) sendCmd('home', { tab: homeTab.value, page: 1 })
  if (fc2Tab.value === 'categories') loadCategories()
}

onMounted(() => {
  if (!state.value) sendCmd('home', { tab: homeTab.value, page: 1 })
})
</script>

<style scoped>
/* 暗色体系与 GSV/RightPanel 一致（应用为固定暗色设计） */
.fc2-view {
  flex: 1; min-height: 0; display: flex; flex-direction: column;
  color: #e0e0e6; background: #17171a;
}
.fc2-header {
  display: flex; align-items: center; gap: 8px; padding: 6px 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.fc2-header-title {
  font-weight: 600; font-size: 13px; max-width: 30%;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.fc2-header-search { margin-left: auto; display: flex; gap: 4px; }
.fc2-search-input {
  width: 180px; padding: 3px 8px; font-size: 12px;
  border: 1px solid #2d2d33; border-radius: 4px;
  background: #1e1e22; color: #e0e0e6;
}
.fc2-body { flex: 1; min-height: 0; }
.fc2-chips {
  display: flex; gap: 6px; padding: 8px 10px 2px; flex-wrap: wrap;
  position: sticky; top: 0; z-index: 5; background: #17171a;
}
/* 批量操作悬浮条：始终悬浮在 FC2 展示框上方（n-scrollbar 内 sticky 失效场景兜底） */
.fc2-batch-bar {
  position: sticky; top: 0; z-index: 6; display: flex; gap: 8px; align-items: center;
  padding: 6px 10px; background: #1f1f24; border-bottom: 1px solid rgba(99, 226, 183, 0.25);
}
/* 排序 chip（对齐 XhView 暗色） */
.xh-sort-chip {
  padding: 3px 12px; font-size: 12px; border-radius: 14px;
  border: 1px solid #2d2d33; background: #1e1e22; color: #c8c8ce; cursor: pointer;
}
.xh-sort-chip.on { border-color: #63e2b7; color: #63e2b7; }
.fc2-sample-tip {
  padding: 6px 10px; font-size: 12px; color: #e6a23c;
  background: rgba(230, 162, 60, 0.12); border-radius: 4px; margin: 6px 10px;
}
.fc2-author { cursor: pointer; }
.fc2-author:hover { text-decoration: underline; }
.fc2-detail-title { padding: 4px 10px; font-size: 13px; font-weight: 600; }
.fc2-user-card { padding: 10px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); }
.fc2-user-head { display: flex; gap: 10px; align-items: center; }
.fc2-user-avatar {
  width: 56px; height: 56px; border-radius: 50%; background: #26262b; overflow: hidden;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.fc2-user-avatar img { width: 100%; height: 100%; object-fit: cover; }
.fc2-user-meta { flex: 1; min-width: 0; }
.fc2-user-name { font-weight: 600; font-size: 14px; }
.fc2-user-gender {
  font-size: 11px; margin-left: 6px; padding: 1px 6px; border-radius: 8px;
  background: rgba(255, 107, 129, 0.15); color: #ff6b81;
}
.fc2-user-following {
  font-size: 11px; margin-left: 6px; padding: 1px 6px; border-radius: 8px;
  background: rgba(99, 226, 183, 0.15); color: #63e2b7;
}
.fc2-user-stats { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 4px; font-size: 12px; color: #9a9aa2; }
.fc2-user-btns { display: flex; gap: 6px; padding: 6px 0 2px; }
.fc2-cat-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px; padding: 10px;
}
.fc2-cat-card {
  padding: 14px 8px; text-align: center; font-size: 13px;
  border: 1px solid #2d2d33; border-radius: 6px;
  background: #1e1e22; color: #e0e0e6; cursor: pointer;
}
.fc2-cat-card:hover { border-color: #63e2b7; color: #63e2b7; }
.fc2-tabbar { display: flex; border-top: 1px solid rgba(255, 255, 255, 0.1); background: #17171a; }
.fc2-tab {
  flex: 1; padding: 6px 0 7px; display: flex; flex-direction: column; align-items: center;
  gap: 2px; font-size: 11px; background: transparent; color: #9a9aa2;
  border: none; cursor: pointer; opacity: 0.85;
}
.fc2-tab.on { opacity: 1; color: #63e2b7; }
.fc2-tab-icon { font-size: 16px; }
.fc2-stat-btn {
  padding: 3px 10px; font-size: 12px; border-radius: 4px;
  border: 1px solid #2d2d33; background: #1e1e22; color: #e0e0e6; cursor: pointer;
}
.fc2-stat-btn:hover { border-color: #63e2b7; color: #63e2b7; }
.fc2-thumb-date {
  position: absolute; right: 6px; top: 6px;
  background: rgba(0, 0, 0, 0.65); color: #e0e0e6; font-size: 11px;
  padding: 1px 5px; border-radius: 3px;
}
/* 上传者角标（左上，避开 时长左下/日期与勾选右上） */
.fc2-thumb-author {
  position: absolute; left: 6px; top: 6px; max-width: 62%;
  background: rgba(0, 0, 0, 0.65); color: #c8c8ce; font-size: 11px;
  padding: 1px 5px; border-radius: 3px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.fc2-batch-progress { font-size: 11px; color: #9a9aa2; }
.iw-batch-check {
  position: absolute; top: 6px; right: 6px; width: 24px; height: 24px;
  border: 2px solid #63e2b7; border-radius: 50%; background: rgba(0, 0, 0, 0.5);
  color: #63e2b7; font-size: 14px; line-height: 20px; text-align: center; font-weight: 700;
}
.iw-batch-check.checked { background: #63e2b7; color: #17171a; }
.search-card.iw-batch-checked { border-color: #63e2b7; }
.fc2-follow-card { text-align: center; }
.fc2-follow-avatar {
  aspect-ratio: 1 / 1; background: #26262b; overflow: hidden;
  display: flex; align-items: center; justify-content: center; font-size: 28px;
}
.fc2-follow-avatar img { width: 100%; height: 100%; object-fit: cover; }
/* 卡片网格（GSV 同款暗色） */
.search-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 12px; padding: 8px 10px 10px;
}
.search-card {
  background: #1e1e22; border: 1px solid #2d2d33; border-radius: 10px;
  overflow: hidden; cursor: pointer; transition: border-color 0.15s, transform 0.15s;
}
.search-card:hover { border-color: #63e2b7; }
.thumb-wrapper {
  position: relative; aspect-ratio: 4 / 3; background: #26262b; overflow: hidden;
}
.thumb-wrapper img { width: 100%; height: 100%; object-fit: cover; }
.card-name {
  padding: 8px 10px; font-size: 12.5px; color: #e0e0e6; line-height: 1.35;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.iw-thumb-duration {
  position: absolute; left: 6px; bottom: 6px;
  background: rgba(0, 0, 0, 0.65); color: #e0e0e6; font-size: 11px;
  padding: 1px 5px; border-radius: 3px;
}
.card-favorite-btn {
  position: absolute; top: 6px; right: 6px; width: 26px; height: 26px;
  border: none; border-radius: 50%; background: rgba(0, 0, 0, 0.55);
  color: #9a9aa2; cursor: pointer; font-size: 13px; opacity: 0;
  transition: opacity 0.15s;
}
.search-card:hover .card-favorite-btn { opacity: 1; }
.card-favorite-btn:hover { color: #ff6b81; transform: scale(1.15); }
.iw-video-area { padding: 0 10px; }
.iw-video-area video, .iw-video-area img {
  width: 100%; max-height: 340px; border-radius: 6px; background: #000; object-fit: contain;
}
/* 播放器固定 16:9 容器：video 填满容器 + contain（任何源比例都居中 letterbox 不变形） */
.fc2-player-box {
  aspect-ratio: 16 / 9; width: 100%; max-height: min(60vh, 480px);
  display: flex; align-items: center; justify-content: center;
  background: #000; border-radius: 6px; overflow: hidden;
}
.fc2-player-box video {
  width: 100%; height: 100%; max-height: 100%; object-fit: contain; background: #000;
}
.iw-detail-stats { display: flex; gap: 12px; padding: 6px 10px; font-size: 12px; color: #9a9aa2; }
.iw-detail-title { padding: 4px 10px; font-weight: 600; }
.gs-desc {
  margin: 4px 10px 8px; padding: 8px 10px;
  background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px; font-size: 12.5px; color: #c8c8ce;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.gs-download-bar { display: flex; gap: 8px; padding: 8px 10px 10px; }
.gs-files-title {
  padding: 10px 10px 6px; font-size: 13px; font-weight: 600; color: #e0e0e6;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}
.tw-browse-more { padding: 6px 10px 12px; }
.tw-follow-error { padding: 20px 12px; color: #e88080; text-align: center; font-size: 13px; }
.tw-follow-empty { padding: 30px 12px; text-align: center; color: #9a9aa2; font-size: 13px; }
</style>