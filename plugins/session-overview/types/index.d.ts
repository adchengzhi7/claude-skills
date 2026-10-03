export type OverviewLimit = {
  kind: string
  percentUsed: number
  // 毫秒；引擎沒給重置時間就是 null
  resetsAt: number | null
}

export type OverviewUsage = {
  tokens: number | null
  window: number
  percent: number | null
  costUsd: number | null
  limits: OverviewLimit[]
}

export type OverviewAgent = {
  id: string
  label: string
  task: string
  status: string
  // 毫秒；面板還沒裝之前就開始或結束的助手，時間不知道就是 null
  startedAt: number | null
  endedAt: number | null
}

declare module 'claude-code' {
  interface PluginState {
    'session-overview': {
      usage: OverviewUsage | null
      agents: OverviewAgent[]
      now: number
      // 開過面板是 true，重新載入時開回來；被關掉之後是 false
      isWanted: boolean
    }
  }
}
