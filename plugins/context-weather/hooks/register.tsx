import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, SessionContextUsage, UiOpenResult } from 'claude-code'

import type { Detail } from '../types'
import { alertStep, bar, labelOf, levelOf, limitLabel, pushReading, short, turnsLeft } from './weather'

const PANE = 'context-weather'
const HOW_BACK = '打 /context-weather 可以叫回來'

const reading = atom({ plugin: 'context-weather', key: 'reading' } as const, null)
const history = atom({ plugin: 'context-weather', key: 'history' } as const, [])
const alerted = atom({ plugin: 'context-weather', key: 'alerted' } as const, 0)
const isHidden = atom({ plugin: 'context-weather', key: 'isHidden' } as const, false)
const detail = atom({ plugin: 'context-weather', key: 'detail' } as const, null)
const limits = atom({ plugin: 'context-weather', key: 'limits' } as const, [])
const compact = atom({ plugin: 'context-weather', key: 'compact' } as const, null)

const finite = (value: number | undefined): number | null =>
  value !== undefined && Number.isFinite(value) ? value : null

const refreshDetail = async ($: EngineInterface): Promise<void> => {
  const usage = await $.session.usage({ breakdown: 'summary' })
  const breakdown = usage.context.breakdown

  if (breakdown === undefined) {
    return
  }

  const next: Detail = {
    rows: breakdown.categories.map(row => ({
      name: row.name,
      tokens: row.tokens,
      kind: row.kind,
    })),
    total: breakdown.totalTokens,
    max: breakdown.rawMaxTokens,
    compactAt: breakdown.autoCompactThreshold ?? null,
  }
  await update($, detail, () => next)
  await update($, compact, () => ({ window: usage.context.window, at: next.compactAt }))
}

// 自動整理的門檻（本地估算，不發請求）：載入時問一次，之後視窗大小變了才再問。
// 問不到就當沒有，預估改算到視窗上限
const learnCompact = async ($: EngineInterface, window: number, isFresh: boolean): Promise<void> => {
  const known = await read($, compact)

  if (!isFresh && known !== null && known.window === window) {
    return
  }

  try {
    const found = (await $.session.usage({ breakdown: 'summary' })).context.breakdown

    // 這次沒拿到明細就不記，下次量測再問；記成「沒有門檻」會讓整個 session 都不再問
    if (found === undefined) {
      return
    }

    await update($, compact, () => ({ window, at: found.autoCompactThreshold ?? null }))
  } catch (error: unknown) {
    $.ui.log(`context-weather: 讀不到自動整理門檻：${String(error)}`, { to: 'debug' })
  }
}

const record = async (
  $: EngineInterface,
  context: SessionContextUsage,
  isFresh = false,
): Promise<void> => {
  const tokens = finite(context.tokens)
  const percent = finite(context.percent)
  await update($, reading, () => ({ tokens, window: context.window, percent }))
  await update($, history, list => pushReading(list, tokens))
  await learnCompact($, context.window, isFresh)
}

// 只在「變更糟」的那一刻提醒一次；明顯降回去（整理過）才重新武裝
const warn = async ($: EngineInterface, percent: number): Promise<void> => {
  const before = await read($, alerted)
  const step = alertStep(before, percent)

  if (step.alerted !== before) {
    await update($, alerted, () => step.alerted)
  }

  if (step.isNew) {
    const level = levelOf(percent)
    $.ui.toast(`對話空間用到 ${percent}%（${level.name}）：${level.advice}`, {
      timeoutMs: 8000,
    })
  }
}

const openDetail = async ($: EngineInterface): Promise<UiOpenResult> => {
  const opened = await $.ui.open({ id: PANE, title: '對話空間明細', columns: 60 })
  await refreshDetail($)

  return opened
}

// 按鈕沒有地方回話，放不下就用提醒講
const showDetail = async ($: EngineInterface): Promise<void> => {
  const opened = await openDetail($)

  if (!opened.isPlaced) {
    $.ui.toast(`明細還沒顯示：${opened.reason}`)
  }
}

const hide = async ($: EngineInterface): Promise<void> => {
  await update($, isHidden, () => true)
  $.ui.toast(`已收起。${HOW_BACK}`)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'context-weather',
      description: '對話空間用量：打開明細（加 off 收起上方那一列）',
      argumentHint: '[off]',
      immediate: true,
    })
    const usage = await $.session.usage()
    await record($, usage.context, true)
    await update($, limits, () =>
      usage.rateLimits.map(one => ({ kind: one.kind, percentUsed: one.percentUsed })),
    )

    return next(e)
  })

  on('session.measure', async ($, e, next) => {
    await record($, e.context)
    await update($, limits, () =>
      e.rateLimits.map(one => ({ kind: one.kind, percentUsed: one.percentUsed })),
    )

    const percent = finite(e.context.percent)

    if (percent !== null) {
      await warn($, percent)
    }

    if ((await $.ui.panes()).some(pane => pane.id === PANE)) {
      await refreshDetail($)
    }

    return next(e)
  })

  // /clear 或換到另一段對話之後舊數字不再成立，等第一次回應再顯示
  on('session.end', async ($, e, next) => {
    if (e.reason === 'clear' || e.reason === 'resume') {
      await update($, reading, () => null)
      await update($, history, () => [])
      await update($, detail, () => null)
      await update($, alerted, () => 0)
    }

    return next(e)
  })

  on('command.run', { command: 'context-weather' }, async ($, e) => {
    if (e.args.trim() === 'off') {
      await update($, isHidden, () => true)
      await $.ui.close({ id: PANE })

      return { text: `已收起對話空間那一列。${HOW_BACK}` }
    }

    await update($, isHidden, () => false)
    const opened = await openDetail($)

    return { text: opened.isPlaced ? '已打開對話空間明細。' : `明細還沒顯示：${opened.reason}` }
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const now = await read($, reading)

    if (e.props.hasSurvey || now === null || (await read($, isHidden))) {
      return next(e)
    }

    const { Box, Button, Text } = $.ui.resolve(e)

    if (now.percent === null) {
      return (
        <Box>
          <Text dimColor>{'對話空間  等下一次回應後才有讀數  '}</Text>
          <Button key="hide" label="收起" dimColor onPress={() => hide($)} />
        </Box>
      )
    }

    const columns = e.props.bodyColumns
    const level = levelOf(now.percent)
    const tint = level.color === null ? {} : { color: level.color }
    const width = columns >= 120 ? 20 : columns >= 80 ? 10 : 0
    const ceiling = (await read($, compact))?.at ?? now.window
    const left = turnsLeft(await read($, history), ceiling)
    const forecast =
      left === null ? '' : `，照最近的速度約還能 ${left > 99 ? '99+' : left} 回合`

    return (
      <Box>
        <Text dimColor>{'對話空間 '}</Text>
        <Text bold {...tint}>
          {level.name}
        </Text>
        {width > 0 && <Text {...tint}>{` ${bar(now.percent, width)}`}</Text>}
        <Text bold>{` ${now.percent}%`}</Text>
        {now.tokens !== null && (
          <Text dimColor>{`  ${short(now.tokens)} / ${short(now.window)}`}</Text>
        )}
        {columns >= 100 && (
          <Text dimColor wrap="truncate-end">
            {`  ${level.advice}${forecast}`}
          </Text>
        )}
        <Text>{'  '}</Text>
        <Button key="detail" label="明細" onPress={() => showDetail($)} />
        <Text> </Text>
        <Button key="hide" label="收起" dimColor onPress={() => hide($)} />
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const now = await read($, detail)

    if (now === null) {
      return (
        <Box>
          <Text dimColor>計算中… 沒出來的話再打一次 /context-weather</Text>
        </Box>
      )
    }

    const used = now.rows
      .filter(row => row.kind === 'used' && row.tokens > 0)
      .toSorted((a, b) => b.tokens - a.tokens)
    const rest = now.rows.filter(row => row.kind !== 'used' && row.tokens > 0)
    const top = used[0]?.tokens ?? 1
    const room = Math.max(4, Math.min(24, e.props.bodyColumns - 38))
    const share = (now.total / now.max) * 100
    const percent = Number.isFinite(share) ? Math.round(share) : 0
    const level = levelOf(percent)
    const quota = (await read($, limits))
      .map(one => `${limitLabel(one.kind)} ${one.percentUsed}%`)
      .join('　')

    return (
      <Box flexDirection="column">
        <Text bold {...(level.color === null ? {} : { color: level.color })}>
          {`${level.name}　已用 ${short(now.total)} / ${short(now.max)}（${percent}%）`}
        </Text>
        <Text dimColor>{level.advice}</Text>
        <Text> </Text>
        <Text dimColor>佔空間的東西（由大到小，估算值）</Text>
        {used.map(row => (
          <Box>
            <Box width={28}>
              <Text>{labelOf(row)}</Text>
            </Box>
            <Box width={7}>
              <Text>{short(row.tokens)}</Text>
            </Box>
            <Text dimColor>
              {'█'.repeat(Math.max(1, Math.round((row.tokens / top) * room)))}
            </Text>
          </Box>
        ))}
        <Text> </Text>
        {rest.map(row => (
          <Box>
            <Box width={28}>
              <Text dimColor>{labelOf(row)}</Text>
            </Box>
            <Text dimColor>{short(row.tokens)}</Text>
          </Box>
        ))}
        {now.compactAt !== null && (
          <Text dimColor>{`用到 ${short(now.compactAt)} 時會自動整理對話`}</Text>
        )}
        {quota !== '' && <Text dimColor>{`額度：${quota}`}</Text>}
      </Box>
    )
  })
}
