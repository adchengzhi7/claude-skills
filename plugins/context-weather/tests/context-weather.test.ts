import { expect, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On, SessionContextBreakdown } from 'claude-code'

import { pushReading, turnsLeft } from '../hooks/weather'

const WINDOW = 200_000

const BAND = {
  plugin: 'context-weather',
  component: 'AbovePrompt',
  props: {
    hasSurvey: false,
    isWorking: false,
    maxRows: 10,
    bodyColumns: 140,
    scroll: { offset: 0, bodyRows: 10 },
    view: {},
  },
} as const

const PANE = {
  plugin: 'context-weather',
  component: 'Pane',
  requestId: 'context-weather',
  props: {
    title: '對話空間明細',
    isFocused: false,
    bodyColumns: 56,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 30 },
    view: {},
  },
} as const

const BREAKDOWN: SessionContextBreakdown = {
  categories: [
    { name: 'System prompt', tokens: 4_000, color: 'promptBorder', isDeferred: false, kind: 'used' },
    { name: 'Messages', tokens: 30_000, color: 'promptBorder', isDeferred: false, kind: 'used' },
    { name: 'Free space', tokens: 146_000, color: 'inactive', isDeferred: false, kind: 'free' },
    { name: 'Autocompact buffer', tokens: 20_000, color: 'inactive', isDeferred: false, kind: 'buffer' },
  ],
  totalTokens: 34_000,
  maxTokens: WINDOW,
  rawMaxTokens: WINDOW,
  autocompactSource: 'model-default',
  percentage: 17,
  gridRows: [],
  model: 'test',
  memoryFiles: [],
  mcpTools: [],
  agents: [],
  autoCompactThreshold: 180_000,
  isAutoCompactEnabled: true,
  apiUsage: null,
}

// 站在引擎的位置回答 mod 會問的事；回傳的函式讀出到目前為止跳過的提醒
const world = (on: On): (() => readonly string[]) => {
  let toasts: readonly string[] = []
  let panes: readonly string[] = []

  on('session.usage', (_, e) => ({
    value: {
      startedAt: 0,
      context:
        e.breakdown === undefined ? { window: WINDOW } : { window: WINDOW, breakdown: BREAKDOWN },
      rateLimits: [{ kind: 'five_hour', percentUsed: 23 }],
    },
  }))
  on('command.register', (_, e) => ({ value: { command: e.name } }))
  on('ui.toast', (_, e) => {
    toasts = [...toasts, e.text]

    return { value: undefined }
  })
  on('ui.open', (_, e) => {
    panes = [...panes, e.id]

    return { value: { isPlaced: true } }
  })
  on('ui.panes', () => ({
    value: panes.map(id => ({ id, title: id, isShown: true, isFocused: false, isPlaced: true })),
  }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.measure', (_, e) => ({ changed: e.changed }))

  return () => toasts
}

const start = ($: Engine) =>
  $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })

const measure = ($: Engine, percent: number) =>
  $.session.measure({
    context: { tokens: (WINDOW * percent) / 100, window: WINDOW, percent },
    rateLimits: [{ kind: 'five_hour', percentUsed: 23 }],
    changed: ['context'],
  })

test('量到用量後，那一列顯示天氣、百分比和用量（終端機與桌面版）', async ($, on) => {
  world(on)
  await start($)
  await measure($, 18)

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...BAND, surface })
    expect((await ui.find({ type: 'Text', text: '晴' }))?.props.color).toBe('success')
    expect((await ui.find({ type: 'Text', text: '%' }))?.text).toBe(' 18%')
    expect(await ui.find({ type: 'Text', text: '36k / 200k' })).toBeDefined()
    await ui.unmount()
  }

  await measure($, 92)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: '暴雨' }))?.props.color).toBe('error')
  expect((await ui.find({ type: 'Text', text: '%' }))?.text).toBe(' 92%')
  await ui.unmount()
})

test('跨進有雨、暴雨各提醒一次；同一級不重複；降回去後會重新提醒', async ($, on) => {
  const toasts = world(on)
  await start($)

  await measure($, 18)
  expect(toasts()).toHaveLength(0)

  await measure($, 76)
  expect(toasts()).toHaveLength(1)
  expect(toasts()[0]).toContain('76%')
  expect(toasts()[0]).toContain('有雨')

  await measure($, 80)
  expect(toasts()).toHaveLength(1)

  await measure($, 92)
  expect(toasts()).toHaveLength(2)
  expect(toasts()[1]).toContain('暴雨')

  await measure($, 30)
  await measure($, 76)
  expect(toasts()).toHaveLength(3)
})

test('資料不夠不猜還能幾回合；有三次讀數後才給預估', async ($, on) => {
  world(on)
  await start($)

  await measure($, 10)
  const early = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await early.find({ type: 'Text', text: '空間很夠' }))?.text).toBe('  空間很夠')
  await early.unmount()

  await measure($, 15)
  await measure($, 20)
  const later = await $.ui.mount({ ...BAND, surface: 'terminal' })
  // 每回合長 10k，離 200k 還有 160k → 16 回合
  expect((await later.find({ type: 'Text', text: '空間很夠' }))?.text).toBe(
    '  空間很夠，照最近的速度約還能 16 回合',
  )
  await later.unmount()
})

test('按「明細」會打開明細，佔空間的由大到小排，額度也列出來', async ($, on) => {
  world(on)
  await start($)
  await measure($, 17)

  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await band.press({ key: 'detail' })

  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await pane.find({ type: 'Text', text: '已用' }))?.text).toBe('晴　已用 34k / 200k（17%）')

  const labels = (await pane.findAll({ type: 'Text' })).map(one => one.text)
  expect(labels.indexOf('對話內容')).toBeGreaterThan(-1)
  expect(labels.indexOf('對話內容')).toBeLessThan(labels.indexOf('系統提示'))
  expect(labels).toContain('剩餘空間')
  expect(labels).toContain('自動整理保留區')
  expect(labels).toContain('額度：5 小時額度 23%')
  await pane.unmount()
  await band.unmount()
})

test('用量變小就重新起算，沒在成長就不預估', () => {
  expect(pushReading([10, 20, 30], 40)).toEqual([10, 20, 30, 40])
  expect(pushReading([10, 20, 30], 5)).toEqual([5])
  expect(pushReading([10, 20, 30], null)).toEqual([])
  expect(turnsLeft([10, 20, 30], 100)).toBe(7)
  expect(turnsLeft([30, 30, 30], 100)).toBe(null)
  expect(turnsLeft([10, 20], 100)).toBe(null)
})
