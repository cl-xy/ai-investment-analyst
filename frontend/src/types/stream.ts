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

export interface StreamEvent {
  run_id: string
  seq: number
  type: EventType
  timestamp: string
  node: string | null
  tool: string | null
  payload: Record<string, unknown>
}

export interface ToolResultPayload {
  tool_name: string
  success: boolean
  cached: boolean
  duration_ms: number
  source_id: string
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
  sec_notes: string
  news_summary?: string
}
