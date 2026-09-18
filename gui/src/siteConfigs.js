// 通用站点规则配置（模块化架构 m4，见 任务中心/任务清单/模块化架构-通用站点模块-任务清单.md）
//
// 每个新站点在此加一个配置对象 = 前端零新代码（GenericSiteView 配置驱动渲染）。
// 后端配套见 bridge/site_template.py（复制为 site_<key>.py 填规则）。
//
// 配置形状（"通用网站规则"）：
// {
//   key: 'example',            // 站点键 = settings.site = 后端 SITE_KEY
//   name: '示例站',             // 显示名
//   toolbar: {
//     buttons: [{ label, title, cmd, args }]        // cmd → gs-command {cmd, ...args}
//     selects: [{ label, key, options: [{label, value}], cmd }]  // 变更即发 cmd（value 作 payload[key]）
//   },
//   list: { title: '示例站', empty: '暂无内容', loadMore: true },
//   card: { showAuthor: true, showPosted: true, badges: item => [] },  // badges 返回 [{text, type}]
//   detail: {
//     backCmd: 'back',                       // ← 返回按钮发的命令
//     downloadCmd: 'download-files',         // 下载选中按钮的命令（payload: {files})
//     showTags: true, tagCmd: 'search-tag',  // tag 点击命令
//   },
//   empty: '输入关键词搜索…',
// }
//
// 事件流：GenericSiteView emit('gs-command', {cmd, ...payload})
//   → RightPanel 转发 → App.handleGsCommand → sendCommand({cmd: `${site}_${cmd}`, ...payload})
// 状态流：后端 emit gs_state {site, view, items, detail, files, loading, error, page, hasMore, total}
//   → App.gsStates[site] → RightPanel(:gs-state) → GenericSiteView

export const GS_SITE_CONFIGS = {
  // FC2 成人视频（2026-09-10 接入；后端 bridge/site_fc2.py）
  fc2: {
    key: 'fc2',
    name: 'FC2',
    toolbar: {
      buttons: [
        { label: '🏠 免费视频', title: 'FC2 免费区列表（新着）', cmd: 'home', args: { page: 1 } },
      ],
      // 分类下拉（站方 20 个中文分类，2026-09-10 实测抓取；选中即发 list 命令）
      selects: [
        {
          label: '分类', key: 'category_id', cmd: 'list',
          options: [
            { label: '全部分类', value: '' },
            { label: '巨乳・美乳', value: '18' }, { label: '新人・清纯', value: '30' },
            { label: '明星', value: '36' }, { label: '人妻・熟女', value: '22' },
            { label: 'OL', value: '17' }, { label: 'SM・凌辱', value: '29' },
            { label: '恋物癖・变态', value: '27' }, { label: '自拍', value: '19' },
            { label: '自慰', value: '26' }, { label: '野外・露出', value: '25' },
            { label: 'Cosplay・制服', value: '24' }, { label: '美臀・肛门', value: '23' },
            { label: '乱交・3P', value: '31' }, { label: '口交', value: '20' },
            { label: '颜射・体外射精', value: '21' }, { label: '体内射精', value: '16' },
            { label: '色情动漫・游戏', value: '40' }, { label: '色情视频', value: '32' },
            { label: '性感的姊姊', value: '49' },
          ],
        },
      ],
    },
    list: { title: 'FC2', empty: '暂无内容', loadMore: true },
    card: { showAuthor: true, showPosted: true },
    detail: { backCmd: 'home', downloadCmd: 'download-files', showTags: true, tagCmd: 'search-tag' },
    search: { cmd: 'search', placeholder: '搜索 FC2 视频…' },
    // 批量勾选（m7 通用模块；不配置则该站无批量按钮）
    batch: { idKey: 'video_id', downloadCmd: 'batch_download' },
    empty: '点上方「免费视频」浏览，或在搜索框输入关键词（勾选卡片后可批量下载）',
  },
  // Fapello（综合资源站点家族；2026-09-13 接入，AJAX 分页 + content 直链）
  fapello: {
    key: 'fapello',
    name: 'Fapello',
    toolbar: {
      buttons: [
        { label: '🏠 最新模型', title: '最新模型列表（可搜索）', cmd: 'home', args: { page: 1 } },
      ],
      selects: [],
    },
    list: { title: 'Fapello', empty: '暂无内容', loadMore: true },
    card: { showAuthor: true, showPosted: false },
    detail: { backCmd: 'home', downloadCmd: 'fapello_download_files', showTags: false },
    batch: { idKey: 'video_id', downloadCmd: 'batch_download' },
    search: { cmd: 'search', placeholder: '搜索模型名称…' },
    empty: '点上方「最新模型」浏览，或在搜索框输入模型名称',
  },
  // CoomerFans（综合资源站点家族；PoW 过盾后可用）
  coomerfans: {
    key: 'coomerfans',
    name: 'CoomerFans',
    toolbar: {
      buttons: [
        { label: '🏠 最新帖子', title: '最新帖子列表（可搜索）', cmd: 'home', args: { page: 1 } },
      ],
      selects: [],
    },
    list: { title: 'CoomerFans', empty: '暂无内容', loadMore: true },
    card: { showAuthor: false, showPosted: false },
    detail: { backCmd: 'home', downloadCmd: 'coomerfans_download_files', showTags: false },
    batch: { idKey: 'video_id', downloadCmd: 'batch_download' },
    search: { cmd: 'search', placeholder: '搜索帖子关键词…' },
    empty: '点上方「最新帖子」浏览，或在搜索框输入关键词',
  },
  // Leakedzone（综合资源站点家族；Cloudflare 盾——先在内置浏览器登录过盾）
  leakedzone: {
    key: 'leakedzone',
    name: 'Leakedzone',
    toolbar: {
      buttons: [
        { label: '🏠 最新内容', title: '最新内容列表（可搜索）', cmd: 'home', args: { page: 1 } },
      ],
      selects: [],
    },
    list: { title: 'Leakedzone', empty: '暂无内容', loadMore: true },
    card: { showAuthor: false, showPosted: false },
    detail: { backCmd: 'home', downloadCmd: 'leakedzone_download_files', showTags: false },
    batch: { idKey: 'video_id', downloadCmd: 'batch_download' },
    search: { cmd: 'search', placeholder: '搜索关键词…' },
    empty: '点上方「最新内容」浏览，或在搜索框输入关键词（需先在左侧登录过 Cloudflare 盾）',
  },
  // Coomer（综合资源站点家族，kemono API；2026-09-13 接入，逻辑对齐 PA 站）
  coomerst: {
    key: 'coomerst',
    name: 'Coomer',
    toolbar: {
      buttons: [
        { label: '🏠 热门创作者', title: '创作者列表（可搜索）', cmd: 'home', args: { page: 1 } },
      ],
      selects: [],
    },
    list: { title: 'Coomer', empty: '暂无内容', loadMore: true },
    card: { showAuthor: true, showPosted: false },
    detail: { backCmd: 'home', downloadCmd: 'coomerst_download_files', showTags: false },
    batch: { idKey: 'video_id', downloadCmd: 'batch_download' },
    search: { cmd: 'search', placeholder: '搜索创作者名称…' },
    empty: '点上方「热门创作者」浏览，或在搜索框输入创作者名称',
  },
  // 示例配置（bridge/site_template.py 的配套演示；未在站点芯片出现，仅作契约样例）
  example: {
    key: 'example',
    name: '示例站',
    toolbar: {
      buttons: [
        { label: '🏠 主页', title: '示例站主页内容流', cmd: 'home', args: { page: 1 } },
      ],
      selects: [],
    },
    list: { title: '示例站', empty: '暂无内容', loadMore: true },
    card: { showAuthor: true, showPosted: true },
    detail: { backCmd: 'back', downloadCmd: 'download-files', showTags: true, tagCmd: 'search-tag' },
    // 批量勾选（m7 通用模块；不配置则该站无批量按钮）
    batch: { idKey: 'video_id', downloadCmd: 'batch_download' },
    empty: '输入关键词搜索，或点上方"主页"浏览内容流',
  },
}

export function gsConfigFor(site) {
  return GS_SITE_CONFIGS[site] || null
}
