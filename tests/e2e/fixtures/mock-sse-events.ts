/**
 * Generates a realistic SSE event sequence for E2E test mocking.
 * Each event follows the backend domain event schema with sequential
 * seq numbers and realistic timing gaps.
 */

interface MockSSEOptions {
  ticker: string
  signal?: 'buy' | 'hold' | 'sell' | 'insufficient_data'
  includeDataGaps?: boolean
  failAtNode?: string
}

function sseEvent(eventType: string, data: Record<string, unknown>): string {
  return `event: ${eventType}\ndata: ${JSON.stringify(data)}\n\n`
}

export function createMockSSEStream(
  ticker: string,
  options: Partial<MockSSEOptions> = {},
): string {
  const {
    signal = 'buy',
    includeDataGaps = false,
    failAtNode,
  } = options

  const runId = 'run_test_' + ticker.toLowerCase()
  const ts = '2026-07-26T10:00:00Z'
  let seq = 0

  const events: string[] = []

  // run_started
  events.push(
    sseEvent('run_started', {
      run_id: runId,
      seq: seq++,
      type: 'run_started',
      timestamp: ts,
      node: null,
      tool: null,
      payload: { tickers: [ticker] },
    }),
  )

  // router node
  events.push(
    sseEvent('node_started', {
      run_id: runId,
      seq: seq++,
      type: 'node_started',
      timestamp: ts,
      node: 'router',
      tool: null,
      payload: { description: 'Routing analysis request' },
    }),
  )

  events.push(
    sseEvent('node_completed', {
      run_id: runId,
      seq: seq++,
      type: 'node_completed',
      timestamp: ts,
      node: 'router',
      tool: null,
      payload: { duration_ms: 340, next_nodes: ['fetch_data'] },
    }),
  )

  // fetch_data node
  events.push(
    sseEvent('node_started', {
      run_id: runId,
      seq: seq++,
      type: 'node_started',
      timestamp: ts,
      node: 'fetch_data',
      tool: null,
      payload: { description: 'Fetching market data' },
    }),
  )

  // tool_call: market data
  events.push(
    sseEvent('tool_call', {
      run_id: runId,
      seq: seq++,
      type: 'tool_call',
      timestamp: ts,
      node: 'fetch_data',
      tool: 'market_data',
      payload: { tool_name: 'market_data', args: { ticker, period: '3mo' } },
    }),
  )

  // tool_result: market data (cached)
  events.push(
    sseEvent('tool_result', {
      run_id: runId,
      seq: seq++,
      type: 'tool_result',
      timestamp: ts,
      node: 'fetch_data',
      tool: 'market_data',
      payload: {
        tool_name: 'market_data',
        success: true,
        cached: true,
        duration_ms: 12,
        source_id: 'yfinance',
      },
    }),
  )

  // tool_call: news
  events.push(
    sseEvent('tool_call', {
      run_id: runId,
      seq: seq++,
      type: 'tool_call',
      timestamp: ts,
      node: 'fetch_data',
      tool: 'news_search',
      payload: { tool_name: 'news_search', args: { query: ticker, limit: 10 } },
    }),
  )

  // tool_result: news (live)
  events.push(
    sseEvent('tool_result', {
      run_id: runId,
      seq: seq++,
      type: 'tool_result',
      timestamp: ts,
      node: 'fetch_data',
      tool: 'news_search',
      payload: {
        tool_name: 'news_search',
        success: true,
        cached: false,
        duration_ms: 890,
        source_id: 'newsapi',
      },
    }),
  )

  if (failAtNode === 'fetch_data') {
    events.push(
      sseEvent('error', {
        run_id: runId,
        seq: seq++,
        type: 'error',
        timestamp: ts,
        node: 'fetch_data',
        tool: 'sec_filings',
        payload: {
          message: 'SEC EDGAR rate limit exceeded',
          recoverable: true,
        },
      }),
    )
  }

  events.push(
    sseEvent('node_completed', {
      run_id: runId,
      seq: seq++,
      type: 'node_completed',
      timestamp: ts,
      node: 'fetch_data',
      tool: null,
      payload: { duration_ms: 1240 },
    }),
  )

  // analyze node
  events.push(
    sseEvent('node_started', {
      run_id: runId,
      seq: seq++,
      type: 'node_started',
      timestamp: ts,
      node: 'analyze',
      tool: null,
      payload: { description: 'Running LLM analysis' },
    }),
  )

  // llm_token streaming (a few tokens to simulate)
  const tokens = ['The', ' stock', ' shows', ' strong', ' momentum']
  for (const token of tokens) {
    events.push(
      sseEvent('llm_token', {
        run_id: runId,
        seq: seq++,
        type: 'llm_token',
        timestamp: ts,
        node: 'analyze',
        tool: null,
        payload: { token },
      }),
    )
  }

  events.push(
    sseEvent('node_completed', {
      run_id: runId,
      seq: seq++,
      type: 'node_completed',
      timestamp: ts,
      node: 'analyze',
      tool: null,
      payload: { duration_ms: 2100 },
    }),
  )

  // analysis_complete
  const analysis = {
    ticker,
    signal,
    confidence: 'high' as const,
    sentiment_score: signal === 'buy' ? 0.72 : signal === 'sell' ? -0.45 : 0.1,
    thesis: `${ticker} demonstrates strong revenue growth driven by AI demand.`,
    bull_case: [
      'Data center revenue up 150% YoY',
      'Expanding moat in AI training hardware',
      'Strong forward guidance',
    ],
    bear_case: [
      'Elevated valuation multiples',
      'Customer concentration risk',
    ],
    risk_flags: ['high_pe_ratio', 'insider_selling'],
    citations: [
      { source_id: 'yfinance', claim: 'Price and volume data', provider: 'Yahoo Finance' },
      { source_id: 'newsapi', claim: 'Recent earnings coverage', provider: 'NewsAPI' },
    ],
    data_gaps: includeDataGaps ? ['sec_filings', 'insider_transactions'] : [],
    price_data: {
      current_price: 135.42,
      change_pct: 2.3,
      retrieved_at: '2026-07-26T09:45:00Z',
    },
    fundamentals: { pe_ratio: 65.2, market_cap: '3.3T' },
    sec_notes: includeDataGaps
      ? 'SEC data unavailable due to rate limiting'
      : 'Latest 10-Q reviewed, no material concerns',
    news_summary: `Recent coverage highlights ${ticker} AI infrastructure dominance.`,
  }

  events.push(
    sseEvent('analysis_complete', {
      run_id: runId,
      seq: seq++,
      type: 'analysis_complete',
      timestamp: ts,
      node: 'analyze',
      tool: null,
      payload: { ticker, analysis },
    }),
  )

  // run_completed
  events.push(
    sseEvent('run_completed', {
      run_id: runId,
      seq: seq++,
      type: 'run_completed',
      timestamp: ts,
      node: null,
      tool: null,
      payload: {
        tickers: [ticker],
        total_duration_ms: 4200,
        total_tokens: 2840,
        cost_usd: 0.0,
      },
    }),
  )

  return events.join('')
}

/**
 * Creates a stream that fails with a non-recoverable error.
 */
export function createErrorSSEStream(ticker: string, message: string): string {
  const runId = 'run_error_' + ticker.toLowerCase()
  const ts = '2026-07-26T10:00:00Z'

  const events: string[] = []

  events.push(
    sseEvent('run_started', {
      run_id: runId,
      seq: 0,
      type: 'run_started',
      timestamp: ts,
      node: null,
      tool: null,
      payload: { tickers: [ticker] },
    }),
  )

  events.push(
    sseEvent('error', {
      run_id: runId,
      seq: 1,
      type: 'error',
      timestamp: ts,
      node: null,
      tool: null,
      payload: { message, recoverable: false },
    }),
  )

  return events.join('')
}

/**
 * Creates a partial SSE stream that cuts off mid-way (simulates disconnect).
 */
export function createDisconnectSSEStream(ticker: string): string {
  const runId = 'run_disconnect_' + ticker.toLowerCase()
  const ts = '2026-07-26T10:00:00Z'

  const events: string[] = []

  events.push(
    sseEvent('run_started', {
      run_id: runId,
      seq: 0,
      type: 'run_started',
      timestamp: ts,
      node: null,
      tool: null,
      payload: { tickers: [ticker] },
    }),
  )

  events.push(
    sseEvent('node_started', {
      run_id: runId,
      seq: 1,
      type: 'node_started',
      timestamp: ts,
      node: 'router',
      tool: null,
      payload: { description: 'Routing analysis request' },
    }),
  )

  // Stream ends abruptly here (no run_completed)
  return events.join('')
}
