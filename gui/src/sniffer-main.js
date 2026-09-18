// 手动抓取（资源嗅探）窗口入口：独立 BrowserWindow 加载（vite 多入口 sniffer.html）
import { createApp } from 'vue'
import naive from 'naive-ui'
import SnifferWindow from './SnifferWindow.vue'

const app = createApp(SnifferWindow)
app.use(naive)
app.mount('#app')
