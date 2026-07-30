export interface TickerAnalysis {
  ticker: string
  signal: 'buy' | 'hold' | 'sell' | 'insufficient_data'
  confidence: 'high' | 'medium' | 'low'
  sentiment_score: number
  news_summary: string
  risk_flags: string[]
  price_data: Record<string, unknown>
  fundamentals: Record<string, unknown>
  earnings: Record<string, unknown>
  sec_notes: string
}

export interface AnalyzeResponse {
  id: string
  tickers: string[]
  report_markdown: string
  analyses: Record<string, TickerAnalysis>
  created_at: string
  comparison: Record<string, unknown> | null
  peer_comparison: Record<string, unknown> | null
}

export interface AnalysisListItem {
  id: string
  tickers: string[]
  created_at: string
}

export interface TrendingStock {
  rank: number
  ticker: string
  name: string
  price: number | null
  change_pct: number | null
  volume: number | null
}

export interface ExploreResponse {
  stocks: TrendingStock[]
  updated_at: string
}

export interface PricePoint {
  date: string
  close: number
}

export interface NewsItem {
  title: string
  url: string | null
}

export interface StockDetail {
  ticker: string
  industry: string | null
  description: string | null
  price_history: PricePoint[]
  trending_reason: NewsItem[]
}
