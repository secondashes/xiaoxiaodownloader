<template>
  <div class="left-panel">
    <!-- 登录区：显示当前站点登录状态 -->
    <div class="login-section">
      <div class="login-icon" :class="{ 'login-icon-on': siteLoggedIn }">
        <n-icon size="28">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
          </svg>
        </n-icon>
      </div>
      <div class="login-text">
        <div class="login-title">小小下载器</div>
        <div class="login-subtitle">{{ loginSubtitle }}</div>
      </div>
      <div class="login-actions">
        <n-button
          quaternary
          size="small"
          :title="themeMode === 'light' ? '切换到夜间模式' : '切换到日间模式'"
          @click="emit('toggle-theme')"
        >
          <template #icon>
            <n-icon size="16">
              <svg v-if="themeMode === 'light'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="5"/>
                <line x1="12" y1="1" x2="12" y2="3"/>
                <line x1="12" y1="21" x2="12" y2="23"/>
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
                <line x1="1" y1="12" x2="3" y2="12"/>
                <line x1="21" y1="12" x2="23" y2="12"/>
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
              </svg>
            </n-icon>
          </template>
          {{ themeMode === 'light' ? '夜间' : '日间' }}
        </n-button>
        <n-button
          quaternary
          size="small"
          :type="activePanel === 'settings' ? 'primary' : 'default'"
          @click="activePanel = activePanel === 'settings' ? '' : 'settings'"
        >
          <template #icon>
            <n-icon size="16">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
            </n-icon>
          </template>
          {{ activePanel === 'settings' ? '收起' : '设置' }}
        </n-button>
      </div>
    </div>

    <!-- 站点快捷工具：打开网站（可选浏览器） + 使用帮助（各站点技巧，可复制） -->
    <div class="site-tools">
      <n-button size="small" secondary title="用所选浏览器打开当前站点首页" @click="openSiteInBrowser">
        打开网站
      </n-button>
      <n-select
        v-model:value="browserChoice"
        size="small"
        class="site-tools-browser"
        :options="browserOptions"
        title="选择用哪个浏览器打开"
      />
      <n-button size="small" tertiary type="info" title="查看当前站点的使用技巧与帮助" @click="showHelp = true">
        帮助
      </n-button>
    </div>

    <!-- 账号信息卡片（需登录站点：Pawchive / ExHentai / X），切换站点信息常驻不丢失 -->
    <div v-if="needsLogin" class="account-card" :class="{ 'account-card-on': siteLoggedIn }">
      <!-- 已登录：展示缓存信息（点击复制）+ 账号档案 + 登出 -->
      <template v-if="siteLoggedIn">
        <div class="account-status-row">
          <span class="account-status-dot" />
          <span class="account-status-text">已登录</span>
          <span class="account-site-name">{{ siteName(site) }}</span>
          <!-- Iwara：IW站/AI站 内容切换（登录信息共用） -->
          <n-button-group v-if="site === 'iwara'" size="tiny" class="iw-site-switch">
            <n-button
              size="tiny"
              :type="iwSite === 'iwara' ? 'primary' : 'default'"
              title="切换到 IW 站 (iwara.tv)"
              @click="emit('iw-set-site', 'iwara')"
            >IW站</n-button>
            <n-button
              size="tiny"
              :type="iwSite === 'ai' ? 'primary' : 'default'"
              title="切换到 AI 站 (iwara.ai)，账号通用"
              @click="emit('iw-set-site', 'ai')"
            >AI站</n-button>
          </n-button-group>
        </div>
        <div class="account-line" title="点击复制用户名" @click="copyText(siteUsername, '用户名')">
          <span class="account-line-label">账号</span>
          <span class="account-line-value">{{ siteUsername || '已登录' }}</span>
        </div>
        <div class="account-line" title="点击复制完整 Cookie" @click="copyText(siteCookieStr, 'Cookie')">
          <span class="account-line-label">Cookie</span>
          <span class="account-line-value account-cookie-value">{{ siteCookieStr ? (siteCookieStr.slice(0, 26) + '…') : '（空）' }}（点击复制）</span>
        </div>
        <div class="account-profiles">
          <n-select
            size="tiny"
            :value="siteActiveAccount || null"
            :options="accountOptions"
            placeholder="切换已保存账号"
            :disabled="accountOptions.length === 0"
            @update:value="v => emit('switch-account', site, v)"
          />
        </div>
        <div class="account-actions">
          <n-button size="tiny" @click="emit('save-account', site)">保存当前</n-button>
          <n-button
            size="tiny"
            tertiary
            type="error"
            :disabled="!siteActiveAccount"
            @click="emit('delete-account', site, siteActiveAccount)"
          >删除</n-button>
          <n-button
            size="tiny"
            title="重新验证当前登录信息（刷新登录状态，登录失效时会自动续期或提示重新登录）"
            @click="emit('refresh-login', site)"
          >重新登录</n-button>
          <n-button size="tiny" tertiary type="error" @click="handleSiteLogout">退出登录</n-button>
        </div>
        <!-- X 专属：清除推特缓存（大按钮，不删登录与关注分类） -->
        <div v-if="site === 'twitter'" class="tw-cache-clear">
          <n-button
            block
            size="small"
            secondary
            type="warning"
            title="清除：关注列表缓存 / 浏览模式缓存 / 用户媒体解析缓存 / 接口参数缓存（保留登录信息与关注分类）"
            @click="handleTwClearCache"
          >
            清除推特缓存
          </n-button>
        </div>
      </template>

      <!-- 未登录：登录表单 + 登录引导（打开登录页 / 一键抓取浏览器 Cookie） -->
      <template v-else>
        <!-- Pawchive 用户名密码登录 -->
        <div v-if="site === 'pawchive'" class="pawchive-login-form">
          <n-input
            v-model:value="loginUsername"
            size="small"
            placeholder="Pawchive 用户名"
            :disabled="loginLoading"
            @keyup.enter="handleLogin"
          />
          <n-input
            v-model:value="loginPassword"
            size="small"
            type="password"
            show-password-on="click"
            placeholder="密码"
            :disabled="loginLoading"
            @keyup.enter="handleLogin"
          />
          <n-button
            size="small"
            type="primary"
            block
            :loading="loginLoading"
            :disabled="!loginUsername.trim() || !loginPassword"
            @click="handleLogin"
          >
            {{ loginLoading ? '登录中...' : '登录' }}
          </n-button>
          <div class="login-hint">登录后可使用"我的收藏"功能</div>
        </div>

        <!-- Twitter/X cookie 登录（auth_token / ct0 分开填写） -->
        <div v-if="site === 'twitter'" class="pawchive-login-form">
          <n-input
            v-model:value="twAuthTokenInput"
            size="small"
            placeholder="auth_token（x.com 登录 Cookie）"
            :disabled="loginLoading"
            @keyup.enter="handleTwitterLogin"
          />
          <n-input
            v-model:value="twCt0Input"
            size="small"
            placeholder="ct0（x.com 登录 Cookie）"
            :disabled="loginLoading"
            @keyup.enter="handleTwitterLogin"
          />
          <n-button
            size="small"
            type="primary"
            block
            :disabled="!twAuthTokenInput.trim() || !twCt0Input.trim()"
            @click="handleTwitterLogin"
          >
            保存并验证登录
          </n-button>
          <div class="login-hint">
            浏览器登录 x.com → F12 → 应用 → Cookie → 分别复制 auth_token 和 ct0 的值填入上方两个框
          </div>
        </div>

        <!-- ExHentai cookie 登录（也可在右侧浏览器视图同步） -->
        <div v-if="site === 'exhentai'" class="pawchive-login-form">
          <n-input
            v-model:value="exCookieInput"
            size="small"
            type="password"
            show-password-on="click"
            placeholder="粘贴 Cookie（含 ipb_member_id / ipb_pass_hash）"
            @keyup.enter="handleExLogin"
          />
          <n-button
            size="small"
            type="primary"
            block
            :disabled="!exCookieInput.trim()"
            @click="handleExLogin"
          >
            保存并验证登录
          </n-button>
          <div class="login-hint">
            也可在右侧"浏览器"视图登录后点"同步Cookie"按钮
          </div>
        </div>

        <!-- Iwara 邮箱密码登录（token 长期保存，自动续期） -->
        <div v-if="site === 'iwara'" class="pawchive-login-form">
          <n-input
            v-model:value="iwaraEmailInput"
            size="small"
            placeholder="Iwara 登录邮箱"
            :disabled="iwaraLoginLoading"
            @keyup.enter="handleIwaraLogin"
          />
          <n-input
            v-model:value="iwaraPasswordInput"
            size="small"
            type="password"
            show-password-on="click"
            placeholder="密码"
            :disabled="iwaraLoginLoading"
            @keyup.enter="handleIwaraLogin"
          />
          <n-button
            size="small"
            type="primary"
            block
            :loading="iwaraLoginLoading"
            :disabled="!iwaraEmailInput.trim() || !iwaraPasswordInput"
            @click="handleIwaraLogin"
          >
            {{ iwaraLoginLoading ? '登录中...' : '登录' }}
          </n-button>
          <div class="login-hint">
            Iwara 账号密码登录；不登录也可搜索与下载公开视频，登录可看私密/好友限定
          </div>
          <!-- 未登录也可切换 IW站/AI站 内容（账号通用） -->
          <n-button-group size="tiny" class="iw-site-switch iw-site-switch-form">
            <n-button
              size="tiny"
              :type="iwSite === 'iwara' ? 'primary' : 'default'"
              title="切换到 IW 站 (iwara.tv)"
              @click="emit('iw-set-site', 'iwara')"
            >IW站</n-button>
            <n-button
              size="tiny"
              :type="iwSite === 'ai' ? 'primary' : 'default'"
              title="切换到 AI 站 (iwara.ai)，登录后账号通用"
              @click="emit('iw-set-site', 'ai')"
            >AI站</n-button>
          </n-button-group>
        </div>

        <!-- Hanime1 邮箱密码登录（H站；登录后可用收藏/评论/用户中心） -->
        <div v-if="site === 'hanime'" class="pawchive-login-form">
          <n-input
            v-model:value="hanimeEmailInput"
            size="small"
            placeholder="Hanime1 登录邮箱"
            :disabled="hanimeLoginLoading"
            @keyup.enter="handleHanimeLogin"
          />
          <n-input
            v-model:value="hanimePasswordInput"
            size="small"
            type="password"
            show-password-on="click"
            placeholder="密码"
            :disabled="hanimeLoginLoading"
            @keyup.enter="handleHanimeLogin"
          />
          <n-button
            size="small"
            type="primary"
            block
            :loading="hanimeLoginLoading"
            :disabled="!hanimeEmailInput.trim() || !hanimePasswordInput"
            @click="handleHanimeLogin"
          >
            {{ hanimeLoginLoading ? '登录中...' : '登录' }}
          </n-button>
          <div class="login-hint">
            H站账号密码登录；不登录也可浏览/搜索/下载视频，登录可收藏（稍後觀看）、发表评论、查看觀看紀錄
          </div>
        </div>

        <!-- 登录引导：打开登录页 / 一键抓取 -->
        <div class="login-guide">
          <n-button size="small" block secondary @click="emit('open-login-page', site)">
            打开登录页（浏览器）
          </n-button>
          <n-button
            v-if="site !== 'iwara' && site !== 'hanime'"
            size="small"
            block
            type="primary"
            @click="emit('fetch-cookies', site)"
          >
            一键抓取浏览器 Cookie（自动登录）
          </n-button>
          <div class="login-hint">
            {{ site === 'pawchive'
              ? '推荐直接用上方账号密码登录；一键抓取会自动读取浏览器登录信息'
              : site === 'twitter'
                ? '先在浏览器登录 x.com，再点上方按钮自动抓取登录信息'
                : site === 'iwara'
                  ? 'Iwara 使用邮箱密码登录（cookie 会过期，密码登录自动续期）；国内网络建议在设置里配置 Iwara 代理'
                  : site === 'hanime'
                    ? 'Hanime1 (H站) 使用邮箱密码登录；国内网络必须在设置里配置 H站代理'
                    : '先在浏览器登录 exhentai.org，再点上方按钮自动抓取登录信息' }}
          </div>
          <div v-if="site !== 'iwara' && site !== 'hanime'" class="login-hint">Chrome 新版加密抓取失败时，请右键管理员运行"抓取Cookie.bat"，结果在 cookies.txt</div>
        </div>

        <!-- 未登录但保存过账号档案：直接选择切换即可恢复登录（当前账号过期也能换） -->
        <div v-if="accountOptions.length" class="account-profiles logged-out-profiles">
          <n-select
            size="tiny"
            :value="siteActiveAccount || null"
            :options="accountOptions"
            placeholder="切换已保存账号"
            @update:value="v => emit('switch-account', site, v)"
          />
          <div class="account-actions">
            <n-button
              size="tiny"
              tertiary
              type="error"
              :disabled="!siteActiveAccount"
              @click="emit('delete-account', site, siteActiveAccount)"
            >删除档案</n-button>
          </div>
          <div class="login-hint">
            已保存 {{ accountOptions.length }} 个账号档案，选择即可切换登录（无需重新输入）
          </div>
        </div>
      </template>

      <!-- X 关注分类管理（母子类 tag 文件夹，保存在本地 cache/twitter_follow_tags.json） -->
      <div v-if="site === 'twitter'" class="follow-tag-section">
        <div class="follow-tag-title">关注分类管理（母类 / 子类）</div>
        <div class="follow-tag-add">
          <n-input v-model:value="newTagParent" size="tiny" placeholder="母类（如：画师）" />
          <n-input v-model:value="newTagChild" size="tiny" placeholder="子类（可留空）" />
          <n-button size="tiny" type="primary" @click="handleAddFollowTag">添加</n-button>
        </div>
        <div v-if="followTags.length === 0" class="follow-tag-empty">
          还没有分类。添加后在右侧"关注列表"里点用户卡片上的"分类"按钮归类。
        </div>
        <div v-for="t in followTags" :key="t.name" class="follow-tag-group">
          <div class="follow-tag-parent">
            <span class="follow-tag-name">{{ t.name }}</span>
            <n-button
              size="tiny"
              quaternary
              type="error"
              title="删除整个母类（含其下所有子类）"
              @click="emit('tw-delete-follow-tag', t.name, '')"
            >删除</n-button>
          </div>
          <div v-if="t.children && t.children.length" class="follow-tag-children">
            <n-tag
              v-for="c in t.children"
              :key="c"
              size="small"
              closable
              @close="emit('tw-delete-follow-tag', t.name, c)"
            >{{ c }}</n-tag>
          </div>
        </div>
      </div>
    </div>

    <n-divider style="margin: 0" />

    <!-- 圆形按钮组 -->
    <div class="round-buttons">
      <button class="round-btn" title="下载状态" @click="$emit('toggle-downloads')">
        <n-icon size="20">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <path d="M7 10l5 5 5-5"/>
            <path d="M12 15V3"/>
          </svg>
        </n-icon>
      </button>
      <!-- 日常标签：搜索历史快速搜索 -->
      <button
        class="round-btn"
        :class="{ 'round-btn-active': activePanel === 'history' }"
        :title="`日常标签（${searchHistory.length} 条搜索记录）`"
        @click="activePanel = activePanel === 'history' ? '' : 'history'"
      >
        <n-icon size="20">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.83z"/>
            <line x1="7" y1="7" x2="7.01" y2="7"/>
          </svg>
        </n-icon>
      </button>
      <!-- 本地收藏：跨站点收藏管理 -->
      <button
        class="round-btn"
        :class="{ 'round-btn-active': activePanel === 'favorites' }"
        :title="`本地收藏（${localFavorites.length} 条）`"
        @click="activePanel = activePanel === 'favorites' ? '' : 'favorites'"
      >
        <n-icon size="20">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 21s-7.5-4.9-10-9c-1.5-2.5 0-6 3.5-6 2 0 3.5 1 4.5 2.5C11 7 12.5 6 14.5 6c3.5 0 5 3.5 3.5 6-2.5 4.1-10 9-10 9z"/>
          </svg>
        </n-icon>
      </button>
      <!-- 识图（占位：未来以图搜源，暂未开放） -->
      <button
        class="round-btn"
        :class="{ 'round-btn-active': activePanel === 'ocr' }"
        title="识图（以网站识图获取详情，开发中）"
        @click="activePanel = activePanel === 'ocr' ? '' : 'ocr'"
      >
        <n-icon size="20">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
            <circle cx="12" cy="13" r="4"/>
          </svg>
        </n-icon>
      </button>
      <!-- 翻译（占位：谷歌/Edge 插件翻译全部网页内容，暂未开放） -->
      <button
        class="round-btn"
        :class="{ 'round-btn-active': activePanel === 'translate' }"
        title="翻译（谷歌/Edge 插件翻译全部网页内容，开发中）"
        @click="activePanel = activePanel === 'translate' ? '' : 'translate'"
      >
        <n-icon size="20">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 8l6 6"/>
            <path d="M4 14l6-6 2-3"/>
            <path d="M2 5h12"/>
            <path d="M7 2h1"/>
            <path d="M22 22l-5-10-5 10"/>
            <path d="M14 18h6"/>
          </svg>
        </n-icon>
      </button>
    </div>

    <!-- 识图占位面板 -->
    <div v-show="activePanel === 'ocr'" class="settings-section">
      <div class="settings-content">
        <div class="section-title">识图</div>
        <div class="placeholder-tip">
          以图搜源：上传/粘贴图片，调用识图网站获取来源详情。<br>
          该功能正在开发中，敬请期待。
        </div>
      </div>
    </div>
    <!-- 翻译占位面板 -->
    <div v-show="activePanel === 'translate'" class="settings-section">
      <div class="settings-content">
        <div class="section-title">翻译</div>
        <div class="placeholder-tip">
          调用谷歌 / Edge 浏览器插件的翻译能力，翻译应用内全部网页内容。<br>
          该功能正在开发中，敬请期待。
        </div>
      </div>
    </div>

    <!-- 日常标签面板（搜索历史快速搜索） -->
    <div v-show="activePanel === 'history'" class="settings-section">
      <n-scrollbar style="max-height: calc(100vh - 240px)">
        <div class="settings-content">
          <div class="section-title">日常标签（搜索历史）</div>

          <!-- 开关：控制点击标签是否直接进入对应网站 -->
          <div class="setting-switch">
            <div>
              <div class="switch-label">自动进入对应网站</div>
              <div class="switch-hint">开启后点击标签直接切换站点搜索，不再询问</div>
            </div>
            <n-switch
              :value="settings.search_history_switch_site"
              @update:value="v => update('search_history_switch_site', v)"
            />
          </div>

          <div class="panel-toolbar">
            <span class="panel-count">共 {{ searchHistory.length }} 条记录</span>
            <n-button
              v-if="searchHistory.length > 0"
              size="tiny"
              quaternary
              type="error"
              @click="$emit('clear-history')"
            >清空全部</n-button>
          </div>

          <!-- 标签列表：关键词 + 站点，点击快速搜索 -->
          <div class="tag-list">
            <div
              v-for="(h, i) in searchHistory"
              :key="`${h.query}-${h.site}-${i}`"
              class="tag-item"
              :title="`点击搜索「${h.query}」（来自 ${siteName(h.site)}）`"
              @click="$emit('use-history', h)"
            >
              <span class="tag-site" :data-site="h.site">{{ siteName(h.site) }}</span>
              <span class="tag-text">{{ h.query }}</span>
              <span v-if="h.search_mode" class="tag-mode">{{ h.search_mode === 'artist' ? '画师' : '标签' }}</span>
              <button class="tag-delete" title="删除这条记录" @click.stop="$emit('delete-history-item', h)">×</button>
            </div>
            <div v-if="searchHistory.length === 0" class="panel-empty">
              暂无搜索记录<br />
              <span class="panel-empty-hint">在右侧搜索框输入关键词后会自动记录</span>
            </div>
          </div>
        </div>
      </n-scrollbar>
    </div>

    <!-- 本地收藏面板（跨站点收藏管理） -->
    <div v-show="activePanel === 'favorites'" class="settings-section">
      <n-scrollbar style="max-height: calc(100vh - 240px)">
        <div class="settings-content">
          <div class="section-title">本地收藏</div>
          <div class="panel-empty-hint" style="margin-bottom: 10px">
            在右侧搜索结果卡片上点 ♥ 可快速收藏，点击下方条目直接打开
          </div>

          <div class="panel-toolbar">
            <span class="panel-count">共 {{ localFavorites.length }} 条收藏</span>
          </div>

          <!-- 收藏列表 -->
          <div class="fav-list">
            <div
              v-for="fav in localFavorites"
              :key="fav.id"
              class="fav-item"
              :title="`打开：${fav.url}`"
              @click="$emit('open-favorite', fav)"
            >
              <div class="fav-thumb-box">
                <img v-if="fav.thumbnail" :src="fav.thumbnail" class="fav-thumb" referrerpolicy="no-referrer" loading="lazy" />
                <span v-else class="fav-thumb-placeholder">{{ favTypeIcon(fav.type) }}</span>
              </div>
              <div class="fav-info">
                <div class="fav-title" :title="fav.title">{{ fav.title || '未命名' }}</div>
                <div class="fav-meta">
                  <span class="tag-site" :data-site="fav.site">{{ siteName(fav.site) }}</span>
                  <span v-if="fav.time">{{ fav.time.slice(0, 10) }}</span>
                </div>
              </div>
              <button class="tag-delete" title="删除这条收藏" @click.stop="$emit('delete-favorite', fav.id)">×</button>
            </div>
            <div v-if="localFavorites.length === 0" class="panel-empty">
              暂无本地收藏<br />
              <span class="panel-empty-hint">搜索结果卡片右上角的 ♥ 按钮可快速收藏</span>
            </div>
          </div>
        </div>
      </n-scrollbar>
    </div>

    <!-- 设置区（默认收起，点击"设置"展开） -->
    <div v-show="activePanel === 'settings'" class="settings-section">
      <n-scrollbar style="max-height: calc(100vh - 140px)">
        <div class="settings-content">
          <div class="section-title">下载设置</div>

          <!-- 下载路径 -->
          <div class="setting-item">
            <div class="setting-label">下载路径</div>
            <n-input-group>
              <n-input
                :value="settings.custom_path"
                placeholder="默认: 当前目录/Downloads"
                readonly
                style="flex: 1"
              />
              <n-button @click="selectFolder" type="primary" ghost>
                选择
              </n-button>
            </n-input-group>
          </div>

          <!-- 并发连接数 -->
          <div class="setting-item">
            <div class="setting-label">并发连接数</div>
            <n-input-number
              :value="settings.connections"
              @update:value="v => update('connections', v)"
              :min="1"
              :max="16"
              style="width: 100%"
            />
          </div>

          <!-- 并发下载文件数 -->
          <div class="setting-item">
            <div class="setting-label">并发下载文件数（同时下载几个文件）</div>
            <n-input-number
              :value="settings.concurrent_files"
              @update:value="v => update('concurrent_files', v)"
              :min="1"
              :max="5"
              style="width: 100%"
            />
          </div>

          <!-- 限速 -->
          <div class="setting-item">
            <div class="setting-label">限速 (KB/s，留空不限)</div>
            <n-input-number
              :value="settings.rate_limit"
              @update:value="v => update('rate_limit', v)"
              :min="0"
              placeholder="不限速"
              style="width: 100%"
              clearable
            />
          </div>

          <!-- 最大重试 -->
          <div class="setting-item">
            <div class="setting-label">最大重试次数</div>
            <n-input-number
              :value="settings.max_retries"
              @update:value="v => update('max_retries', v)"
              :min="0"
              :max="20"
              style="width: 100%"
            />
          </div>

          <n-divider style="margin: 8px 0" />

          <div class="section-title">文件夹组织</div>

          <!-- Pawchive 专属命名规则 -->
          <template v-if="site === 'pawchive'">
            <div class="setting-item">
              <div class="setting-label">Pawchive 文件夹组织（父文件夹为画师名）</div>
              <n-select
                :value="settings.pawchive_subfolder || 'date_post'"
                :options="pawchiveSubfolderOptions"
                @update:value="v => update('pawchive_subfolder', v)"
              />
            </div>
            <div class="setting-item">
              <div class="setting-label">Pawchive 自定义子文件夹模板（优先于上方规则）</div>
              <n-input
                :value="settings.pawchive_folder_template"
                placeholder="如 {date}/{title}，留空用上方规则"
                size="small"
                @change="v => update('pawchive_folder_template', v)"
              />
              <div class="switch-hint" style="margin-top: 4px">变量：{date}=年月 {date_full}=年月日 {title}=帖子标题 {id}=帖子ID</div>
            </div>
            <div class="setting-switch">
              <div>
                <div class="switch-label">搜索模式默认值</div>
                <div class="switch-hint">画师搜索或标签搜索（也可在搜索框旁切换）</div>
              </div>
              <n-select
                :value="settings.pawchive_search_mode || 'artist'"
                :options="searchModeOptions"
                style="width: 110px"
                @update:value="v => update('pawchive_search_mode', v)"
              />
            </div>
          </template>

          <!-- ExHentai 专属设置（代理 + 命名规则） -->
          <template v-if="site === 'exhentai'">
            <div class="setting-item">
              <div class="setting-label">ExHentai 代理地址（浏览器和下载都走此代理）</div>
              <n-input
                :value="settings.exhentai_proxy"
                placeholder="如 http://127.0.0.1:10809"
                size="small"
                @change="v => handleExProxyChange(v)"
              />
              <div class="switch-hint" style="margin-top: 4px">修改后自动应用到浏览器视图和下载后端</div>
            </div>
            <div class="setting-item">
              <div class="setting-label">ExHentai 文件夹组织（父文件夹为画师 tag）</div>
              <n-select
                :value="settings.exhentai_subfolder || 'date_post'"
                :options="pawchiveSubfolderOptions"
                @update:value="v => update('exhentai_subfolder', v)"
              />
            </div>
            <div class="setting-item">
              <div class="setting-label">ExHentai 自定义子文件夹模板（优先于上方规则）</div>
              <n-input
                :value="settings.exhentai_folder_template"
                placeholder="如 {date}/{title}，留空用上方规则"
                size="small"
                @change="v => update('exhentai_folder_template', v)"
              />
              <div class="switch-hint" style="margin-top: 4px">变量：{date}=年月 {date_full}=年月日 {title}=画廊标题 {id}=帖子ID</div>
            </div>
          </template>

          <!-- Twitter/X 专属设置（代理 + 命名规则） -->
          <template v-if="site === 'twitter'">
            <div class="setting-item">
              <div class="setting-label">X (Twitter) 代理地址（API 和媒体下载都走此代理）</div>
              <n-input
                :value="settings.twitter_proxy"
                placeholder="如 http://127.0.0.1:10809"
                size="small"
                @change="v => $emit('twitter-set-proxy', v)"
              />
              <div class="switch-hint" style="margin-top: 4px">国内必须配置代理才能访问 x.com</div>
            </div>
            <div class="setting-item">
              <div class="setting-label">X 文件夹组织（父文件夹为用户名）</div>
              <n-select
                :value="settings.twitter_subfolder || 'date_post'"
                :options="pawchiveSubfolderOptions"
                @update:value="v => update('twitter_subfolder', v)"
              />
            </div>
            <div class="setting-item">
              <div class="setting-label">X 自定义子文件夹模板（优先于上方规则）</div>
              <n-input
                :value="settings.twitter_folder_template"
                placeholder="如 {date}/{id}，留空用上方规则"
                size="small"
                @change="v => update('twitter_folder_template', v)"
              />
              <div class="switch-hint" style="margin-top: 4px">变量：{date}=年月 {date_full}=年月日 {title}=推文内容 {id}=推文ID</div>
            </div>
          </template>

          <!-- Iwara 专属设置（代理 + 文件夹模板） -->
          <template v-if="site === 'iwara'">
            <div class="setting-item">
              <div class="setting-label">Iwara 代理地址（API 和下载都走此代理，留空 = 直连）</div>
              <n-input
                :value="settings.iwara_proxy"
                placeholder="如 http://127.0.0.1:10809，留空直连"
                size="small"
                @change="v => $emit('iwara-set-proxy', v)"
              />
              <div class="switch-hint" style="margin-top: 4px">国内建议配置代理；Iwara 可直连时可留空提速</div>
            </div>
            <div class="setting-item">
              <div class="setting-label">Iwara 自定义子文件夹模板（默认按 年月 存放）</div>
              <n-input
                :value="settings.iwara_folder_template"
                placeholder="如 {date}/{title}，留空=YYYY-MM"
                size="small"
                @change="v => update('iwara_folder_template', v)"
              />
              <div class="switch-hint" style="margin-top: 4px">变量：{date}=年月 {date_full}=年月日 {title}=视频标题 {id}=视频ID；下载默认取最高画质（Source）</div>
            </div>
          </template>

          <!-- Hanime1 专属设置（代理） -->
          <template v-if="site === 'hanime'">
            <div class="setting-item">
              <div class="setting-label">Hanime1 (H站) 代理地址（浏览/搜索/下载都走此代理）</div>
              <n-input
                :value="settings.hanime_proxy"
                placeholder="如 http://127.0.0.1:10809"
                size="small"
                @change="v => $emit('hanime-set-proxy', v)"
              />
              <div class="switch-hint" style="margin-top: 4px">国内必须配置代理才能访问 hanime1.me；下载默认取最高画质（1080P）</div>
            </div>
          </template>

          <!-- Oreno3D 专属设置（代理，默认直连） -->
          <template v-if="site === 'oreno3d'">
            <div class="setting-item">
              <div class="setting-label">Oreno3D (O3D) 代理地址（浏览/搜索/下载都走此代理，留空 = 直连）</div>
              <n-input
                :value="settings.oreno_proxy"
                placeholder="如 http://127.0.0.1:10809，留空直连"
                size="small"
                @change="v => $emit('oreno-set-proxy', v)"
              />
              <div class="switch-hint" style="margin-top: 4px">Oreno3D 一般可直连；无法访问时再填代理。视频实际从 Iwara 源下载（最高画质）</div>
            </div>
          </template>

          <!-- 按文件类型分类 -->
          <div class="setting-switch">
            <div>
              <div class="switch-label">按文件类型分类</div>
              <div class="switch-hint">将图片/视频/音频等分到不同子文件夹</div>
            </div>
            <n-switch
              :value="settings.organize_by_type"
              @update:value="v => update('organize_by_type', v)"
            />
          </div>

          <!-- 日期戳 -->
          <div class="setting-switch">
            <div>
              <div class="switch-label">相册名加日期戳</div>
              <div class="switch-hint">文件夹名格式: 相册名_YYYYMMDD</div>
            </div>
            <n-switch
              :value="settings.date_stamp"
              @update:value="v => update('date_stamp', v)"
            />
          </div>

          <!-- 不创建 Downloads 子文件夹 -->
          <div class="setting-switch">
            <div>
              <div class="switch-label">不创建 Downloads 子文件夹</div>
              <div class="switch-hint">直接保存到指定路径</div>
            </div>
            <n-switch
              :value="settings.no_download_folder"
              @update:value="v => update('no_download_folder', v)"
            />
          </div>

          <!-- 跳过重复项目（下载去重） -->
          <div class="setting-switch">
            <div>
              <div class="switch-label">跳过重复项目</div>
              <div class="switch-hint" title="下载前检查本地同路径同名文件：大小一致 = 已下载过，直接跳过；大小不同 = 重名冲突，按下方改名规则处理">
                同名且大小一致时直接跳过不下载；重名时按"重名改名"规则处理
              </div>
            </div>
            <n-tooltip trigger="hover" placement="top">
              <template #trigger>
                <n-switch
                  :value="settings.skip_duplicates"
                  @update:value="v => update('skip_duplicates', v)"
                />
              </template>
              开启后：下载前逐个检查本地是否已有同名文件。
              大小一致 → 判定为重复，直接跳过（日志显示"跳过重复"）；
              大小不同 → 按下方"重名手动改名"开关处理
            </n-tooltip>
          </div>

          <!-- 重名改名（手动 / 自动序号顺延） -->
          <div class="setting-switch" v-if="settings.skip_duplicates">
            <div>
              <div class="switch-label">重名手动改名</div>
              <div class="switch-hint" title="开启：弹出手动改名窗口，自己输入新文件名后重新下载；关闭：自动命名为排列序号顺延，如 file.jpg → file (1).jpg、file (2).jpg">
                开：弹窗手动输入新文件名；关：自动命名为序号顺延（如 file (1).jpg）
              </div>
            </div>
            <n-tooltip trigger="hover" placement="top">
              <template #trigger>
                <n-switch
                  :value="settings.manual_rename"
                  @update:value="v => update('manual_rename', v)"
                />
              </template>
              只在"跳过重复项目"开启时生效。
              开启 = 遇到重名（大小不同）时弹窗，手动输入新文件名；
              关闭 = 自动在文件名后加序号顺延，如 file.jpg → file (1).jpg
            </n-tooltip>
          </div>

          <n-divider style="margin: 8px 0" />

          <div class="section-title">文件名与过滤</div>

          <!-- 保留原始文件名 -->
          <div class="setting-switch">
            <div>
              <div class="switch-label">保留原始文件名</div>
              <div class="switch-hint">使用页面上的原始文件名</div>
            </div>
            <n-switch
              :value="settings.clean_name"
              @update:value="v => update('clean_name', v)"
            />
          </div>

          <!-- 忽略列表 -->
          <div class="setting-item">
            <div class="setting-label">忽略列表（文件名包含这些词则跳过）</div>
            <n-dynamic-tags
              :value="settings.ignore"
              @update:value="v => update('ignore', v)"
              type="warning"
            />
          </div>

          <!-- 包含列表 -->
          <div class="setting-item">
            <div class="setting-label">包含列表（仅下载文件名包含这些词的）</div>
            <n-dynamic-tags
              :value="settings.include"
              @update:value="v => update('include', v)"
              type="success"
            />
          </div>

          <!-- 悬浮窗 -->
          <n-divider style="margin: 8px 0" />
          <div class="section-title">悬浮窗</div>
          <div class="setting-switch">
            <div>
              <div class="switch-label">显示下载悬浮窗</div>
              <div class="switch-hint">在桌面显示下载速度悬浮窗</div>
            </div>
            <n-switch
              :value="floatVisible"
              @update:value="v => $emit('toggle-float', v)"
            />
          </div>

          <!-- 后端状态 -->
          <n-divider style="margin: 8px 0" />
          <div class="backend-status">
            <n-badge
              :type="backendReady ? 'success' : (backendError ? 'error' : 'default')"
              :status="backendReady ? 'success' : (backendError ? 'error' : 'default')"
              dot
              :processing="!backendReady && !backendError"
            />
            <span class="backend-status-text" :class="{ 'backend-status-err': backendError }">
              {{ backendReady ? '后端已连接' : (backendError ? '后端启动失败' : '正在连接后端...') }}
            </span>
          </div>
          <!-- 启动失败原因 + 解决办法（傻瓜式提示） -->
          <div v-if="backendError && !backendReady" class="backend-error-box">
            <div class="backend-error-msg">{{ backendError }}</div>
            <div class="backend-error-fix">
              解决方法：<br />
              1. 安装 Python 3.10+（官网 python.org 下载，安装时务必勾选 "Add python.exe to PATH"）<br />
              2. 安装依赖：在程序目录运行 pip install -r requirements.txt<br />
              3. 或直接使用打包版程序（无需安装 Python）
            </div>
          </div>

          <!-- 清除缓存 -->
          <div class="setting-item" style="margin-top: 16px">
            <n-button
              block
              secondary
              type="warning"
              @click="handleClearCache"
            >
              清除缓存（缩略图 + 相册信息）
            </n-button>
          </div>
        </div>
      </n-scrollbar>
    </div>

    <!-- 站点使用帮助弹窗（各站点技巧，内容可选中复制 / 一键复制全部） -->
    <n-modal
      v-model:show="showHelp"
      preset="card"
      class="site-help-modal"
      :title="`${siteName(site)} · 使用帮助`"
      style="width: 640px; max-width: 92vw"
    >
      <div class="site-help-actions">
        <n-button size="small" tertiary @click="copyText(helpText, '帮助内容')">
          复制全部
        </n-button>
        <span class="site-help-tip">内容可直接选中复制</span>
      </div>
      <pre class="site-help-pre">{{ helpText }}</pre>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useMessage } from 'naive-ui'

const props = defineProps({
  settings: { type: Object, required: true },
  site: { type: String, default: 'bunkr' },
  pawchiveUser: { type: String, default: '' },
  twitterUser: { type: String, default: '' },
  exhentaiUser: { type: String, default: '' },
  iwaraUser: { type: String, default: '' },
  iwaraLoginLoading: { type: Boolean, default: false },
  // Iwara 当前内容站点：'iwara'（IW站）| 'ai'（AI站）
  iwSite: { type: String, default: 'iwara' },
  // Hanime1 登录用户名（H站，邮箱密码登录）
  hanimeUser: { type: String, default: '' },
  hanimeLoginLoading: { type: Boolean, default: false },
  // 全站点登录信息（后端 login_info 事件：用户名/Cookie/账号档案）
  loginInfo: { type: Object, default: () => ({}) },
  loginLoading: { type: Boolean, default: false },
  backendReady: { type: Boolean, default: false },
  backendError: { type: String, default: '' },
  floatVisible: { type: Boolean, default: true },
  // 搜索历史（日常标签）
  searchHistory: { type: Array, default: () => [] },
  // 本地收藏列表
  localFavorites: { type: Array, default: () => [] },
  // X 关注分类（母子 tag）：[{name, children: []}]
  followTags: { type: Array, default: () => [] },
  // 界面主题：dark=夜间 / light=日间
  themeMode: { type: String, default: 'dark' },
})

const emit = defineEmits([
  'update:settings',
  'clear-cache',
  'toggle-downloads',
  'toggle-float',
  'pawchive-login',
  'pawchive-logout',
  'pawchive-favorites',
  // Twitter/X
  'twitter-set-cookies',  // 保存 cookie 并验证登录（参数：cookie 字符串）
  'twitter-logout',       // 退出 X 登录
  'twitter-set-proxy',     // 修改 X 代理（参数：代理地址）
  // Iwara
  'iwara-login',           // 邮箱密码登录（参数：邮箱, 密码）
  'iwara-logout',          // 退出 Iwara 登录
  'iwara-set-proxy',       // 修改 Iwara 代理（参数：代理地址，空=直连）
  'iw-set-site',           // IW站/AI站 内容切换（参数：'iwara' | 'ai'，登录信息共用）
  // Hanime1（H站）
  'hanime-login',          // 邮箱密码登录（参数：邮箱, 密码）
  'hanime-logout',         // 退出 Hanime1 登录
  'hanime-set-proxy',      // 修改 Hanime1 代理（参数：代理地址，国内必须）
  // Oreno3D（O3D）
  'oreno-set-proxy',       // 修改 Oreno3D 代理（参数：代理地址，空=直连）
  'tw-add-follow-tag',    // 新增关注分类（参数：母类, 子类）
  'tw-delete-follow-tag', // 删除关注分类（参数：母类, 子类）
  'tw-clear-cache',       // 清除 Twitter 专属缓存
  'toggle-theme',         // 切换日间/夜间模式
  // ExHentai
  'exhentai-set-cookies', // 粘贴 cookie 登录 EX
  'exhentai-logout',      // 退出 EX 登录
  // 登录引导 / 账号档案
  'open-login-page',      // 打开登录页（参数：站点 key）
  'fetch-cookies',        // 一键抓取浏览器 Cookie 并自动登录（参数：站点 key）
  'refresh-login',        // 重新检查登录状态（参数：站点 key）
  'save-account',         // 保存当前登录为账号档案（参数：站点 key）
  'switch-account',       // 切换账号档案（参数：站点 key, 档案名）
  'delete-account',       // 删除账号档案（参数：站点 key, 档案名）
  // 搜索历史（日常标签）
  'use-history',          // 点击标签快速搜索（参数：历史条目）
  'delete-history-item',  // 删除单条历史（参数：历史条目）
  'clear-history',        // 清空全部历史
  // 本地收藏
  'open-favorite',        // 打开收藏（参数：收藏条目）
  'delete-favorite',      // 删除收藏（参数：收藏 id）
])

const message = useMessage()

// 当前展开的面板：'' | 'settings' | 'history' | 'favorites'
const activePanel = ref('')

// ============================
// 登录状态（账号卡片）
// ============================
const needsLogin = computed(() => ['pawchive', 'twitter', 'exhentai', 'iwara', 'hanime'].includes(props.site))

const siteLoggedIn = computed(() => {
  if (props.site === 'pawchive') return !!props.pawchiveUser
  if (props.site === 'twitter') return !!props.twitterUser
  if (props.site === 'exhentai') return !!props.exhentaiUser
  if (props.site === 'iwara') return !!props.iwaraUser
  if (props.site === 'hanime') return !!props.hanimeUser
  return false
})

const loginSubtitle = computed(() => {
  if (!needsLogin.value) return '无需登录'
  if (props.site === 'twitter') return props.twitterUser ? `X 已登录: @${props.twitterUser}` : 'X (Twitter) 未登录'
  if (props.site === 'pawchive') return props.pawchiveUser ? `已登录: ${props.pawchiveUser}` : 'Pawchive 未登录'
  if (props.site === 'exhentai') return props.exhentaiUser ? 'ExHentai 已登录' : 'ExHentai 未登录'
  if (props.site === 'iwara') return props.iwaraUser ? `Iwara 已登录: ${props.iwaraUser}` : 'Iwara 未登录'
  if (props.site === 'hanime') return props.hanimeUser ? `H站已登录: ${props.hanimeUser}` : 'Hanime1 未登录'
  return ''
})

// 当前站点的登录信息（来自后端缓存文件，切换站点不丢失）
const siteLoginInfo = computed(() => props.loginInfo[props.site] || {})
const siteUsername = computed(() => {
  if (props.site === 'twitter' && props.twitterUser) return props.twitterUser
  if (props.site === 'pawchive' && props.pawchiveUser) return props.pawchiveUser
  return siteLoginInfo.value.username || ''
})
const siteCookieStr = computed(() => siteLoginInfo.value.cookie_str || '')
const siteActiveAccount = computed(() => siteLoginInfo.value.active || '')
const accountOptions = computed(() => {
  const profiles = siteLoginInfo.value.accounts || {}
  return Object.values(profiles).map(p => ({
    label: p.label || p.username || '未命名',
    value: p.label || '',
  }))
})

// ============================
// 站点快捷工具（打开网站 / 帮助）
// ============================
// 各站点首页地址（"打开网站"按钮）
const SITE_URLS = {
  bunkr: 'https://bunkr.sk',
  coomer: 'https://xxxcoomer.com',
  pawchive: 'https://pawchive.pw',
  exhentai: 'https://exhentai.org',
  twitter: 'https://x.com',
  iwara: 'https://www.iwara.tv',
  hanime: 'https://hanime1.me',
  oreno3d: 'https://oreno3d.com',
}

// 浏览器选择（默认 = 系统默认浏览器）
const browserChoice = ref('')
const browserOptions = [
  { label: '默认浏览器', value: '' },
  { label: 'Chrome', value: 'chrome' },
  { label: 'Edge', value: 'edge' },
  { label: 'Firefox', value: 'firefox' },
]

const showHelp = ref(false)

// 打开当前站点首页（按所选浏览器）
async function openSiteInBrowser() {
  const url = SITE_URLS[props.site] || 'https://bunkr.sk'
  try {
    if (window.api && window.api.openWithBrowser) {
      const r = await window.api.openWithBrowser(url, browserChoice.value)
      if (r && r.ok === false) {
        message.error(r.error || '打开失败')
        return
      }
    } else if (window.api) {
      await window.api.openExternal(url)
    } else {
      window.open(url, '_blank')
      return
    }
    message.info(`已打开 ${siteName(props.site)}（${browserChoice.value ? browserOptions.find(o => o.value === browserChoice.value).label : '默认浏览器'}），登录后可点"一键抓取浏览器 Cookie"`)
  } catch (e) {
    message.error('打开浏览器失败：' + (e.message || e))
  }
}

// 各站点使用技巧（帮助弹窗内容，可复制）
const SITE_HELP_TIPS = {
  bunkr: `📁 关于 Bunkr 与 Gofile 网盘

这两个网盘在国外免费文件分享社区中非常流行，常被用于存储和分发以下内容：

图片、漫画包、Cosplay 图集
游戏 Mod 整合包
部分付费平台的泄露资源（例如 OnlyFans）

⚠️ 注意：这些内容在国内搜索引擎中几乎无法检索到，主要信息源来自海外社区。

🔍 如何找到这些网盘上的资源？

以下三条是最容易上手的路径，按推荐顺序排列：

1. Reddit 社区挖掘
前往以下几个活跃板块，直接浏览或搜索：
r/DataHoarder · r/opendirectories · r/Piracy · r/NSFW411 · r/FreeOnlyFansLeaks（或搜索 onlyfans leak bunkr）

搜索技巧：
基础格式：网盘名 + 关键词
实例：bunkr onlyfans 2025、bunkr cosplay pack、gofile mod pack

很多帖子会直接贴出链接，或者把一串链接放在 Pastebin / TXT 文件中，点进去就能下载。

2. X（原推特）实时追踪
直接在搜索框输入：
bunkr link OR gofile link + 你感兴趣的关键词

例如：bunkr onlyfans OR gofile cosplay
你会发现不少专门发布泄露链接的账号，关注它们可以每天获取新鲜资源（不过失效链接也很多，时效性较强）。

3. 其他社区与论坛
socialmediagirls.com（搜模特名字 + bunkr）
forum.ripper.store（批量下载教程和链接多）
Pastebin.com 搜 "bunkr links 2026" 或 "gofile mega pack"

💡 本工具提示：
- 找到 bunkr 相册链接后，直接粘贴到右侧地址栏即可解析下载
- 也可用顶部搜索框在相册索引站搜关键词找资源`,
  coomer: `🐱 Coomer（xxxcoomer.com）使用技巧

Coomer 是聚合 OnlyFans / Fansly 等平台内容的档案馆站。

🔍 如何找资源：
1. 直接访问 xxxcoomer.com，按服务分类浏览（OnlyFans / Fansly 等）
2. 搜索框输入作者名字（部分站点有索引）
3. Reddit 板块：r/OnlyFansLeaksStyle 等常有 Coomer 链接分享
4. Google 搜索：site:coomer.su 作者名（域名会轮换，注意最新域名）

💡 本工具提示：
- 作者页链接格式：/creator/{服务}/{用户ID}/{用户名}，粘贴到地址栏可解析全部帖子
- 单个帖子链接也可直接下载
- ⚠️ 站点限流很凶：连续请求会被 IP 封锁，本工具已内置自动限流，遇到失败请稍等几分钟再试
- 视频直链带签名会过期，下载时本工具会自动重新抓取新链接`,
  pawchive: `🐾 Pawchive（pawchive.pw）使用技巧

Pawchive 是 Kemono 架构的聚合站（画师作品档案馆）。

🔍 如何找资源：
1. 直接访问 pawchive.pw，首页可按服务/更新浏览
2. 画师页 URL：/{服务}/user/{画师ID}，粘贴到地址栏即可解析
3. 相关社区（Reddit / Discord）常分享画师链接

💡 本工具提示：
- 左侧支持用户名密码登录（也可一键抓取浏览器 Cookie）
- 登录后可使用"我的收藏"功能收藏喜欢的画师
- 点开画师卡片可查看全部帖子（按发布日期倒序），支持批量解析全部媒体
- 下载自动归类到"画师名/年-月/帖子标题"目录
- ⚠️ 站点有下载限速，本工具已强制限速间隔，批量下载请耐心等待`,
  exhentai: `📖 ExHentai（exhentai.org）使用技巧

🔍 访问与登录：
1. 需先在 e-hentai.org 注册账号并登录
2. 无 Cookie 访问 exhentai 会显示 sadpanda（空白页）
3. 登录后 Cookie 关键字段：ipb_member_id、ipb_pass_hash、igneous

💡 本工具提示：
- 左侧粘贴 Cookie 登录，或点"打开网站"在右侧内置浏览器登录后点"同步Cookie"
- ⚠️ 国内网络必须配置代理（设置区可填），否则无法访问
- 画廊页支持标签搜索、我的收藏、种子下载（磁力链接）
- 右侧"浏览器"视图可像网页一样浏览，支持后退/前进/刷新
- ⚠️ 请求过快会触发 509 限流，本工具已内置节流
- 标签隐藏功能：设置区输入不想看到的 tags 可长期屏蔽`,
  twitter: `🐦 X / Twitter 使用技巧

🔑 登录方法（Cookie 方式）：
1. 浏览器登录 x.com
2. F12 → 应用/Application → Cookie → 复制 auth_token 和 ct0
3. 粘贴到左侧登录框，或直接点"一键抓取浏览器 Cookie"

💡 本工具提示：
- ⚠️ 国内必须配置代理（左侧 X 代理设置，默认 http://127.0.0.1:10809）
- 搜索 @用户名 可精确查找用户；直接输入关键词搜索相关推文
- 用户主页可解析全部图片/视频（自动翻页）
- "关注列表"查看/关注/取关；"浏览模式"聚合关注对象最新推文
- 关注分类（母类/子类）帮你管理大量关注
- 下载目录：用户名/年-月/推文内容（可在设置里改规则）
- 接口参数会定期轮换，本工具自动更新，遇到异常可点"清除推特缓存"`,
  iwara: `🎬 Iwara（iwara.tv）使用技巧

Iwara 是 MMD 视频社区，支持邮箱密码登录。

🔑 登录：
- 左侧邮箱密码登录即可，密码会加密保存，过期自动续期
- 不登录也能搜索下载公开视频，登录可看私密/好友限定内容

💡 本工具提示：
- IW站（iwara.tv）与 AI站（iwara.ai）可一键切换，账号通用
- 主页看最近更新；"我关注的更新"只看已关注作者的新投稿
- @用户名 可搜索作者并拉取全部视频
- 视频详情页支持播放、查看简介/tags、评论区、关注作者
- 下载默认选最高画质；目录格式：作者名/年-月/标题.mp4（可自定义模板）
- 国内网络如打不开，在左侧设置里填 Iwara 代理`,
  hanime: `🎬 Hanime1（H站）使用技巧

Hanime1 是里番（成人动画）视频站，支持邮箱密码登录。

🔑 登录：
- 左侧邮箱密码登录即可，登录信息加密保存
- 不登录也能浏览/搜索/播放/下载视频，登录可收藏（稍後觀看）、发表评论、查看觀看紀錄

💡 本工具提示：
- ⚠️ 国内必须配置代理（左侧 H站代理设置，默认 http://127.0.0.1:10809）
- 主页按分区展示（最新上市/最新上傳 + 各分类）
- 搜索支持关键词 + 分类（裏番/泡麵番/3DCG/MMD 等）+ 排序（本日排行/觀看次數等）
- 点视频卡片进详情：在线播放、查看标签/简介、收藏、评论区（可发表评论）
- 用户中心：觀看紀錄 / 稍後觀看 / 讚好的影片 / 上傳的影片 / 審核中的影片
- 下载默认取最高画质（1080P）；粘贴 hanime1.me/watch?v=xxx 链接也可直接解析下载`,
  oreno3d: `🎥 Oreno3D（O3D）使用技巧

Oreno3D 是日本 3D 动画（MMD 等）视频索引站，视频源托管在 Iwara。

🔑 无需登录：直接浏览/搜索/下载

💡 本工具提示：
- 主页默认按人気排序，可切换 お気に入り/最新/閲覧数
- "标签索引"弹窗列出全部标签，点击标签看该分类视频
- 点视频卡片进详情：在线播放（iwara 源最高画质）、查看作者/标签/统计
- 点作者名可查看 TA 的全部作品；点 iwara 链接可跳转原站
- 下载实际从 Iwara 源获取（最高画质），无需登录
- O3D 一般可直连；无法访问时在左侧设置里填代理`,
}

// 当前站点的帮助内容
const helpText = computed(() => SITE_HELP_TIPS[props.site] || '暂无帮助内容')

// 点击复制到剪贴板
async function copyText(text, label) {
  if (!text) {
    message.warning('内容为空，无法复制')
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    message.success(`${label}已复制到剪贴板`)
  } catch {
    message.error('复制失败，请手动选择复制')
  }
}

// 退出当前站点登录
function handleSiteLogout() {
  if (props.site === 'pawchive') emit('pawchive-logout')
  else if (props.site === 'twitter') emit('twitter-logout')
  else if (props.site === 'exhentai') emit('exhentai-logout')
  else if (props.site === 'iwara') emit('iwara-logout')
  else if (props.site === 'hanime') emit('hanime-logout')
}

// 清除 Twitter 专属缓存（确认后执行，保留登录与关注分类）
function handleTwClearCache() {
  if (window.confirm(
    '确定清除推特缓存吗？\n\n将清除：关注列表缓存 / 浏览模式缓存 / 用户媒体解析缓存 / 接口参数缓存\n保留：登录信息 / 关注分类（母子 tag）与已归类关注\n\n清除后重新打开对应页面会自动重新拉取。'
  )) {
    emit('tw-clear-cache')
  }
}

// Pawchive 登录表单
const loginUsername = ref('')
const loginPassword = ref('')

// X 登录：auth_token / ct0 分开填写（也兼容粘贴带名称的完整值）
const twAuthTokenInput = ref('')
const twCt0Input = ref('')

// 提取值：去掉可能粘贴进来的 "name=" 前缀或整段 Cookie 字符串里的对应值
function extractTwValue(raw, name) {
  let text = (raw || '').trim()
  if (!text) return ''
  if (text.includes('=')) {
    // 粘贴了整段 Cookie 或带名称的值：解析出目标键
    for (const pair of text.split(';')) {
      const [k, ...rest] = pair.trim().split('=')
      if (k && k.trim() === name) return rest.join('=').trim()
    }
    // 不是目标键的 name=value：视为无效粘贴
    const firstEq = text.indexOf('=')
    if (text.slice(0, firstEq).trim() !== name) return ''
    text = text.slice(firstEq + 1).trim()
  }
  return text
}

// ExHentai cookie 登录表单
const exCookieInput = ref('')

// Iwara 邮箱密码登录表单
const iwaraEmailInput = ref('')
const iwaraPasswordInput = ref('')

function handleIwaraLogin() {
  if (!iwaraEmailInput.value.trim() || !iwaraPasswordInput.value) return
  emit('iwara-login', iwaraEmailInput.value.trim(), iwaraPasswordInput.value)
}

// Hanime1 邮箱密码登录表单
const hanimeEmailInput = ref('')
const hanimePasswordInput = ref('')

function handleHanimeLogin() {
  if (!hanimeEmailInput.value.trim() || !hanimePasswordInput.value) return
  emit('hanime-login', hanimeEmailInput.value.trim(), hanimePasswordInput.value)
}

function handleTwitterLogin() {
  const authToken = extractTwValue(twAuthTokenInput.value, 'auth_token')
  const ct0 = extractTwValue(twCt0Input.value, 'ct0')
  if (!authToken || !ct0) return
  emit('twitter-set-cookies', `auth_token=${authToken}; ct0=${ct0}`)
}

function handleExLogin() {
  if (!exCookieInput.value.trim()) return
  emit('exhentai-set-cookies', exCookieInput.value.trim())
}

// Pawchive 文件夹组织选项（画师名为父文件夹）
const pawchiveSubfolderOptions = [
  { label: '月份/帖子名 (2026-08/帖子)', value: 'date_post' },
  { label: '按月份 (2026-08)', value: 'date' },
  { label: '按帖子名', value: 'post' },
  { label: '不分子文件夹', value: 'none' },
]

// Pawchive 搜索模式选项
const searchModeOptions = [
  { label: '画师', value: 'artist' },
  { label: '标签', value: 'tag' },
]

// 收藏按钮提示文字
const favoritesTitle = computed(() => {
  if (props.site !== 'pawchive') return '我的收藏（切到 Pawchive 使用）'
  return props.pawchiveUser ? '我的收藏' : '我的收藏（需登录）'
})

function handleLogin() {
  if (!loginUsername.value.trim() || !loginPassword.value) return
  emit('pawchive-login', loginUsername.value.trim(), loginPassword.value)
}

function update(key, value) {
  emit('update:settings', { [key]: value })
}

// ============================
// X 关注分类管理（母子 tag）
// ============================
const newTagParent = ref('')
const newTagChild = ref('')

function handleAddFollowTag() {
  const parent = newTagParent.value.trim()
  const child = newTagChild.value.trim()
  if (!parent) return
  emit('tw-add-follow-tag', parent, child)
  newTagParent.value = ''
  newTagChild.value = ''
}

function handleClearCache() {
  emit('clear-cache')
}

// 站点显示名
const siteNames = { bunkr: 'Bunkr', coomer: 'Coomer', pawchive: 'Pawchive', exhentai: 'EX', twitter: 'X', iwara: 'Iwara', hanime: 'H站', oreno3d: 'O3D' }
function siteName(s) {
  return siteNames[s] || (s ? String(s) : '未知')
}

// 收藏类型图标（无缩略图时显示）
function favTypeIcon(type) {
  if (type === 'artist' || type === 'creator') return '👤'
  if (type === 'tag') return '🏷️'
  if (type === 'post') return '📝'
  return '画廊'
}

// ExHentai 代理修改：保存设置 + 同步 webview 会话代理 + 通知下载后端
function handleExProxyChange(v) {
  const proxy = (v || '').trim()
  update('exhentai_proxy', proxy)
  if (window.api && window.api.exSetProxy) {
    window.api.exSetProxy(proxy)
  }
  if (window.api) {
    window.api.sendCommand({ cmd: 'exhentai_set_proxy', proxy })
  }
}

async function selectFolder() {
  const folder = await window.api.selectFolder()
  if (folder) {
    update('custom_path', folder)
  }
}
</script>

<style scoped>
.left-panel {
  width: 340px;
  min-width: 340px;
  background: #1e1e22;
  border-right: 1px solid #2d2d33;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.login-section {
  display: flex;
  align-items: center;
  padding: 16px;
  gap: 12px;
}

/* 站点快捷工具行：打开网站（可选浏览器） + 帮助 */
.site-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 16px 12px;
}

.site-tools-browser {
  width: 108px;
  flex-shrink: 0;
}

/* 帮助弹窗 */
.site-help-modal .site-help-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.site-help-modal .site-help-tip {
  font-size: 12px;
  opacity: 0.55;
}

.site-help-modal .site-help-pre {
  margin: 0;
  max-height: 58vh;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.7;
  user-select: text;
  padding: 12px;
  border-radius: 6px;
  background: rgba(128, 128, 128, 0.08);
}

html.light-mode .site-help-modal .site-help-pre {
  background: rgba(128, 128, 128, 0.1);
}

.login-icon {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: #2a2a30;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #63e2b7;
}

.login-icon-on {
  color: #63e2b7;
  background: rgba(99, 226, 183, 0.12);
  border: 1px solid rgba(99, 226, 183, 0.4);
}

.pawchive-login-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0 16px 12px;
}

/* 账号信息卡片（需登录站点，切换站点信息常驻） */
.account-card {
  padding: 12px 16px;
  background: rgba(42, 42, 48, 0.4);
  border-top: 1px solid rgba(45, 45, 51, 0.6);
  border-bottom: 1px solid rgba(45, 45, 51, 0.6);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.account-card .pawchive-login-form {
  padding: 0;
}

.account-card-on {
  background: rgba(99, 226, 183, 0.05);
  border-top: 1px solid rgba(99, 226, 183, 0.25);
  border-bottom: 1px solid rgba(99, 226, 183, 0.25);
}

.account-status-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* Iwara IW站/AI站 切换（已登录行右侧，account-site-name 已右推） */
.iw-site-switch {
  flex-shrink: 0;
}

.iw-site-switch-form {
  margin: 0;
  justify-content: center;
  display: flex;
}

.account-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #63e2b7;
  box-shadow: 0 0 6px rgba(99, 226, 183, 0.8);
  flex-shrink: 0;
}

.account-status-text {
  font-size: 12px;
  color: #63e2b7;
  font-weight: 600;
}

.account-site-name {
  font-size: 11px;
  color: #7f7f7f;
  margin-left: auto;
}

.account-line {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.22);
  cursor: pointer;
  transition: background 0.12s ease;
}

.account-line:hover {
  background: rgba(99, 226, 183, 0.1);
}

.account-line-label {
  font-size: 11px;
  color: #7f7f7f;
  flex-shrink: 0;
  width: 36px;
}

.account-line-value {
  font-size: 12px;
  color: #e0e0e6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-cookie-value {
  color: #a0a0a8;
  font-size: 11px;
}

.account-profiles {
  display: flex;
  align-items: center;
  gap: 6px;
}

.account-profiles .n-select {
  flex: 1;
  min-width: 0;
}

/* 未登录状态下的账号档案区（纵向排列：下拉 + 删除 + 提示） */
.logged-out-profiles {
  flex-direction: column;
  align-items: stretch;
  margin-top: 8px;
}

.logged-out-profiles .account-actions {
  justify-content: flex-end;
}

.account-actions {
  display: flex;
  gap: 6px;
  justify-content: space-between;
}

/* X 清除缓存按钮 */
.tw-cache-clear {
  margin-top: 8px;
}

/* X 关注分类管理（母子 tag） */
.follow-tag-section {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed rgba(255, 255, 255, 0.1);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.follow-tag-title {
  font-size: 12px;
  font-weight: 600;
  color: #9a9aa5;
}

.follow-tag-add {
  display: flex;
  gap: 6px;
  align-items: center;
}

.follow-tag-empty {
  font-size: 11px;
  color: #5f5f5f;
  line-height: 1.6;
}

.follow-tag-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.follow-tag-parent {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.follow-tag-name {
  font-size: 12px;
  font-weight: 600;
  color: #e0e0e6;
}

.follow-tag-children {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding-left: 4px;
}

/* 未登录引导区 */
.login-guide {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.login-hint {
  font-size: 11px;
  color: #5f5f5f;
  text-align: center;
}

.login-title {
  font-size: 15px;
  font-weight: 600;
  color: #e0e0e6;
}

.login-subtitle {
  font-size: 12px;
  color: #7f7f7f;
  margin-top: 2px;
}

.login-actions {
  margin-left: auto;
  flex-shrink: 0;
}

.round-buttons {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 12px;
  padding: 14px 8px;
}

.round-btn {
  width: 46px;
  height: 46px;
  border-radius: 50%;
  background: #2a2a30;
  border: 1px solid #3a3a44;
  color: #a0a0a8;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.45);
  transition: transform 0.12s ease, box-shadow 0.12s ease, color 0.12s ease, border-color 0.12s ease, background 0.12s ease;
  outline: none;
  -webkit-tap-highlight-color: transparent;
}

.round-btn:hover {
  color: #63e2b7;
  border-color: #63e2b7;
  background: #303038;
  box-shadow: 0 5px 15px rgba(0, 0, 0, 0.55);
}

.round-btn:active {
  transform: scale(0.88);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
}

.round-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.round-btn:disabled:hover {
  color: #a0a0a8;
  border-color: #3a3a44;
  background: #2a2a30;
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.45);
}

.round-btn-active {
  color: #63e2b7;
  border-color: rgba(99, 226, 183, 0.4);
}

/* 日间模式：圆形按钮配色 */
html.light-mode .round-btn {
  background: #ffffff;
  border-color: #d8d9e0;
  color: #5a5c66;
  box-shadow: 0 2px 8px rgba(30, 34, 44, 0.1);
}

html.light-mode .round-btn:hover {
  color: #18a058;
  border-color: #18a058;
  background: #f4fffa;
  box-shadow: 0 3px 10px rgba(30, 34, 44, 0.14);
}

html.light-mode .round-btn:disabled {
  background: #f2f3f5;
}

html.light-mode .round-btn:disabled:hover {
  color: #5a5c66;
  border-color: #d8d9e0;
  background: #f2f3f5;
}

html.light-mode .round-btn-active {
  color: #18a058;
  border-color: rgba(24, 160, 88, 0.4);
}

.settings-section {
  flex: 1;
  overflow: hidden;
}

.settings-content {
  padding: 12px 16px;
}

/* 占位功能面板提示（识图/翻译） */
.placeholder-tip {
  font-size: 12px;
  line-height: 1.8;
  color: rgba(255, 255, 255, 0.55);
  background: rgba(99, 226, 183, 0.06);
  border: 1px dashed rgba(99, 226, 183, 0.35);
  border-radius: 8px;
  padding: 14px 12px;
  text-align: center;
}

.section-title {
  font-size: 12px;
  font-weight: 600;
  color: #63e2b7;
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.setting-item {
  margin-bottom: 14px;
}

.setting-label {
  font-size: 12px;
  color: #a0a0a8;
  margin-bottom: 5px;
}

.setting-switch {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  gap: 12px;
}

.switch-label {
  font-size: 13px;
  color: #e0e0e6;
}

.switch-hint {
  font-size: 11px;
  color: #7f7f7f;
  margin-top: 2px;
}

.backend-status {
  display: flex;
  align-items: center;
  padding: 4px 0;
}

.backend-status-text {
  margin-left: 8px;
  font-size: 12px;
  color: #7f7f7f;
}

.backend-status-err {
  color: #ff6a6a;
}

.backend-error-box {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  background: rgba(255, 106, 106, 0.08);
  border: 1px solid rgba(255, 106, 106, 0.25);
}

.backend-error-msg {
  font-size: 12px;
  color: #ff8f8f;
  line-height: 1.5;
  word-break: break-all;
  white-space: pre-wrap;
}

.backend-error-fix {
  margin-top: 6px;
  font-size: 11px;
  color: #8f8f98;
  line-height: 1.7;
}

/* ========== 面板通用（历史/收藏） ========== */
.panel-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.panel-count {
  font-size: 12px;
  color: #7f7f7f;
}

.panel-empty {
  text-align: center;
  padding: 32px 0;
  font-size: 13px;
  color: #7f7f7f;
  line-height: 1.8;
}

.panel-empty-hint {
  font-size: 11px;
  color: #5f5f5f;
}

/* ========== 日常标签列表 ========== */
.tag-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tag-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  background: #26262c;
  border: 1px solid #33333c;
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.12s ease, background 0.12s ease;
}

.tag-item:hover {
  border-color: #63e2b7;
  background: #2c2c34;
}

.tag-site {
  flex-shrink: 0;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #3a3a44;
  color: #d0d0d8;
}

.tag-site[data-site='bunkr'] {
  background: rgba(102, 204, 255, 0.15);
  color: #66ccff;
}

.tag-site[data-site='coomer'] {
  background: rgba(255, 163, 71, 0.15);
  color: #ffa347;
}

.tag-site[data-site='pawchive'] {
  background: rgba(99, 226, 183, 0.15);
  color: #63e2b7;
}

.tag-site[data-site='exhentai'] {
  background: rgba(255, 106, 106, 0.15);
  color: #ff6a6a;
}

.tag-site[data-site='twitter'] {
  background: rgba(112, 160, 255, 0.15);
  color: #70a0ff;
}

.tag-text {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: #e0e0e6;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tag-mode {
  flex-shrink: 0;
  font-size: 10px;
  color: #7f7f7f;
}

.tag-delete {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: #5f5f5f;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.tag-delete:hover {
  background: rgba(255, 106, 106, 0.18);
  color: #ff6a6a;
}

/* ========== 本地收藏列表 ========== */
.fav-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.fav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  background: #26262c;
  border: 1px solid #33333c;
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.12s ease, background 0.12s ease;
}

.fav-item:hover {
  border-color: #ff6a6a;
  background: #2c2c34;
}

.fav-thumb-box {
  flex-shrink: 0;
  width: 52px;
  height: 40px;
  border-radius: 6px;
  background: #1e1e22;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.fav-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.fav-thumb-placeholder {
  font-size: 16px;
  color: #7f7f7f;
}

.fav-info {
  flex: 1;
  min-width: 0;
}

.fav-title {
  font-size: 12px;
  color: #e0e0e6;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
}

.fav-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 10px;
  color: #7f7f7f;
}
</style>
