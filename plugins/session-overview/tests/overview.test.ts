import { expect, mock, test } from 'claude-code/testing'
import type { Engine, Plugin } from 'claude-code/testing'
import type { AgentInfo, On } from 'claude-code'

import { mergeAgents, span } from '../hooks/overview'

const T0 = 1_800_000_000_000
const WINDOW = 200_000

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
  description: '審查 POS 改動',
  type: 'code-reviewer',
  status: 'running',
}

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

// 站在引擎的位置回答 mod 會問的事
const world = (on: On, fiveHour = 23) => {
  const time = mock.clock(on, { now: T0 })
  let listed: readonly AgentInfo[] = []
  let panes: readonly string[] = []
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
  on('agent.list', () => {
    listCalls += 1

    return { value: [...listed] }
  })
  on('ui.open', (_, e) => {
    opens += 1
    panes = [...panes.filter(id => id !== e.id), e.id]

    return { value: { isPlaced: true } }
  })
  on('ui.close', (_, e) => {
    panes = panes.filter(id => id !== e.id)

    return { value: undefined }
  })
  on('ui.panes', () => ({
    value: panes.map(id => ({ id, title: id, isShown: true, isFocused: false, isPlaced: true })),
  }))
  on('ui.log', () => ({ value: undefined }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.measure', (_, e) => ({ changed: e.changed }))
  on('agent.spawn', () => ({ model: 'sonnet', agentId: 'a1' }))
  on('turn.complete', (_, e) => ({ text: e.answer }))

  return {
    time,
    list: (next: readonly AgentInfo[]) => {
      listed = next
    },
    listCalls: () => listCalls,
    opens: () => opens,
  }
}

const start = ($: Engine) => $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })

const openPane = ($: Engine) =>
  $.command.run({
    command: 'overview',
    args: '',
    origin: { kind: 'composer' },
    presentation: { isFullscreen: true, columns: 160 },
  })

const closeIt = ($: Engine) =>
  $.session.measure({
    context: { tokens: 36_000, window: WINDOW, percent: 18 },
    rateLimits: [],
    changed: ['context'],
  })

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

test('助手開始後顯示已跑多久，結束後移到「最近結束」', async ($, on) => {
  const { time, list } = world(on)
  await start($)
  await openPane($)
  expect(await shown($)).toContain('目前沒有助手在跑')

  await $.agent.spawn({
    tool_use_id: 'tu1',
    prompt: '審查這批改動',
    description: '審查 POS 改動',
    subagentType: 'code-reviewer',
    provider: { plugin: 'engine', tier: 'core' },
    parentModel: 'opus',
    background: false,
    fork: false,
  })
  list([REVIEWER])
  await time.advance(190_000)

  const during = await shown($)
  expect(during).toContain('助手（1 個在跑）')
  expect(during).toContain('code-reviewer')
  expect(during).toContain('已跑 3 分 10 秒')

  await $.turn.complete({
    agentId: 'a1',
    answer: '審完了',
    durationMs: 190_000,
    isAborted: false,
    turnId: 't1',
    reason: 'answer',
  })
  list([{ ...REVIEWER, status: 'completed' }])

  const after = await shown($)
  expect(after).toContain('目前沒有助手在跑')
  expect(after).toContain('最近結束')
  expect(after).toContain('完成（跑了 3 分 10 秒）')
})

test('額度快用完時那一行變紅，沒快用完的不變色', async ($, on) => {
  world(on, 93)
  await start($)

  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: '93%' }))?.props.color).toBe('error')
  expect((await ui.find({ type: 'Text', text: '41%' }))?.props.color).toBeUndefined()
  await ui.unmount()
})

test('面板開著才每幾秒問一次助手清單，被關掉之後就不問', { plugins: [CLOSER] }, async ($, on) => {
  const { time, listCalls } = world(on)
  await start($)
  await time.settle()

  const whileClosed = listCalls()
  await time.advance(20_000)
  expect(listCalls()).toBe(whileClosed)

  await openPane($)
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

  await openPane($)
  expect(opens()).toBe(1)
  await start($)
  await time.settle()
  expect(opens()).toBe(2)

  await closeIt($)
  await start($)
  await time.settle()
  expect(opens()).toBe(2)
})

test('Claude 可以自己開、關面板，並拿到有沒有開成功', async ($, on) => {
  const { time, opens } = world(on)
  await start($)
  await time.settle()
  const before = opens()

  const status = await $.tool.call({ tool: 'mcp__session-overview__panel', tool_use_id: 'tu1', action: 'status' })
  expect(JSON.parse(String(status.result))).toMatchObject({ isOpen: false, percent: 18, running: 0 })

  const opened = await $.tool.call({ tool: 'mcp__session-overview__panel', tool_use_id: 'tu2', action: 'open' })
  expect(JSON.parse(String(opened.result))).toMatchObject({ isPlaced: true, isOpen: true })
  expect(opens()).toBe(before + 1)

  const closed = await $.tool.call({ tool: 'mcp__session-overview__panel', tool_use_id: 'tu3', action: 'close' })
  expect(JSON.parse(String(closed.result))).toMatchObject({ isOpen: false })
})

test('時間長度的寫法', () => {
  expect(span(40_000)).toBe('40 秒')
  expect(span(192_000)).toBe('3 分 12 秒')
  expect(span(8_100_000)).toBe('2 小時 15 分')
  expect(span(273_600_000)).toBe('3 天 4 小時')
})

test('助手清單：開始時間沿用、結束時間只記一次、裝上之前的不亂猜、結束的只留三個', () => {
  const first = mergeAgents([], [REVIEWER], 1_000)
  expect(first[0]).toMatchObject({ startedAt: 1_000, endedAt: null, status: 'running' })

  const finished = mergeAgents(first, [{ ...REVIEWER, status: 'completed' }], 61_000)
  expect(finished[0]).toMatchObject({ startedAt: 1_000, endedAt: 61_000, status: 'completed' })

  const later = mergeAgents(finished, [{ ...REVIEWER, status: 'completed' }], 99_000)
  expect(later[0]).toMatchObject({ startedAt: 1_000, endedAt: 61_000 })

  const unknown = mergeAgents([], [{ ...REVIEWER, status: 'completed' }], 5_000)
  expect(unknown[0]).toMatchObject({ startedAt: null, endedAt: null })

  const many = ['a', 'b', 'c', 'd', 'e'].map(id => ({ ...REVIEWER, id, status: 'completed' }))
  expect(mergeAgents([], many, 5_000)).toHaveLength(3)
})
