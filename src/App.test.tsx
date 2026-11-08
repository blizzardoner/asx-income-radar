import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, it } from 'vitest'
import App from './App'

afterEach(cleanup)

const universe = [{
  ticker: 'TEST.AX',
  name: 'Test Income Co',
  sector: 'Banks',
  type: 'bank',
  quality: 'A' as const,
  frankingFraction: 1,
  requiredCashYield: 0.072,
  stabilityFactor: 1,
  payoutCoverage: 1.25,
  risk: 'Credit cycle',
}]

const marketData = {
  updatedAt: '2026-11-08T00:00:00Z',
  failures: [],
  stocks: {
    'TEST.AX': {
      price: 9.40,
      currency: 'AUD',
      marketDate: '2026-11-07',
      dataAgeDays: 1,
      high52w: 12,
      low52w: 8,
      firstClose52w: 10,
      trailingCashDps: 0.72,
    },
  },
}

describe('App', () => {
  it('shows a buy signal with its hard buy price and sustainable yield', () => {
    render(<App initialUniverse={universe} initialMarketData={marketData} />)

    expect(screen.getByText('TEST')).toBeInTheDocument()
    expect(screen.getByText('买入区')).toBeInTheDocument()
    expect(screen.getByText('A$10.00')).toBeInTheDocument()
    expect(screen.getAllByText('7.7%')).toHaveLength(2)
  })

  it('filters the value board by ticker or company name', () => {
    const second = { ...universe[0], ticker: 'OTHER.AX', name: 'Other Income Co' }
    const secondMarket = { ...marketData.stocks['TEST.AX'], price: 12 }
    render(
      <App
        initialUniverse={[...universe, second]}
        initialMarketData={{
          ...marketData,
          stocks: { ...marketData.stocks, 'OTHER.AX': secondMarket },
        }}
      />,
    )

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'TEST' } })

    expect(screen.getByText('TEST')).toBeInTheDocument()
    expect(screen.queryByText('OTHER')).not.toBeInTheDocument()
  })
})
