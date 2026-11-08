import { useState } from 'react'
import { AlertTriangle, ArrowDownRight, ArrowUpRight, BadgeDollarSign, Clock3, Radar, Search, ShieldCheck, Sparkles } from 'lucide-react'
import { afterTaxYield, evaluateStock, grossedUpYield, type QualityGrade, type ValueStatus } from './domain/valueScore'
import './styles.css'

export interface UniverseStock {
  ticker: string
  name: string
  sector: string
  type: string
  quality: QualityGrade
  frankingFraction: number
  requiredCashYield: number
  stabilityFactor: number
  payoutCoverage: number
  sustainableDpsOverride?: number
  risk: string
}

export interface MarketStock {
  price: number
  currency: string
  marketDate: string
  dataAgeDays: number
  high52w: number | null
  low52w: number | null
  firstClose52w: number | null
  trailingCashDps: number
}

export interface MarketData {
  updatedAt: string
  stocks: Record<string, MarketStock>
  failures: Array<{ ticker: string; error: string }>
}

interface AppProps {
  initialUniverse: UniverseStock[]
  initialMarketData: MarketData
}

const statusLabels: Record<ValueStatus, string> = {
  BUY: '买入区',
  WATCH: '接近买点',
  WAIT: '等待',
  STALE: '数据过期',
}

const statusOrder: Record<ValueStatus, number> = { BUY: 0, WATCH: 1, WAIT: 2, STALE: 3 }
const money = (value: number) => `A$${value.toFixed(2)}`
const percent = (value: number) => `${(value * 100).toFixed(1)}%`

export default function App({ initialUniverse, initialMarketData }: AppProps) {
  const [query, setQuery] = useState('')
  const marginalTaxRate = 0.47
  const allRows = initialUniverse.flatMap((stock) => {
    const market = initialMarketData.stocks[stock.ticker]
    if (!market) return []
    const sustainableDps = stock.sustainableDpsOverride ?? market.trailingCashDps * stock.stabilityFactor
    const evaluation = evaluateStock({
      price: market.price,
      sustainableDps,
      requiredCashYield: stock.requiredCashYield,
      quality: stock.quality,
      payoutCoverage: stock.payoutCoverage,
      dataAgeDays: market.dataAgeDays,
    })
    const grossYield = grossedUpYield(evaluation.cashYield, stock.frankingFraction)
    const netYield = afterTaxYield(evaluation.cashYield, stock.frankingFraction, marginalTaxRate)
    const oneYearReturn = market.firstClose52w ? market.price / market.firstClose52w - 1 : 0
    const rangePosition = market.high52w && market.low52w && market.high52w > market.low52w
      ? (market.price - market.low52w) / (market.high52w - market.low52w)
      : 0.5
    return [{ stock, market, sustainableDps, evaluation, grossYield, netYield, oneYearReturn, rangePosition }]
  }).sort((a, b) => statusOrder[a.evaluation.status] - statusOrder[b.evaluation.status] || b.evaluation.score - a.evaluation.score)

  const normalizedQuery = query.trim().toLowerCase()
  const rows = normalizedQuery
    ? allRows.filter(({ stock }) => `${stock.ticker} ${stock.name}`.toLowerCase().includes(normalizedQuery))
    : allRows
  const buyCount = allRows.filter((row) => row.evaluation.status === 'BUY').length
  const watchCount = allRows.filter((row) => row.evaluation.status === 'WATCH').length
  const topYield = allRows.reduce((best, row) => Math.max(best, row.evaluation.cashYield), 0)
  const freshestDate = allRows[0]?.market.marketDate ?? '—'

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-mark"><Radar size={22} strokeWidth={2.2} /></div>
        <div className="brand-copy"><strong>ASX Income Radar</strong><span>澳洲高息股买点雷达</span></div>
        <div className="freshness"><Clock3 size={15} /> {freshestDate}</div>
      </header>

      <main>
        <section className="hero">
          <div>
            <div className="eyebrow"><Sparkles size={14} /> QUALITY BEFORE YIELD</div>
            <h1>不是找最高股息，<br />而是等<strong>好股息变便宜。</strong></h1>
            <p>用可持续股息、Franking、覆盖率、周期风险和硬买入价，把“高收益陷阱”与真正的收入机会分开。</p>
          </div>
          <div className="hero-orbit" aria-hidden="true"><span /><span /><span /></div>
        </section>

        <section className="summary-grid" aria-label="市场摘要">
          <article className="summary-card accent-green"><span><BadgeDollarSign size={17} />进入买入区</span><strong>{buyCount}</strong><small>达到质量与收益率双重门槛</small></article>
          <article className="summary-card accent-violet"><span><Radar size={17} />接近买点</span><strong>{watchCount}</strong><small>距离硬买入价不超过8%</small></article>
          <article className="summary-card accent-gold"><span><ArrowUpRight size={17} />最高可持续收益率</span><strong>{percent(topYield)}</strong><small>已按稳定系数调整</small></article>
          <article className="summary-card accent-blue"><span><ShieldCheck size={17} />监控股票</span><strong>{rows.length}</strong><small>银行、保险、REIT、基建及资源</small></article>
        </section>

        <section className="section-head">
          <div><p>VALUE BOARD</p><h2>按买入价值排序</h2></div>
          <div className="legend"><span className="dot buy" />买入区 <span className="dot watch" />接近买点 <span className="dot wait" />等待</div>
        </section>

        <div className="toolbar">
          <Search size={16} />
          <input
            aria-label="搜索股票"
            type="search"
            placeholder="搜索代码或公司，例如 CBA"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <span>{rows.length} / {allRows.length}</span>
        </div>

        <section className="stock-list">
          {rows.map(({ stock, market, sustainableDps, evaluation, grossYield, netYield, oneYearReturn, rangePosition }) => (
            <details className={`stock-card status-${evaluation.status.toLowerCase()}`} key={stock.ticker}>
              <summary>
                <div className="identity">
                  <div className="ticker">{stock.ticker.replace('.AX', '')}</div>
                  <div><h3>{stock.name}</h3><span>{stock.sector} · 质量 {stock.quality}</span></div>
                </div>
                <div className="price-block"><strong>{money(market.price)}</strong><span className={oneYearReturn >= 0 ? 'positive' : 'negative'}>{oneYearReturn >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}{percent(oneYearReturn)}</span></div>
                <div className="yield-block"><strong>{percent(evaluation.cashYield)}</strong><span>可持续现金收益率</span></div>
                <div className="buy-block"><strong>{money(evaluation.buyPrice)}</strong><span>硬买入价</span></div>
                <div className={`status-pill status-${evaluation.status.toLowerCase()}`}><b>{statusLabels[evaluation.status]}</b><span>{evaluation.score}分</span></div>
              </summary>
              <div className="detail-grid">
                <div className="metric"><span>过去12个月现金DPS</span><strong>{money(market.trailingCashDps)}</strong></div>
                <div className="metric"><span>模型可持续DPS</span><strong>{money(sustainableDps)}</strong></div>
                <div className="metric"><span>Franking调整毛收益率</span><strong>{percent(grossYield)}</strong></div>
                <div className="metric"><span>47%税率税后收益估算</span><strong>{percent(netYield)}</strong></div>
                <div className="range"><div><span>52周低 {market.low52w ? money(market.low52w) : '—'}</span><span>52周高 {market.high52w ? money(market.high52w) : '—'}</span></div><i><b style={{ width: `${Math.min(100, Math.max(0, rangePosition * 100))}%` }} /></i></div>
                <div className="risk"><AlertTriangle size={17} /><div><span>首要风险</span><p>{stock.risk}</p></div></div>
              </div>
            </details>
          ))}
        </section>

        <footer>
          <p>价格与股息事件来自Yahoo Finance图表接口；“可持续DPS”按证券类型进行保守折扣，特殊股息、资本返还、REIT税务构成及最新公司指引仍需在下单前复核。</p>
          <p>这是买点初筛工具，不构成个人投资建议。Franking税后收益按澳洲公司税率30%、个人边际税率47%估算。</p>
        </footer>
      </main>
    </div>
  )
}
