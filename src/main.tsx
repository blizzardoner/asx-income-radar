import React from 'react'
import { createRoot } from 'react-dom/client'
import App, { type MarketData, type UniverseStock } from './App'
import universe from '../data/stock-universe.json'
import { selectUniverse } from './domain/bootstrapData'
import DataErrorBoundary from './DataErrorBoundary'

async function bootstrap() {
  const root = createRoot(document.getElementById('root')!)
  try {
    const response = await fetch('./data/market.json', { cache: 'no-store' })
    if (!response.ok) throw new Error(`Market data request failed: ${response.status}`)
    const marketData = await response.json() as MarketData
    root.render(
      <React.StrictMode>
        <DataErrorBoundary>
          <App initialUniverse={selectUniverse(marketData, universe as UniverseStock[])} initialMarketData={marketData} />
        </DataErrorBoundary>
      </React.StrictMode>,
    )
  } catch (error) {
    root.render(
      <div style={{ color: '#f5f7fb', background: '#080b13', minHeight: '100vh', padding: 32, fontFamily: 'system-ui' }}>
        <h1>ASX Income Radar</h1>
        <p>市场数据加载失败。请先运行 <code>python scripts/update_market_data.py</code>。</p>
        <pre>{String(error)}</pre>
      </div>,
    )
  }
}

void bootstrap()

if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    void navigator.serviceWorker.register('./sw.js')
  })
}
