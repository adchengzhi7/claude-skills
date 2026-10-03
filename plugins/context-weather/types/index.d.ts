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
    }
  }
}
