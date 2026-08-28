import axios from 'axios'
import { API_BASE, authHeaders } from './config'

export type AlertSeverity = 'info' | 'warning' | 'critical'

export interface LlmJudgment {
  changed: boolean
  new_signal: string
  reasoning: string
  key_shifts: string[]
}

export interface TriggeredEvent {
  type: string
  summary: string
  metadata?: Record<string, unknown>
}

export interface ReasoningDiff {
  drift_score?: number
  drift_threshold?: number
  components?: Record<string, number>
  details?: Record<string, unknown>
  triggered_events?: TriggeredEvent[]
  prior_signal?: string
  prior_confidence?: string
  llm_judgment?: LlmJudgment | null
}

export interface AlertItem {
  id: string
  ticker: string
  alert_type: string
  severity: AlertSeverity
  drift_score: number
  old_signal: string | null
  new_signal: string | null
  reasoning_diff: ReasoningDiff
  triggered_by: string[]
  llm_judged: boolean
  dispatched_telegram: boolean
  created_at: string
  acknowledged_at: string | null
}

export interface AlertListResponse {
  alerts: AlertItem[]
  total: number
}

export interface SubscriptionItem {
  ticker: string
  source: 'portfolio' | 'watchlist'
  trigger_types: string[]
  active: boolean
}

export async function getAlerts(params?: {
  limit?: number
  offset?: number
  ticker?: string
}): Promise<AlertListResponse> {
  const response = await axios.get<AlertListResponse>(`${API_BASE}/api/alerts`, {
    headers: authHeaders(),
    params,
  })
  return response.data
}

export async function getUnreadCount(): Promise<number> {
  const response = await axios.get<{ unread_count: number }>(
    `${API_BASE}/api/alerts/unread-count`,
    { headers: authHeaders() }
  )
  return response.data.unread_count
}

export async function acknowledgeAlert(id: string): Promise<AlertItem> {
  const response = await axios.post<AlertItem>(
    `${API_BASE}/api/alerts/${encodeURIComponent(id)}/acknowledge`,
    {},
    { headers: authHeaders() }
  )
  return response.data
}

export async function getSubscriptions(): Promise<SubscriptionItem[]> {
  const response = await axios.get<{ subscriptions: SubscriptionItem[] }>(
    `${API_BASE}/api/alerts/subscriptions`,
    { headers: authHeaders() }
  )
  return response.data.subscriptions
}

export async function subscribeTicker(
  ticker: string,
  triggerTypes?: string[]
): Promise<SubscriptionItem> {
  const response = await axios.post<SubscriptionItem>(
    `${API_BASE}/api/alerts/subscribe`,
    { ticker, trigger_types: triggerTypes },
    { headers: authHeaders() }
  )
  return response.data
}

export async function unsubscribeTicker(ticker: string): Promise<void> {
  await axios.delete(`${API_BASE}/api/alerts/subscribe/${encodeURIComponent(ticker)}`, {
    headers: authHeaders(),
  })
}
