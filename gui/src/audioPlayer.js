// ============================================================
// 音声播放器样板（全局单例，站点无关）——后续音声站的标准接入点
// ------------------------------------------------------------
// Audio 元素在模块层创建，不随组件卸载销毁（切站/返回列表后台续播）。
//
// 站点接入三步：
// 1. 构造音轨对象 track：
//    { title, src, fallbackSrc?, subtitleSrc?, subtitleText?, subExt?, raw? }
//    - src：可播音频地址；fallbackSrc：src 播放失败时自动重试的直链（可选）
//    - subtitleSrc：字幕文件地址（.lrc/.srt/.vtt/.txt），拉取自动本地代理优先
//      （音声站 API 普遍不放行应用源，<audio> 有 CORS 豁免而 fetch 没有，
//       需 App 启动时 setProxyPort(port) 注入本地媒体代理端口）
//    - subtitleText：已取到的字幕原文（与 subtitleSrc 二选一）
//    - subExt：字幕文件扩展名（如 'vtt'）——播放地址往往不含扩展名，解析格式
//      必须靠它，站点层务必带上
//    - raw：站点原始行对象（列表高亮比对用）
// 2. play(track, { queue: [track, ...], work })：
//    - queue：整张专辑的 track 快照（自动连播按它推进）
//    - work：作品级元信息（迷你条「回到作品」按钮用，站点自定义结构）
// 3. UI 绑定 playerState（可参考 AsmrView.vue 播放器 + AsmrMiniPlayer.vue 迷你条）；
//    字幕行建议放在进度条正上方（卡拉 OK 式）。
//
// 字幕发现：相似"文件树"结构（音频与字幕同目录同名）可直接用
// findSubtitleFor(file, files) 拿到字幕文件；其他结构自行解析后传 subtitleSrc。
// ============================================================
import { reactive } from 'vue'

const SUB_EXTS = ['lrc', 'srt', 'vtt', 'txt']

function loadVolume() {
  const v = Number(localStorage.getItem('player_volume') ?? localStorage.getItem('asmr_volume'))
  // 存过 100%/0 视同未设置，回落 50%（历史坑：100% 是旧默认值）
  return Number.isFinite(v) && v > 0 && v < 1 ? v : 0.5
}

function loadFlag(newKey, oldKey, fallback) {
  const v = localStorage.getItem(newKey) ?? localStorage.getItem(oldKey)
  return v == null ? fallback : v
}

function fmtTime(s) {
  s = Math.floor(s || 0)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export const playerState = reactive({
  track: null,         // 当前音轨 {title, src, fallbackSrc?, subtitleSrc?, subtitleText?, subExt?, raw?}
  queue: [],           // 播放队列（track 快照）
  work: null,          // 作品元信息（迷你条「回到作品」用）
  index: 0,            // 当前 track 在 queue 中的序号
  paused: true,
  currentTime: 0,
  duration: 0,
  timeText: '0:00 / 0:00',
  error: '',
  fallback: false,     // src 播放失败后已切 fallbackSrc 重试
  volume: loadVolume(),
  muted: loadFlag('player_muted', 'asmr_muted', false),
  subOn: loadFlag('player_sub_off', 'asmr_sub_off', '1') === '1',  // 字幕显示开关（默认开）
  subLines: [],        // [{t, text}] 时间轴升序
  subText: '',         // 当前字幕行
  subNext: '',         // 下一字幕行（预览，双行展示用）
  subStatus: '',       // ''=无任务 | loading | ready | none | error
  proxyPort: 0,        // 本地媒体代理端口（字幕 fetch 走它）
})

const audio = new Audio()
audio.preload = 'auto'
audio.volume = playerState.volume
audio.muted = playerState.muted

// ---------- 基础控制 ----------
export function setProxyPort(p) {
  playerState.proxyPort = p || 0
}

function applyVolume() {
  audio.volume = playerState.volume
  audio.muted = playerState.muted
}

export function setVolume(v) {
  v = Math.max(0, Math.min(1, Number(v) || 0))
  playerState.volume = v
  localStorage.setItem('player_volume', String(v))
  if (v > 0 && playerState.muted) {
    playerState.muted = false
    localStorage.setItem('player_muted', '0')
  }
  applyVolume()
}

export function toggleMute() {
  playerState.muted = !playerState.muted
  localStorage.setItem('player_muted', playerState.muted ? '1' : '0')
  applyVolume()
}

export function setSubOn(v) {
  playerState.subOn = !!v
  localStorage.setItem('player_sub_off', v ? '1' : '0')
}

export function togglePlay() {
  if (!playerState.track) return
  if (audio.paused) audio.play().catch(() => {})
  else audio.pause()
}

export function seekTo(sec) {
  if (!playerState.track) return
  const dur = Number.isFinite(audio.duration) && audio.duration ? audio.duration : playerState.duration
  if (!dur) return
  audio.currentTime = Math.max(0, Math.min(dur, Number(sec) || 0))
}

export function seekBy(dir, back = 5, fwd = 30) {
  if (!playerState.track) return
  seekTo((audio.currentTime || 0) + dir * (dir > 0 ? fwd : back))
}

export function playOffset(step) {
  const q = playerState.queue
  const target = playerState.index + step
  if (target < 0 || target >= q.length) return
  play(q[target], { queue: q, work: playerState.work })
}

export function stopPlayer() {
  audio.pause()
  audio.removeAttribute('src')
  audio.load()
  playerState.track = null
  playerState.queue = []
  playerState.work = null
  playerState.index = 0
  playerState.paused = true
  playerState.currentTime = 0
  playerState.duration = 0
  playerState.timeText = '0:00 / 0:00'
  playerState.error = ''
  playerState.fallback = false
  resetSubtitle('')
}

// ---------- 播放 ----------
export function play(track, opts = {}) {
  if (!track || !track.src) return
  playerState.queue = opts.queue && opts.queue.length ? opts.queue : [track]
  playerState.track = track
  playerState.work = opts.work || null
  playerState.index = Math.max(0, playerState.queue.indexOf(track))
  playerState.error = ''
  playerState.fallback = false
  applyVolume()
  audio.src = track.src
  audio.play().then(() => { playerState.paused = false }).catch(() => {
    // 自动播放受限（如未交互过）：保持暂停态，等用户点播放
    playerState.paused = true
  })
  loadSubtitle(track)
}

// ---------- 字幕 ----------
// 取扩展名（小写）；字幕解析必须用字幕「文件名」的扩展名——播放地址
// （/api/media/stream/{hash}）不含扩展名，用它会把 VTT/SRT 误当 LRC 解析成空
export function extOf(name) {
  const i = (name || '').lastIndexOf('.')
  return i >= 0 ? name.slice(i + 1).toLowerCase() : ''
}

// 基名：循环剥离扩展名链（音频 xxx.wav 配字幕 xxx.wav.vtt 是双层后缀，
// 只剥一层会导致两者基名不等而匹配失败）；纯字母数字且 ≤5 位才算扩展名，
// 避免误剥 "01.合唱版" 这类名字里的点
function baseName(name) {
  let s = String(name || '')
  for (;;) {
    const i = s.lastIndexOf('.')
    if (i <= 0) break
    const ext = s.slice(i + 1)
    if (ext.length > 5 || !/^[a-z0-9]+$/i.test(ext)) break
    s = s.slice(0, i)
  }
  return s
}

// 同目录 + 同基名的字幕文件；扩展名优先级 lrc > srt/vtt > txt。
// files 条目形态：{ title, path?, type? }（type 缺省视作普通文件，type==='audio' 跳过）
export function findSubtitleFor(file, files) {
  if (!file || !files || !Array.isArray(files)) return null
  const base = baseName(file.title)
  if (!base) return null
  let best = null
  let bestRank = SUB_EXTS.length
  for (const f of files) {
    if (f === file || f.type === 'audio') continue
    if ((f.path || '') !== (file.path || '')) continue
    if (baseName(f.title) !== base) continue
    const rank = SUB_EXTS.indexOf(extOf(f.title))
    if (rank >= 0 && rank < bestRank) { best = f; bestRank = rank }
  }
  return best
}

function resetSubtitle(status = '') {
  playerState.subLines = []
  playerState.subText = ''
  playerState.subNext = ''
  playerState.subStatus = status
}

// utf-8 优先，出现替换符则按 gbk 重解（部分 LRC 为 GBK 编码）
function decodeText(buf) {
  const utf8 = new TextDecoder('utf-8').decode(buf)
  if (!utf8.includes('\uFFFD')) return utf8
  try { return new TextDecoder('gbk').decode(buf) } catch { return utf8 }
}

let subToken = 0
async function loadSubtitle(track) {
  resetSubtitle('')
  if (!track) return
  if (track.subtitleText) {
    // 站点已自行取到字幕原文
    const lines = parseSub(track.subtitleText, track.subExt || '')
    if (lines.length) {
      playerState.subLines = lines
      playerState.subStatus = 'ready'
      updateSubIndex(audio.currentTime || 0)
    } else {
      playerState.subStatus = 'none'
    }
    return
  }
  const direct = track.subtitleSrc || ''
  if (!direct) { playerState.subStatus = 'none'; return }
  const token = ++subToken
  playerState.subStatus = 'loading'
  // 本地代理优先（绕开音声站 API 的 CORS 限制），失败回退直链
  const viaProxy = playerState.proxyPort
    ? `http://127.0.0.1:${playerState.proxyPort}/media?url=${encodeURIComponent(direct)}`
    : ''
  let text = ''
  for (const url of [viaProxy, direct].filter(Boolean)) {
    try {
      const resp = await fetch(url)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      text = decodeText(await resp.arrayBuffer())
      break
    } catch { /* 试下一个来源 */ }
  }
  if (token !== subToken) return   // 加载期间已切歌
  // 扩展名优先取站点从字幕文件名带来的 subExt（地址里没有扩展名）
  const lines = parseSub(text, track.subExt || extOf(track.subtitleSrc))
  if (!lines.length) { playerState.subStatus = 'none'; return }
  playerState.subLines = lines
  playerState.subStatus = 'ready'
  updateSubIndex(audio.currentTime || 0)
}

function parseLrc(text) {
  const out = []
  for (const raw of (text || '').split(/\r?\n/)) {
    const tags = [...raw.matchAll(/\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\]/g)]
    if (!tags.length) continue
    const content = raw.replace(/\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\]/g, '').trim()
    if (!content) continue
    for (const m of tags) {
      const t = parseInt(m[1], 10) * 60 + parseInt(m[2], 10)
        + (m[3] ? parseInt(m[3].padEnd(3, '0'), 10) / 1000 : 0)
      out.push({ t, text: content })
    }
  }
  out.sort((a, b) => a.t - b.t)
  return out
}

function parseCueTime(s) {
  const m = String(s || '').trim().match(/^(?:(\d{1,2}):)?(\d{1,2}):(\d{1,2})[.,](\d{1,3})/)
  if (!m) return -1
  return (m[1] ? parseInt(m[1], 10) * 3600 : 0) + parseInt(m[2], 10) * 60
    + parseInt(m[3], 10) + parseInt(m[4].padEnd(3, '0'), 10) / 1000
}

function parseSrtVtt(text) {
  const out = []
  for (const block of (text || '').replace(/\r\n/g, '\n').split(/\n\n+/)) {
    const ls = block.split('\n').filter(l => l.trim())
    const ti = ls.findIndex(l => l.includes('-->'))
    if (ti < 0) continue
    const t = parseCueTime(ls[ti].split('-->')[0])
    if (t < 0) continue
    const content = ls.slice(ti + 1).join('\n').replace(/<[^>]+>/g, '').trim()
    if (content) out.push({ t, text: content })
  }
  out.sort((a, b) => a.t - b.t)
  return out
}

function parseSub(text, ext) {
  const lines = (ext === 'srt' || ext === 'vtt') ? parseSrtVtt(text) : parseLrc(text)
  // .txt 仅当像字幕（≥2 条时间轴）才采用，避免把 readme 当对白
  const min = ext === 'txt' ? 2 : 1
  return lines.length >= min ? lines : []
}

function updateSubIndex(t) {
  const ls = playerState.subLines
  if (!ls.length) { playerState.subText = ''; playerState.subNext = ''; return }
  let idx = -1
  for (let i = 0; i < ls.length; i++) {
    if (ls[i].t <= t) idx = i
    else break
  }
  if (idx >= 0) {
    // 当前行 + 下一行（双行展示；间隙时当前行驻留，直到下一行时间到）
    playerState.subText = ls[idx].text
    playerState.subNext = ls[idx + 1] ? ls[idx + 1].text : ''
  } else {
    // 尚未进入第一条：当前行空占位，下一行预览第一条
    playerState.subText = ''
    playerState.subNext = ls[0].text
  }
}

// ---------- Audio 事件（模块级挂一次） ----------
audio.addEventListener('play', () => { playerState.paused = false })
audio.addEventListener('pause', () => { playerState.paused = true })
audio.addEventListener('loadedmetadata', () => { playerState.duration = audio.duration || 0 })
// 音频流在 Range 拖动后浏览器会重估时长，必须同步，否则出现 4:07/3:20 的错乱显示
audio.addEventListener('durationchange', () => {
  if (Number.isFinite(audio.duration)) playerState.duration = audio.duration
})
audio.addEventListener('timeupdate', () => {
  playerState.currentTime = audio.currentTime || 0
  playerState.timeText = `${fmtTime(audio.currentTime)} / ${fmtTime(audio.duration)}`
  updateSubIndex(audio.currentTime || 0)
})
audio.addEventListener('ended', () => {
  if (playerState.index < playerState.queue.length - 1) playOffset(1)
})
audio.addEventListener('error', () => {
  const t = playerState.track
  // 首选地址失败：回退直链自动重试一次
  if (t && !playerState.fallback && t.fallbackSrc && t.src !== t.fallbackSrc) {
    playerState.fallback = true
    playerState.error = '代理播放失败，已切换直连重试'
    audio.src = t.fallbackSrc
    audio.play().then(() => { playerState.paused = false }).catch(() => {})
  } else {
    playerState.error = '播放失败，可右键该音轨直接下载'
  }
})

export { fmtTime }
