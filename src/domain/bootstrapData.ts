// Schema v2 keeps membership and prices in one snapshot, never two mismatched requests.
export function selectUniverse<T extends { ticker: string }>(payload: unknown, fallback: T[]): T[] {
  const data = payload as { schemaVersion?: number; universeStocks?: T[]; universe?: { kind?: string; holdingCount?: number } }
  if (data.schemaVersion !== 2) return fallback
  const stocks = data.universeStocks
  if (!Array.isArray(stocks) || !stocks.length || data.universe?.kind !== 'vas_proxy'
    || new Set(stocks.map(s => s.ticker)).size !== stocks.length
    || stocks.filter(s => (s as T & { isProxyHolding?: boolean }).isProxyHolding === true).length !== data.universe.holdingCount) {
    throw new Error('代理股票池快照不完整，请刷新数据后重试')
  }
  return stocks
}
