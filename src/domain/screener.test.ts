import { describe, expect, it } from 'vitest'
import { screenRows, type ScreenerRow } from './screener'

const row = (ticker: string, paidYears: number, historicalCashYield: number | null, averageDailyValue: number | null): ScreenerRow => ({
  stock: { ticker, name: ticker, sector: 'Banks', isProxyHolding: true, isCore: false },
  screening: { paidYears, coveredYears: 5, historicalCashYield, averageDailyValue, liquiditySessions: 60, annualCashDividends: [] },
  ordinaryYield: null,
})
describe('transparent screener', () => {
  it('orders by paid years, then historical cash yield, then liquidity without mutating input', () => {
    const rows = [row('HIGH', 1, .2, 1e6), row('LOW', 5, .04, 2e6), row('LIQ', 5, .05, 2e6), row('YLD', 5, .05, 1e6)]
    expect(screenRows(rows).map(r => r.stock.ticker)).toEqual(['LIQ', 'YLD', 'LOW', 'HIGH'])
    expect(rows[0].stock.ticker).toBe('HIGH')
  })
  it('combines explicit proxy, income, sector, history, liquidity and verification controls', () => {
    const good = row('GOOD', 5, .05, 2e6)
    const unknown = row('UNKNOWN', 5, .06, null)
    const zero = row('ZERO', 0, 0, 3e6)
    const core = { ...row('CORE', 3, .04, 1e6), stock: { ...row('CORE', 3, .04, 1e6).stock, isProxyHolding: false, isCore: true }, ordinaryYield: .03 }
    const rows = [good, unknown, zero, core]
    expect(screenRows(rows).map(r => r.stock.ticker)).toEqual(['UNKNOWN', 'GOOD'])
    expect(screenRows(rows, { minAverageDailyValue: 1 }).map(r => r.stock.ticker)).toEqual(['GOOD'])
    expect(screenRows(rows, { incomeOnly: false }).map(r => r.stock.ticker)).toContain('ZERO')
    expect(screenRows(rows, { query: 'good', sector: 'Banks', minPaidYears: 5, minHistoricalYield: .05 })).toEqual([good])
    expect(screenRows(rows, { minPaidYears: 5, minHistoricalYield: .055 })).toEqual([unknown])
    expect(screenRows(rows, { sector: 'Mining' })).toEqual([])
    expect(screenRows(rows, { scope: 'core', verifiedOrdinaryOnly: true })).toEqual([core])
    expect(screenRows(rows, { verifiedOrdinaryOnly: true })).toEqual([])
  })
  it('sorts each yield as its own metric and puts unknown liquidity last', () => {
    const a = { ...row('A', 5, .04, null), ordinaryYield: .08 }
    const b = { ...row('B', 1, .1, 1e6), ordinaryYield: .02 }
    const c = row('C', 2, .06, 3e6)
    expect(screenRows([a,b,c], { sort: 'yield' }).map(r => r.stock.ticker)).toEqual(['B','C','A'])
    expect(screenRows([a,b,c], { sort: 'liquidity' }).map(r => r.stock.ticker)).toEqual(['C','B','A'])
    expect(screenRows([a,b,c], { sort: 'ordinary' }).map(r => r.stock.ticker)).toEqual(['A','B','C'])
  })
})
