import axios from 'axios'
import type { AnalysisListItem, AnalyzeResponse } from '../types/analysis'
import { API_BASE, authHeaders } from './config'

export async function getDashboardResults(): Promise<AnalysisListItem[]> {
  const response = await axios.get<AnalysisListItem[]>(`${API_BASE}/api/dashboard`, { headers: authHeaders() })
  return response.data
}

export async function getDashboardResult(id: string): Promise<AnalyzeResponse> {
  const response = await axios.get<AnalyzeResponse>(`${API_BASE}/api/dashboard/${encodeURIComponent(id)}`, { headers: authHeaders() })
  return response.data
}

export async function deleteAnalysis(id: string): Promise<void> {
  await axios.delete(`${API_BASE}/api/dashboard/${encodeURIComponent(id)}`, { headers: authHeaders() })
}
