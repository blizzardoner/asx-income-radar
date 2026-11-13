import { describe, expect, it } from 'vitest'
import { afterTaxYield, evaluateStock, grossedUpYield } from './valueScore'

describe('evaluateStock', () => {
  it('does not create a yield, score or buy point when ordinary annual income is unverified', () => {
    const result = evaluateStock({ price: 10, sustainableDps: null,
      requiredCashYield: 0.05, quality: 'A', payoutCoverage: 1.2, dataAgeDays: 0 })
    expect(result.status).toBe('UNVERIFIED')
    expect(result.cashYield).toBeNull()
    expect(result.buyPrice).toBeNull()
    expect(result.score).toBe(0)
  })

  it('marks a quality income stock as BUY below its hard buy price', () => {
    const result = evaluateStock({
      price: 9.40,
      sustainableDps: 0.72,
      requiredCashYield: 0.072,
      quality: 'A',
      payoutCoverage: 1.25,
      dataAgeDays: 0,
    })

    expect(result.buyPrice).toBeCloseTo(10)
    expect(result.cashYield).toBeCloseTo(0.0766, 3)
    expect(result.status).toBe('BUY')
    expect(result.score).toBeGreaterThanOrEqual(75)
  })

  it('marks a stock as WATCH when it is within eight percent of its buy price', () => {
    const result = evaluateStock({
      price: 10.60,
      sustainableDps: 0.72,
      requiredCashYield: 0.072,
      quality: 'B',
      payoutCoverage: 1.1,
      dataAgeDays: 0,
    })

    expect(result.status).toBe('WATCH')
  })
})

describe('franking-aware yield', () => {
  it('calculates grossed-up and investor after-tax yield', () => {
    const gross = grossedUpYield(0.06, 1)
    const net = afterTaxYield(0.06, 1, 0.47)

    expect(gross).toBeCloseTo(0.085714, 5)
    expect(net).toBeCloseTo(0.045429, 5)
  })
})
