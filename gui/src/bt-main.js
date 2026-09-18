// BT 下载窗口入口：独立 BrowserWindow 加载（vite 多入口 bt.html）
import { createApp } from 'vue'
import naive from 'naive-ui'
import BtWindow from './BtWindow.vue'

const app = createApp(BtWindow)
app.use(naive)
app.mount('#app')
