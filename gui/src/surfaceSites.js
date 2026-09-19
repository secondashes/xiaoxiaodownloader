// 表世界站点注册表（唯一数据源）—— ModernHome 磁贴由本表驱动。
// 设计（2026-09-18 通宵任务）：
//   1. 每站带 desc（磁贴短说明）+ tip（完整说明：特点/风险/换域名方法）；
//   2. 无 svg 图标的站点统一用「分类图标」兜底（CAT_FALLBACK_ICON）；
//   3. GitHub 校验：应用启动后从发布仓库拉取 surface_sites.json
//      （raw.githubusercontent → jsDelivr 回退），status=ok 下发新地址 /
//      status=dead 标记失效 / extra 动态补新站（"留空位 + GitHub 验证"策略）。
//      本地 baseline 永远可用（离线/拉取失败不受影响）。
import chroma from 'chroma-js'
//   4. home 为空串 = 留空位（地址待 GitHub 校验下发，磁贴置灰"待补地址"）。

// 分类（磁贴区 chips 过滤 + 图标兜底 + 兜底配色）
// 顶层分类 = 细分板块规格（2026-09-18）：全部/常用/影视.看番/美术.艺术/音乐/电子书.书源/
// 游戏资源/ai制作/学术.医学/科学/资讯/软件.资源社区/磁力站；空分类自动隐藏（visibleCategories）。
export const CATEGORIES = [
  { key: 'all', label: '全部' },
  { key: 'freq', label: '常用' },
  { key: 'video', label: '影视 · 看番' },
  { key: 'art', label: '美术 · 艺术' },
  { key: 'music', label: '音乐' },
  { key: 'book', label: '电子书 · 书源' },
  { key: 'game', label: '游戏资源' },
  { key: 'ai', label: 'AI 制作' },
  { key: 'academic', label: '学术 · 医学' },
  { key: 'science', label: '科学' },
  { key: 'news', label: '资讯' },
  { key: 'res', label: '软件 · 资源社区' },
  { key: 'magnet', label: '磁力站' },
]

// 二级分类（细分板块规格）：影视.看番=综合/日韩剧/欧美剧/动漫番剧；
// 美术.艺术=灵感社区/博物馆画廊/素材图库；电子书.书源=综合图书馆/LibGen/轻小说/铅笔小说/白嫖站。
// 站点用 subs 数组，可同时属多个二级（如综合站同时挂"欧美剧"）。
export const SUBCATEGORIES = {
  video: [
    { key: 'gen', label: '综合' },
    { key: 'jpkr', label: '日韩剧' },
    { key: 'west', label: '欧美剧' },
    { key: 'anime', label: '动漫番剧' },
  ],
  art: [
    { key: 'community', label: '灵感 · 作品社区' },
    { key: 'museum', label: '博物馆 · 画廊' },
    { key: 'stock', label: '素材图库' },
  ],
  book: [
    { key: 'lib', label: '综合大型图书馆' },
    { key: 'libgen', label: 'LibGen' },
    { key: 'ltnovel', label: '轻小说' },
    { key: 'pencil', label: '铅笔小说' },
    { key: 'free', label: '白嫖站' },
  ],
}

// 分类兜底图标（站点没有专属 svg 时用；白色填充，铺在分类渐变底上）
export const CAT_FALLBACK_ICON = {
  video: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Zm6 4v8l7-4-7-4Z"/></svg>',
  music: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M20 3v12.2a3.8 3.8 0 1 1-2-3.3V7.4L10 9v9.2a3.8 3.8 0 1 1-2-3.3V5.5L20 3Z"/></svg>',
  book: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M4 3h7a3 3 0 0 1 3 3v15a2.5 2.5 0 0 0-2.5-2.5H4V3Zm16 0h-4a3 3 0 0 0-3 3v15a2.5 2.5 0 0 1 2.5-2.5H20V3Z"/></svg>',
  game: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M7 7h10a5 5 0 0 1 5 5c0 3-2 5-4.5 5-1.5 0-2.6-.7-3.5-1.8h-4C9.1 16.3 8 17 6.5 17 4 17 2 15 2 12a5 5 0 0 1 5-5Zm-.5 3v1.5H5V13h1.5v1.5H8V13h1.5v-1.5H8V10H6.5Zm10 .2a1.3 1.3 0 1 0 0 2.6 1.3 1.3 0 0 0 0-2.6Zm-2.5 3a1.3 1.3 0 1 0 0 2.6 1.3 1.3 0 0 0 0-2.6Z"/></svg>',
  ai: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M12 2l1.8 5.2L19 9l-5.2 1.8L12 16l-1.8-5.2L5 9l5.2-1.8L12 2Zm6 12l.9 2.6L21.5 18l-2.6.9L18 21.5l-.9-2.6L14.5 18l2.6-.9L18 14Z"/></svg>',
  academic: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M12 3 1 9l4 1.9V17c0 1.1 2.7 2.5 7 2.5s7-1.4 7-2.5v-6.1L23 9 12 3Zm0 2.2L19.5 9 12 12.8 4.5 9 12 5.2ZM6 12.5l6 3 6-3v4.9c-.9.8-3.2 1.6-6 1.6s-5.1-.8-6-1.6v-4.9Z"/></svg>',
  res: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M12 2 3 6v6c0 5 3.8 9.4 9 10 5.2-.6 9-5 9-10V6l-9-4Zm0 4.2 5 2.2v3.6c0 3.6-2.1 6.6-5 7.4-2.9-.8-5-3.8-5-7.4V8.4l5-2.2Z"/></svg>',
}

// 分类兜底配色（无品牌色的站点按主分类取色，视觉统一；chroma 和谐化在 tileVisual 统一做）
export const CAT_COLORS = {
  video: ['#e8557f', '#e8854f'],
  music: ['#6a5bff', '#9d8fff'],
  book: ['#d98f2b', '#e8b25f'],
  game: ['#21b573', '#5fd9a4'],
  ai: ['#8a4fff', '#b585ff'],
  academic: ['#3268ac', '#6f9fd0'],
  res: ['#4d6b8a', '#7f9bb8'],
  art: ['#d4380d', '#f07040'],
  magnet: ['#456'],
  news: ['#8d6e63', '#b09585'],
  science: ['#00838f', '#3dbdc9'],
}

// 站点表。字段：key唯一 / name / desc磁贴短说明 / tip完整说明 / cats分类(可多) /
// home主地址(空=留空位) / alts备用 / publish发布页或GitHub校验源 / proxy需系统代理 /
// c1,c2品牌渐变 / svg专属图标(缺省用分类兜底)
export const PLATFORMS = [
  // ============ 影视（综合） ============
  {
    key: 'bilibili', name: '哔哩哔哩', desc: '视频 / 直播 / 番剧', home: 'https://www.bilibili.com',
    tip: '国内最大视频社区。支持专属解析卡：打开视频页自动解析清晰度（登录后更高），可下载 MP4（音视频合并）/ 仅视频 / 仅音频。',
    c1: '#fb7299', c2: '#ff9eb5', cats: ['video'], subs: ['gen', 'anime'],
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M17.8 4.6l1.8-2.2a.7.7 0 1 1 1.1.9L19 5.5h2.2A2.8 2.8 0 0 1 24 8.3v9.4a2.8 2.8 0 0 1-2.8 2.8H2.8A2.8 2.8 0 0 1 0 17.7V8.3a2.8 2.8 0 0 1 2.8-2.8H5L3.3 3.3a.7.7 0 1 1 1.1-.9l1.8 2.2h12.6ZM6.2 10a1 1 0 0 0-1 1v3.2a1 1 0 1 0 2 0V11a1 1 0 0 0-1-1Zm11.6 0a1 1 0 0 0-1 1v3.2a1 1 0 1 0 2 0V11a1 1 0 0 0-1-1Z"/></svg>',
  },
  {
    key: 'jianyun', name: '简云影视', desc: '无广告影视 · 1080P', home: 'https://jianyunys.com/',
    tip: '主打纯净无广告、1080P 高清秒播。覆盖最新电影、电视剧、综艺、动漫、短剧，国产热播/美剧/韩剧都有，每日更新。播放时刷到的 m3u8 流会被捕获，可用"流媒体拼接"下载成 MP4。',
    c1: '#2f6fed', c2: '#6fa5ff', cats: ['video'],
  },
  {
    key: 'juzong', name: '剧踪影院', desc: '超清蓝光 · 超前更新', home: 'https://www.juzong01.me/',
    alts: ['https://1818dy.org'], publish: 'https://juzong.vip',
    tip: '主打超清蓝光、海内外 SVIP 超前更新，电影/剧集/动漫/综艺齐全，播放器有独家源/国内源/海外源可切换。域名易失效，记发布页 juzong.vip。',
    c1: '#e0485f', c2: '#ff8f9e', cats: ['video'],
  },
  {
    key: 'pianku', name: '片库', desc: '纯净影视 · 高清', home: 'https://piankuwan.com',
    alts: ['https://www.pianku.li'],
    tip: '纯净无广告方向、1080P 高清，电影/电视剧/综艺/动漫都有，更新频率高（有日更统计），支持搜索与分类，适合找完整剧集。主域名 pianku.li 已 410 弃用（2026-09-18 探测），现用 piankuwan.com。',
    c1: '#1d9f6e', c2: '#5fd9a4', cats: ['video'],
  },
  {
    key: 'kxyy', name: '开心影院', desc: '高清多线路', home: 'https://www.kxyytv.com/',
    alts: ['https://www.kxyy.app'],
    tip: '最新电影、热播剧更新及时，多条高清线路（推荐带 BD/YX 字样的源，速度画质更好）。页面较干净，覆盖电影/剧集/短剧/综艺/动漫。防走丢域名 kxyy.app。',
    c1: '#f0821e', c2: '#ffc078', cats: ['video'],
  },
  {
    key: 'xiaoya', invalid: true, name: '小鸭影音', desc: '港台影视聚合', home: 'https://777tv.ai/',
    alts: ['https://hk.xiaoyakankan.io', 'https://tw.xiaoyakankan.tv'],
    tip: '电影/电视剧/综艺/动漫全覆盖，每日更新，分类清晰（陆剧/韩剧/欧美剧），有人气排行。域名多，搜"小鸭影音 最新"找当前可用；另有小鸭看看港台镜像。',
    c1: '#f5b400', c2: '#ffd76b', cats: ['video'],
  },
  {
    key: 'mmov', name: 'mmov', desc: '影视聚合 · 多区域', home: 'https://tw.mmov.app/',
    alts: ['https://cn.mmov.im'],
    tip: '综合影视聚合站（港台/大陆多区域镜像），电影剧集综艺动漫都有，每日更新免费在线。搜"mmov 最新"可找当前可用镜像。',
    c1: '#5a4fd0', c2: '#9d8fff', cats: ['video'],
  },
  {
    key: 'youtube', name: 'YouTube', desc: '海外视频（需代理）', home: 'https://www.youtube.com',
    tip: '全球最大视频平台。需系统代理。播放中的视频流会被捕获；HLS(m3u8) 流用"流媒体拼接"下载合并为 MP4。',
    c1: '#ff0000', c2: '#ff5a5a', cats: ['video'], proxy: true,
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M23.5 7.2a3 3 0 0 0-2.1-2.1C19.5 4.5 12 4.5 12 4.5s-7.5 0-9.4.6A3 3 0 0 0 .5 7.2 31.3 31.3 0 0 0 0 12c0 1.6.2 3.2.5 4.8a3 3 0 0 0 2.1 2.1c1.9.6 9.4.6 9.4.6s7.5 0 9.4-.6a3 3 0 0 0 2.1-2.1c.3-1.6.5-3.2.5-4.8s-.2-3.2-.5-4.8ZM9.6 15.6V8.4l6.2 3.6-6.2 3.6Z"/></svg>',
  },

  // ============ 影视 · 动漫番剧（anime） ============
  {
    key: 'agefans', name: 'AGE动漫', desc: '动漫 · 番剧（域名常变）', home: 'https://agefans.ge',
    publish: 'https://github.com/agefanscom/website', gh: true,
    tip: '老牌专注动漫站，新番更新快、老番资源全，支持在线播放。域名因封锁常换：官方发布页 github.com/agefanscom/website（GitHub 校验源），失效时去发布页找最新地址。',
    c1: '#ff9f43', c2: '#ffc078', cats: ['video'], subs: ['anime'],
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><rect x="2" y="5" width="20" height="14" rx="2.5"/><rect x="22" y="9" width="2.5" height="6" rx="1" fill="#fff" opacity=".7"/></svg>',
  },
  {
    key: 'yinghua', invalid: true, name: '樱花动漫', desc: '动漫 · 新番（域名常变）', home: 'https://www.yhdmp.cc',
    tip: '樱花动漫（多镜像），新番更新快，日漫国漫全。域名常变且当前镜像证书异常（浏览器会警告），失效时搜索"樱花动漫 最新"找当前镜像。本机探测仅代理可达。',
    c1: '#ff7eb3', c2: '#ffb3c8', cats: ['video'], proxy: true,
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2Zm0 3.5 5 3-1.6 2.7L12 9.8 8.6 11.2 7 8.5Zm-3 8.3 6 2.2-1 2.4-5.5-1.6Z"/></svg>',
  },
  {
    key: 'zzzfun', invalid: true, name: 'ZzzFun', desc: '动漫 · 新番', home: 'http://www.zzzfun.com',
    tip: '新番资讯 + 在线播放，覆盖日漫国漫，更新及时，支持缓存，播放流畅画质不错。域名变动时搜"ZzzFun 最新"确认当前入口。',
    c1: '#7b5cff', c2: '#b39bff', cats: ['video'],
  },
  {
    key: 'omofun', invalid: true, name: 'OmoFun', desc: '免费动漫 · 高清', home: 'https://omo.fun',
    publish: 'https://github.com/omofundm/omofundm', gh: true,
    tip: '专注免费动漫：日漫/国漫/美漫高清播放，界面现代、分类筛选，追求少广告的追番体验，更新跟官方同步。发布页：GitHub omofundm/omofundm（GitHub 校验源）。',
    c1: '#00b8a9', c2: '#5fe3d0', cats: ['video'],
  },
  {
    key: 'xifan', name: '稀饭动漫', desc: '动漫 · 空位', home: '', slot: true,
    tip: '空位磁贴：默认不显示。GitHub 校验源（上游发布页/每日检测表）下发可用地址后自动出现。',
    c1: '#e86f8a', c2: '#ffb3c1', cats: ['video'],
  },
  {
    key: 'anfuns', name: 'Anfuns', desc: '动漫 · 空位', home: '', slot: true,
    tip: '空位磁贴：默认不显示。GitHub 校验源下发可用地址后自动出现。',
    c1: '#c56f3c', c2: '#ffb38a', cats: ['video'],
  },

  // ============ 常用平台 ============
  {
    key: 'douyin', name: '抖音', desc: '短视频 / 直播', home: 'https://www.douyin.com',
    tip: '刷到的无水印视频流会被实时捕获，点下载即可保存（可全选批量）。',
    c1: '#161823', c2: '#3c415c', cats: ['video'], subs: ['gen'],
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M16.6 3c.4 2.3 1.9 3.9 4.4 4.1v3c-1.7 0-3.2-.5-4.4-1.4v6.6c0 3.7-2.6 6.2-6 6.2-3.2 0-5.8-2.5-5.8-5.8 0-3.4 2.9-6 6.4-5.7v3.1c-1.8-.4-3.4.8-3.4 2.6 0 1.6 1.3 2.8 2.8 2.8 1.7 0 3-1.3 3-3.3V3h3Z"/></svg>',
  },
  {
    key: 'xhs', name: '小红书', desc: '图文 / 笔记', home: 'https://www.xiaohongshu.com',
    tip: '笔记图片与视频会被捕获，图片可单张或批量下载。',
    c1: '#ff2442', c2: '#ff6b7d', cats: [],
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><rect x="1" y="5" width="22" height="14" rx="3.2"/><text x="12" y="15.5" font-size="7.5" font-weight="bold" fill="#ff2442" text-anchor="middle">小红书</text></svg>',
  },
  {
    key: 'kuaishou', name: '快手', desc: '短视频 / 直播', home: 'https://www.kuaishou.com',
    tip: '短视频流实时捕获，支持批量下载。',
    c1: '#ff5000', c2: '#ff8a3d', cats: ['video'], subs: ['gen'],
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><circle cx="13.5" cy="12" r="7.5"/><rect x="2" y="7.6" width="3.2" height="8.8" rx="1.6"/></svg>',
  },
  {
    key: 'weibo', name: '微博', desc: '热搜 / 图文视频', home: 'https://weibo.com',
    tip: '热搜页/时间线的图片与视频会被捕获。',
    c1: '#e6162d', c2: '#f5606f', cats: ['news'],
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M10.1 20.6c-3.9.4-7.3-1.4-7.6-4-.3-2.6 2.6-5.1 6.5-5.5 3.9-.4 7.3 1.4 7.6 4 .3 2.7-2.6 5.1-6.5 5.5Zm3.3-4.6c-.4-1.5-2.2-2.3-4.1-1.9-2 .4-3.3 2-2.9 3.5.4 1.5 2.2 2.3 4.1 1.9 2-.4 3.3-2 2.9-3.5ZM18 10.8a.9.9 0 0 1-1.1-.6.9.9 0 0 1 .6-1.1 1.7 1.7 0 0 0 1.1-2.1 1.7 1.7 0 0 0-2.1-1.2.9.9 0 0 1-.5-1.8 3.5 3.5 0 0 1 4.3 2.4A3.5 3.5 0 0 1 18 10.8Zm3.4 1a.9.9 0 0 1-1.1-.7.9.9 0 0 1 .7-1 3.6 3.6 0 0 0 2.7-4.3 3.6 3.6 0 0 0-4.3-2.7.9.9 0 0 1-.4-1.8 5.4 5.4 0 0 1 6.4 4.1 5.4 5.4 0 0 1-4 6.4Z"/></svg>',
  },
  {
    key: 'zhihu', name: '知乎', desc: '问答 / 专栏', home: 'https://www.zhihu.com',
    tip: '问答与专栏长文可一键"存为 Word"（文字/表格/图片按原位置导出）。',
    c1: '#0066ff', c2: '#4d94ff', cats: ['academic'],
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M5.7 7.2v9.9H4.9c-.1-1.6-.6-2.9-1.6-3.8l.4-.5c.6.6 1 1.3 1.2 2.1V7.2h.8Zm4.8 8.3c-.4-.4-1-.9-1.7-1.3v1.7H8v-3.4c-.3.5-.7 1-1.1 1.4l-.4-.6c.6-.6 1.1-1.4 1.5-2.3H6.8v-.7h1.2V8.5h.8v1.8h1.3v.7h-1.3v.8c.7.4 1.2.8 1.7 1.2l-.4.5Zm7.6 1.6h-5.6v-8h5.6v8Zm-.8-7.2h-4v6.4h4V9.9Z"/></svg>',
  },

  // ============ 音乐 ============
  {
    key: 'music163', name: '网易云', desc: '音乐 / MV', home: 'https://music.163.com',
    tip: '评论区氛围最强，免费内容多。MV/封面媒体会被捕获下载；黑胶 VIP 曲目仅能抓到试听片段。',
    c1: '#c20c0c', c2: '#e85656', cats: ['music'],
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M12 0a12 12 0 1 0 12 12A12 12 0 0 0 12 0Zm4.9 10.9c-.8 0-1.5-.6-1.5-1.4 0-.5.2-.9.6-1.2a4.6 4.6 0 0 0-3-1.1h-.7l-1.5 8.4a3.6 3.6 0 0 1-3.5 3A3.4 3.4 0 0 1 4 15.2a3.4 3.4 0 0 1 3.4-3.4h.4l.4 1.7a1.5 1.5 0 0 0-.8-.2 1.7 1.7 0 1 0 1.7 2l1.6-8.8.1-.4a6.3 6.3 0 0 1 4.9 1.8 1.5 1.5 0 0 1 .7-.2 1.5 1.5 0 0 1 .5 2.9Z"/></svg>',
  },
  {
    key: 'tonzhon', invalid: true, name: '铜钟音乐', desc: '极简在线听歌', home: 'https://tonzhon.whamon.com/',
    tip: '开源极简在线听歌站：搜索歌曲/播放列表/滚动歌词/创建歌单，无广告无社交干扰。注意原 tonzhon.com 已非正版，用 whamon 镜像。播放的音频流可直接捕获下载。',
    c1: '#1fae6a', c2: '#6fe3a8', cats: ['music'],
  },
  {
    key: 'gequbao', name: '歌曲宝', desc: '全网搜歌 · 导出', home: 'https://www.gequbao.com',
    tip: '全网歌曲搜索试听 + 多格式导出下载，适合快速找歌。下载链接（mp3/flac）会被捕获。',
    c1: '#f06292', c2: '#ffa4c3', cats: ['music'],
  },
  {
    key: 'hifini', invalid: true, name: 'HiFiNi', desc: '无损音乐分享', home: 'https://www.hifini.com',
    tip: '音乐磁场：FLAC/APE 无损分享社区，资源质量高，需注册/积分下载。下载附件会被捕获。',
    c1: '#8a6fd1', c2: '#c0aef0', cats: ['music'],
  },
  {
    key: 'listen1', name: 'Listen1', desc: '聚合播放器(开源)', home: 'https://listen1.github.io/listen1/',
    publish: 'https://github.com/listen1/listen1_chrome_extension', gh: true,
    tip: '开源聚合播放器（GitHub 校验源 listen1_chrome_extension / listen1_desktop）：聚合网易云/QQ/酷狗/咪咕/B站等的免费内容，播放失败自动切源，插件版+桌面版。只聚合各平台免费内容，非破解。',
    c1: '#3b82f6', c2: '#8fb8ff', cats: ['music'],
  },
  {
    key: 'lxmusic', name: '洛雪音乐', desc: '开源音乐 · 音源', home: 'https://github.com/lyswhut/lx-music-desktop',
    publish: 'https://github.com/lyswhut/lx-music-desktop', gh: true,
    tip: '开源跨平台音乐播放器（GitHub 校验源 lyswhut/lx-music-desktop）：配合社区音源插件实现标准/无损/Hi-Res 直链下载，无广告无需登录。音源需另行导入（社区维护）。',
    c1: '#7209b7', c2: '#b57bee', cats: ['music'],
  },
  {
    key: 'suno', name: '苏诺之音', desc: 'AI 生成歌曲', home: 'https://www.suno.cn',
    tip: '国内 Suno AI 站点：用文字描述生成歌曲，适合玩 AI 音乐创作。生成的音频可捕获下载。',
    c1: '#e84393', c2: '#fd79a8', cats: ['music', 'ai'],
  },

  // ============ 电子书 · 书源 ============
  {
    key: 'jiumo', name: '鸠摩搜书', desc: '电子书搜聚合（直连）', home: 'https://www.jiumodiary.com',
    tip: '电子书搜索聚合引擎：输入书名聚合各网盘/站点资源（pdf/epub/mobi），直连可用。搜到的文档链接会被捕获为"文档"类可下载。',
    c1: '#e8a33d', c2: '#f5c26b', cats: ['book'],
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M4 3h7a3 3 0 0 1 3 3v15a2.5 2.5 0 0 0-2.5-2.5H4V3Zm16 0h-4a3 3 0 0 0-3 3v15a2.5 2.5 0 0 1 2.5-2.5H20V3Z"/></svg>',
  },
  {
    key: 'zlib', name: 'Z-Library', desc: '电子书（需代理）', home: 'https://z-library.sk',
    alts: ['https://z-lib.fm/'],
    tip: '全球最大电子书库之一，需系统代理。域名极常变（2026-09-18 探测主域已不可达，待 GitHub 校验表下发新地址；也可搜索"Z-Library 最新地址"）。PDF/EPUB 下载会被捕获。',
    c1: '#1a73c9', c2: '#5aa2e8', cats: ['book'], subs: ['lib'], proxy: true,
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M12 6c-1.8-1.6-4.2-2.5-7-2.5H2v14h4.5c1.9 0 3.7.6 5.5 1.5 1.8-.9 3.6-1.5 5.5-1.5H22v-14h-3c-2.8 0-5.2.9-7 2.5Zm-3 2.3V19c-1.4-.6-2.9-1-4.5-1V8c1.7 0 3.2.3 4.5 1Zm6.5-1.3c1.3-.7 2.8-1 4.5-1v10c-1.6 0-3.1.4-4.5 1V7.3Z"/></svg>',
  },
  {
    key: 'annas', name: "Anna's Archive", desc: '全网书聚合（需代理）', home: 'https://annas-archive.org',
    tip: '聚合全球图书馆/书站资源的开源搜索引擎（影子图书馆），需系统代理。PDF/EPUB 下载会被捕获。',
    c1: '#7c3aed', c2: '#a78bfa', cats: ['book'], proxy: true,
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M6 2h9l5 5v15H6V2Zm8 1.5V8h4.5L14 3.5ZM8 12h8v1.5H8V12Zm0 3h8v1.5H8V15Zm0-6h5v1.5H8V9Z"/></svg>',
  },
  {
    key: 'legado', name: 'aoaostar书源', desc: '书源 3900+ 一站式', home: 'https://legado.aoaostar.com',
    publish: 'https://github.com/aoaostar/legado', gh: true,
    tip: 'Legado（阅读3.0 App）书源聚合仓库（GitHub 校验源 aoaostar/legado）：全量书源约 3900+ 条每日同步检测，含精品/破冰/关耳女频等，网页上一键导入到阅读 App。书源 = JSON 规则，导入后在手机/桌面阅读 App 里搜书读正文。',
    c1: '#d35400', c2: '#f0a05a', cats: ['book'],
  },
  {
    key: 'xiu2', name: 'XIU2书源', desc: '精品书源 · 少而精', home: 'https://yuedu.xiu2.xyz',
    publish: 'https://github.com/XIU2/Yuedu', gh: true,
    tip: 'XIU2 精品书源（GitHub 校验源 XIU2/Yuedu）：作者自用精选 20+ 条，更新稳定、失效少、解析质量高，适合不想导太多源的用户。网络导入地址见页面（jsDelivr/Bitbucket 多 CDN）。',
    c1: '#16a085', c2: '#5fd9c0', cats: ['book'],
  },
  {
    key: 'pxsource', name: 'Pixiv书源', desc: 'Pixiv 小说导入阅读', home: 'https://pixivsource.pages.dev',
    publish: 'https://github.com/DowneyRem/PixivSource', gh: true,
    tip: '专为阅读 App 设计的 Pixiv 小说书源（GitHub 校验源 DowneyRem/PixivSource）：搜索作者/发现/书签/登录检测。配合本软件里世界的 Pixiv 登录使用体验更佳。教程站含快速开始与功能手册。',
    c1: '#0096fa', c2: '#66c2ff', cats: ['book'],
  },

  // ============ 游戏 ============
  {
    key: 'itch', name: 'itch.io', desc: '独立游戏 · 免费', home: 'https://itch.io',
    tip: '全球独立游戏宝藏：大量开发者免费游戏/试玩版，"Name your own price" 可填 0，创意多无套路。本机探测仅代理可达（部分地区可直连）。游戏包（zip）会被捕获下载。',
    c1: '#fa5c5c', c2: '#ff9d9d', cats: ['game'], proxy: true,
  },
  {
    key: 'epic', name: 'Epic 喜加一', desc: '每周限免', home: 'https://store.epicgames.com/free-games',
    tip: 'Epic 每周固定送 1-2 款游戏（常有 3A 大作），领取后永久拥有，国区基本可用。周四更新，记得每周来看。',
    c1: '#2a2a2a', c2: '#6b6b6b', cats: ['game'],
  },
  {
    key: 'steam', name: 'Steam', desc: '免费游戏 · 特惠', home: 'https://store.steampowered.com',
    tip: '大量 F2P 永久免费游戏 + 限时免费（Free to Keep）+ 免费周末试玩，社区评价真实。商店国内间歇可直连（2026-09-18 探测直连超时），打不开时开系统代理。',
    c1: '#1b2838', c2: '#4c6b8a', cats: ['game'], proxy: true,
  },
  {
    key: 'krzacg', name: 'KrzACG', desc: 'Galgame 汉化', home: 'https://www.krzacg.com',
    tip: '每日更新绅士向 ACG / Galgame 汉化资源，分类清晰资源较全，适合找日系 RPG/SLG/ADV。下载前建议杀毒扫描。',
    c1: '#ff7597', c2: '#ffb3c6', cats: ['game'],
  },
  {
    key: 'kungal', name: '鲲 Galgame', desc: 'Gal 资源社区', home: 'https://www.kungal.com',
    tip: '开源 Galgame 资源社区：免费下载列表丰富（PC/模拟器），更新活跃，强调分享，二次元圈口碑好。',
    c1: '#0abde3', c2: '#6bd9f0', cats: ['game'],
  },
  {
    key: 'twodfan', name: '2DFan', desc: 'Gal 补丁 · 汉化', home: 'https://2dfan.com',
    tip: 'Galgame 补丁/汉化资源讨论社区，找汉化补丁与存档修改的首选。本机探测仅代理可达。',
    c1: '#596275', c2: '#97a5c0', cats: ['game'], proxy: true,
  },
  {
    key: 'threedm', name: '3DM', desc: '老牌游戏资源', home: 'https://www.3dmgame.com',
    tip: '老牌游戏站：免费汉化/补丁/单机资源多，社区活跃。广告较多，建议配合广告拦截；口碑两极，资源全。',
    c1: '#4a69bd', c2: '#82a0e8', cats: ['game'],
  },

  // ============ AI 制作 ============
  {
    key: 'civitai', name: 'Civitai', desc: '最大 AI 模型库（需代理）', home: 'https://civitai.com',
    tip: '全球最大 AI 绘画模型社区：底模/LoRA/Embedding/ControlNet/工作流最全（15万+），有评分/触发词/推荐设置。下载 safetensors 格式，注意许可证。需系统代理；模型文件下载会被捕获。',
    c1: '#2a5fd0', c2: '#6f9bff', cats: ['ai'], proxy: true,
  },
  {
    key: 'hf', name: 'Hugging Face', desc: '官方模型权重（需代理）', home: 'https://huggingface.co',
    tip: '官方与研究级模型首选：SDXL/Flux/Wan2.1/HunyuanVideo 等开源权重+量化版，许可证清晰。国内可改用镜像 hf-mirror.com 加速。需系统代理。',
    c1: '#ffd21e', c2: '#ffe98a', cats: ['ai'], proxy: true,
  },
  {
    key: 'liblib', name: 'LiblibAI', desc: '国内 AI 绘画社区', home: 'https://www.liblib.art',
    tip: '哩布哩布 AI：国内最大 AI 绘画模型社区（免翻墙），10万+ 模型，国风/二次元/写实 LoRA 丰富，仿 C 站界面，支持在线生图/云端训练，网盘直链下载快。',
    c1: '#6c5ce7', c2: '#a99cff', cats: ['ai'],
  },
  {
    key: 'modelscope', name: '魔搭社区', desc: '阿里系模型', home: 'https://modelscope.cn',
    tip: '阿里 ModelScope：Wan2.1/通义系等开源模型权重完整，国内下载快，镜像友好。',
    c1: '#6a5acd', c2: '#9d8fff', cats: ['ai'],
  },
  {
    key: 'openart', name: 'OpenArt', desc: 'ComfyUI 工作流（需代理）', home: 'https://openart.ai/workflows',
    tip: '高质量 ComfyUI 工作流分享：节点图 + 配套模型推荐，直接导入 ComfyUI 使用。需系统代理。',
    c1: '#e17055', c2: '#f5a582', cats: ['ai'], proxy: true,
  },
  {
    key: 'tensorart', name: 'Tensor.Art', desc: '在线生图 · 模型库', home: 'https://tensor.art',
    tip: '在线生成 + 模型库一体，二次元向模型多，LoRA 社区活跃，免费额度日常够用。',
    c1: '#0984e3', c2: '#74b9ff', cats: ['ai'],
  },

  // ============ 学术 · 医学 ============
  {
    key: 'dxy', name: '丁香园', desc: '医学 · 药学（直连）', home: 'https://www.dxy.cn',
    tip: '国内医学药学专业社区：用药参考、文献、指南。文章可"存为 Word"。',
    c1: '#0e9488', c2: '#5eead4', cats: ['academic'],
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M12 2a3 3 0 0 1 3 3v4h4a3 3 0 0 1 0 6h-4v4a3 3 0 0 1-6 0v-4H5a3 3 0 0 1 0-6h4V5a3 3 0 0 1 3-3Z"/></svg>',
  },
  {
    key: 'pubmed', name: 'PubMed', desc: '医学文献（需代理）', home: 'https://pubmed.ncbi.nlm.nih.gov',
    tip: '美国国立医学图书馆生物医学文献库，医学检索权威。需系统代理；部分全文 PDF 可捕获。',
    c1: '#3268ac', c2: '#6b9bd6', cats: ['academic'], proxy: true,
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M4 3h13a2 2 0 0 1 2 2v3h-2V5H6v14h5v2H4V3Zm15 7-7 7-3-3 1.4-1.4L13 15.2l4.6-4.6L19 10Z"/></svg>',
  },
  {
    key: 'scholar', name: 'Google 学术', desc: '学术搜索（需代理）', home: 'https://scholar.google.com',
    tip: '学术文献搜索引擎：引用/版本/相关文章。需系统代理。',
    c1: '#4285f4', c2: '#7aa7ff', cats: ['academic'], proxy: true,
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M12 3 1 9l4 1.9V17c0 1.1 2.7 2.5 7 2.5s7-1.4 7-2.5v-6.1L23 9 12 3Zm0 2.2L19.5 9 12 12.8 4.5 9 12 5.2ZM6 12.5l6 3 6-3v4.9c-.9.8-3.2 1.6-6 1.6s-5.1-.8-6-1.6v-4.9Z"/></svg>',
  },
  {
    key: 'arxiv', name: 'arXiv', desc: '科学预印本（需代理）', home: 'https://arxiv.org',
    tip: '物理/数学/CS 预印本库，论文 PDF 免费下载（会被捕获为"文档"）。需系统代理。',
    c1: '#b31b1b', c2: '#e06666', cats: ['academic'], proxy: true,
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M4 3h16v3H4V3Zm0 5h16v2.5H4V8Zm0 4.5h16V15H4v-2.5ZM4 17h10v2.5H4V17Z"/></svg>',
  },
  {
    key: 'cnki', name: '中国知网', desc: '学术文献（直连）', home: 'https://www.cnki.net',
    tip: '国内最大中文学术文献库，硕博论文/期刊/会议。正文下载一般需机构权限。',
    c1: '#1a5cb0', c2: '#5a8ad6', cats: ['academic'],
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><circle cx="12" cy="12" r="9"/><path d="M10 6h4v4.5l4 2.5-2 3-3.5-2.2L9 16l-2-3 4-2.5V10.5L8.5 9 10 6Z" fill="#1a5cb0"/></svg>',
  },

  // ============ 软件 · 资源社区 ============
  {
    key: 'github', name: 'GitHub', desc: '开源资源（代理/直连）', home: 'https://github.com',
    tip: '全球最大开源托管平台：软件/脚本/模型发布页。Release 附件下载会被捕获。本软件的站点校验表也托管在 GitHub 上。',
    c1: '#24292e', c2: '#57606a', cats: ['res'], proxy: true,
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M12 1.5A10.5 10.5 0 0 0 8.7 22c.5.1.7-.2.7-.5v-1.8c-3 .6-3.6-1.4-3.6-1.4-.5-1.2-1.2-1.6-1.2-1.6-1-.7 0-.7 0-.7 1.1.1 1.7 1.2 1.7 1.2 1 1.7 2.6 1.2 3.2.9.1-.7.4-1.2.7-1.5-2.4-.3-4.9-1.2-4.9-5.3 0-1.2.4-2.1 1.1-2.9-.1-.3-.5-1.4.1-2.9 0 0 1-.3 3.1 1.2a10.7 10.7 0 0 1 5.6 0c2.2-1.5 3.1-1.2 3.1-1.2.6 1.5.2 2.6.1 2.9.7.8 1.1 1.7 1.1 2.9 0 4.1-2.5 5-4.9 5.3.4.3.8 1 .8 2v2.9c0 .3.2.6.7.5A10.5 10.5 0 0 0 12 1.5Z"/></svg>',
  },
  {
    key: 'wiki', name: '维基百科', desc: '百科知识（需代理）', home: 'https://zh.wikipedia.org',
    tip: '自由百科全书，条目可"存为 Word"离线阅读。需系统代理。',
    c1: '#4d4d4d', c2: '#8c8c8c', cats: ['res'], proxy: true,
    svg: '<svg viewBox="0 0 24 24" fill="#fff"><path d="M12.6 11.7 8.9 3.5H3.2l5.5 12.4a.3.3 0 0 1 0 .1L12.6 11.7Zm1 .3L17.7 20l3.1-7-4.3-9.7-2.9 8.7ZM8.6 18 6.9 14H3.5L8.6 18Z"/></svg>',
  },
  {
    key: 'ghxi', name: '果核剥壳', desc: '绿色软件 · 更新快', home: 'https://www.ghxi.com',
    tip: '绿色/免安装软件站，覆盖 PC 和安卓，资源更新快、相对干净、无过多捆绑。',
    c1: '#e67e22', c2: '#f5b06a', cats: ['res'],
  },
  {
    key: 'appinn', name: '小众软件', desc: '小众实用工具', home: 'https://www.appinn.com',
    tip: '偏小众实用工具推荐博客，文章详细，下载链接靠谱，发现好工具的首选。',
    c1: '#27ae60', c2: '#6fd79f', cats: ['res'],
  },
  {
    key: 'pojie', name: '吾爱破解', desc: '技术社区 · 资源', home: 'https://www.52pojie.cn',
    tip: '国内知名技术社区：去广告/绿色版/逆向讨论多。资源需自行判断（论坛性质），下载后建议杀毒扫描。',
    c1: '#c0392b', c2: '#e67e6b', cats: ['res'],
  },
  {
    key: 'four23', name: '423Down', desc: '老牌软件站', home: 'https://www.423down.com',
    tip: '老牌软件站：办公/设计/系统工具多，审核较严，绿色版质量较高。',
    c1: '#2980b9', c2: '#6db3e8', cats: ['res'],
  },
  {
    key: 'mpyit', name: '殁漂遥', desc: '绿色便携软件', home: 'https://www.mpyit.com',
    tip: '专注绿色便携软件的下载站，免安装解压即用。',
    c1: '#16a085', c2: '#5fd9c0', cats: ['res'],
  },

  // ============ 影视 · 综合（gen） ============
  {
    key: 'xinghe', name: '星河影视', desc: '高清无广告 · 弹幕', home: 'https://www.xhkan.top/',
    tip: '高清无广告的免费影视站，支持弹幕，观影体验干净。失效时可搜索"星河影视"确认当前入口。',
    c1: '#5b8def', c2: '#8fb8ff', cats: ['video'], subs: ['gen'], proxy: true,
  },
  {
    key: 'zhuiying', name: '追影', desc: '蓝光高清 · 免费秒播', home: 'https://zhuiying3.cc/',
    tip: '主打蓝光高清、无广告免费秒播，电影剧集直接看。站点地址可能调整，打不开时搜"追影 最新"。',
    c1: '#e8506e', c2: '#ff92a5', cats: ['video'], subs: ['gen'],
  },
  {
    key: 'douhua', name: '豆花电影网', desc: '免费电影 · 在线观看', home: 'https://dhvideo.cc/',
    tip: '最新免费电影在线观看，新片老片都能搜到。免费源清晰度参差，优先选高清线路。',
    c1: '#3fbf7f', c2: '#7fe3b0', cats: ['video'], subs: ['gen'],
  },
  {
    key: 'fandazi', name: '饭搭子影视', desc: '影视综艺动漫 · 全覆盖', home: 'https://fdzys.com',
    tip: '热门电影、电视剧、动漫、综艺聚合，分类全、更新勤。免费站广告偶有，建议配合广告拦截。',
    c1: '#f2a541', c2: '#ffd07a', cats: ['video'], subs: ['gen'],
  },
  {
    key: 'sasp', name: 'SA视频', desc: '影视综艺 · 免费看', home: 'https://www.lsjys11.com/',
    tip: '最新电影、电视剧、动漫、综艺免费在线观看，更新及时。多线路播放，卡顿时切换线路。',
    c1: '#7a5cf0', c2: '#b39bff', cats: ['video'], subs: ['gen'],
  },
  {
    key: 'dp66', name: '66大片网', desc: '免费电影 · 在线看', home: 'https://www.77dpw.vip/',
    tip: '免费电影在线观看，大片老片都有，页面简洁。域名后缀偶有更换，失效时搜"66大片"。',
    c1: '#2c9fd6', c2: '#7cc8ee', cats: ['video'], subs: ['gen'],
  },
  {
    key: 'changz', name: '厂长资源', desc: '老牌资源 · 片源多', home: 'https://www.czzymovie.com',
    tip: '老牌影视资源站，片源多，冷门片也常能找到。页面较朴素，重在资源扎实。',
    c1: '#c0392b', c2: '#e88877', cats: ['video'], subs: ['gen'],
  },
  {
    key: 'duboku', name: '独播库', desc: '美剧电影 · 更新快', home: 'https://www.dbku.tv',
    tip: '美剧/电影聚合站，更新快，剧集分类清晰。域名有过更换，失效时搜"独播库 最新"。',
    c1: '#16a085', c2: '#6fd9bd', cats: ['video'], subs: ['gen'],
  },
  {
    key: 'naifei', name: '奈飞工厂', desc: '影视聚合 · 域名常变', home: 'https://www.netflixgc.com',
    alts: ['https://naifei.fyi/'],
    tip: '影视聚合站，电影剧集综艺较全，跟进热门更新。域名常变，主站打不开时换备用地址或搜"奈飞工厂 最新"。',
    c1: '#e6412e', c2: '#ff8a70', cats: ['video'], subs: ['gen'],
  },
  {
    key: 'movieffm', name: 'Movieffm', desc: '综合影视 · 聚合站', home: 'https://www.movieffm.net',
    tip: '综合影视聚合站（"电影啊"），热门电影剧集都有收录。聚合源质量不一，播放前多试几条线路。',
    c1: '#4a69bd', c2: '#8fa8e8', cats: ['video'], subs: ['gen'], proxy: true,
  },
  {
    key: 'iyf', name: '爱壹帆', desc: '港台陆剧 · 综艺聚合', home: 'https://iyf.tv',
    alts: ['https://www.iyf.tv/'],
    tip: '港台陆剧与综艺聚合，更新快，海外华语观众常用。主域名与备用域名二选一，打不开时切换。',
    c1: '#0f4c81', c2: '#5a8fc0', cats: ['video'], subs: ['gen'],
  },
  {
    key: 'eyny', name: '伊莉影音', desc: '影视聚合 · 港台向', home: 'https://eynytv.com/',
    tip: '影视聚合站，港台内容见长，剧集综艺都有。失效时搜"伊莉影音"确认入口。',
    c1: '#9b59b6', c2: '#c9a0e8', cats: ['video'], subs: ['gen'],
  },
  {
    key: 'iqiyi', name: '爱奇艺', desc: '官方 · 免费专区+限免', home: 'https://www.iqiyi.com',
    tip: '官方视频平台，有免费专区和限免内容，综艺与自制剧是强项。热门内容多需 VIP，等限免更划算。',
    c1: '#00be06', c2: '#6fe06f', cats: ['video'], subs: ['gen'],
    // 官方平台正片走 Widevine DRM；本项目 Electron 不带 CDM（实测 EME 三种 key system 全部
    // NotSupportedError），播不了。标注出来是为了在打开时给出解释，而不是让用户对着黑屏猜。
    drm: true,
  },
  {
    key: 'tencent', name: '腾讯视频', desc: '官方 · 免费剧集+限免', home: 'https://v.qq.com',
    tip: '官方平台，免费剧集与限免内容不少，国产剧综艺储备大。热门剧集多需 VIP，关注限免片单。',
    c1: '#ff6040', c2: '#ff9e80', cats: ['video'], subs: ['gen'], drm: true,
  },
  {
    key: 'youku', name: '优酷', desc: '官方 · 免费剧集+限免', home: 'https://www.youku.com',
    tip: '官方平台，免费剧集+限免内容持续更新，老剧库深。部分内容需会员，限免片单常换。',
    c1: '#1ec0ff', c2: '#7cdcff', cats: ['video'], subs: ['gen'], drm: true,
  },
  {
    key: 'mgtv', name: '芒果TV', desc: '官方 · 综艺见长', home: 'https://www.mgtv.com',
    tip: '官方平台，综艺见长，限免剧集持续更新。王牌综艺多，热门档期内容需会员。',
    c1: '#ffb300', c2: '#ffd479', cats: ['video'], subs: ['gen'], drm: true,
  },

  // ============ 影视 · 日韩剧（jpkr） ============
  {
    key: 'doki8', invalid: true, name: '心动日剧', desc: '日剧 · 大河剧 · 弹幕', home: 'http://www.doki8.com/',
    tip: '大河剧、经典日剧与新番剧收集，页面整洁并支持弹幕。失效时搜"心动日剧"找当前入口。',
    c1: '#e91e63', c2: '#f58ab0', cats: ['video'], subs: ['jpkr'],
  },
  {
    key: 'fanxinzhui', name: '追新番', desc: '日剧资源 · 网盘下载', home: 'http://www.fanxinzhui.com/',
    tip: '日剧资源收集站，附网盘下载，免费无广告。番剧跟进日更，链接失效较常见，以站内最新为准。',
    c1: '#3d8bfd', c2: '#8ab8ff', cats: ['video'], subs: ['jpkr'], proxy: true,
  },
  {
    key: 'hanjutv', name: '韩剧TV', desc: '韩剧韩综 · 更新快', home: 'https://www.hanjutvcn.com/',
    tip: '韩剧韩综资源多、更新快，追新韩剧方便。域名常变，失效时搜"韩剧TV 最新"找当前入口。',
    c1: '#ce50b3', c2: '#f091d8', cats: ['video'], subs: ['jpkr'],
  },

  // ============ 影视 · 动漫番剧（anime） ============
  {
    key: 'acfun', name: 'AcFun', desc: '弹幕站 · 番剧+国创', home: 'https://www.acfun.cn',
    tip: '官方弹幕视频站，番剧与国创内容都有，社区氛围老牌。部分内容需大会员，免费区日常够看。',
    c1: '#fd4c5d', c2: '#ff8f99', cats: ['video'], subs: ['anime'],
  },
  {
    key: 'aowu', invalid: true, name: '嗷呜动漫', desc: '免费动漫 · 在线看', home: 'https://www.aowu.tv/',
    alts: ['https://www.aowudm.com/'],
    tip: '免费动漫在线观看，新番老番都收录，更新较勤。主站与备用站二选一，打不开时切换。',
    c1: '#d35400', c2: '#eb984e', cats: ['video'], subs: ['anime'],
  },
  {
    key: 'nyafun', name: 'NyaFun', desc: '动漫在线 · ACG资源', home: 'https://www.nyacg.net/',
    tip: '动漫在线播放 + ACG 资源聚合，新番跟进快。失效时搜"NyaFun"确认当前入口。',
    c1: '#8e44ad', c2: '#c08ce8', cats: ['video'], subs: ['anime'],
  },
  {
    key: 'jocy', name: '囧次元', desc: '番剧在线 · 界面清爽', home: 'https://www.jcydm1.com/',
    alts: ['https://www.jocyweb.com/', 'https://www.9ciyuan.com/'],
    tip: '番剧在线观看，界面清爽、播放线路多，追番体验不错。域名有多个备用，主站失效时换用备站。',
    c1: '#18a999', c2: '#7ad9cd', cats: ['video'], subs: ['anime'],
  },
  {
    key: 'gugufan', invalid: true, name: '咕咕番', desc: '番剧在线 · 追更', home: 'https://www.gugufan.com/',
    alts: ['https://www.gugufan.org/', 'https://www.gugu3.com/'],
    tip: '番剧在线追更，新番时间表清晰，老番也补得全。提供多个备用域名，失效时逐个切换。',
    c1: '#ff8c42', c2: '#ffc49b', cats: ['video'], subs: ['anime'], proxy: true,
  },
  {
    key: 'dalv', invalid: true, name: '打驴动漫', desc: '动漫资源站', home: 'https://www.dqsj.cc/',
    alts: ['https://www.dalv666.top/'],
    tip: '动漫资源站，番剧资源较全，以在线观看为主。域名有备用，主站打不开时切换。',
    c1: '#0fb9b1', c2: '#6fe0da', cats: ['video'], subs: ['anime'],
  },
  {
    key: 'wudm', name: '五弹幕', desc: '弹幕番剧站', home: 'https://www.5dm.link/',
    tip: '弹幕番剧站，看番带弹幕氛围，新番持续更新。失效时搜"五弹幕 最新"。',
    c1: '#2980d9', c2: '#7fb4ef', cats: ['video'], subs: ['anime'],
  },
  {
    key: 'mxdm', name: 'MX动漫', desc: '动漫在线 · 多线路', home: 'https://www.mxdm6.com/',
    alts: ['https://www.mxdmp.com/'],
    tip: '动漫在线观看，线路多、分类全，新番老番都有。主站与备用站切换使用。',
    c1: '#d64f7a', c2: '#f093b3', cats: ['video'], subs: ['anime'], proxy: true,
  },
  {
    key: 'mgnacg', name: '橘子动漫', desc: '动漫在线 · 免费看', home: 'https://www.mgnacg.com/',
    tip: '动漫在线免费观看，界面简洁，番剧更新稳定。失效时搜"橘子动漫 最新"。',
    c1: '#f6b93b', c2: '#ffd988', cats: ['video'], subs: ['anime'],
  },
  {
    key: 'ntdm', invalid: true, name: 'NT动漫', desc: '动漫在线 · 更新稳', home: 'https://ntdm.fans/',
    alts: ['https://www.ntdm9.com/'],
    tip: '动漫在线站，番剧资源持续更新，老番收录也不少。主站失效时换备用域名（2026-09-18 探测主/备域名均不可达，失效时搜"NT动漫 最新"）。',
    c1: '#27ae60', c2: '#7ed9a2', cats: ['video'], subs: ['anime'],
  },
  {
    key: 'd1', name: '第一动漫', desc: '动漫在线 · 免费', home: 'https://d1-dm.online/',
    tip: '动漫在线免费观看，分类齐全。失效时搜"第一动漫"确认当前入口。',
    c1: '#487eb0', c2: '#8fb4d9', cats: ['video'], subs: ['anime'],
  },
  {
    key: 'dmmiku', name: '异世界动漫', desc: '番剧 · OVA · 剧场版', home: 'https://www.dmmiku.com/',
    tip: '动漫在线站，番剧、OVA、剧场版收录较全，补番方便。失效时搜"异世界动漫 最新"。',
    c1: '#8c7ae6', c2: '#c0b5f2', cats: ['video'], subs: ['anime'],
  },
  {
    key: 'girigiri', name: 'girigiri爱动漫', desc: '动漫在线 · 资源全', home: 'https://anime.girigirilove.com/',
    alts: ['https://girigirilove.top/'],
    tip: '动漫在线站，资源全，新番老番都好找，播放线路多。主站与备用站切换使用。',
    c1: '#e84393', c2: '#f58ea8', cats: ['video'], subs: ['anime'], proxy: true,
  },
  {
    key: 'mwcy', invalid: true, name: '喵物次元', desc: '二次元番剧', home: 'https://www.mwcy.net/',
    tip: '二次元番剧在线观看，界面轻快，新番跟更。失效时搜"喵物次元 最新"。',
    c1: '#ff9eb5', c2: '#ffccd6', cats: ['video'], subs: ['anime'],
  },
  {
    key: 'cycity', name: '次元城动画', desc: '番剧在线 · 高清', home: 'https://www.cycity.pro/',
    tip: '番剧在线观看，画质清晰、播放稳定。失效时搜"次元城 最新"。',
    c1: '#00a8ff', c2: '#66ccff', cats: ['video'], subs: ['anime'],
  },
  {
    key: 'ezdmw', name: 'E站弹幕网', desc: '弹幕番剧', home: 'https://www.ezdmw.site/',
    tip: '弹幕番剧站，番剧带弹幕播放，新番老番都有。失效时搜"E站弹幕网 最新"。',
    c1: '#5f27cd', c2: '#9b6fe8', cats: ['video'], subs: ['anime'],
  },
  {
    key: 'fengche', name: '风车动漫', desc: '老牌动漫 · 域名常变', home: 'https://fengchedmp.com/',
    tip: '老牌动漫站，番剧资源多、更新稳。域名常变，失效时搜"风车动漫 最新"找当前地址。',
    c1: '#44bd32', c2: '#8ed96b', cats: ['video'], subs: ['anime'],
  },
  {
    key: 'fantuan', name: '饭团动漫', desc: '番剧在线 · 免费追番', home: 'https://zzmplus.com/',
    alts: ['https://ppoft.com/'],
    tip: '番剧在线观看，免费追番，新番跟进及时。两个域名都可用，主站卡顿时换备用。',
    c1: '#d63031', c2: '#f1778a', cats: ['video'], subs: ['anime'],
  },
  {
    key: 'dmhy', name: '动漫花园', desc: 'BT资源 · 字幕组聚合', home: 'https://share.dmhy.org/',
    alts: ['https://dmhy.org'],
    tip: '新番字幕组发布聚合的 BT 资源站，下载动漫首选，资源与字幕组同步更新。下载的种子文件会被自动捕获。',
    c1: '#0984e3', c2: '#74b9ff', cats: ['video'], subs: ['anime'], proxy: true,
  },
  {
    key: 'mikan', name: '蜜柑计划', desc: 'BT资源 · RSS追番', home: 'https://mikanani.me',
    tip: '番剧字幕组聚合站，支持 RSS 订阅追番，合集划分清晰。下载的种子文件会被自动捕获。',
    c1: '#ff9f43', c2: '#ffd08a', cats: ['video'], subs: ['anime'], proxy: true,
  },
  {
    key: 'comicat', name: '漫猫动漫', desc: 'BT资源 · 动漫发布', home: 'https://www.comicat.org/',
    tip: '动漫资源 BT 发布站，番剧、剧场版等资源都有。下载的种子文件会被自动捕获。',
    c1: '#5352ed', c2: '#9c9bff', cats: ['video'], subs: ['anime'],
  },
  {
    key: 'kisssub', name: '爱恋动漫', desc: 'BT资源 · 字幕资源', home: 'https://kisssub.org/',
    tip: '动漫字幕 BT 资源站，字幕组作品收录细。下载的种子文件会被自动捕获。',
    c1: '#ee5253', c2: '#ff9c9d', cats: ['video'], subs: ['anime'],
  },

  // ============ 美术 · 灵感·作品社区（community） ============
  {
    key: 'zcool', name: '站酷', desc: '设计师作品社区', home: 'https://www.zcool.com.cn/',
    tip: '国内最大设计师社区，插画、平面、作品展示与设计赛事齐全。找工作参考、看行业趋势都合适。',
    c1: '#ffc107', c2: '#ffd966', cats: ['art'], subs: ['community'],
  },
  {
    key: 'huaban', name: '花瓣网', desc: '灵感采集 · 国内Pin', home: 'https://huaban.com/',
    tip: '国内 Pinterest 平替，灵感采集强，画板整理素材方便。做参考图收集的首选之一。',
    c1: '#ff4c7e', c2: '#ff8fae', cats: ['art'], subs: ['community'],
  },
  {
    key: 'poocg', invalid: true, name: '涂鸦王国', desc: '插画师聚集地', home: 'https://www.poocg.com/',
    tip: '插画师聚集地，原创插画作品量大质高。找插画风格参考的好去处。',
    c1: '#9b51e0', c2: '#c4a1f0', cats: ['art'], subs: ['community'],
  },
  {
    key: 'uicn', name: 'UI中国', desc: 'UI/UX 专业社区', home: 'https://www.ui.cn/',
    tip: 'UI/UX 专业社区，界面作品与设计文章为主。找交互参考和学习资料都合适。',
    c1: '#2d7dd2', c2: '#7ab5ec', cats: ['art'], subs: ['community'],
  },
  {
    key: 'uisdc', name: '优设网', desc: '设计教程 · 灵感', home: 'https://www.uisdc.com/',
    tip: '设计教程+灵感站点，设计工具教程与文章更新勤。设计师自学资源库。',
    c1: '#e8983e', c2: '#f5c48a', cats: ['art'], subs: ['community'],
  },
  {
    key: 'gtn9', name: '古田路9号', desc: '品牌创意社区', home: 'https://www.gtn9.com/',
    tip: '品牌创意社区，包装、logo、品牌全案作品多。看落地案例合适。',
    c1: '#6c5ce7', c2: '#a29bfe', cats: ['art'], subs: ['community'],
  },
  {
    key: 'behance', name: 'Behance', desc: '全球创意作品平台', home: 'https://www.behance.net/',
    tip: 'Adobe 旗下全球创意作品平台，平面/摄影/插画/UI 全品类。部分作品需系统代理加速。',
    c1: '#1769ff', c2: '#7aa4ff', cats: ['art'], subs: ['community'], proxy: true,
  },
  {
    key: 'artstation', name: 'ArtStation', desc: 'CG原画 · 3D社区', home: 'https://www.artstation.com/',
    tip: 'CG/原画/3D 高口碑社区，游戏影视概念设计、模型材质都有，行业标杆级作品集。需系统代理。',
    c1: '#13a3d8', c2: '#6fcbe9', cats: ['art'], subs: ['community'], proxy: true,
  },
  {
    key: 'dribbble', name: 'Dribbble', desc: '精美设计作品集', home: 'https://dribbble.com/',
    tip: '精美设计作品集平台，UI/品牌/动效走精品路线。找视觉参考合适。需系统代理。',
    c1: '#ea4c89', c2: '#f78fb6', cats: ['art'], subs: ['community'], proxy: true,
  },

  // ============ 美术 · 博物馆·画廊（museum） ============
  {
    key: 'digicol', name: '故宫数字文物库', desc: '故宫 · 高清文物', home: 'https://digicol.dpm.org.cn/',
    tip: '故宫官方数字文物库，免费高清文物图像，书画瓷器都能放大细看。官方出品，完全免费。',
    c1: '#c0392b', c2: '#e07a6a', cats: ['art'], subs: ['museum'],
  },
  {
    key: 'ltfc', name: '中华珍宝馆', desc: '国画书法 · 高清临摹', home: 'http://www.ltfc.net/',
    tip: '国画/书法高清图像库，名作可逐段放大细看。临摹与鉴赏利器，以古代书画为主。',
    c1: '#8b5a2b', c2: '#c49a6c', cats: ['art'], subs: ['museum'],
  },
  {
    key: 'artsandculture', name: 'Google 艺术与文化', desc: '全球博物馆 · 超清', home: 'https://artsandculture.google.com/',
    tip: 'Google 与全球博物馆合作的超清图像与线上展览，名画可放大到笔触级别。需系统代理。',
    c1: '#4285f4', c2: '#8ab0f8', cats: ['art'], subs: ['museum'], proxy: true,
  },
  {
    key: 'gallerix', name: 'Gallerix', desc: '世界名画档案馆', home: 'https://gallerix.asia/',
    tip: '世界名画在线档案馆，按画家与流派整理，高清图像适合临摹研究。失效时搜 Gallerix。',
    c1: '#2c3e50', c2: '#6d88a3', cats: ['art'], subs: ['museum'],
  },
  {
    key: 'artvee', name: 'Artvee', desc: '公共领域 · 油画高清', home: 'https://artvee.com/',
    tip: '公共领域艺术高清图库，油画为主，可自由取用。老画作检索方便。',
    c1: '#c96f2d', c2: '#e8a670', cats: ['art'], subs: ['museum'],
  },
  {
    key: 'wikiart', invalid: true, name: 'WikiArt', desc: '艺术史百科', home: 'https://www.wikiart.org/',
    tip: '艺术史百科，作品按流派/时期/画家组织，配合条目看脉络清晰。需系统代理。',
    c1: '#005f73', c2: '#5a9fb3', cats: ['art'], subs: ['museum'], proxy: true,
  },
  {
    key: 'artlib', name: 'Artlib 艺术鉴赏库', desc: '高清艺术 · 文献', home: 'https://www.artlib.cn/',
    tip: '高清艺术图像+文献数据库，中西艺术都有，鉴赏资料系统。部分资源需机构权限。',
    c1: '#8e7cc3', c2: '#c0b3e8', cats: ['art'], subs: ['museum'],
  },

  // ============ 美术 · 免费素材图库（stock） ============
  {
    key: 'pexels', name: 'Pexels', desc: '免费图库 · 高质量', home: 'https://www.pexels.com/',
    tip: '高质量免费图库+视频素材，授权宽松。需系统代理。',
    c1: '#05a081', c2: '#63d3ba', cats: ['art'], subs: ['stock'], proxy: true,
  },
  {
    key: 'pixabay', name: 'Pixabay', desc: '免费图库 · 可直连', home: 'https://pixabay.com/',
    tip: '免费图库，图片/插画/矢量/视频都有，国内可直连、速度稳定。',
    c1: '#0e7c9c', c2: '#66b8cd', cats: ['art'], subs: ['stock'],
  },
  {
    key: 'unsplash', name: 'Unsplash', desc: '高质量摄影图库', home: 'https://unsplash.com/',
    tip: '高质量摄影图库，摄影师作品水准高，适合做壁纸与设计素材。需系统代理。',
    c1: '#1f1f1f', c2: '#6b6b6b', cats: ['art'], subs: ['stock'], proxy: true,
  },
  {
    key: 'ddesign', name: '堆友', desc: '阿里设计 · 免费素材', home: 'https://d.design',
    tip: '阿里设计团队出品的免费素材站，3D 素材与设计资源质量高。失效时搜"堆友"。',
    c1: '#ff6a00', c2: '#ffa35c', cats: ['art'], subs: ['stock'],
  },

  // ============ 电子书 · 综合大型图书馆（lib） ============
  {
    key: 'libgen', name: 'LibGen', desc: '学术书 · 海盗图书馆', home: 'https://libgen.li/',
    alts: ['https://libgen.rs/', 'https://libgen.is/'],
    tip: '学术书/外文书海盗图书馆，教材论文专著都好找。域名常变，主站失效时换备用地址。',
    c1: '#0f6b5c', c2: '#5fb8a8', cats: ['book'], subs: ['libgen'], proxy: true,
  },
  {
    key: 'gutenberg', name: '古腾堡', desc: '公共领域 · 经典免费', home: 'https://www.gutenberg.org/',
    tip: '公共领域经典电子书，完全合法免费，英文文学为主。多格式下载可选。',
    c1: '#8e6e37', c2: '#c8a875', cats: ['book'], subs: ['lib'],
  },
  {
    key: 'archiveorg', name: 'Internet Archive', desc: '互联网档案馆', home: 'https://archive.org/',
    tip: '互联网档案馆：书籍/音频/影像存档，老资料抢救圣地。需系统代理；书库另有 Open Library 单独入口。',
    c1: '#2d2d34', c2: '#757583', cats: ['book'], subs: ['lib'], proxy: true,
  },
  {
    key: 'openlibrary', name: 'Open Library', desc: '开放图书馆 · 借阅', home: 'https://openlibrary.org/',
    tip: '开放图书馆：书目数据全，部分书可在线借阅。需系统代理。',
    c1: '#5a9e4b', c2: '#9ed48f', cats: ['book'], subs: ['lib'], proxy: true,
  },
  {
    key: 'standardebooks', name: 'Standard Ebooks', desc: '精排公版电子书', home: 'https://standardebooks.org/',
    tip: '精排公共领域电子书，排版校对用心，格式美观。英文经典为主。',
    c1: '#b85c38', c2: '#e3a184', cats: ['book'], subs: ['lib'],
  },
  {
    key: 'manybooks', name: 'ManyBooks', desc: '免费电子书聚合', home: 'https://manybooks.net/',
    tip: '免费电子书聚合站，分类与书单浏览方便。英文书为主。',
    c1: '#5c6bc0', c2: '#98a4e0', cats: ['book'], subs: ['lib'],
  },

  // ============ 电子书 · 轻小说（ltnovel） ============
  {
    key: 'lightnovel', name: '轻之国度', desc: '日轻门户 · 论坛', home: 'https://www.lightnovel.us/',
    tip: '老牌日轻门户+论坛（2026-09-18 探测证书链异常，浏览器可能警告，站点本身可达），轻小说资讯与讨论交流集中地。失效时搜"轻之国度"。',
    c1: '#5b8def', c2: '#9bbcf2', cats: ['book'], subs: ['ltnovel'],
  },
  {
    key: 'sfacg', name: 'SF轻小说', desc: '菠萝包 · 轻小说', home: 'https://book.sfacg.com/',
    tip: '菠萝包 SF：原创+翻译轻小说平台，独家作品多，人气作品能追更。部分章节需 VIP。',
    c1: '#ff7d25', c2: '#ffae7d', cats: ['book'], subs: ['ltnovel'],
  },
  {
    key: 'wenku8', invalid: true, name: '轻小说文库', desc: '老牌轻小说文库', home: 'https://www.wenku8.net/',
    tip: '老牌轻小说文库，日轻收录全、条目整理规范。失效时搜"轻小说文库"。',
    c1: '#4fa3d1', c2: '#92c6e5', cats: ['book'], subs: ['ltnovel'],
  },
  {
    key: 'linovelib', name: '哔哩轻小说', desc: '轻小说 · 在线阅读', home: 'https://www.linovelib.com/',
    tip: '轻小说在线阅读站，分类与排行方便找书，更新跟进热门。与哔哩哔哩官方无关，认准域名。',
    c1: '#20c5e0', c2: '#7cdcf0', cats: ['book'], subs: ['ltnovel'],
  },
  {
    key: 'shencou', invalid: true, name: '神凑轻小说', desc: '轻小说在线 · 收录全', home: 'https://www.shencou.com/',
    tip: '轻小说在线阅读，收录偏全，界面朴素。失效时搜"神凑轻小说"（2026-09-18 探测不可达，失效时搜"神凑轻小说"）。',
    c1: '#7e57c2', c2: '#b39ddb', cats: ['book'], subs: ['ltnovel'],
  },
  {
    key: 'mobinovels', invalid: true, name: '魔笔小说', desc: '轻小说在线 · 热门跟更', home: 'https://www.mobinovels.com/',
    tip: '轻小说在线阅读站，热门轻小说都有收录。失效时搜"魔笔小说"（2026-09-18 探测不可达，失效时搜"魔笔小说"）。',
    c1: '#26a69a', c2: '#7fd6cc', cats: ['book'], subs: ['ltnovel'],
  },
  {
    key: 'acgndog', name: '次元狗', desc: 'ACG小说资源', home: 'https://www.acgndog.com/',
    tip: 'ACG 小说资源站，轻小说与二次元向网文都有。失效时搜"次元狗"。',
    c1: '#ef6c00', c2: '#f7a45c', cats: ['book'], subs: ['ltnovel'], proxy: true,
  },
  {
    key: 'epublove', invalid: true, name: '无限回廊', desc: '轻小说 · EPUB', home: 'https://epub.love/',
    tip: '"图书馆的无限回廊"：轻小说 EPUB 资源。失效时搜"无限回廊"。',
    c1: '#455a9b', c2: '#8c9cc9', cats: ['book'], subs: ['ltnovel'],
  },
  {
    key: 'syosetu', name: '成为小说家吧', desc: '日文网文 · 源头', home: 'https://syosetu.com/',
    tip: '日文原版网文/轻小说源头站，大量作品从这里被改编。日文界面，需系统代理。',
    c1: '#d94f4f', c2: '#ef8b8b', cats: ['book'], subs: ['ltnovel'], proxy: true,
  },
  {
    key: 'novgo', name: 'NOVGO', desc: '英文轻小说 · 网文', home: 'https://novgo.net/',
    tip: '英文轻小说/网文聚合。失效时搜 NOVGO。',
    c1: '#3f7c5f', c2: '#82b89c', cats: ['book'], subs: ['ltnovel'],
  },
  {
    key: 'jnovels', name: 'jnovels', desc: '英文轻小说 · 下载', home: 'https://jnovels.com/',
    tip: '英文轻小说电子书下载，更新跟进出版节奏。需系统代理。',
    c1: '#6a5acd', c2: '#a493ee', cats: ['book'], subs: ['ltnovel'], proxy: true,
  },

  // ============ 电子书 · 铅笔小说（pencil） ============
  {
    key: 'qianbi', name: '铅笔小说', desc: '网文小说 · 在线阅读', home: 'https://www.23qb.com/',
    alts: ['https://www.23qb.net/'],
    tip: '网文/小说在线阅读，书库大、分类细，追更方便。主域名失效时换 .net 备用。',
    c1: '#2f9e6e', c2: '#7ed6ac', cats: ['book'], subs: ['pencil'],
  },

  // ============ 电子书 · 白嫖站（free） ============
  {
    key: 'zxcs', name: '知轩藏书', desc: '网文精校书库', home: 'http://www.zxcs.info/',
    tip: '网文精校书库，精校版本收集齐全。书荒找书实用，失效时搜"知轩藏书"。',
    c1: '#a0522d', c2: '#d19066', cats: ['book'], subs: ['free'],
  },
  {
    key: 'wattpad', name: 'Wattpad', desc: '原创同人 · 故事社区', home: 'https://www.wattpad.com/',
    tip: '全球原创同人故事社区，题材杂、更新活跃，适合淘小众故事。需系统代理。',
    c1: '#ff5000', c2: '#ff8a5c', cats: ['book'], subs: ['free'], proxy: true,
  },
  {
    key: 'wuxiaworld', name: 'Wuxiaworld', desc: '武侠玄幻 · 英译', home: 'https://www.wuxiaworld.com/',
    tip: '中文武侠玄幻英译站，对外网文传播主力。需系统代理。',
    c1: '#c9973d', c2: '#e5c083', cats: ['book'], subs: ['free'], proxy: true,
  },
  {
    key: 'royalroad', name: 'Royal Road', desc: '英文网文 · 连载', home: 'https://www.royalroad.com/',
    tip: '英文网文连载平台，更新活跃。需系统代理。',
    c1: '#4a6fd0', c2: '#8fa5e5', cats: ['book'], subs: ['free'], proxy: true,
  },
  {
    key: 'qidian', name: '起点中文网', desc: '官方网文 · 有免费区', home: 'https://www.qidian.com/',
    tip: '官方网文平台，体量最大，有免费区与限免活动。热门书追更需订阅。',
    c1: '#d0281e', c2: '#e97e77', cats: ['book'], subs: ['free'],
  },
  {
    key: 'zongheng', name: '纵横中文网', desc: '官方网文平台', home: 'https://www.zongheng.com/',
    tip: '官方网文平台，历史军事等品类有特色。失效时搜"纵横中文网"。',
    c1: '#a13d2d', c2: '#d98d80', cats: ['book'], subs: ['free'],
  },

  // ============ 磁力站（无 subs） ============
  {
    key: 'ciliduo', name: '磁力多', desc: '磁力搜索', home: 'https://ciliduo.org/',
    tip: '磁力搜索引擎，关键词即搜即得。搜索到的磁力/种子链接可复制到下载器使用。',
    c1: '#2f80ed', c2: '#7cabf0', cats: ['magnet'],
  },
  {
    key: 'wuqian', invalid: true, name: '吴签磁力', desc: '磁力搜索 · 干净', home: 'https://wuqianso.top/',
    tip: '界面干净好用的磁力搜索。搜索到的磁力/种子链接可复制到下载器使用。',
    c1: '#27ae60', c2: '#7ed9a2', cats: ['magnet'], proxy: true,
  },
  {
    key: 'cilicao', invalid: true, name: '磁力草', desc: '磁力搜索', home: 'https://www.cilicao.com/',
    tip: '磁力搜索引擎。搜索到的磁力/种子链接可复制到下载器使用；失效时搜"磁力草"（2026-09-18 探测不可达，失效时搜"磁力草 最新"）。',
    c1: '#8e44ad', c2: '#c08ce8', cats: ['magnet'],
  },
  {
    key: 'magnetpics', name: '磁力印象', desc: '磁力搜索', home: 'https://beta.magnet.pics/',
    tip: '磁力搜索（测试版站点）。搜索到的磁力/种子链接可复制到下载器使用。',
    c1: '#0f9b8e', c2: '#6fd6ca', cats: ['magnet'],
  },
  {
    key: 'yuhuage', invalid: true, name: '雨花阁', desc: '磁力搜索', home: 'https://www.yuhuage.win/',
    tip: '磁力搜索引擎。搜索到的磁力/种子链接可复制到下载器使用；失效时搜"雨花阁 最新"。',
    c1: '#5f6d7e', c2: '#9aacbe', cats: ['magnet'], proxy: true,
  },
  {
    key: 'lemonso', name: '磁力柠檬', desc: '磁力搜索', home: 'https://lemonso.net/',
    tip: '磁力搜索站。搜索到的磁力/种子链接可复制到下载器使用；失效时搜"磁力柠檬"。',
    c1: '#9acd32', c2: '#c5e37a', cats: ['magnet'],
  },
  {
    key: 'skrbt', name: 'SkrBT', desc: '磁力搜索 · 镜像常变', home: 'https://skrbtcil.buzz/',
    tip: '磁力搜索，镜像常变，失效时搜"SkrBT 最新"找当前地址。搜索到的磁力/种子链接可复制到下载器使用。',
    c1: '#e17055', c2: '#f5a582', cats: ['magnet'],
  },
  {
    key: 'cilimao', name: '磁力猫', desc: '磁力搜索 · 多镜像', home: 'https://www.cilimao.me',
    alts: ['https://clm112.xyz', 'http://clm.la'],
    tip: '多镜像磁力搜索，资源量大。搜索到的磁力/种子链接可复制到下载器使用；主站失效时换镜像。',
    c1: '#f06292', c2: '#f5a5bd', cats: ['magnet'], proxy: true,
  },
  {
    key: 'cilitt', name: '磁力天堂', desc: '磁力搜索', home: 'https://cilitt.cc',
    alts: ['https://www.jzbty.top/'],
    tip: '磁力搜索引擎。搜索到的磁力/种子链接可复制到下载器使用；失效时换备用域名。',
    c1: '#5c6bc0', c2: '#98a4e0', cats: ['magnet'], proxy: true,
  },
  {
    key: 'btdig', name: 'BTDigg', desc: 'DHT磁力搜索', home: 'https://btdig.com/',
    tip: '老牌 DHT 磁力搜索，索引量大。需系统代理；搜索到的磁力/种子链接可复制到下载器使用。',
    c1: '#1e88e5', c2: '#79b6f2', cats: ['magnet'], proxy: true,
  },
  {
    key: 'zhongzidi', name: '种子搜', desc: '种子/磁力搜索', home: 'https://zhongzidi9.com/',
    tip: '种子/磁力搜索引擎。搜索到的磁力/种子链接可复制到下载器使用。',
    c1: '#43a047', c2: '#8bd08d', cats: ['magnet'],
  },
  {
    key: 'clg', name: '磁力狗', desc: '磁力搜索', home: 'http://clg88.net/',
    alts: ['http://clg.cm'],
    tip: '磁力搜索引擎。搜索到的磁力/种子链接可复制到下载器使用；主站失效时换备用域名。',
    c1: '#6d4c41', c2: '#a1887f', cats: ['magnet'], proxy: true,
  },
  {
    key: 'laowang', name: '老王磁力', desc: '磁力搜索 · 发布页', home: 'https://www.ilaowang.xyz',
    publish: 'https://ilaowang.xyz',
    tip: '磁力搜索引擎。搜索到的磁力/种子链接可复制到下载器使用；域名失效时去发布页找最新地址。',
    c1: '#4e342e', c2: '#8d6e63', cats: ['magnet'],
  },
  {
    key: 'bt1207', name: 'BT1207', desc: '磁力搜索', home: 'https://ibt120702.xyz/',
    alts: ['https://1207dizhi.net'],
    tip: '磁力搜索引擎。搜索到的磁力/种子链接可复制到下载器使用；失效时换备用地址。',
    c1: '#00695c', c2: '#4db6ac', cats: ['magnet'],
  },
  {
    key: 'anybt', name: 'AnyBT', desc: '磁力搜索', home: 'https://anybt.eth.link',
    tip: '磁力搜索引擎。搜索到的磁力/种子链接可复制到下载器使用；失效时搜 AnyBT。',
    c1: '#263238', c2: '#607d8b', cats: ['magnet'], proxy: true,
  },
  {
    key: 'cilibaike', invalid: true, name: '磁力百科', desc: '磁力搜索', home: 'https://www.cilibaike.com/',
    tip: '磁力搜索（原 磁力百科.com）。搜索到的磁力/种子链接可复制到下载器使用（2026-09-18 探测不可达，失效时搜"磁力百科"）。',
    c1: '#ad1457', c2: '#df6f9a', cats: ['magnet'],
  },
  {
    key: 'bt91', name: '91BT', desc: '磁力搜索', home: 'https://91btbt.com',
    tip: '磁力搜索引擎。搜索到的磁力/种子链接可复制到下载器使用；失效时搜 91BT。',
    c1: '#ef6c00', c2: '#f79c4a', cats: ['magnet'], proxy: true,
  },
  {
    key: 'cilidog', name: '磁力海', desc: '磁力搜索', home: 'https://cilidog.cc/',
    tip: '磁力搜索引擎。搜索到的磁力/种子链接可复制到下载器使用。',
    c1: '#c62828', c2: '#e57373', cats: ['magnet'],
  },
  {
    key: 'wxcl', invalid: true, name: '无限磁力', desc: '磁力搜索', home: 'https://www.wxcl.live/',
    tip: '磁力搜索引擎。搜索到的磁力/种子链接可复制到下载器使用（2026-09-18 探测不可达，失效时搜"无限磁力 最新"）。',
    c1: '#5e35b1', c2: '#9176d1', cats: ['magnet'],
  },
  {
    key: 'btsow', name: 'BTSOW', desc: '磁力搜索', home: 'https://btsow.pics/',
    tip: '磁力搜索引擎。搜索到的磁力/种子链接可复制到下载器使用；失效时搜 BTSOW。',
    c1: '#00838f', c2: '#4dbac2', cats: ['magnet'], proxy: true,
  },

  // ============ AI 制作（无 subs） ============
  {
    key: 'tusiart', name: '吐司AI', desc: '在线跑图 · 模型分享', home: 'https://tusiart.com',
    alts: ['https://tusi.cn'],
    tip: '在线运行 AI 模型 + 模型分享社区，免装环境直接出图，模型资源多。主站与备用域名切换使用。',
    c1: '#ff5722', c2: '#ff8a65', cats: ['ai'],
  },
  {
    key: 'xingliu', name: '星流AI', desc: '设计Agent · Liblib系', home: 'https://www.xingliu.art',
    tip: 'LiblibAI 旗下设计 Agent 平台，面向设计场景的 AI 生成流程。适合设计向出图。',
    c1: '#3d5afe', c2: '#84a0ff', cats: ['ai'],
  },
  {
    key: 'seaart', name: '海艺AI', desc: '在线生图 · 模型库', home: 'https://www.seaart.ai',
    tip: '在线生图 + 模型库一体，风格模板多，出图门槛低。失效时搜"海艺AI"。',
    c1: '#00bfa5', c2: '#5cdcd0', cats: ['ai'], proxy: true,
  },
  {
    key: 'civarchive', name: 'CivArchive', desc: 'Civitai模型归档', home: 'https://civarchive.com',
    tip: 'Civitai 模型归档/救援索引，找下架或难访问的模型用它。需系统代理。',
    c1: '#607d8b', c2: '#9facb8', cats: ['ai'], proxy: true,
  },
  {
    key: 'comfyworkflows', invalid: true, name: 'ComfyWorkflows', desc: 'ComfyUI工作流分享', home: 'https://comfyworkflows.com',
    tip: 'ComfyUI 工作流分享平台，节点图可直接导入使用。需系统代理。',
    c1: '#22c1ee', c2: '#7ad9f3', cats: ['ai'], proxy: true,
  },
]

// ---- 排序分层：官方主流站永远在前，白嫖/资源站靠后，GitHub 动态站垫底 ----
// rank: 1=官方主流（显式集合，免逐条标注） 2=白嫖/资源站（默认） 3=动态下发（extra）
const RANK1_OFFICIAL = new Set([
  'bilibili', 'douyin', 'kuaishou', 'xhs', 'weibo', 'youtube',
  'zhihu', 'music163', 'github', 'wiki',
  'iqiyi', 'tencent', 'youku', 'mgtv', 'acfun', 'qidian', 'zongheng',
])

// ---- 随包兜底校验表（离线/上游全挂时用；启动即合并，联网后被同步结果覆盖） ----
// 内容 = 发布仓 surface_sites.json 的 v2 快照（63 URL 开证书校验探测）
export const BUNDLED_REGISTRY = {
  version: 4,
  updated: '2026-09-18',
  note: '随包兜底：离线或上游不可达时使用，联网后自动被同步结果覆盖',
  sites: {
    agefans: { status: 'dead', url: '', note: '主域名失效：官方发布页 github.com/agefanscom/website 找最新地址（联网后自动同步）' },
    annas: { status: 'dead', url: '', note: "annas-archive.org 不可达，搜索 Anna's Archive 最新地址" },
    hifini: { status: 'dead', url: '', note: 'www.hifini.com 不可达，搜索 HiFiNi 音乐磁场 最新地址' },
    tonzhon: { status: 'dead', url: '', note: 'whamon 镜像失效，搜索 铜钟音乐 最新地址' },
    zlib: { status: 'dead', url: '', note: 'z-library.sk 不可达，Z-Library 域名常变，搜索最新地址' },
    pianku: { status: 'ok', url: 'https://piankuwan.com', note: '' },
    ntdm: { status: 'dead', url: '', note: '2026-09-18 探测主/备域名均不可达，搜 NT动漫 最新' },
    shencou: { status: 'dead', url: '', note: '2026-09-18 探测不可达，搜 神凑轻小说' },
    mobinovels: { status: 'dead', url: '', note: '2026-09-18 探测不可达，搜 魔笔小说' },
    cilibaike: { status: 'dead', url: '', note: '2026-09-18 探测不可达，搜 磁力百科' },
    cilicao: { status: 'dead', url: '', note: '2026-09-18 探测不可达，搜 磁力草 最新' },
    wxcl: { status: 'dead', url: '', note: '2026-09-18 探测不可达，搜 无限磁力 最新' },
  },
  extra: [],
}

// ---- GitHub 校验合并 ----
// remote 形如：
// {
//   "version": 1, "updated": "2026-09-18",
//   "sites": { "<key>": {"status":"ok|dead|todo", "url":"https://...", "note":"...", "hidden":true} },
//   "extra": [ {"key","name","desc","tip","cats","home","proxy"} ]   // 动态新增（可选）
// }
// 规则：ok→可下发新地址（url 非空且与本地不同则覆盖）；dead→磁贴置灰"已失效"；
//       hidden→整站隐藏；extra→动态补新磁贴（分类图标兜底）；
//       slot 空位站（slot:true 且 home 为空）默认不显示，任一层下发地址即点亮。
export function mergeRegistry(baseline, remote) {
  if (!remote) remote = BUNDLED_REGISTRY
  const byKey = new Map(baseline.map(p => [p.key, { ...p }]))
  let ok = 0
  let dead = 0
  const rs = remote.sites || {}
  for (const [key, info] of Object.entries(rs)) {
    const p = byKey.get(key)
    if (!p) continue
    if (info && info.hidden) {
      byKey.delete(key)
      continue
    }
    const status = (info && info.status) || ''
    if (status === 'dead') {
      p.invalid = true
      p.invalidNote = info.note || ''
      dead += 1
    } else if (status === 'ok') {
      p.invalid = false
      if (info.url && info.url !== p.home) p.home = info.url
      if (info.note) p.invalidNote = ''
      ok += 1
    }
  }
  const extras = []
  for (const e of (remote.extra || [])) {
    if (!e || !e.key || !e.home || byKey.has(e.key)) continue
    byKey.set(e.key, {
      key: e.key, name: e.name || e.key, desc: e.desc || '',
      tip: e.tip || 'GitHub 校验表动态下发的站点。',
      cats: e.cats && e.cats.length ? e.cats : ['res'],
      home: e.home, proxy: !!e.proxy,
      rank: 3, extra: true,
    })
    extras.push(e.key)
  }
  // 空位磁贴：始终没拿到地址的（slot:true 且 home 仍为空）不渲染
  for (const [key, p] of [...byKey]) {
    if (p.slot && !p.home) byKey.delete(key)
  }
  // 排序：官方主流(rank1) → 白嫖/资源站(rank2) → 动态下发(rank3)；同级保持 baseline 顺序
  const rankOf = p => p.rank || (RANK1_OFFICIAL.has(p.key) ? 1 : 2)
  const idxOf = p => {
    const i = baseline.findIndex(b => b.key === p.key)
    return i < 0 ? 9999 : i
  }
  const sites = [...byKey.values()].sort((a, b) => {
    const ra = rankOf(a)
    const rb = rankOf(b)
    if (ra !== rb) return ra - rb
    return idxOf(a) - idxOf(b)
  })
  return { sites, stats: { ok, dead, extra: extras.length }, updated: remote.updated || '' }
}

// 磁贴展示辅助：图标（站点专属 → 分类兜底）、颜色（品牌 → 分类兜底）
// ---- 磁贴配色和谐化（chroma.js / LCH 色彩空间，2026-09-19）----
// 168 站的 c1/c2 是逐站手挑的，明度/饱和度各自为政（纯红 #ff0000 与暗绿 #1d9f6e 同墙）
// → 磁贴墙看起来杂乱。用 chroma 做 LCH 归一：保持各站品牌「色相」，把「亮度」统一进
// 一个带（暗的提亮、刺眼的压暗）、「饱和度」只压过高的（不强行给灰调品牌加色），
// 渐变亮端 c2 统一由归一后的 c1 派生（同色相向上亮化）——整面墙的渐变方向一致、观感和谐。
const TILE_L_MIN = 46
const TILE_L_MAX = 60
const TILE_C_MAX = 66
const _tileHarmonyCache = new Map()

export function harmonizeTile(c1, c2) {
  const key = c1 + '|' + (c2 || '')
  const hit = _tileHarmonyCache.get(key)
  if (hit) return hit
  let out
  try {
    const [l, cc, h] = chroma(c1).lch()
    const L = Math.max(TILE_L_MIN, Math.min(TILE_L_MAX, l))
    const C = Math.min(TILE_C_MAX, cc)
    const base = chroma.lch(L, C, h)
    // 亮端：同色相向白方向亮化（lab 插值比直接 lighten 柔和），过亮会洗白 → 限制幅度
    const light = chroma.mix(base, chroma.lch(Math.min(L + 22, 84), C * 0.8, h), 1, 'lab')
    out = { c1: base.hex(), c2: light.hex() }
  } catch (e) {
    out = { c1, c2: c2 || c1 }   // 非法色值兜底原样返回
  }
  _tileHarmonyCache.set(key, out)
  return out
}

export function tileVisual(p) {
  const mainCat = (p.cats && p.cats[0]) || 'res'
  const fb = CAT_COLORS[mainCat] || CAT_COLORS.res
  return harmonizeTile(p.c1 || fb[0], p.c2 || fb[1] || fb[0])
}

// ---- 「常用」模块：点击统计 + 预设 Top15 + 自动累计（细分板块：收录点击次数最多的 15 个网站） ----
// 预设 = 主流站起步分（15..1）；真实点击 ×10 权重，点几次即可顶掉预设末位；localStorage 持久化。
export const FREQ_PRESET = [
  'bilibili', 'douyin', 'youtube', 'xhs', 'kuaishou', 'weibo', 'zhihu',
  'music163', 'github', 'wiki', 'iqiyi', 'juzong', 'jianyun', 'pianku', 'agefans',
]
const _CLICK_KEY = 'mh_site_clicks_v1'
export function loadSiteClicks() {
  try { return JSON.parse(localStorage.getItem(_CLICK_KEY)) || {} } catch (e) { return {} }
}
export function trackSiteClick(key) {
  const c = loadSiteClicks()
  c[key] = (c[key] || 0) + 1
  try { localStorage.setItem(_CLICK_KEY, JSON.stringify(c)) } catch (e) { /* 隐私模式 */ }
  return c
}
// 常用列表：只排有效、有地址的站；预设分 + 点击分排序取前 15
export function freqSites(platforms) {
  const clicks = loadSiteClicks()
  const preset = new Map(FREQ_PRESET.map((k, i) => [k, FREQ_PRESET.length - i]))
  const idx = new Map(platforms.map((p, i) => [p.key, i]))
  return platforms
    .filter(p => !p.invalid && p.home && !p.slot)
    .map(p => ({ p, score: (clicks[p.key] || 0) * 10 + (preset.get(p.key) || 0) }))
    .filter(s => s.score > 0)
    .sort((a, b) => b.score - a.score
      || (preset.get(b.p.key) || 0) - (preset.get(a.p.key) || 0)
      || (idx.get(a.p.key) || 0) - (idx.get(b.p.key) || 0))
    .slice(0, 15)
    .map(s => s.p)
}

// ---- 分类 chips 动态化（细分板块：空分类自动隐藏，如科学/资讯暂无站点） ----
export function visibleCategories(platforms) {
  const used = new Set()
  for (const p of platforms) for (const c of (p.cats || [])) used.add(c)
  return CATEGORIES.filter(c => c.key === 'all' || c.key === 'freq' || used.has(c.key))
}
// 二级 chips：同理只显示该分类下有站点的二级（如欧美剧未收录专项站时自动隐藏）
export function visibleSubs(cat, platforms) {
  const subs = SUBCATEGORIES[cat]
  if (!subs) return []
  const used = new Set()
  for (const p of platforms) {
    if ((p.cats || []).includes(cat)) for (const s of (p.subs || [])) used.add(s)
  }
  return subs.filter(s => used.has(s.key))
}
