import { expect, mock, test } from 'claude-code/testing'
import type { Engine, Plugin } from 'claude-code/testing'
import type { AgentInfo, On } from 'claude-code'

import { mergeAgents, resetText, short, span, started, statusOf } from '../hooks/overview'

const T0 = 1_800_000_000_000
const WINDOW = 200_000
const TOOL = 'mcp__session-overview__panel'

const PANE = {
  plugin: 'session-overview',
  component: 'Pane',
  requestId: 'session-overview',
  props: {
    title: '總覽',
    isFocused: false,
    bodyColumns: 60,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 30 },
    view: {},
  },
} as const

const REVIEWER: AgentInfo = {
  id: 'a1',
  description: '審查這次改動',
  type: 'code-reviewer',
  status: 'running',
}

const SPAWN = {
  tool_use_id: 'tu1',
  prompt: '審查這批改動',
  description: '審查這次改動',
  subagentType: 'code-reviewer',
  provider: { plugin: 'engine', tier: 'core' },
  parentModel: 'opus',
  background: false,
  fork: false,
} as const

// 另一個外掛，收到量測通知時把總覽面板關掉：用來代替「有人把面板關掉」
const CLOSER: Plugin = {
  name: 'closer',
  register(on) {
    on('session.measure', async ($, e, next) => {
      await $.ui.close({ id: 'session-overview' })

      return next(e)
    })
  },
}

const REFUSED = 'no surface places panes'

// 有人要關面板時引擎怎麼回：真的關掉、被別的外掛擋下、說好但其實沒關
type Closing = 'closes' | 'denied' | 'ignored'

// 站在引擎的位置回答 mod 會問的事。isPlaced 是 false＝介面不放面板
const world = (on: On, { fiveHour = 23, isPlaced = true } = {}) => {
  const time = mock.clock(on, { now: T0 })
  let listed: readonly AgentInfo[] = []
  let panes: readonly string[] = []
  let toasts: readonly string[] = []
  let closing: Closing = 'closes'
  let duringList: (() => Promise<unknown>) | null = null
  let listCalls = 0
  let opens = 0

  on('session.usage', () => ({
    value: {
      startedAt: T0,
      context: { tokens: 36_000, window: WINDOW, percent: 18 },
      rateLimits: [
        // 2 小時 15 分後重置
        { kind: 'five_hour', percentUsed: fiveHour, resetsAt: new Date(T0 + 8_100_000).toISOString() },
        { kind: 'seven_day', percentUsed: 41 },
      ],
      cost: { usd: 4.2 },
    },
  }))
  on('command.register', (_, e) => ({ value: { command: e.name } }))
  on('tool.register', (_, e) => ({ value: { tool: `mcp__session-overview__${e.name}` } }))
  on('agent.list', async () => {
    listCalls += 1
    const snapshot = [...listed]

    // 讓測試能在「清單已經讀出、還沒回到 mod」的空檔插一件事進去
    if (duringList !== null) {
      const interrupt = duringList
      duringList = null
      await interrupt()
    }

    return { value: snapshot }
  })
  on('ui.open', (_, e) => {
    opens += 1
    panes = [...panes.filter(id => id !== e.id), e.id]

    return { value: isPlaced ? { isPlaced: true } : { isPlaced: false, reason: REFUSED } }
  })
  on('ui.close', (_, e) => {
    if (closing === 'denied') {
      return { deny: '另一個外掛不讓它關' }
    }

    if (closing === 'closes') {
      panes = panes.filter(id => id !== e.id)
    }

    return { value: undefined }
  })
  on('ui.panes', () => ({
    value: panes.map(id => ({ id, title: id, isShown: true, isFocused: false, isPlaced })),
  }))
  on('ui.toast', (_, e) => {
    toasts = [...toasts, e.text]

    return { value: undefined }
  })
  on('ui.log', () => ({ value: undefined }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.measure', (_, e) => ({ changed: e.changed }))
  on('session.end', (_, e) => ({ sessionId: e.sessionId }))
  on('agent.spawn', () => ({ model: 'sonnet', agentId: 'a1' }))
  on('turn.complete', (_, e) => ({ text: e.answer }))

  return {
    time,
    list: (next: readonly AgentInfo[]) => {
      listed = next
    },
    listCalls: () => listCalls,
    opens: () => opens,
    toasts: () => toasts,
    isOpen: () => panes.includes('session-overview'),
    closeAttempts: (next: Closing) => {
      closing = next
    },
    whileListing: (interrupt: () => Promise<unknown>) => {
      duringList = interrupt
    },
  }
}

const start = ($: Engine) => $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })

const run = ($: Engine, args: string) =>
  $.command.run({
    command: 'overview',
    args,
    origin: { kind: 'composer' },
    presentation: { isFullscreen: true, columns: 160 },
  })

const closeIt = ($: Engine) =>
  $.session.measure({
    context: { tokens: 36_000, window: WINDOW, percent: 18 },
    rateLimits: [],
    changed: ['context'],
  })

const panel = async ($: Engine, action: 'open' | 'close' | 'status', id: string) =>
  JSON.parse(String((await $.tool.call({ tool: TOOL, tool_use_id: id, action })).result))

const shown = async ($: Engine, surface: 'terminal' | 'desktop' = 'terminal') => {
  const ui = await $.ui.mount({ ...PANE, surface })
  const texts = (await ui.findAll({ type: 'Text' })).map(one => one.text)
  await ui.unmount()

  return texts
}

test('面板顯示對話空間、花費、兩種額度和重置倒數（終端機與桌面版）', async ($, on) => {
  world(on)
  await start($)

  for (const surface of ['terminal', 'desktop'] as const) {
    const texts = await shown($, surface)
    expect(texts).toContain('對話空間')
    expect(texts).toContain('18%')
    expect(texts).toContain('36k / 200k')
    expect(texts).toContain('US$ 4.20')
    expect(texts).toContain('5 小時額度')
    expect(texts).toContain('2 小時 15 分後重置')
    expect(texts).toContain('7 天額度')
    expect(texts).toContain('目前沒有助手在跑')
  }
})

test('助手開始後顯示已跑多久，結束後移到「最近結束」；掛勾只看不改', async ($, on) => {
  const { time, list } = world(on)
  await start($)
  await run($, '')
  expect(await shown($)).toContain('目前沒有助手在跑')

  // 引擎回什麼，經過 mod 之後就還是什麼
  expect(await $.agent.spawn(SPAWN)).toEqual({ model: 'sonnet', agentId: 'a1' })
  list([REVIEWER])
  await time.advance(190_000)

  const during = await shown($)
  expect(during).toContain('助手（1 個在跑）')
  expect(during).toContain('code-reviewer')
  expect(during).toContain('已跑 3 分 10 秒')

  const finished = await $.turn.complete({
    agentId: 'a1',
    answer: '審完了',
    durationMs: 190_000,
    isAborted: false,
    turnId: 't1',
    reason: 'answer',
  })
  expect(finished).toEqual({ text: '審完了' })
  list([{ ...REVIEWER, status: 'completed' }])

  const after = await shown($)
  expect(after).toContain('目前沒有助手在跑')
  expect(after).toContain('最近結束')
  expect(after).toContain('完成（跑了 3 分 10 秒）')
})

test('助手被中斷時顯示「已停止」，不是「完成」', async ($, on) => {
  const { time, list } = world(on)
  await start($)
  await run($, '')
  await $.agent.spawn(SPAWN)
  list([REVIEWER])
  await time.advance(60_000)

  await $.turn.complete({
    agentId: 'a1',
    answer: '',
    durationMs: 60_000,
    isAborted: true,
    turnId: 't1',
    reason: 'aborted',
  })

  const after = await shown($)
  expect(after).toContain('已停止（跑了 1 分 0 秒）')
  expect(after.some(text => text.startsWith('完成'))).toBe(false)
})

test('在 mod 記到之前就在跑的助手只顯示「在跑」，不亂算已跑多久', async ($, on) => {
  const { time, list } = world(on)
  list([REVIEWER])
  await start($)
  await run($, '')
  await time.advance(30_000)

  const texts = await shown($)
  expect(texts).toContain('助手（1 個在跑）')
  expect(texts).toContain('在跑')
  expect(texts.some(text => text.startsWith('已跑'))).toBe(false)
})

test('額度快用完時那一行變紅，沒快用完的不變色', async ($, on) => {
  world(on, { fiveHour: 93 })
  await start($)

  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: '93%' }))?.props.color).toBe('error')
  const calm = await ui.find({ type: 'Text', text: '41%' })
  expect(calm).toBeDefined()
  expect(calm?.props.color).toBeUndefined()
  await ui.unmount()
})

test('面板開著才每幾秒問一次助手清單，被關掉之後就不問', { plugins: [CLOSER] }, async ($, on) => {
  const { time, listCalls } = world(on)
  await start($)
  await time.settle()

  const whileClosed = listCalls()
  await time.advance(20_000)
  expect(listCalls()).toBe(whileClosed)

  await run($, '')
  const whileOpen = listCalls()
  await time.advance(10_000)
  expect(listCalls()).toBe(whileOpen + 2)

  await closeIt($)
  const afterClose = listCalls()
  await time.advance(20_000)
  expect(listCalls()).toBe(afterClose)
})

test('預設不自己打開；開過之後重新載入會開回來；被關掉之後就不再自己開', { plugins: [CLOSER] }, async ($, on) => {
  const { time, opens } = world(on)
  await start($)
  await time.settle()
  expect(opens()).toBe(0)

  expect((await run($, '')).text).toBe('已打開總覽面板。')
  expect(opens()).toBe(1)
  await start($)
  await time.settle()
  expect(opens()).toBe(2)

  await closeIt($)
  await start($)
  await time.settle()
  expect(opens()).toBe(2)
})

test('/overview off 關掉面板，之後重新載入不會自己開', async ($, on) => {
  const { time, opens } = world(on)
  await start($)
  await run($, '')
  expect(await panel($, 'status', 'tu1')).toMatchObject({ isOpen: true })

  expect((await run($, 'off')).text).toContain('已關掉')
  expect(await panel($, 'status', 'tu2')).toMatchObject({ isOpen: false })

  const before = opens()
  await start($)
  await time.settle()
  expect(opens()).toBe(before)
})

test('Claude 可以自己開、關面板，並拿到有沒有開成功', async ($, on) => {
  const { time, opens } = world(on)
  await start($)
  await time.settle()
  const before = opens()

  expect(await panel($, 'status', 'tu1')).toMatchObject({ isOpen: false, percent: 18, running: 0 })
  expect(await panel($, 'open', 'tu2')).toMatchObject({ isPlaced: true, isOpen: true })
  expect(opens()).toBe(before + 1)
  expect(await panel($, 'close', 'tu3')).toMatchObject({ isOpen: false })
})

test('/clear 之後舊的對話空間和花費不留在面板上，額度留著', async ($, on) => {
  world(on)
  await start($)
  const before = await shown($)
  expect(before).toContain('18%')
  expect(before).toContain('US$ 4.20')
  expect(before).toContain('5 小時額度')

  await $.session.end({ reason: 'clear', sessionId: 's1', resume: { id: 's1' } })
  const after = await shown($)
  expect(after).toContain('對話空間')
  expect(after).toContain('—')
  expect(after).not.toContain('18%')
  expect(after).not.toContain('US$ 4.20')
  expect(after).toContain('5 小時額度')
})

for (const how of ['denied', 'ignored'] as const) {
  test(`面板沒真的被關掉（${how}）就不算「不想看」，重新載入照樣開回來`, { plugins: [CLOSER] }, async ($, on) => {
    const { time, opens, isOpen, closeAttempts } = world(on)
    await start($)
    await run($, '')
    closeAttempts(how)
    await closeIt($)
    expect(isOpen()).toBe(true)

    const before = opens()
    await start($)
    await time.settle()
    expect(opens()).toBe(before + 1)
  })
}

test('介面不放面板時照實說：指令、Claude 的開關、重新載入的提醒都帶原因', async ($, on) => {
  const { time, toasts } = world(on, { isPlaced: false })
  await start($)

  expect((await run($, '')).text).toBe(`總覽面板還沒顯示：${REFUSED}`)
  expect(await panel($, 'open', 'tu1')).toEqual({
    action: 'open',
    isPlaced: false,
    isOpen: true,
    reason: REFUSED,
  })

  await start($)
  await time.settle()
  expect(toasts().at(-1)).toBe(`總覽面板還沒顯示，打 /overview 可以直接打開。（${REFUSED}）`)
})

test('/clear 剛好撞上正在更新清單時，舊的助手不會復活賴著不走', async ($, on) => {
  const { time, list, whileListing } = world(on)
  await start($)
  await run($, '')
  await $.agent.spawn(SPAWN)
  list([REVIEWER])
  await time.advance(5_000)
  expect(await shown($)).toContain('助手（1 個在跑）')

  // 下一次更新：引擎先交出 /clear 之前的清單，/clear 在這份清單回到 mod 之前發生
  whileListing(async () => {
    list([])
    await $.session.end({ reason: 'clear', sessionId: 's1', resume: { id: 's1' } })
  })
  await time.advance(5_000)
  await time.advance(10_000)
  expect(await shown($)).toContain('目前沒有助手在跑')
})

test('/clear 之後引擎還列著的助手會回來，但只顯示「在跑」', async ($, on) => {
  const { time, list } = world(on)
  await start($)
  await run($, '')
  await $.agent.spawn(SPAWN)
  list([REVIEWER])
  await time.advance(60_000)
  expect((await shown($)).some(text => text.startsWith('已跑'))).toBe(true)

  await $.session.end({ reason: 'clear', sessionId: 's1', resume: { id: 's1' } })
  await time.advance(5_000)
  const after = await shown($)
  expect(after).toContain('助手（1 個在跑）')
  expect(after).toContain('在跑')
  expect(after.some(text => text.startsWith('已跑'))).toBe(false)
})

test('純計算：時間寫法、還沒對過時間不印倒數、數字寫法、回合結束原因對應的狀態', () => {
  expect(span(40_000)).toBe('40 秒')
  expect(span(192_000)).toBe('3 分 12 秒')
  expect(span(8_100_000)).toBe('2 小時 15 分')
  expect(span(273_600_000)).toBe('3 天 4 小時')

  const limit = { kind: 'five_hour', percentUsed: 23, resetsAt: T0 + 8_100_000 }
  expect(resetText(limit, T0)).toBe('2 小時 15 分後重置')
  expect(resetText(limit, 0)).toBe('')
  expect(resetText({ ...limit, resetsAt: null }, T0)).toBe('')

  expect(short(999_499)).toBe('999k')
  expect(short(999_500)).toBe('1M')

  expect(statusOf('answer')).toBe('completed')
  expect(statusOf('aborted')).toBe('killed')
  expect(statusOf('error')).toBe('failed')
})

test('助手清單：只沿用自己記到的開始時間、結束時間只記一次、結束的只留三個', () => {
  // 沒經過 mod 的掛勾就在跑的：不拿「第一次看到的時間」充數
  const unseen = mergeAgents([], [REVIEWER], 1_000)
  expect(unseen[0]).toMatchObject({ startedAt: null, endedAt: null, status: 'running' })

  // 掛勾記到開始時間的：之後併清單時沿用
  const seen = started([], { id: 'a1', label: 'code-reviewer', task: '審查這次改動' }, 1_000)
  const merged = mergeAgents(seen, [REVIEWER], 30_000)
  expect(merged[0]).toMatchObject({ startedAt: 1_000, endedAt: null, status: 'running' })

  const finished = mergeAgents(merged, [{ ...REVIEWER, status: 'completed' }], 61_000)
  expect(finished[0]).toMatchObject({ startedAt: 1_000, endedAt: 61_000, status: 'completed' })

  const later = mergeAgents(finished, [{ ...REVIEWER, status: 'completed' }], 99_000)
  expect(later[0]).toMatchObject({ startedAt: 1_000, endedAt: 61_000 })

  // 第一次看到就已經結束的：開始和結束時間都不知道，不亂猜
  const unknown = mergeAgents([], [{ ...REVIEWER, status: 'completed' }], 5_000)
  expect(unknown[0]).toMatchObject({ startedAt: null, endedAt: null, status: 'completed' })

  // 清單裡已經沒有的：掛勾記到開始時間的留著，沒有開始時間又在跑的丟掉
  expect(mergeAgents(seen, [], 2_000)).toHaveLength(1)
  expect(mergeAgents(unseen, [], 2_000)).toHaveLength(0)

  const many = ['a', 'b', 'c', 'd', 'e'].map(id => ({ ...REVIEWER, id, status: 'completed' }))
  expect(mergeAgents([], many, 5_000)).toHaveLength(3)
})
