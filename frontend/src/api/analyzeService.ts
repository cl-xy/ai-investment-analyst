import axios from 'axios'
import type { AnalysisListItem, AnalyzeRequest, AnalyzeResponse } from '../types/analysis'

const BASE_URL = '/api'

export async function analyzeStocks(request: AnalyzeRequest): Promise<AnalyzeResponse> {
  const response = await axios.post<AnalyzeResponse>(`${BASE_URL}/analyze`, request)
  return response.data
}

export async function getDashboardResults(): Promise<AnalysisListItem[]> {
  const response = await axios.get<AnalysisListItem[]>(`${BASE_URL}/dashboard`)
  return response.data
}

export async function getDashboardResult(id: string): Promise<AnalyzeResponse> {
  const response = await axios.get<AnalyzeResponse>(`${BASE_URL}/dashboard/${id}`)
  return response.data
}

export async function deleteAnalysis(id: string): Promise<void> {
  await axios.delete(`${BASE_URL}/dashboard/${id}`)
}
