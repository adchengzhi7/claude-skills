export type Reading = {
  tokens: number | null
  window: number
  percent: number | null
}

export type DetailRow = {
  name: string
  tokens: number
  kind: 'used' | 'free' | 'buffer' | 'deferred'
}

export type Detail = {
  rows: DetailRow[]
  total: number
  max: number
  compactAt: number | null
}

export type Limit = { kind: string; percentUsed: number }

declare module 'claude-code' {
  interface PluginState {
    'context-weather': {
      reading: Reading | null
      history: number[]
      alerted: number
      isHidden: boolean
      detail: Detail | null
      limits: Limit[]
      // 自動整理的門檻；at 是 null 表示 Claude Code 沒給（例如關掉自動整理）
      compact: { window: number; at: number | null } | null
    }
  }
}
