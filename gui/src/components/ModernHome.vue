<template>
  <!-- 热门平台主界面：与经典下载器完全不同的一套界面与风格（亮色渐变 / 磁贴 / 卡片）。
       选平台 → 内嵌浏览器（persist:hotplatform 会话，登录持久）+ 右侧实时捕获媒体列表，
       捕获引擎复用手动抓取（webRequest，scope=hot），下载复用后端 sniff_download 通用管线。 -->
  <div class="mh-root">
    <!-- 顶栏 -->
    <header class="mh-header">
      <div class="mh-brand">
        <span class="mh-logo">🔥</span>
        <div class="mh-brand-txt">
          <div class="mh-title">热门平台</div>
          <div class="mh-sub">浏览即抓取 · 视频图片一键下载</div>
        </div>
      </div>
      <div class="mh-header-right">
        <span class="mh-capture-pill" :class="{ live: items.length }">
          <span class="mh-pill-dot" /> 已捕获 {{ items.length }} 条
        </span>
        <button class="mh-help-btn" title="查看下载任务与保存位置" @click="openDownloads()">📥 下载管理</button>
        <button class="mh-help-btn" title="粘贴磁力链接或 .torrent 地址用 aria2 内核下载；磁力站页面直接点磁力链接也会弹出下载"
                @click="btPromptSubmit">🧲 BT 下载</button>
        <button class="mh-help-btn" :disabled="updChecking || updDownloading"
                :title="`检查并安装新版本（当前 v${updCurrent || '…'}）`"
                @click="checkUpdate">{{ updChecking ? '检查中…' : (updHasNew ? '⬇ 有新版' : '⬇ 检查更新') }}</button>
        <button class="mh-help-btn" :class="{ 'mh-btn-on': updAuto }"
                :title="`自动检查更新：${updAuto ? '开（启动时自动检查 GitHub 新版本）' : '关'}`"
                @click="updAuto = !updAuto; message.info(updAuto ? '已开启自动检查更新（每次启动检查一次）' : '已关闭自动检查更新')">{{ updAuto ? '⏰ 自动更新 开' : '⏰ 自动更新 关' }}</button>
        <button class="mh-help-btn" :disabled="syncing"
                title="从 GitHub 校验源强制重新同步站点可用性（官方发布页 / 每日检测表 / 书源端点）"
                @click="syncSites">{{ syncing ? '同步中…' : '🔄 同步站点' }}</button>
        <button class="mh-help-btn" :class="{ 'mh-btn-on': hideDead }"
                :title="`隐藏/显示已失效站点（当前失效 ${deadCount} 个，偏好自动记住）`"
                @click="toggleHideDead">{{ hideDead ? '👁 显示失效' : '🙈 隐藏失效' }}</button>
        <button class="mh-help-btn" title="全部站点分类说明（特点/风险/换域名方法）" @click="openHelp('surface-sites.html')">🌐 站点</button>
        <button class="mh-help-btn" title="软件使用导览（可视化说明）" @click="openHelp('software-guide.html')">📖 说明</button>
        <button class="mh-help-btn" title="本次更新可视化说明（v1.2.59 BT下载 / X站四件套 / 自动更新）" @click="openHelp('changelog-20260919.html')">📜 更新</button>
        <button class="mh-restart-btn" title="还原网络设置并重启应用（界面模式保持；登录卡死/网络异常时使用）"
                @click="restartApp">🔄 重启应用</button>
      </div>
    </header>

    <!-- 内容区：浏览态必须常驻挂载。webview 一旦被 v-if 卸载，Chromium 会销毁
         guest 页面 —— 从下载管理返回时就会整页重载、视频从头重缓冲（用户痛点）。 -->
    <div class="mh-body">

    <!-- 首页：平台磁贴 -->
    <div v-if="!active && !showDownloads" class="mh-home">
      <div class="mh-hero">
        <div class="mh-hero-title">选一个平台开始</div>
        <div class="mh-hero-sub">正常网站模式 —— 打开平台后，刷到的视频 / 图片会实时出现在右侧，点下载即可保存</div>
      </div>
      <div class="mh-cats">
        <button v-for="c in catChips" :key="c.key" class="mh-cat" :class="{ on: activeCat === c.key }" @click="switchCat(c.key)">
          {{ c.label }}
        </button>
      </div>
      <div v-if="subChips.length" class="mh-cats mh-subcats">
        <button class="mh-cat mh-subcat" :class="{ on: !activeSub }" @click="activeSub = null">全部</button>
        <button v-for="s in subChips" :key="s.key" class="mh-cat mh-subcat" :class="{ on: activeSub === s.key }" @click="activeSub = s.key">
          {{ s.label }}
        </button>
      </div>
      <div class="mh-tiles">
        <button
          v-for="p in visiblePlatforms"
          :key="p.key"
          class="mh-tile"
          :class="{ dead: p.invalid, slot: !p.home && !p.invalid }"
          :style="{ '--p1': visualOf(p).c1, '--p2': visualOf(p).c2 }"
          :title="tileTip(p)"
          @click="openPlatform(p)"
        >
          <span v-if="p.invalid" class="mh-tile-proxy mh-tile-dead-tag" title="GitHub 校验表标记已失效">已失效</span>
          <span v-else-if="!p.home" class="mh-tile-proxy mh-tile-slot-tag" title="地址待 GitHub 校验表下发">待补地址</span>
          <span v-else-if="p.proxy" class="mh-tile-proxy" title="需系统代理才能访问">需代理</span>
          <span class="mh-tile-icon" v-html="visualOf(p).svg" />
          <span class="mh-tile-name">{{ p.name }}</span>
          <span class="mh-tile-desc">{{ p.desc }}</span>
        </button>
      </div>
      <div class="mh-foot-hint">
        内置浏览器会记住各平台登录状态；媒体下载走通用下载管线（可在下载管理暂停/续传）；
        站点可用性由 GitHub 校验表自动校准（失效站点会置灰并下发新地址）
      </div>
    </div>

    <!-- 下载管理视图（覆盖层：盖在浏览态之上）。不销毁 webview，因此返回时
         播放中的视频不会重新缓存重播，回到浏览态即无缝接续。 -->
    <div v-if="showDownloads" class="mh-dlview mh-dl-overlay">
      <div class="mh-dl-head">
        <button class="mh-nav-btn" :title="canGoBack() ? '返回上一个界面（不中断播放）' : '返回平台选择'" @click="goBack">↩</button>
        <span class="mh-dl-title">下载管理</span>
        <span class="mh-dl-sub">仅记录本界面的下载</span>
        <span class="mh-save-pill" :title="surfaceSavePath || '默认保存到系统下载文件夹；点「修改」可选其他目录，新任务即时生效'">📁 保存位置：{{ surfaceSavePath || '默认（用户下载夹）' }}</span>
        <button class="mh-mini" title="修改表世界下载保存位置（新任务即时生效）" @click="pickSaveDir">修改</button>
        <n-checkbox v-model:checked="delFiles" class="mh-del-chk"
                    title="勾选后，点「清除记录」会连同任务对应的本地文件一起删除（首次使用会二次确认，偏好自动记住）">同时删除本地文件</n-checkbox>
        <button class="mh-nav-btn" style="margin-left:auto" :title="canGoBack() ? '返回上一个界面（不中断播放）' : '返回平台选择'" @click="goBack">⊞</button>
      </div>
      <div class="mh-dl-body">
        <div v-if="!surfaceTasks.length" class="mh-empty">
          <div class="mh-empty-icon">📭</div>
          <div class="mh-empty-t1">还没有下载记录</div>
          <div class="mh-empty-t2">在平台里下载的视频 / 图片会记录在这里</div>
        </div>
        <div v-for="t in surfaceTasks" :key="t.id" class="mh-task">
          <div class="mh-task-main">
            <div class="mh-task-name">{{ t.album || '下载任务' }}
              <n-tag v-if="t.status === 'completed'" size="tiny" type="success" round>已完成</n-tag>
              <n-tag v-else-if="t.status === 'running'" size="tiny" type="info" round>下载中</n-tag>
              <n-tag v-else-if="t.status === 'paused'" size="tiny" round>已暂停</n-tag>
              <n-tag v-else-if="t.status === 'failed'" size="tiny" type="error" round>失败</n-tag>
              <n-tag v-else size="tiny" round>{{ statusText(t.status) }}</n-tag>
            </div>
            <div class="mh-task-meta">
              {{ t.save_dir || '系统下载文件夹' }} · {{ taskProgressText(t) }}
            </div>
            <div v-if="t.status === 'running' || t.status === 'paused'" class="mh-task-bar">
              <span class="mh-task-bar-fill" :style="{ width: taskPercent(t) + '%' }"></span>
            </div>
          </div>
          <button v-if="t.status === 'running'" class="mh-mini" title="暂停（已下载的分片保留，可续传）"
                  @click="taskCmd('pause_task', t.id)">暂停</button>
          <button v-else-if="t.status === 'paused'" class="mh-mini" title="从断点继续下载"
                  @click="taskCmd('resume_task', t.id)">继续</button>
          <button v-else-if="t.status === 'failed'" class="mh-mini" title="重试（从断点继续，不重下已有分片）"
                  @click="taskCmd('retry_task', t.id)">重试</button>
          <button class="mh-dl" @click="openTaskFolder(t)">打开文件夹</button>
          <button class="mh-mini" @click="clearRecord(t.id)">清除记录</button>
        </div>
      </div>
    </div>

    <!-- 浏览态：左浏览器 + 右捕获列表（常驻挂载：切到下载管理也不卸载，播放不中断） -->
    <div v-if="active" class="mh-work">
      <div class="mh-browser">
        <div class="mh-nav">
          <button class="mh-nav-btn mh-home-btn" title="返回平台选择" @click="closePlatform">🏠</button>
          <button class="mh-nav-btn" title="后退" @click="nav('back')">←</button>
          <button class="mh-nav-btn" title="前进" @click="nav('forward')">→</button>
          <button class="mh-nav-btn" title="刷新" @click="nav('reload')">↻</button>
          <button class="mh-nav-btn" title="回到平台首页" @click="nav('home')">🏠</button>
          <input
            v-model="addressDraft"
            class="mh-address"
            :placeholder="`在 ${active.name} 里随便刷，媒体会自动出现在右侧`"
            @keyup.enter="navigateAddress"
          >
          <button class="mh-nav-btn" :disabled="exportingWord"
                  title="存当前页为 Word（文字/表格/图片按原位置）" @click="exportPageWord">{{ exportingWord ? '⏳' : '📄' }}</button>
          <span class="mh-platform-chip" :style="{ background: active.c1 }">{{ active.name }}</span>
        </div>
        <div class="mh-stage">
          <webview
            ref="wvRef"
            :src="wvSrc"
            partition="persist:hotplatform"
            :useragent="wvUserAgent"
            allowpopups
            class="mh-webview"
            @did-navigate="onNav"
            @did-navigate-in-page="onNav"
            @did-start-loading="loading = true"
            @did-stop-loading="loading = false"
          />
          <div v-if="loading" class="mh-loading-bar" />
        </div>
      </div>

      <aside class="mh-list">
        <!-- B站专属解析卡：进入 B站视频页自动页内解析（登录态/清晰度/音视频分离） -->
        <div v-if="bili.visible" class="mh-bili" :class="{ loading: bili.loading }">
          <div class="mh-bili-head">
            <span class="mh-bili-badge">B站解析</span>
            <span v-if="bili.loading" class="mh-bili-state">解析中…</span>
            <span v-else-if="bili.error" class="mh-bili-err">{{ bili.error }}</span>
            <span v-else class="mh-bili-owner">{{ bili.owner }}</span>
            <button class="mh-mini" @click="bili.visible = false">收起</button>
          </div>
          <template v-if="!bili.loading && !bili.error">
            <div class="mh-bili-title" :title="bili.title">{{ bili.title }}</div>
            <div v-if="(bili.pages || []).length > 1" class="mh-bili-pages">
              <button
                v-for="(pg, i) in bili.pages"
                :key="pg.cid"
                class="mh-p-chip"
                :class="{ on: bili.pageIdx === i }"
                :title="pg.part"
                @click="bili.pageIdx = i"
              >P{{ pg.page }}</button>
            </div>
            <div class="mh-bili-row">
              <span class="mh-bili-label">清晰度</span>
              <select v-model="bili.qualityId" class="mh-bili-select">
                <option v-for="q in bili.qualities" :key="q.id" :value="q.id">
                  {{ q.label }}（{{ q.sizeText }}）
                </option>
              </select>
            </div>
            <div class="mh-bili-row">
              <span class="mh-bili-label">音频</span>
              <span class="mh-bili-audio">{{ bili.audioLabel }}</span>
            </div>
            <div class="mh-bili-actions">
              <button class="mh-dl" @click="downloadBili('merge')">下载 MP4（音视频合并）</button>
              <button class="mh-mini" @click="downloadBili('video')">仅视频</button>
              <button class="mh-mini" @click="downloadBili('audio')">仅音频</button>
            </div>
          </template>
        </div>

        <div class="mh-list-head">
          <span class="mh-list-title">实时捕获</span>
          <div class="mh-filters">
            <button
              v-for="f in FILTERS"
              :key="f.k"
              class="mh-filter"
              :class="{ on: filter === f.k }"
              @click="filter = f.k"
            >{{ f.label }} {{ countOf(f.k) }}</button>
          </div>
          <select v-model="sortKey" class="mh-sort">
            <option value="media">媒体优先</option>
            <option value="time">最新捕获</option>
            <option value="type">按类型</option>
            <option value="size">按大小</option>
            <option value="duration">按时长</option>
          </select>
          <button class="mh-act" :disabled="!filtered.length" @click="downloadAll">全部下载</button>
          <button class="mh-act ghost" :disabled="!items.length && !segTotal" @click="clearAll">清空</button>
          <button class="mh-act ghost" title="把当前网页（文字/表格/图片按原位置）导出为 Word 文档" @click="exportPageWord">📄 存为 Word</button>
        </div>
        <div class="mh-list-body">
          <div v-if="!filtered.length" class="mh-empty">
            <div class="mh-empty-icon">📡</div>
            <div class="mh-empty-t1">{{ filter === 'hlsseg' ? '还没有抓到分片' : '等一条视频刷出来' }}</div>
            <div class="mh-empty-t2">
              {{ filter === 'hlsseg'
                ? 'HLS 播放器的 TS 分片会归到这里（默认不混进主列表，避免把正片挤下去）'
                : '在左侧浏览/播放，媒体链接会实时落到这里' }}
            </div>
          </div>
          <div v-for="it in filtered" :key="it.url" class="mh-item"
               :class="{ done: downloaded.has(it.url), ad: it.verdict === 'ad' }">
            <img v-if="it.type === 'image'" class="mh-thumb" :src="it.url" loading="lazy" referrerpolicy="no-referrer" @error="onThumbErr" />
            <span v-else class="mh-badge" :class="'b-' + it.type">{{ typeLabel(it.type) }}</span>
            <div class="mh-item-main">
              <div class="mh-item-name" :title="it.url">{{ it.filename }}</div>
              <div class="mh-item-meta">
                <!-- 智能判决徽标：后端读播放清单判正片/广告，鼠标悬停给判定依据 -->
                <span v-if="it.verdict" class="mh-v" :class="'v-' + it.verdict"
                      :title="verdictTip(it)">{{ verdictLabel(it.verdict) }}</span>
                {{ hostOf(it.url) }}<template v-if="it.size"> · {{ fmtSize(it.size) }}</template><template v-if="it.durationText"> · ⏱ {{ it.durationText }}</template><template v-if="it.segCount"> · {{ it.segCount }} 片</template>
                <template v-if="hlsBusy.get(it.url)"> · ⏳ {{ hlsBusy.get(it.url) }}</template>
              </div>
              <div v-if="it.verdict === 'ad' && it.probeReasons && it.probeReasons.length"
                   class="mh-ad-why">判定依据：{{ it.probeReasons.slice(0, 2).join('；') }}</div>
              <div v-else-if="it.probeNote" class="mh-ad-note">{{ it.probeNote }}</div>
            </div>
            <!-- HLS：「下载整片」提交为下载任务（分片落盘下载、可暂停续传、下载管理里看进度） -->
            <button v-if="it.type === 'hls'" class="mh-dl"
                    title="下载整片：加入下载管理，分片下载完成后自动合并为 MP4（可暂停/继续/重试）"
                    :disabled="hlsBusy.has(it.url)" @click="downloadOne(it)">
              {{ hlsBusy.has(it.url) ? '提交中…' : (it.verdict === 'ad' ? '仍要下载' : '下载整片') }}
            </button>
            <button v-else class="mh-dl" title="下载" @click="downloadOne(it)">下载</button>
            <button class="mh-mini" title="复制链接" @click="copyOne(it.url)">复制</button>
          </div>
        </div>
      </aside>
    </div>

    </div><!-- /.mh-body -->

    <!-- BT 下载弹窗：替代 window.prompt（Electron 不支持 prompt，调用会静默失败） -->
    <n-modal v-model:show="btShow" preset="dialog" title="🧲 BT 下载（磁力链接 / 种子）" style="width: 580px">
      <div class="mh-bt-body">
        <n-input v-model:value="btText" type="textarea" :rows="6"
                 placeholder="每行一条磁力链接（magnet:?xt=urn:btih:…）或 .torrent 种子地址，支持多行批量" />
        <div class="mh-bt-drop" @dragover.prevent @drop.prevent="onBtDrop">
          🧲 把 .torrent 种子文件拖到这里提交（可多个）
        </div>
        <div class="mh-bt-foot">
          <label class="mh-bt-auto" title="开启后，在网页里点磁力链接不再弹确认，直接加入下载">
            <n-switch v-model:value="btAuto" size="small" />
            自动接管磁力链接
          </label>
          <n-button type="primary" @click="submitBtBatch">批量下载</n-button>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, onUnmounted, nextTick, watch } from 'vue'
import { NButton, NCheckbox, NInput, NModal, NSwitch, NTag, useMessage } from 'naive-ui'
// 站点注册表（唯一数据源）：分类/说明/图标兜底/GitHub 校验合并都在 surfaceSites.js
import { PLATFORMS as PLATFORM_BASELINE, BUNDLED_REGISTRY, mergeRegistry, tileVisual, visibleCategories, visibleSubs, freqSites, trackSiteClick } from '../surfaceSites.js'

const message = useMessage()

// 界面切换已改为「连按 3 次 Alt」（App.vue 全局手势），本组件不再展示切换按钮

// 平台磁贴 = 随包兜底校验表 → 上游 GitHub 同步结果覆盖（agefans 发布页/影视每日检测/
// 书源端点自动验证）：ok 下发新地址、dead 置灰、extra 动态补新站、空位站有地址才显示
const platforms = ref(mergeRegistry(PLATFORM_BASELINE, BUNDLED_REGISTRY).sites)

const FILTERS = [
  { k: 'all', label: '全部' },
  { k: 'video', label: '视频' },
  { k: 'image', label: '图片' },
  { k: 'doc', label: '文档' },
  { k: 'archive', label: '压缩包' },
  { k: 'audio', label: '音频' },
  { k: 'hls', label: '视频流' },
  { k: 'hlsseg', label: '分片' },
]

const active = ref(null)
const addressDraft = ref('')
const currentUrl = ref('')
const loading = ref(false)
const wvRef = ref(null)
const items = ref([])
// TS/m4s 分片单列：HLS 播放器一个视频要请求上百个分片，混进 items 会把真正的正片
// （m3u8 那一条）挤出 MAX_ITEMS 上限被截掉 —— 这才是「找不到要下的视频」的主因。
// 这里只留前 SEG_KEEP 条备查（「分片」筛选），总数单独计数保证计数准确。
const segItems = ref([])
const segTotal = ref(0)
const SEG_KEEP = 50
const filter = ref('all')
const downloaded = ref(new Set())
const MAX_ITEMS = 500
// 截尾一次性提醒：首次触发截尾时弹一次（之后静默截断，不刷屏）
let truncatedHinted = false

// ---- 视图返回栈：浏览态 → 下载管理 → 返回仍回到刚才浏览的平台与页面 ----
// 关键改动：下载管理现在是「覆盖层」（showDownloads），浏览态的 webview 全程保持挂载。
// 以前用 active='downloads' 切走会把 <webview> 从 DOM 卸载 → Chromium 销毁 guest 页面，
// 返回时整页重载、正在播放的视频从头重缓冲（"返回一下就要重新缓存重新播放"）。
// 实测覆盖层能盖住 webview 且不打断播放（_research/_keepalive_probe.cjs）。
// viewStack: [{kind:'home'} | {kind:'platform', key}]；wvSrc 单独维护。
const viewStack = ref([])
const showDownloads = ref(false)
const wvSrc = ref('')
const lastUrlByKey = ref({})
function openDownloads() {
  if (showDownloads.value) return      // 已在下载管理：重复点不再叠栈
  viewStack.value.push(active.value ? { kind: 'platform', key: active.value.key } : { kind: 'home' })
  showDownloads.value = true
}
function canGoBack() { return viewStack.value.length > 0 }
function goBack() {
  const prev = viewStack.value.pop()
  showDownloads.value = false          // 收起覆盖层：浏览态从未卸载，无需重建/重载
  if (!prev || prev.kind === 'home') {
    closePlatform()                    // 从首页进的下载管理：返回即回首页
    return
  }
  const p = platforms.value.find(x => x.key === prev.key)
  if (!p) { closePlatform(); return }
  if (active.value !== p) {            // 兜底：正常路径不会走到（webview 一直活着）
    active.value = p
    wvSrc.value = lastUrlByKey.value[p.key] || p.home
    window.api && window.api.hotCaptureAttach && window.api.hotCaptureAttach()
  }
}

// webview UA：去 Electron 标记（抖音/B站等会校验）
const wvUserAgent = (navigator.userAgent || '').replace(/\sElectron\/[\d.]+/i, '').trim()

const sortKey = ref('media')
// 媒体优先：视频/音频/文档/压缩包排在页面装饰图片之前。图片动辄几十张（缩略图还很显眼），
// 会把唯一那条视频/流压到列表底部，用户于是以为"根本没抓到"。
const TYPE_RANK = { video: 0, hls: 0, audio: 1, doc: 2, archive: 3, hlsseg: 7, other: 8, image: 9 }
// 同类里再按判决排：正片 < 存疑 < 未判定 < 疑似广告。
// 广告沉底是重点——一个页面常同时抓到正片清单和贴片广告清单，按原来的「最新捕获在前」
// 排序，后到的广告会顶掉正片的位置，用户很容易点错。
function verdictRank(it) {
  if (it.verdict === 'content') return 0
  if (it.verdict === 'unknown') return 1
  if (it.verdict === 'ad') return 3
  return 2
}
const filtered = computed(() => {
  let list
  if (filter.value === 'hlsseg') list = segItems.value.slice()
  else if (filter.value === 'all') list = items.value.slice()
  else list = items.value.filter(i => i.type === filter.value)
  if (sortKey.value === 'size') list.sort((a, b) => (b.size || 0) - (a.size || 0))
  else if (sortKey.value === 'duration') list.sort((a, b) => (b.duration || 0) - (a.duration || 0))
  else if (sortKey.value === 'type') list.sort((a, b) => (a.type || '').localeCompare(b.type || ''))
  else if (sortKey.value === 'media') list.sort((a, b) => {
    const ra = TYPE_RANK[a.type] === undefined ? 8 : TYPE_RANK[a.type]
    const rb = TYPE_RANK[b.type] === undefined ? 8 : TYPE_RANK[b.type]
    if (ra !== rb) return ra - rb
    const va = verdictRank(a)
    const vb = verdictRank(b)
    return va === vb ? (b.ts || 0) - (a.ts || 0) : va - vb
  })
  else list.sort((a, b) => (b.ts || 0) - (a.ts || 0))  // 最新捕获在前
  return list
})

function countOf(t) {
  if (t === 'all') return items.value.length
  if (t === 'hlsseg') return segTotal.value   // 分片只留前 SEG_KEEP 条，计数用总数
  return items.value.filter(i => i.type === t).length
}
function typeLabel(t) {
  return { video: '视频', audio: '音频', image: '图片', hls: '视频流', hlsseg: '分片', doc: '文档', archive: '压缩包' }[t] || '其他'
}
// ---- 智能判决（后端 hls_probe 回流）：content=正片 / unknown=存疑 / ad=疑似广告 ----
// 判定依据完全来自播放清单本身：#EXTINF 求时长（广告 15/30 秒）+ SCTE-35 广告插播
// 标记 + 地址广告特征词 + 分片数/清晰度，综合打分（详见 bridge/webcapture.py）。
function verdictLabel(v) {
  return { content: '正片', ad: '疑似广告', unknown: '存疑' }[v] || ''
}
function verdictTip(it) {
  const head = {
    content: '识别为正片',
    ad: '识别为疑似广告（「全部下载」会自动跳过它）',
    unknown: '无法确定是正片还是广告',
  }[it.verdict] || ''
  const lines = []
  if (it.durationText) lines.push(`时长：${it.durationText}`)
  if (it.segCount) lines.push(`分片：${it.segCount} 段`)
  const why = (it.probeReasons || []).join('；')
  if (why) lines.push(`依据：${why}`)
  if (it.probeNote) lines.push(`注意：${it.probeNote}`)
  return [head].concat(lines).filter(Boolean).join('\n')
}
// 时长文案（与后端 web_hls_fmt_dur 同规格，列表里显示风格一致）
function fmtDur(sec) {
  const s = Math.round(Number(sec) || 0)
  if (s <= 0) return ''
  if (s >= 3600) return `${Math.floor(s / 3600)} 小时 ${Math.floor((s % 3600) / 60)} 分`
  if (s >= 60) return `${Math.floor(s / 60)} 分 ${s % 60} 秒`
  return `${s} 秒`
}
function hostOf(u) {
  try { return new URL(u).hostname } catch (e) { return '' }
}
function fmtSize(n) {
  if (!n || n <= 0) return ''
  if (n >= 1024 ** 2) return (n / 1024 ** 2).toFixed(1) + ' MB'
  if (n >= 1024) return (n / 1024).toFixed(0) + ' KB'
  return n + ' B'
}
function filenameFromUrl(u) {
  try {
    const p = new URL(u).pathname.split('/').filter(Boolean).pop() || ''
    const name = decodeURIComponent(p)
    return name.length > 80 ? name.slice(-80) : (name || '')
  } catch (e) { return '' }
}

// 「识别到正片」提示只弹一次（不逐条刷屏）；抓到广告流不弹，列表里标出来即可
let contentHinted = false
function addItem(data) {
  if (!data || !data.url || data.scope !== 'hot') return   // 只收热门平台会话的捕获
  // TS/m4s 分片单列（见 segItems 处说明）：不入主列表、不探测时长，只计数 + 留前
  // SEG_KEEP 条供「分片」筛选查看。分片只有几秒，逐条 ffprobe 纯属浪费。
  if ((data.type || '') === 'hlsseg') {
    segTotal.value++
    if (segItems.value.length < SEG_KEEP && !segItems.value.some(i => i.url === data.url)) {
      segItems.value.push(newItem(data, 'hlsseg'))
    }
    return
  }
  if (items.value.some(i => i.url === data.url)) return
  items.value.unshift(newItem(data, data.type || 'other'))
  if ((data.type || '') === 'video') {
    // 普通 mp4 直链：时长只能靠 ffprobe 远程读（结果经 duration_result 回流）
    window.api && window.api.sendCommand({
      cmd: 'probe_duration', url: data.url, referer: currentUrl.value || '',
    })
  }
  if ((data.type || '') === 'hls') {
    // HLS 不调 ffprobe：后端直接读播放清单 #EXTINF 求和（毫秒级、精确），
    // 并顺带判定这一条是正片还是广告（结果经 hls_probe_result 回流）。
    // 很多站的视频分片被伪装成图片（无扩展名 / content-type=image/*），网络层根本
    // 抓不到分片，只有 m3u8 清单是唯一可辨认的线索 —— 所以清单就是「正片」入口。
    window.api && window.api.sendCommand({
      cmd: 'hls_probe', url: data.url, referer: currentUrl.value || '',
    })
  }
  if (items.value.length > MAX_ITEMS) {
    items.value.length = MAX_ITEMS
    if (!truncatedHinted) {
      truncatedHinted = true
      message.info('捕获已超过 500 条，早前的条目已被移除；需要的话请及时下载或用「复制全部」备份', { duration: 6000 })
    }
  }
}
function newItem(data, type) {
  return {
    url: data.url,
    type,
    size: data.size || 0,
    page_url: data.page_url || '',
    ts: data.ts || Date.now(),
    filename: filenameFromUrl(data.url) || hostOf(data.url),
    duration: 0, durationText: '',
    // 智能判决字段（hls_probe_result 回流填充）
    verdict: '', probeReasons: [], probeNote: '', segCount: 0,
  }
}

const activeCat = ref('all')
const activeSub = ref(null)
// 分类 chips 动态化：空分类自动隐藏；二级分类同理（细分板块规格）
const catChips = computed(() => visibleCategories(platforms.value))
const subChips = computed(() => visibleSubs(activeCat.value, platforms.value))
function switchCat(key) {
  activeCat.value = key
  activeSub.value = null
}
// 隐藏失效站开关（localStorage 记住偏好）
const hideDead = ref(localStorage.getItem('mh_hide_dead') === '1')
const deadCount = computed(() => platforms.value.filter(p => p.invalid).length)
function toggleHideDead() {
  hideDead.value = !hideDead.value
  try { localStorage.setItem('mh_hide_dead', hideDead.value ? '1' : '0') } catch (e) { /* 隐私模式 */ }
}
const visiblePlatforms = computed(() => {
  let list
  if (activeCat.value === 'all') list = platforms.value
  else if (activeCat.value === 'freq') list = freqSites(platforms.value)  // 常用：预设 Top15 + 点击累计
  else {
    list = platforms.value.filter(p => (p.cats || []).includes(activeCat.value))
    if (activeSub.value) list = list.filter(p => (p.subs || []).includes(activeSub.value))
  }
  if (hideDead.value) list = list.filter(p => !p.invalid)
  return list
})

// 磁贴视觉/悬浮说明（图标与配色：站点专属 → 分类兜底）
function visualOf(p) { return tileVisual(p) }
function tileTip(p) {
  const lines = [`${p.name} — ${p.desc}`, p.tip || '']
  if (p.invalid) lines.push(`⛔ GitHub 校验表标记已失效${p.invalidNote ? '：' + p.invalidNote : ''}`)
  else if (!p.home) lines.push('⏳ 地址待定：GitHub 校验表下发后自动点亮')
  else if (p.proxy) lines.push('🛰 需开启系统代理访问')
  if (p.alts && p.alts.length) lines.push(`备用地址：${p.alts.join('  ')}`)
  if (p.publish) lines.push(`发布页：${p.publish}`)
  return lines.filter(Boolean).join('\n')
}

const surfaceTasks = ref([])

// ---- 保存位置显示/修改 + 「同时删除本地文件」偏好 ----
// surface_save_path 留空 = 后端默认落用户下载夹；修改走 save_settings（后端合并保存，只动这一个键）
const surfaceSavePath = ref('')
const delFiles = ref(false)   // 清除记录时是否连本地文件一起删（默认不勾，localStorage 记住偏好）
try { delFiles.value = localStorage.getItem('mh_del_files') === '1' } catch (e) { /* 隐私模式 */ }
watch(delFiles, v => {
  try { localStorage.setItem('mh_del_files', v ? '1' : '0') } catch (e) { /* 隐私模式 */ }
})
async function pickSaveDir() {
  if (!window.api || !window.api.pickDirectory) return
  try {
    const dir = await window.api.pickDirectory()
    if (!dir) return                    // 用户取消
    window.api.sendCommand({ cmd: 'save_settings', settings: { surface_save_path: dir } })
    surfaceSavePath.value = dir
    message.success('保存位置已更新，新任务即时生效')
  } catch (e) { /* 目录选择器异常：忽略 */ }
}

// 注：下载管理入口 openDownloads 定义在上方「视图返回栈」处（进入前压栈，返回即回原界面）

// ===== BT 下载（磁力链接/.torrent）：aria2 内核；world=surface 落「保存位置」 =====
function submitBt(url) {
  const u = (url || '').trim()
  if (!u || !window.api) return
  window.api.sendCommand({
    cmd: 'bt_download',
    url: u,
    album: 'BT 下载',
    world: 'surface',
  })
}
// ---- BT 弹窗：Electron 不支持 window.prompt（调用会静默失败），改用 n-modal ----
const btShow = ref(false)
const btText = ref('')
function btPromptSubmit() {
  btShow.value = true
}
// 自动接管磁力链接：开启后网页里点 magnet: 不再弹确认，直接提交（偏好持久化）
const btAuto = ref(false)
try { btAuto.value = localStorage.getItem('bt_auto_takeover') === '1' } catch (e) { /* 隐私模式 */ }
watch(btAuto, v => {
  try { localStorage.setItem('bt_auto_takeover', v ? '1' : '0') } catch (e) { /* 隐私模式 */ }
})
function submitBtBatch() {
  const lines = (btText.value || '').split('\n').map(s => s.trim()).filter(Boolean)
  if (!lines.length) {
    message.warning('请先粘贴至少一条磁力链接或种子地址')
    return
  }
  lines.forEach(u => submitBt(u))
  message.success(`已提交 ${lines.length} 条 BT 任务`)
  btText.value = ''
  btShow.value = false
}
// .torrent 种子文件拖拽：读文件 → base64 → bt_download_file（world=surface 落保存位置）
async function onBtDrop(e) {
  const files = Array.from((e.dataTransfer && e.dataTransfer.files) || [])
  const torrents = files.filter(f => /\.torrent$/i.test(f.name || ''))
  if (!torrents.length) {
    message.warning('请拖入 .torrent 种子文件（磁力链接请粘贴到上方输入框）')
    return
  }
  for (const f of torrents) {
    try {
      const bytes = new Uint8Array(await f.arrayBuffer())
      let bin = ''
      const CHUNK = 0x8000
      for (let i = 0; i < bytes.length; i += CHUNK) {
        bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK))
      }
      window.api && window.api.sendCommand({
        cmd: 'bt_download_file',
        b64: btoa(bin),
        album: 'BT 下载',
        world: 'surface',
      })
      message.success(`已提交种子：${f.name}`)
    } catch (err) {
      message.error(`读取种子失败：${f.name}`)
    }
  }
}
// 磁力站页面点击 magnet: 链接（主进程协议拦截转发）
// → 开启「自动接管」直接提交；否则确认后进 BT 下载
if (window.api && window.api.onBtMagnetClick) {
  window.api.onBtMagnetClick(({ url }) => {
    if (!url) return
    let auto = false
    try { auto = localStorage.getItem('bt_auto_takeover') === '1' } catch (e) { /* 隐私模式 */ }
    if (auto) {
      submitBt(url)
      message.success('已自动加入 BT 下载（进度在下载管理查看）')
      return
    }
    if (window.confirm(`检测到磁力链接，加入 BT 下载？\n\n${url.slice(0, 120)}`)) submitBt(url)
  })
}

// ===== 自动更新（表世界单独设置；统一从 GitHub Release 获取最新安装包） =====
const updCurrent = ref('')
const updChecking = ref(false)
const updHasNew = ref(false)
const updInfo = ref(null)          // github_update_info 的 release 部分
const updDownloading = ref(false)
const updProgress = ref(0)         // 下载百分比
const updDonePath = ref('')        // 下载完成的安装包路径
// 自动检查开关（表世界单独设置，默认开）
const updAuto = ref(localStorage.getItem('mh_auto_update') !== '0')
watch(updAuto, v => { try { localStorage.setItem('mh_auto_update', v ? '1' : '0') } catch (e) { /* 忽略 */ } })
const updSilent = ref(false)       // 自动检查=静默；手动点击=有反馈

async function checkUpdate(silent = false) {
  if (updChecking.value || !window.api) return
  updChecking.value = true
  updSilent.value = !!silent
  if (!updCurrent.value) {
    try {
      const v = await window.api.getAppVersion()
      updCurrent.value = String(v || '').replace(/^v/, '')
    } catch (e) { /* 忽略 */ }
  }
  window.api.sendCommand({ cmd: 'check_github_update', current_version: updCurrent.value })
  if (!silent) message.info('正在检查更新…')
  setTimeout(() => { updChecking.value = false }, 20000)   // 超时兜底解除按钮
}

function confirmInstallUpdate() {
  const r = updInfo.value || {}
  const asset = (r.assets && r.assets[0]) || {}
  const lines = [
    `发现新版本 ${r.tag || ''}${r.name ? ' · ' + r.name : ''}`,
    asset.name ? `安装包：${asset.name}（${asset.size ? (asset.size / 1048576).toFixed(0) + ' MB' : '大小未知'}）` : '',
    (r.body || '').slice(0, 400),
    '',
    '将开始下载安装包，下载完成后会询问是否立即安装。',
  ].filter(Boolean)
  if (window.confirm(lines.join('\n'))) {
    if (!asset.url) { message.error('该版本没有可下载的安装包附件'); return }
    updDownloading.value = true
    updProgress.value = 0
    window.api.sendCommand({ cmd: 'download_update', url: asset.url, file_name: asset.name })
  }
}

// ===== 当前页面存为 Word（页内提取正文元素，图片表格按原位置写入文档） =====
const exportingWord = ref(false)
let wordTimer = null   // 导出超时兜底（结果事件未回来时解除按钮锁定）

async function exportPageWord() {
  if (exportingWord.value || !wvRef.value) return
  exportingWord.value = true
  message.info && message.info('正在提取正文并导出 Word…')
  const finish = (fn, msg) => {
    if (wordTimer) { clearTimeout(wordTimer); wordTimer = null }
    exportingWord.value = false
    fn && fn(msg)
  }
  wordTimer = setTimeout(() => {
    finish(message.warning, 'Word 导出超时：未收到后端结果，请重试或查看日志')
  }, 150000)
  try {
    // 先滚动触发懒加载（单独一次 evaluate：SPA 滚动过程中若发生导航/跳转，
    // 不会连累后面的正文提取——此前整段一起执行会因"执行上下文被销毁"直接失败）
    const scrollJs = `(async () => {
      const sleep = ms => new Promise(r => setTimeout(r, ms));
      try {
        for (let i = 0; i < 6; i++) { window.scrollBy(0, Math.round(window.innerHeight * 0.8)); await sleep(320); }
        window.scrollTo(0, 0); await sleep(200);
      } catch (e) { /* 页面跳转/销毁：忽略，继续执行后面的提取 */ }
      return true;
    })()`
    try { await wvRef.value.executeJavaScript(scrollJs, false) } catch (e) { /* 忽略滚动失败 */ }

    const js = `(async () => {
      const clean = s => (s || '').replace(/\\s+/g, ' ').trim();
      const BAD = new Set(['script','style','noscript','svg','template','iframe','form','button','select','textarea']);
      const NOISE_SEL = 'nav,footer,aside,header,.nav,.footer,.sidebar,.comment,#comments,.ad,.advert';

      const visible = el => {
        try {
          const s = getComputedStyle(el);
          if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity || '1') < 0.05) return false;
          const r = el.getBoundingClientRect();
          return r.width > 0 || r.height > 0;
        } catch (e) { return true; }
      };
      const nodes = [];
      const seen = new Set();
      let imgCount = 0;
      const push = node => {
        if (nodes.length >= 1200) return;
        const key = node.t + '|' + (node.text || node.src || node.html || '');
        if (seen.has(key)) return;
        seen.add(key);
        nodes.push(node);
      };
      const root = document.querySelector('main, article, [role=main]') || document.body;

      // ---- 第一轮：语义标签（标题/段落/列表/引用/代码块/表格/图片） ----
      const inNoise = el => { try { return !!(el.closest && el.closest(NOISE_SEL)) } catch (e) { return false } };
      root.querySelectorAll('h1,h2,h3,h4,h5,h6,p,li,blockquote,pre,table,figure,img').forEach(el => {
        const tag = el.tagName.toLowerCase();
        if (BAD.has(tag)) return;
        if (tag === 'img') {
          if (imgCount >= 40) return;
          const src = el.currentSrc || el.src || el.getAttribute('data-src') || el.getAttribute('data-original') || '';
          if (!src || src.indexOf('data:') !== 0 && !/^https?:\\/\\//i.test(src)) return;
          const w = el.naturalWidth || el.getBoundingClientRect().width || 0;
          if (w && w < 80) return;             // 图标/像素占位忽略
          imgCount++; push({ t: 'img', src: src.slice(0, 2000) });
          return;
        }
        if (!visible(el) || inNoise(el)) return;
        if (tag === 'table') {
          const txt = clean(el.innerText || el.textContent || '');
          if (!txt) return;
          push({ t: 'table', html: (el.outerHTML || '').slice(0, 300000), text: txt.slice(0, 20000) });
          return;
        }
        const txt = clean(el.innerText || el.textContent || '');
        if (!txt || txt.length < (tag.startsWith('h') ? 2 : 6)) return;   // 太短的碎片（导航项、按钮文案）丢掉
        push({ t: tag, text: txt.slice(0, 20000) });
      });

      // ---- 第二轮兜底：div/span 型站点（多数 SPA 没有 <p>）——取叶子文本节点按父元素聚合 ----
      const textLen = nodes.filter(n => n.t !== 'img').reduce((s, n) => s + (n.text || '').length, 0);
      if (textLen < 300) {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
          acceptNode(n) {
            const t = clean(n.nodeValue || '');
            if (!t || t.length < 20) return NodeFilter.FILTER_REJECT;
            const p = n.parentElement;
            if (!p || BAD.has(p.tagName.toLowerCase())) return NodeFilter.FILTER_REJECT;
            if (!visible(p) || inNoise(p)) return NodeFilter.FILTER_REJECT;
            return NodeFilter.FILTER_ACCEPT;
          }
        });
        let lastParent = null;
        let node;
        while ((node = walker.nextNode())) {
          const t = clean(node.nodeValue);
          if (!t) continue;
          if (node.parentElement === lastParent && nodes.length) {
            const last = nodes[nodes.length - 1];
            if (last.t && !last.t.startsWith('h') && last.t !== 'img' && last.t !== 'table') {
              last.text = (last.text + ' ' + t).slice(0, 20000);
              continue;
            }
          }
          lastParent = node.parentElement;
          push({ t: 'p', text: t });
        }
      }
      return {
        title: (document.title || (document.querySelector('h1') || {}).innerText || '网页导出').slice(0, 120),
        elements: nodes,
        rounds: nodes.length,
      };
    })()`
    // 提取可能因页面跳转（B站等 SPA 常自动重定向）导致"执行上下文被销毁"，
    // 失败后等 1.2s 重试一次，仍失败才报错
    let data = null
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        data = await wvRef.value.executeJavaScript(js, false)
        break
      } catch (e) {
        if (attempt === 1) throw e
        await new Promise(r => setTimeout(r, 1200))
      }
    }
    if (!data || !data.elements || !data.elements.length) {
      finish(message.error, '未识别到可导出的正文（纯图/视频页或内容在框架内无法读取）')
      return
    }
    window.api && window.api.sendCommand({
      cmd: 'web_to_word',
      title: data.title,
      doc_title: data.title,
      page_url: currentUrl.value || '',
      elements: data.elements,
      // 表世界产物：落盘跟随「表世界保存位置」，并登记进本界面下载管理
      world: 'surface',
      album: (active.value && active.value.name) || '网页导出',
    })
    // 结果由 word_result 事件收尾（成功/失败都有提示，不再假成功）
  } catch (e) {
    finish(message.error, 'Word 导出失败：' + ((e && e.message) || '未知错误'))
  }
}

// 只显示 world=surface 的任务（其他世界的任务绝不出现）
function applySurfaceTasks(list) {
  surfaceTasks.value = (list || []).filter(
    t => (t.options || {}).world === 'surface' || t.world === 'surface')
}

function openTaskFolder(t) {
  const dir = t.save_dir
  if (dir && window.api && window.api.openPath) {
    window.api.openPath(dir).then(r => {
      if (r && r.ok === false) message.error(r.error || '无法打开文件夹')
    }).catch(() => {})
  } else {
    message.error('暂无保存位置')
  }
}

function clearRecord(taskId) {
  const del = delFiles.value
  // 首次勾选删除时二次确认；确认一次后记住，之后不再问
  if (del && localStorage.getItem('mh_del_files_confirmed') !== '1') {
    if (!window.confirm('将同时删除任务对应的本地文件，确定？')) return
    try { localStorage.setItem('mh_del_files_confirmed', '1') } catch (e) { /* 隐私模式 */ }
  }
  window.api && window.api.sendCommand({ cmd: 'remove_task', task_id: taskId, delete_files: del })
  surfaceTasks.value = surfaceTasks.value.filter(t => t.id !== taskId)
  message.success(del ? '已删除该任务及其本地文件' : '已清除该下载记录')
}

// ---- 美好世界下载管理的任务进度与控制（流媒体任务尤其需要：几百个分片，
// 进度单位不是字节，且必须能暂停/续传/重试，否则「下载整片」就是个黑盒）----
const TASK_STATUS_TEXT = {
  pending: '等待中', running: '下载中', paused: '已暂停',
  completed: '已完成', failed: '失败', cancelled: '已取消',
}
function statusText(s) {
  return TASK_STATUS_TEXT[s] || s || ''
}
function segInfo(t) {
  const f = (t.files || [])[0] || {}
  return Number(f.hls_total) > 0 ? f : null
}
function taskProgressText(t) {
  const f = segInfo(t)
  if (f) {
    if (t.status === 'completed') return `${f.hls_total} 个分片已合并`
    if (f.hls_phase === 'merging') return '分片下载完成，正在合并 MP4…'
    return `分片 ${f.hls_done || 0}/${f.hls_total}`
  }
  const files = t.files || []
  const done = files.filter(x => x.status === 'completed').length
  return files.length ? `已完成 ${done}/${files.length} 个文件` : ''
}
function taskPercent(t) {
  const f = segInfo(t)
  if (f) return Math.min(100, Number(f.completed) || (t.status === 'completed' ? 100 : 0))
  const files = t.files || []
  if (!files.length) return 0
  if (t.status === 'completed') return 100
  return Math.round(files.filter(x => x.status === 'completed').length * 100 / files.length)
}
function taskCmd(cmd, taskId) {
  window.api && window.api.sendCommand({ cmd, task_id: taskId })
  if (cmd === 'pause_task') message.info('已暂停：已下载的分片保留着，点「继续」从断点接着下')
  if (cmd === 'resume_task') message.info('继续下载：从断点接着下，不重下已有分片')
  if (cmd === 'retry_task') message.info('重试：从断点接着下')
}

function openPlatform(p) {
  // GitHub 校验位：失效站与"留空位"站点不进入浏览态，给出明确指引
  if (p.invalid) {
    message.warning(`「${p.name}」已被 GitHub 校验表标记失效${p.invalidNote ? '：' + p.invalidNote : '，等待校验表下发新地址'}`, { duration: 4000 })
    return
  }
  if (!p.home) {
    message.info(`「${p.name}」地址待定：GitHub 校验表（surface_sites.json）下发可用地址后本磁贴自动点亮`, { duration: 4000 })
    return
  }
  trackSiteClick(p.key)  // 「常用」模块点击统计（localStorage 累计）
  // 官方平台的 DRM 正片在本内置浏览器里一定播不了：Electron 不带 Widevine/EME 组件
  // （2026-09-18 实测 widevine/playready/clearkey 三种 key system 全部 NotSupportedError）。
  // 与其让用户对着黑屏猜，不如进站就说清；预告片与免费图文一般不受影响。
  if (p.drm) {
    message.warning(
      `「${p.name}」正片用 DRM 版权保护，内置浏览器不含 Widevine 组件，无法播放正片`
      + `（非 Chrome 内核浏览器的共同限制，与站点无关）。预告片/免费图文一般正常，看正片请用系统浏览器。`,
      { duration: 9000 }
    )
  }
  active.value = p
  wvSrc.value = p.home
  viewStack.value = []          // 新开平台：返回栈从这一层重新开始
  items.value = []
  downloaded.value = new Set()
  filter.value = 'all'
  hlsBusy.value.clear()
  bili.visible = false
  bili.loading = false
  bili.error = ''
  window.api && window.api.hotCaptureAttach && window.api.hotCaptureAttach()
  nextTick(() => { addressDraft.value = p.home })
}
// Electron webview 卸载缺陷：guestInstance 清理在 disconnectedCallback 里抛
// "Invalid guestInstanceId"，且从 Vue remove() 内部同步逃逸会打断 patch（点磁贴
// 视图不切换的元凶）。在 Vue 卸载之前先手动摘除 webview，把异常吞在 try/catch 里。
function detachWebviewSafely() {
  const wv = wvRef.value
  if (wv && wv.nodeType === 1 && typeof wv.remove === 'function') {
    try { wv.stop() } catch (e) { /* guest 未就绪 */ }
    try { wv.remove() } catch (e) { /* disconnectedCallback 抛错：已摘除即达目的 */ }
  }
}

function closePlatform() {
  detachWebviewSafely()
  active.value = null
  wvSrc.value = ''
  viewStack.value = []
  bili.visible = false
}

function onNav(e) {
  const url = e.url || ''
  if (!url || url === 'about:blank') return
  addressDraft.value = url
  currentUrl.value = url
  // 记住该平台最后浏览地址：从下载管理返回时回到这一页
  if (active.value && active.value.key) lastUrlByKey.value = { ...lastUrlByKey.value, [active.value.key]: url }
  scheduleBiliParse(url)
}
function navigateAddress() {
  let u = (addressDraft.value || '').trim()
  if (!u) return
  if (!/^https?:\/\//i.test(u)) u = 'https://' + u
  try { wvRef.value && wvRef.value.loadURL(u) } catch (e) { /* webview 未就绪 */ }
}
function nav(action) {
  const wv = wvRef.value
  if (!wv) return
  try {
    if (action === 'back') wv.goBack()
    else if (action === 'forward') wv.goForward()
    else if (action === 'reload') wv.reload()
    else if (action === 'home' && active.value) wv.loadURL(active.value.home)
  } catch (e) { /* 忽略 */ }
}

// ===== B站专属解析（插件式：页内 fetch 带登录态/真实指纹，绕开对脚本端的风控） =====
const BILI_Q = {
  127: '8K 超高清', 126: '杜比视界', 125: 'HDR 真彩', 120: '4K 超清',
  116: '1080P 60帧', 112: '1080P 高码率', 100: '智能修复',
  80: '1080P 高清', 74: '720P 60帧', 64: '720P 高清', 32: '480P 清晰', 16: '360P 流畅',
}
const BILI_A = { 30280: '320kbps', 30232: '128kbps', 30216: '64kbps' }
const bili = reactive({
  visible: false, loading: false, error: '',
  title: '', owner: '', bvid: '',
  pages: [], pageIdx: 0,
  qualities: [], qualityId: 0,
  audioLabel: '', audioUrl: '',
})
let biliParseTimer = null
let biliSeq = 0

function scheduleBiliParse(url) {
  const m = String(url || '').match(/bilibili\.com\/video\/(BV[0-9A-Za-z]{8,12})/i)
  if (!m) { bili.visible = false; return }
  bili.visible = true
  bili.loading = true
  bili.error = ''
  const bvid = m[1]
  const pMatch = String(url).match(/[?&]p=(\d+)/)
  const seq = ++biliSeq
  if (biliParseTimer) clearTimeout(biliParseTimer)
  biliParseTimer = setTimeout(() => parseBili(bvid, pMatch ? parseInt(pMatch[1], 10) : 1, seq), 800)
}

async function parseBili(bvid, page, seq) {
  try {
    const wv = wvRef.value
    if (!wv) throw new Error('浏览器未就绪')
    // 页内 fetch：自动带 B站登录 cookie 与真实浏览器指纹（后端直连会被 412 风控）
    const j = await wv.executeJavaScript(
      `fetch('https://api.bilibili.com/x/web-interface/view?bvid=${bvid}',{credentials:'include'}).then(r=>r.json())`, false)
    if (seq !== biliSeq) return
    if (!j || j.code !== 0) throw new Error((j && j.message) || '解析失败')
    const d = j.data || {}
    const pages = (d.pages || []).map(p => ({ page: p.page, part: p.part || '', cid: p.cid }))
    const cur = pages.find(p => p.page === page) || pages[0] || { cid: d.cid, page: 1, part: '' }
    const j2 = await wv.executeJavaScript(
      `fetch('https://api.bilibili.com/x/player/playurl?bvid=${bvid}&cid=${cur.cid}&qn=127&fnval=4048&fourk=1',{credentials:'include'}).then(r=>r.json())`, false)
    if (seq !== biliSeq) return
    if (!j2 || j2.code !== 0) throw new Error((j2 && j2.message) || '取播放流失败')
    const pd = j2.data || {}
    const dash = pd.dash || {}
    const aq = pd.accept_quality || []
    const ad = pd.accept_description || []
    const labelOf = (id) => {
      const i = aq.indexOf(id)
      return (i >= 0 ? ad[i] : '') || BILI_Q[id] || `${id}`
    }
    // 同一清晰度多种编码（avc/hevc/av01）取体积最大的一条
    const byId = new Map()
    for (const v of (dash.video || [])) {
      const prev = byId.get(v.id)
      if (!prev || (v.size || 0) > (prev.size || 0)) byId.set(v.id, v)
    }
    const qualities = [...byId.values()]
      .sort((a, b) => (b.id || 0) - (a.id || 0))
      .map(v => ({
        id: v.id,
        label: labelOf(v.id),
        sizeText: v.size ? `${(v.size / 1048576).toFixed(0)}MB` : '—',
        url: v.base_url || (v.backup_url && v.backup_url[0]) || '',
      }))
    const auds = (dash.audio || []).slice().sort((a, b) => (b.id || 0) - (a.id || 0))
    const aud = auds[0]
    Object.assign(bili, {
      loading: false, error: '',
      title: d.title || '未知标题',
      owner: `UP：${(d.owner || {}).name || '未知'}`,
      bvid: d.bvid || bvid,
      pages,
      pageIdx: Math.max(0, pages.findIndex(p => p.page === (cur.page || 1))),
      qualities,
      qualityId: qualities[0] ? qualities[0].id : 0,
      audioLabel: aud ? `${BILI_A[aud.id] || '音频'}${aud.size ? `（${(aud.size / 1048576).toFixed(1)}MB）` : ''}` : '无',
      audioUrl: aud ? (aud.base_url || '') : '',
    })
  } catch (e) {
    if (seq !== biliSeq) return
    Object.assign(bili, { loading: false, error: (e && e.message) || '解析失败（请先在浏览器中打开本视频页）' })
  }
}

function downloadBili(mode) {
  const q = bili.qualities.find(x => x.id === bili.qualityId) || bili.qualities[0]
  if (!q || !q.url) { message.error('未解析到可用的视频流'); return }
  if (mode in { merge: 1, audio: 1 } && !bili.audioUrl) { message.error('未解析到音频流'); return }
  const pg = bili.pages[bili.pageIdx] || {}
  window.api && window.api.sendCommand({
    cmd: 'bili_download',
    album: '哔哩哔哩',
    item: {
      video_url: q.url,
      audio_url: bili.audioUrl,
      mode,
      quality_label: q.label,
      title: bili.title,
      page: pg.page || 1,
      page_part: pg.part || '',
      page_url: currentUrl.value,
      bvid: bili.bvid,
    },
  })
}

// HLS 拼接中的状态表：url → "下载中 i/total"（hls_progress 事件回填，列表项实时可见）
const hlsBusy = ref(new Map())
const HLS_GENERIC_NAME = /^(index|playlist|master|video|live|hls|stream|main|manifest|getm3u8|get|play|api)([-_.]?\d*)?(\.m3u8)?$/i
const HLS_HASH_NAME = /^[0-9a-f]{16,}$/i

function hlsDisplayName(it) {
  const orig = it.filename || ''
  const raw = orig.replace(/\.m3u8$/i, '')
  // 不可读名（接口名/哈希/无扩展名末段）一律回退「平台名_时间戳」：
  // 很多站把 m3u8 藏在 /nby/m3u8/getM3u8 这类接口路径里，末段根本不是文件名
  const unusable = !raw || raw.length < 2
    || HLS_GENERIC_NAME.test(orig)
    || HLS_HASH_NAME.test(raw)
    || !orig.includes('.')
  if (unusable) {
    const ts = new Date()
    const pad = n => String(n).padStart(2, '0')
    return `${(active.value && active.value.name) || '流媒体'}_${ts.getFullYear()}${pad(ts.getMonth() + 1)}${pad(ts.getDate())}-${pad(ts.getHours())}${pad(ts.getMinutes())}${pad(ts.getSeconds())}`
  }
  return raw
}

function downloadOne(it) {
  if (it.type === 'hls') {
    // 流媒体「下载整片」：提交为下载任务（后端 hls_submit）——分片落盘下载，
    // 可暂停/继续/重试，进度在下载管理里看；不再是"点一下干等到合并完"的一次性动作。
    if (hlsBusy.value.has(it.url)) return
    // 被判为疑似广告：先确认一次（「全部下载」会自动跳过它们，手动点则是明确意愿）
    if (it.verdict === 'ad') {
      const why = (it.probeReasons || []).slice(0, 2).join('；') || '时长过短或含广告标记'
      if (!window.confirm(`这条流被判定为疑似广告：\n\n${why}\n\n确定仍要下载吗？`)) return
    }
    hlsBusy.value.set(it.url, '提交中…')
    hlsBusy.value = new Map(hlsBusy.value)   // 触发响应式
    window.api && window.api.sendCommand({
      cmd: 'hls_submit',
      url: it.url,
      referer: it.page_url || currentUrl.value || '',
      album: active.value ? active.value.name : '热门平台',
      filename: hlsDisplayName(it),
      // 美好世界发起：落盘跟随「保存位置」设置（web_surface_root），并登记进美好世界下载管理。
      // 不带 world 时后端默认 inner → 存到 ~/Downloads/平台名/，且下载管理里看不到。
      world: 'surface',
    })
    return
  }
  submitItems([it])
}
function downloadAll() {
  if (!filtered.value.length) return
  if (filter.value === 'hlsseg') {
    message.info('分片只是视频的一小段，单独下载拼不出整片；要正片请切到「视频流」下载 m3u8 那一条', { duration: 8000 })
  }
  // 通用下载需求：直链走通用管线、HLS 走拼接，一次全下。
  // 已被智能判决为疑似广告的流自动跳过（要下就单独点它右侧的「仍要下载」）——
  // 一个页面通常同时抓到正片清单和贴片广告清单，全下会把广告一起拖下来。
  const direct = []
  let skippedAds = 0
  for (const it of filtered.value) {
    if (it.type === 'hls') {
      if (it.verdict === 'ad') { skippedAds++; continue }
      downloadOne(it)
      continue
    }
    direct.push(it)
  }
  if (skippedAds) {
    message.info(`已自动跳过 ${skippedAds} 条疑似广告流（时长过短或含广告标记）；确实要下就单独点它的「仍要下载」`, { duration: 8000 })
  }
  submitItems(direct)
}
function submitItems(list) {
  if (!list.length || !window.api) return
  window.api.sendCommand({
    cmd: 'sniff_download',
    world: 'surface',   // 美好世界任务：落 C 盘下载夹 + 只出现在本界面下载管理
    album: active.value ? active.value.name : '热门平台',
    items: list.map(i => ({
      url: i.url,
      filename: i.filename,
      media_type: i.type,
      size: i.size || 0,
      page_url: currentUrl.value || i.page_url,
    })),
  })
}
async function copyOne(u) {
  try {
    if (window.api && window.api.copyText) {
      const r = await window.api.copyText(u)
      if (r && r.ok === false) throw new Error(r.error || '复制失败')
    } else {
      await navigator.clipboard.writeText(u)
    }
  } catch (e) { /* 静默 */ }
}
function clearAll() {
  items.value = []
  segItems.value = []
  segTotal.value = 0
  downloaded.value = new Set()
}

function openHelp(file) {
  window.api && window.api.openHelpWindow && window.api.openHelpWindow(file)
}

async function restartApp() {
  if (!window.api || !window.api.restartApp) return
  if (!window.confirm('确定重启应用吗？\n\n将还原嗅探网络设置并自动重新启动（登录状态与界面模式均保持）。')) return
  try { await window.api.restartApp() } catch (e) { /* 重启中进程退出 */ }
}

let offResource = null
let offHotPopup = null
onMounted(() => {
  // 拉取后端设置（settings 事件回流，onEvent 里读 surface_save_path 显示当前保存位置）
  window.api && window.api.sendCommand({ cmd: 'get_settings' })
  // 自动检查更新（表世界单独设置，默认开；结果经 github_update_info 回流）
  if (localStorage.getItem('mh_auto_update') !== '0') checkUpdate(true)
  if (window.api && window.api.onSnifferResource) {
    offResource = window.api.onSnifferResource(addItem)
  }
  // 热门平台 webview 的 _blank 链接 → 当前 webview 内导航（保持登录态与捕获连续）
  if (window.api && window.api.onHotPopupNavigate) {
    offHotPopup = window.api.onHotPopupNavigate(({ url }) => {
      if (active.value && url && wvRef.value) {
        try { wvRef.value.loadURL(url) } catch (e) { /* webview 未就绪 */ }
      }
    })
  }
  if (window.api && window.api.onEvent) {
    window.api.onEvent((ev) => {
      if (!ev || !ev.event) return
      if (ev.event === 'settings') {
        // 保存位置回流（App 层也处理同一事件，互不影响）
        surfaceSavePath.value = (ev.settings && ev.settings.surface_save_path) || ''
        return
      }
      if (ev.event === 'github_update_info') {
        // 更新检查回流：has_new_release → 弹确认（版本+说明+大小）
        updChecking.value = false
        if (ev.current_version) updCurrent.value = ev.current_version
        const rel = ev.release || null
        updHasNew.value = !!ev.has_new_release
        updInfo.value = rel
        if (ev.has_new_release && rel) confirmInstallUpdate()
        else if (!updSilent.value) message.info(`当前已是最新版本（v${updCurrent.value || ev.current_version}）`)
        return
      }
      if (ev.event === 'update_download_progress') {
        updProgress.value = ev.percent || 0
        return
      }
      if (ev.event === 'update_download_done') {
        updDownloading.value = false
        updDonePath.value = ev.path || ''
        message.success(`更新包已下载：${ev.file_name || ''}（${((ev.size || 0) / 1048576).toFixed(0)} MB）`)
        // 安装确认环节：用户确认后才运行安装包（NSIS 覆盖安装即更新）
        if (window.confirm(`新版本安装包已就绪：\n${ev.path}\n\n立即运行安装程序？（安装过程中应用会关闭）`)) {
          window.api.sendCommand({ cmd: 'open_update_installer', path: updDonePath.value })
        } else {
          message.info('已取消安装；安装包保留在下载文件夹，可稍后手动运行')
        }
        return
      }
      if (ev.event === 'update_download_error') {
        updDownloading.value = false
        message.error(ev.error || '更新下载失败')
        return
      }
      if (ev.event === 'word_result') {
        if (wordTimer) { clearTimeout(wordTimer); wordTimer = null }
        exportingWord.value = false
        if (ev.ok) {
          // 明确告知「存到哪了」：后端 message 已带「· 保存于 <目录>」，
          // 即便后端没带，也用 ev.dir 兜底补一句，用户不必再猜默认位置。
          const line = ev.message
            || `Word 已导出${ev.filename ? '：' + ev.filename : ''}${ev.dir ? ' · 保存于 ' + ev.dir : ''}`
          message.success(line, { duration: 10000 })
          // 同一次导出已登记进本界面「下载管理」，给一条轻提示指路（不抢主提示）
          if (ev.dir) message.info('该文档已记入「📥 下载管理」，可在那里一键打开文件夹', { duration: 7000 })
        } else {
          message.error(ev.message || 'Word 导出失败', { duration: 8000 })
        }
        return
      }
      if (ev.event === 'sniff_download_result' && ev.ok) {
        const urls = ev.urls || []
        if (urls.length) downloaded.value = new Set([...downloaded.value, ...urls])
        return
      }
      if (ev.event === 'tasks_snapshot') {
        applySurfaceTasks(ev.tasks || [])
        return
      }
      if (ev.event === 'duration_result') {
        const hit = items.value.find(i => i.url === ev.url)
        if (hit && ev.duration > 0) {
          hit.duration = ev.duration
          hit.durationText = fmtDur(ev.duration)
        }
        return
      }
      if (ev.event === 'hls_probe_result') {
        // 智能判决回流：填时长/分片数/判决徽标 + 判定依据（列表内联展示，不用再猜）
        const hit = items.value.find(i => i.url === ev.url)
        if (!hit) return
        if (!ev.ok) {
          hit.probeNote = ev.message || '播放清单探测失败'
          return
        }
        hit.verdict = ev.verdict || ''
        hit.probeReasons = ev.reasons || []
        hit.probeNote = ev.note || ''
        hit.segCount = ev.segCount || 0
        if (ev.duration > 0) {
          hit.duration = ev.duration
          hit.durationText = fmtDur(ev.duration)
        }
        if (ev.verdict === 'content' && !contentHinted) {
          contentHinted = true
          message.success(`识别到正片${ev.durationText ? '（' + ev.durationText + '）' : ''}：点这条右侧「下载整片」保存 MP4`, { duration: 8000 })
        }
        return
      }
      if (ev.event === 'bt_result') {
        if (ev.ok) message.success(ev.message || 'BT 任务已提交')
        else message.error(ev.message || 'BT 提交失败')
        return
      }
      if (ev.event === 'bili_download_result') {
        if (ev.ok) message.success(ev.message || 'B站下载已提交')
        else message.error(ev.message || 'B站下载提交失败')
        return
      }
      if (ev.event === 'hls_progress') {
        const cur = hlsBusy.value.get(ev.url)
        if (cur !== undefined && ev.total > 0) {
          hlsBusy.value.set(ev.url, `分片 ${ev.done}/${ev.total}`)
          hlsBusy.value = new Map(hlsBusy.value)
        }
        // 拼接时后端也会解析清单：把时长/判决回填到列表项（hls_probe 失败或还没回来的兜底）
        if (ev.phase === 'analyzed') {
          const hit = items.value.find(i => i.url === ev.url)
          if (hit) {
            if (ev.duration > 0 && !hit.durationText) {
              hit.duration = ev.duration
              hit.durationText = fmtDur(ev.duration)
            }
            if (ev.verdict && !hit.verdict) hit.verdict = ev.verdict
            if (ev.encrypted) hit.probeNote = 'AES-128 加密流（下载时自动解密）'
            else if (ev.fmp4) hit.probeNote = 'fMP4 分片'
          }
        }
        return
      }
      if (ev.event === 'hls_submit_result') {
        // 「下载整片」已提交为下载任务：清掉提交中态，提示去哪儿看进度
        const busy = hlsBusy.value.has(ev.url)
        if (busy) {
          hlsBusy.value.delete(ev.url)
          hlsBusy.value = new Map(hlsBusy.value)
        }
        const hit = items.value.find(i => i.url === ev.url)
        if (ev.ok) {
          if (ev.url) downloaded.value = new Set([...downloaded.value, ev.url])
          if (hit) {
            if (ev.duration > 0 && !hit.durationText) {
              hit.duration = ev.duration
              hit.durationText = fmtDur(ev.duration)
            }
            if (ev.verdict && !hit.verdict) hit.verdict = ev.verdict
          }
          message.success(ev.message || '已加入下载管理')
        } else {
          message.error(ev.message || '流媒体提交失败')
        }
        return
      }
      if (ev.event === 'hls_result') {
        const busy = hlsBusy.value.has(ev.url)
        if (busy) {
          hlsBusy.value.delete(ev.url)
          hlsBusy.value = new Map(hlsBusy.value)
        }
        if (ev.ok) {
          if (ev.url) {
            downloaded.value = new Set([...downloaded.value, ev.url])
            const hit = items.value.find(i => i.url === ev.url)
            if (hit) {
              if (ev.duration > 0 && !hit.durationText) {
                hit.duration = ev.duration
                hit.durationText = fmtDur(ev.duration)
              }
              if (ev.verdict && !hit.verdict) hit.verdict = ev.verdict
            }
          }
          message.success(ev.message || '流媒体已合并完成')
        } else if (busy) {
          message.error(ev.message || '流媒体拼接失败')
        }
        return
      }
      if (ev.event === 'surface_registry_result') {
        applyRegistry(ev)
        return
      }
    })
  }
  // 启动即拉 GitHub 校验表（后端 30 分钟缓存节流；失败静默保持本地 baseline）
  window.api && window.api.sendCommand({ cmd: 'web_registry_fetch' })
})

// GitHub 校验表合并：ok→可下发新地址；dead→置灰；extra→动态补新磁贴；slot→空位点亮
function applyRegistry(ev) {
  if (!ev || !ev.ok || !ev.registry) {
    if (syncing.value) {
      syncing.value = false
      message.error((ev && ev.message) || '站点同步失败（使用本地站点表）')
    }
    return
  }
  const merged = mergeRegistry(PLATFORM_BASELINE, ev.registry)
  platforms.value = merged.sites
  const { ok, dead, extra } = merged.stats
  if (syncing.value) {
    syncing.value = false
    if (syncTimer) { clearTimeout(syncTimer); syncTimer = null }
    const parts = [`有效 ${ok}`]
    if (dead > 0) parts.push(`失效 ${dead}（置灰）`)
    if (extra > 0) parts.push(`新增 ${extra}`)
    message.success(`站点同步完成：${parts.join('，')}`, { duration: 4500 })
    return
  }
  if (dead > 0 || extra > 0) {
    const parts = []
    if (dead > 0) parts.push(`${dead} 个站点已失效（置灰）`)
    if (extra > 0) parts.push(`${extra} 个新站点`)
    message.info(`站点校验已更新：${parts.join('，')}（更新于 ${merged.updated || '未知日期'}）`, { duration: 5000 })
  }
}

// 手动「同步站点」：强制绕过 30 分钟缓存，直取上游 GitHub 源
const syncing = ref(false)
let syncTimer = null
function syncSites() {
  if (syncing.value || !window.api) return
  syncing.value = true
  syncTimer = setTimeout(() => {
    if (syncing.value) {
      syncing.value = false
      message.warning('站点同步超时（网络不佳？上游源需代理时请先开系统代理）')
    }
  }, 90000)
  window.api.sendCommand({ cmd: 'web_registry_fetch', force: true })
}
onBeforeUnmount(() => {
  // 三连 Alt 切回经典界面时 ModernHome 整体卸载：先摘 webview（同 closePlatform）
  detachWebviewSafely()
})
onUnmounted(() => {
  if (offResource) offResource()   // 防反复切换模式时监听器叠加
  if (offHotPopup) offHotPopup()
})
</script>

<style scoped>
.mh-root {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: linear-gradient(160deg, rgba(246,247,251,0.97) 0%, rgba(238,241,248,0.95) 55%, rgba(253,238,244,0.95) 100%);
  color: #23262f;
}
/* 内容区：浏览态与下载管理共用的层，也是下载管理覆盖层的定位上下文 */
.mh-body {
  flex: 1; min-height: 0;
  position: relative;
  display: flex; flex-direction: column;
}
/* ---------- 顶栏 ---------- */
.mh-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 26px;
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(14px);
  border-bottom: 1px solid #e8eaf2;
  flex-shrink: 0;
}
.mh-brand { display: flex; align-items: center; gap: 12px; }
.mh-logo {
  width: 42px; height: 42px; border-radius: 14px;
  display: flex; align-items: center; justify-content: center;
  font-size: 22px;
  background: linear-gradient(135deg, #ff5f8f, #ff9966);
  box-shadow: 0 6px 16px rgba(255, 95, 143, 0.35);
}
.mh-title { font-size: 17px; font-weight: 700; letter-spacing: 0.5px; }
.mh-sub { font-size: 11.5px; color: #8a8f9e; margin-top: 1px; }
.mh-header-right { display: flex; align-items: center; gap: 14px; }
.mh-capture-pill {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; color: #5a6072;
  background: #eef0f7; border-radius: 999px; padding: 6px 12px;
}
.mh-capture-pill.live { color: #ff3f7f; background: #ffeef4; font-weight: 600; }
.mh-pill-dot { width: 7px; height: 7px; border-radius: 50%; background: #c3c8d6; }
.mh-capture-pill.live .mh-pill-dot { background: #ff3f7f; box-shadow: 0 0 6px #ff3f7f; }
.mh-switch-hint {
  font-size: 12px; color: #8a8f9e;
  background: #eef0f7; border-radius: 10px; padding: 7px 12px;
}
.mh-restart-btn {
  border: none; cursor: pointer;
  font-size: 12.5px; font-weight: 600; color: #4a54a8;
  background: #eef0f7; border-radius: 10px; padding: 8px 14px;
}
.mh-restart-btn:hover { background: #dfe4f7; }
.mh-nav-btn.mh-home-btn {
  font-size: 17px;
  color: #fff;
  background: linear-gradient(135deg, #ff5f8f, #ff8a5f);
  width: 40px; height: 34px;
  box-shadow: 0 4px 14px rgba(255, 95, 143, 0.4);
}
.mh-nav-btn.mh-home-btn:hover {
  transform: scale(1.12);
  background: linear-gradient(135deg, #ff4a80, #ff7a4a);
}
.mh-help-btn {
  border: none; cursor: pointer;
  font-size: 12.5px; font-weight: 600; color: #4a54a8;
  background: #eef0f7; border-radius: 10px; padding: 8px 14px;
}
.mh-help-btn:hover { background: #dfe4f7; }
.mh-help-btn:disabled { opacity: 0.5; cursor: default; }
.mh-help-btn.mh-btn-on { background: #ffeef4; color: #d4336b; }

/* ---------- B站解析卡 ---------- */
.mh-bili {
  border-bottom: 1px solid #eef0f7;
  background: linear-gradient(150deg, #fff4f8, #f5f7ff);
  padding: 12px 14px;
}
.mh-bili.loading { opacity: 0.75; }
.mh-bili-head { display: flex; align-items: center; gap: 8px; }
.mh-bili-badge {
  font-size: 11px; font-weight: 700; color: #fff;
  background: linear-gradient(135deg, #fb7299, #ff9eb5);
  padding: 3px 9px; border-radius: 999px;
  flex-shrink: 0;
}
.mh-bili-state { font-size: 12px; color: #7a8090; }
.mh-bili-err { font-size: 12px; color: #e0436b; }
.mh-bili-owner { font-size: 11.5px; color: #8a8f9e; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mh-bili-title {
  font-size: 13px; font-weight: 600; margin-top: 8px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mh-bili-pages { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 8px; max-height: 58px; overflow-y: auto; }
.mh-p-chip {
  border: none; cursor: pointer;
  font-size: 11px; color: #5a6072;
  background: #fff; border: 1px solid #e4e6ef;
  padding: 3px 8px; border-radius: 8px;
}
.mh-p-chip.on { background: #fb7299; color: #fff; border-color: #fb7299; font-weight: 600; }
.mh-bili-row { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.mh-bili-label { font-size: 11.5px; color: #8a8f9e; flex-shrink: 0; }
.mh-bili-select {
  flex: 1; height: 30px;
  border: 1px solid #e4e6ef; border-radius: 9px;
  background: #fff; color: #23262f;
  font-size: 12px; padding: 0 8px; outline: none;
}
.mh-bili-audio { font-size: 12px; color: #4a4f5e; font-weight: 500; }
.mh-bili-actions { display: flex; align-items: center; gap: 8px; margin-top: 10px; }
.mh-bili-actions .mh-dl { flex: 1; padding: 8px 10px; }

/* ---------- 首页磁贴 ---------- */
.mh-home {
  flex: 1; min-height: 0;
  display: flex; flex-direction: column; align-items: center;
  overflow-y: auto;
  padding: 30px 40px 40px;
}
.mh-hero { text-align: center; margin-bottom: 26px; }
.mh-hero-title { font-size: 30px; font-weight: 800; letter-spacing: 1px; }
.mh-hero-sub { font-size: 13px; color: #8a8f9e; margin-top: 8px; }
.mh-tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 18px;
  width: 100%;
  max-width: 1060px;
}
.mh-tile {
  position: relative;
  border: none; cursor: pointer;
  display: flex; flex-direction: column; align-items: flex-start;
  gap: 3px; text-align: left;
  background: #fff;
  border-radius: 20px;
  padding: 20px 18px 18px;
  box-shadow: 0 4px 18px rgba(35, 38, 47, 0.07);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.mh-tile:hover { transform: translateY(-4px); box-shadow: 0 12px 26px rgba(35, 38, 47, 0.14); }
.mh-tile::before {
  content: '';
  position: absolute; inset: 0;
  border-radius: 20px;
  background: linear-gradient(135deg, var(--p1), var(--p2));
  opacity: 0.09;
  transition: opacity 0.15s ease;
}
.mh-tile:hover::before { opacity: 0.2; }
.mh-tile-icon {
  width: 46px; height: 46px; border-radius: 14px;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, var(--p1), var(--p2));
  box-shadow: 0 6px 14px rgba(35, 38, 47, 0.18);
  margin-bottom: 8px;
}
.mh-tile-icon :deep(svg) { width: 26px; height: 26px; }
.mh-tile-name { font-size: 15.5px; font-weight: 700; position: relative; }
.mh-tile-desc { font-size: 11.5px; color: #8a8f9e; position: relative; }
.mh-foot-hint { margin-top: 26px; font-size: 12px; color: #a0a5b4; }

/* ---------- 浏览态 ---------- */
.mh-work {
  flex: 1; min-height: 0;
  display: flex; gap: 14px;
  padding: 14px 20px 18px;
}
.mh-browser {
  flex: 1.7; min-width: 0;
  display: flex; flex-direction: column; gap: 10px;
}
.mh-nav { display: flex; align-items: center; gap: 7px; }
.mh-nav-btn {
  width: 32px; height: 32px;
  border: none; cursor: pointer;
  border-radius: 10px;
  background: #fff; color: #4a4f5e;
  font-size: 14px;
  box-shadow: 0 2px 8px rgba(35, 38, 47, 0.08);
}
.mh-nav-btn:hover { background: #f2f3f9; }
.mh-address {
  flex: 1; height: 34px;
  border: 1px solid #e4e6ef; border-radius: 10px;
  background: #fff;
  padding: 0 14px;
  font-size: 12.5px; color: #23262f;
  outline: none;
}
.mh-address:focus { border-color: #b9c2ff; box-shadow: 0 0 0 3px rgba(106, 123, 255, 0.12); }
.mh-platform-chip {
  font-size: 12px; font-weight: 600; color: #fff;
  padding: 6px 12px; border-radius: 999px;
  flex-shrink: 0;
}
.mh-stage {
  flex: 1; min-height: 0;
  position: relative;
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 8px 26px rgba(35, 38, 47, 0.12);
  background: #fff;
}
.mh-webview { width: 100%; height: 100%; border: none; }
.mh-loading-bar {
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, #ff5f8f, #ffb46a);
  animation: mh-loading 1s linear infinite;
  background-size: 200% 100%;
}
@keyframes mh-loading {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ---------- 下载管理视图 ---------- */
.mh-dlview {
  flex: 1; min-height: 0;
  display: flex; flex-direction: column;
  background: #fff; border-radius: 16px;
  box-shadow: 0 8px 26px rgba(35,38,47,.1); overflow: hidden;
}
/* 下载管理覆盖层：绝对定位盖在浏览态之上（z-index 取极大值 —— 实测该值能稳定盖住
   <webview>），背景不透明，避免透出下层播放画面。浏览态的 webview 不被卸载，
   所以收起覆盖层时视频从原位置继续播放，不重新缓存、不重播。 */
.mh-dl-overlay {
  position: absolute; inset: 0;
  z-index: 2147482000;
  border-radius: 0;
  box-shadow: none;
}
.mh-dl-head {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 20px; border-bottom: 1px solid #eef0f7;
}
.mh-dl-title { font-size: 16px; font-weight: 800; }
.mh-dl-sub { font-size: 12px; color: #9aa0b2; margin-right: auto; }
.mh-dl-body { flex: 1; min-height: 0; overflow-y: auto; padding: 8px 0; }
.mh-task {
  display: flex; align-items: center; gap: 14px;
  padding: 14px 20px; border-bottom: 1px solid #f2f3f9;
}
.mh-task-main { flex: 1; min-width: 0; }
.mh-task-name { font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.mh-task-meta { font-size: 12px; color: #9aa0b2; margin-top: 3px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* 流媒体任务进度条（分片级进度，一个视频几百片） */
.mh-task-bar { height: 4px; border-radius: 2px; background: rgba(120,140,200,.18);
  margin-top: 6px; overflow: hidden; }
.mh-task-bar-fill { display: block; height: 100%; border-radius: 2px;
  background: linear-gradient(90deg, #6a9cff, #9d7bff); transition: width .3s; }

/* ---------- 捕获列表 ---------- */
.mh-list {
  flex: 1; min-width: 360px;
  display: flex; flex-direction: column;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 8px 26px rgba(35, 38, 47, 0.1);
  overflow: hidden;
}
.mh-list-head {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 14px;
  border-bottom: 1px solid #eef0f7;
  flex-wrap: wrap;
}
.mh-list-title { font-size: 14px; font-weight: 700; }
.mh-filters { display: flex; gap: 4px; flex: 1; }
.mh-filter {
  border: none; cursor: pointer;
  font-size: 11.5px; color: #7a8090;
  background: transparent;
  padding: 5px 8px; border-radius: 8px;
}
.mh-filter.on { background: #f0f2fb; color: #4a54a8; font-weight: 600; }
.mh-act {
  border: none; cursor: pointer;
  font-size: 12px; font-weight: 600; color: #fff;
  background: linear-gradient(135deg, #ff5f8f, #ff8a5f);
  padding: 7px 12px; border-radius: 10px;
}
.mh-act:disabled { opacity: 0.4; cursor: default; }
.mh-act.ghost { background: #f0f1f7; color: #7a8090; }
.mh-list-body { flex: 1; min-height: 0; overflow-y: auto; }
.mh-empty {
  height: 100%;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  color: #a0a5b4; text-align: center; padding: 20px;
}
.mh-empty-icon { font-size: 42px; margin-bottom: 10px; }
.mh-empty-t1 { font-size: 14px; font-weight: 600; color: #6a7080; }
.mh-empty-t2 { font-size: 12px; margin-top: 6px; }
.mh-item {
  display: flex; align-items: center; gap: 9px;
  padding: 10px 14px;
  border-bottom: 1px solid #f2f3f9;
}
.mh-item.done { opacity: 0.5; }
/* 疑似广告条：整行压暗，避免用户把它当成正片点下去 */
.mh-item.ad .mh-item-name { color: #9aa0aa; }
.mh-item.ad .b-hls { background: linear-gradient(135deg, #b9bec9, #d2d6df); }
.mh-v {
  display: inline-block; margin-right: 6px;
  padding: 0 5px; border-radius: 4px;
  font-size: 11px; font-weight: 600; line-height: 15px;
}
.mh-v.v-content { background: #e8f8ec; color: #1a9c46; border: 1px solid #b8e6c6; }
.mh-v.v-ad { background: #fdecec; color: #d4380d; border: 1px solid #f7c1bb; }
.mh-v.v-unknown { background: #f2f3f5; color: #8a8f99; border: 1px solid #e3e5e8; }
.mh-ad-why { margin-top: 2px; font-size: 11px; color: #d4380d; }
.mh-ad-note { margin-top: 2px; font-size: 11px; color: #a07d1f; }
.mh-badge {
  flex-shrink: 0;
  font-size: 11px; font-weight: 600; color: #fff;
  padding: 3px 9px; border-radius: 999px;
}
.b-video { background: linear-gradient(135deg, #ff5f8f, #ff8a5f); }
.b-audio { background: linear-gradient(135deg, #6a7bff, #8f9bff); }
.b-image { background: linear-gradient(135deg, #21c58b, #4fdba8); }
.b-hls { background: linear-gradient(135deg, #f5a623, #ffc46b); }
.b-other { background: #c3c8d6; }
.mh-item-main { flex: 1; min-width: 0; }
.mh-item-name {
  font-size: 12.5px; font-weight: 500;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mh-item-meta { font-size: 11px; color: #9ba0af; margin-top: 2px; }
.mh-dl {
  border: none; cursor: pointer;
  font-size: 11.5px; font-weight: 600; color: #fff;
  background: linear-gradient(135deg, #ff5f8f, #ff8a5f);
  padding: 6px 11px; border-radius: 9px;
  flex-shrink: 0;
}
.mh-dl:disabled { opacity: 0.4; cursor: default; }
.mh-mini {
  border: none; cursor: pointer;
  font-size: 11.5px; color: #7a8090;
  background: transparent;
  padding: 6px 6px; border-radius: 8px;
  flex-shrink: 0;
}
.mh-mini:hover { background: #f0f1f7; }

/* 下载管理顶栏：保存位置 pill + 「同时删除本地文件」勾选 */
.mh-save-pill {
  font-size: 12px; color: #5a6072;
  background: #f3f4fb; border: 1px solid #e4e7f2;
  padding: 4px 10px; border-radius: 999px;
  max-width: 380px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  min-width: 0;
}
.mh-del-chk { font-size: 12.5px; flex-shrink: 0; }

/* BT 下载弹窗（亮色风格） */
.mh-bt-body { display: flex; flex-direction: column; gap: 10px; }
.mh-bt-drop {
  border: 1.5px dashed #c4cbe0; border-radius: 10px;
  padding: 14px 10px; text-align: center;
  font-size: 12.5px; color: #8a90a6;
  background: #fafbff; cursor: pointer;
  transition: border-color .2s, background .2s;
}
.mh-bt-drop:hover { border-color: #9aa8d8; background: #f4f6ff; }
.mh-bt-foot { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.mh-bt-auto { display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: #5a6072; cursor: pointer; }

/* 经典界面的浅色主题也能容纳（新界面自带亮色，不依赖主题变量） */

/* ---------- 分类 chips + 磁贴角标 + 缩略图 + 排序 ---------- */
.mh-cats { display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; margin-bottom: 22px; }
.mh-subcats { margin-top: -12px; margin-bottom: 22px; gap: 8px; }
.mh-subcat { font-size: 12px; padding: 4px 13px; opacity: .92; }
.mh-cat {
  border: 1px solid #e6e9f2; background: #fff; color: #6a7080;
  font-size: 13px; padding: 7px 18px; border-radius: 999px; cursor: pointer;
  transition: all .12s;
}
.mh-cat:hover { border-color: #5b7cfa; color: #5b7cfa; }
.mh-cat.on {
  background: linear-gradient(135deg, #5b7cfa, #8f6bff);
  color: #fff; border-color: transparent; font-weight: 700;
}
.mh-tile { position: relative; }
.mh-tile-proxy {
  position: absolute; top: 10px; right: 12px;
  font-size: 10px; font-weight: 700; color: #b07b1a;
  background: #fff3d6; border: 1px solid #f0d9a0;
  padding: 1px 8px; border-radius: 999px;
}
/* GitHub 校验表：失效站（置灰）与留空位站（虚线待补） */
.mh-tile.dead { opacity: 0.45; filter: grayscale(0.9); }
.mh-tile.dead::before { opacity: 0.04; }
.mh-tile.dead:hover { transform: none; box-shadow: 0 4px 18px rgba(35, 38, 47, 0.07); }
.mh-tile.slot { border: 1.5px dashed #d5d9e6; box-shadow: none; opacity: 0.7; }
.mh-tile-dead-tag { color: #a02036; background: #ffe3e8; border-color: #f0b6c0; }
.mh-tile-slot-tag { color: #5a6072; background: #eef0f7; border-color: #d5d9e6; }
.mh-thumb {
  width: 58px; height: 44px; object-fit: cover; border-radius: 8px;
  border: 1px solid #e6e9f2; flex-shrink: 0; background: #f0f1f6;
}
.mh-sort {
  height: 30px; border: 1px solid #e6e9f2; border-radius: 9px;
  background: #fff; color: #23262f; font-size: 12px; padding: 0 8px; outline: none;
  margin-left: auto;
}
.mh-badge.b-doc { background: linear-gradient(135deg, #e8a33d, #f5c26b); }
.mh-badge.b-archive { background: linear-gradient(135deg, #8a63d2, #b39ddb); }
.mh-item-meta .doc-note { color: #9aa0b2; }
</style>
