# 验证总结 · 三站问题 · 全局账号系统 · ASMR 修复（2026-08-28）

> 本文件为本轮任务的任务前总结 + 边修复边完善的记录。
> 修复完成后需：重建前端 dist、重打包后端（若改 gui_bridge.py）、同步 bugfile/、更新 事件任务对话压缩上下文.md。

---

## 一、之前几轮修复的验证结果（对照 md 与实际代码）

### bug 修复轮（commit f7410e7，见 事件任务对话压缩上下文.md）——全部属实 ✅

| 声明 | 验证结果 |
|---|---|
| EX 点击进入本子（handleExOpenGallery 参数改名） | ✅ App.vue 已用 `galleryUrl` 参数，无遮蔽 bug |
| iw/ai 站切换强校验（防旧请求混入） | ✅ `iwara_home` / `iwara_follow_list` / `iwara_friend_list` / `iwara_video_detail` 4 处均有 `event.site !== iwSite.value` 丢弃逻辑 |
| ASMR "打开网站"按钮 URL | ✅ LeftPanel SITE_URLS 已有 `asmr: 'https://asmr-100.com/popular'` |
| 启动登录静默化（silent: true） | ✅ ready 事件中 ex/twitter/xh/ph/xv 均带 silent |
| EX 批量下载（母文件夹弹窗） | ✅ exBatchFolderVisible 弹窗 + options.batch_parent_folder 已接通 |

### P2 翻译重制 / P3 设置功能（快捷键、不息屏、托盘、拟态）——代码均存在 ✅（dist 已重建过）

### 结论：此前记录与代码一致，无虚假声明；**唯一未兑现的承诺就是 ASMR 站点的前端接线（见下）**

---

## 二、ASMR-100 三个问题的根因（本轮修复目标）

后端 `gui_bridge.py` 的 ASMR 模块（登录/热门/媒体库/收藏/索引/详情/批量下载/启动恢复/账号档案切换）**全部完整**；App.vue 中 `handleAsmr*` 函数族与事件处理（asmr_login_result / asmr_list 等）**也全部存在**；RightPanel.vue 的 ASMR 视图 UI（props 17 个 + emits 14 个）**全部定义**。

**根因：App.vue 的 `<RightPanel>` 标签一个 ASMR 属性/事件都没绑定，`<LeftPanel>` 也没绑 ASMR 登录事件，LeftPanel.vue 里没有 ASMR 登录表单。**

| 用户反馈 | 根因 |
|---|---|
| 没有账号系统（UI） | LeftPanel.vue 无 ASMR 登录表单；needsLogin/siteLoggedIn/loginSubtitle/siteUsername/handleSiteLogout 均无 asmr 分支 |
| 热门作品按钮不生效 | RightPanel 点"热门作品"emit `asmr-popular`，但 App.vue 没监听 → 后端命令根本不会发出 |
| 仅带字幕无法勾选 | checkbox 显示 `settings.asmr_subtitle`，emit `update:asmr-search` 无人监听 → settings 永不更新 → 视觉上勾不上，且搜索/列表过滤也不生效 |

### 修复方案（最小改动）

1. **App.vue `<RightPanel>`**：补全 17 个 ASMR props + 14 个事件绑定（映射到已存在的 handleAsmr*）
2. **LeftPanel.vue**：
   - props 加 `asmrUser` / `asmrLoginLoading`；emits 加 `asmr-login` / `asmr-logout` / `asmr-set-proxy`
   - 加 ASMR 登录表单（用户名+密码；ASMR-100 用用户名非邮箱，参照 hanime 表单）
   - needsLogin / siteLoggedIn / loginSubtitle / siteUsername / handleSiteLogout 加 asmr 分支
   - 设置区加 ASMR 代理输入（`asmr_proxy`，留空=直连）
3. **App.vue `<LeftPanel>`**：绑定上述 props/事件；`handleRefreshLogin` 加 asmr 分支
   - 启动静默检查：后端 main() 里已有（settings 加载后 token 存在则 asmr_check_login），无需前端再发
4. **仅带字幕在热门视图也生效**：
   - 前端：`handleAsmrSearchUpdate` popular 分支 → `handleAsmrPopular(1)` 刷新；`handleAsmrPopular` 发命令时带 `subtitle` 参数
   - 后端：`asmr_popular(page, subtitle)` 支持 subtitle，按 `has_subtitle` 过滤（卡片已含该字段）；命令分发传参
   - 收藏视图（服务器收藏无字幕筛选）保持不刷新

---

## 三、三个成人站（xHamster / Pornhub / XVideos）问题总结与提需求指南

### 现状
按 2026-08-28 企划调整：**只做框架（登录 + 区域切换 + 代理设置），不接搜索/解析/下载业务**。已就绪：
- webview OAuth 通用登录（xh/ph 共享 persist:twitter 会话用 X 站 cookie 授权；xv 邮箱密码弹窗）
- cookie 加密持久化 + 启动静默检查 + 退出登录 + 代理设置
- 账号卡片 / 账号档案 / 左侧登录表单全套

### 当前问题
1. **登录后无事可做**：没有搜索框、没有内容列表、没有下载——用户登录后右侧空白
2. **登录成功判定靠 URL 模式猜测**：successPatterns 是正则猜测，站点改版会失灵
3. **无内容消费闭环**：无法验证 cookie 是否真正可用（比如拉一次收藏列表）

### 以后应该如何提需求（按其他站的经验，给出以下 6 项信息即可开工）

参照已完成站点的三种模板，提需求时按这个清单给：

1. **站点类型选择**（决定工作量）：
   - X 站类型（复杂站）：有 GraphQL/REST API + 关注体系 + cookie 登录（如 Twitter、Hanime1）
   - IW 站类型（简单站）：邮箱密码 + REST 分页 API（如 Iwara、ASMR-100）
   - Bunkr/PA 站类型（纯资源站）：URL 解析 + 批量下载，无账号（如 Bunkr、Oreno3d）
2. **登录方式**：邮箱密码 / cookie 粘贴 / OAuth / webview 抓取；有无人机验证（xv 有）
3. **搜索入口**：搜索 API 端点或页面 URL、参数格式、分页方式（页码/cursor）
4. **列表与详情结构**：卡片字段（标题/缩略图/作者/时长等）、详情页 URL 规则
5. **媒体直链与防盗链**：直链是否永久有效（twimg 永久 / coomer 会过期需重抓）、是否需要 referer/cookie
6. **代理需求**：国内直连是否可用、默认代理地址

> 示例提法（照抄格式）："接入 xx 站：邮箱密码登录，搜索 GET /api/search?page=N，卡片有封面+标题+作者，视频直链 m3p8 需带 referer，国内必须代理 127.0.0.1:10809。"

---

## 四、全局账号系统架构总结（面向后期新增网站）

### 分层架构（已实现，新站按此接入）

```
┌─ 前端 UI 层（LeftPanel.vue）────────────────────────────┐
│ 登录表单（按站点类型） / 账号卡片（用户名+Cookie+四按钮）   │
│ 账号档案下拉（未登录也常显）/ 站点代理设置                │
└──────────────┬──────────────────────────────────────────┘
               │ emit（asmr-login / site-oauth-login / ...）
┌──────────────▼──────────────────────────────────────────┐
│ 调度层（App.vue）                                        │
│ handleXxxLogin → sendCommand │ 事件处理：xxx_login_result │
│ handleRefreshLogin（重查） │ handleSaveAccount（档案）    │
└──────────────┬──────────────────────────────────────────┘
               │ NDJSON stdin/stdout（UTF-8）
┌──────────────▼──────────────────────────────────────────┐
│ 后端凭据层（gui_bridge.py）                              │
│ 加密存 theme_cache.dat → creds[site]（token/cookie/密码）│
│ 失效自动重登（保存了密码的站：iwara/asmr/hanime）         │
│ _emit_login_info() 推送全部站登录信息（切站不丢失）        │
│ 账号档案 accounts.json：save/switch/delete（通用）        │
└─────────────────────────────────────────────────────────┘
```

### 三种站点接入模板

| 模板 | 登录 | 凭据存储 | 自动重登 | 代表站 |
|---|---|---|---|---|
| X 站类型（复杂） | cookie 粘贴 / webview OAuth | cookie 串加密 | ❌（需重抓） | twitter、exhentai、xh/ph/xv |
| IW 站类型（简单） | 邮箱密码（asmr 为用户名密码） | token+密码加密 | ✅ 过期自动重登 | iwara、asmr、hanime |
| 纯资源站 | 无账号 | — | — | bunkr、oreno3d |

### 新站接入清单（照做即可，全部已有基础设施）

1. 后端：`xxx_login` / `xxx_check_login(silent)` / `xxx_logout` / `xxx_set_proxy` + 命令分发 + DEFAULT_SETTINGS 加 `xxx_proxy` + `_emit_login_info()` 加站点 + 密码存 creds（可自动重登）
2. 启动恢复：main() 里恢复代理设置 + 有凭据则静默 check_login
3. 前端 App.vue：`xxxUser` ref + `handleXxxLogin/Logout/SetProxy` + `xxx_login_result` 事件处理（silent/logout/network_issue 三分支）+ handleRefreshLogin 分支 + LeftPanel 绑定
4. 前端 LeftPanel.vue：登录表单（按模板选 cookie 粘贴/邮箱密码/OAuth 按钮）+ needsLogin/siteLoggedIn/loginSubtitle/siteUsername/handleSiteLogout 五处加分支 + emits + 代理设置输入
5. 账号档案/切换账号/删除：通用代码自动覆盖（switch_account 加站点分支即可）
6. 抓取 Cookie 工具：fetch_cookies.py 的 SITES 列表加一行

### 本轮补全
- ASMR 站补齐了第 3、4 步（之前后端和 UI 组件都在，只缺 App.vue/LeftPanel 的接线）——即"全局账号系统"在 ASMR 站的断链修复

---

## 五、修复记录（边修复边完善）

- [x] 验证此前修复（第一节）
- [x] 本 md 任务前总结
- [x] App.vue RightPanel ASMR 绑定（17 props + 14 events，插在 oreno 绑定之后）
- [x] LeftPanel.vue ASMR 登录表单（用户名+密码）+ 五处分支 + 代理设置（asmr_proxy）+ emits/props
- [x] App.vue LeftPanel 绑定 + handleRefreshLogin asmr 分支（notify: true）
- [x] 仅带字幕：popular 视图刷新（handleAsmrSearchUpdate）+ handleAsmrPopular 带 subtitle 参数 + 后端 asmr_popular(page, subtitle) 按 has_subtitle 过滤 + 命令分发传参
- [x] 前端 dist 重建（vite build 成功，1.75MB js）
- [x] Python 后端 PyInstaller 重打包并替换根目录 bunkr_bridge/（onedir，exe+internal）
- [x] bugfile/ 同步（gui_bridge.py / App.vue / LeftPanel.vue / dist / bunkr_bridge / 上下文 md / 本 md）
- [x] 事件任务对话压缩上下文.md 已更新（本轮记录段）
- [x] 新单文件 EXE：`小小下载器/小小下载器.exe`（100.7MB，含本轮全部修复）
- [x] 补丁.exe：`补丁.exe`（54.2MB，bugfile/ 内嵌全部改动）
- [x] git commit 5ebfb6e + push 成功（含之前积压的 2 个本地提交一并推送）

---

## 六、识图功能实现（2026-08-28 第二轮）

按用户需求完成（详见 事件任务对话压缩上下文.md "识图功能实现轮"）：
- **左侧识图按钮下方粘贴窗口**：placeholder "可以粘贴搜索结果到此处"，自动保存 `cache/reverse_paste.txt`（启动加载、失焦保存）
- **点击识图 → 右侧内容区被占用**：显示拖拽框（拖图或点击选图）
- **全部网站返回后展示**：逐站进度（✓ n 条 / ✕ 失败），失效网站直接不展示；结果按站点分组、标注网站来源、缩略图/标题/相似度/链接（复制/打开/点击卡片跳转）
- **内置识图网站 9 站并发**：trace.moe（补充，免费 JSON API，番剧识别最强）、SauceNAO（补充，二次元插画最常用）、IQDB、ascii2d、搜图bot酱（soutubot.moe）、Google、Yandex（后两站国内需在左侧填识图代理）、Lenso.ai（官方 API 需付费订阅，设置中填 Token 后启用，留空跳过）、Whos.tv（无公开免费 API，失败自动移除）
- 新增设置：`reverse_proxy`（识图代理）、`reverse_lenso_token`（Lenso Token）；preload 新增 `getPathForFile`（Electron 30 拖拽取路径）
- 构建产物：前端 dist 重建、后端 bunkr_bridge 重打包、bugfile 同步、新 EXE + 补丁.exe 已产出
