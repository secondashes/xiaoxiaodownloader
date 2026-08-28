const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('floatApi', {
  onData: (callback) => {
    ipcRenderer.on('float-data', (event, data) => callback(data))
  },
  showMain: () => {
    ipcRenderer.send('float-show-main')
  },
  close: () => {
    ipcRenderer.send('float-close')
  },
  openDownloads: () => {
    ipcRenderer.send('float-open-downloads')
  },
  moveWindow: (dx, dy) => {
    ipcRenderer.send('float-move', { dx, dy })
  },
  sendCommand: (cmd) => {
    ipcRenderer.send('float-command', cmd)
  },
  showContextMenu: (payload) => {
    ipcRenderer.send('float-context-menu', payload)
  },
})
