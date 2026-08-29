const { contextBridge, ipcRenderer } = require('electron')

// 事件缓冲：在渲染进程注册回调前，先缓存收到的事件
const eventBuffer = []
let eventCallback = null

// 立即开始监听，避免错过早期事件（如 ready）
ipcRenderer.on('python-event', (event, data) => {
  if (eventCallback) {
    eventCallback(data)
  } else {
    eventBuffer.push(data)
  }
})

// 通过 contextBridge 安全地暴露 API 给渲染进程
contextBridge.exposeInMainWorld('api', {
  // 发送命令到 Python 后端
  // 注意：Vue 的 reactive/ref 是 Proxy 对象，无法被 IPC 结构化克隆。
  // 先 JSON 序列化再反序列化，得到纯对象后再发送。
  sendCommand: (command) => {
    const plainCommand = JSON.parse(JSON.stringify(command))
    ipcRenderer.send('python-command', plainCommand)
  },

  // 监听 Python 后端事件（注册时自动回放缓存的事件）
  onEvent: (callback) => {
    eventCallback = callback
    // 回放缓冲的事件
    while (eventBuffer.length > 0) {
      callback(eventBuffer.shift())
    }
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

  // 用系统默认程序打开外部链接（磁力链接 -> 下载器/浏览器）
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  // 用指定浏览器打开网站（'chrome' | 'edge' | 'firefox' | ''=系统默认）
  openWithBrowser: (url, browser) => ipcRenderer.invoke('open-with-browser', url, browser),

  // 获取应用版本号（package.json version，用于更新检查对比）
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),

  // P3 设置功能：托盘 / 全局快捷键 / 不息屏 / 拟态模式
  // 不息屏：开启/关闭 prevent-display-sleep
  preventSleepStart: () => ipcRenderer.invoke('prevent-sleep-start'),
  preventSleepStop: () => ipcRenderer.invoke('prevent-sleep-stop'),
  // 全局快捷键注册：action ∈ toggle_prevent_sleep | quick_minimize | toggle_mimic | toggle_float
  registerShortcut: (action, accelerator) => ipcRenderer.invoke('register-shortcut', action, accelerator),
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

  // 查询后端启动错误（页面加载完成时主动拉取，避免错过启动早期的事件）
  getBackendError: () => ipcRenderer.invoke('get-backend-error'),

  // 识图（反向图片搜索）：拖拽的 File 对象 → 真实文件路径
  // （Electron 30 移除了 File.path，必须用 webUtils.getPathForFile）
  getPathForFile: (file) => {
    const { webUtils } = require('electron')
    return webUtils.getPathForFile(file)
  },
})
