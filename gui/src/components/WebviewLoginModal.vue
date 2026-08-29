<template>
  <!-- 通用 webview OAuth 登录弹窗：嵌入 webview 完成 OAuth 授权 + 机器验证 + 抓取目标站 cookie -->
  <n-modal
    v-model:show="visible"
    preset="card"
    :title="title"
    style="width: 90%; max-width: 1100px"
    :mask-closable="false"
    @after-leave="onClose"
  >
    <!-- 工具栏 -->
    <div class="wv-toolbar">
      <n-button-group size="small">
        <n-button quaternary @click="nav('back')" :disabled="!canBack" title="后退">←</n-button>
        <n-button quaternary @click="nav('forward')" :disabled="!canForward" title="前进">→</n-button>
        <n-button quaternary @click="nav('reload')" title="刷新">↻</n-button>
        <n-button quaternary @click="nav('home')" title="主页">🏠</n-button>
      </n-button-group>
      <n-input
        v-model:value="address"
        size="small"
        placeholder="https://..."
        class="wv-address"
        @keyup.enter="navigateToAddress"
      >
        <template #prefix>
          <span style="font-size: 12px; color: #63e2b7">{{ loading ? '⏳' : '🔒' }}</span>
        </template>
      </n-input>
      <n-button
        v-if="!manualConfirm"
        size="small"
        type="primary"
        :loading="grabbing"
        :disabled="!canGrab"
        @click="grabCookies"
        title="手动抓取当前会话的 cookie（用于登录成功后未自动触发的情况）"
      >完成抓取</n-button>
      <n-button size="small" quaternary @click="visible = false" title="取消登录">取消</n-button>
    </div>

    <!-- 状态提示 -->
    <div class="wv-status">
      <n-tag v-if="status === 'idle'" size="small" type="default" round>等待开始登录</n-tag>
      <n-tag v-else-if="status === 'loading'" size="small" type="info" round>加载中...</n-tag>
      <n-tag v-else-if="status === 'oauth'" size="small" type="info" round>OAuth 授权中（X 站 cookie 自动登录）</n-tag>
      <n-tag v-else-if="status === 'captcha'" size="small" type="warning" round>⚠ 人机验证，请在下方完成</n-tag>
      <n-tag v-else-if="status === 'success'" size="small" type="success" round>✓ 登录成功，已抓取 cookie</n-tag>
      <n-tag v-else-if="status === 'failed'" size="small" type="error" round>✗ {{ errorMsg }}</n-tag>
    </div>

    <!-- webview 浏览器（partition 共享 persist:twitter，OAuth 跳转 x.com 自动带 X 站 cookie） -->
    <webview
      ref="wvRef"
      :src="currentUrl"
      :partition="partition"
      class="login-webview"
      @did-navigate="onNav"
      @did-navigate-in-page="onNav"
      @did-start-loading="loading = true; status = 'loading'"
      @did-stop-loading="loading = false; onStop()"
    />

    <!-- 手动确认模式（EX 站）：底部提示 + 取消/确认按钮，用户确认后抓取 cookie -->
    <div v-if="manualConfirm" class="wv-confirm-bar">
      <span class="wv-confirm-hint">请登录，如果已登录请点击确认。</span>
      <span class="wv-confirm-btns">
        <n-button size="small" quaternary @click="visible = false">取消</n-button>
        <n-button size="small" type="primary" :loading="grabbing" @click="grabCookies()">确认</n-button>
      </span>
    </div>
  </n-modal>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const props = defineProps({
  // 是否显示
  show: { type: Boolean, default: false },
  // 站点 key（xhamster/pornhub/xvideos）
  site: { type: String, required: true },
  // 弹窗标题
  title: { type: String, default: 'webview 登录' },
  // 登录页 URL（OAuth 起点）
  loginUrl: { type: String, required: true },
  // 主页 URL（点🏠回到此页）
  homeUrl: { type: String, default: '' },
  // webview 会话 partition（共享 persist:twitter 让 X 站 OAuth 自动带 cookie）
  partition: { type: String, default: 'persist:twitter' },
  // 登录成功的 URL 匹配模式（RegExp 数组，命中任一即视为登录回跳）
  successPatterns: { type: Array, default: () => [] },
  // captcha/机器验证 URL 匹配模式（RegExp 数组，命中即弹提示让用户手动通过）
  captchaPatterns: { type: Array, default: () => [] },
  // 登录账号预填（{ email, password }）：加载登录页后自动填入表单（javdb/xvideos 邮箱密码登录）
  credentials: { type: Object, default: null },
  // 手动确认模式（EX 站）：不自动检测登录成功，底部显示提示 + 取消/确认按钮，
  // 用户点"确认"后才抓取 cookie（e-hentai 论坛登录成功后 URL 不确定，自动检测不可靠）
  manualConfirm: { type: Boolean, default: false },
})

const emit = defineEmits(['update:show', 'login-success', 'login-failed', 'close'])

const visible = ref(props.show)
const address = ref('')
const currentUrl = ref('')
const loading = ref(false)
const grabbing = ref(false)
const status = ref('idle')
const errorMsg = ref('')
const canBack = ref(false)
const canForward = ref(false)
const wvRef = ref(null)

const canGrab = computed(() => status.value !== 'success' && !grabbing.value)

// 同步外部 show 变化
watch(() => props.show, (v) => {
  visible.value = v
  if (v) startLogin()
})
watch(visible, (v) => emit('update:show', v))

// 启动登录：加载登录页
function startLogin() {
  status.value = 'loading'
  errorMsg.value = ''
  address.value = props.loginUrl
  currentUrl.value = props.loginUrl
}

// 导航事件：检测 captcha + 登录成功
async function onNav(e) {
  const url = e.url || address.value || ''
  address.value = url
  // 更新后退/前进可用状态
  await nextTick()
  const wv = wvRef.value
  if (wv) {
    try {
      canBack.value = await wv.canGoBack()
      canForward.value = await wv.canGoForward()
    } catch (err) { /* webview 未就绪 */ }
  }
  if (!url) return
  // 1. 检测 captcha/机器验证页
  if (props.captchaPatterns.some(re => re.test(url))) {
    status.value = 'captcha'
    return
  }
  // 2. 检测登录成功（URL 在站点域 + 满足成功模式）；手动确认模式跳过（用户点"确认"才抓）
  if (!props.manualConfirm && props.successPatterns.some(re => re.test(url))) {
    // 等页面渲染稳定后抓 cookie（避免 cookie 还没 set 就抓）
    setTimeout(() => grabCookies(true), 800)
  }
  // 3. 检测 OAuth 跳转到 x.com / accounts.google.com（共享凭据自动授权中；目标站自身登录时不提示）
  if (props.site !== 'twitter' && /twitter\.com|x\.com/i.test(url)) {
    status.value = 'oauth'
  }
  if (props.site !== 'google' && /accounts\.google\.com/i.test(url)) {
    status.value = 'oauth'
  }
}

function onStop() {
  if (status.value === 'loading') status.value = 'idle'
  // 登录页加载完成：自动预填账号密码（用户只需完成人机验证并点登录）
  prefillCredentials()
}

// 自动预填登录表单（javdb：#session_email / #session_password；其他站按 name/id 候选匹配）
async function prefillCredentials() {
  const creds = props.credentials
  const wv = wvRef.value
  if (!creds || !creds.email || !wv) return
  try {
    const js = `
      (() => {
        const setVal = (input, v) => {
          if (!input || input.value) return false
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
          setter.call(input, v)
          input.dispatchEvent(new Event('input', { bubbles: true }))
          input.dispatchEvent(new Event('change', { bubbles: true }))
          return true
        }
        const candidates = {
          email: ['input#identifierId', 'input#session_email', 'input[name="session[email]"]', 'input[type="email"]', 'input[name="email"]', 'input[name="user[email]"]', 'input[name="username"]'],
          password: ['input[name="Passwd"]', 'input#session_password', 'input[name="session[password]"]', 'input[type="password"]', 'input[name="password"]', 'input[name="user[password]"]'],
        }
        let filled = 0
        for (const sel of candidates.email) { if (setVal(document.querySelector(sel), ${JSON.stringify(creds.email)})) { filled++; break } }
        for (const sel of candidates.password) { if (setVal(document.querySelector(sel), ${JSON.stringify(creds.password || '')})) { filled++; break } }
        return filled
      })()
    `
    await wv.executeJavaScript(js, true)
  } catch (err) { /* 页面未就绪或跨域，忽略 */ }
}

// 手动抓取 cookie（用户点"完成抓取"或自动触发）
async function grabCookies(auto = false) {
  grabbing.value = true
  try {
    const res = await window.api.siteGetCookies(props.site)
    if (!res.ok) {
      if (auto) return  // 自动触发时静默失败（用户可手动点）
      status.value = 'failed'
      errorMsg.value = res.error || '抓取 cookie 失败'
      emit('login-failed', res.error || '抓取 cookie 失败')
      return
    }
    if (res.hasAuth) {
      status.value = 'success'
      emit('login-success', { cookieStr: res.cookieStr, count: res.count, userAgent: res.userAgent || '' })
      setTimeout(() => { visible.value = false }, 800)
    } else {
      // cookie 数量不足，可能还没登录完成
      if (auto) return
      status.value = 'failed'
      errorMsg.value = `未检测到登录态（cookie 数量 ${res.count}，请先在 webview 中完成登录）`
      emit('login-failed', errorMsg.value)
    }
  } catch (err) {
    status.value = 'failed'
    errorMsg.value = err.message || String(err)
    emit('login-failed', errorMsg.value)
  } finally {
    grabbing.value = false
  }
}

// 导航控制
async function nav(action) {
  const wv = wvRef.value
  if (!wv) return
  try {
    if (action === 'back') await wv.goBack()
    else if (action === 'forward') await wv.goForward()
    else if (action === 'reload') await wv.reload()
    else if (action === 'home') {
      const home = props.homeUrl || props.loginUrl
      address.value = home
      currentUrl.value = home
    }
  } catch (err) { /* 忽略 */ }
}

function navigateToAddress() {
  if (!address.value) return
  currentUrl.value = address.value
}

function onClose() {
  emit('close')
  status.value = 'idle'
  errorMsg.value = ''
}
</script>

<style scoped>
.wv-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.wv-address {
  flex: 1;
}
.wv-status {
  margin-bottom: 8px;
  min-height: 24px;
}
.login-webview {
  width: 100%;
  height: 560px;
  border: 1px solid #2d2d33;
  border-radius: 4px;
  background: #fff;
}
html.light-mode .login-webview {
  border-color: #e0e0e6;
}
/* 手动确认模式底部栏（EX 站）：提示 + 取消/确认按钮 */
.wv-confirm-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px solid #63e2b7;
  border-radius: 4px;
  background: rgba(99, 226, 183, 0.08);
}
.wv-confirm-hint {
  font-size: 13px;
  color: #63e2b7;
}
.wv-confirm-btns {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
</style>
