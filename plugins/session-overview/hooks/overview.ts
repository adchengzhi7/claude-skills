import type { OverviewAgent, OverviewLimit } from '../types'

const RECENT = 3

export const span = (ms: number): string => {
  const seconds = Math.max(0, Math.floor(ms / 1000))
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)

  if (days > 0) {
    return `${days} 天 ${hours % 24} 小時`
  }

  if (hours > 0) {
    return `${hours} 小時 ${minutes % 60} 分`
  }

  if (minutes > 0) {
    return `${minutes} 分 ${seconds % 60} 秒`
  }

  return `${seconds} 秒`
}

export const bar = (percent: number, width: number): string => {
  const share = Math.min(100, Math.max(0, percent)) / 100
  const filled = percent > 0 ? Math.max(1, Math.round(share * width)) : 0

  return '█'.repeat(filled) + '░'.repeat(width - filled)
}

export const short = (tokens: number): string => {
  // 999.5k 以上四捨五入就是 1000k，直接當 1M 顯示
  if (tokens >= 999_500) {
    return `${(tokens / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`
  }

  if (tokens >= 1_000) {
    return `${Math.round(tokens / 1_000)}k`
  }

  return String(tokens)
}

// 快滿才上色，平常不搶眼
export const tintOf = (percent: number): { color?: string } => {
  if (percent >= 90) {
    return { color: 'error' }
  }

  if (percent >= 75) {
    return { color: 'warning' }
  }

  return {}
}

const LIMITS: Readonly<Record<string, string>> = {
  five_hour: '5 小時額度',
  seven_day: '7 天額度',
  spend_limit: '花費上限',
}

export const limitLabel = (kind: string): string => LIMITS[kind] ?? kind

const STATUS: Readonly<Record<string, string>> = {
  completed: '完成',
  failed: '失敗',
  killed: '已停止',
}

export const statusLabel = (status: string): string => STATUS[status] ?? status

// now 是 0＝還沒對過時間，這時不印倒數（不然會印出「兩萬天後重置」）
export const resetText = (limit: OverviewLimit, now: number): string =>
  now <= 0 || limit.resetsAt === null || limit.resetsAt <= now
    ? ''
    : `${span(limit.resetsAt - now)}後重置`

export const toLimit = (one: { kind: string; percentUsed: number; resetsAt?: string }): OverviewLimit => {
  const at = one.resetsAt === undefined ? Number.NaN : Date.parse(one.resetsAt)

  return { kind: one.kind, percentUsed: one.percentUsed, resetsAt: Number.isNaN(at) ? null : at }
}

type Listed = { id: string; description: string; type: string; status: string; name?: string }

const isRunning = (agent: { status: string }): boolean => agent.status === 'running'

// 在跑的全留（先開始的在上面），結束的只留最近幾個
const trim = (agents: readonly OverviewAgent[]): OverviewAgent[] => {
  const running = agents
    .filter(isRunning)
    .toSorted((a, b) => (a.startedAt ?? 0) - (b.startedAt ?? 0))
  const ended = agents
    .filter(agent => !isRunning(agent))
    .toSorted((a, b) => (b.endedAt ?? 0) - (a.endedAt ?? 0))
    .slice(0, RECENT)

  return [...running, ...ended]
}

// 把引擎給的清單併進我們記得的：開始時間只沿用自己記到的（沒記到就是 null，不拿「第一次看到」充數），
// 剛從「在跑」變成別的就記下結束時間
export const mergeAgents = (
  known: readonly OverviewAgent[],
  listed: readonly Listed[],
  now: number,
): OverviewAgent[] => {
  const before = new Map(known.map(agent => [agent.id, agent]))
  const ids = new Set(listed.map(one => one.id))
  const merged = listed.map(one => {
    const old = before.get(one.id)
    const running = isRunning(one)

    return {
      id: one.id,
      label: one.name ?? one.type,
      task: one.description,
      status: one.status,
      startedAt: old?.startedAt ?? null,
      endedAt: running ? null : (old?.endedAt ?? (old !== undefined && isRunning(old) ? now : null)),
    }
  })

  // 清單裡沒有、我們卻記得的：有開始時間的是掛勾剛記到、清單還沒跟上，留著；
  // 沒有開始時間又在跑的只可能來自舊清單，清單沒有了就丟
  const kept = known.filter(
    agent => !ids.has(agent.id) && !(isRunning(agent) && agent.startedAt === null),
  )

  return trim([...merged, ...kept])
}

export const started = (
  known: readonly OverviewAgent[],
  agent: { id: string; label: string; task: string },
  now: number,
): OverviewAgent[] =>
  trim([
    ...known.filter(one => one.id !== agent.id),
    { ...agent, status: 'running', startedAt: now, endedAt: null },
  ])

// 回合怎麼結束的 → 助手的狀態：正常回答算完成，被中斷算已停止，其餘算失敗
export const statusOf = (reason: string): string => {
  if (reason === 'answer') {
    return 'completed'
  }

  return reason === 'aborted' ? 'killed' : 'failed'
}

export const ended = (
  known: readonly OverviewAgent[],
  id: string,
  now: number,
  reason: string,
): OverviewAgent[] =>
  trim(
    known.map(one =>
      one.id === id && isRunning(one) ? { ...one, status: statusOf(reason), endedAt: now } : one,
    ),
  )
