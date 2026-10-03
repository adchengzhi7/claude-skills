import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, SessionContextUsage } from 'claude-code'

import type { Detail } from '../types'
import { bar, labelOf, levelOf, limitLabel, pushReading, short, turnsLeft } from './weather'

const PANE = 'context-weather'
const HOW_BACK = '打 /context-weather 可以叫回來'

const reading = atom({ plugin: 'context-weather', key: 'reading' } as const, null)
const history = atom({ plugin: 'context-weather', key: 'history' } as const, [])
const alerted = atom({ plugin: 'context-weather', key: 'alerted' } as const, 0)
const isHidden = atom({ plugin: 'context-weather', key: 'isHidden' } as const, false)
const detail = atom({ plugin: 'context-weather', key: 'detail' } as const, null)
const limits = atom({ plugin: 'context-weather', key: 'limits' } as const, [])

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
}

const record = async ($: EngineInterface, context: SessionContextUsage): Promise<void> => {
  const tokens = context.tokens ?? null
  const percent = context.percent ?? null
  await update($, reading, () => ({ tokens, window: context.window, percent }))
  await update($, history, list => pushReading(list, tokens))
}

// 只在「變更糟」的那一刻提醒一次；降回去（整理過）就重新武裝
const warn = async ($: EngineInterface, percent: number): Promise<void> => {
  const level = levelOf(percent)
  const before = await read($, alerted)

  if (level.alert === before) {
    return
  }

  await update($, alerted, () => level.alert)

  if (level.alert > before) {
    $.ui.toast(`對話空間用到 ${percent}%（${level.name}）：${level.advice}`, {
      timeoutMs: 8000,
    })
  }
}

const openDetail = async ($: EngineInterface): Promise<void> => {
  await $.ui.open({ id: PANE, title: '對話空間明細', columns: 56 })
  await refreshDetail($)
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
    })
    const usage = await $.session.usage()
    await record($, usage.context)
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

    if (e.context.percent !== undefined) {
      await warn($, e.context.percent)
    }

    if ((await $.ui.panes()).some(pane => pane.id === PANE)) {
      await refreshDetail($)
    }

    return next(e)
  })

  // /clear 之後舊數字不再成立，等新對話的第一次回應再顯示
  on('session.end', async ($, e, next) => {
    if (e.reason === 'clear') {
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
    await openDetail($)

    return { text: '已打開對話空間明細。' }
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
    const left = turnsLeft(await read($, history), now.window)
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
        <Button key="detail" label="明細" onPress={() => openDetail($)} />
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
    const room = Math.max(4, Math.min(24, e.props.bodyColumns - 32))
    const percent = now.max > 0 ? Math.round((now.total / now.max) * 100) : 0
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
            <Box width={22}>
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
            <Box width={22}>
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
