import { atom, read, update } from 'claude-code'
import type {
  EngineInterface,
  Register,
  SessionContextUsage,
  SessionCost,
  SessionRateLimit,
  UiOpenResult,
} from 'claude-code'

import {
  bar,
  ended,
  limitLabel,
  mergeAgents,
  resetText,
  short,
  span,
  started,
  statusLabel,
  tintOf,
  toLimit,
} from './overview'

const PANE = 'session-overview'
const TOOL = 'mcp__session-overview__panel'
const TICK_MS = 5000
const BAR = 14

const usage = atom({ plugin: 'session-overview', key: 'usage' } as const, null)
const agents = atom({ plugin: 'session-overview', key: 'agents' } as const, [])
const clock = atom({ plugin: 'session-overview', key: 'now' } as const, 0)
const wanted = atom({ plugin: 'session-overview', key: 'isWanted' } as const, false)

const recordUsage = async (
  $: EngineInterface,
  context: SessionContextUsage,
  rateLimits: readonly SessionRateLimit[],
  cost: SessionCost | undefined,
): Promise<void> => {
  await update($, usage, () => ({
    tokens: context.tokens ?? null,
    window: context.window,
    percent: context.percent ?? null,
    costUsd: cost?.usd ?? null,
    limits: rateLimits.map(toLimit),
  }))
}

const syncAgents = async ($: EngineInterface): Promise<void> => {
  const listed = await $.agent.list()
  const now = await $.clock.now()
  await update($, agents, known => mergeAgents(known, listed, now))
  await update($, clock, () => now)
}

const openPane = ($: EngineInterface): Promise<UiOpenResult> =>
  $.ui.open({ id: PANE, title: '總覽', columns: 60 })

const isOpen = async ($: EngineInterface): Promise<boolean> =>
  (await $.ui.panes()).some(pane => pane.id === PANE)

// 面板關著就不做事；開著才每幾秒對一次助手清單、把「已跑多久」往前推
const tick = async ($: EngineInterface): Promise<void> => {
  if (await isOpen($)) {
    await syncAgents($)
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'overview',
      description: '總覽面板：對話空間、花費、額度、正在跑的助手（加 off 關掉）',
      argumentHint: '[off]',
      // 回合進行中也能打：最想看「助手是不是卡住」的時候就是回合跑到一半
      immediate: true,
    })
    // 讓 Claude 自己能開關面板、回報有沒有開成功（人說「打開」時不用自己打指令）
    await $.tool.register({
      name: 'panel',
      description:
        'Opens, closes or reports the overview pane (總覽面板: context, cost, rate limits, running agents). Call with action "open" when the user asks to open it, "close" to close it, "status" to check. Returns whether the pane is open.',
      inputSchema: {
        type: 'object',
        properties: { action: { type: 'string', enum: ['open', 'close', 'status'] } },
        required: ['action'],
      },
    })
    // 計時器先起來：下面的讀取就算失敗，面板之後還是會自己更新
    $.clock.every(TICK_MS, () => {
      tick($).catch((error: unknown) => {
        $.ui.log(`session-overview: 更新面板失敗：${String(error)}`, { to: 'debug' })
      })
    })
    const now = await $.session.usage()
    await recordUsage($, now.context, now.rateLimits, now.cost)
    await syncAgents($)

    // 預設不自己打開；這個 session 開過（還沒被關掉）的話，重新載入時開回來。
    // 不等它畫完，免得卡住 session 開場；視窗太窄放不下就講一聲
    if (await read($, wanted)) {
      openPane($)
        .then(opened => {
          if (!opened.isPlaced) {
            $.ui.toast(`總覽面板放不下，打 /overview 可以直接打開。（${opened.reason}）`, {
              timeoutMs: 8000,
            })
          }
        })
        .catch((error: unknown) => {
          $.ui.log(`session-overview: 打開面板失敗：${String(error)}`, { to: 'debug' })
        })
    }

    return next(e)
  })

  // 面板被關掉＝不想看，之後重新載入不要再自己跳出來；重新載入本身造成的關閉（unload）不算。
  // 等真的關成功才記，免得別人擋下這次關閉、面板還開著卻被記成不想看
  on('ui.close', async ($, e, next) => {
    const result = await next(e)

    if (e.id === PANE && e.origin.kind !== 'unload') {
      await update($, wanted, () => false)
    }

    return result
  })

  // /clear 或換到另一段對話之後，舊的用量和助手清單不再成立
  on('session.end', async ($, e, next) => {
    if (e.reason === 'clear' || e.reason === 'resume') {
      await update($, usage, () => null)
      await update($, agents, () => [])
    }

    return next(e)
  })

  on('session.measure', async ($, e, next) => {
    await recordUsage($, e.context, e.rateLimits, e.cost)

    return next(e)
  })

  // 助手一開始就記下時間，面板關著也記，之後打開才算得出「已跑多久」
  on('agent.spawn', async ($, e, next) => {
    const result = await next(e)

    if (result.agentId !== undefined) {
      const agent = { id: result.agentId, label: e.subagentType, task: e.description }
      const now = await $.clock.now()
      await update($, agents, known => started(known, agent, now))
    }

    return result
  })

  on('turn.complete', async ($, e, next) => {
    const id = e.agentId

    if (id !== undefined) {
      const now = await $.clock.now()
      await update($, agents, known => ended(known, id, now, e.reason))
      await update($, clock, () => now)
    }

    return next(e)
  })

  on('tool.call', { tool: TOOL }, async ($, e) => {
    const action = 'action' in e ? String(e.action) : 'status'

    if (action === 'open') {
      await update($, wanted, () => true)
      const opened = await openPane($)
      await syncAgents($)

      return {
        result: JSON.stringify({
          action,
          isPlaced: opened.isPlaced,
          isOpen: await isOpen($),
          ...(opened.isPlaced ? {} : { reason: opened.reason }),
        }),
      }
    }

    if (action === 'close') {
      await update($, wanted, () => false)
      await $.ui.close({ id: PANE })
    }

    const use = await read($, usage)
    const running = (await read($, agents)).filter(one => one.status === 'running').length

    return {
      result: JSON.stringify({ action, isOpen: await isOpen($), percent: use?.percent ?? null, running }),
    }
  })

  on('command.run', { command: 'overview' }, async ($, e) => {
    if (e.args.trim() === 'off') {
      await update($, wanted, () => false)
      await $.ui.close({ id: PANE })

      return { text: '已關掉總覽面板。再打 /overview 會回來。' }
    }

    await update($, wanted, () => true)
    const opened = await openPane($)
    await syncAgents($)

    return { text: opened.isPlaced ? '已打開總覽面板。' : `總覽面板放不下：${opened.reason}` }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const use = await read($, usage)
    const team = await read($, agents)
    const now = await read($, clock)
    const running = team.filter(one => one.status === 'running')
    const done = team.filter(one => one.status !== 'running')

    const line = (label: string, value: string, percent: number | null, note: string) => (
      <Box>
        <Box width={12}>
          <Text dimColor>{label}</Text>
        </Box>
        <Box width={11}>
          <Text bold {...(percent === null ? {} : tintOf(percent))}>
            {value}
          </Text>
        </Box>
        {percent !== null && <Text {...tintOf(percent)}>{`${bar(percent, BAR)}  `}</Text>}
        <Text dimColor wrap="truncate-end">
          {note}
        </Text>
      </Box>
    )

    return (
      <Box flexDirection="column">
        {use === null && <Text dimColor>等第一次回應後才有讀數</Text>}
        {use !== null &&
          line(
            '對話空間',
            use.percent === null ? '—' : `${use.percent}%`,
            use.percent,
            use.tokens === null ? '' : `${short(use.tokens)} / ${short(use.window)}`,
          )}
        {use !== null && use.costUsd !== null && line('本次花費', `US$ ${use.costUsd.toFixed(2)}`, null, '')}
        {use !== null &&
          use.limits.map(limit =>
            line(limitLabel(limit.kind), `${limit.percentUsed}%`, limit.percentUsed, resetText(limit, now)),
          )}
        <Text> </Text>
        <Text dimColor>
          {running.length === 0 ? '目前沒有助手在跑' : `助手（${running.length} 個在跑）`}
        </Text>
        {running.map(one => (
          <Box>
            <Box width={20}>
              <Text wrap="truncate-end">{one.label}</Text>
            </Box>
            <Text>
              {one.startedAt === null || now <= 0 ? '在跑' : `已跑 ${span(now - one.startedAt)}`}
            </Text>
            <Text dimColor wrap="truncate-end">{`  ${one.task}`}</Text>
          </Box>
        ))}
        {done.length > 0 && <Text dimColor>最近結束</Text>}
        {done.map(one => (
          <Box>
            <Box width={20}>
              <Text dimColor wrap="truncate-end">
                {one.label}
              </Text>
            </Box>
            <Text {...(one.status === 'completed' ? { color: 'success' } : { color: 'warning' })}>
              {statusLabel(one.status) +
                (one.startedAt === null || one.endedAt === null
                  ? ''
                  : `（跑了 ${span(one.endedAt - one.startedAt)}）`)}
            </Text>
          </Box>
        ))}
      </Box>
    )
  })
}
