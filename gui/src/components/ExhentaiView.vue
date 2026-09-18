<template>
  <!-- ExHentai 搜索选项栏（复刻原版搜索页过滤按钮），改动后自动按新条件重新搜索 -->
  <div v-if="mode === 'options'" class="ex-search-options">
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
        :class="{ on: exPopularMode }"
        title="与主站相同的首页推荐内容（最新画廊）"
        @click="$emit('ex-popular', 1)"
      >🏠 首页推荐</button>
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

  <!-- 主视图：画廊详情 > 浏览器 > 搜索结果（与拆分前 RightPanel v-else-if 链同序；
       详情需无文件列表且非内联模式；搜索结果在解析中时仅内联模式保留） -->
  <div v-else-if="(exGalleryDetail || exDetailLoading) && fileList.length === 0 && !exInlineDetail" class="ex-detail">
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
              <tr v-if="exGalleryDetail.length"><td>张数</td><td>{{ exGalleryDetail.length }}</td></tr>
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
                @click="exRequestTorrents(exGalleryDetail.url)"
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

  <!-- 浏览器视图（webview 独立会话 persist:exhentai，cookie 持久化保存） -->
  <div v-else-if="exViewMode === 'browser'" class="ex-browser">
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
        <n-button :type="exViewMode === 'browser' ? 'primary' : 'default'" size="small" @click="$emit('ex-show-browser')">浏览器</n-button>
        <n-button :type="exViewMode === 'search' ? 'primary' : 'default'" size="small" @click="$emit('ex-set-viewmode', 'search')">搜索结果</n-button>
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

  <!-- 搜索结果视图（EX 内联详情模式下解析中也保留，进度显示在内联区块底部）；
       原 :on-scroll="handleScroll" 对 EX 为空操作（仅 bunkr/coomer 生效），省略 -->
  <n-scrollbar v-else-if="searchResults.length > 0 && (!inspecting || exInlineDetail)" class="search-results" trigger="none" :content-style="{ padding: '12px 16px' }">
    <div class="ex-results">
      <!-- 工具栏：显示模式切换 + 批量收藏 + 结果统计 -->
      <div class="ex-toolbar">
        <n-button-group size="tiny">
          <n-button size="tiny" :type="exDisplayMode === 'list' ? 'primary' : 'default'" @click="exDisplayMode = 'list'" title="列表视图（原版 List 模式）">列表</n-button>
          <n-button size="tiny" :type="exDisplayMode === 'thumbnail' ? 'primary' : 'default'" @click="exDisplayMode = 'thumbnail'" title="缩略图视图（原版 Thumbnail 模式）">缩略图</n-button>
        </n-button-group>
        <!-- 批量下载：独立开关按钮（默认关；开启后点卡片勾选画廊，逐个选/取消） -->
        <n-button
          class="batch-cta"
          size="small"
          :type="exBatchMode ? 'warning' : 'primary'"
          :disabled="exBatchRunning"
          :title="exBatchRunning
            ? '批量解析进行中，请稍候…'
            : (exBatchMode ? '退出勾选模式（清空已勾选）' : '进入勾选模式：点卡片勾选画廊，批量解析下载')"
          @click="toggleExBatchMode"
        >{{ exBatchRunning
          ? `批量解析中 (${exBatchProgress.done}/${exBatchProgress.total})`
          : (exBatchMode ? `取消勾选${exChecked.length ? `(${exChecked.length})` : ''}` : '批量下载') }}</n-button>
        <!-- 下载选中（列表/缩略图勾选即显示，无需进入勾选模式） -->
        <n-button
          v-if="exChecked.length && !exBatchMode"
          size="tiny"
          type="warning"
          ghost
          title="解析选中画廊的全部图片并加入文件列表，可统一勾选下载"
          @click="$emit('ex-batch-download', exChecked)"
        >下载选中 ({{ exChecked.length }})</n-button>
        <!-- 批量进行中：可取消（已派发的会完成，剩余不再解析，不自动下载） -->
        <n-button
          v-if="exBatchRunning"
          size="tiny"
          type="error"
          ghost
          title="停止派发剩余画廊；已发出的解析请求会完成，完成后不自动下载"
          @click="$emit('ex-batch-cancel')"
        >取消批量</n-button>
        <template v-if="exBatchMode">
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
          <n-button
            size="tiny"
            type="warning"
            ghost
            :disabled="!searchResults.length"
            title="跳过勾选，直接批量解析当前页全部画廊"
            @click="$emit('ex-batch-download', searchResults.map(i => i.album_url).filter(Boolean))"
          >批量下载全部 ({{ searchResults.length }})</n-button>
          <template v-if="exBatchMode">
            <n-button size="tiny" :disabled="!searchResults.length" title="勾选当前页全部画廊"
                      @click="exSelectChecked('all')">全选</n-button>
            <n-button size="tiny" :disabled="!searchResults.length" title="勾选状态反转"
                      @click="exSelectChecked('invert')">反选</n-button>
            <n-button size="tiny" :disabled="!exChecked.length" title="清空全部勾选"
                      @click="exSelectChecked('clear')">清空</n-button>
          </template>
          <!-- 选中操作：全选 / 反选 / 取消全部 -->
          <n-button-group v-if="searchResults.length" size="tiny">
            <n-button size="tiny" quaternary title="选中当前页全部画廊" @click="exCheckAll">全选</n-button>
            <n-button size="tiny" quaternary title="反转选择（未选的变为选中）" @click="exInvertCheck">反选</n-button>
            <n-button size="tiny" quaternary title="取消全部选择" @click="exChecked = []">取消全部</n-button>
          </n-button-group>
        </template>
        <!-- 查看收集的文件：批量收集完成后解锁文件列表（可对单个文件勾选/取消后再下载） -->
        <n-button
          v-if="fileList.length > 0 && batchFileCollected && !exBatchRunning"
          size="tiny"
          type="info"
          ghost
          title="显示批量解析收集的文件列表（可单独勾选/取消后下载）"
          @click="$emit('show-collected-files')"
        >查看收集的文件 ({{ fileList.length }})</n-button>
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
            :class="{ 'ex-tr-alt': idx % 2 === 1, 'ex-tr-checked': exBatchMode && exChecked.includes(item.album_url) }"
            :title="exBatchMode ? '点击勾选/取消该画廊' : '点击查看画廊详情'"
            @click="exBatchMode ? toggleExChecked(item.album_url) : $emit('ex-open-gallery', item.album_url)"
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
          :class="{ 'ex-thumb-card-checked': exBatchMode && exChecked.includes(item.album_url) }"
          :title="exBatchMode ? `${item.album_name}（点击勾选/取消）` : item.album_name"
          @click="exBatchMode ? toggleExChecked(item.album_url) : $emit('ex-open-gallery', item.album_url)"
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
            <!-- 多选勾选框（仅批量勾选模式显示；与列表模式共用 exChecked） -->
            <label v-if="exBatchMode" class="ex-thumb-check" title="勾选后可批量下载" @click.stop>
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

          <!-- 画廊信息（封面/元数据，信息到位即显示，不等解析完成） -->
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
                <tr v-if="exGalleryDetail.length"><td>张数</td><td>{{ exGalleryDetail.length }}</td></tr>
                <tr v-if="exGalleryDetail.rating">
                  <td>评分</td>
                  <td>⭐ {{ exGalleryDetail.rating }}<span v-if="exGalleryDetail.rating_count">（{{ exGalleryDetail.rating_count }} 人评分）</span></td>
                </tr>
              </table>
              <div class="ex-detail-actions">
                <n-button
                  size="small"
                  type="primary"
                  title="解析画廊全部图片进入文件列表（勾选后点下载）"
                  @click="$emit('open-album', { album_url: exGalleryDetail.url, album_name: exGalleryDetail.title })"
                >⬇ 解析图片列表</n-button>
                <n-button
                  size="small"
                  type="warning"
                  ghost
                  :loading="torrentLoading"
                  title="查看画廊附带的种子（可获取磁力或保存种子文件）"
                  @click="exRequestTorrents(exGalleryDetail.url)"
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
          <!-- 解析中：进度动画（封面/信息已显示，图片在下方就位） -->
          <div v-if="inspecting || exDetailLoading" class="ex-inline-detail-loading">
            <n-spin size="medium" />
            <span>
              {{ inspecting ? '正在解析文件列表...' : '正在获取画廊信息...' }}
              <template v-if="inspecting && inspectProgress && inspectProgress.total > 0">
                （{{ inspectProgress.current }}/{{ inspectProgress.total }}）
              </template>
            </span>
          </div>
          <template v-else>

          <!-- 文件列表（工具栏 + 方格/列表 + 下载栏，与独立文件列表视图一致）——全站共用设施，由 RightPanel 经插槽提供 -->
          <slot name="inline-filelist" />
          </template>
      </div>
    </div>
  </n-scrollbar>
</template>

<script setup>
// Exhentai（EX站）视图组件（从 RightPanel.vue 拆出，重构 f2，沿用 PixivPanel/XhView 模式：
// props 下行 + 事件上行经 RightPanel 转发到 App）。种子/磁力弹窗及其数据仍属 RightPanel
// （App 后端事件经 defineExpose 注入），本组件以 ex-torrents 事件触发；内联详情下方的
// 文件列表为全站共用设施，经 #inline-filelist 插槽由 RightPanel 提供（保持父作用域样式/逻辑）。
import { ref, computed, watch } from 'vue'
import { NButton, NButtonGroup, NInput, NInputNumber, NSelect, NSwitch, NTag, NSpin, NScrollbar } from 'naive-ui'
import PaginationBar from './PaginationBar.vue'

const props = defineProps({
  mode: { type: String, default: 'main' },               // options=搜索选项栏 | main=主视图
  site: { type: String, default: 'bunkr' },
  settings: { type: Object, default: () => ({}) },
  searchResults: { type: Array, default: () => [] },
  searchHasMore: { type: Boolean, default: false },
  searchPage: { type: Number, default: 1 },
  searchTotalPages: { type: Number, default: 0 },
  searchTotalResults: { type: Number, default: 0 },
  searching: { type: Boolean, default: false },
  inspecting: { type: Boolean, default: false },
  inspectProgress: { type: Object, default: () => ({}) },
  albumInfo: { type: Object, default: () => ({}) },
  fileList: { type: Array, default: () => [] },
  batchFileCollected: { type: Boolean, default: false },
  exGalleryDetail: { type: Object, default: null },   // EX 画廊详情（完整信息 + 分组标签）
  exDetailLoading: { type: Boolean, default: false }, // 详情加载中
  exInlineDetail: { type: Boolean, default: false },
  exFavMode: { type: Boolean, default: false },       // 当前结果视图是否为"我的收藏"
  exPopularMode: { type: Boolean, default: false },    // 当前结果视图是否为"首页推荐"
  exBatchRunning: { type: Boolean, default: false },  // EX 批量解析进行中
  exBatchProgress: { type: Object, default: () => ({ done: 0, total: 0 }) }, // 批量进度 done/total
  exHiddenTags: { type: Array, default: () => [] },    // EX 隐藏标签列表（长期保存）
  exhentaiUser: { type: String, default: '' },
  exViewMode: { type: String, default: 'search' },     // browser | search（状态在 RightPanel：链条件/切回搜索 watch 使用）
  torrentLoading: { type: Boolean, default: false },   // 种子列表获取中（弹窗在 RightPanel）
  translatedTitles: { type: Object, default: () => ({}) },     // {原标题: 译文}，展示时回填
})

const emit = defineEmits([
  // 选项栏
  'update:ex-search', 'ex-popular', 'ex-favorites', 'ex-add-hidden-tag', 'ex-delete-hidden-tag',
  // 主视图
  'ex-open-gallery', 'ex-close-detail', 'ex-torrents', 'open-album', 'ex-batch-download',
  'ex-batch-cancel', 'show-collected-files', 'clear-batch-tasks', 'go-page', 'back-to-search',
  'add-favorite', 'ex-parse-gallery', 'ex-sync-cookies', 'ex-set-viewmode', 'ex-show-browser',
  'update:search-query', 'search',
])

// ---------- 共用工具（PixivPanel/XhView 先例：本地内置，不依赖 RightPanel 作用域） ----------
// 判断输入是否为 ExHentai 画廊链接（exhentai.org / e-hentai.org）
function isExhentaiUrl(text) {
  return /(e-hentai|exhentai)\.org\/g\/\d+\/[0-9a-f]+/i.test(text)
}

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

// 标签搜索（EX 场景：回填搜索词并触发搜索；共用版 searchTag 的 pawchive 分支在此不适用）
function searchTag(t) {
  if (!t) return
  emit('update:search-query', t)
  emit('search')
}

// 请求种子/磁力弹窗（弹窗与其数据在 RightPanel，App 后端事件经 defineExpose 注入）
function exRequestTorrents(url) {
  if (!url) return
  emit('ex-torrents', url)
}

// 浏览器"磁力"按钮：仅画廊页可用（保留原 exShowTorrents 的 exIsGallery 守卫）
function exShowTorrents() {
  if (!exIsGallery.value) return
  exRequestTorrents(exCurrentUrl.value)
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

const exWebviewRef = ref(null)
const exAddress = ref('https://exhentai.org/')
const exLoading = ref(false)
const exNavState = ref({ canBack: false, canForward: false })
const cookieSyncing = ref(false)

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

// 显示模式：列表（原版 List）/ 缩略图（原版 Thumbnail）
const exDisplayMode = ref('list')
// 列表模式勾选的画廊（批量收藏，对应原版复选框逻辑）
const exChecked = ref([])
// EX 批量下载勾选模式（默认关：点卡片=打开画廊详情；开启后点卡片=勾选/取消勾选）
const exBatchMode = ref(false)
function toggleExBatchMode() {
  exBatchMode.value = !exBatchMode.value
  if (!exBatchMode.value) exChecked.value = []  // 退出勾选模式清空选择
}
// 批量模式下勾选/取消单个画廊（点卡片切换）
function toggleExChecked(galleryUrl) {
  if (!galleryUrl) return
  const idx = exChecked.value.indexOf(galleryUrl)
  if (idx >= 0) exChecked.value.splice(idx, 1)
  else exChecked.value.push(galleryUrl)
}
// 全选/反选/清空当前搜索结果页的画廊勾选
function exSelectChecked(mode) {
  const all = (props.searchResults || []).map(i => i.album_url).filter(Boolean)
  if (mode === 'clear') { exChecked.value = []; return }
  if (mode === 'all') { exChecked.value = [...all]; return }
  exChecked.value = all.filter(u => !exChecked.value.includes(u))
}

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
</script>

<style scoped>
/* ExhentaiView 样式：自 RightPanel.vue 迁出（move）或复制（copy：ex-search-options / ex-cat-chip /
   ex-detail 系列 / card-favorite-btn 等仍被 RightPanel 内 pawchive、javdb、hanime、asmr 视图共用），保持原级联顺序 */

/* ============ 搜索结果 ============ */
.search-results {
  flex: 1;
  min-height: 0;
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
/* ========== ExHentai 画廊详情（复刻原版画廊页信息区） ========== */
.ex-detail {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
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
.card-favorite-btn:hover {
  color: #ff6b81;
  transform: scale(1.15);
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
/* 批量勾选模式：已勾选的行高亮（勾选框隐藏模式下靠它辨识选中项） */
.ex-tr-checked {
  background: #4a4235 !important;
}
html.light-mode .ex-tr-checked {
  background: #f3e8d8 !important;
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
</style>
