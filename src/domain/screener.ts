export interface Screening {
  historicalCashYield: number | null
  averageDailyValue: number | null
  liquiditySessions: number
  paidYears: number
  coveredYears: number
  annualCashDividends: Array<{ year: number; dps: number; complete: boolean }>
}
export interface ScreenerRow {
  stock: { ticker: string; name: string; sector: string; isProxyHolding?: boolean; isCore?: boolean }
  screening?: Screening
  ordinaryYield: number | null
}
export interface ScreenerFilters {
  query?: string
  sector?: string
  minHistoricalYield?: number
  minPaidYears?: number
  minAverageDailyValue?: number
  scope?: 'proxy' | 'core'
  incomeOnly?: boolean
  verifiedOrdinaryOnly?: boolean
  sort?: 'history' | 'yield' | 'liquidity' | 'ordinary'
}
export function screenRows<T extends ScreenerRow>(rows: T[], filters: ScreenerFilters = {}): T[] {
  const query = filters.query?.trim().toLowerCase() ?? ''
  const filtered = rows.filter(({ stock, screening: s, ordinaryYield }) =>
    (filters.scope === 'core' ? stock.isCore === true : stock.isProxyHolding !== false)
    && `${stock.ticker} ${stock.name}`.toLowerCase().includes(query)
    && (!filters.sector || stock.sector === filters.sector)
    && (filters.incomeOnly === false || (s?.historicalCashYield ?? 0) > 0)
    && (!(filters.minHistoricalYield! > 0) || (s?.historicalCashYield ?? -1) >= filters.minHistoricalYield!)
    && (s?.paidYears ?? 0) >= (filters.minPaidYears ?? 0)
    && (!(filters.minAverageDailyValue! > 0) || (s?.averageDailyValue ?? -1) >= filters.minAverageDailyValue!)
    && (!filters.verifiedOrdinaryOnly || ordinaryYield != null))
  const primary = (row: T) => filters.sort === 'yield' ? row.screening?.historicalCashYield
    : filters.sort === 'liquidity' ? row.screening?.averageDailyValue
    : filters.sort === 'ordinary' ? row.ordinaryYield : row.screening?.paidYears
  return filtered.sort((a, b) => (primary(b) ?? -1) - (primary(a) ?? -1)
    || (b.screening?.paidYears ?? 0) - (a.screening?.paidYears ?? 0)
    || (b.screening?.historicalCashYield ?? -1) - (a.screening?.historicalCashYield ?? -1)
    || (b.screening?.averageDailyValue ?? -1) - (a.screening?.averageDailyValue ?? -1)
    || a.stock.ticker.localeCompare(b.stock.ticker))
}
