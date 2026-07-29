/**
 * Stream event types matching the backend domain event schema.
 */

export type EventType =
  | 'run_started'
  | 'node_started'
  | 'node_completed'
  | 'tool_call'
  | 'tool_result'
  | 'llm_token'
  | 'citation'
  | 'warning'
  | 'error'
  | 'analysis_complete'
  | 'run_completed'
  | 'heartbeat'
  // Adversarial debate events
  | 'debate_started'
  | 'debate_turn'
  | 'debate_verdict'
  // Auto sector-peer comparison
  | 'peer_comparison_ready'

export interface StreamEvent {
  run_id: string
  seq: number
  type: EventType
  timestamp: string
  node: string | null
  tool: string | null
  payload: Record<string, unknown>
  correlation_id: string | null
}

export interface ToolResultPayload {
  tool_name: string
  success: boolean
  cached: boolean
  duration_ms: number
  source_id: string
  no_data?: boolean
}

export interface AnalysisCompletePayload {
  ticker: string
  analysis: AnalysisOutput
}

export interface RunCompletedPayload {
  tickers: string[]
  total_duration_ms: number
  total_tokens: number
  cost_usd: number
}

export interface Citation {
  source_id: string
  claim: string
  provider: string
}

export interface AnalysisOutput {
  ticker: string
  signal: 'buy' | 'hold' | 'sell' | 'insufficient_data'
  confidence: 'high' | 'medium' | 'low'
  sentiment_score: number
  thesis?: string
  bull_case?: string[]
  bear_case?: string[]
  risk_flags: string[]
  citations?: Citation[]
  data_gaps?: string[]
  price_data: Record<string, unknown>
  fundamentals: Record<string, unknown>
  earnings?: {
    next_earnings_date?: string
    days_until_earnings?: number
    eps_estimate?: number | null
  }
  sec_notes: string
  news_summary?: string
}

// Debate-specific payload types

export interface DebateStartedPayload {
  ticker: string
  agents: string[]
}

export interface DebateTurnPayload {
  ticker: string
  role: 'bull' | 'bear' | 'moderator'
  thesis: string
  confidence: 'high' | 'medium' | 'low'
  key_arguments: string[]
  turn_index: number
  duration_ms: number
}

export interface DebateVerdictPayload {
  ticker: string
  signal: 'buy' | 'hold' | 'sell' | 'insufficient_data'
  confidence: 'high' | 'medium' | 'low'
  verdict_rationale: string
  key_disagreements: string[]
  duration_ms: number
}

// Auto sector-peer comparison payload

export interface PeerSnapshot {
  ticker: string
  source: 'cached_analysis' | 'fundamentals_only'
  signal?: string | null
  confidence?: string | null
  current_price?: number | null
  pe_ratio?: number | null
  revenue_growth_yoy?: number | null
  profit_margin?: number | null
}

export interface PeerComparisonPayload {
  primary: string
  sector: string
  peers: PeerSnapshot[]
}
