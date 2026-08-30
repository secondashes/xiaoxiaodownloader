<template>
  <!-- Pixiv 全功能面板：功能栏（常用标签/关注粉丝/首页插画漫画小说/关注更新/收藏书签/推荐/排行/消息提醒/发布作品）+ 三模式搜索 + 三种卡片 + 用户页 + 详情页 -->
  <div class="px-panel">
    <!-- ================= 功能栏（置顶常显） ================= -->
    <div class="px-toolbar">
      <!-- 行1：搜索模式切换 + 排行榜 -->
      <div class="px-toolbar-row">
        <n-button-group size="small">
          <n-button size="small" :type="pixivSearchType === 'illust' ? 'primary' : 'default'" title="搜索插画/漫画作品（默认）" @click="emitCmd({ cmd: 'pixiv_set_search_type', type: 'illust' })">插画/漫画</n-button>
          <n-button size="small" :type="pixivSearchType === 'novel' ? 'primary' : 'default'" title="搜索小说" @click="emitCmd({ cmd: 'pixiv_set_search_type', type: 'novel' })">小说</n-button>
          <n-button size="small" :type="pixivSearchType === 'user' ? 'primary' : 'default'" title="搜索用户" @click="emitCmd({ cmd: 'pixiv_set_search_type', type: 'user' })">用户</n-button>
        </n-button-group>
        <n-dropdown size="small" trigger="click" :options="rankOptions" @select="k => emitCmd({ cmd: 'pixiv_feed', kind: k, page: 1 })">
          <n-button size="small" title="排行榜：日榜 / 周榜 / 月榜">🏆 排行榜</n-button>
        </n-dropdown>
        <n-button size="small" :type="state.view === '' && activeFeed === 'home' ? 'primary' : 'default'" title="个性化推荐（含榜单作品）" @click="emitCmd({ cmd: 'pixiv_feed', kind: 'home', page: 1 })">🏠 首页</n-button>
        <n-button size="small" :type="state.view === '' && activeFeed === 'illust' ? 'primary' : 'default'" @click="emitCmd({ cmd: 'pixiv_feed', kind: 'illust', page: 1 })">插画</n-button>
        <n-button size="small" :type="state.view === '' && activeFeed === 'manga' ? 'primary' : 'default'" @click="emitCmd({ cmd: 'pixiv_feed', kind: 'manga', page: 1 })">漫画</n-button>
        <n-button size="small" :type="state.view === '' && activeFeed === 'novel' ? 'primary' : 'default'" @click="emitCmd({ cmd: 'pixiv_feed', kind: 'novel', page: 1 })">小说</n-button>
        <!-- 关注的人更新：漫画/小说切换 -->
        <n-button-group size="small">
          <n-button size="small" :type="state.view === '' && activeFeed === 'follow_illust' ? 'primary' : 'default'" title="已关注作者的最新插画/漫画（断点更新+历史缓存）" @click="emitCmd({ cmd: 'pixiv_follow_feed', content: 'illust' })">关注更新</n-button>
          <n-button size="small" :type="state.view === '' && activeFeed === 'follow_novel' ? 'primary' : 'default'" title="已关注作者的最新小说（断点更新+历史缓存）" @click="emitCmd({ cmd: 'pixiv_follow_feed', content: 'novel' })">小说</n-button>
        </n-button-group>
      </div>

      <!-- 行2（1号区）：常用标签 + 关注列表 + 粉丝列表 -->
      <div class="px-toolbar-row px-tags-row">
        <span class="px-tags-label">常用标签：</span>
        <div class="px-tags-list" :class="{ expanded: tagsExpanded }">
          <n-tag
            v-for="t in displayTags"
            :key="t.name"
            size="small"
            round
            checkable
            class="px-tag"
            :title="t.count ? `点击搜索「${t.name}」（用过 ${t.count} 次）` : `点击搜索「${t.name}」`"
            @click="emitCmd({ cmd: 'pixiv_tag_search', tag: t.name })"
          >{{ t.name }}</n-tag>
          <span v-if="!displayTags.length" class="px-tags-empty">暂无常用标签（搜索/点击标签后会记录在这里）</span>
        </div>
        <n-button v-if="allTags.length > tagPreviewCount" size="tiny" quaternary type="primary" @click="tagsExpanded = !tagsExpanded">
          {{ tagsExpanded ? '收起' : `展开(${allTags.length})` }}
        </n-button>
        <n-button size="small" :type="state.view === '' && activeFeed === 'userlist_following' ? 'primary' : 'default'" title="我的关注列表（可查看 TA 人的关注）" @click="emitCmd({ cmd: 'pixiv_user_list', mode: 'following', page: 1 })">关注列表</n-button>
        <n-button size="small" :type="state.view === '' && activeFeed === 'userlist_followers' ? 'primary' : 'default'" title="我的粉丝列表" @click="emitCmd({ cmd: 'pixiv_user_list', mode: 'followers', page: 1 })">粉丝列表</n-button>
      </div>

      <!-- 行3（2号区）：收藏 / 书签 / 推荐作品 / 推荐用户 / 消息 / 提醒 / 发布作品 -->
      <div class="px-toolbar-row">
        <n-popover trigger="click" placement="bottom-start">
          <template #trigger>
            <n-button size="small" :type="state.view === '' && activeFeed === 'bookmark' ? 'primary' : 'default'" title="我的收藏：插画/漫画/小说 × 公开/私密 × 年龄限制">⭐ 收藏</n-button>
          </template>
          <div class="px-pop">
            <div class="px-pop-title">收藏内容</div>
            <n-button-group size="small">
              <n-button size="small" :type="bookmarkContent === 'illust' ? 'primary' : 'default'" @click="bookmarkContent = 'illust'">插画</n-button>
              <n-button size="small" :type="bookmarkContent === 'manga' ? 'primary' : 'default'" @click="bookmarkContent = 'manga'">漫画</n-button>
              <n-button size="small" :type="bookmarkContent === 'novel' ? 'primary' : 'default'" @click="bookmarkContent = 'novel'">小说</n-button>
            </n-button-group>
            <div class="px-pop-title" style="margin-top: 8px">公开 / 私密</div>
            <n-button-group size="small">
              <n-button size="small" :type="bookmarkRestrict === 'public' ? 'primary' : 'default'" @click="bookmarkRestrict = 'public'">仅公开收藏</n-button>
              <n-button size="small" :type="bookmarkRestrict === 'private' ? 'primary' : 'default'" @click="bookmarkRestrict = 'private'">私密收藏</n-button>
            </n-button-group>
            <div class="px-pop-row" style="margin-top: 8px">
              <n-checkbox size="small" :checked="bookmarkAllowR18" @update:checked="v => bookmarkAllowR18 = v">显示年龄限制(R-18)内容</n-checkbox>
            </div>
            <div class="px-pop-row" style="margin-top: 8px">
              <n-checkbox v-if="bookmarkContent === 'novel'" size="small" :checked="novelNewestFirst" @update:checked="v => novelNewestFirst = v">按最新收藏排序</n-checkbox>
            </div>
            <n-button size="small" type="primary" block style="margin-top: 10px" @click="loadBookmarks">查看收藏</n-button>
          </div>
        </n-popover>
        <n-button size="small" :type="state.view === '' && activeFeed === 'bookmark' ? 'primary' : 'default'" title="书签：收藏标签列表，点标签查看该标签的收藏" @click="emitCmd({ cmd: 'pixiv_bookmark_tags', content: bookmarkContent === 'novel' ? 'novel' : 'illust' })">🔖 书签</n-button>
        <n-button size="small" :type="state.view === '' && activeFeed === 'illust' ? 'primary' : 'default'" title="为你推荐的作品" @click="emitCmd({ cmd: 'pixiv_feed', kind: 'illust', page: 1 })">推荐作品</n-button>
        <n-button size="small" :type="state.view === '' && activeFeed === 'recommended_user' ? 'primary' : 'default'" title="为你推荐的用户" @click="emitCmd({ cmd: 'pixiv_feed', kind: 'recommended_user', page: 1 })">推荐用户</n-button>
        <n-button size="small" title="消息通知中心" @click="emitCmd({ cmd: 'pixiv_notification' })">💬 消息</n-button>
        <n-button size="small" title="提醒（点赞/收藏/关注/回复动态）" @click="emitCmd({ cmd: 'pixiv_notification' })">
          🔔 提醒
          <span v-if="state.notifications && state.notifications.unread" class="px-unread-badge">{{ state.notifications.unread > 99 ? '99+' : state.notifications.unread }}</span>
        </n-button>
        <n-button size="small" type="warning" title="上传作品发布到 Pixiv（标题/说明/标签）" @click="uploadVisible = true">✏️ 发布作品</n-button>
      </div>
      <!-- 批量下载（多批次）进度条 -->
      <div v-if="batchRunning" class="px-batch-progress">
        <n-progress
          type="line"
          :percentage="batchProgress.total ? Math.round(batchProgress.done / batchProgress.total * 100) : 0"
          :height="8"
          :show-indicator="false"
          processing
        />
        <span class="px-batch-text">{{ batchProgress.message || '准备中...' }}（{{ batchProgress.done }}/{{ batchProgress.total }}）</span>
      </div>
    </div>

    <!-- ================= 列表视图（搜索结果 / feed / 列表） ================= -->
    <n-scrollbar v-if="state.view === ''" class="px-list-scroll" trigger="none">
      <div class="pa-toolbar">
        <span class="pa-result-count">
          {{ searchQuery ? `「${searchQuery}」` : 'Pixiv' }} · 第 {{ searchPage }} 页
          <template v-if="searchTotalResults > 0">（共 {{ formatCount(searchTotalResults) }} 个）</template>
        </span>
        <!-- 用户列表批量下载（多批次：每个用户一个下载任务） -->
        <span v-if="userCards.length" class="pa-batch-bar">
          <span class="pa-batch-label">批量下载本页 {{ userCards.length }} 个用户：</span>
          <n-button size="tiny" type="warning" @click="batchDownloadPageUsers('illust')">⬇ 插画/漫画</n-button>
          <n-button size="tiny" type="warning" @click="batchDownloadPageUsers('novel')">⬇ 小说</n-button>
        </span>
      </div>
      <PaginationBar
        :page="searchPage"
        :total-pages="searchTotalPages"
        :has-more="searchHasMore"
        :searching="searching"
        @go-page="p => $emit('go-page', p)"
      />
      <div class="search-grid">
        <!-- 插画/漫画卡片：图片 → 标题 → 作者头像+名字（多图显示张数；图片可点击收藏；点图片/标题进详情；点作者进用户页） -->
        <div
          v-for="item in searchResults"
          :key="item.illust_id || item.novel_id || item.user_id || item.album_url"
          class="search-card px-card"
        >
          <div class="thumb-wrapper" @click="openDetail(item)">
            <img :src="proxied(item.thumbnail)" loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name" />
            <div class="thumb-files" v-if="item.files != null && item.files > 1">{{ item.files }}P</div>
            <div class="thumb-files" v-else-if="item.words">≈{{ formatCount(item.words) }}字</div>
            <span v-if="item.r18" class="px-badge" style="background: #d03050">R-18</span>
            <span v-if="item.ugoira" class="px-badge" style="background: #722ed1">动图</span>
            <span v-if="item.manga_type" class="px-badge" style="background: #2a7de1">漫画</span>
            <!-- 图片右上角快捷按钮：下载 / 收藏 -->
            <div class="px-card-actions">
              <button class="px-mini-btn" title="解析并下载全部图片" @click.stop="$emit('open-album', item)">⬇</button>
              <button v-if="item.kind !== 'user'" class="px-mini-btn" :class="{ active: item.is_bookmarked }" :title="item.is_bookmarked ? '已收藏（点击取消）' : '快速收藏'" @click.stop="toggleBookmark(item)">♥</button>
            </div>
          </div>
          <div class="card-name px-clickable" :title="item.album_name" @click="openDetail(item)">{{ item.album_name }}</div>
          <!-- 用户卡片：头像 + 简介 + 关注按钮 -->
          <div v-if="item.kind === 'user'" class="px-user-meta">
            <div class="px-user-line">
              <img v-if="item.thumbnail" class="px-avatar-sm" :src="proxied(item.thumbnail)" referrerpolicy="no-referrer" @click="openUser(item)" />
              <div class="px-user-sub">
                <span class="px-user-account">@{{ item.account || item.user_id }}</span>
                <n-button size="tiny" :type="item.is_followed ? 'error' : 'primary'" secondary @click="toggleFollow(item)">
                  {{ item.is_followed ? '已关注' : '+ 关注' }}
                </n-button>
              </div>
            </div>
            <div v-if="item.comment" class="px-user-comment" :title="item.comment">{{ item.comment }}</div>
            <div v-if="item.recent_thumbs && item.recent_thumbs.length" class="px-user-thumbs">
              <img v-for="(t, i) in item.recent_thumbs" :key="i" :src="proxied(t)" loading="lazy" referrerpolicy="no-referrer" />
            </div>
            <!-- 单个用户批量下载（直接后台任务，不经预览） -->
            <div class="px-user-dl">
              <n-button size="tiny" type="warning" secondary title="后台解析并下载 TA 的全部插画/漫画" @click.stop="batchDownloadUser(item, 'illust')">⬇ 插画/漫画</n-button>
              <n-button size="tiny" type="warning" secondary title="后台解析并下载 TA 的全部小说（txt+封面）" @click.stop="batchDownloadUser(item, 'novel')">⬇ 小说</n-button>
            </div>
          </div>
          <!-- 插画/小说卡片：作者头像+名字 -->
          <div v-else class="iw-card-meta">
            <span class="px-author" :title="`查看 ${item.author} 的主页`" @click.stop="openUser(item)">
              <img v-if="item.avatar" class="px-avatar-xs" :src="proxied(item.avatar)" referrerpolicy="no-referrer" />
              <span class="iw-card-author">{{ item.author || '未知' }}</span>
            </span>
            <span class="px-stats-mini" v-if="item.bookmarks">♥{{ formatCount(item.bookmarks) }}</span>
            <span v-if="item.posted" class="iw-card-time">{{ item.posted }}</span>
          </div>
        </div>
      </div>
      <PaginationBar
        :page="searchPage"
        :total-pages="searchTotalPages"
        :has-more="searchHasMore"
        :searching="searching"
        @go-page="p => $emit('go-page', p)"
      />
    </n-scrollbar>

    <!-- ================= 用户主页视图 ================= -->
    <div v-else-if="state.view === 'user'" class="px-view">
      <div class="tw-follow-toolbar">
        <n-button size="small" quaternary type="primary" @click="emitCmd({ cmd: 'pixiv_back' })">← 返回</n-button>
        <span class="tw-follow-title">用户主页</span>
        <n-spin v-if="state.userLoading" :size="14" />
      </div>
      <n-scrollbar class="px-view-scroll">
        <div v-if="state.userPage" class="px-profile">
          <div class="px-profile-head">
            <img v-if="state.userPage.user.avatar" class="px-avatar-lg" :src="proxied(state.userPage.user.avatar)" referrerpolicy="no-referrer" />
            <div class="px-profile-info">
              <div class="px-profile-name">
                <span class="px-name">{{ state.userPage.user.name }}</span>
                <span class="px-account">@{{ state.userPage.user.account }}</span>
                <n-tag v-if="state.userPage.user.is_followed" size="tiny" type="success" round>已关注</n-tag>
              </div>
              <div v-if="state.userPage.user.comment" class="px-profile-desc">{{ state.userPage.user.comment }}</div>
              <div class="px-profile-stats">
                <span>关注 {{ formatCount(state.userPage.profile.total_following) }}</span>
                <span>粉丝 {{ formatCount(state.userPage.profile.total_follower) }}</span>
                <span>插画 {{ formatCount(state.userPage.profile.total_illusts) }}</span>
                <span>漫画 {{ formatCount(state.userPage.profile.total_manga) }}</span>
                <span>小说 {{ formatCount(state.userPage.profile.total_novels) }}</span>
                <span>收藏 {{ formatCount(state.userPage.profile.total_illust_bookmarks + state.userPage.profile.total_novel_bookmarks) }}</span>
              </div>
            </div>
          </div>
          <div class="px-profile-actions">
            <n-button
              size="small"
              :type="state.userPage.user.is_followed ? 'error' : 'primary'"
              @click="emitCmd({ cmd: 'pixiv_action', action: state.userPage.user.is_followed ? 'unfollow' : 'follow', kind: 'user', item_id: state.userPage.user.user_id })"
            >{{ state.userPage.user.is_followed ? '取消关注' : '关注' }}</n-button>
            <n-button size="small" @click="emitCmd({ cmd: 'pixiv_user_list', mode: 'following', user_id: state.userPage.user.user_id, page: 1 })">TA 的关注</n-button>
            <n-button size="small" @click="emitCmd({ cmd: 'pixiv_user_list', mode: 'followers', user_id: state.userPage.user.user_id, page: 1 })">TA 的粉丝</n-button>
            <n-button size="small" @click="emitCmd({ cmd: 'pixiv_bookmarks', content: 'illust', user_id: state.userPage.user.user_id, page: 1 })">TA 的插画收藏</n-button>
            <n-button size="small" @click="emitCmd({ cmd: 'pixiv_bookmarks', content: 'novel', user_id: state.userPage.user.user_id, page: 1 })">TA 的小说收藏</n-button>
            <n-button size="small" type="warning" title="解析 TA 的全部插画/漫画原图（后台任务）" @click="downloadUserAll('illust')">⬇ 下载全部插画/漫画</n-button>
            <n-button size="small" type="warning" title="解析 TA 的全部小说（txt+封面）" @click="downloadUserAll('novel')">⬇ 下载全部小说</n-button>
          </div>
          <!-- 作品三区块 -->
          <div v-for="sec in userSections" :key="sec.key" class="px-user-section">
            <div class="px-section-head">
              <span class="px-section-title">{{ sec.label }}（{{ sec.items.length }}）</span>
              <n-button v-if="sec.items.length" size="tiny" quaternary type="primary" @click="downloadSection(sec)">⬇ 下载本区</n-button>
            </div>
            <div v-if="sec.items.length" class="search-grid">
              <div v-for="item in sec.items" :key="item.illust_id || item.novel_id" class="search-card px-card" @click="openDetail(item)">
                <div class="thumb-wrapper">
                  <img :src="proxied(item.thumbnail)" loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name" />
                  <div class="thumb-files" v-if="item.files > 1">{{ item.files }}P</div>
                  <span v-if="item.r18" class="px-badge" style="background: #d03050">R-18</span>
                </div>
                <div class="card-name">{{ item.album_name }}</div>
                <div class="iw-card-meta">
                  <span class="iw-card-author">{{ item.author }}</span>
                  <span class="px-stats-mini" v-if="item.bookmarks">♥{{ formatCount(item.bookmarks) }}</span>
                </div>
              </div>
            </div>
            <div v-else class="px-section-empty">暂无{{ sec.label }}</div>
          </div>
        </div>
      </n-scrollbar>
    </div>

    <!-- ================= 作品详情视图 ================= -->
    <div v-else-if="state.view === 'detail' && state.detail" class="px-view">
      <div class="tw-follow-toolbar">
        <n-button size="small" quaternary type="primary" @click="emitCmd({ cmd: 'pixiv_back' })">← 返回</n-button>
        <span class="tw-follow-title">{{ state.detail.kind === 'novel' ? '小说详情' : '作品详情' }}</span>
        <n-spin v-if="state.detailLoading" :size="14" />
      </div>
      <n-scrollbar class="px-view-scroll">
        <div class="px-detail">
          <!-- 内容区 -->
          <!-- 插画/漫画：加载全部页 -->
          <div v-if="state.detail.kind === 'illust'" class="px-illust-pages">
            <div v-for="(u, i) in detailPageUrls" :key="i" class="px-illust-page" :title="`第 ${i + 1}P`">
              <img :src="proxied(u)" loading="lazy" referrerpolicy="no-referrer" :alt="`${state.detail.detail.album_name} 第${i + 1}P`" />
              <span class="px-page-no">{{ i + 1 }}P</span>
            </div>
          </div>
          <!-- 小说：左上角封面（点击查看/下载）+ 正文 -->
          <div v-else class="px-novel-body">
            <div class="px-novel-cover">
              <img :src="proxied(state.detail.detail.thumbnail)" referrerpolicy="no-referrer" alt="封面" @click="coverPreview = !coverPreview" />
              <div class="px-novel-cover-btns">
                <n-button size="tiny" @click="coverPreview = !coverPreview">{{ coverPreview ? '收起大图' : '查看大图' }}</n-button>
                <n-button size="tiny" type="warning" @click="downloadDetail">⬇ 下载封面</n-button>
              </div>
            </div>
            <div v-if="coverPreview" class="px-novel-cover-full">
              <img :src="proxied(detailCoverOriginal || state.detail.detail.thumbnail)" referrerpolicy="no-referrer" alt="封面大图" />
            </div>
            <div class="px-novel-text">
              <template v-for="(seg, i) in novelSegments" :key="i">
                <h4 v-if="seg.type === 'chapter'" class="px-novel-chapter">{{ seg.text }}</h4>
                <hr v-else-if="seg.type === 'newpage'" class="px-novel-sep" />
                <p v-else class="px-novel-para">{{ seg.text }}</p>
              </template>
            </div>
          </div>

          <!-- 赞 + 爱心（收藏） -->
          <div class="px-action-bar">
            <n-button size="small" round type="info" secondary @click="emitCmd({ cmd: 'pixiv_action', action: 'like', kind: state.detail.kind, item_id: state.detail.item_id })">👍 赞</n-button>
            <n-button size="small" round :type="state.detail.detail.is_bookmarked ? 'error' : 'warning'" secondary @click="emitCmd({ cmd: 'pixiv_action', action: state.detail.detail.is_bookmarked ? 'bookmark_delete' : 'bookmark_add', kind: state.detail.kind, item_id: state.detail.item_id })">
              {{ state.detail.detail.is_bookmarked ? '♥ 已收藏' : '♡ 收藏' }}
            </n-button>
            <n-button size="small" round type="warning" @click="downloadDetail">⬇ 下载{{ state.detail.kind === 'novel' ? '小说(txt)' : '全部原图' }}</n-button>
            <n-button size="small" round quaternary @click="openExternalPage">在浏览器打开</n-button>
          </div>

          <!-- 标题 → 作者说明 → TAGs → 统计 -->
          <h3 class="px-detail-title">{{ state.detail.detail.album_name }}</h3>
          <div class="px-detail-author">
            <img v-if="state.detail.detail.avatar" class="px-avatar-sm" :src="proxied(state.detail.detail.avatar)" referrerpolicy="no-referrer" @click="openUser(state.detail.detail)" />
            <span class="px-clickable" @click="openUser(state.detail.detail)">{{ state.detail.detail.author }}</span>
            <span v-if="state.detail.detail.posted" class="px-posted">{{ state.detail.detail.posted }}</span>
          </div>
          <div v-if="detailCaption" class="px-detail-caption">{{ detailCaption }}</div>
          <div class="px-detail-tags">
            <n-tag
              v-for="t in detailTags"
              :key="t.tag"
              size="small"
              round
              class="px-tag"
              :title="t.translated || t.tag"
              @click="emitCmd({ cmd: 'pixiv_tag_search', tag: t.tag })"
            >{{ t.tag }}</n-tag>
          </div>
          <div class="px-detail-stats">
            <span>👍 {{ formatCount(state.detail.detail.likes) }} 赞</span>
            <span>♥ {{ formatCount(state.detail.detail.bookmarks) }} 收藏</span>
            <span v-if="state.detail.detail.views">👁 {{ formatCount(state.detail.detail.views) }} 观看</span>
            <span>💬 {{ formatCount(state.detail.total_comments) }} 评论</span>
            <span v-if="state.detail.kind === 'novel' && state.detail.detail.words">✎ ≈{{ formatCount(state.detail.detail.words) }}字</span>
          </div>

          <!-- 合集（系列） -->
          <div v-if="state.detail.detail.series" class="px-series">
            <span class="px-series-label">合集：</span>
            <span class="px-series-name">{{ state.detail.detail.series }}</span>
          </div>

          <!-- 作品目录（多页目录，点击滚动定位） -->
          <div v-if="state.detail.kind === 'illust' && detailPageUrls.length > 1" class="px-toc">
            <div class="px-toc-title">作品目录（共 {{ detailPageUrls.length }}P）</div>
            <div class="px-toc-pages">
              <span v-for="(u, i) in detailPageUrls" :key="i" class="px-toc-item" @click="scrollToPage(i)">P{{ i + 1 }}</span>
            </div>
          </div>

          <!-- 评论区：留言 / 回复 / 删除自己的发言 -->
          <div class="px-comments">
            <div class="px-comments-title">评论区（{{ formatCount(state.detail.total_comments) }}）</div>
            <div class="px-comment-input">
              <n-input
                v-model:value="commentText"
                size="small"
                type="textarea"
                :rows="2"
                :placeholder="replyTarget ? `回复 ${replyTarget.user_name}：` : '写下你的评论...'"
              />
              <div class="px-comment-btns">
                <n-button v-if="replyTarget" size="tiny" quaternary @click="replyTarget = null">取消回复</n-button>
                <n-button size="small" type="primary" :disabled="!commentText.trim()" @click="sendComment">发表</n-button>
              </div>
            </div>
            <div v-for="c in state.detail.comments" :key="c.id" class="px-comment">
              <img v-if="c.user_avatar" class="px-avatar-sm" :src="proxied(c.user_avatar)" referrerpolicy="no-referrer" @click="emitCmd({ cmd: 'pixiv_open_user', user_id: c.user_id, name: c.user_name })" />
              <div class="px-comment-main">
                <div class="px-comment-head">
                  <span class="px-comment-user" @click="emitCmd({ cmd: 'pixiv_open_user', user_id: c.user_id, name: c.user_name })">{{ c.user_name }}</span>
                  <span v-if="c.parent_user" class="px-comment-reply-to">回复 {{ c.parent_user }}</span>
                  <span class="px-comment-date">{{ c.date }}</span>
                </div>
                <div class="px-comment-text">{{ c.comment }}</div>
                <div class="px-comment-ops">
                  <n-button size="tiny" quaternary type="primary" @click="replyTarget = c">回复</n-button>
                  <n-button v-if="c.user_id === state.userId" size="tiny" quaternary type="error" @click="deleteComment(c)">删除</n-button>
                </div>
              </div>
            </div>
            <div v-if="!state.detail.comments.length" class="px-section-empty">暂无评论，来抢沙发</div>
          </div>

          <!-- 相关作品（默认不加载，点击后加载） -->
          <div class="px-related">
            <n-button v-if="!relatedLoaded" size="small" block secondary :loading="relatedLoading" @click="loadRelated">相关作品（点击加载）</n-button>
            <template v-else>
              <div class="px-section-title" style="margin-bottom: 8px">相关作品</div>
              <div class="search-grid">
                <div v-for="item in relatedItems" :key="item.illust_id || item.novel_id" class="search-card px-card" @click="openDetail(item)">
                  <div class="thumb-wrapper">
                    <img :src="proxied(item.thumbnail)" loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name" />
                    <div class="thumb-files" v-if="item.files > 1">{{ item.files }}P</div>
                  </div>
                  <div class="card-name">{{ item.album_name }}</div>
                  <div class="iw-card-meta">
                    <span class="iw-card-author">{{ item.author }}</span>
                    <span class="px-stats-mini" v-if="item.bookmarks">♥{{ formatCount(item.bookmarks) }}</span>
                  </div>
                </div>
              </div>
              <div v-if="!relatedItems.length" class="px-section-empty">暂无相关作品</div>
            </template>
          </div>
        </div>
      </n-scrollbar>
    </div>

    <!-- ================= 发布作品弹窗（仿 Pixiv 投稿界面） ================= -->
    <n-modal v-model:show="uploadVisible" preset="card" title="发布作品" style="width: 92%; max-width: 640px">
      <div class="px-upload">
        <div class="px-upload-row">
          <span class="px-upload-label">作品图片：</span>
          <n-button size="small" @click="pickImages">选择图片（可多选）</n-button>
          <span class="px-upload-hint">支持 jpg / png / gif，第一张为封面</span>
        </div>
        <div v-if="uploadPaths.length" class="px-upload-files">
          <n-tag v-for="(p, i) in uploadPaths" :key="i" size="small" closable round @close="uploadPaths.splice(i, 1)">
            {{ p.split(/[\\/]/).pop() }}
          </n-tag>
        </div>
        <div class="px-upload-row"><span class="px-upload-label">标题：</span></div>
        <n-input v-model:value="uploadTitle" size="small" placeholder="作品标题（必填）" />
        <div class="px-upload-row"><span class="px-upload-label">说明：</span></div>
        <n-input v-model:value="uploadCaption" size="small" type="textarea" :rows="3" placeholder="作品说明（可选）" />
        <div class="px-upload-row">
          <span class="px-upload-label">标签：</span>
          <span class="px-upload-hint">逗号或空格分隔，至少 1 个（Pixiv 必填，最多 10 个）</span>
        </div>
        <n-input v-model:value="uploadTagsText" size="small" placeholder="如：原创, 女孩子, 风景" />
        <div class="px-upload-row">
          <span class="px-upload-label">年龄限制：</span>
          <n-button-group size="small">
            <n-button size="small" :type="uploadXRestrict === 0 ? 'primary' : 'default'" @click="uploadXRestrict = 0">全年龄</n-button>
            <n-button size="small" :type="uploadXRestrict === 1 ? 'primary' : 'default'" @click="uploadXRestrict = 1">R-18</n-button>
            <n-button size="small" :type="uploadXRestrict === 2 ? 'primary' : 'default'" @click="uploadXRestrict = 2">R-18G</n-button>
          </n-button-group>
        </div>
        <div class="px-upload-hint" style="margin-top: 10px">发布需登录；上传后可在 Pixiv 网页端查看审核状态</div>
      </div>
      <template #action>
        <n-button size="small" @click="uploadVisible = false">取消</n-button>
        <n-button size="small" type="primary" :loading="uploading" :disabled="!uploadPaths.length || !uploadTitle.trim() || !uploadTagsText.trim()" @click="submitUpload">发布</n-button>
      </template>
    </n-modal>

    <!-- ================= 消息 / 提醒 弹窗 ================= -->
    <n-modal v-model:show="notifyVisible" preset="card" title="消息与提醒" style="width: 90%; max-width: 620px">
      <div v-if="state.notifications && state.notifications.items && state.notifications.items.length" class="px-notify-list">
        <div v-for="n in state.notifications.items" :key="n.id" class="px-notify-item">
          <img v-if="n.user_avatar" class="px-avatar-sm" :src="proxied(n.user_avatar)" referrerpolicy="no-referrer" />
          <div class="px-notify-main">
            <div class="px-notify-text"><b>{{ n.user_name }}</b> {{ n.content }}</div>
            <div class="px-notify-date">{{ n.created }}</div>
          </div>
        </div>
      </div>
      <div v-else class="px-section-empty">
        {{ state.notifications && state.notifications.message ? state.notifications.message : '暂无消息/提醒' }}
      </div>
    </n-modal>

    <!-- ================= 书签（收藏标签）弹窗 ================= -->
    <n-modal v-model:show="bookmarkTagsVisible" preset="card" title="书签 · 收藏标签" style="width: 90%; max-width: 620px">
      <div v-if="state.bookmarkTags && state.bookmarkTags.tags && state.bookmarkTags.tags.length" class="px-tag-list">
        <n-tag
          v-for="t in state.bookmarkTags.tags"
          :key="t.name"
          size="small"
          round
          checkable
          class="px-tag"
          :title="`用「${t.name}」搜索我的收藏内容`"
          @click="searchBookmarkTag(t.name)"
        >{{ t.name }} ({{ t.count }})</n-tag>
      </div>
      <div v-else class="px-section-empty">
        {{ state.bookmarkTags && state.bookmarkTags.message ? state.bookmarkTags.message : '暂无收藏标签（收藏作品时加的标签会显示在这里）' }}
      </div>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { NTag, NButton, NButtonGroup, NDropdown, NPopover, NCheckbox, NInput, NModal, NSpin, NScrollbar, NProgress } from 'naive-ui'
import PaginationBar from './PaginationBar.vue'

const props = defineProps({
  // Pixiv 状态对象（App.vue reactive 透传：view/loginUser/userId/userPage/userLoading/detail/detailLoading/related/myTags/trending/notifications/bookmarkTags）
  state: { type: Object, required: true },
  searchQuery: { type: String, default: '' },
  searchResults: { type: Array, default: () => [] },
  searchPage: { type: Number, default: 1 },
  searchTotalPages: { type: Number, default: 0 },
  searchHasMore: { type: Boolean, default: false },
  searchTotalResults: { type: Number, default: 0 },
  searching: { type: Boolean, default: false },
  // 当前 feed 高亮（feed/follow/bookmark/userlist）
  activeFeed: { type: String, default: '' },
  pixivSearchType: { type: String, default: 'illust' },
  // 批量下载（多批次）进度
  batchRunning: { type: Boolean, default: false },
  batchProgress: { type: Object, default: () => ({ done: 0, total: 0, message: '' }) },
  mediaProxyPort: { type: Number, default: 0 },
})

const emit = defineEmits(['pixiv-command', 'open-album', 'go-page'])

// 统一命令出口：App.vue 集中处理（发后端 / 切视图 / 记录状态）
function emitCmd(payload) {
  emit('pixiv-command', payload)
}

// ---------- 工具 ----------
function proxied(url) {
  if (!url) return ''
  if (!props.mediaProxyPort) return url
  if (url.startsWith('thumb://') || url.startsWith('http://127.0.0.1')) return url
  return `http://127.0.0.1:${props.mediaProxyPort}/media?url=${encodeURIComponent(url)}`
}
function formatCount(n) {
  const v = Number(n) || 0
  if (v >= 10000) return (v / 10000).toFixed(1).replace(/\.0$/, '') + '万'
  return String(v)
}

// ---------- 常用标签 ----------
const tagPreviewCount = 12
const tagsExpanded = ref(false)
const allTags = computed(() => {
  const list = [...(props.state.myTags || []).map(t => ({ name: t.name, count: t.count, mine: true }))]
  const mineNames = new Set(list.map(t => t.name))
  for (const t of (props.state.trending || [])) {
    if (t.name && !mineNames.has(t.name)) list.push({ name: t.name, count: 0, mine: false })
  }
  return list
})
const displayTags = computed(() => tagsExpanded.value ? allTags.value : allTags.value.slice(0, tagPreviewCount))

// ---------- 排行榜菜单 ----------
const rankOptions = [
  { label: '插画日榜', key: 'rank_illust_day' },
  { label: '插画周榜', key: 'rank_illust_week' },
  { label: '插画月榜', key: 'rank_illust_month' },
  { label: '漫画日榜', key: 'rank_manga_day' },
  { label: '漫画周榜', key: 'rank_manga_week' },
  { label: '漫画月榜', key: 'rank_manga_month' },
  { label: '小说日榜', key: 'rank_novel_day' },
  { label: '小说周榜', key: 'rank_novel_week' },
  { label: '小说月榜', key: 'rank_novel_month' },
]

// ---------- 收藏选项 ----------
const bookmarkContent = ref('illust')
const bookmarkRestrict = ref('public')
const bookmarkAllowR18 = ref(true)
const novelNewestFirst = ref(true)
function loadBookmarks() {
  emitCmd({ cmd: 'pixiv_bookmarks', content: bookmarkContent.value, restrict: bookmarkRestrict.value, allow_r18: bookmarkAllowR18.value, page: 1 })
}

// ---------- 书签（收藏标签）弹窗 ----------
const bookmarkTagsVisible = ref(false)
watch(() => props.state.bookmarkTags, (v) => {
  if (v) bookmarkTagsVisible.value = true
})
function searchBookmarkTag(tag) {
  bookmarkTagsVisible.value = false
  emitCmd({ cmd: 'pixiv_tag_search', tag })
}

// ---------- 通知弹窗 ----------
const notifyVisible = ref(false)
watch(() => props.state.notifications, (v) => {
  if (v) notifyVisible.value = true
})

// ---------- 卡片操作 ----------
function openDetail(item) {
  if (item.kind === 'user' || item.user_id) {
    openUser(item)
    return
  }
  const kind = item.novel_id ? 'novel' : 'illust'
  emitCmd({ cmd: 'pixiv_detail', kind, item_id: item.novel_id || item.illust_id })
}
function openUser(item) {
  const uid = item.user_id || (item.author_url || '').match(/users\/(\d+)/)?.[1]
  if (uid) emitCmd({ cmd: 'pixiv_open_user', user_id: uid, name: item.author || item.album_name })
}
function toggleBookmark(item) {
  const kind = item.novel_id ? 'novel' : 'illust'
  const id = item.novel_id || item.illust_id
  emitCmd({ cmd: 'pixiv_action', action: item.is_bookmarked ? 'bookmark_delete' : 'bookmark_add', kind, item_id: id })
  item.is_bookmarked = !item.is_bookmarked
}
function toggleFollow(item) {
  emitCmd({ cmd: 'pixiv_action', action: item.is_followed ? 'unfollow' : 'follow', kind: 'user', item_id: item.user_id })
  item.is_followed = !item.is_followed
}

// ---------- 用户页 ----------
const userSections = computed(() => {
  const up = props.state.userPage
  if (!up) return []
  return [
    { key: 'illusts', label: '插画', items: up.illusts || [] },
    { key: 'manga', label: '漫画', items: up.manga || [] },
    { key: 'novels', label: '小说', items: up.novels || [] },
  ]
})
// ---------- 批量下载（多批次：每个用户一个后台下载任务） ----------
const userCards = computed(() => (props.searchResults || []).filter(i => i.kind === 'user'))
function batchDownloadPageUsers(content) {
  const ids = userCards.value.map(i => String(i.user_id)).filter(Boolean)
  if (!ids.length) return
  emitCmd({ cmd: 'pixiv_batch_download', user_ids: ids, content })
}
function batchDownloadUser(item, content) {
  const uid = String(item.user_id || '').trim()
  if (!uid) return
  emitCmd({ cmd: 'pixiv_batch_download', user_ids: [uid], content })
}
function downloadUserAll(content) {
  const up = props.state.userPage
  if (!up) return
  // 直接后台批量任务（多批次下载），不经解析预览页
  emitCmd({ cmd: 'pixiv_batch_download', user_ids: [String(up.user.user_id)], content })
}
function downloadSection(sec) {
  // 本区作品合并为一个批量任务（插画/漫画按 illust_id，小说按 novel_id）
  const illustIds = sec.items.map(i => i.illust_id).filter(Boolean).map(String)
  const novelIds = sec.items.map(i => i.novel_id).filter(Boolean).map(String)
  if (!illustIds.length && !novelIds.length) return
  emitCmd({ cmd: 'pixiv_batch_download', illust_ids: illustIds, novel_ids: novelIds, content: sec.key === 'novels' ? 'novel' : 'illust' })
}
function $emitOpenAlbum(item) {
  emit('open-album', item)
}

// ---------- 详情页 ----------
const coverPreview = ref(false)
const detailPageUrls = computed(() => {
  const raw = props.state.detail?.raw || {}
  return raw.page_urls || []
})
const detailCoverOriginal = computed(() => {
  const raw = props.state.detail?.raw || {}
  return (raw.meta_single_page || {}).original_image_url || ''
})
const detailCaption = computed(() => {
  const cap = (props.state.detail?.raw || {}).caption || ''
  if (!cap) return ''
  return cap
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&gt;/g, '>').replace(/&lt;/g, '<').replace(/&amp;/g, '&').replace(/&quot;/g, '"')
    .trim()
})
const detailTags = computed(() => {
  const raw = props.state.detail?.raw || {}
  return (raw.tags || []).map(t => ({ tag: t.tag || t.name || '', translated: t.translated_name || '' })).filter(t => t.tag)
})
// 小说正文分段：[newpage] 分页 / [chapter:标题] 章节 / [[rb:汉字>假名]] 注音 / [jump:n] 跳页
const novelSegments = computed(() => {
  const text = (props.state.detail?.raw || {}).novel_text || ''
  if (!text) return [{ type: 'para', text: '（正文加载失败或为空）' }]
  const segs = []
  let para = ''
  const flush = () => {
    const t = para.trim()
    if (t) segs.push({ type: 'para', text: t })
    para = ''
  }
  for (const line of text.split('\n')) {
    const chapter = line.trim().match(/^\[chapter:(.+)\]$/)
    if (chapter) { flush(); segs.push({ type: 'chapter', text: chapter[1] }); continue }
    if (line.trim() === '[newpage]') { flush(); segs.push({ type: 'newpage' }); continue }
    para += line
      .replace(/\[\[rb:\s*([^>\]]+)>\s*([^\]]+)\]\]/g, '$1（$2）')
      .replace(/\[jump:\d+\]/g, '')
      .replace(/\[\[jumpui:\d+\]\]/g, '')
  }
  flush()
  return segs.length ? segs : [{ type: 'para', text: '（正文为空）' }]
})
function scrollToPage(i) {
  const el = document.querySelectorAll('.px-illust-page')[i]
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
function openExternalPage() {
  const d = props.state.detail?.detail || {}
  if (d.album_url && window.api && window.api.openExternal) window.api.openExternal(d.album_url)
}
function downloadDetail() {
  $emitOpenAlbum(props.state.detail.detail)
}

// ---------- 评论区 ----------
const commentText = ref('')
const replyTarget = ref(null)
function sendComment() {
  const text = commentText.value.trim()
  if (!text) return
  emitCmd({
    cmd: 'pixiv_action', action: 'comment_add',
    kind: props.state.detail.kind, item_id: props.state.detail.item_id,
    text, parent_id: replyTarget.value ? replyTarget.value.id : '',
  })
  commentText.value = ''
  replyTarget.value = null
}
function deleteComment(c) {
  emitCmd({ cmd: 'pixiv_action', action: 'comment_delete', kind: props.state.detail.kind, item_id: props.state.detail.item_id, comment_id: c.id })
}

// ---------- 相关作品（懒加载） ----------
const relatedLoaded = ref(false)
const relatedLoading = ref(false)
const relatedItems = computed(() => {
  const r = props.state.related
  if (!r) return []
  return r.items || []
})
watch(() => props.state.related, (r) => {
  if (r) relatedLoading.value = false
})
watch(() => props.state.detail?.item_id, () => {
  relatedLoaded.value = false
  relatedLoading.value = false
})
function loadRelated() {
  relatedLoading.value = true
  emitCmd({ cmd: 'pixiv_related', kind: props.state.detail.kind, item_id: props.state.detail.item_id })
  relatedLoaded.value = true
}

// ---------- 发布作品 ----------
const uploadVisible = ref(false)
const uploading = ref(false)
const uploadPaths = ref([])
const uploadTitle = ref('')
const uploadCaption = ref('')
const uploadTagsText = ref('')
const uploadXRestrict = ref(0)
function pickImages() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/jpeg,image/png,image/gif'
  input.multiple = true
  input.onchange = () => {
    for (const f of (input.files || [])) {
      // Electron 30：File.path 为本地真实路径
      const p = f.path || ''
      if (p && !uploadPaths.value.includes(p)) uploadPaths.value.push(p)
    }
  }
  input.click()
}
watch(() => props.state.uploadResult, (r) => {
  if (r) {
    uploading.value = false
    if (r.ok) {
      uploadVisible.value = false
      uploadPaths.value = []
      uploadTitle.value = ''
      uploadCaption.value = ''
      uploadTagsText.value = ''
      uploadXRestrict.value = 0
    }
  }
})
function submitUpload() {
  uploading.value = true
  emitCmd({
    cmd: 'pixiv_upload',
    paths: uploadPaths.value.slice(),
    title: uploadTitle.value.trim(),
    caption: uploadCaption.value.trim(),
    tags: uploadTagsText.value.split(/[,，\s]+/).map(s => s.trim()).filter(Boolean).slice(0, 10),
    x_restrict: uploadXRestrict.value,
  })
}
</script>

<style scoped>
.px-panel {
  display: flex; flex-direction: column; gap: 8px;
  flex: 1; min-height: 0; overflow: hidden;
}
.px-list-scroll { flex: 1; min-height: 0; }

/* ---------- 卡片网格（复刻 RightPanel 搜索卡片样式） ---------- */
.search-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 12px;
  padding: 4px 0 10px;
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
.thumb-files {
  position: absolute;
  right: 6px;
  bottom: 6px;
  background: rgba(0, 0, 0, 0.65);
  color: #e0e0e6;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
}
.card-name {
  padding: 8px 10px 4px;
  font-size: 12.5px;
  color: #e0e0e6;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
.pa-toolbar { padding: 2px 0 4px; }
.pa-result-count { font-size: 12px; color: #8f8f98; }
.iw-card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px 8px;
  font-size: 11px;
  color: #8f8f98;
}
.iw-card-author {
  color: #63e2b7;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.iw-card-time { color: #777; margin-left: auto; flex-shrink: 0; }
html.light-mode .search-card { background: #fff; border-color: #e0e0e6; }
html.light-mode .card-name { color: #333338; }
html.light-mode .iw-card-meta { color: #8a8a93; }

/* ---------- 功能栏 ---------- */
.px-toolbar {
  display: flex; flex-direction: column; gap: 6px;
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
}
.px-toolbar-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.px-tags-row { align-items: flex-start; }
.px-tags-label { font-size: 12px; color: #999; flex-shrink: 0; padding-top: 2px; }
.px-tags-list { display: flex; flex-wrap: wrap; gap: 4px; flex: 1; min-width: 0; max-height: 26px; overflow: hidden; }
.px-tags-list.expanded { max-height: none; }
.px-tags-empty { font-size: 12px; color: #777; }
.px-tag { cursor: pointer; }
.px-unread-badge {
  display: inline-block; min-width: 16px; height: 16px; line-height: 16px;
  border-radius: 8px; background: #d03050; color: #fff;
  font-size: 10px; text-align: center; padding: 0 4px; margin-left: 2px;
}
.px-pop { display: flex; flex-direction: column; min-width: 220px; }
.px-pop-title { font-size: 12px; color: #999; margin-bottom: 4px; }
.px-pop-row { display: flex; align-items: center; gap: 8px; }

/* ---------- 卡片 ---------- */
.px-card { display: flex; flex-direction: column; }
.px-clickable { cursor: pointer; }
.px-badge {
  position: absolute; left: 6px; bottom: 6px;
  font-size: 11px; padding: 1px 6px; border-radius: 4px;
  color: #fff; pointer-events: none;
}
.px-card-actions {
  position: absolute; top: 6px; right: 6px;
  display: flex; gap: 4px; opacity: 0; transition: opacity 0.15s;
}
.search-card:hover .px-card-actions { opacity: 1; }
.px-mini-btn {
  width: 24px; height: 24px; border-radius: 50%; border: none; cursor: pointer;
  background: rgba(0, 0, 0, 0.55); color: #fff; font-size: 12px; line-height: 1;
}
.px-mini-btn:hover { background: rgba(0, 0, 0, 0.8); }
.px-mini-btn.active { background: #e0506a; }
.px-avatar-xs { width: 16px; height: 16px; border-radius: 50%; margin-right: 4px; object-fit: cover; }
.px-avatar-sm { width: 32px; height: 32px; border-radius: 50%; object-fit: cover; cursor: pointer; flex-shrink: 0; }
.px-avatar-lg { width: 72px; height: 72px; border-radius: 50%; object-fit: cover; flex-shrink: 0; }
.px-author { display: inline-flex; align-items: center; cursor: pointer; min-width: 0; }
.px-stats-mini { font-size: 11px; color: #e0506a; }

/* 用户卡片 */
.px-user-meta { display: flex; flex-direction: column; gap: 4px; padding: 0 8px 8px; }
.px-user-line { display: flex; align-items: center; gap: 8px; }
.px-user-sub { display: flex; align-items: center; justify-content: space-between; flex: 1; gap: 4px; min-width: 0; }
.px-user-account { font-size: 11px; color: #888; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.px-user-comment { font-size: 11px; color: #999; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.px-user-dl { display: flex; gap: 6px; margin-top: 4px; }
.pa-batch-bar { display: inline-flex; align-items: center; gap: 6px; margin-left: 10px; }
.pa-batch-label { font-size: 11px; color: #999; }
.px-batch-progress { display: flex; align-items: center; gap: 8px; padding: 4px 2px 2px; }
.px-batch-progress :deep(.n-progress) { flex: 1; min-width: 120px; }
.px-batch-text { font-size: 11px; color: #d48806; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 60%; }
.px-user-thumbs { display: flex; gap: 4px; }
.px-user-thumbs img { width: 48px; height: 48px; object-fit: cover; border-radius: 4px; }

/* ---------- 视图（用户页/详情页） ---------- */
.px-view { display: flex; flex-direction: column; min-height: 0; flex: 1; }
.px-view-scroll { flex: 1; min-height: 0; }

/* 用户主页 */
.px-profile { display: flex; flex-direction: column; gap: 14px; padding: 4px 2px; }
.px-profile-head { display: flex; gap: 14px; }
.px-profile-info { display: flex; flex-direction: column; gap: 6px; min-width: 0; flex: 1; }
.px-profile-name { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.px-name { font-size: 17px; font-weight: 600; }
.px-account { font-size: 12px; color: #888; }
.px-profile-desc { font-size: 12px; color: #aaa; white-space: pre-wrap; word-break: break-word; }
.px-profile-stats { display: flex; gap: 12px; flex-wrap: wrap; font-size: 12px; color: #999; }
.px-profile-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.px-user-section { display: flex; flex-direction: column; gap: 6px; }
.px-section-head { display: flex; align-items: center; gap: 8px; }
.px-section-title { font-size: 13px; font-weight: 600; color: #ddd; }
.px-section-empty { font-size: 12px; color: #777; padding: 12px 0; text-align: center; }

/* 详情页 */
.px-detail { display: flex; flex-direction: column; gap: 14px; padding: 4px 2px 30px; }
.px-illust-pages { display: flex; flex-direction: column; gap: 8px; }
.px-illust-page { position: relative; text-align: center; }
.px-illust-page img { max-width: 100%; border-radius: 4px; }
.px-page-no { position: absolute; right: 8px; top: 8px; font-size: 11px; background: rgba(0,0,0,0.55); color: #fff; border-radius: 4px; padding: 1px 6px; }
.px-novel-body { display: flex; flex-direction: column; gap: 10px; }
.px-novel-cover { display: flex; gap: 10px; align-items: flex-start; }
.px-novel-cover img { width: 120px; border-radius: 4px; cursor: pointer; object-fit: cover; }
.px-novel-cover-btns { display: flex; flex-direction: column; gap: 6px; }
.px-novel-cover-full img { max-width: 100%; border-radius: 4px; }
.px-novel-text { font-size: 14px; line-height: 1.9; color: #ccc; white-space: pre-wrap; word-break: break-word; background: rgba(255,255,255,0.02); border-radius: 6px; padding: 14px 16px; }
.px-novel-chapter { margin: 10px 0 4px; font-size: 15px; color: #7dd3fc; border-left: 3px solid #7dd3fc; padding-left: 8px; }
.px-novel-sep { border: none; border-top: 1px dashed rgba(255,255,255,0.2); margin: 14px 0; }
.px-novel-para { margin: 0; }
.px-action-bar { display: flex; gap: 8px; flex-wrap: wrap; }
.px-detail-title { margin: 0; font-size: 18px; }
.px-detail-author { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #aaa; }
.px-detail-author .px-clickable { cursor: pointer; }
.px-detail-author .px-clickable:hover { color: #63e2b7; }
.px-posted { font-size: 12px; color: #777; }
.px-detail-caption { font-size: 13px; color: #aaa; white-space: pre-wrap; word-break: break-word; line-height: 1.7; }
.px-detail-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.px-detail-stats { display: flex; gap: 14px; flex-wrap: wrap; font-size: 12px; color: #999; }
.px-series { font-size: 13px; color: #bbb; }
.px-series-label { color: #888; }
.px-series-name { color: #f2c97d; }
.px-toc { display: flex; flex-direction: column; gap: 6px; }
.px-toc-title { font-size: 13px; font-weight: 600; color: #ddd; }
.px-toc-pages { display: flex; flex-wrap: wrap; gap: 6px; }
.px-toc-item {
  font-size: 12px; padding: 2px 10px; border-radius: 10px;
  background: rgba(255,255,255,0.06); cursor: pointer; color: #ccc;
}
.px-toc-item:hover { background: rgba(99,226,183,0.2); }

/* 评论区 */
.px-comments { display: flex; flex-direction: column; gap: 10px; }
.px-comments-title { font-size: 13px; font-weight: 600; color: #ddd; }
.px-comment-input { display: flex; flex-direction: column; gap: 6px; }
.px-comment-btns { display: flex; justify-content: flex-end; gap: 6px; }
.px-comment { display: flex; gap: 10px; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
.px-comment-main { display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 0; }
.px-comment-head { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.px-comment-user { color: #63e2b7; cursor: pointer; }
.px-comment-reply-to { color: #888; }
.px-comment-date { color: #777; margin-left: auto; }
.px-comment-text { font-size: 13px; color: #ccc; white-space: pre-wrap; word-break: break-word; }
.px-comment-ops { display: flex; gap: 4px; }

/* 相关作品 */
.px-related { display: flex; flex-direction: column; gap: 8px; }

/* 弹窗内容 */
.px-upload { display: flex; flex-direction: column; gap: 8px; }
.px-upload-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.px-upload-label { font-size: 13px; color: #aaa; flex-shrink: 0; }
.px-upload-hint { font-size: 11px; color: #777; }
.px-upload-files { display: flex; flex-wrap: wrap; gap: 4px; }
.px-notify-list { display: flex; flex-direction: column; max-height: 400px; overflow-y: auto; }
.px-notify-item { display: flex; gap: 10px; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
.px-notify-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.px-notify-text { font-size: 13px; color: #ccc; }
.px-notify-date { font-size: 11px; color: #777; }
.px-tag-list { display: flex; flex-wrap: wrap; gap: 6px; }

/* 复用 tw-follow-toolbar 风格（RightPanel 全局样式不可用，这里内联定义） */
.tw-follow-toolbar {
  display: flex; align-items: center; gap: 10px; padding: 2px 0;
}
.tw-follow-title { font-size: 14px; font-weight: 600; color: #ddd; }

html.light-mode .px-toolbar { background: rgba(0, 0, 0, 0.02); border-color: rgba(0, 0, 0, 0.08); }
html.light-mode .px-novel-text { background: rgba(0,0,0,0.02); color: #444; }
html.light-mode .px-novel-chapter { color: #0369a1; border-left-color: #0369a1; }
html.light-mode .px-name, html.light-mode .tw-follow-title, html.light-mode .px-section-title,
html.light-mode .px-comments-title, html.light-mode .px-toc-title { color: #333; }
html.light-mode .px-profile-desc, html.light-mode .px-detail-caption, html.light-mode .px-comment-text,
html.light-mode .px-notify-text { color: #555; }
html.light-mode .px-detail-author, html.light-mode .px-detail-stats, html.light-mode .px-profile-stats { color: #666; }
</style>
