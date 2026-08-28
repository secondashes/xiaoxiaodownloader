const { contextBridge, ipcRenderer } = require('electron')

// 事件缓冲：在渲染进程注册回调前，先缓存收到的事件，
// 避免首次打开窗口时（加载未完成）丢失 tasks_snapshot
const eventBuffer = []
let eventCallback = null

ipcRenderer.on('downloads-event', (event, data) => {
  if (eventCallback) {
    eventCallback(data)
  } else {
    eventBuffer.push(data)
  }
})

contextBridge.exposeInMainWorld('downloadsApi', {
  onEvent: (callback) => {
    eventCallback = callback
    while (eventBuffer.length > 0) {
      callback(eventBuffer.shift())
    }
  },
  pauseTask: (id) => ipcRenderer.send('dl-command', { cmd: 'pause_task', task_id: id }),
  resumeTask: (id) => ipcRenderer.send('dl-command', { cmd: 'resume_task', task_id: id }),
  cancelTask: (id) => ipcRenderer.send('dl-command', { cmd: 'cancel_task', task_id: id }),
  removeTask: (id) => ipcRenderer.send('dl-command', { cmd: 'remove_task', task_id: id }),
  toggleShutdown: (enabled) => ipcRenderer.send('dl-command', { cmd: 'shutdown_after_done', enabled }),
  openDetail: (id) => ipcRenderer.send('dl-open-detail', id),
  close: () => ipcRenderer.send('dl-close'),
})
