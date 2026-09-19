<template>
  <n-config-provider :theme="naiveTheme" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <n-dialog-provider>
        <!-- 里/美好世界自定义标题栏：随模式变色（里=暗 / 表=亮），兼作拖动区与窗口控制 -->
        <div class="win-titlebar" :class="settings.ui_mode_hot ? 'tb-light' : 'tb-dark'">
          <span class="tb-badge">{{ settings.ui_mode_hot ? '美好世界' : '里世界' }}</span>
          <span class="tb-app">小小浏览器</span>
          <div class="tb-controls">
            <button title="最小化" @click="winCtl('minimize')">—</button>
            <button title="最大化/还原" @click="winCtl('maximize')">▢</button>
            <button class="tb-close" title="关闭" @click="winCtl('close')">✕</button>
          </div>
        </div>

        <!-- 经典下载器界面 = 里世界（ui_mode_hot=true 时整屏切换为美好世界 ModernHome） -->
        <div class="win-frame" :class="{ 'win-maxed': winMaxed }" v-show="!settings.ui_mode_hot">
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
            :pixiv-user="pixivUser"
            :pixiv-login-loading="pixivLoginLoading"
            @pixiv-login="handlePixivLogin"
            @pixiv-logout="handlePixivLogout"
            @pixiv-set-proxy="handlePixivSetProxy"
            :asmr-user="asmrUser"
            :asmr-login-loading="asmrLoginLoading"
            @asmr-login="handleAsmrLogin"
            @asmr-logout="handleAsmrLogout"
            @asmr-set-proxy="handleAsmrSetProxy"
            :reverse-paste="reversePaste"
            @reverse-toggle="handleReverseToggle"
            @reverse-paste-save="handleReversePasteSave"
            @reverse-set-proxy="handleReverseSetProxy"
            @oreno-set-proxy="handleOrenoSetProxy"
            :xhamster-user="xhamsterUser"
            :fc2-user="fc2User"
            :pornhub-user="pornhubUser"
            :xvideos-user="xvideosUser"
            :javdb-user="javdbUser"
            :google-user="googleUser"
            :oreno3d-user="oreno3dUser"
            :erommdtube-user="erommdtubeUser"
            :oreno3d-cred="oreno3dCred"
            :erommdtube-cred="erommdtubeCred"
            :google-email="googleEmail"
            :google-accounts="googleAccounts"
            @site-oauth-login="handleSiteOAuthLogin"
            @site-logout="handleSiteLogout"
            @site-set-proxy="handleSiteSetProxy"
            @google-save-cred="handleGoogleSaveCred"
            @google-switch-account="handleGoogleSwitchAccount"
            @google-delete-account="handleGoogleDeleteAccount"
            @oreno-save-cred="handleOrenoSaveCred"
            @site-save-cred="handleSiteSaveCred"
            :site-creds="siteCreds"
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
            @common-proxy="handleCommonProxy"
            @sniffer-open="handleSnifferOpen"
            @bt-open="handleBtOpen"
            @leak-edge-login="handleLeakEdgeLogin"
            @leak-edge-harvest="handleLeakEdgeHarvest"
            :leak-edge-running="leakEdgeRunning"
            :tw-follows="twFollowItems"
            :media-proxy-port="mediaProxyPort"
            @tw-open-user="handleTwOpenUser"
            @tw-get-follows="handleTwGetFollows"
            :theme-mode="settings.theme || 'dark'"
            @toggle-theme="toggleTheme"
            @tw-add-follow-tag="handleTwAddFollowTag"
            @tw-delete-follow-tag="handleTwDeleteFollowTag"
            @tw-clear-cache="handleTwClearCache"
            @exhentai-set-cookies="handleExSyncCookies"
            @exhentai-webview-login="creds => handleSiteOAuthLogin('exhentai', creds)"
            @exhentai-logout="handleExLogout"
            @open-login-page="handleOpenLoginPage"
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
            @check-github-update="handleFetchChangelog"
            :github-update-info="githubUpdateInfo"
            :github-checking="githubChecking"
            :changelog-loading="changelogLoading"
            :app-version="appVersion"
            :update-download="updateDownload"
            @download-update="handleDownloadUpdate"
            @install-update="handleInstallUpdate"
            @shortcut-change="handleShortcutChange"
            @cancel-login="handleCancelLogin"
            @restart-app="handleRestartApp"
          />
          <RightPanel
            v-show="!detailVisible"
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
            :ex-inline-detail="exInlineDetail"
            :ex-fav-mode="exFavMode"
            :ex-popular-mode="exPopularMode"
            :ex-batch-running="exBatchDownloading"
            :ex-batch-progress="exBatchProgress"
            :batch-file-collected="batchFileCollected"
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
            :tw-user-feed="twUserFeed"
            :tw-user-feed-loading="twUserFeedLoading"
            :tw-user-feed-has-more="twUserFeedHasMore"
            :tw-profile-stats="twUserProfileStats"
            :tw-user-load-all-running="twUserLoadAllRunning"
            :tw-user-load-all-progress="twUserLoadAllProgress"
            :tw-export-running="twExportRunning"
            :tw-export-progress="twExportProgress"
            :tw-browse-load-all-running="twBrowseLoadAllRunning"
            :tw-browse-load-all-count="twBrowseLoadAllCount"
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
            :xh-view="xhView"
            :xh-tab="xhTab"
            :xh-home-items="xhHomeItems"
            :xh-home-loading="xhHomeLoading"
            :xh-home-error="xhHomeError"
            :xh-home-sort="xhHomeSort"
            :xh-home-has-more="xhHomeHasMore"
            :xh-cats-loading="xhCatsLoading"
            :xh-cats-trending="xhCatsTrending"
            :xh-cats-groups="xhCatsGroups"
            :xh-cats-error="xhCatsError"
            :xh-cat-name="xhCatName"
            :xh-cat-items="xhCatItems"
            :xh-cat-loading="xhCatLoading"
            :xh-cat-error="xhCatError"
            :xh-cat-has-more="xhCatHasMore"
            :xh-shorts-items="xhShortsItems"
            :xh-shorts-loading="xhShortsLoading"
            :xh-shorts-error="xhShortsError"
            :xh-shorts-has-more="xhShortsHasMore"
            :xh-notif="xhNotif"
            :xh-notif-loading="xhNotifLoading"
            :xh-my-tab="xhMyTab"
            :xh-my-items="xhMyItems"
            :xh-my-loading="xhMyLoading"
            :xh-my-error="xhMyError"
            :xh-my-has-more="xhMyHasMore"
            :xh-my-username="xhMyUsername"
            :xh-detail="xhDetail"
            :xh-detail-loading="xhDetailLoading"
            :xh-detail-error="xhDetailError"
            :xh-comments="xhComments"
            :xh-comment-count="xhCommentCount"
            :xh-user="xhUser"
            :xh-user-items="xhUserItems"
            :xh-user-loading="xhUserLoading"
            :xh-user-error="xhUserError"
            :xh-user-has-more="xhUserHasMore"
            :xh-user-tab="xhUserTab"
            :xh-user-profile="xhUserProfile"
            :xh-subscribe-loading="xhSubscribeLoading"
            :xh-comment-sending="xhCommentSending"
            :xh-batch-running="xhBatchRunning"
            :xh-batch-progress="xhBatchProgress"
            :asmr-view="asmrView"
            :asmr-items="asmrItems"
            :asmr-recommend="asmrRecommend"
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
            :asmr-related="asmrRelated"
            :asmr-related-pending="asmrRelatedPending"
            :asmr-batch-running="asmrBatchRunning"
            :asmr-batch-progress="asmrBatchProgress"
            :reverse-active="reverseActive"
            :reverse-sites="reverseSites"
            :reverse-running="reverseRunning"
            :pixiv-state="pixivState"
            :pixiv-search-type="settings.pixiv_search_type || 'illust'"
            :pixiv-active-feed="pixivActiveFeed"
            :pixiv-batch-running="pixivBatchRunning"
            :pixiv-batch-progress="pixivBatchProgress"
            @pixiv-command="handlePixivCommand"
            @reverse-search="handleReverseSearch"
            @reverse-reset="handleReverseReset"
            @reverse-cancel="handleReverseCancel"
            @reverse-download="handleReverseDownload"
            :reverse-merged="reverseMerged"
            :reverse-cached="reverseCached"
            :javdb-detail="javdbDetail"
            :javdb-detail-loading="javdbDetailLoading"
            :javdb-batch-running="javdbBatchRunning"
            :javdb-batch-progress="javdbBatchProgress"
            :javdb-user="javdbUser"
            :javdb-search-field="javdbSearchField"
            :javdb-tags-vocab="javdbTagsVocab"
            :javdb-tags-mode="javdbTagsMode"
            :javdb-hot="javdbHotKeywords"
            :javdb-dir="javdbDir"
            :javdb-mode-recommend="javdbModeRecommend"
            :auto-translating="autoTranslating"
            :auto-translate-mode="autoTranslateMode"
            :translated-titles="translatedTitles"
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
            @tw-user-feed-more="handleTwUserFeedMore"
            @tw-user-feed-download-all="handleTwUserFeedDownloadAll"
            @tw-user-load-all="handleTwUserFeedLoadAll"
            @tw-export-html="handleTwExportHtml"
            @tw-browse-load-all="handleTwBrowseLoadAll"
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
            @xh-tab="handleXhTab"
            @xh-home="p => handleXhHome(p || 1)"
            @xh-home-more="handleXhHomeMore"
            @xh-home-sort="handleXhHomeSort"
            @xh-open-category="handleXhOpenCategory"
            @xh-cat-back="handleXhCatBack"
            @xh-cat-more="handleXhCatMore"
            @xh-open-categories="handleXhOpenCategories"
            @xh-shorts-reload="handleXhShortsReload"
            @xh-shorts-more="handleXhShortsMore"
            @xh-notifications="handleXhNotifications"
            @xh-my-tab="t => handleXhMy(t || 'favorites', 1)"
            @xh-my-more="handleXhMyMore"
            @xh-open-detail="handleXhOpenDetail"
            @xh-detail-back="handleXhDetailBack"
            @xh-open-user="handleXhOpenUser"
            @xh-user-back="handleXhUserBack"
            @xh-user-more="handleXhUserMore"
            @xh-user-tab="handleXhUserTab"
            @xh-subscribe="handleXhSubscribe"
            @xh-add-comment="handleXhAddComment"
            @xh-search-tag="handleXhSearchTag"
            @xh-search="handleXhSearch"
            @xh-batch-download="handleXhBatchDownload"
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
            @asmr-download-files="handleAsmrDownloadFiles"
            @javdb-open-detail="handleJavdbOpenDetail"
            @javdb-detail-back="handleJavdbDetailBack"
            @javdb-download-images="handleJavdbDownloadImages"
            @javdb-batch-download="handleJavdbBatchDownload"
            @javdb-home="p => handleJavdbHome(p || 1)"
            @javdb-open-actor="u => handleJavdbOpenActor(u)"
            @javdb-search-tag="handleJavdbSearchTag"
            @javdb-search-field="setJavdbSearchField"
            @javdb-hot="handleJavdbHotSearch"
            @javdb-open-list="handleJavdbOpenList"
            @javdb-dir="handleJavdbDir"
            @javdb-dir-page="handleJavdbDirPage"
            @javdb-dir-clear="handleJavdbDirClear"
            @javdb-mode="handleJavdbTagsMode"
            @javdb-logout="handleJavdbLogout"
            @search="handleSearch"
            @load-more="handleLoadMore"
            @go-page="handleGoPage"
            @open-album="openSearchResult"
            @back-to-search="handleBackToSearch"
            @download="handleDownload"
            @ctx-download-file="handleCtxDownloadFile"
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
            @ex-popular="handleExPopular"
            @ex-batch-download="handleExBatchDownload"
            @ex-batch-cancel="handleExBatchCancel"
            @show-collected-files="handleShowCollectedFiles"
            @clear-batch-tasks="handleClearBatchTasks"
            @ex-close-detail="handleExCloseDetail"
            @ex-save-torrent="handleExSaveTorrent"
            @pa-open-post="handlePaOpenPost"
            @pa-close-detail="handlePaCloseDetail"
            @pa-favorites="handlePawchiveFavorites"
            @pa-home="handlePawchiveHome"
            @pa-open-artist="handlePaOpenArtist"
            @pa-close-artist="handlePaCloseArtist"
            @ex-add-hidden-tag="handleExAddHiddenTag"
            @ex-delete-hidden-tag="handleExDeleteHiddenTag"
            @add-favorite="handleAddFavorite"
            @pa-download-artist="handlePaDownloadArtist"
            @pa-fav-toggle="handlePaFavToggle"
            @site-back="handleSiteBack"
            @site-back-root="handleSiteBackRoot"
            :gs-state="gsStates[settings.site || 'bunkr'] || null"
            :local-favorites="localFavorites"
            @gs-command="handleGsCommand"
            @gs-restore-state="handleGsRestoreState"
          />

          <!-- 迅雷式下载管理视图（左侧"下载状态"按钮切换，占据主内容区） -->
          <DownloadManagerPanel
            v-if="detailVisible"
            :visible="detailVisible"
            :tasks="downloadTasks"
            :shutdown-on="shutdownOn"
            :focus-task-id="detailTaskId"
            :translated-titles="translatedTitles"
            @close="detailVisible = false"
            @pause="pauseTask"
            @resume="resumeTask"
            @retry="retryTask"
            @retry-file="retryFile"
            @resume-all="resumeAllTasks"
            @cancel="cancelTask"
            @remove="removeTask"
            @clear-all="clearAllTasks"
            @toggle-shutdown="toggleShutdown"
            @open-folder="handleOpenTaskFolder"
            @locate-file="handleLocateTaskFile"
          />
          </div><!-- /app-layout（flex：左面板 + 右侧内容区横排） -->
        </div>

        <!-- 美好世界 = 热门平台主界面（B站/抖音/小红书等；完全替换经典界面，进出只靠三连 Alt） -->
        <div class="win-frame" :class="{ 'win-maxed': winMaxed }" v-show="settings.ui_mode_hot">
          <ModernHome />
        </div>

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

        <!-- 更新日志弹窗（点"检查更新"先弹：多版本更新说明，可下滑浏览，底部取消/更新） -->
        <n-modal v-model:show="changelogModalVisible" preset="dialog" :title="changelogInfo?.has_new ? `发现新版本 ${changelogInfo.latest_version}` : '更新说明'" style="width: 640px">
          <div class="changelog-modal">
            <div v-if="changelogInfo?.has_new" class="changelog-tip">
              当前版本 v{{ changelogInfo.current_version || appVersion }} → 最新版本 {{ changelogInfo.latest_version }}，以下是本次更新内容：
            </div>
            <div v-else class="changelog-tip changelog-tip-latest">当前已是最新版本，以下为历史版本更新记录：</div>
            <n-scrollbar class="changelog-scroll">
              <div v-for="sec in (changelogInfo?.versions || [])" :key="sec.version" class="changelog-section">
                <div class="changelog-section-title">{{ sec.version }}<span v-if="sec.date" class="changelog-section-date">{{ sec.date }}</span></div>
                <ul class="changelog-lines">
                  <li v-for="(line, i) in sec.lines" :key="i">{{ line }}</li>
                </ul>
              </div>
            </n-scrollbar>
          </div>
          <template #action>
            <n-button size="small" @click="changelogModalVisible = false">取消</n-button>
            <n-button size="small" type="primary" @click="handleChangelogConfirmUpdate">更新</n-button>
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
          :credentials="wvLogin.credentials"
          :manual-confirm="wvLogin.manualConfirm"
          :confirm-hint="wvLogin.confirmHint"
          :confirm-text="wvLogin.confirmText"
          :auto-grab-pattern="wvLogin.autoGrabPattern"
          :code-regex="wvLogin.codeRegex"
          :watch-login-url="wvLogin.watchLoginUrl"
          :title="`${wvLogin.site} webview 登录`"
          @login-success="handleSiteLoginSuccess"
          @login-failed="err => message.error(err || '登录失败')"
          @login-code="handleSiteLoginCode"
        />

        <!-- ASMR 后台迷你播放器：有播放任务且全量播放器（asmr 详情）不可见时悬浮右下 -->
        <AsmrMiniPlayer
          v-if="audioPlayer.track && !(settings.site === 'asmr' && asmrView === 'detail' && !detailVisible)"
          @jump-back="handleAsmrMiniJumpBack"
        />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { ref, reactive, computed, watch, watchEffect, onMounted, onUnmounted, defineAsyncComponent } from 'vue'
import { darkTheme, zhCN, dateZhCN, createDiscreteApi } from 'naive-ui'
import LeftPanel from './components/LeftPanel.vue'
import RightPanel from './components/RightPanel.vue'
import DownloadManagerPanel from './components/DownloadManagerPanel.vue'
// f5b 代码分割：美好世界主界面/登录弹窗按需加载（无 ref 契约，异步包裹零行为差异）
const ModernHome = defineAsyncComponent(() => import('./components/ModernHome.vue'))
const WebviewLoginModal = defineAsyncComponent(() => import('./components/WebviewLoginModal.vue'))
// 上次停留在美好世界：立刻预取 ModernHome 分包。defineAsyncComponent 只在首次渲染时才
// 开始下载分块，若等到首帧再拉，美好世界用户会先看到一段空白（或里世界的残留）。
try {
  const bootHot = !!(window.api && window.api.uiModeHotAtBoot === true)
  const lsHot = localStorage.getItem('mh_ui_mode_hot') === '1'
  if (bootHot || lsHot) import('./components/ModernHome.vue').catch(() => {})
} catch (e) { /* 隐私模式 */ }
import AsmrMiniPlayer from './components/AsmrMiniPlayer.vue'
import { playerState as audioPlayer, setProxyPort as setAsmrProxyPort } from './audioPlayer.js'
import { gsConfigFor } from './siteConfigs.js'

// 独立的消息提示（用于在非 Provider 组件中弹出 Toast）
const { message, dialog } = createDiscreteApi(['message', 'dialog'], {
  configProviderProps: { theme: darkTheme },
})

// ============================
// 设置
// ============================
const settings = reactive({
  custom_path: '',
  // 表世界（美好世界）专属保存位置：留空 = 用户下载夹。
  // 只影响表世界的媒体下载 / 流媒体拼接 / Word 导出，不动里世界与各站下载路径
  surface_save_path: '',
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
  fc2_proxy: 'http://127.0.0.1:10809',   // FC2 国内必须代理（webview 登录 + 浏览 + 下载）
  twitter_subfolder: 'media',
  twitter_md5_dedup: true, // MD5 查重：同内容只保留最早发布的一份
  // Iwara 专属设置（代理留空 = 直连）
  iwara_proxy: '',
  // Hanime1 / Oreno3D / EroMMDTube 专属设置（H站国内需代理；O3D/E站 默认直连）
  hanime_proxy: 'http://127.0.0.1:10809',
  oreno_proxy: '',
  erommd_proxy: '',
  // H站搜索过滤（分类/排序，随搜索选项发送并长期保存）
  hanime_genre: '',
  hanime_sort: '',
  // Pixiv 专属设置（国内必须代理；搜索模式：''=全部 / safe=全年龄 / r18=R-18）
  pixiv_proxy: 'http://127.0.0.1:10809',
  pixiv_mode: '',
  pixiv_search_type: 'illust',   // 搜索三模式：illust=插画/漫画（默认） novel=小说 user=用户
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
  // 识图（反向图片搜索）设置
  reverse_proxy: '',            // 识图代理（默认只给 Lenso.ai 用；留空 = 直连）
  reverse_proxy_all: false,     // true = 所有识图站点都走该代理（默认只给需要代理的站点）
  reverse_lenso_token: '',      // Lenso.ai API Token（官方 API 需付费订阅；留空跳过该站）
  reverse_saucenao_api_key: '', // SauceNAO API Key（免费注册获取；留空走免费配额）
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
  float_visible: false,  // 默认不开悬浮窗（2026-09-17 用户要求：避免旁人看到下载历史）
  // 主界面模式：false=经典下载器界面（里世界）/ true=热门平台界面（美好世界，ModernHome）
  // 取值优先级（都是为了"打开程序一次都不闪里世界"）：
  //   1) 主进程从 settings.json 同步读出、随命令行传入的启动模式（首帧之前就可用）
  //   2) localStorage 缓存的上次模式（浏览器环境下/旧版 preload 的兜底）
  //   3) 默认里世界
  // 后端 settings 到达后会再校准一次（见 _pyEvt_settings），并写回 localStorage。
  ui_mode_hot: (() => {
    try {
      const boot = window.api && window.api.uiModeHotAtBoot
      if (typeof boot === 'boolean') return boot
    } catch (e) { /* ignore */ }
    try { return localStorage.getItem('mh_ui_mode_hot') === '1' } catch (e) { return false } /* 隐私模式 */
  })(),
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
  // 界面模式写回 localStorage：保证下次启动首帧就是正确界面，不闪里世界
  if ('ui_mode_hot' in newSettings) {
    try { localStorage.setItem('mh_ui_mode_hot', newSettings.ui_mode_hot ? '1' : '0') } catch (e) { /* 隐私模式 */ }
  }
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
let inspectWatchdog = null  // 解析看门狗：后端长时间无响应时解除 loading
let searchWatchdog = null   // 搜索看门狗：后端只发 search_start 就静默时解除转圈
let javdbDetailWatchdog = null  // JavDB 详情看门狗：loading 后无结果事件时解除
const inspectProgress = reactive({ current: 0, total: 0, filename: '' })
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
// 悬浮窗显示状态（默认关：避免旁人看到下载历史；用户可在设置里开）
const floatVisible = ref(false)
const leakEdgeRunning = ref(false)  // Leakedzone：专用 Edge 调试实例运行中（过盾抓 Cookie 流程）

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
// EX 内联详情模式：从搜索结果/收藏点开作品时，搜索结果保留在上方，详情+文件列表追加在下方（不跳转）
const exInlineDetail = ref(false)
// 点击画廊 → 新开详情界面并自动解析出图片缩略图（不再用"追加在结果最下方"的内联模式）
const exAutoParseGallery = ref(false)
// 通用站点状态仓（模块化架构 m5）：后端 gs_state {site, ...} 按 site 存取，GenericSiteView 消费
const gsStates = ref({})
// 详情打开来源标记（通用返回逻辑 m8）：从搜索结果点开详情时记录站点键，
// 返回时直接回到搜索结果（列表数据仍在），而非弹站点视图栈
const detailFromSearch = ref('')
const exFavMode = ref(false)        // 当前搜索结果视图是否为"我的收藏"模式
const exPopularMode = ref(false)    // 当前结果视图是否为"EX 首页推荐"
const exBatchDownloading = ref(false)  // EX 批量下载进行中（inspect_complete 时追加而非替换 fileList）
const exBatchCancelled = ref(false)    // 用户请求取消批量（派发循环中止；已派发的等返回后收尾且不自动下载）
const exBatchPending = ref(0)            // EX 批量下载待完成的 inspect_complete 计数（异步返回时减一）
const exBatchTotal = ref(0)              // EX 批量下载总画廊数（进度显示 done/total）
// 批量进度（传给 RightPanel 按钮）：done = 总数 - 待完成
const exBatchProgress = computed(() => ({
  done: Math.max(0, exBatchTotal.value - exBatchPending.value),
  total: exBatchTotal.value,
}))

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
// 目标语言（持久化到 settings.auto_translate_to，默认中文；左侧翻译面板可修改）
const autoTranslateTo = ref('zh-CN')
// 翻译开关：开=翻译当前页+后续新增内容自动翻译；关=停止并恢复原文
const autoTranslateMode = ref(false)
// 批量翻译在途请求：batch_id → 发送时的标题列表（回填时对位用）
const translateBatchPending = new Map()
// 目标语言改动时（左侧翻译面板修改 settings.auto_translate_to）同步到 ref
watch(() => settings.auto_translate_to, v => {
  if (v) autoTranslateTo.value = v
})


// GitHub 仓库更新检查结果（左侧设置区）
// {ok, latest_sha, latest_message, latest_date, latest_author, latest_url, local_sha, has_update, has_new_release, current_version, release:{tag,assets}, repo_url, commits_url, error}
const githubUpdateInfo = ref(null)
// 检查进行中标志（仅手动点击"检查更新"时为 true；启动后不发任何 GitHub 请求）
const githubChecking = ref(false)
// 当前程序版本号（Electron app.getVersion()，与 release tag 对比）
const appVersion = ref('')
// 更新安装包下载状态：{ downloading, received, total, percent, speed, fileName, path, done, error }
const updateDownload = reactive({ downloading: false, received: 0, total: 0, percent: 0, speed: 0, fileName: '', path: '', done: false, error: '' })
// 更新日志弹窗：点"检查更新"时先从发布仓库拉取更新日志展示（多版本可下滑浏览）
// changelogInfo = { ok, current_version, has_new, latest_version, versions: [{version, date, lines: []}] }
const changelogInfo = ref(null)
const changelogLoading = ref(false)
const changelogModalVisible = ref(false)
// 后台批量收集锁定：批量解析收集过文件后不自动切换到文件列表视图（静默后台下载），
// 用户点"返回"/新搜索/导航切换时解锁
const batchFileCollected = ref(false)

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
// 博主内容流（点开博主自动解析，详情页下方展示推文卡片）
const twUserFeed = ref([])
const twUserFeedLoading = ref(false)
const twUserFeedCursor = ref('')
const twUserFeedHasMore = ref(false)
const twUserFeedUserId = ref('')   // 当前请求的博主 id（防快速切换博主时旧数据串台）
// X 本地搜索：在已缓存内容（浏览模式信息流/关注列表/我的分类）中过滤
const twLocalSearch = ref('')
// 本地搜索的推文结果
const twSearchTweets = ref([])
// 搜索结果视图（从搜索态返回时恢复原视图）
const twSearchSnapshot = ref(null)
// 用户页资料统计（twitter_user_feed 无 cursor 首包的 profile 字段：媒体/推文/粉丝/关注数）
const twUserProfileStats = ref(null)
// 用户页「加载全部」（load_all 模式：后端一次翻完所有页，前端只做防抖与进度显示）
const twUserLoadAllRunning = ref(false)
const twUserLoadAllProgress = reactive({ loaded: 0, total_media: 0 })
// 用户页 HTML 相册导出（twitter_export_html：拉全部内容生成/增量更新「时间线.html」）
const twExportRunning = ref(false)
const twExportProgress = reactive({ phase: '', done: 0 })
// 浏览模式「加载全部」（前端循环逐批发 twitter_browse 命令，1.2s 间隔防限流，可中止）
const twBrowseLoadAllRunning = ref(false)
const twBrowseLoadAllCount = ref(0)
let twBrowseLoadAllAbort = false

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
// xHamster 浏览视图（类 App 布局：底部 Tab 首页/分类/短视频/消息/我的 + 顶部搜索）
// ============================
// xhView: ''=空态 | 'home'=首页 | 'categories'=分类 | 'category'=分类列表 | 'shorts'=短视频
//         | 'notifications'=消息 | 'my'=我的 | 'detail'=视频详情 | 'user'=用户主页
const xhView = ref('')
const xhTab = ref('home')             // 底部 Tab 当前页（home/categories/shorts/notifications/my）
// 首页（newest=新着 / views=最多播放 / rating=最高评分）
const xhHomeSort = ref('newest')
const xhHomeItems = ref([])
const xhHomeLoading = ref(false)
const xhHomeError = ref('')
const xhHomePage = ref(1)
const xhHomeHasMore = ref(false)
// 分类（热门 + 分组）
const xhCatsLoading = ref(false)
const xhCatsTrending = ref([])
const xhCatsGroups = ref([])
const xhCatsError = ref('')
// 分类列表（点某个分类进入）
const xhCatSlug = ref('')
const xhCatName = ref('')
const xhCatItems = ref([])
const xhCatLoading = ref(false)
const xhCatError = ref('')
const xhCatPage = ref(1)
const xhCatHasMore = ref(false)
// 短视频
const xhShortsItems = ref([])
const xhShortsLoading = ref(false)
const xhShortsError = ref('')
const xhShortsPage = ref(1)
const xhShortsHasMore = ref(false)
// 消息中心
const xhNotif = ref(null)             // {logged_in, counts, message}
const xhNotifLoading = ref(false)
// 我的（登录用户的视频/收藏）
const xhMyTab = ref('favorites')      // 我的关注：favorites=关注用户列表（我的视频已移除）
const xhMyItems = ref([])
const xhMyLoading = ref(false)
const xhMyError = ref('')
const xhMyPage = ref(1)
const xhMyHasMore = ref(false)
const xhMyUsername = ref('')
// 视频详情（含播放直链/tags/评论）
const xhDetail = ref(null)
const xhDetailLoading = ref(false)
const xhDetailError = ref('')
const xhComments = ref([])
const xhCommentCount = ref(0)
const xhDetailFrom = ref('home')       // 详情返回目标视图（home/category/my/user）
// 用户主页
const xhUser = ref('')                 // 用户名
const xhUserItems = ref([])
const xhUserLoading = ref(false)
const xhUserError = ref('')
const xhUserPage = ref(1)
const xhUserHasMore = ref(false)
const xhUserTab = ref('videos')
const xhUserProfile = ref(null)
const xhSubscribeLoading = ref(false)
const xhCommentSending = ref(false)
// 批量下载（浏览区勾选多个视频 URL）
const xhBatchRunning = ref(false)
const xhBatchProgress = reactive({ done: 0, total: 0, message: '' })

// ============================
// Hanime1 主页/详情/用户中心（H站，与 Iwara 模式一致）
// ============================
// haView: ''=普通搜索 | 'home'=主页分区 | 'user'=用户中心 | 'detail'=视频详情
const haView = ref('')
const hanimeUser = ref('')
const hanimeLoginLoading = ref(false)
// Pixiv 登录状态（P站：Refresh Token 登录 + App API 全功能）
const pixivUser = ref('')
const pixivLoginLoading = ref(false)
// Pixiv 全功能面板状态（PixivPanel 透传）：view=''/user/detail，userId 用于评论区"删除自己的发言"
const pixivState = reactive({
  view: '',           // ''=列表（搜索/feed） | 'user'=用户主页 | 'detail'=作品详情
  detailFrom: '',     // 详情/用户页进入来源（back 时回上一层）
  userId: '',         // 登录用户 id
  userPage: null,     // 用户主页 {user, profile, illusts, manga, novels}
  userLoading: false,
  detail: null,       // 作品详情 {kind, item_id, detail, raw, comments, total_comments}
  detailLoading: false,
  related: null,      // 相关作品 {kind, item_id, items}（详情页点击后懒加载）
  myTags: [],         // 常用标签（本地频次统计）
  trending: [],       // 热门标签（trending tags）
  notifications: null, // 消息/提醒 {items, unread, message}
  bookmarkTags: null, // 书签收藏标签 {content, tags, message}
  uploadResult: null, // 发布作品结果 {ok, message}
})
// 功能栏当前高亮 feed（home/illust/manga/novel/follow_*/bookmark/userlist_*）
const pixivActiveFeed = ref('')
// Pixiv 批量下载（多批次：每个用户一个后台任务）进度
const pixivBatchRunning = ref(false)
const pixivBatchProgress = reactive({ done: 0, total: 0, message: '' })
// 列表翻页上下文：feed 翻页记住 kind/page（搜索模式走 doSearch，不走这里）
const pixivListCtx = reactive({ mode: '', kind: 'home', content: 'illust', restrict: 'public', allow_r18: true, user_id: '', umode: 'following', feedKind: '' })
// Pixiv 各 feed 数据快照（切换秒显，后台刷新后替换）：feed_kind → {items,page,total_pages,total_results}
const pixivFeedCache = new Map()
// 缓存优先恢复：切到已有快照的 feed 时立即显示旧数据（不转圈），刷新结果到达后整体替换
function pixivRestoreCache(feedKind) {
  const snap = pixivFeedCache.get(feedKind)
  if (!snap || !snap.items?.length) return false
  pixivState.view = ''
  searchResults.value = snap.items
  searchPage.value = snap.page || 1
  searchTotalPages.value = snap.total_pages || 0
  searchTotalResults.value = snap.total_results || 0
  searching.value = false
  return true
}
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
const asmrRelated = ref([])           // 相似作品（同社团随详情立即下发 + tags 后台补齐合并）
const asmrRelatedPending = ref(false) // tags 推荐后台补齐进行中（空态提示用）
const asmrRecommend = ref([])         // 收藏页推荐流（收藏 tags 相同标签作品）
const asmrDetailLoading = ref(false)
// 批量下载
const asmrBatchRunning = ref(false)
const asmrBatchProgress = reactive({ done: 0, total: 0, message: '' })

// ============================
// 识图（反向图片搜索）状态：拖拽图片 → 多网站并发查询 → 全部返回后展示
// ============================
const reverseActive = ref(false)      // 识图视图激活（占用右侧内容区）
const reverseRunning = ref(false)      // 搜索进行中
const reverseSites = ref([])           // [{key,name,status:running|done|failed,results,url,error}]
const reversePaste = ref('')           // 左侧粘贴板内容（后端 cache/reverse_paste.txt 持久化）
const reverseSession = ref('')         // 当前搜索会话 id（用于丢弃上一轮的过期回传）
const reverseMerged = ref([])          // 跨站去重 + 相似度排序后的聚合结果
const reverseCached = ref(false)       // 本次结果是否来自本地缓存（未消耗站点配额）

// ============================
// 通用 webview OAuth 三站（xhamster/pornhub/xvideos）状态
// AP1 阶段：登录用户名显示 + webview 弹窗状态 + OAuth 配置
// ============================
const xhamsterUser = ref('')
const fc2User = ref('')
const pornhubUser = ref('')
const xvideosUser = ref('')
const javdbUser = ref('')
const googleUser = ref('')      // 谷歌邮箱（OAuth 授权共用凭据源）
const oreno3dUser = ref('')    // Oreno3D 会话状态（账号密码 + cookie 互相验证）
const erommdtubeUser = ref('') // EroMMDTube 会话状态（账号密码 + cookie 互相验证）
// O3D / E站 凭据回填（login_info 提取的保存账号密码，传给 LeftPanel 表单）
const oreno3dCred = ref({ email: '', password: '' })
const erommdtubeCred = ref({ email: '', password: '' })
// 全站登录套件凭据回填（login_info 提取各站保存的账号密码，传给 LeftPanel 表单预填）
const siteCreds = ref({})
// JavDB 视频详情（封面/预览图/磁力列表）+ 批量下载进度
const javdbDetail = ref(null)
const javdbDetailLoading = ref(false)
const javdbBatchRunning = ref(false)
const javdbBatchProgress = reactive({ done: 0, total: 0 })
// JavDB 列表上下文（首页最新影片 / 演员主页 / 通用列表页）：翻页走对应命令而非搜索命令
const javdbListCtx = reactive({
  mode: '',   // ''（普通搜索）/ 'home' / 'actor' / 'url'
  url: '',    // actor 模式的演员页链接 / url 模式的列表页链接
  label: '',  // url 模式的列表标题（翻页时透传）
})
// JavDB 搜索类型（影片/演员/系列/片商/导演/番号/标签）+ 标签词库 + 热搜 + 目录导航
const javdbSearchField = ref('all')     // f= 参数：all/actor/series/maker/director/coded/tag
const javdbTagsVocab = ref(null)        // 5 模式标签词表（后端 javdb_tags_vocab 下发）
const javdbTagsMode = ref('censored')   // 标签页当前模式 key（有码/无码/欧美/FC2/动漫）
const javdbHotKeywords = ref([])        // 热搜关键词（后端离线词表）
const javdbDir = reactive({ kind: '', label: '', items: [], page: 1, hasMore: false, params: '' })
// 第五行：当前 tags 模式的主要推荐作品（横滚条）+ 待匹配的加载标记
const javdbModeRecommend = reactive({ mode: '', label: '', items: [] })
const javdbRecommendPending = reactive({ mode: '', label: '' })
// webview 登录弹窗（共用 WebviewLoginModal 组件）
const wvLogin = reactive({
  visible: false,
  site: '',                   // xhamster / pornhub / xvideos / javdb / exhentai / google / oreno3d
  loginUrl: '',
  homeUrl: '',
  partition: 'persist:twitter',
  successPatterns: [],
  captchaPatterns: [],
  credentials: null,          // 登录页自动预填账号（javdb 邮箱密码登录）
  manualConfirm: false,       // 手动确认模式（EX/javdb：底部取消+确定按钮，用户点确定才抓 cookie）
  confirmHint: undefined,     // 手动确认栏提示文案（undefined=用组件默认）
  confirmText: undefined,     // 手动确认按钮文案（undefined=用组件默认）
  autoGrabPattern: null,      // 自动抓取模式（javdb 已改为手动确认模式，不再使用）
  codeRegex: null,            // OAuth 授权码提取（pixiv://account/login?code=xxx 拦截）
  watchLoginUrl: false,       // 登录 URL 动态更新模式（后端生成 OAuth URL 后推给弹窗重载）
})

// 谷歌邮箱凭据表单（设置区"登录谷歌邮箱"：保存账号密码 + 内置浏览器登录）
const googleEmail = ref('')
// 谷歌邮箱多账号列表（login_info 提取，设置区展示/复制/切换/删除）
const googleAccounts = ref([])
const googlePassword = ref('')


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
const batchFolderContext = ref('ex')        // 母文件夹弹窗上下文（ex / javdb：确认后走对应批量逻辑）
const pixivNovelFmtOverride = ref('')      // Pixiv 小说下载格式一次性覆盖（txt/docx，详情下载按钮设置）


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

// ============================
// f4：后端事件处理器注册表（原 handlePythonEvent 193 case 逐字迁入各函数；
// 顶层 break→return，嵌套循环/switch 内的 break 语义不变；多标签 case 为多键映射）
// ============================
function _pyEvt_ready(event) {
backendReady.value = true
      backendError.value = ''
      addLog('系统', '后端已就绪')
      requestSettings()
      requestHistory()
      requestTasks()
      // P3 设置功能：监听主进程触发的快捷键事件
      setupShortcutTriggeredListener()
      // 3 连 Alt 唤出悬浮面板
      setupTripleAltListener()
      // 标题栏最大化状态：切换圆角贴边样式
      if (window.api && window.api.onWinMaxState) {
        window.api.onWinMaxState((maxed) => { winMaxed.value = !!maxed })
      }
      // 关闭弹窗勾选"记住我的选择"后，主进程直接写 settings.json → 同步本地 + 后端缓存
      setupCloseActionListener()
      // 加载搜索历史与本地收藏
      if (window.api) {
        window.api.sendCommand({ cmd: 'get_search_history' })
        window.api.sendCommand({ cmd: 'get_favorites' })
        // 拉取全部站点登录信息（账号卡片：用户名/Cookie/账号档案）
        window.api.sendCommand({ cmd: 'get_login_info' })
        // 各站登录状态检查 + 标签加载延后 2.5 秒批量发送——启动首秒让位给
        // 首屏命令（设置/任务/当前站点首页），避免十几个网络检查把命令队列占满
        //（每个检查 0.5~2 秒网络串行，曾导致"打开很卡"）
        setTimeout(() => {
          if (!window.api) return
          // 启动检查全部后台静默（结果只刷新账号卡片，不弹任何提示——用户点了
          // 对应站点才发现登录失效时再提示）
          // exhentai/twitter/xhamster/javdb 的启动检查后端已后台执行并推送结果，不再重复发
          window.api.sendCommand({ cmd: 'pornhub_check_login', silent: true })
          window.api.sendCommand({ cmd: 'xvideos_check_login', silent: true })
          window.api.sendCommand({ cmd: 'google_check_login', silent: true })
          window.api.sendCommand({ cmd: 'oreno3d_check_login', silent: true })
          window.api.sendCommand({ cmd: 'erommdtube_check_login', silent: true })
          window.api.sendCommand({ cmd: 'twitter_get_follow_tags' })
          window.api.sendCommand({ cmd: 'exhentai_get_hidden_tags' })
        }, 2500)
      }
}

function _pyEvt_inspect_start(event) {
if (exBatchDownloading.value || exBatchPending.value > 0) {
        addLog('解析', `后台解析: ${event.url}`)
        return
      }
      clearTimeout(inspectWatchdog)  // 后端已响应，解除点击时的看门狗
      inspecting.value = true
      fileList.value = []
      inspectProgress.current = 0
      inspectProgress.total = 0
      addLog('解析', `开始解析: ${event.url}`)
      // 重挂看门狗：后端确认接收后仍可能在解析中途静默（hang/崩溃），
      // 无保护会永久转圈；progress 事件会持续刷新
      armInspectWatchdog(300000)
}

function _pyEvt_inspect_progress(event) {
inspectProgress.current = event.current
      inspectProgress.total = event.total
      inspectProgress.filename = event.filename || ''
      armInspectWatchdog(300000)
}

function _pyEvt_inspect_complete(event) {
clearTimeout(inspectWatchdog)
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
          selected: item.status === 'ok' && !item.is_downloaded,
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
            addLog('系统', `批量解析全部完成，共收集 ${fileList.value.length} 个文件`)
            finishExBatch(exBatchCancelled.value)
          }
        }
      } else {
        fileList.value = (event.items || []).map((item) => ({
          ...item,
          selected: item.status === 'ok' && !item.is_downloaded,
          size_text: formatSize(item.size),
          file_type: getFileType(item.filename),
        }))
        // 非图片/视频文件加载系统图标作为缩略图占位
        applyFileIcons()
        addLog('解析', `完成: ${event.album_name} (${fileList.value.length} 个文件)`)
        // 增量提示：已下载过的默认不勾选，只勾选截断日期之后的新内容
        const dlCount = fileList.value.filter(it => it.is_downloaded).length
        if (dlCount) {
          addLog('解析', `增量更新: 已下载过 ${dlCount} 个（默认不勾选），新内容 ${fileList.value.length - dlCount} 个`)
        }
      }
}

function _pyEvt_inspect_error(event) {
clearTimeout(inspectWatchdog)
      inspecting.value = false
      addLog('错误', event.message)
      // 后台批量解析中某个画廊失败：同样递减计数，避免批量状态卡死
      if (exBatchDownloading.value && exBatchPending.value > 0) {
        exBatchPending.value -= 1
        message.error(`批量解析中一个画廊失败: ${event.message}`)
        if (exBatchPending.value === 0) {
          if (exBatchCancelled.value) {
            addLog('系统', '批量解析已取消（部分画廊解析失败）')
          }
          finishExBatch(exBatchCancelled.value)
        }
      }
}

function _pyEvt_search_start(event) {
searching.value = true
      armSearchWatchdog()
}

function _pyEvt_search_result(event) {
{
      // Pixiv 迟到过滤——必须先于任何状态/列表写入：插画/小说关注更新等后台任务
      // 交错到达，feed 与当前所选不符 → 整条丢弃。此前过滤排在列表替换之后，
      // "丢弃"时列表已被旧数据覆盖（点A出B 未绝根的原因）。补页静默丢，首发记日志。
      if (event.site === 'pixiv' && pixivListCtx.feedKind && event.feed_kind
          && event.feed_kind !== pixivListCtx.feedKind) {
        if (!event.append) addLog('P站', '已丢弃迟到的旧列表数据（你已切换到其他内容）')
        return
      }
      clearTimeout(searchWatchdog)
      searching.value = false
      searchHasMore.value = !!event.has_more
      searchPage.value = event.page
      searchTotalPages.value = event.total_pages || 0
      searchTotalResults.value = event.total_results || 0
      // Pixiv 关注更新的后台补页（append）：只追加新条目去重，不替换列表
      //（避免重置勾选/滚动位置），也不拽视图、不刷日志
      if (event.site === 'pixiv' && event.append && pixivActiveFeed.value === event.feed_kind) {
        const seen = new Set(searchResults.value.map(w => String(w.illust_id || w.novel_id || '')))
        searchResults.value = [...searchResults.value, ...(event.items || []).filter(w => !seen.has(String(w.illust_id || w.novel_id || '')))]
        searchTotalResults.value = searchResults.value.length
        const snap = pixivFeedCache.get(event.feed_kind)
        if (snap) pixivFeedCache.set(event.feed_kind, { ...snap, items: searchResults.value })
        return
      }
      // 翻页模式：每页替换结果（统一页码逻辑）
      searchResults.value = event.items || []
      // Pixiv：列表数据到达 → 退出用户页/详情视图回到列表，写 feed 快照缓存
      if (event.site === 'pixiv') {
        if (event.feed_kind && !event.append) {
          pixivFeedCache.set(event.feed_kind, {
            items: event.items || [], page: event.page, total_pages: event.total_pages,
            total_results: event.total_results,
          })
        }
        const keepDetail = pixivState.view === 'detail'
          && (pixivState.detailLoading || (event.page || 1) > 1)
        if (!keepDetail) {
          pixivState.view = ''
          if (event.feed_kind) pixivActiveFeed.value = event.feed_kind
          else if (!pixivListCtx.mode) pixivActiveFeed.value = ''
        }
      }
      // EX 我的收藏模式（翻页走收藏命令而非搜索命令）
      exFavMode.value = event.query === '__ex_favorites__'
      exPopularMode.value = event.feed_kind === 'exhentai_popular'
      const displayQuery = exFavMode.value ? '我的收藏' : event.query
      addLog('搜索', `「${displayQuery}」第 ${event.page}${event.total_pages ? `/${event.total_pages}` : ''} 页，${(event.items || []).length} 个结果`)
      // 持续自动翻译模式：搜索结果到达后自动翻译一次
      maybeAutoTranslateAfterSearch()
      return
    }
}

function _pyEvt_search_error(event) {
if (event.site === 'pixiv' && pixivListCtx.feedKind && event.feed_kind
          && event.feed_kind !== pixivListCtx.feedKind) {
        addLog('P站', `后台任务失败（已忽略）：${event.message || ''}`)
        return
      }
      clearTimeout(searchWatchdog)
      searching.value = false
      addLog('错误', event.message)
}

function _pyEvt_download_start(event) {
downloading.value = true
      addLog('下载', `开始下载 ${event.total_files} 个文件`)
}

function _pyEvt_file_start(event) {
downloadProgress[event.filename] = {
        completed: 0,
        status: 'downloading',
        size: event.size,
      }
}

function _pyEvt_file_progress(event) {
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
          // 必须按文件名精确匹配——此前按"第一个 downloading 状态"匹配，
          // 多文件并发下载时进度互相覆盖（进度条波动/倒退的根源）
          const file = task.files.find(f => f.filename === event.filename)
          if (file) {
            file.completed = event.completed
            file.speed = event.speed || 0
          }
        }
      }
      updateFloatData()
}

function _pyEvt_file_complete(event) {
if (downloadProgress[event.filename]) {
        downloadProgress[event.filename].status = event.success ? 'completed' : 'failed'
        downloadProgress[event.filename].completed = 100
      }
      // 下载管理（迅雷式详情）：记录文件完成/失败时间 + 清掉实时速度
      if (event.task_id) {
        const t = downloadTasks.value.find(t => t.id === event.task_id)
        if (t) {
          const f = (t.files || []).find(f => f.filename === event.filename && f.status !== 'completed')
            || (t.files || []).find(f => f.filename === event.filename)
          if (f) {
            f.finished_at = Date.now()
            f.speed = 0
            if (event.success) { f.status = 'completed'; f.completed = 100 }
          }
        }
      }
      addLog(
        event.success ? '完成' : '失败',
        `${event.filename} ${event.success ? '下载完成' : '下载失败'}`
      )
}

function _pyEvt_task_paused(event) {
message.info(event.message || '任务已暂停')
      addLog('下载', event.message || '任务已暂停')
}

function _pyEvt_task_retry(event) {
if (event.ok) {
        message.success(event.message || '重试已开始')
      } else {
        message.warning(event.message || '无法重试')
      }
      addLog('下载', event.message || '')
      requestTasks()
}

function _pyEvt_download_complete(event) {
downloading.value = false
      addLog('下载', `全部完成 (用时 ${event.execution_time}秒)`)
}

function _pyEvt_download_error(event) {
downloading.value = false
      addLog('错误', event.message)
}

function _pyEvt_history(event) {
history.value = event.items || []
}

function _pyEvt_settings(event) {
Object.assign(settings, event.settings || {})
      // 界面模式同步回 localStorage：后端是权威值，写回后下次启动首帧即正确（不闪里世界）
      try { localStorage.setItem('mh_ui_mode_hot', settings.ui_mode_hot ? '1' : '0') } catch (e) { /* 隐私模式 */ }
      // 应用悬浮窗可见性记忆：只有显式 true 才创建/显示（默认关——避免旁人看到
      // 下载历史；旧 settings.json 缺该键时也不开，避免启动一闪而过）
      floatVisible.value = settings.float_visible === true
      if (window.api && window.api.setFloatVisible) {
        window.api.setFloatVisible(floatVisible.value)
      }
      // 全局自动翻译：只恢复目标语言；开关每次启动默认关闭（不持久化，避免"默认自动开启"）
      if (settings.auto_translate_to) autoTranslateTo.value = settings.auto_translate_to
      autoTranslateMode.value = false
      // P3：设置加载完成后，把已保存的快捷键注册到主进程 + 应用不息屏状态
      syncP3SettingsToMain()
}

function _pyEvt_tasks_snapshot(event) {
downloadTasks.value = event.tasks || []
      updateFloatData()
}

function _pyEvt_pa_artist_dl_progress(event) {
addLog('PA', `画师「${event.artist || ''}」后台解析中: ${event.current || 0}/${event.total || 0} 个帖子`)
}

function _pyEvt_pa_artist_dl_done(event) {
message.success(`画师「${event.artist || ''}」解析完成，${event.files || 0} 个文件已加入后台下载`)
      addLog('PA', `画师「${event.artist || ''}」下载任务已提交（${event.files || 0} 个文件）`)
      requestTasks()
}

function _pyEvt_pa_artist_dl_error(event) {
message.error(event.message || '解析画师内容失败')
      addLog('PA', `画师下载失败: ${event.message || '未知错误'}`)
}

function _pyEvt_media_proxy_ready(event) {
mediaProxyPort.value = event.port || 0
      setAsmrProxyPort(event.port || 0)
}

function _pyEvt_media_url_resolved(event) {
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
}

function _pyEvt_thumbnails_cached(event) {
applyCachedThumbnails(event.items || [])
}

function _pyEvt_cache_cleared(event) {
if (event.cleared) {
        addLog('系统', `缓存已清除: ${event.cache_dir}`)
        message.success(`缓存已清除（缩略图 + 相册信息）：${event.cache_dir}`)
      } else {
        addLog('系统', `缓存目录不存在，无需清除: ${event.cache_dir}`)
        message.info('缓存目录不存在，无需清除')
      }
}

function _pyEvt_log(event) {
addLog(event.type, event.message)
}

function _pyEvt_backend_error(event) {
backendReady.value = false
      backendError.value = event.message || '后端启动失败'
      message.error(backendError.value)
      addLog('错误', backendError.value)
}

function _pyEvt_pawchive_login_result(event) {
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
}

function _pyEvt_exhentai_login_result(event) {
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
}

function _pyEvt_twitter_login_result(event) {
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
}

function _pyEvt_xhamster_home_loading(event) {
xhHomeLoading.value = !!event.loading
}

function _pyEvt_xhamster_home(event) {
xhHomeLoading.value = false
      xhHomeError.value = event.error || ''
      if (event.error) return
      if ((event.page || 1) <= 1) xhHomeItems.value = event.items || []
      else xhHomeItems.value.push(...(event.items || []))
      xhHomePage.value = event.page || 1
      xhHomeHasMore.value = !!event.has_more
      if (event.sort) xhHomeSort.value = event.sort
      if (!['detail', 'user', 'category'].includes(xhView.value)) {
        xhView.value = 'home'
        xhTab.value = 'home'
      }
}

function _pyEvt_xhamster_categories_loading(event) {
xhCatsLoading.value = !!event.loading
}

function _pyEvt_xhamster_categories(event) {
xhCatsLoading.value = false
      xhCatsError.value = event.error || ''
      if (event.error) return
      xhCatsTrending.value = event.trending || []
      xhCatsGroups.value = event.groups || []
}

function _pyEvt_xhamster_category_loading(event) {
xhCatLoading.value = !!event.loading
}

function _pyEvt_xhamster_category(event) {
xhCatLoading.value = false
      xhCatError.value = event.error || ''
      if (event.error) return
      if ((event.page || 1) <= 1) xhCatItems.value = event.items || []
      else xhCatItems.value.push(...(event.items || []))
      xhCatPage.value = event.page || 1
      xhCatHasMore.value = !!event.has_more
}

function _pyEvt_xhamster_shorts_loading(event) {
xhShortsLoading.value = !!event.loading
}

function _pyEvt_xhamster_shorts(event) {
xhShortsLoading.value = false
      xhShortsError.value = event.error || ''
      if (event.error) return
      if ((event.page || 1) <= 1) xhShortsItems.value = event.items || []
      else xhShortsItems.value.push(...(event.items || []))
      xhShortsPage.value = event.page || 1
      xhShortsHasMore.value = !!event.has_more
}

function _pyEvt_xhamster_detail_loading(event) {
xhDetailLoading.value = !!event.loading
}

function _pyEvt_xhamster_video_detail(event) {
xhDetailLoading.value = false
      xhDetailError.value = event.error || ''
      if (event.error) {
        xhDetail.value = null
        return
      }
      xhDetail.value = event.video || null
      xhComments.value = event.comments || []
      xhCommentCount.value = event.comment_count || 0
      if (event.video) {
if (!xhView.value) detailFromSearch.value = 'xhamster'
                navPushView('xhamster', 'detail')
        xhView.value = 'detail'
      }
}

function _pyEvt_xhamster_notifications_loading(event) {
xhNotifLoading.value = !!event.loading
}

function _pyEvt_xhamster_notifications(event) {
xhNotifLoading.value = false
      xhNotif.value = {
        logged_in: !!event.logged_in,
        counts: event.counts || {},
        message: event.message || '',
      }
}

function _pyEvt_xhamster_my_loading(event) {
xhMyLoading.value = !!event.loading
}

function _pyEvt_xhamster_my(event) {
xhMyLoading.value = false
      if (event.logged_in && event.username) xhMyUsername.value = event.username
      // 未登录 / 过期才当错误；空列表的提示文案只展示、仍写入 items
      const myLoggedOut = event.logged_in === false
      xhMyError.value = myLoggedOut ? (event.message || '未登录') : ''
      if (myLoggedOut) {
        xhMyItems.value = []
        xhMyHasMore.value = false
        return
      }
      if ((event.page || 1) <= 1) xhMyItems.value = event.items || []
      else xhMyItems.value.push(...(event.items || []))
      xhMyPage.value = event.page || 1
      xhMyHasMore.value = !!event.has_more
      if (event.tab) xhMyTab.value = event.tab
}

function _pyEvt_xhamster_user_loading(event) {
xhUserLoading.value = !!event.loading
}

function _pyEvt_xhamster_user_videos(event) {
xhUserLoading.value = false
      xhUserError.value = event.error || ''
      if (event.username) xhUser.value = event.username
      if (event.profile) xhUserProfile.value = event.profile
      if (event.tab) xhUserTab.value = event.tab
      if (event.keep_items) return
      if (event.error) return
      if ((event.page || 1) <= 1) xhUserItems.value = event.items || []
      else xhUserItems.value.push(...(event.items || []))
      xhUserPage.value = event.page || 1
      xhUserHasMore.value = !!event.has_more
}

function _pyEvt_xhamster_subscribe_result(event) {
xhSubscribeLoading.value = false
      if (event.message) {
        if (event.ok) message.success(event.message)
        else message.warning(event.message)
      }
      if (xhDetail.value && event.user_id && String(xhDetail.value.author_id || '') === String(event.user_id || '')) {
        xhDetail.value.subscribed = !!event.subscribed
      }
      if (xhUserProfile.value && (event.username === xhUser.value || String(xhUserProfile.value.id || '') === String(event.user_id || ''))) {
        xhUserProfile.value.subscribed = !!event.subscribed
      }
}

function _pyEvt_xhamster_comment_result(event) {
xhCommentSending.value = false
      if (event.ok) message.success(event.message || '评论已发布')
      else message.warning(event.message || '评论失败')
}

function _pyEvt_xhamster_batch_progress(event) {
xhBatchProgress.done = event.done || 0
      xhBatchProgress.total = event.total || 0
      xhBatchProgress.message = event.message || ''
}

function _pyEvt_xhamster_batch_done(event) {
xhBatchRunning.value = false
      message.info(event.message || `批量下载完成：${event.done || 0}/${event.total || 0}`)
      addLog('下载', `xHamster 批量下载完成: ${event.done || 0}/${event.total || 0}，失败 ${event.failed || 0}`)
}

function _pyEvt_iwara_login_result(event) {
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
}

function _pyEvt_iwara_site_changed(event) {
iwSite.value = event.site || 'iwara'
      message.info(event.message || '站点已切换')
      // 切换 IW/AI 站后重新加载主页最近更新（详情页属于旧站点，一并返回）
      iwHomeItems.value = []
      iwHomePage.value = 1
      iwHomeMode.value = ''
      iwDetail.value = null
      iwComments.value = []
      handleIwHome(1)
}

function _pyEvt_iwara_home(event) {
iwHomeLoading.value = false
      iwHomeError.value = event.error || ''
      if (event.error) return
      // 强校验：丢弃来自错误站点的数据（防止未切换 AI 站时显示 AI 站内容）
      if (event.site && event.site !== iwSite.value) {
        console.warn('[iwara_home] 丢弃站点不匹配的数据', { expected: iwSite.value, got: event.site })
        addLog('系统', `丢弃 IW/${iwSite.value === 'ai' ? 'AI' : '普通'}站不匹配的旧数据`)
        return
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
      maybeAutoTranslateAfterSearch()
}

function _pyEvt_iwara_home_loading(event) {
iwHomeLoading.value = !!event.loading
}

function _pyEvt_iwara_follow_list(event) {
iwFollowLoading.value = false
      iwFollowError.value = event.error || ''
      if (event.error) return
      if (event.site && event.site !== iwSite.value) {
        console.warn('[iwara_follow_list] 丢弃站点不匹配数据', { expected: iwSite.value, got: event.site })
        return
      }
      if ((event.page || 1) <= 1) {
        iwFollowItems.value = event.items || []
      } else {
        iwFollowItems.value.push(...(event.items || []))
      }
      iwFollowPage.value = event.page || 1
      iwFollowHasMore.value = !!event.has_more
      iwFollowTotal.value = event.total || 0
}

function _pyEvt_iwara_follow_loading(event) {
iwFollowLoading.value = !!event.loading
}

function _pyEvt_iwara_friend_list(event) {
iwFriendLoading.value = false
      iwFriendError.value = event.error || ''
      if (event.error) return
      if (event.site && event.site !== iwSite.value) {
        console.warn('[iwara_friend_list] 丢弃站点不匹配数据', { expected: iwSite.value, got: event.site })
        return
      }
      if ((event.page || 1) <= 1) {
        iwFriendItems.value = event.items || []
      } else {
        iwFriendItems.value.push(...(event.items || []))
      }
      iwFriendPage.value = event.page || 1
      iwFriendHasMore.value = !!event.has_more
      iwFriendTotal.value = event.total || 0
}

function _pyEvt_iwara_friend_loading(event) {
iwFriendLoading.value = !!event.loading
}

function _pyEvt_iwara_user_profile(event) {
{
      // 后台补齐的关注/好友个人说明与缺失头像：按 username 匹配渐进更新
      const patchUser = (u) => {
        if (u.username !== event.username) return
        if (event.bio) u.bio = event.bio
        if (event.avatar && !u.avatar) {
          u.avatar = event.avatar
          u.thumbnail = event.avatar
        }
      }
      iwFollowItems.value.forEach(patchUser)
      iwFriendItems.value.forEach(patchUser)
      return
    }
}

function _pyEvt_iwara_follow_result(event) {
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
}

function _pyEvt_iwara_video_detail(event) {
iwDetailLoading.value = false
      if (event.error || !event.video) {
        message.error(event.error || '获取视频详情失败')
        return
      }
      // 强校验：丢弃来自错误站点的视频详情
      if (event.site && event.site !== iwSite.value) {
        console.warn('[iwara_video_detail] 丢弃站点不匹配数据', { expected: iwSite.value, got: event.site })
        addLog('系统', `丢弃 IW/${iwSite.value === 'ai' ? 'AI' : '普通'}站不匹配的视频详情`)
        return
      }
      iwDetail.value = event.video
      iwComments.value = event.comments || []
      iwCommentsPage.value = 1
      iwCommentsHasMore.value = (event.comment_count || 0) > (iwComments.value.length)
if (!iwView.value) detailFromSearch.value = 'iwara'
            navPushView('iwara', 'detail')
      iwView.value = 'detail'
}

function _pyEvt_iwara_detail_loading(event) {
iwDetailLoading.value = !!event.loading
}

function _pyEvt_iwara_comments(event) {
if (event.error) {
        message.error(event.error)
        return
      }
      iwComments.value.push(...(event.comments || []))
      iwCommentsPage.value = event.page || 1
      iwCommentsHasMore.value = !!event.has_more
}

function _pyEvt_iwara_batch_progress(event) {
iwBatchRunning.value = true
      iwBatchProgress.done = event.done || 0
      iwBatchProgress.total = event.total || 0
      iwBatchProgress.message = event.message || ''
}

function _pyEvt_iwara_batch_done(event) {
iwBatchRunning.value = false
      iwBatchProgress.done = event.done || 0
      iwBatchProgress.total = event.total || 0
      iwBatchProgress.message = ''
      if (event.message) {
        message.info(event.message)
        addLog('下载', event.message)
      }
}

function _pyEvt_hanime_login_result(event) {
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
}

function _pyEvt_hanime_proxy_set(event) {
if ((event.proxy || '') !== settings.hanime_proxy) {
        settings.hanime_proxy = event.proxy || ''
        saveSettings()
      }
}

function _pyEvt_pixiv_login_result(event) {
pixivLoginLoading.value = false
      if (event.logout) {
        pixivUser.value = ''
        if (!event.silent) message.info(event.message || '已退出 Pixiv 登录')
        addLog('系统', 'Pixiv 已退出登录')
      } else if (event.success) {
        pixivUser.value = event.username || '已登录'
        if (event.user_id) pixivState.userId = String(event.user_id)
        if (!event.silent) message.success(event.message || 'Pixiv 登录成功')
        addLog('系统', `Pixiv 登录成功: ${pixivUser.value}`)
      } else {
        if (event.network_issue) {
          // 网络问题：保留当前登录显示
          if (!event.silent) message.warning(event.message || 'Pixiv 连接失败（网络问题），登录状态已保留')
          addLog('系统', `Pixiv 连接失败（网络）: ${event.message || ''}`)
        } else {
          pixivUser.value = ''
          if (!event.silent) message.error(event.message || 'Pixiv 未登录')
          addLog('系统', `Pixiv 未登录: ${event.message || ''}`)
        }
      }
}

function _pyEvt_pixiv_oauth_url(event) {
if (event.url && wvLogin.site === 'pixiv' && wvLogin.visible) {
        wvLogin.loginUrl = event.url
        addLog('系统', 'Pixiv 登录页已生成（请在弹窗内完成登录与人机验证）')
      }
}

function _pyEvt_pixiv_user_loading(event) {
pixivState.userLoading = !!event.loading
}

function _pyEvt_pixiv_user_result(event) {
{
        const wasUserLoading = pixivState.userLoading
        pixivState.userLoading = false
        if (event.error) {
          message.error(event.error)
          addLog('P站', event.error)
          return
        }
        if (event.page > 1 && pixivState.userPage) {
          // 追加模式：只合并当前 tab 类型（不覆盖 user/profile）
          const up = pixivState.userPage
          const tk = event.tab
          if (tk && Array.isArray(event.items)) {
            const seen = new Set((up[tk] || []).map(w => String(w.illust_id || w.novel_id || '')))
            up[tk] = [...(up[tk] || []), ...event.items.filter(w => !seen.has(String(w.illust_id || w.novel_id || '')))]
            if (up.has_more) up.has_more = { ...(up.has_more || {}), [tk]: !!event.has_more }
            if (up.page) up.page = { ...(up.page || {}), [tk]: event.page }
          }
        } else {
          pixivState.userPage = event
          // 首屏三类型逐个到达：迟到的 page=1 事件不得把用户从详情页拽走
          //（用户页点开作品"一闪而过就没内容"的真凶）
          if (wasUserLoading || pixivState.view === 'user') pixivState.view = 'user'
        }
      }
}

function _pyEvt_pixiv_detail_loading(event) {
pixivState.detailLoading = !!event.loading
}

function _pyEvt_pixiv_detail_result(event) {
pixivState.detailLoading = false
      if (event.error) {
        message.error(event.error)
        addLog('P站', event.error)
        return
      }
      pixivState.detail = event
      pixivState.view = 'detail'
      addLog('P站', `详情已加载：${(event.detail || {}).album_name || event.item_id}（评论 ${event.total_comments ?? 0}）`)
}

function _pyEvt_pixiv_author_works(event) {
if (pixivState.detail && String(pixivState.detail.item_id) === String(event.item_id)) {
        pixivState.detail = { ...pixivState.detail, author_works: event.works || [] }
      }
}

function _pyEvt_pixiv_novel_images(event) {
if (pixivState.detail && String(pixivState.detail.item_id) === String(event.item_id)
          && pixivState.detail.raw) {
        pixivState.detail = {
          ...pixivState.detail,
          raw: { ...pixivState.detail.raw, embedded_images: event.embedded_images || {} },
        }
      }
}

function _pyEvt_pixiv_related_result(event) {
pixivState.related = { kind: event.kind, item_id: event.item_id, items: event.items || [] }
      if (event.error) addLog('P站', event.error)
}

function _pyEvt_pixiv_action_result(event) {
if (event.ok) {
        message.success(event.message)
        // 评论操作后刷新详情（重拉评论列表）
        if ((event.action || '').startsWith('comment_') && pixivState.detail) {
          window.api.sendCommand({
            cmd: 'pixiv_detail', kind: pixivState.detail.kind, item_id: pixivState.detail.item_id,
          })
        }
        // 收藏/取消后同步详情卡片状态
        if (pixivState.detail && String(pixivState.detail.item_id) === String(event.item_id)) {
          if (event.action === 'bookmark_add') pixivState.detail.detail.is_bookmarked = true
          if (event.action === 'bookmark_delete') pixivState.detail.detail.is_bookmarked = false
        }
      } else {
        message.error(event.message)
      }
      addLog('P站', `互动 ${event.action}: ${event.message}`)
}

function _pyEvt_pixiv_tags_result(event) {
pixivState.myTags = event.my_tags || []
      pixivState.trending = event.trending || []
}

function _pyEvt_pixiv_notification_result(event) {
if (event.ok) {
        pixivState.notifications = { items: event.items || [], unread: event.unread || 0, message: '' }
      } else {
        pixivState.notifications = { items: [], unread: 0, message: event.message || '加载失败' }
      }
}

function _pyEvt_pixiv_bookmark_tags_result(event) {
pixivState.bookmarkTags = event.ok
        ? { content: event.content, tags: event.tags || [], message: '' }
        : { content: '', tags: [], message: event.message || '加载失败' }
}

function _pyEvt_pixiv_upload_result(event) {
pixivState.uploadResult = event
      if (event.ok) message.success(event.message)
      else message.error(event.message)
      addLog('P站', `发布作品: ${event.message}`)
}

function _pyEvt_pixiv_batch_progress(event) {
pixivBatchRunning.value = true
      pixivBatchProgress.done = event.done || 0
      pixivBatchProgress.total = event.total || 0
      pixivBatchProgress.message = event.message || ''
      addLog('P站', `批量下载 ${event.done || 0}/${event.total || 0}: ${event.message || ''}`)
}

function _pyEvt_pixiv_batch_done(event) {
pixivBatchRunning.value = false
      if (event.failed && event.failed.length) {
        message.warning(event.message || '批量下载部分失败')
      } else {
        message.success(event.message || '批量下载已提交')
      }
      addLog('P站', `批量下载完成: ${event.message || ''}`)
      if (!detailVisible.value) {
        detailVisible.value = true
      }
}

function _pyEvt_pixiv_proxy_set(event) {
if ((event.proxy || '') !== settings.pixiv_proxy) {
        settings.pixiv_proxy = event.proxy || ''
        saveSettings()
      }
}

function _pyEvt_hanime_home(event) {
haHomeLoading.value = false
      haHomeError.value = event.error || ''
      if (event.error) return
      haSections.value = event.sections || []
      if (event.genres) haGenres.value = event.genres
      if (event.sorts) haSorts.value = event.sorts
      if (haView.value !== 'detail') haView.value = 'home'
      maybeAutoTranslateAfterSearch()
}

function _pyEvt_hanime_home_loading(event) {
haHomeLoading.value = !!event.loading
}

function _pyEvt_hanime_video_detail(event) {
haDetailLoading.value = false
      if (event.error || !event.video) {
        message.error(event.error || '获取视频详情失败')
        return
      }
      haDetail.value = event.video
      haComments.value = event.comments || []
if (!haView.value) detailFromSearch.value = 'hanime1'
            navPushView('hanime1', 'detail')
      haView.value = 'detail'
}

function _pyEvt_hanime_detail_loading(event) {
haDetailLoading.value = !!event.loading
}

function _pyEvt_hanime_comments(event) {
if (event.error) {
        message.error(event.error)
        return
      }
      haComments.value = event.items || []
}

function _pyEvt_hanime_comment_result(event) {
if (event.success) {
        message.success(event.message || '评论发表成功')
        // 刷新当前视频的评论列表
        if (haDetail.value && haDetail.value.video_id === event.video_id) {
          window.api.sendCommand({ cmd: 'hanime_comments', video_id: event.video_id })
        }
      } else {
        message.error(event.message || '评论发表失败')
      }
}

function _pyEvt_hanime_save_result(event) {
if (event.success) {
        message.success(event.message || (event.saved ? '已加入稍後觀看' : '已取消收藏'))
        if (haDetail.value && haDetail.value.video_id === event.video_id) {
          haDetail.value.saved = !!event.saved
        }
      } else {
        message.error(event.message || '收藏操作失败')
      }
}

function _pyEvt_hanime_user_videos(event) {
haUserLoading.value = false
      if (event.error) {
        message.error(event.error)
        if ((event.page || 1) <= 1) haUserItems.value = []
        return
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
}

function _pyEvt_hanime_user_loading(event) {
haUserLoading.value = !!event.loading
}

function _pyEvt_hanime_batch_progress(event) {
haBatchRunning.value = true
      haBatchProgress.done = event.done || 0
      haBatchProgress.total = event.total || 0
      haBatchProgress.message = event.message || ''
}

function _pyEvt_hanime_batch_done(event) {
haBatchRunning.value = false
      haBatchProgress.done = event.done || 0
      haBatchProgress.total = event.total || 0
      haBatchProgress.message = ''
      if (event.message) {
        message.info(event.message)
        addLog('下载', event.message)
      }
}

function _pyEvt_oreno_proxy_set(event) {
{
      // 后端确认代理设置（含自动补 http:// 前缀；按 site_key 区分 O3D / E站）
      const field = event.site_key === 'erommdtube' ? 'erommd_proxy' : 'oreno_proxy'
      if ((event.proxy || '') !== settings[field]) {
        settings[field] = event.proxy || ''
        saveSettings()
      }
      return
    }
}

function _pyEvt_oreno_home(event) {
if (orEventStale(event)) return
      orHomeLoading.value = false
      orDataSite.value = event.site_key || siteKey.value
      orHomeError.value = event.error || ''
      if (event.error) return
      if ((event.page || 1) <= 1) {
        orHomeItems.value = event.items || []
      } else {
        orHomeItems.value.push(...(event.items || []))
      }
      orHomePage.value = event.page || 1
      orHomeHasMore.value = !!event.has_more
      if (event.sorts) orSorts.value = event.sorts
      if (orView.value !== 'detail' && orView.value !== 'list') orView.value = 'home'
      maybeAutoTranslateAfterSearch()
}

function _pyEvt_oreno_home_loading(event) {
if (orEventStale(event)) return
      orHomeLoading.value = !!event.loading
}

function _pyEvt_oreno_list(event) {
if (orEventStale(event)) return
      orListLoading.value = false
      orDataSite.value = event.site_key || siteKey.value
      if (event.error) {
        orListError.value = event.error
        message.error(event.error)
        if ((event.page || 1) <= 1) orList.items = []
        return
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
}

function _pyEvt_oreno_list_loading(event) {
if (orEventStale(event)) return
      orListLoading.value = !!event.loading
}

function _pyEvt_oreno_tags(event) {
if (orEventStale(event)) return
      orTagsLoading.value = false
      orDataSite.value = event.site_key || siteKey.value
      if (event.error) {
        message.error(event.error)
        return
      }
      orTags.value = event.tags || []
      orTagGroups.value = event.groups || []
      orTagGroupTitle.value = event.group_title || ''
}

function _pyEvt_oreno_tags_loading(event) {
if (orEventStale(event)) return
      orTagsLoading.value = !!event.loading
}

function _pyEvt_oreno_characters(event) {
if (orEventStale(event)) return
      orCharsLoading.value = false
      orDataSite.value = event.site_key || siteKey.value
      if (event.error) {
        message.error(event.error)
        return
      }
      orCharacters.value = { popular: event.popular || [], kana_groups: event.kana_groups || {} }
}

function _pyEvt_oreno_chars_loading(event) {
if (orEventStale(event)) return
      orCharsLoading.value = !!event.loading
}

function _pyEvt_oreno_authors(event) {
if (orEventStale(event)) return
      orAuthorsLoading.value = false
      orDataSite.value = event.site_key || siteKey.value
      if (event.error) {
        message.error(event.error)
        return
      }
      orAuthors.value = event.authors || []
      orAuthorsPage.value = event.page || 1
      orAuthorsHasMore.value = !!event.has_more
}

function _pyEvt_oreno_authors_loading(event) {
if (orEventStale(event)) return
      orAuthorsLoading.value = !!event.loading
}

function _pyEvt_oreno_fav_result(event) {
if (orEventStale(event)) return
      if (event.error) {
        message.error(event.error)
        return
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
}

function _pyEvt_oreno_video_detail(event) {
if (orEventStale(event)) return
      orDetailLoading.value = false
      if (event.error || !event.video) {
        message.error(event.error || '获取视频详情失败')
        return
      }
      orDetail.value = event.video
      orDataSite.value = event.site_key || siteKey.value
if (!orView.value) detailFromSearch.value = 'oreno'
            navPushView('oreno', 'detail')
      orView.value = 'detail'
}

function _pyEvt_oreno_detail_loading(event) {
if (orEventStale(event)) return
      orDetailLoading.value = !!event.loading
}

function _pyEvt_oreno_batch_progress(event) {
if (orEventStale(event)) return
      orBatchRunning.value = true
      orBatchProgress.done = event.done || 0
      orBatchProgress.total = event.total || 0
      orBatchProgress.message = event.message || ''
}

function _pyEvt_oreno_batch_done(event) {
if (orEventStale(event)) return
      orBatchRunning.value = false
      orBatchProgress.done = event.done || 0
      orBatchProgress.total = event.total || 0
      orBatchProgress.message = ''
      if (event.message) {
        message.info(event.message)
        addLog('下载', event.message)
      }
}

function _pyEvt_asmr_login_result(event) {
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
}

function _pyEvt_asmr_proxy_set(event) {
if ((event.proxy || '') !== settings.asmr_proxy) {
        settings.asmr_proxy = event.proxy || ''
        saveSettings()
      }
}

function _pyEvt_asmr_list(event) {
if ((settings.site || 'bunkr') !== 'asmr') return
      asmrListLoading.value = false
      asmrView.value = event.view || 'popular'
      asmrPage.value = event.page || 1
      asmrHasMore.value = !!event.has_more
      asmrError.value = event.error || ''
      if (event.view === 'favorites') asmrRecommend.value = event.recommend || []
      if (event.error) return
      if ((event.page || 1) <= 1) {
        asmrItems.value = event.items || []
      } else {
        asmrItems.value.push(...(event.items || []))
      }
      asmrLabel.value = event.label || ''
      asmrTotal.value = event.total || 0
      if (event.orders) asmrOrders.value = event.orders
      searchResults.value = []
      maybeAutoTranslateAfterSearch()
}

function _pyEvt_move_task_folder_result(event) {
if (event.ok) {
        message.success(event.message || '文件夹已移动')
        addLog('系统', event.message || '文件夹已移动')
      } else {
        message.error(event.message || '文件夹移动失败')
        addLog('错误', event.message || '文件夹移动失败')
      }
}

function _pyEvt_reverse_start(event) {
reverseSession.value = event.session || ''
      reverseMerged.value = []
      reverseCached.value = false
      reverseRunning.value = true
      reverseSites.value = (event.sites || []).map(s => ({
        ...s, status: 'running', results: [], url: '', error: '',
      }))
}

function _pyEvt_reverse_site_update(event) {
{
      if (event.session && event.session !== reverseSession.value) return
      const site = reverseSites.value.find(x => x.key === event.site)
      if (site) {
        site.status = event.status
        site.results = event.results || []
        site.url = event.url || ''
        site.error = event.error || ''
      }
      return
    }
}

function _pyEvt_reverse_all_done(event) {
{
      if (event.session && event.session !== reverseSession.value) return
      reverseRunning.value = false
      reverseMerged.value = event.merged || []
      reverseCached.value = !!event.cached
      // 缓存命中路径后端不发逐站 site_update：从 groups 回填站点状态与结果
      for (const g of (event.groups || [])) {
        const site = reverseSites.value.find(x => x.key === g.site || x.name === g.name)
        if (site) {
          site.status = 'done'
          site.results = g.results || []
          site.url = g.url || site.url || ''
        }
      }
      const okCount = (event.ok_sites || []).length
      const failCount = (event.failed_sites || []).length
      if (okCount > 0) {
        message.success(
          `识图完成：${okCount} 个网站返回结果${failCount ? `（${failCount} 个网站失败已移除）` : ''}`
          + (event.cached ? '（本地缓存）' : ''))
      } else {
        message.error('识图失败：所有网站均未返回结果（请检查网络或代理设置）')
      }
      addLog('识图', `搜索完成：成功 ${okCount} 个网站，失败 ${failCount} 个${event.cached ? '（缓存）' : ''}`)
      return
    }
}

function _pyEvt_reverse_cancelled(event) {
{
      if (event.session && event.session !== reverseSession.value) return
      reverseRunning.value = false
      addLog('识图', '已取消搜索')
      return
    }
}

function _pyEvt_reverse_error(event) {
if (event.session && event.session !== reverseSession.value) return
      reverseRunning.value = false
      message.error(event.message || '识图失败')
      addLog('识图', `失败: ${event.message || '未知错误'}`)
}

function _pyEvt_reverse_download_start(event) {
addLog('识图', `解析下载: ${event.url}`)
}

function _pyEvt_reverse_download_done(event) {
message.success(`已加入下载：${event.count} 个文件${event.album ? `（${event.album}）` : ''}`)
      addLog('识图', `已创建下载任务: ${event.url}（${event.count} 个文件）`)
}

function _pyEvt_reverse_download_error(event) {
message.error(event.message || '无法下载该结果')
      addLog('识图', `下载失败: ${event.message || '未知错误'}`)
}

function _pyEvt_reverse_paste(event) {
reversePaste.value = event.text || ''
}

function _pyEvt_reverse_proxy_set(event) {
if ((event.proxy || '') !== settings.reverse_proxy) {
        settings.reverse_proxy = event.proxy || ''
        saveSettings()
      }
      if (!!event.all_sites !== !!settings.reverse_proxy_all) {
        settings.reverse_proxy_all = !!event.all_sites
        saveSettings()
      }
}

function _pyEvt_asmr_list_loading(event) {
asmrListLoading.value = !!event.loading
}

function _pyEvt_asmr_video_detail(event) {
asmrDetailLoading.value = false
      if (event.error || !event.video) {
        message.error(event.error || '获取作品详情失败')
        return
      }
      if (asmrView.value !== 'detail') asmrListPrevView.value = asmrView.value
      asmrDetail.value = event.video
      // 后端音轨字段为 stream_url/media_url，前端播放器用 play_url —— 统一映射（播放修复）
      asmrFiles.value = (event.files || []).map(f => ({
        ...f,
        play_url: f.play_url || f.stream_url || f.media_url || '',
      }))
      asmrLoggedIn.value = !!event.logged_in
      asmrRelated.value = event.related || []
      asmrRelatedPending.value = !!event.related_pending
if (!asmrView.value) detailFromSearch.value = 'asmr'
            navPushView('asmr', 'detail')
      asmrView.value = 'detail'
}

function _pyEvt_asmr_related_extra(event) {
{
      // tags 推荐后台补齐（异步架构）：仅当用户仍停留在同一作品详情时合并，防切详情串台
      if (String(asmrDetail.value?.video_id || '') !== String(event.work_id || '')) return
      asmrRelatedPending.value = false
      const extra = (event.items || []).filter(it => it && it.video_id)
      if (!extra.length) return
      const seen = new Set(asmrRelated.value.map(r => String(r.video_id)))
      seen.add(String(asmrDetail.value.video_id || ''))
      const merged = asmrRelated.value.slice()
      for (const it of extra) {
        const id = String(it.video_id)
        if (seen.has(id)) continue
        seen.add(id)
        merged.push(it)
        if (merged.length >= 12) break
      }
      asmrRelated.value = merged
      return
    }
}

function _pyEvt_pa_fav_result(event) {
{
      // 关注结果：回填对应卡片状态
      if (event.error) { message.error(event.error); return }
      message.success(event.favorited ? '已关注' : '已取消关注')
      const favKey = `${event.service}_${event.user_id}`
      searchResults.value = searchResults.value.map(it => {
        if (it.site === 'pawchive' && it.user_id && `${it.service}_${it.user_id}` === favKey) {
          return { ...it, favorited: !!event.favorited }
        }
        return it
      })
      return
    }
}

function _pyEvt_gs_state(event) {
{
      // 通用站点状态回流（模块化契约：后端 emit gs_state {site, view, items, ...}）
      let gsEvent = event
      const gsSite = event.site || ''
      // 翻页追加（GSV「加载更多」契约）：page>1 时合并旧列表（后端无状态按页抓；
      // loading 占位事件 items 为空，直接覆盖会清掉已加载内容）
      const gsPrev = gsSite ? gsStates.value[gsSite] : null
      if (gsSite && event.view === 'list' && Number(event.page) > 1 && gsPrev && gsPrev.view === 'list') {
        const gsKey = i => String((i && (i.album_url || i.video_id)) || '')
        if (event.loading) {
          gsEvent = { ...event, items: gsPrev.items || [] }
        } else {
          const gsSeen = new Set((gsPrev.items || []).map(gsKey))
          const gsFresh = (event.items || []).filter(i => !gsSeen.has(gsKey(i)))
          gsEvent = { ...event, items: [...(gsPrev.items || []), ...gsFresh] }
        }
      }
      if (gsSite) {
        gsStates.value = { ...gsStates.value, [gsSite]: gsEvent }
        if (gsSite === 'fc2' && String(event.error || '').startsWith('NEED_LOGIN')) {
          fc2NeedCookieSync = true   // 后端会话失效：下一条 fc2 命令前自动同步分区 cookie（可能用户在 webview 里刚动过）
        }
        // FC2 批量解析提交完成：自动打开下载管理面板（此前任务在后台跑，用户以为"没反应"）
        if (gsSite === 'fc2' && /已提交/.test(String((event.batchProgress || {}).message || ''))) {
          if (!detailVisible.value) {
            detailVisible.value = true
            message.info('批量下载任务已提交，已为你打开下载管理')
          }
        }
      }
      return
    }
}

function _pyEvt_asmr_detail_loading(event) {
asmrDetailLoading.value = !!event.loading
}

function _pyEvt_asmr_circles(event) {
if (event.error) {
        message.error(event.error)
        return
      }
      asmrIndexItems.value = event.items || []
}

function _pyEvt_asmr_circles_loading(event) {
asmrIndexLoading.value = !!event.loading
}

function _pyEvt_asmr_fav_result(event) {
if (event.error) {
        message.error(event.error)
        return
      }
      message.success(event.saved ? '已收藏' : '已取消收藏')
      if (asmrDetail.value && String(asmrDetail.value.video_id) === String(event.video_id)) {
        asmrDetail.value.saved = !!event.saved
      }
      // 收藏列表视图中同步移除/恢复
      if (asmrView.value === 'favorites' && !event.saved) {
        asmrItems.value = asmrItems.value.filter(i => String(i.video_id) !== String(event.video_id))
      }
}

function _pyEvt_asmr_batch_progress(event) {
asmrBatchRunning.value = true
      asmrBatchProgress.done = event.done || 0
      asmrBatchProgress.total = event.total || 0
      asmrBatchProgress.message = event.message || ''
}

function _pyEvt_asmr_batch_done(event) {
asmrBatchRunning.value = false
      asmrBatchProgress.done = event.done || 0
      asmrBatchProgress.total = event.total || 0
      asmrBatchProgress.message = ''
      if (event.message) {
        message.info(event.message)
        addLog('下载', event.message)
      }
}

function _pyEvt_login_info(event) {
loginInfo.value = event.sites || {}
      // 登录成功的站点移出"已提醒"名单（再失效时可再次提醒）
      for (const _li of Object.keys(loginInfo.value)) {
        if (loginInfo.value[_li] && loginInfo.value[_li].logged_in) loginWarnedSites.delete(_li)
      }
      // 谷歌邮箱：回填设置区表单邮箱（来自加密凭据库；表单在 LeftPanel 内部自持状态）
      if (loginInfo.value.google && loginInfo.value.google.username) {
        googleEmail.value = loginInfo.value.google.username
      }
      // 谷歌邮箱多账号列表（设置区展示/复制/切换/删除）
      googleAccounts.value = (loginInfo.value.google && loginInfo.value.google.accounts) || []
      // O3D / E站：回填账号密码（LeftPanel 登录表单预填）
      for (const _oKey of ['oreno3d', 'erommdtube']) {
        const _oInfo = loginInfo.value[_oKey] || {}
        const _cred = { email: _oInfo.email || _oInfo.username || '', password: _oInfo.password || '' }
        if (_oKey === 'oreno3d') oreno3dCred.value = _cred
        else erommdtubeCred.value = _cred
      }
      // 全站登录套件：回填各站保存的账号密码（LeftPanel 登录表单预填）
      const _savedCreds = {}
      for (const _sKey of ['pawchive', 'twitter', 'exhentai', 'iwara', 'hanime', 'asmr',
                           'xhamster', 'pornhub', 'xvideos', 'javdb']) {
        const _sInfo = loginInfo.value[_sKey] || {}
        if (_sInfo.email || _sInfo.password) {
          _savedCreds[_sKey] = { email: _sInfo.email || '', password: _sInfo.password || '' }
        }
      }
      siteCreds.value = _savedCreds
}

function _pyEvt_account_saved(event) {
      // silent=启动恢复/自动保存路径：只进日志不弹窗（2026-09-17 用户要求：启动不得弹出内部信息提醒）
      if (!event.silent) message.success(event.message || '账号档案已更新')
      addLog('系统', event.message || '')
}

function _pyEvt_account_error(event) {
message.error(event.message || '账号档案操作失败')
      addLog('错误', event.message || '')
}

function _pyEvt_exhentai_torrents(event) {
if (rightPanelRef.value) rightPanelRef.value.setTorrents(event.torrents)
      if (event.message) addLog('磁力', event.message)
}

function _pyEvt_exhentai_torrents_error(event) {
if (rightPanelRef.value) rightPanelRef.value.setTorrentsError()
      message.error(event.message || '获取种子失败')
      addLog('错误', `获取种子失败: ${event.message || ''}`)
}

function _pyEvt_exhentai_magnet(event) {
if (rightPanelRef.value) rightPanelRef.value.setMagnet(event.magnet)
      addLog('磁力', `已获取磁力链接: ${event.name || event.infohash || ''}`)
}

function _pyEvt_exhentai_magnet_error(event) {
if (rightPanelRef.value) rightPanelRef.value.setMagnetError()
      message.error(event.message || '磁力解析失败')
      addLog('错误', `磁力解析失败: ${event.message || ''}`)
}

function _pyEvt_ex_gallery_info(event) {
exDetailLoading.value = false
      exGalleryDetail.value = event
      addLog('解析', `画廊详情: ${event.title || ''}`)
      // 自动解析：详情界面展示画师/tag 后直接出图片缩略图（需求：点开即见资源，不用再点"解析图片列表"）
      if (exAutoParseGallery.value && event.url) {
        exAutoParseGallery.value = false
        openSearchResult({ album_url: event.url, album_name: event.title || '' })
      }
}

function _pyEvt_ex_gallery_info_error(event) {
exDetailLoading.value = false
      message.error(event.message || '获取画廊信息失败')
      addLog('错误', `获取画廊信息失败: ${event.message || ''}`)
}

function _pyEvt_bg_busy(event) {
message.warning(event.message || '上一个同类任务还在处理中')
      addLog('提示', event.message || '同类任务进行中')
}

function _pyEvt_ex_torrents_result(event) {
if (rightPanelRef.value && rightPanelRef.value.setTorrents) {
        if (event.error) {
          rightPanelRef.value.setTorrentsError()
          message.error(event.error || '种子获取失败')
        } else {
          rightPanelRef.value.setTorrents(event.torrents || [])
          if (!(event.torrents || []).length) message.info('该画廊没有可用种子')
        }
      }
}

function _pyEvt_ex_torrent_saved(event) {
if (event.success) {
        message.success(event.message || '种子已保存')
        addLog('下载', `种子已保存: ${event.path || ''}`)
      } else {
        message.error(event.message || '种子保存失败')
        addLog('错误', `种子保存失败: ${event.message || ''}`)
      }
}

function _pyEvt_pa_post_info(event) {
paDetailLoading.value = false
      paPostDetail.value = event
      addLog('解析', `帖子详情: ${event.title || ''}`)
}

function _pyEvt_pa_post_info_error(event) {
paDetailLoading.value = false
      message.error(event.message || '获取帖子信息失败')
      addLog('错误', `获取帖子信息失败: ${event.message || ''}`)
}

function _pyEvt_pa_artist_posts(event) {
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
}

function _pyEvt_pa_artist_posts_error(event) {
paArtistPostsLoading.value = false
      message.error(event.message || '获取画师帖子列表失败')
      addLog('错误', `获取画师帖子列表失败: ${event.message || ''}`)
}

function _pyEvt_ex_hidden_tags(event) {
exHiddenTags.value = event.tags || []
}

function _pyEvt_search_history(event) {
searchHistory.value = event.items || []
}

function _pyEvt_translate_result(event) {
translateResult.value = event
}

function _pyEvt_translate_batch_result(event) {
{
      // 全局自动翻译：批量译文回填到 translatedTitles 映射
      autoTranslating.value = false
      // 结果到达：清掉看门狗
      if (translateWatchdog) {
        clearTimeout(translateWatchdog)
        translateWatchdog = null
      }
      // 用发送时记录的标题列表对位（batch_id 关联），避免期间列表变化导致错位
      const pending = translateBatchPending.get(event.batch_id)
      const titles = (pending && pending.titles) || collectCurrentTitles()
      translateBatchPending.delete(event.batch_id)
      // 代际校验：用户已关闭翻译开关（gen 已 +1）→ 迟到结果丢弃，不再回填
      if (pending && pending.gen !== translateBatchGen) return
      if (!event.ok) {
        message.error(event.error || '翻译失败（Google 免费端点不可达，可在左侧翻译面板配置代理或更换引擎）')
        return
      }
      if (Array.isArray(event.translations)) {
        const map = { ...translatedTitles.value }
        // 按发送顺序对位覆盖（后端保证顺序一致）
        for (let i = 0; i < titles.length && i < event.translations.length; i++) {
          const orig = titles[i]
          const tr = event.translations[i]
          if (orig && tr && tr !== orig) map[orig] = tr
        }
        translatedTitles.value = map
      }
      return
    }
}

function _pyEvt_github_update_info(event) {
githubChecking.value = false
      githubUpdateInfo.value = event
}

function _pyEvt_changelog_info(event) {
changelogLoading.value = false
      if (event.ok) {
        changelogInfo.value = event
        changelogModalVisible.value = true
      } else {
        message.error(event.error || '更新日志获取失败，请检查网络')
        // 更新日志拉取失败时仍走原更新检查流程，保证功能可用
        handleCheckGithubUpdate()
      }
}

function _pyEvt_update_download_progress(event) {
updateDownload.downloading = true
      updateDownload.received = event.received || 0
      updateDownload.total = event.total || updateDownload.total || 0
      updateDownload.percent = event.percent || 0
      updateDownload.speed = event.speed || 0
      updateDownload.fileName = event.file_name || updateDownload.fileName
      updateDownload.path = event.path || updateDownload.path
}

function _pyEvt_update_download_done(event) {
updateDownload.downloading = false
      updateDownload.done = true
      updateDownload.percent = 100
      updateDownload.received = event.size || updateDownload.received
      updateDownload.total = event.total || updateDownload.total
      updateDownload.path = event.path || updateDownload.path
      updateDownload.fileName = event.file_name || updateDownload.fileName
      updateDownload.speed = 0
      message.success('更新安装包下载完成，点"立即安装"覆盖更新（数据不丢失）')
      addLog('完成', `更新安装包已下载: ${updateDownload.fileName}`)
}

function _pyEvt_update_download_error(event) {
updateDownload.downloading = false
      updateDownload.error = event.error || '下载失败'
      message.error(`更新下载失败: ${updateDownload.error}`)
      addLog('错误', `更新下载失败: ${updateDownload.error}`)
}

function _pyEvt_update_installer_launched(event) {
message.info('更新安装程序已启动，按提示完成覆盖安装（登录与下载数据保留）')
}

function _pyEvt_github_update_marked(event) {
if (githubUpdateInfo.value && typeof githubUpdateInfo.value === 'object') {
        githubUpdateInfo.value = { ...githubUpdateInfo.value, has_update: false }
      }
}

function _pyEvt_local_favorites(event) {
localFavorites.value = event.items || []
}

function _pyEvt_local_favorites_saved(event) {
if (event.duplicate) {
        message.info(event.message || '已在收藏中')
      } else {
        message.success(event.message || '已收藏到本地')
      }
      // 刷新收藏列表
      if (window.api) window.api.sendCommand({ cmd: 'get_favorites' })
}

function _pyEvt_local_favorites_error(event) {
message.error(event.message || '收藏失败')
}

function _pyEvt_twitter_follow_loading(event) {
twFollowLoading.value = !!event.loading
}

function _pyEvt_twitter_follow_list(event) {
twFollowLoading.value = false
      if (event.refresh_failed) {
        // 已展示缓存，仅后台刷新失败
        addLog('X', `刷新关注列表失败（继续显示缓存）: ${event.refresh_failed}`)
        return
      }
      if (event.error) {
        twFollowError.value = event.error
        if (!event.append) twFollowItems.value = []
        message.error(event.error)
        addLog('错误', event.error)
        return
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
}

function _pyEvt_twitter_browse_loading(event) {
twBrowseLoading.value = !!event.loading
      if (event.loading) {
        twBrowseProgress.done = 0
        twBrowseProgress.total = 0
        twBrowseError.value = ''
      }
}

function _pyEvt_twitter_browse_progress(event) {
twBrowseProgress.done = event.done || 0
      twBrowseProgress.total = event.total || 0
}

function _pyEvt_twitter_user_feed_loading(event) {
twUserFeedLoading.value = !!event.loading
}

function _pyEvt_twitter_user_feed(event) {
{
      // 仅在用户详情视图时应用；快速切换博主时丢弃旧博主的数据（防串台）
      if (twFollowMode.value !== 'user') return
      if (event.error) {
        twUserFeed.value = []
        twUserLoadAllRunning.value = false
        message.error(event.error)
        addLog('错误', event.error)
        return
      }
      if (twUserFeedUserId.value && event.user_id
        && String(event.user_id) !== twUserFeedUserId.value) {
        twUserLoadAllRunning.value = false
        return
      }
      // 无 cursor 首包带博主资料统计（媒体/推文/粉丝/关注数），存起来给用户页头部显示
      if (!event.append && event.profile) {
        twUserProfileStats.value = event.profile
      }
      twUserFeed.value = event.append
        ? twUserFeed.value.concat(event.items || [])
        : (event.items || [])
      twUserFeedCursor.value = event.cursor || ''
      twUserFeedHasMore.value = !!event.has_more
      // load_all 模式的最终包（has_more=false，items=全量）到达后结束「加载全部」状态
      if (twUserLoadAllRunning.value && !twUserFeedHasMore.value) {
        twUserLoadAllRunning.value = false
      }
      if (!event.append) {
        addLog('X', `博主内容流：@${event.screen_name || ''} ${(event.items || []).length} 条推文`)
      }
      return
    }
}

// 用户页「加载全部」进度（load_all 模式中后端持续上报：已加载推文数 / 媒体总数）
function _pyEvt_twitter_user_feed_progress(event) {
  twUserLoadAllProgress.loaded = event.loaded || 0
  twUserLoadAllProgress.total_media = event.total_media || 0
}

// HTML 相册导出进度（拉取内容阶段上报：阶段 + 已完成条数）
function _pyEvt_twitter_export_progress(event) {
  twExportRunning.value = true
  twExportProgress.phase = event.phase || ''
  twExportProgress.done = event.done || 0
}

function _pyEvt_twitter_export_done(event) {
  twExportRunning.value = false
  if (event.ok) {
    message.success(`HTML 相册已保存（共 ${event.total || 0} 条，新增 ${event.new || 0} 条）：${event.path || ''}`)
    addLog('X', `HTML 相册已保存：${event.path || ''}（共 ${event.total || 0} 条，新增 ${event.new || 0} 条）`)
  } else {
    message.error(event.error || 'HTML 相册导出失败')
    addLog('错误', `HTML 相册导出失败：${event.error || '未知错误'}`)
  }
}

function _pyEvt_twitter_browse_feed(event) {
if (!['browse', ''].includes(twFollowMode.value)) return
      twFollowMode.value = 'browse'
      if (event.error) {
        twBrowseError.value = event.error
        if (!event.items?.length && !event.cached) twBrowseFeed.value = []
        message.error(event.error)
        addLog('错误', event.error)
        return
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
}

function _pyEvt_twitter_cache_cleared(event) {
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
}

function _pyEvt_twitter_follows(event) {
twFollowLoading.value = false
      if (!['user', 'browse'].includes(twFollowMode.value)) {
        twFollowMode.value = 'follows'
      }
      twFollowError.value = ''
      twFollowItems.value = event.items || []
      twFollowHasMore.value = false
}

function _pyEvt_twitter_follow_tags(event) {
twFollowTags.value = event.tags || []
}

function _pyEvt_twitter_follow_result(event) {
{
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
      return
    }
}

function _pyEvt_download_rename_prompt(event) {
renameQueue.value.push(event)
      if (!renameModal.visible) showNextRenamePrompt()
}

function _pyEvt_site_login_result(event) {
{
      const siteKey = event.site
      const userRefs = {
        xhamster: xhamsterUser, fc2: fc2User, pornhub: pornhubUser, xvideos: xvideosUser,
        javdb: javdbUser, google: googleUser, oreno3d: oreno3dUser, erommdtube: erommdtubeUser,
      }
      const userRef = userRefs[siteKey]
      if (event.logout) {
        if (userRef) userRef.value = ''
        // 同步刷新本地登录信息缓存（否则 siteLoggedIn 残留 true，登录表单回不来）
        if (loginInfo.value[siteKey]) loginInfo.value[siteKey].logged_in = false
        if (!event.silent) message.info(event.message || `已退出 ${siteKey} 登录`)
        addLog('系统', `${siteKey} 已退出登录`)
        // FC2：退出后直接弹出内置浏览器登录界面（登录 → 确认抓 cookie → 全功能恢复）
        if (siteKey === 'fc2') {
          setTimeout(() => handleSiteOAuthLogin('fc2', (() => {
            const cred = loginInfo.value.fc2 || {}
            return cred.email ? { email: cred.email, password: cred.password || '' } : null
          })()), 600)
        }
      } else if (event.logged_in) {
        const uname = event.username || '已登录'
        if (userRef) userRef.value = uname
        if (!event.silent) message.success(event.message || `${siteKey} 登录成功`)
        addLog('系统', `${siteKey} 登录成功: ${uname}`)
        // xHamster：登录成功自动进入浏览首页（修复登录后右侧无界面）
        if (siteKey === 'xhamster' && settings.site === 'xhamster' && !xhView.value) {
          handleXhHome(1)
        }
      } else {
        if (userRef) userRef.value = ''
        let hint = event.message || `${siteKey} 未登录或登录失效`
        // javdb cookie 约 7 天有效（"记住装置"），过期提示重新登录（网络异常除外）
        if (siteKey === 'javdb' && !event.network_issue) hint = 'JavDB 登录已失效（"记住装置"约 7 天），请在左侧重新登录'
        if (!event.silent) message.warning(hint)
        addLog('系统', `${siteKey} 未登录`)
      }
      return
    }
}

function _pyEvt_javdb_detail_loading(event) {
clearTimeout(javdbDetailWatchdog)
      javdbDetailLoading.value = !!event.loading
      // 详情结束时同步解除全局解析转圈（手动粘贴链接走 inspect 命令时，
      // JavDB 后端流程不发 inspect 终止事件，inspecting 会卡满 120s 看门狗）
      if (!event.loading) {
        clearTimeout(inspectWatchdog)
        inspecting.value = false
      }
      // loading 后 60s 无 video_detail/error 事件时解除转圈（后端静默兜底）
      if (event.loading) {
        javdbDetailWatchdog = setTimeout(() => {
          if (javdbDetailLoading.value) {
            javdbDetailLoading.value = false
            addLog('错误', 'JavDB 详情解析超时（后端长时间无响应）')
            message.error('JavDB 详情解析超时，请重试')
          }
        }, 60000)
      }
}

function _pyEvt_javdb_video_detail(event) {
clearTimeout(javdbDetailWatchdog)
      javdbDetailLoading.value = false
      clearTimeout(inspectWatchdog)
      inspecting.value = false
      if (event.error) {
        message.error(event.error)
        addLog('错误', event.error)
        return
      }
      javdbDetail.value = event.video || null
      addLog('解析', `JavDB 详情: ${event.video?.title || ''}（${event.video?.magnets?.length || 0} 磁力 / ${event.video?.previews?.length || 0} 预览图）`)
}

function _pyEvt_javdb_batch_progress(event) {
javdbBatchRunning.value = true
      javdbBatchProgress.done = event.done || 0
      javdbBatchProgress.total = event.total || 0
}

function _pyEvt_javdb_batch_done(event) {
javdbBatchRunning.value = false
      if (event.message) {
        message.info(event.message)
        addLog('下载', event.message)
      }
}

function _pyEvt_javdb_tags_vocab(event) {
javdbTagsVocab.value = event.modes || null
      // 首次拿到词库：进入站点默认加载当前 tags 模式的推荐作品（第五行）
      if (
        javdbTagsVocab.value && (settings.site || '') === 'javdb' &&
        !javdbModeRecommend.items.length && !searchResults.value.length && !searching.value
      ) {
        const m = javdbTagsVocab.value.find(x => x.key === javdbTagsMode.value) || javdbTagsVocab.value[0]
        if (m) handleJavdbTagsMode(m)
      }
}

function _pyEvt_javdb_hot_search(event) {
javdbHotKeywords.value = event.keywords || []
}

function _pyEvt_javdb_directory(event) {
javdbDir.kind = event.kind || ''
      javdbDir.label = event.label || ''
      javdbDir.items = event.items || []
      javdbDir.page = event.page || 1
      javdbDir.hasMore = !!event.has_more
}

const PY_EVENT_HANDLERS = {
  'ready': _pyEvt_ready,
  'inspect_start': _pyEvt_inspect_start,
  'inspect_progress': _pyEvt_inspect_progress,
  'inspect_complete': _pyEvt_inspect_complete,
  'inspect_error': _pyEvt_inspect_error,
  'search_start': _pyEvt_search_start,
  'search_result': _pyEvt_search_result,
  'search_error': _pyEvt_search_error,
  'download_start': _pyEvt_download_start,
  'file_start': _pyEvt_file_start,
  'file_progress': _pyEvt_file_progress,
  'file_complete': _pyEvt_file_complete,
  'task_paused': _pyEvt_task_paused,
  'task_retry': _pyEvt_task_retry,
  'download_complete': _pyEvt_download_complete,
  'download_error': _pyEvt_download_error,
  'history': _pyEvt_history,
  'settings': _pyEvt_settings,
  'tasks_snapshot': _pyEvt_tasks_snapshot,
  'pa_artist_dl_progress': _pyEvt_pa_artist_dl_progress,
  'pa_artist_dl_done': _pyEvt_pa_artist_dl_done,
  'pa_artist_dl_error': _pyEvt_pa_artist_dl_error,
  'media_proxy_ready': _pyEvt_media_proxy_ready,
  'media_url_resolved': _pyEvt_media_url_resolved,
  'thumbnails_cached': _pyEvt_thumbnails_cached,
  'cache_cleared': _pyEvt_cache_cleared,
  'log': _pyEvt_log,
  'backend_error': _pyEvt_backend_error,
  'pawchive_login_result': _pyEvt_pawchive_login_result,
  'exhentai_login_result': _pyEvt_exhentai_login_result,
  'twitter_login_result': _pyEvt_twitter_login_result,
  'xhamster_home_loading': _pyEvt_xhamster_home_loading,
  'xhamster_home': _pyEvt_xhamster_home,
  'xhamster_categories_loading': _pyEvt_xhamster_categories_loading,
  'xhamster_categories': _pyEvt_xhamster_categories,
  'xhamster_category_loading': _pyEvt_xhamster_category_loading,
  'xhamster_category': _pyEvt_xhamster_category,
  'xhamster_shorts_loading': _pyEvt_xhamster_shorts_loading,
  'xhamster_shorts': _pyEvt_xhamster_shorts,
  'xhamster_detail_loading': _pyEvt_xhamster_detail_loading,
  'xhamster_video_detail': _pyEvt_xhamster_video_detail,
  'xhamster_notifications_loading': _pyEvt_xhamster_notifications_loading,
  'xhamster_notifications': _pyEvt_xhamster_notifications,
  'xhamster_my_loading': _pyEvt_xhamster_my_loading,
  'xhamster_my': _pyEvt_xhamster_my,
  'xhamster_user_loading': _pyEvt_xhamster_user_loading,
  'xhamster_user_videos': _pyEvt_xhamster_user_videos,
  'xhamster_subscribe_result': _pyEvt_xhamster_subscribe_result,
  'xhamster_comment_result': _pyEvt_xhamster_comment_result,
  'xhamster_batch_progress': _pyEvt_xhamster_batch_progress,
  'xhamster_batch_done': _pyEvt_xhamster_batch_done,
  'iwara_login_result': _pyEvt_iwara_login_result,
  'iwara_site_changed': _pyEvt_iwara_site_changed,
  'iwara_home': _pyEvt_iwara_home,
  'iwara_home_loading': _pyEvt_iwara_home_loading,
  'iwara_follow_list': _pyEvt_iwara_follow_list,
  'iwara_follow_loading': _pyEvt_iwara_follow_loading,
  'iwara_friend_list': _pyEvt_iwara_friend_list,
  'iwara_friend_loading': _pyEvt_iwara_friend_loading,
  'iwara_user_profile': _pyEvt_iwara_user_profile,
  'iwara_follow_result': _pyEvt_iwara_follow_result,
  'iwara_video_detail': _pyEvt_iwara_video_detail,
  'iwara_detail_loading': _pyEvt_iwara_detail_loading,
  'iwara_comments': _pyEvt_iwara_comments,
  'iwara_batch_progress': _pyEvt_iwara_batch_progress,
  'iwara_batch_done': _pyEvt_iwara_batch_done,
  'hanime_login_result': _pyEvt_hanime_login_result,
  'hanime_proxy_set': _pyEvt_hanime_proxy_set,
  'pixiv_login_result': _pyEvt_pixiv_login_result,
  'pixiv_oauth_url': _pyEvt_pixiv_oauth_url,
  'pixiv_user_loading': _pyEvt_pixiv_user_loading,
  'pixiv_user_result': _pyEvt_pixiv_user_result,
  'pixiv_detail_loading': _pyEvt_pixiv_detail_loading,
  'pixiv_detail_result': _pyEvt_pixiv_detail_result,
  'pixiv_author_works': _pyEvt_pixiv_author_works,
  'pixiv_novel_images': _pyEvt_pixiv_novel_images,
  'pixiv_related_result': _pyEvt_pixiv_related_result,
  'pixiv_action_result': _pyEvt_pixiv_action_result,
  'pixiv_tags_result': _pyEvt_pixiv_tags_result,
  'pixiv_notification_result': _pyEvt_pixiv_notification_result,
  'pixiv_bookmark_tags_result': _pyEvt_pixiv_bookmark_tags_result,
  'pixiv_upload_result': _pyEvt_pixiv_upload_result,
  'pixiv_batch_progress': _pyEvt_pixiv_batch_progress,
  'pixiv_batch_done': _pyEvt_pixiv_batch_done,
  'pixiv_proxy_set': _pyEvt_pixiv_proxy_set,
  'hanime_home': _pyEvt_hanime_home,
  'hanime_home_loading': _pyEvt_hanime_home_loading,
  'hanime_video_detail': _pyEvt_hanime_video_detail,
  'hanime_detail_loading': _pyEvt_hanime_detail_loading,
  'hanime_comments': _pyEvt_hanime_comments,
  'hanime_comment_result': _pyEvt_hanime_comment_result,
  'hanime_save_result': _pyEvt_hanime_save_result,
  'hanime_user_videos': _pyEvt_hanime_user_videos,
  'hanime_user_loading': _pyEvt_hanime_user_loading,
  'hanime_batch_progress': _pyEvt_hanime_batch_progress,
  'hanime_batch_done': _pyEvt_hanime_batch_done,
  'oreno_proxy_set': _pyEvt_oreno_proxy_set,
  'oreno_home': _pyEvt_oreno_home,
  'oreno_home_loading': _pyEvt_oreno_home_loading,
  'oreno_list': _pyEvt_oreno_list,
  'oreno_list_loading': _pyEvt_oreno_list_loading,
  'oreno_tags': _pyEvt_oreno_tags,
  'oreno_tags_loading': _pyEvt_oreno_tags_loading,
  'oreno_characters': _pyEvt_oreno_characters,
  'oreno_chars_loading': _pyEvt_oreno_chars_loading,
  'oreno_authors': _pyEvt_oreno_authors,
  'oreno_authors_loading': _pyEvt_oreno_authors_loading,
  'oreno_fav_result': _pyEvt_oreno_fav_result,
  'oreno_video_detail': _pyEvt_oreno_video_detail,
  'oreno_detail_loading': _pyEvt_oreno_detail_loading,
  'oreno_batch_progress': _pyEvt_oreno_batch_progress,
  'oreno_batch_done': _pyEvt_oreno_batch_done,
  'asmr_login_result': _pyEvt_asmr_login_result,
  'asmr_proxy_set': _pyEvt_asmr_proxy_set,
  'asmr_list': _pyEvt_asmr_list,
  'move_task_folder_result': _pyEvt_move_task_folder_result,
  'reverse_start': _pyEvt_reverse_start,
  'reverse_site_update': _pyEvt_reverse_site_update,
  'reverse_all_done': _pyEvt_reverse_all_done,
  'reverse_cancelled': _pyEvt_reverse_cancelled,
  'reverse_error': _pyEvt_reverse_error,
  'reverse_download_start': _pyEvt_reverse_download_start,
  'reverse_download_done': _pyEvt_reverse_download_done,
  'reverse_download_error': _pyEvt_reverse_download_error,
  'reverse_paste': _pyEvt_reverse_paste,
  'reverse_proxy_set': _pyEvt_reverse_proxy_set,
  'asmr_list_loading': _pyEvt_asmr_list_loading,
  'asmr_video_detail': _pyEvt_asmr_video_detail,
  'asmr_related_extra': _pyEvt_asmr_related_extra,
  'pa_fav_result': _pyEvt_pa_fav_result,
  'gs_state': _pyEvt_gs_state,
  'asmr_detail_loading': _pyEvt_asmr_detail_loading,
  'asmr_circles': _pyEvt_asmr_circles,
  'asmr_tags': _pyEvt_asmr_circles,
  'asmr_vas': _pyEvt_asmr_circles,
  'asmr_circles_loading': _pyEvt_asmr_circles_loading,
  'asmr_tags_loading': _pyEvt_asmr_circles_loading,
  'asmr_vas_loading': _pyEvt_asmr_circles_loading,
  'asmr_fav_result': _pyEvt_asmr_fav_result,
  'asmr_batch_progress': _pyEvt_asmr_batch_progress,
  'asmr_batch_done': _pyEvt_asmr_batch_done,
  'login_info': _pyEvt_login_info,
  'account_saved': _pyEvt_account_saved,
  'account_error': _pyEvt_account_error,
  'exhentai_torrents': _pyEvt_exhentai_torrents,
  'exhentai_torrents_error': _pyEvt_exhentai_torrents_error,
  'exhentai_magnet': _pyEvt_exhentai_magnet,
  'exhentai_magnet_error': _pyEvt_exhentai_magnet_error,
  'ex_gallery_info': _pyEvt_ex_gallery_info,
  'ex_gallery_info_error': _pyEvt_ex_gallery_info_error,
  'bg_busy': _pyEvt_bg_busy,
  'ex_torrents_result': _pyEvt_ex_torrents_result,
  'ex_torrent_saved': _pyEvt_ex_torrent_saved,
  'pa_post_info': _pyEvt_pa_post_info,
  'pa_post_info_error': _pyEvt_pa_post_info_error,
  'pa_artist_posts': _pyEvt_pa_artist_posts,
  'pa_artist_posts_error': _pyEvt_pa_artist_posts_error,
  'ex_hidden_tags': _pyEvt_ex_hidden_tags,
  'search_history': _pyEvt_search_history,
  'translate_result': _pyEvt_translate_result,
  'translate_batch_result': _pyEvt_translate_batch_result,
  'github_update_info': _pyEvt_github_update_info,
  'changelog_info': _pyEvt_changelog_info,
  'update_download_progress': _pyEvt_update_download_progress,
  'update_download_done': _pyEvt_update_download_done,
  'update_download_error': _pyEvt_update_download_error,
  'update_installer_launched': _pyEvt_update_installer_launched,
  'github_update_marked': _pyEvt_github_update_marked,
  'local_favorites': _pyEvt_local_favorites,
  'local_favorites_saved': _pyEvt_local_favorites_saved,
  'local_favorites_error': _pyEvt_local_favorites_error,
  'twitter_follow_loading': _pyEvt_twitter_follow_loading,
  'twitter_follow_list': _pyEvt_twitter_follow_list,
  'twitter_browse_loading': _pyEvt_twitter_browse_loading,
  'twitter_browse_progress': _pyEvt_twitter_browse_progress,
  'twitter_user_feed_loading': _pyEvt_twitter_user_feed_loading,
  'twitter_user_feed': _pyEvt_twitter_user_feed,
  'twitter_user_feed_progress': _pyEvt_twitter_user_feed_progress,
  'twitter_export_progress': _pyEvt_twitter_export_progress,
  'twitter_export_done': _pyEvt_twitter_export_done,
  'twitter_browse_feed': _pyEvt_twitter_browse_feed,
  'twitter_cache_cleared': _pyEvt_twitter_cache_cleared,
  'twitter_follows': _pyEvt_twitter_follows,
  'twitter_follow_tags': _pyEvt_twitter_follow_tags,
  'twitter_follow_result': _pyEvt_twitter_follow_result,
  'download_rename_prompt': _pyEvt_download_rename_prompt,
  'site_login_result': _pyEvt_site_login_result,
  'javdb_detail_loading': _pyEvt_javdb_detail_loading,
  'javdb_video_detail': _pyEvt_javdb_video_detail,
  'javdb_batch_progress': _pyEvt_javdb_batch_progress,
  'javdb_batch_done': _pyEvt_javdb_batch_done,
  'javdb_tags_vocab': _pyEvt_javdb_tags_vocab,
  'javdb_hot_search': _pyEvt_javdb_hot_search,
  'javdb_directory': _pyEvt_javdb_directory,
}

function handlePythonEvent(event) {
  const h = PY_EVENT_HANDLERS[event && event.event]
  if (h) h(event)
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

// 判断输入是否为 xHamster 链接（任意子域的 xhamster.com 页面，走后端 xhamster_inspect）
function isXhamsterUrl(text) {
  return /^https?:\/\/([a-z0-9-]+\.)*xhamster\.com\//i.test((text || '').trim())
}

// 判断输入是否为 FC2 内容页链接（video.fc2.com/content/{id} 或 /a/content/{id}，走后端 fc2_inspect）
function isFc2Url(text) {
  return /^https?:\/\/([a-z0-9-]+\.)*fc2\.com\/(?:a\/)?content\/[0-9A-Za-z]{12,20}/i.test((text || '').trim())
}

// 判断输入是否为 JavDB 链接（javdb.com/v/{id} 详情页）
function isJavdbUrl(text) {
  return /javdb\.com\/(?:zh\/)?v\/[0-9a-zA-Z]+/i.test((text || '').trim())
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

// 判断输入是否为 Pixiv 链接（作品页 /artworks/{id} 或用户主页 /users/{id}）
function isPixivUrl(text) {
  return /^https?:\/\/(www\.)?pixiv\.net\/(?:en\/)?(artworks\/\d+|users\/\d+|member_illust\.php\?.*illust_id=\d+)/i.test((text || '').trim())
}

// 判断输入是否为 Oreno3D / EroMMDTube 视频链接（oreno3d.com/movies/xxx、erommdtube.com/movies/xxx）
function isOrenoUrl(text) {
  return /^https?:\/\/(www\.)?(oreno3d|erommdtube)\.com\/movies\/\d+/i.test((text || '').trim())
}

// 判断输入是否为 ASMR 音声作品链接（asmr-100.com / asmr.one 的 /work/xxx）
function isAsmrUrl(text) {
  return /^https?:\/\/(www\.)?(asmr-100|asmr)\.\w+\/work\/\d+/i.test((text || '').trim())
}

const siteNames = { bunkr: 'Bunkr', coomerst: 'Coomer', coomerfans: 'CoomerFans', fapello: 'Fapello', leakedzone: 'Leakedzone', coomer: 'Coomer', pawchive: 'Pawchive', exhentai: 'EX', twitter: 'X', iwara: 'Iwara', hanime: 'H站', pixiv: 'P站', oreno3d: 'O3D', erommdtube: 'E站', asmr: '音声' }
function siteNameOf(s) {
  return siteNames[s] || (s ? String(s) : '未知')
}

// 每站只提醒一次（本会话内）：切入站点时若已知登录失效/未登录，此时才提示
// （启动期的登录检查全部后台静默，不再打扰）
const loginWarnedSites = new Set()

// 切换站点（Bunkr / Coomer），清空当前结果并持久化设置
function updateSite(site) {
  settings.site = site
  // 用户主动切站时才做登录提醒（启动静默检查的结果只更新账号卡片）
  if (loginInfo.value[site] && loginInfo.value[site].logged_in === false
      && !loginWarnedSites.has(site)) {
    loginWarnedSites.add(site)
    message.warning(`${siteNameOf(site)} 未登录或登录已失效，可点左侧登录卡片重新登录`)
  }
  // 通用站点框架：切到配置驱动站点时若尚无状态，自动发首屏命令（GSV 工具条按钮的前置）
  if (gsConfigFor(site) && !gsStates.value[site]) {
    const homeBtn = (gsConfigFor(site).toolbar.buttons || []).find(b => b.cmd === 'home')
    if (homeBtn) handleGsCommand({ site, cmd: 'home', ...(homeBtn.args || {}) })
  }
  // 切换站点后清空旧站点的搜索结果与文件列表，避免混淆
  searchResults.value = []
  fileList.value = []
  cameFromSearch.value = false
  exInlineDetail.value = false
  exGalleryDetail.value = null
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
  if (isBunkrUrl(text) || isCoomerUrl(text) || isPawchiveUrl(text) || isExhentaiUrl(text) || isTwitterUrl(text) || isIwaraUrl(text) || isHanimeUrl(text) || isPixivUrl(text) || isOrenoUrl(text) || isAsmrUrl(text) || isJavdbUrl(text) || isXhamsterUrl(text) || isFc2Url(text)) {
    // 粘贴的是 Bunkr / Coomer / Pawchive / ExHentai / Twitter / Iwara / Hanime1 / Oreno3D / EroMMDTube / ASMR / JavDB / xHamster / FC2 链接，直接解析（后端按链接自动路由）
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
  // 新搜索：清当前站链式详情快照（返回链以新搜索结果为界）
  if (settings.site) {
    detailSnapClear(settings.site)
    if (settings.site === 'oreno3d' || settings.site === 'erommdtube') detailSnapClear('oreno')
  }
  // 搜索时退出下载管理面板与文件收集锁定视图——此前在下载/文件列表界面
  // 搜索后结果区被面板挡住（RightPanel v-show="!detailVisible"），看起来"无法搜索跳转"
  if (detailVisible.value) detailVisible.value = false
  batchFileCollected.value = false
  // 搜索时退出 EX 画廊详情/内联详情/收藏视图（EX 详情覆盖搜索结果区，搜了"没反应"）
  if (settings.site === 'exhentai') {
    exGalleryDetail.value = null
    exInlineDetail.value = false
    exFavMode.value = false
    exPopularMode.value = false
  }
  paHomeMode.value = false   // 新搜索退出 PA 主页模式（翻页不再走主页命令）
  if (page === 1) {
    searchResults.value = []
    searchPage.value = 1
    lastSearchKeyword.value = query
    // 新搜索：退出 EX 内联详情模式（详情区让位给新结果）
    exInlineDetail.value = false
    exGalleryDetail.value = null
    // 新搜索：清空旧译文，避免上一搜索的标题译文错位
    translatedTitles.value = {}
    // 新搜索：清空 EX 批量母文件夹，避免误套用
    exBatchParentFolder.value = ''
  }
  // 通用站点框架：全局搜索框路由到站点 gs 搜索（GSV 列表渲染，不进通用搜索结果区）
  if (gsConfigFor(settings.site || '')) {
    searching.value = false
    handleGsCommand({ site: settings.site, cmd: 'search', query, page })
    return
  }
  // 退出 X 关注视图 / Iwara 主页等视图，展示搜索结果
  twFollowMode.value = ''
  twFollowItems.value = []
  iwView.value = ''
  haView.value = ''
  orView.value = ''
  asmrView.value = ''
  xhView.value = ''   // xHamster 浏览视图让位给搜索结果
  // Pixiv：搜索时退出用户页/详情视图，翻页走搜索命令（不走 feed 翻页）
  pixivState.view = ''
  pixivListCtx.mode = ''
  pixivActiveFeed.value = ''
  pixivListCtx.feedKind = ''   // 搜索结果的 feed_kind 为空，清空期望值防误杀
  exFavMode.value = false
  exGalleryDetail.value = null
  paPostDetail.value = null
  paArtistPosts.value = null
  javdbDetail.value = null
  javdbListCtx.mode = ''
  javdbListCtx.url = ''
  javdbListCtx.label = ''
  javdbDir.kind = ''    // 新搜索退出目录浏览视图
  const options = JSON.parse(JSON.stringify(settings))
  // JavDB：附带搜索类型（影片/演员/系列/片商/导演/番号/标签 → f= 参数）
  if ((settings.site || 'bunkr') === 'javdb') options.javdb_field = javdbSearchField.value
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
  // PA 主页模式：翻页走主页命令（全站最新帖子流）
  if ((settings.site || 'bunkr') === 'pawchive' && paHomeMode.value && !lastSearchKeyword.value) {
    handlePawchiveHome(target)
    return
  }
  // Pixiv feed/收藏/关注粉丝列表模式：翻页走对应命令（收藏为 next_url 游标分页，页码顺序前进）
  if ((settings.site || 'bunkr') === 'pixiv' && pixivListCtx.mode) {
    if (pixivListCtx.mode === 'feed') {
      window.api.sendCommand({ cmd: 'pixiv_feed', kind: pixivListCtx.kind, page: target })
    } else if (pixivListCtx.mode === 'bookmarks') {
      window.api.sendCommand({
        cmd: 'pixiv_bookmarks', content: pixivListCtx.content,
        restrict: pixivListCtx.restrict, allow_r18: pixivListCtx.allow_r18,
        page: target, user_id: pixivListCtx.user_id,
      })
    } else if (pixivListCtx.mode === 'userlist') {
      window.api.sendCommand({
        cmd: 'pixiv_user_list', mode: pixivListCtx.umode,
        user_id: pixivListCtx.user_id, page: target,
      })
    } else {
      pixivListCtx.mode = ''
    }
    return
  }
  // JavDB 首页/演员/通用列表模式：翻页走对应命令（非搜索命令）
  if ((settings.site || 'bunkr') === 'javdb' && javdbListCtx.mode) {
    if (javdbListCtx.mode === 'home') {
      window.api.sendCommand({ cmd: 'javdb_home', page: target })
    } else if (javdbListCtx.mode === 'url') {
      window.api.sendCommand({
        cmd: 'javdb_open_url', url: javdbListCtx.url,
        label: javdbListCtx.label || '', page: target,
      })
    } else {
      window.api.sendCommand({ cmd: 'javdb_actor', url: javdbListCtx.url, page: target })
    }
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
  // Pixiv 小说格式选择（详情"下载小说（txt/word）"下拉设置），handleInspect 发命令时取用
  pixivNovelFmtOverride.value = item._novel_fmt || ''
  // 解析媒体时退出 Iwara 视图（主页/详情），展示文件列表
  iwView.value = ''
  iwDetail.value = null
  iwComments.value = []
  // 解析媒体时退出 Hanime1 / Oreno3D 视图，展示文件列表
  haView.value = ''
  haDetail.value = null
  orView.value = ''
  orDetail.value = null
  // 解析媒体时退出 xHamster 浏览视图，展示文件列表
  xhView.value = ''
  xhDetail.value = null
  xhComments.value = []
  // 解析媒体时退出 X 关注/浏览视图，展示文件列表
  twFollowMode.value = ''
  twViewUser.value = null
  twNavStack.value = []
  handleInspect()
}

// 解析反馈：点击瞬间立即进入"解析中"（乐观更新，不等后端 inspect_start 事件），
// 并挂看门狗防止后端无响应导致 loading 卡死
function armInspectWatchdog(ms) {
  clearTimeout(inspectWatchdog)
  inspectWatchdog = setTimeout(() => {
    if (inspecting.value) {
      inspecting.value = false
      addLog('错误', '解析超时（后端长时间无响应），请检查网络或代理后重试')
      message.error('解析超时：后端长时间无响应，请检查网络/代理后重试')
    }
  }, ms)
}

function beginInspectFeedback() {
  inspecting.value = true
  inspectProgress.current = 0
  inspectProgress.total = 0
  armInspectWatchdog(120000)
}

// 搜索看门狗：search_start 后 90s 无 result/error 时解除转圈（后端静默兜底）
function armSearchWatchdog(ms = 90000) {
  clearTimeout(searchWatchdog)
  searchWatchdog = setTimeout(() => {
    if (searching.value) {
      searching.value = false
      addLog('错误', '搜索超时（后端长时间无响应）')
      message.error('搜索超时：后端长时间无响应，请重试')
    }
  }, ms)
}

function handleInspect() {
  console.log('[App] 点击解析, url =', url.value)
  if (!url.value.trim()) return
  if (!window.api) {
    console.error('[App] window.api 未定义！')
    addLog('错误', 'window.api 未定义，preload 可能未加载')
    return
  }
  // EX 批量解析进行中：单个 inspect 的 inspect_complete 会被误计入批量计数、
  // 文件混入批量收集列表（原 handleExOpenGallery 内的同款保护，点开画廊改为仅查看后移到这里）
  if (exBatchDownloading.value || exBatchPending.value > 0) {
    message.info('批量解析进行中，请等批量结束后再解析（画廊详情仍可点开浏览）')
    return
  }
  fileList.value = []
  beginInspectFeedback()
  // URL 解析也标记来自搜索视图（文件列表显示"返回"按钮，可清空文件列表回主页）
  cameFromSearch.value = true
  // 用户主动解析 → 解锁批量收集的视图锁定（显示文件列表）
  batchFileCollected.value = false
  // 单次解析（非批量）：清空 EX 批量母文件夹，避免误套用到本次下载
  exBatchParentFolder.value = ''
  // reactive 对象是 Proxy，无法被 IPC 克隆，必须先转成纯对象
  const options = JSON.parse(JSON.stringify(settings))
  // Pixiv 小说格式一次性覆盖（txt/docx）
  if (pixivNovelFmtOverride.value) {
    options.pixiv_novel_fmt = pixivNovelFmtOverride.value
    pixivNovelFmtOverride.value = ''
  }
  console.log('[App] 发送 inspect 命令')
  window.api.sendCommand({
    cmd: 'inspect',
    url: url.value.trim(),
    options,
  })
}

async function handleDownload(selectedItems, opts = {}) {
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
    // 批量自动提交（opts.fromBatch）时 album_name 传空：让后端从文件列表取画师名作目录，
    // 避免多画廊混合任务顶层目录错用"最后一个解析的画廊标题"
    // opts.album_name 可显式指定任务名（如 X 博主内容流一键下载用博主名）
    album_name: opts.album_name ?? (opts.fromBatch ? '' : (albumInfo.album_name || '')),
    album_id: opts.fromBatch ? undefined : (albumInfo.album_id || undefined),
  })
  // 通用反馈：提交后马上提示（下载管理面板会自动收到任务快照）
  message.success(`任务已提交（${plainItems.length} 个文件）`)
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

// 右键菜单"下载此项"：静默添加单个文件到下载任务（不弹确认框、不切换视图）
async function handleCtxDownloadFile(file) {
  if (!file || !window.api) return
  addLog('下载', `右键下载: ${file.filename || file.item_page || ''}`)
  const plainItems = [JSON.parse(JSON.stringify(file))]
  const options = JSON.parse(JSON.stringify(settings))
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

function handleClearCache() {
  if (!window.api) {
    addLog('错误', 'window.api 未定义，preload 可能未加载')
    return
  }
  window.api.sendCommand({ cmd: 'clear_cache' })
}

// 清除批量任务：一键清空批量收集的文件列表 + 复位批量状态 + 解锁视图
// （不影响已提交的下载任务和已下载的文件；批量解析进行中不可清除）
function handleClearBatchTasks() {
  if (exBatchDownloading.value || exBatchPending.value > 0) {
    message.warning('批量解析进行中，请等待完成后再清除')
    return
  }
  const n = fileList.value.length
  fileList.value = []
  batchFileCollected.value = false
  cameFromSearch.value = false
  exBatchPending.value = 0
  exBatchDownloading.value = false
  exGalleryDetail.value = null
  exInlineDetail.value = false
  message.success(`已清除批量任务（${n} 个文件）。下载任务不受影响，可在"下载状态"查看`)
  addLog('系统', `清除批量任务：清空 ${n} 个已收集文件，解锁视图`)
}

function handleBackToSearch() {
  // 清空文件列表，返回搜索结果视图
  fileList.value = []
  cameFromSearch.value = false
  // 解锁批量收集视图锁定（用户主动返回）
  batchFileCollected.value = false
  // 同步清理各站点详情/子项目视图（避免回退后被旧详情卡住看不到搜索结果）
  exGalleryDetail.value = null
  exDetailLoading.value = false
  exInlineDetail.value = false
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
  setLoginLoading('pawchive', true)
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

// 通用站点命令上行（模块化契约：{site, cmd, ...payload} → `${site}_${cmd}` 发后端）
let lastFc2Cookies = ''
// FC2 分区 cookie 同步开关：只有后端报 NEED_LOGIN 后才允许从分区拉 cookie 推给后端。
// 此前每条命令前置同步——重启后会把分区里冻结的旧会话倒灌覆盖后端 restore 出的新会话
//（FC2 服务端轮换会话后旧快照已作废），导致反复要求重新登录。
let fc2NeedCookieSync = false
// FC2 多级返回：把上一推入视图的状态快照写回站点状态（Fc2View 保存的不可变快照恢复）
function handleGsRestoreState(payload) {
  if (!payload || payload.site !== 'fc2' || !payload.state) return
  gsStates.value = { ...gsStates.value, fc2: payload.state }
}

async function handleGsCommand(evt) {
  if (!window.api || !evt || !evt.site || !evt.cmd) return
  const { site, cmd, ...payload } = evt
  // 通用框架：卡片 item 可能是 Vue 响应式 Proxy——JSON.stringify 能通过但 IPC
  // structuredClone 依然拒绝（"object could not be cloned"，命令静默丢失），
  // 必须无条件深拷贝成纯对象再发
  const safePayload = JSON.parse(JSON.stringify(payload))
  // FC2：需要登录的内容 → 直接打开内置浏览器登录弹窗（不发给后端）
  if (site === 'fc2' && cmd === 'open-login') {
    handleSiteOAuthLogin('fc2')
    return
  }
  // FC2：仅在后端报 NEED_LOGIN 后同步分区 cookie（正常时后端受控 dict 自转并回写账号档案，
  // 每命令前置同步反而会在重启后把分区旧会话倒灌覆盖后端 restore 的新会话 → 反复要求重登）
  if (site === 'fc2' && fc2NeedCookieSync && window.api.siteGetCookies) {
    fc2NeedCookieSync = false
    try {
      const r = await window.api.siteGetCookies('fc2')
      if (r && r.ok && r.count > 3 && r.cookieStr && r.cookieStr !== lastFc2Cookies) {
        lastFc2Cookies = r.cookieStr
        window.api.sendCommand({ cmd: 'fc2_set_cookies', cookie_str: r.cookieStr })
        await new Promise(res => setTimeout(res, 400))  // 等后端应用 cookie（同队列 FIFO 保序）
      }
    } catch (e) { /* 刷新失败不阻塞命令 */ }
  }
  window.api.sendCommand({ cmd: `${site}_${cmd}`, ...safePayload })
}

// 通用返回（多层）：弹出站点视图栈并恢复上一层视图；栈空回落该站主页。
// 覆盖 iwara / asmr（视图状态可由现有 handler 恢复）；其余站维持各自返回逻辑。
function handleSiteBack(site) {
  const prev = navPopView(site)
  if (site === 'iwara') {
    if (prev === 'following') { handleIwFollowing(1); return }
    if (prev === 'friends') { handleIwFriends(1); return }
    handleIwHome(1)
    return
  }
  if (site === 'asmr') {
    if (prev === 'favorites') { handleAsmrFavorites(1); return }
    if (prev === 'works') { handleAsmrWorks(1); return }
    handleAsmrPopular(1)
    return
  }
}

// 回到站点起点（清空视图栈 + 搜索上下文，回到该站主页内容流）
const SITE_BACK_ROOT_SITES = ['iwara', 'asmr', 'xhamster', 'hanime1', 'oreno']
function handleSiteBackRoot(site) {
  navClearView(site)
  cameFromSearch.value = false
  searchQuery.value = ''
  searchResults.value = []
  fileList.value = []
  if (site === 'iwara') { handleIwHome(1); return }
  if (site === 'asmr') { handleAsmrPopular(1); return }
  if (site === 'xhamster') { handleXhTab('home'); return }
  if (site === 'hanime1') { handleHaHome(); return }
  if (site === 'oreno') { handleOrHome(1); return }
}

// PA 关注/取关画师（kemono API）
function handlePaFavToggle(payload) {
  if (!window.api || !payload || !payload.user_id) return
  window.api.sendCommand({
    cmd: 'pawchive_favorite',
    service: payload.service,
    user_id: payload.user_id,
    unfavorite: !!payload.favorited,
  })
}

function handlePawchiveFavorites(favType) {
  if (!window.api) return
  // 清空当前列表，以"我的收藏"作为搜索结果展示
  searchQuery.value = ''
  fileList.value = []
  cameFromSearch.value = false
  searchResults.value = []
  searching.value = true
  paHomeMode.value = false
  window.api.sendCommand({ cmd: 'pawchive_favorites', fav_type: favType === 'post' ? 'post' : 'creator' })
}

// PA 主页模式（全站最新帖子流，支持翻页）
const paHomeMode = ref(false)

function handlePawchiveHome(page = 1) {
  if (!window.api) return
  searchQuery.value = ''
  fileList.value = []
  cameFromSearch.value = false
  searchResults.value = []
  searching.value = true
  paHomeMode.value = true
  window.api.sendCommand({ cmd: 'pawchive_home', page: Math.max(1, Math.floor(Number(page) || 1)) })
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
    if (isBunkrUrl(query) || isCoomerUrl(query) || isPawchiveUrl(query) || isExhentaiUrl(query) || isTwitterUrl(query) || isIwaraUrl(query) || isHanimeUrl(query) || isPixivUrl(query) || isOrenoUrl(query) || isAsmrUrl(query)) {
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
  const engine = settings.translate_engine || 'google_free'
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

// 翻译开关（右侧缩小版 🌐 按钮）：
// 开 → 立即翻译当前页面全部内容，后续新增内容自动翻译（转圈动效表示进行中）
// 关 → 立即停止转圈并恢复原文（未完成的翻译结果到达后丢弃）
function handleToggleAutoTranslateMode() {
  autoTranslateMode.value = !autoTranslateMode.value
  // 开关不持久化：每次启动默认关闭（用户手动点击才开启）
  if (autoTranslateMode.value) {
    handleAutoTranslate(autoTranslateTo.value)
  } else {
    // 关闭：立即停止转圈 + 清掉看门狗 + 恢复原文
    autoTranslating.value = false
    if (translateWatchdog) {
      clearTimeout(translateWatchdog)
      translateWatchdog = null
    }
    translateBatchGen += 1  // 让在途的翻译结果失效（关闭后不再回填）
    translatedTitles.value = {}
  }
}

// 看门狗：批量翻译发出后 45s 未返回强制停止转圈（防"一直转圈"）
let translateWatchdog = null
// 代际计数：关闭开关/重新开启时 +1，旧请求的迟到结果按代际丢弃
let translateBatchGen = 0

// 翻译当前页面所有标题（已翻译过的自动跳过，只翻译新增内容）
function handleAutoTranslate(toLang) {
  if (!window.api) return
  let titles = collectCurrentTitles()
  if (!titles.length) return
  // 跳过已有译文的标题（翻页/加载更多时只翻译新增部分）
  titles = titles.filter(t => !(t in translatedTitles.value))
  if (!titles.length) return
  autoTranslating.value = true
  const batchId = `auto_${Date.now()}`
  // 45s 看门狗：后端快速失败策略下最长 ~40s（Google 3×6s + MyMemory 兜底），超时即停转圈
  if (translateWatchdog) clearTimeout(translateWatchdog)
  translateWatchdog = setTimeout(() => {
    if (autoTranslating.value) {
      autoTranslating.value = false
      message.warning('翻译超时已停止（Google 端点不可达且兜底未响应）。可在左侧翻译面板配置代理后重试')
    }
    translateWatchdog = null
  }, 45000)
  translateBatchPending.set(batchId, { titles, gen: translateBatchGen })
  window.api.sendCommand({
    cmd: 'translate_batch',
    texts: titles,
    from: 'auto',
    to: toLang || autoTranslateTo.value || 'zh-CN',
    batch_id: batchId,
  })
}

// 列表/搜索结果到达后：若翻译开关已开启，自动翻译新增内容（各站加载事件末尾调用）
function maybeAutoTranslateAfterSearch() {
  if (autoTranslateMode.value) handleAutoTranslate(autoTranslateTo.value)
}


// ============================
// P3 设置功能：快捷键 / 拟态模式
// ============================
// 快捷键变更：保存 settings + 通知主进程注册/注销。
// （2026-09-14 修复真凶：settings 是 reactive 对象不是 ref，`settings.value`
//   恒 undefined → 本函数曾在第一行直接 return——录入后从不保存、从不注册，
//   即"快捷键录制一直不可用"的根因）
// 通用代理（Pornhub / GitHub 更新共用）：保存并立即应用到 Pornhub webview 会话。
// 留空 = 默认 http://127.0.0.1:10809；填 off = 直连（用户挂 VPN 场景）
const COMMON_PROXY_DEFAULT = 'http://127.0.0.1:10809'
function handleCommonProxy(v) {
  const val = (v || '').trim()
  updateSettings({ common_proxy: val })
  const eff = (!val || val.toLowerCase() === 'off') ? val : (val.startsWith('http') || val.startsWith('socks') ? val : 'http://' + val)
  if (window.api) {
    window.api.siteSetProxy('pornhub', eff || 'http://127.0.0.1:10809').catch(() => {})
    window.api.sendCommand({ cmd: 'common_proxy', proxy: val })
  }
  addLog('系统', val ? `通用代理已更新：${eff}` : '通用代理已恢复默认（http://127.0.0.1:10809）')
}

// 手动抓取（资源嗅探）：打开独立全量窗口（内置浏览器 + 实时媒体捕获，复刻 res-downloader）
function handleSnifferOpen() {
  if (window.api && window.api.snifferOpen) window.api.snifferOpen()
}

// BT 下载：打开独立 BT 窗口（磁力链接批量粘贴 + .torrent 种子拖拽）
function handleBtOpen() {
  if (window.api && window.api.btOpen) window.api.btOpen()
}

// Leakedzone：Edge 过盾登录（真实浏览器引擎过 Turnstile；CDP 抓 Cookie+UA 保存）
function handleLeakEdgeLogin() {
  if (window.api && window.api.leakEdgeLogin) {
    message.info('正在打开专用 Edge 窗口…', 3000)
    window.api.leakEdgeLogin()
  }
}
function handleLeakEdgeHarvest() {
  if (window.api && window.api.leakEdgeHarvest) window.api.leakEdgeHarvest()
}


async function handleShortcutChange(action, accelerator) {
  updateSettings({ [`shortcut_${action}`]: accelerator || '' })
  if (!window.api || !window.api.registerShortcut) return
  try {
    const r = await window.api.registerShortcut(action, accelerator || '')
    if (r && r.ok === false) {
      // 注册失败（组合被系统/其它程序占用）：回滚设置并提示
      updateSettings({ [`shortcut_${action}`]: '' })
      addLog('错误', `快捷键注册失败：${r.error || '未知错误'}`)
      message.error(`快捷键注册失败：${r.error || '该组合可能已被其它程序占用'}`)
    } else if (accelerator) {
      addLog('系统', `快捷键已注册：${formatShortcutLog(accelerator)}`)
    }
  } catch { /* IPC 异常静默 */ }
}

// ============================
// 主界面模式（经典 ↔ 热门平台里模式）：切换手势为「连按 3 次单独 Alt」
// （setupTripleAltListener），界面上不展示任何切换按钮
// ============================
function formatShortcutLog(acc) {
  return String(acc || '').split('+').map(x => x.trim()).filter(Boolean).join(' + ')
}

// 启动时同步设置到主进程（注册全部快捷键）
function syncP3SettingsToMain() {
  if (!window.api || !settings) return
  const s = settings
  const actions = [
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
  // 通用代理（Pornhub / GitHub 更新共用）：留空 = 默认 http://127.0.0.1:10809
  const cp = s.common_proxy || 'http://127.0.0.1:10809'
  if (window.api.siteSetProxy) {
    window.api.siteSetProxy('pornhub', cp).catch(() => {})
  }
}

// 监听主进程触发的快捷键事件（部分动作需要前端处理）
function setupShortcutTriggeredListener() {
  if (!window.api || !window.api.onShortcutTriggered) return
  window.api.onShortcutTriggered((data) => {
    const action = data?.action
    if (action === 'toggle_float') {
      // 切换悬浮窗（复用现有 float_visible 设置）
      const next = !settings.float_visible
      updateSettings({ float_visible: next })
      if (next) {
        window.api.sendCommand({ cmd: 'get_tasks' })  // 触发悬浮窗刷新
      }
    }
  })
}

// ============================
// 连按 3 次单独 Alt（1.5 秒内）：切换 经典下载器 ↔ 热门平台 里模式
// （界面上不展示切换按钮，此为唯一入口；1.5 秒内三连，重复三连来回切换）
// ============================
let altTapTimes = []
let tripleAltInited = false
// ============================
// 登录转圈取消：网络不佳时后端登录结果迟迟不回，转圈永不复位导致「再也登不上」。
// ① 各登录按钮转圈旁提供「取消」（LeftPanel emit cancel-login）；
// ② 60 秒无响应自动复位兜底。取消/超时只复位前端等待，后端跑完的结果仍会照常刷账号卡。
// ============================
const loginLoadingRefs = {
  pawchive: pawchiveLoginLoading,
  iwara: iwaraLoginLoading,
  hanime: hanimeLoginLoading,
  pixiv: pixivLoginLoading,
  asmr: asmrLoginLoading,
}
const loginLoadingTimers = {}
const LOGIN_LOADING_TIMEOUT = 60000

function setLoginLoading(key, val) {
  const r = loginLoadingRefs[key]
  if (!r) return
  if (loginLoadingTimers[key]) {
    clearTimeout(loginLoadingTimers[key])
    loginLoadingTimers[key] = null
  }
  r.value = val
  if (val) {
    loginLoadingTimers[key] = setTimeout(() => {
      if (r.value) {
        r.value = false
        addLog('系统', '登录等待已超时自动取消（60 秒无响应，网络不佳），可重新点击登录')
      }
    }, LOGIN_LOADING_TIMEOUT)
  }
}

function handleCancelLogin(key) {
  setLoginLoading(key, false)
  addLog('系统', '已取消登录等待——后端仍会在后台尝试，登录结果稍后自动刷新到账号卡')
}

// 里/美好世界自定义标题栏：窗口控制 + 最大化状态（最大化时容器去圆角贴边）
const winMaxed = ref(false)

function winCtl(action) {
  window.api && window.api.winControl && window.api.winControl(action)
}

async function handleRestartApp() {
  addLog('系统', '正在重启应用……（重启后保持当前停留的世界）')
  try {
    if (window.api && window.api.restartApp) {
      await window.api.restartApp()
    }
  } catch (e) { /* 重启中进程退出，忽略 */ }
}

function toggleUiMode() {
  const next = !settings.ui_mode_hot
  updateSettings({ ui_mode_hot: next })
  // 美好世界 = 正常网站模式（白）；里世界 = 含 NSFW 内容的站点模式（黑）
  message.success(next ? '已切换到美好世界（正常网站模式）' : '已切换到里世界（NSFW 站点模式）')
  addLog('系统', next ? '三连Alt：进入美好世界（正常网站模式）' : '三连Alt：进入里世界（NSFW 站点模式）')
}
function setupTripleAltListener() {
  if (tripleAltInited) return
  tripleAltInited = true
  window.addEventListener('keydown', (e) => {
    const code = e.code || ''
    if (code !== 'AltLeft' && code !== 'AltRight' && e.key !== 'Alt') return
    // 仅统计"单独按 Alt"（同时按着其他修饰键的组合不算）
    if (e.ctrlKey || e.shiftKey || e.metaKey) return
    // 阻止 Alt 激活窗口菜单栏/标题栏快捷键
    e.preventDefault()
    const now = Date.now()
    altTapTimes = altTapTimes.filter(t => now - t < 1500)
    altTapTimes.push(now)
    if (altTapTimes.length < 3) return
    altTapTimes = []
    toggleUiMode()
  }, true)
}

// 关闭弹窗"记住我的选择"→ 主进程已写 settings.json，这里同步：
// ① 前端内存 settings（设置面板立即显示新值）；② Python 后端 set_setting 刷新缓存（防旧值覆盖）
function setupCloseActionListener() {
  if (!window.api || !window.api.onCloseActionChanged) return
  window.api.onCloseActionChanged((action) => {
    if (action !== 'tray' && action !== 'exit' && action !== 'ask') return
    settings.close_action = action
    window.api.sendCommand({ cmd: 'set_setting', key: 'close_action', value: action })
  })
}

// ============================
// GitHub 仓库更新检查（设置区）
// ============================
function handleCheckGithubUpdate() {
  if (!window.api) return
  githubChecking.value = true       // 显式 loading（请求失败/超时由后端事件复位）
  githubUpdateInfo.value = null    // 清空旧结果
  window.api.sendCommand({ cmd: 'check_github_update', current_version: appVersion.value || '' })
}

// 检查更新入口：先拉取发布仓库的更新日志弹窗展示（多版本可下滑浏览），用户点"更新"后再走下载流程
function handleFetchChangelog() {
  if (!window.api || changelogLoading.value) return
  changelogLoading.value = true
  changelogInfo.value = null
  window.api.sendCommand({ cmd: 'fetch_changelog', current_version: appVersion.value || '' })
}

// 更新日志弹窗"更新"按钮：有新版时走原更新检查+下载流程，无新版时仅提示
function handleChangelogConfirmUpdate() {
  changelogModalVisible.value = false
  if (changelogInfo.value?.has_new) {
    handleCheckGithubUpdate()
  } else {
    message.info(`当前已是最新版本 v${appVersion.value || changelogInfo.value?.current_version || ''}`)
  }
}

// 下载最新版安装包（后端流式下载到系统「下载」文件夹，进度通过 update_download_progress 事件推送）
function handleDownloadUpdate() {
  if (!window.api || updateDownload.downloading) return
  const assets = githubUpdateInfo.value?.release?.assets || []
  const asset = assets.find(a => a.url) || assets[0]
  if (!asset || !asset.url) {
    message.error('未找到安装包下载地址，请到仓库主页手动下载')
    return
  }
  // 复位下载状态
  updateDownload.downloading = true
  updateDownload.received = 0
  updateDownload.total = asset.size || 0
  updateDownload.percent = 0
  updateDownload.speed = 0
  updateDownload.fileName = asset.name || ''
  updateDownload.path = ''
  updateDownload.done = false
  updateDownload.error = ''
  window.api.sendCommand({ cmd: 'download_update', url: asset.url, file_name: asset.name || '' })
  addLog('系统', `开始下载更新安装包: ${asset.name || asset.url}`)
}

// 运行已下载的更新安装包（NSIS 覆盖安装即更新）
function handleInstallUpdate() {
  if (!window.api || !updateDownload.path) return
  window.api.sendCommand({ cmd: 'open_update_installer', path: updateDownload.path })
  addLog('系统', `已运行更新安装包: ${updateDownload.path}（按提示覆盖安装，data 数据不会丢失）`)
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
// 点开仅查看详情（封面/元数据/标签），不再自动解析下载；
// 下载走详情里的「解析图片列表」按钮或工具栏批量下载（显式动作）
// 注意参数名用 galleryUrl 而非 url，避免遮蔽（shadow）外层 url ref 导致 url.value = url 自赋值
// EX 首页推荐（与主站 exhentai.org 首页相同的最新画廊列表）
function handleExPopular(page = 1) {
  if (!window.api) return
  exFavMode.value = false
  exPopularMode.value = true
  pixivState.view = '' // 防御：退出其他站视图态
  searching.value = false
  window.api.sendCommand({ cmd: 'exhentai_popular', page })
}

function handleExOpenGallery(galleryUrl) {
  if (!window.api || !galleryUrl) return
  // 同步 URL 栏 + 标记来自搜索（"后退"按钮可用，回到搜索结果）
  url.value = galleryUrl
  searchQuery.value = galleryUrl
  cameFromSearch.value = true
  // 统一逻辑：点开画廊 = 新开详情界面（封面/画师/tag + 图片预览），自动解析出图；← 后退回列表
  // （搜索结果与我的收藏行为一致；不再使用内联追加模式）
  exInlineDetail.value = false
  exAutoParseGallery.value = true
  // 退出其他站点视图，进入 EX 详情视图
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
  // 批量解析进行中也允许点开查看详情（只有单个解析会被拦）
  exDetailLoading.value = true
  window.api.sendCommand({ cmd: 'exhentai_gallery_info', url: galleryUrl })
  // 详情视图的显示条件是 fileList 为空：清掉旧文件列表并解锁批量视图锁定
  // （此前点开自动解析时也会清空，行为保持一致）
  if (fileList.value.length) {
    fileList.value = []
    batchFileCollected.value = false
  }
}

// EX 批量下载：把多个画廊的全部图片解析后追加到 fileList，统一勾选下载
async function handleExBatchDownload(urls) {
  if (!window.api || !Array.isArray(urls) || !urls.length) return
  // 弹出母文件夹命名弹窗：默认填入当前搜索词，用户可修改/留空
  batchFolderContext.value = 'ex'
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

  // JavDB 批量下载：确认后走 javdb 专用批量命令（逐个解析详情，每个视频一个下载任务）
  if (batchFolderContext.value === 'javdb') {
    const options = JSON.parse(JSON.stringify(settings))
    if (exBatchParentFolder.value) options.batch_parent_folder = exBatchParentFolder.value
    javdbBatchRunning.value = true
    javdbBatchProgress.done = 0
    javdbBatchProgress.total = urls.length
    const tip = exBatchParentFolder.value ? `母文件夹「${exBatchParentFolder.value}」，` : ''
    message.info(`开始批量解析 ${urls.length} 个视频，${tip}封面与预览图将逐个加入下载任务`)
    window.api.sendCommand({ cmd: 'javdb_batch_download', urls, options })
    return
  }

  // 后台批量：不切换视图（用户留在搜索结果页可继续浏览/翻页），解析结果静默收集进 fileList
  cameFromSearch.value = false
  // 视图锁定：批量收集期间与完成后都不自动切到文件列表（完全静默后台下载）
  batchFileCollected.value = true
  // 清空 fileList（后台解析模式，避免与旧文件列表混在一起）
  fileList.value = []
  exGalleryDetail.value = null
  exInlineDetail.value = false
  exBatchDownloading.value = true
  exBatchPending.value = urls.length
  exBatchTotal.value = urls.length
  const tip = exBatchParentFolder.value
    ? `母文件夹「${exBatchParentFolder.value}」，`
    : ''
  message.info(`后台批量解析 ${exBatchPending.value} 个画廊，${tip}完成后自动下载（可继续浏览其他页面）`)
  const options = JSON.parse(JSON.stringify(settings))
  // 顺序解析（并发会触发 EX 限流 509）；解析结果会通过 inspect_complete 累加进 fileList
  exBatchCancelled.value = false
  for (const u of urls) {
    if (exBatchCancelled.value) break  // 用户点了「取消批量」：剩余画廊不再派发
    if (!u) continue
    url.value = u
    window.api.sendCommand({ cmd: 'inspect', url: u, options })
    // 间隔 1.5s 防 509
    await new Promise(r => setTimeout(r, 1500))
  }
  // 取消时：已派发的等返回后按 cancelled 收尾（不自动下载）；一个都没派发则立即收尾
  if (exBatchCancelled.value && exBatchPending.value === 0) {
    finishExBatch(true)
    return
  }
  // 注：exBatchPending 异步递减；全部完成后 inspect_complete handler 内自动提交下载任务
  addLog('系统', `后台批量解析请求已派发（${exBatchPending.value} 个画廊待返回）`)
}

// 批量解析收尾（inspect_complete / inspect_error / 取消共用）：cancelled=true 不自动下载
function finishExBatch(cancelled) {
  exBatchDownloading.value = false
  exBatchCancelled.value = false
  const selected = fileList.value.filter(it => it.selected)
  if (cancelled) {
    addLog('系统', `批量解析已取消，共收集 ${fileList.value.length} 个文件（未自动下载）`)
    message.info(`批量解析已取消，已收集 ${fileList.value.length} 个文件，可点「查看收集的文件」勾选后手动下载`)
    return
  }
  if (selected.length) {
    addLog('系统', `后台批量解析完成，自动开始下载 ${selected.length} 个文件`)
    message.success(`批量解析完成，已自动开始下载 ${selected.length} 个文件（失败项会在任务结束后生成清单）`)
    handleDownload(selected, { fromBatch: true })
  } else {
    message.warning('批量解析完成，但没有可下载的文件')
  }
}

// 取消 EX 批量解析：中止剩余派发；已派发的等返回后收尾（不自动下载）
function handleExBatchCancel() {
  if (!exBatchDownloading.value) return
  exBatchCancelled.value = true
  message.info('正在取消批量解析：已发出的请求会完成，剩余画廊不再解析')
  addLog('系统', '用户取消批量解析：停止派发剩余画廊')
}

function handleExCloseDetail() {
  exGalleryDetail.value = null
  exInlineDetail.value = false
}

// 查看批量收集的文件：解锁视图锁定，回文件列表（可对单个文件勾选/取消后再下载）
// cameFromSearch=true 让文件列表显示「后退」按钮（标题为"清空文件列表返回"，返回会丢弃预览列表，
// 不影响已提交的下载任务）
function handleShowCollectedFiles() {
  if (!fileList.value.length) return
  batchFileCollected.value = false
  exInlineDetail.value = false
  cameFromSearch.value = true
  addLog('系统', `查看批量收集的文件：共 ${fileList.value.length} 个（可单独勾选/取消后点下载）`)
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

// PA 右键"下载画师所有内容"：后台解析画师全部帖子并直接提交下载任务
function handlePaDownloadArtist(payload) {
  const artistUrl = payload?.url || payload
  if (!window.api || !artistUrl) return
  const options = JSON.parse(JSON.stringify(settings))
  window.api.sendCommand({
    cmd: 'pawchive_download_artist',
    url: artistUrl,
    options,
  })
  message.info('正在后台解析画师全部内容，完成后自动开始下载...')
  addLog('PA', `右键下载画师所有内容: ${payload?.name || artistUrl}`)
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
    message.info('已打开登录页（推荐直接使用左侧"打开内置浏览器登录"按钮，登录后点"确认"自动抓取）')
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
  else if (['xhamster', 'pornhub', 'xvideos', 'oreno3d', 'erommdtube', 'fc2', 'javdb', 'leakedzone'].includes(site)) window.api.sendCommand({ cmd: `${site}_check_login`, notify: true })
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
  setLoginLoading('iwara', true)
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
  navPushView('iwara', 'home')
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
  navPushView('iwara', 'following')
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
  navPushView('iwara', 'friends')
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
  // 链式详情：快照当前详情，返回时逐级恢复
  if (iwView.value === 'detail' && iwDetail.value) {
    detailSnapPush('iwara', { detail: iwDetail.value, comments: iwComments.value })
  }
  window.api.sendCommand({ cmd: 'iwara_video_detail', video_id: videoId })
}

// 关闭视频详情（先弹链式详情快照逐级恢复；弹空后走历史栈/兜底）
function handleIwDetailBack() {
  const snap = detailSnapPop('iwara')
  if (snap) { iwDetail.value = snap.detail; iwComments.value = snap.comments; return }
  if (detailFromSearch.value === 'iwara') { detailFromSearch.value = ''; iwView.value = ''; iwDetail.value = null; iwComments.value = []; return }
  const prev = navPopView('iwara')
  if (prev) iwView.value = prev
  else iwView.value = iwHomeItems.value.length ? 'home' : ''
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
  // 批量任务已提交：自动打开下载管理面板（后台任务可视化，防"没反应"体感）
  if (!detailVisible.value) {
    detailVisible.value = true
    message.info('批量下载任务已提交，已为你打开下载管理')
  }
}

// ============================
// xHamster 浏览视图：底部 Tab（首页/分类/短视频/消息/我的）+ 详情/用户/分类列表
// ============================
// 底部 Tab 切换（进入对应视图；无缓存数据时拉取第一页）
function handleXhTab(tab) {
  if (!window.api) return
  navPushView('xhamster', tab)
  xhTab.value = tab
  xhView.value = tab
  if (tab === 'home') {
    if (!xhHomeItems.value.length) handleXhHome(1, xhHomeSort.value)
  } else if (tab === 'categories') {
    if (!xhCatsTrending.value.length && !xhCatsGroups.value.length) {
      window.api.sendCommand({ cmd: 'xhamster_categories' })
    }
  } else if (tab === 'shorts') {
    if (!xhShortsItems.value.length) {
      window.api.sendCommand({ cmd: 'xhamster_shorts', page: 1 })
    }
  } else if (tab === 'notifications') {
    window.api.sendCommand({ cmd: 'xhamster_notifications' })
  } else if (tab === 'my') {
    if (!xhMyItems.value.length) handleXhMy(xhMyTab.value, 1)
  }
}

// 分类目录刷新（进入或手动刷新）
function handleXhOpenCategories() {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'xhamster_categories' })
}

// 短视频刷新（清空重载第 1 页）
function handleXhShortsReload() {
  if (!window.api) return
  xhShortsItems.value = []
  window.api.sendCommand({ cmd: 'xhamster_shorts', page: 1 })
}

// 消息中心刷新（未登录时后端提示去登录）
function handleXhNotifications() {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'xhamster_notifications' })
}

// 首页（page 1 换排序时清空旧内容）
function handleXhHome(page = 1, sort = xhHomeSort.value) {
  if (!window.api) return
  xhView.value = 'home'
  xhTab.value = 'home'
  if (page <= 1 || sort !== xhHomeSort.value) xhHomeItems.value = []
  xhHomeSort.value = sort
  if (page <= 1) searchResults.value = []
  window.api.sendCommand({ cmd: 'xhamster_home', page, sort })
}

function handleXhHomeMore() {
  handleXhHome(xhHomePage.value + 1, xhHomeSort.value)
}

// 首页排序切换（新着/最多播放/最高评分）
function handleXhHomeSort(sort) {
  if (sort === xhHomeSort.value) return
  handleXhHome(1, sort)
}

// 点分类进入列表（slug + 名称）
function handleXhOpenCategory(cat) {
  if (!window.api || !cat) return
  xhCatSlug.value = cat.slug || cat.id || ''
  xhCatName.value = cat.name || xhCatSlug.value
  if (!xhCatSlug.value) return
  navPushView('xhamster', 'category')
  xhView.value = 'category'
  xhCatItems.value = []
  xhCatPage.value = 1
  window.api.sendCommand({ cmd: 'xhamster_category', slug: xhCatSlug.value, page: 1 })
}

// 分类列表返回（历史栈上一步；栈空回分类 Tab）
function handleXhCatBack() {
  xhView.value = navPopView('xhamster') || 'categories'
  xhCatItems.value = []
}

function handleXhCatMore() {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'xhamster_category', slug: xhCatSlug.value, page: xhCatPage.value + 1 })
}

function handleXhShortsMore() {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'xhamster_shorts', page: xhShortsPage.value + 1 })
}

// 我的关注：直接加载关注用户列表
function handleXhMy(tab = 'favorites', page = 1) {
  if (!window.api) return
  xhView.value = 'my'
  xhTab.value = 'my'
  if (page <= 1 || tab !== xhMyTab.value) xhMyItems.value = []
  xhMyTab.value = tab
  window.api.sendCommand({ cmd: 'xhamster_my', tab, page })
}

function handleXhMyMore() {
  handleXhMy(xhMyTab.value, xhMyPage.value + 1)
}

// 打开视频详情（进入时由 xhamster_video_detail 事件入栈）
function handleXhOpenDetail(item) {
  if (!window.api || !item) return
  if (item.kind === 'user') {
    handleXhOpenUser(item.author || item.album_name)
    return
  }
  if (item.kind === 'gallery') {
    openSearchResult(item)
    return
  }
  // 链式详情（详情内相关推荐点开下一个）：快照当前详情，返回时逐级恢复；
  // xhDetailFrom 保留首级详情的来源（链式不覆盖，首级返回仍回正确列表）
  const chained = xhView.value === 'detail' && xhDetail.value
  if (chained) detailSnapPush('xhamster', { detail: xhDetail.value, comments: xhComments.value })
  if (!chained) xhDetailFrom.value = ['home', 'category', 'my', 'user'].includes(xhView.value) ? xhView.value : 'home'
  xhDetail.value = null
  xhDetailError.value = ''
  xhComments.value = []
  window.api.sendCommand({ cmd: 'xhamster_video_detail', page_url: item.album_url })
}

// 详情返回（先弹链式详情快照逐级恢复；弹空后走历史栈/搜索来源兜底）
function handleXhDetailBack() {
  const snap = detailSnapPop('xhamster')
  if (snap) { xhDetail.value = snap.detail; xhComments.value = snap.comments; xhDetailError.value = ''; return }
  if (detailFromSearch.value === 'xhamster') { detailFromSearch.value = ''; xhView.value = ''; xhDetail.value = null; xhComments.value = []; return }
  const prev = navPopView('xhamster')
  if (prev) {
    xhView.value = prev
  } else {
    xhView.value = xhDetailFrom.value === 'user' ? 'user' : (xhDetailFrom.value === 'category' ? 'category' : (xhDetailFrom.value === 'my' ? 'my' : 'home'))
  }
  xhDetail.value = null
  xhComments.value = []
}

// 查看用户主页视频列表（用户页互跳链：详情→作者A→…→作者B，返回逐级恢复）
function handleXhOpenUser(username) {
  if (!window.api || !username) return
  // 链式用户页（已在用户页又点进另一用户）：快照当前用户页上下文
  if (xhView.value === 'user' && xhUser.value) {
    detailSnapPush('xhamster_user', {
      user: xhUser.value, items: xhUserItems.value, page: xhUserPage.value,
      tab: xhUserTab.value, profile: xhUserProfile.value, hasMore: xhUserHasMore.value,
    })
  }
  navPushView('xhamster', 'user')
  xhUser.value = username
  xhUserItems.value = []
  xhUserPage.value = 1
  xhUserTab.value = 'videos'
  xhUserProfile.value = null
  xhView.value = 'user'
  window.api.sendCommand({ cmd: 'xhamster_user_videos', username, page: 1, tab: 'videos' })
}

// 用户主页返回（先弹用户页快照逐级恢复；弹空后走历史栈/详情兜底）
function handleXhUserBack() {
  const snap = detailSnapPop('xhamster_user')
  if (snap) {
    xhUser.value = snap.user
    xhUserItems.value = snap.items
    xhUserPage.value = snap.page
    xhUserTab.value = snap.tab
    xhUserProfile.value = snap.profile
    xhUserHasMore.value = snap.hasMore
    xhView.value = 'user'
    return
  }
  const prev = navPopView('xhamster')
  if (prev) xhView.value = prev
  else if (xhDetail.value) xhView.value = 'detail'
  else { xhView.value = 'home'; xhTab.value = 'home' }
}

function handleXhUserMore() {
  if (!window.api) return
  window.api.sendCommand({
    cmd: 'xhamster_user_videos',
    username: xhUser.value,
    page: xhUserPage.value + 1,
    tab: xhUserTab.value,
  })
}

function handleXhUserTab(tab) {
  if (!window.api || !xhUser.value) return
  xhUserTab.value = tab || 'videos'
  xhUserItems.value = []
  xhUserPage.value = 1
  window.api.sendCommand({
    cmd: 'xhamster_user_videos',
    username: xhUser.value,
    page: 1,
    tab: xhUserTab.value,
  })
}

function handleXhSubscribe(payload) {
  if (!window.api || !payload) return
  xhSubscribeLoading.value = true
  window.api.sendCommand({
    cmd: 'xhamster_subscribe',
    user_id: payload.user_id || '',
    username: payload.username || '',
    subscribe: payload.subscribe !== false,
  })
}

function handleXhAddComment(payload) {
  if (!window.api || !payload || !payload.text) return
  xhCommentSending.value = true
  window.api.sendCommand({
    cmd: 'xhamster_add_comment',
    entity_type: payload.entity_type || 'video',
    entity_id: payload.entity_id || '',
    text: payload.text,
    page_url: payload.page_url || '',
  })
}

// 点 tag / 分类搜索（走通用搜索命令）
function handleXhSearchTag(tag) {
  if (!tag) return
  searchQuery.value = tag
  handleSearch()
}

function handleXhSearch(query) {
  const q = (query || '').trim()
  if (!q) return
  searchQuery.value = q
  handleSearch()
}

// 批量下载（浏览区勾选的视频 URL 列表 → 后端逐个解析提交下载）
function handleXhBatchDownload(payload) {
  const items = Array.isArray(payload) ? payload : []
  const urls = items.map(it => (typeof it === 'string' ? it : it && it.album_url)).filter(Boolean)
  if (!window.api || !urls.length) return
  xhBatchRunning.value = true
  xhBatchProgress.done = 0
  xhBatchProgress.total = urls.length
  xhBatchProgress.message = '准备中...'
  try {
    window.api.sendCommand({
      cmd: 'xhamster_batch_download',
      urls,
      // 卡片是 Vue 响应式 Proxy，直接过 IPC 会 "An object could not be cloned"
      // → 命令发不出去且 xhBatchRunning 卡死转圈（2026-09-10 实锤），必须深拷贝
      items: JSON.parse(JSON.stringify(items.filter(it => it && typeof it === 'object'))),
      options: JSON.parse(JSON.stringify(settings)),
    })
  } catch (e) {
    xhBatchRunning.value = false
    xhBatchProgress.message = ''
    message.error(`批量下载命令发送失败：${e?.message || e}`)
    addLog('错误', `xHamster 批量下载命令发送失败: ${e?.message || e}`)
  }
  addLog('下载', `xHamster 批量下载：${urls.length} 个条目（按作者/视频|短视频|画廊 分目录）`)
  // 批量任务已提交：自动打开下载管理面板（后台任务可视化，防"没反应"体感）
  if (!detailVisible.value) {
    detailVisible.value = true
    message.info('批量下载任务已提交，已为你打开下载管理')
  }
}

// ============================
// Hanime1 登录 / 代理 / 主页 / 详情 / 用户中心
// ============================
function handleHanimeLogin(email, password) {
  if (!window.api || !email.trim() || !password) return
  setLoginLoading('hanime', true)
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

// Pixiv 登录（Refresh Token 方案，PKCE OAuth）：发 pixiv_oauth_start → 后端回推 pixiv_oauth_url
// → 打开 WebviewLoginModal（watchLoginUrl 动态加载 + codeRegex 拦截 pixiv://account/login?code=xxx）
function handlePixivLogin() {
  if (!window.api) return
  setLoginLoading('pixiv', true)
  // 先打开弹窗（等后端 pixiv_oauth_url 事件推 URL 进来重载）
  wvLogin.site = 'pixiv'
  wvLogin.loginUrl = ''
  wvLogin.homeUrl = 'https://www.pixiv.net/'
  wvLogin.partition = 'persist:pixiv'
  wvLogin.successPatterns = []
  wvLogin.captchaPatterns = [/challenge|captcha|recaptcha|turnstile|gotcha/i]
  wvLogin.credentials = null
  wvLogin.manualConfirm = false
  wvLogin.autoGrabPattern = null
  // 匹配登录成功后的两种回跳 URL（对齐 ZipFile/pixiv_auth 官方流程）：
  // ① https://app-api.pixiv.net/web/v1/users/auth/pixiv/callback?state=...&code=xxx（https 302，did-navigate 触发，首选）
  // ② pixiv://account/login?code=xxx（callback 页 JS 深链跳转，协议已被主进程接管，兜底）
  wvLogin.codeRegex = /app-api\.pixiv\.net\/web\/v1\/users\/auth\/pixiv\/callback\?.*?\bcode=([^&#\s]+)|pixiv:\/\/account\/login\?code=([^&#\s]+)/
  wvLogin.watchLoginUrl = true
  wvLogin.visible = true
  // webview 会话代理（国内必须走代理才能打开登录页；直连 app-api.pixiv.net 不通=白屏）。
  // 设置留空时兜底默认 10809（与后端 PIXIV_DEFAULT_PROXY 一致）；等代理落地后再发
  // oauth_start，避免 webview 先于代理加载导致白屏
  const pxProxy = settings.pixiv_proxy || 'http://127.0.0.1:10809'
  Promise.resolve(window.api.siteSetProxy('pixiv', pxProxy))
    .catch(() => {})
    .then(() => {
      window.api.sendCommand({ cmd: 'pixiv_oauth_start' })
    })
}

function handlePixivLogout() {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'pixiv_logout' })
}

// Pixiv 代理修改：保存设置 + 通知后端（国内必须走代理）
function handlePixivSetProxy(proxy) {
  updateSettings({ pixiv_proxy: proxy })
  if (window.api) {
    window.api.sendCommand({ cmd: 'pixiv_set_proxy', proxy: proxy || '' })
  }
}

// Pixiv 面板统一命令出口（PixivPanel emit → RightPanel 透传到这里集中处理：
// 视图切换在前端完成，数据命令发后端；返回时回上一层（用户页点进的作品回用户页））
function handlePixivCommand(e) {
  if (!window.api || !e || !e.cmd) return
  const cmd = e.cmd
  if (cmd === 'pixiv_set_search_type') {
    // 搜索三模式切换：插画/漫画 → 小说 → 用户
    settings.pixiv_search_type = e.type || 'illust'
    saveSettings()
    return
  }
  if (cmd === 'pixiv_tag_search') {
    // 点常用标签：记录频次 + 用该标签搜索（搜索模式沿用当前三模式设置）
    window.api.sendCommand({ cmd: 'pixiv_tag_click', tag: e.tag })
    searchQuery.value = e.tag
    searchPage.value = 1
    doSearch(e.tag, 1)
    return
  }
  if (cmd === 'pixiv_open_user') {
    // 打开用户主页（记录进入来源：详情返回时回列表或用户页）
    pixivState.detailFrom = pixivState.view
    pixivState.view = 'user'
    pixivState.userPage = null
    pixivState.userLoading = true
    window.api.sendCommand({ cmd: 'pixiv_user_page', user_id: e.user_id })
    return
  }
  if (cmd === 'pixiv_detail') {
    // 打开作品详情（插画多页原图 / 小说正文）
    // 链式详情（详情内相关作品点开下一个）：快照当前详情，返回时逐级恢复
    if (pixivState.view === 'detail' && pixivState.detail) {
      detailSnapPush('pixiv', { detail: pixivState.detail, related: pixivState.related, detailFrom: pixivState.detailFrom })
    }
    pixivState.detailFrom = pixivState.view
    pixivState.view = 'detail'
    pixivState.detail = null
    pixivState.related = null
    pixivState.detailLoading = true
    // 详情失败兜底"重试"按钮：记录本次请求（PixivPanel 详情空态调用）
    pixivState.detailRetry = () => {
      pixivState.detailLoading = true
      window.api.sendCommand({ cmd: 'pixiv_detail', kind: e.kind, item_id: e.item_id })
    }
    window.api.sendCommand({ cmd: 'pixiv_detail', kind: e.kind, item_id: e.item_id })
    return
  }
  if (cmd === 'pixiv_back') {
    // 先弹链式详情快照逐级恢复；弹空后按来源回用户页或列表
    const snap = detailSnapPop('pixiv')
    if (snap) {
      pixivState.detail = snap.detail
      pixivState.related = snap.related
      pixivState.detailFrom = snap.detailFrom
      pixivState.view = 'detail'
      pixivState.detailLoading = false
      return
    }
    // 返回上一层：用户页点进的作品回用户页，否则回列表
    pixivState.view = pixivState.detailFrom === 'user' && pixivState.userPage ? 'user' : ''
    return
  }
  if (cmd === 'pixiv_feed') {
    pixivListCtx.mode = 'feed'
    pixivListCtx.kind = e.kind || 'home'
    pixivActiveFeed.value = pixivListCtx.kind
    pixivListCtx.feedKind = pixivListCtx.kind
    if (e.page === 1 && pixivRestoreCache(pixivListCtx.feedKind)) {
      window.api.sendCommand({ cmd: 'pixiv_feed', kind: pixivListCtx.kind, page: 1 })
      return
    }
    window.api.sendCommand({ cmd: 'pixiv_feed', kind: pixivListCtx.kind, page: e.page || 1 })
    return
  }
  if (cmd === 'pixiv_follow_feed') {
    // 关注的人更新（断点更新 + 历史缓存，逻辑与 X 站浏览模式一致）
    pixivListCtx.mode = ''
    pixivListCtx.content = e.content || 'illust'
    pixivActiveFeed.value = `follow_${pixivListCtx.content}`
    pixivListCtx.feedKind = pixivActiveFeed.value
    pixivRestoreCache(pixivListCtx.feedKind)
    window.api.sendCommand({ cmd: 'pixiv_follow_feed', content: pixivListCtx.content })
    return
  }
  if (cmd === 'pixiv_bookmarks') {
    pixivListCtx.mode = 'bookmarks'
    pixivListCtx.content = e.content || 'illust'
    pixivListCtx.restrict = e.restrict || 'public'
    pixivListCtx.allow_r18 = e.allow_r18 !== false
    pixivListCtx.user_id = e.user_id || ''
    pixivActiveFeed.value = 'bookmark'
    pixivListCtx.feedKind = `bookmark_${pixivListCtx.content}`
    if (e.page === 1) pixivRestoreCache(pixivListCtx.feedKind)
    window.api.sendCommand({
      cmd: 'pixiv_bookmarks', content: pixivListCtx.content,
      restrict: pixivListCtx.restrict, allow_r18: pixivListCtx.allow_r18,
      page: e.page || 1, user_id: pixivListCtx.user_id,
    })
    return
  }
  if (cmd === 'pixiv_user_list') {
    pixivListCtx.mode = 'userlist'
    pixivListCtx.umode = e.mode || 'following'
    pixivListCtx.user_id = e.user_id || ''
    pixivActiveFeed.value = `userlist_${pixivListCtx.umode}`
    pixivListCtx.feedKind = pixivActiveFeed.value
    if (e.page === 1) pixivRestoreCache(pixivListCtx.feedKind)
    window.api.sendCommand({
      cmd: 'pixiv_user_list', mode: pixivListCtx.umode,
      user_id: pixivListCtx.user_id, page: e.page || 1,
    })
    return
  }
  if (cmd === 'pixiv_batch_download') {
    // 批量解析下载（多批次：每个用户一个后台任务；勾选作品合并为一个任务）
    // 形态一：卡片勾选（items + novel_fmt）——直接透传后端。
    // （2026-09-13 实锤：此前本分支只读 user_ids/illust_ids/novel_ids，
    //   卡片勾选的 items 载荷三数组全空 → 静默 return → 后端永远收不到命令、
    //   下载管理里没有任何任务产生）
    if (Array.isArray(e.items) && e.items.length) {
      pixivBatchRunning.value = true
      pixivBatchProgress.done = 0
      pixivBatchProgress.total = e.items.length
      pixivBatchProgress.message = '准备中...'
      window.api.sendCommand({
        cmd: 'pixiv_batch_download',
        items: JSON.parse(JSON.stringify(e.items)),
        novel_fmt: e.novel_fmt || 'txt',
      })
      return
    }
    // 形态二：用户列表批量（user_ids + content）
    const userIds = (e.user_ids || []).map(String).filter(Boolean)
    const illustIds = (e.illust_ids || []).map(String).filter(Boolean)
    const novelIds = (e.novel_ids || []).map(String).filter(Boolean)
    if (!userIds.length && !illustIds.length && !novelIds.length) return
    pixivBatchRunning.value = true
    pixivBatchProgress.done = 0
    pixivBatchProgress.total = userIds.length + ((illustIds.length || novelIds.length) ? 1 : 0)
    pixivBatchProgress.message = '准备中...'
    window.api.sendCommand({
      cmd: 'pixiv_batch_download',
      user_ids: userIds,
      content: e.content || 'illust',
      illust_ids: illustIds,
      novel_ids: novelIds,
      options: JSON.parse(JSON.stringify(settings)),
    })
    addLog('下载', `Pixiv 批量下载：${userIds.length} 个用户、${illustIds.length + novelIds.length} 个作品`)
    return
  }
  if (cmd === 'pixiv_series_download') {
    // 下载全部系列（连载：书名目录 + 每话章节），novel_fmt 供小说章节选择 txt/word
    pixivBatchRunning.value = true
    pixivBatchProgress.done = 0
    pixivBatchProgress.total = 0
    pixivBatchProgress.message = '正在获取系列章节...'
    window.api.sendCommand({
      cmd: 'pixiv_series_download',
      series_id: e.series_id,
      kind: e.kind || 'novel',
      novel_fmt: e.novel_fmt || 'txt',
      options: JSON.parse(JSON.stringify(settings)),
    })
    addLog('下载', `Pixiv 全部系列下载：${e.title || e.series_id}（${e.kind === 'illust' ? '漫画' : '小说'}）`)
    return
  }
  if (cmd === 'pixiv_following_download_all') {
    // 下载全部关注用户的作品：后端遍历关注列表全部分页，每人一个下载任务
    pixivBatchRunning.value = true
    pixivBatchProgress.done = 0
    pixivBatchProgress.total = 0
    pixivBatchProgress.message = '正在获取关注列表...'
    window.api.sendCommand({
      cmd: 'pixiv_following_download_all',
      content: e.content || 'illust',
      options: JSON.parse(JSON.stringify(settings)),
    })
    addLog('下载', `Pixiv 下载全部关注用户作品（${e.content === 'novel' ? '小说' : '插画/漫画'}）`)
    return
  }
  if (cmd === 'pixiv_bookmarks_download_all') {
    // 下载全部收藏：后端遍历全部分页 + 跨记录查重跳过已下载，统一归档 我的插画/漫画/小说收藏
    pixivBatchRunning.value = true
    pixivBatchProgress.done = 0
    pixivBatchProgress.total = 0
    pixivBatchProgress.message = '正在获取收藏列表...'
    window.api.sendCommand({
      cmd: 'pixiv_bookmarks_download_all',
      content: e.content || 'illust',
      restrict: e.restrict || 'public',
      allow_r18: e.allow_r18 !== false,
      options: JSON.parse(JSON.stringify(settings)),
    })
    addLog('下载', `Pixiv 下载全部收藏（${{ illust: '插画', manga: '漫画', novel: '小说' }[e.content] || '插画'}）`)
    return
  }
  // 其余命令直接透传后端（pixiv_related / pixiv_action / pixiv_notification / pixiv_bookmark_tags / pixiv_upload / pixiv_user_novels）
  // 注意必须带上 cmd——此前解构剥掉 cmd 只发 payload，这批命令全部静默失效
  window.api.sendCommand(e)
}

// H站主页：各分区视频（进入站点时自动加载）
function handleHaHome() {
  if (!window.api) return
  navPushView('hanime1', 'home')
  haView.value = 'home'
  searchResults.value = []
  window.api.sendCommand({ cmd: 'hanime_home' })
}

// 打开视频详情
function handleHanimeOpenDetail(videoId) {
  if (!window.api) return
  // 链式详情（详情内相關影片点开下一个）：快照当前详情，返回时逐级恢复
  if (haView.value === 'detail' && haDetail.value) {
    detailSnapPush('hanime1', { detail: haDetail.value, comments: haComments.value })
  }
  window.api.sendCommand({ cmd: 'hanime_video_detail', video_id: videoId })
}

// 关闭视频详情（先弹链式详情快照逐级恢复；弹空后回上一层：有主页内容回主页，否则回搜索态）
function handleHaDetailBack() {
  const snap = detailSnapPop('hanime1')
  if (snap) { haDetail.value = snap.detail; haComments.value = snap.comments; return }
  if (detailFromSearch.value === 'hanime1') { detailFromSearch.value = ''; haView.value = ''; haDetail.value = null; haComments.value = []; return }
  const prev = navPopView('hanime1')
  if (prev) haView.value = prev
  else haView.value = haSections.value.length ? 'home' : ''
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
  navPushView('hanime1', 'user')
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

// 点击 tag 搜索：走 tags[] 精确过滤（broad=on 兼容模糊），此前按 query 全文搜常返回 0 结果
function handleHanimeSearchTag(tag) {
  if (!tag || !window.api) return
  navPushView('hanime1', '')
  haView.value = ''
  searchQuery.value = tag
  searchResults.value = []
  searchPage.value = 1
  window.api.sendCommand({
    cmd: 'hanime_search',
    query: '',
    page: 1,
    genre: settings.hanime_genre || '',
    sort: settings.hanime_sort || '',
    tags: [tag],
    broad: 'on',
  })
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
  // 批量任务已提交：自动打开下载管理面板（后台任务可视化，防"没反应"体感）
  if (!detailVisible.value) {
    detailVisible.value = true
    message.info('批量下载任务已提交，已为你打开下载管理')
  }
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
  navPushView('oreno', 'home')
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
  if (detailFromSearch.value === 'oreno') { detailFromSearch.value = ''; orView.value = ''; orDetail.value = null; return }
  const prev = navPopView('oreno')
  if (prev) orView.value = prev
  else orView.value = orList.items.length ? 'list' : (orHomeItems.value.length ? 'home' : '')
  orDetail.value = null
}

// 标签页视频列表
function handleOrenoTag(tagId, page = 1, sort) {
  if (!window.api) return
  navPushView('oreno', 'list')
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
  navPushView('oreno', 'list')
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
  navPushView('oreno', 'list')
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
  navPushView('oreno', 'list')
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
  const prev = navPopView('oreno')
  if (prev) orView.value = prev
  else orView.value = orHomeItems.value.length ? 'home' : ''
  orList.items = []
}

// 角色/作者浏览视图返回（历史栈上一步）
function handleOrBrowseBack() {
  const prev = navPopView('oreno')
  if (prev) orView.value = prev
  else orView.value = orHomeItems.value.length ? 'home' : ''
}

// 角色列表视图（人気角色 + 五十音分组）
function handleOrenoCharacters() {
  if (!window.api) return
  navPushView('oreno', 'characters')
  orView.value = 'characters'
  searchResults.value = []
  window.api.sendCommand({ cmd: 'oreno_characters', site_key: siteKey.value })
}

// 人気作者列表视图（分页）
function handleOrenoAuthorsIndex(page = 1) {
  if (!window.api) return
  navPushView('oreno', 'authors')
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
  setLoginLoading('asmr', true)
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
// 识图（反向图片搜索）：拖拽/选择图片 → 后端并发查询全部识图网站 → 展示结果
// ============================
// 识图视图开关（左侧识图按钮触发；占用/退出右侧展示区）
// 退出时若在搜索中，顺带取消，避免后台请求继续占用带宽
function handleReverseToggle(active) {
  reverseActive.value = !!active
  if (!active && reverseRunning.value) handleReverseCancel()
}

// 开始识图（图片本地路径 → 后端 reverse_search 并发查询全部网站）
function handleReverseSearch(path) {
  if (!window.api || !path) return
  // 先作废上一轮 session，上一轮的迟到回传会被 reverse_site_update 过滤掉
  reverseSession.value = ''
  reverseMerged.value = []
  reverseCached.value = false
  reverseSites.value = []
  reverseRunning.value = true
  window.api.sendCommand({ cmd: 'reverse_search', path })
  addLog('识图', `开始以图搜源: ${path}`)
}

// 取消进行中的识图（已发出的请求在后台结束，结果一律丢弃）
function handleReverseCancel() {
  if (!window.api || !reverseRunning.value) return
  reverseSession.value = ''
  reverseRunning.value = false
  window.api.sendCommand({ cmd: 'reverse_cancel' })
  addLog('识图', '已请求取消搜索')
}

// 清空结果回到拖拽框（重新识图）
function handleReverseReset() {
  if (reverseRunning.value) handleReverseCancel()
  reverseSites.value = []
  reverseMerged.value = []
  reverseCached.value = false
  reverseRunning.value = false
}

// 把识图结果链接交给下载器（后端内部解析成文件列表后直接建任务）
function handleReverseDownload(url) {
  if (!window.api || !url) return
  window.api.sendCommand({ cmd: 'reverse_download', url })
  addLog('识图', `请求下载: ${url}`)
}

// 保存左侧粘贴板内容（cache/reverse_paste.txt 长期记录）
function handleReversePasteSave(text) {
  if (window.api) window.api.sendCommand({ cmd: 'reverse_paste_save', text: text || '' })
}

// 识图代理修改（默认只给 Google / Yandex / Lenso.ai 用；开关打开则全站生效）
function handleReverseSetProxy(proxy, allSites) {
  const payload = { reverse_proxy: proxy || '' }
  if (allSites !== undefined) payload.reverse_proxy_all = !!allSites
  updateSettings(payload)
  if (window.api) {
    window.api.sendCommand({
      cmd: 'reverse_set_proxy',
      proxy: proxy || '',
      all_sites: allSites !== undefined ? !!allSites : !!settings.reverse_proxy_all,
    })
  }
}

// 代理作用域开关变化：不改代理地址，只切换"是否所有站点都走代理"
watch(() => settings.reverse_proxy_all, (v) => {
  if (!window.api) return
  window.api.sendCommand({
    cmd: 'reverse_set_proxy',
    proxy: settings.reverse_proxy || '',
    all_sites: !!v,
  })
})

// ============================
// 通用 webview 浏览器登录（twitter/xhamster/pornhub/xvideos 等与 EX 站相同的操作）
// ============================
// 触发 webview 登录弹窗：弹出的浏览器内自行完成登录（邮箱/Twitter 授权皆可），
// 登录后点弹窗下方"确认"自动抓取 Cookie（手动确认模式，同 EX 站）
function handleSiteOAuthLogin(siteKey, creds) {
  const configs = {
    // X 站：弹窗内登录 x.com，抓取 .x.com 域的 auth_token / ct0
    twitter: {
      loginUrl: 'https://x.com/login',
      homeUrl: 'https://x.com/home',
      partition: 'persist:twitter',
      successPatterns: [],
      captchaPatterns: [/challenge|captcha|login_challenge/i],
      manualConfirm: true,
    },
    // Pawchive：弹窗内登录 pawchive.pw，确认后抓取会话 cookie
    pawchive: {
      loginUrl: 'https://pawchive.pw/login',
      homeUrl: 'https://pawchive.pw/',
      partition: 'persist:pawchive',
      successPatterns: [],
      captchaPatterns: [/challenge|captcha|turnstile/i],
      manualConfirm: true,
    },
    // Iwara：弹窗内登录 iwara.tv（真人验证在弹窗内完成），确认后保存表单账号密码供自动重登
    iwara: {
      loginUrl: 'https://www.iwara.tv/login',
      homeUrl: 'https://www.iwara.tv/',
      partition: 'persist:iwara',
      successPatterns: [],
      captchaPatterns: [/challenge|captcha|turnstile/i],
      manualConfirm: true,
    },
    // Hanime1：弹窗内登录 hanime1.me（真人验证在弹窗内完成），确认后保存会话 cookie + 账号密码
    hanime: {
      loginUrl: 'https://hanime1.me/login',
      homeUrl: 'https://hanime1.me/',
      partition: 'persist:hanime',
      successPatterns: [],
      captchaPatterns: [/challenge|captcha|recaptcha|hcaptcha|turnstile/i],
      manualConfirm: true,
    },
    // Pixiv：Refresh Token 登录（PKCE OAuth）：先发 pixiv_oauth_start，后端回推 pixiv_oauth_url 再打开弹窗
    // （登录页为 app-api.pixiv.net/web/v1/login，成功重定向 pixiv://account/login?code=xxx 由 webview 拦截）
    // （pixiv 走 handlePixivLogin 单独入口，不在此配置）
    // ASMR-100：弹窗内登录 asmr-100.com，确认后保存表单账号密码供 token 失效自动重登
    asmr: {
      loginUrl: 'https://asmr-100.com/login',
      homeUrl: 'https://asmr-100.com/',
      partition: 'persist:asmr',
      successPatterns: [],
      captchaPatterns: [/challenge|captcha|turnstile/i],
      manualConfirm: true,
    },
    xhamster: {
      loginUrl: 'https://jp.xhamster.com/login',
      homeUrl: 'https://jp.xhamster.com/',
      partition: 'persist:twitter',
      successPatterns: [/xhamster\.com\/(users|my|favorites)/i, /xhamster\.com\/?\?auth=1/i],
      captchaPatterns: [/challenge|captcha|areyouhuman|check\.xhamster/i],
      manualConfirm: true,
    },
    pornhub: {
      loginUrl: 'https://jp.pornhub.com/login',
      homeUrl: 'https://jp.pornhub.com/',
      partition: 'persist:twitter',
      successPatterns: [/pornhub\.com\/(users|my|user)/i, /pornhub\.com\/?\?login=/i],
      captchaPatterns: [/challenge|captcha|areyouhuman|cdn\.pornhub/i],
      manualConfirm: true,
    },
    xvideos: {
      loginUrl: 'https://www.xvideos.com/profile/login',
      homeUrl: 'https://www.xvideos.com/',
      partition: 'persist:xvideos',
      successPatterns: [/xvideos\.com\/(profiles|account|favorites)/i],
      captchaPatterns: [/challenge|captcha|areyouhuman|cdn\.xvideos/i],
      manualConfirm: true,
    },
    leakedzone: {
      loginUrl: 'https://leakedzone.com/',
      homeUrl: 'https://leakedzone.com/',
      partition: 'persist:leakedzone',
      successPatterns: [],
      captchaPatterns: [/challenge|captcha|just a moment/i],
      manualConfirm: true,
      confirmHint: '请在弹窗内完成 Cloudflare 人机验证（复选框→转圈→出现网站内容）后，点「确认」保存过盾会话（cookie+UA 一起保存）',
      confirmText: '确认并保存会话',
    },
    fc2: {
      // FC2 ID 登录（免费邮箱注册）；未登录也可浏览/看免费视频，登录后付费内容可见
      loginUrl: 'https://secure.id.fc2.com/?done=video&switch_language=ja',
      homeUrl: 'https://video.fc2.com/a/',
      partition: 'persist:fc2',
      successPatterns: [],
      captchaPatterns: [],
      manualConfirm: true,
      confirmHint: '请完成 FC2 登录（登录成功会跳回视频页），然后点"确定"抓取 cookie。',
      confirmText: '确定',
    },
    javdb: {
      // JavDB 邮箱密码登录：webview 内完成 Cloudflare 人机验证；"记住此装置"后 cookie 约 7 天有效
      // 手动确认模式：自动抓取会在"同意条款"页提前触发导致 cookie 不完整，
      // 改为用户完成登录+点"同意"后，自己点底部"确定"再抓取，保证 cookie 完整准确
      loginUrl: 'https://javdb.com/login/',
      homeUrl: 'https://javdb.com/',
      partition: 'persist:javdb',
      successPatterns: [],
      captchaPatterns: [/challenge|captcha|cdn-cgi|turnstile/i],
      manualConfirm: true,
      confirmHint: '请完成登录并点击"同意"，然后点"确定"抓取 cookie。',
      confirmText: '确定',
    },
    exhentai: {
      // EX 登录：弹窗内打开 e-hentai 论坛登录页（EX 账号即论坛账号）；
      // 登录成功后论坛域会自动下发 ipb_member_id/ipb_pass_hash cookie，
      // 用户点下方"确认"抓取（手动确认模式，不依赖 URL 检测）
      loginUrl: 'https://forums.e-hentai.org/index.php?act=Login&CODE=00',
      homeUrl: 'https://forums.e-hentai.org/',
      partition: 'persist:exhentai',
      successPatterns: [],
      captchaPatterns: [/challenge|captcha|turnstile|hcaptcha/i],
      manualConfirm: true,
    },
    google: {
      // 谷歌邮箱：登录后的 cookie 是其他站 Google OAuth 授权的凭据源；
      // 登录判定不依赖 URL（Google 登录流程多跳转），用手动确认模式
      loginUrl: 'https://accounts.google.com/',
      homeUrl: 'https://myaccount.google.com/',
      partition: 'persist:google',
      successPatterns: [],
      captchaPatterns: [/challenge|captcha/i],
      manualConfirm: true,
    },
    oreno3d: {
      // Oreno3D：无强制账号体系，登录环节仅保存站点会话 cookie（个人浏览状态）
      loginUrl: 'https://oreno3d.com/',
      homeUrl: 'https://oreno3d.com/',
      partition: 'persist:oreno3d',
      successPatterns: [],
      captchaPatterns: [/challenge|captcha|turnstile/i],
      manualConfirm: true,
    },
    erommdtube: {
      // EroMMDTube：与 Oreno3D 同架构，登录环节保存站点会话 cookie（Cloudflare 验证后免重复验证）
      loginUrl: 'https://erommdtube.com/',
      homeUrl: 'https://erommdtube.com/',
      partition: 'persist:erommdtube',
      successPatterns: [],
      captchaPatterns: [/challenge|captcha|turnstile/i],
      manualConfirm: true,
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
  wvLogin.manualConfirm = !!cfg.manualConfirm
  wvLogin.confirmHint = cfg.confirmHint
  wvLogin.confirmText = cfg.confirmText
  wvLogin.autoGrabPattern = cfg.autoGrabPattern || null
  wvLogin.codeRegex = null
  wvLogin.watchLoginUrl = false
  // 账号密码登录站：webview 登录页自动预填（用户只需完成真人验证并点登录）
  wvLogin.credentials = (creds && creds.email) ? {
    email: creds.email,
    password: creds.password || '',
  } : null
  wvLogin.visible = true
  // 同时设置 webview 会话代理（复用站点代理设置；EX 站用 exhentai_proxy）
  const proxyKey = siteKey === 'exhentai' ? 'exhentai_proxy' : `${siteKey}_proxy`
  // fc2/leakedzone 缺省即给通用代理（webview 打不开登录页/CF 按 IP 信誉循环挑战 =
  // 登录失败的常见根因；默认值可改，settings.common_proxy 优先）
  const proxyUrl = settings[proxyKey]
    || (['fc2', 'leakedzone'].includes(siteKey) ? (settings.common_proxy || COMMON_PROXY_DEFAULT) : '')
  if (window.api && proxyUrl) {
    window.api.siteSetProxy(siteKey, proxyUrl)
  }
  // 跨站凭据注入：把谷歌邮箱/X 的 cookie 复制进目标站会话（OAuth 授权跳转自动带凭据）
  // 场景：xhamster/pornhub/xvideos 用 Google/X 授权登录时无需重新输账号
  if (window.api && window.api.syncSharedCookies) {
    window.api.syncSharedCookies(siteKey).catch(() => { /* 注入失败不阻塞登录流程 */ })
  }
}

// WebviewLoginModal 抓取 cookie 成功 → 发后端持久化 + 验证
// （javdb 附带 webview UA：cf_clearance 等 Cloudflare cookie 绑定 UA，后端请求需同 UA）
// （exhentai/twitter 后端命令读 cookies 字段，其他站读 cookie_str）
// （javdb 同时回传登录表单的账号密码，长期保存供下次预填）
function handleSiteLoginSuccess({ cookieStr, count, userAgent }) {
  if (!window.api || !wvLogin.site) return
  // iwara / asmr：token 型登录，webview 里完成真人验证后保存表单账号密码
  //（后端用保存的密码走 API 登录 / token 失效自动重登）
  if (wvLogin.site === 'iwara' || wvLogin.site === 'asmr') {
    if (wvLogin.credentials && wvLogin.credentials.email) {
      window.api.sendCommand({
        cmd: 'site_save_cred',
        site: wvLogin.site,
        email: wvLogin.credentials.email,
        password: wvLogin.credentials.password || '',
      })
      addLog('系统', `${wvLogin.site} 内置浏览器登录完成，账号密码已保存（token 失效自动重登）`)
    } else {
      message.warning('未检测到表单账号密码：请在左侧登录表单输入账号密码后再用内置浏览器登录')
    }
    return
  }
  const payload = { cmd: `${wvLogin.site}_set_cookies`, cookie_str: cookieStr }
  if (wvLogin.site === 'exhentai' || wvLogin.site === 'twitter') payload.cookies = cookieStr
  // javdb/leakedzone 附带 webview UA：cf_clearance 等 Cloudflare cookie 绑定 UA，后端请求需同 UA
  if (wvLogin.site === 'javdb' && userAgent) payload.user_agent = userAgent
  if (wvLogin.site === 'leakedzone' && userAgent) payload.user_agent = userAgent
  if (wvLogin.site === 'javdb' && wvLogin.credentials) {
    payload.email = wvLogin.credentials.email || ''
    payload.password = wvLogin.credentials.password || ''
  }
  // O3D / E站 / Hanime1：登录表单的账号密码随 cookie 一起保存（下次登录自动预填）
  if (['oreno3d', 'erommdtube', 'hanime'].includes(wvLogin.site) && wvLogin.credentials) {
    payload.email = wvLogin.credentials.email || ''
    payload.password = wvLogin.credentials.password || ''
  }
  // 谷歌邮箱：带上保存的邮箱（后端凭据库补记，展示用）
  if (wvLogin.site === 'google' && googleEmail.value) {
    payload.email = googleEmail.value
  }
  window.api.sendCommand(payload)
  addLog('系统', `${wvLogin.site} 抓取到 ${count} 个 cookie，已发给后端保存`)
}

// WebviewLoginModal 拦截到 OAuth 授权码（pixiv://account/login?code=xxx 无法在 webview 加载，
// will-navigate/did-fail-load 事件提取 code）→ 抓取 webview cookie 一并发后端换 Refresh Token
async function handleSiteLoginCode({ code, site }) {
  if (!window.api || !code) return
  // 诊断日志：code 长度+前缀（换 token 失败时可据此排查截断/错码）
  addLog('系统', `${site} OAuth 授权码已提取（长度 ${code.length}，前缀 ${code.slice(0, 6)}...），正在换取 Token...`)
  let cookieStr = ''
  try {
    // 登录页 webview cookie（通知/提醒等 Web ajax 备用通道）
    const res = await window.api.siteGetCookies(site)
    cookieStr = res && res.cookieStr ? res.cookieStr : ''
  } catch (e) { /* cookie 抓取失败不阻塞换 token */ }
  window.api.sendCommand({ cmd: `${site}_oauth_complete`, code, cookie_str: cookieStr })
  wvLogin.visible = false
}

// 谷歌邮箱账号密码保存（设置区"登录谷歌邮箱"表单）
function handleGoogleSaveCred(email, password) {
  if (!window.api) return
  if (!email || !email.trim()) {
    message.warning('请输入谷歌邮箱地址')
    return
  }
  window.api.sendCommand({
    cmd: 'google_save_cred',
    email: email.trim(),
    password: password || '',
  })
  addLog('系统', `谷歌邮箱账号密码已保存: ${email.trim()}`)
}

// 谷歌邮箱：切换账号（选中账号设为当前使用，登录表单/浏览器预填用）
function handleGoogleSwitchAccount(email) {
  if (!window.api || !email) return
  window.api.sendCommand({ cmd: 'google_switch_account', email })
}

// 谷歌邮箱：删除账号记录（不影响当前 cookie 会话）
function handleGoogleDeleteAccount(email) {
  if (!window.api || !email) return
  window.api.sendCommand({ cmd: 'google_delete_account', email })
}

// 通用退出登录
function handleSiteLogout(siteKey) {
  if (!window.api) return
  window.api.sendCommand({ cmd: `${siteKey}_logout` })
  // FC2：同步清除内置浏览器分区 cookie，保证下次 webview 打开是干净会话
  if (siteKey === 'fc2' && window.api.siteClearCookies) {
    window.api.siteClearCookies('fc2').catch(() => {})
  }
}

// O3D / E站 账号密码保存（加密存本机，登录会话与 cookie 互相验证）
function handleOrenoSaveCred(siteKey, email, password) {
  if (!window.api) return
  if (!email || !email.trim()) {
    const label = siteKey === 'erommdtube' ? 'EroMMDTube' : 'Oreno3D'
    message.warning(`请输入 ${label} 账号`)
    return
  }
  window.api.sendCommand({
    cmd: `${siteKey}_save_cred`,
    email: email.trim(),
    password: password || '',
  })
  addLog('系统', `${siteKey} 账号密码已保存: ${email.trim()}`)
}

// 通用账号密码保存（全站登录套件：加密存本机，供表单回填与内置浏览器预填）
function handleSiteSaveCred(siteKey, email, password) {
  if (!window.api) return
  if (!email || !email.trim()) {
    message.warning('请输入账号（邮箱/用户名）')
    return
  }
  window.api.sendCommand({
    cmd: 'site_save_cred',
    site: siteKey,
    email: email.trim(),
    password: password || '',
  })
  addLog('系统', `${siteKey} 账号密码已保存: ${email.trim()}`)
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

// ============================
// JavDB（javdb.com）业务
// ============================
// 点击搜索结果卡片 → 解析视频详情（封面/预览图/磁力列表）
function handleJavdbOpenDetail(item) {
  if (!item || !item.album_url) return
  javdbDetail.value = null
  url.value = item.album_url
  // 走 javdb_video_info 专用命令（由 javdb_detail_loading/javdb_video_detail 事件驱动详情区转圈）。
  // 此前走通用 inspect 命令，但 JavDB 后端流程不发 inspect 终止事件，
  // 导致全局解析转圈 inspecting 卡满 120s 看门狗才解除（表现为"点开后一直加载"）。
  if (!window.api) return
  const options = JSON.parse(JSON.stringify(settings))
  window.api.sendCommand({ cmd: 'javdb_video_info', url: item.album_url, options })
}

// 关闭详情返回搜索结果
function handleJavdbDetailBack() {
  javdbDetail.value = null
  fileList.value = []
}

// 下载当前详情页的封面 + 全部预览图（直链下载任务）
function handleJavdbDownloadImages() {
  if (!window.api || !javdbDetail.value) return
  const options = JSON.parse(JSON.stringify(settings))
  window.api.sendCommand({ cmd: 'javdb_download_images', url: javdbDetail.value.url, options })
  message.success('已提交下载任务（封面 + 预览图）')
}

// JavDB 批量下载（弹母文件夹命名弹窗，与 EX 同一套交互）
function handleJavdbBatchDownload(urls) {
  if (!window.api || !Array.isArray(urls) || !urls.length) return
  batchFolderContext.value = 'javdb'
  exBatchFolderPendingUrls.value = urls.filter(u => u)
  exBatchFolderName.value = lastSearchKeyword.value || ''
  exBatchFolderVisible.value = true
}

// JavDB 首页最新影片（无需关键词，进入站点即有内容；翻页走 javdb_home）
function handleJavdbHome(page = 1) {
  if (!window.api) return
  javdbListCtx.mode = 'home'
  javdbListCtx.url = ''
  javdbListCtx.label = ''
  javdbDir.kind = ''
  javdbDetail.value = null
  if (page <= 1) {
    searchResults.value = []
    searchPage.value = 1
  }
  searchQuery.value = '最新影片'
  window.api.sendCommand({ cmd: 'javdb_home', page })
}

// JavDB 演员主页全部作品（详情页点演员名进入；翻页走 javdb_actor）
function handleJavdbOpenActor(actorUrl, page = 1) {
  if (!window.api || !actorUrl) return
  javdbListCtx.mode = 'actor'
  javdbListCtx.url = actorUrl
  javdbListCtx.label = ''
  javdbDir.kind = ''
  javdbDetail.value = null
  if (page <= 1) {
    searchResults.value = []
    searchPage.value = 1
  }
  window.api.sendCommand({ cmd: 'javdb_actor', url: actorUrl, page })
}

// JavDB 详情点标签 → 按标签名搜索（f=tag，回到普通搜索流程）
function handleJavdbSearchTag(tag, field = 'tag') {
  if (!tag) return
  javdbSearchField.value = field
  searchQuery.value = tag
  doSearch(tag, 1)
}

// ---------- JavDB 第一~五行工具栏 ----------

// 第一行：搜索类型切换（影片/演员/系列/片商/导演/番号）；
// 有搜索词时立即按新类型重搜（否则点击无任何反馈）
function setJavdbSearchField(f) {
  javdbSearchField.value = f
  const q = (searchQuery.value || '').trim()
  if (q && !searching.value) doSearch(q, 1)
}

// 第三行/第四行词条：热搜词走 f=all，标签词走 f=tag
function handleJavdbHotSearch(kw) {
  if (!kw) return
  javdbSearchField.value = 'all'
  searchQuery.value = kw
  doSearch(kw, 1)
}

// 通用列表页（类别 /uc、排行榜 /ranking、年份筛选等）：翻页走 javdb_open_url
function handleJavdbOpenList(url, label, page = 1) {
  if (!window.api || !url) return
  javdbDir.kind = ''
  javdbListCtx.mode = 'url'
  javdbListCtx.url = url
  javdbListCtx.label = label || 'JavDB 列表'
  javdbDetail.value = null
  if (page <= 1) {
    searchResults.value = []
    searchPage.value = 1
  }
  window.api.sendCommand({ cmd: 'javdb_open_url', url, label: javdbListCtx.label, page })
}

// 第二行：目录导航（演员 / 系列 / 片商），目录页解析名称列表；params 支持 vft 分类参数
function handleJavdbDir(kind, page = 1, params = '') {
  if (!window.api || !kind) return
  javdbListCtx.mode = ''
  javdbDetail.value = null
  if (page <= 1) {
    searchResults.value = []
    searchPage.value = 1
  }
  window.api.sendCommand({ cmd: 'javdb_directory', kind, page, params })
}

// 目录翻页 / 返回
function handleJavdbDirPage(page) {
  handleJavdbDir(javdbDir.kind, page, javdbDir.params)
}
function handleJavdbDirClear() {
  javdbDir.kind = ''
  javdbDir.items = []
}

// 第四行：标签页模式切换（有码/无码/欧美/FC2/动漫）并加载对应列表；
// 列表结果同时作为第五行「模式推荐作品」数据源
function handleJavdbTagsMode(mode) {
  if (!mode || !mode.key) return
  javdbTagsMode.value = mode.key
  if (mode.vft) {
    javdbRecommendPending.mode = mode.key
    javdbRecommendPending.label = `${mode.label}影片`
    // 类别真实结构：/{censored|uncensored|western}?vft=1（含磁鏈过滤；Google 索引证实 vft 用法）
    handleJavdbOpenList(`/${mode.key}?vft=${mode.vft}`, `${mode.label}影片`)
  } else if (mode.key === 'fc2' || mode.key === 'anime') {
    // FC2/動漫分区：/tags/{key}?c10=1（导航 HTML 实测 2026-09-01：'FC2' -> /tags/fc2?c10=1；
    // 该路径需登录可见。此前误走关键词搜索 fallback，导致 FC2 无内容/動漫错位）
    javdbRecommendPending.mode = mode.key
    javdbRecommendPending.label = mode.label
    handleJavdbOpenList(`/tags/${mode.key}?c10=1`, mode.label)
  } else {
    javdbSearchField.value = 'all'
    searchQuery.value = mode.fallback_q || mode.label
    javdbRecommendPending.mode = mode.key
    javdbRecommendPending.label = mode.fallback_q || mode.label
    doSearch(mode.fallback_q || mode.label, 1)
  }
}

// JavDB 退出登录（清空用户态；cookie 由后端删除）
function handleJavdbLogout() {
  if (!window.api) return
  window.api.sendCommand({ cmd: 'javdb_logout' })
  javdbUser.value = ''
  message.info('已退出 JavDB 登录')
}

// 热门作品（每页 100，进入站点时自动加载）
function handleAsmrPopular(page = 1) {
  if (!window.api) return
  navPushView('asmr', 'popular')
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
  navPushView('asmr', 'works')
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
  navPushView('asmr', 'favorites')
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
  // 链式详情（详情内相似作品点开下一个）：快照当前详情，返回时逐级恢复
  if (asmrView.value === 'detail' && asmrDetail.value) {
    detailSnapPush('asmr', {
      detail: asmrDetail.value, files: asmrFiles.value, related: asmrRelated.value,
      relatedPending: asmrRelatedPending.value,
    })
  }
  asmrDetail.value = null
  asmrFiles.value = []
  asmrRelated.value = []
  asmrRelatedPending.value = false
  window.api.sendCommand({ cmd: 'asmr_work_detail', work_id: String(wid) })
}

// 迷你播放器"回到作品"：切回音声站并重开当前播放作品的详情（后台播放不受影响）
function handleAsmrMiniJumpBack() {
  const w = audioPlayer.work
  if (!w) return
  if ((settings.site || 'bunkr') !== 'asmr') updateSite('asmr')
  handleAsmrOpenDetail(w)
}

// 关闭详情返回上一层（先弹链式详情快照逐级恢复；弹空后有列表回列表，否则回搜索态）
function handleAsmrDetailBack() {
  const snap = detailSnapPop('asmr')
  if (snap) {
    asmrDetail.value = snap.detail
    asmrFiles.value = snap.files
    asmrRelated.value = snap.related
    asmrRelatedPending.value = snap.relatedPending
    return
  }
  if (detailFromSearch.value === 'asmr') { detailFromSearch.value = ''; asmrView.value = ''; asmrDetail.value = null; asmrFiles.value = []; return }
  const prev = navPopView('asmr')
  if (prev) asmrView.value = prev
  else asmrView.value = asmrItems.value.length ? (asmrListPrevView.value || 'popular') : ''
  asmrDetail.value = null
  asmrFiles.value = []
  asmrRelated.value = []
  asmrRelatedPending.value = false
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
  // 批量任务已提交：自动打开下载管理面板（后台任务可视化，防"没反应"体感）
  if (!detailVisible.value) {
    detailVisible.value = true
    message.info('批量下载任务已提交，已为你打开下载管理')
  }
}

// 右键下载单个/多个音轨文件（提交下载管理器，保留文件夹路径）
function handleAsmrDownloadFiles(files) {
  if (!window.api || !asmrDetail.value || !files || !files.length) return
  const d = asmrDetail.value
  const wid = String(d.video_id || (d.album_url || '').match(/work\/(\d+)/)?.[1] || '')
  if (!wid) return
  window.api.sendCommand({
    cmd: 'asmr_file_download',
    work_id: wid,
    work: { title: d.album_name || d.title || '', source_id: d.source_id || '', release: d.post_date || '', name: d.author || '' },
    files: files.map(f => ({ title: f.title, path: f.path, size: f.size, media_url: f.media_url })),
    options: JSON.parse(JSON.stringify(settings)),
  })
  addLog('下载', `音声站文件下载：${files.length} 个文件（${files.map(f => f.title).join('、').slice(0, 80)}）`)
}

// 进入 Iwara / Hanime1 / Oreno3D / EroMMDTube / ASMR 站点（或启动时停留在该站）自动加载主页
// 真人验证站点提示（每次会话只提示一次；解决方案 = 内置浏览器登录弹窗内完成验证）
const humanVerifyPrompted = new Set()

// ============================
// 全局站点视图导航历史栈（"← 返回" = 上一步）
// ============================
// 每站点独立栈，栈顶 = 当前视图；进入视图时 push（同视图去重，翻页/切 tab 不产生历史），
// 返回时 pop 弹掉当前视图回到上一步；栈空时走各站原有兜底逻辑（回主页/清空态）
const viewNavStacks = {}

function navPushView(siteKey, view) {
  if (!view) return
  const stack = viewNavStacks[siteKey] || (viewNavStacks[siteKey] = [])
  if (stack[stack.length - 1] !== view) stack.push(view)
  if (stack.length > 30) stack.shift()
}

// 返回上一步：弹出当前视图，返回新的栈顶视图；栈空返回 ''（调用方走兜底）
function navPopView(siteKey) {
  const stack = viewNavStacks[siteKey] || []
  stack.pop()
  return stack.length ? stack[stack.length - 1] : ''
}

// 站点栈清空（切换站点时重置返回链）
function navClearView(siteKey) {
  viewNavStacks[siteKey] = []
  detailSnapClear(siteKey)
}

// ============================
// 链式详情内容栈：详情内"相关推荐/相似作品"逐级点开（详情→详情）时，通用视图栈按
// 视图类型去重不会加深——返回会一次跳回列表、跳过中间详情。推入新详情前把当前详情
// 快照压栈，返回时逐级恢复；快照栈弹空后才走视图栈/搜索来源兜底。
// ============================
const detailSnapStacks = {}

function detailSnapPush(site, snap) {
  const st = detailSnapStacks[site] || (detailSnapStacks[site] = [])
  st.push(snap)
  if (st.length > 30) st.shift()
}

function detailSnapPop(site) {
  const st = detailSnapStacks[site]
  return (st && st.length) ? st.pop() : null
}

function detailSnapClear(site) {
  if (site) delete detailSnapStacks[site]
}

watch(() => settings.site, (s) => {
  navClearView(s)
  if (s === 'oreno3d' || s === 'erommdtube') navClearView('oreno')
  // xHamster：切入站点自动加载浏览首页（浏览不需登录；已有内容/二级视图时不打扰）
  if (s === 'xhamster' && !xhView.value && !xhHomeItems.value.length) {
    handleXhHome(1)
  }
  if (s === 'iwara' && !iwHomeItems.value.length) {
    handleIwHome(1)
  } else if (s === 'hanime' && !haSections.value.length) {
    handleHaHome()
  } else if ((s === 'oreno3d' || s === 'erommdtube') && !orHomeItems.value.length) {
    handleOrHome(1)
  } else if (s === 'asmr' && !asmrItems.value.length) {
    handleAsmrPopular(1)
  } else if (s === 'pixiv') {
    // 进入 P站：加载常用标签/热门标签（功能栏常显）+ 首页推荐 feed（需登录，未登录提示）
    if (window.api) {
      window.api.sendCommand({ cmd: 'pixiv_tags' })
      if (!searchResults.value.length) {
        handlePixivCommand({ cmd: 'pixiv_feed', kind: 'home', page: 1 })
      }
    }
    if (!pixivUser.value && !humanVerifyPrompted.has('pixiv')) {
      humanVerifyPrompted.add('pixiv')
      message.warning('P站 (Pixiv) 推荐流/收藏/关注更新等功能需要登录：请点左侧「打开内置浏览器登录」完成 Refresh Token 登录', { duration: 6000 })
    }
  } else if (s === 'javdb' && !searchResults.value.length) {
    // 进入 JavDB：加载当前 tags 模式的推荐作品（第五行数据源 = 模式列表）
    // 词库已到直接加载；未到则由 javdb_tags_vocab 事件回调自动加载
    if (javdbTagsVocab.value && javdbTagsVocab.value.length) {
      const m = javdbTagsVocab.value.find(x => x.key === javdbTagsMode.value) || javdbTagsVocab.value[0]
      if (m) handleJavdbTagsMode(m)
    }
  }
  // JavDB：首次进入请求标签词库（5 模式词表）+ 热搜关键词（功能栏常显）
  if (s === 'javdb' && window.api) {
    if (!javdbTagsVocab.value) window.api.sendCommand({ cmd: 'javdb_tags_vocab' })
    if (!javdbHotKeywords.value.length) window.api.sendCommand({ cmd: 'javdb_hot_search' })
  }
  // EX：进入站点自动加载首页推荐（与主站首页相同；已有结果/收藏视图时不打扰）
  if (s === 'exhentai' && !searchResults.value.length && !exFavMode.value && !exPopularMode.value
      && cameFromSearch.value === false) {
    handleExPopular(1)
  }
  // X 站：进入默认进入浏览模式（已登录且当前不在任何 X 视图时；未登录不打扰）
  if (s === 'twitter' && twitterUser.value && !twFollowMode.value) {
    handleTwBrowse()
  }
  // Hanime1 真人验证提示：使用前告知用户（未登录时弹提示，推荐内置浏览器登录完成验证）
  if (s === 'hanime' && !humanVerifyPrompted.has('hanime')) {
    humanVerifyPrompted.add('hanime')
    if (!hanimeUser.value) {
      message.warning('Hanime1 (H站) 需要真人验证（hCaptcha）：浏览/搜索偶发验证拦截，建议先点左侧"打开内置浏览器登录"，在弹窗内完成验证后再使用', { duration: 6000 })
    }
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
function handleTwGetFollows() {
  if (window.api) window.api.sendCommand({ cmd: 'twitter_get_follows' })
}

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
    twUserFeed.value = []
    twUserFeedCursor.value = ''
    twUserFeedHasMore.value = false
    twUserFeedUserId.value = ''
    twUserProfileStats.value = null
    twUserLoadAllRunning.value = false
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
  // 返回用户详情页时内容流为空：自动重新拉取（导航栈不存内容流数据）
  if (twFollowMode.value === 'user' && twViewUser.value
    && !twUserFeed.value.length && window.api) {
    twUserFeedUserId.value = String(twViewUser.value.user_id || '')
    twUserProfileStats.value = null
    twUserLoadAllRunning.value = false
    window.api.sendCommand({
      cmd: 'twitter_user_feed',
      screen_name: twViewUser.value.screen_name,
      user_id: String(twViewUser.value.user_id || ''),
      cursor: '',
    })
  }
}

// 查看用户详情（点开关注的人：显示 TA 的关注/粉丝入口 + 自动解析内容流展示在下方）
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
  // 点开博主即自动解析内容流（无需再手动点"解析 TA 的全部媒体"）
  twUserFeed.value = []
  twUserFeedCursor.value = ''
  twUserFeedHasMore.value = false
  twUserFeedUserId.value = String(u.user_id || '')
  twUserProfileStats.value = null
  twUserLoadAllRunning.value = false
  if (window.api) {
    window.api.sendCommand({
      cmd: 'twitter_user_feed',
      screen_name: u.screen_name,
      user_id: String(u.user_id || ''),
      cursor: '',
    })
  }
}

// 博主内容流：加载更多（UserMedia 时间线 cursor 翻页）
function handleTwUserFeedMore() {
  if (!window.api || twUserFeedLoading.value) return
  const u = twViewUser.value || {}
  window.api.sendCommand({
    cmd: 'twitter_user_feed',
    screen_name: u.screen_name || '',
    user_id: String(u.user_id || twUserFeedUserId.value || ''),
    cursor: twUserFeedCursor.value || '',
  })
}

// 博主内容流：一次加载全部（load_all 模式，后端自动翻完所有页，最终包 items=全量）
// 前端不循环，只做防抖；进度由 twitter_user_feed_progress 事件驱动
function handleTwUserFeedLoadAll() {
  if (!window.api) return
  if (twUserLoadAllRunning.value || twUserFeedLoading.value) return // 防重复点击
  const u = twViewUser.value || {}
  if (!u.screen_name && !twUserFeedUserId.value) return
  twUserLoadAllRunning.value = true
  twUserLoadAllProgress.loaded = twUserFeed.value.length
  twUserLoadAllProgress.total_media = twUserProfileStats.value?.media_count || 0
  window.api.sendCommand({
    cmd: 'twitter_user_feed',
    screen_name: u.screen_name || '',
    user_id: String(u.user_id || twUserFeedUserId.value || ''),
    cursor: '',
    load_all: true,
  })
}

// 用户页：生成/增量更新博主 HTML 相册（后端拉全部内容，已下载视频本地引用，存为「时间线.html」）
function handleTwExportHtml(payload) {
  if (!window.api) return
  if (twExportRunning.value) {
    message.info('HTML 相册正在导出中，请稍候…')
    return
  }
  const u = payload || twViewUser.value || {}
  if (!u.screen_name) return
  twExportRunning.value = true
  twExportProgress.phase = '准备'
  twExportProgress.done = 0
  message.info('正在拉取全部内容并生成/更新 HTML 相册…')
  window.api.sendCommand({
    cmd: 'twitter_export_html',
    screen_name: u.screen_name,
    user_id: String(u.user_id || ''),
  })
}

// 博主内容流：一键下载当前已加载的全部媒体（卡片自带与文件列表同构的条目）
async function handleTwUserFeedDownloadAll() {
  const items = []
  const seen = new Set()
  for (const c of twUserFeed.value) {
    for (const it of (c.media_items || [])) {
      const k = it.media_url
      if (!k || seen.has(k)) continue
      seen.add(k)
      items.push(it)
    }
  }
  if (!items.length) {
    message.warning('当前还没有可下载的内容，先等内容流加载出来')
    return
  }
  const u = twViewUser.value || {}
  // handleDownload 从 url.value 取任务 URL（后端 X 任务实际按 items.site 走媒体直链）
  url.value = u.album_url || `https://x.com/${u.screen_name || ''}`
  await handleDownload(items, {
    album_name: u.name || u.screen_name || 'X 下载',
  })
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
  // 常驻工具栏下，已在浏览模式内重复点击 = 刷新，不叠加导航栈
  if (twFollowMode.value !== 'browse') twPushNav()
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
  if (!window.api || twBrowseLoading.value || twBrowseLoadAllRunning.value) return
  window.api.sendCommand({ cmd: 'twitter_browse', offset: twBrowseNextOffset.value || 0 })
}

// 等待浏览模式当前一批拉取结束：loading 出现过再消失，或 offset 变化 / 无下一批；超时兜底
function waitTwBrowseRoundDone(prevOffset, timeoutMs = 90000) {
  return new Promise((resolve) => {
    const started = Date.now()
    let seenLoading = false
    const timer = setInterval(() => {
      if (Date.now() - started > timeoutMs) { clearInterval(timer); resolve(); return }
      if (twBrowseLoading.value) seenLoading = true
      else if (seenLoading
        || twBrowseNextOffset.value !== prevOffset
        || !twBrowseHasMore.value) {
        clearInterval(timer)
        resolve()
      }
    }, 150)
  })
}

// 浏览模式：自动连续翻页加载全部（每批间隔 1.2s 防限流；再点一次按钮 = 中止）
async function handleTwBrowseLoadAll() {
  if (!window.api) return
  // 运行中再点 = 置中止标志，循环每轮检查
  if (twBrowseLoadAllRunning.value) {
    twBrowseLoadAllAbort = true
    return
  }
  if (!twBrowseHasMore.value) {
    message.info('已加载全部关注博主的动态')
    return
  }
  twBrowseLoadAllRunning.value = true
  twBrowseLoadAllAbort = false
  twBrowseLoadAllCount.value = twBrowseFeed.value.length
  let aborted = false
  try {
    // 上限 50 批，防后端 offset 异常导致无限循环
    for (let round = 0; round < 50; round++) {
      if (twBrowseLoadAllAbort || twFollowMode.value !== 'browse') { aborted = true; break }
      if (twBrowseLoading.value) {
        // 上一批还没回来（或手动刷新中）：等它结束再发下一批
        await waitTwBrowseRoundDone(twBrowseNextOffset.value)
        continue
      }
      const prevOffset = twBrowseNextOffset.value
      window.api.sendCommand({ cmd: 'twitter_browse', offset: twBrowseNextOffset.value || 0 })
      await waitTwBrowseRoundDone(prevOffset)
      twBrowseLoadAllCount.value = twBrowseFeed.value.length
      if (twBrowseLoadAllAbort || twFollowMode.value !== 'browse') { aborted = true; break }
      if (!twBrowseHasMore.value) break // 后端已无下一批
      // 防限流：每批之间隔 1.2s（期间响应中止）
      for (let i = 0; i < 12 && !twBrowseLoadAllAbort; i++) {
        await new Promise(r => setTimeout(r, 100))
      }
    }
  } finally {
    twBrowseLoadAllRunning.value = false
    twBrowseLoadAllAbort = false
  }
  if (aborted) message.info('已停止加载全部')
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

// 切换迅雷式下载管理视图（占据主内容区，隐藏搜索面板）
function toggleDownloadManager() {
  detailVisible.value = !detailVisible.value
  if (detailVisible.value) {
    requestTasks()
  }
}

// 打开任务保存文件夹的上层目录
// 打开任务文件夹：直接打开后端为该任务创建的目录（task.save_dir，与下载时
// build_album_directory 创建的一致——"我们怎么创建的就打开哪个目录"）
function handleOpenTaskFolder(task) {
  const target = task && task.save_dir
  if (!target) {
    message.warning('任务尚未开始下载，暂无保存文件夹')
    return
  }
  if (window.api && window.api.openPath) {
    window.api.openPath(target).then(r => {
      if (r && r.ok === false) {
        message.error(`打开文件夹失败: ${r.error || '未知错误'}`)
      }
    }).catch(() => {})
  }
}

// 在文件管理器中定位任务里的某个文件（文件下载后记录 _final_path）
// 文件尚未下载完成时回退到打开任务的保存文件夹，保证按钮始终有响应
function handleLocateTaskFile(payload) {
  const f = payload && payload.file
  const task = payload && payload.task
  const fp = f && f._final_path
  if (fp && window.api && window.api.showInFolder) {
    window.api.showInFolder(fp).then(r => {
      if (r && r.ok === false) {
        message.error(`定位文件失败: ${r.error || '未知错误'}`)
      }
    }).catch(() => {})
    return
  }
  const dir = task && task.save_dir
  if (dir && window.api && window.api.openPath) {
    window.api.openPath(dir).then(r => {
      if (r && r.ok === false) {
        message.error(`打开文件夹失败: ${r.error || '未知错误'}`)
      }
    }).catch(() => {})
    return
  }
  message.warning('文件尚未下载完成，暂无保存位置')
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

// 重试任务：失败文件重置为待下载并重新开始
function retryTask(taskId) {
  if (window.api) window.api.sendCommand({ cmd: 'retry_task', task_id: taskId })
}

// 重试单个文件：仅该文件重置为待下载，其他失败文件不动
function retryFile({ taskId, itemPage }) {
  if (window.api) window.api.sendCommand({ cmd: 'retry_file', task_id: taskId, item_page: itemPage })
}

function resumeAllTasks() {
  downloadTasks.value
    .filter(t => t.status === 'paused')
    .forEach(t => resumeTask(t.id))
}

function cancelTask(taskId) {
  if (window.api) window.api.sendCommand({ cmd: 'cancel_task', task_id: taskId })
}

function removeTask(taskId, deleteFiles = false) {
  if (window.api) window.api.sendCommand({ cmd: 'remove_task', task_id: taskId, delete_files: !!deleteFiles })
}

// 清除所有任务（下载管理面板「清除所有任务」按钮；deleteFiles = 同时删除本地文件）
function clearAllTasks(deleteFiles = false) {
  if (window.api) window.api.sendCommand({ cmd: 'clear_tasks', delete_files: !!deleteFiles })
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
  // 获取当前程序版本号（设置区更新检查对比用）
  if (window.api && window.api.getAppVersion) {
    window.api.getAppVersion().then((v) => {
      appVersion.value = v || ''
    }).catch(() => { /* 开发环境下取不到也不影响 */ })
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
  // Leakedzone：Edge 过盾流程状态（专用 Edge 实例开/关 + 抓取结果提示）
  if (window.api && window.api.onLeakEdgeState) {
    window.api.onLeakEdgeState((payload) => {
      leakEdgeRunning.value = !!payload.running
      if (payload.error) message.error(payload.error)
      else if (payload.message) message.info(payload.message, 6000)
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
/* 批量下载入口按钮：增大增粗高亮（全站统一） */
.n-button.batch-cta {
  font-weight: 700;
  font-size: 13px;
  padding: 0 14px;
}
.n-button.batch-cta.n-button--primary-type {
  box-shadow: 0 0 8px rgba(99, 226, 183, 0.45);
}
</style>
<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body, #app {
  height: 100%;
  overflow: hidden;
  background: transparent;  /* 里/美好世界：透明窗口，圆角由界面容器绘制 */
}

/* ---------- 里/美好世界自定义标题栏（随模式变色；单按 Alt 不再弹菜单栏） ---------- */
.win-titlebar {
  position: fixed;
  top: 0; left: 0; right: 0;
  height: 38px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 12px 0 16px;
  z-index: 3000;
  -webkit-app-region: drag;
  backdrop-filter: blur(18px);
}
.win-titlebar.tb-dark {
  background: rgba(16, 19, 26, 0.82);
  border-bottom: 1px solid rgba(108, 140, 255, 0.18);
}
.win-titlebar.tb-light {
  background: rgba(246, 247, 251, 0.78);
  border-bottom: 1px solid rgba(255, 255, 255, 0.6);
}
.tb-badge {
  font-size: 11.5px; font-weight: 700; letter-spacing: 1px;
  padding: 3px 12px; border-radius: 999px;
}
.tb-dark .tb-badge { background: rgba(108, 140, 255, 0.16); color: #8fa4ff; border: 1px solid rgba(108, 140, 255, 0.35); }
.tb-light .tb-badge { background: rgba(108, 140, 255, 0.14); color: #4a54a8; border: 1px solid rgba(108, 140, 255, 0.3); }
.tb-app { font-size: 12.5px; font-weight: 600; }
.tb-dark .tb-app { color: #c6cede; }
.tb-light .tb-app { color: #3c415c; }
.tb-controls {
  margin-left: auto;
  display: flex; align-items: center; gap: 4px;
  -webkit-app-region: no-drag;
}
.tb-controls button {
  width: 38px; height: 26px;
  border: none; cursor: pointer;
  font-size: 12px;
  border-radius: 8px;
  transition: background .12s;
}
.tb-dark .tb-controls button { background: rgba(255,255,255,.06); color: #aeb7c9; }
.tb-dark .tb-controls button:hover { background: rgba(255,255,255,.14); }
.tb-light .tb-controls button { background: rgba(35,38,47,.06); color: #5a6072; }
.tb-light .tb-controls button:hover { background: rgba(35,38,47,.14); }
.tb-controls .tb-close:hover { background: #ff5f57 !important; color: #fff !important; }

/* ---------- 圆角窗口容器（经典/美好世界共用；最大化时贴边去圆角） ---------- */
.win-frame {
  position: absolute;
  top: 38px; left: 10px; right: 10px; bottom: 12px;
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.45);
}
.win-frame.win-maxed {
  top: 38px; left: 0; right: 0; bottom: 0;
  border-radius: 0;
  box-shadow: none;
}

/* 让 naive-ui 的 provider 包裹层也占满高度，否则内部 height:100% 会失效 */
.n-config-provider,
.n-message-provider,
.n-dialog-provider {
  height: 100%;
}

.app-layout {
  display: flex;
  height: 100%;
  background: #18181c;  /* 里世界：暗色（黑模式） */
}

/* 重名文件手动改名弹窗 */
.rename-modal {
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 13px;
}

/* 更新日志弹窗：内容区可下滑浏览多版本更新说明 */
.changelog-modal {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 13px;
}

.changelog-tip {
  color: #f2c97d;
}

.changelog-tip-latest {
  color: #63e2b7;
}

.changelog-scroll {
  max-height: 420px;
  padding-right: 6px;
}

.changelog-section {
  margin-bottom: 14px;
}

.changelog-section-title {
  font-weight: 600;
  font-size: 14px;
  color: #63e2b7;
  margin-bottom: 6px;
}

.changelog-section-date {
  font-weight: 400;
  font-size: 12px;
  color: #909090;
  margin-left: 8px;
}

.changelog-lines {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: #d8d8d8;
  line-height: 1.5;
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
  background: transparent;  /* 透明窗口：圆角外不可有底色 */
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
