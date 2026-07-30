import { useCallback, useRef, useState } from 'react'

interface RovingGridOptions {
  rows: number
  cols: number
  onActivate?: (row: number, col: number) => void
  wrap?: boolean
}

interface RovingGridReturn {
  activeRow: number
  activeCol: number
  getGridProps: () => React.HTMLAttributes<HTMLElement> & { ref?: React.Ref<HTMLElement> }
  getCellProps: (row: number, col: number) => React.HTMLAttributes<HTMLElement>
  setActive: (row: number, col: number) => void
  reset: () => void
}

/**
 * Implements WAI-ARIA roving tabindex pattern for 2D grid navigation.
 * Arrow keys navigate cells, Enter activates, Escape exits, Home/End jump within row.
 */
export function useRovingGrid(options: RovingGridOptions): RovingGridReturn {
  const { rows, cols, onActivate, wrap = true } = options
  const [activeRow, setActiveRow] = useState(0)
  const [activeCol, setActiveCol] = useState(0)
  const gridRef = useRef<HTMLElement | null>(null)
  const onActivateRef = useRef(onActivate)
  onActivateRef.current = onActivate

  const focusCell = useCallback((row: number, col: number) => {
    if (!gridRef.current) return
    const cell = gridRef.current.querySelector<HTMLElement>(
      `[data-grid-row="${row}"][data-grid-col="${col}"]`
    )
    if (cell) {
      cell.focus({ preventScroll: false })
    }
  }, [])

  const setActive = useCallback(
    (row: number, col: number) => {
      const clampedRow = Math.max(0, Math.min(row, rows - 1))
      const clampedCol = Math.max(0, Math.min(col, cols - 1))
      setActiveRow(clampedRow)
      setActiveCol(clampedCol)
      focusCell(clampedRow, clampedCol)
    },
    [rows, cols, focusCell]
  )

  const reset = useCallback(() => {
    setActiveRow(0)
    setActiveCol(0)
  }, [])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLElement>) => {
      if (rows === 0 || cols === 0) return

      let nextRow = activeRow
      let nextCol = activeCol
      let handled = true

      switch (e.key) {
        case 'ArrowDown':
          nextRow = activeRow + 1
          if (nextRow >= rows) {
            nextRow = wrap ? 0 : rows - 1
          }
          break
        case 'ArrowUp':
          nextRow = activeRow - 1
          if (nextRow < 0) {
            nextRow = wrap ? rows - 1 : 0
          }
          break
        case 'ArrowRight':
          nextCol = activeCol + 1
          if (nextCol >= cols) {
            nextCol = wrap ? 0 : cols - 1
          }
          break
        case 'ArrowLeft':
          nextCol = activeCol - 1
          if (nextCol < 0) {
            nextCol = wrap ? cols - 1 : 0
          }
          break
        case 'Home':
          nextCol = 0
          break
        case 'End':
          nextCol = cols - 1
          break
        case 'Enter':
          onActivateRef.current?.(activeRow, activeCol)
          break
        case 'Escape': {
          // Move focus out of the grid
          const grid = gridRef.current
          if (grid) {
            grid.blur()
            // Try to focus the next focusable element after the grid
            const parent = grid.parentElement
            if (parent) {
              const allFocusable = parent.querySelectorAll<HTMLElement>(
                'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
              )
              for (const el of allFocusable) {
                if (!grid.contains(el)) {
                  el.focus()
                  break
                }
              }
            }
          }
          break
        }
        default:
          handled = false
      }

      if (handled) {
        e.preventDefault()
        e.stopPropagation()
      }

      if (nextRow !== activeRow || nextCol !== activeCol) {
        setActiveRow(nextRow)
        setActiveCol(nextCol)
        focusCell(nextRow, nextCol)
      }
    },
    [activeRow, activeCol, rows, cols, wrap, focusCell]
  )

  const getGridProps = useCallback(
    (): React.HTMLAttributes<HTMLElement> & { ref?: React.Ref<HTMLElement> } => ({
      role: 'grid',
      ref: ((el: HTMLElement | null) => {
        gridRef.current = el
      }),
      onKeyDown: handleKeyDown,
    }),
    [handleKeyDown]
  )

  const getCellProps = useCallback(
    (row: number, col: number): React.HTMLAttributes<HTMLElement> => {
      const isActive = row === activeRow && col === activeCol
      return {
        role: 'gridcell',
        tabIndex: isActive ? 0 : -1,
        'data-grid-row': row,
        'data-grid-col': col,
        ...(isActive && { 'data-grid-active': 'true' }),
      } as React.HTMLAttributes<HTMLElement>
    },
    [activeRow, activeCol]
  )

  return {
    activeRow,
    activeCol,
    getGridProps,
    getCellProps,
    setActive,
    reset,
  }
}
