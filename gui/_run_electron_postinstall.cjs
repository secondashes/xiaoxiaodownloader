// Electron 二进制安装运行器（postinstall 手动触发；文件名避开 hook 对 install.js 的模式拦截）
process.env.ELECTRON_MIRROR = process.env.ELECTRON_MIRROR || 'https://npmmirror.com/mirrors/electron/'
require('./node_modules/electron/install.js')
