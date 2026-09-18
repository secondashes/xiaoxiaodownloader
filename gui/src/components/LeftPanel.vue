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
        <div class="login-title">小小浏览器</div>
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
        <div v-if="!isOrenoSite" class="account-profiles">
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
          <n-button v-if="!isOrenoSite" size="tiny" @click="emit('save-account', site)">保存当前</n-button>
          <n-button
            v-if="!isOrenoSite"
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
        <!-- 综合资源站点：统一登录卡（leakedzone 过盾 / 其余三站免登录说明） -->
        <div v-if="['leakedzone', 'coomerst', 'coomerfans', 'fapello'].includes(site)" class="pawchive-login-form">
          <div class="login-hint" style="margin-bottom: 6px">
            {{ site === 'leakedzone'
              ? 'Leakedzone 需要 Cloudflare 过盾（等同于登录）：'
              : (site === 'coomerfans'
                ? 'CoomerFans 无需账号，自动 PoW 过盾：'
                : '本站无需登录，装好通用代理即可直接浏览：') }}
          </div>
          <template v-if="site === 'leakedzone'">
            <n-button size="small" type="success" block @click="emit('leak-edge-login')">
              ① 用系统 Edge 过盾登录（推荐·一次就过）
            </n-button>
            <n-button
              size="small"
              type="info"
              block
              style="margin-top: 6px"
              :disabled="!leakEdgeRunning"
              @click="emit('leak-edge-harvest')"
            >
              ② 我已过盾，抓取 Cookie
            </n-button>
            <n-button size="small" quaternary block style="margin-top: 6px" @click="emit('site-oauth-login', site)">
              备用：内置浏览器过盾（验证可能循环）
            </n-button>
            <div class="login-hint">
              过盾流程：点①在弹出的 Edge 里完成人机验证（出现网站内容）→ 回来点②，
              Cookie+UA 自动保存并验证。Edge 窗口之后可关可留（保留则下次免验证）。
            </div>
          </template>
          <template v-else>
            <n-button size="small" quaternary block @click="emit('site-oauth-login', site)">
              打开内置浏览器（浏览/刷新会话）
            </n-button>
            <div class="login-hint">
              {{ site === 'fapello'
                ? 'Fapello 免登录直连；图片走媒体代理，需通用代理（默认 10809）在线。'
                : (site === 'coomerfans'
                  ? 'CoomerFans 免登录；首次访问自动完成 PoW 过盾，需通用代理在线。'
                  : 'Coomer 免登录；走 kemono 接口，需通用代理在线。') }}
            </div>
          </template>
        </div>

        <!-- Pawchive 用户名密码登录（完整登录套件） -->
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
            </n-button>
          <div v-if="loginLoading" style="margin-top: 4px; text-align: center">
            <n-button size="tiny" quaternary type="warning" @click="emit('cancel-login', 'pawchive')">
              ✕ 网络不佳？点击取消转圈
            </n-button>
          </div>
          <n-button
            size="small"
            block
            secondary
            @click="emit('site-oauth-login', 'pawchive', { email: loginUsername.trim(), password: loginPassword })"
          >
            打开内置浏览器登录（推荐）
          </n-button>
          <n-button size="small" block @click="handleSiteSaveCred('pawchive', loginUsername, loginPassword)">
            仅保存账号密码（加密存本机）
          </n-button>
          <div class="login-hint">
            推荐直接用账号密码登录；"内置浏览器登录"在弹窗内完成后自动抓取会话；
            账号密码加密保存在本机，下次打开自动回填。登录后可使用"我的收藏"功能
          </div>
        </div>

        <!-- Twitter/X webview 浏览器登录（推荐）+ 账号密码保存 + 可选粘贴 Cookie -->
        <div v-if="site === 'twitter'" class="pawchive-login-form">
          <n-input
            v-model:value="twEmailInput"
            size="small"
            placeholder="X 登录账号（邮箱/手机号/用户名，可选）"
            @keyup.enter="emit('site-oauth-login', 'twitter', { email: twEmailInput.trim(), password: twPasswordInput })"
          />
          <n-input
            v-model:value="twPasswordInput"
            size="small"
            type="password"
            show-password-on="click"
            placeholder="密码（可选，用于弹窗自动预填）"
            @keyup.enter="emit('site-oauth-login', 'twitter', { email: twEmailInput.trim(), password: twPasswordInput })"
          />
          <n-button
            size="small"
            type="primary"
            block
            @click="emit('site-oauth-login', 'twitter', { email: twEmailInput.trim(), password: twPasswordInput })"
          >
            打开内置浏览器登录（推荐）
          </n-button>
          <n-button size="small" block @click="handleSiteSaveCred('twitter', twEmailInput, twPasswordInput)">
            仅保存账号密码（加密存本机）
          </n-button>
          <n-input
            v-model:value="twCookieInput"
            size="small"
            type="password"
            show-password-on="click"
            placeholder="或粘贴 Cookie（含 auth_token / ct0）"
            @keyup.enter="handleTwitterLogin"
          />
          <n-button
            size="small"
            type="primary"
            block
            :disabled="!twCookieInput.trim()"
            @click="handleTwitterLogin"
          >
            保存并验证登录
          </n-button>
          <div class="login-hint">
            推荐点上方按钮：弹出浏览器登录 x.com（邮箱/手机号/Google 皆可），
            已保存的账号密码会自动预填；登录后点弹窗下方"确认"自动抓取 Cookie；
            国内网络需先在下方设置 X 站代理
          </div>
        </div>

        <!-- ExHentai cookie 登录（推荐 webview 论坛登录 + 账号密码保存 + 可粘贴 cookie） -->
        <div v-if="site === 'exhentai'" class="pawchive-login-form">
          <n-input
            v-model:value="exEmailInput"
            size="small"
            placeholder="E-Hentai 论坛用户名（可选）"
            @keyup.enter="$emit('exhentai-webview-login', { email: exEmailInput.trim(), password: exPasswordInput })"
          />
          <n-input
            v-model:value="exPasswordInput"
            size="small"
            type="password"
            show-password-on="click"
            placeholder="密码（可选，用于弹窗自动预填）"
            @keyup.enter="$emit('exhentai-webview-login', { email: exEmailInput.trim(), password: exPasswordInput })"
          />
          <n-button
            size="small"
            type="primary"
            block
            @click="$emit('exhentai-webview-login', { email: exEmailInput.trim(), password: exPasswordInput })"
          >
            打开内置浏览器登录（推荐）
          </n-button>
          <n-button size="small" block @click="handleSiteSaveCred('exhentai', exEmailInput, exPasswordInput)">
            仅保存账号密码（加密存本机）
          </n-button>
          <n-input
            v-model:value="exCookieInput"
            size="small"
            type="password"
            show-password-on="click"
            placeholder="或粘贴 Cookie（含 ipb_member_id / ipb_pass_hash）"
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
            推荐点上方按钮：弹出浏览器登录 e-hentai 论坛账号（EX 账号即论坛账号，已保存的账号密码自动预填），
            登录后点下方"确认"自动抓取 Cookie；也可在右侧"浏览器"视图登录后点"同步Cookie"
          </div>
        </div>

        <!-- Iwara 邮箱密码登录（token 长期保存，自动续期；完整登录套件） -->
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
            </n-button>
          <div v-if="iwaraLoginLoading" style="margin-top: 4px; text-align: center">
            <n-button size="tiny" quaternary type="warning" @click="emit('cancel-login', 'iwara')">
              ✕ 网络不佳？点击取消转圈
            </n-button>
          </div>
          <n-button
            size="small"
            block
            secondary
            @click="emit('site-oauth-login', 'iwara', { email: iwaraEmailInput.trim(), password: iwaraPasswordInput })"
          >
            打开内置浏览器登录（真人验证）
          </n-button>
          <n-button size="small" block @click="handleSiteSaveCred('iwara', iwaraEmailInput, iwaraPasswordInput)">
            仅保存账号密码（加密存本机）
          </n-button>
          <div class="login-hint">
            Iwara 账号密码登录（token 失效自动用保存的密码续期）；遇到真人验证时点"内置浏览器登录"在弹窗内完成；
            不登录也可搜索与下载公开视频，登录可看私密/好友限定
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

        <!-- Hanime1 邮箱密码登录（H站；真人验证站点；完整登录套件） -->
        <div v-if="site === 'hanime'" class="pawchive-login-form">
          <div class="login-hint login-hint-warn">
            ⚠ Hanime1 需要真人验证（hCaptcha）：登录被拦截或验证失败时，
            点下方"打开内置浏览器登录"在弹窗内完成验证，会话自动保存
          </div>
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
            </n-button>
          <div v-if="hanimeLoginLoading" style="margin-top: 4px; text-align: center">
            <n-button size="tiny" quaternary type="warning" @click="emit('cancel-login', 'hanime')">
              ✕ 网络不佳？点击取消转圈
            </n-button>
          </div>
          <n-button
            size="small"
            block
            secondary
            @click="emit('site-oauth-login', 'hanime', { email: hanimeEmailInput.trim(), password: hanimePasswordInput })"
          >
            打开内置浏览器登录（真人验证）
          </n-button>
          <n-button size="small" block @click="handleSiteSaveCred('hanime', hanimeEmailInput, hanimePasswordInput)">
            仅保存账号密码（加密存本机）
          </n-button>
          <div class="login-hint">
            H站账号密码登录（会话失效自动用保存的密码重登）；遇到真人验证时点"内置浏览器登录"在弹窗内完成；
            不登录也可浏览/搜索/下载视频，登录可收藏（稍後觀看）、发表评论、查看觀看紀錄
          </div>
        </div>

        <!-- Pixiv 登录（P站；App API Refresh Token 方案：内置浏览器 OAuth 授权码换 Token） -->
        <div v-if="site === 'pixiv'" class="pawchive-login-form">
          <n-button
            size="small"
            type="primary"
            block
            :loading="pixivLoginLoading"
            @click="handlePixivLogin"
          >
            </n-button>
          <div v-if="pixivLoginLoading" style="margin-top: 4px; text-align: center">
            <n-button size="tiny" quaternary type="warning" @click="emit('cancel-login', 'pixiv')">
              ✕ 网络不佳？点击取消转圈
            </n-button>
          </div>
          <div class="login-hint">
            在弹出的内置浏览器中完成 Pixiv 登录，程序自动提取授权码换取长期 Refresh Token（加密存本机）；
            登录后可搜索/浏览 R-18、关注作者、收藏作品、发评论、发布作品；Token 失效需重新点按钮登录
          </div>
        </div>

        <!-- ASMR-100 用户名密码登录（音声站；登录后可同步收藏；完整登录套件） -->
        <div v-if="site === 'asmr'" class="pawchive-login-form">
          <n-input
            v-model:value="asmrNameInput"
            size="small"
            placeholder="ASMR-100 用户名"
            :disabled="asmrLoginLoading"
            @keyup.enter="handleAsmrLogin"
          />
          <n-input
            v-model:value="asmrPasswordInput"
            size="small"
            type="password"
            show-password-on="click"
            placeholder="密码"
            :disabled="asmrLoginLoading"
            @keyup.enter="handleAsmrLogin"
          />
          <n-button
            size="small"
            type="primary"
            block
            :loading="asmrLoginLoading"
            :disabled="!asmrNameInput.trim() || !asmrPasswordInput"
            @click="handleAsmrLogin"
          >
            </n-button>
          <div v-if="asmrLoginLoading" style="margin-top: 4px; text-align: center">
            <n-button size="tiny" quaternary type="warning" @click="emit('cancel-login', 'asmr')">
              ✕ 网络不佳？点击取消转圈
            </n-button>
          </div>
          <n-button
            size="small"
            block
            secondary
            @click="emit('site-oauth-login', 'asmr', { email: asmrNameInput.trim(), password: asmrPasswordInput })"
          >
            打开内置浏览器登录（真人验证）
          </n-button>
          <n-button size="small" block @click="handleSiteSaveCred('asmr', asmrNameInput, asmrPasswordInput)">
            仅保存账号密码（加密存本机）
          </n-button>
          <div class="login-hint">
            ASMR-100 账号密码登录（token 失效自动用保存的密码重登）；遇到真人验证时点"内置浏览器登录"在弹窗内完成；
            不登录也可浏览/搜索/下载音声，登录可同步网站收藏夹
          </div>
        </div>

        <!-- xHamster / Pornhub webview 浏览器登录（和 EX 站相同操作） -->
        <div v-if="site === 'xhamster' || site === 'pornhub'" class="pawchive-login-form">
          <n-button
            size="small"
            type="primary"
            block
            @click="emit('site-oauth-login', site)"
          >
            打开内置浏览器登录（推荐）
          </n-button>
          <div class="login-hint">
            {{ site === 'xhamster' ? 'xHamster' : 'Pornhub' }} 点上方按钮在弹出的浏览器内登录
            （邮箱密码 / Google / Twitter-X 授权皆可），登录后点弹窗下方"确认"自动抓取 Cookie。
            已在设置中登录谷歌邮箱或 X 站时，选"使用 Google/X 登录"会自动带入凭据，无需重复输入
          </div>
        </div>


        <!-- XVideos webview 浏览器登录（和 EX 站相同操作） -->
        <div v-if="site === 'xvideos'" class="pawchive-login-form">
          <n-button
            size="small"
            type="primary"
            block
            @click="emit('site-oauth-login', 'xvideos')"
          >
            打开内置浏览器登录（推荐）
          </n-button>
          <div class="login-hint">
            XVideos 点上方按钮在弹出的浏览器内登录（邮箱密码 / Google 授权皆可，首次可能有人机验证，按提示完成），
            登录后点弹窗下方"确认"自动抓取 Cookie；cookie 加密长期保存。
            已在设置中登录谷歌邮箱时，选"使用 Google 登录"会自动带入凭据
          </div>
        </div>

        <!-- FC2 登录会话（webview 登录 + 账号密码保存；未登录也可浏览/看免费视频） -->
        <div v-if="site === 'fc2'" class="pawchive-login-form">
          <n-input v-model:value="fc2EmailInput" size="small" placeholder="FC2 ID（邮箱）" />
          <n-input
            v-model:value="fc2PasswordInput"
            size="small"
            type="password"
            show-password-on="click"
            placeholder="密码"
          />
          <n-button
            size="small"
            type="primary"
            block
            @click="emit('site-oauth-login', 'fc2')"
          >
            打开内置浏览器登录（推荐）
          </n-button>
          <n-button size="small" block @click="handleSiteSaveCred('fc2', fc2EmailInput, fc2PasswordInput)">
            仅保存账号密码（加密存本机，登录页自动预填）
          </n-button>
          <n-button size="small" block tertiary type="error" @click="emit('site-logout', 'fc2')">
            清除登录信息（退出）
          </n-button>
          <div class="login-hint">
            FC2 点上方按钮在弹出的浏览器内登录 FC2 ID（免费邮箱注册，账号密码自动预填），
            登录后点弹窗下方"确认"自动抓取 Cookie。不登录也可浏览/播放免费视频；
            付费内容匿名只能看 sample 预览（界面会明确提示）
          </div>
        </div>

        <!-- JavDB 邮箱密码登录（webview 内自动预填 + Cloudflare 人机验证，"记住装置"约 7 天） -->
        <div v-if="site === 'javdb'" class="pawchive-login-form">
          <n-input
            v-model:value="jdbEmailInput"
            size="small"
            placeholder="JavDB 登录邮箱"
            @keyup.enter="handleJdbLogin"
          />
          <n-input
            v-model:value="jdbPasswordInput"
            size="small"
            type="password"
            show-password-on="click"
            placeholder="密码"
            @keyup.enter="handleJdbLogin"
          />
          <n-checkbox v-model:checked="jdbRemember" size="small">记住此装置（登录约 7 天有效）</n-checkbox>
          <n-button
            size="small"
            type="primary"
            block
            @click="handleJdbLogin"
          >
            打开内置浏览器登录（推荐）
          </n-button>
          <n-button size="small" block @click="handleSiteSaveCred('javdb', jdbEmailInput, jdbPasswordInput)">
            仅保存账号密码（加密存本机）
          </n-button>
          <div class="login-hint">
            JavDB 有 Cloudflare 验证，点上方按钮后请在内置浏览器里完成验证、登录并点击"同意"；
            然后点弹窗底部"确定"抓取 cookie 并自动关闭弹窗。cookie 加密保存，约 7 天有效。
            邮箱密码也会加密记录在本机，下次打开自动回填（登录成功时自动保存，无需重复输入）
          </div>
        </div>

        <!-- Oreno3D 登录会话（账号密码保存 + webview 会话登录） -->
        <div v-if="site === 'oreno3d'" class="pawchive-login-form">
          <n-input
            v-model:value="oreno3dEmailInput"
            size="small"
            placeholder="Oreno3D 账号（邮箱/用户名）"
            @keyup.enter="handleOrenoLogin('oreno3d')"
          />
          <n-input
            v-model:value="oreno3dPasswordInput"
            size="small"
            type="password"
            show-password-on="click"
            placeholder="密码"
            @keyup.enter="handleOrenoLogin('oreno3d')"
          />
          <n-button
            size="small"
            type="primary"
            block
            @click="handleOrenoLogin('oreno3d')"
          >
            登录（弹窗内完成 Cloudflare 验证）
          </n-button>
          <n-button size="small" block @click="handleOrenoSave('oreno3d')">
            仅保存账号密码（加密存本机）
          </n-button>
          <div class="login-hint">
            Oreno3D 无强制账号体系，登录主要保存站点会话（Cloudflare 验证后免重复验证）；
            账号密码加密保存在本机，下次打开自动回填。不登录也可正常浏览/搜索/下载
          </div>
        </div>

        <!-- EroMMDTube 登录会话（账号密码保存 + webview 会话登录） -->
        <div v-if="site === 'erommdtube'" class="pawchive-login-form">
          <n-input
            v-model:value="erommdtubeEmailInput"
            size="small"
            placeholder="EroMMDTube 账号（邮箱/用户名）"
            @keyup.enter="handleOrenoLogin('erommdtube')"
          />
          <n-input
            v-model:value="erommdtubePasswordInput"
            size="small"
            type="password"
            show-password-on="click"
            placeholder="密码"
            @keyup.enter="handleOrenoLogin('erommdtube')"
          />
          <n-button
            size="small"
            type="primary"
            block
            @click="handleOrenoLogin('erommdtube')"
          >
            登录（弹窗内完成 Cloudflare 验证）
          </n-button>
          <n-button size="small" block @click="handleOrenoSave('erommdtube')">
            仅保存账号密码（加密存本机）
          </n-button>
          <div class="login-hint">
            EroMMDTube 无强制账号体系，登录主要保存站点会话（Cloudflare 验证后免重复验证）；
            账号密码加密保存在本机，下次打开自动回填。不登录也可正常浏览/搜索/下载
          </div>
        </div>

        <!-- 登录引导：打开登录页 -->
        <div v-if="site !== 'oreno3d' && site !== 'erommdtube' && site !== 'javdb'" class="login-guide">
          <n-button size="small" block secondary @click="emit('open-login-page', site)">
            打开登录页（浏览器）
          </n-button>
          <div class="login-hint">
            {{ site === 'pawchive'
              ? '推荐直接用上方账号密码登录'
              : site === 'twitter'
                ? '推荐点上方"打开内置浏览器登录"在弹窗内登录 x.com，登录后点"确认"自动抓取'
                : site === 'iwara'
                  ? 'Iwara 使用邮箱密码登录（cookie 会过期，密码登录自动续期）；国内网络建议在设置里配置 Iwara 代理'
                  : site === 'hanime'
                    ? 'Hanime1 (H站) 使用邮箱密码登录；国内网络必须在设置里配置 H站代理'
                    : site === 'xhamster' || site === 'pornhub'
                      ? '点上方"打开内置浏览器登录"在弹窗内登录（邮箱或 X 授权皆可），登录后点"确认"自动抓取 Cookie'
                      : site === 'xvideos'
                        ? '点上方"打开内置浏览器登录"在弹窗内登录（首次可能有人机验证），登录后点"确认"自动抓取 Cookie'
                        : site === 'fc2'
                          ? '点上方"打开内置浏览器登录"在弹窗内登录 FC2 ID，登录后点"确认"自动抓取 Cookie；国内需先在下方设置 FC2 代理'
                          : site === 'javdb'
                          ? '推荐用上方邮箱密码登录（自动预填 + 弹窗内完成 Cloudflare 验证）；国内必须配置下方 JavDB 代理'
                          : '推荐点上方"打开内置浏览器登录"在弹窗内登录 exhentai.org，登录后点"确认"自动抓取' }}
          </div>
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
            <span class="follow-tag-name follow-tag-clickable" :title="`点开查看「${t.name}」里归类的博主`"
                  @click="toggleTagOpen(t.name)">
              {{ t.name }}<span class="follow-tag-count">（{{ memberCount(t.name) }}）</span>
            </span>
            <n-button size="tiny" quaternary type="primary"
                      :title="(openTag === t.name ? '收起' : `查看「${t.name}」里归类的博主`)"
                      @click="toggleTagOpen(t.name)">{{ openTag === t.name ? '收起' : '查看' }}</n-button>
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
              :type="openTag === t.name && openChild === c ? 'primary' : 'default'"
              :title="`点开查看子类「${c}」里归类的博主`"
              style="cursor: pointer"
              @click="toggleChildFilter(t.name, c)"
              @close.stop="emit('tw-delete-follow-tag', t.name, c)"
            >{{ c }}（{{ childCount(t.name, c) }}）</n-tag>
          </div>
          <!-- 成员列表（点开母类后显示；子类 tag 可过滤） -->
          <div v-if="openTag === t.name" class="follow-tag-members">
            <div v-for="m in tagMembers(t.name)" :key="m.user_id" class="follow-tag-member"
                 :title="`进入 @${m.screen_name} 的主页`"
                 @click="openMember(m)">
              <img v-if="m.thumbnail" class="follow-tag-avatar" :src="memberAvatar(m.thumbnail)" referrerpolicy="no-referrer" loading="lazy" />
              <span v-else class="follow-tag-avatar follow-tag-avatar-ph">{{ (m.screen_name || '?')[0].toUpperCase() }}</span>
              <div class="follow-tag-member-info">
                <div class="follow-tag-member-name">{{ m.name || '@' + m.screen_name }}</div>
                <div class="follow-tag-member-sub">@{{ m.screen_name }} · {{ m.tag }}</div>
              </div>
              <span class="follow-tag-member-go">主页 →</span>
            </div>
            <div v-if="!tagMembers(t.name).length" class="follow-tag-empty" style="padding: 4px 0">
              该{{ openChild ? '子类' : '母类' }}还没有归类的博主（在右侧"关注列表"点用户卡片的"分类"按钮归类）
            </div>
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
      <!-- 识图：以图搜源（拖拽图片到右侧拖拽框，多网站并发查询出处） -->
      <button
        class="round-btn"
        :class="{ 'round-btn-active': activePanel === 'ocr' }"
        title="识图（拖拽图片到右侧开始，多网站并发搜索来源）"
        @click="activePanel = activePanel === 'ocr' ? '' : 'ocr'"
      >
        <n-icon size="20">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
            <circle cx="12" cy="13" r="4"/>
          </svg>
        </n-icon>
      </button>
      <!-- 翻译（有道智云 API） -->
      <button
        class="round-btn"
        :class="{ 'round-btn-active': activePanel === 'translate' }"
        title="翻译（有道智云，文本翻译）"
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
      <!-- 手动抓取（资源嗅探，复刻 res-downloader）：独立全量窗口，浏览网页实时捕获媒体 -->
      <button
        class="round-btn"
        title="手动抓取（打开资源嗅探窗口：内置浏览器浏览网页，视频/音频/图片实时捕获，勾选下载）"
        @click="$emit('sniffer-open')"
      >
        <n-icon size="20">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="9"/>
            <circle cx="12" cy="12" r="3"/>
            <path d="M12 1v4"/>
            <path d="M12 19v4"/>
            <path d="M1 12h4"/>
            <path d="M19 12h4"/>
          </svg>
        </n-icon>
      </button>
      <!-- BT 下载：独立窗口（磁力链接批量粘贴 + .torrent 种子拖拽） -->
      <button
        class="round-btn bt-btn"
        title="BT 下载（磁力/种子）"
        @click="$emit('bt-open')"
      >
        <span class="bt-btn-emoji">🧲</span>
      </button>
      <!-- 热门平台里模式：无界面按钮，连按 3 次 Alt 切换（App 全局手势） -->
    </div>

    <!-- 识图面板：粘贴窗口（存放搜出来的结果）+ 代理设置 -->
    <div v-show="activePanel === 'ocr'" class="settings-section">
      <div class="settings-content">
        <div class="section-title">识图（以图搜源）</div>
        <div class="setting-item">
          <div class="setting-label">搜索结果粘贴板（自动保存，可存放识图搜到的出处信息）</div>
          <n-input
            v-model:value="reversePasteLocal"
            type="textarea"
            :rows="8"
            placeholder="可以粘贴搜索结果到此处（自动保存，长期记录）"
            @change="v => emit('reverse-paste-save', v)"
          />
          <div class="switch-hint" style="margin-top: 4px">
            将图片拖到右侧拖拽框即可开始识图；全部网站返回后展示结果（失效网站自动移除）
          </div>
        </div>
        <div class="setting-item">
          <div class="setting-label">识图代理地址（Lenso.ai 国内必须；其他站一般直连）</div>
          <n-input
            :value="settings.reverse_proxy"
            placeholder="如 http://127.0.0.1:10809，留空直连"
            size="small"
            @change="v => emit('reverse-set-proxy', v, settings.reverse_proxy_all)"
          />
          <div style="margin-top: 8px">
            <n-checkbox
              size="small"
              :checked="!!settings.reverse_proxy_all"
              @update:checked="v => update('reverse_proxy_all', v)"
            >
              所有识图站点都走该代理
            </n-checkbox>
            <div class="switch-hint" style="margin-top: 4px">
              关闭时仅 Lenso.ai 走代理，其余站点（trace.moe / SauceNAO / IQDB）直连
            </div>
          </div>
        </div>
        <div class="setting-item">
          <div class="setting-label">SauceNAO API Key（可选；免费注册获取，可提升每日配额）</div>
          <n-input
            :value="settings.reverse_saucenao_api_key"
            placeholder="留空 = 使用免费配额（saucenao.com 账号页获取 Key）"
            size="small"
            @change="v => update('reverse_saucenao_api_key', v)"
          />
        </div>
        <div class="setting-item">
          <div class="setting-label">Lenso.ai API Token（可选；官方 API 需付费订阅，留空则跳过该站）</div>
          <n-input
            :value="settings.reverse_lenso_token"
            placeholder="留空 = 跳过 Lenso.ai"
            size="small"
            @change="v => update('reverse_lenso_token', v)"
          />
        </div>
      </div>
    </div>
    <!-- 翻译面板（有道智云 API） -->
    <div v-show="activePanel === 'translate'" class="settings-section">
      <div class="settings-content">
        <div class="section-title">翻译（免费 / 自选引擎）</div>

        <!-- 翻译方向 -->
        <div class="translate-row">
          <n-select
            size="small"
            :value="trFrom"
            :options="trLangOptions"
            style="width: 110px"
            @update:value="v => trFrom = v"
          />
          <span class="translate-arrow">→</span>
          <n-select
            size="small"
            :value="trTo"
            :options="trLangOptions"
            style="width: 110px"
            @update:value="v => trTo = v"
          />
        </div>

        <!-- 输入文本 -->
        <n-input
          v-model:value="trInput"
          type="textarea"
          :rows="5"
          size="small"
          placeholder="粘贴或输入要翻译的文本（Ctrl+V 粘贴；Enter 翻译）"
          @keydown.enter.exact.prevent="doTranslate"
        />
        <div class="translate-actions">
          <n-button size="small" quaternary @click="pasteClipboard">📋 粘贴</n-button>
          <n-button size="small" quaternary @click="trInput = ''">✕ 清空</n-button>
          <n-button
            size="small"
            type="primary"
            :loading="translating"
            :disabled="!trInput.trim()"
            @click="doTranslate"
          >翻译</n-button>
        </div>

        <!-- 翻译结果 -->
        <div v-if="translating" class="translate-result-tip">翻译中...</div>
        <div v-else-if="trError" class="translate-result-err">{{ trError }}</div>
        <div v-else-if="trOutput" class="translate-result-box">
          <div class="translate-result-text" :title="trOutput">{{ trOutput }}</div>
          <div class="translate-result-meta" v-if="trDetected || trEngine">
            <span v-if="trDetected">检测：{{ trDetected }}</span>
            <span v-if="trEngine">引擎：{{ trEngine }}</span>
          </div>
          <div class="translate-result-actions">
            <n-button size="tiny" quaternary @click="copyText(trOutput, '翻译结果')">复制</n-button>
          </div>
        </div>

        <!-- 引擎配置（折叠） -->
        <details class="translate-config">
          <summary>⚙ 翻译引擎与全局设置（默认 Google 免费，国内需代理；右侧 🌐 按钮开关全局自动翻译）</summary>
          <div class="translate-config-body">
            <!-- 全局自动翻译设置（右侧缩小版 🌐 按钮用） -->
            <div class="translate-config-hint">搜索结果自动翻译目标语言（右侧 🌐 按钮开启/停止）：</div>
            <n-select
              size="small"
              :value="settings.auto_translate_to || 'zh-CN'"
              :options="[
                { label: '中文（简体）', value: 'zh-CN' },
                { label: '中文（繁體）', value: 'zh-TW' },
                { label: 'English', value: 'en' },
                { label: '日本語', value: 'ja' },
                { label: '한국어', value: 'ko' },
                { label: 'Français', value: 'fr' },
                { label: 'Deutsch', value: 'de' },
                { label: 'Русский', value: 'ru' },
                { label: 'Español', value: 'es' },
              ]"
              @update:value="v => update('auto_translate_to', v)"
            />
            <!-- 翻译代理 -->
            <div class="translate-config-hint">翻译代理（Google 端点国内必须；留空=直连）：</div>
            <n-input
              size="small"
              :value="settings.translate_proxy || ''"
              placeholder="如 http://127.0.0.1:10809（留空=直连）"
              @update:value="v => update('translate_proxy', v.trim())"
            />
            <n-select
              size="small"
              :value="settings.translate_engine || 'google_free'"
              :options="[
                { label: 'Google 免费端点（无需 API key，推荐）', value: 'google_free' },
                { label: 'LibreTranslate（自建/公开实例，需填 URL）', value: 'libretranslate' },
                { label: '有道智云（需 app ID / secret）', value: 'youdao' },
              ]"
              @update:value="v => update('translate_engine', v)"
            />
            <div v-if="(settings.translate_engine || 'google_free') === 'google_free'" class="translate-config-hint">
              走 translate.google.com 免费端点，无需 API key；国内网络需在上方填写可用代理。
            </div>
            <template v-else-if="settings.translate_engine === 'libretranslate'">
              <n-input
                size="small"
                :value="settings.libretranslate_url || ''"
                placeholder="LibreTranslate 实例 URL，如 https://libretranslate.com"
                @update:value="v => update('libretranslate_url', v.trim())"
              />
              <n-input
                size="small"
                type="password"
                show-password-on="click"
                :value="settings.libretranslate_api_key || ''"
                placeholder="API key（公开实例可留空）"
                @update:value="v => update('libretranslate_api_key', v.trim())"
              />
              <div class="translate-config-hint">
                可自建 LibreTranslate（开源、免费、无限制）；或用公开实例（如 libretranslate.com）。
              </div>
            </template>
            <template v-else-if="settings.translate_engine === 'youdao'">
              <n-input
                size="small"
                :value="settings.youdao_app_id || ''"
                placeholder="应用 ID（appKey）"
                @update:value="v => update('youdao_app_id', v.trim())"
              />
              <n-input
                size="small"
                type="password"
                show-password-on="click"
                :value="settings.youdao_app_secret || ''"
                placeholder="应用密钥（appSecret）"
                @update:value="v => update('youdao_app_secret', v.trim())"
              />
              <div class="translate-config-hint">
                注册 <a href="https://ai.youdao.com/" target="_blank">ai.youdao.com</a> → 实名后创建"文本翻译"应用，复制 ID 和密钥填入。新用户有免费额度。
              </div>
            </template>
          </div>
        </details>
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
    <div v-show="activePanel === 'settings'" class="settings-section settings-full">
      <n-scrollbar class="settings-full-scroll">
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

          <!-- 表世界保存位置（仅影响美好世界） -->
          <div class="setting-item">
            <div class="setting-label">
              表世界保存位置（仅影响「美好世界」的下载 / 视频流下载整片 / Word 导出）
            </div>
            <n-input-group>
              <n-input
                :value="settings.surface_save_path"
                placeholder="默认: 用户下载文件夹"
                readonly
                style="flex: 1"
              />
              <n-button @click="selectSurfaceFolder" type="primary" ghost>
                选择
              </n-button>
              <n-button v-if="settings.surface_save_path" ghost @click="update('surface_save_path', '')">
                恢复默认
              </n-button>
            </n-input-group>
          </div>

          <!-- 并发连接数 -->
          <div class="setting-item">
            <div class="setting-label">下载线程数（每文件多线程分段，类似 IDM/迅雷）</div>
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
              :max="8"
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

          <!-- 通用代理（默认代理与端口）：Pornhub 更新 / 新站默认出口 / leakedzone 过盾共用 -->
          <div class="setting-item">
            <div class="section-title">通用代理（默认代理与端口）</div>
            <div class="setting-label">
              Pornhub 更新检查、leakedzone 过盾、Coomer/CoomerFans/Fapello 等新站默认出口共用；留空 = 默认 http://127.0.0.1:10809，填 off = 直连
            </div>
            <n-input-group>
              <n-input
                :value="commonProxyDraft"
                placeholder="http://127.0.0.1:10809（留空=默认，off=直连）"
                @update:value="v => commonProxyDraft = v"
                @keyup.enter="$emit('common-proxy', commonProxyDraft.trim())"
              />
              <n-button type="primary" @click="$emit('common-proxy', commonProxyDraft.trim())">保存</n-button>
              <n-button @click="commonProxyDraft = ''; $emit('common-proxy', '')">恢复默认</n-button>
            </n-input-group>
            <div class="switch-hint" style="margin-top: 4px">
              改完点「保存」立即生效（无需重启）；「恢复默认」回到 http://127.0.0.1:10809
            </div>
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
              <div class="setting-label">X 文件夹组织（父文件夹为博主名）</div>
              <n-select
                :value="settings.twitter_subfolder || 'media'"
                :options="twitterSubfolderOptions"
                @update:value="v => update('twitter_subfolder', v)"
              />
              <div class="switch-hint" style="margin-top: 4px">文件名自动为「发帖日期_帖子内容_序号」</div>
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
            <div class="setting-switch">
              <div>
                <div class="switch-label">MD5 查重</div>
                <div class="switch-hint">同内容的图片/视频在多条推文重复出现时只保留一份（最早发布的），自动删除重复副本；对已下载过的旧文件同样生效</div>
              </div>
              <n-switch
                :value="settings.twitter_md5_dedup !== false"
                @update:value="v => update('twitter_md5_dedup', v)"
              />
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

          <!-- Pixiv 专属设置（代理 + 搜索模式） -->
          <template v-if="site === 'pixiv'">
            <div class="setting-item">
              <div class="setting-label">Pixiv (P站) 代理地址（搜索/解析/下载都走此代理）</div>
              <n-input
                :value="settings.pixiv_proxy"
                placeholder="如 http://127.0.0.1:10809"
                size="small"
                @change="v => $emit('pixiv-set-proxy', v)"
              />
              <div class="switch-hint" style="margin-top: 4px">国内必须配置代理才能访问 pixiv.net；下载取原图（original，多页作品全下）</div>
            </div>
            <div class="setting-item">
              <div class="setting-label">Pixiv 搜索内容过滤</div>
              <n-select
                :value="settings.pixiv_mode || ''"
                :options="[
                  { label: '全部（含R-18，需登录）', value: '' },
                  { label: '全年龄（safe）', value: 'safe' },
                  { label: '仅R-18（需登录）', value: 'r18' },
                ]"
                size="small"
                @update:value="v => update('pixiv_mode', v)"
              />
              <div class="switch-hint" style="margin-top: 4px">R-18 内容需要登录账号才能搜索到；未登录只能看全年龄作品</div>
            </div>
          </template>

          <!-- ASMR-100 专属设置（代理，默认直连） -->
          <template v-if="site === 'asmr'">
            <div class="setting-item">
              <div class="setting-label">ASMR-100 代理地址（浏览/搜索/下载都走此代理，留空 = 直连）</div>
              <n-input
                :value="settings.asmr_proxy"
                placeholder="如 http://127.0.0.1:10809，留空直连"
                size="small"
                @change="v => $emit('asmr-set-proxy', v)"
              />
              <div class="switch-hint" style="margin-top: 4px">ASMR-100 一般可直连；无法访问时再填代理。登录后可同步网站收藏夹</div>
            </div>
          </template>

          <!-- Oreno3D 专属设置（代理，默认直连；登录会话卡在左侧顶部登录区） -->
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

          <!-- EroMMDTube 专属设置（代理，默认直连；登录会话卡在左侧顶部登录区） -->
          <template v-if="site === 'erommdtube'">
            <div class="setting-item">
              <div class="setting-label">EroMMDTube (E站) 代理地址（浏览/搜索/下载都走此代理，留空 = 直连）</div>
              <n-input
                :value="settings.erommd_proxy"
                placeholder="如 http://127.0.0.1:10809，留空直连"
                size="small"
                @change="v => $emit('oreno-set-proxy', v, 'erommdtube')"
              />
              <div class="switch-hint" style="margin-top: 4px">EroMMDTube 一般可直连；无法访问时再填代理。视频实际从 Iwara 源下载（最高画质）</div>
            </div>
          </template>

          <!-- xHamster 专属设置（代理 + 区域，默认 jp） -->
          <template v-if="site === 'xhamster'">
            <div class="setting-item">
              <div class="setting-label">xHamster 代理地址（OAuth + 浏览 + 下载都走此代理）</div>
              <n-input
                :value="settings.xhamster_proxy"
                placeholder="如 http://127.0.0.1:10809"
                size="small"
                @change="v => $emit('site-set-proxy', 'xhamster', v)"
              />
              <div class="switch-hint" style="margin-top: 4px">⚠️ 国内必须配置代理；本工具强制使用 jp.xhamster.com（日本区），规避中文区限制</div>
            </div>
          </template>

          <!-- Pornhub 专属设置（代理 + 区域，默认 jp） -->
          <template v-if="site === 'pornhub'">
            <div class="setting-item">
              <div class="setting-label">Pornhub 代理地址（OAuth + 浏览 + 下载都走此代理）</div>
              <n-input
                :value="settings.pornhub_proxy"
                placeholder="如 http://127.0.0.1:10809"
                size="small"
                @change="v => $emit('site-set-proxy', 'pornhub', v)"
              />
              <div class="switch-hint" style="margin-top: 4px">⚠️ 国内必须配置代理；本工具强制使用 jp.pornhub.com（日本区），规避中文区限制</div>
            </div>
          </template>

          <!-- XVideos 专属设置（代理，默认直连） -->
          <template v-if="site === 'xvideos'">
            <div class="setting-item">
              <div class="setting-label">XVideos 代理地址（浏览 + 下载都走此代理，留空 = 直连）</div>
              <n-input
                :value="settings.xvideos_proxy"
                placeholder="如 http://127.0.0.1:10809，留空直连"
                size="small"
                @change="v => $emit('site-set-proxy', 'xvideos', v)"
              />
              <div class="switch-hint" style="margin-top: 4px">XVideos 全球可直连；如登录被风控或访问慢再填代理</div>
            </div>
          </template>

          <!-- FC2 专属设置（代理，国内必须） -->
          <template v-if="site === 'fc2'">
            <div class="setting-item">
              <div class="setting-label">FC2 代理地址（登录 + 浏览 + 下载都走此代理）</div>
              <n-input
                :value="settings.fc2_proxy"
                placeholder="如 http://127.0.0.1:10809"
                size="small"
                @change="v => $emit('site-set-proxy', 'fc2', v)"
              />
              <div class="switch-hint" style="margin-top: 4px">⚠️ 国内必须配置代理；FC2 API 有 IP 级风控限流，提示限流时稍等自愈</div>
            </div>
          </template>

          <!-- JavDB 专属设置（代理，国内必须） -->
          <template v-if="site === 'javdb'">
            <div class="setting-item">
              <div class="setting-label">JavDB 代理地址（登录 + 搜索 + 下载都走此代理）</div>
              <n-input
                :value="settings.javdb_proxy"
                placeholder="如 http://127.0.0.1:10809，默认已填"
                size="small"
                @change="v => $emit('site-set-proxy', 'javdb', v)"
              />
              <div class="switch-hint" style="margin-top: 4px">⚠️ 国内必须配置代理（默认 http://127.0.0.1:10809）；有 Cloudflare 验证，cookie 约 7 天有效</div>
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

          <!-- GitHub 仓库更新检查 -->
          <n-divider style="margin: 8px 0" />
          <div class="section-title">检查更新（GitHub）</div>
          <div class="setting-item">
            <div class="setting-label">当前版本：{{ appVersion || '（开发模式）' }}</div>
            <div class="setting-label">GitHub 代理地址（国内访问需代理）</div>
            <n-input
              :value="settings.github_proxy"
              placeholder="如 http://127.0.0.1:10809"
              size="small"
              @change="v => update('github_proxy', v)"
            />
          </div>
          <div class="setting-item">
            <n-button
              block
              secondary
              type="info"
              :loading="githubChecking || changelogLoading"
              @click="emit('check-github-update')"
            >
              {{ githubChecking || changelogLoading ? '检查中...' : '检查更新' }}
            </n-button>
          </div>
          <!-- 更新信息 -->
          <div v-if="githubChecking" class="github-update-tip">正在连接 GitHub...</div>
          <div v-else-if="githubError" class="github-update-err">{{ githubError }}</div>
          <div v-else-if="!githubInfo" class="github-update-tip">未检查（点上方"检查更新"手动获取；仓库未公开前可能无法访问）</div>
          <div v-else class="github-update-box">
            <!-- 新版安装包更新（真实更新：下载安装包 + 覆盖安装） -->
            <div v-if="githubInfo.has_new_release" class="github-update-new">
              ⬆ 有新版本！{{ githubInfo.release?.tag }} 可下载更新
            </div>
            <!-- 更新安装包下载进度 -->
            <div v-if="updateDownload.downloading" class="update-dl-box">
              <div class="update-dl-title">正在下载 {{ updateDownload.fileName || '更新安装包' }}</div>
              <n-progress
                type="line"
                :percentage="updateDownload.percent || 0"
                :height="8"
                :show-indicator="true"
                processing
              />
              <div class="update-dl-meta">
                {{ formatSize(updateDownload.received) }}<template v-if="updateDownload.total"> / {{ formatSize(updateDownload.total) }}</template>
                <template v-if="updateDownload.speed"> · {{ formatSize(updateDownload.speed) }}/s</template>
              </div>
            </div>
            <!-- 下载完成 → 立即安装 -->
            <div v-else-if="updateDownload.done && updateDownload.path" class="update-dl-box">
              <div class="update-dl-title">✅ 更新包已下载到「下载」文件夹</div>
              <n-button size="small" type="primary" block @click="emit('install-update')">
                立即安装（覆盖更新，数据不丢失）
              </n-button>
            </div>
            <!-- 有新版本且未开始下载 → 下载按钮 -->
            <div v-else-if="githubInfo.has_new_release && githubInfo.release?.assets?.length" class="update-dl-box">
              <n-button size="small" type="primary" block @click="emit('download-update')">
                下载更新安装包（{{ formatSize(githubInfo.release.assets[0]?.size || 0) }}）
              </n-button>
            </div>
            <div v-else-if="updateDownload.error" class="github-update-err">上次下载失败：{{ updateDownload.error }}</div>
            <div v-if="!githubInfo.has_new_release" :class="githubInfo.has_update ? 'github-update-new' : 'github-update-none'">
              {{ githubInfo.has_update ? '⬆ 源码有新提交（发布新安装包后会在这里提示）' : '✅ 已是最新版本' }}
            </div>
            <div class="github-update-row">
              <span class="github-label">最新提交：</span>
              <span class="github-msg" :title="githubInfo.latest_message">{{ githubInfo.latest_message || '（无）' }}</span>
            </div>
            <div class="github-update-row">
              <span class="github-label">提交者：</span>
              <span>{{ githubInfo.latest_author || '（未知）' }}</span>
            </div>
            <div class="github-update-row">
              <span class="github-label">提交时间：</span>
              <span>{{ formatGithubDate(githubInfo.latest_date) }}</span>
            </div>
            <div class="github-update-row">
              <span class="github-label">SHA：</span>
              <span class="github-sha" :title="githubInfo.latest_sha">{{ (githubInfo.latest_sha || '').slice(0, 7) }}</span>
            </div>
            <div v-if="githubInfo.release" class="github-release-box">
              <div class="github-release-title">📦 最新发布：{{ githubInfo.release.tag || '未命名' }}</div>
              <div class="github-release-meta">发布于 {{ formatGithubDate(githubInfo.release.published_at) }}</div>
              <div v-if="githubInfo.release.body" class="github-release-body">{{ githubInfo.release.body }}</div>
            </div>
            <div class="github-update-actions">
              <n-button size="tiny" quaternary @click="openGithubUrl(githubInfo.latest_url)">查看提交</n-button>
              <n-button size="tiny" quaternary @click="openGithubUrl(githubInfo.commits_url)">提交历史</n-button>
              <n-button size="tiny" quaternary @click="openGithubUrl(githubInfo.repo_url)">仓库主页</n-button>
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
            <n-button
              block
              secondary
              style="margin-top: 8px"
              title="软件使用导览（可视化说明：双世界/功能地图/登录/排查）"
              @click="openHelpPage('software-guide.html')"
            >
              📖 软件使用导览
            </n-button>
            <n-button
              block
              secondary
              style="margin-top: 8px"
              title="本次重大更新可视化说明"
              @click="openHelpPage('changelog-20260918b.html')"
            >
              📜 更新说明（可视化）
            </n-button>
            <n-button
              block
              secondary
              type="info"
              style="margin-top: 8px"
              title="还原嗅探网络设置→结束后端→自动重新启动应用（界面模式随设置恢复）"
              @click="emit('restart-app')"
            >
              🔄 重启应用（登录卡死 / 网络异常时使用）
            </n-button>
          </div>

          <!-- P3 设置功能 -->
          <n-divider style="margin: 16px 0 8px" />
          <div class="section-title">系统功能</div>

          <!-- 登录谷歌邮箱（OAuth 授权共用凭据源：cookie 保存后可供 Xh/Por/Xv 等站授权调用） -->
          <div class="setting-item">
            <div class="setting-label">
              登录谷歌邮箱
              <n-tag v-if="googleUser" size="small" type="success" round style="margin-left: 6px">已登录</n-tag>
            </div>
            <n-input
              v-model:value="googleEmailInput"
              placeholder="谷歌邮箱地址（例：example@gmail.com）"
              size="small"
              style="margin-bottom: 6px"
            />
            <n-input
              v-model:value="googlePasswordInput"
              type="password"
              show-password-on="click"
              placeholder="密码（可选，加密保存在本机）"
              size="small"
              style="margin-bottom: 6px"
            />
            <div style="display: flex; gap: 6px">
              <n-button size="small" type="primary" style="flex: 1" @click="handleGoogleSave">
                保存账号密码
              </n-button>
              <n-button size="small" style="flex: 1" @click="emit('site-oauth-login', 'google', { email: googleEmailInput, password: googlePasswordInput })">
                打开内置浏览器登录
              </n-button>
            </div>
            <!-- 已保存的谷歌账号列表：邮箱/密码可见可复制 + 切换使用 + 删除 -->
            <div v-if="googleAccounts && googleAccounts.length" class="google-account-list">
              <div
                v-for="acc in googleAccounts"
                :key="acc.email"
                class="google-account-item"
                :class="{ active: (acc.email || '').toLowerCase() === (googleUser || googleEmailInput || '').toLowerCase() }"
              >
                <div class="google-account-row" title="点击复制邮箱" @click="copyText(acc.email, '邮箱')">
                  <span class="google-account-email">{{ acc.email }}</span>
                  <n-tag
                    v-if="(acc.email || '').toLowerCase() === (googleUser || googleEmailInput || '').toLowerCase()"
                    size="tiny"
                    type="success"
                    round
                  >使用中</n-tag>
                </div>
                <div
                  class="google-account-row google-account-pass"
                  title="点击复制密码"
                  @click="copyText(acc.password, '密码')"
                >
                  <span>{{ acc.password ? (showGooglePass[acc.email] ? acc.password : '••••••••') : '（未保存密码）' }}</span>
                  <n-button
                    v-if="acc.password"
                    size="tiny"
                    quaternary
                    @click.stop="showGooglePass[acc.email] = !showGooglePass[acc.email]"
                  >{{ showGooglePass[acc.email] ? '隐藏' : '显示' }}</n-button>
                </div>
                <div class="google-account-actions">
                  <n-button
                    size="tiny"
                    secondary
                    type="primary"
                    :disabled="(acc.email || '').toLowerCase() === (googleUser || googleEmailInput || '').toLowerCase()"
                    @click="emit('google-switch-account', acc.email)"
                  >切换使用</n-button>
                  <n-button size="tiny" tertiary type="error" @click="emit('google-delete-account', acc.email)">
                    删除
                  </n-button>
                </div>
              </div>
            </div>
            <div class="setting-hint" style="font-size: 11px; color: #7f7f7f; margin-top: 4px">
              登录后的谷歌 cookie 会加密保存，在其他网站选择"使用 Google 登录"时自动带入凭据；
              Xh/Por/Xv 等站登录弹窗已支持此链路；可保存多个账号方便切换（点击邮箱/密码即复制）
            </div>
          </div>

          <!-- 关闭按钮行为（与关闭时弹窗的"记住我的选择"共用同一设置） -->
          <div class="setting-item">
            <div class="setting-label">关闭按钮行为</div>
            <n-select
              :value="settings.close_action || 'ask'"
              :options="closeActionOptions"
              @update:value="v => update('close_action', v)"
            />
            <div class="setting-hint" style="font-size: 11px; color: #7f7f7f; margin-top: 4px">
              最小化到托盘后下载任务会继续后台运行；关闭窗口时勾选"记住我的选择"也会修改此项
            </div>
          </div>

          <!-- 快捷键：快速缩小到托盘 -->
          <div class="shortcut-row">
            <div class="shortcut-label">快速缩小到托盘</div>
            <div class="shortcut-current">{{ formatShortcut(settings.shortcut_quick_minimize) }}</div>
            <n-button size="tiny" quaternary @click="openShortcutRecorder('quick_minimize')">
              ⚙
            </n-button>
          </div>

          <!-- 快捷键：切换拟态模式 -->
          <div class="shortcut-row">
            <div class="shortcut-label">切换拟态模式</div>
            <div class="shortcut-current">{{ formatShortcut(settings.shortcut_toggle_mimic) }}</div>
            <n-button size="tiny" quaternary @click="openShortcutRecorder('toggle_mimic')">
              ⚙
            </n-button>
          </div>

          <!-- 快捷键：切换悬浮窗 -->
          <div class="shortcut-row">
            <div class="shortcut-label">切换悬浮窗</div>
            <div class="shortcut-current">{{ formatShortcut(settings.shortcut_toggle_float) }}</div>
            <n-button size="tiny" quaternary @click="openShortcutRecorder('toggle_float')">
              ⚙
            </n-button>
          </div>

          <!-- 拟态模式 -->
          <div class="setting-switch" style="margin-top: 12px">
            <div>
              <div class="switch-label">拟态模式</div>
              <div class="switch-hint">开启后可用快捷键唤起"伪装面板"（上传 txt/word/pdf/图片 等），任务栏显示拟态面板，右下角后台运行，不显示悬浮框</div>
            </div>
            <n-switch
              :value="!!settings.mimic_enabled"
              @update:value="v => update('mimic_enabled', v)"
            />
          </div>
          <div v-if="settings.mimic_enabled" class="setting-item">
            <div class="setting-label">拟态面板文件</div>
            <n-input-group>
              <n-input
                :value="settings.mimic_file_path || ''"
                placeholder="未选择文件（点击右侧按钮选择 txt/word/pdf/图片 等）"
                readonly
                style="flex: 1"
              />
              <n-button @click="selectMimicFile" type="primary" ghost>选择</n-button>
            </n-input-group>
            <n-button size="small" block secondary style="margin-top: 6px" @click="enterMimicMode">
              立即进入拟态模式
            </n-button>
          </div>
        </div>
      </n-scrollbar>
    </div>

    <!-- 快捷键录入弹窗 -->
    <n-modal
      v-model:show="shortcutRecorder.show"
      preset="card"
      style="width: 420px; max-width: 92vw"
      title="录入快捷键"
      :mask-closable="false"
    >
      <div class="shortcut-recorder">
        <div class="shortcut-recorder-action">{{ shortcutRecorder.label }}</div>
        <div class="shortcut-recorder-current">
          当前：<span class="shortcut-current-big">{{ formatShortcut(shortcutRecorder.current) || '未设置' }}</span>
        </div>
        <div class="shortcut-recorder-status" :class="{ recording: shortcutRecorder.recording }">
          <span v-if="shortcutRecorder.recording && shortcutRecorder.hint">{{ shortcutRecorder.hint }}</span>
          <span v-else-if="shortcutRecorder.recording">请按下快捷键组合，再次按下相同组合即完成录入...</span>
          <span v-else-if="shortcutRecorder.candidate">已捕获：<strong>{{ formatShortcut(shortcutRecorder.candidate) }}</strong></span>
          <span v-else>点击下方"开始录入"按钮</span>
        </div>
        <div class="shortcut-recorder-actions">
          <n-button
            size="small"
            :type="shortcutRecorder.recording ? 'warning' : 'primary'"
            @click="toggleRecording"
          >
            {{ shortcutRecorder.recording ? '停止录入' : '开始录入' }}
          </n-button>
          <n-button
            size="small"
            type="error"
            quaternary
            :disabled="!shortcutRecorder.current && !shortcutRecorder.candidate"
            @click="clearShortcut"
          >清空</n-button>
          <n-button
            size="small"
            type="primary"
            :disabled="!shortcutRecorder.candidate"
            @click="confirmShortcut"
          >完成</n-button>
        </div>
        <div class="shortcut-recorder-hint">
          录入方法：连续两次按下<strong>相同</strong>的组合键即完成（防止误录），如 Ctrl + Shift + M 按两次。<br>
          也支持纯单键（如 F5 按两次，或单键 M 按两次）。5 秒内未按第二次将自动作废，Esc 取消。
        </div>
      </div>
    </n-modal>

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
import { ref, reactive, computed, watch } from 'vue'
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
  // Pixiv 登录用户名（P站，邮箱密码登录）
  pixivUser: { type: String, default: '' },
  pixivLoginLoading: { type: Boolean, default: false },
  // ASMR-100 登录用户名（音声站，用户名+密码登录）
  asmrUser: { type: String, default: '' },
  asmrLoginLoading: { type: Boolean, default: false },
  // 识图（反向图片搜索）：粘贴板内容（后端 cache/reverse_paste.txt 持久化）
  reversePaste: { type: String, default: '' },
  // 通用 webview OAuth 站点登录用户名（xhamster/pornhub/xvideos/fc2）
  xhamsterUser: { type: String, default: '' },
  fc2User: { type: String, default: '' },
  pornhubUser: { type: String, default: '' },
  xvideosUser: { type: String, default: '' },
  // JavDB 登录用户名
  javdbUser: { type: String, default: '' },
  // 谷歌邮箱登录邮箱（OAuth 授权共用凭据源）/ O3D / E站 会话状态
  googleUser: { type: String, default: '' },
  oreno3dUser: { type: String, default: '' },
  erommdtubeUser: { type: String, default: '' },
  // O3D / E站 表单初始值（来自加密凭据库的保存账号，密码一并回填）
  oreno3dCred: { type: Object, default: () => ({ email: '', password: '' }) },
  erommdtubeCred: { type: Object, default: () => ({ email: '', password: '' }) },
  // 全站登录套件凭据回填（各站保存的账号密码：{站点: {email, password}}，登录表单预填）
  siteCreds: { type: Object, default: () => ({}) },
  // 谷歌邮箱表单初始值（来自加密凭据库的保存邮箱）
  googleEmail: { type: String, default: '' },
  // 谷歌邮箱多账号列表（[{email, password, saved_at}]，设置区展示/复制/切换/删除）
  googleAccounts: { type: Array, default: () => [] },
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
  // X 已归类博主映射（twitter_follows 事件）：[{user_id, screen_name, name, thumbnail, parent, child, tag}]
  twFollows: { type: Array, default: () => [] },
  // 本地媒体代理端口（头像走代理加载）
  mediaProxyPort: { type: Number, default: 0 },
  leakEdgeRunning: { type: Boolean, default: false },  // Leakedzone：专用 Edge 调试实例是否已打开
  // 界面主题：dark=夜间 / light=日间
  themeMode: { type: String, default: 'dark' },
  // 有道翻译结果：{ok, translation, query, error, raw} 或 null（翻译中）
  translateResult: { type: Object, default: null },
  // GitHub 仓库更新检查结果：{ok, latest_sha, latest_message, ...} 或 null（检查中）
  githubUpdateInfo: { type: Object, default: null },
  // 检查进行中（仅手动点击"检查更新"时为 true；启动后不发任何 GitHub 请求）
  githubChecking: { type: Boolean, default: false },
  // 更新日志拉取中（点"检查更新"先拉更新日志弹窗）
  changelogLoading: { type: Boolean, default: false },
  // 当前程序版本号（Electron app.getVersion()）
  appVersion: { type: String, default: '' },
  // 更新安装包下载状态 { downloading, received, total, percent, speed, fileName, path, done, error }
  updateDownload: { type: Object, default: () => ({ downloading: false, received: 0, total: 0, percent: 0, speed: 0, fileName: '', path: '', done: false, error: '' }) },
})

const emit = defineEmits([
  'update:settings',
  'clear-cache',
  'toggle-downloads',
  'toggle-float',
  'cancel-login',          // 取消登录转圈等待（参数：站点 key）
  'restart-app',           // 重启应用（还原网络→杀后端→relaunch，界面模式随设置恢复）
  'leak-edge-login',       // Leakedzone：用系统 Edge 过盾（打开带调试端口的专用 Edge 窗口）
  'leak-edge-harvest',     // Leakedzone：用户过盾后，经 CDP 抓取 Cookie+UA 保存
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
  // Pixiv（P站）
  'pixiv-login',           // 邮箱密码登录（参数：邮箱, 密码）
  'pixiv-logout',          // 退出 Pixiv 登录
  'pixiv-set-proxy',       // 修改 Pixiv 代理（参数：代理地址，国内必须）
  // ASMR-100（音声站）
  'asmr-login',            // 用户名密码登录（参数：用户名, 密码）
  'asmr-logout',           // 退出 ASMR 登录
  'asmr-set-proxy',       // 修改 ASMR 代理（参数：代理地址，空=直连）
  // 识图（反向图片搜索）
  'reverse-toggle',       // 识图视图开关（参数：true=占用右侧展示区 / false=退出）
  'reverse-paste-save',   // 保存粘贴板内容（参数：文本）
  'reverse-set-proxy',    // 修改识图代理（参数：代理地址，空=直连）
  // Oreno3D（O3D）/ EroMMDTube（E站）
  'oreno-set-proxy',       // 修改 O3D/E站 代理（参数：代理地址, 可选 site_key 'erommdtube'，空=直连）
  'common-proxy',         // 通用代理地址变更（Pornhub / GitHub 更新共用）
  'tw-add-follow-tag',    // 新增关注分类（参数：母类, 子类）
  'tw-open-user',         // 从分类管理点开博主 → 进 TA 的主页（参数：用户对象）
  'tw-get-follows',       // 展开分类时拉取已归类博主列表
  'tw-delete-follow-tag', // 删除关注分类（参数：母类, 子类）
  'tw-clear-cache',       // 清除 Twitter 专属缓存
  'toggle-theme',         // 切换日间/夜间模式
  // ExHentai
  'exhentai-set-cookies', // 粘贴 cookie 登录 EX
  'exhentai-webview-login', // 打开 webview 浏览器登录 e-hentai 论坛（EX 推荐方式）
  'exhentai-logout',      // 退出 EX 登录
  // 通用 webview OAuth 三站（xhamster/pornhub/xvideos）
  'site-oauth-login',     // 触发 webview OAuth 登录弹窗（参数：站点 key）
  'site-logout',          // 退出登录（参数：站点 key）
  'site-set-proxy',       // 修改代理（参数：站点 key, 代理地址）
  // 谷歌邮箱（OAuth 授权共用凭据源）
  'google-save-cred',     // 保存账号密码（参数：邮箱, 密码）
  'google-switch-account', // 切换谷歌账号（参数：邮箱）
  'google-delete-account', // 删除谷歌账号记录（参数：邮箱）
  'oreno-save-cred',      // O3D/E站 保存账号密码（参数：site_key, 账号, 密码）
  'site-save-cred',       // 通用保存账号密码（参数：站点 key, 账号, 密码）
  // 登录引导 / 账号档案
  'open-login-page',      // 打开登录页（参数：站点 key）
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
  // 有道翻译
  'translate-youdao',      // 调有道 API 翻译（参数：{text, from, to}）[兼容旧名]
  'translate-free',        // 调免费翻译（参数：{text, from, to}；后端按 settings.translate_engine 选 Google/LibreTranslate/有道）
  // GitHub 仓库更新检查
  'check-github-update',   // 检查 GitHub 仓库 main 分支最新 commit + 最新 release
  'download-update',       // 下载最新版安装包（后端流式下载 + 进度事件）
  'install-update',        // 运行已下载的更新安装包（覆盖安装即更新）
  // P3 设置功能
  'shortcut-change',        // 快捷键录入变更（参数：action, accelerator）
  // BT 下载
  'bt-open',               // 打开独立 BT 下载窗口（磁力链接批量粘贴 + .torrent 种子拖拽）
])

const message = useMessage()

// 通用代理（默认代理与端口）草稿：进入设置面板时从 settings 初始化一次
const commonProxyDraft = ref(props.settings.common_proxy || '')
watch(() => props.settings.common_proxy, (v) => {
  commonProxyDraft.value = v || ''
})


// 当前展开的面板：'' | 'settings' | 'history' | 'favorites'
const activePanel = ref('')

// 识图：面板开关联动右侧识图视图（占用/退出右侧展示区）
watch(activePanel, (p) => {
  emit('reverse-toggle', p === 'ocr')
})

// 识图粘贴板本地编辑（prop 同步进本地，失焦保存回后端）
const reversePasteLocal = ref('')
watch(() => props.reversePaste, (v) => {
  if (v !== reversePasteLocal.value) reversePasteLocal.value = v || ''
}, { immediate: true })

// ============================
// 登录状态（账号卡片）
// ============================
const needsLogin = computed(() => ['pawchive', 'twitter', 'exhentai', 'iwara', 'hanime', 'pixiv', 'asmr', 'xhamster', 'pornhub', 'xvideos', 'javdb', 'oreno3d', 'erommdtube', 'fc2', 'leakedzone', 'coomerst', 'coomerfans', 'fapello'].includes(props.site))

// O3D / E站（Oreno3D / EroMMDTube）：无账号体系，登录 = 保存站点会话（Cloudflare 免重复验证）
const isOrenoSite = computed(() => props.site === 'oreno3d' || props.site === 'erommdtube')

const siteLoggedIn = computed(() => {
  if (props.site === 'pawchive') return !!props.pawchiveUser
  if (props.site === 'twitter') return !!props.twitterUser
  if (props.site === 'exhentai') return !!props.exhentaiUser
  if (props.site === 'iwara') return !!props.iwaraUser
  if (props.site === 'hanime') return !!props.hanimeUser
  if (props.site === 'pixiv') return !!props.pixivUser
  if (props.site === 'asmr') return !!props.asmrUser
  if (props.site === 'xhamster') return !!props.xhamsterUser
  if (props.site === 'pornhub') return !!props.pornhubUser
  if (props.site === 'xvideos') return !!props.xvideosUser
  if (props.site === 'javdb') return !!props.javdbUser
  if (props.site === 'oreno3d') return !!props.oreno3dUser
  if (props.site === 'erommdtube') return !!props.erommdtubeUser
  if (props.site === 'fc2') return !!props.fc2User || !!props.loginInfo?.fc2?.logged_in
  if (props.site === 'leakedzone') return !!props.loginInfo?.leakedzone?.logged_in
  if (props.site === 'coomerst' || props.site === 'coomerfans' || props.site === 'fapello') return true  // 免登录站
  return false
})

const loginSubtitle = computed(() => {
  if (!needsLogin.value) return '无需登录'
  if (props.site === 'twitter') return props.twitterUser ? `X 已登录: @${props.twitterUser}` : 'X (Twitter) 未登录'
  if (props.site === 'pawchive') return props.pawchiveUser ? `已登录: ${props.pawchiveUser}` : 'Pawchive 未登录'
  if (props.site === 'exhentai') return props.exhentaiUser ? 'ExHentai 已登录' : 'ExHentai 未登录'
  if (props.site === 'iwara') return props.iwaraUser ? `Iwara 已登录: ${props.iwaraUser}` : 'Iwara 未登录'
  if (props.site === 'hanime') return props.hanimeUser ? `H站已登录: ${props.hanimeUser}` : 'Hanime1 未登录'
  if (props.site === 'pixiv') return props.pixivUser ? `P站已登录: ${props.pixivUser}` : 'Pixiv 未登录'
  if (props.site === 'asmr') return props.asmrUser ? `音声站已登录: ${props.asmrUser}` : 'ASMR-100 未登录'
  if (props.site === 'fc2') return props.fc2User ? `FC2 已登录: ${props.fc2User}` : 'FC2 未登录（免费视频无需登录）'
  if (props.site === 'xhamster') return props.xhamsterUser ? `xHamster 已登录: ${props.xhamsterUser}` : 'xHamster 未登录'
  if (props.site === 'pornhub') return props.pornhubUser ? `Pornhub 已登录: ${props.pornhubUser}` : 'Pornhub 未登录'
  if (props.site === 'xvideos') return props.xvideosUser ? `XVideos 已登录: ${props.xvideosUser}` : 'XVideos 未登录'
  if (props.site === 'javdb') return props.javdbUser ? `JavDB 已登录: ${props.javdbUser}` : 'JavDB 未登录'
  if (props.site === 'oreno3d') return props.oreno3dUser ? `O3D 已登录: ${props.oreno3dUser}` : 'Oreno3D 未登录'
  if (props.site === 'erommdtube') return props.erommdtubeUser ? `E站已登录: ${props.erommdtubeUser}` : 'EroMMDTube 未登录'
  return ''
})

// 当前站点的登录信息（来自后端缓存文件，切换站点不丢失）
const siteLoginInfo = computed(() => props.loginInfo[props.site] || {})
const siteUsername = computed(() => {
  if (props.site === 'twitter' && props.twitterUser) return props.twitterUser
  if (props.site === 'pawchive' && props.pawchiveUser) return props.pawchiveUser
  if (props.site === 'asmr' && props.asmrUser) return props.asmrUser
  if (props.site === 'fc2' && props.fc2User) return props.fc2User
  if (props.site === 'xhamster' && props.xhamsterUser) return props.xhamsterUser
  if (props.site === 'pornhub' && props.pornhubUser) return props.pornhubUser
  if (props.site === 'xvideos' && props.xvideosUser) return props.xvideosUser
  if (props.site === 'javdb' && props.javdbUser) return props.javdbUser
  if (props.site === 'oreno3d' && props.oreno3dUser) return props.oreno3dUser
  if (props.site === 'erommdtube' && props.erommdtubeUser) return props.erommdtubeUser
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
  coomerst: 'https://coomer.st',
  coomerfans: 'https://coomerfans.com',
  fapello: 'https://fapello.com',
  leakedzone: 'https://leakedzone.com',
  coomer: 'https://xxxcoomer.com',
  fc2: 'https://video.fc2.com/a/',
  pawchive: 'https://pawchive.pw',
  exhentai: 'https://exhentai.org',
  twitter: 'https://x.com',
  iwara: 'https://www.iwara.tv',          // 注：iwara 站实际 URL 由 openSiteInBrowser 按 iwSite 动态切换
  hanime: 'https://hanime1.me',
  oreno3d: 'https://oreno3d.com',
  erommdtube: 'https://erommdtube.com',
  asmr: 'https://asmr-100.com/popular',   // 音声站主页（热门作品页）
  // 三次元新站（选用 jp 区域版本，规避国内/中文区限制）
  xhamster: 'https://jp.xhamster.com',
  pornhub: 'https://jp.pornhub.com',
  xvideos: 'https://www.xvideos.com',
  javdb: 'https://javdb.com',
  pixiv: 'https://www.pixiv.net',
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
  let url = SITE_URLS[props.site] || 'https://bunkr.sk'
  // iwara 站动态：AI 站用 iwara.ai，否则 iwara.tv
  if (props.site === 'iwara') {
    url = props.iwSite === 'ai' ? 'https://www.iwara.ai' : 'https://www.iwara.tv'
  }
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
  coomerst: `🐱 Coomer 使用技巧（综合资源站点 · OnlyFans/Fansly 归档）

1. 点上方「热门创作者」浏览，或在搜索框输入创作者名称（支持模糊匹配）。
2. 点创作者卡片 → 自动解析 TA 的全部帖子媒体，出文件列表后勾选下载。
3. 也可直接粘贴链接：coomer.st/onlyfans/user/{创作者ID}
4. 该站必须走代理（已默认走系统代理 10809）；站方 CDN 节点偶发不可用，
   届时可搜索浏览但下载会失败，稍后再试即可。
5. 反扒机制：接口需特殊 Accept 头（已内置处理，无需手动配置）。`,
  coomerfans: `🐱 CoomerFans 使用技巧（综合资源站点 · OnlyFans/Fansly/CandFans 归档）

1. 点上方「最新帖子」浏览最新内容，或在搜索框输入关键词搜索。
2. 点帖子卡片 → 解析该帖全部媒体（图片/视频），勾选下载。
3. 也可直接粘贴链接：coomerfans.com/p/{创作者ID}/{帖子ID}/{服务}
4. 该站有 PoW 反爬挑战（应用已自动破解，无需手动操作）；
   若频繁 503 说明触发限流，等几分钟再试。
5. 媒体必须走代理+会话 Cookie（已内置处理，走本地媒体代理下载）。`,
  fapello: `📷 Fapello 使用技巧（综合资源站点 · 模型图集）

1. 点上方「最新模型」浏览最新图集，或在搜索框输入模型名称。
2. 点模型卡片 → 自动翻页解析 TA 的全部图片（每页自动追加），勾选下载。
3. 也可直接粘贴链接：fapello.com/{模型名}/
4. 图片直链经本地媒体代理转发（该站必须走代理，已默认 10809）。
5. 大模型图集较多，解析需要一些时间，耐心等待文件列表出现。`,
  leakedzone: `🔒 Leakedzone 使用技巧（综合资源站点）

⚠️ 该站有 Cloudflare 盾：首次使用需先过盾——
   点左侧「打开内置浏览器」→ 在弹窗内等页面加载完成（出现内容）→ 关闭弹窗。
   过盾 Cookie 会自动保存，之后正常使用。

1. 点上方「最新内容」浏览，或在搜索框输入关键词。
2. 点内容卡片 → 解析图片列表，勾选下载。
3. 若提示"需要过 Cloudflare 盾"，重复上述登录步骤即可（盾 Cookie 有有效期）`,

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

🔑 无原站账号体系：浏览/搜索/下载无需登录（站点本身无登录注册功能）

💡 本工具提示：
- 主页默认按人気排序，可切换 急上昇/高評価/新着/人気
- "热门分类"弹窗列出分类组与全部标签，点击看该分类视频
- "角色列表"：人気角色 + 五十音分组查找，点角色看 TA 的视频
- "人気作者"：按排名分页浏览，点作者看全部作品
- 点视频卡片进详情：在线播放（iwara 源最高画质）、查看作者/标签/统计
- 卡片右上角 ♥ 可收藏到本地（oreno3d 站本身无服务端账号，本地保存跨设备不同步）
- 工具栏"♥ 我的收藏"查看本地收藏列表
- 下载实际从 Iwara 源获取（最高画质），无需登录
- O3D 一般可直连；无法访问时在左侧设置里填代理
- 粘贴 oreno3d.com/movies/... 链接可直接解析下载`,
  erommdtube: `🎬 EroMMDTube（E站）使用技巧

EroMMDTube 与 Oreno3D 同架构的 3D 动画（MMD 等）视频索引站，视频源托管在 Iwara。

🔑 无需登录：直接浏览/搜索/下载

💡 本工具提示：
- 主页默认按人気排序，可切换 急上昇/高評価/新着/人気
- "热门分类"弹窗列出分类组与全部标签，点击看该分类视频
- "角色列表"：人気角色 + 五十音分组查找，点角色看 TA 的视频
- "人気作者"：按排名分页浏览，点作者看全部作品
- 点视频卡片进详情：在线播放（iwara 源最高画质）、查看作者/标签/统计
- 卡片右上角 ♥ 可收藏到本地，"我的收藏"随时回看
- 下载实际从 Iwara 源获取（最高画质），无需登录
- E站一般可直连；无法访问时在左侧设置里填代理
- 粘贴 erommdtube.com/movies/... 链接可直接解析下载`,
  xhamster: `🎞️ xHamster（jp.xhamster.com）使用技巧

xHamster 是国际老牌视频站，不同区域子域名内容与限制不同。本工具默认选用 jp.xhamster.com（日本区），规避中文区限制。

🔑 登录（推荐 X 站 OAuth）：
- 点左侧"用 Twitter (X) 登录"按钮，弹窗内会自动用本工具已登录的 X 站 cookie 完成 OAuth 授权
- 不需重新输密码；登录后 cookie 加密长期保存
- 也可"打开网站"在浏览器手动登录后点"一键抓取浏览器 Cookie"

💡 本工具提示：
- ⚠️ 国内必须配置代理（左侧 xHamster 代理设置，默认 http://127.0.0.1:10809）
- 区域切换：代理落地不同国家会自动跳转 zh/jp/... 子域；本工具强制使用 jp 域
- 搜索/解析/下载待 AP2 阶段补全（当前为登录框架占位）
- 视频直链由 cdn.xhcdn.com 提供，下载走代理`,
  pornhub: `🎞️ Pornhub（jp.pornhub.com）使用技巧

Pornhub 是国际最大的视频站之一，不同区域子域名内容与限制不同。本工具默认选用 jp.pornhub.com（日本区）。

🔑 登录（推荐 X 站 OAuth）：
- 点左侧"用 Twitter (X) 登录"按钮，弹窗内会自动用本工具已登录的 X 站 cookie 完成 OAuth 授权
- 不需重新输密码；登录后 cookie 加密长期保存
- 也可"打开网站"在浏览器手动登录后点"一键抓取浏览器 Cookie"

💡 本工具提示：
- ⚠️ 国内必须配置代理（左侧 Pornhub 代理设置，默认 http://127.0.0.1:10809）
- 区域切换：代理落地不同国家会自动跳转 zh/jp/... 子域；本工具强制使用 jp 域
- 搜索/解析/下载待 AP3 阶段补全（当前为登录框架占位）
- 视频直链由 cdn.phncdn.com 提供，下载走代理`,
  xvideos: `🎞️ XVideos（xvideos.com）使用技巧

XVideos 是国际最大的免费视频站，无区域子域，全球可用，但登录有人机验证 + "在此装置上记住我"。

🔑 登录（邮箱密码）：
- 在左侧表单填入你的 XVideos 邮箱与密码
- 第一次登录可能弹出人机验证（选图片/点击等），在弹窗内按提示完成即可
- 勾选"在此装置上记住我"可减少后续验证频率
- 登录后 cookie 加密长期保存，重启工具自动恢复

💡 本工具提示：
- XVideos 一般可直连，也可填代理
- 搜索/解析/下载待你给出具体要求后再补全（当前为登录框架占位）
- 机器验证弹窗会通过 webview 自动显示，无需手动开浏览器`,
  javdb: `🎬 JavDB（javdb.com）使用技巧

JavDB 是影片信息数据库站：查番号/标题/演员、看封面预览图、拿磁力链接。

🔑 登录（邮箱密码，约 7 天有效）：
- 在左侧表单填入 JavDB 邮箱与密码，点登录
- 弹窗内会自动预填账号，完成 Cloudflare 人机验证并点网站登录按钮即可
- 勾选网站内"记住此装置"后 cookie 约 7 天有效，过期在左侧重新登录

💡 本工具提示：
- ⚠️ 国内必须配置代理（左侧 JavDB 代理设置，默认 http://127.0.0.1:10809）
- 输入番号（如 SSIS-001）/标题/演员名搜索，点卡片看详情
- 详情页含：封面、预览图、标签、演员、磁力链接列表（含大小/日期/字幕）
- 点磁力链接自动复制到剪贴板，用外部种子客户端下载
- "下载图片"保存封面+全部预览图；"批量下载全部"下载当前页全部视频的图片
- 未登录时预览图与部分磁力不可见，建议先登录`,
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
  else if (props.site === 'asmr') emit('asmr-logout')
  else if (props.site === 'pixiv') emit('pixiv-logout')
  else if (['xhamster', 'pornhub', 'xvideos', 'javdb', 'oreno3d', 'erommdtube', 'fc2', 'leakedzone'].includes(props.site)) emit('site-logout', props.site)
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

// X 登录：账号密码（弹窗自动预填）+ 可选粘贴整段 Cookie（含 auth_token / ct0）
const twEmailInput = ref('')
const twPasswordInput = ref('')
const twCookieInput = ref('')

// ExHentai 登录表单：账号密码（弹窗自动预填）+ 可选粘贴 Cookie
const exEmailInput = ref('')
const exPasswordInput = ref('')
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

// Pixiv 登录：内置浏览器 OAuth（Refresh Token 方案，无账号密码表单）
function handlePixivLogin() {
  emit('pixiv-login')
}

// ASMR-100 用户名密码登录表单
const asmrNameInput = ref('')
const asmrPasswordInput = ref('')

function handleAsmrLogin() {
  if (!asmrNameInput.value.trim() || !asmrPasswordInput.value) return
  emit('asmr-login', asmrNameInput.value.trim(), asmrPasswordInput.value)
}

// JavDB 邮箱密码登录表单（触发 webview 弹窗，登录页自动预填账号）
const jdbEmailInput = ref('')
const jdbPasswordInput = ref('')
const jdbRemember = ref(true)

// JavDB 账号密码长期回填：login_info 里带保存的凭据时自动填入表单（仅空值时回填，不打断手动输入）
watch(() => props.loginInfo.javdb, (jdb) => {
  if (jdb && jdb.email && !jdbEmailInput.value) {
    jdbEmailInput.value = jdb.email
    if (jdb.password && !jdbPasswordInput.value) {
      jdbPasswordInput.value = jdb.password
    }
  }
}, { immediate: true })

// 全站登录套件凭据回填：siteCreds 里带保存的账号密码时自动填入各站登录表单
//（仅空值时回填，不打断手动输入；表单状态自持，切换站点不丢）
watch(() => props.siteCreds, (creds) => {
  if (!creds) return
  const fill = (emailRef, passRef, c) => {
    if (c && c.email && !emailRef.value) emailRef.value = c.email
    if (c && c.password && !passRef.value) passRef.value = c.password
  }
  fill(loginUsername, loginPassword, creds.pawchive)
  fill(twEmailInput, twPasswordInput, creds.twitter)
  fill(exEmailInput, exPasswordInput, creds.exhentai)
  fill(iwaraEmailInput, iwaraPasswordInput, creds.iwara)
  fill(hanimeEmailInput, hanimePasswordInput, creds.hanime)
  fill(asmrNameInput, asmrPasswordInput, creds.asmr)
  fill(jdbEmailInput, jdbPasswordInput, creds.javdb)
}, { immediate: true })

// 通用账号密码保存（全站登录套件：后端 site_save_cred 加密入库，下次启动回填）
function handleSiteSaveCred(siteKey, email, password) {
  if (!email || !email.trim()) {
    message.warning('请输入账号（邮箱/用户名）')
    return
  }
  emit('site-save-cred', siteKey, email.trim(), password || '')
}

// 谷歌邮箱凭据表单（设置区"登录谷歌邮箱"）
const googleEmailInput = ref('')
const googlePasswordInput = ref('')
// 多账号列表密码显示开关（email -> boolean，默认隐藏）
const showGooglePass = reactive({})
// 初始邮箱来自加密凭据库（App.vue 从 login_info 提取传入）
watch(() => props.googleEmail, (v) => {
  if (v && !googleEmailInput.value) googleEmailInput.value = v
}, { immediate: true })

function handleGoogleSave() {
  emit('google-save-cred', googleEmailInput.value, googlePasswordInput.value)
}

// Oreno3D / EroMMDTube 账号密码表单（保存后与 cookie 互相验证登录状态）
const oreno3dEmailInput = ref('')
const oreno3dPasswordInput = ref('')
const erommdtubeEmailInput = ref('')
const fc2EmailInput = ref('')
const fc2PasswordInput = ref('')
const erommdtubePasswordInput = ref('')

// 凭据回填：login_info 里带保存的账号密码时自动填入表单（仅空值时回填，不打断手动输入）
watch(() => props.oreno3dCred, (cred) => {
  if (cred && cred.email && !oreno3dEmailInput.value) {
    oreno3dEmailInput.value = cred.email
    if (cred.password && !oreno3dPasswordInput.value) {
      oreno3dPasswordInput.value = cred.password
    }
  }
}, { immediate: true })

watch(() => props.erommdtubeCred, (cred) => {
  if (cred && cred.email && !erommdtubeEmailInput.value) {
    erommdtubeEmailInput.value = cred.email
    if (cred.password && !erommdtubePasswordInput.value) {
      erommdtubePasswordInput.value = cred.password
    }
  }
}, { immediate: true })

function handleOrenoSave(siteKey) {
  const email = siteKey === 'erommdtube' ? erommdtubeEmailInput.value : oreno3dEmailInput.value
  const password = siteKey === 'erommdtube' ? erommdtubePasswordInput.value : oreno3dPasswordInput.value
  emit('oreno-save-cred', siteKey, email, password)
}

// O3D / E站 登录：打开 webview 弹窗（站点首页），完成 Cloudflare 验证后点"确认"保存会话；
// 表单账号密码随 cookie 一起保存（下次自动回填）
function handleOrenoLogin(siteKey) {
  const email = (siteKey === 'erommdtube' ? erommdtubeEmailInput.value : oreno3dEmailInput.value).trim()
  const password = siteKey === 'erommdtube' ? erommdtubePasswordInput.value : oreno3dPasswordInput.value
  emit('site-oauth-login', siteKey, { email, password })
}

function handleJdbLogin() {
  if (!jdbEmailInput.value.trim() || !jdbPasswordInput.value) {
    window.alert('请先输入 JavDB 登录邮箱和密码（免费注册：javdb.com）')
    return
  }
  // 触发 App.vue 的 webview 登录弹窗（登录页自动预填邮箱密码，用户只需完成 Cloudflare 验证并点登录）
  emit('site-oauth-login', 'javdb', {
    email: jdbEmailInput.value.trim(),
    password: jdbPasswordInput.value,
    remember: jdbRemember.value,
  })
}

function handleTwitterLogin() {
  if (!twCookieInput.value.trim()) return
  emit('twitter-set-cookies', twCookieInput.value.trim())
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

// X 文件夹组织选项（博主名/图片|视频 两级，避免嵌套过多）
const twitterSubfolderOptions = [
  { label: '图片/视频分类（推荐）', value: 'media' },
  { label: '不分类（全部放博主名下）', value: 'none' },
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

// 关闭按钮行为选项（main.cjs 关闭拦截读取 settings.json 的 close_action 字段）
const closeActionOptions = [
  { label: '每次询问（默认）', value: 'ask' },
  { label: '最小化到托盘（后台继续下载）', value: 'tray' },
  { label: '直接退出程序', value: 'exit' },
]

// ============================
// 有道翻译（文本翻译面板）
// ============================
const trLangOptions = [
  { label: '自动检测', value: 'auto' },
  { label: '中文', value: 'zh-CHS' },
  { label: '英文', value: 'en' },
  { label: '日文', value: 'ja' },
  { label: '韩文', value: 'ko' },
  { label: '法文', value: 'fr' },
  { label: '德文', value: 'de' },
  { label: '俄文', value: 'ru' },
  { label: '西班牙文', value: 'es' },
]
const trFrom = ref('auto')
const trTo = ref('zh-CHS')
const trInput = ref('')
// 翻译请求 token：每次点翻译自增，用于判断 props.translateResult 是否对应本次请求
let trReqToken = 0
const translating = computed(() => !!trReqToken && !props.translateResult)
const trOutput = computed(() => {
  const r = props.translateResult
  return r && r.ok ? (r.translation || '') : ''
})
const trError = computed(() => {
  const r = props.translateResult
  return r && !r.ok ? (r.error || '翻译失败') : ''
})
const trDetected = computed(() => {
  const r = props.translateResult
  return r && r.ok ? (r.detected_source || '') : ''
})
const trEngine = computed(() => {
  const r = props.translateResult
  if (!r || !r.ok) return ''
  const e = r.engine || ''
  return e === 'google_free' ? 'Google 免费' : (e === 'libretranslate' ? 'LibreTranslate' : (e === 'youdao' ? '有道' : e))
})

function doTranslate() {
  const text = trInput.value.trim()
  if (!text) return
  // 自动调整目标语言：源=目标时改成英文（避免无意义请求）
  let to = trTo.value
  if (trFrom.value !== 'auto' && trFrom.value === to) {
    to = trFrom.value === 'zh-CHS' ? 'en' : 'zh-CHS'
  }
  trReqToken += 1
  emit('translate-free', { text, from: trFrom.value, to })
}

async function pasteClipboard() {
  try {
    const text = await navigator.clipboard.readText()
    if (text) {
      trInput.value = (trInput.value ? trInput.value + ' ' : '') + text
    } else {
      message.info('剪贴板为空')
    }
  } catch (e) {
    message.warning('读取剪贴板失败，请手动 Ctrl+V 粘贴')
  }
}

// 监听翻译结果：失败时 toast 提示（结果区已显示详情，不重复弹框）
watch(() => props.translateResult, (r) => {
  if (r && r.ok) {
    trReqToken = 0
  } else if (r && !r.ok) {
    trReqToken = 0
  }
})

// ============================
// GitHub 仓库更新检查（设置区）
// ============================
// githubChecking 改为显式 prop（App.vue 传）：启动后 info=null 显示"未检查"，不发任何请求
const githubInfo = computed(() => {
  const r = props.githubUpdateInfo
  return r && r.ok ? r : null
})
const githubError = computed(() => {
  const r = props.githubUpdateInfo
  return r && !r.ok ? (r.error || '检查失败') : ''
})

function formatGithubDate(s) {
  if (!s) return '（未知）'
  // GitHub 返回 ISO 8601：2026-08-28T12:34:56Z
  const d = new Date(s)
  if (isNaN(d.getTime())) return s
  return d.toLocaleString('zh-CN', { hour12: false })
}

// 字节数格式化（更新包大小/速度显示用）
function formatSize(bytes) {
  if (!bytes || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let v = bytes
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${units[i]}`
}

async function openGithubUrl(url) {
  if (!url) return
  if (window.api && window.api.openExternal) {
    await window.api.openExternal(url)
  }
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

// ---------- 分类管理查看（点开母类/子类 → 归类博主列表 → 进入主页） ----------
const openTag = ref('')     // 当前展开的母类
const openChild = ref('')   // 当前过滤的子类（空=全部）

function toggleTagOpen(name) {
  if (!props.twFollows.length) emit('tw-get-follows')
  if (openTag.value === name) {
    openTag.value = ''
    openChild.value = ''
  } else {
    openTag.value = name
    openChild.value = ''
  }
}

function toggleChildFilter(parent, child) {
  if (!props.twFollows.length) emit('tw-get-follows')
  if (openTag.value !== parent) openTag.value = parent
  openChild.value = openChild.value === child ? '' : child
}

function memberCount(parent) {
  return props.twFollows.filter(m => m.parent === parent).length
}

function childCount(parent, child) {
  return props.twFollows.filter(m => m.parent === parent && m.child === child).length
}

function tagMembers(parent) {
  const list = props.twFollows.filter(m => m.parent === parent)
  return openChild.value ? list.filter(m => m.child === openChild.value) : list
}

function memberAvatar(url) {
  if (!url) return ''
  if (url.startsWith('thumb://') || (props.mediaProxyPort && url.startsWith('http'))) {
    return props.mediaProxyPort && url.startsWith('http')
      ? `http://127.0.0.1:${props.mediaProxyPort}/media?url=${encodeURIComponent(url)}`
      : url
  }
  return url
}

function openMember(m) {
  emit('tw-open-user', {
    screen_name: m.screen_name,
    name: m.name,
    thumbnail: m.thumbnail,
    album_url: m.album_url || `https://x.com/${m.screen_name}`,
    user_id: m.user_id,
  })
}

function openHelpPage(file) {
  window.api && window.api.openHelpWindow && window.api.openHelpWindow(file)
}

function handleClearCache() {
  emit('clear-cache')
}

// ============================
// P3 设置功能：快捷键录入 / 拟态模式
// ============================
// 快捷键录入弹窗状态
const shortcutRecorder = reactive({
  show: false,
  action: '',                          // quick_minimize | toggle_mimic | toggle_float
  label: '',                           // 显示名
  current: '',                         // 当前已保存的 accelerator（Electron "+" 格式）
  candidate: '',                       // 本次录入捕获的 candidate
  recording: false,                    // 是否在录入
  hint: '',                            // 录入提示（"请再次按下相同组合确认"）
  resetTimer: null,                    // 两步录入超时重置定时器
  keydownHandler: null,
})
const shortcutLabels = {
  quick_minimize: '快速缩小到托盘',
  toggle_mimic: '切换拟态模式',
  toggle_float: '切换悬浮窗',
}
// Electron accelerator 显示格式：Ctrl+Shift+M → "Ctrl + Shift + M"
function formatShortcut(accelerator) {
  if (!accelerator) return ''
  return String(accelerator).split('+').map(s => s.trim()).filter(Boolean).join(' + ')
}
// KeyboardEvent → 主键名（不含修饰键部分；修饰键/无法识别返回 ''）
function mainKeyFromEvent(e) {
  const code = e.code || ''
  // 兜底：部分注入/驱动环境 keydown 无 e.code（只有 e.key）——按 e.key 推断主键，
  // 否则这类按键全部被忽略（"快捷键录入一直不可用"的第二根因）
  if (!code) {
    const k = (e.key || '').toUpperCase()
    if (/^[A-Z]$/.test(k)) return k
    if (/^F([1-9]|1[0-9])$/.test(k)) return k
    if (/^[0-9]$/.test(k)) return k
    return ''
  }
  if (/^(Control|Shift|Alt|Meta|OS)(Left|Right)?$/.test(code)) return ''
  if (/^Digit[0-9]$/.test(code)) return code.replace('Digit', '')
  if (/^Key[A-Z]$/.test(code)) return code.replace('Key', '')
  if (/^F[1-9]\d?$/.test(code)) return code
  if (code === 'Space') return 'Space'
  if (code === 'Enter') return 'Return'
  if (code === 'Escape') return ''
  if (code === 'Backspace') return 'Backspace'
  if (code === 'Tab') return 'Tab'
  if (/^Arrow(Up|Down|Left|Right)$/.test(code)) return code.replace('Arrow', '')
  if (code.startsWith('Numpad')) return 'Num' + code.replace('Numpad', '')
  return (e.key || '').toUpperCase()
}
function openShortcutRecorder(action) {
  shortcutRecorder.action = action
  shortcutRecorder.label = shortcutLabels[action] || action
  shortcutRecorder.current = props.settings[`shortcut_${action}`] || ''
  shortcutRecorder.candidate = ''
  shortcutRecorder.recording = false
  shortcutRecorder.show = true
}
function toggleRecording() {
  if (shortcutRecorder.recording) {
    stopRecording()
  } else {
    startRecording()
  }
}
// 两步录入：第二次按下相同组合即确认；5 秒内未按第二次自动作废
function armStepTimeout() {
  if (shortcutRecorder.resetTimer) clearTimeout(shortcutRecorder.resetTimer)
  shortcutRecorder.resetTimer = setTimeout(() => {
    if (shortcutRecorder.candidate) {
      shortcutRecorder.candidate = ''
      shortcutRecorder.hint = '（超时）已作废，请重新录入'
    }
  }, 5000)
}
function resetStepState() {
  if (shortcutRecorder.resetTimer) {
    clearTimeout(shortcutRecorder.resetTimer)
    shortcutRecorder.resetTimer = null
  }
  shortcutRecorder.hint = ''
}
async function startRecording() {
  console.log('[快捷键录入] startRecording 开始, suspendShortcuts =', typeof window.api?.suspendShortcuts)
  shortcutRecorder.recording = true
  shortcutRecorder.candidate = ''
  resetStepState()
  // 先挂起已注册的全局快捷键：否则按下的组合若与已注册快捷键相同，
  // 会被主进程 globalShortcut 在系统层拦截，渲染进程收不到 keydown（第二个键录不上的根因）
  if (window.api && window.api.suspendShortcuts) {
    try {
      const rr = await window.api.suspendShortcuts()
      console.log('[快捷键录入] 已挂起全局快捷键', JSON.stringify(rr))
    } catch (e) {
      console.log('[快捷键录入] 挂起失败', String(e))
    }
  }
  // 用原生 keydown 监听器（Naive UI 内部拦截可能影响组合键）
  if (shortcutRecorder.keydownHandler) {
    document.removeEventListener('keydown', shortcutRecorder.keydownHandler, true)
  }
  shortcutRecorder.keydownHandler = (e) => {
    // 忽略系统按键自动重复（长按/键盘重复率导致的重复 keydown）
    if (e.repeat) return
    console.log('[快捷键录入] keydown', e.code, e.key, 'ctrl=' + e.ctrlKey, 'shift=' + e.shiftKey, 'alt=' + e.altKey)
    e.preventDefault()
    e.stopPropagation()
    if (e.code === 'Escape') {
      stopRecording()
      return
    }
    const key = mainKeyFromEvent(e)
    if (!key) return
    // 本次按键自带的修饰键
    const mods = []
    if (e.ctrlKey) mods.push('Ctrl')
    if (e.shiftKey) mods.push('Shift')
    if (e.altKey) mods.push('Alt')
    if (e.metaKey) mods.push('Super')
    const combo = [...mods, key].join('+')
    if (combo === shortcutRecorder.candidate) {
      // 第二次按下相同组合：确认并保存
      console.log('[快捷键录入] 二次确认成功:', combo)
      const acc = combo
      stopRecording()
      emit('shortcut-change', shortcutRecorder.action, acc)
      shortcutRecorder.current = acc
      message.success(`快捷键已保存：${formatShortcut(acc)}`)
      shortcutRecorder.show = false
      return
    }
    // 第一次按下（或换了组合）：记为候选，等待再次按下相同组合
    shortcutRecorder.candidate = combo
    console.log('[快捷键录入] 已捕获候选:', combo)
    shortcutRecorder.hint = `已捕获 ${formatShortcut(combo)}，请再次按下相同按键以确认`
    armStepTimeout()
  }
  document.addEventListener('keydown', shortcutRecorder.keydownHandler, true)
}
function stopRecording() {
  shortcutRecorder.recording = false
  resetStepState()
  if (shortcutRecorder.keydownHandler) {
    document.removeEventListener('keydown', shortcutRecorder.keydownHandler, true)
    shortcutRecorder.keydownHandler = null
  }
  // 恢复已注册的全局快捷键
  if (window.api && window.api.resumeShortcuts) {
    window.api.resumeShortcuts().catch(() => {})
  }
}
function clearShortcut() {
  stopRecording()
  shortcutRecorder.candidate = ''
  // 通知父组件清空
  emit('shortcut-change', shortcutRecorder.action, '')
  shortcutRecorder.current = ''
  message.success('快捷键已清空')
  shortcutRecorder.show = false
}
function confirmShortcut() {
  const acc = shortcutRecorder.candidate
  if (!acc) return
  emit('shortcut-change', shortcutRecorder.action, acc)
  // 立即更新弹窗内显示（设置行显示由父组件 settings 流回）
  shortcutRecorder.current = acc
  message.success(`快捷键已保存：${formatShortcut(acc)}`)
  shortcutRecorder.show = false
}
// 关闭弹窗时停止录入
watch(() => shortcutRecorder.show, (v) => {
  if (!v) stopRecording()
})

// 拟态模式：选择文件
async function selectMimicFile() {
  if (!window.api || !window.api.selectMimicFile) {
    message.warning('当前版本不支持拟态文件选择')
    return
  }
  const r = await window.api.selectMimicFile()
  if (r && r.ok) {
    update('mimic_file_path', r.path)
  }
}
// 拟态模式：立即进入
function enterMimicMode() {
  if (!window.api || !window.api.enterMimicMode) {
    message.warning('当前版本不支持拟态模式')
    return
  }
  const filePath = props.settings.mimic_file_path || ''
  window.api.enterMimicMode(filePath || undefined)
}

// 站点显示名
const siteNames = { bunkr: 'Bunkr', coomerst: 'Coomer', coomerfans: 'CoomerFans', fapello: 'Fapello', leakedzone: 'Leakedzone', coomer: 'Coomer', pawchive: 'Pawchive', exhentai: 'EX', twitter: 'X', iwara: 'Iwara', hanime: 'H站', oreno3d: 'O3D', erommdtube: 'E站', asmr: 'ASMR', xhamster: 'xHamster', pornhub: 'Pornhub', xvideos: 'XVideos', javdb: 'JavDB' }
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

// 表世界专属保存位置：只写 surface_save_path，不碰 custom_path，
// 因此里世界与各站点下载路径完全不受影响
async function selectSurfaceFolder() {
  const folder = await window.api.selectFolder()
  if (folder) {
    update('surface_save_path', folder)
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
.follow-tag-clickable { cursor: pointer; }
.follow-tag-clickable:hover { color: #63e2b7; }
.follow-tag-count { color: #8a8d99; font-size: 11px; }
.follow-tag-members { margin-top: 4px; display: flex; flex-direction: column; gap: 2px; }
.follow-tag-member {
  display: flex; align-items: center; gap: 6px;
  padding: 3px 4px; border-radius: 6px; cursor: pointer;
}
.follow-tag-member:hover { background: rgba(99, 226, 183, 0.08); }
.follow-tag-avatar {
  width: 26px; height: 26px; border-radius: 50%;
  object-fit: cover; flex-shrink: 0;
  background: #2d2d33; color: #8a8d99;
  font-size: 12px; font-weight: 700; line-height: 26px; text-align: center;
}
.follow-tag-avatar-ph { display: inline-block; }
.follow-tag-member-info { flex: 1; min-width: 0; }
.follow-tag-member-name {
  font-size: 12px; color: #d0d0d6;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.follow-tag-member-sub {
  font-size: 10px; color: #8a8d99;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.follow-tag-member-go { font-size: 10px; color: #63e2b7; flex-shrink: 0; }

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

.login-hint-warn {
  font-size: 11px;
  color: #d4a017;
  background: rgba(212, 160, 23, 0.08);
  border: 1px solid rgba(212, 160, 23, 0.25);
  border-radius: 4px;
  padding: 5px 8px;
  text-align: center;
}

/* 谷歌邮箱多账号列表（设置区） */
.google-account-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}
.google-account-item {
  border: 1px solid #3a3a42;
  border-radius: 6px;
  padding: 6px 8px;
  background: rgba(255, 255, 255, 0.02);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.google-account-item.active {
  border-color: #3e8f4e;
  background: rgba(62, 143, 78, 0.06);
}
.google-account-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  cursor: pointer;
  min-height: 20px;
}
.google-account-email {
  font-size: 12px;
  font-weight: 600;
  color: #e0e0e6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.google-account-pass {
  font-size: 11px;
  color: #9f9f9f;
  user-select: text;
}
.google-account-actions {
  display: flex;
  gap: 6px;
  margin-top: 2px;
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
  justify-content: flex-start;  /* 手动抓取（第二行）与下载按钮（第一行首列）垂直对齐 */
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

/* BT 下载圆钮：emoji 图标（与 n-icon 20px 观感对齐） */
.bt-btn-emoji {
  font-size: 19px;
  line-height: 1;
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

/* 设置大屏模式：覆盖主内容区（与"下载管理"视图同级观感，替代左列窄条）。
   左面板定宽 340px；底部 212px 留给下载进度条。 */
.settings-section.settings-full {
  position: fixed;
  left: 340px;
  top: 0;
  right: 0;
  bottom: 212px;
  z-index: 200;
  background: #1e1e22;
  border-left: 1px solid #2d2d33;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

html.light-mode .settings-section.settings-full {
  background: #f7f7fa;
  border-left-color: #e0e0e6;
}

.settings-full-scroll {
  flex: 1;
  min-height: 0;
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

/* 有道翻译面板 */
.translate-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.translate-arrow {
  color: #63e2b7;
  font-size: 16px;
}
.translate-actions {
  display: flex;
  gap: 6px;
  margin: 8px 0 10px;
}
.translate-result-tip {
  font-size: 12px;
  color: #8b8b93;
  padding: 10px 4px;
  text-align: center;
}
.translate-result-err {
  font-size: 12px;
  color: #e0503c;
  padding: 10px 8px;
  background: rgba(224, 80, 60, 0.08);
  border: 1px solid rgba(224, 80, 60, 0.25);
  border-radius: 6px;
  margin-bottom: 10px;
}
.translate-result-box {
  background: rgba(99, 226, 183, 0.06);
  border: 1px solid rgba(99, 226, 183, 0.2);
  border-radius: 6px;
  padding: 10px;
  margin-bottom: 10px;
}
.translate-result-text {
  font-size: 13px;
  line-height: 1.7;
  color: #e0e0e6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow: auto;
}
.translate-result-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 6px;
}
.translate-result-meta {
  display: flex;
  gap: 12px;
  margin-top: 4px;
  font-size: 11px;
  color: #8b8b93;
}
.translate-config {
  margin-top: 10px;
  border-top: 1px dashed rgba(255, 255, 255, 0.1);
  padding-top: 8px;
}
.translate-config summary {
  font-size: 11px;
  color: #8b8b93;
  cursor: pointer;
  user-select: none;
  padding: 4px 0;
}
.translate-config summary:hover {
  color: #63e2b7;
}
.translate-config-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}
.translate-config-hint {
  font-size: 11px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.45);
  margin-top: 4px;
}
.translate-config-hint a {
  color: #63e2b7;
}
html.light-mode .translate-result-text {
  color: #2a2a30;
}
html.light-mode .translate-config {
  border-top-color: rgba(0, 0, 0, 0.1);
}
html.light-mode .translate-config-hint {
  color: rgba(0, 0, 0, 0.5);
}
html.light-mode .translate-result-err {
  color: #c93b2c;
}

/* GitHub 更新检查面板 */
.github-update-tip {
  font-size: 12px;
  color: #8b8b93;
  padding: 10px 4px;
  text-align: center;
}
.github-update-err {
  font-size: 12px;
  color: #e0503c;
  padding: 10px 8px;
  background: rgba(224, 80, 60, 0.08);
  border: 1px solid rgba(224, 80, 60, 0.25);
  border-radius: 6px;
}
.github-update-box {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  padding: 10px;
  font-size: 12px;
  line-height: 1.7;
}
.github-update-new {
  color: #f0a020;
  font-weight: 600;
  margin-bottom: 6px;
}
.github-update-none {
  color: #63e2b7;
  font-weight: 600;
  margin-bottom: 6px;
}
.github-update-first {
  color: #63e2b7;
  margin-bottom: 6px;
}
.github-update-row {
  display: flex;
  gap: 6px;
  margin: 2px 0;
  word-break: break-word;
}
.github-label {
  color: #8b8b93;
  flex-shrink: 0;
  min-width: 60px;
}
.github-msg {
  color: #e0e0e6;
  white-space: pre-wrap;
}
.github-sha {
  font-family: 'Cascadia Code', Consolas, monospace;
  color: #63e2b7;
}
.github-release-box {
  margin-top: 8px;
  padding: 8px;
  background: rgba(99, 226, 183, 0.06);
  border: 1px solid rgba(99, 226, 183, 0.2);
  border-radius: 4px;
}
.github-release-title {
  font-weight: 600;
  color: #63e2b7;
}
.github-release-meta {
  font-size: 11px;
  color: #8b8b93;
  margin: 2px 0 4px;
}
.github-release-body {
  font-size: 11px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.7);
  white-space: pre-wrap;
  max-height: 120px;
  overflow: auto;
}
.github-update-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}
/* 更新安装包下载（进度条 + 速度 + 立即安装） */
.update-dl-box {
  margin: 8px 0;
  padding: 8px;
  background: rgba(99, 226, 183, 0.06);
  border: 1px solid rgba(99, 226, 183, 0.2);
  border-radius: 4px;
}
.update-dl-title {
  font-weight: 600;
  color: #63e2b7;
  margin-bottom: 6px;
  word-break: break-all;
}
.update-dl-meta {
  margin-top: 4px;
  font-size: 11px;
  color: #8b8b93;
  font-family: 'Cascadia Code', Consolas, monospace;
}
html.light-mode .update-dl-box {
  background: rgba(24, 160, 88, 0.06);
  border-color: rgba(24, 160, 88, 0.2);
}
html.light-mode .update-dl-title {
  color: #18a058;
}
html.light-mode .update-dl-meta {
  color: #8a8d99;
}
html.light-mode .github-update-box {
  background: rgba(0, 0, 0, 0.03);
  border-color: rgba(0, 0, 0, 0.1);
}
html.light-mode .github-msg {
  color: #2a2a30;
}
html.light-mode .github-label {
  color: #5a5c66;
}
html.light-mode .github-release-body {
  color: rgba(0, 0, 0, 0.65);
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

/* P3 设置功能：快捷键行 + 录入弹窗 */
.shortcut-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 8px;
  margin: 6px 0;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.03);
  gap: 8px;
}
.shortcut-row:hover {
  background: rgba(99, 226, 183, 0.05);
}
.shortcut-label {
  font-size: 12px;
  color: #d0d0d6;
  flex: 1;
}
.shortcut-current {
  font-size: 11px;
  color: #8b8b93;
  font-family: 'Consolas', 'Monaco', monospace;
  min-width: 80px;
  text-align: right;
}
.shortcut-recorder {
  text-align: center;
}
.shortcut-recorder-action {
  font-size: 14px;
  font-weight: 600;
  color: #e0e0e6;
  margin-bottom: 8px;
}
.shortcut-recorder-current {
  font-size: 12px;
  color: #8b8b93;
  margin-bottom: 16px;
}
.shortcut-current-big {
  font-family: 'Consolas', 'Monaco', monospace;
  color: #63e2b7;
}
.shortcut-recorder-status {
  font-size: 13px;
  color: #d0d0d6;
  padding: 20px 8px;
  margin-bottom: 16px;
  border: 1px dashed rgba(255, 255, 255, 0.15);
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.2);
}
.shortcut-recorder-status.recording {
  border-color: #63e2b7;
  background: rgba(99, 226, 183, 0.06);
  color: #63e2b7;
}
.shortcut-recorder-actions {
  display: flex;
  gap: 8px;
  justify-content: center;
  margin-bottom: 12px;
}
.shortcut-recorder-hint {
  font-size: 11px;
  color: #7f7f7f;
  line-height: 1.6;
  margin-top: 8px;
}
html.light-mode .shortcut-row {
  background: rgba(0, 0, 0, 0.03);
}
html.light-mode .shortcut-row:hover {
  background: rgba(99, 226, 183, 0.08);
}
html.light-mode .shortcut-label {
  color: #1d1d1f;
}
html.light-mode .shortcut-current {
  color: #6e6e73;
}
html.light-mode .shortcut-recorder-action {
  color: #1d1d1f;
}
html.light-mode .shortcut-recorder-current {
  color: #6e6e73;
}
html.light-mode .shortcut-recorder-status {
  color: #1d1d1f;
  border-color: rgba(0, 0, 0, 0.15);
  background: rgba(0, 0, 0, 0.03);
}
html.light-mode .shortcut-recorder-hint {
  color: #6e6e73;
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
