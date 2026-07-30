import axios from 'axios'
import type { ExploreResponse, StockDetail } from '../types/analysis'
import { API_BASE, authHeaders } from './config'

export async function getExploreStocks(): Promise<ExploreResponse> {
  const response = await axios.get<ExploreResponse>(`${API_BASE}/api/explore`, { headers: authHeaders() })
  return response.data
}

export async function getStockDetail(ticker: string): Promise<StockDetail> {
  const response = await axios.get<StockDetail>(`${API_BASE}/api/explore/${encodeURIComponent(ticker)}/detail`, { headers: authHeaders() })
  return response.data
}
