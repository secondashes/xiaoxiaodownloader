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
          <n-button size="small" :type="state.view === '' && activeFeed === 'follow_illust' ? 'primary' : 'default'" title="已关注作者的最新插画/漫画（断点更新+历史缓存）" @click="emitCmd({ cmd: 'pixiv_follow_feed', content: 'illust' })">关注作者更新漫画</n-button>
          <n-button size="small" :type="state.view === '' && activeFeed === 'follow_novel' ? 'primary' : 'default'" title="已关注作者的最新小说（断点更新+历史缓存）" @click="emitCmd({ cmd: 'pixiv_follow_feed', content: 'novel' })">关注作者更新小说</n-button>
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
            <n-button size="small" :type="state.view === '' && isBookmarkActive ? 'primary' : 'default'" title="我的收藏：插画/漫画/小说 × 公开/私密 × 年龄限制">⭐ 收藏</n-button>
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
        <n-button size="small" :type="state.view === '' && isBookmarkActive ? 'primary' : 'default'" title="书签：收藏标签列表，点标签查看该标签的收藏" @click="emitCmd({ cmd: 'pixiv_bookmark_tags', content: bookmarkContent === 'novel' ? 'novel' : 'illust' })">🔖 书签</n-button>
        <n-button size="small" :type="state.view === '' && activeFeed === 'illust' ? 'primary' : 'default'" title="为你推荐的作品" @click="emitCmd({ cmd: 'pixiv_feed', kind: 'illust', page: 1 })">推荐作品</n-button>
        <n-button size="small" :type="state.view === '' && activeFeed === 'recommended_user' ? 'primary' : 'default'" title="为你推荐的用户" @click="emitCmd({ cmd: 'pixiv_feed', kind: 'recommended_user', page: 1 })">推荐用户</n-button>
        <n-button size="small" type="warning" title="上传作品发布到 Pixiv（标题/说明/标签）" @click="uploadVisible = true">✏️ 发布作品</n-button>
        <n-button size="small" :type="(pxHiddenTags.length || pxHiddenAuthors.length) ? 'error' : 'default'" secondary
                  title="屏蔽设置：命中的标签或作者不显示在客户端" @click="openPxBlock">🚫 屏蔽{{ (pxHiddenTags.length || pxHiddenAuthors.length) ? `(${pxHiddenTags.length + pxHiddenAuthors.length})` : '' }}</n-button>
        <n-dropdown size="small" trigger="click" :options="batchDownloadOptions" @select="k => emitCmd({ cmd: 'pixiv_following_download_all', content: k })">
          <n-button size="small" type="warning" title="遍历全部关注用户，每人一个下载任务（同关注列表勾选批量）">⬇ 全部关注</n-button>
        </n-dropdown>
        <!-- 批量勾选（与其他站同款按键逻辑）：开关 → 全选/反选/清空 → 开始下载（消息/提醒按钮已删，腾位给批量） -->
        <n-button class="batch-cta" size="small"
                  :type="pxBatchJustSubmitted ? 'success' : (pxBatch.mode.value ? 'warning' : 'primary')"
                  :title="pxBatchJustSubmitted ? '任务已提交' : (pxBatch.mode.value ? '退出勾选模式' : '点击后列表进入勾选模式，点卡片勾选作品')"
                  @click="togglePxBatch">{{ pxBatchJustSubmitted ? '已提交 ✓' : (pxBatch.mode.value ? '取消勾选' : '批量下载') }}</n-button>
        <template v-if="pxBatch.mode.value">
          <n-button size="small" title="勾选当前列表全部可下载作品" @click="selectPxBatch('all')">全选</n-button>
          <n-button size="small" title="勾选状态反转" @click="selectPxBatch('invert')">反选</n-button>
          <n-button size="small" title="清空全部勾选" @click="selectPxBatch('clear')">清空</n-button>
          <n-button size="small" type="error" :disabled="!pxBatch.count.value"
                    title="下载勾选的作品（每个作品全部原图）"
                    @click="startPxBatch">开始下载{{ pxBatch.count.value ? `(${pxBatch.count.value})` : '' }}</n-button>
        </template>
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
        <span v-if="pxFiltered.hidden" class="px-hidden-note">已隐藏 {{ pxFiltered.hidden }} 个（屏蔽标签/作者）</span>
        <!-- 用户列表批量下载（多批次：每个用户一个下载任务） -->
        <span v-if="userCards.length" class="pa-batch-bar">
          <span class="pa-batch-label">批量下载本页 {{ userCards.length }} 个用户：</span>
          <n-button size="tiny" type="warning" @click="batchDownloadPageUsers('illust')">⬇ 插画/漫画</n-button>
          <n-button size="tiny" type="warning" @click="batchDownloadPageUsers('novel')">⬇ 小说</n-button>
        </span>
        <!-- 收藏列表批量下载（本页 / 全部；全部会自动跳过历史已下载，统一放进 我的插画/漫画/小说收藏 文件夹） -->
        <span v-if="isBookmarkFeed && searchResults.length" class="pa-batch-bar">
          <span class="pa-batch-label">收藏批量下载：</span>
          <n-button size="tiny" type="warning" title="下载当前页显示的全部作品" @click="downloadBookmarksPage">⬇ 本页全部</n-button>
          <n-button size="tiny" type="warning" title="遍历全部收藏，跳过已下载过的作品，按内容类型统一归档" @click="downloadAllBookmarks">⬇ 全部收藏（跳过已下载）</n-button>
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
          v-for="item in pxDisplayItems"
          :key="item.illust_id || item.novel_id || item.user_id || item.album_url"
          class="search-card px-card"
          :class="{
            'iw-batch-checked': pxBatch.mode.value && pxBatchCheckable(item) && pxBatch.checked.value.has(pxBatchKey(item)),
            'px-card-submitted': pxSubmitted.has(pxBatchKey(item)),
          }"
        >
          <div class="thumb-wrapper" @click="pxBatch.mode.value ? togglePxBatchItem(item) : openDetail(item)">
            <span v-if="pxBatch.mode.value && pxBatchCheckable(item)" class="iw-batch-check"
                  :class="{ checked: pxBatch.checked.value.has(pxBatchKey(item)) }">{{ pxBatch.checked.value.has(pxBatchKey(item)) ? '✓' : '' }}</span>
            <span v-else-if="pxBatch.mode.value" class="iw-batch-check" style="opacity: 0.35">－</span>
            <!-- 用户卡片：封面用近期作品图（当作背景图），无近期图回落头像 -->
            <img
              :src="proxied(item.kind === 'user' ? (item.recent_thumbs && item.recent_thumbs[0]) || item.thumbnail : item.thumbnail)"
              loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name"
            />
            <!-- 用户卡片：名称角标（画师名显示在封面左下） -->
            <span v-if="item.kind === 'user' && item.album_name" class="px-user-cover-name" :title="item.album_name">{{ item.album_name }}</span>
            <div class="thumb-files" v-if="item.files != null && item.files > 1">{{ item.files }}P</div>
            <div class="thumb-files" v-else-if="item.words">≈{{ formatCount(item.words) }}字</div>
            <span v-if="item.r18" class="px-badge" style="background: #d03050">R-18</span>
            <span v-if="item.ugoira" class="px-badge" style="background: #722ed1">动图</span>
            <span v-if="item.manga_type" class="px-badge" style="background: #2a7de1">漫画</span>
            <!-- 图片右上角快捷按钮：下载 / 收藏 / 全部系列 -->
            <div class="px-card-actions">
              <button class="px-mini-btn" title="解析并下载全部图片" @click.stop="$emit('open-album', item)">⬇</button>
              <button v-if="item.series_id" class="px-mini-btn" :title="`下载全部系列：${item.series_title || ''}（书名目录 + 每话章节）`" @click.stop="seriesDownload(item)">📚</button>
              <button v-if="item.kind !== 'user'" class="px-mini-btn" :class="{ active: item.is_bookmarked }" :title="item.is_bookmarked ? '已收藏（点击取消）' : '快速收藏'" @click.stop="toggleBookmark(item)">♥</button>
            </div>
          </div>
          <div class="card-name px-clickable" :title="item.album_name" @click="openDetail(item)">{{ item.album_name }}</div>
          <!-- 用户卡片：头像 + 简介 + 关注按钮 -->
          <div v-if="item.kind === 'user'" class="px-user-meta">
            <div class="px-user-line">
              <img v-if="item.thumbnail" class="px-avatar-sm" :src="proxied(item.thumbnail)" referrerpolicy="no-referrer" @click="openUser(item)" />
              <div class="px-user-sub">
                <span class="px-user-name px-clickable" :title="item.album_name" @click="openUser(item)">{{ item.album_name || '未知画师' }}</span>
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
      <!-- 渲染切片续载：多页 feed（关注更新等）数据完整，仅按需挂载卡片保证切换流畅 -->
      <div v-if="pxFiltered.items.length > pxDisplayItems.length" class="px-load-more">
        <n-button size="small" quaternary type="primary" @click="pxVisibleCount += PX_RENDER_PAGE">
          显示更多（已显示 {{ pxDisplayItems.length }} / 共 {{ pxFiltered.items.length }} 条）
        </n-button>
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
              <span class="px-section-title">{{ sec.label }}（{{ (state.userPage.page && state.userPage.page[sec.key]) ? `${sec.items.length}/${state.userPage.profile[`total_${sec.key === 'illusts' ? 'illusts' : sec.key}`] || sec.items.length}` : sec.items.length }}）</span>
              <n-button v-if="userSectionHasMore(sec.key)" size="tiny" quaternary type="primary"
                        :loading="state.userLoading"
                        title="加载该分类的下一页作品"
                        @click="loadUserSectionMore(sec.key)">加载更多</n-button>
              <n-button v-if="sec.items.length" size="tiny" quaternary type="primary" @click="downloadSection(sec)">⬇ 下载本区</n-button>
            </div>
            <div v-if="sec.items.length" class="search-grid">
              <div v-for="item in sec.items" :key="item.illust_id || item.novel_id" class="search-card px-card"
                   :class="{
                     'iw-batch-checked': pxBatch.mode.value && pxBatchCheckable(item) && pxBatch.checked.value.has(pxBatchKey(item)),
                     'px-card-submitted': pxSubmitted.has(pxBatchKey(item)),
                   }"
                   @click="pxBatch.mode.value && pxBatchCheckable(item) ? togglePxBatchItem(item) : openDetail(item)">
                <div class="thumb-wrapper">
                  <span v-if="pxBatch.mode.value && pxBatchCheckable(item)" class="iw-batch-check"
                        :class="{ checked: pxBatch.checked.value.has(pxBatchKey(item)) }">{{ pxBatch.checked.value.has(pxBatchKey(item)) ? '✓' : '' }}</span>
                  <img :src="proxied(item.thumbnail)" loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name" />
                  <div class="thumb-files" v-if="item.files > 1">{{ item.files }}P</div>
                  <span v-if="item.r18" class="px-badge" style="background: #d03050">R-18</span>
                </div>
                <div class="card-name">{{ item.album_name }}</div>
                <div class="iw-card-meta">
                  <span class="iw-card-author">{{ item.author }}</span>
                  <span class="px-stats-mini" v-if="item.bookmarks">♥{{ formatCount(item.bookmarks) }}</span>
                  <button v-if="item.series_id" class="px-mini-btn" style="margin-left: auto"
                          :title="`下载全部系列：${item.series_title || ''}（书名目录 + 每话章节）`"
                          @click.stop="seriesDownload(item)">📚 系列</button>
                </div>
              </div>
            </div>
            <div v-else class="px-section-empty">暂无{{ sec.label }}</div>
          </div>
        </div>
      </n-scrollbar>
    </div>

    <!-- ================= 作品详情视图 ================= -->
    <div v-else-if="state.view === 'detail'" class="px-view">
      <div class="tw-follow-toolbar">
        <n-button size="small" quaternary type="primary" @click="emitCmd({ cmd: 'pixiv_back' })">← 返回</n-button>
        <span class="tw-follow-title">{{ state.detail ? (state.detail.kind === 'novel' ? '小说详情' : '作品详情') : '作品详情' }}</span>
        <n-spin v-if="state.detailLoading" :size="14" />
      </div>
      <!-- 详情加载中 / 失败兜底：此前 state.detail 未到时整个面板空白（无任何反馈） -->
      <div v-if="!state.detail" class="px-section-empty" style="padding: 60px 12px">
        <template v-if="state.detailLoading">正在加载作品详情...</template>
        <template v-else>
          <div>详情加载失败或暂无数据</div>
          <n-button size="small" type="primary" style="margin-top: 10px"
                    @click="state.detailRetry && state.detailRetry()">重试</n-button>
        </template>
      </div>
      <n-scrollbar v-if="state.detail" class="px-view-scroll">
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
              </div>
            </div>
            <div v-if="coverPreview" class="px-novel-cover-full">
              <img :src="proxied(detailCoverOriginal || state.detail.detail.thumbnail)" referrerpolicy="no-referrer" alt="封面大图" />
            </div>
            <div class="px-novel-text">
              <template v-for="(seg, i) in novelSegments" :key="i">
                <h4 v-if="seg.type === 'chapter'" class="px-novel-chapter">{{ seg.text }}</h4>
                <hr v-else-if="seg.type === 'newpage'" class="px-novel-sep" />
                <img v-else-if="seg.type === 'image'" class="px-novel-illust" :src="proxied(seg.url)" loading="lazy" referrerpolicy="no-referrer" alt="插图" @click="novelIllustPreview = seg.url" />
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
            <n-dropdown v-if="state.detail.kind === 'novel'" size="small" trigger="click"
                        :options="novelFmtOptions" @select="k => downloadDetail(k)">
              <n-button size="small" round type="warning">⬇ 下载小说（txt/word）</n-button>
            </n-dropdown>
            <n-button v-else size="small" round type="warning" @click="downloadDetail()">⬇ 下载全部原图</n-button>
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

          <!-- 合集（系列）：连载作品可一键下载全部章节（书名目录 + 每话文件） -->
          <div v-if="state.detail.detail.series" class="px-series">
            <span class="px-series-label">合集：</span>
            <span class="px-series-name">{{ state.detail.detail.series }}</span>
            <n-button v-if="state.detail.detail.series_id" size="tiny" type="warning"
                      title="下载该系列全部章节，按书名目录归档" @click="seriesDownload(state.detail.detail)">⬇ 下载全部系列</n-button>
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

          <!-- 作者的其他作品（原站"用户作品"面板：同作者最新 12 个，点击链式开详情） -->
          <div v-if="authorWorks.length" class="px-related">
            <div class="px-section-title" style="margin-bottom: 8px">
              <a class="px-section-empty" style="color: #63e2b7; cursor: pointer"
                 @click="emitCmd({ cmd: 'pixiv_open_user', user_id: authorWorks[0].author_id || '', name: authorWorks[0].author })">{{ authorWorks[0].author }} 的作品</a>
            </div>
            <div class="search-grid">
              <div v-for="item in authorWorks" :key="item.illust_id" class="search-card px-card" @click="openDetail(item)">
                <div class="thumb-wrapper">
                  <img :src="proxied(item.thumbnail)" loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name" />
                  <div class="thumb-files" v-if="item.files > 1">{{ item.files }}P</div>
                </div>
                <div class="card-name" :title="item.album_name">{{ trTitle(item.album_name) }}</div>
              </div>
            </div>
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

    <!-- 小说插图大图预览 -->
    <n-modal :show="!!novelIllustPreview" preset="card" title="插图" style="width: min(880px, 92vw)"
             @update:show="v => { if (!v) novelIllustPreview = '' }">
      <div style="text-align: center">
        <img v-if="novelIllustPreview" :src="proxied(novelIllustPreview)" style="max-width: 100%; max-height: 76vh" referrerpolicy="no-referrer" alt="插图大图" />
      </div>
    </n-modal>

    <!-- 小说保存格式弹选（批量勾选含小说时） -->
    <n-modal :show="novelFmtModal" preset="dialog" type="info" title="选择小说保存格式"
             style="width: 460px"
             positive-text="TXT（纯文本 + 封面文件）" negative-text="word（封面插图按原文嵌入）"
             @positive-click="() => resolveNovelFmt('txt')"
             @negative-click="() => resolveNovelFmt('docx')"
             @update:show="v => { if (!v) novelFmtModal = false }">
      <div style="font-size: 13px; line-height: 1.8">
        <template v-if="pxBatchPendingKind === 'series'">
          系列连载《{{ (pxBatchPending || [])[0]?.title || '' }}》的每话章节将按所选格式保存到「书名」目录下：<br />
        </template>
        <template v-else>
          本次勾选中包含小说（{{ (pxBatchPending || []).filter(it => it.novel_id).length }} 本），请选择保存格式：<br />
        </template>
        • <b>TXT</b>：纯文本正文 + 单独的封面图片文件<br />
        • <b>word</b>：.docx 文档，封面与插图按原文位置嵌入
      </div>
    </n-modal>

    <!-- 屏蔽标签/作者设置 -->
    <n-modal v-model:show="pxBlockVisible" preset="card" title="屏蔽设置（标签 / 作者）" style="width: min(560px, 92vw)">
      <div class="px-block-hint">
        命中规则的作品卡片将<b>不显示在客户端</b>（搜索/收藏/关注更新/用户主页作品区均生效）。每行一条，精确匹配、忽略大小写。
      </div>
      <div class="px-block-row">
        <div class="px-block-label">屏蔽标签（每行一个）</div>
        <n-input v-model:value="pxBlockTagsText" type="textarea" :rows="5"
                 placeholder="例如：&#10;ロリ&#10;妹" />
      </div>
      <div class="px-block-row">
        <div class="px-block-label">屏蔽作者（每行一个，作者名或 @账号）</div>
        <n-input v-model:value="pxBlockAuthorsText" type="textarea" :rows="5"
                 placeholder="例如：&#10;某作者名&#10;some_account" />
      </div>
      <div style="display: flex; justify-content: flex-end; gap: 8px; margin-top: 10px">
        <n-button size="small" @click="pxBlockVisible = false">取消</n-button>
        <n-button size="small" type="primary" @click="savePxBlock">保存</n-button>
      </div>
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
import { NTag, NButton, NButtonGroup, NDropdown, NPopover, NCheckbox, NInput, NModal, NSpin, NScrollbar, NProgress, useMessage } from 'naive-ui'
import PaginationBar from './PaginationBar.vue'
import { useBatchSelection } from '../useBatchSelection.js'

const message = useMessage()

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

// ---------- 屏蔽标签/作者（抓取内容命中规则即不显示在客户端） ----------
const PX_BLOCK_KEY = 'pixiv_block_rules'
const pxBlockVisible = ref(false)
const pxHiddenTags = ref([])      // 屏蔽的标签（精确匹配，忽略大小写）
const pxHiddenAuthors = ref([])   // 屏蔽的作者名/账号（精确匹配，忽略大小写）
const pxBlockTagsText = ref('')
const pxBlockAuthorsText = ref('')
try {
  const _saved = JSON.parse(localStorage.getItem(PX_BLOCK_KEY) || '{}')
  pxHiddenTags.value = Array.isArray(_saved.tags) ? _saved.tags : []
  pxHiddenAuthors.value = Array.isArray(_saved.authors) ? _saved.authors : []
} catch { /* 损坏的本地缓存按空处理 */ }

function openPxBlock() {
  pxBlockTagsText.value = pxHiddenTags.value.join('\n')
  pxBlockAuthorsText.value = pxHiddenAuthors.value.join('\n')
  pxBlockVisible.value = true
}

function savePxBlock() {
  pxHiddenTags.value = pxBlockTagsText.value.split(/\n+/).map(s => s.trim()).filter(Boolean)
  pxHiddenAuthors.value = pxBlockAuthorsText.value.split(/\n+/).map(s => s.trim()).filter(Boolean)
  try {
    localStorage.setItem(PX_BLOCK_KEY, JSON.stringify({ tags: pxHiddenTags.value, authors: pxHiddenAuthors.value }))
  } catch { /* 忽略 */ }
  pxBlockVisible.value = false
  message.success(`屏蔽规则已保存（标签 ${pxHiddenTags.value.length} 个 / 作者 ${pxHiddenAuthors.value.length} 个）`)
}

function pxIsHidden(item) {
  const author = String(item.author || '').trim().toLowerCase()
  const account = String(item.account || '').trim().toLowerCase()
  if (pxHiddenAuthors.value.length && author) {
    for (const rule of pxHiddenAuthors.value) {
      const k = String(rule).toLowerCase()
      if (author === k || (account && account === k)) return true
    }
  }
  if (pxHiddenTags.value.length) {
    const tags = (item.tags || []).map(t => String(t).toLowerCase())
    if (tags.some(t => pxHiddenTags.value.some(rule => String(rule).toLowerCase() === t))) return true
  }
  return false
}

// 主列表过滤（搜索/feed/收藏/关注更新共用），hidden 计数用于提示条
const pxFiltered = computed(() => {
  const items = props.searchResults || []
  if (!pxHiddenTags.value.length && !pxHiddenAuthors.value.length) return { items, hidden: 0 }
  const out = items.filter(it => !pxIsHidden(it))
  return { items: out, hidden: items.length - out.length }
})

// ---------- 渲染切片（切换流畅性关键）：关注更新等多页 feed 现在动辄 240-600 条，
// 全量挂载会拖慢每次视图切换。每次只挂 100 张，底部"显示更多"续载；数据始终完整
//（批量全选/下载不受影响，仍作用于全量 pxFiltered） ----------
const PX_RENDER_PAGE = 100
const pxVisibleCount = ref(PX_RENDER_PAGE)
const pxDisplayItems = computed(() => pxFiltered.value.items.slice(0, pxVisibleCount.value))
// 仅"列表被替换"（换数据源）才重置切片；append 增量（长度增长且首条不变）不重置
// ——否则用户点过"显示更多"后，后台每补一页就把切片拽回 100 条、列表骤缩滚动
// 跳动（"界面自己动"的观感来源之一）
watch(() => props.searchResults, (nl, ol) => {
  const grew = (nl?.length || 0) > (ol?.length || 0)
  const sameHead = grew && nl?.[0] && ol?.[0]
    && String(nl[0].illust_id || nl[0].novel_id) === String(ol[0].illust_id || ol[0].novel_id)
  if (!sameHead) pxVisibleCount.value = PX_RENDER_PAGE
})

// ---------- 通用批量勾选模块（勾选模式 → 全选/反选/清空 → 提交后端批量下载） ----------
const pxBatch = useBatchSelection()

// 勾选池：列表视图用过滤后的搜索结果；用户主页视图用三区块作品（插画/漫画/小说均可勾选）
const pxBatchPool = computed(() => {
  if (props.state.view === 'user' && props.state.userPage) {
    const up = props.state.userPage
    const works = [...(up.illusts || []), ...(up.manga || []), ...(up.novels || [])]
    return works.filter(it => !pxIsHidden(it))
  }
  return pxFiltered.value.items
})

// 已提交标记（通用反馈）：提交批量后卡片保持绿色描边，批量结束自动清除
const pxSubmitted = ref(new Set())
const pxBatchJustSubmitted = ref(false)
watch(() => props.batchRunning, (running, was) => {
  if (was && !running) pxSubmitted.value = new Set()
})

// 小说保存格式弹选（勾选含小说时）
const novelFmtModal = ref(false)
let pxBatchPending = []
let pxBatchPendingKind = 'batch'   // batch=卡片勾选批量 | series=全部系列下载

function pxBatchKey(item) {
  return String(item.illust_id || item.novel_id || '')
}

function pxBatchCheckable(item) {
  // 用户卡片不可下载；插画/小说可勾选
  return !!(item.illust_id || item.novel_id)
}

function togglePxBatch() {
  pxBatch.toggle()
}

function pxBatchCurrentIds() {
  return pxBatchPool.value
    .filter(it => pxBatchCheckable(it))
    .map(it => pxBatchKey(it))
}

function selectPxBatch(mode) {
  const ids = pxBatchCurrentIds()
  if (mode === 'all') pxBatch.selectAll(ids)
  else if (mode === 'invert') pxBatch.invert(ids)
  else pxBatch.clearChecked()
}

function togglePxBatchItem(item) {
  if (!pxBatchCheckable(item)) return
  pxBatch.toggleItem(pxBatchKey(item))
}

function startPxBatch() {
  const byId = new Map(pxBatchPool.value.map(it => [pxBatchKey(it), it]))
  const picked = [...pxBatch.checked.value]
    .map(id => byId.get(id))
    .filter(it => it && (it.illust_id || it.novel_id))
  if (!picked.length) return
  // 勾选含小说：先弹 TXT/word 格式选择（通用交互，01:40 契约延续）
  if (picked.some(it => it.novel_id)) {
    pxBatchPendingKind = 'batch'
    pxBatchPending = picked
    novelFmtModal.value = true
    return
  }
  startPxBatchDo(picked, 'txt')
}

// ---------- 全部系列下载（连载：书名目录 + 每话章节） ----------
function seriesDownload(item) {
  const kind = item.novel_id ? 'novel' : 'illust'
  const title = item.series_title || item.album_name || item.series || ''
  if (kind === 'novel') {
    // 小说系列：先弹 txt/word 格式选择
    pxBatchPendingKind = 'series'
    pxBatchPending = [{ series_id: item.series_id, kind, title }]
    novelFmtModal.value = true
    return
  }
  emitCmd({ cmd: 'pixiv_series_download', series_id: item.series_id, kind: 'illust', title })
  message.success(`系列下载任务已提交：${title}（每话按章节归档）`)
}

function resolveNovelFmt(fmt) {
  novelFmtModal.value = false
  const picked = pxBatchPending
  pxBatchPending = []
  if (!picked.length) return
  if (pxBatchPendingKind === 'series') {
    const it = picked[0]
    emitCmd({ cmd: 'pixiv_series_download', series_id: it.series_id, kind: 'novel', novel_fmt: fmt, title: it.title })
    message.success(`系列下载任务已提交（小说 ${fmt === 'docx' ? 'word' : 'txt'}）`)
    return
  }
  startPxBatchDo(picked, fmt)
}

function startPxBatchDo(picked, fmt) {
  emit('pixiv-command', {
    cmd: 'pixiv_batch_download',
    novel_fmt: fmt,
    items: picked.map(it => ({
      illust_id: it.illust_id || '',
      novel_id: it.novel_id || '',
      kind: it.novel_id ? 'novel' : 'illust',
      title: it.album_name || '',
      author: it.author || '',
    })),
  })
  // 通用反馈：立即提示"任务已提交" + 按钮变绿 + 勾选目标改已提交色（批量结束后自动清除）
  message.success(`任务已提交（${picked.length} 个作品${fmt === 'docx' ? '，小说保存为 word' : ''}），正在后台解析下载`)
  const next = new Set(pxSubmitted.value)
  for (const it of picked) next.add(pxBatchKey(it))
  pxSubmitted.value = next
  pxBatchJustSubmitted.value = true
  setTimeout(() => { pxBatchJustSubmitted.value = false }, 4000)
  pxBatch.reset()
}

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

  // ---------- 批量下载菜单（下载全部关注用户的作品） ----------
  const batchDownloadOptions = [
    { label: '全部关注 · 插画/漫画', key: 'illust' },
    { label: '全部关注 · 小说', key: 'novel' },
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
  // 用户主页作品区同样应用屏蔽规则（标签/作者命中即不显示）
  const _f = (items) => (items || []).filter(it => !pxIsHidden(it))
  return [
    { key: 'illusts', label: '插画', items: _f(up.illusts) },
    { key: 'manga', label: '漫画', items: _f(up.manga) },
    { key: 'novels', label: '小说', items: _f(up.novels) },
  ]
})

// 用户页分区是否有下一页（后端 pixiv_user_result.has_more[tab]）
function userSectionHasMore(tabKey) {
  const up = props.state.userPage
  return !!(up && up.has_more && up.has_more[tabKey])
}

// 加载用户页分区下一页（App 追加到 pixivState.userPage[key]）
function loadUserSectionMore(tabKey) {
  const up = props.state.userPage
  if (!up) return
  const next = ((up.page && up.page[tabKey]) || 1) + 1
  emitCmd({ cmd: 'pixiv_user_page', user_id: up.user.user_id, tab: tabKey, page: next })
}
// ---------- 批量下载（多批次：每个用户一个后台下载任务） ----------
const userCards = computed(() => (props.searchResults || []).filter(i => i.kind === 'user'))
// 收藏模式：feed_kind 可能是 'bookmark' / 'bookmark_illust' / 'bookmark_manga' / 'bookmark_novel'
const isBookmarkActive = computed(() => props.activeFeed.startsWith('bookmark'))
// 收藏列表模式：顶部显示收藏批量下载工具条
const isBookmarkFeed = computed(() => isBookmarkActive.value && props.state.view === '')
function downloadBookmarksPage() {
  // 本页全部作品 → 复用勾选作品合并下载通道（插画/漫画按 illust_id，小说按 novel_id）
  const rs = props.searchResults || []
  const illustIds = rs.map(i => i.illust_id).filter(Boolean).map(String)
  const novelIds = rs.map(i => i.novel_id).filter(Boolean).map(String)
  if (!illustIds.length && !novelIds.length) return
  emitCmd({ cmd: 'pixiv_batch_download', illust_ids: illustIds, novel_ids: novelIds, content: novelIds.length && !illustIds.length ? 'novel' : 'illust' })
}
function downloadAllBookmarks() {
  // 全部收藏：后端遍历全部分页，跨记录查重跳过已下载，统一归档 我的插画/漫画/小说收藏
  emitCmd({
    cmd: 'pixiv_bookmarks_download_all',
    content: bookmarkContent.value, restrict: bookmarkRestrict.value,
    allow_r18: bookmarkAllowR18.value,
  })
}
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
// 作者的其他作品（后端随详情下发，原站"用户作品"面板）
const authorWorks = computed(() => props.state.detail?.author_works || [])
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
  const raw = props.state.detail?.raw || {}
  const text = raw.novel_text || ''
  if (!text) return [{ type: 'para', text: '（正文加载失败或为空）' }]
  const embeddedImgs = raw.embedded_images || {}
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
    // 插图标记（[uploadedimage:N] / [pixivimage:ID-p]）：按原位拆分渲染为图片段
    const parts = line.split(/(\[(?:uploadedimage:\d+|pixivimage:\d+(?:-\d+)?)\])/)
    for (let pi = 0; pi < parts.length; pi++) {
      const part = parts[pi]
      if (pi % 2 === 1) {
        flush()
        const url = embeddedImgs[part]
        if (url) segs.push({ type: 'image', url })
        continue
      }
      para += part
        .replace(/\[\[rb:\s*([^>\]]+)>\s*([^\]]+)\]\]/g, '$1（$2）')
        .replace(/\[jump:\d+\]/g, '')
        .replace(/\[\[jumpui:\d+\]\]/g, '')
    }
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
function downloadDetail(fmt) {
  const d = props.state.detail.detail
  if (props.state.detail.kind === 'novel') {
    // 小说：带格式标记走解析管线（后端按 _novel_fmt 生成 txt 或 word 下载条目）
    $emitOpenAlbum({ ...d, _novel_fmt: fmt === 'docx' ? 'docx' : 'txt' })
    return
  }
  $emitOpenAlbum(d)
}
// 小说插图大图预览
const novelIllustPreview = ref('')
const novelFmtOptions = [
  { label: '📄 下载为 txt（纯文本，附封面文件）', key: 'txt' },
  { label: '📝 下载为 word（封面+插图按原文位置嵌入）', key: 'docx' },
]

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
/* 用户卡片：封面左下画师名角标 + 元信息区名称行 */
.px-user-cover-name {
  position: absolute; left: 0; bottom: 0; right: 0;
  padding: 14px 6px 3px;
  font-size: 12px; font-weight: 600; color: #fff;
  background: linear-gradient(transparent, rgba(0,0,0,.72));
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  pointer-events: none;
}
.px-user-names { display: flex; flex-direction: column; min-width: 0; flex: 1; gap: 1px; }
.px-user-name { max-width: 130px; font-size: 12px; font-weight: 600; color: #d8d8de; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.px-user-name:hover { color: #63e2b7; }
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
.px-novel-illust { display: block; max-width: 100%; max-height: 70vh; margin: 10px auto; border-radius: 6px; cursor: zoom-in; }
.px-block-hint { font-size: 12px; color: #999; line-height: 1.7; margin-bottom: 10px; }
.px-block-row { margin-bottom: 10px; }
.px-block-label { font-size: 12px; color: #bbb; margin-bottom: 4px; }
.px-hidden-note { font-size: 12px; color: #e08c8c; }
.px-load-more { display: flex; justify-content: center; padding: 8px 0 4px; }
/* 批量勾选角标（此前缺样式导致勾选模式视觉上无任何变化 = "没有框选"） */
.px-card .iw-batch-check {
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
.px-card .iw-batch-check.checked { background: #18a058; border-color: #36ad6a; }
.px-card.iw-batch-checked { outline: 2px solid #18a058; outline-offset: -2px; }
.px-card-submitted { outline: 2px solid #63e2b7; outline-offset: -2px; border-radius: 8px; background: rgba(99, 226, 183, 0.08); }
.px-card-submitted .card-name::after { content: ' ✓已提交'; color: #63e2b7; font-size: 11px; }
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
