const { app, BrowserWindow, ipcMain, protocol, shell, Menu, session } = require('electron')
const { spawn, spawnSync, execSync, execFileSync } = require('child_process')
const path = require('path')
const fs = require('fs')

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

let pythonProcess = null
let mainWindow = null
let floatWindow = null
let downloadsWindow = null
const isDev = !app.isPackaged

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

function debugLog(msg) {
  const ts = new Date().toISOString()
  const line = `[${ts}] ${msg}\n`
  try {
    fs.mkdirSync(logDir, { recursive: true })
    fs.appendFileSync(debugLogPath, line, 'utf-8')
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
  pythonProcess.stdout.on('data', (data) => {
    const text = data.toString()
    debugLog(`Python stdout: ${text.trim()}`)
    stdoutBuffer += text
    const lines = stdoutBuffer.split('\n')
    stdoutBuffer = lines.pop()
    for (const line of lines) {
      if (line.trim()) {
        try {
          const event = JSON.parse(line)
          if (event.event === 'ready') backendReadyReceived = true
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
      title: '小小下载器',
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
// 一键抓取浏览器 Cookie（运行 fetch_cookies.py --json <站点名>）
// ============================
// 供运行脚本用的系统 Python 查找（不复用 findPythonPath：打包模式下它返回的是后端 exe）
function findPythonForScript() {
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
    } catch (e) { /* where 找不到该命令，跳过 */ }
  }
  for (const p of candidates) {
    if (verifyPythonCandidate(p)) return p
  }
  return ''
}

const FETCH_SITE_NAMES = { twitter: 'X (Twitter)', exhentai: 'ExHentai', pawchive: 'Pawchive' }

ipcMain.handle('fetch-cookies', async (event, siteKey) => {
  const siteName = FETCH_SITE_NAMES[siteKey]
  if (!siteName) return { ok: false, error: '未知站点' }
  const root = getProjectRoot()
  const script = path.join(root, 'fetch_cookies.py')
  if (!fs.existsSync(script)) {
    return { ok: false, error: '未找到 fetch_cookies.py（请确认文件在程序根目录）' }
  }
  const pythonExe = findPythonForScript()
  if (!pythonExe) {
    return { ok: false, error: '未找到 Python（新版加密 Cookie 需要它解密）。可右键管理员运行 抓取Cookie.bat，再把结果粘贴到登录框' }
  }
  try {
    const out = execFileSync(pythonExe, [script, '--json', siteName], {
      encoding: 'utf-8',
      timeout: 180000,
      windowsHide: true,
      cwd: root,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    })
    // 兼容个别库在 JSON 前打印提示行的情况：取最后一行以 { 开头的输出
    const jsonLine = out.trim().split(/\r?\n/).filter((l) => l.trim().startsWith('{')).pop()
    if (!jsonLine) return { ok: false, error: '抓取输出解析失败' }
    return JSON.parse(jsonLine)
  } catch (e) {
    debugLog(`fetch-cookies 执行失败: ${e.message}`)
    return { ok: false, error: `抓取执行失败: ${e.message}` }
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

// 打开文件（用系统默认程序）
ipcMain.handle('open-path', async (event, filePath) => {
  try {
    const result = await shell.openPath(filePath)
    return { ok: result === '', error: result }
  } catch (err) {
    return { ok: false, error: err.message }
  }
})

// 在文件管理器中定位文件
ipcMain.handle('show-in-folder', async (event, filePath) => {
  try {
    shell.showItemInFolder(filePath)
    return { ok: true }
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

app.on('window-all-closed', () => {
  debugLog('--- window-all-closed ---')
  if (pythonProcess) {
    try { pythonProcess.kill() } catch (e) {}
    pythonProcess = null
  }
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', () => {
  debugLog('--- before-quit ---')
  if (pythonProcess) {
    try { pythonProcess.kill() } catch (e) {}
    pythonProcess = null
  }
})

process.on('uncaughtException', (err) => {
  debugLog(`!!! 未捕获异常: ${err.message}`)
  debugLog(err.stack)
})
