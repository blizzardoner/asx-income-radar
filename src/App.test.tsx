import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date('2026-11-14T01:00:00Z')) })
afterEach(() => { cleanup(); vi.useRealTimers() })

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
      annualOrdinaryCashDps: 0.72,
      dividendBasis: { status: 'verified' as const, annualDpsAud: 0.72, dps: 0.72,
        currency: 'AUD', kind: 'reported' as const, periodEnd: '2026-06-30',
        announcedOn: '2026-08-01', validUntil: '2099-01-01',
        sources: ['https://company.example/fy26'] },
    },
  },
}

describe('App', () => {
  it.each([
    ['expired', { rate: 1.5, asOf: '2026-11-06', source: 'test' }],
    ['future', { rate: 1.5, asOf: '2026-11-15', source: 'test' }],
    ['missing date', { rate: 1.5, asOf: '', source: 'test' }],
    ['invalid date', { rate: 1.5, asOf: 'not-a-date', source: 'test' }],
    ['missing FX', undefined],
    ['missing rate', { rate: undefined as unknown as number, asOf: '2026-11-14', source: 'test' }],
    ['zero rate', { rate: 0, asOf: '2026-11-14', source: 'test' }],
    ['negative rate', { rate: -1.5, asOf: '2026-11-14', source: 'test' }],
    ['nonfinite rate', { rate: Infinity, asOf: '2026-11-14', source: 'test' }],
  ])('rejects cached verified foreign dividends with %s FX', (_label, fx) => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData,
      stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'], marketDate: '2026-11-14', dividendBasis: {
        ...marketData.stocks['TEST.AX'].dividendBasis, currency: 'USD', fx,
      } } } }} />)
    const card = screen.getByText('TEST').closest('details')!
    expect(card).toHaveClass('status-unverified')
    expect(within(card).queryByText('买入区')).not.toBeInTheDocument()
    expect(within(card).queryByText('接近买点')).not.toBeInTheDocument()
    expect(within(card).queryByText('7.7%')).not.toBeInTheDocument()
    expect(card.querySelector('.income-basis strong')).toHaveTextContent('— · 财年截至 2026-06-30')
    expect(within(card).queryByText(/汇率 ×/)).not.toBeInTheDocument()
  })

  it.each(['USD', 'EUR'])('accepts a %s dividend basis with positive FX exactly seven days old', (currency) => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData,
      stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'], dividendBasis: {
        ...marketData.stocks['TEST.AX'].dividendBasis, currency,
        fx: { rate: 1.5, asOf: '2026-11-07', source: 'test' },
      } } } }} />)
    expect(screen.getByText('TEST').closest('details')).toHaveClass('status-buy')
  })

  it('marks future market dates stale even when the cached quote age is zero', () => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData,
      stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'], marketDate: '2026-11-15', dataAgeDays: 0 } } }} />)
    expect(screen.getByText('TEST').closest('details')).toHaveClass('status-stale')
    expect(within(screen.getByText('TEST').closest('details')!).queryByText('买入区')).not.toBeInTheDocument()
  })

  it.each(['', 'not-a-date'])('marks missing or invalid market date %j stale', (marketDate) => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData,
      stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'], marketDate, dataAgeDays: 0 } } }} />)
    expect(screen.getByText('TEST').closest('details')).toHaveClass('status-stale')
  })
  it('does not display a negative zero caused by quote float noise', () => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData,
      stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'], priceChanges: {
        week: { percent: -0.000000011, amount: -0.00000007, baselinePrice: 9.4, baselineDate: '2026-11-06', targetDate: '2026-11-06' },
      } } } }} />)
    expect(within(screen.getByRole('group', { name: '股价变化' })).getByText('0.00%')).toBeInTheDocument()
    expect(screen.queryByText('-0.00%')).not.toBeInTheDocument()
  })

  it('rechecks quote age when an offline snapshot still claims fresh prices', () => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData,
      stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'], marketDate: '2026-11-01', dataAgeDays: 0 } } }} />)
    expect(screen.getByText('数据过期')).toBeInTheDocument()
    expect(screen.queryByText('买入区')).not.toBeInTheDocument()
  })

  it('shows daily, weekly and yearly price changes side by side with their own baselines', () => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData,
      stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'], priceChanges: {
        day: { percent: 0.012, baselineDate: '2026-11-12', baselinePrice: 9.29, targetDate: '2026-11-12', amount: 0.11 },
        week: { percent: -0.03, baselineDate: '2026-11-06', baselinePrice: 9.69, targetDate: '2026-11-06', amount: -0.29 },
        year: { percent: 0.10, baselineDate: '2025-11-13', baselinePrice: 8.55, targetDate: '2025-11-13', amount: 0.85 },
      } } } }} />)
    const changes = within(screen.getByRole('group', { name: '股价变化' }))
    expect(changes.getByText('当天')).toBeInTheDocument()
    expect(changes.getByText('过去一周')).toBeInTheDocument()
    expect(changes.getByText('过去一年')).toBeInTheDocument()
    expect(changes.getByText('+1.20%')).toBeInTheDocument()
    expect(changes.getByText('-3.00%')).toBeInTheDocument()
    expect(changes.getByText('+10.00%')).toBeInTheDocument()
    expect(screen.getAllByText(/2025-11-13/).length).toBeGreaterThan(0)
  })

  it('does not use rolling dividends or a legacy override when the annual basis is missing', () => {
    render(<App initialUniverse={[{ ...universe[0], sustainableDpsOverride: 2 }]}
      initialMarketData={{ ...marketData, stocks: { 'TEST.AX': {
        ...marketData.stocks['TEST.AX'], dividendBasis: undefined, trailingCashDps: 2,
      } } }} />)
    expect(screen.getByText('股息待核实')).toBeInTheDocument()
    expect(screen.queryByText('买入区')).not.toBeInTheDocument()
    expect(screen.queryByText('21.3%')).not.toBeInTheDocument()
  })

  it('rechecks expiry so a previously verified offline snapshot cannot keep buy signals', () => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData,
      stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'], dividendBasis: {
        ...marketData.stocks['TEST.AX'].dividendBasis, validUntil: '2000-01-01',
      } } } }} />)
    expect(screen.getByText('股息待核实')).toBeInTheDocument()
    expect(screen.queryByText('买入区')).not.toBeInTheDocument()
  })

  it('uses the ordinary annual basis for yield and buy price, not three rolling payments', () => {
    render(<App initialUniverse={universe} initialMarketData={{
      ...marketData,
      stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'],
        trailingCashDps: 1.08, annualOrdinaryCashDps: 0.72 } },
    }} />)

    expect(screen.getAllByText('7.7%')).toHaveLength(3)
    expect(screen.getByText('A$10.00')).toBeInTheDocument()
    expect(screen.queryByText('11.5%')).not.toBeInTheDocument()
    expect(screen.getByText('A$1.08')).toBeInTheDocument()
  })

  it('shows missing period history as unavailable without using the old range-start baseline', () => {
    render(<App initialUniverse={universe} initialMarketData={marketData} />)
    const changes = within(screen.getByRole('group', { name: '股价变化' }))
    expect(changes.getAllByText('—')).toHaveLength(3)
    expect(screen.queryByText('-6.0%')).not.toBeInTheDocument()
  })

  it('shows a buy signal with its hard buy price and sustainable yield', () => {
    render(<App initialUniverse={universe} initialMarketData={marketData} />)

    expect(screen.getByText('TEST')).toBeInTheDocument()
    expect(screen.getByText('买入区')).toBeInTheDocument()
    expect(screen.getByText('A$10.00')).toBeInTheDocument()
    expect(screen.getAllByText('7.7%')).toHaveLength(3)
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
