<template>
  <!-- xHamster 浏览视图（类 App 布局：顶部 Header + 内容区 + 底部 Tab 首页/分类/短视频/消息/我的；
       详情/用户/分类列表为二级视图，Header 显示返回）。
       从 RightPanel.vue 拆出（f1）：状态在 App.vue，经 RightPanel 透传 props；事件上行由 RightPanel 转发 -->
  <div class="xh-app">
    <!-- 顶部 Header -->
    <div class="xh-header">
      <n-button
        v-if="['category', 'detail', 'user'].includes(xhView)"
        size="tiny"
        quaternary
        type="primary"
        @click="xhView === 'category' ? $emit('xh-cat-back') : (xhView === 'user' ? $emit('xh-user-back') : $emit('xh-detail-back'))"
      >← 返回</n-button>
      <span class="xh-header-title">{{ xhHeaderTitle }}</span>
      <div v-if="!['detail'].includes(xhView)" class="xh-header-search">
        <input
          v-model="xhSearchDraft"
          class="xh-search-input"
          type="search"
          placeholder="搜索视频 / 标签"
          @keyup.enter="submitXhSearch"
        />
        <n-button size="tiny" type="primary" :disabled="!xhSearchDraft.trim()" @click="submitXhSearch">搜索</n-button>
      </div>
      <template v-if="xhCanBatch && xhView !== 'detail'">
        <n-button
          class="batch-cta"
          size="small"
          :type="xhBatchMode ? 'warning' : 'primary'"
          :title="xhBatchMode ? '退出勾选模式' : '点击后当前列表进入勾选模式，勾选要下载的视频'"
          @click="toggleXhBatch"
        >{{ xhBatchMode ? '取消勾选' : '批量下载' }}</n-button>
        <n-button
          v-if="xhBatchMode"
          size="tiny"
          type="error"
          :disabled="!xhBatchChecked.size"
          :loading="xhBatchRunning"
          :title="`开始下载勾选的 ${xhBatchChecked.size} 个视频（后端逐个解析最高画质 mp4）`"
          @click="startXhBatch"
        >开始下载{{ xhBatchChecked.size ? `(${xhBatchChecked.size})` : '' }}</n-button>
        <template v-if="xhBatchMode">
          <n-button size="tiny" title="勾选当前列表全部可下载项" @click="selectXhBatch('all')">全选</n-button>
          <n-button size="tiny" title="勾选状态反转" @click="selectXhBatch('invert')">反选</n-button>
          <n-button size="tiny" title="清空全部勾选" @click="selectXhBatch('clear')">清空</n-button>
        </template>
      </template>
      <span v-if="xhBatchRunning" class="xh-header-hint">
        {{ xhBatchProgress.message || '准备中...' }}（{{ xhBatchProgress.done }}/{{ xhBatchProgress.total }}）
      </span>
      <n-button
        v-else-if="xhView === 'home'"
        size="tiny"
        quaternary
        :loading="xhHomeLoading"
        @click="$emit('xh-home', 1)"
      >刷新</n-button>
      <n-button
        v-else-if="xhView === 'categories'"
        size="tiny"
        quaternary
        :loading="xhCatsLoading"
        @click="$emit('xh-open-categories')"
      >刷新</n-button>
      <n-button
        v-else-if="xhView === 'shorts'"
        size="tiny"
        quaternary
        :loading="xhShortsLoading"
        @click="$emit('xh-shorts-reload')"
      >刷新</n-button>
      <n-button
        v-else-if="xhView === 'my'"
        size="tiny"
        quaternary
        :loading="xhMyLoading"
        @click="$emit('xh-my-tab', xhMyTab)"
      >刷新</n-button>
    </div>

    <!-- 内容区（n-scrollbar 滚动，底部留出 Tab 高度） -->
    <n-scrollbar class="xh-body">
      <!-- 首页：排序标签栏 + 视频网格 -->
      <template v-if="xhView === 'home'">
        <div class="xh-sort-bar">
          <button
            v-for="s in xhSortOptions"
            :key="s.key"
            class="xh-sort-chip"
            :class="{ on: xhHomeSort === s.key }"
            @click="$emit('xh-home-sort', s.key)"
          >{{ s.label }}</button>
        </div>
        <div class="tw-follow-count xh-list-count" v-if="xhHomeItems.length">
          {{ xhHomeItems.length }} 个视频<template v-if="xhHomeHasMore">（可继续加载）</template>
        </div>
      </template>

      <!-- 分类 Tab：热门分类网格 + 分组分类 -->
      <template v-else-if="xhView === 'categories'">
        <div v-if="xhCatsError" class="tw-follow-error">{{ xhCatsError }}</div>
        <div v-else-if="xhCatsLoading && !xhCatsTrending.length && !xhCatsGroups.length" class="tw-follow-empty">
          <n-spin size="medium" />
          <span>正在获取分类...</span>
        </div>
        <template v-else>
          <div v-if="xhCatsTrending.length" class="xh-cats-section">
            <div class="xh-cats-title">🔥 热门分类</div>
            <div class="xh-cats-grid">
              <div
                v-for="c in xhCatsTrending"
                :key="c.id || c.slug"
                class="xh-cat-card"
                :title="`查看「${c.name}」分类的视频`"
                @click="$emit('xh-open-category', c)"
              >
                <div class="xh-cat-thumb">
                  <img v-if="c.thumb" :src="c.thumb" loading="lazy" referrerpolicy="no-referrer" :alt="c.name" />
                  <span v-else class="xh-cat-thumb-empty">#</span>
                </div>
                <div class="xh-cat-name">{{ c.name }}</div>
              </div>
            </div>
          </div>
          <div v-for="g in xhCatsGroups" :key="g.id || g.name" class="xh-cats-section">
            <div class="xh-cats-title">{{ g.name }}</div>
            <div v-if="g.items && g.items.length" class="or-chip-list">
              <span
                v-for="c in g.items"
                :key="c.id || c.slug"
                class="or-tag-chip"
                :title="`查看「${c.name}」分类的视频`"
                @click="$emit('xh-open-category', c)"
              >{{ c.name }}</span>
            </div>
            <div v-else class="or-tags-empty">暂无分类</div>
          </div>
          <div v-if="!xhCatsTrending.length && !xhCatsGroups.length" class="tw-follow-empty">暂无分类数据</div>
        </template>
      </template>

      <!-- 分类列表：标题 + 网格（复用统一网格） -->
      <template v-else-if="xhView === 'category'">
        <div v-if="xhCatItems.length" class="tw-follow-count xh-list-count">
          {{ xhCatItems.length }} 个视频<template v-if="xhCatHasMore">（可继续加载）</template>
        </div>
      </template>

      <!-- 短视频：网格（时长短的视频卡片） -->
      <template v-else-if="xhView === 'shorts'">
        <div v-if="xhShortsItems.length" class="tw-follow-count xh-list-count">
          {{ xhShortsItems.length }} 个短视频<template v-if="xhShortsHasMore">（可继续加载）</template>
        </div>
      </template>

      <!-- 消息中心视图已随底栏消息 Tab 移除（2026-09-09） -->

      <!-- 我的关注：直接显示关注用户列表（我的视频子按钮已移除 2026-09-10，登录用户名右上角） -->
      <template v-else-if="xhView === 'my'">
        <div class="xh-sort-bar">
          <span class="xh-sort-chip on">我的关注</span>
          <span v-if="xhMyUsername" class="xh-my-user" title="登录用户">@{{ xhMyUsername }}</span>
        </div>
      </template>

      <!-- 视频详情：播放器 + 信息 + 标签 + 评论 -->
      <template v-else-if="xhView === 'detail'">
        <div v-if="xhDetailLoading && !xhDetail" class="tw-follow-empty">
          <n-spin size="medium" />
          <span>正在获取视频详情...</span>
        </div>
        <div v-else-if="xhDetailError" class="tw-follow-error">{{ xhDetailError }}</div>
        <template v-else-if="xhDetail">
          <div class="iw-video-area">
            <video
              v-if="xhDetail.video_url || xhDetail.hls_url"
              ref="xhVideoEl"
              controls
              preload="metadata"
              :poster="xhDetail.thumbnail"
              @error="onXhVideoError"
            />
            <img v-else :src="xhDetail.thumbnail" referrerpolicy="no-referrer" :alt="xhDetail.album_name" />
          </div>
          <div class="xh-detail-actions">
            <n-button size="small" tertiary type="primary" title="解析视频文件并加入下载列表" @click="$emit('open-album', xhDetail)">解析下载</n-button>
            <n-select
              v-if="xhDetail.mp4_list && xhDetail.mp4_list.length > 1"
              :value="xhDetail.mp4_list[0].quality"
              :options="xhQualityOptions"
              size="small"
              class="xh-quality-select"
              title="在线播放画质（下载始终取最高画质）"
              @update:value="q => switchXhQuality(q)"
            />
            <span v-if="xhDetail.hls_url" class="xh-header-hint">HLS 流可用（下载自动回退）</span>
          </div>
          <div class="iw-detail-stats">
            <span>👁 {{ formatCount(xhDetail.views) }}</span>
            <span>♥ {{ formatCount(xhDetail.likes) }}</span>
            <span v-if="xhDetail.rating">👍 {{ xhDetail.rating }}</span>
            <span v-if="xhDetail.created">{{ xhDetail.created }}</span>
            <n-tag v-if="xhDetail.is_hd" size="tiny" type="info" round>HD</n-tag>
            <span v-if="xhDetail.duration">⏱ {{ xhDetail.duration }}</span>
          </div>
          <div class="iw-author-row">
            <img
              v-if="xhDetail.author_avatar"
              class="iw-author-avatar"
              :src="xhDetail.author_avatar"
              referrerpolicy="no-referrer"
              title="查看作者主页"
              @click="$emit('xh-open-user', xhDetail.author_url || xhAuthorSlug)"
            />
            <span v-else class="iw-author-avatar iw-author-avatar-empty" title="查看作者主页" @click="$emit('xh-open-user', xhDetail.author_url || xhAuthorSlug)">@</span>
            <span class="iw-author-name" title="查看作者主页" @click="$emit('xh-open-user', xhDetail.author_url || xhAuthorSlug)">
              {{ xhDetail.author || '未知作者' }}
            </span>
            <span v-if="xhDetail.subscribers" class="xh-header-hint">{{ formatCount(xhDetail.subscribers) }} 订阅</span>
            <n-button
              size="tiny"
              :type="xhDetail.subscribed ? 'warning' : 'primary'"
              :loading="xhSubscribeLoading"
              @click="$emit('xh-subscribe', { user_id: xhDetail.author_id, username: xhAuthorSlug, subscribe: !xhDetail.subscribed })"
            >{{ xhDetail.subscribed ? '已关注' : '关注' }}</n-button>
          </div>
          <div v-if="xhDetail.categories && xhDetail.categories.length" class="iw-tags">
            <n-tag
              v-for="c in xhDetail.categories"
              :key="'c' + c"
              size="small"
              round
              type="warning"
              class="iw-tag"
              title="点击查看该分类"
              @click="$emit('xh-search-tag', c)"
            >{{ c }}</n-tag>
          </div>
          <div v-if="xhDetail.tags && xhDetail.tags.length" class="iw-tags">
            <n-tag
              v-for="t in xhDetail.tags"
              :key="'t' + t"
              size="small"
              round
              type="info"
              class="iw-tag"
              title="点击搜索该标签"
              @click="$emit('xh-search-tag', t)"
            >{{ t }}</n-tag>
          </div>
          <div v-if="xhRelated.length" class="xh-related">
            <div class="xh-cats-title">相关推荐</div>
            <div class="xh-related-row">
              <div
                v-for="item in xhRelated"
                :key="item.video_id || item.album_url"
                class="xh-related-card"
                :title="item.album_name"
                @click="$emit('xh-open-detail', item)"
              >
                <img v-if="item.thumbnail" :src="item.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name" />
                <div class="xh-related-name">{{ trTitle(item.album_name) }}</div>
              </div>
            </div>
          </div>
          <!-- 评论区 -->
          <div class="iw-comments-title">评论<template v-if="xhCommentCount">（{{ xhCommentCount }}）</template></div>
          <div v-if="xhDetail.comment_can_write !== false" class="xh-comment-form">
            <input
              v-model="xhCommentDraft"
              class="xh-search-input xh-comment-input"
              type="text"
              maxlength="500"
              placeholder="写下评论，回车发送"
              @keyup.enter="submitXhComment"
            />
            <n-button size="tiny" type="primary" :disabled="!xhCommentDraft.trim()" :loading="xhCommentSending" @click="submitXhComment">发送</n-button>
          </div>
          <div v-if="!xhComments.length" class="iw-comments-empty">暂无评论</div>
          <div v-for="c in xhComments" :key="c.id" class="iw-comment">
            <img
              v-if="c.avatar"
              class="iw-comment-avatar"
              :src="c.avatar"
              referrerpolicy="no-referrer"
              title="查看评论者主页"
              @click="$emit('xh-open-user', c.author)"
            />
            <span v-else class="iw-comment-avatar iw-comment-avatar-empty" title="查看评论者主页" @click="$emit('xh-open-user', c.author)">@</span>
            <div class="iw-comment-main">
              <div class="iw-comment-head">
                <span class="iw-comment-name" title="查看评论者主页" @click="$emit('xh-open-user', c.author)">
                  {{ c.author || '匿名' }}<template v-if="c.is_verified"> ✓</template><template v-if="c.vip"> 👑</template>
                </span>
                <span class="iw-comment-time">{{ c.created }}<template v-if="c.country"> · {{ c.country }}</template></span>
              </div>
              <div v-if="c.reply_to" class="xh-comment-reply">↩ 回复 {{ c.reply_to }}</div>
              <div class="iw-comment-body">{{ c.text }}</div>
              <div v-if="c.likes" class="xh-comment-likes">👍 {{ c.likes }}</div>
            </div>
          </div>
        </template>
      </template>

      <!-- 用户主页：资料 + 视频/短视频/画廊 Tab（复用统一网格） -->
      <template v-else-if="xhView === 'user'">
        <div v-if="xhUserProfile" class="xh-user-head">
          <img v-if="xhUserProfile.avatar" class="iw-author-avatar" :src="xhUserProfile.avatar" referrerpolicy="no-referrer" alt="" />
          <div class="xh-user-meta">
            <div class="iw-author-name">{{ xhUserProfile.name || xhUser }}</div>
            <div class="xh-header-hint">
              <template v-if="xhUserProfile.subscribers">{{ formatCount(xhUserProfile.subscribers) }} 订阅 · </template>
              <template v-if="xhUserProfile.is_friend">好友</template>
              <template v-else-if="xhUserProfile.relation && xhUserProfile.relation !== 'no-one'">{{ xhUserProfile.relation }}</template>
            </div>
            <div v-if="xhUserProfile.intro" class="xh-user-intro">{{ xhUserProfile.intro }}</div>
          </div>
          <n-button
            size="tiny"
            :type="xhUserProfile.subscribed ? 'warning' : 'primary'"
            :loading="xhSubscribeLoading"
            @click="$emit('xh-subscribe', { user_id: xhUserProfile.id, username: xhUser, subscribe: !xhUserProfile.subscribed })"
          >{{ xhUserProfile.subscribed ? '已关注' : '关注' }}</n-button>
        </div>
        <!-- 视频/短视频/画廊切换：吸顶（作者视频多时滚动中也能随时切 Tab，用户指定 2026-09-09） -->
        <div class="xh-sort-bar xh-user-tabs">
          <button class="xh-sort-chip" :class="{ on: xhUserTab === 'videos' }" @click="$emit('xh-user-tab', 'videos')">视频</button>
          <button class="xh-sort-chip" :class="{ on: xhUserTab === 'shorts' }" @click="$emit('xh-user-tab', 'shorts')">短视频</button>
          <button class="xh-sort-chip" :class="{ on: xhUserTab === 'galleries' }" @click="$emit('xh-user-tab', 'galleries')">画廊</button>
        </div>
        <div v-if="xhUserItems.length" class="tw-follow-count xh-list-count">
          @{{ xhUser }} · {{ xhUserItems.length }} 个<template v-if="xhUserHasMore">（可继续加载）</template>
        </div>
      </template>

      <!-- 统一视频网格（home/category/shorts/my/user 五个列表视图共用） -->
      <template v-if="xhListViews.includes(xhView)">
        <div v-if="xhCurrentError" class="tw-follow-error">{{ xhCurrentError }}</div>
        <div v-else-if="xhCurrentLoading && !xhCurrentItems.length" class="tw-follow-empty">
          <n-spin size="medium" />
          <span>正在获取内容...</span>
        </div>
        <div v-else-if="!xhCurrentItems.length" class="tw-follow-empty">{{ xhView === 'my' ? (xhCurrentError || '暂无内容（本账号没有可展示的视频/收藏）') : '暂无内容' }}</div>
        <div v-else class="search-grid">
            <div v-if="xhCurrentItems.length && xhCurrentHasMore" class="tw-browse-more" style="grid-column: 1 / -1; padding: 0 0 6px">
              <n-button size="tiny" quaternary block :loading="xhCurrentLoading" @click="emitXhMore"
              >加载更多</n-button>
            </div>
          <div
            v-for="item in xhCurrentItems"
            :key="item.video_id || item.album_url"
            class="search-card iw-card"
            :class="{ 'iw-batch-checked': xhBatchMode && xhBatchChecked.has(item.album_url) }"
            :title="`${item.album_name}\n作者: ${item.author || '未知'}\n${xhBatchMode ? '点击勾选/取消勾选' : '点击查看完整信息'}`"
            @click="xhBatchMode ? toggleXhBatchItem(item.album_url) : (item.kind === 'user' ? $emit('xh-open-user', item.author || item.album_name) : $emit('xh-open-detail', item))"
          >
            <div class="thumb-wrapper">
              <img :src="item.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name" />
              <span v-if="item.duration" class="iw-thumb-duration">{{ item.duration }}</span>
              <span v-if="item.access === 'friends'" class="iw-thumb-r18" title="仅好友可见">好友</span>
              <span v-else-if="item.access === 'private'" class="iw-thumb-r18" title="私密">私密</span>
              <span v-else-if="item.kind === 'short'" class="iw-thumb-r18">短</span>
              <span v-else-if="item.kind === 'gallery'" class="iw-thumb-r18">画廊</span>
              <span v-if="item.is_hd" class="iw-thumb-r18">HD</span>
              <div class="iw-thumb-stats">
                <span v-if="item.views">👁 {{ item.views }}</span>
                <span v-if="item.likes">♥ {{ item.likes }}</span>
              </div>
              <span v-if="xhBatchMode" class="iw-batch-check" :class="{ checked: xhBatchChecked.has(item.album_url) }">{{ xhBatchChecked.has(item.album_url) ? '✓' : '' }}</span>
              <button v-else-if="xhView !== 'user'" class="card-favorite-btn" title="快速收藏到本地" @click.stop="handleQuickFavorite(item)">♥</button>
            </div>
            <div class="card-name" :title="item.album_name">{{ trTitle(item.album_name) }}</div>
            <div class="iw-card-meta">
              <span class="iw-card-author" :title="item.author" @click.stop="$emit('xh-open-user', item.author_url || item.author)">{{ item.author || '未知作者' }}</span>
              <span v-if="item.created" class="iw-card-time">{{ item.created }}</span>
            </div>
          </div>
        </div>
        <div v-if="xhCurrentItems.length && xhCurrentHasMore" class="tw-browse-more">
          <n-button quaternary block :loading="xhCurrentLoading" @click="emitXhMore">加载更多</n-button>
        </div>
      </template>
    </n-scrollbar>

    <!-- 底部 Tab Bar（首页/分类/短视频/消息/我的；detail/user/category 二级视图时隐藏高亮） -->
    <div class="xh-tabbar">
      <button
        v-for="t in xhTabs"
        :key="t.key"
        class="xh-tab"
        :class="{ on: xhTab === t.key && !['detail', 'user', 'category'].includes(xhView) }"
        :title="t.title"
        @click="$emit('xh-tab', t.key)"
      >
        <span class="xh-tab-icon">{{ t.icon }}</span>
        <span class="xh-tab-label">{{ t.label }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
// xHamster 浏览视图组件（从 RightPanel.vue 拆出，f1）
// 模式沿用 PixivPanel：props 下行（App 状态经 RightPanel 透传）+ 事件上行（RightPanel 转发到 App）
// 共用基础设施（trTitle/proxied/formatCount/handleQuickFavorite）按 PixivPanel 先例本地内置
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import { NButton, NSelect, NSpin, NTag, NScrollbar } from 'naive-ui'
import Hls from 'hls.js'

const props = defineProps({
  site: { type: String, default: 'xhamster' },
  xhView: { type: String, default: '' },
  xhTab: { type: String, default: 'home' },          // 底部 Tab 当前高亮页
  xhHomeItems: { type: Array, default: () => [] },   // 首页视频卡片
  xhHomeLoading: { type: Boolean, default: false },
  xhHomeError: { type: String, default: '' },
  xhHomeSort: { type: String, default: 'newest' },   // 首页排序（newest/views/rating）
  xhHomeHasMore: { type: Boolean, default: false },
  xhCatsLoading: { type: Boolean, default: false },  // 分类目录加载中
  xhCatsTrending: { type: Array, default: () => [] },// 热门分类（带缩略图）
  xhCatsGroups: { type: Array, default: () => [] },  // 分组分类 [{id, name, items: [{id, slug, name}]}]
  xhCatsError: { type: String, default: '' },
  xhCatName: { type: String, default: '' },          // 当前分类列表名称
  xhCatItems: { type: Array, default: () => [] },    // 分类列表视频卡片
  xhCatLoading: { type: Boolean, default: false },
  xhCatError: { type: String, default: '' },
  xhCatHasMore: { type: Boolean, default: false },
  xhShortsItems: { type: Array, default: () => [] }, // 短视频卡片
  xhShortsLoading: { type: Boolean, default: false },
  xhShortsError: { type: String, default: '' },
  xhShortsHasMore: { type: Boolean, default: false },
  xhNotif: { type: Object, default: null },          // 消息中心（视图已下线，保留 prop 兼容透传）
  xhNotifLoading: { type: Boolean, default: false },
  xhMyTab: { type: String, default: 'videos' },      // 我的：videos=我的视频 | favorites=我的收藏
  xhMyItems: { type: Array, default: () => [] },
  xhMyLoading: { type: Boolean, default: false },
  xhMyError: { type: String, default: '' },
  xhMyHasMore: { type: Boolean, default: false },
  xhMyUsername: { type: String, default: '' },       // 登录用户名
  xhDetail: { type: Object, default: null },         // 视频详情（含播放直链/画质列表/评论）
  xhDetailLoading: { type: Boolean, default: false },
  xhDetailError: { type: String, default: '' },
  xhComments: { type: Array, default: () => [] },    // 详情页评论
  xhCommentCount: { type: Number, default: 0 },
  xhUser: { type: String, default: '' },             // 用户主页用户名
  xhUserItems: { type: Array, default: () => [] },
  xhUserLoading: { type: Boolean, default: false },
  xhUserError: { type: String, default: '' },
  xhUserHasMore: { type: Boolean, default: false },
  xhUserTab: { type: String, default: 'videos' },
  xhUserProfile: { type: Object, default: null },
  xhSubscribeLoading: { type: Boolean, default: false },
  xhCommentSending: { type: Boolean, default: false },
  xhBatchRunning: { type: Boolean, default: false }, // 批量解析下载进行中
  xhBatchProgress: { type: Object, default: () => ({ done: 0, total: 0, message: '' }) },
  translatedTitles: { type: Object, default: () => ({}) },  // {原标题: 译文}，trTitle 回填
  mediaProxyPort: { type: Number, default: 0 },             // 媒体代理端口（详情视频走本地代理）
})

const emit = defineEmits([
  'xh-tab',                 // 底部 Tab 切换（参数：home/categories/shorts/my）
  'xh-home',                // 首页刷新/排序后重载（参数：页码）
  'xh-home-more',           // 首页加载更多
  'xh-home-sort',           // 首页排序切换（参数：newest/views/rating）
  'xh-open-categories',     // 分类目录刷新
  'xh-open-category',       // 打开分类视频列表（参数：分类对象 {slug, name}）
  'xh-cat-back',            // 分类列表返回目录
  'xh-cat-more',            // 分类列表加载更多
  'xh-shorts-reload',       // 短视频刷新
  'xh-shorts-more',         // 短视频加载更多
  'xh-notifications',       // 消息中心刷新（视图已下线，保留事件声明兼容转发）
  'xh-my-tab',              // 我的：切换 我的视频/我的收藏（参数：videos/favorites）
  'xh-my-more',             // 我的加载更多
  'xh-open-detail',         // 打开视频详情（参数：视频条目）
  'xh-detail-back',         // 详情返回上一层
  'xh-open-user',           // 查看用户主页（参数：username）
  'xh-user-back',           // 用户主页返回
  'xh-user-more',           // 用户主页加载更多
  'xh-user-tab',            // 作者页 Tab：videos/shorts/galleries
  'xh-subscribe',           // 关注/取关 {user_id, username, subscribe}
  'xh-add-comment',         // 发表评论 {entity_type, entity_id, text, page_url}
  'xh-search-tag',          // 点击分类/标签搜索（参数：名称）
  'xh-search',              // Header 搜索框提交（参数：关键词）
  'xh-batch-download',      // 批量解析下载（参数：卡片数组）
  'open-album',             // 解析下载（详情页按钮，转发给 App openSearchResult）
  'add-favorite',           // 快速收藏到本地（参数：视频条目）
])

// ---------- 共用工具（PixivPanel 先例：本地内置，不依赖 RightPanel 作用域） ----------
// 远端直链 → 本地代理 URL（走 cookie/代理，国内可播）
function proxied(url) {
  if (!url) return ''
  if (!props.mediaProxyPort) return url
  if (url.startsWith('thumb://') || url.startsWith('http://127.0.0.1')) return url
  return `http://127.0.0.1:${props.mediaProxyPort}/media?url=${encodeURIComponent(url)}`
}

// ---------- 详情播放器（hls.js）：mp4 加密直链部分网络下 403（2026-09-09 实测），
// 失败自动回退 HLS（m3u8 经媒体代理实测可拉）；Safari 走原生 HLS ----------
const xhVideoEl = ref(null)
let xhHls = null

function detachXhHls() {
  if (xhHls) { xhHls.destroy(); xhHls = null }
}

function attachXhVideo() {
  const el = xhVideoEl.value
  const d = props.xhDetail
  detachXhHls()
  if (!el || !d) return
  const hlsUrl = d.hls_url ? proxied(d.hls_url) : ''
  const mp4 = (d.mp4_list && d.mp4_list.length) ? proxied(d.mp4_list[0].url) : ''
  // mp4 加密直链经代理实测 403（令牌绑定失效），有 HLS 一律优先 HLS（2026-09-09）
  if (hlsUrl && Hls.isSupported()) {
    xhHls = new Hls()
    console.log('[XH播放] attach HLS:', d.hls_url.slice(0, 80))
    xhHls.on(Hls.Events.ERROR, (_e, data) => {
      if (data.fatal) console.log('[XH播放] HLS致命错误:', data.type, data.details)
    })
    xhHls.loadSource(hlsUrl)
    xhHls.attachMedia(el)
    return
  }
  const src = hlsUrl || mp4   // Safari 原生 HLS 兜底
  if (src) {
    el.src = src
    el.load()
  }
}

function onXhVideoError() {
  // mp4-only 视频失败无 HLS 可退，保持原图占位（无额外动作）
}

watch(() => props.xhDetail, () => {
  nextTick(attachXhVideo)
})
onUnmounted(detachXhHls)

// 自动翻译：把原标题替换为译文（无译文回退原标题；空值返回 '未命名'）
function trTitle(name) {
  if (!name) return '未命名'
  return props.translatedTitles[name] || name
}

// 数字千分位
function formatCount(n) {
  if (!n || n <= 0) return '0'
  return Number(n).toLocaleString('zh-CN')
}

// 快速收藏到本地（搜索结果卡片爱心按钮）
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

// ============================
// xHamster 浏览视图逻辑（类 App 布局：底部 Tab + 统一视频网格 + 批量勾选）
// ============================
// 列表视图（统一网格 / 加载更多 / 批量勾选共用）
const xhListViews = ['home', 'category', 'shorts', 'my', 'user']

// 底部 Tab（首页/分类/短视频/我的；消息 Tab 已按需求移除 2026-09-09）
const xhTabs = [
  { key: 'home', label: '首页', icon: '🏠', title: '首页（最新 / 最多播放 / 最高评分）' },
  { key: 'categories', label: '分类', icon: '🗂️', title: '全站分类目录' },
  { key: 'shorts', label: '短视频', icon: '📱', title: '短视频' },
  { key: 'my', label: '我的关注', icon: '👤', title: '我的关注列表（需登录）' },
]

// 首页排序
const xhSortOptions = [
  { key: 'newest', label: '最新' },
  { key: 'views', label: '最多播放' },
  { key: 'rating', label: '最高评分' },
  { key: 'hd', label: 'HD' },
  { key: '4k', label: '4K' },
  { key: 'vr', label: 'VR' },
]
const xhSearchDraft = ref('')
function submitXhSearch() {
  const q = (xhSearchDraft.value || '').trim()
  if (!q) return
  emit('xh-search', q)
}

// 消息中心：通知分类计数按键已按需求移除（2026-09-09），仅保留登录态与空态提示

// 当前列表视图 → 数据源映射
const xhCurrentItems = computed(() => ({
  home: props.xhHomeItems,
  category: props.xhCatItems,
  shorts: props.xhShortsItems,
  my: props.xhMyItems,
  user: props.xhUserItems,
}[props.xhView] || []))
const xhCurrentLoading = computed(() => ({
  home: props.xhHomeLoading,
  category: props.xhCatLoading,
  shorts: props.xhShortsLoading,
  my: props.xhMyLoading,
  user: props.xhUserLoading,
}[props.xhView] || false))
const xhCurrentError = computed(() => ({
  home: props.xhHomeError,
  category: props.xhCatError,
  shorts: props.xhShortsError,
  my: props.xhMyError,
  user: props.xhUserError,
}[props.xhView] || ''))
const xhCurrentHasMore = computed(() => ({
  home: props.xhHomeHasMore,
  category: props.xhCatHasMore,
  shorts: props.xhShortsHasMore,
  my: props.xhMyHasMore,
  user: props.xhUserHasMore,
}[props.xhView] || false))

// Header 标题（二级视图显示具体名称）
const xhHeaderTitle = computed(() => {
  if (props.xhView === 'home') return 'xHamster'
  if (props.xhView === 'categories') return '分类'
  if (props.xhView === 'category') return props.xhCatName || '分类'
  if (props.xhView === 'shorts') return '短视频'
  if (props.xhView === 'my') return '我的关注'
  if (props.xhView === 'detail') return (props.xhDetail && props.xhDetail.album_name) || '视频详情'
  if (props.xhView === 'user') return `@${props.xhUser || ''}`
  return 'xHamster'
})

// 详情作者名（点击进用户主页）
const xhAuthorName = computed(() => (props.xhDetail && props.xhDetail.author) || '')
const xhAuthorSlug = computed(() => (props.xhDetail && (props.xhDetail.author_slug || props.xhDetail.author)) || '')
const xhCommentDraft = ref('')
function submitXhComment() {
  const text = (xhCommentDraft.value || '').trim()
  const d = props.xhDetail
  if (!text || !d) return
  emit('xh-add-comment', {
    entity_type: d.comment_entity_type || 'video',
    entity_id: d.comment_entity_id || d.numeric_id || '',
    text,
    page_url: d.album_url,
  })
  xhCommentDraft.value = ''
}
const xhRelated = computed(() => {
  const d = props.xhDetail
  const arr = (d && (d.related || d.related_items)) || []
  return Array.isArray(arr) ? arr.filter(x => x && x.album_url) : []
})

// 在线播放画质选项（mp4_list → n-select options）
const xhQualityOptions = computed(() =>
  ((props.xhDetail && props.xhDetail.mp4_list) || []).map(m => ({ label: m.quality, value: m.quality }))
)

// 切换在线播放画质（直接换 <video> src；下载始终取最高画质，不受此影响）
function switchXhQuality(q) {
  const d = props.xhDetail
  if (!d || !Array.isArray(d.mp4_list)) return
  const hit = d.mp4_list.find(m => m && m.quality === q && m.url)
  if (hit) d.video_url = hit.url
}

// 可批量勾选的视图（五个列表视图）
const xhCanBatch = computed(() => xhListViews.includes(props.xhView))

// 批量勾选状态（视图切换时自动退出并清空）
const xhBatchMode = ref(false)
const xhBatchChecked = ref(new Set())
watch(() => props.xhView, () => {
  xhBatchMode.value = false
  xhBatchChecked.value = new Set()
})

function toggleXhBatch() {
  xhBatchMode.value = !xhBatchMode.value
  if (!xhBatchMode.value) xhBatchChecked.value = new Set()
}

// 勾选/取消勾选（Set 重新赋值触发响应式更新）
function toggleXhBatchItem(url) {
  if (!url) return
  const s = new Set(xhBatchChecked.value)
  if (s.has(url)) s.delete(url)
  else s.add(url)
  xhBatchChecked.value = s
}

// 全选/反选/清空（作用于当前视图列表的可下载项；与开始下载一致排除用户卡）
function selectXhBatch(mode) {
  if (mode === 'clear') { xhBatchChecked.value = new Set(); return }
  const ids = xhCurrentItems.value.filter(it => it && it.album_url && it.kind !== 'user').map(it => it.album_url)
  if (mode === 'all') xhBatchChecked.value = new Set(ids)
  else xhBatchChecked.value = new Set(ids.filter(u => !xhBatchChecked.value.has(u)))
}

// 开始批量下载勾选的视频（后端逐个解析最高画质 mp4 并提交下载）
function startXhBatch() {
  const urls = [...xhBatchChecked.value]
  if (!urls.length) return
  const picked = xhCurrentItems.value.filter(it => it && urls.includes(it.album_url) && it.kind !== 'user')
  emit('xh-batch-download', picked.length ? picked : urls.map(u => ({ album_url: u, kind: 'video' })))
  xhBatchMode.value = false
  xhBatchChecked.value = new Set()
}

// 统一"加载更多"：按当前视图 emit 对应事件
function emitXhMore() {
  if (props.xhView === 'home') emit('xh-home-more')
  else if (props.xhView === 'category') emit('xh-cat-more')
  else if (props.xhView === 'shorts') emit('xh-shorts-more')
  else if (props.xhView === 'my') emit('xh-my-more')
  else if (props.xhView === 'user') emit('xh-user-more')
}
</script>

<style scoped>
/* ============================ */
/* xHamster 类 App 布局（Header + 内容区 + 底部 Tab）——自 RightPanel.vue 迁出 */
/* ============================ */
.xh-app {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

/* 顶部 Header：返回/标题/批量按钮/刷新 */
.xh-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.02);
  flex-shrink: 0;
  min-width: 0;
}

.xh-header-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 700;
  color: #e8e8ea;
}

.xh-header-search {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.xh-search-input {
  width: 160px;
  max-width: 28vw;
  height: 24px;
  padding: 0 8px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.16);
  background: rgba(255, 255, 255, 0.06);
  color: #e8e8ea;
  font-size: 12px;
  outline: none;
}

.xh-search-input:focus {
  border-color: rgba(64, 152, 215, 0.7);
}

.xh-related {
  margin: 12px;
}

.xh-related-row {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 6px;
}

.xh-related-card {
  width: 140px;
  flex-shrink: 0;
  cursor: pointer;
}

.xh-related-card img {
  width: 140px;
  height: 80px;
  object-fit: cover;
  border-radius: 6px;
  display: block;
  background: #1d1d22;
}

.xh-related-name {
  margin-top: 4px;
  font-size: 12px;
  color: #ccc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.xh-header-hint {
  font-size: 12px;
  color: #999;
  white-space: nowrap;
}

/* 内容区（弹性填充，底部 Tab 由 flex 兄弟节点占位） */
.xh-body {
  flex: 1;
  min-height: 0;
}

/* 排序/切换标签条（首页排序、我的视频/收藏） */

/* 用户页 Tab 条：吸顶 + 毛玻璃底（滚动翻视频时也能随时切换） */
.xh-user-tabs {
  position: sticky;
  top: 0;
  z-index: 5;
  padding: 8px 12px;
  background: rgba(18, 18, 23, 0.92);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

html.light-mode .xh-user-tabs {
  background: rgba(250, 250, 252, 0.92);
}

.xh-sort-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 8px 12px 4px;
}

.xh-sort-chip {
  padding: 3px 12px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(255, 255, 255, 0.04);
  color: #bbb;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.xh-sort-chip:hover {
  color: #fff;
  border-color: rgba(255, 255, 255, 0.35);
}

.xh-sort-chip.on {
  color: #fff;
  background: rgba(64, 152, 215, 0.25);
  border-color: rgba(64, 152, 215, 0.7);
}

/* 列表计数行 */
.xh-list-count {
  margin: 4px 12px;
}

/* 我的：登录用户名（靠右） */
.xh-my-user {
  margin-left: auto;
  font-size: 12px;
  color: #4098d7;
  white-space: nowrap;
}

/* 分类目录：分区 + 热门分类网格 */
.xh-cats-section {
  margin: 10px 12px 4px;
}

.xh-cats-title {
  font-size: 13px;
  font-weight: 700;
  color: #ddd;
  margin-bottom: 8px;
}

.xh-cats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: 10px;
}

.xh-cat-card {
  cursor: pointer;
  text-align: center;
}

.xh-cat-thumb {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  border-radius: 8px;
  overflow: hidden;
  background: #1d1d22;
  border: 1px solid rgba(255, 255, 255, 0.06);
  transition: border-color 0.15s;
}

.xh-cat-card:hover .xh-cat-thumb {
  border-color: rgba(64, 152, 215, 0.6);
}

.xh-cat-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.xh-cat-thumb-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
  color: #555;
  font-weight: 700;
}

.xh-cat-name {
  margin-top: 5px;
  font-size: 12px;
  color: #ccc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 详情：操作行（解析下载/画质选择） */
.xh-detail-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 8px 12px 0;
}

.xh-quality-select {
  width: 110px;
}

/* 详情：评论回复/点赞 */
.xh-comment-reply {
  font-size: 12px;
  color: #4098d7;
  margin-bottom: 2px;
}

.xh-comment-likes {
  margin-top: 3px;
  font-size: 12px;
  color: #999;
}

/* 底部 Tab Bar */
.xh-tabbar {
  display: flex;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.02);
  flex-shrink: 0;
}

.xh-tab {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  padding: 6px 0 7px;
  background: none;
  border: none;
  color: #888;
  cursor: pointer;
  transition: color 0.15s;
}

.xh-tab:hover {
  color: #ccc;
}

.xh-tab.on {
  color: #4098d7;
}

.xh-tab-icon {
  font-size: 17px;
  line-height: 1.2;
}

.xh-tab-label {
  font-size: 11px;
}

/* xHamster 布局日间模式 */
html.light-mode .xh-header {
  border-bottom-color: rgba(0, 0, 0, 0.08);
  background: rgba(0, 0, 0, 0.02);
}

html.light-mode .xh-header-title {
  color: #222;
}

html.light-mode .xh-search-input {
  border-color: rgba(0, 0, 0, 0.16);
  background: #fff;
  color: #222;
}

html.light-mode .xh-related-name {
  color: #444;
}

.xh-user-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px 4px;
}

.xh-user-meta {
  flex: 1;
  min-width: 0;
}

.xh-user-intro {
  margin-top: 4px;
  font-size: 12px;
  color: #aaa;
  max-height: 4.5em;
  overflow: hidden;
}

.xh-comment-form {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 6px 12px 8px;
}

.xh-comment-input {
  flex: 1;
  width: auto;
  max-width: none;
  height: 28px;
}

html.light-mode .xh-user-intro {
  color: #666;
}

html.light-mode .xh-sort-chip {
  border-color: rgba(0, 0, 0, 0.12);
  background: rgba(0, 0, 0, 0.02);
  color: #666;
}

html.light-mode .xh-sort-chip:hover {
  color: #222;
  border-color: rgba(0, 0, 0, 0.3);
}

html.light-mode .xh-sort-chip.on {
  color: #1c6ea4;
  background: rgba(64, 152, 215, 0.12);
  border-color: rgba(64, 152, 215, 0.55);
}

html.light-mode .xh-cats-title {
  color: #333;
}

html.light-mode .xh-cat-thumb {
  background: #eee;
  border-color: rgba(0, 0, 0, 0.08);
}

html.light-mode .xh-cat-thumb-empty {
  color: #aaa;
}

html.light-mode .xh-cat-name {
  color: #444;
}

html.light-mode .xh-my-user,
html.light-mode .xh-comment-reply {
  color: #1c6ea4;
}

html.light-mode .xh-tabbar {
  border-top-color: rgba(0, 0, 0, 0.08);
  background: rgba(0, 0, 0, 0.02);
}

html.light-mode .xh-tab {
  color: #999;
}

html.light-mode .xh-tab.on {
  color: #1c6ea4;
}

/* ============================ */
/* 共用样式副本（RightPanel 为 scoped 样式，本组件内部元素拿不到；
   按 PixivPanel 先例从 RightPanel 原样复制，保持两处同步） */
/* ============================ */
.search-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 12px;
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

.search-card:active {
  transform: scale(0.985);
  transition: transform 0.08s ease;
  filter: brightness(1.15);
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

.iw-thumb-r18 {
  position: absolute;
  left: 6px;
  top: 6px;
  background: rgba(208, 48, 48, 0.85);
  color: #ffffff;
  font-size: 11px;
  font-weight: 600;
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

.iw-author-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  object-fit: cover;
  cursor: pointer;
  flex-shrink: 0;
}

.iw-author-avatar-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  background: #2d2d33;
  color: #63e2b7;
  font-size: 16px;
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

.iw-comment-avatar-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  background: #2d2d33;
  color: #63e2b7;
  font-size: 14px;
  cursor: pointer;
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

.or-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 2px 0 10px;
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

html.light-mode .or-tag-chip {
  background: rgba(0, 128, 90, 0.06);
  border-color: rgba(0, 128, 90, 0.35);
  color: #0a7a52;
}

html.light-mode .or-tags-empty {
  color: #888;
}

.tw-follow-count {
  font-size: 12px;
  color: #7a7a85;
}

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
</style>
