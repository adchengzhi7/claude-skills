import { expect, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On, SessionContextBreakdown } from 'claude-code'

import { alertStep, pushReading, short, turnsLeft } from '../hooks/weather'

const WINDOW = 200_000
const EMPTY = '（這一列沒有東西）'

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
    bodyColumns: 60,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 30 },
    view: {},
  },
} as const

// compactAt 是 null＝Claude Code 沒有回報自動整理門檻
const breakdown = (compactAt: number | null): SessionContextBreakdown => ({
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
  ...(compactAt === null ? {} : { autoCompactThreshold: compactAt }),
  isAutoCompactEnabled: compactAt !== null,
  apiUsage: null,
})

// 問明細時引擎怎麼回：正常給、不給（但不報錯）、直接報錯
type Detail = 'ok' | 'absent' | 'throws'

const REFUSED = 'no surface places panes'

// 站在引擎的位置回答 mod 會問的事。compactAt 是 null＝沒有自動整理門檻；isPlaced 是 false＝介面不放面板
const world = (on: On, { compactAt = 180_000 as number | null, isPlaced = true } = {}) => {
  let toasts: readonly string[] = []
  let logs: readonly string[] = []
  let panes: readonly string[] = []
  let detail: Detail = 'ok'
  let asks = 0

  on('session.usage', (_, e) => {
    if (e.breakdown !== undefined) {
      asks += 1

      if (detail === 'throws') {
        throw new Error('明細暫時拿不到')
      }
    }

    return {
      value: {
        startedAt: 0,
        context:
          e.breakdown === undefined || detail !== 'ok'
            ? { window: WINDOW }
            : { window: WINDOW, breakdown: breakdown(compactAt) },
        rateLimits: [{ kind: 'five_hour', percentUsed: 23 }],
      },
    }
  })
  on('command.register', (_, e) => ({ value: { command: e.name } }))
  on('ui.toast', (_, e) => {
    toasts = [...toasts, e.text]

    return { value: undefined }
  })
  on('ui.open', (_, e) => {
    panes = [...panes.filter(id => id !== e.id), e.id]

    return { value: isPlaced ? { isPlaced: true } : { isPlaced: false, reason: REFUSED } }
  })
  on('ui.close', (_, e) => {
    panes = panes.filter(id => id !== e.id)

    return { value: undefined }
  })
  on('ui.panes', () => ({
    value: panes.map(id => ({ id, title: id, isShown: true, isFocused: false, isPlaced: true })),
  }))
  on('ui.log', (_, e) => {
    logs = [...logs, e.text]

    return { value: undefined }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.measure', (_, e) => ({ changed: e.changed }))
  on('session.end', (_, e) => ({ sessionId: e.sessionId }))
  // mod 把那一列讓出來時，看到的就是引擎自己畫的這一行
  on('ui.render', { component: 'AbovePrompt' }, ($, e) => {
    const { Text } = $.ui.resolve(e)

    return <Text>{EMPTY}</Text>
  })

  return {
    toasts: () => toasts,
    logs: () => logs,
    asks: () => asks,
    answerDetail: (next: Detail) => {
      detail = next
    },
  }
}

const start = ($: Engine) =>
  $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })

const measure = ($: Engine, percent: number, window = WINDOW) =>
  $.session.measure({
    context: { tokens: (WINDOW * percent) / 100, window, percent },
    rateLimits: [{ kind: 'five_hour', percentUsed: 23 }],
    changed: ['context'],
  })

const run = ($: Engine, args: string) =>
  $.command.run({
    command: 'context-weather',
    args,
    origin: { kind: 'composer' },
    presentation: { isFullscreen: true, columns: 160 },
  })

const band = async ($: Engine, props: { hasSurvey?: boolean; bodyColumns?: number } = {}) => {
  const ui = await $.ui.mount({ ...BAND, props: { ...BAND.props, ...props }, surface: 'terminal' })
  const texts = (await ui.findAll({ type: 'Text' })).map(one => one.text)
  await ui.unmount()

  return texts
}

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

test('跨進有雨、暴雨各提醒一次；門檻邊緣來回不重複；明顯降回去後會重新提醒', async ($, on) => {
  const { toasts } = world(on)
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

  await measure($, 89)
  await measure($, 90)
  expect(toasts()).toHaveLength(2)

  await measure($, 30)
  await measure($, 76)
  expect(toasts()).toHaveLength(3)
})

test('資料不夠不猜還能幾回合；有三次讀數後，算到自動整理的門檻為止', async ($, on) => {
  world(on)
  await start($)

  await measure($, 10)
  const early = (await band($)).find(text => text.includes('空間很夠'))
  expect(early).toBe('  空間很夠')

  await measure($, 15)
  await measure($, 20)
  // 每回合長 10k，目前 40k，門檻 180k → 14 回合（不是算到 200k 的 16）
  const later = (await band($)).find(text => text.includes('空間很夠'))
  expect(later).toBe('  空間很夠，照最近的速度約還能 14 回合')
})

test('Claude Code 沒給自動整理門檻時，預估改算到上限', async ($, on) => {
  world(on, { compactAt: null })
  await start($)
  await measure($, 10)
  await measure($, 15)
  await measure($, 20)

  const note = (await band($)).find(text => text.includes('空間很夠'))
  expect(note).toBe('  空間很夠，照最近的速度約還能 16 回合')
})

test('按「明細」會打開明細，佔空間的由大到小排，額度也列出來', async ($, on) => {
  world(on)
  await start($)
  await measure($, 17)

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'detail' })

  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await pane.find({ type: 'Text', text: '已用' }))?.text).toBe('晴　已用 34k / 200k（17%）')

  const labels = (await pane.findAll({ type: 'Text' })).map(one => one.text)
  expect(labels.indexOf('對話內容')).toBeGreaterThan(-1)
  expect(labels.indexOf('對話內容')).toBeLessThan(labels.indexOf('系統提示'))
  expect(labels).toContain('剩餘空間')
  expect(labels).toContain('自動整理保留區')
  expect(labels).toContain('用到 180k 時會自動整理對話')
  expect(labels).toContain('額度：5 小時額度 23%')
  await pane.unmount()
  await ui.unmount()
})

test('按「收起」那一列讓位，打指令叫回來；/context-weather off 也會收起', async ($, on) => {
  const { toasts } = world(on)
  await start($)
  await measure($, 18)
  expect(await band($)).toContain('晴')

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'hide' })
  await ui.unmount()
  expect(await band($)).toEqual([EMPTY])
  expect(toasts().at(-1)).toContain('/context-weather')

  expect((await run($, '')).text).toBe('已打開對話空間明細。')
  expect(await band($)).toContain('晴')

  expect((await run($, 'off')).text).toContain('已收起')
  expect(await band($)).toEqual([EMPTY])
})

test('/clear 之後舊讀數不留在畫面上', async ($, on) => {
  world(on)
  await start($)
  await measure($, 80)
  expect(await band($)).toContain('有雨')

  await $.session.end({ reason: 'clear', sessionId: 's1', resume: { id: 's1' } })
  expect(await band($)).toEqual([EMPTY])
})

test('換到另一段對話（resume）之後舊讀數也不留', async ($, on) => {
  world(on)
  await start($)
  await measure($, 80)
  expect(await band($)).toContain('有雨')

  await $.session.end({ reason: 'resume', sessionId: 's1', resume: { id: 's1' } })
  expect(await band($)).toEqual([EMPTY])
})

test('門檻只在載入和視窗大小改變時問，不是每回合問', async ($, on) => {
  const { asks } = world(on)
  await start($)
  expect(asks()).toBe(1)

  await measure($, 10)
  await measure($, 15)
  await measure($, 20)
  expect(asks()).toBe(1)

  await measure($, 21, 1_000_000)
  expect(asks()).toBe(2)
  await measure($, 22, 1_000_000)
  expect(asks()).toBe(2)
})

for (const [how, logged] of [['absent', 0], ['throws', 1]] as const) {
  test(`開場拿不到門檻（${how}）不會就此認定沒有門檻，下一回合會再問`, async ($, on) => {
    const { asks, logs, answerDetail } = world(on)
    answerDetail(how)
    await start($)
    expect(asks()).toBe(1)
    expect(logs()).toHaveLength(logged)

    answerDetail('ok')
    await measure($, 10)
    await measure($, 15)
    await measure($, 20)
    expect(asks()).toBe(2)
    // 拿到門檻 180k → 14 回合；若被記成「沒有門檻」會是 16
    const note = (await band($)).find(text => text.includes('空間很夠'))
    expect(note).toBe('  空間很夠，照最近的速度約還能 14 回合')
  })
}

test('介面不放面板時照實說，不說「已打開」', async ($, on) => {
  const { toasts } = world(on, { isPlaced: false })
  await start($)
  await measure($, 18)

  expect((await run($, '')).text).toBe(`明細還沒顯示：${REFUSED}`)

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'detail' })
  await ui.unmount()
  expect(toasts().at(-1)).toBe(`明細還沒顯示：${REFUSED}`)
})

test('壞讀數（不是數字）當成沒有讀數：顯示佔位、不跳提醒', async ($, on) => {
  const { toasts } = world(on)
  await start($)
  await measure($, 80)
  expect(await band($)).toContain('有雨')
  expect(toasts()).toHaveLength(1)

  await $.session.measure({
    context: { tokens: Number.NaN, window: WINDOW, percent: Number.NaN },
    rateLimits: [],
    changed: ['context'],
  })
  expect((await band($))[0]).toBe('對話空間  等下一次回應後才有讀數  ')
  expect(toasts()).toHaveLength(1)
})

test('有問卷佔用那一列時讓位；視窗窄時省略長條和後面那句話', async ($, on) => {
  world(on)
  await start($)
  await measure($, 18)

  const wide = await band($)
  expect(wide.some(text => text.includes('█'))).toBe(true)
  expect(wide.some(text => text.includes('空間很夠'))).toBe(true)

  expect(await band($, { hasSurvey: true })).toEqual([EMPTY])

  const narrow = await band($, { bodyColumns: 70 })
  expect(narrow).toContain('晴')
  expect(narrow.some(text => text.includes('█'))).toBe(false)
  expect(narrow.some(text => text.includes('空間很夠'))).toBe(false)
})

test('純計算：重新起算、不亂預估、數字寫法、提醒的緩衝', () => {
  expect(pushReading([10, 20, 30], 40)).toEqual([10, 20, 30, 40])
  expect(pushReading([10, 20, 30], 5)).toEqual([5])
  expect(pushReading([10, 20, 30], null)).toEqual([])
  expect(turnsLeft([10, 20, 30], 100)).toBe(7)
  expect(turnsLeft([30, 30, 30], 100)).toBe(null)
  expect(turnsLeft([10, 20], 100)).toBe(null)

  expect(short(999_499)).toBe('999k')
  expect(short(999_500)).toBe('1M')
  expect(short(1_250_000)).toBe('1.3M')

  expect(alertStep(0, 76)).toEqual({ alerted: 75, isNew: true })
  expect(alertStep(75, 92)).toEqual({ alerted: 90, isNew: true })
  expect(alertStep(90, 89)).toEqual({ alerted: 90, isNew: false })
  expect(alertStep(90, 85)).toEqual({ alerted: 75, isNew: false })
  expect(alertStep(75, 72)).toEqual({ alerted: 75, isNew: false })
  expect(alertStep(75, 70)).toEqual({ alerted: 0, isNew: false })
  // 從暴雨一次掉很多：只離開暴雨，還沒降到 70 以下就還算在有雨，回到 75 不重複跳
  expect(alertStep(90, 72)).toEqual({ alerted: 75, isNew: false })
  expect(alertStep(75, 75)).toEqual({ alerted: 75, isNew: false })
  expect(alertStep(90, 70)).toEqual({ alerted: 0, isNew: false })
  expect(alertStep(0, 95)).toEqual({ alerted: 90, isNew: true })
  expect(alertStep(90, 99)).toEqual({ alerted: 90, isNew: false })
})
