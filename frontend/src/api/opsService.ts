import axios from 'axios'
import { API_BASE, authHeaders } from './config'

export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy'
  components: {
    api: ComponentHealth
    database: ComponentHealth
    llm_provider: ComponentHealth
    mcp_servers: ComponentHealth
  }
  timestamp: string
}

export interface ComponentHealth {
  status: 'up' | 'degraded' | 'down'
  latency_ms?: number
  message?: string
}

export interface SLOData {
  availability: { current: number; target: number; budget_remaining: number }
  p95_latency: { current_ms: number; target_ms: number }
  error_budget: { burned_pct: number; remaining_pct: number; window_days: number }
}

export interface CircuitBreaker {
  name: string
  state: 'closed' | 'open' | 'half-open'
  failure_count: number
  last_state_change: string
  next_retry_at?: string
}

export interface RateLimitStatus {
  openrouter: {
    per_minute: { used: number; limit: number }
    daily: { used: number; limit: number }
  }
}

export interface RecentError {
  id: string
  timestamp: string
  correlation_id: string
  message: string
  stage: string
  ticker?: string
}

export interface LatencyEntry {
  id: string
  ticker: string
  timestamp: string
  total_ms: number
  stages: {
    fetch_data_ms: number
    debate_ms: number
    report_ms: number
  }
}

export interface MetricsData {
  circuit_breakers: CircuitBreaker[]
  rate_limits: RateLimitStatus
  recent_errors: RecentError[]
  latency_history: LatencyEntry[]
}

export interface ChaosScenario {
  id: string
  label: string
  description: string
  enabled: boolean
}

export interface ChaosState {
  active: boolean
  scenarios: ChaosScenario[]
}

// Wire format from backend (scenarios is a keyed object, not an array)
interface ChaosWireScenario {
  enabled: boolean
  activated_at: string | null
  description: string
}

interface ChaosWireState {
  scenarios: Record<string, ChaosWireScenario>
  any_active: boolean
}

function humanizeScenarioId(id: string): string {
  return id
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

function parseChaosResponse(wire: ChaosWireState): ChaosState {
  const scenarios: ChaosScenario[] = Object.entries(wire.scenarios).map(([id, s]) => ({
    id,
    label: humanizeScenarioId(id),
    description: s.description,
    enabled: s.enabled,
  }))
  return {
    active: wire.any_active,
    scenarios,
  }
}

export async function getHealth(): Promise<HealthStatus> {
  const response = await axios.get<HealthStatus>(`${API_BASE}/api/ops/health`, { headers: authHeaders() })
  return response.data
}

export async function getMetrics(): Promise<MetricsData> {
  const response = await axios.get<MetricsData>(`${API_BASE}/api/ops/metrics`, { headers: authHeaders() })
  return response.data
}

export async function getSLO(): Promise<SLOData> {
  const response = await axios.get<SLOData>(`${API_BASE}/api/ops/slo`, { headers: authHeaders() })
  return response.data
}

export async function getTraces(): Promise<LatencyEntry[]> {
  const response = await axios.get<LatencyEntry[]>(`${API_BASE}/api/ops/traces`, { headers: authHeaders() })
  return response.data
}

export async function getChaosState(): Promise<ChaosState> {
  const response = await axios.get<ChaosWireState>(`${API_BASE}/api/ops/chaos`, { headers: authHeaders() })
  return parseChaosResponse(response.data)
}

export async function toggleChaosScenario(scenarioId: string, enabled: boolean): Promise<void> {
  await axios.post(
    `${API_BASE}/api/ops/chaos`,
    { scenario: scenarioId, enabled },
    { headers: authHeaders() }
  )
}

export async function resetChaos(): Promise<void> {
  await axios.post(`${API_BASE}/api/ops/chaos`, { reset: true }, { headers: authHeaders() })
}
