import { cleanup, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DataErrorBoundary from './DataErrorBoundary'

afterEach(cleanup)

describe('snapshot render failure boundary', () => {
  it('renders a recoverable error rather than a blank app for malformed nested data', () => {
    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    const Broken = () => { throw new Error('Malformed snapshot') }
    try {
      render(<DataErrorBoundary><Broken /></DataErrorBoundary>)
      expect(screen.getByRole('alert')).toHaveTextContent('市场数据无法显示')
      expect(screen.getByRole('alert')).toHaveTextContent('刷新')
    } finally { log.mockRestore() }
  })
  it('preserves the working application when the snapshot renders normally', () => {
    render(<DataErrorBoundary><p>有效数据</p></DataErrorBoundary>)
    expect(screen.getByText('有效数据')).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
