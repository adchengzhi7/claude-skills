import type { DetailRow } from '../types'

export type Level = {
  from: number
  name: string
  advice: string
  color: string | null
  // 跨進這一級時要不要跳提醒；0 = 不提醒
  alert: number
}

const LEVELS: readonly Level[] = [
  { from: 90, name: '暴雨', advice: '快滿了，先交接再繼續', color: 'error', alert: 90 },
  { from: 75, name: '有雨', advice: '該找段落收尾了', color: 'warning', alert: 75 },
  { from: 60, name: '陰', advice: '用掉一大半了', color: 'warning', alert: 0 },
  { from: 40, name: '多雲', advice: '還夠用', color: null, alert: 0 },
  { from: 0, name: '晴', advice: '空間很夠', color: 'success', alert: 0 },
]

const FAIR: Level = { from: 0, name: '晴', advice: '空間很夠', color: 'success', alert: 0 }

export const levelOf = (percent: number): Level =>
  LEVELS.find(level => percent >= level.from) ?? FAIR

// 降到門檻以下這麼多個百分點，才算真的離開那一級；在門檻邊緣來回不重複提醒
const REARM_GAP = 5

// 會跳提醒的門檻，由高到低
const ALERTS: readonly number[] = LEVELS.map(level => level.alert).filter(alert => alert > 0)

// 回傳新的「已提醒到哪一級」，以及這次要不要跳提醒
export const alertStep = (before: number, percent: number): { alerted: number; isNew: boolean } => {
  const level = levelOf(percent)

  if (level.alert > before) {
    return { alerted: level.alert, isNew: true }
  }

  // 一級一級退：提醒過的級別裡，還沒降到它門檻以下 REARM_GAP 的最高那一級，就算還在那一級
  const held = ALERTS.find(alert => alert <= before && percent > alert - REARM_GAP) ?? 0

  return { alerted: held, isNew: false }
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

// 用量變小（整理過、清空過）就重新起算，否則預估會被舊數字拉歪
export const pushReading = (list: readonly number[], tokens: number | null): number[] => {
  if (tokens === null) {
    return []
  }

  const last = list[list.length - 1]

  if (last === undefined || tokens < last) {
    return [tokens]
  }

  if (tokens === last) {
    return [...list]
  }

  return [...list, tokens].slice(-12)
}

// 照最近幾回合的成長速度，離 ceiling（自動整理門檻，沒有就用視窗上限）還有幾回合；資料不夠就不猜（null）
export const turnsLeft = (list: readonly number[], ceiling: number): number | null => {
  const recent = list.slice(-6)
  const last = recent[recent.length - 1]

  if (recent.length < 3 || last === undefined) {
    return null
  }

  const growth = (last - (recent[0] ?? last)) / (recent.length - 1)

  if (growth <= 0) {
    return null
  }

  return Math.max(0, Math.floor((ceiling - last) / growth))
}

const NAMES: Readonly<Record<string, string>> = {
  'System prompt': '系統提示',
  'System tools': '內建工具說明',
  'MCP tools': '外接工具說明',
  'Custom agents': '自訂助手',
  'Memory files': '記憶與規則檔',
  Skills: '技能清單',
  Messages: '對話內容',
}

export const labelOf = (row: DetailRow): string => {
  if (row.kind === 'free') {
    return '剩餘空間'
  }

  if (row.kind === 'buffer') {
    return '自動整理保留區'
  }

  const name = NAMES[row.name] ?? row.name

  return row.kind === 'deferred' ? `${name}（用到才載入）` : name
}

const LIMITS: Readonly<Record<string, string>> = {
  five_hour: '5 小時額度',
  seven_day: '7 天額度',
  spend_limit: '花費上限',
}

export const limitLabel = (kind: string): string => LIMITS[kind] ?? kind
