<template>
  <n-config-provider :theme="naiveTheme" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <n-dialog-provider>
        <div class="app-layout">
          <LeftPanel
            :settings="settings"
            :site="settings.site || 'bunkr'"
            :pawchive-user="pawchiveUser"
            :twitter-user="twitterUser"
            :exhentai-user="exhentaiUser"
            :iwara-user="iwaraUser"
            :iwara-login-loading="iwaraLoginLoading"
            :iw-site="iwSite"
            @iw-set-site="handleIwSetSite"
            :hanime-user="hanimeUser"
            :hanime-login-loading="hanimeLoginLoading"
            @hanime-login="handleHanimeLogin"
            @hanime-logout="handleHanimeLogout"
            @hanime-set-proxy="handleHanimeSetProxy"
            :asmr-user="asmrUser"
            :asmr-login-loading="asmrLoginLoading"
            @asmr-login="handleAsmrLogin"
            @asmr-logout="handleAsmrLogout"
            @asmr-set-proxy="handleAsmrSetProxy"
            @oreno-set-proxy="handleOrenoSetProxy"
            :xhamster-user="xhamsterUser"
            :pornhub-user="pornhubUser"
            :xvideos-user="xvideosUser"
            @site-oauth-login="handleSiteOAuthLogin"
            @site-logout="handleSiteLogout"
            @site-set-proxy="handleSiteSetProxy"
            :login-info="loginInfo"
            :login-loading="pawchiveLoginLoading"
            :search-history="searchHistory"
            :local-favorites="localFavorites"
            @update:settings="updateSettings"
            @clear-cache="handleClearCache"
            @toggle-downloads="toggleDownloadManager"
            :float-visible="floatVisible"
            @toggle-float="toggleFloat"
            :backend-ready="backendReady"
            :backend-error="backendError"
            @pawchive-login="handlePawchiveLogin"
            @pawchive-logout="handlePawchiveLogout"
            @pawchive-favorites="handlePawchiveFavorites"
            @twitter-set-cookies="handleTwitterSetCookies"
            @twitter-logout="handleTwitterLogout"
            @twitter-set-proxy="handleTwitterSetProxy"
            @iwara-login="handleIwaraLogin"
            @iwara-logout="handleIwaraLogout"
            @iwara-set-proxy="handleIwaraSetProxy"
            :follow-tags="twFollowTags"
            :theme-mode="settings.theme || 'dark'"
            @toggle-theme="toggleTheme"
            @tw-add-follow-tag="handleTwAddFollowTag"
            @tw-delete-follow-tag="handleTwDeleteFollowTag"
            @tw-clear-cache="handleTwClearCache"
            @exhentai-set-cookies="handleExSyncCookies"
            @exhentai-logout="handleExLogout"
            @open-login-page="handleOpenLoginPage"
            @fetch-cookies="handleFetchCookies"
            @refresh-login="handleRefreshLogin"
            @save-account="handleSaveAccount"
            @switch-account="handleSwitchAccount"
            @delete-account="handleDeleteAccount"
            @use-history="handleUseHistory"
            @delete-history-item="handleDeleteHistoryItem"
            @clear-history="handleClearHistory"
            @open-favorite="handleOpenFavorite"
            @delete-favorite="handleDeleteFavorite"
            @translate-youdao="handleTranslateYoudao"
            @translate-free="handleTranslateFree"
            :translate-result="translateResult"
            @check-github-update="handleCheckGithubUpdate"
            :github-update-info="githubUpdateInfo"
            @shortcut-change="handleShortcutChange"
            @prevent-sleep-change="handlePreventSleepChange"
          />
          <RightPanel
            ref="rightPanelRef"
            :settings="settings"
            :site="settings.site || 'bunkr'"
            @update:site="updateSite"
            :search-mode="settings.pawchive_search_mode || 'artist'"
            @update:search-mode="updateSearchMode"
            :search-query="searchQuery"
            @update:search-query="searchQuery = $event"
            :searching="searching"
            :search-results="searchResults"
            :search-has-more="searchHasMore"
            :search-page="searchPage"
            :search-total-pages="searchTotalPages"
            :search-total-results="searchTotalResults"
            :inspecting="inspecting"
            :inspect-progress="inspectProgress"
            :album-info="albumInfo"
            :file-list="fileList"
            :came-from-search="cameFromSearch"
            :downloading="downloading"
            :download-progress="downloadProgress"
            :logs="logs"
            :history="history"
            :media-proxy-port="mediaProxyPort"
            @resolve-media="handleResolveMedia"
            :exhentai-user="exhentaiUser"
            :ex-gallery-detail="exGalleryDetail"
            :ex-detail-loading="exDetailLoading"
            :ex-fav-mode="exFavMode"
            :pa-post-detail="paPostDetail"
            :pa-detail-loading="paDetailLoading"
            :pa-artist-posts="paArtistPosts"
            :pa-artist-posts-loading="paArtistPostsLoading"
            :ex-hidden-tags="exHiddenTags"
            :tw-follow-mode="twFollowMode"
            :tw-follow-loading="twFollowLoading"
            :tw-follow-items="twFollowItems"
            :tw-follow-has-more="twFollowHasMore"
            :tw-follow-error="twFollowError"
            :tw-follow-tags="twFollowTags"
            :tw-follow-label="twFollowLabel"
            :tw-view-user="twViewUser"
            :tw-browse-feed="twBrowseFeed"
            :tw-browse-loading="twBrowseLoading"
            :tw-browse-progress="twBrowseProgress"
            :tw-browse-updated-at="twBrowseUpdatedAt"
            :tw-browse-error="twBrowseError"
            :tw-browse-has-more="twBrowseHasMore"
            :tw-local-search="twLocalSearch"
            :tw-search-tweets="twSearchTweets"
            :iw-view="iwView"
            :iw-site="iwSite"
            :iw-home-items="iwHomeItems"
            :iw-home-loading="iwHomeLoading"
            :iw-home-has-more="iwHomeHasMore"
            :iw-home-error="iwHomeError"
            :iw-home-mode="iwHomeMode"
            :iw-follow-items="iwFollowItems"
            :iw-follow-loading="iwFollowLoading"
            :iw-follow-has-more="iwFollowHasMore"
            :iw-follow-error="iwFollowError"
            :iw-friend-items="iwFriendItems"
            :iw-friend-loading="iwFriendLoading"
            :iw-friend-has-more="iwFriendHasMore"
            :iw-friend-error="iwFriendError"
            :iw-detail="iwDetail"
            :iw-detail-loading="iwDetailLoading"
            :iw-comments="iwComments"
            :iw-comments-has-more="iwCommentsHasMore"
            :iw-batch-running="iwBatchRunning"
            :iw-batch-progress="iwBatchProgress"
            :ha-view="haView"
            :ha-sections="haSections"
            :ha-home-loading="haHomeLoading"
            :ha-home-error="haHomeError"
            :ha-genres="haGenres"
            :ha-sorts="haSorts"
            :ha-detail="haDetail"
            :ha-detail-loading="haDetailLoading"
            :ha-comments="haComments"
            :ha-user-tab="haUserTab"
            :ha-user-items="haUserItems"
            :ha-user-loading="haUserLoading"
            :ha-user-has-more="haUserHasMore"
            :ha-user-page="haUserPage"
            :ha-user-label="haUserLabel"
            :ha-batch-running="haBatchRunning"
            :ha-batch-progress="haBatchProgress"
            :or-view="orView"
            :or-home-items="orHomeItems"
            :or-home-loading="orHomeLoading"
            :or-home-has-more="orHomeHasMore"
            :or-home-error="orHomeError"
            :or-sorts="orSorts"
            :or-list="orList"
            :or-list-loading="orListLoading"
            :or-list-error="orListError"
            :or-tags="orTags"
            :or-tag-groups="orTagGroups"
            :or-tag-group-title="orTagGroupTitle"
            :or-tags-loading="orTagsLoading"
            :or-characters="orCharacters"
            :or-chars-loading="orCharsLoading"
            :or-authors="orAuthors"
            :or-authors-page="orAuthorsPage"
            :or-authors-has-more="orAuthorsHasMore"
            :or-authors-loading="orAuthorsLoading"
            :or-detail="orDetail"
            :or-detail-loading="orDetailLoading"
            :or-batch-running="orBatchRunning"
            :or-batch-progress="orBatchProgress"
            :asmr-view="asmrView"
            :asmr-items="asmrItems"
            :asmr-list-loading="asmrListLoading"
            :asmr-has-more="asmrHasMore"
            :asmr-error="asmrError"
            :asmr-label="asmrLabel"
            :asmr-total="asmrTotal"
            :asmr-orders="asmrOrders"
            :asmr-filter="asmrFilter"
            :asmr-index-items="asmrIndexItems"
            :asmr-index-loading="asmrIndexLoading"
            :asmr-detail="asmrDetail"
            :asmr-files="asmrFiles"
            :asmr-detail-loading="asmrDetailLoading"
            :asmr-logged-in="asmrLoggedIn"
            :asmr-batch-running="asmrBatchRunning"
            :asmr-batch-progress="asmrBatchProgress"
            :auto-translate-to="autoTranslateTo"
            @update:auto-translate-to="handleUpdateAutoTranslateTo"
            :auto-translating="autoTranslating"
            :auto-translate-mode="autoTranslateMode"
            :auto-translate-lang-options="autoTranslateLangOptions"
            :translated-titles="translatedTitles"
            @auto-translate="handleAutoTranslate"
            @toggle-auto-translate-mode="handleToggleAutoTranslateMode"
            @update:tw-local-search="twLocalSearch = $event; handleTwLocalSearch($event)"
            @tw-follow-list="handleTwFollowList"
            @tw-follow-load-more="handleTwFollowLoadMore"
            @tw-follow="handleTwFollow"
            @tw-unfollow="handleTwUnfollow"
            @tw-set-follow-tag="handleTwSetFollowTag"
            @tw-open-user="handleTwOpenUser"
            @tw-user-list="handleTwUserList"
            @tw-browse="handleTwBrowse"
            @tw-browse-more="handleTwBrowseMore"
            @tw-back="handleTwBack"
            @iw-set-site="handleIwSetSite"
            @iw-home="handleIwHome"
            @iw-home-more="handleIwHomeMore"
            @iw-subscribed="handleIwSubscribed"
            @iw-following="handleIwFollowing"
            @iw-following-more="handleIwFollowingMore"
            @iw-friends="handleIwFriends"
            @iw-friends-more="handleIwFriendsMore"
            @iw-follow="u => handleIwFollow(u.user_id || u.author_id, true)"
            @iw-unfollow="u => handleIwFollow(u.user_id || u.author_id, false)"
            @iw-open-detail="item => handleIwOpenDetail(item.video_id)"
            @iw-detail-back="handleIwDetailBack"
            @iw-comments-more="handleIwCommentsMore"
            @iw-open-user="handleIwOpenUser"
            @iw-search-tag="handleIwSearchTag"
            @iw-batch-download="handleIwBatchDownload"
            @ha-home="handleHaHome"
            @ha-open-detail="item => handleHanimeOpenDetail(item.video_id)"
            @ha-detail-back="handleHaDetailBack"
            @hanime-add-comment="handleHanimeAddComment"
            @hanime-save-video="handleHanimeSaveVideo"
            @hanime-user-videos="handleHanimeUserVideos"
            @hanime-user-back="handleHaHome"
            @update:ha-search="handleHanimeSearchUpdate"
            @hanime-search-tag="handleHanimeSearchTag"
            @hanime-batch-download="handleHanimeBatchDownload"
            @or-home="handleOrHome"
            @or-home-more="handleOrHomeMore"
            @or-open-detail="item => handleOrenoOpenDetail(item.video_id, item.site_key)"
            @or-detail-back="handleOrDetailBack"
            @or-tag="handleOrenoTag"
            @or-author="handleOrenoAuthor"
            @or-character="handleOrenoCharacter"
            @or-origin="handleOrenoOrigin"
            @or-list-back="handleOrListBack"
            @or-list-more="handleOrListMore"
            @or-tags-index="handleOrenoTagsIndex"
            @or-tag-group="handleOrenoTagGroup"
            @or-characters="handleOrenoCharacters"
            @or-authors-index="handleOrenoAuthorsIndex"
            @or-browse-back="handleOrBrowseBack"
            @or-favorites="handleOrenoFavorites"
            @or-toggle-favorite="handleOrenoToggleFavorite"
            @or-sort-update="handleOrenoSortUpdate"
            @or-batch-download="handleOrenoBatchDownload"
            @asmr-popular="handleAsmrPopular"
            @asmr-works="handleAsmrWorks"
            @asmr-favorites="handleAsmrFavorites"
            @asmr-more="handleAsmrMore"
            @update:asmr-search="handleAsmrSearchUpdate"
            @asmr-index="handleAsmrIndex"
            @asmr-index-pick="handleAsmrIndexPick"
            @asmr-open-detail="handleAsmrOpenDetail"
            @asmr-detail-back="handleAsmrDetailBack"
            @asmr-toggle-favorite="handleAsmrToggleFavorite"
            @asmr-search-tag="handleAsmrSearchTag"
            @asmr-open-circle="handleAsmrOpenCircle"
            @asmr-open-va="handleAsmrOpenVa"
            @asmr-batch-download="handleAsmrBatchDownload"
            @search="handleSearch"
            @load-more="handleLoadMore"
            @go-page="handleGoPage"
            @open-album="openSearchResult"
            @back-to-search="handleBackToSearch"
            @download="handleDownload"
            @delete-history="deleteHistoryRecord"
            @open-file="openFilePath"
            @show-folder="showFileInFolder"
            @ex-get-torrents="handleExGetTorrents"
            @ex-get-magnet="handleExGetMagnet"
            @ex-parse-gallery="handleExParseGallery"
            @ex-sync-cookies="handleExSyncCookies"
            @update:ex-search="handleExSearchUpdate"
            @ex-favorites="handleExFavorites"
            @ex-open-gallery="handleExOpenGallery"
            @ex-batch-download="handleExBatchDownload"
            @ex-close-detail="handleExCloseDetail"
            @ex-save-torrent="handleExSaveTorrent"
            @pa-open-post="handlePaOpenPost"
            @pa-close-detail="handlePaCloseDetail"
            @pa-favorites="handlePawchiveFavorites"
            @pa-open-artist="handlePaOpenArtist"
            @pa-close-artist="handlePaCloseArtist"
            @ex-add-hidden-tag="handleExAddHiddenTag"
            @ex-delete-hidden-tag="handleExDeleteHiddenTag"
            @add-favorite="handleAddFavorite"
          />
        </div>

        <!-- 主窗口内的详细下载内容面板（从下载管理窗口双击/右键跳转） -->
        <DownloadManagerPanel
          :visible="detailVisible"
          :tasks="downloadTasks"
          :shutdown-on="shutdownOn"
          :focus-task-id="detailTaskId"
          @close="detailVisible = false"
          @pause="pauseTask"
          @resume="resumeTask"
          @resume-all="resumeAllTasks"
          @cancel="cancelTask"
          @remove="removeTask"
          @toggle-shutdown="toggleShutdown"
        />

        <!-- 下载重名手动改名弹窗（skip_duplicates + manual_rename 开启时触发） -->
        <n-modal v-model:show="renameModal.visible" preset="dialog" title="重名文件改名" style="width: 520px">
          <div class="rename-modal">
            <div class="rename-tip">已存在同名但大小不同的文件，请输入新文件名：</div>
            <div class="rename-row"><span class="rename-label">原文件名</span><span class="rename-value">{{ renameModal.filename }}</span></div>
            <div class="rename-row"><span class="rename-label">已存在大小</span><span class="rename-value">{{ formatSize(renameModal.existingSize) }}</span></div>
            <div class="rename-row"><span class="rename-label">本次下载大小</span><span class="rename-value">{{ formatSize(renameModal.newSize) }}</span></div>
            <n-input
              v-model:value="renameModal.newName"
              size="small"
              placeholder="输入新文件名（含扩展名，如 photo-2.jpg）"
              @keyup.enter="confirmRenameDownload"
            />
            <div class="rename-hint">点击"改名并下载"后将以新文件名重新下载；关闭窗口则跳过该文件</div>
          </div>
          <template #action>
            <n-button size="small" @click="renameModal.visible = false">跳过该文件</n-button>
            <n-button size="small" type="primary" :disabled="!renameModal.newName.trim()" @click="confirmRenameDownload">
              改名并下载
            </n-button>
          </template>
        </n-modal>

        <!-- EX 批量下载母文件夹命名弹窗（确定批量下载时弹出） -->
        <n-modal v-model:show="exBatchFolderVisible" preset="dialog" title="批量下载 - 母文件夹命名" style="width: 520px">
          <div class="rename-modal">
            <div class="rename-tip">是否将搜索词「{{ lastSearchKeyword || '（无搜索词）' }}」作为新的母文件夹名称？</div>
            <div class="rename-hint">每个画廊将按其标题作为子文件夹归入母文件夹下；留空则不使用母文件夹。</div>
            <n-input
              v-model:value="exBatchFolderName"
              size="small"
              placeholder="母文件夹名称（可修改，留空 = 不使用母文件夹）"
              @keyup.enter="confirmExBatchFolder(true)"
            />
          </div>
          <template #action>
            <n-button size="small" @click="confirmExBatchFolder(false)">不用母文件夹</n-button>
            <n-button size="small" type="primary" @click="confirmExBatchFolder(true)">
              使用并批量解析
            </n-button>
          </template>
        </n-modal>

        <!-- 通用 webview OAuth 登录弹窗（xhamster/pornhub/xvideos 共用） -->
        <WebviewLoginModal
          :show="wvLogin.visible"
          @update:show="v => wvLogin.visible = v"
          :site="wvLogin.site"
          :login-url="wvLogin.loginUrl"
          :home-url="wvLogin.homeUrl"
          :partition="wvLogin.partition"
          :success-patterns="wvLogin.successPatterns"
          :captcha-patterns="wvLogin.captchaPatterns"
          :title="`${wvLogin.site} webview 登录`"
          @login-success="handleSiteLoginSuccess"
          @login-failed="err => message.error(err || '登录失败')"
        />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { ref, reactive, computed, watch, watchEffect, onMounted, onUnmounted } from 'vue'
import { darkTheme, zhCN, dateZhCN, createDiscreteApi } from 'naive-ui'
import LeftPanel from './components/LeftPanel.vue'
import RightPanel from './components/RightPanel.vue'
import DownloadManagerPanel from './components/DownloadManagerPanel.vue'
import WebviewLoginModal from './components/WebviewLoginModal.vue'

// 独立的消息提示（用于在非 Provider 组件中弹出 Toast）
const { message, dialog } = createDiscreteApi(['message', 'dialog'], {
  configProviderProps: { theme: darkTheme },
})

// ============================
// 设置
// ============================
const settings = reactive({
  custom_path: '',
  site: 'bunkr',
  pawchive_search_mode: 'artist',
  pawchive_subfolder: 'date_post',
  exhentai_proxy: 'http://127.0.0.1:10809',
  exhentai_subfolder: 'date_post',
  // ExHentai 搜索过滤选项（对应原版搜索页按钮）
  exhentai_cats: ['misc', 'doujinshi', 'manga', 'artistcg', 'gamecg', 'imageset', 'cosplay', 'asianporn', 'nonh', 'western'],
  exhentai_min_rating: 0,      // 最低评分（0=不限，2-5）
  exhentai_torrents_only: false, // 仅显示有种子的画廊
  exhentai_page_min: 0,        // 最小页数（0=不限）
  exhentai_page_max: 0,        // 最大页数（0=不限）
  // Twitter/X 专属设置
  twitter_proxy: 'http://127.0.0.1:10809',
  twitter_subfolder: 'date_post',
  // Iwara 专属设置（代理留空 = 直连）
  iwara_proxy: '',
  // Hanime1 / Oreno3D / EroMMDTube 专属设置（H站国内需代理；O3D/E站 默认直连）
  hanime_proxy: 'http://127.0.0.1:10809',
  oreno_proxy: '',
  erommd_proxy: '',
  // H站搜索过滤（分类/排序，随搜索选项发送并长期保存）
  hanime_genre: '',
  hanime_sort: '',
  // O3D 列表排序（hot=人気 / favorites=お気に入り / latest=最新 / popularity=閲覧数）
  oreno_sort: '',
  // ASMR 音声站（asmr-100.com）专属设置
  asmr_proxy: '',               // 代理（留空 = 直连）
  asmr_subtitle: false,         // 仅显示带中文字幕的作品
  asmr_order: 'create_date',    // 媒体库排序（ASMR_ORDERS：release/create_date/dl_count/price/rate_average_2dp/review_count）
  asmr_seek_forward: 30,        // 播放器快进秒数
  asmr_seek_back: 5,            // 播放器倒带秒数
  asmr_smooth: false,           // 音质流畅优先（优先低码率流畅播放）
  asmr_smart_path: true,        // 智能路径（按文件夹结构整理下载目录）
  asmr_sound_effect: '',        // 效果音偏好（如：耳舐め/環境音）
  asmr_audio_type: 'mp3',       // 音频类型偏好（mp3>flac>wav>opus>m4a>aac 顺序）
  asmr_show_hot: true,          // 详情页显示热门作品
  asmr_show_recommend: true,    // 详情页显示推荐作品
  asmr_show_similar: true,      // 详情页显示相似作品
  // 每站点自定义子文件夹模板（留空=使用组织规则；变量 {date}/{date_full}/{title}/{id}）
  pawchive_folder_template: '',
  exhentai_folder_template: '',
  twitter_folder_template: '',
  iwara_folder_template: '',
  search_history_switch_site: false,
  connections: 4,
  concurrent_files: 2,
  rate_limit: null,
  max_retries: 5,
  clean_name: false,
  organize_by_type: false,
  // 下载去重：跳过重复项目 / 重名手动改名（关闭=自动序号顺延）
  skip_duplicates: false,
  manual_rename: false,
  // 界面主题：dark=夜间 / light=日间
  theme: 'dark',
  date_stamp: false,
  no_download_folder: false,
  disable_disk_check: false,
  ignore: [],
  include: [],
  float_visible: true,
  // 全局自动翻译（每站搜索结果常驻）：目标语言 + 持续自动翻译开关
  auto_translate_to: 'zh-CN',
  auto_translate_mode: false,
})

function saveSettings() {
  if (!window.api) return
  window.api.sendCommand({
    cmd: 'save_settings',
    settings: JSON.parse(JSON.stringify(settings)),
  })
}

function updateSettings(newSettings) {
  Object.assign(settings, newSettings)
  saveSettings()
}

// ============================
// 主题（日间 / 夜间）
// ============================
// naive-ui 主题：夜间=darkTheme，日间=null（跟随亮色默认）
const naiveTheme = computed(() => (settings.theme === 'light' ? null : darkTheme))
// 切换主题（设置持久化 + html 根类名，供自定义 CSS 覆盖）
function toggleTheme() {
  updateSettings({ theme: settings.theme === 'light' ? 'dark' : 'light' })
}
watchEffect(() => {
  document.documentElement.classList.toggle('light-mode', settings.theme === 'light')
})

// ============================
// 状态
// ============================
const url = ref('')
const backendReady = ref(false)
const inspecting = ref(false)
const inspectProgress = reactive({ current: 0, total: 0 })
const albumInfo = reactive({ album_name: '', album_id: '', is_album: false })
const fileList = ref([])
const downloading = ref(false)
const downloadProgress = reactive({})  // filename -> { completed, status, size }
const logs = ref([])

// 搜索状态
const searchQuery = ref('')
const searching = ref(false)
const searchResults = ref([])
const searchPage = ref(1)
const searchHasMore = ref(false)
const searchTotalPages = ref(0)
// 搜索结果总数（EX "Found about N results" / PA 画师匹配数；未知为 0）
const searchTotalResults = ref(0)
// 记录当前文件列表是否来自搜索结果（用于显示"后退"按钮）
const cameFromSearch = ref(false)
// 记住最后一次搜索关键词，便于从相册返回搜索结果时恢复输入框
const lastSearchKeyword = ref('')

// 历史任务
const history = ref([])

// 下载任务（用于悬浮窗汇总显示）
const downloadTasks = ref([])
// 悬浮窗显示状态（默认开，与后端悬浮窗同步）
const floatVisible = ref(true)

// 本地媒体代理端口（在线播放：图片/视频经 127.0.0.1 流式代理）
const mediaProxyPort = ref(0)

// 主窗口内的详细下载面板
const detailVisible = ref(false)
const detailTaskId = ref(null)
// 下载完关机状态（详细面板开关）
const shutdownOn = ref(false)

// Pawchive 登录状态
const pawchiveUser = ref('')
const pawchiveLoginLoading = ref(false)

// 全站点登录信息（账号卡片数据源：用户名/Cookie/账号档案，切换站点不丢失）
const loginInfo = ref({})

// ExHentai 登录状态（webview cookie 同步后由后端验证）
const exhentaiUser = ref('')
const twitterUser = ref('')
// Iwara 登录状态（邮箱 + 密码 → token）
const iwaraUser = ref('')
const iwaraLoginLoading = ref(false)
const exGalleryDetail = ref(null)   // EX 画廊详情（完整信息 + 分组标签）
const exDetailLoading = ref(false)  // 详情加载中
const exFavMode = ref(false)        // 当前搜索结果视图是否为"我的收藏"模式
const exBatchDownloading = ref(false)  // EX 批量下载进行中（inspect_complete 时追加而非替换 fileList）
const exBatchPending = ref(0)            // EX 批量下载待完成的 inspect_complete 计数（异步返回时减一）

// Pawchive 帖子详情（完整信息 + 标签 + 附件预览）
const paPostDetail = ref(null)
const paDetailLoading = ref(false)

// Pawchive 画师子项目列表（点开画师后按发布日期浏览全部帖子）
const paArtistPosts = ref(null)
const paArtistPostsLoading = ref(false)

// ExHentai 隐藏标签列表（长期保存，过滤搜索结果）
const exHiddenTags = ref([])

// 后端启动错误（未找到 Python 等，显示在左侧状态区）
const backendError = ref('')

// 搜索历史（日常标签）
const searchHistory = ref([])
// 本地收藏（跨站点）
const localFavorites = ref([])

// 有道翻译结果（左侧翻译面板）
// {ok, translation, query, error, raw}
const translateResult = ref(null)

// 全局自动翻译（每站搜索结果常驻）：把搜索/列表结果标题翻译到目标语言
// translatedTitles: {原标题: 译文}；展示时由 RightPanel.trTitle() 回填
const translatedTitles = ref({})
const autoTranslating = ref(false)
// 目标语言（持久化到 settings.auto_translate_to，默认中文）
const autoTranslateTo = ref('zh-CN')
// 持续自动翻译模式（每次搜索后自动翻译全部结果）
const autoTranslateMode = ref(false)
// 目标语言下拉选项（可修改：用户可在设置里增减）
const autoTranslateLangOptions = ref([
  { label: '中文', value: 'zh-CN' },
  { label: '英文', value: 'en' },
  { label: '日文', value: 'ja' },
  { label: '韩文', value: 'ko' },
  { label: '繁中', value: 'zh-TW' },
  { label: '法文', value: 'fr' },
  { label: '德文', value: 'de' },
  { label: '俄文', value: 'ru' },
  { label: '西班牙文', value: 'es' },
])


// GitHub 仓库更新检查结果（左侧设置区）
// {ok, latest_sha, latest_message, latest_date, latest_author, latest_url, local_sha, has_update, is_first_check, release, repo_url, commits_url, error}
const githubUpdateInfo = ref(null)

// X (Twitter) 关注列表 / 关注分类 / 浏览模式
// twFollowMode: ''=普通视图 | 'following'=关注列表 | 'followers'=关注我的人 | 'follows'=我的分类
//               | 'user'=用户详情（TA的关注/粉丝入口） | 'browse'=浏览模式（最近博主更新）
const twFollowMode = ref('')
const twFollowLoading = ref(false)
const twFollowItems = ref([])
const twFollowHasMore = ref(false)
const twFollowCursor = ref('')
const twFollowError = ref('')
// 母子类分类标签：[{name: '母类', children: ['子类', ...]}]
const twFollowTags = ref([])
// 当前查看谁的列表（''=自己；否则为对方 screen_name）
const twFollowOwner = ref('')
// 后端返回的列表标题（如"@xxx 的关注列表"）
const twFollowLabel = ref('')
// 用户详情视图当前查看的用户（卡片数据）
const twViewUser = ref(null)
// X 视图导航栈（返回上一层：用户详情 → TA 的列表 → 更深用户）
const twNavStack = ref([])
// 浏览模式（最近博主更新）：信息流 + 进度 + 缓存时间
const twBrowseFeed = ref([])
const twBrowseLoading = ref(false)
const twBrowseProgress = reactive({ done: 0, total: 0 })
const twBrowseUpdatedAt = ref(null)
const twBrowseError = ref('')
// 浏览模式"加载更多"：下一批关注博主的偏移量（后端 next_offset）
const twBrowseNextOffset = ref(0)
const twBrowseHasMore = ref(false)
// X 本地搜索：在已缓存内容（浏览模式信息流/关注列表/我的分类）中过滤
const twLocalSearch = ref('')
// 本地搜索的推文结果
const twSearchTweets = ref([])
// 搜索结果视图（从搜索态返回时恢复原视图）
const twSearchSnapshot = ref(null)

// Iwara 主页/关注/好友/视频详情（IW站与AI站共用，切换不丢状态）
// iwView: ''=普通搜索 | 'home'=主页最近更新 | 'following'=我的关注 | 'friends'=我的好友 | 'detail'=视频详情
const iwView = ref('')
const iwSite = ref('iwara')          // 'iwara' | 'ai'
const iwHomeItems = ref([])
const iwHomeLoading = ref(false)
const iwHomePage = ref(1)
const iwHomeHasMore = ref(false)
const iwHomeTotal = ref(0)
const iwHomeError = ref('')
// 主页模式：''=最近更新（默认主页）| 'subscribed'=我关注的更新（订阅流）
const iwHomeMode = ref('')
const iwFollowItems = ref([])
const iwFollowLoading = ref(false)
const iwFollowPage = ref(1)
const iwFollowHasMore = ref(false)
const iwFollowTotal = ref(0)
const iwFollowError = ref('')
const iwFriendItems = ref([])
const iwFriendLoading = ref(false)
const iwFriendPage = ref(1)
const iwFriendHasMore = ref(false)
const iwFriendTotal = ref(0)
const iwFriendError = ref('')
const iwDetail = ref(null)           // 视频详情（含 body/tags/作者关注状态）
const iwDetailLoading = ref(false)
const iwComments = ref([])
const iwCommentsPage = ref(1)
const iwCommentsHasMore = ref(false)
// 批量解析下载（关注/好友勾用户，主页勾视频）
const iwBatchRunning = ref(false)
const iwBatchProgress = reactive({ done: 0, total: 0, message: '' })

// ============================
// Hanime1 主页/详情/用户中心（H站，与 Iwara 模式一致）
// ============================
// haView: ''=普通搜索 | 'home'=主页分区 | 'user'=用户中心 | 'detail'=视频详情
const haView = ref('')
const hanimeUser = ref('')
const hanimeLoginLoading = ref(false)
// 主页：分区列表 [{title, items}]（最新上市/最新上傳 + 每个分类）
const haSections = ref([])
const haHomeLoading = ref(false)
const haHomeError = ref('')
// 主页下发的分类/排序选项（搜索过滤复用）
const haGenres = ref([])
const haSorts = ref([])
// 视频详情（含播放直链/tags/收藏状态）
const haDetail = ref(null)
const haDetailLoading = ref(false)
const haComments = ref([])
// 用户中心：当前 tab + 视频列表
const haUserTab = ref('')
const haUserItems = ref([])
const haUserLoading = ref(false)
const haUserPage = ref(1)
const haUserHasMore = ref(false)
const haUserLabel = ref('')
// 批量解析下载（勾选视频）
const haBatchRunning = ref(false)
const haBatchProgress = reactive({ done: 0, total: 0, message: '' })

// ============================
// Oreno3D / EroMMDTube 主页/标签/角色/作者/详情（两站共用一套视图状态）
// ============================
// orView: ''=普通搜索 | 'home'=主页 | 'list'=标签/作者/角色/原作列表 | 'characters'=角色列表
//         | 'authors'=人気作者列表 | 'detail'=视频详情
const orView = ref('')
const orHomeItems = ref([])
const orHomeLoading = ref(false)
const orHomePage = ref(1)
const orHomeHasMore = ref(false)
const orHomeError = ref('')
const orSorts = ref({})              // 可用排序（{value: label}）
// 当前视图数据所属站点（'oreno3d' | 'erommdtube' | ''=尚无数据），切换站点时据此清空旧站数据
const orDataSite = ref('')
// 标签/作者/角色/原作/收藏列表（type: 'tag' | 'author' | 'character' | 'origin' | 'favorites'）
const orList = reactive({ type: '', id: '', name: '', items: [], page: 1, has_more: false })
const orListLoading = ref(false)
const orListError = ref('')
// 热门分类弹窗（标签 + 分类组）
const orTags = ref([])
const orTagGroups = ref([])          // 分类组 [{id, name, count}]
const orTagGroupTitle = ref('')      // 非空 = 正在查看某分类组内的标签
const orTagsLoading = ref(false)
// 角色列表视图（人気角色 + 五十音分组）
const orCharacters = ref({ popular: [], kana_groups: {} })
const orCharsLoading = ref(false)
// 人気作者列表视图（分页）
const orAuthors = ref([])
const orAuthorsPage = ref(1)
const orAuthorsHasMore = ref(false)
const orAuthorsLoading = ref(false)
// 视频详情（含 iwara 源播放直链）
const orDetail = ref(null)
const orDetailLoading = ref(false)
// 批量下载（勾选视频，解析 iwara 源下载）
const orBatchRunning = ref(false)
const orBatchProgress = reactive({ done: 0, total: 0, message: '' })

// ============================
// ASMR 音声站（asmr-100.com）状态
// ============================
// asmrView: ''=普通搜索 | 'popular'=热门 | 'works'=媒体库/筛选 | 'favorites'=收藏 | 'detail'=详情
const asmrView = ref('')
const asmrUser = ref('')
const asmrLoginLoading = ref(false)
const asmrLoggedIn = ref(false)
// 列表（热门/媒体库/收藏/筛选共用）
const asmrItems = ref([])
const asmrListLoading = ref(false)
const asmrHasMore = ref(false)
const asmrError = ref('')
const asmrLabel = ref('')
const asmrTotal = ref(0)
const asmrOrders = ref({})              // 可用排序 {value: label}
const asmrPage = ref(1)
// 当前社团/标签/声优筛选（点击索引项进入）
const asmrFilter = reactive({ kind: '', id: '', name: '' })
// 社团/标签/声优索引弹窗
const asmrIndexItems = ref([])
const asmrIndexLoading = ref(false)
// 详情（含音轨文件列表）
const asmrDetail = ref(null)
const asmrFiles = ref([])
const asmrDetailLoading = ref(false)
// 批量下载
const asmrBatchRunning = ref(false)
const asmrBatchProgress = reactive({ done: 0, total: 0, message: '' })

// ============================
// 通用 webview OAuth 三站（xhamster/pornhub/xvideos）状态
// AP1 阶段：登录用户名显示 + webview 弹窗状态 + OAuth 配置
// ============================
const xhamsterUser = ref('')
const pornhubUser = ref('')
const xvideosUser = ref('')
// webview 登录弹窗（共用 WebviewLoginModal 组件）
const wvLogin = reactive({
  visible: false,
  site: '',                   // xhamster / pornhub / xvideos
  loginUrl: '',
  homeUrl: '',
  partition: 'persist:twitter',
  successPatterns: [],
  captchaPatterns: [],
})


// 当前站点对应的后端 site_key（oreno3d → 'oreno3d'，erommdtube → 'erommdtube'）
const siteKey = computed(() => (settings.site === 'erommdtube' ? 'erommdtube' : 'oreno3d'))

// 忽略另一站的过期事件（双站共用视图状态，快速切换站点时旧站响应直接丢弃）
function orEventStale(event) {
  return !!event.site_key && event.site_key !== siteKey.value
}

// 清空 O3D/E站 全部视图状态（两站之间切换 / 进入异站缓存数据时调用）
function resetOrenoViews() {
  orView.value = ''
  orDataSite.value = ''
  orHomeItems.value = []
  orHomeLoading.value = false
  orHomePage.value = 1
  orHomeHasMore.value = false
  orHomeError.value = ''
  orList.type = ''
  orList.id = ''
  orList.name = ''
  orList.items = []
  orList.page = 1
  orList.has_more = false
  orListLoading.value = false
  orListError.value = ''
  orTags.value = []
  orTagGroups.value = []
  orTagGroupTitle.value = ''
  orTagsLoading.value = false
  orCharacters.value = { popular: [], kana_groups: {} }
  orCharsLoading.value = false
  orAuthors.value = []
  orAuthorsPage.value = 1
  orAuthorsHasMore.value = false
  orAuthorsLoading.value = false
  orDetail.value = null
  orDetailLoading.value = false
}

// 重名文件手动改名弹窗（skip_duplicates + manual_rename 开启时触发）
const renameModal = reactive({
  visible: false,
  filename: '',
  existingSize: null,
  newSize: null,
  newName: '',
  item: null,
  url: '',
  album: '',
})
// 等待处理的改名请求队列（一次弹一个）
const renameQueue = ref([])

// EX 批量下载母文件夹命名弹窗（确定下载时弹出，问是否用搜索词作母文件夹名）
// exBatchParentFolder 非空 → 下载时把文件归入 <下载目录>/<母文件夹>/<画廊名>/ 下
const exBatchFolderVisible = ref(false)
const exBatchFolderName = ref('')          // 输入框值（默认 = 当前搜索词）
const exBatchParentFolder = ref('')        // 确认后保存的母文件夹名（传给下载 options）
const exBatchFolderPendingUrls = ref([])   // 待批量下载的画廊 URL（确认后继续解析）


// RightPanel 组件引用（转发 ExHentai 种子/磁力事件）
const rightPanelRef = ref(null)

// ============================
// 日志
// ============================
function addLog(type, message) {
  const now = new Date()
  const time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`
  logs.value.unshift({ time, type, message })
  if (logs.value.length > 200) {
    logs.value.pop()
  }
}

// ============================
// Python 事件处理
// ============================
// 缩略图缓存完成（后端 thumbnails_cached）：把当前各视图里还在直连原图的
// 条目换成本地 thumb:// 缓存路径，加载失败的图立即恢复显示
function applyCachedThumbnails(cached) {
  if (!cached.length) return
  const map = new Map(cached.map(c => [c.url, c.thumbnail]))
  const swap = item => {
    if (item && typeof item === 'object' && map.has(item.thumbnail)) {
      item.thumbnail = map.get(item.thumbnail)
      return true
    }
    return false
  }
  const arrays = [
    searchResults, iwHomeItems, iwFollowItems, iwFriendItems,
    twFollowItems, twBrowseFeed, twSearchTweets,
    haUserItems, orHomeItems,
  ]
  let updated = 0
  for (const arr of arrays) {
    for (const item of arr.value) {
      if (swap(item)) updated++
    }
  }
  // H站主页分区（[{title, items}] 结构）
  for (const sec of haSections.value) {
    for (const item of (sec.items || [])) {
      if (swap(item)) updated++
    }
  }
  // O3D 标签/作者列表
  for (const item of orList.items || []) {
    if (swap(item)) updated++
  }
  // PA 画师子项目视图（{posts: []} 结构）
  if (paArtistPosts.value && Array.isArray(paArtistPosts.value.posts)) {
    for (const item of paArtistPosts.value.posts) {
      if (swap(item)) updated++
    }
  }
  // 视频详情页封面
  if (iwDetail.value && swap(iwDetail.value)) updated++
  if (haDetail.value && swap(haDetail.value)) updated++
  if (orDetail.value && swap(orDetail.value)) updated++
  if (updated) {
    addLog('系统', `已刷新 ${updated} 张本地缓存的缩略图`)
  }
}

// 在线播放：请求后端解析条目直链（Bunkr/EX 懒解析，其他站点条目已带 media_url 直接返回）
function handleResolveMedia(item) {
  if (!window.api || !item) return
  if (item.media_url || item.media_resolving) return
  item.media_resolving = true
  window.api.sendCommand({
    cmd: 'resolve_media_url',
    item: {
      item_page: item.item_page,
      media_url: item.media_url || '',
      site: item.site || '',
      filename: item.filename || '',
    },
  })
}

function handlePythonEvent(event) {
  switch (event.event) {
    case 'ready':
      backendReady.value = true
      backendError.value = ''
      addLog('系统', '后端已就绪')
      requestSettings()
      requestHistory()
      requestTasks()
      // P3 设置功能：监听主进程触发的快捷键事件
      setupShortcutTriggeredListener()
      // 加载搜索历史与本地收藏
      if (window.api) {
        window.api.sendCommand({ cmd: 'get_search_history' })
        window.api.sendCommand({ cmd: 'get_favorites' })
        // 拉取全部站点登录信息（账号卡片：用户名/Cookie/账号档案）
        window.api.sendCommand({ cmd: 'get_login_info' })
        // 统一提示：正在后台静默检查登录状态（不弹各站单独的提示，避免来回切换观感）
        message.loading('正在后台检查各站登录状态（需外网环境的站点请保持代理通畅）', {
          duration: 4000,
        })
        // 静默检查 ExHentai 登录状态（cookie 已持久化时自动恢复显示）
        window.api.sendCommand({ cmd: 'exhentai_check_login', silent: true })
        // 静默检查 Twitter 登录状态
        window.api.sendCommand({ cmd: 'twitter_check_login', silent: true })
        // 静默检查通用 webview OAuth 三站登录状态（xhamster/pornhub/xvideos，cookie 已持久化时自动恢复）
        window.api.sendCommand({ cmd: 'xhamster_check_login', silent: true })
        window.api.sendCommand({ cmd: 'pornhub_check_login', silent: true })
        window.api.sendCommand({ cmd: 'xvideos_check_login', silent: true })
        // 加载 X 关注分类标签（本地持久化）
        window.api.sendCommand({ cmd: 'twitter_get_follow_tags' })
        // 加载 EX 隐藏标签列表（长期保存）
        window.api.sendCommand({ cmd: 'exhentai_get_hidden_tags' })
      }
      break

    case 'inspect_start':
      inspecting.value = true
      fileList.value = []
      inspectProgress.current = 0
      inspectProgress.total = 0
      addLog('解析', `开始解析: ${event.url}`)
      break

    case 'inspect_progress':
      inspectProgress.current = event.current
      inspectProgress.total = event.total
      break

    case 'inspect_complete':
      inspecting.value = false
      albumInfo.album_name = event.album_name
      albumInfo.album_id = event.album_id
      albumInfo.is_album = event.is_album
      // EX 批量下载进行中时追加到 fileList，否则替换
      if (exBatchDownloading.value || exBatchPending.value > 0) {
        // 批量模式：给每个文件标记所属画廊名（供"用搜索词作母文件夹"时按画廊分文件夹）
        const galleryTitle = event.album_name || ''
        const newItems = (event.items || []).map((item) => ({
          ...item,
          gallery_title: galleryTitle,
          selected: item.status === 'ok',
          size_text: formatSize(item.size),
          file_type: getFileType(item.filename),
        }))
        fileList.value.push(...newItems)
        addLog('解析', `批量追加: ${event.album_name} (+${newItems.length} 个文件，共 ${fileList.value.length} 个)`)
        if (window.api && window.api.applyFileIcons) {
          // 触发图标重算（非图片/视频文件加载系统图标作为缩略图占位）
          applyFileIcons()
        }
        // 待完成计数减一，全部完成时关闭批量模式
        if (exBatchPending.value > 0) {
          exBatchPending.value -= 1
          if (exBatchPending.value === 0) {
            exBatchDownloading.value = false
            addLog('系统', `批量解析全部完成，共收集 ${fileList.value.length} 个文件`)
          }
        }
      } else {
        fileList.value = (event.items || []).map((item) => ({
          ...item,
          selected: item.status === 'ok',
          size_text: formatSize(item.size),
          file_type: getFileType(item.filename),
        }))
        // 非图片/视频文件加载系统图标作为缩略图占位
        applyFileIcons()
        addLog('解析', `完成: ${event.album_name} (${fileList.value.length} 个文件)`)
      }
      break

    case 'inspect_error':
      inspecting.value = false
      addLog('错误', event.message)
      break

    case 'search_start':
      searching.value = true
      break

    case 'search_result':
      searching.value = false
      searchHasMore.value = !!event.has_more
      searchPage.value = event.page
      searchTotalPages.value = event.total_pages || 0
      searchTotalResults.value = event.total_results || 0
      // 翻页模式：每页替换结果（统一页码逻辑）
      searchResults.value = event.items || []
      // EX 我的收藏模式（翻页走收藏命令而非搜索命令）
      exFavMode.value = event.query === '__ex_favorites__'
      const displayQuery = exFavMode.value ? '我的收藏' : event.query
      addLog('搜索', `「${displayQuery}」第 ${event.page}${event.total_pages ? `/${event.total_pages}` : ''} 页，${(event.items || []).length} 个结果`)
      // 持续自动翻译模式：搜索结果到达后自动翻译一次
      maybeAutoTranslateAfterSearch()
      break

    case 'search_error':
      searching.value = false
      addLog('错误', event.message)
      break

    case 'download_start':
      downloading.value = true
      addLog('下载', `开始下载 ${event.total_files} 个文件`)
      break

    case 'file_start':
      downloadProgress[event.filename] = {
        completed: 0,
        status: 'downloading',
        size: event.size,
      }
      break

    case 'file_progress':
      if (!downloadProgress[event.filename]) {
        downloadProgress[event.filename] = { completed: 0, status: 'downloading', size: null }
      }
      downloadProgress[event.filename].completed = event.completed
      downloadProgress[event.filename].speed = event.speed || 0
      downloadProgress[event.filename].status = 'downloading'
      // 同步更新下载管理器中的文件进度
      if (event.task_id) {
        const task = downloadTasks.value.find(t => t.id === event.task_id)
        if (task) {
          const file = task.files.find(f => f.status === 'downloading')
          if (file) {
            file.completed = event.completed
            file.speed = event.speed || 0
          }
        }
      }
      updateFloatData()
      break

    case 'file_complete':
      if (downloadProgress[event.filename]) {
        downloadProgress[event.filename].status = event.success ? 'completed' : 'failed'
        downloadProgress[event.filename].completed = 100
      }
      addLog(
        event.success ? '完成' : '失败',
        `${event.filename} ${event.success ? '下载完成' : '下载失败'}`
      )
      break

    case 'download_complete':
      downloading.value = false
      addLog('下载', `全部完成 (用时 ${event.execution_time}秒)`)
      break

    case 'download_error':
      downloading.value = false
      addLog('错误', event.message)
      break

    case 'history':
      history.value = event.items || []
      break

    case 'settings':
      // 后端返回已保存的设置，覆盖默认值（记忆功能）
      Object.assign(settings, event.settings || {})
      // 应用悬浮窗可见性记忆：true 则创建/显示，false 则不创建（避免启动一闪而过）
      floatVisible.value = settings.float_visible !== false
      if (window.api && window.api.setFloatVisible) {
        window.api.setFloatVisible(floatVisible.value)
      }
      // 全局自动翻译：从设置恢复目标语言 + 持续自动翻译开关
      if (settings.auto_translate_to) autoTranslateTo.value = settings.auto_translate_to
      autoTranslateMode.value = !!settings.auto_translate_mode
      // P3：设置加载完成后，把已保存的快捷键注册到主进程 + 应用不息屏状态
      syncP3SettingsToMain()
      break

    case 'tasks_snapshot':
      downloadTasks.value = event.tasks || []
      updateFloatData()
      break

    case 'media_proxy_ready':
      // 本地媒体代理就绪（在线播放）
      mediaProxyPort.value = event.port || 0
      break

    case 'media_url_resolved':
      // 在线播放直链解析完成：回填到文件列表条目（预览弹窗监听同一对象，自动刷新）
      if (event.item_page) {
        const item = fileList.value.find(f => f.item_page === event.item_page)
        if (item) {
          item.media_url = event.media_url || ''
          item.media_resolve_failed = !event.success
          item.media_resolve_msg = event.message || ''
          item.media_resolving = false
        }
        if (event.success && event.media_url) {
          addLog('系统', `已解析播放直链: ${decodeURIComponent((event.media_url || '').split('/').pop() || '').slice(0, 60)}`)
        } else if (!event.success) {
          message.warning(event.message || '直链解析失败，无法在线播放')
        }
      }
      break

    case 'thumbnails_cached':
      // 后台缩略图缓存完成：把还在直连原图的条目换成本地缓存路径
      // （修复首次查看时直连 twimg/iwara 等原图加载失败且无刷新的问题）
      applyCachedThumbnails(event.items || [])
      break

    case 'cache_cleared':
      if (event.cleared) {
        addLog('系统', `缓存已清除: ${event.cache_dir}`)
        message.success(`缓存已清除（缩略图 + 相册信息）：${event.cache_dir}`)
      } else {
        addLog('系统', `缓存目录不存在，无需清除: ${event.cache_dir}`)
        message.info('缓存目录不存在，无需清除')
      }
      break

    case 'log':
      addLog(event.type, event.message)
      break

    case 'backend_error':
      // 后端启动失败（未找到 Python / 进程异常退出），显示明确原因
      backendReady.value = false
      backendError.value = event.message || '后端启动失败'
      message.error(backendError.value)
      addLog('错误', backendError.value)
      break

    case 'pawchive_login_result':
      pawchiveLoginLoading.value = false
      if (event.logout) {
        // 退出登录
        pawchiveUser.value = ''
        message.info(event.message || '已退出登录')
        addLog('系统', 'Pawchive 已退出登录')
      } else if (event.success) {
        pawchiveUser.value = event.username
        if (!event.silent) {
          message.success(event.message || `登录成功: ${event.username}`)
        }
        addLog('系统', `Pawchive 登录成功: ${event.username}`)
      } else {
        if (!event.network_issue) pawchiveUser.value = ''
        if (!event.silent) {
          if (event.network_issue) {
            message.warning('登录状态检查失败：登录信息未变化，可能是网络问题，请检查网络后点"重新检查"')
          } else {
            message.error(event.message || '登录失败')
          }
        }
        addLog('错误', `Pawchive 登录失败: ${event.message || ''}`)
      }
      break

    case 'exhentai_login_result':
      if (event.logout) {
        exhentaiUser.value = ''
        if (!event.silent) message.info(event.message || '已退出 ExHentai 登录')
        addLog('系统', 'ExHentai 已退出登录')
      } else if (event.success) {
        exhentaiUser.value = event.username || '已登录'
        if (!event.silent) message.success(event.message || 'ExHentai 登录成功')
        addLog('系统', `ExHentai 登录成功: ${event.username || ''}`)
      } else {
        if (!event.network_issue) exhentaiUser.value = ''
        if (!event.silent) {
          if (event.network_issue) {
            message.warning('登录状态检查失败：登录信息未变化，可能是网络/代理问题，请检查后点"重新检查"')
          } else {
            message.error(event.message || 'ExHentai 未登录')
          }
        }
        addLog('系统', `ExHentai 未登录: ${event.message || ''}`)
      }
      break

    case 'twitter_login_result':
      if (event.logout) {
        twitterUser.value = ''
        if (!event.silent) message.info(event.message || '已退出 X 登录')
        addLog('系统', 'X (Twitter) 已退出登录')
      } else if (event.success) {
        twitterUser.value = event.username || '已登录'
        if (!event.silent) message.success(event.message || 'X 登录成功')
        addLog('系统', `X (Twitter) 登录成功: ${event.username || ''}`)
      } else {
        if (!event.network_issue) twitterUser.value = ''
        if (!event.silent) {
          if (event.network_issue) {
            message.warning('登录状态检查失败：登录信息未变化，可能是网络/代理问题，请检查后点"重新检查"')
          } else {
            message.error(event.message || 'X 未登录')
          }
        }
        addLog('系统', `X (Twitter) 未登录: ${event.message || ''}`)
      }
      break

    case 'iwara_login_result':
      iwaraLoginLoading.value = false
      if (event.logout) {
        iwaraUser.value = ''
        if (!event.silent) message.info(event.message || '已退出 Iwara 登录')
        addLog('系统', 'Iwara 已退出登录')
      } else if (event.success) {
        iwaraUser.value = event.username || event.email || '已登录'
        if (!event.silent) message.success(event.message || 'Iwara 登录成功')
        addLog('系统', `Iwara 登录成功: ${iwaraUser.value}`)
      } else {
        if (event.network_issue) {
          // 网络问题：保留当前登录显示（token 未被服务器拒绝，只是连不上）
          if (!event.silent) message.warning(event.message || 'Iwara 连接失败（网络问题），登录状态已保留')
          addLog('系统', `Iwara 连接失败（网络）: ${event.message || ''}`)
        } else {
          iwaraUser.value = ''
          if (!event.silent) message.error(event.message || 'Iwara 未登录')
          addLog('系统', `Iwara 未登录: ${event.message || ''}`)
        }
      }
      break

    case 'iwara_site_changed':
      iwSite.value = event.site || 'iwara'
      message.info(event.message || '站点已切换')
      // 切换 IW/AI 站后重新加载主页最近更新（详情页属于旧站点，一并返回）
      iwHomeItems.value = []
      iwHomePage.value = 1
      iwHomeMode.value = ''
      iwDetail.value = null
      iwComments.value = []
      handleIwHome(1)
      break

    case 'iwara_home':
      iwHomeLoading.value = false
      iwHomeError.value = event.error || ''
      if (event.error) break
      // 强校验：丢弃来自错误站点的数据（防止未切换 AI 站时显示 AI 站内容）
      if (event.site && event.site !== iwSite.value) {
        console.warn('[iwara_home] 丢弃站点不匹配的数据', { expected: iwSite.value, got: event.site })
        addLog('系统', `丢弃 IW/${iwSite.value === 'ai' ? 'AI' : '普通'}站不匹配的旧数据`)
        break
      }
      if ((event.page || 1) <= 1) {
        iwHomeItems.value = event.items || []
      } else {
        iwHomeItems.value.push(...(event.items || []))
      }
      iwHomePage.value = event.page || 1
      iwHomeHasMore.value = !!event.has_more
      iwHomeTotal.value = event.total || 0
      if (event.mode !== undefined) iwHomeMode.value = event.mode || ''
      if (iwView.value !== 'detail') iwView.value = 'home'
      break

    case 'iwara_home_loading':
      iwHomeLoading.value = !!event.loading
      break

    case 'iwara_follow_list':
      iwFollowLoading.value = false
      iwFollowError.value = event.error || ''
      if (event.error) break
      if (event.site && event.site !== iwSite.value) {
        console.warn('[iwara_follow_list] 丢弃站点不匹配数据', { expected: iwSite.value, got: event.site })
        break
      }
      if ((event.page || 1) <= 1) {
        iwFollowItems.value = event.items || []
      } else {
        iwFollowItems.value.push(...(event.items || []))
      }
      iwFollowPage.value = event.page || 1
      iwFollowHasMore.value = !!event.has_more
      iwFollowTotal.value = event.total || 0
      break

    case 'iwara_follow_loading':
      iwFollowLoading.value = !!event.loading
      break

    case 'iwara_friend_list':
      iwFriendLoading.value = false
      iwFriendError.value = event.error || ''
      if (event.error) break
      if (event.site && event.site !== iwSite.value) {
        console.warn('[iwara_friend_list] 丢弃站点不匹配数据', { expected: iwSite.value, got: event.site })
        break
      }
      if ((event.page || 1) <= 1) {
        iwFriendItems.value = event.items || []
      } else {
        iwFriendItems.value.push(...(event.items || []))
      }
      iwFriendPage.value = event.page || 1
      iwFriendHasMore.value = !!event.has_more
      iwFriendTotal.value = event.total || 0
      break

    case 'iwara_friend_loading':
      iwFriendLoading.value = !!event.loading
      break

    case 'iwara_follow_result':
      if (event.success) {
        message.success(event.message || '操作成功')
        // 同步更新关注/好友列表与详情页中的关注状态
        const following = !!event.following
        for (const u of iwFollowItems.value) {
          if (u.user_id === event.user_id) u.following = following
        }
        for (const u of iwFriendItems.value) {
          if (u.user_id === event.user_id) u.following = following
        }
        if (iwDetail.value && iwDetail.value.author_id === event.user_id) {
          iwDetail.value.author_following = following
        }
        addLog('系统', `Iwara ${event.message || ''}`)
      } else {
        message.error(event.message || '操作失败')
      }
      break

    case 'iwara_video_detail':
      iwDetailLoading.value = false
      if (event.error || !event.video) {
        message.error(event.error || '获取视频详情失败')
        break
      }
      // 强校验：丢弃来自错误站点的视频详情
      if (event.site && event.site !== iwSite.value) {
        console.warn('[iwara_video_detail] 丢弃站点不匹配数据', { expected: iwSite.value, got: event.site })
        addLog('系统', `丢弃 IW/${iwSite.value === 'ai' ? 'AI' : '普通'}站不匹配的视频详情`)
        break
      }
      iwDetail.value = event.video
      iwComments.value = event.comments || []
      iwCommentsPage.value = 1
      iwCommentsHasMore.value = (event.comment_count || 0) > (iwComments.value.length)
      iwView.value = 'detail'
      break

    case 'iwara_detail_loading':
      iwDetailLoading.value = !!event.loading
      break

    case 'iwara_comments':
      if (event.error) {
        message.error(event.error)
        break
      }
      iwComments.value.push(...(event.comments || []))
      iwCommentsPage.value = event.page || 1
      iwCommentsHasMore.value = !!event.has_more
      break

    case 'iwara_batch_progress':
      iwBatchRunning.value = true
      iwBatchProgress.done = event.done || 0
      iwBatchProgress.total = event.total || 0
      iwBatchProgress.message = event.message || ''
      break

    case 'iwara_batch_done':
      iwBatchRunning.value = false
      iwBatchProgress.done = event.done || 0
      iwBatchProgress.total = event.total || 0
      iwBatchProgress.message = ''
      if (event.message) {
        message.info(event.message)
        addLog('下载', event.message)
      }
      break

    case 'hanime_login_result':
      hanimeLoginLoading.value = false
      if (event.logout) {
        hanimeUser.value = ''
        if (!event.silent) message.info(event.message || '已退出 Hanime1 登录')
        addLog('系统', 'Hanime1 已退出登录')
      } else if (event.success) {
        hanimeUser.value = event.username || '已登录'
        if (!event.silent) message.success(event.message || 'Hanime1 登录成功')
        addLog('系统', `Hanime1 登录成功: ${hanimeUser.value}`)
      } else {
        if (event.network_issue) {
          // 网络问题：保留当前登录显示
          if (!event.silent) message.warning(event.message || 'Hanime1 连接失败（网络问题），登录状态已保留')
          addLog('系统', `Hanime1 连接失败（网络）: ${event.message || ''}`)
        } else {
          hanimeUser.value = ''
          if (!event.silent) message.error(event.message || 'Hanime1 未登录')
          addLog('系统', `Hanime1 未登录: ${event.message || ''}`)
        }
      }
      break

    case 'hanime_proxy_set':
      // 后端确认代理设置（含自动补 http:// 前缀）
      if ((event.proxy || '') !== settings.hanime_proxy) {
        settings.hanime_proxy = event.proxy || ''
        saveSettings()
      }
      break

    case 'hanime_home':
      haHomeLoading.value = false
      haHomeError.value = event.error || ''
      if (event.error) break
      haSections.value = event.sections || []
      if (event.genres) haGenres.value = event.genres
      if (event.sorts) haSorts.value = event.sorts
      if (haView.value !== 'detail') haView.value = 'home'
      break

    case 'hanime_home_loading':
      haHomeLoading.value = !!event.loading
      break

    case 'hanime_video_detail':
      haDetailLoading.value = false
      if (event.error || !event.video) {
        message.error(event.error || '获取视频详情失败')
        break
      }
      haDetail.value = event.video
      haComments.value = event.comments || []
      haView.value = 'detail'
      break

    case 'hanime_detail_loading':
      haDetailLoading.value = !!event.loading
      break

    case 'hanime_comments':
      if (event.error) {
        message.error(event.error)
        break
      }
      haComments.value = event.items || []
      break

    case 'hanime_comment_result':
      if (event.success) {
        message.success(event.message || '评论发表成功')
        // 刷新当前视频的评论列表
        if (haDetail.value && haDetail.value.video_id === event.video_id) {
          window.api.sendCommand({ cmd: 'hanime_comments', video_id: event.video_id })
        }
      } else {
        message.error(event.message || '评论发表失败')
      }
      break

    case 'hanime_save_result':
      if (event.success) {
        message.success(event.message || (event.saved ? '已加入稍後觀看' : '已取消收藏'))
        if (haDetail.value && haDetail.value.video_id === event.video_id) {
          haDetail.value.saved = !!event.saved
        }
      } else {
        message.error(event.message || '收藏操作失败')
      }
      break

    case 'hanime_user_videos':
      haUserLoading.value = false
      if (event.error) {
        message.error(event.error)
        if ((event.page || 1) <= 1) haUserItems.value = []
        break
      }
      if ((event.page || 1) <= 1) {
        haUserItems.value = event.items || []
      } else {
        haUserItems.value.push(...(event.items || []))
      }
      haUserPage.value = event.page || 1
      haUserHasMore.value = !!event.has_more
      haUserLabel.value = event.label || ''
      if (haView.value !== 'detail') haView.value = 'user'
      break

    case 'hanime_user_loading':
      haUserLoading.value = !!event.loading
      break

    case 'hanime_batch_progress':
      haBatchRunning.value = true
      haBatchProgress.done = event.done || 0
      haBatchProgress.total = event.total || 0
      haBatchProgress.message = event.message || ''
      break

    case 'hanime_batch_done':
      haBatchRunning.value = false
      haBatchProgress.done = event.done || 0
      haBatchProgress.total = event.total || 0
      haBatchProgress.message = ''
      if (event.message) {
        message.info(event.message)
        addLog('下载', event.message)
      }
      break

    case 'oreno_proxy_set': {
      // 后端确认代理设置（含自动补 http:// 前缀；按 site_key 区分 O3D / E站）
      const field = event.site_key === 'erommdtube' ? 'erommd_proxy' : 'oreno_proxy'
      if ((event.proxy || '') !== settings[field]) {
        settings[field] = event.proxy || ''
        saveSettings()
      }
      break
    }

    case 'oreno_home':
      if (orEventStale(event)) break
      orHomeLoading.value = false
      orDataSite.value = event.site_key || siteKey.value
      orHomeError.value = event.error || ''
      if (event.error) break
      if ((event.page || 1) <= 1) {
        orHomeItems.value = event.items || []
      } else {
        orHomeItems.value.push(...(event.items || []))
      }
      orHomePage.value = event.page || 1
      orHomeHasMore.value = !!event.has_more
      if (event.sorts) orSorts.value = event.sorts
      if (orView.value !== 'detail' && orView.value !== 'list') orView.value = 'home'
      break

    case 'oreno_home_loading':
      if (orEventStale(event)) break
      orHomeLoading.value = !!event.loading
      break

    case 'oreno_list':
      if (orEventStale(event)) break
      orListLoading.value = false
      orDataSite.value = event.site_key || siteKey.value
      if (event.error) {
        orListError.value = event.error
        message.error(event.error)
        if ((event.page || 1) <= 1) orList.items = []
        break
      }
      orListError.value = ''
      orList.type = event.type || 'tag'
      orList.id = event.id || ''
      orList.name = event.name || ''
      if ((event.page || 1) <= 1) {
        orList.items = event.items || []
      } else {
        orList.items.push(...(event.items || []))
      }
      orList.page = event.page || 1
      orList.has_more = !!event.has_more
      orView.value = 'list'
      break

    case 'oreno_list_loading':
      if (orEventStale(event)) break
      orListLoading.value = !!event.loading
      break

    case 'oreno_tags':
      if (orEventStale(event)) break
      orTagsLoading.value = false
      orDataSite.value = event.site_key || siteKey.value
      if (event.error) {
        message.error(event.error)
        break
      }
      orTags.value = event.tags || []
      orTagGroups.value = event.groups || []
      orTagGroupTitle.value = event.group_title || ''
      break

    case 'oreno_tags_loading':
      if (orEventStale(event)) break
      orTagsLoading.value = !!event.loading
      break

    case 'oreno_characters':
      if (orEventStale(event)) break
      orCharsLoading.value = false
      orDataSite.value = event.site_key || siteKey.value
      if (event.error) {
        message.error(event.error)
        break
      }
      orCharacters.value = { popular: event.popular || [], kana_groups: event.kana_groups || {} }
      break

    case 'oreno_chars_loading':
      if (orEventStale(event)) break
      orCharsLoading.value = !!event.loading
      break

    case 'oreno_authors':
      if (orEventStale(event)) break
      orAuthorsLoading.value = false
      orDataSite.value = event.site_key || siteKey.value
      if (event.error) {
        message.error(event.error)
        break
      }
      orAuthors.value = event.authors || []
      orAuthorsPage.value = event.page || 1
      orAuthorsHasMore.value = !!event.has_more
      break

    case 'oreno_authors_loading':
      if (orEventStale(event)) break
      orAuthorsLoading.value = !!event.loading
      break

    case 'oreno_fav_result':
      if (orEventStale(event)) break
      if (event.error) {
        message.error(event.error)
        break
      }
      message.success(event.saved ? '已加入收藏' : '已取消收藏')
      // 详情页同步收藏状态
      if (orDetail.value && orDetail.value.video_id === event.video_id) {
        orDetail.value.saved = !!event.saved
      }
      // 收藏列表视图内取消收藏时同步移除卡片
      if (orList.type === 'favorites' && !event.saved) {
        orList.items = orList.items.filter(i => i.video_id !== event.video_id)
      }
      break

    case 'oreno_video_detail':
      if (orEventStale(event)) break
      orDetailLoading.value = false
      if (event.error || !event.video) {
        message.error(event.error || '获取视频详情失败')
        break
      }
      orDetail.value = event.video
      orDataSite.value = event.site_key || siteKey.value
      orView.value = 'detail'
      break

    case 'oreno_detail_loading':
      if (orEventStale(event)) break
      orDetailLoading.value = !!event.loading
      break

    case 'oreno_batch_progress':
      if (orEventStale(event)) break
      orBatchRunning.value = true
      orBatchProgress.done = event.done || 0
      orBatchProgress.total = event.total || 0
      orBatchProgress.message = event.message || ''
      break

    case 'oreno_batch_done':
      if (orEventStale(event)) break
      orBatchRunning.value = false
      orBatchProgress.done = event.done || 0
      orBatchProgress.total = event.total || 0
      orBatchProgress.message = ''
      if (event.message) {
        message.info(event.message)
        addLog('下载', event.message)
      }
      break

    // ============================
    // ASMR 音声站事件
    // ============================
    case 'asmr_login_result':
      asmrLoginLoading.value = false
      if (event.logout) {
        asmrUser.value = ''
        asmrLoggedIn.value = false
        if (!event.silent) message.info(event.message || '已退出 ASMR 登录')
        addLog('系统', 'ASMR 已退出登录')
      } else if (event.success) {
        asmrUser.value = event.username || '已登录'
        asmrLoggedIn.value = true
        if (!event.silent) message.success(event.message || 'ASMR 登录成功')
        addLog('系统', `ASMR 登录成功: ${asmrUser.value}`)
      } else {
        if (event.network_issue) {
          // 网络问题：保留当前登录显示
          if (!event.silent) message.warning(event.message || 'ASMR 连接失败（网络问题），登录状态已保留')
          addLog('系统', `ASMR 连接失败（网络）: ${event.message || ''}`)
        } else {
          asmrUser.value = ''
          asmrLoggedIn.value = false
          if (!event.silent) message.error(event.message || 'ASMR 未登录')
          addLog('系统', `ASMR 未登录: ${event.message || ''}`)
        }
      }
      break

    case 'asmr_proxy_set':
      // 后端确认代理设置（含自动补 http:// 前缀）
      if ((event.proxy || '') !== settings.asmr_proxy) {
        settings.asmr_proxy = event.proxy || ''
        saveSettings()
      }
      break

    case 'asmr_list':
      if ((settings.site || 'bunkr') !== 'asmr') break
      asmrListLoading.value = false
      asmrView.value = event.view || 'popular'
      asmrPage.value = event.page || 1
      asmrHasMore.value = !!event.has_more
      asmrError.value = event.error || ''
      if (event.error) break
      if ((event.page || 1) <= 1) {
        asmrItems.value = event.items || []
      } else {
        asmrItems.value.push(...(event.items || []))
      }
      asmrLabel.value = event.label || ''
      asmrTotal.value = event.total || 0
      if (event.orders) asmrOrders.value = event.orders
      searchResults.value = []
      break

    case 'asmr_list_loading':
      asmrListLoading.value = !!event.loading
      break

    case 'asmr_video_detail':
      asmrDetailLoading.value = false
      if (event.error || !event.video) {
        message.error(event.error || '获取作品详情失败')
        break
      }
      if (asmrView.value !== 'detail') asmrListPrevView.value = asmrView.value
      asmrDetail.value = event.video
      asmrFiles.value = event.files || []
      asmrLoggedIn.value = !!event.logged_in
      asmrView.value = 'detail'
      break

    case 'asmr_detail_loading':
      asmrDetailLoading.value = !!event.loading
      break

    case 'asmr_circles':
    case 'asmr_tags':
    case 'asmr_vas':
      if (event.error) {
        message.error(event.error)
        break
      }
      asmrIndexItems.value = event.items || []
      break

    case 'asmr_circles_loading':
    case 'asmr_tags_loading':
    case 'asmr_vas_loading':
      asmrIndexLoading.value = !!event.loading
      break

    case 'asmr_fav_result':
      if (event.error) {
        message.error(event.error)
        break
      }
      message.success(event.saved ? '已收藏' : '已取消收藏')
      if (asmrDetail.value && String(asmrDetail.value.video_id) === String(event.video_id)) {
        asmrDetail.value.saved = !!event.saved
      }
      // 收藏列表视图中同步移除/恢复
      if (asmrView.value === 'favorites' && !event.saved) {
        asmrItems.value = asmrItems.value.filter(i => String(i.video_id) !== String(event.video_id))
      }
      break

    case 'asmr_batch_progress':
      asmrBatchRunning.value = true
      asmrBatchProgress.done = event.done || 0
      asmrBatchProgress.total = event.total || 0
      asmrBatchProgress.message = event.message || ''
      break

    case 'asmr_batch_done':
      asmrBatchRunning.value = false
      asmrBatchProgress.done = event.done || 0
      asmrBatchProgress.total = event.total || 0
      asmrBatchProgress.message = ''
      if (event.message) {
        message.info(event.message)
        addLog('下载', event.message)
      }
      break

    case 'login_info':
      loginInfo.value = event.sites || {}
      break

    case 'account_saved':
      message.success(event.message || '账号档案已更新')
      addLog('系统', event.message || '')
      break

    case 'account_error':
      message.error(event.message || '账号档案操作失败')
      addLog('错误', event.message || '')
      break

    case 'exhentai_torrents':
      if (rightPanelRef.value) rightPanelRef.value.setTorrents(event.torrents)
      if (event.message) addLog('磁力', event.message)
      break

    case 'exhentai_torrents_error':
      if (rightPanelRef.value) rightPanelRef.value.setTorrentsError()
      message.error(event.message || '获取种子失败')
      addLog('错误', `获取种子失败: ${event.message || ''}`)
      break

    case 'exhentai_magnet':
      if (rightPanelRef.value) rightPanelRef.value.setMagnet(event.magnet)
      addLog('磁力', `已获取磁力链接: ${event.name || event.infohash || ''}`)
      break

    case 'exhentai_magnet_error':
      if (rightPanelRef.value) rightPanelRef.value.setMagnetError()
      message.error(event.message || '磁力解析失败')
      addLog('错误', `磁力解析失败: ${event.message || ''}`)
      break

    case 'ex_gallery_info':
      exDetailLoading.value = false
      exGalleryDetail.value = event
      addLog('解析', `画廊详情: ${event.title || ''}`)
      break

    case 'ex_gallery_info_error':
      exDetailLoading.value = false
      message.error(event.message || '获取画廊信息失败')
      addLog('错误', `获取画廊信息失败: ${event.message || ''}`)
      break

    case 'ex_torrent_saved':
      if (event.success) {
        message.success(event.message || '种子已保存')
        addLog('下载', `种子已保存: ${event.path || ''}`)
      } else {
        message.error(event.message || '种子保存失败')
        addLog('错误', `种子保存失败: ${event.message || ''}`)
      }
      break

    case 'pa_post_info':
      paDetailLoading.value = false
      paPostDetail.value = event
      addLog('解析', `帖子详情: ${event.title || ''}`)
      break

    case 'pa_post_info_error':
      paDetailLoading.value = false
      message.error(event.message || '获取帖子信息失败')
      addLog('错误', `获取帖子信息失败: ${event.message || ''}`)
      break

    case 'pa_artist_posts':
      // 画师子项目列表（按发布日期倒序的全部帖子）
      paArtistPostsLoading.value = false
      paArtistPosts.value = event
      paPostDetail.value = null
      exGalleryDetail.value = null
      twFollowMode.value = ''
      if (event.cached) {
        addLog('Pawchive', `画师子项目（缓存）: ${event.artist || ''} 共 ${(event.posts || []).length} 个帖子`)
      } else {
        addLog('Pawchive', `画师子项目: ${event.artist || ''} 共 ${(event.posts || []).length} 个帖子`)
      }
      break

    case 'pa_artist_posts_error':
      paArtistPostsLoading.value = false
      message.error(event.message || '获取画师帖子列表失败')
      addLog('错误', `获取画师帖子列表失败: ${event.message || ''}`)
      break

    case 'ex_hidden_tags':
      // 隐藏标签列表（增删后后端回推最新列表）
      exHiddenTags.value = event.tags || []
      break

    case 'search_history':
      searchHistory.value = event.items || []
      break

    case 'translate_result':
      // 有道翻译结果（成功/失败都回传，前端面板显示 translation 或 error）
      translateResult.value = event
      break

    case 'translate_batch_result': {
      // 全局自动翻译：批量译文回填到 translatedTitles 映射
      autoTranslating.value = false
      if (event.ok && Array.isArray(event.translations)) {
        const titles = collectCurrentTitles()
        const map = { ...translatedTitles.value }
        // 按收集顺序对位覆盖（后端保证顺序一致）
        for (let i = 0; i < titles.length && i < event.translations.length; i++) {
          const orig = titles[i]
          const tr = event.translations[i]
          if (orig && tr && tr !== orig) map[orig] = tr
        }
        translatedTitles.value = map
      }
      break
    }

    case 'github_update_info':
      // GitHub 仓库更新检查结果
      githubUpdateInfo.value = event
      break

    case 'github_update_marked':
      // 用户已确认更新完成 → 重新检查
      if (window.api) window.api.sendCommand({ cmd: 'check_github_update' })
      break

    case 'local_favorites':
      localFavorites.value = event.items || []
      break

    case 'local_favorites_saved':
      if (event.duplicate) {
        message.info(event.message || '已在收藏中')
      } else {
        message.success(event.message || '已收藏到本地')
      }
      // 刷新收藏列表
      if (window.api) window.api.sendCommand({ cmd: 'get_favorites' })
      break

    case 'local_favorites_error':
      message.error(event.message || '收藏失败')
      break

    // ---------- X (Twitter) 关注列表 / 关注管理 ----------
    case 'twitter_follow_loading':
      twFollowLoading.value = !!event.loading
      break

    case 'twitter_follow_list':
      twFollowLoading.value = false
      if (event.refresh_failed) {
        // 已展示缓存，仅后台刷新失败
        addLog('X', `刷新关注列表失败（继续显示缓存）: ${event.refresh_failed}`)
        break
      }
      if (event.error) {
        twFollowError.value = event.error
        if (!event.append) twFollowItems.value = []
        message.error(event.error)
        addLog('错误', event.error)
        break
      }
      twFollowError.value = ''
      // 后台返回较慢时用户可能已切到用户详情/浏览视图，避免覆盖当前视图
      if (!['user', 'browse'].includes(twFollowMode.value)) {
        twFollowMode.value = event.mode
      }
      if (event.label) twFollowLabel.value = event.label
      if (event.append) {
        twFollowItems.value.push(...(event.items || []))
      } else {
        twFollowItems.value = event.items || []
      }
      twFollowCursor.value = event.next_cursor || ''
      twFollowHasMore.value = !!event.has_more
      if (!event.cached) {
        addLog('X', `获取${event.label || '关注列表'}：${(event.items || []).length} 人`)
      }
      break

    case 'twitter_browse_loading':
      twBrowseLoading.value = !!event.loading
      if (event.loading) {
        twBrowseProgress.done = 0
        twBrowseProgress.total = 0
        twBrowseError.value = ''
      }
      break

    case 'twitter_browse_progress':
      twBrowseProgress.done = event.done || 0
      twBrowseProgress.total = event.total || 0
      break

    case 'twitter_browse_feed':
      // 用户可能已离开浏览视图，迟到的结果不覆盖当前视图
      if (!['browse', ''].includes(twFollowMode.value)) break
      twFollowMode.value = 'browse'
      if (event.error) {
        twBrowseError.value = event.error
        if (!event.items?.length && !event.cached) twBrowseFeed.value = []
        message.error(event.error)
        addLog('错误', event.error)
        break
      }
      twBrowseError.value = ''
      if (event.items) twBrowseFeed.value = event.items
      if (event.updated_at) twBrowseUpdatedAt.value = event.updated_at
      // 加载更多翻页状态
      twBrowseHasMore.value = !!event.has_more && !event.no_more
      twBrowseNextOffset.value = event.next_offset || 0
      if (event.no_more) {
        twBrowseHasMore.value = false
        if (event.append) message.info('已加载全部关注博主的动态')
      }
      if (!event.cached) {
        addLog('X', `浏览模式：${(event.items || []).length} 条最近更新${event.append ? '（已追加）' : ''}`)
      }
      break

    case 'twitter_cache_cleared':
      // 清缓存后同步清空前端对应视图状态
      twBrowseFeed.value = []
      twBrowseUpdatedAt.value = null
      twBrowseHasMore.value = false
      twBrowseNextOffset.value = 0
      twFollowItems.value = []
      twFollowCursor.value = ''
      twFollowHasMore.value = false
      twFollowMode.value = ''
      message.success(event.message || '已清除 Twitter 缓存')
      addLog('系统', event.message || '已清除 Twitter 缓存')
      break

    case 'twitter_follows':
      // 我的分类（已归类的关注，本地数据）
      twFollowLoading.value = false
      if (!['user', 'browse'].includes(twFollowMode.value)) {
        twFollowMode.value = 'follows'
      }
      twFollowError.value = ''
      twFollowItems.value = event.items || []
      twFollowHasMore.value = false
      break

    case 'twitter_follow_tags':
      twFollowTags.value = event.tags || []
      break

    case 'twitter_follow_result': {
      // 关注/取关结果：更新列表中对应卡片的按钮状态
      const idx = twFollowItems.value.findIndex(
        u => String(u.user_id) === String(event.user_id),
      )
      if (idx >= 0) twFollowItems.value[idx].following = !!event.following
      if (event.success) {
        message.success(event.message || '操作成功')
        addLog('X', event.message || '')
      } else {
        message.error(event.message || '操作失败')
        addLog('错误', event.message || '')
      }
      break
    }

    // ---------- 重名文件手动改名（下载去重） ----------
    case 'download_rename_prompt':
      renameQueue.value.push(event)
      if (!renameModal.visible) showNextRenamePrompt()
      break

    // ---------- 通用 webview OAuth 站点（xhamster/pornhub/xvideos）登录结果 ----------
    case 'site_login_result': {
      const siteKey = event.site
      if (event.logout) {
        if (siteKey === 'xhamster') xhamsterUser.value = ''
        else if (siteKey === 'pornhub') pornhubUser.value = ''
        else if (siteKey === 'xvideos') xvideosUser.value = ''
        if (!event.silent) message.info(event.message || `已退出 ${siteKey} 登录`)
        addLog('系统', `${siteKey} 已退出登录`)
      } else if (event.logged_in) {
        const uname = event.username || '已登录'
        if (siteKey === 'xhamster') xhamsterUser.value = uname
        else if (siteKey === 'pornhub') pornhubUser.value = uname
        else if (siteKey === 'xvideos') xvideosUser.value = uname
        if (!event.silent) message.success(event.message || `${siteKey} 登录成功`)
        addLog('系统', `${siteKey} 登录成功: ${uname}`)
      } else {
        if (siteKey === 'xhamster') xhamsterUser.value = ''
        else if (siteKey === 'pornhub') pornhubUser.value = ''
        else if (siteKey === 'xvideos') xvideosUser.value = ''
        if (!event.silent) message.warning(event.message || `${siteKey} 未登录或登录失效`)
        addLog('系统', `${siteKey} 未登录`)
      }
      break
    }
  }
}

// ============================
// 命令发送
// ============================
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

// 站点显示名
// 判断输入是否为 Twitter/X 链接（x.com / twitter.com）
function isTwitterUrl(text) {
  return /^https?:\/\/(www\.)?(x|twitter)\.com\/[^/?#]+(\/status\/\d+)?\/?/i.test((text || '').trim())
}

// 判断输入是否为 Iwara 链接（视频页 / 用户主页）
function isIwaraUrl(text) {
  return /^https?:\/\/(www\.|ecchi\.)?iwara\.tv\/(video|profile|user|image)s?\/[A-Za-z0-9_-]+/i.test((text || '').trim())
}

// 判断输入是否为 Hanime1 视频链接（hanime1.me/watch?v=xxx）
function isHanimeUrl(text) {
  return /^https?:\/\/(www\.)?hanime1\.me\/watch\?v=\w+/i.test((text || '').trim())
}

// 判断输入是否为 Oreno3D / EroMMDTube 视频链接（oreno3d.com/movies/xxx、erommdtube.com/movies/xxx）
function isOrenoUrl(text) {
  return /^https?:\/\/(www\.)?(oreno3d|erommdtube)\.com\/movies\/\d+/i.test((text || '').trim())
}

// 判断输入是否为 ASMR 音声作品链接（asmr-100.com / asmr.one 的 /work/xxx）
function isAsmrUrl(text) {
  return /^https?:\/\/(www\.)?(asmr-100|asmr)\.\w+\/work\/\d+/i.test((text || '').trim())
}

const siteNames = { bunkr: 'Bunkr', coomer: 'Coomer', pawchive: 'Pawchive', exhentai: 'EX', twitter: 'X', iwara: 'Iwara', hanime: 'H站', oreno3d: 'O3D', erommdtube: 'E站', asmr: '音声' }
function siteNameOf(s) {
  return siteNames[s] || (s ? String(s) : '未知')
}

// 切换站点（Bunkr / Coomer），清空当前结果并持久化设置
function updateSite(site) {
  settings.site = site
  // 切换站点后清空旧站点的搜索结果与文件列表，避免混淆
  searchResults.value = []
  fileList.value = []
  cameFromSearch.value = false
  paArtistPosts.value = null
  if (site !== 'iwara') iwView.value = ''
  if (site !== 'hanime') haView.value = ''
  if (site !== 'asmr') {
    asmrView.value = ''
    asmrDetail.value = null
    asmrFiles.value = []
  }
  // O3D / E站 双站共用一套视图状态：切换到其中一站时，若缓存的是另一站数据则整体清空
  if (site === 'oreno3d' || site === 'erommdtube') {
    if (orDataSite.value && orDataSite.value !== (site === 'erommdtube' ? 'erommdtube' : 'oreno3d')) {
      resetOrenoViews()
    }
  } else if (orView.value) {
    orView.value = ''
  }
  saveSettings()
}

function handleSearch() {
  const text = searchQuery.value.trim()
  if (!text) return
  if (isBunkrUrl(text) || isCoomerUrl(text) || isPawchiveUrl(text) || isExhentaiUrl(text) || isTwitterUrl(text) || isIwaraUrl(text) || isHanimeUrl(text) || isOrenoUrl(text) || isAsmrUrl(text)) {
    // 粘贴的是 Bunkr / Coomer / Pawchive / ExHentai / Twitter / Iwara / Hanime1 / Oreno3D / EroMMDTube / ASMR 链接，直接解析（后端按链接自动路由）
    url.value = text
    cameFromSearch.value = false
    handleInspect()
  } else {
    // 是关键词，执行当前站点的搜索
    searchPage.value = 1
    doSearch(text, 1)
  }
}

function doSearch(query, page) {
  if (!window.api) {
    addLog('错误', 'window.api 未定义')
    return
  }
  searching.value = true
  if (page === 1) {
    searchResults.value = []
    searchPage.value = 1
    lastSearchKeyword.value = query
    // 新搜索：清空旧译文，避免上一搜索的标题译文错位
    translatedTitles.value = {}
    // 新搜索：清空 EX 批量母文件夹，避免误套用
    exBatchParentFolder.value = ''
  }
  // 退出 X 关注视图 / Iwara 主页等视图，展示搜索结果
  twFollowMode.value = ''
  twFollowItems.value = []
  iwView.value = ''
  haView.value = ''
  orView.value = ''
  asmrView.value = ''
  exFavMode.value = false
  exGalleryDetail.value = null
  paPostDetail.value = null
  paArtistPosts.value = null
  const options = JSON.parse(JSON.stringify(settings))
  window.api.sendCommand({
    cmd: 'search',
    query,
    page,
    per_page: 20,
    options,
  })
}

// 翻页：上一页 / 下一页 / 跳页（统一页码逻辑，替换结果）
function handleGoPage(page) {
  const target = Math.max(1, Math.floor(Number(page) || 1))
  if (searching.value || target === searchPage.value) return
  // 已知总页数时限制范围
  if (searchTotalPages.value > 0 && target > searchTotalPages.value) {
    message.warning(`最多只有 ${searchTotalPages.value} 页`)
    return
  }
  // EX 我的收藏模式：翻页走收藏命令
  if (exFavMode.value && (settings.site || 'bunkr') === 'exhentai') {
    handleExFavorites(target)
    return
  }
  // H站分类浏览模式：翻页走分类浏览命令（无关键词）
  if ((settings.site || 'bunkr') === 'hanime' && !lastSearchKeyword.value && settings.hanime_genre) {
    handleHanimeGenreBrowse(target)
    return
  }
  doSearch(lastSearchKeyword.value || searchQuery.value.trim(), target)
}

function handleLoadMore() {
  if (!searchHasMore.value || searching.value) return
  handleGoPage(searchPage.value + 1)
}

// ExHentai 搜索选项更新（分类/评分/种子/页数范围，对应原版搜索页按钮）：
// 存入设置 + 若当前已有搜索结果则立即按新条件重新搜索第 1 页
function handleExSearchUpdate(opts) {
  Object.assign(settings, opts)
  saveSettings()
  if ((settings.site || 'bunkr') === 'exhentai'
    && searchResults.value.length > 0
    && lastSearchKeyword.value
    && !searching.value) {
    doSearch(lastSearchKeyword.value, 1)
  }
}

function openSearchResult(item) {
  if (!item || !item.album_url) return
  url.value = item.album_url
  searchQuery.value = item.album_url
  cameFromSearch.value = true
  paPostDetail.value = null
  paArtistPosts.value = null
  // 解析媒体时退出 Iwara 视图（主页/详情），展示文件列表
  iwView.value = ''
  iwDetail.value = null
  iwComments.value = []
  // 解析媒体时退出 Hanime1 / Oreno3D 视图，展示文件列表
  haView.value = ''
  haDetail.value = null
  orView.value = ''
  orDetail.value = null
  // 解析媒体时退出 X 关注/浏览视图，展示文件列表
  twFollowMode.value = ''
  twViewUser.value = null
  twNavStack.value = []
  handleInspect()
}

function handleInspect() {
  console.log('[App] 点击解析, url =', url.value)
  if (!url.value.trim()) return
  if (!window.api) {
    console.error('[App] window.api 未定义！')
    addLog('错误', 'window.api 未定义，preload 可能未加载')
    return
  }
  fileList.value = []
  // 单次解析（非批量）：清空 EX 批量母文件夹，避免误套用到本次下载
  exBatchParentFolder.value = ''
  // reactive 对象是 Proxy，无法被 IPC 克隆，必须先转成纯对象
  const options = JSON.parse(JSON.stringify(settings))
  console.log('[App] 发送 inspect 命令')
  window.api.sendCommand({
    cmd: 'inspect',
    url: url.value.trim(),
    options,
  })
}

async function handleDownload(selectedItems) {
  console.log('[App] 点击下载, 选中', selectedItems.length, '个文件')
  if (!window.api) {
    console.error('[App] window.api 未定义！')
    addLog('错误', 'window.api 未定义，preload 可能未加载')
    return
  }

  // 检测与已有下载任务重复的文件
  const dups = findDuplicateItems(selectedItems)
  if (dups.length > 0) {
    const confirmed = await new Promise((resolve) => {
      dialog.warning({
        title: '检测到重复文件',
        content: `有 ${dups.length} 个文件已在下载任务中，是否仍要添加？（将自动重命名避免覆盖）`,
        positiveText: '仍要添加',
        negativeText: '取消',
        onPositiveClick: () => resolve(true),
        onNegativeClick: () => resolve(false),
        onClose: () => resolve(false),
      })
    })
    if (!confirmed) return
  }

  Object.keys(downloadProgress).forEach((k) => delete downloadProgress[k])
  // 转成纯对象，避免 Proxy 无法被 IPC 克隆
  const plainItems = JSON.parse(JSON.stringify(selectedItems))
  const options = JSON.parse(JSON.stringify(settings))
  // EX 批量下载母文件夹：非空时把文件归入 <母文件夹>/<画廊名>/ 下
  // （在单次解析 handleInspect / 新搜索 doSearch 时清空，此处保留以便同批次多次下载）
  if (exBatchParentFolder.value) {
    options.batch_parent_folder = exBatchParentFolder.value
  }
  window.api.sendCommand({
    cmd: 'download',
    url: url.value.trim(),
    items: plainItems,
    options,
    album_name: albumInfo.album_name || '',
    album_id: albumInfo.album_id || undefined,
  })
}

function findDuplicateItems(items) {
  const existing = new Set()
  for (const t of downloadTasks.value) {
    for (const f of t.files || []) {
      if (f.item_page) existing.add(f.item_page)
    }
  }
  return items.filter(it => it.item_page && existing.has(it.item_page))
}

function handleClearCache() {
  if (!window.api) {
    addLog('错误', 'window.api 未定义，preload 可能未加载')
    return
  }
  window.api.sendCommand({ cmd: 'clear_cache' })
}

function handleBackToSearch() {
  // 清空文件列表，返回搜索结果视图
  fileList.value = []
  cameFromSearch.value = false
  // 同步清理各站点详情/子项目视图（避免回退后被旧详情卡住看不到搜索结果）
  exGalleryDetail.value = null
  exDetailLoading.value = false
  paPostDetail.value = null
  paArtistPosts.value = null
  iwDetail.value = null
  iwComments.value = []
  haDetail.value = null
  orDetail.value = null
  if (lastSearchKeyword.value) {
    searchQuery.value = lastSearchKeyword.value
  }
}

// ============================
// Pawchive 登录 / 收藏 / 搜索模式
// ============================
function handlePawchiveLogin(username, password) {
  if (!window.api) {
    addLog('错误', 'window.api 未定义')
    return
  }
  pawchiveLoginLoading.value = true
  window.api.sendCommand({
    cmd: 'pawchive_login',
    username,
    password,
  })
}

function handlePawchiveLogout() {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'pawchive_logout' })
}

function handlePawchiveFavorites() {
  if (!window.api) return
  // 清空当前列表，以"我的收藏"作为搜索结果展示
  searchQuery.value = ''
  fileList.value = []
  cameFromSearch.value = false
  searchResults.value = []
  searching.value = true
  window.api.sendCommand({ cmd: 'pawchive_favorites' })
}

function updateSearchMode(mode) {
  settings.pawchive_search_mode = mode
  // 切换搜索模式后清空旧结果，避免两种结果混在一起
  searchResults.value = []
  saveSettings()
}

// ============================
// 搜索历史（日常标签快速搜索）
// ============================
// 点击历史标签：
//   开关开启 → 直接切换到对应站点并搜索
//   开关关闭 → 弹窗询问（是=切换并搜索 / 否=填入当前搜索框）
function handleUseHistory(h) {
  const query = (h.query || '').trim()
  if (!query) return
  const targetSite = h.site || 'bunkr'

  const doSwitchSearch = () => {
    if (settings.site !== targetSite) {
      updateSite(targetSite)
    }
    // Pawchive 历史记录带有搜索模式（画师/标签），恢复
    if (targetSite === 'pawchive' && h.search_mode) {
      settings.pawchive_search_mode = h.search_mode
      saveSettings()
    }
    searchQuery.value = query
    if (isBunkrUrl(query) || isCoomerUrl(query) || isPawchiveUrl(query) || isExhentaiUrl(query) || isTwitterUrl(query) || isIwaraUrl(query) || isHanimeUrl(query) || isOrenoUrl(query) || isAsmrUrl(query)) {
      // 历史记录是链接：直接解析
      url.value = query
      cameFromSearch.value = false
      handleInspect()
    } else {
      searchPage.value = 1
      doSearch(query, 1)
    }
  }

  const fillCurrentBox = () => {
    searchQuery.value = query
    message.info(`已填入当前搜索框：${query}`)
  }

  if (settings.search_history_switch_site) {
    doSwitchSearch()
  } else {
    dialog.info({
      title: '快速搜索',
      content: `是否切换到 ${siteNameOf(targetSite)} 并搜索「${query}」？`,
      positiveText: '切换并搜索',
      negativeText: '填入当前搜索框',
      onPositiveClick: doSwitchSearch,
      onNegativeClick: fillCurrentBox,
    })
  }
}

function handleDeleteHistoryItem(h) {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'delete_search_history', query: h.query || '', site: h.site || '' })
}

function handleClearHistory() {
  if (!window.api) return
  dialog.warning({
    title: '清空搜索历史',
    content: '确定要清空全部搜索记录吗？此操作不可恢复。',
    positiveText: '清空',
    negativeText: '取消',
    onPositiveClick: () => {
      window.api.sendCommand({ cmd: 'clear_search_history' })
    },
  })
}

// ============================
// 本地收藏（跨站点快速打开）
// ============================
function handleAddFavorite(item) {
  if (!window.api) return
  // Vue reactive 对象无法被 IPC 克隆，先转纯对象
  window.api.sendCommand({ cmd: 'add_favorite', item: JSON.parse(JSON.stringify(item)) })
}

// 点击本地收藏：切换到对应站点并解析 URL
function handleOpenFavorite(fav) {
  const favUrl = (fav.url || '').trim()
  if (!favUrl) return
  const targetSite = fav.site || 'bunkr'
  if (settings.site !== targetSite) {
    updateSite(targetSite)
  }
  searchQuery.value = favUrl
  url.value = favUrl
  cameFromSearch.value = false
  handleInspect()
}

function handleDeleteFavorite(id) {
  if (!window.api || !id) return
  window.api.sendCommand({ cmd: 'delete_favorite', id })
}

// ============================
// 有道翻译（左侧翻译面板）
// ============================
function handleTranslateFree(payload) {
  if (!window.api) return
  const { text = '', from = 'auto', to = 'zh-CN' } = payload || {}
  translateResult.value = null  // 清空旧结果，触发面板 loading
  // 根据设置里的引擎选择后端命令：默认 google_free（translate_free）
  const engine = settings.value?.translate_engine || 'google_free'
  const cmd = engine === 'youdao' ? 'translate_youdao' : 'translate_free'
  window.api.sendCommand({ cmd, text, from, to })
}

// 兼容旧 emit 名称（LeftPanel 旧版本可能还在发 translate-youdao）
function handleTranslateYoudao(payload) {
  handleTranslateFree(payload)
}

// ============================
// 全局自动翻译（每站搜索结果常驻）
// ============================
// 收集当前视图所有结果项的标题（album_name），用于批量翻译
function collectCurrentTitles() {
  const titles = []
  const push = (items) => {
    if (!Array.isArray(items)) return
    for (const it of items) {
      const name = it && (it.album_name || it.title)
      if (name && !titles.includes(name)) titles.push(name)
    }
  }
  push(searchResults.value)
  push(iwHomeItems.value)
  push(iwFollowItems.value)
  push(iwFriendItems.value)
  push(haUserItems.value)
  push(orHomeItems.value)
  if (Array.isArray(orList.items)) push(orList.items)
  if (Array.isArray(haSections.value)) {
    for (const sec of haSections.value) push(sec && sec.items)
  }
  push(asmrItems.value)
  return titles
}

// 目标语言下拉切换：保存到 settings 持久化
function handleUpdateAutoTranslateTo(v) {
  autoTranslateTo.value = v || 'zh-CN'
  settings.auto_translate_to = autoTranslateTo.value
  saveSettings()
}

// 切换持续自动翻译模式（持久化）
function handleToggleAutoTranslateMode() {
  autoTranslateMode.value = !autoTranslateMode.value
  settings.auto_translate_mode = autoTranslateMode.value
  saveSettings()
  // 开启后立即翻译一次当前结果
  if (autoTranslateMode.value) handleAutoTranslate(autoTranslateTo.value)
}

// 点击 🌐 按钮：把当前搜索/列表结果标题批量翻译到目标语言
function handleAutoTranslate(toLang) {
  if (!window.api) return
  const titles = collectCurrentTitles()
  if (!titles.length) return
  autoTranslating.value = true
  const batchId = `auto_${Date.now()}`
  window.api.sendCommand({
    cmd: 'translate_batch',
    texts: titles,
    from: 'auto',
    to: toLang || autoTranslateTo.value || 'zh-CN',
    batch_id: batchId,
  })
}

// 搜索完成后若开启持续自动翻译，自动触发一次
function maybeAutoTranslateAfterSearch() {
  if (autoTranslateMode.value && searchResults.value.length) {
    handleAutoTranslate(autoTranslateTo.value)
  }
}


// ============================
// P3 设置功能：快捷键 / 不息屏 / 拟态模式
// ============================
// 快捷键变更：保存 settings + 通知主进程注册/注销
function handleShortcutChange(action, accelerator) {
  if (!settings.value) return
  const key = `shortcut_${action}`
  // 通过 updateSettings 触发持久化（与 LeftPanel update() 同路径）
  updateSettings({ [key]: accelerator || '' })
  // 通知主进程注册
  if (window.api && window.api.registerShortcut) {
    window.api.registerShortcut(action, accelerator || '').catch(() => {})
  }
}

// 不息屏开关变更
async function handlePreventSleepChange(enabled) {
  if (!window.api) return
  if (enabled) {
    if (window.api.preventSleepStart) {
      const r = await window.api.preventSleepStart()
      if (!r || !r.ok) {
        window.api.sendCommand({ cmd: 'set_setting', key: 'prevent_display_sleep', value: false })
        message?.error?.('不息屏开启失败') || console.warn('preventSleepStart failed')
      }
    }
  } else {
    if (window.api.preventSleepStop) {
      await window.api.preventSleepStop()
    }
  }
}

// 启动时同步设置到主进程（注册全部快捷键 + 不息屏状态）
function syncP3SettingsToMain() {
  if (!window.api || !settings.value) return
  const s = settings.value
  const actions = [
    'toggle_prevent_sleep',
    'quick_minimize',
    'toggle_mimic',
    'toggle_float',
  ]
  for (const a of actions) {
    const acc = s[`shortcut_${a}`] || ''
    if (acc && window.api.registerShortcut) {
      window.api.registerShortcut(a, acc).catch(() => {})
    }
  }
  if (s.prevent_display_sleep && window.api.preventSleepStart) {
    window.api.preventSleepStart().catch(() => {})
  }
}

// 监听主进程触发的快捷键事件（部分动作需要前端处理）
function setupShortcutTriggeredListener() {
  if (!window.api || !window.api.onShortcutTriggered) return
  window.api.onShortcutTriggered((data) => {
    const action = data?.action
    if (action === 'toggle_prevent_sleep') {
      // 切换不息屏开关
      const next = !settings.value.prevent_display_sleep
      updateSettings({ prevent_display_sleep: next })
      handlePreventSleepChange(next)
    } else if (action === 'toggle_float') {
      // 切换悬浮窗（复用现有 float_visible 设置）
      const next = !settings.value.float_visible
      updateSettings({ float_visible: next })
      if (next) {
        window.api.sendCommand({ cmd: 'get_tasks' })  // 触发悬浮窗刷新
      }
    }
  })
}

// ============================
// GitHub 仓库更新检查（设置区）
// ============================
function handleCheckGithubUpdate() {
  if (!window.api) return
  githubUpdateInfo.value = null  // 清空旧结果，触发 loading
  window.api.sendCommand({ cmd: 'check_github_update' })
}

// ============================
// ExHentai 浏览器视图（webview）相关
// ============================
// 获取画廊种子列表（弹窗展示）
function handleExGetTorrents(galleryUrl) {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'exhentai_get_torrents', url: galleryUrl })
}

// 解析 .torrent 文件生成磁力链接
function handleExGetMagnet(torrentUrl) {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'exhentai_get_magnet', torrent_url: torrentUrl })
}

// EX 我的收藏（favorites.php，复用搜索结果视图与分页栏）
function handleExFavorites(page = 1) {
  if (!window.api) return
  searching.value = true
  if (page === 1) {
    searchResults.value = []
    searchPage.value = 1
  }
  exFavMode.value = true
  exGalleryDetail.value = null
  window.api.sendCommand({ cmd: 'exhentai_favorites', page })
}

// EX 画廊详情（点击搜索结果 → 完整信息 + 分组标签 + 种子入口）
// 同时自动解析全部图片并展示文件列表（点开链接自动解析展示）
// 注意参数名用 galleryUrl 而非 url，避免遮蔽（shadow）外层 url ref 导致 url.value = url 自赋值
function handleExOpenGallery(galleryUrl) {
  if (!window.api || !galleryUrl) return
  // 同步 URL 栏 + 标记来自搜索（"后退"按钮可用，回到搜索结果）
  url.value = galleryUrl
  searchQuery.value = galleryUrl
  cameFromSearch.value = true
  // 退出其他站点视图，进入 EX 详情+文件列表视图
  paPostDetail.value = null
  paArtistPosts.value = null
  iwView.value = ''
  iwDetail.value = null
  iwComments.value = []
  haView.value = ''
  haDetail.value = null
  orView.value = ''
  orDetail.value = null
  twFollowMode.value = ''
  twViewUser.value = null
  twNavStack.value = []
  // 1) 画廊详情（标题/标签/上传者/评分/封面 + 第1页缩略图）—— 立即返回
  exDetailLoading.value = true
  window.api.sendCommand({ cmd: 'exhentai_gallery_info', url: galleryUrl })
  // 2) 自动解析全部图片直链，进入文件列表视图（带批量下载）
  fileList.value = []
  const options = JSON.parse(JSON.stringify(settings))
  window.api.sendCommand({ cmd: 'inspect', url: galleryUrl, options })
}

// EX 批量下载：把多个画廊的全部图片解析后追加到 fileList，统一勾选下载
async function handleExBatchDownload(urls) {
  if (!window.api || !Array.isArray(urls) || !urls.length) return
  // 弹出母文件夹命名弹窗：默认填入当前搜索词，用户可修改/留空
  exBatchFolderPendingUrls.value = urls.filter(u => u)
  exBatchFolderName.value = lastSearchKeyword.value || ''
  exBatchFolderVisible.value = true
}

// EX 批量下载母文件夹弹窗确认后执行：开始顺序解析画廊（加入文件列表）
async function confirmExBatchFolder(useFolder) {
  exBatchFolderVisible.value = false
  // 记录母文件夹名（非空 → 下载时按 <母文件夹>/<画廊名>/ 归档）
  exBatchParentFolder.value = useFolder ? (exBatchFolderName.value || '').trim() : ''
  const urls = exBatchFolderPendingUrls.value
  exBatchFolderPendingUrls.value = []
  if (!urls.length) return
  // 进入文件列表视图（如果还没进入）
  cameFromSearch.value = true
  // 清空 fileList 并发解析多个画廊
  fileList.value = []
  exGalleryDetail.value = null
  exBatchDownloading.value = true
  exBatchPending.value = urls.length
  const tip = exBatchParentFolder.value
    ? `母文件夹「${exBatchParentFolder.value}」，`
    : ''
  message.info(`开始批量解析 ${exBatchPending.value} 个画廊，${tip}请稍候（图片将逐个加入文件列表）`)
  const options = JSON.parse(JSON.stringify(settings))
  // 顺序解析（并发会触发 EX 限流 509）；解析结果会通过 inspect_complete 累加进 fileList
  for (const u of urls) {
    if (!u) continue
    url.value = u
    window.api.sendCommand({ cmd: 'inspect', url: u, options })
    // 间隔 1.5s 防 509
    await new Promise(r => setTimeout(r, 1500))
  }
  // 注：exBatchPending 异步递减；全部完成后 inspect_complete handler 内会关闭 exBatchDownloading
  addLog('系统', `批量解析请求已派发（${exBatchPending.value} 个画廊待返回）`)
}

function handleExCloseDetail() {
  exGalleryDetail.value = null
}

// 下载 .torrent 种子文件到 downloads/torrents/
function handleExSaveTorrent(torrent) {
  if (!window.api || !torrent) return
  window.api.sendCommand({
    cmd: 'exhentai_save_torrent',
    torrent_url: torrent.url || torrent,
    name: torrent.name || '',
  })
}

// Pawchive 帖子详情（点击标签搜索结果卡片 → 完整信息 + 附件预览）
function handlePaOpenPost(url) {
  if (!window.api || !url) return
  paDetailLoading.value = true
  window.api.sendCommand({ cmd: 'pawchive_post_info', url })
}

function handlePaCloseDetail() {
  paPostDetail.value = null
}

// Pawchive 画师子项目列表（点开画师 → 按发布日期浏览全部帖子）
function handlePaOpenArtist(artistUrl) {
  if (!window.api || !artistUrl) return
  paArtistPostsLoading.value = true
  paArtistPosts.value = null
  paPostDetail.value = null
  window.api.sendCommand({ cmd: 'pawchive_artist_posts', url: artistUrl })
}

function handlePaCloseArtist() {
  paArtistPosts.value = null
}

// EX 隐藏标签：添加 / 删除（后端长期保存并回推最新列表）
function handleExAddHiddenTag(tag) {
  if (!window.api || !tag) return
  window.api.sendCommand({ cmd: 'exhentai_add_hidden_tag', tag })
}

function handleExDeleteHiddenTag(tag) {
  if (!window.api || !tag) return
  window.api.sendCommand({ cmd: 'exhentai_delete_hidden_tag', tag })
}

// 解析当前 webview 中的画廊（复用 inspect 流程）
function handleExParseGallery(galleryUrl) {
  if (!galleryUrl) return
  url.value = galleryUrl
  searchQuery.value = galleryUrl
  cameFromSearch.value = false
  handleInspect()
}

// 同步 webview cookie 到下载后端（保持登录状态）
function handleExSyncCookies(cookieStr) {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'exhentai_set_cookies', cookies: cookieStr || '' })
}

// ============================
// Twitter/X 登录与代理
// ============================
// 保存用户粘贴的 cookie（auth_token + ct0）并验证登录
function handleTwitterSetCookies(cookieStr) {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'twitter_set_cookies', cookies: cookieStr || '' })
}

// 退出 X 登录（清除已保存 cookie）
function handleTwitterLogout() {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'twitter_clear_cookies' })
}

// ============================
// 登录引导 / 一键抓取 Cookie / 账号档案
// ============================
// 各站点登录页地址（"打开登录页"按钮）
const LOGIN_PAGE_URLS = {
  twitter: 'https://x.com/login',
  exhentai: 'https://exhentai.org',
  pawchive: 'https://pawchive.pw/account/login',
  iwara: 'https://www.iwara.tv/login',
  hanime: 'https://hanime1.me/login',
}

function handleOpenLoginPage(site) {
  const url = LOGIN_PAGE_URLS[site]
  if (url && window.api) {
    window.api.openExternal(url)
    message.info('已打开登录页，登录后回到本工具点"一键抓取浏览器 Cookie"')
  }
}

// 一键抓取：调用 fetch_cookies.py 从本机浏览器解密 Cookie 并自动登录
async function handleFetchCookies(site) {
  if (!window.api || !window.api.fetchCookies) {
    message.error('当前环境不支持一键抓取，请双击根目录"抓取Cookie.bat"获取后粘贴')
    return
  }
  message.info('正在从本机浏览器抓取 Cookie（首次可能需要十几秒）...')
  try {
    const result = await window.api.fetchCookies(site)
    if (!result || !result.ok) {
      message.error(`抓取失败：${(result && result.error) || '未知错误'}`)
      addLog('错误', `Cookie 抓取失败（${site}）: ${(result && result.error) || ''}`)
      return
    }
    message.success(`已从 ${result.source || '浏览器'} 抓取到 Cookie，正在验证登录...`)
    addLog('系统', `Cookie 抓取成功（${site}，来源 ${result.source || '未知'}）`)
    if (site === 'twitter') {
      window.api.sendCommand({ cmd: 'twitter_set_cookies', cookies: result.cookie_str })
    } else if (site === 'exhentai') {
      window.api.sendCommand({ cmd: 'exhentai_set_cookies', cookies: result.cookie_str })
    } else if (site === 'pawchive') {
      window.api.sendCommand({ cmd: 'pawchive_set_cookies', cookies: result.cookie_str })
    }
  } catch (err) {
    message.error(`抓取出错: ${err.message || err}`)
  }
}

// 重新检查当前站点登录状态（失效/网络问题排查）
function handleRefreshLogin(site) {
  if (!window.api) return
  if (site === 'twitter') window.api.sendCommand({ cmd: 'twitter_check_login', notify: true })
  else if (site === 'exhentai') window.api.sendCommand({ cmd: 'exhentai_check_login', notify: true })
  else if (site === 'pawchive') window.api.sendCommand({ cmd: 'pawchive_check_login', notify: true })
  else if (site === 'iwara') window.api.sendCommand({ cmd: 'iwara_check_login' })
  else if (site === 'hanime') window.api.sendCommand({ cmd: 'hanime_check_login' })
  else if (site === 'asmr') window.api.sendCommand({ cmd: 'asmr_check_login', notify: true })
  else if (['xhamster', 'pornhub', 'xvideos'].includes(site)) window.api.sendCommand({ cmd: `${site}_check_login`, notify: true })
}

// 退出 ExHentai 登录（清除已保存 cookie）
function handleExLogout() {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'exhentai_clear_cookies' })
}

// 账号档案：保存当前登录 / 切换 / 删除
function handleSaveAccount(site) {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'save_account', site })
}

function handleSwitchAccount(site, label) {
  if (!window.api) return
  message.info(`正在切换账号: ${label}`)
  window.api.sendCommand({ cmd: 'switch_account', site, label })
}

function handleDeleteAccount(site, label) {
  if (!window.api) return
  dialog.warning({
    title: '删除账号档案',
    content: `确定删除账号档案「${label}」吗？（不影响当前登录状态）`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: () => {
      window.api.sendCommand({ cmd: 'delete_account', site, label })
    },
  })
}

// X 代理修改：保存设置 + 通知下载后端
function handleTwitterSetProxy(proxy) {
  updateSettings({ twitter_proxy: proxy })
  if (window.api) {
    window.api.sendCommand({ cmd: 'twitter_set_proxy', proxy: proxy || '' })
  }
}

// ============================
// Iwara 登录 / 代理
// ============================
function handleIwaraLogin(email, password) {
  if (!window.api || !email.trim() || !password) return
  iwaraLoginLoading.value = true
  window.api.sendCommand({ cmd: 'iwara_login', email: email.trim(), password })
}

function handleIwaraLogout() {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'iwara_logout' })
}

// Iwara 代理修改：保存设置 + 通知后端（留空 = 直连）
function handleIwaraSetProxy(proxy) {
  updateSettings({ iwara_proxy: proxy })
  if (window.api) {
    window.api.sendCommand({ cmd: 'iwara_set_proxy', proxy: proxy || '' })
  }
}

// ============================
// Iwara 主页 / 关注 / 好友 / 视频详情
// ============================
// 主页：最近更新的视频（进入 Iwara 站点时自动加载）
// mode: ''=最近更新（默认）| 'subscribed'=我关注的更新（订阅流）
function handleIwHome(page = 1, mode = '') {
  if (!window.api) return
  iwView.value = 'home'
  if (page <= 1 || mode !== iwHomeMode.value) {
    // 换模式或刷新第一页时清空旧内容
    iwHomeItems.value = []
    iwHomeMode.value = mode
  }
  if (page <= 1) searchResults.value = []
  window.api.sendCommand({ cmd: 'iwara_home', page, mode })
}

// 主页"加载更多"（下一页追加，沿用当前模式）
function handleIwHomeMore() {
  handleIwHome(iwHomePage.value + 1, iwHomeMode.value)
}

// 我关注的更新（订阅流：只看已关注作者的最新投稿）
function handleIwSubscribed() {
  handleIwHome(1, 'subscribed')
}

// 我的关注列表
function handleIwFollowing(page = 1) {
  if (!window.api) return
  iwView.value = 'following'
  searchResults.value = []
  if (page <= 1) iwFollowItems.value = []
  window.api.sendCommand({ cmd: 'iwara_following', page })
}

// 关注列表"加载更多"
function handleIwFollowingMore() {
  handleIwFollowing(iwFollowPage.value + 1)
}

// 我的好友列表
function handleIwFriends(page = 1) {
  if (!window.api) return
  iwView.value = 'friends'
  searchResults.value = []
  if (page <= 1) iwFriendItems.value = []
  window.api.sendCommand({ cmd: 'iwara_friends', page })
}

// 好友列表"加载更多"
function handleIwFriendsMore() {
  handleIwFriends(iwFriendPage.value + 1)
}

// IW站 / AI站 切换（登录信息共用）
function handleIwSetSite(site) {
  if (!window.api || site === iwSite.value) return
  window.api.sendCommand({ cmd: 'iwara_set_site', site })
}

// 关注 / 取消关注
function handleIwFollow(userId, follow) {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'iwara_follow', user_id: userId, follow })
}

// 打开视频详情
function handleIwOpenDetail(videoId) {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'iwara_video_detail', video_id: videoId })
}

// 关闭视频详情（返回上一层）
function handleIwDetailBack() {
  iwView.value = iwHomeItems.value.length ? 'home' : ''
  iwDetail.value = null
  iwComments.value = []
}

// 加载更多评论
function handleIwCommentsMore() {
  if (!window.api || !iwDetail.value) return
  window.api.sendCommand({
    cmd: 'iwara_video_comments',
    video_id: iwDetail.value.video_id,
    page: iwCommentsPage.value + 1,
  })
}

// 查看用户主页（@用户名搜索，与搜索逻辑一致）
function handleIwOpenUser(username) {
  if (!username) return
  iwView.value = ''
  searchQuery.value = `@${username}`
  handleSearch()
}

// 用 tag 搜索
function handleIwSearchTag(tag) {
  if (!tag) return
  iwView.value = ''
  searchQuery.value = tag
  handleSearch()
}

// 批量解析下载：勾选的用户/视频 → 后端逐个解析并提交下载任务
function handleIwBatchDownload(payload) {
  if (!window.api) return
  const usernames = (payload && payload.usernames) || []
  const videoIds = (payload && payload.video_ids) || []
  if (!usernames.length && !videoIds.length) return
  iwBatchRunning.value = true
  iwBatchProgress.done = 0
  iwBatchProgress.total = usernames.length + (videoIds.length ? 1 : 0)
  iwBatchProgress.message = '准备中...'
  window.api.sendCommand({
    cmd: 'iwara_batch_download',
    usernames,
    video_ids: videoIds,
    options: JSON.parse(JSON.stringify(settings)),
  })
  addLog('下载', `批量解析下载：${usernames.length} 个用户、${videoIds.length} 个视频`)
}

// ============================
// Hanime1 登录 / 代理 / 主页 / 详情 / 用户中心
// ============================
function handleHanimeLogin(email, password) {
  if (!window.api || !email.trim() || !password) return
  hanimeLoginLoading.value = true
  window.api.sendCommand({ cmd: 'hanime_login', email: email.trim(), password })
}

function handleHanimeLogout() {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'hanime_logout' })
}

// Hanime1 代理修改：保存设置 + 通知后端（国内默认走代理）
function handleHanimeSetProxy(proxy) {
  updateSettings({ hanime_proxy: proxy })
  if (window.api) {
    window.api.sendCommand({ cmd: 'hanime_set_proxy', proxy: proxy || '' })
  }
}

// H站主页：各分区视频（进入站点时自动加载）
function handleHaHome() {
  if (!window.api) return
  haView.value = 'home'
  searchResults.value = []
  window.api.sendCommand({ cmd: 'hanime_home' })
}

// 打开视频详情
function handleHanimeOpenDetail(videoId) {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'hanime_video_detail', video_id: videoId })
}

// 关闭视频详情（返回上一层：有主页内容回主页，否则回搜索态）
function handleHaDetailBack() {
  haView.value = haSections.value.length ? 'home' : ''
  haDetail.value = null
  haComments.value = []
}

// 发表评论（需登录）
function handleHanimeAddComment(payload) {
  if (!window.api) return
  window.api.sendCommand({
    cmd: 'hanime_add_comment',
    video_id: payload.video_id,
    text: payload.text,
  })
}

// 收藏 / 取消收藏（稍後觀看）
function handleHanimeSaveVideo(videoId, saved) {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'hanime_save_video', video_id: videoId, saved: !!saved })
}

// 用户中心：觀看紀錄/稍後觀看/讚好的影片/上傳的影片/審核中的影片
function handleHanimeUserVideos(tab, page = 1) {
  if (!window.api) return
  haView.value = 'user'
  haUserTab.value = tab
  searchResults.value = []
  if (page <= 1) haUserItems.value = []
  window.api.sendCommand({ cmd: 'hanime_user_videos', tab, page })
}

// H站搜索选项更新（分类/排序）：存入设置并按新条件重新搜索
function handleHanimeSearchUpdate(opts) {
  Object.assign(settings, opts)
  saveSettings()
  if ((settings.site || 'bunkr') !== 'hanime') return
  if (searchResults.value.length > 0 && lastSearchKeyword.value && !searching.value) {
    // 有关键词：按新分类/排序重新搜索
    doSearch(lastSearchKeyword.value, 1)
  } else if (settings.hanime_genre) {
    // 无关键词：直接按分类浏览
    handleHanimeGenreBrowse(1)
  } else {
    // 无关键词且无分类：回主页分区
    handleHaHome()
  }
}

// H站分类浏览（无关键词，按分类+排序翻页）
function handleHanimeGenreBrowse(page = 1) {
  if (!window.api) return
  haView.value = ''
  searching.value = true
  if (page <= 1) {
    searchResults.value = []
    searchPage.value = 1
    lastSearchKeyword.value = ''
  }
  window.api.sendCommand({
    cmd: 'hanime_search',
    query: '',
    page,
    genre: settings.hanime_genre || '',
    sort: settings.hanime_sort || '',
  })
}

// 点击 tag 搜索（填入搜索框并搜索）
function handleHanimeSearchTag(tag) {
  if (!tag) return
  haView.value = ''
  searchQuery.value = tag
  handleSearch()
}

// 批量解析下载：勾选的视频 → 后端逐个解析最高画质并提交下载任务
function handleHanimeBatchDownload(videoIds) {
  if (!window.api || !videoIds || !videoIds.length) return
  haBatchRunning.value = true
  haBatchProgress.done = 0
  haBatchProgress.total = videoIds.length
  haBatchProgress.message = '准备中...'
  window.api.sendCommand({
    cmd: 'hanime_batch_download',
    video_ids: videoIds,
    options: JSON.parse(JSON.stringify(settings)),
  })
  addLog('下载', `H站批量解析下载：${videoIds.length} 个视频`)
}

// ============================
// Oreno3D / EroMMDTube 代理 / 主页 / 标签 / 角色 / 作者 / 详情
// ============================
// O3D / E站 代理修改：保存设置 + 通知后端（留空 = 直连；site_key 区分两站）
function handleOrenoSetProxy(proxy, siteKeyArg) {
  const key = siteKeyArg === 'erommdtube' ? 'erommdtube' : 'oreno3d'
  updateSettings(key === 'erommdtube' ? { erommd_proxy: proxy } : { oreno_proxy: proxy })
  if (window.api) {
    window.api.sendCommand({ cmd: 'oreno_set_proxy', proxy: proxy || '', site_key: key })
  }
}

// O3D / E站 主页/列表（进入站点时自动加载，sort 使用设置持久化）
function handleOrHome(page = 1, sort) {
  if (!window.api) return
  orView.value = 'home'
  if (page <= 1) {
    orHomeItems.value = []
    searchResults.value = []
  }
  window.api.sendCommand({ cmd: 'oreno_home', page, sort: sort !== undefined ? sort : settings.oreno_sort || '', site_key: siteKey.value })
}

// 主页"加载更多"
function handleOrHomeMore() {
  handleOrHome(orHomePage.value + 1)
}

// 排序切换：保存设置并刷新当前视图（主页/标签/角色/作者列表回第 1 页，搜索态重新搜索）
function handleOrenoSortUpdate(sort) {
  updateSettings({ oreno_sort: sort })
  if (!['oreno3d', 'erommdtube'].includes(settings.site || 'bunkr')) return
  if (orView.value === 'list') {
    if (orList.type === 'tag') handleOrenoTag(orList.id, 1, sort)
    else if (orList.type === 'author') handleOrenoAuthor(orList.id, 1, sort)
    else if (orList.type === 'character') handleOrenoCharacter(orList.id, 1, sort)
    else if (orList.type === 'origin') handleOrenoOrigin(orList.id, 1, sort)
  } else if (orView.value === 'home' || !searchResults.value.length) {
    handleOrHome(1, sort)
  } else if (searchResults.value.length && lastSearchKeyword.value && !searching.value) {
    doSearch(lastSearchKeyword.value, 1)
  }
}

// 打开视频详情（含 iwara 源播放直链；卡片自带 site_key 时按卡片站点请求）
function handleOrenoOpenDetail(movieId, siteKeyArg) {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'oreno_detail', movie_id: movieId, site_key: siteKeyArg || siteKey.value })
}

// 关闭视频详情（返回上一层：列表态回列表，否则回主页）
function handleOrDetailBack() {
  orView.value = orList.items.length ? 'list' : (orHomeItems.value.length ? 'home' : '')
  orDetail.value = null
}

// 标签页视频列表
function handleOrenoTag(tagId, page = 1, sort) {
  if (!window.api) return
  orView.value = 'list'
  if (page <= 1) {
    orList.items = []
    searchResults.value = []
  }
  window.api.sendCommand({
    cmd: 'oreno_tag',
    tag_id: tagId,
    page,
    sort: sort !== undefined ? sort : settings.oreno_sort || '',
    site_key: siteKey.value,
  })
}

// 作者页视频列表
function handleOrenoAuthor(authorId, page = 1, sort) {
  if (!window.api) return
  orView.value = 'list'
  if (page <= 1) {
    orList.items = []
    searchResults.value = []
  }
  window.api.sendCommand({
    cmd: 'oreno_author',
    author_id: authorId,
    page,
    sort: sort !== undefined ? sort : settings.oreno_sort || '',
    site_key: siteKey.value,
  })
}

// 角色页视频列表
function handleOrenoCharacter(characterId, page = 1, sort) {
  if (!window.api) return
  orView.value = 'list'
  if (page <= 1) {
    orList.items = []
    searchResults.value = []
  }
  window.api.sendCommand({
    cmd: 'oreno_character',
    character_id: characterId,
    page,
    sort: sort !== undefined ? sort : settings.oreno_sort || '',
    site_key: siteKey.value,
  })
}

// 原作页视频列表
function handleOrenoOrigin(originId, page = 1, sort) {
  if (!window.api) return
  orView.value = 'list'
  if (page <= 1) {
    orList.items = []
    searchResults.value = []
  }
  window.api.sendCommand({
    cmd: 'oreno_origin',
    origin_id: originId,
    page,
    sort: sort !== undefined ? sort : settings.oreno_sort || '',
    site_key: siteKey.value,
  })
}

// 标签/角色/作者列表"加载更多"（按列表类型分发对应命令）
function handleOrListMore() {
  if (orList.type === 'author') handleOrenoAuthor(orList.id, orList.page + 1)
  else if (orList.type === 'character') handleOrenoCharacter(orList.id, orList.page + 1)
  else if (orList.type === 'origin') handleOrenoOrigin(orList.id, orList.page + 1)
  else handleOrenoTag(orList.id, orList.page + 1)
}

// 列表返回主页
function handleOrListBack() {
  orView.value = orHomeItems.value.length ? 'home' : ''
  orList.items = []
}

// 角色/作者浏览视图返回主页
function handleOrBrowseBack() {
  orView.value = orHomeItems.value.length ? 'home' : ''
}

// 角色列表视图（人気角色 + 五十音分组）
function handleOrenoCharacters() {
  if (!window.api) return
  orView.value = 'characters'
  searchResults.value = []
  window.api.sendCommand({ cmd: 'oreno_characters', site_key: siteKey.value })
}

// 人気作者列表视图（分页）
function handleOrenoAuthorsIndex(page = 1) {
  if (!window.api) return
  orView.value = 'authors'
  searchResults.value = []
  window.api.sendCommand({ cmd: 'oreno_authors_index', page, site_key: siteKey.value })
}

// 热门分类弹窗（标签 + 分类组）
function handleOrenoTagsIndex() {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'oreno_tags_index', site_key: siteKey.value })
}

// 分类组内标签列表（弹窗内点击分类组）
function handleOrenoTagGroup(groupId) {
  if (!window.api || !groupId) return
  window.api.sendCommand({ cmd: 'oreno_tag_group', group_id: groupId, site_key: siteKey.value })
}

// 本地收藏列表（oreno_list type='favorites' 视图展示）
function handleOrenoFavorites() {
  if (!window.api) return
  searchResults.value = []
  window.api.sendCommand({ cmd: 'oreno_favorites', site_key: siteKey.value })
}

// 收藏/取消收藏（卡片爱心按钮；卡片字段随命令保存到本地收藏文件）
function handleOrenoToggleFavorite(item) {
  if (!window.api || !item || !item.video_id) return
  const key = item.site_key || siteKey.value
  window.api.sendCommand({
    cmd: 'oreno_toggle_favorite',
    movie_id: item.video_id,
    card: {
      album_name: item.album_name || '',
      album_url: item.album_url || '',
      thumbnail: item.thumbnail || '',
      video_id: item.video_id,
      author: item.author || '',
      views: item.views || '',
      likes: item.likes || '',
      tags: item.tags || [],
      site_key: key,
    },
    site_key: key,
  })
}

// 批量下载：勾选的视频 → 后端解析 iwara 源并下载（最高画质）
function handleOrenoBatchDownload(videoIds) {
  if (!window.api || !videoIds || !videoIds.length) return
  orBatchRunning.value = true
  orBatchProgress.done = 0
  orBatchProgress.total = videoIds.length
  orBatchProgress.message = '准备中...'
  window.api.sendCommand({
    cmd: 'oreno_batch_download',
    video_ids: videoIds,
    options: JSON.parse(JSON.stringify(settings)),
    site_key: siteKey.value,
  })
  addLog('下载', `${siteNameOf(settings.site)}批量下载：${videoIds.length} 个视频`)
}

// ============================
// ASMR 音声站：登录 / 代理 / 热门 / 媒体库 / 收藏 / 索引 / 详情 / 批量下载
// ============================
// 筛选类型中文名（列表标题用）
const ASMR_FILTER_KIND_NAMES = { circles: '社团', tags: '标签', vas: '声优' }
// 进入详情前的视图（返回时恢复）
const asmrListPrevView = ref('')

function handleAsmrLogin(username, password) {
  if (!window.api || !username.trim() || !password) return
  asmrLoginLoading.value = true
  window.api.sendCommand({ cmd: 'asmr_login', username: username.trim(), password })
}

function handleAsmrLogout() {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'asmr_logout' })
}

// ASMR 代理修改：保存设置 + 通知后端（留空 = 直连）
function handleAsmrSetProxy(proxy) {
  updateSettings({ asmr_proxy: proxy })
  if (window.api) {
    window.api.sendCommand({ cmd: 'asmr_set_proxy', proxy: proxy || '' })
  }
}

// ============================
// 通用 webview OAuth 三站（xhamster/pornhub/xvideos）登录流程
// ============================
// 触发 webview OAuth 登录弹窗（用户点"用 Twitter 登录"/XVideos 登录按钮调用）
// xvideos 第二参数带邮箱密码/记住装置；xhamster/pornhub 仅 siteKey
function handleSiteOAuthLogin(siteKey, creds) {
  // 各站登录页 + 成功/captcha 模式（AP1 阶段先用通用配置，具体业务待用户给出要求后补全）
  const configs = {
    xhamster: {
      loginUrl: 'https://jp.xhamster.com/login',
      homeUrl: 'https://jp.xhamster.com/',
      partition: 'persist:twitter',
      successPatterns: [/xhamster\.com\/(users|my|favorites)/i, /xhamster\.com\/?\?auth=1/i],
      captchaPatterns: [/challenge|captcha|areyouhuman|check\.xhamster/i],
    },
    pornhub: {
      loginUrl: 'https://jp.pornhub.com/login',
      homeUrl: 'https://jp.pornhub.com/',
      partition: 'persist:twitter',
      successPatterns: [/pornhub\.com\/(users|my|user)/i, /pornhub\.com\/?\?login=/i],
      captchaPatterns: [/challenge|captcha|areyouhuman|cdn\.pornhub/i],
    },
    xvideos: {
      // xvideos 邮箱密码登录，webview 内自动预填账号 + 处理人机验证
      loginUrl: 'https://www.xvideos.com/profile/login',
      homeUrl: 'https://www.xvideos.com/',
      partition: 'persist:xvideos',
      successPatterns: [/xvideos\.com\/(profiles|account|favorites)/i],
      captchaPatterns: [/challenge|captcha|areyouhuman|cdn\.xvideos/i],
    },
  }
  const cfg = configs[siteKey]
  if (!cfg) return
  wvLogin.site = siteKey
  wvLogin.loginUrl = cfg.loginUrl
  wvLogin.homeUrl = cfg.homeUrl
  wvLogin.partition = cfg.partition
  wvLogin.successPatterns = cfg.successPatterns
  wvLogin.captchaPatterns = cfg.captchaPatterns
  wvLogin.visible = true
  // 同时设置 webview 会话代理（复用站点代理设置）
  const proxyKey = `${siteKey}_proxy`
  const proxyUrl = settings[proxyKey] || ''
  if (window.api && proxyUrl) {
    window.api.siteSetProxy(siteKey, proxyUrl)
  }
}

// WebviewLoginModal 抓取 cookie 成功 → 发后端持久化 + 验证
function handleSiteLoginSuccess({ cookieStr, count }) {
  if (!window.api || !wvLogin.site) return
  window.api.sendCommand({
    cmd: `${wvLogin.site}_set_cookies`,
    cookie_str: cookieStr,
  })
  addLog('系统', `${wvLogin.site} 抓取到 ${count} 个 cookie，已发给后端保存`)
}

// 通用退出登录
function handleSiteLogout(siteKey) {
  if (!window.api) return
  window.api.sendCommand({ cmd: `${siteKey}_logout` })
}

// 通用代理修改
function handleSiteSetProxy(siteKey, proxy) {
  updateSettings({ [`${siteKey}_proxy`]: proxy })
  if (window.api) {
    window.api.sendCommand({ cmd: `${siteKey}_set_proxy`, proxy: proxy || '' })
    window.api.siteSetProxy(siteKey, proxy || '')
  }
}

// 通用检查登录（重启后从缓存恢复时调用）
function handleSiteCheckLogin(siteKey, silent = true) {
  if (!window.api) return
  window.api.sendCommand({ cmd: `${siteKey}_check_login`, silent })
}

// 热门作品（每页 100，进入站点时自动加载）
function handleAsmrPopular(page = 1) {
  if (!window.api) return
  asmrView.value = 'popular'
  asmrFilter.kind = ''
  asmrFilter.id = ''
  asmrFilter.name = ''
  if (page <= 1) {
    asmrItems.value = []
    asmrPage.value = 1
    searchResults.value = []
  }
  window.api.sendCommand({ cmd: 'asmr_popular', page, subtitle: !!settings.asmr_subtitle })
}

// 媒体库（最新入库等排序 + 仅带字幕 + 社团/标签/声优筛选）
function handleAsmrWorks(page = 1, filter) {
  if (!window.api) return
  const f = filter || asmrFilter
  asmrView.value = 'works'
  if (f && f.id) {
    asmrFilter.kind = f.kind
    asmrFilter.id = f.id
    asmrFilter.name = f.name
  } else if (!f) {
    asmrFilter.kind = ''
    asmrFilter.id = ''
    asmrFilter.name = ''
  }
  if (page <= 1) {
    asmrItems.value = []
    asmrPage.value = 1
    searchResults.value = []
  }
  window.api.sendCommand({
    cmd: 'asmr_works',
    page,
    order: settings.asmr_order || 'create_date',
    sort: 'desc',
    subtitle: !!settings.asmr_subtitle,
    circle_id: asmrFilter.kind === 'circles' ? asmrFilter.id : '',
    tag_id: asmrFilter.kind === 'tags' ? asmrFilter.id : '',
    va_id: asmrFilter.kind === 'vas' ? asmrFilter.id : '',
    label: asmrFilter.name ? `${ASMR_FILTER_KIND_NAMES[asmrFilter.kind] || '筛选'}：${asmrFilter.name}` : '媒体库',
  })
}

// ASMR 搜索选项更新（排序/仅带字幕）：存入设置并按新条件刷新列表
function handleAsmrSearchUpdate(opts) {
  Object.assign(settings, opts)
  saveSettings()
  if ((settings.site || 'bunkr') !== 'asmr') return
  // 有筛选：刷新筛选列表；在媒体库/热门：刷新对应列表；搜索态且有结果：重新搜索
  if (asmrView.value === 'works') {
    handleAsmrWorks(1)
  } else if (asmrView.value === 'popular') {
    // 热门作品也支持"仅带字幕"过滤（后端按 has_subtitle 过滤后返回）
    handleAsmrPopular(1)
  } else if (asmrView.value === 'favorites') {
    // 服务器收藏无字幕筛选，不刷新
  } else if (searchResults.value.length > 0 && lastSearchKeyword.value && !searching.value) {
    doSearch(lastSearchKeyword.value, 1)
  }
}

// 我的收藏（需登录）
function handleAsmrFavorites(page = 1) {
  if (!window.api) return
  if (!asmrUser.value && !asmrLoggedIn.value) {
    message.warning('请先在左侧登录 ASMR 账号')
    return
  }
  asmrView.value = 'favorites'
  asmrFilter.kind = ''
  asmrFilter.id = ''
  asmrFilter.name = ''
  if (page <= 1) {
    asmrItems.value = []
    asmrPage.value = 1
    searchResults.value = []
  }
  window.api.sendCommand({ cmd: 'asmr_favorites', page })
}

// 当前列表加载更多（按当前视图分发）
function handleAsmrMore() {
  if (asmrView.value === 'popular') handleAsmrPopular(asmrPage.value + 1)
  else if (asmrView.value === 'favorites') handleAsmrFavorites(asmrPage.value + 1)
  else if (asmrView.value === 'works') handleAsmrWorks(asmrPage.value + 1)
}

// 社团/标签/声优索引弹窗
function handleAsmrIndex(kind) {
  if (!window.api) return
  asmrIndexItems.value = []
  window.api.sendCommand({ cmd: 'asmr_browse_index', kind })
}

// 点击索引项进入筛选列表（tag_id/circle_id/va_id 走 asmr_works）
function handleAsmrIndexPick(kind, id, name) {
  if (!window.api || !id) return
  handleAsmrWorks(1, { kind, id, name })
}

// 打开作品详情
function handleAsmrOpenDetail(item) {
  if (!window.api || !item) return
  const wid = item.video_id || (item.album_url || '').match(/work\/(\d+)/)?.[1]
  if (!wid) return
  asmrDetail.value = null
  asmrFiles.value = []
  window.api.sendCommand({ cmd: 'asmr_work_detail', work_id: String(wid) })
}

// 关闭详情返回上一层（有列表回列表，否则回搜索态）
function handleAsmrDetailBack() {
  asmrView.value = asmrItems.value.length ? (asmrListPrevView.value || 'popular') : ''
  asmrDetail.value = null
  asmrFiles.value = []
}

// 收藏/取消收藏作品
function handleAsmrToggleFavorite(item) {
  if (!window.api || !item) return
  window.api.sendCommand({
    cmd: 'asmr_toggle_favorite',
    work_id: String(item.video_id),
    card: JSON.parse(JSON.stringify(item)),
  })
}

// 点击 tag 搜索（填入搜索框并搜索）
function handleAsmrSearchTag(tag) {
  if (!tag) return
  asmrView.value = ''
  asmrItems.value = []
  searchQuery.value = tag
  handleSearch()
}

// 点击社团查看全部作品
function handleAsmrOpenCircle(detail) {
  if (!detail) return
  const cid = (detail.circle && detail.circle.id) || detail.circle_id
  const name = (detail.circle && detail.circle.name) || detail.author
  if (!cid) {
    message.warning('该作品没有社团信息')
    return
  }
  handleAsmrWorks(1, { kind: 'circles', id: String(cid), name })
}

// 点击声优查看作品
function handleAsmrOpenVa(detail) {
  if (!detail || !detail.vas || !detail.vas.length) return
  const name = detail.vas[0]
  // 音声列表 vas 是名字数组；索引弹窗里有声优 id，这里直接用名字打开索引弹窗由用户选择
  searchQuery.value = name
  asmrView.value = ''
  asmrItems.value = []
  handleSearch()
}

// 批量下载作品（整包下载全部音轨）
function handleAsmrBatchDownload(workIds) {
  if (!window.api || !workIds || !workIds.length) return
  asmrBatchRunning.value = true
  asmrBatchProgress.done = 0
  asmrBatchProgress.total = workIds.length
  asmrBatchProgress.message = '准备中...'
  window.api.sendCommand({
    cmd: 'asmr_batch_download',
    work_ids: workIds,
    options: JSON.parse(JSON.stringify(settings)),
  })
  addLog('下载', `音声站批量下载：${workIds.length} 个作品`)
}

// 进入 Iwara / Hanime1 / Oreno3D / EroMMDTube / ASMR 站点（或启动时停留在该站）自动加载主页
watch(() => settings.site, (s) => {
  if (s === 'iwara' && !iwHomeItems.value.length) {
    handleIwHome(1)
  } else if (s === 'hanime' && !haSections.value.length) {
    handleHaHome()
  } else if ((s === 'oreno3d' || s === 'erommdtube') && !orHomeItems.value.length) {
    handleOrHome(1)
  } else if (s === 'asmr' && !asmrItems.value.length) {
    handleAsmrPopular(1)
  }
}, { immediate: true })

// ============================
// X (Twitter) 关注列表 / 关注管理 / 关注分类 / 浏览模式
// ============================
// 记录导航栈（用于 X 视图内"← 返回"回到上一层）
function twPushNav() {
  twNavStack.value.push({
    mode: twFollowMode.value,
    owner: twFollowOwner.value,
    label: twFollowLabel.value,
    user: twViewUser.value,
    items: twFollowItems.value.slice(),
    cursor: twFollowCursor.value,
    hasMore: twFollowHasMore.value,
    feed: twBrowseFeed.value.slice(),
  })
  if (twNavStack.value.length > 20) twNavStack.value.shift()
}

// 打开关注视图：'following'=关注列表 | 'followers'=关注我的人 | 'follows'=我的分类 | ''=返回
function handleTwFollowList(mode) {
  if (!window.api) return
  if (!mode) {
    handleTwBack()
    return
  }
  if (!twitterUser.value && mode !== 'follows') {
    message.warning('请先在左侧登录 X (Twitter)')
    return
  }
  twPushNav()
  twFollowMode.value = mode
  twFollowItems.value = []
  twFollowError.value = ''
  twFollowCursor.value = ''
  twFollowHasMore.value = false
  twFollowOwner.value = ''
  twViewUser.value = null
  twFollowLabel.value = ''
  if (mode === 'follows') {
    window.api.sendCommand({ cmd: 'twitter_get_follows' })
  } else {
    window.api.sendCommand({
      cmd: mode === 'followers' ? 'twitter_followers' : 'twitter_following',
      cursor: '',
      screen_name: '',
    })
  }
}

// X 视图内返回上一层（无栈则回工具栏）
function handleTwBack() {
  const prev = twNavStack.value.pop()
  // 退出搜索态（若有），恢复搜索前的原数据
  if (twSearchSnapshot.value) {
    twSearchSnapshot.value = null
    twSearchTweets.value = []
    twLocalSearch.value = ''
  }
  if (!prev) {
    twFollowMode.value = ''
    twFollowItems.value = []
    twViewUser.value = null
    twFollowOwner.value = ''
    twFollowError.value = ''
    twBrowseError.value = ''
    return
  }
  twFollowMode.value = prev.mode
  twFollowOwner.value = prev.owner
  twFollowLabel.value = prev.label
  twViewUser.value = prev.user
  twFollowItems.value = prev.items
  twFollowCursor.value = prev.cursor
  twFollowHasMore.value = prev.hasMore
  twBrowseFeed.value = prev.feed
  twFollowError.value = ''
}

// 查看用户详情（点开关注的人：显示 TA 的关注/粉丝入口 + 解析媒体）
function handleTwOpenUser(u) {
  if (!u || !u.screen_name) return
  twPushNav()
  // 退出本地搜索态
  twSearchSnapshot.value = null
  twSearchTweets.value = []
  twLocalSearch.value = ''
  twFollowMode.value = 'user'
  twViewUser.value = JSON.parse(JSON.stringify(u))
  twFollowError.value = ''
}

// 打开指定用户的关注/粉丝列表（TA 的列表）
function handleTwUserList(mode, screenName) {
  if (!window.api || !screenName) return
  twPushNav()
  // 退出本地搜索态
  twSearchSnapshot.value = null
  twSearchTweets.value = []
  twLocalSearch.value = ''
  twFollowMode.value = mode
  twFollowOwner.value = screenName
  twViewUser.value = null
  twFollowItems.value = []
  twFollowError.value = ''
  twFollowCursor.value = ''
  twFollowHasMore.value = false
  window.api.sendCommand({
    cmd: mode === 'followers' ? 'twitter_followers' : 'twitter_following',
    cursor: '',
    screen_name: screenName,
  })
}

// 浏览模式：最近博主更新（缓存先显示 + 后台刷新）
function handleTwBrowse() {
  if (!window.api) return
  if (!twitterUser.value) {
    message.warning('请先在左侧登录 X (Twitter)')
    return
  }
  twPushNav()
  // 退出本地搜索态
  twSearchSnapshot.value = null
  twSearchTweets.value = []
  twLocalSearch.value = ''
  twFollowMode.value = 'browse'
  twBrowseError.value = ''
  if (!twBrowseFeed.value.length) {
    twBrowseFeed.value = []
  }
  window.api.sendCommand({ cmd: 'twitter_browse', offset: 0 })
}

// 浏览模式：加载更多（下一批关注博主，后端追加合并去重）
function handleTwBrowseMore() {
  if (!window.api || twBrowseLoading.value) return
  window.api.sendCommand({ cmd: 'twitter_browse', offset: twBrowseNextOffset.value || 0 })
}

// X 本地搜索：在已缓存内容中过滤（浏览信息流 / 关注列表 / 我的分类）
// 关键词匹配：#tag、推文内容、用户昵称、@handle、简介、分类 tag
function handleTwLocalSearch(keyword) {
  const kw = (keyword || '').trim().toLowerCase()
  // 清空 = 退出搜索态，恢复原视图
  if (!kw) {
    const snap = twSearchSnapshot.value
    if (snap) {
      twFollowMode.value = snap.mode
      twFollowItems.value = snap.items
      twBrowseFeed.value = snap.feed
      twSearchSnapshot.value = null
    }
    return
  }
  // 进入搜索态前保存当前视图（仅首次）
  if (!twSearchSnapshot.value) {
    twSearchSnapshot.value = {
      mode: twFollowMode.value,
      items: twFollowItems.value.slice(),
      feed: twBrowseFeed.value.slice(),
    }
  }
  twFollowMode.value = 'search'
  twSearchSnapshot.value.keyword = kw

  const matchUser = (u) => {
    const hay = [
      u.name, u.screen_name && `@${u.screen_name}`, u.screen_name,
      u.description, u.follow_tag, u.tag, u.album_name,
    ].filter(Boolean).join(' ').toLowerCase()
    return hay.includes(kw)
  }
  const matchTweet = (t) => {
    const hay = [
      t.text, t.user?.name, t.user?.screen_name && `@${t.user?.screen_name}`,
      t.user?.screen_name, t.item_page,
    ].filter(Boolean).join(' ').toLowerCase()
    return hay.includes(kw)
  }
  const results = []
  // 浏览信息流
  for (const t of twSearchSnapshot.value.feed) {
    if (matchTweet(t)) results.push({ type: 'tweet', tweet: t })
  }
  // 关注列表 / 我的分类（用户卡片）
  for (const u of twSearchSnapshot.value.items) {
    if (matchUser(u)) results.push({ type: 'user', user: u })
  }
  // 搜索态下放在 items 里渲染（复用关注列表卡片）
  twFollowItems.value = results.filter(r => r.type === 'user').map(r => r.user)
  // 推文结果单独存放
  twSearchTweets.value = results.filter(r => r.type === 'tweet').map(r => r.tweet)
  addLog('X', `本地搜索“${keyword}”：${twFollowItems.value.length} 个用户 / ${twSearchTweets.value.length} 条动态`)
}

// 加载更多（v1.1 cursor 翻页，跟随当前列表归属者）
function handleTwFollowLoadMore() {
  if (!window.api || !twFollowCursor.value || twFollowLoading.value) return
  window.api.sendCommand({
    cmd: twFollowMode.value === 'followers' ? 'twitter_followers' : 'twitter_following',
    cursor: twFollowCursor.value,
    screen_name: twFollowOwner.value || '',
  })
}

// 关注用户
function handleTwFollow(u) {
  if (!window.api) return
  window.api.sendCommand({
    cmd: 'twitter_follow',
    user_id: String(u.user_id || ''),
    screen_name: u.screen_name || '',
  })
}

// 取消关注
function handleTwUnfollow(u) {
  if (!window.api) return
  dialog.warning({
    title: '取消关注',
    content: `确定取消关注 @${u.screen_name || u.user_id} 吗？`,
    positiveText: '取消关注',
    negativeText: '再想想',
    onPositiveClick: () => {
      window.api.sendCommand({
        cmd: 'twitter_unfollow',
        user_id: String(u.user_id || ''),
        screen_name: u.screen_name || '',
      })
    },
  })
}

// 保存用户的分类归属（parent 为空 = 移除归类）
function handleTwSetFollowTag(user, parent, child) {
  if (!window.api) return
  window.api.sendCommand({
    cmd: 'twitter_set_follow_tag',
    user: JSON.parse(JSON.stringify(user || {})),
    parent: parent || '',
    child: child || '',
  })
  // 本地同步更新卡片上的分类标签显示
  const idx = twFollowItems.value.findIndex(
    u => String(u.user_id) === String(user?.user_id),
  )
  if (idx >= 0) {
    const tag = [parent, child].filter(Boolean).join('/')
    twFollowItems.value[idx].follow_tag = tag
  }
}

// 新增关注分类（母类，或已有母类下加子类）
function handleTwAddFollowTag(parent, child) {
  if (!window.api) return
  window.api.sendCommand({
    cmd: 'twitter_add_follow_tag',
    parent: parent || '',
    child: child || '',
  })
}

// 删除关注分类（母类或子类）
function handleTwDeleteFollowTag(parent, child) {
  if (!window.api) return
  window.api.sendCommand({
    cmd: 'twitter_delete_follow_tag',
    parent: parent || '',
    child: child || '',
  })
}

// 清除 Twitter 专属缓存（保留登录与关注分类）
function handleTwClearCache() {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'twitter_clear_cache' })
}

// ============================
// 重名文件手动改名（下载去重）
// ============================
// 弹出队列中下一个改名请求
function showNextRenamePrompt() {
  const next = renameQueue.value.shift()
  if (!next) {
    renameModal.visible = false
    return
  }
  const orig = next.filename || ''
  const dotIdx = orig.lastIndexOf('.')
  const stem = dotIdx > 0 ? orig.slice(0, dotIdx) : orig
  const ext = dotIdx > 0 ? orig.slice(dotIdx) : ''
  renameModal.filename = orig
  renameModal.existingSize = next.existing_size
  renameModal.newSize = next.new_size
  // 预填建议名：自动序号顺延（name (1).ext）
  renameModal.newName = `${stem} (1)${ext}`
  renameModal.item = next.item || null
  renameModal.url = next.url || url.value
  renameModal.album = next.album || ''
  renameModal.visible = true
}

// 确认改名并重新下载该文件（rename_map 回传给后端）
function confirmRenameDownload() {
  const newName = (renameModal.newName || '').trim()
  if (!newName) return
  if (!renameModal.item || !window.api) {
    renameModal.visible = false
    return
  }
  const options = JSON.parse(JSON.stringify(settings))
  options.rename_map = { [renameModal.filename]: newName }
  if (renameModal.item.item_page) {
    options.rename_map[renameModal.item.item_page] = newName
  }
  window.api.sendCommand({
    cmd: 'download',
    url: renameModal.url || url.value,
    items: [JSON.parse(JSON.stringify(renameModal.item))],
    options,
    album_name: renameModal.album || albumInfo.album_name || '',
    album_id: albumInfo.album_id || undefined,
  })
  addLog('下载', `重名文件改名重下: ${renameModal.filename} → ${newName}`)
  renameModal.visible = false
}

// 弹窗关闭后（跳过或确认），若队列还有冲突则继续弹下一个
watch(() => renameModal.visible, (v) => {
  if (!v && renameQueue.value.length) {
    setTimeout(showNextRenamePrompt, 150)
  }
})

// ============================
// 下载任务管理器操作
// ============================
function requestSettings() {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'get_settings' })
}

function requestTasks() {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'get_tasks' })
}

// 打开独立下载管理器窗口（不再使用应用内覆盖层）
function toggleDownloadManager() {
  if (window.api && window.api.showDownloadsWindow) {
    window.api.showDownloadsWindow()
  }
}

// 在主窗口打开详细下载面板（聚焦指定任务）
function openDownloadDetail(taskId) {
  detailTaskId.value = taskId || null
  detailVisible.value = true
  requestTasks()
}

function pauseTask(taskId) {
  if (window.api) window.api.sendCommand({ cmd: 'pause_task', task_id: taskId })
}

function resumeTask(taskId) {
  if (window.api) window.api.sendCommand({ cmd: 'resume_task', task_id: taskId })
}

function resumeAllTasks() {
  downloadTasks.value
    .filter(t => t.status === 'paused')
    .forEach(t => resumeTask(t.id))
}

function cancelTask(taskId) {
  if (window.api) window.api.sendCommand({ cmd: 'cancel_task', task_id: taskId })
}

function removeTask(taskId) {
  if (window.api) window.api.sendCommand({ cmd: 'remove_task', task_id: taskId })
}

function toggleShutdown(v) {
  shutdownOn.value = v
  if (window.api) window.api.sendCommand({ cmd: 'shutdown_after_done', enabled: v })
}

// 切换悬浮窗显示/隐藏
function toggleFloat(v) {
  floatVisible.value = v
  settings.float_visible = v
  if (window.api && window.api.setFloatVisible) {
    window.api.setFloatVisible(v)
  }
  saveSettings()
}

// 计算下载汇总并更新悬浮窗（发送完整任务列表，供悬浮窗波浪进度条切换显示）
function updateFloatData() {
  if (!window.api || !window.api.updateFloat) return
  let running = 0
  let speed = 0
  const tasks = downloadTasks.value.map((t) => {
    let taskSpeed = 0
    const files = (t.files || []).map((f) => {
      if (f.status === 'downloading') {
        taskSpeed += f.speed || 0
      }
      return {
        filename: f.filename,
        status: f.status,
        completed: f.completed,
        speed: f.speed || 0,
        size: f.size,
      }
    })
    if (t.status === 'running') {
      running++
      speed += taskSpeed
    }
    const done = t.done || 0
    const total = t.total || 0
    const percent = total > 0 ? Math.round((done / total) * 100) : 0
    return {
      id: t.id,
      album: t.album,
      status: t.status,
      done,
      total,
      percent,
      speed: taskSpeed,
      files,
    }
  })
  window.api.updateFloat({ running, speed, tasks })
}

// ============================
// 历史任务操作
// ============================
function requestHistory() {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'get_history' })
}

function deleteHistoryRecord(id, deleteFile) {
  if (!window.api) return
  window.api.sendCommand({
    cmd: 'delete_history',
    id,
    delete_file: deleteFile,
  })
}

async function openFilePath(filePath) {
  if (!window.api || !filePath) return
  const result = await window.api.openPath(filePath)
  if (result && !result.ok) {
    addLog('错误', `打开文件失败: ${result.error}`)
  }
}

async function showFileInFolder(filePath) {
  if (!window.api || !filePath) return
  const result = await window.api.showInFolder(filePath)
  if (result && !result.ok) {
    addLog('错误', `打开文件夹失败: ${result.error}`)
  }
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

// ============================
// 文件类型判断（按后缀）
// ============================
const IMAGE_EXTS = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.tiff', '.avif', '.ico']
const VIDEO_EXTS = ['.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv', '.wmv', '.m4v', '.ts', '.m2ts', '.3gp']
const AUDIO_EXTS = ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.opus']
const ARCHIVE_EXTS = ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.cab', '.iso']
const DOC_EXTS = ['.pdf', '.doc', '.docx', '.txt', '.md', '.rtf', '.xls', '.xlsx', '.ppt', '.pptx', '.csv', '.json', '.xml']

function getFileExt(filename) {
  const name = filename || ''
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i).toLowerCase() : ''
}

function getFileType(filename) {
  const ext = getFileExt(filename)
  if (IMAGE_EXTS.includes(ext)) return '图片'
  if (VIDEO_EXTS.includes(ext)) return '视频'
  if (AUDIO_EXTS.includes(ext)) return '音频'
  if (ARCHIVE_EXTS.includes(ext)) return '压缩包'
  if (DOC_EXTS.includes(ext)) return '文档'
  return '其他'
}

function isMediaFile(filename) {
  const ext = getFileExt(filename)
  return IMAGE_EXTS.includes(ext) || VIDEO_EXTS.includes(ext)
}

// 为非图片/视频文件加载系统图标
async function applyFileIcons() {
  if (!window.api || !window.api.getFileIcon) return
  const targets = fileList.value.filter((item) => !item.thumbnail && !isMediaFile(item.filename))
  await Promise.all(targets.map(async (item) => {
    try {
      const dataUrl = await window.api.getFileIcon(item.filename)
      if (dataUrl) item.file_icon = dataUrl
    } catch (e) {
      // 忽略图标获取失败
    }
  }))
}

// ============================
// 生命周期
// ============================
onMounted(() => {
  console.log('[App] onMounted, window.api =', typeof window.api)
  if (window.api && window.api.onEvent) {
    window.api.onEvent(handlePythonEvent)
    console.log('[App] 已注册事件监听')
  } else {
    console.error('[App] window.api 或 onEvent 不可用')
    addLog('错误', '无法连接后端：window.api 不可用')
  }
  // 悬浮窗被关闭时，同步设置里的开关状态
  if (window.api && window.api.onFloatClosed) {
    window.api.onFloatClosed(() => {
      floatVisible.value = false
    })
  }
  // 下载管理窗口双击/右键：在主窗口打开详细下载面板
  if (window.api && window.api.onOpenDownloadDetail) {
    window.api.onOpenDownloadDetail((taskId) => {
      openDownloadDetail(taskId)
    })
  }
  // 主动查询后端启动错误（事件可能在本组件挂载前就已发出）
  if (window.api && window.api.getBackendError) {
    window.api.getBackendError().then((err) => {
      if (err && !backendReady.value) {
        backendError.value = err
        message.error(err)
        addLog('错误', err)
      }
    }).catch(() => {})
  }
})

onUnmounted(() => {
  // Electron 会自动清理
})
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body, #app {
  height: 100%;
  overflow: hidden;
  background: #18181c;
}

/* 让 naive-ui 的 provider 包裹层也占满高度，否则内部 height:100% 会失效 */
.n-config-provider,
.n-message-provider,
.n-dialog-provider {
  height: 100%;
}

.app-layout {
  display: flex;
  height: 100vh;
  background: #18181c;
}

/* 重名文件手动改名弹窗 */
.rename-modal {
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 13px;
}

.rename-tip {
  color: #f2c97d;
}

.rename-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.rename-label {
  flex-shrink: 0;
  width: 80px;
  color: #909090;
}

.rename-value {
  color: #e0e0e0;
  word-break: break-all;
}

.rename-hint {
  font-size: 12px;
  color: #909090;
}

/* ============================ */
/* 日间模式（html.light-mode）：主要容器与文字覆盖 */
/* ============================ */
html.light-mode body,
html.light-mode #app {
  background: #f2f3f5;
}

html.light-mode .app-layout {
  background: #f2f3f5;
}

/* 左右面板与顶栏 */
html.light-mode .left-panel,
html.light-mode .url-bar,
html.light-mode .inspect-progress,
html.light-mode .account-card {
  background: #ffffff;
}

html.light-mode .right-panel {
  background: #f7f7fa;
}

html.light-mode .url-bar,
html.light-mode .inspect-progress {
  border-color: #e5e6eb;
}

/* 卡片 / 列表条目 / 工具栏等深色面板 */
html.light-mode .search-card,
html.light-mode .ex-search-options,
html.light-mode .ex-detail,
html.light-mode .ex-browser,
html.light-mode .torrent-list,
html.light-mode .torrent-item,
html.light-mode .magnet-result,
html.light-mode .download-bar,
html.light-mode .tw-toolbar,
html.light-mode .tw-follow-view,
html.light-mode .tw-user-card,
html.light-mode .empty-state,
html.light-mode .pa-results,
html.light-mode .pa-toolbar,
html.light-mode .ex-results,
html.light-mode .ex-toolbar,
html.light-mode .ex-tr,
html.light-mode .ex-inline-info,
html.light-mode .tw-follow-toolbar {
  background: #ffffff;
}

html.light-mode .tw-user-card:hover,
html.light-mode .search-card:hover {
  background: #f0f1f4;
}

/* 深色小面板（chips / hover 层） */
html.light-mode .ex-cat-chip,
html.light-mode .ex-detail-tag,
html.light-mode .ex-cat-all,
html.light-mode .ex-tr-alt,
html.light-mode .account-profiles {
  background: #ececf1;
}

/* 主要文字（深色主题下为浅色文字的类） */
html.light-mode .album-name,
html.light-mode .thumb-files,
html.light-mode .torrent-name,
html.light-mode .card-name,
html.light-mode .ex-thumb-card-title,
html.light-mode .ex-info-title,
html.light-mode .ex-detail-name,
html.light-mode .login-title,
html.light-mode .switch-label,
html.light-mode .account-line-value,
html.light-mode .tag-text,
html.light-mode .fav-title,
html.light-mode .tw-user-nick,
html.light-mode .tw-user-desc,
html.light-mode .tw-user-stats,
html.light-mode .tw-follow-title,
html.light-mode .tw-tag-user,
html.light-mode .rename-value,
html.light-mode .rename-tip,
html.light-mode .empty-text,
html.light-mode .selected-info,
html.light-mode .magnet-label,
html.light-mode .pa-result-count,
html.light-mode .ex-result-count,
html.light-mode .torrent-meta,
html.light-mode .ex-info-meta,
html.light-mode .ex-inline-label,
html.light-mode .ex-inline-tagrow-ns {
  color: #4e5969;
}

html.light-mode .ex-inline-value,
html.light-mode .ex-inline-tag {
  color: #1f2329;
}

/* 边框微调 */
html.light-mode .search-card,
html.light-mode .tw-user-card,
html.light-mode .torrent-item,
html.light-mode .magnet-result,
html.light-mode .ex-detail {
  border-color: #e5e6eb;
}

/* ============================ */
/* 日间模式：底部下载进度 / 日志 / 历史 */
/* ============================ */
html.light-mode .bottom-area {
  background: #ffffff;
  border-top-color: #e5e6eb;
}

html.light-mode .progress-filename,
html.light-mode .log-message,
html.light-mode .empty-tab,
html.light-mode .log-time,
html.light-mode .history-meta,
html.light-mode .progress-meta {
  color: #5a5c66;
}

html.light-mode .progress-speed {
  color: #18a058;
}

html.light-mode .log-item,
html.light-mode .history-item {
  border-bottom-color: rgba(30, 34, 44, 0.06);
}

html.light-mode .history-name {
  color: #1f2329;
}

/* 日间模式：其余次要面板（浏览器工具栏 / 标签面板 / 设置区 / 标签列表） */
html.light-mode .ex-toolbar,
html.light-mode .settings-section,
html.light-mode .ex-search-options,
html.light-mode .follow-tag-section {
  background: #ffffff;
}

html.light-mode .ex-address,
html.light-mode .ex-cat-chip,
html.light-mode .follow-tag-group {
  background: #f2f3f5;
}

html.light-mode .section-title {
  color: #18a058;
}

html.light-mode .switch-hint,
html.light-mode .login-hint,
html.light-mode .account-subtitle,
html.light-mode .login-subtitle,
html.light-mode .progress-text,
html.light-mode .tw-toolbar-hint,
html.light-mode .tw-follow-count,
html.light-mode .tw-user-handle,
html.light-mode .tw-user-stats,
html.light-mode .empty-hint {
  color: #8a8d99;
}

html.light-mode .tw-user-desc,
html.light-mode .tw-tweet-text,
html.light-mode .settings-content,
html.light-mode .ex-detail-tag {
  color: #3a3d46;
}

/* 日间模式：X 浏览模式推文卡片 / 浏览进度条 */
html.light-mode .tw-tweet-card {
  background: #ffffff;
  border-color: #e5e6eb;
}

html.light-mode .tw-tweet-card:hover {
  background: #f7f8fa;
}

html.light-mode .tw-browse-progress {
  border-bottom-color: #e5e6eb;
}

/* 日间模式：文件小方格视图 */
html.light-mode .file-grid-item {
  background: #ffffff;
}

html.light-mode .file-grid-item:hover {
  background: #f7f8fa;
}

html.light-mode .file-grid-item.grid-selected {
  border-color: #18a058;
  background: #f0fff7;
}

html.light-mode .grid-thumb {
  background: #eceef2;
}

html.light-mode .grid-check {
  background: #18a058;
  color: #ffffff;
}

html.light-mode .grid-name {
  color: #1f2329;
}
</style>
