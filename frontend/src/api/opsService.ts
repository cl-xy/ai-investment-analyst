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
  state: 'closed' | 'open' | 'half-open' | 'half_open'
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
  const scenarios: ChaosScenario[] = Object.entries(wire.scenarios ?? {}).map(([id, s]) => ({
    id,
    label: humanizeScenarioId(id),
    description: s.description,
    enabled: s.enabled,
  }))
  return {
    active: wire.any_active ?? false,
    scenarios,
  }
}

// Wire format from backend /api/ops/health
interface HealthWireComponent {
  status?: 'up' | 'degraded' | 'down'
  connected?: boolean
  circuit_breaker?: string
  rate_limiter?: { tokens_available: number; capacity: number }
  [key: string]: unknown
}

interface HealthWireResponse {
  status: string
  components: Record<string, HealthWireComponent | Record<string, unknown>>
  timestamp: string
}

function parseHealthResponse(wire: HealthWireResponse): HealthStatus {
  const mapStatus = (comp: HealthWireComponent | Record<string, unknown> | undefined): ComponentHealth => {
    if (!comp) return { status: 'up' }
    // Direct status field
    if ('status' in comp && (comp.status === 'up' || comp.status === 'degraded' || comp.status === 'down')) {
      return { status: comp.status, latency_ms: (comp as HealthWireComponent).latency_ms as number | undefined }
    }
    // Connected boolean (database)
    if ('connected' in comp) {
      return { status: comp.connected ? 'up' : 'down' }
    }
    return { status: 'up' }
  }

  return {
    status: (wire.status === 'healthy' || wire.status === 'degraded' || wire.status === 'unhealthy')
      ? wire.status as HealthStatus['status']
      : 'healthy',
    components: {
      api: { status: 'up' },
      database: mapStatus(wire.components?.database as HealthWireComponent),
      llm_provider: mapStatus(wire.components?.llm_provider as HealthWireComponent),
      mcp_servers: { status: 'up' },
    },
    timestamp: wire.timestamp ?? new Date().toISOString(),
  }
}

export async function getHealth(): Promise<HealthStatus> {
  const response = await axios.get<HealthWireResponse>(`${API_BASE}/api/ops/health`, { headers: authHeaders() })
  return parseHealthResponse(response.data)
}

// Wire format from backend /api/ops/metrics
interface MetricsWireCircuitBreaker {
  state: 'closed' | 'open' | 'half-open'
  failure_count: number
  threshold: number
}

interface MetricsWireResponse {
  requests: { total: number; errors: number; by_endpoint: Record<string, number>; errors_by_endpoint: Record<string, number> }
  latency: { p50_ms: number; p95_ms: number; observations: number }
  llm: { total_calls: number; duration_p50_ms: number; duration_p95_ms: number; total_prompt_tokens: number; total_completion_tokens: number }
  circuit_breakers: Record<string, MetricsWireCircuitBreaker>
  cache: { hits: number; misses: number; hit_rate: number }
  uptime_seconds: number
  rate_limiter: { tokens_available: number; capacity: number; rate_per_second: number }
  budget: Record<string, { used: number; limit: number; remaining: number; exhausted: boolean }>
}

function parseMetricsResponse(wire: MetricsWireResponse): MetricsData {
  // Transform circuit_breakers object to array
  const circuit_breakers: CircuitBreaker[] = Object.entries(wire.circuit_breakers ?? {}).map(
    ([name, cb]) => ({
      name,
      state: cb.state,
      failure_count: cb.failure_count,
      last_state_change: '',
    })
  )

  // Build rate_limits from rate_limiter + budget.openrouter
  const orBudget = wire.budget?.openrouter ?? { used: 0, limit: 1400, remaining: 1400 }
  const rate_limits: RateLimitStatus = {
    openrouter: {
      per_minute: {
        used: Math.round(wire.rate_limiter?.capacity ?? 0) - Math.round(wire.rate_limiter?.tokens_available ?? 0),
        limit: Math.round(wire.rate_limiter?.capacity ?? 0),
      },
      daily: {
        used: orBudget.used,
        limit: orBudget.limit,
      },
    },
  }

  return {
    circuit_breakers,
    rate_limits,
    recent_errors: [],
    latency_history: [],
  }
}

export async function getMetrics(): Promise<MetricsData> {
  const response = await axios.get<MetricsWireResponse>(`${API_BASE}/api/ops/metrics`, { headers: authHeaders() })
  return parseMetricsResponse(response.data)
}

// Wire format from backend /api/ops/slo
interface SLOWireResponse {
  window: string
  total_requests: number
  targets: { availability: number; latency_p95_ms: number; error_budget_monthly: number }
  actuals: { availability: number; latency_p95_ms: number; error_rate: number }
  budget: { error_budget_total: number; error_budget_consumed: number; error_budget_remaining: number; burn_rate: number }
  status: string
}

function parseSLOResponse(wire: SLOWireResponse): SLOData {
  const windowDays = wire.window === '7d' ? 7 : wire.window === '30d' ? 30 : 7
  const budgetTotal = wire.budget?.error_budget_total || 0.005
  const budgetConsumed = wire.budget?.error_budget_consumed || 0
  const burnedPct = budgetTotal > 0 ? (budgetConsumed / budgetTotal) * 100 : 0

  return {
    availability: {
      current: wire.actuals?.availability ?? 1.0,
      target: wire.targets?.availability ?? 0.995,
      budget_remaining: wire.budget?.error_budget_remaining ?? 0.005,
    },
    p95_latency: {
      current_ms: wire.actuals?.latency_p95_ms ?? 0,
      target_ms: wire.targets?.latency_p95_ms ?? 120000,
    },
    error_budget: {
      burned_pct: burnedPct,
      remaining_pct: 100 - burnedPct,
      window_days: windowDays,
    },
  }
}

export async function getSLO(): Promise<SLOData> {
  const response = await axios.get<SLOWireResponse>(`${API_BASE}/api/ops/slo`, { headers: authHeaders() })
  return parseSLOResponse(response.data)
}

export async function getTraces(): Promise<LatencyEntry[]> {
  const response = await axios.get<{ traces: LatencyEntry[]; total: number } | LatencyEntry[]>(`${API_BASE}/api/ops/traces`, { headers: authHeaders() })
  const data = response.data
  return Array.isArray(data) ? data : data.traces
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
