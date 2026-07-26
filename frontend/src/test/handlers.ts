import { http, HttpResponse } from 'msw'

export const handlers = [
  http.get('/api/health', () => {
    return HttpResponse.json({ status: 'ok' })
  }),

  // SSE stream endpoint: passthrough for now, actual SSE tests will use custom utilities
  http.get('/api/analyze/stream', () => {
    return new HttpResponse(null, { status: 200 })
  }),

  http.get('/api/dashboard/analyses', () => {
    return HttpResponse.json([
      {
        id: 'analysis-1',
        tickers: ['AAPL', 'GOOGL'],
        created_at: '2026-07-20T10:00:00Z',
      },
      {
        id: 'analysis-2',
        tickers: ['MSFT'],
        created_at: '2026-07-21T14:30:00Z',
      },
    ])
  }),

  http.get('/api/explore', () => {
    return HttpResponse.json({
      stocks: [
        {
          rank: 1,
          ticker: 'AAPL',
          name: 'Apple Inc.',
          price: 198.5,
          change_pct: 1.23,
          volume: 54_000_000,
        },
        {
          rank: 2,
          ticker: 'TSLA',
          name: 'Tesla, Inc.',
          price: 245.0,
          change_pct: -2.1,
          volume: 120_000_000,
        },
        {
          rank: 3,
          ticker: 'NVDA',
          name: 'NVIDIA Corporation',
          price: 480.25,
          change_pct: 3.45,
          volume: 65_000_000,
        },
      ],
      updated_at: '2026-07-26T12:00:00Z',
    })
  }),

  http.get('/api/explore/:ticker/detail', ({ params }) => {
    const ticker = params.ticker as string
    return HttpResponse.json({
      ticker,
      industry: 'Technology',
      description: `${ticker} is a leading technology company.`,
      price_history: [
        { date: '2026-07-01', close: 190.0 },
        { date: '2026-07-15', close: 195.0 },
        { date: '2026-07-26', close: 198.5 },
      ],
      trending_reason: [
        { title: 'Strong quarterly earnings report', url: 'https://example.com/news/1' },
      ],
    })
  }),
]
