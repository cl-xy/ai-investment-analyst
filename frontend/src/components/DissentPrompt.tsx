import { Brain, X, ArrowDown } from 'lucide-react'

interface DissentPromptProps {
  onDismiss: () => void
  onReviewCritically?: () => void
}

/**
 * Gentle nudge banner shown when user has agreed with too many consecutive
 * AI signals without reviewing bear cases or questioning results.
 */
export function DissentPrompt({ onDismiss, onReviewCritically }: DissentPromptProps) {
  const handleReview = () => {
    if (onReviewCritically) {
      onReviewCritically()
    } else {
      // Fallback: scroll to bear case section if no handler provided
      const bearSection = document.getElementById('bear-case')
      if (bearSection) {
        bearSection.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    }
  }

  return (
    <div
      role="alert"
      aria-live="polite"
      className="animate-fade-in"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        padding: '12px 16px',
        borderRadius: '8px',
        border: '1px solid var(--border)',
        backgroundColor: 'var(--surface-elevated)',
        borderLeft: '3px solid var(--warning)',
      }}
    >
      <Brain
        size={20}
        style={{ color: 'var(--warning)', flexShrink: 0 }}
        aria-hidden="true"
      />

      <p
        style={{
          flex: 1,
          margin: 0,
          fontSize: '0.875rem',
          lineHeight: 1.5,
          color: 'var(--text-secondary)',
        }}
      >
        You've agreed with all recent AI signals. Consider reviewing the bear
        cases before acting.
      </p>

      <button
        onClick={handleReview}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          padding: '8px 12px',
          minHeight: '44px',
          minWidth: '44px',
          fontSize: '0.8125rem',
          fontWeight: 500,
          color: 'var(--text-primary)',
          backgroundColor: 'var(--warning-bg)',
          border: '1px solid var(--warning)',
          borderRadius: '6px',
          cursor: 'pointer',
          whiteSpace: 'nowrap',
        }}
        aria-label="Review bear cases critically"
      >
        <ArrowDown size={14} aria-hidden="true" />
        Review critically
      </button>

      <button
        onClick={onDismiss}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '44px',
          minWidth: '44px',
          padding: '8px',
          background: 'none',
          border: 'none',
          borderRadius: '6px',
          cursor: 'pointer',
          color: 'var(--text-muted)',
        }}
        aria-label="Dismiss"
      >
        <X size={18} aria-hidden="true" />
      </button>
    </div>
  )
}
