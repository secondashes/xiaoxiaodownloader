// 临时测试：net.fetch 头部矩阵（找出哪个头导致 BLOCKED_BY_CLIENT）
const { app, net } = require('electron')
const path = require('path')
const fs = require('fs')

app.setPath('userData', path.join(__dirname, '.test-userdata'))
fs.mkdirSync(path.join(__dirname, '.test-userdata'), { recursive: true })

let token = ''
try { token = JSON.parse(fs.readFileSync(path.join(__dirname, '.test-token.json'), 'utf8')).t } catch (e) {}
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'

app.whenReady().then(async () => {
  const base = 'https://api.iwara.tv/search?query=genshin&type=video&limit=3&sort=relevance&rating=all'
  const tests = [
    ['Accept only', { 'Accept': 'application/json' }],
    ['+Origin', { 'Accept': 'application/json', 'Origin': 'https://www.iwara.tv' }],
    ['+Referer', { 'Accept': 'application/json', 'Referer': 'https://www.iwara.tv/' }],
    ['+UA', { 'Accept': 'application/json', 'User-Agent': UA }],
    ['UA+Auth', { 'Accept': 'application/json', 'User-Agent': UA, 'Authorization': `Bearer ${token}` }],
    ['UA only', { 'User-Agent': UA }],
  ]
  for (const [label, headers] of tests) {
    try {
      const r = await net.fetch(base, { headers })
      const text = await r.text()
      let d = null
      try { d = JSON.parse(text) } catch (e) {}
      const list = d && d.results && (Array.isArray(d.results) ? d.results : (d.results.video || []))
      console.log(`=== ${label} | HTTP ${r.status} | count: ${d && d.count}`)
      if (Array.isArray(list)) for (const v of list.slice(0, 3)) console.log('  -', (v.title || '').slice(0, 50))
      else if (text) console.log('  body:', text.slice(0, 100))
    } catch (e) {
      console.log(`=== ${label} | ERR: ${e.message}`)
    }
  }
  app.quit()
})
