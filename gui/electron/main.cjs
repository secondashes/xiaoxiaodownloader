const { app, BrowserWindow, ipcMain, protocol, shell, Menu, session, Tray, globalShortcut, nativeImage, dialog } = require('electron')
const { spawn, spawnSync, execSync, execFileSync } = require('child_process')
const path = require('path')
const fs = require('fs')

// 应用版本号（package.json）：主窗口标题显示"小小下载器 vX.Y.Z"
const APP_VERSION = require('../package.json').version || ''
const APP_TITLE = APP_VERSION ? `小小下载器 v${APP_VERSION}` : '小小下载器'

// 在 app ready 之前设置命令行参数
app.commandLine.appendSwitch('no-sandbox')
app.commandLine.appendSwitch('disable-gpu')
app.commandLine.appendSwitch('disable-software-rasterizer')
app.disableHardwareAcceleration()

// ============================
// 便携版定位（单文件自解压 → 文件夹程序）
// ============================
// 单文件版（electron-builder portable）双击后先解压到临时目录运行（__dirname 在临时目录）。
// 首次运行把完整程序释放到单文件旁边的“小小下载器”文件夹并移除单文件（= exe 移入文件夹）；
// 之后程序与全部数据都在该文件夹内。释放失败则退回旧便携逻辑（数据在单文件旁）。
const exeDir = path.dirname(process.execPath)   // 当前运行程序所在目录（单文件模式 = 临时解压目录）
const stubEnv = process.env.PORTABLE_EXECUTABLE_DIR || ''
const STUB_MARKER = 'xxd.app'                   // 文件夹程序标记（内容 = 版本号，用于升级时重新释放）
const RELEASE_DIR_NAME = '小小下载器'
const isStub = !!stubEnv                         // 单文件模式（从临时目录运行）
const isReleased = !isStub && fs.existsSync(path.join(exeDir, STUB_MARKER))  // 文件夹完整程序模式
const PORTABLE_MODE = isStub || isReleased

// 单实例锁（跳过单文件自解压引导模式：stub 会拉起正式程序后自行退出，抢锁会误杀正式程序）
// 防止双实例并行：两个实例同时运行时关掉一个、另一个还在托盘，用户看来就是"点了退出却缩到托盘"
if (!isStub && !app.requestSingleInstanceLock()) {
  // 已有实例在运行：本实例直接退出（已有实例会收到 second-instance 并把主窗口弹回前台）
  process.exit(0)
}

// 单文件所在目录（stubEnv）里已释放的文件夹程序；exe 已在名为“小小下载器”的文件夹里时不嵌套
function getReleaseDir() {
  if (fs.existsSync(path.join(stubEnv, STUB_MARKER))) return stubEnv  // 单文件被移进程序文件夹内运行
  if (path.basename(stubEnv).toLowerCase() === RELEASE_DIR_NAME) return stubEnv
  return path.join(stubEnv, RELEASE_DIR_NAME)
}

// 所有运行数据（后端 cwd / 缩略图 / 设置 / 日志 / Chromium 会话）的根目录
function getDataDir() {
  if (isReleased) return path.join(exeDir, 'data')
  if (isStub) return path.join(getReleaseDir(), 'data')
  return getProjectRoot()
}

// 加密账号库隐藏位置：Chromium 磁盘缓存目录内（伪装成缓存文件）
function getThemeCacheDir() {
  return path.join(getDataDir(), 'Cache', 'Cache_Data')
}

if (PORTABLE_MODE) {
  try { app.setPath('userData', getDataDir()) } catch (e) {}
  if (isReleased) {
    try { fs.mkdirSync(getThemeCacheDir(), { recursive: true }) } catch (e) {}
  }
}

// 注册自定义 thumb 协议（用于加载本地缓存的缩略图）
protocol.registerSchemesAsPrivileged([
  { scheme: 'thumb', privileges: { standard: true, secure: true, supportFetchAPI: true } },
])

// ExHentai webview 使用的独立会话（与主界面隔离，只走代理）
const EX_SESSION_PARTITION = 'persist:exhentai'

// 通用 webview 站点会话注册表（浏览器登录，登录后点"确认"抓取目标站 cookie）
// xhamster/pornhub 的 partition 共享 persist:twitter：弹窗内用 X 授权登录时自动带 x.com cookie
// domains 用于抓取目标站登录后的 cookie（不跨域注入 X cookie，仅共享会话）
const SITE_SESSIONS = {
  // X 站：弹窗内登录 x.com，抓取 .x.com 域的 auth_token / ct0（同 EX 站操作）
  twitter:  { partition: 'persist:twitter', domains: ['.x.com', '.twitter.com'], authNames: ['auth_token'] },
  xhamster: { partition: 'persist:twitter', domains: ['.xhamster.com', '.xhcdn.com'] },
  pornhub:  { partition: 'persist:twitter', domains: ['.pornhub.com', '.phncdn.com'] },
  xvideos:  { partition: 'persist:xvideos', domains: ['.xvideos.com', '.xvideos-cdn.com'] },
  // JavDB：独立会话（webview 内完成邮箱密码登录 + Cloudflare 人机验证，"记住装置"后 cookie 约 7 天有效）
  javdb:    { partition: 'persist:javdb', domains: ['.javdb.com', '.jdbstatic.com'] },
  // 谷歌邮箱：独立会话，登录后 cookie 是其他站 Google OAuth 授权的凭据源
  // （authNames：SID/HSID/SSID + SAPISID 同时存在才算已登录）
  google:   { partition: 'persist:google', domains: ['.google.com', '.accounts.google.com'], authNames: ['SID', 'SAPISID'] },
  // Oreno3D：无强制账号体系，登录环节仅保存站点会话 cookie（个人浏览状态）
  oreno3d:  { partition: 'persist:oreno3d', domains: ['.oreno3d.com'] },
  // EroMMDTube：与 Oreno3D 同架构（无账号体系），保存站点会话 cookie（Cloudflare 验证后免重复验证）
  erommdtube: { partition: 'persist:erommdtube', domains: ['.erommdtube.com'] },
  // Pixiv：独立会话（webview 内完成邮箱密码登录 + Cloudflare/人机验证），抓取 PHPSESSID
  pixiv:    { partition: 'persist:pixiv', domains: ['.pixiv.net', '.pximg.net'], authNames: ['PHPSESSID'] },
  // ExHentai：与右侧浏览器视图共用 persist:exhentai 会话（cookie 互通）；
  // 登录走 e-hentai 论坛账号（forums.e-hentai.org），登录后自动下发 exhentai.org 的 ipb cookie
  exhentai: { partition: 'persist:exhentai', domains: ['.e-hentai.org', '.exhentai.org'], authNames: ['ipb_member_id', 'ipb_pass_hash'] },
}

// 跨站共享凭据源（OAuth 授权注入用）：打开某站登录弹窗前，把这些域的 cookie
// 复制进目标站 partition，弹窗内点"使用 Google/X 登录"时自动带凭据跳转
const SHARED_COOKIE_SOURCES = [
  { partition: 'persist:google',  domains: ['.google.com', '.accounts.google.com'] },   // Google 授权
  { partition: 'persist:twitter', domains: ['.x.com', '.twitter.com'] },                // X 授权
]

let pythonProcess = null
let mainWindow = null
let floatWindow = null
let downloadsWindow = null
const isDev = !app.isPackaged

// P3 设置功能状态：托盘 / 全局快捷键 / 拟态窗口
let appTray = null                  // Tray 实例（仅在最小化到托盘时创建）
let isQuitting = false              // 正在退出（托盘"退出"/关闭对话框选"退出"时置真，跳过托盘拦截）
let mimicWindow = null              // 拟态窗口（伪装面板）
const shortcutMap = new Map()       // action → accelerator 字符串
// 快捷键防抖：同 action 300ms 内的重复触发只执行一次（系统/驱动偶尔一次按键派发两次事件）
const shortcutLastFired = new Map()
function fireShortcutOnce(action, fn) {
  const now = Date.now()
  const last = shortcutLastFired.get(action) || 0
  if (now - last < 300) return
  shortcutLastFired.set(action, now)
  try { fn() } catch (err) {
    debugLog(`快捷键动作执行失败 ${action}: ${err && err.message}`)
  }
}
const shortcutCallbacks = {
  quick_minimize: () => fireShortcutOnce('quick_minimize', quickMinimizeToTray),
  toggle_mimic: () => fireShortcutOnce('toggle_mimic', toggleMimicMode),
  toggle_float: () => {
    // 切换悬浮窗显示
    fireShortcutOnce('toggle_float', () => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('shortcut-triggered', { action: 'toggle_float' })
      }
    })
  },
}

// 悬浮窗与下载管理窗口的固定尺寸。硬编码并在移动时显式写回，
// 避免 Windows 上 frameless 透明窗口在频繁移动时因厚边框 inset 累积而“越拖越大”。
const FLOAT_SIZE = { width: 280, height: 140 }
const DOWNLOADS_SIZE = { width: 273, height: 364 }

// ============================
// 调试日志
// ============================
function getProjectRootSafe() {
  // 便携版：日志写入 data/logs（与后端日志同一目录，全部包裹在 data 内）
  if (PORTABLE_MODE) {
    return getDataDir()
  }
  return path.resolve(__dirname, '..', '..')
}

const logDir = path.join(getProjectRootSafe(), 'logs')
const debugLogPath = path.join(logDir, 'electron_debug.log')
// 日志上限：超过后轮转为 .old（最多保留一份旧档），防止日志无限膨胀
// （曾出现 20 分钟 189MB：tasks_snapshot 全量任务表每 0.5s 一条全部落盘）
const DEBUG_LOG_MAX_BYTES = 10 * 1024 * 1024
let debugLogBytes = -1  // -1 = 尚未统计（首次写入时 stat）

function debugLog(msg) {
  const ts = new Date().toISOString()
  // 单条截断：快照类事件一行可达数百 KB，只保留开头便于排查
  let text = String(msg)
  if (text.length > 600) text = text.slice(0, 600) + ` ...(截断, 原始 ${text.length} 字符)`
  const line = `[${ts}] ${text}\n`
  try {
    fs.mkdirSync(logDir, { recursive: true })
    if (debugLogBytes < 0) {
      try { debugLogBytes = fs.existsSync(debugLogPath) ? fs.statSync(debugLogPath).size : 0 } catch (e) { debugLogBytes = 0 }
    }
    if (debugLogBytes > DEBUG_LOG_MAX_BYTES) {
      try { fs.unlinkSync(debugLogPath + '.old') } catch (e) {}
      try { fs.renameSync(debugLogPath, debugLogPath + '.old') } catch (e) {}
      debugLogBytes = 0
    }
    fs.appendFileSync(debugLogPath, line, 'utf-8')
    debugLogBytes += line.length
  } catch (e) {
    // 忽略
  }
}

// 清空旧日志
try { fs.writeFileSync(debugLogPath, '', 'utf-8') } catch (e) {}

// ============================
// 延迟移除单文件：引导器（SFX）进程退出前其 exe 处于锁定状态，无法直接删，
// 用 PowerShell 后台重试删除（-EncodedCommand = base64 UTF-16LE，中文路径安全）
// ============================
function scheduleStubRemoval(stubFile, releasedExe) {
  try {
    if (!stubFile) return
    // 单文件已被完整 exe 原地覆盖（同路径）时不能删（会删掉程序本体）
    if (path.resolve(stubFile).toLowerCase() === path.resolve(releasedExe).toLowerCase()) return
    // 先试直接删（引导器可能已退出）；失败再靠后台 PowerShell 重试
    try { fs.unlinkSync(stubFile) } catch (e) {}
    const p = stubFile.replace(/'/g, "''")
    const ps = [
      `$f='${p}'`,
      `$t=0`,
      `while((Test-Path -LiteralPath $f) -and $t -lt 30){`,
      `  try{ Remove-Item -LiteralPath $f -Force -ErrorAction Stop }catch{}`,
      `  Start-Sleep -Seconds 1; $t++`,
      `}`,
    ].join('\n')
    const encoded = Buffer.from(ps, 'utf16le').toString('base64')
    const child = spawn('powershell', [
      '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-EncodedCommand', encoded,
    ], { detached: true, stdio: 'ignore', windowsHide: true })
    child.unref()
    debugLog(`已安排移除单文件: ${stubFile}`)
  } catch (e) {
    debugLog(`安排移除单文件失败(忽略): ${e.message}`)
  }
}

// ============================
// 单文件自解压引导（双击单文件 → 创建“小小下载器”文件夹 → exe 移入其中）
// ============================
if (isStub) {
  try {
    const appVersion = require('../package.json').version
    const releaseDir = getReleaseDir()
    const markerPath = path.join(releaseDir, STUB_MARKER)
    const releasedExe = path.join(releaseDir, `${RELEASE_DIR_NAME}.exe`)
    // 版本不同（分享了新版单文件）或文件夹程序缺失 → 重新释放覆盖（data/ 等数据不受影响）
    let needRelease = true
    try {
      if (fs.existsSync(markerPath) && fs.existsSync(releasedExe)
          && fs.readFileSync(markerPath, 'utf-8').trim() === appVersion) {
        needRelease = false
      }
    } catch (e) {}
    if (needRelease) {
      debugLog(`自解压: ${exeDir} -> ${releaseDir} ...`)
      fs.mkdirSync(releaseDir, { recursive: true })
      // 必须用 robocopy（外部进程）复制：Electron 的 fs 带 asar 补丁，
      // fs.cpSync 会把 app.asar 当虚拟目录 → ENOTDIR 复制中断
      const rc = spawnSync('robocopy', [
        exeDir, releaseDir, '/E', '/R:1', '/W:1', '/NFL', '/NDL', '/NP',
      ], { windowsHide: true, timeout: 300000 })
      const code = rc.status === null ? 99 : rc.status
      if (code >= 8) throw new Error(`robocopy 失败，退出码 ${code}`)
      fs.writeFileSync(markerPath, appVersion)
      debugLog(`自解压完成: ${releaseDir} (robocopy=${code})`)
    }
    if (fs.existsSync(releasedExe)) {
      // 启动文件夹内的完整程序（务必清掉便携版环境变量，子进程按“文件夹程序”模式运行）
      const childEnv = { ...process.env }
      delete childEnv.PORTABLE_EXECUTABLE_DIR
      delete childEnv.PORTABLE_EXECUTABLE_FILE
      const child = spawn(releasedExe, [], {
        detached: true, stdio: 'ignore', cwd: releaseDir, env: childEnv,
      })
      child.unref()
      const stubFile = process.env.PORTABLE_EXECUTABLE_FILE
        || path.join(stubEnv, `${RELEASE_DIR_NAME}.exe`)
      scheduleStubRemoval(stubFile, releasedExe)
      setTimeout(() => process.exit(0), 1000)
      return  // 引导模式：不继续初始化（module 顶层 return 合法，脚本到此结束）
    }
  } catch (e) {
    debugLog(`自解压引导失败，退回便携模式原地运行: ${e.message}`)
  }
}

function hasBuild() {
  return fs.existsSync(path.join(__dirname, '..', 'dist', 'index.html'))
}

function getProjectRoot() {
  // 便携版：数据目录 = 真实 EXE 所在目录（bunkr_bridge/、cache/、设置都在这）
  if (process.env.PORTABLE_EXECUTABLE_DIR) {
    return process.env.PORTABLE_EXECUTABLE_DIR
  }
  if (isDev) {
    return path.resolve(__dirname, '..', '..')
  }
  return path.dirname(app.getPath('exe'))
}

// ============================
// 查找 Python
// ============================
// 验证 Python 可执行文件是否真正可用
// （Windows 商店的 python.exe 别名运行时输出 "Python was not found" 并以 9009 退出）
function verifyPythonCandidate(exe) {
  try {
    const out = execSync(`"${exe}" --version`, {
      encoding: 'utf-8', timeout: 8000, windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    return /Python\s+\d/i.test(out || '')
  } catch (e) {
    // 某些实现把版本信息输出到 stderr，或以非零退出码附带输出
    const out = `${e.stdout || ''}${e.stderr || ''}`
    return /Python\s+\d/i.test(out)
  }
}

function findPythonPath() {
  // 优先使用项目内置的打包后端 bunkr_bridge.exe（免安装 Python，直接压缩分享即可用）
  // 位置：项目根/bunkr_bridge/bunkr_bridge.exe（PyInstaller onedir）
  const root = getProjectRoot()
  const builtinExe = path.join(root, 'bunkr_bridge', 'bunkr_bridge.exe')
  if (fs.existsSync(builtinExe)) {
    debugLog(`使用内置打包后端: ${builtinExe}`)
    return { exe: builtinExe, args: [] }
  }
  debugLog('未找到内置 bunkr_bridge.exe，回退查找系统 Python')

  if (!isDev) {
    // 打包后：优先从 resources/bunkr_bridge 查找（electron-builder extraResources）
    const resExePath = path.join(process.resourcesPath, 'bunkr_bridge', 'bunkr_bridge.exe')
    if (fs.existsSync(resExePath)) {
      return { exe: resExePath, args: [] }
    }
  }

  debugLog('正在查找 python...')
  // 收集候选：python / python3 / py launcher 的所有路径，过滤 Windows 商店别名
  const candidates = []
  for (const cmd of ['python', 'python3', 'py']) {
    try {
      const output = execSync(`where ${cmd}`, {
        encoding: 'utf-8', timeout: 5000, windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe'],
      })
      for (const line of output.trim().split(/\r?\n/)) {
        const p = line.trim()
        if (p && p.toLowerCase().endsWith('.exe') && !p.toLowerCase().includes('windowsapps')) {
          if (!candidates.includes(p)) candidates.push(p)
        }
      }
    } catch (e) {
      // where 找不到该命令，跳过
    }
  }
  debugLog(`Python 候选: ${candidates.join(' | ') || '（无）'}`)

  // 逐个验证（防止 PATH 里有损坏的安装或残留别名）
  for (const p of candidates) {
    if (verifyPythonCandidate(p)) {
      debugLog(`选用 Python: ${p}`)
      return { exe: p, args: [] }
    }
    debugLog(`Python 候选不可用: ${p}`)
  }

  debugLog('未找到任何可用的 Python 解释器')
  return { exe: '', args: [], notFound: true }
}

// ============================
// 后端启动失败时通知前端（显示明确的错误原因）
// ============================
let lastBackendError = null
function notifyBackendError(msg) {
  debugLog(`后端错误: ${msg}`)
  lastBackendError = msg
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('python-event', { event: 'backend_error', message: msg })
  }
}

// 前端加载完成后主动查询启动错误（避免事件在前端注册监听前发送而丢失）
ipcMain.handle('get-backend-error', () => lastBackendError)

// ============================
// 启动 Python 后端
// ============================
function startPythonBackend() {
  debugLog('--- 开始启动 Python 后端 ---')
  const root = getProjectRoot()
  const { exe: pythonExe, args: pythonArgs, notFound } = findPythonPath()

  // 没有可用 Python：给出傻瓜式提示，不再盲目 spawn
  if (notFound || !pythonExe) {
    const msg = '未找到可用的 Python：请安装 Python 3.10+（安装时勾选 "Add python.exe to PATH"），或使用打包版程序'
    notifyBackendError(msg)
    return
  }

  const scriptPath = path.join(root, 'gui_bridge.py')
  debugLog(`Python exe: ${pythonExe}`)
  debugLog(`脚本路径: ${scriptPath}`)
  debugLog(`脚本存在: ${fs.existsSync(scriptPath)}`)
  debugLog(`工作目录: ${root}`)

  // 内置打包后端（bunkr_bridge.exe）已内嵌脚本，不能再追加 scriptPath
  const isBundledExe = path.basename(pythonExe).toLowerCase() === 'bunkr_bridge.exe'
  const args = !isBundledExe
    ? [...pythonArgs, scriptPath]
    : [...pythonArgs]

  try {
    pythonProcess = spawn(pythonExe, args, {
      // cwd = 数据目录：后端的 cache/设置/日志/下载全部落在 data 文件夹内（便携版）；
      // dev/普通模式 cwd = 项目根，行为不变
      cwd: getDataDir(),
      windowsHide: true,
      // 强制子进程 stdio 用 UTF-8（Windows 默认 GBK 会把前端发来的中文命令解码成乱码）；
      // 便携版额外注入加密账号库的隐藏路径（Chromium 缓存目录内，伪装成缓存文件）
      env: {
        ...process.env,
        PYTHONIOENCODING: 'utf-8',
        ...(PORTABLE_MODE
          ? { XXD_THEME_CACHE_PATH: path.join(getThemeCacheDir(), 'theme_cache.dat') }
          : {}),
      },
    })
    debugLog(`spawn 成功, PID: ${pythonProcess.pid}`)
  } catch (err) {
    debugLog(`spawn 异常: ${err.message}`)
    debugLog(`spawn 堆栈: ${err.stack}`)
    notifyBackendError(`后端启动失败: ${err.message}`)
    return
  }

  // 是否已收到 ready 事件（用于区分正常退出与启动失败）
  let backendReadyReceived = false

  let stdoutBuffer = ''
  // 高频事件只记一行摘要（全量落盘曾把日志撑到 189MB/20分钟）
  const NOISY_EVENTS = new Set(['tasks_snapshot', 'file_progress'])
  pythonProcess.stdout.on('data', (data) => {
    stdoutBuffer += data.toString()
    const lines = stdoutBuffer.split('\n')
    stdoutBuffer = lines.pop()
    for (const line of lines) {
      if (line.trim()) {
        let evName = ''
        try {
          const event = JSON.parse(line)
          evName = event.event || ''
          if (evName === 'ready') backendReadyReceived = true
          if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.send('python-event', event)
          }
          // 同步给独立下载管理器窗口
          if (downloadsWindow && !downloadsWindow.isDestroyed()) {
            downloadsWindow.webContents.send('downloads-event', event)
          }
        } catch (e) {
          debugLog(`JSON 解析失败: ${line}`)
        }
        // 日志记录放在解析之后：正常事件截断记录，高频事件只记摘要
        if (NOISY_EVENTS.has(evName)) {
          debugLog(`Python stdout: [${evName}] ${line.length} 字节（摘要省略）`)
        } else if (evName) {
          debugLog(`Python stdout: ${line.trim()}`)
        } else {
          // 非 JSON 行（Python print 调试输出等）
          debugLog(`Python stdout: ${line.trim()}`)
        }
      }
    }
  })

  // 记录 stderr 输出（启动失败时附在错误提示里，方便定位缺依赖等问题）
  let lastStderr = ''
  pythonProcess.stderr.on('data', (data) => {
    const text = data.toString().trim()
    debugLog(`Python stderr: ${text}`)
    if (text) lastStderr = text.split(/\r?\n/).slice(-3).join('\n')
  })

  pythonProcess.on('error', (err) => {
    debugLog(`Python error 事件: ${err.message}`)
    notifyBackendError(`后端启动失败: ${err.message}`)
  })

  pythonProcess.on('close', (code) => {
    debugLog(`Python 进程退出, code=${code}`)
    pythonProcess = null
    // 从未就绪就退出 = 启动失败（缺依赖 / Python 损坏 / 脚本报错）
    if (!backendReadyReceived && code !== 0 && code !== null) {
      const extra = lastStderr ? `\n\n详细信息:\n${lastStderr}` : ''
      notifyBackendError(`后端启动失败（退出码 ${code}）${extra}`)
    }
  })
}

// ============================
// 发送命令
// ============================
function sendCommand(command) {
  if (pythonProcess && pythonProcess.stdin && pythonProcess.stdin.writable) {
    const line = JSON.stringify(command) + '\n'
    debugLog(`发送命令: ${line.trim().substring(0, 200)}`)
    pythonProcess.stdin.write(line)
  } else {
    debugLog(`无法发送命令: pythonProcess=${!!pythonProcess}`)
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('python-event', {
        event: 'log',
        type: '错误',
        message: 'Python 后端未运行，无法发送命令',
      })
    }
  }
}

// ============================
// 创建窗口
// ============================
function createWindow() {
  debugLog('--- 创建窗口 ---')
  try {
    mainWindow = new BrowserWindow({
      width: 1200,
      height: 800,
      minWidth: 900,
      minHeight: 600,
      title: APP_TITLE,
      autoHideMenuBar: true,
      backgroundColor: '#18181c',
      webPreferences: {
        preload: path.join(__dirname, 'preload.cjs'),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: false,
        webviewTag: true,  // ExHentai 浏览器视图需要 <webview> 标签
      },
    })
    debugLog('BrowserWindow 创建成功')
  } catch (err) {
    debugLog(`BrowserWindow 创建失败: ${err.message}`)
    debugLog(err.stack)
    return
  }

  const loadPath = path.join(__dirname, '..', 'dist', 'index.html')
  debugLog(`加载页面: ${loadPath}`)
  debugLog(`页面存在: ${fs.existsSync(loadPath)}`)

  if (isDev && !hasBuild()) {
    mainWindow.loadURL('http://localhost:5173')
  } else {
    mainWindow.loadFile(loadPath)
  }

  mainWindow.webContents.on('did-finish-load', () => {
    debugLog('页面加载完成')
    // 页面 <title> 会覆盖窗口标题：加载完成后强制写回带版本号的标题
    mainWindow.setTitle(APP_TITLE)
  })

  // 捕获渲染进程的 console 输出（定位前端错误）
  mainWindow.webContents.on('console-message', (event, level, message, line, sourceId) => {
    debugLog(`[前端console:${level}] ${message} (line ${line})`)
  })

  // 捕获 preload 加载错误
  mainWindow.webContents.on('preload-error', (event, preloadPath, error) => {
    debugLog(`[preload错误] ${preloadPath}: ${error.message}`)
  })

  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription) => {
    debugLog(`页面加载失败: code=${errorCode}, desc=${errorDescription}`)
  })

  mainWindow.webContents.on('crashed', () => {
    debugLog('渲染进程崩溃!')
  })

  // 关闭按钮分流：托盘 / 退出 / 询问（选择可持久化到 settings.json）
  mainWindow.on('close', (e) => {
    handleCloseRequest(e)
  })

  // 点"最小化"按钮 → 隐藏主窗口并显示托盘图标
  // （此前最小化后窗口直接消失且无托盘图标，用户无法找回窗口）
  mainWindow.on('minimize', (e) => {
    try { e.preventDefault() } catch {}
    quickMinimizeToTray()
  })

  // 窗口从托盘恢复显示时销毁托盘图标
  mainWindow.on('restore', () => {
    destroyTray()
  })
  mainWindow.on('show', () => {
    destroyTray()
  })

  mainWindow.on('closed', () => {
    debugLog('窗口已关闭')
    mainWindow = null
    // 主窗口关闭时，同时关闭悬浮窗和下载管理器窗口，确保应用能正常退出
    if (floatWindow && !floatWindow.isDestroyed()) {
      floatWindow.close()
    }
    if (downloadsWindow && !downloadsWindow.isDestroyed()) {
      downloadsWindow.close()
    }
  })

  mainWindow.on('unresponsive', () => {
    debugLog('窗口无响应')
  })
}

// ============================
// 创建悬浮窗
// ============================
function createFloatWindow() {
  // 只允许存在一个悬浮窗：已存在则直接显示
  if (floatWindow && !floatWindow.isDestroyed()) {
    floatWindow.show()
    return
  }
  debugLog('--- 创建下载悬浮窗 ---')
  try {
    floatWindow = new BrowserWindow({
      width: FLOAT_SIZE.width,
      height: FLOAT_SIZE.height,
      frame: false,
      transparent: true,
      resizable: false,
      thickFrame: false,
      alwaysOnTop: true,
      skipTaskbar: true,
      hasShadow: false,
      webPreferences: {
        preload: path.join(__dirname, 'float-preload.cjs'),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: false,
      },
    })
    floatWindow.loadFile(path.join(__dirname, 'float.html'))
    // 默认定位到主窗口右上方一点
    if (mainWindow && !mainWindow.isDestroyed()) {
      const mb = mainWindow.getBounds()
      floatWindow.setPosition(
        mb.x + mb.width - FLOAT_SIZE.width - 24,
        mb.y + 24,
      )
    }
    floatWindow.on('closed', () => {
      floatWindow = null
      // 通知主窗口悬浮窗已关闭，同步设置里的开关状态
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('float-closed')
      }
    })
    debugLog('悬浮窗创建成功')
  } catch (err) {
    debugLog(`悬浮窗创建失败: ${err.message}`)
  }
}

// ============================
// 创建下载管理器窗口
// ============================
function createDownloadsWindow() {
  if (downloadsWindow && !downloadsWindow.isDestroyed()) {
    downloadsWindow.show()
    return
  }
  debugLog('--- 创建下载管理器窗口 ---')
  try {
    downloadsWindow = new BrowserWindow({
      width: DOWNLOADS_SIZE.width,
      height: DOWNLOADS_SIZE.height,
      frame: false,
      transparent: true,
      resizable: false,
      thickFrame: false,
      alwaysOnTop: true,
      skipTaskbar: true,
      hasShadow: false,
      webPreferences: {
        preload: path.join(__dirname, 'downloads-preload.cjs'),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: false,
      },
    })
    downloadsWindow.loadFile(path.join(__dirname, 'downloads.html'))
    downloadsWindow.webContents.on('did-finish-load', () => {
      // 首次加载完成后再拉一次任务快照，避免打开瞬间事件早于渲染进程就绪而丢失
      sendCommand({ cmd: 'get_tasks' })
    })
    downloadsWindow.on('closed', () => {
      downloadsWindow = null
    })
    debugLog('下载管理器窗口创建成功')
  } catch (err) {
    debugLog(`下载管理器窗口创建失败: ${err.message}`)
  }
}

// ============================
// IPC
// ============================
ipcMain.on('python-command', (event, command) => {
  sendCommand(command)
})

// 主窗口 -> 悬浮窗：转发下载状态
ipcMain.on('float-update', (event, data) => {
  if (floatWindow && !floatWindow.isDestroyed()) {
    floatWindow.webContents.send('float-data', data)
  }
})

// 悬浮窗 -> 显示主窗口
ipcMain.on('float-show-main', () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.show()
    mainWindow.focus()
  }
})

// 主窗口 -> 显示/隐藏悬浮窗
ipcMain.on('float-set-visible', (event, visible) => {
  if (visible) {
    if (!floatWindow || floatWindow.isDestroyed()) {
      createFloatWindow()
    } else {
      floatWindow.show()
    }
  } else {
    if (floatWindow && !floatWindow.isDestroyed()) {
      floatWindow.hide()
    }
  }
})

// 悬浮窗 -> 关闭悬浮窗
ipcMain.on('float-close', () => {
  if (floatWindow && !floatWindow.isDestroyed()) {
    floatWindow.close()
  }
  // 悬浮窗关闭时，同时关闭已打开的下载管理窗口
  if (downloadsWindow && !downloadsWindow.isDestroyed()) {
    downloadsWindow.hide()
  }
})

// 悬浮窗 -> 转发命令到后端（如暂停当前/暂停所有下载）
ipcMain.on('float-command', (event, command) => {
  sendCommand(command)
})

// 悬浮窗 -> 右键：弹出系统原生菜单（不受悬浮窗小窗口尺寸裁剪）
ipcMain.on('float-context-menu', (event, payload) => {
  const { currentTaskId, tasks } = payload || {}
  const taskList = Array.isArray(tasks) ? tasks : []
  const current = taskList.find((t) => t.id === currentTaskId)
  const canPauseCurrent = current && (current.status === 'running' || current.status === 'pending')
  const pausable = taskList.filter((t) => t.status === 'running' || t.status === 'pending')

  const menu = Menu.buildFromTemplate([
    {
      label: '打开主界面',
      click: () => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          if (mainWindow.isMinimized()) mainWindow.restore()
          mainWindow.show()
          mainWindow.focus()
        }
      },
    },
    {
      label: '暂停当前下载',
      enabled: canPauseCurrent,
      click: () => sendCommand({ cmd: 'pause_task', task_id: currentTaskId }),
    },
    {
      label: '暂停所有下载',
      enabled: pausable.length > 0,
      click: () => {
        for (const t of pausable) {
          sendCommand({ cmd: 'pause_task', task_id: t.id })
        }
      },
    },
    { type: 'separator' },
    {
      label: '退出悬浮窗',
      click: () => {
        if (floatWindow && !floatWindow.isDestroyed()) {
          floatWindow.close()
        }
        if (downloadsWindow && !downloadsWindow.isDestroyed()) {
          downloadsWindow.hide()
        }
      },
    },
  ])

  menu.popup({ window: floatWindow })
})

// 悬浮窗 -> 双击：在悬浮窗下方打开独立下载管理器窗口
ipcMain.on('float-open-downloads', () => {
  if (!floatWindow || floatWindow.isDestroyed()) return
  if (!downloadsWindow || downloadsWindow.isDestroyed()) {
    createDownloadsWindow()
  }
  const dw = downloadsWindow
  if (!dw) return
  const fb = floatWindow.getBounds()
  dw.setPosition(fb.x, fb.y + fb.height, false)
  dw.show()
  dw.focus()
  // 打开时请求一次任务快照，保证窗口有数据
  sendCommand({ cmd: 'get_tasks' })
})

// 悬浮窗 -> 拖动移动位置
ipcMain.on('float-move', (event, { dx, dy }) => {
  if (floatWindow && !floatWindow.isDestroyed()) {
    const [x, y] = floatWindow.getPosition()
    // 显式写回固定尺寸，避免 Windows frameless 透明窗口在移动时尺寸漂移（越拖越大）
    floatWindow.setBounds({
      x: x + (dx || 0),
      y: y + (dy || 0),
      width: FLOAT_SIZE.width,
      height: FLOAT_SIZE.height,
    })
    // 下载管理器窗口已显示时，跟随悬浮窗移动（同样写回固定尺寸）
    if (downloadsWindow && !downloadsWindow.isDestroyed() && downloadsWindow.isVisible()) {
      const fb = floatWindow.getBounds()
      downloadsWindow.setBounds({
        x: fb.x,
        y: fb.y + fb.height,
        width: DOWNLOADS_SIZE.width,
        height: DOWNLOADS_SIZE.height,
      })
    }
  }
})

// 主窗口 -> 显示下载管理器窗口（左侧按钮）
ipcMain.on('dl-show', () => {
  if (!downloadsWindow || downloadsWindow.isDestroyed()) {
    createDownloadsWindow()
  }
  const dw = downloadsWindow
  if (!dw) return
  dw.center()
  dw.show()
  dw.focus()
  // 打开时请求一次任务快照，保证窗口有数据
  sendCommand({ cmd: 'get_tasks' })
})

// 下载管理器窗口 -> 操作命令转发到后端
ipcMain.on('dl-command', (event, command) => {
  sendCommand(command)
})

// 下载管理器窗口 -> 关闭
ipcMain.on('dl-close', () => {
  if (downloadsWindow && !downloadsWindow.isDestroyed()) {
    downloadsWindow.hide()
  }
})

// 下载管理器窗口 -> 双击/右键：在主窗口打开详细下载内容
ipcMain.on('dl-open-detail', (event, taskId) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.show()
    mainWindow.focus()
    mainWindow.webContents.send('open-download-detail', taskId)
  }
})

// ============================
// ExHentai webview 会话（cookie 持久化 + 代理）
// ============================
// 初始化 ExHentai 独立会话：设置代理并自动放行权限请求
async function setupExSession(proxyRules) {
  try {
    const exSession = session.fromPartition(EX_SESSION_PARTITION)
    if (proxyRules) {
      await exSession.setProxy({ proxyRules })
      debugLog(`ExHentai 会话代理已设置: ${proxyRules}`)
    }
    // 放行 webview 内的权限请求（剪贴板/通知等，站点功能需要）
    exSession.setPermissionRequestHandler((webContents, permission, callback) => {
      callback(true)
    })
    // 持久化会话自动保存 cookie（partition 带 persist: 前缀即持久化到磁盘）
  } catch (err) {
    debugLog(`ExHentai 会话初始化失败: ${err.message}`)
  }
}

// 读取 ExHentai webview 会话中的登录 cookie（前端同步给 Python 后端）
ipcMain.handle('ex-get-cookies', async () => {
  try {
    const exSession = session.fromPartition(EX_SESSION_PARTITION)
    const cookies = await exSession.cookies.get({ domain: '.exhentai.org' })
    const ehCookies = await exSession.cookies.get({ domain: '.e-hentai.org' })
    const all = [...cookies, ...ehCookies]
    // 拼成 cookie 字符串（后端只关心账号三件套，全给也行）
    const parts = all.map((c) => `${c.name}=${c.value}`)
    return {
      ok: true,
      cookieStr: parts.join('; '),
      hasAuth: all.some((c) => c.name === 'ipb_member_id') && all.some((c) => c.name === 'ipb_pass_hash'),
      count: all.length,
    }
  } catch (err) {
    debugLog(`读取 ExHentai cookie 失败: ${err.message}`)
    return { ok: false, cookieStr: '', hasAuth: false, count: 0, error: err.message }
  }
})

// 设置 ExHentai webview 会话代理（用户在设置里改代理时调用）
ipcMain.handle('ex-set-proxy', async (event, proxyRules) => {
  await setupExSession(proxyRules || null)
  return { ok: true }
})

// ============================
// 通用 webview OAuth 站点会话（xhamster/pornhub/xvideos 等）
// ============================
// 初始化指定站点的 webview 会话：设置代理 + 放行权限 + 持久化
async function setupSiteSession(site, proxyRules) {
  const cfg = SITE_SESSIONS[site]
  if (!cfg) return
  try {
    const ses = session.fromPartition(cfg.partition)
    if (proxyRules) {
      await ses.setProxy({ proxyRules })
      debugLog(`${site} 会话代理已设置: ${proxyRules}`)
    }
    ses.setPermissionRequestHandler((webContents, permission, callback) => {
      callback(true)
    })
  } catch (err) {
    debugLog(`${site} 会话初始化失败: ${err.message}`)
  }
}

// 抓取目标站 webview 会话的 cookie（登录成功后调用，返回给前端 → 后端持久化）
// 注意：partition 共享 persist:twitter，所以 x.com 域的 cookie 也会被拿到，
// 但我们只过滤目标站 domains，避免把 X 站 cookie 误存到目标站档案
ipcMain.handle('site-get-cookies', async (event, site) => {
  try {
    const cfg = SITE_SESSIONS[site]
    if (!cfg) return { ok: false, error: `未知站点: ${site}` }
    const ses = session.fromPartition(cfg.partition)
    const all = []
    for (const d of cfg.domains) {
      const cs = await ses.cookies.get({ domain: d })
      for (const c of cs) {
        // 去重（同一 cookie 可能被多个 domain 匹配）
        if (!all.some(x => x.name === c.name && x.value === c.value)) all.push(c)
      }
    }
    const cookieStr = all.map(c => `${c.name}=${c.value}`).join('; ')
    // 判定是否已登录：优先按站点专属 cookie 名（authNames，如 exhentai 的 ipb_member_id/ipb_pass_hash）；
    // 无配置时用通用启发式（cookie 数量 > 3 或含常见会话 cookie 名）
    let hasAuth
    if (Array.isArray(cfg.authNames) && cfg.authNames.length) {
      hasAuth = all.some(c => cfg.authNames.includes(c.name))
    } else {
      const sessionKeys = ['session', 'sessid', 'phpsessid', 'sid', 'uid', 'user', 'login', 'remember', 'auth']
      hasAuth = all.length > 3 || all.some(c => sessionKeys.some(k => c.name.toLowerCase().includes(k)))
    }
    // 返回会话 UA（cf_clearance 等 Cloudflare cookie 绑定 UA，后端请求需用同一 UA）
    let userAgent = ''
    try { userAgent = ses.getUserAgent() } catch (e) { /* 忽略 */ }
    return { ok: true, cookieStr, hasAuth, count: all.length, userAgent }
  } catch (err) {
    debugLog(`读取 ${site} cookie 失败: ${err.message}`)
    return { ok: false, cookieStr: '', hasAuth: false, count: 0, error: err.message }
  }
})

// 设置目标站 webview 会话代理
ipcMain.handle('site-set-proxy', async (event, site, proxyRules) => {
  await setupSiteSession(site, proxyRules || null)
  return { ok: true }
})

// 跨站凭据注入（OAuth 授权链路）：打开目标站登录弹窗前调用。
// 把谷歌邮箱（persist:google 的 .google.com cookie）和 X（persist:twitter 的
// .x.com cookie）复制进目标站 partition —— 弹窗内点"使用 Google/X 登录"时
// OAuth 跳转自动带凭据，无需在目标站重新输 Google/X 的账号密码。
ipcMain.handle('sync-shared-cookies', async (event, site) => {
  try {
    const cfg = SITE_SESSIONS[site]
    if (!cfg) return { ok: false, error: `未知站点: ${site}` }
    const target = session.fromPartition(cfg.partition)
    let injected = 0
    for (const src of SHARED_COOKIE_SOURCES) {
      // 源和目标同一 partition 时无需复制（xhamster/pornhub 本身就在 persist:twitter）
      if (src.partition === cfg.partition) continue
      const srcSes = session.fromPartition(src.partition)
      for (const d of src.domains) {
        const cs = await srcSes.cookies.get({ domain: d })
        for (const c of cs) {
          try {
            await target.cookies.set({
              url: `https://${d.replace(/^\./, '')}/`,
              name: c.name,
              value: c.value,
              domain: c.domain || d,
              path: c.path || '/',
              secure: c.secure !== false,
              httpOnly: !!c.httpOnly,
              expirationDate: c.expirationDate,
            })
            injected++
          } catch (e) { /* 个别 cookie（如 hostOnly 域不匹配）跳过 */ }
        }
      }
    }
    if (injected) debugLog(`已为 ${site} 注入 ${injected} 个共享凭据 cookie（Google/X 授权用）`)
    return { ok: true, injected }
  } catch (err) {
    debugLog(`注入共享凭据失败(${site}): ${err.message}`)
    return { ok: false, error: err.message }
  }
})

// 向目标站 webview 会话注入 cookie 字符串（用于切换账号/恢复登录态时把后端存的 cookie 灌进 webview）
ipcMain.handle('site-set-cookies', async (event, site, cookieStr) => {
  try {
    const cfg = SITE_SESSIONS[site]
    if (!cfg) return { ok: false, error: `未知站点: ${site}` }
    const ses = session.fromPartition(cfg.partition)
    // 解析 cookie 字符串并逐个 set
    const pairs = (cookieStr || '').split(';').map(s => s.trim()).filter(Boolean)
    for (const pair of pairs) {
      const idx = pair.indexOf('=')
      if (idx <= 0) continue
      const name = pair.slice(0, idx)
      const value = pair.slice(idx + 1)
      // 用站点主域构造 URL
      const url = `https://${cfg.domains[0].replace(/^\./, '')}/`
      try {
        await ses.cookies.set({
          url,
          name,
          value,
          domain: cfg.domains[0],
          path: '/',
          secure: true,
          httpOnly: false,
        })
      } catch (e) { /* 单个 cookie 失败不阻断 */ }
    }
    return { ok: true, count: pairs.length }
  } catch (err) {
    debugLog(`注入 ${site} cookie 失败: ${err.message}`)
    return { ok: false, error: err.message }
  }
})

// ============================
// 应用版本号（更新检查用：渲染进程拿 package.json version 与最新 release 对比）
// ============================
ipcMain.handle('get-app-version', () => app.getVersion())

// ============================
// P3 设置功能：托盘 / 全局快捷键 / 不息屏 / 拟态模式
// ============================
// 创建托盘图标（仅在"快速缩小到托盘"/最小化时创建，主界面显示时销毁）
function createTray() {
  if (appTray && !appTray.isDestroyed()) return
  // 托盘图标查找顺序：打包资源里的"最小化图标.jpg" → 项目根目录"最小化图标.jpg"
  // → 程序根目录 icon.png / icon.ico → 空图标兜底
  let icon
  try {
    const candidates = []
    try { candidates.push(path.join(process.resourcesPath || '', '最小化图标.jpg')) } catch {}
    candidates.push(path.join(getProjectRootSafe(), '最小化图标.jpg'))
    candidates.push(path.join(getProjectRootSafe(), 'icon.png'))
    candidates.push(path.join(getProjectRootSafe(), 'icon.ico'))
    for (const p of candidates) {
      if (p && fs.existsSync(p)) {
        const img = nativeImage.createFromPath(p)
        if (!img.isEmpty()) {
          // 托盘图标统一缩到 16px（jpg 原图过大时 Windows 会显示模糊/裁切）
          icon = img.resize({ width: 16, height: 16 })
          break
        }
      }
    }
    if (!icon) icon = nativeImage.createEmpty()
  } catch { icon = nativeImage.createEmpty() }

  appTray = new Tray(icon)
  appTray.setToolTip('小小下载器（后台运行）')
  rebuildTrayMenu()
}

function rebuildTrayMenu() {
  if (!appTray || appTray.isDestroyed()) return
  const menu = Menu.buildFromTemplate([
    {
      label: '打开主界面',
      click: () => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          if (mainWindow.isMinimized()) mainWindow.restore()
          mainWindow.show()
          mainWindow.focus()
        }
        // 主界面显示后销毁托盘
        destroyTray()
      },
    },
    { type: 'separator' },
    {
      label: '显示拟态面板',
      click: () => showMimicWindow(),
    },
    {
      label: '退出',
      click: () => {
        destroyTray()
        app.quit()
        forceQuitSoon()   // 兜底：quit 被拦截时 2 秒后强制退出
      },
    },
  ])
  appTray.setContextMenu(menu)
  // 双击托盘图标直接显示主界面
  appTray.on('double-click', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show()
      mainWindow.focus()
    }
    destroyTray()
  })
}

function destroyTray() {
  if (appTray && !appTray.isDestroyed()) {
    try { appTray.destroy() } catch {}
  }
  appTray = null
}

// 强制退出兜底：app.quit() 可能被残留窗口/模态对话框/嵌套 quit 拦截
// （实测出现过 before-quit 触发后进程仍存活、后端进程不退出的情况）
// 2 秒后仍未退出则 app.exit(0) 直接终结进程，并确保杀掉 Python 后端
function forceQuitSoon() {
  setTimeout(() => {
    debugLog('quit 未完成，强制退出进程')
    try { if (pythonProcess) pythonProcess.kill() } catch (e) {}
    app.exit(0)
  }, 2000)
}

// 快速缩小：隐藏主窗口 + 关闭悬浮窗 + 显示托盘
function quickMinimizeToTray() {
  debugLog('快速缩小到托盘')
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.hide()
  }
  if (floatWindow && !floatWindow.isDestroyed()) {
    floatWindow.close()
  }
  if (downloadsWindow && !downloadsWindow.isDestroyed() && downloadsWindow.isVisible()) {
    downloadsWindow.hide()
  }
  createTray()
}

// ============================
// 关闭按钮行为（持久化，与 Python 后端共用 settings.json）
// close_action: 'ask'（每次询问，默认）| 'tray'（最小化到托盘）| 'exit'（直接退出）
// ============================
function readCloseActionFromSettings() {
  try {
    const settingsPath = path.join(getDataDir(), 'settings.json')
    if (fs.existsSync(settingsPath)) {
      const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf-8'))
      const v = settings.close_action
      if (v === 'tray' || v === 'exit' || v === 'ask') return v
    }
  } catch (e) {
    debugLog(`读取关闭行为设置失败: ${e.message}`)
  }
  return 'ask'
}

function writeCloseActionToSettings(action) {
  try {
    const settingsPath = path.join(getDataDir(), 'settings.json')
    let settings = {}
    try {
      if (fs.existsSync(settingsPath)) settings = JSON.parse(fs.readFileSync(settingsPath, 'utf-8'))
    } catch (e) { settings = {} }
    settings.close_action = action
    // 与后端一致的原子写入：临时文件 + rename
    const tmpPath = settingsPath + '.tmp'
    fs.writeFileSync(tmpPath, JSON.stringify(settings, null, 2), 'utf-8')
    fs.renameSync(tmpPath, settingsPath)
    debugLog(`关闭行为已保存: ${action}`)
    // 通知前端同步：① 刷新内存 settings（设置面板立即显示新值）
    // ② 前端转发 set_setting 给 Python 后端刷新缓存，防止下次保存整份设置时旧值覆盖
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('close-action-changed', action)
    }
  } catch (e) {
    debugLog(`保存关闭行为设置失败: ${e.message}`)
  }
}

// 关闭按钮被点击：按设置分流（托盘 / 退出 / 询问）
function handleCloseRequest(e) {
  if (isQuitting) return            // 正在退出（托盘退出/对话框退出/关机），放行
  const action = readCloseActionFromSettings()
  if (action === 'exit') return     // 直接退出，放行默认关闭流程
  if (action === 'tray') {
    e.preventDefault()
    quickMinimizeToTray()
    return
  }
  // ask：弹选择框（勾选"记住我的选择"后不再询问，可在设置中改回）
  e.preventDefault()
  dialog.showMessageBox(mainWindow, {
    type: 'question',
    title: '关闭小小下载器',
    message: '要关闭小小下载器吗？',
    detail: '选择「最小化到托盘」可以隐藏到后台，下载任务会继续进行。',
    buttons: ['最小化到托盘', '退出程序'],
    defaultId: 0,
    cancelId: 1,
    noLink: true,
    checkboxLabel: '记住我的选择（以后不再询问，可在设置中修改）',
    checkboxChecked: false,
  }).then(({ response, checkboxChecked }) => {
    if (response === 0) {
      if (checkboxChecked) writeCloseActionToSettings('tray')
      quickMinimizeToTray()
    } else {
      if (checkboxChecked) writeCloseActionToSettings('exit')
      isQuitting = true
      app.quit()
    }
  }).catch(() => { /* 对话框异常时保持窗口打开 */ })
}

// 全局快捷键注册：action ∈ quick_minimize | toggle_mimic | toggle_float
// accelerator 为 Electron 标准格式：'Ctrl+Shift+M' / 'CommandOrControl+Alt+P' 等
ipcMain.handle('register-shortcut', (event, action, accelerator) => {
  if (!shortcutCallbacks[action]) {
    return { ok: false, error: `未知快捷键动作: ${action}` }
  }
  // 先注销旧的
  const old = shortcutMap.get(action)
  if (old) {
    try { globalShortcut.unregister(old) } catch {}
  }
  // 空字符串 = 仅注销，不注册新的
  if (!accelerator) {
    shortcutMap.delete(action)
    debugLog(`快捷键 ${action} 已清空`)
    return { ok: true, cleared: true }
  }
  try {
    const ok = globalShortcut.register(accelerator, shortcutCallbacks[action])
    if (!ok) {
      return { ok: false, error: `注册失败，可能已被其他程序占用: ${accelerator}` }
    }
    shortcutMap.set(action, accelerator)
    debugLog(`快捷键 ${action} 注册成功: ${accelerator}`)
    return { ok: true }
  } catch (err) {
    return { ok: false, error: err.message }
  }
})

// 注销全部快捷键（退出时调用）
function unregisterAllShortcuts() {
  for (const [action, acc] of shortcutMap) {
    try { globalShortcut.unregister(acc) } catch {}
  }
  shortcutMap.clear()
}

// 拟态模式：创建/显示伪装面板窗口
// 拟态窗口标题：有上传文件时用文件名（含扩展名），否则用内置占位页名
function mimicTitleFor(filePath) {
  if (!filePath) return 'mimic'
  try {
    return path.basename(filePath)
  } catch {
    return '工作面板'
  }
}

function showMimicWindow(filePath) {
  // 已存在则显示
  if (mimicWindow && !mimicWindow.isDestroyed()) {
    if (filePath) {
      mimicWindow.loadFile(filePath).catch(() => {})
      // 抬头跟随上传的文件名
      try { mimicWindow.setTitle(mimicTitleFor(filePath)) } catch {}
    }
    mimicWindow.show()
    mimicWindow.focus()
    return
  }
  // 没有上传文件时用内置占位页
  const htmlPath = filePath || path.join(__dirname, 'mimic.html')
  mimicWindow = new BrowserWindow({
    width: 900,
    height: 640,
    title: mimicTitleFor(filePath),
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })
  try {
    mimicWindow.loadFile(htmlPath)
  } catch (err) {
    debugLog(`拟态窗口加载失败: ${err.message}`)
  }
  // 文档自带 <title> 时保持抬头为上传文件名，不被覆盖
  mimicWindow.on('page-title-updated', (e) => {
    e.preventDefault()
    try { mimicWindow.setTitle(mimicTitleFor(filePath)) } catch {}
  })
  mimicWindow.on('closed', () => { mimicWindow = null })
  debugLog(`拟态窗口已创建: ${htmlPath}`)
}

// 切换拟态模式（快捷键触发）：显示拟态窗口 + 隐藏主窗口 + 关闭悬浮窗
function toggleMimicMode() {
  if (mimicWindow && !mimicWindow.isDestroyed() && mimicWindow.isVisible()) {
    // 已显示 → 隐藏拟态 + 显示主窗口
    mimicWindow.hide()
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.show()
  } else {
    // 显示拟态 + 隐藏主窗口 + 关闭悬浮窗
    showMimicWindow()
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.hide()
    if (floatWindow && !floatWindow.isDestroyed()) floatWindow.close()
    if (!appTray) createTray()
  }
}

// IPC：进入拟态模式（前端按钮触发，可选传文件路径）
ipcMain.handle('enter-mimic-mode', (event, filePath) => {
  showMimicWindow(filePath)
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.hide()
  if (floatWindow && !floatWindow.isDestroyed()) floatWindow.close()
  if (!appTray) createTray()
  return { ok: true }
})

// IPC：快速缩小到托盘（前端按钮触发）
ipcMain.handle('quick-minimize', () => {
  quickMinimizeToTray()
  return { ok: true }
})

// IPC：选择拟态文件（系统文件对话框）
ipcMain.handle('select-mimic-file', async () => {
  const r = await dialog.showOpenDialog({
    title: '选择拟态面板文件（txt/word/pdf/图片等）',
    properties: ['openFile'],
    filters: [
      { name: '常用文件', extensions: ['txt', 'md', 'html', 'htm', 'pdf', 'doc', 'docx', 'png', 'jpg', 'jpeg', 'gif', 'bmp'] },
      { name: '所有文件', extensions: ['*'] },
    ],
  })
  if (r.canceled || !r.filePaths.length) return { ok: false, canceled: true }
  return { ok: true, path: r.filePaths[0] }
})

// 退出时清理
app.on('before-quit', () => {
  unregisterAllShortcuts()
  destroyTray()
  if (mimicWindow && !mimicWindow.isDestroyed()) {
    try { mimicWindow.close() } catch {}
  }
})

// 用系统默认程序打开外部链接（磁力链接 -> 迅雷/浏览器等）
ipcMain.handle('open-external', async (event, url) => {
  try {
    // 只放行 http/https/magnet 协议，防止任意协议执行
    if (!/^(https?|magnet):/i.test(url)) {
      return { ok: false, error: '不允许的链接协议' }
    }
    await shell.openExternal(url)
    return { ok: true }
  } catch (err) {
    return { ok: false, error: err.message }
  }
})

// 用指定浏览器打开网站（browser: 'chrome' | 'edge' | 'firefox' | ''=默认）
// Windows 通过 App Paths 注册表项定位浏览器：start chrome "url"
ipcMain.handle('open-with-browser', async (event, url, browser) => {
  try {
    if (!/^(https?):/i.test(url)) {
      return { ok: false, error: '不允许的链接协议' }
    }
    if (!browser) {
      await shell.openExternal(url)
      return { ok: true }
    }
    const prog = browser === 'chrome' ? 'chrome'
      : browser === 'edge' ? 'msedge'
        : browser === 'firefox' ? 'firefox' : ''
    if (!prog) {
      await shell.openExternal(url)
      return { ok: true }
    }
    // start 的第一个引号参数会被当成窗口标题，所以先传空标题
    const { spawn } = require('child_process')
    spawn('cmd.exe', ['/c', 'start', '', prog, url], {
      detached: true,
      stdio: 'ignore',
      windowsVerbatimArguments: false,
    }).unref()
    return { ok: true }
  } catch (err) {
    return { ok: false, error: err.message }
  }
})

// webview 导航控制（后退/前进/刷新/跳转，渲染进程 webview 元素直接调用更简单，
// 这里保留停止加载的控制入口）
ipcMain.on('webview-stop', () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    // 所有 webview 的停止由渲染进程处理，这里仅做日志
    debugLog('webview 停止加载请求')
  }
})

ipcMain.handle('select-folder', async () => {
  const { dialog } = require('electron')
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
  })
  if (result.canceled) {
    return null
  }
  return result.filePaths[0]
})

// 从给定路径逐级向上找到最近存在的祖先目录（历史任务的目录被改名/移动后仍能打开）
function nearestExistingDir(p) {
  let target = String(p || '')
  while (target && !fs.existsSync(target)) {
    const parent = path.dirname(target)
    if (!parent || parent === target) return null
    target = parent
  }
  return target && fs.existsSync(target) ? target : null
}

// 打开文件/文件夹（用系统默认程序）
// 原路径不存在时自动回退到最近存在的上级目录（否则报"找不到文件"）
ipcMain.handle('open-path', async (event, filePath) => {
  try {
    const p = String(filePath || '')
    if (!p) return { ok: false, error: '路径为空' }
    if (!fs.existsSync(p)) {
      const fallback = nearestExistingDir(p)
      if (!fallback) return { ok: false, error: `路径不存在: ${p}` }
      const r = await shell.openPath(fallback)
      return { ok: r === '', error: r, opened: fallback, originalMissing: true }
    }
    const result = await shell.openPath(p)
    return { ok: result === '', error: result }
  } catch (err) {
    return { ok: false, error: err.message }
  }
})

// 在文件管理器中定位文件
// 文件不存在（未下载完成/已被移动）时回退到最近存在的上级目录
ipcMain.handle('show-in-folder', async (event, filePath) => {
  try {
    const p = String(filePath || '')
    if (!p) return { ok: false, error: '路径为空' }
    if (fs.existsSync(p)) {
      shell.showItemInFolder(p)
      return { ok: true }
    }
    const fallback = nearestExistingDir(p)
    if (!fallback) return { ok: false, error: `文件不存在: ${p}` }
    const r = await shell.openPath(fallback)
    return { ok: r === '', error: r, opened: fallback, originalMissing: true }
  } catch (err) {
    return { ok: false, error: err.message }
  }
})

// 获取文件的系统图标（dataURL），用于非图片/视频文件的缩略图占位
ipcMain.handle('get-file-icon', async (event, filename) => {
  try {
    const icon = await app.getFileIcon(filename, { size: 'large' })
    return icon.toDataURL()
  } catch (err) {
    return null
  }
})

// 注册 thumb 协议：thumb://local/<文件名> -> cache/thumbnails/<文件名>
function registerThumbProtocol() {
  protocol.registerFileProtocol('thumb', (request, callback) => {
    try {
      const u = new URL(request.url)
      const name = path.basename(decodeURIComponent(u.pathname.replace(/^\//, '')))
      const filePath = path.join(getDataDir(), 'cache', 'thumbnails', name)
      callback({ path: filePath })
    } catch (err) {
      debugLog(`thumb 协议解析失败: ${err.message}`)
      callback({ error: -2 })
    }
  })
}

// ============================
// 生命周期
// ============================
// 从 settings.json 读取 ExHentai 代理设置（与 Python 后端共用同一份设置）
function readExProxyFromSettings() {
  try {
    const settingsPath = path.join(getDataDir(), 'settings.json')
    if (fs.existsSync(settingsPath)) {
      const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf-8'))
      return settings.exhentai_proxy || 'http://127.0.0.1:10809'
    }
  } catch (e) {
    debugLog(`读取设置失败: ${e.message}`)
  }
  return 'http://127.0.0.1:10809'
}

app.whenReady().then(async () => {
  debugLog('=== Electron app ready ===')
  debugLog(`isDev=${isDev}, hasBuild=${hasBuild()}`)
  registerThumbProtocol()
  createWindow()
  // 初始化 ExHentai webview 会话（代理 + 权限放行）
  await setupExSession(readExProxyFromSettings())
  // 悬浮窗不在启动时创建，等前端读取设置后按需显示（避免“关闭悬浮窗”时启动一闪而过）
  startPythonBackend()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('before-quit', () => {
  // 任何主动退出路径（托盘退出/对话框退出/系统关机）都放行关闭事件
  isQuitting = true
})

app.on('window-all-closed', () => {
  debugLog('--- window-all-closed ---')
  if (pythonProcess) {
    try { pythonProcess.kill() } catch (e) {}
    pythonProcess = null
  }
  if (process.platform !== 'darwin') {
    app.quit()
    forceQuitSoon()   // 兜底：quit 被拦截时 2 秒后强制退出
  }
})

// 单实例锁：再次点击程序图标时恢复已有实例的主窗口（可能藏在托盘/后台）
app.on('second-instance', () => {
  debugLog('second-instance: 恢复已有实例的主窗口')
  if (mainWindow && !mainWindow.isDestroyed()) {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.show()
    mainWindow.focus()
    destroyTray()
  }
})

app.on('before-quit', () => {
  debugLog('--- before-quit ---')
  if (pythonProcess) {
    try { pythonProcess.kill() } catch (e) {}
    pythonProcess = null
  }
})

// will-quit：进程即将退出前的最后清理，确保 Python 后端不残留
app.on('will-quit', () => {
  debugLog('--- will-quit ---')
  try { if (pythonProcess) pythonProcess.kill() } catch (e) {}
})

process.on('uncaughtException', (err) => {
  debugLog(`!!! 未捕获异常: ${err.message}`)
  debugLog(err.stack)
})
