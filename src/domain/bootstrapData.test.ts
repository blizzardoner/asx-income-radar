import { describe, expect, it } from 'vitest'
import { selectUniverse } from './bootstrapData'

describe('atomic market universe bootstrap', () => {
  const fallback = [{ ticker: 'OLD.AX', name: 'Old' }]
  it('uses the fetched proxy universe rather than the old curated bundle', () => {
    const stocks = [{ ticker: 'NEW.AX', name: 'New', isProxyHolding: true }]
    expect(selectUniverse({ schemaVersion: 2, universeStocks: stocks, universe: { kind: 'vas_proxy', holdingCount: 1 } }, fallback)).toEqual(stocks)
  })
  it('rejects a partial v2 snapshot instead of silently falling back to 25 stocks', () => {
    expect(() => selectUniverse({ schemaVersion: 2 }, fallback)).toThrow()
    expect(() => selectUniverse({ schemaVersion: 2, universeStocks: [], universe: { kind: 'vas_proxy', holdingCount: 302 } }, fallback)).toThrow()
    expect(() => selectUniverse({ schemaVersion: 2, universeStocks: [{ ticker: 'DUP.AX' }, { ticker: 'DUP.AX' }], universe: {} }, fallback)).toThrow()
  })
  it('supports an explicitly legacy snapshot without inventing proxy coverage', () => {
    expect(selectUniverse({ stocks: {} }, fallback)).toEqual(fallback)
  })
})
