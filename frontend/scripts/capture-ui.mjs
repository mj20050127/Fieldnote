import { chromium } from 'playwright'
import { mkdir, writeFile } from 'node:fs/promises'

const browser = await chromium.launch()
const context = await browser.newContext({ baseURL: process.env.BASE_URL || 'http://127.0.0.1:8000', viewport: { width: 1440, height: 1000 } })
const page = await context.newPage()
const destination = new URL('../../.local/screenshots/', import.meta.url)
await mkdir(destination, { recursive: true })
const diagnostics = []
page.on('pageerror', error => diagnostics.push(error.message))
await page.goto('/login')
await page.screenshot({ path: new URL('01-login.png', destination).pathname.replace(/^\/(\w:)/, '$1'), fullPage: true })
await page.getByLabel('用户名', { exact: true }).fill('demo')
await page.getByLabel('密码', { exact: true }).fill('Fieldnote2026!')
await page.getByRole('button', { name: '登录工作空间' }).click()
await page.getByRole('heading', { name: '我的问卷' }).waitFor()
await page.screenshot({ path: new URL('02-dashboard.png', destination).pathname.replace(/^\/(\w:)/, '$1'), fullPage: true })
const surveys = (await (await page.request.get('/api/surveys')).json()).items
const soccer = surveys.find(s => s.title === '校园足球活动参与调查')
const stats = surveys.find(s => s.title === '校园学习空间体验调查')
await page.goto(`/surveys/${soccer.id}/edit`)
await page.getByRole('heading', { name: soccer.title, exact: true }).waitFor()
await page.screenshot({ path: new URL('03-editor.png', destination).pathname.replace(/^\/(\w:)/, '$1'), fullPage: true })
await page.goto(`/surveys/${stats.id}/statistics`)
await page.getByRole('heading', { name: '你更喜欢在哪里学习？', exact: true }).waitFor()
await page.screenshot({ path: new URL('04-statistics.png', destination).pathname.replace(/^\/(\w:)/, '$1'), fullPage: true })
await page.setViewportSize({ width: 390, height: 844 })
for (const [name, path] of [['mobile-dashboard', '/dashboard'], ['mobile-editor', `/surveys/${soccer.id}/edit`], ['mobile-statistics', `/surveys/${stats.id}/statistics`], ['mobile-form', `/survey/${soccer.public_code}`]]) {
  await page.goto(path)
  await page.waitForLoadState('networkidle')
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
  if (overflow) diagnostics.push(`${name}: horizontal overflow`)
  await page.screenshot({ path: new URL(`${name}.png`, destination).pathname.replace(/^\/(\w:)/, '$1'), fullPage: true })
}
await writeFile(new URL('diagnostics.json', destination), JSON.stringify(diagnostics, null, 2))
await browser.close()
console.log(JSON.stringify({ screenshots: destination.pathname, diagnostics }))
