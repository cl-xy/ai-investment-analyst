import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { render } from '../../test/utils'
import App from '../../App'

describe('App', () => {
  it('renders without crashing', () => {
    render(<App />)
    // Header should be present
    expect(document.querySelector('header')).toBeInTheDocument()
  })

  it('renders the watchlist page at root route', () => {
    render(<App />)
    // The watchlist page has an input for adding tickers
    expect(screen.getByRole('main')).toBeInTheDocument()
  })

  it('renders footer', () => {
    render(<App />)
    expect(document.querySelector('footer')).toBeInTheDocument()
  })
})
