import axios from 'axios'
import type { ExploreResponse, StockDetail } from '../types/analysis'

const BASE_URL = '/api'

export async function getExploreStocks(): Promise<ExploreResponse> {
  const response = await axios.get<ExploreResponse>(`${BASE_URL}/explore`)
  return response.data
}

export async function getStockDetail(ticker: string): Promise<StockDetail> {
  const response = await axios.get<StockDetail>(`${BASE_URL}/explore/${ticker}/detail`)
  return response.data
}
