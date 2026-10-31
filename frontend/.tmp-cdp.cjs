const fs = require('fs')
const http = require('http')
const WebSocket = require('C:/Users/admin/Documents/Vigilens/frontend/node_modules/ws')

const HOST = '127.0.0.1'
const PORT = 9222
const APP = 'http://127.0.0.1:5176/'
const SHOTS = 'C:/Users/admin/Documents/Vigilens/frontend/.tmp-shots'
const OUT = 'C:/Users/admin/Documents/Vigilens/frontend/.tmp-cdp-results.json'

function httpJson(method, path) {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: HOST, port: PORT, method, path }, res => {
      let data = ''
      res.on('data', c => { data += c })
      res.on('end', () => {
        try { resolve(data ? JSON.parse(data) : null) } catch (e) { reject(new Error(data)) }
      })
    })
    req.on('error', reject)
    req.end()
  })
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)) }

async function main() {
  fs.mkdirSync(SHOTS, { recursive: true })
  const target = await httpJson('PUT', '/json/new?about:blank')
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  let nextId = 1
  const pending = new Map()
  ws.on('message', raw => {
    const msg = JSON.parse(raw)
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id)
      pending.delete(msg.id)
      if (msg.error) reject(new Error(JSON.stringify(msg.error)))
      else resolve(msg.result)
    }
  })
  await new Promise((resolve, reject) => { ws.on('open', resolve); ws.on('error', reject) })
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = nextId++
    pending.set(id, { resolve, reject })
    ws.send(JSON.stringify({ id, method, params }))
  })
  const evaluate = async (expression) => {
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture: true })
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + ' ' + (r.exceptionDetails.exception && r.exceptionDetails.exception.description))
    return r.result.value
  }
  const waitFor = async (expression, timeout = 8000) => {
    const start = Date.now()
    while (Date.now() - start < timeout) {
      if (await evaluate(expression)) return true
      await sleep(100)
    }
    throw new Error('Timeout waiting for ' + expression)
  }
  const clickAt = async (x, y) => {
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y })
    await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 })
    await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 })
    await sleep(100)
  }
  const press = async (key) => {
    const code = key === ' ' ? 'Space' : key
    const vk = key === 'Enter' ? 13 : 32
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key, code, windowsVirtualKeyCode: vk, text: key === ' ' ? ' ' : undefined })
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key, code, windowsVirtualKeyCode: vk })
    await sleep(150)
  }
  const shot = async (name) => {
    const data = await send('Page.captureScreenshot', { format: 'png', fromSurface: true })
    fs.writeFileSync(`${SHOTS}/${name}.png`, Buffer.from(data.data, 'base64'))
  }
  const setViewport = async (width, height) => {
    await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false })
    await sleep(200)
  }
  const reload = async (theme) => {
    await evaluate(`localStorage.setItem('vigilens-theme', ${JSON.stringify(theme)}); location.reload()`)
    await waitFor(`document.readyState === 'complete'`)
    await waitFor(`!!document.querySelector('.sample-btn')`)
    await sleep(400)
  }
  const uploadPublic = async (name) => {
    await evaluate(`(async () => {
      const blob = await (await fetch('/${name}')).blob()
      const file = new File([blob], '${name}', { type: 'image/png' })
      const input = document.querySelector('input[type=file]')
      const dt = new DataTransfer()
      dt.items.add(file)
      input.files = dt.files
      input.dispatchEvent(new Event('change', { bubbles: true }))
      return true
    })()`)
    await waitFor(`(() => { const i = document.querySelector('.zone-canvas-wrapper img'); return !!i && i.naturalWidth > 0 })()`, 10000)
    await sleep(400)
  }
  const startDrawing = async () => {
    await evaluate(`(() => { const b = [...document.querySelectorAll('.zone-controls .btn')].find(x => x.textContent.trim() === 'Draw zone'); if (!b) throw new Error('no draw'); b.click(); return true })()`)
    await sleep(200)
  }
  const computed = (selector, props) => evaluate(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)})
    if (!el) return null
    const c = getComputedStyle(el)
    const out = {}
    for (const p of ${JSON.stringify(props)}) out[p] = c.getPropertyValue(p)
    return out
  })()`)
  const rect = (selector) => evaluate(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)})
    if (!el) return null
    const r = el.getBoundingClientRect()
    return { left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height }
  })()`)
  const drawPoint = () => evaluate(`(() => { const p = document.querySelector('.draw-point'); return p ? { cx: +p.getAttribute('cx'), cy: +p.getAttribute('cy') } : null })()`)

  const results = {}
  await send('Page.enable')
  await send('Runtime.enable')

  // ---------- 1280: geometry, click mapping, keyboard, hazard log ----------
  await setViewport(1280, 1000)
  await send('Page.navigate', { url: APP })
  await waitFor(`document.readyState === 'complete'`)
  await waitFor(`!!document.querySelector('.sample-btn')`)
  await sleep(400)
  await reload('light')

  await uploadPublic('tmp-normal.png')
  const wrapper = await computed('.zone-canvas-wrapper', ['position','display','line-height','padding','border-top-width','margin','transform','object-fit','overflow','box-sizing'])
  const imgStyle = await computed('.zone-canvas-wrapper img', ['display','max-width','height','object-fit','transform','padding','border-top-width','margin'])
  const svgStyle = await computed('.zone-svg', ['position','inset','width','height','transform','padding','border-top-width','margin'])
  const wrapperRect = await rect('.zone-canvas-wrapper')
  const imgRect = await rect('.zone-canvas-wrapper img')
  const svgRect = await rect('.zone-svg')
  results.styles1280 = { wrapper, img: imgStyle, svg: svgStyle, wrapperRect, imgRect, svgRect }

  await startDrawing()
  await clickAt(imgRect.left + imgRect.width * 0.5, imgRect.top + imgRect.height * 0.5)
  results.centreClick1280 = await drawPoint()
  const before = await evaluate(`document.querySelectorAll('.draw-point').length`)
  await clickAt(imgRect.right + 6, imgRect.top + Math.min(20, imgRect.height / 2))
  await sleep(200)
  const after = await evaluate(`document.querySelectorAll('.draw-point').length`)
  results.outsideClick = { before, after }

  // Analyse sample for findings/hazard log.
  await reload('light')
  await evaluate(`(() => { const b=[...document.querySelectorAll('.sample-btn')].find(x=>x.textContent.trim()==='sample-3'); b.click(); return true })()`)
  await waitFor(`!!document.querySelector('.zone-canvas-wrapper img')`)
  await sleep(300)
  await evaluate(`(() => { const a=document.querySelector('.analyse-btn'); a.click(); return true })()`)
  await waitFor(`!!document.querySelector('[role="tablist"]')`, 15000)
  await sleep(700)
  results.audit1280 = await evaluate(`(() => ({
    rows: document.querySelectorAll('.finding-row').length,
    selectedRows: document.querySelectorAll('.finding-row.is-selected').length,
    hasMasked: !!document.querySelector('.evidence-pill'),
    summary: (document.querySelector('.inspector-summary') || {}).textContent || null,
    findingsCount: document.querySelectorAll('.finding-row').length,
    ppeChips: document.querySelectorAll('.ppe-chip').length,
    overlayPersons: document.querySelectorAll('.person-outline').length,
    overlayZones: document.querySelectorAll('.zone-region').length,
    hasStageFrameTag: !!document.querySelector('.stage-frame__tag'),
    severityLabels: [...document.querySelectorAll('.finding-meta .severity-badge, .finding-meta .uncertainty-badge')].map(x=>x.textContent),
    evidenceImgOk: (() => { const i=document.querySelector('.stage-block img'); return i ? { nw: i.naturalWidth, nh: i.naturalHeight } : null })()
  }))()`)

  const firstBtn = await evaluate(`(() => { const b=document.querySelectorAll('.finding-person')[0]; if(!b) return null; b.focus(); return { label: b.textContent, active: document.activeElement === b } })()`)
  await press('Enter')
  const afterEnter = await evaluate(`(() => { const r=document.querySelector('.finding-row.is-selected'); return { count: document.querySelectorAll('.finding-row.is-selected').length, text: r ? r.textContent.slice(0,40) : null } })()`)
  const secondFocus = await evaluate(`(() => { const b=document.querySelectorAll('.finding-person')[1]; if(!b) return null; b.focus(); return { label: b.textContent, active: document.activeElement === b } })()`)
  await press(' ')
  const afterSpace = await evaluate(`(() => { const r=document.querySelector('.finding-row.is-selected'); return { count: document.querySelectorAll('.finding-row.is-selected').length, text: r ? r.textContent.slice(0,40) : null } })()`)
  results.keyboardFinding = { firstBtn, afterEnter, secondFocus, afterSpace }

  // Overlay polygons: Enter and Space selection.
  const overlayFocus1 = await evaluate(`(() => { const p=document.querySelectorAll('.person-outline')[0]; p.focus(); return { active: document.activeElement === p, label: p.getAttribute('aria-label') } })()`)
  await press('Enter')
  const overlayEnter = await evaluate(`(() => { const p=document.querySelectorAll('.person-outline.is-selected'); return { selected: document.querySelectorAll('.person-outline.is-selected').length, label: p[0] ? p[0].getAttribute('aria-label') : null } })()`)
  const overlayFocus2 = await evaluate(`(() => { const p=document.querySelectorAll('.person-outline')[1]; p.focus(); return { active: document.activeElement === p, label: p.getAttribute('aria-label') } })()`)
  await press(' ')
  const overlaySpace = await evaluate(`(() => { const p=document.querySelectorAll('.person-outline.is-selected'); return { selected: document.querySelectorAll('.person-outline.is-selected').length, label: p[0] ? p[0].getAttribute('aria-label') : null } })()`)
  results.keyboardOverlay = { overlayFocus1, overlayEnter, overlayFocus2, overlaySpace }

  await evaluate(`document.getElementById('tab-log').click()`)
  await sleep(300)
  results.hazard1280 = await evaluate(`(() => { const w=document.querySelector('.table-scroll'); const t=document.querySelector('.data-table'); const s=document.querySelector('.data-table tr.is-selected'); return { table: !!t, headers: [...document.querySelectorAll('.data-table th')].map(h=>h.textContent), rows: document.querySelectorAll('.data-table tbody tr').length, scrollWidth: w?w.scrollWidth:null, clientWidth: w?w.clientWidth:null, overflowX: w?getComputedStyle(w).overflowX:null, selected: !!s, firstSeverity: (document.querySelector('.data-table tbody .severity-badge')||{}).textContent||null } })()`)
  await shot('1280-light-audit')
  await evaluate(`document.documentElement.setAttribute('data-theme','dark')`)
  await sleep(300)
  await shot('1280-dark-audit')
  await evaluate(`document.documentElement.setAttribute('data-theme','light')`)

  // ---------- 768: below stage, alignment, click ----------
  await reload('light')
  await setViewport(768, 1100)
  await sleep(400)
  results.layout768 = await evaluate(`(() => { const w=document.querySelector('.workspace').getBoundingClientRect(); const i=document.querySelector('.inspector').getBoundingClientRect(); return { workspaceBottom: w.bottom, inspectorTop: i.top, below: i.top >= w.bottom - 1, pageScrollWidth: document.scrollingElement.scrollWidth, pageClientWidth: document.scrollingElement.clientWidth } })()`)
  await uploadPublic('tmp-normal.png')
  const r768 = await rect('.zone-canvas-wrapper img')
  await startDrawing()
  await clickAt(r768.left + r768.width * 0.25, r768.top + r768.height * 0.75)
  results.click768 = await drawPoint()
  results.align768 = { wrapperRect: await rect('.zone-canvas-wrapper'), imgRect: await rect('.zone-canvas-wrapper img'), svgRect: await rect('.zone-svg') }
  await shot('768-editor')

  // ---------- 390: no page scroll, icon-only toggle, alignment, click ----------
  await reload('dark')
  await setViewport(390, 900)
  await sleep(500)
  results.layout390 = await evaluate(`(() => { const d=document.scrollingElement; const label=document.querySelector('.theme-toggle__label'); const lc=label?getComputedStyle(label):null; return { scrollWidth:d.scrollWidth, clientWidth:d.clientWidth, noPageScroll:d.scrollWidth<=d.clientWidth, toggleLabelPosition:lc?lc.position:null, toggleLabelWidth:lc?lc.width:null, theme:document.documentElement.getAttribute('data-theme'), inspectorTop: document.querySelector('.inspector').getBoundingClientRect().top, workspaceBottom: document.querySelector('.workspace').getBoundingClientRect().bottom } })()`)
  await uploadPublic('tmp-normal.png')
  const r390 = await rect('.zone-canvas-wrapper img')
  await startDrawing()
  await clickAt(r390.left + r390.width * 0.8, r390.top + r390.height * 0.2)
  results.click390 = await drawPoint()
  results.align390 = { wrapperRect: await rect('.zone-canvas-wrapper'), imgRect: await rect('.zone-canvas-wrapper img'), svgRect: await rect('.zone-svg') }
  results.layout390.afterImage = await evaluate(`(() => { const d=document.scrollingElement; return { scrollWidth:d.scrollWidth, clientWidth:d.clientWidth, noPageScroll:d.scrollWidth<=d.clientWidth } })()`)
  await shot('390-editor-dark')

  // ---------- Wide / tall at 1280 ----------
  await setViewport(1280, 1000)
  await reload('light')
  await uploadPublic('tmp-wide.png')
  results.wide = { natural: await evaluate(`(() => { const i=document.querySelector('.zone-canvas-wrapper img'); return { w:i.naturalWidth, h:i.naturalHeight } })()`), imgRect: await rect('.zone-canvas-wrapper img'), wrapperRect: await rect('.zone-canvas-wrapper'), svgRect: await rect('.zone-svg') }
  await shot('1280-wide')
  await uploadPublic('tmp-tall.png')
  results.tall = { natural: await evaluate(`(() => { const i=document.querySelector('.zone-canvas-wrapper img'); return { w:i.naturalWidth, h:i.naturalHeight } })()`), imgRect: await rect('.zone-canvas-wrapper img'), wrapperRect: await rect('.zone-canvas-wrapper'), svgRect: await rect('.zone-svg') }
  await shot('1280-tall')

  // ---------- Print ----------
  await reload('dark')
  await evaluate(`(() => { const b=[...document.querySelectorAll('.sample-btn')].find(x=>x.textContent.trim()==='sample-3'); b.click(); return true })()`)
  await waitFor(`!!document.querySelector('.zone-canvas-wrapper img')`)
  await sleep(300)
  await evaluate(`(() => { const a=document.querySelector('.analyse-btn'); a.click(); return true })()`)
  await waitFor(`!!document.querySelector('[role="tablist"]')`, 15000)
  await sleep(400)
  await send('Emulation.setEmulatedMedia', { media: 'print' })
  await sleep(400)
  results.print = await evaluate(`(() => {
    const root = getComputedStyle(document.documentElement)
    const topbar = document.querySelector('.topbar')
    const panels = [...document.querySelectorAll('[role=tabpanel]')].map(p => getComputedStyle(p).display)
    const footer = document.querySelector('.print-footer')
    const table = document.querySelector('.data-table')
    const tag = document.querySelector('.stage-frame__tag')
    return {
      bg: root.getPropertyValue('--bg').trim(),
      text: root.getPropertyValue('--text').trim(),
      topbarDisplay: topbar ? getComputedStyle(topbar).display : null,
      themeToggleDisplay: (() => { const e=document.querySelector('.theme-toggle'); return e?getComputedStyle(e).display:null })(),
      panelDisplays: panels,
      footerText: footer ? footer.textContent.trim() : null,
      footerDisplay: footer ? getComputedStyle(footer).display : null,
      tableDisplay: table ? getComputedStyle(table).display : null,
      stageTagDisplay: tag ? getComputedStyle(tag).display : null,
      findingsRows: document.querySelectorAll('.finding-row').length
    }
  })()`)
  await shot('print')
  await send('Emulation.setEmulatedMedia', { media: '' })

  fs.writeFileSync(OUT, JSON.stringify(results, null, 2))
  console.log(JSON.stringify(results, null, 2))
  await httpJson('GET', `/json/close/${target.id}`)
  ws.close()
}

main().catch(err => { console.error(err.stack || String(err)); process.exit(1) })
