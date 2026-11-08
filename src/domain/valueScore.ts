export type QualityGrade = 'A' | 'B' | 'C'
export type ValueStatus = 'BUY' | 'WATCH' | 'WAIT' | 'STALE'

export interface StockEvaluationInput {
  price: number
  sustainableDps: number
  requiredCashYield: number
  quality: QualityGrade
  payoutCoverage: number
  dataAgeDays: number
}

export interface StockEvaluation {
  buyPrice: number
  cashYield: number
  discountToBuyPrice: number
  score: number
  status: ValueStatus
}

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value))

export function grossedUpYield(cashYield: number, frankedFraction: number, companyTaxRate = 0.30) {
  return cashYield * (1 + frankedFraction * companyTaxRate / (1 - companyTaxRate))
}

export function afterTaxYield(
  cashYield: number,
  frankedFraction: number,
  marginalTaxRate: number,
  companyTaxRate = 0.30,
) {
  const grossYield = grossedUpYield(cashYield, frankedFraction, companyTaxRate)
  const frankingCreditYield = cashYield * frankedFraction * companyTaxRate / (1 - companyTaxRate)
  return cashYield - (grossYield * marginalTaxRate - frankingCreditYield)
}

export function evaluateStock(input: StockEvaluationInput): StockEvaluation {
  const buyPrice = input.sustainableDps / input.requiredCashYield
  const cashYield = input.sustainableDps / input.price
  const discountToBuyPrice = buyPrice / input.price - 1
  const qualityPoints = { A: 40, B: 28, C: 15 }[input.quality]
  const yieldPoints = clamp((cashYield / input.requiredCashYield - 0.8) * 100, 0, 35)
  const valuationPoints = input.price <= buyPrice ? 25 : clamp(25 - (input.price / buyPrice - 1) * 100, 0, 25)
  const coveragePoints = clamp((input.payoutCoverage - 0.8) * 20, 0, 10)
  const score = Math.round(clamp(qualityPoints + yieldPoints + valuationPoints + coveragePoints, 0, 100))

  let status: ValueStatus = 'WAIT'
  if (input.dataAgeDays > 7) status = 'STALE'
  else if (input.price <= buyPrice && input.quality !== 'C' && input.payoutCoverage >= 1) status = 'BUY'
  else if (input.price <= buyPrice * 1.08) status = 'WATCH'

  return { buyPrice, cashYield, discountToBuyPrice, score, status }
}
