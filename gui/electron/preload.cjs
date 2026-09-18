const { contextBridge, ipcRenderer } = require('electron')

// 事件监听：多订阅（App.vue 的 handlePythonEvent 与 ModernHome/SnifferInner 都要收；
// 原单回调槽"后注册覆盖"在 ModernHome 改异步加载后注册顺序反转，会把主事件链顶掉——
// 2026-09-17 f4/f5b 联调实锤：渲染进程收不到任何后端事件。改为 Set 多播 + 单监听异常隔离）
const eventListeners = new Set()
const eventBuffer = []

// 立即开始监听，避免错过早期事件（如 ready）
ipcRenderer.on('python-event', (event, data) => {
  if (eventListeners.size > 0) {
    for (const fn of eventListeners) {
      try { fn(data) } catch (e) { console.error('[preload] 事件处理器异常:', e) }
    }
  } else {
    eventBuffer.push(data)
  }
})

// 通过 contextBridge 安全地暴露 API 给渲染进程
contextBridge.exposeInMainWorld('api', {
  // 启动界面模式：主进程从 settings.json 同步读出，随 additionalArguments 传入。
  // 渲染层在首帧就能拿到正确模式（true=美好世界 / false=里世界 / null=未知）。
  uiModeHotAtBoot: (() => {
    try {
      const arg = process.argv.find((s) => s.startsWith('--xxd-ui-mode-hot='))
      return arg ? arg.slice('--xxd-ui-mode-hot='.length) === '1' : null
    } catch (e) { return null }
  })(),

  // 发送命令到 Python 后端
  // 注意：Vue 的 reactive/ref 是 Proxy 对象，无法被 IPC 结构化克隆。
  // 先 JSON 序列化再反序列化，得到纯对象后再发送。
  sendCommand: (command) => {
    const plainCommand = JSON.parse(JSON.stringify(command))
    ipcRenderer.send('python-command', plainCommand)
  },

  // 监听 Python 后端事件（多订阅：返回退订函数；首个监听者自动回放缓存的事件）
  onEvent: (callback) => {
    eventListeners.add(callback)
    // 回放缓冲的事件（仅首个注册者排空，避免多订阅下重复投递）
    if (eventListeners.size === 1) {
      while (eventBuffer.length > 0) {
        try { callback(eventBuffer.shift()) } catch (e) { console.error('[preload] 回放事件异常:', e) }
      }
    }
    return () => eventListeners.delete(callback)
  },

  // 选择文件夹
  selectFolder: () => ipcRenderer.invoke('select-folder'),

  // 打开文件（系统默认程序）
  openPath: (filePath) => ipcRenderer.invoke('open-path', filePath),

  // 在文件管理器中定位文件
  showInFolder: (filePath) => ipcRenderer.invoke('show-in-folder', filePath),

  // 获取文件的系统图标（dataURL）
  getFileIcon: (filename) => ipcRenderer.invoke('get-file-icon', filename),

  // 更新下载悬浮窗显示（总速度/进度）
  updateFloat: (data) => {
    ipcRenderer.send('float-update', data)
  },

  // 显示/隐藏悬浮窗
  setFloatVisible: (visible) => {
    ipcRenderer.send('float-set-visible', visible)
  },

  // 监听悬浮窗被关闭
  onFloatClosed: (callback) => {
    ipcRenderer.on('float-closed', () => callback())
  },

  // 监听 webview 弹窗拦截（登录弹窗内网页 window.open 的新窗口 URL，
  // 由 WebviewLoginModal 显示为模态内第二层；主进程 setWindowOpenHandler 统一 deny）
  onWebviewPopup: (callback) => {
    ipcRenderer.on('webview-popup-open', (_e, data) => callback(data))
  },

  // 手动抓取（资源嗅探）：打开独立嗅探窗口（内置浏览器 + webRequest 媒体捕获）
  snifferOpen: () => ipcRenderer.send('sniffer-open'),
  // BT 下载：打开独立 BT 窗口（磁力链接批量粘贴 + .torrent 拖拽）
  btOpen: () => ipcRenderer.send('bt-open'),
  // 热门平台主界面（ModernHome）：挂载 persist:hotplatform 会话的媒体捕获
  hotCaptureAttach: () => ipcRenderer.send('hot-capture-attach'),
  // 重启应用（还原嗅探网络→杀后端→relaunch；界面模式随设置持久化恢复）
  restartApp: () => ipcRenderer.invoke('app-restart'),
  // 选择目录（移动文件夹用）
  pickDirectory: () => ipcRenderer.invoke('pick-directory'),
  // 在文件管理器中打开任意路径
  openPath: (p) => ipcRenderer.invoke('open-path', p),
  // 内置可视化帮助页（软件说明 / 更新说明）：独立窗口打开
  openHelpWindow: (file) => ipcRenderer.invoke('open-help-window', file),
  // 里/表世界自定义标题栏：窗口控制（minimize/maximize/close）
  winControl: (action) => ipcRenderer.send('win-control', action),
  // 最大化状态变化（渲染层切圆角贴边样式）；返回退订函数
  onWinMaxState: (callback) => {
    const listener = (_e, maxed) => callback(maxed)
    ipcRenderer.on('win-max-state', listener)
    return () => ipcRenderer.removeListener('win-max-state', listener)
  },
  // 热门平台 webview 的 _blank 弹窗：改为当前 webview 内导航
  onHotPopupNavigate: (callback) => {
    const listener = (_e, data) => callback(data)
    ipcRenderer.on('hot-popup-navigate', listener)
    return () => ipcRenderer.removeListener('hot-popup-navigate', listener)
  },
  // 嗅探窗口：接收实时捕获的媒体资源（主进程 webRequest.onCompleted 转发；返回退订函数）
  onSnifferResource: (callback) => {
    const listener = (_e, data) => callback(data)
    ipcRenderer.on('sniffer-resource', listener)
    return () => ipcRenderer.removeListener('sniffer-resource', listener)
  },
  // 磁力链接点击（磁力站页面 magnet: 协议拦截，两个世界都会收到；返回退订函数）
  onBtMagnetClick: (callback) => {
    const listener = (_e, data) => callback(data)
    ipcRenderer.on('bt-magnet-click', listener)
    return () => ipcRenderer.removeListener('bt-magnet-click', listener)
  },

  // Leakedzone：系统 Edge 过盾登录（真实浏览器引擎过 Turnstile，CDP 抓 Cookie+UA）
  leakEdgeLogin: () => ipcRenderer.send('leak-edge-login'),
  leakEdgeHarvest: () => ipcRenderer.send('leak-edge-harvest'),
  onLeakEdgeState: (callback) => {
    ipcRenderer.on('leak-edge-state', (_e, data) => callback(data))
  },

  // 打开独立下载管理器窗口
  showDownloadsWindow: () => {
    ipcRenderer.send('dl-show')
  },

  // 监听下载管理窗口请求：在主窗口打开详细下载内容
  onOpenDownloadDetail: (callback) => {
    ipcRenderer.on('open-download-detail', (event, taskId) => callback(taskId))
  },

  // ============================
  // ExHentai webview 浏览器视图
  // ============================
  // 读取 ExHentai webview 会话中的 cookie（同步给 Python 后端用）
  exGetCookies: () => ipcRenderer.invoke('ex-get-cookies'),

  // 更新 ExHentai webview 会话的代理设置
  exSetProxy: (proxyRules) => ipcRenderer.invoke('ex-set-proxy', proxyRules),

  // ============================
  // 通用 webview OAuth 站点（xhamster/pornhub/xvideos 等）
  // ============================
  // 抓取目标站 webview 会话的 cookie（OAuth 登录成功后调用，返回给后端持久化）
  siteGetCookies: (site) => ipcRenderer.invoke('site-get-cookies', site),

  // 设置目标站 webview 会话代理
  siteSetProxy: (site, proxyRules) => ipcRenderer.invoke('site-set-proxy', site, proxyRules),

  // 跨站凭据注入：把谷歌邮箱/X 的 cookie 复制进目标站会话（OAuth 授权跳转自动带凭据）
  syncSharedCookies: (site) => ipcRenderer.invoke('sync-shared-cookies', site),

  // 向目标站 webview 会话注入 cookie（切换账号/恢复登录态时把后端存的 cookie 灌进 webview）
  siteSetCookies: (site, cookieStr) => ipcRenderer.invoke('site-set-cookies', site, cookieStr),
  siteClearCookies: (site) => ipcRenderer.invoke('site-clear-cookies', site),

  // 用系统默认程序打开外部链接（磁力链接 -> 下载器/浏览器）
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  // 用指定浏览器打开网站（'chrome' | 'edge' | 'firefox' | ''=系统默认）
  openWithBrowser: (url, browser) => ipcRenderer.invoke('open-with-browser', url, browser),
  // 主进程剪贴板写入（识图结果等复制链路；navigator.clipboard 在 Electron 下不可靠）
  copyText: (text) => ipcRenderer.invoke('copy-text', text),

  // 获取应用版本号（package.json version，用于更新检查对比）
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),

  // P3 设置功能：托盘 / 全局快捷键 / 拟态模式
  // 全局快捷键注册：action ∈ quick_minimize | toggle_mimic | toggle_float
  registerShortcut: (action, accelerator) => ipcRenderer.invoke('register-shortcut', action, accelerator),
  // 快捷键录入保护：录入期间暂停全局快捷键、结束后恢复
  suspendShortcuts: () => ipcRenderer.invoke('suspend-shortcuts'),
  resumeShortcuts: () => ipcRenderer.invoke('resume-shortcuts'),
  // 快速缩小到托盘（按钮触发）
  quickMinimize: () => ipcRenderer.invoke('quick-minimize'),
  // 进入拟态模式（按钮触发，可选传文件路径）
  enterMimicMode: (filePath) => ipcRenderer.invoke('enter-mimic-mode', filePath),
  // 选择拟态文件（系统文件对话框）
  selectMimicFile: () => ipcRenderer.invoke('select-mimic-file'),
  // 监听快捷键触发事件（main → renderer）
  onShortcutTriggered: (cb) => {
    const listener = (_, data) => cb(data)
    ipcRenderer.on('shortcut-triggered', listener)
    return () => ipcRenderer.removeListener('shortcut-triggered', listener)
  },
  // 监听关闭行为变更（关闭弹窗勾选"记住我的选择" → 同步前端设置面板与后端缓存）
  onCloseActionChanged: (cb) => {
    const listener = (_, action) => cb(action)
    ipcRenderer.on('close-action-changed', listener)
    return () => ipcRenderer.removeListener('close-action-changed', listener)
  },

  // 查询后端启动错误（页面加载完成时主动拉取，避免错过启动早期的事件）
  getBackendError: () => ipcRenderer.invoke('get-backend-error'),

  // 识图（反向图片搜索）：拖拽的 File 对象 → 真实文件路径
  // （Electron 30 移除了 File.path，必须用 webUtils.getPathForFile）
  getPathForFile: (file) => {
    const { webUtils } = require('electron')
    return webUtils.getPathForFile(file)
  },
})
