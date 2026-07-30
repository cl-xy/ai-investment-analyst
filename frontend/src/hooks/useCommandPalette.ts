import { useState, useEffect, useCallback, useMemo } from 'react'

export interface CommandItem {
  id: string
  label: string
  path: string
  keywords?: string[]
}

interface FuzzyMatch {
  item: CommandItem
  score: number
}

/** Simple fuzzy matching: exact prefix > word-start > substring */
function fuzzyMatch(query: string, item: CommandItem): number {
  if (!query) return 1
  const q = query.toLowerCase()
  const label = item.label.toLowerCase()
  const path = item.path.toLowerCase()
  const keywords = (item.keywords ?? []).map((k) => k.toLowerCase())

  // Exact prefix match on label (highest priority)
  if (label.startsWith(q)) return 100

  // Word-start match on label
  const words = label.split(/\s+/)
  if (words.some((w) => w.startsWith(q))) return 80

  // Keyword prefix match
  if (keywords.some((k) => k.startsWith(q))) return 70

  // Path match
  if (path.includes(q)) return 60

  // Substring match on label
  if (label.includes(q)) return 50

  // Keyword substring match
  if (keywords.some((k) => k.includes(q))) return 40

  // Multi-word: all query terms appear somewhere
  const terms = q.split(/\s+/).filter(Boolean)
  if (terms.length > 1) {
    const combined = `${label} ${path} ${keywords.join(' ')}`
    if (terms.every((t) => combined.includes(t))) return 30
  }

  return 0
}

function filterAndRank(items: CommandItem[], query: string): CommandItem[] {
  if (!query.trim()) return items

  const matches: FuzzyMatch[] = []
  for (const item of items) {
    const score = fuzzyMatch(query, item)
    if (score > 0) {
      matches.push({ item, score })
    }
  }

  matches.sort((a, b) => b.score - a.score)
  return matches.map((m) => m.item)
}

export function useCommandPalette(items: CommandItem[]) {
  const [isOpen, setIsOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)

  const results = useMemo(() => filterAndRank(items, query), [items, query])

  // Reset selection when results change
  useEffect(() => {
    setSelectedIndex(0)
  }, [results.length, query])

  const open = useCallback(() => {
    setIsOpen(true)
    setQuery('')
    setSelectedIndex(0)
  }, [])

  const close = useCallback(() => {
    setIsOpen(false)
    setQuery('')
    setSelectedIndex(0)
  }, [])

  // Global Cmd+K / Ctrl+K listener
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const isMod = e.metaKey || e.ctrlKey
      if (isMod && e.key === 'k') {
        e.preventDefault()
        e.stopPropagation()
        if (isOpen) {
          close()
        } else {
          open()
        }
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, open, close])

  return {
    isOpen,
    open,
    close,
    query,
    setQuery,
    results,
    selectedIndex,
    setSelectedIndex,
  }
}
