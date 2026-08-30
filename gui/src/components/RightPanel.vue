<template>
  <div class="right-panel">
    <!-- 全局右键菜单：单个文件/资源 → 下载此项（静默添加到下载任务） -->
    <n-dropdown
      trigger="manual"
      placement="bottom-start"
      :x="ctxMenu.x"
      :y="ctxMenu.y"
      :show="ctxMenu.show"
      :options="ctxMenuOptions"
      @select="onCtxMenuSelect"
      @clickoutside="ctxMenu.show = false"
    />

    <!-- 顶部：站点切换 + 搜索/链接输入 + 按钮 -->
    <div class="url-bar">
      <!-- 站点切换：竖排三类（二次元 / 三次元 / 综合类） -->
      <div class="site-switch-groups">
        <div class="site-group">
          <span class="site-group-label">二次元</span>
          <div class="site-group-btns">
            <button
              v-for="s in ['pawchive', 'exhentai', 'iwara', 'hanime', 'pixiv', 'oreno3d', 'erommdtube', 'asmr']"
              :key="s"
              class="site-chip"
              :class="{ on: site === s }"
              @click="switchSite(s)"
            >{{ siteChipName(s) }}</button>
          </div>
        </div>
        <div class="site-group">
          <span class="site-group-label">三次元</span>
          <div class="site-group-btns">
            <button
              class="site-chip"
              :class="{ on: site === 'coomer' }"
              @click="switchSite('coomer')"
            >Coomer</button>
            <button
              v-for="s in ['xhamster', 'pornhub', 'xvideos', 'javdb']"
              :key="s"
              class="site-chip"
              :class="{ on: site === s }"
              @click="switchSite(s)"
            >{{ s === 'xhamster' ? 'xHamster' : (s === 'pornhub' ? 'Pornhub' : (s === 'javdb' ? 'JavDB' : 'XVideos')) }}</button>
          </div>
        </div>
        <div class="site-group">
          <span class="site-group-label">综合类</span>
          <div class="site-group-btns">
            <button
              v-for="s in ['bunkr', 'twitter']"
              :key="s"
              class="site-chip"
              :class="{ on: site === s }"
              @click="switchSite(s)"
            >{{ s === 'bunkr' ? 'Bunkr' : 'X' }}</button>
          </div>
        </div>
      </div>
      <!-- Pawchive 搜索模式：画师搜索 / 标签搜索 -->
      <n-select
        v-if="site === 'pawchive'"
        :value="searchMode"
        :options="searchModeOptions"
        size="large"
        class="search-mode-select"
        @update:value="v => $emit('update:search-mode', v)"
      />
      <n-input
        :value="searchQuery"
        @update:value="$emit('update:search-query', $event)"
        :placeholder="inputPlaceholder"
        size="large"
        clearable
        @keyup.enter="handleSearch"
        style="flex: 1"
      >
        <template #prefix>
          <span style="color: #63e2b7">🔍</span>
        </template>
      </n-input>
      <n-button
        type="primary"
        size="small"
        class="search-btn"
        :loading="searching || inspecting"
        :disabled="!searchQuery.trim() || downloading"
        @click="handleSearch"
      >
        {{ (searching || inspecting) ? '处理中...' : (isUrl ? '解析' : '搜索') }}
      </n-button>
      <!-- 全局自动翻译开关（缩小按钮）：点击一次开始翻译当前页面全部内容（转圈动效表示进行中），
           开启后新增内容自动翻译；再点击一次停止翻译并恢复原文 -->
      <n-button
        size="tiny"
        class="auto-translate-btn"
        :class="{ on: autoTranslateMode }"
        :title="autoTranslateMode ? '翻译进行中/已开启，点击停止并恢复原文' : '点击开始翻译当前页面全部内容（后续内容自动翻译）'"
        @click="$emit('toggle-auto-translate-mode')"
      >
        <!-- 自绘转圈（不用 :loading，避免按钮被禁用无法点击停止） -->
        <span v-if="autoTranslating" class="tr-spinner"></span>
        <span v-else :style="{ color: autoTranslateMode ? '#63e2b7' : '' }">🌐</span>
      </n-button>
    </div>

    <!-- ExHentai 搜索选项栏：复刻原版搜索页过滤按钮（分类复选/评分/仅种子/页数范围），
         改动后自动按新条件重新搜索（汉化按钮） -->
    <div v-if="site === 'exhentai' && fileList.length === 0 && !exGalleryDetail" class="ex-search-options">
      <div class="ex-cats">
        <span class="ex-cats-label">分类：</span>
        <button
          v-for="c in exCategories"
          :key="c.key"
          class="ex-cat-chip"
          :class="{ on: exCats.includes(c.key) }"
          :title="c.label"
          @click="exToggleCat(c.key)"
        >{{ c.label }}</button>
        <button class="ex-cat-chip ex-cat-all" title="恢复全部分类" @click="exSelectAllCats">全选</button>
        <button
          class="ex-cat-chip ex-fav-btn"
          :class="{ on: exFavMode }"
          title="查看我在 ExHentai 收藏的画廊"
          @click="$emit('ex-favorites', 1)"
        >★ 我的收藏</button>
        <button
          class="ex-cat-chip ex-hide-tag-btn"
          :class="{ on: exHidePanel }"
          title="设置不想显示的标签（含该标签的画廊会被隐藏）"
          @click="exHidePanel = !exHidePanel"
        >🚫 隐藏标签{{ exHiddenTags.length ? `（${exHiddenTags.length}）` : '' }}</button>
      </div>
      <!-- 隐藏标签管理面板：手动输入标签名长期保存，× 删除 -->
      <div v-if="exHidePanel" class="ex-hide-panel">
        <div class="ex-hide-input-row">
          <n-input
            v-model:value="exHideTagInput"
            size="tiny"
            clearable
            placeholder="输入标签名，如 female:x 或直接填 x"
            class="ex-hide-input"
            @keyup.enter="exAddHiddenTag"
          />
          <n-button size="tiny" type="primary" @click="exAddHiddenTag">添加</n-button>
        </div>
        <div class="ex-hide-tags" v-if="exHiddenTags.length">
          <span
            v-for="t in exHiddenTags"
            :key="t"
            class="ex-hide-chip"
            :title="`点击删除隐藏标签：${t}`"
          >{{ t }}<span class="ex-hide-chip-x" @click.stop="$emit('ex-delete-hidden-tag', t)">×</span></span>
        </div>
        <div v-else class="ex-hide-empty">尚未设置隐藏标签。填 "xxx" 会隐藏所有命名空间下的 xxx；填 "female:xxx" 只隐藏 female 下的 xxx。</div>
      </div>
      <div class="ex-filters">
        <div class="ex-filter-item">
          <span class="ex-filter-label">最低评分</span>
          <n-select
            :value="exMinRating"
            :options="exRatingOptions"
            size="tiny"
            class="ex-rating-select"
            @update:value="v => emitExSearch({ exhentai_min_rating: v })"
          />
        </div>
        <div class="ex-filter-item">
          <span class="ex-filter-label">仅显示有种子</span>
          <n-switch
            :value="exTorrentsOnly"
            size="small"
            @update:value="v => emitExSearch({ exhentai_torrents_only: v })"
          />
        </div>
        <div class="ex-filter-item">
          <span class="ex-filter-label">页数范围</span>
          <n-input-number
            :value="exPageMin || null"
            size="tiny"
            :min="0"
            :max="9999"
            placeholder="最小"
            clearable
            class="ex-page-input"
            @update:value="v => emitExSearch({ exhentai_page_min: v || 0 })"
          />
          <span class="ex-filter-sep">-</span>
          <n-input-number
            :value="exPageMax || null"
            size="tiny"
            :min="0"
            :max="9999"
            placeholder="最大"
            clearable
            class="ex-page-input"
            @update:value="v => emitExSearch({ exhentai_page_max: v || 0 })"
          />
        </div>
      </div>
    </div>

    <!-- X (Twitter) 工具栏：浏览模式 / 关注列表 / 关注我的人 / 我的分类（需登录）
         常驻显示（此前文件列表/搜索结果非空时整条消失，导致无法进入浏览模式） -->
    <div v-if="site === 'twitter' && !twFollowMode" class="tw-toolbar">
      <n-button
        size="small"
        :type="twFollowMode === 'browse' ? 'primary' : 'default'"
        :loading="twBrowseLoading && twFollowMode === 'browse'"
        @click="$emit('tw-browse')"
      >浏览模式</n-button>
      <n-button
        size="small"
        :type="twFollowMode === 'following' ? 'primary' : 'default'"
        :loading="twFollowLoading && twFollowMode === 'following'"
        @click="$emit('tw-follow-list', 'following')"
      >关注列表</n-button>
      <n-button
        size="small"
        :type="twFollowMode === 'followers' ? 'primary' : 'default'"
        :loading="twFollowLoading && twFollowMode === 'followers'"
        @click="$emit('tw-follow-list', 'followers')"
      >关注我的人</n-button>
      <n-button
        size="small"
        :type="twFollowMode === 'follows' ? 'primary' : 'default'"
        @click="$emit('tw-follow-list', 'follows')"
      >我的分类</n-button>
      <!-- 本地搜索：搜缓存内容（#tag / 推文内容 / 昵称 / @handle / 简介 / 分类） -->
      <n-input
        :value="twLocalSearch"
        size="small"
        clearable
        round
        placeholder="🔍 搜缓存内容：tag / 推文 / 昵称 / @推特号"
        class="tw-local-search"
        @update:value="$emit('update:tw-local-search', $event)"
      />
      <span class="tw-toolbar-hint">点用户查看 TA 的关注/粉丝与媒体；浏览模式看关注博主的最近更新</span>
    </div>

    <!-- Iwara 工具栏：IW站/AI站 切换 + 主页（最近更新）/ 我的关注 / 我的好友 -->
    <div v-if="site === 'iwara' && fileList.length === 0 && iwView !== 'detail'" class="tw-toolbar">
      <n-button-group size="small">
        <n-button
          size="small"
          :type="iwSite === 'iwara' ? 'primary' : 'default'"
          title="切换到 IW 站 (iwara.tv)"
          @click="$emit('iw-set-site', 'iwara')"
        >IW站</n-button>
        <n-button
          size="small"
          :type="iwSite === 'ai' ? 'primary' : 'default'"
          title="切换到 AI 站 (iwara.ai)，登录信息与 IW 站共用"
          @click="$emit('iw-set-site', 'ai')"
        >AI站</n-button>
      </n-button-group>
      <n-button
        size="small"
        :type="iwView === 'home' && iwHomeMode !== 'subscribed' ? 'primary' : 'default'"
        :loading="iwHomeLoading && iwView === 'home' && iwHomeMode !== 'subscribed'"
        title="全站最近投稿（主页默认）"
        @click="$emit('iw-home', 1)"
      >主页</n-button>
      <n-button
        size="small"
        :type="iwView === 'home' && iwHomeMode === 'subscribed' ? 'primary' : 'default'"
        :loading="iwHomeLoading && iwView === 'home' && iwHomeMode === 'subscribed'"
        title="我关注的更新（订阅流）：只看已关注作者的最新投稿，需登录"
        @click="$emit('iw-subscribed')"
      >我关注的更新</n-button>
      <n-button
        size="small"
        :type="iwView === 'following' ? 'primary' : 'default'"
        :loading="iwFollowLoading && iwView === 'following'"
        @click="$emit('iw-following', 1)"
      >我的关注</n-button>
      <n-button
        size="small"
        :type="iwView === 'friends' ? 'primary' : 'default'"
        :loading="iwFriendLoading && iwView === 'friends'"
        @click="$emit('iw-friends', 1)"
      >我的好友</n-button>
      <n-button
        size="small"
        :type="iwBatchMode ? 'warning' : 'default'"
        :title="iwBatchMode ? '退出勾选模式' : '点击后当前列表进入勾选模式，勾选要下载的用户/视频'"
        @click="toggleIwBatch"
      >{{ iwBatchMode ? '取消勾选' : '批量解析下载' }}</n-button>
      <n-button
        v-if="iwBatchMode"
        size="small"
        type="error"
        :disabled="!iwBatchChecked.size"
        :loading="iwBatchRunning"
        :title="`开始下载勾选的 ${iwBatchChecked.size} 项（每个用户单独建任务）`"
        @click="startIwBatch"
      >开始下载{{ iwBatchChecked.size ? `(${iwBatchChecked.size})` : '' }}</n-button>
      <span v-if="iwBatchRunning" class="tw-toolbar-hint iw-batch-progress">
        {{ iwBatchProgress.message || '准备中...' }}（{{ iwBatchProgress.done }}/{{ iwBatchProgress.total }}）
      </span>
      <span v-else class="tw-toolbar-hint">主页看最近更新；点视频卡片看完整信息；点作者可关注 / 进主页</span>
    </div>

    <!-- Hanime1 (H站) 搜索选项栏：分类 + 排序 + 主页/用户中心（分类浏览复刻原版分类按钮） -->
    <div v-if="site === 'hanime' && fileList.length === 0 && haView !== 'detail'" class="ex-search-options">
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
          size="tiny"
          :type="haBatchMode ? 'warning' : 'default'"
          :title="haBatchMode ? '退出勾选模式' : '点击后当前列表进入勾选模式，勾选要下载的视频'"
          @click="toggleHaBatch"
        >{{ haBatchMode ? '取消勾选' : '批量下载' }}</n-button>
        <n-button
          v-if="haBatchMode"
          size="tiny"
          type="error"
          :disabled="!haBatchChecked.size"
          :loading="haBatchRunning"
          :title="`开始下载勾选的 ${haBatchChecked.size} 个视频（自动取最高画质）`"
          @click="startHaBatch"
        >开始下载{{ haBatchChecked.size ? `(${haBatchChecked.size})` : '' }}</n-button>
        <span v-if="haBatchRunning" class="iw-batch-progress ha-batch-progress">
          {{ haBatchProgress.message || '准备中...' }}（{{ haBatchProgress.done }}/{{ haBatchProgress.total }}）
        </span>
      </div>
    </div>

    <!-- Oreno3D (O3D) / EroMMDTube (E站) 工具栏：主页 + 排序 + 角色列表/人気作者/热门分类 + 收藏（无需登录） -->
    <div v-if="isOrenoSite && fileList.length === 0 && orView !== 'detail'" class="tw-toolbar">
      <n-button
        size="small"
        :type="orView === 'home' ? 'primary' : 'default'"
        :loading="orHomeLoading && orView === 'home'"
        title="主页（人気排序的视频列表）"
        @click="$emit('or-home', 1)"
      >主页</n-button>
      <n-select
        :value="settings.oreno_sort || 'hot'"
        :options="orSortOptions"
        size="small"
        class="or-sort-select"
        title="切换排序（切主页/标签/角色/作者列表与搜索结果）"
        @update:value="v => $emit('or-sort-update', v || 'hot')"
      />
      <n-button
        size="small"
        :type="orView === 'characters' ? 'primary' : 'default'"
        :loading="orCharsLoading && orView === 'characters'"
        title="浏览全部角色（人気角色 + 五十音分组），点击角色查看对应视频"
        @click="$emit('or-characters')"
      >👥 角色列表</n-button>
      <n-button
        size="small"
        :type="orView === 'authors' ? 'primary' : 'default'"
        :loading="orAuthorsLoading && orView === 'authors'"
        title="人気作者排行榜（分页浏览），点击作者查看全部作品"
        @click="$emit('or-authors-index', 1)"
      >👤 人気作者</n-button>
      <n-button
        size="small"
        :loading="orTagsLoading"
        title="热门分类组 + 全部标签，点击查看对应视频"
        @click="showOrTags"
      >🏷 热门分类</n-button>
      <n-button
        size="small"
        :type="orView === 'list' && orList.type === 'favorites' ? 'primary' : 'default'"
        title="我收藏的视频（保存在本地，点击管理）"
        @click="$emit('or-favorites')"
      >♥ 我的收藏</n-button>
      <n-button
        size="small"
        :type="orBatchMode ? 'warning' : 'default'"
        :title="orBatchMode ? '退出勾选模式' : '点击后当前列表进入勾选模式，勾选要下载的视频'"
        @click="toggleOrBatch"
      >{{ orBatchMode ? '取消勾选' : '批量下载' }}</n-button>
      <n-button
        v-if="orBatchMode"
        size="small"
        type="error"
        :disabled="!orBatchChecked.size"
        :loading="orBatchRunning"
        :title="`开始下载勾选的 ${orBatchChecked.size} 个视频（iwara 源最高画质）`"
        @click="startOrBatch"
      >开始下载{{ orBatchChecked.size ? `(${orBatchChecked.size})` : '' }}</n-button>
      <span v-if="orBatchRunning" class="tw-toolbar-hint iw-batch-progress">
        {{ orBatchProgress.message || '准备中...' }}（{{ orBatchProgress.done }}/{{ orBatchProgress.total }}）
      </span>
      <span v-else class="tw-toolbar-hint">点视频卡片看详情与播放；点角色/作者/标签查看同类作品</span>
    </div>

    <!-- ASMR 音声站工具栏：热门作品 / 媒体库（排序+仅带字幕）/ 我的收藏 / 社团·标签·声优索引 / 批量下载 -->
    <div v-if="site === 'asmr' && fileList.length === 0 && asmrView !== 'detail'" class="ex-search-options">
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
          size="tiny"
          :type="asmrBatchMode ? 'warning' : 'default'"
          :title="asmrBatchMode ? '退出勾选模式' : '点击后当前列表进入勾选模式，勾选要下载的作品'"
          @click="toggleAsmrBatch"
        >{{ asmrBatchMode ? '取消勾选' : '批量下载' }}</n-button>
        <n-button
          v-if="asmrBatchMode"
          size="tiny"
          type="error"
          :disabled="!asmrBatchChecked.size"
          :loading="asmrBatchRunning"
          :title="`开始下载勾选的 ${asmrBatchChecked.size} 个作品（整包下载全部音轨）`"
          @click="startAsmrBatch"
        >开始下载{{ asmrBatchChecked.size ? `(${asmrBatchChecked.size})` : '' }}</n-button>
        <span v-if="asmrBatchRunning" class="iw-batch-progress">
          {{ asmrBatchProgress.message || '准备中...' }}（{{ asmrBatchProgress.done }}/{{ asmrBatchProgress.total }}）
        </span>
        <span v-else class="tw-toolbar-hint">点作品卡片查看音轨列表并在线试听；可按社团/标签/声优筛选</span>
      </div>
    </div>

    <!-- Oreno3D / EroMMDTube 热门分类弹窗：分类组（tag-groups）+ 全部标签；点击分类组查看组内标签 -->
    <n-modal
      v-model:show="orTagsModal"
      preset="card"
      class="or-tags-modal"
      :title="orTagGroupTitle ? `分类组：${orTagGroupTitle}` : '热门分类（分类组 + 标签）'"
      style="width: 560px; max-width: 92vw"
    >
      <n-input
        v-model:value="orTagsFilter"
        size="small"
        clearable
        placeholder="🔍 输入文字过滤分类组/标签"
        style="margin-bottom: 8px"
      />
      <div class="or-tags-body">
        <div v-if="orTagsLoading && !orTags.length && !orTagGroups.length" class="tw-follow-empty">
          <n-spin size="medium" />
          <span>正在获取分类列表...</span>
        </div>
        <template v-else>
          <!-- 分类组内标签视图：显示返回按钮 + 组内标签 -->
          <template v-if="orTagGroupTitle">
            <n-button size="tiny" quaternary type="primary" style="margin-bottom: 8px" @click="$emit('or-tags-index')">← 返回全部分类</n-button>
            <span
              v-for="t in filteredOrTags"
              :key="t.id"
              class="or-tag-chip"
              :title="`点击查看「${t.name}」的视频`"
              @click="pickOrTag(t)"
            >{{ t.name }}</span>
            <div v-if="!filteredOrTags.length" class="or-tags-empty">该分类组内没有匹配的标签</div>
          </template>
          <!-- 总览视图：热门分类组（名称+作品数）+ 全部标签 -->
          <template v-else>
            <span
              v-for="g in filteredOrGroups"
              :key="'g' + g.id"
              class="or-tag-chip or-group-chip"
              :title="`点击查看分类组「${g.name}」内的标签${g.count ? `（共 ${g.count} 部作品）` : ''}`"
              @click="$emit('or-tag-group', g.id)"
            >{{ g.name }}<span v-if="g.count" class="or-chip-count">{{ g.count }}</span></span>
            <span
              v-for="t in filteredOrTags"
              :key="t.id"
              class="or-tag-chip"
              :title="`点击查看「${t.name}」的视频`"
              @click="pickOrTag(t)"
            >{{ t.name }}</span>
            <div v-if="!filteredOrGroups.length && !filteredOrTags.length" class="or-tags-empty">没有匹配的分类</div>
          </template>
        </template>
      </div>
    </n-modal>

    <!-- ASMR 社团/标签/声优索引弹窗：点击进入对应筛选列表 -->
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

    <!-- 解析进度 -->
    <div v-if="inspecting" class="inspect-progress">
      <n-progress
        type="line"
        :percentage="inspectPercentage"
        :indicator-placement="'inside'"
        processing
      />
      <span class="progress-text">
        正在解析文件列表... {{ inspectProgress.current }} / {{ inspectProgress.total }}
      </span>
    </div>

    <!-- 中间内容区 -->
    <div class="content-area">
      <!-- 识图视图：拖拽/选择图片 → 多站点并发识图 → 全部返回后展示结果（占用整个内容区） -->
      <div v-if="reverseActive" class="reverse-view">
        <!-- 拖拽/选择图片 -->
        <div v-if="!(reverseSites || []).length" class="reverse-dropzone" :class="{ 'drop-over': reverseDragOver }"
             @click="reversePickFile()"
             @dragover.prevent="reverseDragOver = true"
             @dragleave.prevent="reverseDragOver = false"
             @drop.prevent="handleReverseDrop">
          <input ref="reverseFileInput" type="file" accept="image/*" style="display: none" @change="handleReversePick" />
          <div class="reverse-dropzone-icon">🖼️</div>
          <div class="reverse-dropzone-title">把图片拖到这里开始识图</div>
          <div class="reverse-dropzone-tip">也可以点击此处选择图片（JPG / PNG / WebP）</div>
          <div class="reverse-dropzone-sites">
            将同时查询：trace.moe · SauceNAO · IQDB · ascii2d · 搜图bot酱 · Google · Yandex · Lenso.ai · Whos.tv<br>
            （全部网站返回后展示结果，失效网站自动移除；Google / Yandex 需在左侧设置代理）
          </div>
        </div>
        <!-- 搜索中：各站进度 -->
        <div v-else-if="reverseRunning" class="reverse-progress">
          <div class="reverse-progress-title">识图中，请稍候...（全部网站返回后自动展示结果）</div>
          <div v-for="s in reverseSites" :key="s.key" class="reverse-progress-item">
            <span class="reverse-progress-name">{{ s.name }}</span>
            <span v-if="s.status === 'running'" class="reverse-progress-running">查询中...</span>
            <span v-else-if="s.status === 'done'" class="reverse-progress-ok">✓ {{ (s.results || []).length }} 条</span>
            <span v-else class="reverse-progress-fail">✕ 失败</span>
          </div>
        </div>
        <!-- 结果展示（全部网站返回后） -->
        <div v-else class="reverse-results">
          <div class="reverse-results-header">
            <span class="reverse-results-title">识图结果（{{ reverseTotalCount }} 条）</span>
            <n-button size="small" quaternary @click="$emit('reverse-reset')">↺ 重新识图</n-button>
          </div>
          <div v-for="s in reverseDoneSites" :key="s.key" class="reverse-site-block">
            <div class="reverse-site-header">
              <span class="reverse-site-name">{{ s.name }}</span>
              <span class="reverse-site-count">{{ (s.results || []).length }} 条结果</span>
              <a v-if="s.url" class="reverse-site-link" href="javascript:void(0)" @click="reverseOpenExternal(s.url)">打开网站 ↗</a>
            </div>
            <div class="reverse-item-list">
              <div v-for="(it, idx) in s.results" :key="idx" class="reverse-item"
                   :class="{ clickable: !!it.url }"
                   @click="it.url && reverseOpenExternal(it.url)">
                <div class="reverse-item-thumb">
                  <img v-if="it.thumbnail" :src="it.thumbnail" loading="lazy" referrerpolicy="no-referrer" />
                  <span v-else class="reverse-item-thumb-empty">无图</span>
                </div>
                <div class="reverse-item-info">
                  <div class="reverse-item-title">{{ it.title || '未知结果' }}</div>
                  <div v-if="it.subtitle" class="reverse-item-subtitle">{{ it.subtitle }}</div>
                  <div class="reverse-item-meta">
                    <n-tag v-if="it.similarity" size="tiny" type="success" round>{{ it.similarity }}</n-tag>
                    <span v-if="it.url" class="reverse-item-url">{{ it.url }}</span>
                  </div>
                </div>
                <div class="reverse-item-actions" @click.stop>
                  <n-button v-if="it.url" size="tiny" quaternary @click="reverseCopyText(it.url)">复制</n-button>
                  <n-button v-if="it.url" size="tiny" quaternary @click="reverseOpenExternal(it.url)">打开</n-button>
                </div>
              </div>
            </div>
          </div>
          <div v-if="!reverseDoneSites.length" class="reverse-empty">
            所有网站均未返回结果（可能图片无匹配、被限流或网络不通；Google / Yandex 请配置代理）
          </div>
        </div>
      </div>
      <!-- 文件列表视图（后台批量收集期间与完成后均不切换：保持当前视图，静默后台下载）；
           EX 内联详情模式下不显示独立文件列表（内容追加在搜索结果下方） -->
      <!-- X 浏览/关注/用户视图优先于文件列表（此前 fileList 有旧数据时
           浏览模式解析结果被文件列表抢占，导致"看不到内容只看到下载数据"） -->
      <div v-else-if="fileList.length > 0 && !(site === 'twitter' && twFollowMode) && !exBatchRunning && !batchFileCollected && !exInlineDetail" class="file-list-area">
        <!-- 列表操作栏 -->
        <div class="list-toolbar">
          <div class="album-info">
            <n-button
              v-if="cameFromSearch || (site === 'exhentai' && exGalleryDetail)"
              size="small"
              quaternary
              type="primary"
              title="清空文件列表返回"
              @click="$emit('back-to-search')"
            >
              <template #icon>
                <n-icon size="16">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M19 12H5M12 19l-7-7 7-7"/>
                  </svg>
                </n-icon>
              </template>
              后退
            </n-button>
            <span class="album-name">{{ albumInfo.album_name || '未知相册' }}</span>
            <n-tag size="small" :type="albumInfo.is_album ? 'info' : 'warning'" round>
              {{ albumInfo.is_album ? '相册' : '单文件' }}
            </n-tag>
            <span class="file-count">共 {{ fileList.length }} 个文件</span>
            <!-- Pawchive：画师内 tag/关键词过滤（本地过滤帖子标题和文件名） -->
            <n-input
              v-if="isPawchiveList"
              :value="localFilter"
              @update:value="localFilter = $event"
              size="small"
              clearable
              placeholder="过滤帖子标题/文件名..."
              class="local-filter"
            >
              <template #prefix>
                <span style="font-size: 12px">🏷️</span>
              </template>
            </n-input>
          </div>
          <div class="list-actions">
            <!-- EX 画廊信息切换：自动解析后保留元数据可见（点开链接自动解析展示） -->
            <n-button
              v-if="site === 'exhentai' && exGalleryDetail"
              size="small"
              quaternary
              :type="showExGalleryInfo ? 'primary' : 'default'"
              :title="showExGalleryInfo ? '收起画廊信息' : '展开画廊信息（上传者/时间/评分/标签）'"
              @click="showExGalleryInfo = !showExGalleryInfo"
            >ℹ️ 画廊信息</n-button>
            <n-button size="small" quaternary @click="selectAll">全选</n-button>
            <n-button size="small" quaternary @click="selectNone">取消全选</n-button>
            <n-button size="small" quaternary @click="invertSelection">反选</n-button>
            <n-button size="small" quaternary @click="selectByType('ok')">仅选可下载</n-button>
            <!-- 显示模式切换：小方格 / 横向详细 -->
            <n-button
              size="small"
              quaternary
              :title="viewMode === 'grid' ? '切换为横向详细列表' : '切换为小方格排列'"
              @click="toggleViewMode"
            >
              <template #icon>
                <n-icon size="16">
                  <svg v-if="viewMode === 'grid'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/>
                    <line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>
                  </svg>
                  <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
                    <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
                  </svg>
                </n-icon>
              </template>
              {{ viewMode === 'grid' ? '列表' : '方格' }}
            </n-button>
          </div>
        </div>

        <!-- EX 画廊信息内联面板（自动解析展示后保留元数据可见，可折叠） -->
        <div
          v-if="site === 'exhentai' && exGalleryDetail && showExGalleryInfo"
          class="ex-inline-info"
        >
          <div class="ex-inline-row">
            <span v-if="exGalleryDetail.uploader" class="ex-inline-field">
              <span class="ex-inline-label">发布者</span>
              <span class="ex-inline-value">{{ exGalleryDetail.uploader }}</span>
            </span>
            <span v-if="exGalleryDetail.posted" class="ex-inline-field">
              <span class="ex-inline-label">时间</span>
              <span class="ex-inline-value">{{ exGalleryDetail.posted }}</span>
            </span>
            <span v-if="exGalleryDetail.language" class="ex-inline-field">
              <span class="ex-inline-label">语言</span>
              <span class="ex-inline-value">{{ exGalleryDetail.language }}</span>
            </span>
            <span v-if="exGalleryDetail.file_size" class="ex-inline-field">
              <span class="ex-inline-label">大小</span>
              <span class="ex-inline-value">{{ exGalleryDetail.file_size }}</span>
            </span>
            <span v-if="exGalleryDetail.length" class="ex-inline-field">
              <span class="ex-inline-label">页数</span>
              <span class="ex-inline-value">{{ exGalleryDetail.length }}</span>
            </span>
            <span v-if="exGalleryDetail.rating" class="ex-inline-field">
              <span class="ex-inline-label">评分</span>
              <span class="ex-inline-value">⭐ {{ exGalleryDetail.rating }}<span v-if="exGalleryDetail.rating_count">（{{ exGalleryDetail.rating_count }}）</span></span>
            </span>
            <span v-if="exGalleryDetail.favorited" class="ex-inline-field">
              <span class="ex-inline-label">收藏</span>
              <span class="ex-inline-value">{{ exGalleryDetail.favorited }}</span>
            </span>
          </div>
          <div v-if="exGalleryDetail.tags && Object.keys(exGalleryDetail.tags).length" class="ex-inline-tags">
            <div v-for="(tags, ns) in exGalleryDetail.tags" :key="ns" class="ex-inline-tagrow">
              <span class="ex-inline-tagrow-ns">{{ ns }}:</span>
              <a
                v-for="t in tags"
                :key="t"
                class="ex-inline-tag"
                title="点击搜索该标签"
                @click="searchTag(`${ns}:${t}`)"
              >{{ t }}</a>
            </div>
          </div>
        </div>

        <!-- 文件表格（横向详细模式） -->
        <n-data-table
          v-if="viewMode === 'list'"
          :columns="columns"
          :data="filteredFileList"
          :row-key="row => row.item_page"
          :row-props="fileRowProps"
          v-model:checked-row-keys="checkedKeys"
          :max-height="tableHeight"
          :scroll-x="700"
          size="small"
          striped
        />

        <!-- 小方格模式：缩略图网格，点击切换选中 -->
        <n-scrollbar v-else class="file-grid-scroll">
          <div class="file-grid">
            <div
              v-for="f in filteredFileList"
              :key="f.item_page"
              class="file-grid-item"
              :class="{ 'grid-selected': checkedKeys.includes(f.item_page), 'grid-bad': f.status === 'error' }"
              :title="`${f.filename}\n${f.size_text || ''}`"
              @click="toggleGridSelect(f.item_page)"
              @contextmenu.prevent="openFileCtxMenu($event, f)"
            >
              <div class="grid-thumb">
                <img v-if="f.thumbnail" :src="f.thumbnail" referrerpolicy="no-referrer" loading="lazy" alt="" />
                <img v-else-if="f.file_icon" :src="f.file_icon" class="grid-icon" alt="" />
                <span v-else class="grid-type">{{ f.file_type || '文件' }}</span>
                <span v-if="f.is_new" class="grid-new">新</span>
                <span v-if="f.is_downloaded" class="grid-downloaded" title="历史任务已下载过（默认不勾选，可手动勾选重下）">已下载</span>
                <span v-if="checkedKeys.includes(f.item_page)" class="grid-check">✓</span>
                <!-- 在线预览/播放按钮（点击弹窗，不与勾选冲突） -->
                <span
                  v-if="f.status !== 'fetch_failed' && (isImageItem(f) || isVideoItem(f))"
                  class="grid-preview-btn"
                  :title="isVideoItem(f) ? '在线播放' : '查看大图'"
                  @click.stop="openPreview(f)"
                >{{ isVideoItem(f) ? '▶' : '👁' }}</span>
              </div>
              <div class="grid-name">{{ f.filename }}</div>
              <div class="grid-size">{{ f.size_text || '—' }}</div>
            </div>
          </div>
        </n-scrollbar>

        <!-- 下载按钮 -->
        <div class="download-bar">
          <div class="selected-info">
            已选择 <span class="selected-count">{{ checkedKeys.length }}</span> 个文件
            <span class="selected-size" v-if="selectedSizeText">({{ selectedSizeText }})</span>
          </div>
          <n-button
            type="primary"
            size="large"
            :disabled="checkedKeys.length === 0"
            :loading="downloading"
            @click="handleDownload"
          >
            {{ downloading ? '下载中...' : `下载选中 (${checkedKeys.length})` }}
          </n-button>
        </div>
      </div>

      <!-- EX 画廊详情视图：完整信息（标题/发布者/时间/父画廊/大小/页数/收藏数/评分）+ 分组标签可点击 + 种子入口 -->
      <!-- 文件列表加载完成后自动隐藏（让位给文件列表视图，点击"后退"可回到此处）；
           内联详情模式下不显示独立详情视图（内容追加在搜索结果下方） -->
      <div v-else-if="site === 'exhentai' && (exGalleryDetail || exDetailLoading) && fileList.length === 0 && !exInlineDetail" class="ex-detail">
        <div class="ex-detail-toolbar">
          <n-button size="small" quaternary type="primary" @click="$emit('ex-close-detail')">← 后退</n-button>
          <span class="ex-detail-toolbar-title">画廊详情</span>
        </div>
        <n-scrollbar class="ex-detail-scroll">
          <div v-if="exDetailLoading && !exGalleryDetail" class="ex-detail-loading">
            <n-spin size="medium" />
            <span>正在获取画廊信息...</span>
          </div>
          <template v-else-if="exGalleryDetail">
            <div class="ex-detail-head">
              <div class="ex-detail-cover">
                <img
                  v-if="exGalleryDetail.thumbnail"
                  :src="exGalleryDetail.thumbnail"
                  referrerpolicy="no-referrer"
                  :alt="exGalleryDetail.title"
                />
                <span v-else class="ex-thumb-empty">EX</span>
              </div>
              <div class="ex-detail-info">
                <div class="ex-detail-name" :title="exGalleryDetail.title">{{ exGalleryDetail.title }}</div>
                <div
                  v-if="exGalleryDetail.title_jp && exGalleryDetail.title_jp !== exGalleryDetail.title"
                  class="ex-detail-name-jp"
                >{{ exGalleryDetail.title_jp }}</div>
                <table class="ex-detail-meta">
                  <tr v-if="exGalleryDetail.uploader"><td>发布者</td><td>{{ exGalleryDetail.uploader }}</td></tr>
                  <tr v-if="exGalleryDetail.posted"><td>发布时间</td><td>{{ exGalleryDetail.posted }}</td></tr>
                  <tr v-if="exGalleryDetail.parent">
                    <td>父画廊</td>
                    <td>
                      <a class="ex-detail-link" title="点击查看父画廊" @click="$emit('ex-open-gallery', exGalleryDetail.parent)">{{ exGalleryDetail.parent }}</a>
                    </td>
                  </tr>
                  <tr v-if="exGalleryDetail.visible"><td>可见性</td><td>{{ exGalleryDetail.visible }}</td></tr>
                  <tr v-if="exGalleryDetail.language"><td>语言</td><td>{{ exGalleryDetail.language }}</td></tr>
                  <tr v-if="exGalleryDetail.file_size"><td>文件大小</td><td>{{ exGalleryDetail.file_size }}</td></tr>
                  <tr v-if="exGalleryDetail.length"><td>页数</td><td>{{ exGalleryDetail.length }}</td></tr>
                  <tr v-if="exGalleryDetail.favorited"><td>收藏数</td><td>{{ exGalleryDetail.favorited }}</td></tr>
                  <tr v-if="exGalleryDetail.rating">
                    <td>评分</td>
                    <td>⭐ {{ exGalleryDetail.rating }}<span v-if="exGalleryDetail.rating_count">（{{ exGalleryDetail.rating_count }} 人评分）</span></td>
                  </tr>
                </table>
                <div class="ex-detail-actions">
                  <n-button
                    size="small"
                    type="primary"
                    title="解析画廊全部图片并进入文件列表"
                    @click="$emit('open-album', { album_url: exGalleryDetail.url, album_name: exGalleryDetail.title })"
                  >解析图片列表</n-button>
                  <n-button
                    size="small"
                    type="warning"
                    ghost
                    :loading="torrentLoading"
                    title="查看画廊附带的种子（可获取磁力或保存种子文件）"
                    @click="exDetailTorrents(exGalleryDetail.url)"
                  >种子 / 磁力</n-button>
                </div>
              </div>
            </div>
            <!-- 分组标签（female:/male:/mixed:/artist:/group:...，点击按命名空间搜索，与原版一致） -->
            <div class="ex-detail-tags">
              <div v-for="(tags, ns) in exGalleryDetail.tags" :key="ns" class="ex-detail-tagrow">
                <span class="ex-detail-tagrow-ns">{{ ns }}:</span>
                <a
                  v-for="t in tags"
                  :key="t"
                  class="ex-detail-tag"
                  title="点击搜索该标签"
                  @click="searchTag(`${ns}:${t}`)"
                >{{ t }}</a>
              </div>
              <div v-if="!exGalleryDetail.tags || Object.keys(exGalleryDetail.tags).length === 0" class="ex-detail-notags">
                无标签
              </div>
            </div>
          </template>
        </n-scrollbar>
      </div>

      <!-- PA 帖子详情视图：完整信息（标题/画师/时间/正文/标签）+ 附件预览 + 下载入口 -->
      <div v-else-if="site === 'pawchive' && (paPostDetail || paDetailLoading)" class="ex-detail">
        <div class="ex-detail-toolbar">
          <n-button size="small" quaternary type="primary" @click="$emit('pa-close-detail')">← 后退</n-button>
          <span class="ex-detail-toolbar-title">帖子详情</span>
        </div>
        <n-scrollbar class="ex-detail-scroll">
          <div v-if="paDetailLoading && !paPostDetail" class="ex-detail-loading">
            <n-spin size="medium" />
            <span>正在获取帖子信息...</span>
          </div>
          <template v-else-if="paPostDetail">
            <div class="ex-detail-head">
              <div class="ex-detail-cover" v-if="paPostDetail.previews && paPostDetail.previews.length">
                <img
                  :src="paPostDetail.previews[0].thumbnail"
                  referrerpolicy="no-referrer"
                  :alt="paPostDetail.title"
                />
              </div>
              <div class="ex-detail-info">
                <div class="ex-detail-name" :title="paPostDetail.title">{{ paPostDetail.title }}</div>
                <table class="ex-detail-meta">
                  <tr>
                    <td>画师</td>
                    <td>
                      <a class="ex-detail-link" title="点击解析画师全部内容" @click="$emit('open-album', { album_url: paPostDetail.artist_url, album_name: paPostDetail.artist })">{{ paPostDetail.artist }}</a>
                    </td>
                  </tr>
                  <tr v-if="paPostDetail.posted"><td>发布时间</td><td>{{ paPostDetail.posted }}</td></tr>
                  <tr v-if="paPostDetail.previews"><td>文件数</td><td>{{ paPostDetail.previews.length }} 个附件</td></tr>
                </table>
                <div class="ex-detail-actions">
                  <n-button
                    size="small"
                    type="primary"
                    title="解析帖子全部文件并进入文件列表"
                    @click="$emit('open-album', { album_url: paPostDetail.url, album_name: paPostDetail.title })"
                  >解析下载列表</n-button>
                </div>
              </div>
            </div>
            <!-- 标签（可点击 → 标签搜索） -->
            <div class="ex-detail-tags" v-if="paPostDetail.tags && paPostDetail.tags.length">
              <div class="ex-detail-tagrow">
                <span class="ex-detail-tagrow-ns">标签:</span>
                <a
                  v-for="t in paPostDetail.tags"
                  :key="t"
                  class="ex-detail-tag"
                  title="点击搜索该标签"
                  @click="searchTag(t)"
                >{{ t }}</a>
              </div>
            </div>
            <!-- 正文 -->
            <div class="pa-detail-content" v-if="paPostDetail.content">{{ paPostDetail.content }}</div>
            <!-- 附件预览网格 -->
            <div class="pa-detail-previews" v-if="paPostDetail.previews && paPostDetail.previews.length > 1">
              <div class="pa-detail-previews-title">全部附件（{{ paPostDetail.previews.length }}）</div>
              <div class="pa-detail-grid">
                <div
                  v-for="(p, i) in paPostDetail.previews"
                  :key="i"
                  class="pa-detail-cell"
                  :title="p.name"
                >
                  <img
                    :src="p.thumbnail"
                    loading="lazy"
                    referrerpolicy="no-referrer"
                    :alt="p.name"
                    @error="e => e.target.style.display = 'none'"
                  />
                  <div class="pa-detail-cell-name">{{ p.name }}</div>
                </div>
              </div>
            </div>
          </template>
        </n-scrollbar>
      </div>

      <!-- PA 画师子项目视图：点开画师后按发布日期展示全部帖子（文件/链接/视频/图片/压缩包） -->
      <div v-else-if="site === 'pawchive' && (paArtistPosts || paArtistPostsLoading)" class="ex-detail">
        <div class="ex-detail-toolbar">
          <n-button size="small" quaternary type="primary" @click="$emit('pa-close-artist')">← 后退</n-button>
          <span class="ex-detail-toolbar-title">画师子项目</span>
          <n-button
            size="tiny"
            quaternary
            :loading="paArtistPostsLoading"
            title="重新拉取最新帖子列表"
            @click="$emit('pa-open-artist', paArtistPosts?.url)"
          >刷新</n-button>
          <n-button
            size="tiny"
            type="primary"
            ghost
            title="解析画师全部帖子的文件并进入下载列表"
            @click="$emit('open-album', { album_url: paArtistPosts?.url, album_name: paArtistPosts?.artist })"
          >批量解析全部</n-button>
        </div>
        <n-scrollbar class="ex-detail-scroll">
          <div v-if="paArtistPostsLoading && !paArtistPosts" class="ex-detail-loading">
            <n-spin size="medium" />
            <span>正在获取画师帖子列表...</span>
          </div>
          <template v-else-if="paArtistPosts">
            <div class="pa-artist-head">
              <span class="pa-artist-name" :title="paArtistPosts.artist">{{ paArtistPosts.artist }}</span>
              <span class="pa-artist-count">共 {{ paArtistPosts.posts.length }} 个帖子</span>
              <span v-if="paArtistPosts.cached" class="pa-artist-cached">缓存数据（点"刷新"更新）</span>
            </div>
            <div
              v-for="p in paArtistPosts.posts"
              :key="p.post_id"
              class="pa-post-row"
              :title="paPostTooltip(p)"
              @click="$emit('pa-open-post', p.post_url)"
            >
              <div class="pa-post-thumb">
                <img
                  v-if="p.thumbnail"
                  :src="p.thumbnail"
                  loading="lazy"
                  referrerpolicy="no-referrer"
                  :alt="p.title"
                  @error="e => e.target.style.display = 'none'"
                />
                <span v-else class="pa-post-thumb-empty">帖</span>
              </div>
              <div class="pa-post-info">
                <div class="pa-post-title">{{ p.title }}</div>
                <div class="pa-post-meta">
                  <span class="pa-post-date">{{ (p.published || '').slice(0, 10) }}</span>
                  <span class="pa-post-files">{{ p.file_count }} 个文件</span>
                  <span v-if="p.has_video" class="pa-post-badge pa-post-badge-video">视频</span>
                  <span v-if="p.has_archive" class="pa-post-badge pa-post-badge-zip">压缩包</span>
                </div>
                <div v-if="p.content" class="pa-post-content">{{ p.content }}</div>
              </div>
            </div>
            <div v-if="!paArtistPosts.posts.length" class="pa-artist-empty">该画师没有帖子</div>
          </template>
        </n-scrollbar>
      </div>

      <!-- X 浏览模式：关注博主的最近媒体更新（缓存先显示，重新点击后台刷新） -->
      <div v-else-if="site === 'twitter' && twFollowMode === 'browse'" class="tw-follow-view">
        <div class="tw-follow-toolbar">
          <n-button size="small" quaternary type="primary" @click="$emit('tw-back')">← 返回</n-button>
          <span class="tw-follow-title">最近博主更新</span>
          <span v-if="twBrowseUpdatedAt" class="tw-follow-count">
            更新于 {{ formatTwTime(twBrowseUpdatedAt) }}
          </span>
          <n-button
            size="tiny"
            quaternary
            :loading="twBrowseLoading"
            @click="$emit('tw-browse')"
          >刷新</n-button>
        </div>
        <div v-if="twBrowseLoading && twBrowseProgress.total" class="tw-browse-progress">
          <n-progress
            type="line"
            :percentage="Math.min(100, Math.round(twBrowseProgress.done / twBrowseProgress.total * 100))"
            :indicator-placement="'inside'"
            processing
          />
          <span class="progress-text">正在拉取博主动态 {{ twBrowseProgress.done }} / {{ twBrowseProgress.total }} ...</span>
        </div>
        <n-scrollbar class="tw-follow-scroll">
          <div v-if="twBrowseError && twBrowseFeed.length === 0" class="tw-follow-error">{{ twBrowseError }}</div>
          <div v-else-if="!twBrowseLoading && twBrowseFeed.length === 0" class="tw-follow-empty">
            <n-spin v-if="false" size="medium" />
            <span>暂无更新数据，点上方"刷新"拉取关注博主的最近动态</span>
          </div>
          <div
            v-for="t in twBrowseFeed"
            :key="t.tweet_id"
            class="tw-tweet-card"
            title="点击解析这条推文的媒体"
            @click="$emit('open-album', { album_name: `${t.user?.name || t.user?.screen_name} 的推文`, album_url: t.item_page, site: 'twitter' })"
          >
            <div class="tw-tweet-head" @click.stop="$emit('tw-open-user', t.user)">
              <div class="tw-user-avatar tw-tweet-avatar">
                <img v-if="t.user?.thumbnail" :src="t.user.thumbnail" referrerpolicy="no-referrer" :alt="t.user?.screen_name" />
                <span v-else class="tw-avatar-empty">@</span>
              </div>
              <div class="tw-tweet-user">
                <span class="tw-user-nick">{{ t.user?.name || t.user?.screen_name }}</span>
                <span class="tw-user-handle">@{{ t.user?.screen_name }}</span>
              </div>
              <span v-if="t.post_date" class="tw-tweet-time">{{ t.post_date }}</span>
            </div>
            <div v-if="t.text" class="tw-tweet-text">{{ t.text }}</div>
            <div v-if="t.media?.length" class="tw-tweet-media">
              <div
                v-for="m in t.media.slice(0, 4)"
                :key="m.media_url"
                class="tw-tweet-thumb"
                :class="{ 'tw-tweet-video': m.type === 'video' }"
              >
                <img v-if="m.thumbnail" :src="m.thumbnail" referrerpolicy="no-referrer" loading="lazy" alt="" />
                <span v-if="m.type === 'video'" class="tw-tweet-play">▶</span>
              </div>
              <span v-if="t.media.length > 4" class="tw-tweet-more">+{{ t.media.length - 4 }}</span>
            </div>
          </div>
          <!-- 点击继续更新：加载下一批关注博主动态 -->
          <div v-if="twBrowseFeed.length" class="tw-browse-more">
            <n-button
              v-if="twBrowseHasMore"
              size="small"
              block
              secondary
              :loading="twBrowseLoading"
              @click="$emit('tw-browse-more')"
            >↓ 点击继续更新（下一批博主）</n-button>
            <div v-else class="tw-browse-end">已加载全部关注博主的动态</div>
          </div>
        </n-scrollbar>
      </div>

      <!-- X 本地搜索结果：用户卡片 + 推文卡片（搜缓存内容） -->
      <div v-else-if="site === 'twitter' && twFollowMode === 'search'" class="tw-follow-view">
        <div class="tw-follow-toolbar">
          <n-button size="small" quaternary type="primary" @click="$emit('update:tw-local-search', '')">← 返回</n-button>
          <span class="tw-follow-title">搜索缓存：{{ twLocalSearch }}</span>
          <span class="tw-follow-count">
            {{ twFollowItems.length + twSearchTweets.length }} 条结果（用户 {{ twFollowItems.length }} / 动态 {{ twSearchTweets.length }}）
          </span>
        </div>
        <n-scrollbar class="tw-follow-scroll">
          <div v-if="twFollowItems.length === 0 && twSearchTweets.length === 0" class="tw-follow-empty">
            没有匹配的缓存内容，试试先打开"关注列表"或"浏览模式"载入数据后再搜
          </div>
          <!-- 用户结果 -->
          <div
            v-for="u in twFollowItems"
            :key="'u-' + u.user_id"
            class="tw-user-card"
            title="点击查看 TA 的主页（关注/粉丝列表 + 全部媒体）"
            @click="$emit('tw-open-user', u)"
          >
            <div class="tw-user-avatar">
              <img v-if="u.thumbnail" :src="u.thumbnail" referrerpolicy="no-referrer" :alt="u.screen_name" />
              <span v-else class="tw-avatar-empty">@</span>
            </div>
            <div class="tw-user-info">
              <div class="tw-user-name">
                <span class="tw-user-nick">{{ u.name || u.screen_name }}</span>
                <span v-if="u.verified" class="tw-verified" title="认证账号">✔</span>
                <span class="tw-user-handle">@{{ u.screen_name }}</span>
                <n-tag v-if="u.follow_tag || u.tag" size="tiny" type="info" round>{{ u.follow_tag || u.tag }}</n-tag>
              </div>
              <div v-if="u.description" class="tw-user-desc" :title="u.description">{{ u.description }}</div>
            </div>
            <div class="tw-user-actions" @click.stop>
              <n-button size="tiny" quaternary title="解析该用户的全部媒体" @click="$emit('open-album', u)">媒体</n-button>
              <n-button size="tiny" tertiary @click="twOpenTagModal(u)">分类</n-button>
            </div>
          </div>
          <!-- 推文结果 -->
          <div
            v-for="t in twSearchTweets"
            :key="'t-' + t.tweet_id"
            class="tw-tweet-card"
            title="点击解析这条推文的媒体"
            @click="$emit('open-album', { album_name: `${t.user?.name || t.user?.screen_name} 的推文`, album_url: t.item_page, site: 'twitter' })"
          >
            <div class="tw-tweet-head" @click.stop="$emit('tw-open-user', t.user)">
              <div class="tw-user-avatar tw-tweet-avatar">
                <img v-if="t.user?.thumbnail" :src="t.user.thumbnail" referrerpolicy="no-referrer" :alt="t.user?.screen_name" />
                <span v-else class="tw-avatar-empty">@</span>
              </div>
              <div class="tw-tweet-user">
                <span class="tw-user-nick">{{ t.user?.name || t.user?.screen_name }}</span>
                <span class="tw-user-handle">@{{ t.user?.screen_name }}</span>
              </div>
              <span v-if="t.post_date" class="tw-tweet-time">{{ t.post_date }}</span>
            </div>
            <div v-if="t.text" class="tw-tweet-text">{{ t.text }}</div>
            <div v-if="t.media?.length" class="tw-tweet-media">
              <div
                v-for="m in t.media.slice(0, 4)"
                :key="m.media_url"
                class="tw-tweet-thumb"
                :class="{ 'tw-tweet-video': m.type === 'video' }"
              >
                <img v-if="m.thumbnail" :src="m.thumbnail" referrerpolicy="no-referrer" loading="lazy" alt="" />
                <span v-if="m.type === 'video'" class="tw-tweet-play">▶</span>
              </div>
            </div>
          </div>
        </n-scrollbar>
      </div>

      <!-- X 用户详情：点开关注的人，查看 TA 的关注/粉丝列表 + 解析媒体 -->
      <div v-else-if="site === 'twitter' && twFollowMode === 'user' && twViewUser" class="tw-follow-view">
        <div class="tw-follow-toolbar">
          <n-button size="small" quaternary type="primary" @click="$emit('tw-back')">← 返回</n-button>
          <span class="tw-follow-title">用户主页</span>
        </div>
        <n-scrollbar class="tw-follow-scroll">
          <div class="tw-profile-card">
            <div class="tw-user-avatar tw-profile-avatar">
              <img v-if="twViewUser.thumbnail" :src="twViewUser.thumbnail" referrerpolicy="no-referrer" :alt="twViewUser.screen_name" />
              <span v-else class="tw-avatar-empty">@</span>
            </div>
            <div class="tw-user-info">
              <div class="tw-user-name">
                <span class="tw-user-nick">{{ twViewUser.name || twViewUser.screen_name }}</span>
                <span v-if="twViewUser.verified" class="tw-verified" title="认证账号">✔</span>
                <span class="tw-user-handle">@{{ twViewUser.screen_name }}</span>
                <n-tag v-if="twViewUser.follow_tag || twViewUser.tag" size="tiny" type="info" round>{{ twViewUser.follow_tag || twViewUser.tag }}</n-tag>
              </div>
              <div v-if="twViewUser.description" class="tw-user-desc">{{ twViewUser.description }}</div>
              <div v-if="twViewUser.followers_count != null" class="tw-user-stats">
                <span>关注 {{ formatCount(twViewUser.friends_count) }}</span>
                <span>粉丝 {{ formatCount(twViewUser.followers_count) }}</span>
                <span>推文 {{ formatCount(twViewUser.statuses_count) }}</span>
              </div>
            </div>
          </div>
          <div class="tw-profile-actions">
            <n-button
              size="small"
              secondary
              type="primary"
              @click="$emit('open-album', twViewUser)"
            >解析 TA 的全部媒体</n-button>
            <n-button
              size="small"
              @click="$emit('tw-user-list', 'following', twViewUser.screen_name)"
            >TA 的关注</n-button>
            <n-button
              size="small"
              @click="$emit('tw-user-list', 'followers', twViewUser.screen_name)"
            >关注 TA 的人</n-button>
            <n-button
              size="small"
              tertiary
              :title="(twViewUser.follow_tag || twViewUser.tag) ? `已归类：${twViewUser.follow_tag || twViewUser.tag}，点击修改` : '归类到母类/子类文件夹'"
              @click="twOpenTagModal(twViewUser)"
            >{{ (twViewUser.follow_tag || twViewUser.tag) ? '改分类' : '分类' }}</n-button>
            <n-button
              size="small"
              ghost
              :type="twViewUser.following ? 'error' : 'primary'"
              @click="$emit(twViewUser.following ? 'tw-unfollow' : 'tw-follow', twViewUser)"
            >{{ twViewUser.following ? '取消关注' : '关注' }}</n-button>
          </div>

          <!-- 博主内容流：点开博主自动解析，内容卡片直接展示在下方（可查看、可一键下载） -->
          <div class="tw-user-feed-bar">
            <n-button
              size="small"
              secondary
              type="primary"
              :disabled="!twUserFeed.length"
              :title="'把下方已加载内容的全部媒体（' + twUserFeedMediaCount + ' 个文件）加入下载任务'"
              @click="$emit('tw-user-feed-download-all')"
            >⬇ 下载当前全部媒体 ({{ twUserFeedMediaCount }})</n-button>
            <n-button
              v-if="twUserFeedHasMore || twUserFeed.length"
              size="small"
              quaternary
              :loading="twUserFeedLoading"
              @click="$emit('tw-user-feed-more')"
            >{{ twUserFeedHasMore ? '加载更多' : '刷新加载' }}</n-button>
          </div>
          <div v-if="twUserFeedLoading && twUserFeed.length === 0" class="tw-user-feed-loading">
            <n-spin size="medium" />
            <span>正在解析博主内容...</span>
          </div>
          <div v-else-if="!twUserFeedLoading && twUserFeed.length === 0" class="tw-follow-empty">
            未获取到内容（博主可能没有图片/视频，或网络/代理异常，点"刷新加载"重试）
          </div>
          <div
            v-for="t in twUserFeed"
            :key="t.tweet_id"
            class="tw-tweet-card"
            title="点击解析这条推文的媒体并勾选下载"
            @click="$emit('open-album', { album_name: `${twViewUser.name || twViewUser.screen_name} 的推文`, album_url: t.item_page, site: 'twitter' })"
          >
            <div class="tw-tweet-head">
              <div class="tw-tweet-user">
                <span class="tw-user-nick">{{ twViewUser.name || twViewUser.screen_name }}</span>
                <span class="tw-user-handle">@{{ twViewUser.screen_name }}</span>
              </div>
              <span v-if="t.post_date" class="tw-tweet-time">{{ t.post_date }}</span>
            </div>
            <div v-if="t.text" class="tw-tweet-text">{{ t.text }}</div>
            <div v-if="t.media?.length" class="tw-tweet-media">
              <div
                v-for="m in t.media.slice(0, 4)"
                :key="m.media_url"
                class="tw-tweet-thumb"
                :class="{ 'tw-tweet-video': m.type === 'video' }"
              >
                <img v-if="m.thumbnail" :src="m.thumbnail" referrerpolicy="no-referrer" loading="lazy" alt="" />
                <span v-if="m.type === 'video'" class="tw-tweet-play">▶</span>
              </div>
              <span v-if="t.media.length > 4" class="tw-tweet-more">+{{ t.media.length - 4 }}</span>
            </div>
          </div>
          <div v-if="twUserFeed.length" class="tw-browse-more">
            <n-button
              v-if="twUserFeedHasMore"
              size="small"
              block
              secondary
              :loading="twUserFeedLoading"
              @click="$emit('tw-user-feed-more')"
            >↓ 加载更多内容</n-button>
            <div v-else class="tw-browse-end">已加载全部内容（已翻到时间线底部）</div>
          </div>
        </n-scrollbar>
      </div>

      <!-- X 关注视图：关注列表 / 关注我的人 / 我的分类（点用户查看 TA 的主页） -->
      <div v-else-if="site === 'twitter' && twFollowMode" class="tw-follow-view">
        <div class="tw-follow-toolbar">
          <n-button size="small" quaternary type="primary" @click="$emit('tw-back')">← 返回</n-button>
          <span class="tw-follow-title">
            {{ twFollowLabel || (twFollowMode === 'follows' ? '我的分类（已归类的关注）' : (twFollowMode === 'followers' ? '关注我的人' : '关注列表')) }}
          </span>
          <span v-if="twFollowItems.length" class="tw-follow-count">
            {{ followSearch ? `${filteredFollowItems.length}/${twFollowItems.length}` : twFollowItems.length }} 人<template v-if="twFollowHasMore">（可继续加载）</template>
          </span>
          <!-- 本地搜索：快速检索已缓存的关注/粉丝（昵称 / @推特号 / 简介 / 分类） -->
          <n-input
            v-model:value="followSearch"
            size="tiny"
            clearable
            round
            placeholder="🔍 搜本地缓存：昵称 / @推特号"
            class="tw-follow-search"
          />
          <n-button
            v-if="twFollowMode !== 'follows' && twFollowHasMore"
            size="tiny"
            :loading="twFollowLoading"
            @click="$emit('tw-follow-load-more')"
          >加载更多</n-button>
          <n-button
            v-if="twFollowMode === 'follows'"
            size="tiny"
            quaternary
            :loading="twFollowLoading"
            @click="$emit('tw-follow-list', 'follows')"
          >刷新</n-button>
        </div>
        <n-scrollbar class="tw-follow-scroll">
          <div v-if="twFollowError" class="tw-follow-error">{{ twFollowError }}</div>
          <div v-else-if="twFollowLoading && twFollowItems.length === 0" class="tw-follow-empty">
            <n-spin size="medium" />
            <span>正在获取列表...</span>
          </div>
          <div v-else-if="twFollowItems.length === 0" class="tw-follow-empty">
            {{ twFollowMode === 'follows' ? '还没有归类任何关注，去"关注列表"给用户点"分类"吧' : '暂无数据' }}
          </div>
          <div v-else-if="filteredFollowItems.length === 0" class="tw-follow-empty">
            没有匹配「{{ followSearch }}」的人（试试加载更多，或清空搜索）
          </div>
          <div
            v-for="u in filteredFollowItems"
            :key="u.user_id"
            class="tw-user-card"
            title="点击查看 TA 的主页（关注/粉丝列表 + 全部媒体）"
            @click="$emit('tw-open-user', u)"
          >
            <div class="tw-user-avatar">
              <img v-if="u.thumbnail" :src="u.thumbnail" referrerpolicy="no-referrer" :alt="u.screen_name" />
              <span v-else class="tw-avatar-empty">@</span>
            </div>
            <div class="tw-user-info">
              <div class="tw-user-name">
                <span class="tw-user-nick">{{ u.name || u.screen_name }}</span>
                <span v-if="u.verified" class="tw-verified" title="认证账号">✔</span>
                <span class="tw-user-handle">@{{ u.screen_name }}</span>
                <n-tag v-if="u.follow_tag || u.tag" size="tiny" type="info" round>{{ u.follow_tag || u.tag }}</n-tag>
              </div>
              <div v-if="u.description" class="tw-user-desc" :title="u.description">{{ u.description }}</div>
              <div v-if="u.followers_count != null" class="tw-user-stats">
                <span>关注 {{ formatCount(u.friends_count) }}</span>
                <span>粉丝 {{ formatCount(u.followers_count) }}</span>
                <span>推文 {{ formatCount(u.statuses_count) }}</span>
              </div>
            </div>
            <div class="tw-user-actions" @click.stop>
              <n-button
                size="tiny"
                quaternary
                title="解析该用户的全部媒体"
                @click="$emit('open-album', u)"
              >媒体</n-button>
              <n-button
                size="tiny"
                tertiary
                :title="(u.follow_tag || u.tag) ? `已归类：${u.follow_tag || u.tag}，点击修改` : '归类到母类/子类文件夹'"
                @click="twOpenTagModal(u)"
              >{{ (u.follow_tag || u.tag) ? '改分类' : '分类' }}</n-button>
              <n-button
                v-if="twFollowMode !== 'follows'"
                size="tiny"
                ghost
                :type="u.following ? 'error' : 'primary'"
                @click="$emit(u.following ? 'tw-unfollow' : 'tw-follow', u)"
              >{{ u.following ? '取消关注' : '关注' }}</n-button>
            </div>
          </div>
        </n-scrollbar>
      </div>

      <!-- Iwara 视频详情页：视频播放 + 标题 / 作者（关注）/ 简介 / tags / 评论 -->
      <div v-else-if="site === 'iwara' && iwView === 'detail'" class="iw-detail">
        <div v-if="iwDetailLoading && !iwDetail" class="tw-follow-empty">
          <n-spin size="medium" />
          <span>正在获取视频详情...</span>
        </div>
        <template v-else-if="iwDetail">
          <div class="tw-follow-toolbar">
            <n-button size="small" quaternary type="primary" @click="$emit('iw-detail-back')">← 返回</n-button>
            <span class="tw-follow-title iw-detail-title" :title="iwDetail.album_name">{{ iwDetail.album_name }}</span>
            <n-button
              size="tiny"
              tertiary
              type="primary"
              title="解析视频文件并加入下载列表"
              @click="$emit('open-album', iwDetail)"
            >解析下载</n-button>
          </div>
          <n-scrollbar class="iw-detail-scroll">
            <div class="iw-video-area">
              <!-- 视频走本地媒体代理（带登录态/代理设置，国内直连 files.iwara.tv 不稳） -->
              <video
                v-if="iwDetail.video_url"
                :src="proxied(iwDetail.video_url)"
                controls
                preload="metadata"
                :poster="iwDetail.thumbnail"
              />
              <img v-else :src="iwDetail.thumbnail" referrerpolicy="no-referrer" :alt="iwDetail.album_name" />
            </div>
            <div class="iw-detail-stats">
              <span>👁 {{ formatCount(iwDetail.views) }}</span>
              <span>♥ {{ formatCount(iwDetail.likes) }}</span>
              <span>💬 {{ formatCount(iwDetail.num_comments) }}</span>
              <span>{{ iwTimeAgo(iwDetail.created_at) || iwDetail.post_date }}</span>
              <n-tag v-if="iwDetail.rating === 'r18'" size="tiny" type="error" round>R-18</n-tag>
              <n-tag v-else-if="iwDetail.rating === 'ecchi'" size="tiny" type="warning" round>Ecchi</n-tag>
              <span v-if="iwDuration(iwDetail.duration)">⏱ {{ iwDuration(iwDetail.duration) }}</span>
            </div>
            <!-- 作者行：头像/昵称可点击进主页，右侧关注按钮 -->
            <div class="iw-author-row">
              <img
                v-if="iwDetail.author_avatar"
                class="iw-author-avatar"
                :src="iwDetail.author_avatar"
                referrerpolicy="no-referrer"
                title="查看作者主页"
                @click="$emit('iw-open-user', iwDetail.author_username)"
              />
              <span v-else class="iw-author-avatar iw-author-avatar-empty" title="查看作者主页" @click="$emit('iw-open-user', iwDetail.author_username)">@</span>
              <span class="iw-author-name" title="查看作者主页" @click="$emit('iw-open-user', iwDetail.author_username)">
                {{ iwDetail.author || '未知作者' }}<template v-if="iwDetail.author_username">（@{{ iwDetail.author_username }}）</template>
              </span>
              <n-button
                size="tiny"
                ghost
                :type="iwDetail.author_following ? 'error' : 'primary'"
                @click="$emit(iwDetail.author_following ? 'iw-unfollow' : 'iw-follow', iwDetail)"
              >{{ iwDetail.author_following ? '取消关注' : '关注' }}</n-button>
            </div>
            <div v-if="iwDetail.body" class="iw-body">{{ iwDetail.body }}</div>
            <div v-if="iwDetail.tags && iwDetail.tags.length" class="iw-tags">
              <n-tag
                v-for="t in iwDetail.tags"
                :key="t.id"
                size="small"
                round
                :type="t.sensitive ? 'error' : 'info'"
                class="iw-tag"
                title="点击搜索该标签"
                @click="$emit('iw-search-tag', t.name)"
              >{{ t.name }}</n-tag>
            </div>
            <!-- 评论区 -->
            <div class="iw-comments-title">评论<template v-if="iwComments.length">（{{ iwComments.length }}{{ iwCommentsHasMore ? '+' : '' }}）</template></div>
            <div v-if="!iwComments.length" class="iw-comments-empty">暂无评论</div>
            <div v-for="c in iwComments" :key="c.id" class="iw-comment">
              <img
                v-if="c.user && c.user.thumbnail"
                class="iw-comment-avatar"
                :src="c.user.thumbnail"
                referrerpolicy="no-referrer"
                title="查看评论者主页"
                @click="$emit('iw-open-user', c.user.username)"
              />
              <span v-else class="iw-comment-avatar iw-comment-avatar-empty" title="查看评论者主页" @click="$emit('iw-open-user', c.user && c.user.username)">@</span>
              <div class="iw-comment-main">
                <div class="iw-comment-head">
                  <span class="iw-comment-name" title="查看评论者主页" @click="$emit('iw-open-user', c.user.username)">{{ (c.user && c.user.name) || (c.user && c.user.username) || '匿名' }}</span>
                  <span class="iw-comment-time">{{ iwTimeAgo(c.created_at) }}</span>
                </div>
                <div class="iw-comment-body">{{ c.body }}</div>
              </div>
            </div>
            <div v-if="iwCommentsHasMore" class="iw-comments-more">
              <n-button size="small" quaternary :loading="iwDetailLoading" @click="$emit('iw-comments-more')">加载更多评论</n-button>
            </div>
          </n-scrollbar>
        </template>
      </div>

      <!-- Iwara 主页：最近更新（缩略图 + 播放/爱心/R-18/时长 + 标题 + 作者/时间） -->
      <div v-else-if="site === 'iwara' && iwView === 'home'" class="tw-follow-view">
        <div class="tw-follow-toolbar">
          <span class="tw-follow-title">{{ iwSite === 'ai' ? 'AI 站 (iwara.ai)' : 'IW 站 (iwara.tv)' }} · {{ iwHomeMode === 'subscribed' ? '我关注的更新（订阅）' : '最近更新' }}</span>
          <span v-if="iwHomeItems.length" class="tw-follow-count">
            {{ iwHomeItems.length }} 个视频<template v-if="iwHomeHasMore">（可继续加载）</template>
          </span>
          <n-button
            size="tiny"
            quaternary
            :loading="iwHomeLoading"
            @click="iwHomeMode === 'subscribed' ? $emit('iw-subscribed') : $emit('iw-home', 1)"
          >刷新</n-button>
        </div>
        <n-scrollbar class="tw-follow-scroll">
          <div v-if="iwHomeError" class="tw-follow-error">{{ iwHomeError }}</div>
          <div v-else-if="iwHomeLoading && !iwHomeItems.length" class="tw-follow-empty">
            <n-spin size="medium" />
            <span>正在获取主页内容...</span>
          </div>
          <div v-else-if="!iwHomeItems.length" class="tw-follow-empty">暂无内容</div>
          <div v-else class="search-grid">
            <div
              v-for="item in iwHomeItems"
              :key="item.video_id || item.album_url"
              class="search-card iw-card"
              :class="{ 'iw-batch-checked': iwBatchMode && iwBatchChecked.has(item.video_id) }"
              :title="`${item.album_name}\n作者: ${item.author || '未知'}\n${iwBatchMode ? '点击勾选/取消勾选' : '点击查看完整信息'}`"
              @click="iwBatchMode ? toggleIwBatchItem(item.video_id) : $emit('iw-open-detail', item)"
            >
              <div class="thumb-wrapper">
                <img :src="item.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name" />
                <span v-if="iwDuration(item.duration)" class="iw-thumb-duration">{{ iwDuration(item.duration) }}</span>
                <span v-if="item.rating === 'r18'" class="iw-thumb-r18">R-18</span>
                <span v-else-if="item.rating === 'ecchi'" class="iw-thumb-ecchi">Ecchi</span>
                <div class="iw-thumb-stats">
                  <span v-if="item.views != null">👁 {{ formatCount(item.views) }}</span>
                  <span v-if="item.likes != null">♥ {{ formatCount(item.likes) }}</span>
                </div>
                <span v-if="iwBatchMode" class="iw-batch-check" :class="{ checked: iwBatchChecked.has(item.video_id) }">{{ iwBatchChecked.has(item.video_id) ? '✓' : '' }}</span>
                <button v-if="!iwBatchMode" class="card-favorite-btn" title="快速收藏到本地" @click.stop="handleQuickFavorite(item)">♥</button>
              </div>
              <div class="card-name" :title="item.album_name">{{ trTitle(item.album_name) }}</div>
              <div class="iw-card-meta">
                <span class="iw-card-author" :title="item.author" @click.stop="$emit('iw-open-user', item.author_username)">{{ item.author || '未知作者' }}</span>
                <span class="iw-card-time">{{ iwTimeAgo(item.created_at) || item.post_date }}</span>
              </div>
            </div>
          </div>
          <div v-if="iwHomeItems.length && iwHomeHasMore" class="tw-browse-more">
            <n-button quaternary block :loading="iwHomeLoading" @click="$emit('iw-home-more')">加载更多</n-button>
          </div>
        </n-scrollbar>
      </div>

      <!-- Iwara 我的关注 / 我的好友：用户卡片（点进去看内容 / 关注/取关） -->
      <div v-else-if="site === 'iwara' && (iwView === 'following' || iwView === 'friends')" class="tw-follow-view">
        <div class="tw-follow-toolbar">
          <n-button size="small" quaternary type="primary" @click="$emit('iw-home', 1)">← 返回</n-button>
          <span class="tw-follow-title">{{ iwView === 'friends' ? '我的好友' : '我的关注' }}</span>
          <span v-if="(iwView === 'friends' ? iwFriendItems : iwFollowItems).length" class="tw-follow-count">
            {{ iwView === 'friends' ? iwFriendItems.length : iwFollowItems.length }} 人
            <template v-if="iwView === 'friends' ? iwFriendHasMore : iwFollowHasMore">（可继续加载）</template>
          </span>
          <n-button
            v-if="iwView === 'friends' ? iwFriendHasMore : iwFollowHasMore"
            size="tiny"
            :loading="iwView === 'friends' ? iwFriendLoading : iwFollowLoading"
            @click="$emit(iwView === 'friends' ? 'iw-friends-more' : 'iw-following-more')"
          >加载更多</n-button>
        </div>
        <n-scrollbar class="tw-follow-scroll">
          <div v-if="iwView === 'friends' ? iwFriendError : iwFollowError" class="tw-follow-error">
            {{ iwView === 'friends' ? iwFriendError : iwFollowError }}
          </div>
          <div v-else-if="(iwView === 'friends' ? iwFriendLoading : iwFollowLoading) && !(iwView === 'friends' ? iwFriendItems : iwFollowItems).length" class="tw-follow-empty">
            <n-spin size="medium" />
            <span>正在获取列表...</span>
          </div>
          <div v-else-if="!(iwView === 'friends' ? iwFriendItems : iwFollowItems).length" class="tw-follow-empty">暂无数据</div>
          <div
            v-for="u in (iwView === 'friends' ? iwFriendItems : iwFollowItems)"
            :key="u.user_id"
            class="iw-user-card"
            :class="{ 'iw-batch-checked': iwBatchMode && iwBatchChecked.has(u.username) }"
            :title="`${u.name} (@${u.username})\n${iwBatchMode ? '点击勾选/取消勾选' : '查看 TA 的视频'}`"
            @click="iwBatchMode ? toggleIwBatchItem(u.username) : $emit('iw-open-user', u.username)"
          >
            <span v-if="iwBatchMode" class="iw-batch-check iw-batch-check-user" :class="{ checked: iwBatchChecked.has(u.username) }">{{ iwBatchChecked.has(u.username) ? '✓' : '' }}</span>
            <div class="iw-user-avatar">
              <img v-if="u.thumbnail" :src="u.thumbnail" referrerpolicy="no-referrer" :alt="u.username" />
              <span v-else class="iw-user-avatar-empty">@</span>
            </div>
            <div class="iw-user-info">
              <div class="iw-user-name">
                <span class="iw-user-nick">{{ u.name || u.username }}</span>
                <n-tag v-if="u.premium" size="tiny" type="warning" round>会员</n-tag>
                <n-tag v-if="u.friend" size="tiny" type="info" round>好友</n-tag>
              </div>
              <div class="iw-user-handle">@{{ u.username }}</div>
            </div>
            <div class="iw-user-actions" @click.stop>
              <n-button
                size="tiny"
                quaternary
                type="primary"
                title="查看 TA 的全部视频"
                @click="$emit('iw-open-user', u.username)"
              >看内容</n-button>
              <n-button
                size="tiny"
                ghost
                :type="u.following ? 'error' : 'primary'"
                @click="$emit(u.following ? 'iw-unfollow' : 'iw-follow', u)"
              >{{ u.following ? '取消关注' : '关注' }}</n-button>
            </div>
          </div>
        </n-scrollbar>
      </div>

      <!-- Hanime1 (H站) 视频详情：播放 + 信息 + 收藏 + 评论区（登录后可发表评论） -->
      <div v-else-if="site === 'hanime' && haView === 'detail'" class="iw-detail">
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
          </n-scrollbar>
        </template>
      </div>

      <!-- Hanime1 (H站) 主页：分区列表（最新上市/最新上傳 + 各分类，每区最多 20 条） -->
      <div v-else-if="site === 'hanime' && haView === 'home'" class="tw-follow-view">
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
                  @click="haBatchMode ? toggleHaBatchItem(item.video_id) : $emit('ha-open-detail', item)"
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

      <!-- Hanime1 (H站) 用户中心：觀看紀錄/稍後觀看/讚好的影片/上傳的影片/審核中的影片 -->
      <div v-else-if="site === 'hanime' && haView === 'user'" class="tw-follow-view">
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
            <div
              v-for="item in haUserItems"
              :key="item.video_id || item.album_url"
              class="search-card iw-card"
              :class="{ 'iw-batch-checked': haBatchMode && haBatchChecked.has(item.video_id) }"
              :title="`${item.album_name}\n${haBatchMode ? '点击勾选/取消勾选' : '点击查看完整信息'}`"
              @click="haBatchMode ? toggleHaBatchItem(item.video_id) : $emit('ha-open-detail', item)"
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

      <!-- Oreno3D (O3D) / EroMMDTube (E站) 视频详情：播放（iwara 源最高画质）+ 作者/角色/原作可点击 + iwara 原站链接 + 下载 -->
      <div v-else-if="isOrenoSite && orView === 'detail'" class="iw-detail">
        <div v-if="orDetailLoading && !orDetail" class="tw-follow-empty">
          <n-spin size="medium" />
          <span>正在获取视频详情...</span>
        </div>
        <template v-else-if="orDetail">
          <div class="tw-follow-toolbar">
            <n-button size="small" quaternary type="primary" @click="$emit('or-detail-back')">← 返回</n-button>
            <span class="tw-follow-title iw-detail-title" :title="orDetail.album_name">{{ orDetail.album_name }}</span>
            <n-button
              size="tiny"
              :type="orDetail.saved ? 'error' : 'default'"
              tertiary
              :title="orDetail.saved ? '已收藏，点击取消' : '收藏到本地'"
              @click="$emit('or-toggle-favorite', orDetail)"
            >{{ orDetail.saved ? '♥ 已收藏' : '♡ 收藏' }}</n-button>
            <n-button
              v-if="orDetail.iwara_id"
              size="tiny"
              tertiary
              type="primary"
              title="下载此视频（iwara 源最高画质）"
              :loading="orBatchRunning"
              @click="$emit('or-batch-download', [orDetail.video_id])"
            >下载视频</n-button>
          </div>
          <n-scrollbar class="iw-detail-scroll">
            <div class="iw-video-area">
              <!-- iwara 源直链经本地媒体代理（带代理/登录态转发） -->
              <video
                v-if="orDetail.video_url"
                :src="proxied(orDetail.video_url)"
                controls
                preload="metadata"
                :poster="orDetail.thumbnail"
              />
              <img v-else :src="orDetail.thumbnail" referrerpolicy="no-referrer" :alt="orDetail.album_name" />
            </div>
            <div class="iw-detail-stats">
              <span v-if="orDetail.views">👁 {{ orDetail.views }}</span>
              <span v-if="orDetail.likes">♥ {{ orDetail.likes }}</span>
              <span v-if="orDetail.duration">⏱ {{ orDuration(orDetail.duration) }}</span>
              <span v-if="orDetail.post_date">{{ orDetail.post_date }}</span>
            </div>
            <!-- 作者可点击查看全部作品 + iwara 原站链接 -->
            <div class="iw-author-row">
              <span
                class="iw-author-name or-author-link"
                title="查看该作者的全部作品"
                @click="$emit('or-author', orDetail.author_id)"
              >👤 {{ orDetail.author || '未知作者' }}</span>
              <a
                v-if="orDetail.iwara_url"
                class="or-iwara-link"
                title="在浏览器打开 iwara.tv 原视频"
                @click.prevent="openOrExternal(orDetail.iwara_url)"
              >iwara 原站 ↗</a>
            </div>
            <div v-if="orDetail.origins && orDetail.origins.length" class="iw-tags">
              <n-tag
                v-for="o in orDetail.origins"
                :key="'o' + o.id"
                size="small"
                round
                type="warning"
                class="iw-tag"
                title="点击查看该原作（出处作品）的视频"
                @click="$emit('or-origin', o.id)"
              >🎬 {{ o.name }}</n-tag>
            </div>
            <div v-if="orDetail.characters && orDetail.characters.length" class="iw-tags">
              <n-tag
                v-for="c in orDetail.characters"
                :key="'c' + c.id"
                size="small"
                round
                type="success"
                class="iw-tag"
                title="点击查看该角色的视频"
                @click="$emit('or-character', c.id)"
              >🎭 {{ c.name }}</n-tag>
            </div>
            <div v-if="orDetail.tags && orDetail.tags.length" class="iw-tags">
              <n-tag
                v-for="t in orDetail.tags"
                :key="t.id"
                size="small"
                round
                type="info"
                class="iw-tag"
                title="点击查看该标签的视频"
                @click="$emit('or-tag', t.id)"
              >{{ t.name }}</n-tag>
            </div>
            <div v-if="!orDetail.iwara_id" class="or-no-source">
              该视频没有找到 iwara 源，无法在线播放 / 下载
            </div>
          </n-scrollbar>
        </template>
      </div>

      <!-- Oreno3D (O3D) / EroMMDTube (E站) 主页：卡片网格 + 排序 + 加载更多 -->
      <div v-else-if="isOrenoSite && orView === 'home'" class="tw-follow-view">
        <div class="tw-follow-toolbar">
          <span class="tw-follow-title">{{ orSiteLabel }} · {{ orSortLabel }}</span>
          <span v-if="orHomeItems.length" class="tw-follow-count">
            {{ orHomeItems.length }} 个视频<template v-if="orHomeHasMore">（可继续加载）</template>
          </span>
          <n-button size="tiny" quaternary :loading="orHomeLoading" @click="$emit('or-home', 1)">刷新</n-button>
        </div>
        <n-scrollbar class="tw-follow-scroll">
          <div v-if="orHomeError" class="tw-follow-error">{{ orHomeError }}</div>
          <div v-else-if="orHomeLoading && !orHomeItems.length" class="tw-follow-empty">
            <n-spin size="medium" />
            <span>正在获取主页内容...</span>
          </div>
          <div v-else-if="!orHomeItems.length" class="tw-follow-empty">暂无内容</div>
          <div v-else class="search-grid">
            <div
              v-for="item in orHomeItems"
              :key="item.video_id || item.album_url"
              class="search-card iw-card"
              :class="{ 'iw-batch-checked': orBatchMode && orBatchChecked.has(item.video_id) }"
              :title="`${item.album_name}\n作者: ${item.author || '未知'}${item.tags && item.tags.length ? '\n标签: ' + item.tags.join(' ') : ''}\n${orBatchMode ? '点击勾选/取消勾选' : '点击查看完整信息'}`"
              @click="orBatchMode ? toggleOrBatchItem(item.video_id) : $emit('or-open-detail', item)"
            >
              <div class="thumb-wrapper">
                <img :src="item.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name" />
                <div class="iw-thumb-stats">
                  <span v-if="item.views">👁 {{ item.views }}</span>
                  <span v-if="item.likes">♥ {{ item.likes }}</span>
                </div>
                <span v-if="orBatchMode" class="iw-batch-check" :class="{ checked: orBatchChecked.has(item.video_id) }">{{ orBatchChecked.has(item.video_id) ? '✓' : '' }}</span>
                <button v-if="!orBatchMode" class="card-favorite-btn" title="收藏到本地（再点一次取消）" @click.stop="$emit('or-toggle-favorite', item)">♥</button>
              </div>
              <div class="card-name" :title="item.album_name">{{ trTitle(item.album_name) }}</div>
              <div class="iw-card-meta">
                <span class="iw-card-author">{{ item.author || '未知作者' }}</span>
              </div>
            </div>
          </div>
          <div v-if="orHomeItems.length && orHomeHasMore" class="tw-browse-more">
            <n-button quaternary block :loading="orHomeLoading" @click="$emit('or-home-more')">加载更多</n-button>
          </div>
        </n-scrollbar>
      </div>

      <!-- Oreno3D / EroMMDTube 角色列表：人気角色（名称+原作+作品数）+ 五十音分组 tab -->
      <div v-else-if="isOrenoSite && orView === 'characters'" class="tw-follow-view">
        <div class="tw-follow-toolbar">
          <n-button size="small" quaternary type="primary" @click="$emit('or-browse-back')">← 返回</n-button>
          <span class="tw-follow-title">👥 角色列表</span>
          <span v-if="orCharacters.popular && orCharacters.popular.length" class="tw-follow-count">
            人気 {{ orCharacters.popular.length }} 个角色
          </span>
          <n-button size="tiny" quaternary :loading="orCharsLoading" @click="$emit('or-characters')">刷新</n-button>
        </div>
        <n-scrollbar class="tw-follow-scroll">
          <div v-if="orCharsLoading && !orCharacters.popular.length && !orKanaRows.length" class="tw-follow-empty">
            <n-spin size="medium" />
            <span>正在获取角色列表...</span>
          </div>
          <template v-else>
            <div class="or-browse-section">
              <div class="or-browse-section-title">人気角色</div>
              <div v-if="orCharacters.popular && orCharacters.popular.length" class="or-chip-list">
                <span
                  v-for="c in orCharacters.popular"
                  :key="'p' + c.id"
                  class="or-tag-chip or-char-chip"
                  :title="`查看「${c.name}」的视频${c.count ? `（${c.count} 部作品）` : ''}`"
                  @click="$emit('or-character', c.id)"
                >{{ c.name }}<span v-if="c.origin" class="or-chip-origin">（{{ c.origin }}）</span><span v-if="c.count" class="or-chip-count">{{ c.count }}</span></span>
              </div>
              <div v-else class="or-tags-empty">暂无人気角色数据</div>
            </div>
            <div class="or-browse-section">
              <div class="or-browse-section-title">五十音分组</div>
              <div v-if="orKanaRows.length" class="or-kana-tabs">
                <button
                  v-for="row in orKanaRows"
                  :key="row"
                  class="or-kana-tab"
                  :class="{ on: orKanaActive === row }"
                  @click="orKanaRow = row"
                >{{ row }}</button>
              </div>
              <div v-if="orKanaActive && orKanaList.length" class="or-chip-list">
                <span
                  v-for="c in orKanaList"
                  :key="c.id"
                  class="or-tag-chip or-char-chip"
                  :title="`查看「${c.name}」的视频${c.count ? `（${c.count} 部作品）` : ''}`"
                  @click="$emit('or-character', c.id)"
                >{{ c.name }}<span v-if="c.origin" class="or-chip-origin">（{{ c.origin }}）</span><span v-if="c.count" class="or-chip-count">{{ c.count }}</span></span>
              </div>
              <div v-else-if="orKanaRows.length" class="or-tags-empty">该行没有角色</div>
              <div v-else class="or-tags-empty">暂无五十音分组数据</div>
            </div>
          </template>
        </n-scrollbar>
      </div>

      <!-- Oreno3D / EroMMDTube 人気作者列表：排名 + 名称，分页浏览 -->
      <div v-else-if="isOrenoSite && orView === 'authors'" class="tw-follow-view">
        <div class="tw-follow-toolbar">
          <n-button size="small" quaternary type="primary" @click="$emit('or-browse-back')">← 返回</n-button>
          <span class="tw-follow-title">👤 人気作者</span>
          <span class="tw-follow-count">第 {{ orAuthorsPage }} 页</span>
          <n-button
            size="tiny"
            quaternary
            :disabled="orAuthorsPage <= 1"
            :loading="orAuthorsLoading"
            @click="$emit('or-authors-index', orAuthorsPage - 1)"
          >上一页</n-button>
          <n-button
            size="tiny"
            quaternary
            :disabled="!orAuthorsHasMore"
            :loading="orAuthorsLoading"
            @click="$emit('or-authors-index', orAuthorsPage + 1)"
          >下一页</n-button>
          <n-button size="tiny" quaternary :loading="orAuthorsLoading" @click="$emit('or-authors-index', orAuthorsPage)">刷新</n-button>
        </div>
        <n-scrollbar class="tw-follow-scroll">
          <div v-if="orAuthorsLoading && !orAuthors.length" class="tw-follow-empty">
            <n-spin size="medium" />
            <span>正在获取作者列表...</span>
          </div>
          <div v-else-if="!orAuthors.length" class="tw-follow-empty">暂无作者</div>
          <div v-else class="or-author-list">
            <div
              v-for="a in orAuthors"
              :key="a.id"
              class="or-author-item"
              :title="`查看「${a.name}」的全部作品`"
              @click="$emit('or-author', a.id)"
            >
              <span v-if="a.rank" class="or-author-rank">{{ a.rank }}</span>
              <span class="or-author-name">{{ a.name }}</span>
            </div>
          </div>
          <div v-if="orAuthors.length && !orAuthorsHasMore" class="tw-follow-count" style="text-align: center; padding: 10px 0">没有更多了</div>
        </n-scrollbar>
      </div>

      <!-- Oreno3D / EroMMDTube 标签/角色/作者/原作/收藏列表：卡片网格 + 加载更多 + 返回主页 -->
      <div v-else-if="isOrenoSite && orView === 'list'" class="tw-follow-view">
        <div class="tw-follow-toolbar">
          <n-button size="small" quaternary type="primary" @click="$emit('or-list-back')">← 返回</n-button>
          <span class="tw-follow-title">{{ orListTitle }}</span>
          <span v-if="orList.items.length" class="tw-follow-count">
            {{ orList.items.length }} 个视频<template v-if="orList.has_more">（可继续加载）</template>
          </span>
          <n-button
            size="tiny"
            quaternary
            :loading="orListLoading"
            title="刷新当前列表"
            @click="refreshOrList"
          >刷新</n-button>
        </div>
        <n-scrollbar class="tw-follow-scroll">
          <div v-if="orListError" class="tw-follow-error">{{ orListError }}</div>
          <div v-else-if="orListLoading && !orList.items.length" class="tw-follow-empty">
            <n-spin size="medium" />
            <span>正在获取列表...</span>
          </div>
          <div v-else-if="!orList.items.length" class="tw-follow-empty">{{ orList.type === 'favorites' ? '还没有收藏，点卡片右上角 ♥ 收藏视频' : '暂无视频' }}</div>
          <div v-else class="search-grid">
            <div
              v-for="item in orList.items"
              :key="item.video_id || item.album_url"
              class="search-card iw-card"
              :class="{ 'iw-batch-checked': orBatchMode && orBatchChecked.has(item.video_id) }"
              :title="`${item.album_name}\n作者: ${item.author || '未知'}${item.tags && item.tags.length ? '\n标签: ' + item.tags.join(' ') : ''}\n${orBatchMode ? '点击勾选/取消勾选' : '点击查看完整信息'}`"
              @click="orBatchMode ? toggleOrBatchItem(item.video_id) : $emit('or-open-detail', item)"
            >
              <div class="thumb-wrapper">
                <img :src="item.thumbnail" loading="lazy" referrerpolicy="no-referrer" :alt="item.album_name" />
                <div class="iw-thumb-stats">
                  <span v-if="item.views">👁 {{ item.views }}</span>
                  <span v-if="item.likes">♥ {{ item.likes }}</span>
                </div>
                <span v-if="orBatchMode" class="iw-batch-check" :class="{ checked: orBatchChecked.has(item.video_id) }">{{ orBatchChecked.has(item.video_id) ? '✓' : '' }}</span>
                <button v-if="!orBatchMode" class="card-favorite-btn" :title="orList.type === 'favorites' ? '取消收藏' : '收藏到本地（再点一次取消）'" @click.stop="$emit('or-toggle-favorite', item)">{{ orList.type === 'favorites' ? '✕' : '♥' }}</button>
              </div>
              <div class="card-name" :title="item.album_name">{{ trTitle(item.album_name) }}</div>
              <div class="iw-card-meta">
                <span class="iw-card-author">{{ item.author || '未知作者' }}</span>
              </div>
            </div>
          </div>
          <div v-if="orList.items.length && orList.has_more" class="tw-browse-more">
            <n-button quaternary block :loading="orListLoading" @click="$emit('or-list-more')">加载更多</n-button>
          </div>
        </n-scrollbar>
      </div>

      <!-- ASMR 音声站列表视图（热门/媒体库/收藏/社团·标签·声优筛选共用）：作品卡片 -->
      <div v-else-if="site === 'asmr' && asmrView && asmrView !== 'detail'" class="tw-follow-view">
        <div class="tw-follow-toolbar">
          <n-button
            v-if="asmrFilter.id"
            size="small"
            quaternary
            type="primary"
            title="返回媒体库"
            @click="$emit('asmr-works', 1)"
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
            <div
              v-for="item in asmrItems"
              :key="item.video_id || item.album_url"
              class="search-card iw-card asmr-card"
              :class="{ 'iw-batch-checked': asmrBatchMode && asmrBatchChecked.has(item.video_id) }"
              :title="asmrCardTooltip(item)"
              @click="asmrBatchMode ? toggleAsmrBatchItem(item.video_id) : $emit('asmr-open-detail', item)"
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
        </n-scrollbar>
      </div>

      <!-- ASMR 作品详情：封面 + 元信息 + 收藏 + 音轨列表（文件夹分组）+ 内置音频播放器 -->
      <div v-else-if="site === 'asmr' && asmrView === 'detail'" class="iw-detail">
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
          </div>
          <n-scrollbar class="iw-detail-scroll">
            <div class="asmr-detail-head">
              <div class="asmr-detail-cover">
                <img :src="asmrDetail.thumbnail" referrerpolicy="no-referrer" :alt="asmrDetail.album_name" />
              </div>
              <div class="asmr-detail-info">
                <div v-if="asmrDetail.source_id" class="asmr-detail-rid">RJ号：{{ asmrDetail.source_id }}</div>
                <div class="asmr-detail-circle" title="点击查看该社团全部作品" @click="$emit('asmr-open-circle', asmrDetail)">
                  社团：{{ (asmrDetail.circle && asmrDetail.circle.name) || asmrDetail.author || '未知' }}
                </div>
                <div class="asmr-detail-stats">
                  <span v-if="asmrDetail.rating != null">★ {{ asmrDetail.rating }}<template v-if="asmrDetail.review_count">（{{ asmrDetail.review_count }} 条评价）</template></span>
                  <span v-if="asmrDetail.views != null">⬇ {{ formatCount(asmrDetail.views) }}</span>
                  <span v-if="asmrDetail.duration">⏱ {{ asmrDetail.duration }} 分钟</span>
                  <span v-if="asmrDetail.price != null">{{ asmrDetail.price > 0 ? `¥${asmrDetail.price}` : '免费' }}</span>
                  <n-tag v-if="asmrDetail.has_subtitle" size="tiny" type="info" round>中文字幕</n-tag>
                  <n-tag v-if="asmrDetail.nsfw" size="tiny" type="error" round>NSFW</n-tag>
                </div>
                <div v-if="asmrDetail.post_date" class="asmr-detail-meta">发售日：{{ asmrDetail.post_date }}<template v-if="asmrDetail.create_date"> · 入库：{{ asmrDetail.create_date }}</template></div>
                <div v-if="asmrDetail.file_count" class="asmr-detail-meta">共 {{ asmrDetail.file_count }} 个文件</div>
                <div class="asmr-detail-actions">
                  <n-button
                    size="tiny"
                    ghost
                    :type="asmrDetail.saved ? 'warning' : 'primary'"
                    :title="asmrDetail.saved ? '已收藏（点击取消）' : '加入收藏（需登录）'"
                    @click="$emit('asmr-toggle-favorite', asmrDetail)"
                  >{{ asmrDetail.saved ? '★ 已收藏' : '☆ 收藏' }}</n-button>
                  <n-button
                    v-if="asmrDetail.vas && asmrDetail.vas.length"
                    size="tiny"
                    quaternary
                    :title="`声优：${asmrDetail.vas.join('、')}`"
                    @click="$emit('asmr-open-va', asmrDetail)"
                  >🎤 声优：{{ asmrDetail.vas.join('、') }}</n-button>
                </div>
              </div>
            </div>
            <!-- 作品属性（中文附加信息） -->
            <div v-if="asmrDescEntries.length" class="asmr-attrs">
              <div v-for="a in asmrDescEntries" :key="a.key" class="asmr-attr-row">
                <span class="asmr-attr-key">{{ a.key }}</span>
                <span class="asmr-attr-value">{{ a.value }}</span>
              </div>
            </div>
            <div v-if="asmrDetail.tags && asmrDetail.tags.length" class="iw-tags">
              <n-tag
                v-for="t in asmrDetail.tags"
                :key="t"
                size="small"
                round
                type="info"
                class="iw-tag"
                title="点击查看该标签作品"
                @click="$emit('asmr-search-tag', t)"
              >{{ t }}</n-tag>
            </div>
            <!-- 音轨文件列表：按文件夹路径分组 -->
            <div class="asmr-files-title">音轨文件<template v-if="asmrFiles.length">（{{ asmrFiles.length }}）</template></div>
            <div v-if="!asmrFiles.length" class="iw-comments-empty">暂无音轨文件</div>
            <div v-for="g in asmrFileGroups" :key="g.path || 'root'" class="asmr-file-group">
              <div v-if="g.path" class="asmr-folder-name" title="文件夹路径">📁 {{ g.path }}</div>
              <div
                v-for="(f, fi) in g.files"
                :key="fi"
                class="asmr-file-row"
                :class="{ active: f === asmrPlayingFile, text: f.type === 'text' }"
                :title="f.type === 'text' ? '文本文件（无音频）' : '点击播放'"
                @click="f.type === 'text' ? null : playAsmrFile(f)"
              >
                <span class="asmr-file-icon">{{ f.type === 'text' ? '📄' : (asmrPlayingFile === f ? '▶' : '♪') }}</span>
                <span class="asmr-file-name" :title="f.title">{{ f.title }}</span>
                <span v-if="f.type !== 'text' && f.duration" class="asmr-file-duration">{{ iwDuration(f.duration) }}</span>
                <span v-if="f.size" class="asmr-file-size">{{ formatSize(f.size) }}</span>
              </div>
            </div>
            <!-- 底部占位（播放器悬浮时不遮挡列表） -->
            <div class="asmr-player-space"></div>
          </n-scrollbar>
          <!-- 内置音频播放器（悬浮底部）：连续自动播放 + 快进/倒带 + 音量 -->
          <div v-if="asmrPlayingFile" class="asmr-player">
            <span class="asmr-player-icon">🎵</span>
            <div class="asmr-player-info">
              <div class="asmr-player-name" :title="asmrPlayingFile.title">{{ asmrPlayingFile.title }}</div>
              <div class="asmr-player-track">
                {{ asmrPlayingIndex + 1 }} / {{ asmrAudioFiles.length }}<template v-if="asmrPlayingFile.path"> · {{ asmrPlayingFile.path }}</template>
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
            <span class="asmr-player-time">{{ asmrTimeText }}</span>
            <n-button size="tiny" quaternary type="error" title="关闭播放器" @click="stopAsmrPlayer">✕</n-button>
            <audio
              ref="asmrAudioRef"
              :src="asmrPlayingFile.play_url"
              preload="auto"
              @ended="onAsmrEnded"
              @timeupdate="onAsmrTimeUpdate"
              @error="onAsmrAudioError"
            />
          </div>
        </template>
      </div>

      <!-- JavDB 视频详情：封面大图 + 预览图网格 + 信息面板 + 标签/演员 + 磁力列表 + 下载图片 -->
      <div v-else-if="site === 'javdb' && (javdbDetail || javdbDetailLoading)" class="ex-detail">
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
            <!-- 封面 -->
            <div class="iw-video-area javdb-cover-area">
              <img
                v-if="javdbDetail.cover"
                :src="javdbDetail.cover"
                referrerpolicy="no-referrer"
                :alt="javdbDetail.title"
                @click="openOrExternal(javdbDetail.cover)"
              />
            </div>
            <!-- 信息面板 -->
            <div v-if="javdbDetail.code || Object.keys(javdbDetail.info || {}).length" class="iw-detail-stats javdb-info-panel">
              <span v-if="javdbDetail.code">🏷️ 番号: {{ javdbDetail.code }}</span>
              <span v-for="(v, k) in javdbDetail.info" :key="k">{{ k }}: {{ v }}</span>
            </div>
            <!-- 演员 -->
            <div v-if="javdbDetail.actors && javdbDetail.actors.length" class="iw-tags">
              <n-tag size="small" round type="success" class="iw-tag">演员</n-tag>
              <n-tag v-for="a in javdbDetail.actors" :key="a" size="small" round type="success" class="iw-tag">{{ a }}</n-tag>
            </div>
            <!-- 标签 -->
            <div v-if="javdbDetail.tags && javdbDetail.tags.length" class="iw-tags">
              <n-tag v-for="t in javdbDetail.tags" :key="t" size="small" round type="info" class="iw-tag">{{ t }}</n-tag>
            </div>
            <!-- 磁力链接列表 -->
            <div v-if="javdbDetail.magnets && javdbDetail.magnets.length" class="javdb-magnets">
              <div class="javdb-magnets-title">🧲 磁力链接（{{ javdbDetail.magnets.length }} 个，点击复制，用外部种子客户端下载）</div>
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
            <div v-else class="or-no-source">没有磁力链接（部分磁力需登录后可见，可在左侧登录 JavDB）</div>
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
                  @click="openOrExternal(p)"
                />
              </div>
            </div>
          </n-scrollbar>
        </template>
      </div>

      <!-- ExHentai 浏览器视图（类浏览器界面，可登录/浏览/收藏；点"浏览器/搜索结果"切换） -->
      <div v-else-if="site === 'exhentai' && exViewMode === 'browser'" class="ex-browser">
        <!-- 浏览器工具栏 -->
        <div class="ex-toolbar">
          <n-button-group size="small">
            <n-button quaternary @click="exNav('back')" :disabled="!exNavState.canBack" title="后退">←</n-button>
            <n-button quaternary @click="exNav('forward')" :disabled="!exNavState.canForward" title="前进">→</n-button>
            <n-button quaternary @click="exNav('reload')" title="刷新">↻</n-button>
            <n-button quaternary @click="exNav('home')" title="主页">🏠</n-button>
          </n-button-group>
          <n-input
            v-model:value="exAddress"
            size="small"
            placeholder="https://exhentai.org/..."
            class="ex-address"
            @keyup.enter="exNavigateToAddress"
          >
            <template #prefix>
              <span style="font-size: 12px; color: #63e2b7">{{ exLoading ? '⏳' : '🔒' }}</span>
            </template>
          </n-input>
          <n-button size="small" type="primary" ghost :disabled="!exIsGallery" @click="exParseGallery" title="解析当前画廊的图片列表">
            解析画廊
          </n-button>
          <n-button size="small" type="warning" ghost :disabled="!exIsGallery" :loading="torrentLoading" @click="exShowTorrents" title="查看画廊的磁力链接">
            磁力
          </n-button>
          <n-button size="small" ghost :loading="cookieSyncing" @click="exSyncCookies" title="把浏览器登录状态同步给下载后端">
            同步Cookie
          </n-button>
          <!-- 登录状态（后端 cookie 验证结果） -->
          <n-tag v-if="exhentaiUser" size="small" type="success" round title="下载后端已登录 ExHentai">
            已登录: {{ exhentaiUser }}
          </n-tag>
          <n-tag v-else size="small" type="warning" round title="下载后端未登录，请先在浏览器中登录后点同步Cookie">
            后端未登录
          </n-tag>
          <!-- 浏览器/搜索结果视图切换 -->
          <n-button-group size="small">
            <n-button :type="exViewMode === 'browser' ? 'primary' : 'default'" size="small" @click="exShowBrowser">浏览器</n-button>
            <n-button :type="exViewMode === 'search' ? 'primary' : 'default'" size="small" @click="exViewMode = 'search'">搜索结果</n-button>
          </n-button-group>
        </div>
        <!-- webview 浏览器（独立会话 persist:exhentai，cookie 持久化保存） -->
        <webview
          ref="exWebviewRef"
          src="https://exhentai.org/"
          partition="persist:exhentai"
          class="ex-webview"
          @did-navigate="onExNavigated"
          @did-navigate-in-page="onExNavigated"
          @did-start-loading="exLoading = true"
          @did-stop-loading="exLoading = false"
        />
      </div>

      <!-- 搜索结果视图（解析中让位给"解析中"视图：点击后立即切换 + 显示加载态；
           EX 内联详情模式下解析中也保留搜索结果，进度显示在内联区块底部） -->
      <n-scrollbar
        v-else-if="searchResults.length > 0 && (!inspecting || exInlineDetail)"
        class="search-results"
        trigger="none"
        :on-scroll="handleScroll"
        :content-style="{ padding: '12px 16px' }"
      >
        <!-- ExHentai：复刻原版搜索页布局（列表/缩略图模式 + 顶底分页 + 跳页） -->
        <div v-if="site === 'exhentai'" class="ex-results">
          <!-- 工具栏：显示模式切换 + 批量收藏 + 结果统计 -->
          <div class="ex-toolbar">
            <n-button-group size="tiny">
              <n-button size="tiny" :type="exDisplayMode === 'list' ? 'primary' : 'default'" @click="exDisplayMode = 'list'" title="列表视图（原版 List 模式）">列表</n-button>
              <n-button size="tiny" :type="exDisplayMode === 'thumbnail' ? 'primary' : 'default'" @click="exDisplayMode = 'thumbnail'" title="缩略图视图（原版 Thumbnail 模式）">缩略图</n-button>
            </n-button-group>
            <!-- 批量下载全部：常驻按钮（无需逐个勾选，直接批量解析当前页全部画廊） -->
            <n-button
              size="tiny"
              type="warning"
              :disabled="exBatchRunning"
              :title="exBatchRunning
                ? '批量解析进行中，请稍候…'
                : `批量解析当前页全部 ${searchResults.length} 个画廊的图片并加入文件列表，可统一勾选下载（确认时可设置母文件夹）`"
              @click="$emit('ex-batch-download', searchResults.map(i => i.album_url).filter(Boolean))"
            >{{ exBatchRunning ? `批量解析中 (${exBatchProgress.done}/${exBatchProgress.total})` : `批量下载全部 (${searchResults.length})` }}</n-button>
            <n-button
              v-if="exChecked.length"
              size="tiny"
              type="primary"
              ghost
              @click="batchFavoriteEx"
            >收藏选中 ({{ exChecked.length }})</n-button>
            <n-button
              v-if="exChecked.length"
              size="tiny"
              type="warning"
              ghost
              title="批量解析选中画廊的全部图片并加入文件列表，可统一勾选下载"
              @click="$emit('ex-batch-download', exChecked)"
            >批量下载选中 ({{ exChecked.length }})</n-button>
            <!-- 选中操作：全选 / 反选 / 取消全部 -->
            <n-button-group v-if="searchResults.length" size="tiny">
              <n-button size="tiny" quaternary title="选中当前页全部画廊" @click="exCheckAll">全选</n-button>
              <n-button size="tiny" quaternary title="反转选择（未选的变为选中）" @click="exInvertCheck">反选</n-button>
              <n-button size="tiny" quaternary title="取消全部选择" @click="exChecked = []">取消全部</n-button>
            </n-button-group>
            <!-- 清除批量任务：批量收集过文件后常驻，一键清空并解锁视图（不删除已下载文件） -->
            <n-button
              v-if="fileList.length > 0 && !exBatchRunning"
              size="tiny"
              type="error"
              ghost
              title="清空批量解析收集的文件列表并解锁视图（不影响已提交的下载任务和已下载的文件）"
              @click="$emit('clear-batch-tasks')"
            >清除批量任务 ({{ fileList.length }})</n-button>
            <span class="ex-result-count">
              {{ exFavMode ? '我的收藏' : `共约 ${formatCount(searchTotalResults)} 条结果` }} · 第 {{ searchPage }}{{ searchTotalPages ? `/${searchTotalPages}` : '' }} 页
            </span>
          </div>
          <PaginationBar
            :page="searchPage"
            :total-pages="searchTotalPages"
            :has-more="searchHasMore"
            :searching="searching"
            @go-page="p => $emit('go-page', p)"
          />

          <!-- 列表模式（复刻 EX List：复选框 + 缩略图 + 绿色标题 + 可点击标签 + meta 行） -->
          <table v-if="exDisplayMode === 'list'" class="ex-list-table">
            <tbody>
              <tr
                v-for="(item, idx) in searchResults"
                :key="item.album_url"
                class="ex-tr"
                :class="{ 'ex-tr-alt': idx % 2 === 1 }"
                @click="$emit('ex-open-gallery', item.album_url)"
              >
                <td class="ex-td-check">
                  <input
                    type="checkbox"
                    class="ex-check"
                    :value="item.album_url"
                    v-model="exChecked"
                    @click.stop
                  />
                </td>
                <td class="ex-td-thumb">
                  <div class="ex-thumb">
                    <img
                      v-if="item.thumbnail"
                      :src="item.thumbnail"
                      loading="lazy"
                      referrerpolicy="no-referrer"
                      :alt="item.album_name"
                    />
                    <span v-else class="ex-thumb-empty">EX</span>
                  </div>
                </td>
                <td class="ex-td-info">
                  <div class="ex-info-title" :title="item.album_name">{{ trTitle(item.album_name) }}</div>
                  <div class="ex-info-tags" v-if="item.tags && item.tags.length">
                    <a
                      v-for="t in item.tags"
                      :key="t"
                      class="ex-info-tag"
                      title="点击搜索该标签"
                      @click.stop="searchTag(t)"
                    >{{ t }}</a>
                  </div>
                  <div class="ex-info-meta">
                    <span v-if="item.posted">发布于 {{ item.posted }}</span>
                    <span v-if="item.uploader">发布者 {{ item.uploader }}</span>
                    <span v-if="item.pages">{{ item.pages }} 页</span>
                  </div>
                </td>
                <td class="ex-td-fav">
                  <button
                    class="card-favorite-btn ex-row-fav"
                    title="快速收藏到本地"
                    @click.stop="handleQuickFavorite(item)"
                  >♥</button>
                </td>
              </tr>
            </tbody>
          </table>

          <!-- 缩略图模式（复刻 EX Thumbnail：网格缩略图 + 标题 + 勾选批量下载） -->
          <div v-else class="ex-thumb-grid">
            <div
              v-for="item in searchResults"
              :key="item.album_url"
              class="ex-thumb-card"
              :class="{ 'ex-thumb-card-checked': exChecked.includes(item.album_url) }"
              :title="item.album_name"
              @click="$emit('ex-open-gallery', item.album_url)"
            >
              <div class="ex-thumb-card-img">
                <img
                  v-if="item.thumbnail"
                  :src="item.thumbnail"
                  loading="lazy"
                  referrerpolicy="no-referrer"
                  :alt="item.album_name"
                />
                <span v-else class="ex-thumb-empty">EX</span>
                <!-- 多选勾选框（与列表模式共用 exChecked，勾选后可批量下载） -->
                <label class="ex-thumb-check" title="勾选后可批量下载" @click.stop>
                  <input
                    type="checkbox"
                    class="ex-check"
                    :value="item.album_url"
                    v-model="exChecked"
                  />
                </label>
              </div>
              <div class="ex-thumb-card-title">{{ trTitle(item.album_name) }}</div>
              <button
                class="card-favorite-btn ex-card-fav"
                title="快速收藏到本地"
                @click.stop="handleQuickFavorite(item)"
              >♥</button>
            </div>
          </div>

          <PaginationBar
            :page="searchPage"
            :total-pages="searchTotalPages"
            :has-more="searchHasMore"
            :searching="searching"
            @go-page="p => $emit('go-page', p)"
          />

          <!-- EX 内联详情+文件列表：从搜索结果/收藏点开作品后，追加在搜索结果下方（不跳转新界面） -->
          <div v-if="exInlineDetail" class="ex-inline-detail">
            <div class="ex-inline-detail-head">
              <span class="ex-inline-detail-title">
                {{ exGalleryDetail ? exGalleryDetail.title : (albumInfo.album_name || '正在解析...') }}
              </span>
              <n-button
                size="tiny"
                quaternary
                type="error"
                title="收起详情并清空文件列表，回到纯搜索结果"
                @click="$emit('back-to-search')"
              >✕ 收起详情</n-button>
            </div>

            <!-- 解析中：进度动画（搜索结果保留在上方） -->
            <div v-if="inspecting || exDetailLoading" class="ex-inline-detail-loading">
              <n-spin size="medium" />
              <span>
                正在解析文件列表...
                <template v-if="inspectProgress && inspectProgress.total > 0">
                  （{{ inspectProgress.current }}/{{ inspectProgress.total }}）
                </template>
              </span>
            </div>

            <template v-else>
              <!-- 画廊详情（完整信息 + 分组标签，与独立详情视图一致） -->
              <div v-if="exGalleryDetail" class="ex-detail-head">
                <div class="ex-detail-cover">
                  <img
                    v-if="exGalleryDetail.thumbnail"
                    :src="exGalleryDetail.thumbnail"
                    referrerpolicy="no-referrer"
                    :alt="exGalleryDetail.title"
                  />
                  <span v-else class="ex-thumb-empty">EX</span>
                </div>
                <div class="ex-detail-info">
                  <div class="ex-detail-name" :title="exGalleryDetail.title">{{ exGalleryDetail.title }}</div>
                  <div
                    v-if="exGalleryDetail.title_jp && exGalleryDetail.title_jp !== exGalleryDetail.title"
                    class="ex-detail-name-jp"
                  >{{ exGalleryDetail.title_jp }}</div>
                  <table class="ex-detail-meta">
                    <tr v-if="exGalleryDetail.uploader"><td>发布者</td><td>{{ exGalleryDetail.uploader }}</td></tr>
                    <tr v-if="exGalleryDetail.posted"><td>发布时间</td><td>{{ exGalleryDetail.posted }}</td></tr>
                    <tr v-if="exGalleryDetail.language"><td>语言</td><td>{{ exGalleryDetail.language }}</td></tr>
                    <tr v-if="exGalleryDetail.file_size"><td>文件大小</td><td>{{ exGalleryDetail.file_size }}</td></tr>
                    <tr v-if="exGalleryDetail.length"><td>页数</td><td>{{ exGalleryDetail.length }}</td></tr>
                    <tr v-if="exGalleryDetail.rating">
                      <td>评分</td>
                      <td>⭐ {{ exGalleryDetail.rating }}<span v-if="exGalleryDetail.rating_count">（{{ exGalleryDetail.rating_count }} 人评分）</span></td>
                    </tr>
                  </table>
                  <div class="ex-detail-actions">
                    <n-button
                      size="small"
                      type="warning"
                      ghost
                      :loading="torrentLoading"
                      title="查看画廊附带的种子（可获取磁力或保存种子文件）"
                      @click="exDetailTorrents(exGalleryDetail.url)"
                    >种子 / 磁力</n-button>
                  </div>
                </div>
              </div>
              <div v-if="exGalleryDetail && exGalleryDetail.tags && Object.keys(exGalleryDetail.tags).length" class="ex-detail-tags">
                <div v-for="(tags, ns) in exGalleryDetail.tags" :key="ns" class="ex-detail-tagrow">
                  <span class="ex-detail-tagrow-ns">{{ ns }}:</span>
                  <a
                    v-for="t in tags"
                    :key="t"
                    class="ex-detail-tag"
                    title="点击搜索该标签"
                    @click="searchTag(`${ns}:${t}`)"
                  >{{ t }}</a>
                </div>
              </div>

              <!-- 文件列表（工具栏 + 方格/列表 + 下载栏，与独立文件列表视图一致） -->
              <div v-if="fileList.length > 0" class="ex-inline-file-list">
                <div class="list-toolbar">
                  <div class="album-info">
                    <span class="album-name">{{ albumInfo.album_name || '未知相册' }}</span>
                    <n-tag size="small" :type="albumInfo.is_album ? 'info' : 'warning'" round>
                      {{ albumInfo.is_album ? '相册' : '单文件' }}
                    </n-tag>
                    <span class="file-count">共 {{ fileList.length }} 个文件</span>
                  </div>
                  <div class="list-actions">
                    <n-button size="small" quaternary @click="selectAll">全选</n-button>
                    <n-button size="small" quaternary @click="selectNone">取消全选</n-button>
                    <n-button size="small" quaternary @click="invertSelection">反选</n-button>
                    <n-button size="small" quaternary @click="selectByType('ok')">仅选可下载</n-button>
                    <n-button
                      size="small"
                      quaternary
                      :title="viewMode === 'grid' ? '切换为横向详细列表' : '切换为小方格排列'"
                      @click="toggleViewMode"
                    >{{ viewMode === 'grid' ? '列表' : '方格' }}</n-button>
                  </div>
                </div>

                <n-data-table
                  v-if="viewMode === 'list'"
                  :columns="columns"
                  :data="filteredFileList"
                  :row-key="row => row.item_page"
                  :row-props="fileRowProps"
                  v-model:checked-row-keys="checkedKeys"
                  :max-height="tableHeight"
                  :scroll-x="700"
                  size="small"
                  striped
                />
                <div v-else class="file-grid">
                  <div
                    v-for="f in filteredFileList"
                    :key="f.item_page"
                    class="file-grid-item"
                    :class="{ 'grid-selected': checkedKeys.includes(f.item_page), 'grid-bad': f.status === 'error' }"
                    :title="`${f.filename}\n${f.size_text || ''}`"
                    @click="toggleGridSelect(f.item_page)"
                    @contextmenu.prevent="openFileCtxMenu($event, f)"
                  >
                    <div class="grid-thumb">
                      <img v-if="f.thumbnail" :src="f.thumbnail" referrerpolicy="no-referrer" loading="lazy" alt="" />
                      <img v-else-if="f.file_icon" :src="f.file_icon" class="grid-icon" alt="" />
                      <span v-else class="grid-type">{{ f.file_type || '文件' }}</span>
                      <span v-if="f.is_new" class="grid-new">新</span>
                      <span v-if="f.is_downloaded" class="grid-downloaded" title="历史任务已下载过（默认不勾选，可手动勾选重下）">已下载</span>
                      <span v-if="checkedKeys.includes(f.item_page)" class="grid-check">✓</span>
                      <span
                        v-if="f.status !== 'fetch_failed' && (isImageItem(f) || isVideoItem(f))"
                        class="grid-preview-btn"
                        :title="isVideoItem(f) ? '在线播放' : '查看大图'"
                        @click.stop="openPreview(f)"
                      >{{ isVideoItem(f) ? '▶' : '👁' }}</span>
                    </div>
                    <div class="grid-name">{{ f.filename }}</div>
                    <div class="grid-size">{{ f.size_text || '—' }}</div>
                  </div>
                </div>

                <div class="download-bar">
                  <div class="selected-info">
                    已选择 <span class="selected-count">{{ checkedKeys.length }}</span> 个文件
                    <span class="selected-size" v-if="selectedSizeText">({{ selectedSizeText }})</span>
                  </div>
                  <n-button
                    type="primary"
                    size="large"
                    :disabled="checkedKeys.length === 0"
                    :loading="downloading"
                    @click="handleDownload"
                  >
                    {{ downloading ? '下载中...' : `下载选中 (${checkedKeys.length})` }}
                  </n-button>
                </div>
              </div>
            </template>
          </div>
        </div>

        <!-- Pawchive：卡片网格 + 顶底分页（与 EX 同一套分页逻辑） -->
        <div v-else-if="site === 'pawchive'" class="pa-results">
          <div class="pa-toolbar">
            <span class="pa-result-count">
              {{ !searchQuery ? (searchResults.length && searchResults[0]?.album_url?.includes('/post/') ? '主页' : '我的收藏') : (searchMode === 'tag' ? `标签「${searchQuery}」` : `画师「${searchQuery}」`) }} · 第 {{ searchPage }}{{ searchTotalPages ? `/${searchTotalPages}` : '' }} 页
              <template v-if="searchTotalResults > 0">（{{ searchMode === 'artist' ? `共 ${formatCount(searchTotalResults)} 位画师` : `约 ${formatCount(searchTotalResults)} 条结果` }}）</template>
            </span>
            <button
              class="ex-cat-chip ex-fav-btn"
              title="查看全站最新帖子（主页内容流）"
              @click="$emit('pa-home')"
            >🏠 主页</button>
            <button
              class="ex-cat-chip ex-fav-btn"
              title="查看我在 Pawchive 服务器上收藏的画师（需登录）"
              @click="$emit('pa-favorites')"
            >★ 我的收藏</button>
          </div>
          <PaginationBar
            :page="searchPage"
            :total-pages="searchTotalPages"
            :has-more="searchHasMore"
            :searching="searching"
            @go-page="p => $emit('go-page', p)"
          />
          <div class="search-grid">
            <div
              v-for="item in searchResults"
              :key="item.album_url"
              class="search-card"
              @click="handlePaCardClick(item)"
              @contextmenu.prevent="openPaContextMenu($event, item)"
            >
              <div class="thumb-wrapper">
                <img
                  :src="item.thumbnail"
                  loading="lazy"
                  referrerpolicy="no-referrer"
                  :alt="item.album_name"
                />
                <div class="thumb-files" v-if="item.files != null">{{ item.files }} 个文件</div>
                <!-- 快速收藏到本地（悬浮提示） -->
                <button
                  class="card-favorite-btn"
                  title="快速收藏到本地"
                  @click.stop="handleQuickFavorite(item)"
                >♥</button>
              </div>
              <div class="card-name" :title="item.album_name">{{ trTitle(item.album_name) }}</div>
            </div>
          </div>
          <PaginationBar
            :page="searchPage"
            :total-pages="searchTotalPages"
            :has-more="searchHasMore"
            :searching="searching"
            @go-page="p => $emit('go-page', p)"
          />
        </div>

        <!-- Iwara：视频卡片网格（作者/日期/播放/点赞/R-18/时长）+ 顶底分页，点击进详情 -->
        <div v-else-if="site === 'iwara'" class="pa-results">
          <div class="pa-toolbar">
            <span class="pa-result-count">
              {{ searchQuery ? `「${searchQuery}」` : 'Iwara 视频' }} · 第 {{ searchPage }} 页
              <template v-if="searchTotalResults > 0">（共 {{ formatCount(searchTotalResults) }} 个视频）</template>
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
            <div
              v-for="item in searchResults"
              :key="item.album_url"
              class="search-card iw-card"
              :title="`${item.album_name}\n作者: ${item.author || '未知'}\n发布: ${item.post_date || '未知'}\n点击查看完整信息`"
              @click="$emit('iw-open-detail', item)"
            >
              <div class="thumb-wrapper">
                <img
                  :src="item.thumbnail"
                  loading="lazy"
                  referrerpolicy="no-referrer"
                  :alt="item.album_name"
                />
                <div class="thumb-files">▶ 视频</div>
                <span v-if="iwDuration(item.duration)" class="iw-thumb-duration">{{ iwDuration(item.duration) }}</span>
                <span v-if="item.rating === 'r18'" class="iw-thumb-r18">R-18</span>
                <span v-else-if="item.rating === 'ecchi'" class="iw-thumb-ecchi">Ecchi</span>
                <div class="iw-thumb-stats">
                  <span v-if="item.views != null">👁 {{ formatCount(item.views) }}</span>
                  <span v-if="item.likes != null">♥ {{ formatCount(item.likes) }}</span>
                </div>
                <button
                  class="card-favorite-btn"
                  title="快速收藏到本地"
                  @click.stop="handleQuickFavorite(item)"
                >♥</button>
              </div>
              <div class="card-name" :title="item.album_name">{{ trTitle(item.album_name) }}</div>
              <div class="iw-card-meta">
                <span class="iw-card-author" :title="item.author" @click.stop="$emit('iw-open-user', item.author_username)">{{ item.author || '未知作者' }}</span>
                <span class="iw-card-stats">
                  <span class="iw-card-time">{{ iwTimeAgo(item.created_at) || item.post_date }}</span>
                </span>
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
        </div>

        <!-- Hanime1：视频卡片（搜索/分类浏览通用）+ 顶底分页，点击进详情 -->
        <div v-else-if="site === 'hanime'" class="pa-results">
          <div class="pa-toolbar">
            <span class="pa-result-count">
              {{ searchQuery ? `「${searchQuery}」` : (settings.hanime_genre ? `分类「${settings.hanime_genre}」` : 'H站视频') }} · 第 {{ searchPage }} 页
              <template v-if="searchTotalResults > 0">（共 {{ formatCount(searchTotalResults) }} 个视频）</template>
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
            <div
              v-for="item in searchResults"
              :key="item.album_url"
              class="search-card iw-card"
              :class="{ 'iw-batch-checked': haBatchMode && haBatchChecked.has(item.video_id) }"
              :title="`${item.album_name}\n作者: ${item.author || '未知'}\n${haBatchMode ? '点击勾选/取消勾选' : '点击查看完整信息'}`"
              @click="haBatchMode ? toggleHaBatchItem(item.video_id) : $emit('ha-open-detail', item)"
            >
              <div class="thumb-wrapper">
                <img
                  :src="item.thumbnail"
                  loading="lazy"
                  referrerpolicy="no-referrer"
                  :alt="item.album_name"
                />
                <div class="thumb-files">▶ 视频</div>
                <span v-if="item.duration" class="iw-thumb-duration">{{ item.duration }}</span>
                <div class="iw-thumb-stats">
                  <span v-if="item.views">👁 {{ item.views }}</span>
                  <span v-if="item.rating">👍 {{ item.rating }}</span>
                </div>
                <span v-if="haBatchMode" class="iw-batch-check" :class="{ checked: haBatchChecked.has(item.video_id) }">{{ haBatchChecked.has(item.video_id) ? '✓' : '' }}</span>
                <button
                  v-else
                  class="card-favorite-btn"
                  title="快速收藏到本地"
                  @click.stop="handleQuickFavorite(item)"
                >♥</button>
              </div>
              <div class="card-name" :title="item.album_name">{{ trTitle(item.album_name) }}</div>
              <div class="iw-card-meta">
                <span class="iw-card-author">{{ item.author || '未知' }}</span>
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
        </div>

        <!-- Pixiv：插画卡片（搜索通用）+ 顶底分页，点击解析作品全部原图 -->
        <div v-else-if="site === 'pixiv'" class="pa-results">
          <div class="pa-toolbar">
            <span class="pa-result-count">
              {{ searchQuery ? `「${searchQuery}」` : 'Pixiv 作品' }} · 第 {{ searchPage }} 页
              <template v-if="searchTotalResults > 0">（共 {{ formatCount(searchTotalResults) }} 个作品）</template>
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
            <div
              v-for="item in searchResults"
              :key="item.album_url"
              class="search-card iw-card"
              :title="`${item.album_name}\n作者: ${item.author || '未知'}\n点击解析并下载全部原图`"
              @click="$emit('open-album', item)"
            >
              <div class="thumb-wrapper">
                <img
                  :src="proxied(item.thumbnail)"
                  loading="lazy"
                  referrerpolicy="no-referrer"
                  :alt="item.album_name"
                />
                <div class="thumb-files" v-if="item.files != null">{{ item.files }}P</div>
                <span v-if="item.r18" class="iw-thumb-duration" style="background: #d03050">R-18</span>
                <span v-if="item.ugoira" class="asmr-thumb-sub" style="background: #722ed1">动图</span>
                <button
                  class="card-favorite-btn"
                  title="快速收藏到本地"
                  @click.stop="handleQuickFavorite(item)"
                >♥</button>
              </div>
              <div class="card-name" :title="item.album_name">{{ trTitle(item.album_name) }}</div>
              <div class="iw-card-meta">
                <span
                  v-if="item.author"
                  class="iw-card-author"
                  title="点击解析该作者的全部作品"
                  @click.stop="$emit('open-album', { album_url: item.author_url, album_name: item.author })"
                >{{ item.author }}</span>
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
        </div>

        <!-- Oreno3D / EroMMDTube：视频卡片（搜索通用）+ 顶底分页，点击进详情 -->
        <div v-else-if="isOrenoSite" class="pa-results">
          <div class="pa-toolbar">
            <span class="pa-result-count">
              {{ searchQuery ? `「${searchQuery}」` : `${orSiteLabel} 视频` }} · 第 {{ searchPage }} 页
              <template v-if="searchTotalResults > 0">（共 {{ formatCount(searchTotalResults) }} 个视频）</template>
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
            <div
              v-for="item in searchResults"
              :key="item.album_url"
              class="search-card iw-card"
              :class="{ 'iw-batch-checked': orBatchMode && orBatchChecked.has(item.video_id) }"
              :title="`${item.album_name}\n作者: ${item.author || '未知'}${item.tags && item.tags.length ? '\n标签: ' + item.tags.join(' ') : ''}\n${orBatchMode ? '点击勾选/取消勾选' : '点击查看完整信息'}`"
              @click="orBatchMode ? toggleOrBatchItem(item.video_id) : $emit('or-open-detail', item)"
            >
              <div class="thumb-wrapper">
                <img
                  :src="item.thumbnail"
                  loading="lazy"
                  referrerpolicy="no-referrer"
                  :alt="item.album_name"
                />
                <div class="thumb-files">▶ 视频</div>
                <div class="iw-thumb-stats">
                  <span v-if="item.views">👁 {{ item.views }}</span>
                  <span v-if="item.likes">♥ {{ item.likes }}</span>
                </div>
                <span v-if="orBatchMode" class="iw-batch-check" :class="{ checked: orBatchChecked.has(item.video_id) }">{{ orBatchChecked.has(item.video_id) ? '✓' : '' }}</span>
                <button
                  v-else
                  class="card-favorite-btn"
                  title="收藏到本地（再点一次取消）"
                  @click.stop="$emit('or-toggle-favorite', item)"
                >♥</button>
              </div>
              <div class="card-name" :title="item.album_name">{{ trTitle(item.album_name) }}</div>
              <div class="iw-card-meta">
                <span class="iw-card-author">{{ item.author || '未知作者' }}</span>
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
        </div>

        <!-- ASMR 音声站：作品卡片（搜索通用，支持批量勾选）+ 顶底分页，点击进详情 -->
        <div v-else-if="site === 'asmr'" class="pa-results">
          <div class="pa-toolbar">
            <span class="pa-result-count">
              {{ searchQuery ? `「${searchQuery}」` : '音声作品' }} · 第 {{ searchPage }} 页
            </span>
            <n-button
              size="tiny"
              :type="asmrBatchMode ? 'warning' : 'default'"
              :title="asmrBatchMode ? '退出勾选模式' : '勾选多个作品批量下载'"
              @click="toggleAsmrBatch"
            >{{ asmrBatchMode ? `取消勾选${asmrBatchChecked.size ? `(${asmrBatchChecked.size})` : ''}` : '批量下载' }}</n-button>
            <n-button
              v-if="asmrBatchMode"
              size="tiny"
              type="error"
              :disabled="!asmrBatchChecked.size"
              :loading="asmrBatchRunning"
              @click="startAsmrBatch"
            >开始下载{{ asmrBatchChecked.size ? `(${asmrBatchChecked.size})` : '' }}</n-button>
          </div>
          <PaginationBar
            :page="searchPage"
            :total-pages="searchTotalPages"
            :has-more="searchHasMore"
            :searching="searching"
            @go-page="p => $emit('go-page', p)"
          />
          <div class="search-grid">
            <div
              v-for="item in searchResults"
              :key="item.album_url"
              class="search-card iw-card asmr-card"
              :class="{ 'iw-batch-checked': asmrBatchMode && asmrBatchChecked.has(item.video_id) }"
              :title="asmrCardTooltip(item)"
              @click="asmrBatchMode ? toggleAsmrBatchItem(item.video_id) : $emit('asmr-open-detail', item)"
            >
              <div class="thumb-wrapper">
                <img
                  :src="item.thumbnail"
                  loading="lazy"
                  referrerpolicy="no-referrer"
                  :alt="item.album_name"
                />
                <span v-if="item.duration" class="iw-thumb-duration">{{ item.duration }} 分钟</span>
                <span v-if="item.has_subtitle" class="asmr-thumb-sub">字幕</span>
                <div class="iw-thumb-stats">
                  <span v-if="item.views != null" title="下载数">⬇ {{ formatCount(item.views) }}</span>
                  <span v-if="item.rating" title="评分">★ {{ item.rating }}</span>
                </div>
                <span v-if="asmrBatchMode" class="iw-batch-check" :class="{ checked: asmrBatchChecked.has(item.video_id) }">{{ asmrBatchChecked.has(item.video_id) ? '✓' : '' }}</span>
                <button
                  v-else
                  class="card-favorite-btn"
                  title="快速收藏到本地"
                  @click.stop="handleQuickFavorite(item)"
                >♥</button>
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
          <PaginationBar
            :page="searchPage"
            :total-pages="searchTotalPages"
            :has-more="searchHasMore"
            :searching="searching"
            @go-page="p => $emit('go-page', p)"
          />
        </div>

        <!-- JavDB：搜索结果卡片（封面 + 番号 + 标题 + 分页 + 批量下载） -->
        <div v-else-if="site === 'javdb'" class="pa-results">
          <div class="pa-toolbar">
            <span class="pa-result-count">
              {{ searchQuery ? `「${searchQuery}」` : 'JavDB' }} · 第 {{ searchPage }} 页
            </span>
            <n-button
              size="tiny"
              type="warning"
              :loading="javdbBatchRunning"
              :title="`批量下载当前页全部 ${searchResults.length} 个视频的封面+预览图`"
              @click="startJavdbBatch"
            >批量下载全部{{ javdbBatchRunning ? `（${javdbBatchProgress.done}/${javdbBatchProgress.total}）` : '' }}</n-button>
          </div>
          <PaginationBar
            :page="searchPage"
            :total-pages="searchTotalPages"
            :has-more="searchHasMore"
            :searching="searching"
            @go-page="p => $emit('go-page', p)"
          />
          <div class="search-grid">
            <div
              v-for="item in searchResults"
              :key="item.album_url"
              class="search-card iw-card"
              :title="`${item.album_name}${item.author ? `\n演员: ${item.author}` : ''}${(item.tags && item.tags.length) ? `\n${item.tags.join(' ')}` : ''}${item.duration ? `\n时长: ${item.duration}` : ''}${item.score != null ? `\n评分: ${item.score}` : ''}${item.date ? `\n日期: ${item.date}` : ''}`"
              @click="$emit('javdb-open-detail', item)"
            >
              <div class="thumb-wrapper">
                <img
                  :src="item.thumbnail"
                  loading="lazy"
                  referrerpolicy="no-referrer"
                  :alt="item.album_name"
                />
                <span v-if="item.duration" class="iw-thumb-duration">{{ item.duration }}</span>
                <span v-if="item.has_subtitle" class="asmr-thumb-sub">字幕</span>
                <span v-if="item.is_vr" class="asmr-thumb-sub" style="background: #722ed1">VR</span>
                <div class="iw-thumb-stats">
                  <span v-if="item.score != null" title="评分">★ {{ item.score }}</span>
                  <span v-if="item.date" title="发行日期">{{ item.date }}</span>
                </div>
              </div>
              <div class="card-name" :title="item.album_name">{{ trTitle(item.album_name) }}</div>
              <div class="iw-card-meta">
                <span class="iw-card-author" :title="item.author ? `演员: ${item.author}` : ''">{{ item.author || '未知演员' }}</span>
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
        </div>

        <!-- 其他站点：网格卡片 -->
        <div v-else class="search-grid">
          <div
            v-for="item in searchResults"
            :key="item.album_url"
            class="search-card"
            @click="$emit('open-album', item)"
          >
            <div class="thumb-wrapper">
              <img
                :src="item.thumbnail"
                loading="lazy"
                referrerpolicy="no-referrer"
                :alt="item.album_name"
              />
              <div class="thumb-files" v-if="item.files != null">{{ item.files }} 个文件</div>
              <!-- 快速收藏到本地（悬浮提示） -->
              <button
                class="card-favorite-btn"
                title="快速收藏到本地"
                @click.stop="handleQuickFavorite(item)"
              >♥</button>
            </div>
            <div class="card-name" :title="item.album_name">{{ trTitle(item.album_name) }}</div>
          </div>
        </div>

        <!-- 加载更多（Bunkr/Coomer 保留；EX/PA 改为顶底页码分页） -->
        <div v-if="site === 'bunkr' || site === 'coomer'" class="load-more">
          <n-button
            v-if="searchHasMore"
            quaternary
            :loading="searching"
            @click="$emit('load-more')"
          >加载更多</n-button>
          <span v-else class="load-more-end">已加载全部</span>
        </div>
      </n-scrollbar>

      <!-- 解析中/搜索中视图（点击后立即切换到此处，明确反馈已响应） -->
      <div v-else-if="inspecting || searching" class="inspect-loading-view">
        <n-spin size="large" />
        <div class="inspect-loading-title">{{ searching ? '正在搜索...' : '正在解析文件列表...' }}</div>
        <div class="inspect-loading-sub">
          {{ searching
            ? '正在请求源站，请稍候'
            : (inspectProgress.total > 0
              ? `已解析 ${inspectProgress.current} / ${inspectProgress.total} 项`
              : '正在连接源站，首次解析可能需要几秒钟') }}
        </div>
      </div>

      <!-- 空状态 -->
      <div v-else-if="!inspecting" class="empty-state">
        <div class="empty-icon">🔍</div>
        <template v-if="site === 'coomer'">
          <div class="empty-text">搜索 Coomer 作者，或粘贴 xxxcoomer.com 链接</div>
          <div class="empty-hint">输入关键词搜索作者，点击作者卡片查看全部帖子文件</div>
        </template>
        <template v-else-if="site === 'pawchive'">
          <div class="empty-text">搜索 Pawchive 画师或标签，或粘贴 pawchive.pw 链接</div>
          <div class="empty-actions">
            <button class="empty-action-btn" @click="$emit('pa-home')">
              <span class="ea-icon">🏠</span> 主页
              <span class="ea-desc">全站最新帖子</span>
            </button>
            <button class="empty-action-btn" @click="$emit('pa-favorites')">
              <span class="ea-icon">★</span> 我的收藏
              <span class="ea-desc">收藏的画师（需登录）</span>
            </button>
          </div>
          <div class="empty-hint">
            画师搜索按名称匹配，标签搜索按帖子标签匹配
          </div>
        </template>
        <template v-else-if="site === 'exhentai'">
          <div class="empty-text">ExHentai 搜索</div>
          <div class="empty-hint">输入关键词搜索画廊，或点上方"浏览器"直接浏览站点；"解析画廊"获取图片列表，"磁力"获取种子链接</div>
        </template>
        <template v-else-if="site === 'twitter'">
          <div class="empty-text">X (Twitter) 用户媒体下载</div>
          <div class="empty-hint">输入用户名（如 @xxx）搜索并解析全部图片/视频，或直接粘贴推文链接；需在左侧设置中填写 Cookie 并配置代理</div>
        </template>
        <template v-else-if="site === 'iwara'">
          <div class="empty-text">Iwara (MMD) 视频下载</div>
          <div class="empty-hint">输入关键词搜索视频，@用户名 拉取作者全部视频，或粘贴 iwara.tv 视频页 / 用户主页链接；下载默认取最高画质（Source）源</div>
        </template>
        <template v-else-if="site === 'hanime'">
          <div class="empty-text">Hanime1 (H站) 里番视频下载</div>
          <div class="empty-hint">点上方"主页"看分区推荐，或输入关键词搜索；按分类按钮（裏番/3DCG/MMD...）浏览；登录后可收藏、评论、查看觀看紀錄</div>
        </template>
        <template v-else-if="site === 'oreno3d'">
          <div class="empty-text">Oreno3D 3D 视频聚合下载</div>
          <div class="empty-hint">点上方"主页"看人気推荐；"角色列表 / 人気作者 / 热门分类"分类浏览；输入关键词搜索；视频从 iwara 源下载最高画质</div>
        </template>
        <template v-else-if="site === 'erommdtube'">
          <div class="empty-text">EroMMDTube (E站) MMD 视频聚合下载</div>
          <div class="empty-hint">点上方"主页"看人気推荐；"角色列表 / 人気作者 / 热门分类"分类浏览；输入关键词搜索；视频从 iwara 源下载最高画质</div>
        </template>
        <template v-else-if="site === 'asmr'">
          <div class="empty-text">ASMR 音声作品下载（asmr-100.com）</div>
          <div class="empty-hint">点上方"热门作品"看推荐；"媒体库"按最新入库/评分等排序浏览；社团/标签/声优分类筛选；输入关键词或 RJ 号搜索；详情页可在线试听整包音轨</div>
        </template>
        <template v-else-if="site === 'javdb'">
          <div class="empty-text">JavDB 影片信息数据库（javdb.com）</div>
          <div class="empty-hint">输入番号（如 SSIS-001）/标题/演员名搜索，点卡片看详情（封面/预览/标签/磁力）；国内必须在左侧设置里配置 JavDB 代理</div>
        </template>
        <template v-else>
          <div class="empty-text">搜索 Bunkr 相册，或粘贴 Bunkr 链接</div>
          <div class="empty-hint">支持关键词搜索和直接链接解析，点击相册查看文件列表</div>
        </template>
      </div>
    </div>

    <!-- 底部：下载进度 + 日志 + 右侧实时下载滚动栏 -->
    <div class="bottom-area">
      <n-tabs type="line" size="small" :value="activeTab" @update:value="activeTab = $event">
        <n-tab-pane name="progress" tab="下载进度">
          <div class="progress-list">
            <template v-if="Object.keys(downloadProgress).length === 0">
              <div class="empty-tab">暂无下载任务</div>
            </template>
            <div
              v-for="(item, filename) in downloadProgress"
              :key="filename"
              class="progress-item"
            >
              <div class="progress-item-header">
                <span class="progress-filename" :title="filename">{{ filename }}</span>
                <div class="progress-meta">
                  <span
                    v-if="item.status === 'downloading' && item.speed > 0"
                    class="progress-speed"
                  >{{ formatSpeed(item.speed) }}</span>
                  <n-tag size="tiny" :type="statusTagType(item.status)" round>{{ statusText(item.status) }}</n-tag>
                </div>
              </div>
              <n-progress
                type="line"
                :percentage="item.completed || 0"
                :status="progressStatus(item.status)"
                :show-indicator="false"
                :height="6"
              />
            </div>
          </div>
        </n-tab-pane>
        <n-tab-pane name="logs" tab="日志">
          <div class="log-list">
            <div v-for="(log, i) in logs" :key="i" class="log-item">
              <span class="log-time">{{ log.time }}</span>
              <n-tag size="tiny" :type="logTagType(log.type)" round>{{ log.type }}</n-tag>
              <span class="log-message">{{ log.message }}</span>
            </div>
            <div v-if="logs.length === 0" class="empty-tab">暂无日志</div>
          </div>
        </n-tab-pane>
        <n-tab-pane name="history" tab="历史">
          <div class="history-list">
            <div v-for="item in history" :key="item.id" class="history-item">
              <div class="history-main">
                <span class="history-name" :title="item.path">{{ item.filename }}</span>
                <span class="history-meta">{{ item.time }} · {{ formatSize(item.size) }}</span>
              </div>
              <div class="history-actions">
                <n-button size="tiny" quaternary @click="$emit('open-file', item.path)">打开</n-button>
                <n-button size="tiny" quaternary @click="$emit('show-folder', item.path)">文件夹</n-button>
                <n-button size="tiny" quaternary type="warning" @click="handleDeleteHistory(item, false)">删记录</n-button>
                <n-button size="tiny" quaternary type="error" @click="handleDeleteHistory(item, true)">删文件</n-button>
              </div>
            </div>
            <div v-if="history.length === 0" class="empty-tab">暂无历史任务</div>
          </div>
        </n-tab-pane>
      </n-tabs>

      <!-- 右侧：实时下载滚动信息（文件名 + 进度 + 速度，自动向上滚动） -->
      <div class="dl-ticker">
        <div class="dl-ticker-header">
          <span class="dl-ticker-title">实时下载</span>
          <span v-if="tickerTotalSpeedText" class="dl-ticker-total">{{ tickerTotalSpeedText }}</span>
        </div>
        <div class="dl-ticker-viewport">
          <div v-if="tickerItems.length === 0" class="dl-ticker-empty">暂无下载任务</div>
          <div v-else class="dl-ticker-track">
            <div v-for="(item, i) in tickerLoopItems" :key="i" class="dl-ticker-item">
              <span class="dl-ticker-name" :title="item.name">{{ item.name }}</span>
              <span class="dl-ticker-pct">{{ item.percent }}%</span>
              <span class="dl-ticker-speed">{{ item.speedText }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 磁力链接弹窗：选择种子 -> 获取磁力 -> 复制/打开 -->
    <n-modal v-model:show="torrentModalVisible" preset="card" title="磁力链接（选择种子）" style="width: 640px">
      <div class="torrent-list">
        <div v-if="torrentList.length === 0 && !torrentLoading" class="torrent-empty">
          该画廊没有可用的种子
        </div>
        <div
          v-for="(t, i) in torrentList"
          :key="i"
          class="torrent-item"
        >
          <div class="torrent-info">
            <div class="torrent-name" :title="t.name">{{ t.name }}</div>
            <div class="torrent-meta">
              <span v-if="t.size">大小 {{ t.size }}</span>
              <span v-if="t.posted">发布 {{ t.posted }}</span>
              <span>做种 {{ t.seeds }} · 下载 {{ t.peers }}</span>
            </div>
          </div>
          <div class="torrent-actions">
            <n-button size="small" type="primary" ghost :loading="magnetLoading" @click="handleGetMagnet(t)">
              获取磁力
            </n-button>
            <n-button
              size="small"
              ghost
              title="下载 .torrent 种子文件到 downloads/torrents/"
              @click="$emit('ex-save-torrent', t)"
            >
              保存种子文件
            </n-button>
          </div>
        </div>
      </div>
      <!-- 磁力结果 -->
      <div v-if="currentMagnet" class="magnet-result">
        <div class="magnet-label">磁力链接：</div>
        <n-input :value="currentMagnet" size="small" readonly type="textarea" :rows="2" />
        <div class="magnet-actions">
          <n-button size="small" @click="copyMagnet">复制链接</n-button>
          <n-button size="small" type="primary" @click="openMagnet">用下载器打开</n-button>
        </div>
      </div>
    </n-modal>

    <!-- X 关注分类弹窗：填写或选择母类/子类后保存归类 -->
    <n-modal v-model:show="twTagModalVisible" preset="dialog" title="设置关注分类" style="width: 480px">
      <div class="tw-tag-modal">
        <div class="tw-tag-user">
          正在归类：<b>@{{ twTagModalUser && twTagModalUser.screen_name }}</b>
          <span v-if="twTagModalUser && (twTagModalUser.follow_tag || twTagModalUser.tag)" class="tw-tag-current">
            （当前：{{ twTagModalUser.follow_tag || twTagModalUser.tag }}）
          </span>
        </div>
        <div class="tw-tag-row">
          <span class="tw-tag-label">母类</span>
          <n-select
            v-model:value="twTagParent"
            size="small"
            filterable
            tag
            clearable
            placeholder="选择已有母类，或直接输入新母类"
            :options="twParentOptions"
          />
        </div>
        <div class="tw-tag-row">
          <span class="tw-tag-label">子类</span>
          <n-select
            v-model:value="twTagChild"
            size="small"
            filterable
            tag
            clearable
            placeholder="选择该母类下的子类，或直接输入新子类（可留空）"
            :options="twChildOptions"
          />
        </div>
        <div class="tw-tag-hint">
          可下拉选择已保存的分类，也可直接输入新名称（保存时自动创建）；
          母类留空保存 = 移除该用户的归类。分类可在左侧"关注分类管理"维护。
        </div>
      </div>
      <template #action>
        <n-button size="small" @click="twTagModalVisible = false">取消</n-button>
        <n-button size="small" type="error" ghost @click="twRemoveTag">移除归类</n-button>
        <n-button size="small" type="primary" @click="twSaveTag">保存归类</n-button>
      </template>
    </n-modal>

    <!-- 在线预览/播放弹窗（所有站点通用：图片看原图 + 视频在线播放，支持左右键切换） -->
    <n-modal
      v-model:show="previewVisible"
      preset="card"
      class="media-preview-modal"
      :title="previewItem ? (previewIsVideo ? '在线播放' : '图片预览') : '预览'"
      style="width: min(920px, 92vw)"
    >
      <div v-if="previewItem" class="media-preview-body">
        <!-- 视频播放（走本地媒体代理，可拖进度条） -->
        <div v-if="previewIsVideo" class="media-preview-video">
          <video
            v-if="previewSrc"
            ref="previewVideoRef"
            :key="previewSrc"
            :src="previewSrc"
            :muted="previewMuted"
            :volume="previewVolume"
            controls
            autoplay
            preload="metadata"
            @loadedmetadata="applyPreviewVolume"
            @volumechange="onPreviewVolumeChange"
            @error="previewItem.media_resolve_failed = true"
          ></video>
          <div v-else-if="previewLoading" class="media-preview-tip">
            正在解析播放地址（Bunkr/EX 需要请求源站）...
          </div>
          <div v-else class="media-preview-tip media-preview-err">
            {{ previewItem.media_resolve_msg || '无法解析播放地址，请直接下载后观看' }}
          </div>
          <!-- 音量控制（默认静音 + 音量持久化，仅视频时显示） -->
          <div v-if="previewSrc" class="media-preview-controls">
            <n-button size="tiny" quaternary title="静音 / 取消静音（音量已记忆）" @click="togglePreviewMute">{{ previewMuted ? '🔇' : '🔊' }}</n-button>
            <input
              class="preview-volume"
              type="range"
              min="0"
              max="100"
              :value="previewVolumePercent"
              title="音量（拖动后自动记住）"
              @input="onPreviewVolumeInput"
            />
            <span class="preview-volume-text">{{ previewVolumePercent }}%</span>
          </div>
        </div>
        <!-- 图片预览（加载中显示 spinner，避免大图白屏卡顿感） -->
        <div v-else class="media-preview-image" @click="previewNav(1)">
          <n-spin v-if="previewSrc && !previewImageLoaded && !previewImageFailed" size="large" class="media-preview-img-loading" />
          <img
            v-if="previewSrc && !previewImageFailed"
            v-show="previewImageLoaded"
            :src="previewSrc"
            referrerpolicy="no-referrer"
            decoding="async"
            alt=""
            @load="previewImageLoaded = true"
            @error="previewImageFailed = true"
          />
          <div v-if="previewImageFailed" class="media-preview-tip media-preview-err">
            图片加载失败（可能被源站防盗链拦截），请直接下载后查看
          </div>
        </div>
        <!-- 底部信息 + 导航 -->
        <div class="media-preview-footer">
          <n-button size="small" quaternary :disabled="previewableList.length < 2" @click="previewNav(-1)">← 上一个</n-button>
          <div class="media-preview-name" :title="previewItem.filename">
            {{ previewItem.filename }}
            <span class="media-preview-size">{{ previewItem.size_text || '' }}</span>
          </div>
          <n-button size="small" quaternary :disabled="previewableList.length < 2" @click="previewNav(1)">下一个 →</n-button>
        </div>
      </div>
    </n-modal>

    <!-- PA 右键属性菜单：下载画师所有内容 -->
    <template v-if="paCtx.show">
      <div class="pa-ctx-backdrop" @click="paCtx.show = false" @contextmenu.prevent="paCtx.show = false"></div>
      <div
        class="pa-ctx-menu"
        :style="{ left: paCtx.x + 'px', top: paCtx.y + 'px' }"
      >
        <div class="pa-ctx-header" :title="paCtx.name">{{ paCtx.name || '画师' }}</div>
        <div class="pa-ctx-item" @click="paCtxDownloadArtist">
          <span class="pa-ctx-icon">⬇</span>
          <span>下载画师所有内容</span>
        </div>
        <div class="pa-ctx-item" @click="paCtxCopyLink">
          <span class="pa-ctx-icon">📋</span>
          <span>复制画师链接</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, h, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { NTag, NButton } from 'naive-ui'
import PaginationBar from './PaginationBar.vue'

const props = defineProps({
  settings: { type: Object, required: true },
  site: { type: String, default: 'bunkr' },
  searchMode: { type: String, default: 'artist' },
  searchQuery: { type: String, default: '' },
  searching: { type: Boolean, default: false },
  searchResults: { type: Array, required: true },
  searchHasMore: { type: Boolean, default: false },
  searchPage: { type: Number, default: 1 },
  searchTotalPages: { type: Number, default: 0 },
  searchTotalResults: { type: Number, default: 0 },
  inspecting: { type: Boolean, default: false },
  inspectProgress: { type: Object, required: true },
  albumInfo: { type: Object, required: true },
  fileList: { type: Array, required: true },
  cameFromSearch: { type: Boolean, default: false },
  downloading: { type: Boolean, default: false },
  downloadProgress: { type: Object, required: true },
  logs: { type: Array, required: true },
  history: { type: Array, required: true },
  // 本地媒体代理端口（在线播放：0=未就绪）
  mediaProxyPort: { type: Number, default: 0 },
  exhentaiUser: { type: String, default: '' },
  exGalleryDetail: { type: Object, default: null },   // EX 画廊详情（完整信息 + 分组标签）
  exDetailLoading: { type: Boolean, default: false }, // 详情加载中
  // EX 内联详情模式：从搜索结果/收藏点开作品时，搜索结果保留在上方，详情+文件列表追加在下方（不跳转新界面）
  exInlineDetail: { type: Boolean, default: false },
  exFavMode: { type: Boolean, default: false },       // 当前结果视图是否为"我的收藏"
  exBatchRunning: { type: Boolean, default: false },  // EX 批量解析进行中
  exBatchProgress: { type: Object, default: () => ({ done: 0, total: 0 }) }, // 批量进度 done/total
  // 批量收集视图锁定：批量下载收集过文件后不自动切到文件列表（静默后台下载，用户返回时解锁）
  batchFileCollected: { type: Boolean, default: false },
  paPostDetail: { type: Object, default: null },       // PA 帖子详情（完整信息 + 附件预览）
  paDetailLoading: { type: Boolean, default: false }, // PA 详情加载中
  paArtistPosts: { type: Object, default: null },      // PA 画师子项目列表（按发布日期的全部帖子）
  paArtistPostsLoading: { type: Boolean, default: false }, // 子项目列表加载中
  exHiddenTags: { type: Array, default: () => [] },    // EX 隐藏标签列表（长期保存）
  // X 关注视图（following=关注列表 / followers=关注我的人 / follows=我的分类
  // / user=用户详情 / browse=浏览模式；''=关闭）
  twFollowMode: { type: String, default: '' },
  twFollowLoading: { type: Boolean, default: false },
  twFollowItems: { type: Array, default: () => [] },
  twFollowHasMore: { type: Boolean, default: false },
  twFollowError: { type: String, default: '' },
  twFollowTags: { type: Array, default: () => [] },   // [{name, children: []}]
  twFollowLabel: { type: String, default: '' },       // 当前列表标题（如"@xxx 的关注列表"）
  twViewUser: { type: Object, default: null },        // 用户详情视图当前用户
  // X 浏览模式（最近博主更新）
  twBrowseFeed: { type: Array, default: () => [] },  // [{tweet_id, item_page, text, post_date, user, media: []}]
  twBrowseLoading: { type: Boolean, default: false },
  twBrowseProgress: { type: Object, default: () => ({ done: 0, total: 0 }) },
  twBrowseUpdatedAt: { type: Number, default: null },
  twBrowseError: { type: String, default: '' },
  twBrowseHasMore: { type: Boolean, default: false },  // 是否还有下一批博主
  // X 博主内容流（点开博主自动解析，详情页下方展示推文卡片）
  twUserFeed: { type: Array, default: () => [] },      // [{tweet_id, item_page, text, post_date, media: [], media_items: []}]
  twUserFeedLoading: { type: Boolean, default: false },
  twUserFeedHasMore: { type: Boolean, default: false },
  // X 本地搜索（搜缓存内容）
  twLocalSearch: { type: String, default: '' },
  twSearchTweets: { type: Array, default: () => [] }, // 搜索命中的推文卡片
  // Iwara 视图（''=搜索 | home=主页 | following=关注 | friends=好友 | detail=详情）
  iwView: { type: String, default: '' },
  iwSite: { type: String, default: 'iwara' },        // 'iwara' | 'ai'
  iwHomeItems: { type: Array, default: () => [] },   // 主页最近更新视频
  iwHomeLoading: { type: Boolean, default: false },
  iwHomeHasMore: { type: Boolean, default: false },
  iwHomeError: { type: String, default: '' },
  // 主页模式：''=最近更新 | 'subscribed'=我关注的更新（订阅流）
  iwHomeMode: { type: String, default: '' },
  iwFollowItems: { type: Array, default: () => [] }, // 我的关注用户
  iwFollowLoading: { type: Boolean, default: false },
  iwFollowHasMore: { type: Boolean, default: false },
  iwFollowError: { type: String, default: '' },
  iwFriendItems: { type: Array, default: () => [] }, // 我的好友用户
  iwFriendLoading: { type: Boolean, default: false },
  iwFriendHasMore: { type: Boolean, default: false },
  iwFriendError: { type: String, default: '' },
  iwDetail: { type: Object, default: null },         // 视频详情（含 body/tags/播放直链）
  iwDetailLoading: { type: Boolean, default: false },
  iwComments: { type: Array, default: () => [] },    // 详情页评论
  iwCommentsHasMore: { type: Boolean, default: false },
  // 批量解析下载进度（App.vue 从后端事件转发）
  iwBatchRunning: { type: Boolean, default: false },
  iwBatchProgress: { type: Object, default: () => ({ done: 0, total: 0, message: '' }) },
  // Hanime1 视图（''=搜索 | home=主页分区 | user=用户中心 | detail=详情）
  haView: { type: String, default: '' },
  haSections: { type: Array, default: () => [] },   // 主页分区 [{title, items: []}]
  haHomeLoading: { type: Boolean, default: false },
  haHomeError: { type: String, default: '' },
  haGenres: { type: Array, default: () => [] },     // 分类列表（裏番/3DCG/...）
  haSorts: { type: Array, default: () => [] },      // 排序列表（最新上市/本日排行/...）
  haDetail: { type: Object, default: null },        // 视频详情（含 video_url/tags/comments）
  haDetailLoading: { type: Boolean, default: false },
  haComments: { type: Array, default: () => [] },   // 详情页评论
  haUserTab: { type: String, default: '' },         // 用户中心 tab（history/saves/likes/uploaded/uploading）
  haUserItems: { type: Array, default: () => [] },  // 用户中心视频列表
  haUserLoading: { type: Boolean, default: false },
  haUserHasMore: { type: Boolean, default: false },
  haUserPage: { type: Number, default: 1 },         // 用户中心当前页码（加载更多用）
  haUserLabel: { type: String, default: '' },       // 当前 tab 中文名
  haBatchRunning: { type: Boolean, default: false },
  haBatchProgress: { type: Object, default: () => ({ done: 0, total: 0, message: '' }) },
  // Oreno3D / EroMMDTube 视图（''=搜索 | home=主页 | list=标签/角色/作者/原作/收藏列表
  // | characters=角色列表 | authors=人気作者列表 | detail=详情）
  orView: { type: String, default: '' },
  orHomeItems: { type: Array, default: () => [] },  // 主页视频卡片
  orHomeLoading: { type: Boolean, default: false },
  orHomeHasMore: { type: Boolean, default: false },
  orHomeError: { type: String, default: '' },
  orSorts: { type: Object, default: () => ({}) },   // 排序映射 {hot: '急上昇', ...}
  orList: { type: Object, default: () => ({ type: '', id: '', name: '', items: [], page: 1, has_more: false }) }, // 标签/角色/作者列表
  orListLoading: { type: Boolean, default: false },
  orListError: { type: String, default: '' },
  orTags: { type: Array, default: () => [] },       // 标签列表 [{id, name}]
  orTagGroups: { type: Array, default: () => [] },  // 热门分类组 [{id, name, count}]
  orTagGroupTitle: { type: String, default: '' },   // 非空 = 弹窗正在查看该分类组
  orTagsLoading: { type: Boolean, default: false },
  orCharacters: { type: Object, default: () => ({ popular: [], kana_groups: {} }) }, // 角色列表（人気+五十音）
  orCharsLoading: { type: Boolean, default: false },
  orAuthors: { type: Array, default: () => [] },    // 人気作者列表 [{id, name, rank}]
  orAuthorsPage: { type: Number, default: 1 },
  orAuthorsHasMore: { type: Boolean, default: false },
  orAuthorsLoading: { type: Boolean, default: false },
  orDetail: { type: Object, default: null },        // 视频详情（含 iwara 直链/作者/角色/原作/标签）
  orDetailLoading: { type: Boolean, default: false },
  orBatchRunning: { type: Boolean, default: false },
  orBatchProgress: { type: Object, default: () => ({ done: 0, total: 0, message: '' }) },
  // ASMR 音声站视图（''=搜索 | popular=热门 | works=媒体库/筛选 | favorites=收藏 | detail=详情）
  asmrView: { type: String, default: '' },
  asmrItems: { type: Array, default: () => [] },     // 当前列表作品卡片
  asmrListLoading: { type: Boolean, default: false },
  asmrHasMore: { type: Boolean, default: false },
  asmrError: { type: String, default: '' },
  asmrLabel: { type: String, default: '' },          // 当前列表标题（热门作品/媒体库/筛选名）
  asmrTotal: { type: Number, default: 0 },           // 筛选列表总数
  asmrOrders: { type: Object, default: () => ({}) }, // 可用排序 {value: label}
  asmrFilter: { type: Object, default: () => ({ kind: '', id: '', name: '' }) }, // 当前社团/标签/声优筛选
  // 社团/标签/声优索引弹窗数据
  asmrIndexItems: { type: Array, default: () => [] }, // [{id, name, count}]
  asmrIndexLoading: { type: Boolean, default: false },
  // 详情（含音轨文件列表 play_url 本地代理可播）
  asmrDetail: { type: Object, default: null },
  asmrFiles: { type: Array, default: () => [] },
  asmrDetailLoading: { type: Boolean, default: false },
  asmrLoggedIn: { type: Boolean, default: false },
  // 批量下载
  asmrBatchRunning: { type: Boolean, default: false },
  asmrBatchProgress: { type: Object, default: () => ({ done: 0, total: 0, message: '' }) },
  // 全局自动翻译（每站搜索结果常驻）
  autoTranslating: { type: Boolean, default: false },          // 翻译进行中（转圈动效）
  autoTranslateMode: { type: Boolean, default: false },        // 翻译已开启（后续内容自动翻译）
  translatedTitles: { type: Object, default: () => ({}) },     // {原标题: 译文}，展示时回填
  // 识图（反向图片搜索）：占用右侧内容区
  reverseActive: { type: Boolean, default: false },            // 识图视图激活（左侧识图按钮开关）
  reverseSites: { type: Array, default: () => [] },           // [{key,name,status,results,url,error}]
  reverseRunning: { type: Boolean, default: false },          // 搜索进行中
  // JavDB 视频详情（封面/预览图/磁力列表，非空 = 占用右侧内容区）
  javdbDetail: { type: Object, default: null },
  javdbDetailLoading: { type: Boolean, default: false },
  javdbBatchRunning: { type: Boolean, default: false },
  javdbBatchProgress: { type: Object, default: () => ({ done: 0, total: 0 }) },
})

const emit = defineEmits([
  'update:search-query',
  'update:site',
  'update:search-mode',
  'toggle-auto-translate-mode', // 翻译开关：开=翻译当前页+后续自动；关=停止并恢复原文
  'search',
  'load-more',
  'go-page',
  'open-album',
  'back-to-search',
  'download',
  'ctx-download-file',     // 右键菜单"下载此项"：静默添加单个文件到下载任务（参数：文件条目）
  'resolve-media',   // 在线播放：请求后端解析条目直链（参数：文件条目对象）
  'delete-history',
  'open-file',
  'show-folder',
  // ExHentai 事件（由 App.vue 转发给 Python 后端）
  'ex-get-torrents',        // 获取画廊种子列表（参数：画廊 URL）
  'ex-get-magnet',          // 获取磁力链接（参数：.torrent 文件 URL）
  'ex-parse-gallery',       // 解析当前 webview 中的画廊（参数：画廊 URL）
  'ex-sync-cookies',        // 同步 webview cookie 到后端（参数：cookie 字符串）
  'add-favorite',           // 快速收藏到本地（参数：搜索结果条目）
  'update:ex-search',       // ExHentai 搜索选项更新（分类/评分/种子/页数范围）
  'ex-favorites',           // 打开我的收藏（参数：页码）
  'ex-open-gallery',        // 打开画廊详情（参数：画廊 URL）
  'ex-batch-download',      // 批量下载选中画廊（参数：URL 数组，解析全部图片加入文件列表）
  'clear-batch-tasks',      // 清除批量任务（清空批量收集的文件列表并解锁视图）
  'ex-close-detail',        // 关闭画廊详情（返回搜索结果）
  'ex-save-torrent',        // 保存 .torrent 种子文件（参数：种子条目）
  'pa-open-post',           // 打开 PA 帖子详情（参数：帖子 URL）
  'pa-close-detail',        // 关闭 PA 帖子详情（返回搜索结果）
  'pa-favorites',           // PA 我的收藏（服务器收藏，需登录）
  'pa-home',                // PA 主页（全站最新帖子流）
  'pa-open-artist',         // 打开 PA 画师子项目列表（参数：画师 URL）
  'pa-close-artist',        // 关闭画师子项目视图（返回搜索结果）
  'pa-download-artist',     // 右键下载画师所有内容（参数：{url, name}，后台解析并提交下载任务）
  'ex-add-hidden-tag',      // EX 添加隐藏标签（参数：标签名）
  'ex-delete-hidden-tag',  // EX 删除隐藏标签（参数：标签名）
  // X (Twitter) 关注事件（由 App.vue 转发给 Python 后端）
  'tw-follow-list',         // 打开/切换/关闭关注视图（参数：'following' | 'followers' | 'follows' | ''）
  'tw-follow-load-more',    // 加载下一页关注列表
  'tw-follow',              // 关注用户（参数：用户条目）
  'tw-unfollow',            // 取消关注用户（参数：用户条目）
  'tw-set-follow-tag',      // 归类用户（参数：用户条目, 母类, 子类）
  'tw-open-user',           // 查看用户主页（参数：用户条目）
  'tw-user-list',           // 查看指定用户的关注/粉丝列表（参数：模式, screen_name）
  'tw-browse',              // 打开/刷新浏览模式（最近博主更新）
  'tw-browse-more',         // 浏览模式加载下一批博主
  'tw-user-feed-more',      // 博主内容流加载更多（下一页时间线）
  'tw-user-feed-download-all', // 一键下载博主内容流已加载的全部媒体
  'update:tw-local-search', // X 本地搜索关键词（v-model 式）
  'tw-back',                // X 视图内返回上一层
  // Iwara 事件（由 App.vue 转发给 Python 后端）
  'iw-set-site',            // IW站/AI站 切换（参数：'iwara' | 'ai'）
  'iw-home',                // 打开/刷新主页（参数：页码）
  'iw-home-more',           // 主页加载更多
  'iw-subscribed',          // 我关注的更新（订阅流，需登录）
  'iw-following',           // 打开我的关注（参数：页码）
  'iw-following-more',      // 关注列表加载更多
  'iw-friends',             // 打开我的好友（参数：页码）
  'iw-friends-more',        // 好友列表加载更多
  'iw-follow',              // 关注用户（参数：用户条目/详情对象）
  'iw-unfollow',            // 取消关注（参数：用户条目/详情对象）
  'iw-open-detail',         // 打开视频详情（参数：视频条目）
  'iw-detail-back',         // 关闭详情返回
  'iw-comments-more',      // 评论加载更多
  'iw-open-user',           // 查看用户主页（参数：username）
  'iw-search-tag',          // 点击 tag 搜索（参数：tag 名）
  'iw-batch-download',      // 批量解析下载（参数：{usernames: [], video_ids: []}）
  // Hanime1 事件（由 App.vue 转发给 Python 后端）
  'ha-home',                // 打开/刷新主页分区
  'ha-open-detail',         // 打开视频详情（参数：视频条目）
  'ha-detail-back',         // 关闭详情返回
  'hanime-add-comment',     // 发表评论（参数：{video_id, text}）
  'hanime-save-video',      // 收藏/取消收藏（参数：video_id, saved）
  'hanime-user-videos',     // 用户中心列表（参数：tab, 页码）
  'hanime-user-back',       // 用户中心返回主页
  'update:ha-search',       // H站搜索选项更新（分类/排序，v-model 式）
  'hanime-search-tag',      // 点击 tag 搜索（参数：tag 名）
  'hanime-batch-download',  // 批量解析下载（参数：[video_id]）
  // Oreno3D / EroMMDTube 事件（由 App.vue 转发给 Python 后端，均带 site_key）
  'or-home',                // 打开/刷新主页（参数：页码）
  'or-home-more',           // 主页加载更多
  'or-open-detail',         // 打开视频详情（参数：视频条目）
  'or-detail-back',         // 关闭详情返回
  'or-tag',                 // 打开标签列表（参数：tag_id）
  'or-author',              // 打开作者列表（参数：author_id）
  'or-character',           // 打开角色列表（参数：character_id）
  'or-origin',              // 打开原作列表（参数：origin_id）
  'or-list-back',           // 列表视图返回
  'or-list-more',           // 列表加载更多
  'or-tags-index',          // 打开热门分类弹窗（标签 + 分类组）
  'or-tag-group',           // 查看分类组内标签（参数：group_id）
  'or-characters',          // 打开角色列表视图（人気 + 五十音分组）
  'or-authors-index',       // 打开人気作者列表视图（参数：页码）
  'or-browse-back',         // 角色/作者浏览视图返回主页
  'or-favorites',           // 打开本地收藏列表
  'or-toggle-favorite',     // 收藏/取消收藏（参数：视频条目）
  'or-sort-update',         // 排序切换（参数：hot/favorites/latest/popularity）
  'or-batch-download',      // 批量解析下载（参数：[video_id]）
  // ASMR 音声站事件（由 App.vue 转发给 Python 后端）
  'asmr-popular',           // 打开/刷新热门作品（参数：页码）
  'asmr-works',             // 打开/刷新媒体库（参数：页码）
  'asmr-favorites',         // 打开我的收藏（参数：页码）
  'asmr-more',              // 当前列表加载更多
  'update:asmr-search',     // 排序/仅带字幕更新（v-model 式，参数：{asmr_order, asmr_subtitle}）
  'asmr-index',             // 打开社团/标签/声优索引弹窗（参数：'circles'|'tags'|'vas'）
  'asmr-index-pick',        // 点击索引项进入筛选列表（参数：kind, id, name）
  'asmr-open-detail',       // 打开作品详情（参数：作品条目）
  'asmr-detail-back',       // 关闭详情返回
  'asmr-toggle-favorite',   // 收藏/取消收藏（参数：作品条目）
  'asmr-search-tag',        // 点击 tag 搜索（参数：tag 名）
  'asmr-open-circle',       // 点击社团查看全部作品（参数：详情对象）
  'asmr-open-va',           // 点击声优查看作品（参数：详情对象）
  'asmr-batch-download',    // 批量下载（参数：[work_id]）
  // JavDB
  'javdb-open-detail',      // 点击搜索卡片打开视频详情（参数：条目对象）
  'javdb-detail-back',      // 关闭详情返回搜索结果
  'javdb-download-images',  // 下载封面+预览图（当前详情页）
  'javdb-batch-download',   // 批量下载（参数：URL 数组）
  // 识图（反向图片搜索）
  'reverse-search',        // 开始识图（参数：图片本地路径）
  'reverse-reset',         // 清空结果回到拖拽框
])

const checkedKeys = ref([])
const activeTab = ref('logs')
const tableHeight = ref(320)
const localFilter = ref('')

// 文件列表显示模式：list=横向详细表格 / grid=小方格
const viewMode = ref(localStorage.getItem('file_view_mode') || 'list')
// 切换显示模式（持久化到 localStorage）
function toggleViewMode() {
  viewMode.value = viewMode.value === 'grid' ? 'list' : 'grid'
  localStorage.setItem('file_view_mode', viewMode.value)
}
// 方格视图：点击卡片切换选中（与表格勾选行为一致）
function toggleGridSelect(itemPage) {
  const idx = checkedKeys.value.indexOf(itemPage)
  if (idx >= 0) checkedKeys.value.splice(idx, 1)
  else checkedKeys.value.push(itemPage)
}

// ============================
// 全局右键菜单：单个文件"下载此项"（静默添加到下载任务，不切换视图）
// ============================
const ctxMenu = ref({ show: false, x: 0, y: 0, file: null })
const ctxMenuOptions = [
  { key: 'download', label: '⬇ 下载此项', props: { title: '静默添加到下载任务并立即开始下载' } },
]

// 方格模式：右键文件卡片弹出菜单
function openFileCtxMenu(e, file) {
  ctxMenu.value = { show: true, x: e.clientX, y: e.clientY, file }
}

// 列表模式：data-table 行右键（rowProps 回调）
function fileRowProps(row) {
  return {
    onContextmenu: (e) => {
      e.preventDefault()
      openFileCtxMenu(e, row)
    },
  }
}

function onCtxMenuSelect(key) {
  const file = ctxMenu.value.file
  ctxMenu.value.show = false
  if (!file) return
  if (key === 'download') {
    emit('ctx-download-file', file)
  }
}

// 自动翻译：把原标题替换为译文（无译文回退原标题；空值返回 '未命名'）
function trTitle(name) {
  if (!name) return '未命名'
  return props.translatedTitles[name] || name
}


// ============================
// EX 隐藏标签管理面板
// ============================
const exHidePanel = ref(false)
const exHideTagInput = ref('')

// 添加隐藏标签（去重 + 转发后端保存并重新过滤）
function exAddHiddenTag() {
  const t = (exHideTagInput.value || '').trim()
  if (!t) return
  emit('ex-add-hidden-tag', t)
  exHideTagInput.value = ''
}

// ============================
// PA 画师子项目：悬浮详情提示
// ============================
function paPostTooltip(p) {
  if (!p) return ''
  const lines = [p.title || '未命名帖子']
  if (p.published) lines.push(`发布：${String(p.published).slice(0, 10)}`)
  if (p.file_count != null) lines.push(`文件数：${p.file_count}`)
  if (p.files && p.files.length) lines.push(`文件：${p.files.join('、')}`)
  if (p.content) lines.push(`内容：${p.content}`)
  return lines.join('\n')
}

// ============================
// X (Twitter) 关注分类弹窗
// ============================
const twTagModalVisible = ref(false)
const twTagModalUser = ref(null)
const twTagParent = ref(null)
const twTagChild = ref(null)

// 母类下拉选项（已保存的分类，支持输入新名称）
const twParentOptions = computed(() =>
  (props.twFollowTags || []).map(t => ({ label: t.name, value: t.name })),
)
// 子类下拉选项（跟随所选母类的子类列表）
const twChildOptions = computed(() => {
  const parent = (props.twFollowTags || []).find(t => t.name === twTagParent.value)
  return (parent && parent.children ? parent.children : []).map(c => ({ label: c, value: c }))
})

// 博主内容流已加载的媒体总数（"下载当前全部媒体"按钮显示用）
const twUserFeedMediaCount = computed(() => {
  const seen = new Set()
  for (const c of props.twUserFeed || []) {
    for (const it of (c.media_items || [])) {
      if (it.media_url) seen.add(it.media_url)
    }
  }
  return seen.size
})

function twOpenTagModal(user) {
  twTagModalUser.value = user
  // 预填当前归类（"母类/子类" 或仅有母类）
  const tag = user.follow_tag || user.tag || ''
  const [p, c] = tag.split('/')
  twTagParent.value = p || null
  twTagChild.value = c || null
  twTagModalVisible.value = true
}

function twSaveTag() {
  const parent = (twTagParent.value || '').trim()
  const child = (twTagChild.value || '').trim()
  if (!parent && !child) {
    twRemoveTag()
    return
  }
  emit('tw-set-follow-tag', twTagModalUser.value, parent, child)
  twTagModalVisible.value = false
}

function twRemoveTag() {
  emit('tw-set-follow-tag', twTagModalUser.value, '', '')
  twTagModalVisible.value = false
}

// Pawchive 搜索模式选项（画师 / 标签，区分两种搜索逻辑）
const searchModeOptions = [
  { label: '画师', value: 'artist' },
  { label: '标签', value: 'tag' },
]

// 判断输入是否为 Bunkr 链接
function isBunkrUrl(text) {
  return /bunkr\.\w+\/(a|f|i|v)\//i.test(text)
}

// 判断输入是否为 Coomer 链接（xxxcoomer.com 作者页/帖子页）
function isCoomerUrl(text) {
  return /xxxcoomer\.com\/(creator|post)\//i.test(text)
}

// 判断输入是否为 Pawchive 链接（pawchive.pw 画师页/帖子页）
function isPawchiveUrl(text) {
  return /pawchive\.pw\/[\w-]+\/user\/\d+/i.test(text)
}

// 判断输入是否为 ExHentai 画廊链接（exhentai.org / e-hentai.org）
function isExhentaiUrl(text) {
  return /(e-hentai|exhentai)\.org\/g\/\d+\/[0-9a-f]+/i.test(text)
}

// 判断输入是否为 Twitter/X 链接（x.com / twitter.com 用户页或推文页）
function isTwitterUrl(text) {
  return /^https?:\/\/(www\.)?(x|twitter)\.com\/[^/?#]+(\/status\/\d+)?\/?/i.test((text || '').trim())
}

// 判断输入是否为站点直链（决定按钮显示"解析"还是"搜索"）
const isUrl = computed(() => {
  return isBunkrUrl(props.searchQuery) || isCoomerUrl(props.searchQuery)
    || isPawchiveUrl(props.searchQuery) || isExhentaiUrl(props.searchQuery)
    || isTwitterUrl(props.searchQuery)
})

// ============================
// ExHentai 浏览器视图（webview）
// ============================
const exWebviewRef = ref(null)
const exViewMode = ref('search')  // browser | search（默认搜索列表，点"浏览器"切换 webview）
const exAddress = ref('https://exhentai.org/')
const exLoading = ref(false)
const exNavState = ref({ canBack: false, canForward: false })
const cookieSyncing = ref(false)
const torrentLoading = ref(false)
const magnetLoading = ref(false)
const torrentModalVisible = ref(false)
const torrentList = ref([])
const currentMagnet = ref('')
// 当前 webview 地址（did-navigate 更新，与输入框同步）
const exCurrentUrl = ref('https://exhentai.org/')

// EX 站点发起搜索时自动切到"搜索结果"视图
watch(() => props.searching, (v) => {
  if (v && props.site === 'exhentai') exViewMode.value = 'search'
})

// 切回浏览器视图（正在看文件列表时先清空返回）
function exShowBrowser() {
  exViewMode.value = 'browser'
  if (props.fileList.length > 0) {
    emit('back-to-search')
  }
}

// 当前 webview 地址是否为画廊页（决定"解析画廊/磁力"按钮可用）
const exIsGallery = computed(() => isExhentaiUrl(exCurrentUrl.value))

// webview 导航完成：同步地址栏和前进/后退状态
function onExNavigated(e) {
  const url = e.url || ''
  if (url && url !== 'about:blank') {
    exCurrentUrl.value = url
    exAddress.value = url
  }
  const wv = exWebviewRef.value
  if (wv) {
    exNavState.value = {
      canBack: wv.canGoBack(),
      canForward: wv.canGoForward(),
    }
  }
}

// 浏览器导航操作
function exNav(action) {
  const wv = exWebviewRef.value
  if (!wv) return
  if (action === 'back' && wv.canGoBack()) wv.goBack()
  else if (action === 'forward' && wv.canGoForward()) wv.goForward()
  else if (action === 'reload') wv.reload()
  else if (action === 'home') wv.loadURL('https://exhentai.org/')
}

// 地址栏回车跳转
function exNavigateToAddress() {
  const wv = exWebviewRef.value
  let url = (exAddress.value || '').trim()
  if (!wv || !url) return
  if (!/^https?:\/\//i.test(url)) {
    url = 'https://' + url.replace(/^\/+/, '')
  }
  // 只允许 exhentai/e-hentai 域名（防止跳到其他网站）
  if (!/(e-hentai|exhentai)\.org/i.test(url)) {
    url = 'https://exhentai.org/'
  }
  wv.loadURL(url)
}

// 解析当前画廊（触发后端 inspect）
function exParseGallery() {
  if (!exIsGallery.value) return
  emit('ex-parse-gallery', exCurrentUrl.value)
}

// 打开磁力弹窗（获取种子列表）
function exShowTorrents() {
  if (!exIsGallery.value) return
  torrentModalVisible.value = true
  torrentList.value = []
  currentMagnet.value = ''
  torrentLoading.value = true
  emit('ex-get-torrents', exCurrentUrl.value)
}

// 画廊详情视图的种子按钮（参数：画廊 URL，不依赖 webview）
function exDetailTorrents(url) {
  if (!url) return
  torrentModalVisible.value = true
  torrentList.value = []
  currentMagnet.value = ''
  torrentLoading.value = true
  emit('ex-get-torrents', url)
}

// 同步 webview cookie 给后端（保持登录状态）
async function exSyncCookies() {
  cookieSyncing.value = true
  try {
    if (window.api) {
      const result = await window.api.exGetCookies()
      if (result && result.cookieStr) {
        emit('ex-sync-cookies', result.cookieStr)
      } else {
        // 无 cookie 时也触发一次（后端会提示未登录）
        emit('ex-sync-cookies', '')
      }
    }
  } finally {
    setTimeout(() => { cookieSyncing.value = false }, 500)
  }
}

// 获取某个种子的磁力链接
function handleGetMagnet(torrent) {
  magnetLoading.value = true
  currentMagnet.value = ''
  emit('ex-get-magnet', torrent.url)
}

// 复制磁力链接
async function copyMagnet() {
  try {
    await navigator.clipboard.writeText(currentMagnet.value)
  } catch (e) {
    // 剪贴板 API 不可用时的兜底
    const input = document.createElement('textarea')
    input.value = currentMagnet.value
    document.body.appendChild(input)
    input.select()
    document.execCommand('copy')
    document.body.removeChild(input)
  }
}

// 用系统默认下载器打开磁力链接
async function openMagnet() {
  if (window.api) {
    await window.api.openExternal(currentMagnet.value)
  }
}

// ============================
// ExHentai 搜索选项（复刻原版搜索页过滤按钮）
// ============================
// 分类（key 与后端 EXHENTAI_CATEGORIES 对应，f_cats 位掩码）
const exCategories = [
  { key: 'misc', label: '杂项' },
  { key: 'doujinshi', label: '同人志' },
  { key: 'manga', label: '漫画' },
  { key: 'artistcg', label: '艺术家CG' },
  { key: 'gamecg', label: '游戏CG' },
  { key: 'imageset', label: '图集' },
  { key: 'cosplay', label: 'Cosplay' },
  { key: 'asianporn', label: '亚洲色情' },
  { key: 'nonh', label: '非H' },
  { key: 'western', label: '西方' },
]

const exRatingOptions = [
  { label: '不限', value: 0 },
  { label: '2 星', value: 2 },
  { label: '3 星', value: 3 },
  { label: '4 星', value: 4 },
  { label: '5 星', value: 5 },
]

// 已勾选分类（旧配置无该字段时视为全选）
const exCats = computed(() => {
  const cats = props.settings.exhentai_cats
  if (Array.isArray(cats) && cats.length > 0) return cats
  return exCategories.map(c => c.key)
})
const exMinRating = computed(() => Number(props.settings.exhentai_min_rating) || 0)
const exTorrentsOnly = computed(() => !!props.settings.exhentai_torrents_only)
const exPageMin = computed(() => Number(props.settings.exhentai_page_min) || 0)
const exPageMax = computed(() => Number(props.settings.exhentai_page_max) || 0)

// 选项变更 → 通知 App.vue 存设置并自动重新搜索
function emitExSearch(opts) {
  emit('update:ex-search', opts)
}

function exToggleCat(key) {
  const cur = [...exCats.value]
  const i = cur.indexOf(key)
  if (i >= 0) cur.splice(i, 1)
  else cur.push(key)
  emitExSearch({ exhentai_cats: cur })
}

function exSelectAllCats() {
  emitExSearch({ exhentai_cats: exCategories.map(c => c.key) })
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
// ExHentai 搜索结果（复刻原版布局）
// ============================
// 显示模式：列表（原版 List）/ 缩略图（原版 Thumbnail）
const exDisplayMode = ref('list')
// 列表模式勾选的画廊（批量收藏，对应原版复选框逻辑）
const exChecked = ref([])
// EX 画廊信息内联面板展开状态（文件列表视图下保留元数据可见）
const showExGalleryInfo = ref(true)

// 换页/新结果时清空勾选
watch(() => props.searchResults, () => { exChecked.value = [] })

// 批量收藏勾选的画廊
function batchFavoriteEx() {
  const selected = props.searchResults.filter(i => exChecked.value.includes(i.album_url))
  selected.forEach(i => handleQuickFavorite(i))
  exChecked.value = []
}

// 全选当前页画廊
function exCheckAll() {
  exChecked.value = props.searchResults.map(i => i.album_url).filter(Boolean)
}

// 反选：未选中的变为选中，已选中的取消
function exInvertCheck() {
  const all = props.searchResults.map(i => i.album_url).filter(Boolean)
  exChecked.value = all.filter(u => !exChecked.value.includes(u))
}

// 点击标签搜索（原版标签点击 = 按该命名空间搜索）
function searchTag(t) {
  if (!t) return
  // Pawchive：标签必须切到"标签"搜索模式才有效
  if (props.site === 'pawchive' && props.searchMode !== 'tag') {
    emit('update:search-mode', 'tag')
  }
  emit('update:search-query', t)
  emit('search')
}

// PA 卡片点击分流：帖子卡片 → 帖子详情；画师卡片 → 子项目列表（按日期浏览全部帖子）
function handlePaCardClick(item) {
  if (!item || !item.album_url) return
  if (item.album_url.includes('/post/')) {
    emit('pa-open-post', item.album_url)
  } else {
    emit('pa-open-artist', item.album_url)
  }
}

// ============================
// PA 右键属性菜单（下载画师所有内容）
// ============================
const paCtx = ref({ show: false, x: 0, y: 0, url: '', name: '' })

// 右键打开菜单：帖子卡片截断 /post/ 部分得到画师主页；画师卡片直接使用
function openPaContextMenu(e, item) {
  if (!item || !item.album_url) return
  const url = item.album_url
  const artistUrl = url.includes('/post/') ? url.split('/post/')[0] : url
  const vw = window.innerWidth || 1200
  const vh = window.innerHeight || 800
  paCtx.value = {
    show: true,
    // 菜单尺寸约 200x110，防溢出屏幕
    x: Math.max(8, Math.min(e.clientX, vw - 210)),
    y: Math.max(8, Math.min(e.clientY, vh - 120)),
    url: artistUrl,
    name: item.album_name || '',
  }
}

function paCtxDownloadArtist() {
  const ctx = paCtx.value
  ctx.show = false
  if (!ctx.url) return
  emit('pa-download-artist', { url: ctx.url, name: ctx.name })
}

async function paCtxCopyLink() {
  const ctx = paCtx.value
  ctx.show = false
  if (!ctx.url) return
  try {
    await navigator.clipboard.writeText(ctx.url)
  } catch {
    /* 剪贴板不可用时静默失败（点击内容自动复制的场景已有提示） */
  }
}

// 数字千分位
function formatCount(n) {
  if (!n || n <= 0) return '0'
  return Number(n).toLocaleString('zh-CN')
}

// ============================
// X 关注名单本地搜索（快速检索已缓存的人）
// ============================
const followSearch = ref('')
// 按昵称 / @推特号 / 简介 / 分类过滤当前列表（纯前端过滤已加载的条目）
const filteredFollowItems = computed(() => {
  const kw = (followSearch.value || '').trim().toLowerCase()
  if (!kw) return props.twFollowItems
  return props.twFollowItems.filter(u => {
    const fields = [
      u.name || '',
      u.screen_name || '',
      u.description || '',
      u.follow_tag || '',
      u.tag || '',
    ]
    return fields.some(f => (f || '').toLowerCase().includes(kw))
  })
})
// 切换列表模式时清空搜索（不同列表共用一个搜索框）
watch(() => props.twFollowMode, () => { followSearch.value = '' })

// 浏览模式缓存时间戳 → 可读文本
function formatTwTime(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const pad = v => String(v).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// Iwara 相对时间：xx 天/小时/分钟前（createdAt 为 ISO 字符串）
function iwTimeAgo(iso) {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (!t) return ''
  const m = Math.floor((Date.now() - t) / 60000)
  if (m < 1) return '刚刚'
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} 小时前`
  const d = Math.floor(h / 24)
  if (d < 30) return `${d} 天前`
  const mo = Math.floor(d / 30)
  if (mo < 12) return `${mo} 个月前`
  return `${Math.floor(mo / 12)} 年前`
}

// Iwara 视频时长秒数 → mm:ss
function iwDuration(sec) {
  const s = Math.floor(Number(sec) || 0)
  if (!s) return ''
  const mm = Math.floor(s / 60)
  const ss = String(s % 60).padStart(2, '0')
  return `${mm}:${ss}`
}

// Iwara 批量解析下载：勾选模式（主页勾视频 / 关注好友勾用户）
const iwBatchMode = ref(false)
const iwBatchChecked = ref(new Set())

function toggleIwBatch() {
  iwBatchMode.value = !iwBatchMode.value
  if (!iwBatchMode.value) iwBatchChecked.value = new Set()
}

function toggleIwBatchItem(key) {
  if (!key) return
  const next = new Set(iwBatchChecked.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  iwBatchChecked.value = next
}

// 开始下载：按当前视图收集勾选内容（关注/好友 → 用户名；主页 → 视频 ID），交给 App.vue 转发后端
function startIwBatch() {
  const usernames = []
  const video_ids = []
  if (iwView.value === 'following' || iwView.value === 'friends') {
    const items = iwView.value === 'friends' ? iwFriendItems.value : iwFollowItems.value
    for (const u of items) {
      if (iwBatchChecked.value.has(u.username)) usernames.push(u.username)
    }
  } else if (iwView.value === 'home') {
    for (const item of iwHomeItems.value) {
      if (item.video_id && iwBatchChecked.value.has(item.video_id)) video_ids.push(item.video_id)
    }
  }
  if (!usernames.length && !video_ids.length) return
  emit('iw-batch-download', { usernames, video_ids })
  iwBatchMode.value = false
  iwBatchChecked.value = new Set()
}

// ============================
// Hanime1 (H站) 搜索选项 / 评论 / 批量下载
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

// H站批量解析下载：勾选模式（主页分区/用户中心/搜索结果均按 video_id 勾选）
const haBatchMode = ref(false)
const haBatchChecked = ref(new Set())

function toggleHaBatch() {
  haBatchMode.value = !haBatchMode.value
  if (!haBatchMode.value) haBatchChecked.value = new Set()
}

function toggleHaBatchItem(videoId) {
  if (!videoId) return
  const next = new Set(haBatchChecked.value)
  if (next.has(videoId)) next.delete(videoId)
  else next.add(videoId)
  haBatchChecked.value = next
}

// 开始下载：收集当前视图勾选的视频 ID，交给 App.vue 转发后端
function startHaBatch() {
  const ids = []
  if (props.haView === 'home') {
    for (const sec of (props.haSections || [])) {
      for (const item of (sec.items || [])) {
        if (item.video_id && haBatchChecked.value.has(item.video_id)) ids.push(item.video_id)
      }
    }
  } else if (props.haView === 'user') {
    for (const item of props.haUserItems) {
      if (item.video_id && haBatchChecked.value.has(item.video_id)) ids.push(item.video_id)
    }
  } else {
    for (const item of props.searchResults) {
      if (item.video_id && haBatchChecked.value.has(item.video_id)) ids.push(item.video_id)
    }
  }
  if (!ids.length) return
  emit('hanime-batch-download', ids)
  haBatchMode.value = false
  haBatchChecked.value = new Set()
}

// ============================
// Oreno3D (O3D) / EroMMDTube (E站) 排序 / 热门分类 / 角色作者浏览 / 批量下载
// ============================
// 双站共用一套视图（oreno3d / erommdtube）
const isOrenoSite = computed(() => props.site === 'oreno3d' || props.site === 'erommdtube')
// 当前站点显示名（主页/搜索结果标题用）
const orSiteLabel = computed(() => (props.site === 'erommdtube' ? 'EroMMDTube' : 'Oreno3D'))

// 排序下拉选项（后端 ORENO_SORTS：hot=急上昇/favorites=高評価/latest=新着/popularity=人気）
const orSortOptions = computed(() => {
  const map = props.orSorts || {}
  return Object.keys(map).map(k => ({ label: map[k], value: k }))
})

// 主页标题当前排序中文名
const orSortLabel = computed(() => (props.orSorts || {})[props.settings.oreno_sort || 'hot'] || '人気')

// 列表视图标题（按列表类型显示 图标+名称）
const orListTitle = computed(() => {
  const name = props.orList.name || ''
  const t = props.orList.type
  if (t === 'author') return `👤 ${name || '作者'}`
  if (t === 'character') return `🎭 ${name || '角色'}`
  if (t === 'origin') return `🎬 ${name || '原作'}`
  if (t === 'favorites') return `♥ ${name || '我的收藏'}`
  return `🏷 ${name || '标签'}`
})

// 列表视图刷新（按列表类型分发对应命令）
function refreshOrList() {
  const id = props.orList.id
  const t = props.orList.type
  if (t === 'author') emit('or-author', id)
  else if (t === 'character') emit('or-character', id)
  else if (t === 'origin') emit('or-origin', id)
  else if (t === 'favorites') emit('or-favorites')
  else emit('or-tag', id)
}

// 时长秒数 → mm:ss（与 Iwara 同规则）
function orDuration(sec) {
  return iwDuration(sec)
}

// 在系统浏览器打开 iwara 原站链接
function openOrExternal(url) {
  if (!url) return
  if (window.api && window.api.openExternal) window.api.openExternal(url)
  else window.open(url, '_blank')
}

// ============================
// 识图（反向图片搜索）：拖拽/选择图片 → 通知后端并发查询全部识图网站
// ============================
const reverseDragOver = ref(false)
const reverseFileInput = ref(null)

// 已成功返回的站点（失效/失败站点直接不展示）
const reverseDoneSites = computed(() => (props.reverseSites || []).filter(s => s.status === 'done'))
const reverseTotalCount = computed(() =>
  reverseDoneSites.value.reduce((n, s) => n + (s.results || []).length, 0))

// 从 File 对象取真实路径（Electron 30 需 webUtils）
function _reversePathFromFile(file) {
  if (!file) return ''
  try {
    if (window.api && window.api.getPathForFile) return window.api.getPathForFile(file)
  } catch (e) { /* ignore */ }
  return file.path || ''
}

function handleReverseDrop(e) {
  reverseDragOver.value = false
  const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]
  if (!file) return
  if (file.type && !file.type.startsWith('image/')) {
    emit('reverse-reset')
    return
  }
  const p = _reversePathFromFile(file)
  if (!p) return
  emit('reverse-search', p)
}

function reversePickFile() {
  reverseFileInput.value && reverseFileInput.value.click()
}

function handleReversePick(e) {
  const file = e.target.files && e.target.files[0]
  if (!file) return
  const p = _reversePathFromFile(file)
  if (!p) return
  emit('reverse-search', p)
}

function reverseOpenExternal(url) {
  if (!url) return
  if (window.api && window.api.openExternal) window.api.openExternal(url)
  else window.open(url, '_blank')
}

function reverseCopyText(text) {
  if (!text) return
  if (navigator.clipboard) navigator.clipboard.writeText(text)
}

// 热门分类弹窗（打开时向后端请求 分类组 + 全部标签）
const orTagsModal = ref(false)
const orTagsFilter = ref('')

const filteredOrTags = computed(() => {
  const q = (orTagsFilter.value || '').trim().toLowerCase()
  const tags = props.orTags || []
  if (!q) return tags
  return tags.filter(t => String(t.name || '').toLowerCase().includes(q))
})

const filteredOrGroups = computed(() => {
  const q = (orTagsFilter.value || '').trim().toLowerCase()
  const groups = props.orTagGroups || []
  if (!q) return groups
  return groups.filter(g => String(g.name || '').toLowerCase().includes(q))
})

function showOrTags() {
  orTagsModal.value = true
  orTagsFilter.value = ''
  emit('or-tags-index')
}

function pickOrTag(t) {
  if (!t || !t.id) return
  orTagsModal.value = false
  emit('or-tag', t.id)
}

// ============================
// 角色列表视图：五十音分组 tab
// ============================
const orKanaRow = ref('')
// 全部五十音行（あ/か/さ/...，来自后端 kana_groups 键）
const orKanaRows = computed(() => Object.keys((props.orCharacters && props.orCharacters.kana_groups) || {}))
// 当前生效的行（未选/失效时取第一行）
const orKanaActive = computed(() => {
  if (orKanaRow.value && orKanaRows.value.includes(orKanaRow.value)) return orKanaRow.value
  return orKanaRows.value[0] || ''
})
// 当前行的角色列表
const orKanaList = computed(() => {
  const groups = (props.orCharacters && props.orCharacters.kana_groups) || {}
  return groups[orKanaActive.value] || []
})
// 新数据到达时重置选中行
watch(() => props.orCharacters, () => { orKanaRow.value = '' })

// O3D 批量解析下载：勾选模式（主页/标签作者列表/搜索结果均按 video_id 勾选）
const orBatchMode = ref(false)
const orBatchChecked = ref(new Set())

function toggleOrBatch() {
  orBatchMode.value = !orBatchMode.value
  if (!orBatchMode.value) orBatchChecked.value = new Set()
}

function toggleOrBatchItem(videoId) {
  if (!videoId) return
  const next = new Set(orBatchChecked.value)
  if (next.has(videoId)) next.delete(videoId)
  else next.add(videoId)
  orBatchChecked.value = next
}

// 开始下载：收集当前视图勾选的视频 ID，交给 App.vue 转发后端（iwara 源最高画质）
function startOrBatch() {
  const ids = []
  if (props.orView === 'home') {
    for (const item of props.orHomeItems) {
      if (item.video_id && orBatchChecked.value.has(item.video_id)) ids.push(item.video_id)
    }
  } else if (props.orView === 'list') {
    for (const item of (props.orList && props.orList.items) || []) {
      if (item.video_id && orBatchChecked.value.has(item.video_id)) ids.push(item.video_id)
    }
  } else {
    for (const item of props.searchResults) {
      if (item.video_id && orBatchChecked.value.has(item.video_id)) ids.push(item.video_id)
    }
  }
  if (!ids.length) return
  emit('or-batch-download', ids)
  orBatchMode.value = false
  orBatchChecked.value = new Set()
}

// ============================
// ASMR 音声站：排序 / 索引弹窗 / 批量下载 / 音频播放器
// ============================
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

// 卡片悬浮提示（社团/评分/下载数/字幕/标签）
function asmrCardTooltip(item) {
  const lines = [item.album_name || '未命名']
  if (item.author) lines.push(`社团: ${item.author}`)
  if (item.rating != null) lines.push(`评分: ★${item.rating}`)
  if (item.views != null) lines.push(`下载数: ${formatCount(item.views)}`)
  if (item.duration) lines.push(`时长: ${item.duration} 分钟`)
  if (item.has_subtitle) lines.push('带中文字幕')
  if (item.tags && item.tags.length) lines.push(`标签: ${item.tags.join(' ')}`)
  lines.push(props.asmrBatchMode ? '点击勾选/取消勾选' : '点击查看音轨列表并试听')
  return lines.join('\n')
}

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

// 批量下载：勾选模式（列表视图/搜索结果均按 video_id 勾选）
const asmrBatchMode = ref(false)
const asmrBatchChecked = ref(new Set())

function toggleAsmrBatch() {
  asmrBatchMode.value = !asmrBatchMode.value
  if (!asmrBatchMode.value) asmrBatchChecked.value = new Set()
}

function toggleAsmrBatchItem(workId) {
  if (!workId) return
  const next = new Set(asmrBatchChecked.value)
  if (next.has(workId)) next.delete(workId)
  else next.add(workId)
  asmrBatchChecked.value = next
}

function startAsmrBatch() {
  const ids = []
  if (props.asmrView) {
    for (const item of props.asmrItems) {
      if (item.video_id && asmrBatchChecked.value.has(item.video_id)) ids.push(item.video_id)
    }
  } else {
    for (const item of props.searchResults) {
      if (item.video_id && asmrBatchChecked.value.has(item.video_id)) ids.push(item.video_id)
    }
  }
  if (!ids.length) return
  emit('asmr-batch-download', ids)
  asmrBatchMode.value = false
  asmrBatchChecked.value = new Set()
}

// JavDB 批量下载：当前页全部视频（弹母文件夹命名弹窗，与 EX 批量下载同交互）
function startJavdbBatch() {
  const urls = props.searchResults.map(i => i.album_url).filter(u => u)
  if (!urls.length) return
  emit('javdb-batch-download', urls)
}

// 详情作品属性（description 为 dict）
const asmrDescEntries = computed(() => {
  const d = (props.asmrDetail && props.asmrDetail.description) || {}
  return Object.keys(d).filter(k => d[k] != null && d[k] !== '').map(k => ({
    key: k, value: String(d[k]),
  }))
})

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
// 内置音频播放器（连续自动播放 + 快进/倒带 + 音量记忆）
// ============================
const asmrAudioRef = ref(null)
const asmrPlayingFile = ref(null)   // 当前播放的音轨对象
const asmrPlayingIndex = ref(0)     // 在音频列表中的序号
const asmrAudioPaused = ref(true)
const asmrAudioMuted = ref(true)    // 默认静音（音量记忆在 localStorage）
const asmrTimeText = ref('0:00 / 0:00')

// 音量（0-1）：记忆到 localStorage，默认 0.8
const asmrVolume = ref(Number(localStorage.getItem('asmr_volume')) || 0.8)
const asmrVolumePercent = computed(() => Math.round((asmrVolume.value || 0) * 100))

// 仅音频文件（连续播放按此列表推进）
const asmrAudioFiles = computed(() => (props.asmrFiles || []).filter(f => f.type === 'audio' && f.play_url))
const asmrHasPrev = computed(() => asmrPlayingIndex.value > 0)
const asmrHasNext = computed(() => asmrPlayingIndex.value < asmrAudioFiles.value.length - 1)

// 同步音量/静音到 <audio>
watch([asmrVolume, asmrAudioMuted], () => {
  const el = asmrAudioRef.value
  if (!el) return
  el.volume = asmrVolume.value
  el.muted = asmrAudioMuted.value
})

// 点击音轨播放（连续自动播放下一轨）
function playAsmrFile(file) {
  if (!file || !file.play_url) return
  const idx = asmrAudioFiles.value.indexOf(file)
  if (idx < 0) return
  asmrPlayingFile.value = file
  asmrPlayingIndex.value = idx
  nextTick(() => {
    const el = asmrAudioRef.value
    if (!el) return
    el.volume = asmrVolume.value
    el.muted = asmrAudioMuted.value
    el.play().then(() => { asmrAudioPaused.value = false }).catch(() => {
      // 自动播放受限（默认静音一般可播；失败提示用户手动点播放）
      asmrAudioPaused.value = true
    })
  })
}

// 相对当前曲目跳转（-1 上一轨 / +1 下一轨）
function playAsmrOffset(step) {
  const list = asmrAudioFiles.value
  const target = asmrPlayingIndex.value + step
  if (target < 0 || target >= list.length) return
  playAsmrFile(list[target])
}

// 播放 / 暂停
function toggleAsmrPlay() {
  const el = asmrAudioRef.value
  if (!el) return
  if (el.paused) {
    el.play().then(() => { asmrAudioPaused.value = false }).catch(() => {})
  } else {
    el.pause()
    asmrAudioPaused.value = true
  }
}

// 快进 / 倒带（秒数来自设置，默认快进 30 秒倒带 5 秒）
function asmrSeekBy(dir) {
  const el = asmrAudioRef.value
  if (!el) return
  const sec = dir > 0
    ? Number(props.settings.asmr_seek_forward) || 30
    : Number(props.settings.asmr_seek_back) || 5
  el.currentTime = Math.max(0, Math.min((el.duration || 0), el.currentTime + dir * sec))
}

// 静音切换（音量记忆）
function toggleAsmrMute() {
  asmrAudioMuted.value = !asmrAudioMuted.value
  localStorage.setItem('asmr_muted', asmrAudioMuted.value ? '1' : '0')
}

// 拖动音量条：更新音量并记忆；拖离 0 时自动取消静音
function onAsmrVolumeInput(e) {
  const v = Math.max(0, Math.min(100, Number(e.target.value) || 0)) / 100
  asmrVolume.value = v
  localStorage.setItem('asmr_volume', String(v))
  if (v > 0) {
    asmrAudioMuted.value = false
    localStorage.setItem('asmr_muted', '0')
  }
}

// 一轨播完自动播下一轨
function onAsmrEnded() {
  if (asmrHasNext.value) playAsmrOffset(1)
  else asmrAudioPaused.value = true
}

function onAsmrTimeUpdate() {
  const el = asmrAudioRef.value
  if (!el) return
  const fmt = s => {
    s = Math.floor(s || 0)
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
  }
  asmrTimeText.value = `${fmt(el.currentTime)} / ${fmt(el.duration)}`
}

function onAsmrAudioError() {
  asmrAudioPaused.value = true
}

// 关闭播放器
function stopAsmrPlayer() {
  const el = asmrAudioRef.value
  if (el) el.pause()
  asmrPlayingFile.value = null
  asmrAudioPaused.value = true
  asmrTimeText.value = '0:00 / 0:00'
}

// 详情数据刷新时停掉旧播放器
watch(() => props.asmrFiles, () => stopAsmrPlayer())

// 恢复上次静音状态（首次默认静音）
onMounted(() => {
  const saved = localStorage.getItem('asmr_muted')
  if (saved != null) asmrAudioMuted.value = saved === '1'
})

// 当前文件列表是否为 Pawchive 内容（显示画师内过滤框）
const isPawchiveList = computed(() => {
  return props.site === 'pawchive' && props.fileList.some(f => f.site === 'pawchive')
})

// 画师内 tag/关键词过滤：匹配帖子标题或文件名
const filteredFileList = computed(() => {
  const q = (localFilter.value || '').trim().toLowerCase()
  if (!q) return props.fileList
  return props.fileList.filter(f => {
    const title = (f.post_title || '').toLowerCase()
    const name = (f.filename || '').toLowerCase()
    return title.includes(q) || name.includes(q)
  })
})

// ============================
// 在线预览 / 播放（图片 + 视频，所有站点通用）
// ============================
const previewVisible = ref(false)
const previewItem = ref(null)   // 引用 fileList 条目对象（media_url 解析后自动刷新）
// 预览视频音量持久化（默认静音，用户取消静音/调音量后记忆到 localStorage，下次沿用）
const previewVideoRef = ref(null)
const previewMuted = ref(localStorage.getItem('preview_muted') !== '0')   // 默认静音 true
const previewVolume = ref(Number(localStorage.getItem('preview_volume')) || 1)  // 0~1，默认 1
const previewVolumePercent = computed(() => Math.round((previewVolume.value || 0) * 100))
function applyPreviewVolume() {
  const el = previewVideoRef.value
  if (!el) return
  el.muted = previewMuted.value
  try { el.volume = previewVolume.value } catch (e) {}
}
function onPreviewVolumeChange(e) {
  const el = e.target
  if (!el) return
  previewMuted.value = el.muted
  previewVolume.value = el.volume
  localStorage.setItem('preview_muted', el.muted ? '1' : '0')
  localStorage.setItem('preview_volume', String(el.volume))
}
function togglePreviewMute() {
  previewMuted.value = !previewMuted.value
  localStorage.setItem('preview_muted', previewMuted.value ? '1' : '0')
  const el = previewVideoRef.value
  if (el) el.muted = previewMuted.value
}
function onPreviewVolumeInput(e) {
  const p = Number(e.target.value) / 100
  previewVolume.value = p
  localStorage.setItem('preview_volume', String(p))
  const el = previewVideoRef.value
  if (el) {
    try { el.volume = p } catch (e2) {}
    if (p > 0 && el.muted) {
      el.muted = false
      previewMuted.value = false
      localStorage.setItem('preview_muted', '0')
    }
  }
}

const VIDEO_EXTS = ['mp4', 'webm', 'mkv', 'mov', 'avi', 'm4v', 'ts', 'flv', 'wmv']
const IMAGE_EXTS = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'avif', 'jfif']

function extOf(item) {
  const src = item.filename || item.media_url || item.thumbnail || ''
  const m = String(src).toLowerCase().match(/\.([a-z0-9]{2,5})(?:\?|$)/)
  return m ? m[1] : ''
}
function isVideoItem(item) {
  return VIDEO_EXTS.includes(extOf(item))
}
function isImageItem(item) {
  if (isVideoItem(item)) return false
  const e = extOf(item)
  if (e) return IMAGE_EXTS.includes(e)
  // 无扩展名：有缩略图按图片处理
  return !!(item.thumbnail && !String(item.thumbnail).includes('video'))
}
// 可预览条目（图片或视频）
const previewableList = computed(() => filteredFileList.value.filter(f =>
  f.status !== 'fetch_failed' && (isImageItem(f) || isVideoItem(f))
))
// Bunkr/EX 需要懒解析：无 media_url 时发给后端解析
function ensureMediaUrl(item) {
  if (item && !item.media_url && !item.media_resolving && !item.media_resolve_failed) {
    emit('resolve-media', item)
  }
}
// 远端直链 → 本地代理 URL（走 cookie/代理，国内可播）
function proxied(url) {
  if (!url) return ''
  if (!props.mediaProxyPort) return url
  if (url.startsWith('thumb://') || url.startsWith('http://127.0.0.1')) return url
  return `http://127.0.0.1:${props.mediaProxyPort}/media?url=${encodeURIComponent(url)}`
}
// 预览源（视频用代理直链；图片优先 media_url 原图，否则用缩略图）
const previewSrc = computed(() => {
  const it = previewItem.value
  if (!it) return ''
  if (isVideoItem(it)) return it.media_url ? proxied(it.media_url) : ''
  if (it.media_url) return proxied(it.media_url)
  return it.thumbnail || ''
})
const previewIsVideo = computed(() => previewItem.value && isVideoItem(previewItem.value))
// 图片预览加载态：切换图片时复位，加载完成/失败前显示 spinner（大图不再白屏无反馈）
const previewImageLoaded = ref(false)
const previewImageFailed = ref(false)
watch(previewSrc, () => {
  previewImageLoaded.value = false
  previewImageFailed.value = false
})
const previewLoading = computed(() => {
  const it = previewItem.value
  return !!it && isVideoItem(it) && !it.media_url && !it.media_resolve_failed
})

function openPreview(item) {
  previewItem.value = item
  previewVisible.value = true
  if (!item.media_url) {
    // Bunkr/EX 视频必须解析直链；图片先用缩略图展示同时后台解析原图
    ensureMediaUrl(item)
  }
}
function previewNav(step) {
  const list = previewableList.value
  if (!list.length) return
  const idx = list.indexOf(previewItem.value)
  const next = (idx + step + list.length) % list.length
  previewItem.value = list[next]
  if (!list[next].media_url) ensureMediaUrl(list[next])
}
// 键盘左右键翻图
function onPreviewKeydown(e) {
  if (!previewVisible.value) return
  if (e.key === 'ArrowLeft') previewNav(-1)
  if (e.key === 'ArrowRight') previewNav(1)
}
window.addEventListener('keydown', onPreviewKeydown)
onUnmounted(() => window.removeEventListener('keydown', onPreviewKeydown))


// 搜索框占位文本（按站点和搜索模式切换）
const inputPlaceholder = computed(() => {
  if (props.site === 'coomer') {
    return '搜索 Coomer 作者，或粘贴 xxxcoomer.com 链接'
  }
  if (props.site === 'pawchive') {
    return props.searchMode === 'tag'
      ? '输入标签搜索帖子，如 furry，或粘贴 pawchive.pw 链接'
      : '输入画师名搜索，或粘贴 pawchive.pw 链接'
  }
  if (props.site === 'exhentai') {
    return '搜索 ExHentai 画廊（支持 artist:xxx / tag 语法），或粘贴画廊链接'
  }
  if (props.site === 'twitter') {
    return '搜索 X 内容/推文关键词；@用户名 直接解析博主全部媒体'
  }
  if (props.site === 'iwara') {
    return '搜索 Iwara 视频（MMD）；@用户名 拉取 TA 的全部视频，或粘贴 iwara.tv 链接'
  }
  if (props.site === 'hanime') {
    return '搜索 H站（Hanime1）里番视频，或粘贴 hanime1.me/watch?v=... 链接'
  }
  if (props.site === 'pixiv') {
    return '搜索 Pixiv 插画/漫画作品，或粘贴 pixiv.net/artworks/... 、/users/... 链接'
  }
  if (props.site === 'oreno3d') {
    return '搜索 Oreno3D / EroMMDTube 3D 视频，或粘贴 oreno3d.com、erommdtube.com/movies/... 链接'
  }
  if (props.site === 'erommdtube') {
    return '搜索 EroMMDTube 3D 视频，或粘贴 erommdtube.com、oreno3d.com/movies/... 链接'
  }
  if (props.site === 'asmr') {
    return '搜索音声作品（RJ号 / 标题 / 社团 / 标签），或粘贴 asmr-100.com/work/... 链接'
  }
  return '搜索 Bunkr 相册，或粘贴 Bunkr 链接'
})

// 切换站点
function switchSite(site) {
  if (site === props.site) return
  emit('update:site', site)
}

// 站点按钮显示名
function siteChipName(s) {
  const names = {
    pawchive: 'PA站',
    exhentai: 'EX站',
    iwara: 'Iwara',
    hanime: 'H站',
    pixiv: 'P站',
    oreno3d: 'O3D',
    erommdtube: 'E站',
    asmr: '音声',
    coomer: 'Coomer',
    bunkr: 'Bunkr',
    twitter: 'X',
  }
  return names[s] || s
}

// 解析进度百分比
const inspectPercentage = computed(() => {
  if (props.inspectProgress.total === 0) return 0
  return Math.round((props.inspectProgress.current / props.inspectProgress.total) * 100)
})

// 表格列定义
const columns = [
  { type: 'selection' },
  {
    title: '缩略图',
    key: 'thumbnail',
    width: 80,
    render(row) {
      if (row.thumbnail) {
        return h('img', {
          src: row.thumbnail,
          referrerPolicy: 'no-referrer',
          style: 'width:56px;height:42px;object-fit:cover;border-radius:4px;display:block;background:#26262b;',
        })
      }
      if (row.file_icon) {
        return h('img', {
          src: row.file_icon,
          style: 'width:40px;height:40px;object-fit:contain;display:block;margin:0 auto;',
        })
      }
      return h('div', {
        style: 'width:56px;height:42px;display:flex;align-items:center;justify-content:center;color:#5f5f5f;font-size:12px;background:#26262b;border-radius:4px;',
      }, row.file_type || '无')
    },
  },
  {
    title: '文件名',
    key: 'filename',
    ellipsis: { tooltip: true },
    width: 300,
    render(row) {
      // 增量下载：上次下载之后新增的文件标"新"
      if (row.is_new) {
        return h('div', { style: 'display:flex;align-items:center;gap:6px;min-width:0;' }, [
          h('span', { style: 'flex-shrink:0;font-size:10px;padding:1px 5px;border-radius:3px;background:#e0503c;color:#fff;' }, '新'),
          h('span', { style: 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;' }, row.filename),
        ])
      }
      return row.filename
    },
  },
  {
    title: '大小',
    key: 'size_text',
    width: 100,
  },
  {
    title: '文件类型',
    key: 'file_type',
    width: 90,
  },
  {
    title: '状态',
    key: 'status',
    width: 120,
    render(row) {
      // 历史查重：下载记录里已有该文件 → 显示"已下载"（下载按钮仍可手动勾选重下）
      if (row.is_downloaded) {
        return h(NTag, { size: 'small', type: 'warning', round: true, bordered: false }, { default: () => '已下载' })
      }
      const map = {
        ok: { text: '可下载', type: 'success' },
        unresolved: { text: '无法解析', type: 'error' },
        fetch_failed: { text: '获取失败', type: 'error' },
      }
      const info = map[row.status] || { text: row.status, type: 'default' }
      return h(NTag, { size: 'small', type: info.type, round: true }, { default: () => info.text })
    },
  },
  {
    title: '预览',
    key: 'preview',
    width: 90,
    render(row) {
      // 在线播放/预览按钮（所有站点通用：图片看原图、视频在线播放）
      if (!isImageItem(row) && !isVideoItem(row)) {
        return h('span', { style: 'color:#5f5f5f;font-size:12px;' }, '—')
      }
      return h(NButton, {
        size: 'tiny',
        tertiary: true,
        type: 'info',
        title: isVideoItem(row) ? '在线播放' : '查看大图',
        onClick: () => openPreview(row),
      }, { default: () => (isVideoItem(row) ? '▶ 播放' : '👁 预览') })
    },
  },
]

// 选中文件的大小
const selectedSizeText = computed(() => {
  const selected = props.fileList.filter(f => checkedKeys.value.includes(f.item_page))
  const total = selected.reduce((sum, f) => sum + (f.size || 0), 0)
  if (total === 0) return ''
  return formatSize(total)
})

// 监听文件列表变化，默认选中可下载的（已下载过的文件默认不勾选，避免重复下载）
watch(() => props.fileList, (newList) => {
  checkedKeys.value = newList
    .filter(f => f.status === 'ok' && !f.is_downloaded)
    .map(f => f.item_page)
  localFilter.value = ''
  activeTab.value = newList.length > 0 ? 'progress' : 'logs'
}, { immediate: true })

// 下载开始时切换到进度标签
watch(() => props.downloading, (downloading) => {
  if (downloading) activeTab.value = 'progress'
})

// ============================
// 搜索触发
// ============================
function handleSearch() {
  if (!props.searchQuery.trim()) return
  // EX 站点：关键词搜索时切到搜索结果视图（链接解析仍走文件列表）
  if (props.site === 'exhentai' && !isExhentaiUrl(props.searchQuery)) {
    exViewMode.value = 'search'
  }
  emit('search')
}

// 无限滚动：滚到底部附近自动加载更多（仅 Bunkr/Coomer；EX/PA 用顶底页码分页）
function handleScroll(e) {
  if (props.site !== 'bunkr' && props.site !== 'coomer') return
  const el = e.target
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 300) {
    emit('load-more')
  }
}

// ============================
// 选择操作
// ============================
function selectAll() {
  // 只选当前可见（过滤后）的文件
  checkedKeys.value = filteredFileList.value.map(f => f.item_page)
}

function selectNone() {
  checkedKeys.value = []
}

function invertSelection() {
  const allKeys = filteredFileList.value.map(f => f.item_page)
  checkedKeys.value = allKeys.filter(k => !checkedKeys.value.includes(k))
}

function selectByType(status) {
  checkedKeys.value = props.fileList
    .filter(f => f.status === status)
    .map(f => f.item_page)
}

function handleDownload() {
  const selectedItems = props.fileList.filter(f => checkedKeys.value.includes(f.item_page))
  emit('download', selectedItems)
}

// ============================
// 工具函数
// ============================
function formatSize(bytes) {
  if (bytes == null) return '未知'
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

function formatSpeed(bytesPerSecond) {
  if (!bytesPerSecond || bytesPerSecond <= 0) return ''
  return `${formatSize(bytesPerSecond)}/s`
}

// ============================
// 右侧实时下载滚动栏（下载中的文件：文件名 + 进度 + 速度）
// ============================
const tickerItems = computed(() => {
  const items = []
  for (const [name, p] of Object.entries(props.downloadProgress || {})) {
    if (p && p.status === 'downloading') {
      items.push({
        name,
        percent: Math.round(p.completed || 0),
        speedText: p.speed > 0 ? formatSpeed(p.speed) : '',
      })
    }
  }
  return items
})

// 内容复制一份拼接实现无缝循环滚动
const tickerLoopItems = computed(() => tickerItems.value.concat(tickerItems.value))

// 所有下载中文件的合计速度
const tickerTotalSpeedText = computed(() => {
  let total = 0
  for (const p of Object.values(props.downloadProgress || {})) {
    if (p && p.status === 'downloading') total += p.speed || 0
  }
  return total > 0 ? formatSpeed(total) : ''
})

function handleDeleteHistory(item, deleteFile) {
  const msg = deleteFile
    ? `确定删除记录和文件「${item.filename}」吗？此操作不可恢复。`
    : `确定删除记录「${item.filename}」吗？`
  if (window.confirm(msg)) {
    emit('delete-history', item.id, deleteFile)
  }
}

function statusTagType(status) {
  const map = { downloading: 'info', completed: 'success', failed: 'error' }
  return map[status] || 'default'
}

function statusText(status) {
  const map = { downloading: '下载中', completed: '完成', failed: '失败' }
  return map[status] || status
}

function progressStatus(status) {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'error'
  return 'default'
}

function logTagType(type) {
  const map = {
    '错误': 'error',
    '失败': 'error',
    '完成': 'success',
    '解析': 'info',
    '下载': 'info',
    '搜索': 'info',
    '系统': 'default',
  }
  return map[type] || 'default'
}

// ============================
// 对外接口（App.vue 收到后端事件后调用）
// ============================
defineExpose({
  // 更新种子列表（后端 exhentai_torrents 事件）
  setTorrents(torrents) {
    torrentList.value = Array.isArray(torrents) ? torrents : []
    torrentLoading.value = false
    if (torrentList.value.length === 0) {
      // 无种子保持弹窗打开提示"没有可用种子"
    }
  },
  // 种子获取失败
  setTorrentsError() {
    torrentLoading.value = false
  },
  // 更新磁力链接（后端 exhentai_magnet 事件）
  setMagnet(magnet) {
    currentMagnet.value = magnet || ''
    magnetLoading.value = false
  },
  // 磁力获取失败
  setMagnetError() {
    magnetLoading.value = false
    currentMagnet.value = ''
  },
})
</script>

<style scoped>
.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: #18181c;
}

.url-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #1e1e22;
  border-bottom: 1px solid #2d2d33;
}

/* 搜索按钮（缩小版） */
.search-btn {
  flex-shrink: 0;
}

/* 全局自动翻译开关（缩小版，约原按钮 1/3 大小；开启时绿色描边） */
.auto-translate-btn {
  flex-shrink: 0;
  min-width: 28px;
  padding: 0 6px;
}
.auto-translate-btn.on {
  border-color: #63e2b7;
}
/* 翻译进行中转圈（自绘，按钮保持可点击以停止翻译） */
.tr-spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(99, 226, 183, 0.25);
  border-top-color: #63e2b7;
  border-radius: 50%;
  animation: tr-spin 0.8s linear infinite;
  vertical-align: -2px;
}
@keyframes tr-spin {
  to { transform: rotate(360deg); }
}

.site-switch {
  flex-shrink: 0;
}

/* 站点切换：竖排三类（二次元 / 三次元 / 综合类） */
.site-switch-groups {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex-shrink: 0;
  margin-right: 2px;
}
.site-group {
  display: flex;
  align-items: center;
  gap: 6px;
}
.site-group-label {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.45);
  width: 34px;
  flex-shrink: 0;
  user-select: none;
}
html.light-mode .site-group-label {
  color: rgba(0, 0, 0, 0.45);
}
.site-group-btns {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.site-chip {
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: #2a2a30;
  color: rgba(255, 255, 255, 0.75);
  border-radius: 6px;
  padding: 3px 9px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.site-chip:hover {
  border-color: #63e2b7;
  color: #63e2b7;
}
.site-chip.on {
  background: #63e2b7;
  border-color: #63e2b7;
  color: #103d2b;
  font-weight: 600;
}
html.light-mode .site-chip {
  background: #fff;
  border-color: rgba(0, 0, 0, 0.12);
  color: rgba(0, 0, 0, 0.7);
}
html.light-mode .site-chip.on {
  background: #18a058;
  border-color: #18a058;
  color: #fff;
}

.search-mode-select {
  width: 100px;
  flex-shrink: 0;
}

.local-filter {
  width: 200px;
}

.inspect-progress {
  padding: 8px 16px;
  background: #1e1e22;
  border-bottom: 1px solid #2d2d33;
}

.inspect-progress .n-progress {
  margin-bottom: 4px;
}

.progress-text {
  font-size: 12px;
  color: #7f7f7f;
}

.content-area {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* ============ 文件列表 ============ */
.file-list-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 12px 16px;
  min-height: 0;
}

.list-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}

.album-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.album-name {
  font-size: 14px;
  font-weight: 600;
  color: #e0e0e6;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-count {
  font-size: 12px;
  color: #7f7f7f;
}

.list-actions {
  display: flex;
  gap: 4px;
}

.download-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0 0;
  margin-top: auto;
}

.selected-info {
  font-size: 13px;
  color: #a0a0a8;
}

.selected-count {
  color: #63e2b7;
  font-weight: 600;
  font-size: 15px;
}

.selected-size {
  color: #7f7f7f;
  font-size: 12px;
}

/* ============ 搜索结果 ============ */
.search-results {
  flex: 1;
  min-height: 0;
}

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

.ex-cats {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px;
}

.ex-cats-label {
  font-size: 12px;
  color: #8f8f98;
  margin-right: 2px;
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

.ex-cat-all {
  margin-left: 4px;
  border-style: dashed;
}

.ex-filters {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 14px;
}

.ex-filter-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.ex-filter-label {
  font-size: 12px;
  color: #8f8f98;
  white-space: nowrap;
}

.ex-rating-select {
  width: 78px;
}

.ex-page-input {
  width: 84px;
}

.ex-filter-sep {
  color: #7f7f88;
  font-size: 12px;
}

/* ========== ExHentai 画廊详情（复刻原版画廊页信息区） ========== */
.ex-detail {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

/* ============ EX 内联详情+文件列表（搜索结果下方追加展示） ============ */
.ex-inline-detail {
  margin-top: 16px;
  border: 1px solid #3a3a42;
  border-radius: 8px;
  background: #191a1d;
  padding: 12px;
}
.ex-inline-detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}
.ex-inline-detail-title {
  font-size: 14px;
  font-weight: 600;
  color: #a3c74f;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ex-inline-detail-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 40px 0;
  color: #8f8f98;
  font-size: 13px;
}
.ex-inline-file-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
}

.ex-detail-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid #2d2d33;
  background: #191a1d;
}

.ex-detail-toolbar-title {
  font-size: 13px;
  color: #8f8f98;
}

.ex-detail-scroll {
  flex: 1;
  min-height: 0;
}

.ex-detail-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 0;
  color: #8f8f98;
  font-size: 13px;
}

.ex-detail-head {
  display: flex;
  gap: 16px;
  padding: 16px;
  border-bottom: 1px solid #2d2d33;
}

.ex-detail-cover {
  flex-shrink: 0;
  width: 184px;
  min-height: 240px;
  border: 1px solid #3d3d45;
  border-radius: 4px;
  overflow: hidden;
  background: #141517;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ex-detail-cover img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.ex-detail-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ex-detail-name {
  font-size: 15px;
  font-weight: 600;
  color: #a3c74f; /* 原版画廊标题绿 */
  line-height: 1.4;
  word-break: break-all;
}

.ex-detail-name-jp {
  font-size: 12px;
  color: #8f8f98;
  word-break: break-all;
}

.ex-detail-meta {
  border-collapse: collapse;
  margin-top: 4px;
}

.ex-detail-meta td {
  padding: 2px 10px 2px 0;
  font-size: 12px;
  color: #c8c8cc;
  vertical-align: top;
}

.ex-detail-meta td:first-child {
  color: #8f8f98;
  white-space: nowrap;
  min-width: 60px;
}

.ex-detail-link {
  color: #63e2b7;
  cursor: pointer;
  word-break: break-all;
  text-decoration: none;
}

.ex-detail-link:hover {
  text-decoration: underline;
}

.ex-detail-actions {
  display: flex;
  gap: 10px;
  margin-top: 10px;
}

.ex-detail-tags {
  padding: 12px 16px 20px;
}

.ex-detail-tagrow {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  margin-bottom: 6px;
}

.ex-detail-tagrow-ns {
  flex-shrink: 0;
  font-size: 12px;
  color: #8f8f98;
  min-width: 56px;
  padding-top: 2px;
}

.ex-detail-tag {
  display: inline-block;
  font-size: 12px;
  color: #d0d0d6;
  background: #2a2b2e;
  border: 1px solid #3d3d45;
  border-radius: 3px;
  padding: 1px 7px;
  margin: 0 3px 3px 0;
  cursor: pointer;
  text-decoration: none;
}

.ex-detail-tag:hover {
  background: #4a7c3a;
  border-color: #5a9c46;
  color: #dff5cf;
}

.ex-detail-notags {
  font-size: 12px;
  color: #8f8f98;
}

/* EX 画廊信息内联面板（文件列表视图下，自动解析后保留元数据可见） */
.ex-inline-info {
  margin: 0 0 8px;
  padding: 8px 12px;
  background: #1e1f22;
  border: 1px solid #2d2d33;
  border-radius: 4px;
  font-size: 12px;
}
.ex-inline-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  align-items: center;
}
.ex-inline-field {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.ex-inline-label {
  color: #8f8f98;
}
.ex-inline-value {
  color: #c8c8d0;
}
.ex-inline-tags {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ex-inline-tagrow {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
}
.ex-inline-tagrow-ns {
  color: #8f8f98;
  font-weight: 600;
}
.ex-inline-tag {
  display: inline-block;
  padding: 1px 6px;
  background: #2a2f1f;
  border: 1px solid #3a4a2a;
  border-radius: 3px;
  color: #b5d8a0;
  cursor: pointer;
  font-size: 11px;
  text-decoration: none;
}
.ex-inline-tag:hover {
  background: #4a7c3a;
  border-color: #5a9c46;
  color: #dff5cf;
}

.torrent-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* ========== Pawchive 帖子详情（复用 EX 详情布局） ========== */
.pa-detail-content {
  margin: 0 16px 12px;
  padding: 10px 12px;
  background: #1e1f22;
  border: 1px solid #2d2d33;
  border-radius: 4px;
  font-size: 12px;
  color: #c8c8cc;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
}

.pa-detail-previews {
  padding: 0 16px 20px;
}

.pa-detail-previews-title {
  font-size: 12px;
  color: #8f8f98;
  margin-bottom: 8px;
}

.pa-detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 10px;
}

.pa-detail-cell {
  border: 1px solid #2d2d33;
  border-radius: 4px;
  overflow: hidden;
  background: #141517;
}

.pa-detail-cell img {
  width: 100%;
  aspect-ratio: 1 / 1;
  object-fit: cover;
  display: block;
}

.pa-detail-cell-name {
  font-size: 11px;
  color: #b8b8b8;
  padding: 4px 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ========== ExHentai 搜索结果（复刻原版 List/Thumbnail 布局） ========== */
.ex-results {
  display: flex;
  flex-direction: column;
}

.ex-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.ex-result-count {
  font-size: 12px;
  color: #8f8f98;
  margin-left: auto;
}

/* 列表模式：行式表格（原版 List） */
.ex-list-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}

.ex-tr {
  background: #34353b;
  cursor: pointer;
  transition: background 0.1s ease;
}

.ex-tr-alt {
  background: #3c3e44;
}

.ex-tr:hover {
  background: #4f535b;
}

.ex-td-check {
  width: 30px;
  padding: 0 4px;
  text-align: center;
  vertical-align: middle;
}

.ex-check {
  cursor: pointer;
}

.ex-td-thumb {
  width: 116px;
  padding: 6px 8px;
  vertical-align: middle;
}

.ex-thumb {
  width: 100px;
  height: 140px;
  background: #26262b;
  border: 1px solid #525252;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ex-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.ex-thumb-empty {
  font-size: 11px;
  font-weight: bold;
  color: #5f5f5f;
}

.ex-td-info {
  padding: 8px 10px;
  vertical-align: middle;
}

/* 原版绿色标题链接 */
.ex-info-title {
  font-size: 13px;
  font-weight: bold;
  color: #a3c74f;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}

.ex-tr:hover .ex-info-title {
  color: #c8e88a;
}

/* 标签行：灰色可点击（点击按命名空间搜索，同原版逻辑） */
.ex-info-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 5px;
}

.ex-info-tag {
  font-size: 11px;
  color: #b8b8b8;
  text-decoration: none;
  cursor: pointer;
  white-space: nowrap;
}

.ex-info-tag:hover {
  color: #ffffff;
  text-decoration: underline;
}

.ex-info-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 5px;
  font-size: 11px;
  color: #989898;
}

.ex-td-fav {
  width: 34px;
  vertical-align: middle;
}

.ex-row-fav {
  position: static;
  opacity: 0;
  transition: opacity 0.12s ease;
}

.ex-tr:hover .ex-row-fav {
  opacity: 1;
}

/* 缩略图模式（原版 Thumbnail：网格） */
.ex-thumb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
  margin-top: 8px;
}

.ex-thumb-card {
  position: relative;
  background: #1e1e22;
  border: 1px solid #2d2d33;
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.15s ease;
}

.ex-thumb-card:hover {
  border-color: #a3c74f;
}

.ex-thumb-card-img {
  aspect-ratio: 100 / 140;
  background: #26262b;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}

/* 缩略图模式多选勾选框（左上角，勾选后卡片高亮） */
.ex-thumb-check {
  position: absolute;
  top: 4px;
  left: 4px;
  width: 20px;
  height: 20px;
  background: rgba(0, 0, 0, 0.55);
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 2;
}
.ex-thumb-check .ex-check {
  width: 14px;
  height: 14px;
  cursor: pointer;
}
.ex-thumb-card-checked {
  outline: 2px solid #3889ff;
  outline-offset: -2px;
}

.ex-thumb-card-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.ex-thumb-card-title {
  font-size: 11px;
  color: #e6e6ec;
  padding: 6px 8px;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}

.ex-card-fav {
  opacity: 0;
  transition: opacity 0.12s ease;
}

.ex-thumb-card:hover .ex-card-fav {
  opacity: 1;
}

/* ========== Pawchive 搜索结果（卡片网格 + 分页） ========== */
.pa-results {
  display: flex;
  flex-direction: column;
}

/* ========== EX 隐藏标签按钮 + 管理面板 ========== */
.ex-hide-tag-btn.on {
  background: #5f2b2b;
  border-color: #a25b5b;
  color: #f0b1b1;
}

.ex-hide-panel {
  margin: 6px 0 4px;
  padding: 8px 10px;
  border: 1px dashed #5a5a64;
  border-radius: 8px;
  background: #17181b;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ex-hide-input-row {
  display: flex;
  gap: 6px;
  align-items: center;
}

.ex-hide-input {
  flex: 1;
}

.ex-hide-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.ex-hide-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: #2b1f22;
  border: 1px solid #7a4a4a;
  color: #e8b8b8;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  cursor: pointer;
  user-select: none;
}

.ex-hide-chip:hover {
  border-color: #c76a6a;
}

.ex-hide-chip-x {
  font-weight: 700;
  color: #ff9c9c;
  padding: 0 2px;
  cursor: pointer;
}

.ex-hide-chip-x:hover {
  color: #ffffff;
}

.ex-hide-empty {
  font-size: 12px;
  color: #8f8f98;
  line-height: 1.6;
}

/* ========== PA 画师子项目视图 ========== */
.pa-artist-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid #2d2d33;
  flex-wrap: wrap;
}

.pa-artist-name {
  font-size: 14px;
  font-weight: 600;
  color: #63e2b7;
  word-break: break-all;
}

.pa-artist-count {
  font-size: 12px;
  color: #8f8f98;
}

.pa-artist-cached {
  font-size: 12px;
  color: #d4a94e;
}

.pa-artist-empty {
  padding: 40px 0;
  text-align: center;
  color: #8f8f98;
  font-size: 13px;
}

.pa-post-row {
  display: flex;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid #232329;
  cursor: pointer;
  transition: background 0.15s;
}

.pa-post-row:hover {
  background: #1f2024;
}

.pa-post-thumb {
  flex-shrink: 0;
  width: 96px;
  height: 72px;
  border-radius: 6px;
  overflow: hidden;
  background: #26262b;
  display: flex;
  align-items: center;
  justify-content: center;
}

.pa-post-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.pa-post-thumb-empty {
  color: #5a5a64;
  font-size: 13px;
}

.pa-post-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.pa-post-title {
  font-size: 13px;
  color: #e0e0e6;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pa-post-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #8f8f98;
}

.pa-post-badge {
  padding: 0 6px;
  border-radius: 4px;
  font-size: 11px;
  line-height: 18px;
}

.pa-post-badge-video {
  background: #2b2440;
  color: #b3a1f0;
  border: 1px solid #4a3d6a;
}

.pa-post-badge-zip {
  background: #3a2f22;
  color: #e0b878;
  border: 1px solid #6a5535;
}

.pa-post-content {
  font-size: 12px;
  color: #7a7a84;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pa-toolbar {
  padding: 2px 0 4px;
}

.pa-result-count {
  font-size: 12px;
  color: #8f8f98;
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

.iw-card-stats {
  display: flex;
  gap: 8px;
  white-space: nowrap;
  overflow: hidden;
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

.iw-thumb-ecchi {
  position: absolute;
  left: 6px;
  top: 6px;
  background: rgba(240, 160, 32, 0.85);
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

.iw-comments-more {
  padding: 4px 0 14px;
  text-align: center;
}

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

/* 批量下载进度（复用 iw-batch-progress 样式） */
.ha-batch-progress {
  margin-left: 4px;
}

/* ==================== Oreno3D (O3D) 专属样式 ==================== */
/* 工具栏排序下拉 */
.or-sort-select {
  width: 110px;
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

/* 详情页：作者可点击 */
.or-author-link {
  cursor: pointer;
  color: #63e2b7;
}

.or-author-link:hover {
  text-decoration: underline;
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

/* ==================== 角色列表 / 人気作者 / 热门分类（双站共用） ==================== */
/* 浏览视图分区（人気角色 / 五十音分组） */
.or-browse-section {
  padding: 12px 14px 4px;
}

.or-browse-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #e0e0e6;
  margin-bottom: 10px;
}

/* chip 列表容器 */
.or-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 2px 0 10px;
}

/* 角色 chip（基于 or-tag-chip）：名称 +（原作）+ 作品数 */
.or-char-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.or-chip-origin {
  font-size: 11px;
  opacity: 0.75;
}

.or-chip-count {
  padding: 0 6px;
  border-radius: 8px;
  background: rgba(99, 226, 183, 0.18);
  font-size: 11px;
  line-height: 16px;
}

/* 五十音分组 tab（あ/か/さ...） */
.or-kana-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 2px 0 10px;
}

.or-kana-tab {
  padding: 2px 10px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: #a0a0a8;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.or-kana-tab:hover {
  color: #63e2b7;
  border-color: rgba(99, 226, 183, 0.4);
}

.or-kana-tab.on {
  color: #63e2b7;
  background: rgba(99, 226, 183, 0.12);
  border-color: rgba(99, 226, 183, 0.45);
}

/* 人気作者列表（排名 + 名称） */
.or-author-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
  padding: 10px 14px 14px;
}

.or-author-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
  cursor: pointer;
  transition: background 0.15s;
}

.or-author-item:hover {
  background: rgba(255, 255, 255, 0.06);
}

.or-author-rank {
  min-width: 22px;
  text-align: center;
  padding: 1px 4px;
  border-radius: 6px;
  background: rgba(99, 226, 183, 0.15);
  color: #63e2b7;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}

.or-author-name {
  font-size: 13px;
  color: #e0e0e6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 分类组 chip（基于 or-tag-chip，蓝色区分 + 作品数） */
.or-group-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border-color: rgba(112, 192, 232, 0.35);
  background: rgba(112, 192, 232, 0.08);
  color: #70c0e8;
}

.or-group-chip:hover {
  background: rgba(112, 192, 232, 0.2);
}

/* 日间模式适配 */
html.light-mode .ha-section-title,
html.light-mode .ha-uploader {
  color: #333;
}

html.light-mode .ha-comment-reply {
  border-left-color: rgba(0, 128, 90, 0.25);
}

html.light-mode .or-tag-chip {
  background: rgba(0, 128, 90, 0.06);
  border-color: rgba(0, 128, 90, 0.35);
  color: #0a7a52;
}

html.light-mode .or-tags-empty {
  color: #888;
}

html.light-mode .or-author-link {
  color: #0a7a52;
}

html.light-mode .or-iwara-link {
  color: #0a6ebd;
}

html.light-mode .or-no-source {
  background: rgba(240, 160, 32, 0.08);
  border-color: rgba(200, 130, 20, 0.35);
  color: #9a6a10;
}

/* 角色/作者/分类组（双站共用）日间模式 */
html.light-mode .or-browse-section-title {
  color: #333;
}

html.light-mode .or-chip-count {
  background: rgba(0, 128, 90, 0.12);
}

html.light-mode .or-kana-tab {
  border-color: rgba(0, 0, 0, 0.12);
  background: rgba(0, 0, 0, 0.02);
  color: #666;
}

html.light-mode .or-kana-tab:hover {
  color: #0a7a52;
  border-color: rgba(0, 128, 90, 0.4);
}

html.light-mode .or-kana-tab.on {
  color: #0a7a52;
  background: rgba(0, 128, 90, 0.08);
  border-color: rgba(0, 128, 90, 0.45);
}

html.light-mode .or-author-item {
  background: rgba(0, 0, 0, 0.02);
  border-color: rgba(0, 0, 0, 0.06);
}

html.light-mode .or-author-item:hover {
  background: rgba(0, 0, 0, 0.05);
}

html.light-mode .or-author-rank {
  background: rgba(0, 128, 90, 0.1);
  color: #0a7a52;
}

html.light-mode .or-author-name {
  color: #333;
}

html.light-mode .or-group-chip {
  background: rgba(0, 110, 189, 0.06);
  border-color: rgba(0, 110, 189, 0.35);
  color: #0a6ebd;
}

html.light-mode .or-group-chip:hover {
  background: rgba(0, 110, 189, 0.14);
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

.iw-batch-check-user {
  position: static;
  flex-shrink: 0;
  margin-right: 2px;
}

.iw-batch-progress {
  color: #f0a020;
}

/* Iwara 关注/好友列表用户卡片 */
.iw-user-card {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 8px 12px;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
  cursor: pointer;
  transition: background 0.15s;
}

.iw-user-card:hover {
  background: rgba(255, 255, 255, 0.06);
}

.iw-user-avatar {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
  background: #2d2d33;
}

.iw-user-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.iw-user-avatar-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #63e2b7;
  font-size: 16px;
}

.iw-user-info {
  flex: 1;
  min-width: 0;
}

.iw-user-name {
  display: flex;
  align-items: center;
  gap: 6px;
}

.iw-user-nick {
  font-size: 14px;
  font-weight: 600;
  color: #e0e0e6;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.iw-user-handle {
  font-size: 12px;
  color: #8f8f98;
}

.iw-user-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
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

/* ExHentai 浏览器视图 */
.ex-browser {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.ex-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #1e1e22;
  border-bottom: 1px solid #2d2d33;
  flex-shrink: 0;
  flex-wrap: nowrap;
}

.ex-address {
  flex: 1;
  min-width: 120px;
}

.ex-webview {
  flex: 1;
  min-height: 0;
  background: #fff;
}

/* 磁力弹窗 */
.torrent-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 300px;
  overflow-y: auto;
}

.torrent-empty {
  text-align: center;
  color: #8f8f99;
  padding: 24px 0;
}

.torrent-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: #1e1e22;
  border: 1px solid #2d2d33;
  border-radius: 8px;
}

.torrent-info {
  flex: 1;
  min-width: 0;
}

.torrent-name {
  font-size: 13px;
  color: #e0e0e6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.torrent-meta {
  font-size: 11.5px;
  color: #8f8f99;
  margin-top: 4px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.magnet-result {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #2d2d33;
}

.magnet-label {
  font-size: 12.5px;
  color: #8f8f99;
  margin-bottom: 6px;
}

.magnet-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
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

.load-more {
  display: flex;
  justify-content: center;
  padding: 14px 0;
}

.load-more-end {
  font-size: 12px;
  color: #5f5f5f;
}

/* ============ 空状态 ============ */
/* 解析中视图：点击后立即切换到此处的明确加载反馈 */
.inspect-loading-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  color: #7f7f7f;
}

.inspect-loading-title {
  font-size: 15px;
  color: #d0d0d8;
}

.inspect-loading-sub {
  font-size: 12px;
  color: #6f6f78;
}

/* 点击反馈：卡片/行按下时立即有视觉响应（消除"不知道点没点上"的感觉） */
.ex-tr:active,
.search-card:active {
  transform: scale(0.985);
  transition: transform 0.08s ease;
  filter: brightness(1.15);
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #7f7f7f;
}

/* 空状态快捷操作按钮（PA 主页/我的收藏等） */
.empty-actions {
  display: flex;
  gap: 14px;
  margin: 14px 0 6px;
}

.empty-action-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 150px;
  padding: 12px 18px;
  border: 1px solid rgba(99, 226, 183, 0.25);
  border-radius: 10px;
  background: rgba(99, 226, 183, 0.06);
  color: #e8e8e8;
  cursor: pointer;
  transition: all 0.15s ease;
  font-size: 14px;
}

.empty-action-btn:hover {
  background: rgba(99, 226, 183, 0.14);
  border-color: rgba(99, 226, 183, 0.5);
  transform: translateY(-1px);
}

.empty-action-btn .ea-icon {
  font-size: 20px;
}

.empty-action-btn .ea-desc {
  font-size: 11px;
  color: #8f8f8f;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
  opacity: 0.5;
}

.empty-text {
  font-size: 14px;
  margin-bottom: 4px;
}

.empty-hint {
  font-size: 12px;
  color: #5f5f5f;
}

/* ============ 底部 ============ */
.bottom-area {
  height: 200px;
  min-height: 200px;
  border-top: 1px solid #2d2d33;
  background: #1e1e22;
  padding: 0 16px;
  overflow: hidden;
  display: flex;
  align-items: stretch;
  gap: 12px;
}

/* 底部 tabs 限宽，右侧让位给实时下载滚动栏 */
.bottom-area > .n-tabs {
  flex: 1;
  min-width: 0;
}

/* ============ 右侧实时下载滚动栏 ============ */
.dl-ticker {
  width: 300px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-left: 1px solid #2d2d33;
  padding: 6px 0 6px 12px;
  overflow: hidden;
}

.dl-ticker-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  margin-bottom: 4px;
}

.dl-ticker-title {
  font-size: 12px;
  font-weight: 600;
  color: #e0e0e6;
}

.dl-ticker-total {
  font-size: 11px;
  color: #63e2b7;
  font-family: 'Cascadia Code', Consolas, monospace;
}

.dl-ticker-viewport {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  position: relative;
}

.dl-ticker-empty {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: #6c6c75;
}

.dl-ticker-track {
  display: flex;
  flex-direction: column;
  animation: dl-ticker-scroll 14s linear infinite;
}

.dl-ticker-viewport:hover .dl-ticker-track {
  animation-play-state: paused; /* 悬停暂停方便看清 */
}

@keyframes dl-ticker-scroll {
  0% { transform: translateY(0); }
  100% { transform: translateY(-50%); }
}

.dl-ticker-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 0;
  font-size: 11px;
  white-space: nowrap;
}

.dl-ticker-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #c9c9d1;
}

.dl-ticker-pct {
  color: #63e2b7;
  font-family: 'Cascadia Code', Consolas, monospace;
  min-width: 34px;
  text-align: right;
}

.dl-ticker-speed {
  color: #63e2b7;
  font-family: 'Cascadia Code', Consolas, monospace;
  min-width: 62px;
  text-align: right;
}

html.light-mode .dl-ticker {
  border-left-color: #e5e6eb;
}

html.light-mode .dl-ticker-title {
  color: #1f2329;
}

html.light-mode .dl-ticker-name {
  color: #5a5c66;
}

html.light-mode .dl-ticker-empty {
  color: #8a8d99;
}

/* ============ 文件小方格视图 ============ */
.file-grid-scroll {
  flex: 1;
  min-height: 0;
}

.file-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 12px;
  padding: 12px 16px;
}

.file-grid-item {
  cursor: pointer;
  border-radius: 8px;
  border: 2px solid transparent;
  background: rgba(255, 255, 255, 0.03);
  padding: 6px;
  transition: border-color 0.12s, background 0.12s, transform 0.12s;
  overflow: hidden;
}

.file-grid-item:hover {
  background: rgba(255, 255, 255, 0.07);
  transform: translateY(-2px);
}

.file-grid-item.grid-selected {
  border-color: #63e2b7;
  background: rgba(99, 226, 183, 0.08);
}

.file-grid-item.grid-bad {
  opacity: 0.55;
}

.grid-thumb {
  position: relative;
  width: 100%;
  aspect-ratio: 1 / 1;
  border-radius: 5px;
  overflow: hidden;
  background: #26262b;
  display: flex;
  align-items: center;
  justify-content: center;
}

.grid-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.grid-thumb img.grid-icon {
  width: 44px;
  height: 44px;
  object-fit: contain;
}

.grid-type {
  font-size: 11px;
  color: #5f5f5f;
}

.grid-new {
  position: absolute;
  top: 4px;
  left: 4px;
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  background: #e0503c;
  color: #fff;
}

/* 历史查重角标（左下角，与"新"错开） */
.grid-downloaded {
  position: absolute;
  bottom: 4px;
  left: 4px;
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(240, 160, 32, 0.92);
  color: #fff;
}

.grid-check {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #63e2b7;
  color: #10341f;
  font-size: 12px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 方格模式：在线预览/播放悬浮按钮（左下角，不与勾选冲突） */
.grid-preview-btn {
  position: absolute;
  left: 4px;
  bottom: 4px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 12px;
  display: none;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 2;
}

.file-grid-item:hover .grid-preview-btn {
  display: flex;
}

.grid-preview-btn:hover {
  background: #18a058;
}

/* 在线预览/播放弹窗 */
.media-preview-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.media-preview-video video {
  width: 100%;
  max-height: 62vh;
  background: #000;
  border-radius: 6px;
  display: block;
}

.media-preview-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 2px 0;
}
.preview-volume {
  -webkit-appearance: none;
  appearance: none;
  width: 120px;
  height: 4px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
  outline: none;
  cursor: pointer;
}
.preview-volume::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 12px;
  height: 12px;
  background: #63e2b7;
  border-radius: 50%;
  cursor: pointer;
}
.preview-volume::-moz-range-thumb {
  width: 12px;
  height: 12px;
  background: #63e2b7;
  border: none;
  border-radius: 50%;
  cursor: pointer;
}
.preview-volume-text {
  font-size: 12px;
  color: #8b8b93;
  min-width: 36px;
}
html.light-mode .preview-volume {
  background: rgba(0, 0, 0, 0.18);
}
html.light-mode .preview-volume-text {
  color: #5a5c66;
}

.media-preview-image {
  position: relative;  /* 供加载 spinner 绝对定位居中 */
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  max-height: 64vh;
  cursor: pointer;
  background: rgba(0, 0, 0, 0.25);
  border-radius: 6px;
  overflow: hidden;
}

/* 图片加载中 spinner 居中 */
.media-preview-img-loading {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
}

.media-preview-image img {
  max-width: 100%;
  max-height: 64vh;
  object-fit: contain;
  user-select: none;
}

.media-preview-tip {
  padding: 40px 16px;
  text-align: center;
  color: #8b8b93;
}

.media-preview-err {
  color: #e0503c;
}

.media-preview-footer {
  display: flex;
  align-items: center;
  gap: 10px;
}

.media-preview-name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  user-select: text;
}

.media-preview-size {
  margin-left: 8px;
  font-size: 12px;
  opacity: 0.55;
}

.grid-name {
  margin-top: 6px;
  font-size: 11px;
  color: #d0d0d6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.grid-size {
  font-size: 10px;
  color: #5f5f5f;
  margin-top: 2px;
}

.progress-list {
  max-height: 150px;
  overflow-y: auto;
  padding: 4px 0;
}

.progress-item {
  margin-bottom: 8px;
}

.progress-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 3px;
}

.progress-filename {
  font-size: 12px;
  color: #a0a0a8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 80%;
}

.progress-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.progress-speed {
  font-size: 11px;
  color: #63e2b7;
  font-family: monospace;
}

.log-list {
  max-height: 150px;
  overflow-y: auto;
  padding: 4px 0;
}

.log-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
  font-size: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
}

.log-time {
  color: #5f5f5f;
  font-family: monospace;
  min-width: 60px;
}

.log-message {
  color: #a0a0a8;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-tab {
  text-align: center;
  color: #5f5f5f;
  padding: 30px 0;
  font-size: 12px;
}

/* ============ 历史任务 ============ */
.history-list {
  max-height: 150px;
  overflow-y: auto;
  padding: 4px 0;
}

.history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
}

.history-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.history-name {
  font-size: 12px;
  color: #e0e0e6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-meta {
  font-size: 11px;
  color: #5f5f5f;
}

.history-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

/* ============================ X (Twitter) 关注视图 ============================ */
.tw-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  flex-shrink: 0;
  flex-wrap: wrap;
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

/* 关注名单本地搜索框：靠右伸展，快速检索已缓存的人 */
.tw-follow-search {
  margin-left: auto;
  width: 220px;
  flex-shrink: 1;
}
.tw-follow-search + .n-button {
  margin-left: 0;
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

/* 浏览模式进度条 */
.tw-browse-progress {
  padding: 8px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

/* 浏览模式"加载更多"区域 */
.tw-browse-more {
  padding: 6px 12px 16px;
}

/* 博主内容流操作栏 + 加载中提示（用户详情页下方） */
.tw-user-feed-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px 2px;
}

.tw-user-feed-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 26px 0;
  color: #7a7a85;
  font-size: 13px;
}

.tw-browse-end {
  text-align: center;
  font-size: 12px;
  color: #7a7a85;
  padding: 10px 0;
}

/* 工具栏本地搜索框 */
.tw-local-search {
  width: 220px;
  flex-shrink: 0;
}

/* 浏览模式推文卡片 */
.tw-tweet-card {
  margin: 10px 12px;
  padding: 12px 14px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
  cursor: pointer;
  transition: background 0.15s;
}

.tw-tweet-card:hover {
  background: rgba(255, 255, 255, 0.06);
}

.tw-tweet-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.tw-tweet-avatar {
  width: 36px;
  height: 36px;
}

.tw-tweet-user {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.tw-tweet-time {
  margin-left: auto;
  font-size: 11px;
  color: #7a7a85;
  flex-shrink: 0;
}

.tw-tweet-text {
  margin-top: 8px;
  font-size: 13px;
  color: #d0d0d6;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.tw-tweet-media {
  display: flex;
  gap: 6px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.tw-tweet-thumb {
  position: relative;
  width: 120px;
  height: 120px;
  border-radius: 6px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.05);
}

.tw-tweet-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.tw-tweet-video .tw-tweet-play {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}

.tw-tweet-more {
  align-self: center;
  font-size: 12px;
  color: #7a7a85;
}

/* 用户详情视图 */
.tw-profile-card {
  display: flex;
  gap: 14px;
  padding: 18px 16px 12px;
  align-items: flex-start;
}

.tw-profile-avatar {
  width: 72px;
  height: 72px;
}

.tw-profile-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 16px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
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

.tw-user-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  margin: 0 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.15s;
}

.tw-user-card:hover {
  background: rgba(255, 255, 255, 0.04);
}

.tw-user-avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
}

.tw-user-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.tw-avatar-empty {
  font-size: 18px;
  color: #7a7a85;
}

.tw-user-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.tw-user-name {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  min-width: 0;
}

.tw-user-nick {
  font-size: 13px;
  font-weight: 600;
  color: #e0e0e6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 280px;
}

.tw-verified {
  color: #63e2b7;
  font-size: 11px;
}

.tw-user-handle {
  font-size: 12px;
  color: #7a7a85;
}

.tw-user-desc {
  font-size: 12px;
  color: #9a9aa5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tw-user-stats {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: #5f5f5f;
}

.tw-user-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

/* X 关注分类弹窗 */
.tw-tag-modal {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 4px;
}

.tw-tag-user {
  font-size: 13px;
  color: #e0e0e6;
}

.tw-tag-current {
  color: #7a7a85;
  font-weight: normal;
}

.tw-tag-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.tw-tag-label {
  font-size: 13px;
  color: #9a9aa5;
  width: 34px;
  flex-shrink: 0;
}

.tw-tag-hint {
  font-size: 11px;
  color: #7a7a85;
  line-height: 1.6;
}

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

/* JavDB 详情：封面区域（限宽居中） */
.javdb-cover-area {
  display: flex;
  justify-content: center;
  background: transparent;
  padding: 8px 0;
}
.javdb-cover-area img {
  max-width: min(100%, 480px);
  max-height: 420px;
  border-radius: 8px;
  cursor: zoom-in;
  object-fit: contain;
}
/* JavDB 信息面板 */
.javdb-info-panel {
  flex-wrap: wrap;
  gap: 6px 14px;
}
/* JavDB 磁力列表 */
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
  width: 90px;
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
.asmr-player-space {
  height: 64px;
}

/* 内置音频播放器（悬浮底部，锚定详情容器） */
.asmr-player {
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 10px;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-radius: 10px;
  background: rgba(24, 24, 28, 0.96);
  border: 1px solid rgba(99, 226, 183, 0.25);
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(8px);
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

/* ============================ 识图（反向图片搜索） ============================ */
.reverse-view {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  min-height: 0;
}

/* 拖拽框 */
.reverse-dropzone {
  flex: 1;
  min-height: 320px;
  border: 2px dashed rgba(99, 226, 183, 0.4);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  text-align: center;
  padding: 24px;
}

.reverse-dropzone:hover,
.reverse-dropzone.drop-over {
  border-color: #63e2b7;
  background: rgba(99, 226, 183, 0.08);
}

.reverse-dropzone-icon {
  font-size: 48px;
}

.reverse-dropzone-title {
  font-size: 18px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.9);
}

.reverse-dropzone-tip {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.55);
}

.reverse-dropzone-sites {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
  line-height: 1.8;
}

/* 搜索中进度 */
.reverse-progress {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 20px;
}

.reverse-progress-title {
  font-size: 15px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.85);
  margin-bottom: 8px;
}

.reverse-progress-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
}

.reverse-progress-name {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.8);
}

.reverse-progress-running {
  font-size: 12px;
  color: #63e2b7;
}

.reverse-progress-ok {
  font-size: 12px;
  color: #63e2b7;
  font-weight: 600;
}

.reverse-progress-fail {
  font-size: 12px;
  color: #e88080;
}

/* 结果展示 */
.reverse-results {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.reverse-results-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.reverse-results-title {
  font-size: 15px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.9);
}

.reverse-site-block {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  overflow: hidden;
}

.reverse-site-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: rgba(99, 226, 183, 0.07);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.reverse-site-name {
  font-size: 14px;
  font-weight: 600;
  color: #63e2b7;
}

.reverse-site-count {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
}

.reverse-site-link {
  margin-left: auto;
  font-size: 12px;
  color: #63e2b7;
  text-decoration: none;
}

.reverse-site-link:hover {
  text-decoration: underline;
}

.reverse-item-list {
  display: flex;
  flex-direction: column;
}

.reverse-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.reverse-item:last-child {
  border-bottom: none;
}

.reverse-item.clickable {
  cursor: pointer;
}

.reverse-item.clickable:hover {
  background: rgba(255, 255, 255, 0.04);
}

.reverse-item-thumb {
  width: 72px;
  height: 54px;
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.06);
  display: flex;
  align-items: center;
  justify-content: center;
}

.reverse-item-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.reverse-item-thumb-empty {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.35);
}

.reverse-item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.reverse-item-title {
  font-size: 13px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.9);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reverse-item-subtitle {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reverse-item-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.reverse-item-url {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.35);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reverse-item-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.reverse-empty {
  text-align: center;
  padding: 40px 20px;
  color: rgba(255, 255, 255, 0.45);
  font-size: 13px;
}

/* 日间模式适配 */
html.light-mode .reverse-dropzone-title {
  color: #333;
}

html.light-mode .reverse-dropzone-tip {
  color: #777;
}

html.light-mode .reverse-dropzone-sites {
  color: #999;
}

html.light-mode .reverse-progress-title,
html.light-mode .reverse-results-title {
  color: #333;
}

html.light-mode .reverse-progress-item,
html.light-mode .reverse-item.clickable:hover {
  background: rgba(0, 0, 0, 0.04);
}

html.light-mode .reverse-progress-name,
html.light-mode .reverse-item-title {
  color: #333;
}

html.light-mode .reverse-site-block {
  border-color: rgba(0, 0, 0, 0.1);
}

html.light-mode .reverse-site-header {
  background: rgba(99, 226, 183, 0.12);
  border-bottom-color: rgba(0, 0, 0, 0.08);
}

html.light-mode .reverse-site-count,
html.light-mode .reverse-item-subtitle {
  color: #777;
}

html.light-mode .reverse-item {
  border-bottom-color: rgba(0, 0, 0, 0.06);
}

html.light-mode .reverse-item-thumb {
  background: rgba(0, 0, 0, 0.05);
}

html.light-mode .reverse-item-thumb-empty {
  color: #aaa;
}

html.light-mode .reverse-item-url {
  color: #999;
}

html.light-mode .reverse-empty {
  color: #888;
}

/* ==================== PA 右键属性菜单 ==================== */
.pa-ctx-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1200;
}

.pa-ctx-menu {
  position: fixed;
  z-index: 1201;
  min-width: 190px;
  background: #26262b;
  border: 1px solid #3a3a44;
  border-radius: 8px;
  padding: 4px;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.55);
  user-select: none;
}

.pa-ctx-header {
  font-size: 12px;
  color: #7f7f7f;
  padding: 6px 10px 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  border-bottom: 1px solid #2d2d33;
  margin-bottom: 4px;
}

.pa-ctx-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  font-size: 13px;
  color: #d8d8de;
  border-radius: 6px;
  cursor: pointer;
}

.pa-ctx-item:hover {
  background: #33333c;
  color: #63e2b7;
}

.pa-ctx-icon {
  font-size: 13px;
  width: 16px;
  text-align: center;
}

html.light-mode .pa-ctx-menu {
  background: #fff;
  border-color: #ddd;
}

html.light-mode .pa-ctx-header {
  color: #999;
  border-bottom-color: #eee;
}

html.light-mode .pa-ctx-item {
  color: #333;
}

html.light-mode .pa-ctx-item:hover {
  background: #f0f7f4;
  color: #18a058;
}
</style>
