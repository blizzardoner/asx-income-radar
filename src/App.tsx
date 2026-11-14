import { useEffect, useState } from 'react'
import { AlertTriangle, ArrowUpRight, BadgeDollarSign, Clock3, Radar, Search, ShieldCheck, Sparkles } from 'lucide-react'
import { afterTaxYield, evaluateStock, grossedUpYield, type QualityGrade, type ValueStatus } from './domain/valueScore'
import { screenRows, type Screening, type ScreenerFilters } from './domain/screener'
import './styles.css'

export interface UniverseStock {
  ticker: string
  name: string
  sector: string
  type: string
  quality?: QualityGrade
  frankingFraction?: number
  requiredCashYield?: number
  stabilityFactor?: number
  payoutCoverage?: number
  isCore?: boolean
  isProxyHolding?: boolean
  holdingWeight?: number | null
  sustainableDpsOverride?: number
  dividendSource?: string
  risk?: string
}

export interface PriceChange {
  percent: number | null
  amount: number | null
  baselinePrice: number | null
  baselineDate: string | null
  targetDate: string
}

const pricePeriods = [{ key: 'day', label: '当天' }, { key: 'week', label: '过去一周' },
  { key: 'year', label: '过去一年' }] as const

export interface MarketStock {
  screening?: Screening
  franking?: { status: 'verified' | 'unknown'; rate: number | null; periodEnd?: string; sources: string[]; kind?: string; appliesTo?: string; reviewedOn?: string; reason?: string }
  disclosureUpdate?: { status: 'current' | 'needs_review' | 'unavailable'; checkedAt: string; latestRelevant?: { headline: string; date: string; url: string }; reason?: string }
  price: number
  previousClose?: number | null
  dailyChange?: number | null
  dailyChangePercent?: number | null
  priceChanges?: Partial<Record<'day' | 'week' | 'year', PriceChange>>
  currency: string
  marketDate: string
  dataAgeDays: number
  high52w: number | null
  low52w: number | null
  firstClose52w: number | null
  trailingCashDps: number
  annualOrdinaryCashDps?: number | null
  dividendBasis?: {
    status: string
    annualDpsAud: number | null
    kind?: 'reported' | 'guidance'
    periodEnd?: string
    announcedOn?: string
    validUntil?: string
    sources?: string[]
    reason?: string
    dps?: number | null
    currency?: string
    fx?: { rate: number; asOf: string; source: string }
  }
}

export interface MarketData {
  schemaVersion?: number
  universeStocks?: UniverseStock[]
  universe?: { kind: 'vas_proxy'; name: string; sourceUrl: string; asOf: string; retrievedAt: string; holdingCount: number; watchOnlyCount: number; excludedRows: number }
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
  UNVERIFIED: '股息待核实',
}


const money = (value: number | null) => value == null ? '—' : `A$${value.toFixed(2)}`
const percent = (value: number | null) => value == null ? '—' : `${(value * 100).toFixed(1)}%`
const validDate = (value: string | undefined): value is string => !!value && /^\d{4}-\d{2}-\d{2}$/.test(value)
  && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value
const changePercent = (value: number | null | undefined) => {
  if (value == null) return '—'
  const rounded = Number((value * 100).toFixed(2))
  return `${rounded > 0 ? '+' : ''}${rounded.toFixed(2)}%`
}

export default function App({ initialUniverse, initialMarketData }: AppProps) {
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState<ScreenerFilters>({ incomeOnly: true, scope: 'proxy', sort: 'history' })
  const setFilter = <K extends keyof ScreenerFilters>(key: K, value: ScreenerFilters[K]) => setFilters(current => ({ ...current, [key]: value }))
  const marginalTaxRate = 0.47
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const refresh = () => setNow(Date.now())
    const timer = window.setInterval(refresh, 60000)
    document.addEventListener('visibilitychange', refresh)
    window.addEventListener('focus', refresh)
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', refresh); window.removeEventListener('focus', refresh) }
  }, [])
  const asOf = new Intl.DateTimeFormat('en-CA', { timeZone: 'Australia/Sydney' }).format(new Date(now))
  const allRows = initialUniverse.flatMap((stock) => {
    const market = initialMarketData.stocks[stock.ticker]
    if (!market || !Number.isFinite(market.price) || market.price <= 0 || market.currency !== 'AUD') return []
    const basis = market.dividendBasis
    const disclosure = market.disclosureUpdate
    const checkedAt = disclosure?.checkedAt ?? ''
    const checkedTime = Date.parse(checkedAt)
    const checkNow = checkedAt.length === 10 ? Date.parse(asOf) : now
    const disclosureCurrent = disclosure ? disclosure.status === 'current'
      && validDate(checkedAt.slice(0, 10)) && Number.isFinite(checkedTime)
      && (checkedAt.length === 10 || /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(checkedAt))
      && checkedTime <= checkNow && checkNow - checkedTime <= 7 * 86400000
      : initialMarketData.schemaVersion !== 2
    const fxDate = basis?.fx?.asOf
    const fxTime = fxDate ? Date.parse(fxDate) : NaN
    const fxAge = (Date.parse(asOf) - fxTime) / 86400000
    const fxVerified = basis?.currency === 'AUD' || (basis?.fx != null
      && Number.isFinite(basis.fx.rate) && basis.fx.rate > 0
      && !!basis.fx.source?.trim()
      && /^\d{4}-\d{2}-\d{2}$/.test(fxDate ?? '') && Number.isFinite(fxTime)
      && new Date(fxTime).toISOString().slice(0, 10) === fxDate && fxAge >= 0 && fxAge <= 7)
    const ordinaryDps = basis?.status === 'verified' && validDate(basis.validUntil) && basis.validUntil >= asOf
      && validDate(basis.announcedOn) && basis.announcedOn <= asOf
      && validDate(basis.periodEnd) && (basis.kind === 'guidance' || basis.periodEnd <= basis.announcedOn)
      && !!basis.sources?.some(source => source.trim().length > 0)
      && disclosureCurrent
      && fxVerified
      && basis.annualDpsAud != null && Number.isFinite(basis.annualDpsAud) && basis.annualDpsAud >= 0
      ? basis.annualDpsAud : null
    const isCore = stock.isCore ?? stock.quality != null
    const sustainableDps = ordinaryDps == null || !isCore || stock.stabilityFactor == null ? null : ordinaryDps * stock.stabilityFactor
    const quoteAge = Math.floor((Date.parse(asOf) - Date.parse(market.marketDate)) / 86400000)
    const quoteAgeDays = validDate(market.marketDate) && Number.isFinite(quoteAge) && quoteAge >= 0
      && Number.isFinite(market.dataAgeDays) ? Math.max(market.dataAgeDays, quoteAge) : 99
    const evaluation = evaluateStock({
      price: market.price,
      sustainableDps,
      requiredCashYield: stock.requiredCashYield ?? 1,
      quality: stock.quality ?? 'C',
      payoutCoverage: stock.payoutCoverage ?? 0,
      dataAgeDays: quoteAgeDays,
    })
    const fr = market.franking
    const frankingRate = fr?.status === 'verified' && fr.rate != null && Number.isFinite(fr.rate) && fr.rate >= 0 && fr.rate <= 1
      && fr.kind === 'annual_ordinary' && (!fr.appliesTo || fr.appliesTo === 'annual_ordinary')
      && validDate(fr.reviewedOn) && fr.reviewedOn <= asOf
      && fr.sources.some(source => source.trim().length > 0) && fr.periodEnd === basis?.periodEnd && ordinaryDps != null ? fr.rate : null
    const grossYield = evaluation.cashYield == null || frankingRate == null ? null : grossedUpYield(evaluation.cashYield, frankingRate)
    const complexTax = ['infrastructure', 'reit'].includes(stock.type)
    const netYield = evaluation.cashYield == null || frankingRate == null || complexTax ? null : afterTaxYield(evaluation.cashYield, frankingRate, marginalTaxRate)

    const rangePosition = market.high52w && market.low52w && market.high52w > market.low52w
      ? (market.price - market.low52w) / (market.high52w - market.low52w)
      : 0.5
    return [{ stock, market, ordinaryDps, ordinaryYield: ordinaryDps == null || quoteAgeDays > 7 ? null : ordinaryDps / market.price,
      screening: market.screening, sustainableDps, evaluation, grossYield, netYield, frankingRate, complexTax, disclosureCurrent, rangePosition }]
  })

  const rows = screenRows(allRows, { ...filters, query })
  const proxyRows = allRows.filter(row => row.stock.isProxyHolding !== false)
  const proxyCount = initialMarketData.universe?.holdingCount ?? initialUniverse.filter(stock => stock.isProxyHolding !== false).length
  const verifiedCount = proxyRows.filter(row => row.ordinaryDps != null).length
  const reviewCount = proxyRows.filter(row => row.market.disclosureUpdate?.status === 'needs_review' && row.market.dividendBasis?.periodEnd).length
  const unavailable = initialUniverse.filter(stock => !allRows.some(row => row.stock.ticker === stock.ticker))
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
            <div className="eyebrow"><Sparkles size={14} /> EVIDENCE BEFORE YIELD</div>
            <h1>先看广度，<br />再核实<strong>每一份股息。</strong></h1>
            <p>历史现金收入只做初筛；经核实的普通年度股息与重点观察模型分开呈现，不把高分派直接当作买点。</p>
          </div>
          <div className="hero-orbit" aria-hidden="true"><span /><span /><span /></div>
        </section>

        <section className="summary-grid" aria-label="市场摘要">
          <article className="summary-card accent-green"><span><Radar size={17} />代理持仓数</span><strong>{proxyCount}</strong><small>实际持仓数量，不固定为300</small></article>
          <article className="summary-card accent-violet"><span><ArrowUpRight size={17} />报价覆盖</span><strong>{proxyRows.length} / {proxyCount}</strong><small>可用AUD报价；不代表实时</small></article>
          <article className="summary-card accent-gold"><span><ShieldCheck size={17} />已核实普通年度依据</span><strong>{verifiedCount}</strong><small>代理范围；有效财年与汇率守卫</small></article>
          <article className="summary-card accent-blue"><span><BadgeDollarSign size={17} />新披露待复核</span><strong>{reviewCount}</strong><small>未复核不触发买点</small></article>
        </section>
        <aside className="universe-note"><strong>ASX300代理（VAS持仓）</strong>
          <p>这是VAS官方持仓代理，不是标普／ASX300官方指数成分，数量、权重与时点可能不同。</p>
          {initialMarketData.universe ? <p><a href={initialMarketData.universe.sourceUrl} target="_blank" rel="noreferrer">VAS官方持仓来源</a> · 持仓截至 {initialMarketData.universe.asOf} · 获取 {initialMarketData.universe.retrievedAt} · 排除零权重行 {initialMarketData.universe.excludedRows}</p> : <p>持仓来源与日期待提供，不宣称覆盖官方指数。</p>}
        </aside>

        <section className="section-head">
          <div><p>INCOME SCREENER</p><h2>收入初筛 · 透明排序</h2></div>
          <span className="screen-count">{rows.length} 项符合筛选</span>
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
          <span>{rows.length} 项</span>
        </div>
        <div className="filter-grid" aria-label="筛选条件">
          <label>范围<select aria-label="范围" value={filters.scope} onChange={e => setFilter('scope', e.target.value as 'proxy' | 'core')}><option value="proxy">全部代理持仓</option><option value="core">重点观察（含代理外）</option></select></label>
          <label>行业<select aria-label="行业" value={filters.sector ?? ''} onChange={e => setFilter('sector', e.target.value)}><option value="">全部行业</option>{[...new Set(initialUniverse.map(s => s.sector))].sort().map(sector => <option key={sector}>{sector}</option>)}</select></label>
          <label>最低历史收益率（%）<input aria-label="最低历史收益率（%）" type="number" min="0" step="0.5" value={(filters.minHistoricalYield ?? 0) * 100} onChange={e => setFilter('minHistoricalYield', Math.max(0, Number(e.target.value)) / 100)} /></label>
          <label>最低历史派息年数<select aria-label="最低历史派息年数" value={filters.minPaidYears ?? 0} onChange={e => setFilter('minPaidYears', Number(e.target.value))}>{[0,1,2,3,4,5].map(year => <option key={year} value={year}>{year}年</option>)}</select></label>
          <label>最低日均成交额（A$）<input aria-label="最低日均成交额（A$）" type="number" min="0" step="100000" value={filters.minAverageDailyValue ?? 0} onChange={e => setFilter('minAverageDailyValue', Math.max(0, Number(e.target.value)))} /></label>
          <label>排序<select aria-label="排序" value={filters.sort} onChange={e => setFilter('sort', e.target.value as ScreenerFilters['sort'])}><option value="history">派息年数 → 历史收益率 → 流动性</option><option value="yield">历史现金分派收益率</option><option value="liquidity">日均成交额</option><option value="ordinary">已核实普通年度收益率</option></select></label>
          <label className="check-filter"><input type="checkbox" checked={filters.incomeOnly} onChange={e => setFilter('incomeOnly', e.target.checked)} />仅看有历史现金分派</label>
          <label className="check-filter"><input type="checkbox" checked={filters.verifiedOrdinaryOnly ?? false} onChange={e => setFilter('verifiedOrdinaryOnly', e.target.checked)} />仅看已核实普通年度股息</label>
        </div>
        <p className="method-note">默认按近5年派息年数降序，再按历史现金收益率、日均成交额降序，同值按代码。其他排序以选中指标优先；普通年度收益率不混入历史分派。成交额阈值大于0时排除未知值。历史分派含特别项目，不代表可持续或未来收入。</p>

        <section className="stock-list">
          {rows.length === 0 && <p className="empty-state">没有符合条件的股票，请放宽筛选。</p>}
          {rows.map(({ stock, market, ordinaryDps, ordinaryYield, sustainableDps, evaluation, grossYield, netYield, frankingRate, complexTax, disclosureCurrent, rangePosition }) => (
            <details className={`stock-card status-${evaluation.status.toLowerCase()}`} key={stock.ticker}>
              <summary>
                <div className="identity">
                  <div className="ticker">{stock.ticker.replace('.AX', '')}</div>
                  <div><h3>{stock.name}</h3><span>{stock.sector} · {stock.isCore ? stock.isProxyHolding === false ? '代理外重点观察' : '重点观察' : '广域初筛'}</span><span className="franking-label">Franking率：{frankingRate == null ? '未知' : percent(frankingRate)}</span></div>
                </div>
                <div className="price-block"><strong>{money(market.price)}</strong><span>{market.marketDate}</span></div>
                <div className="yield-block"><strong>{percent(market.screening?.historicalCashYield ?? null)}</strong><span>历史现金分派收益率（含特别）</span></div>
                <div className="buy-block"><strong>{percent(ordinaryYield)}</strong><span>已核实普通年度收益率</span></div>
                <div className={`status-pill status-${evaluation.status.toLowerCase()}`}><b>{stock.isCore || evaluation.status === 'STALE' ? statusLabels[evaluation.status] : ordinaryDps == null ? '股息待核实' : '仅作初筛'}</b><span>{stock.isCore ? '重点模型参考' : '无买点模型'}</span></div>
                <p className="rank-reason">排序依据：派息 {market.screening?.paidYears ?? '未知'}年 / 覆盖 {market.screening?.coveredYears ?? '未知'}年；历史 {percent(market.screening?.historicalCashYield ?? null)}；日均 {money(market.screening?.averageDailyValue ?? null)}；普通年度 {percent(ordinaryYield)}</p>
                <div className="price-periods" role="group" aria-label="股价变化">
                  {pricePeriods.map(({ key, label }) => {
                    const change = market.priceChanges?.[key]
                    return <div className="price-period" key={key}>
                      <span>{label}</span>
                      <strong className={change?.percent == null || changePercent(change.percent) === '0.00%' ? '' : change.percent > 0 ? 'positive' : 'negative'}>{changePercent(change?.percent)}</strong>
                    </div>
                  })}
                </div>
              </summary>
              <div className="detail-grid">
                <div className="metric"><span>现价</span><strong>{money(market.price)}</strong></div>
                <div className="metric"><span>可持续现金收益率</span><strong>{percent(evaluation.cashYield)}</strong></div>
                <div className="metric"><span>重点观察模型硬买入价</span><strong>{money(evaluation.buyPrice)}</strong></div>
                <div className="metric"><span>已核实普通年度收益率</span><strong>{percent(ordinaryYield)}</strong></div>
                <div className="metric"><span>日均成交额</span><strong>{money(market.screening?.averageDailyValue ?? null)}</strong><small>样本 {market.screening?.liquiditySessions ?? 0}个交易日；成交价 × 成交量均值，非保证可成交金额</small></div>
                <div className="history-panel"><h4>近5个日历年现金分派 / 每股AUD（含特别）</h4><div className="history-years">{market.screening?.annualCashDividends.map(item => <div key={item.year}><span>{item.year}</span><strong>{money(item.complete ? item.dps : null)}</strong><small>{item.complete ? '完整' : '不完整'}</small></div>) ?? <p>历史记录未知</p>}</div><p>按除息日归属；不等于财年普通股息。覆盖不完整时，不把缺失当作零。完整仅指历史数据覆盖检查，不保证全年无停牌、稳定派息或未来继续派息。</p></div>
                {pricePeriods.map(({ key, label }) => {
                  const change = market.priceChanges?.[key]
                  return <div className="metric price-baseline" key={key}><span>{label}基准收盘</span>
                    <strong>{money(change?.baselinePrice ?? null)}</strong>
                    <small>{change?.baselineDate ?? '历史数据不足'} · 不含股息</small></div>
                })}
                <div className="metric"><span>过去12个月现金分派（含特别）</span><strong>{money(market.trailingCashDps)}</strong></div>
                <div className="metric"><span>模型可持续DPS</span><strong>{money(sustainableDps)}</strong></div>
                <div className="metric"><span>Franking调整毛收益率</span><strong>{percent(grossYield)}</strong><small>仅作现金＋抵税额参考，假设公司税率30%；不是实际到手现金。</small></div>
                <div className="metric"><span>假设边际税率47%：税后收益估算</span><strong>{percent(netYield)}</strong><small>{complexTax ? '税后无法估算：税务成分复杂，可能包含递延、利息或其他成分，须依个人年度税单。' : '情景假设，不是你的实际税率或个人税务建议；Franking未知时不估算。'}</small></div>
                <div className="metric"><span>现金收益率计算</span><strong>{money(sustainableDps)} ÷ {money(market.price)}</strong></div>
                <div className="income-basis">
                  <div><span>{market.dividendBasis?.kind === 'guidance' ? '普通年度股息指引（非保证）' : ['reit', 'infrastructure'].includes(stock.type) ? '披露年度经常性现金分派' : '披露普通年度股息'}</span>
                    <strong>{money(ordinaryDps)} · 财年截至 {market.dividendBasis?.periodEnd ?? '待核实'}</strong></div>
                  <p>{sustainableDps == null ? market.dividendBasis?.reason ?? '股息依据缺失或超过有效期，不计算买点。' : '按披露财年归属，不按除息日窗口或派息笔数推断；模型再乘稳定系数。'}</p>
                  <small>公布 {market.dividendBasis?.announcedOn ?? '—'} · 复核有效期至 {market.dividendBasis?.validUntil ?? '—'}</small>
                  {ordinaryDps != null && market.dividendBasis?.fx && <small>USD股息按 {market.dividendBasis.fx.asOf} 汇率 × {market.dividendBasis.fx.rate.toFixed(4)} 换算为AUD，非历史实际到账金额。</small>}
                  <div className="income-sources">{market.dividendBasis?.sources?.map((source, index) => <a href={source} key={source} target="_blank" rel="noreferrer">披露来源 {index + 1}</a>)}</div>
                  <div className="income-sources">{frankingRate != null && market.franking?.sources.map((source, index) => <a href={source} key={source} target="_blank" rel="noreferrer">Franking来源 {index + 1}</a>)}</div>
                  {frankingRate != null && <small>Franking率为对应年度现金分派的加权比例，不是最近一笔派息的比例。</small>}
                </div>
                <div className="disclosure-panel"><strong>披露更新：{market.disclosureUpdate?.status === 'current' ? disclosureCurrent ? '已检查' : '检查过期或无效' : market.disclosureUpdate?.status === 'needs_review' ? market.dividendBasis?.periodEnd ? '新披露待复核' : '年度股息待复核' : '检查不可用'}</strong>
                  <p>{market.disclosureUpdate?.reason ?? '披露检查状态未知；请查阅原始公告。'} · 检查 {market.disclosureUpdate?.checkedAt ?? '未知'}</p>
                  {market.disclosureUpdate?.latestRelevant && <a href={market.disclosureUpdate.latestRelevant.url} target="_blank" rel="noreferrer">{market.disclosureUpdate.latestRelevant.date} · {market.disclosureUpdate.latestRelevant.headline}</a>}
                </div>
                <div className="range"><div><span>52周低 {market.low52w ? money(market.low52w) : '—'}</span><span>52周高 {market.high52w ? money(market.high52w) : '—'}</span></div><i><b style={{ width: `${Math.min(100, Math.max(0, rangePosition * 100))}%` }} /></i></div>
                <div className="risk"><AlertTriangle size={17} /><div><span>首要风险</span><p>{stock.risk ?? '尚未完成个股风险复核；历史高分派可能含一次性项目。'}</p></div></div>
              </div>
            </details>
          ))}
        </section>

        <aside className="unavailable-panel" aria-label="行情不可用">
          <h3>行情不可用：{unavailable.length} 项</h3><p>这些持仓未被静默删除；不参与收益率排名。包括缺失、无效或非AUD报价。</p>
          <ul>{unavailable.map(stock => <li key={stock.ticker}><strong>{stock.ticker} · {stock.name}</strong><span>{initialMarketData.failures.find(item => item.ticker === stock.ticker)?.error ?? '报价缺失或不适用'}</span></li>)}</ul>
        </aside>
        <footer>
          <p>当天以上一交易日收盘价为基准；过去一周／一年以报价日往前7天／周年日为目标，休市取此前最近收盘价（最多回溯7天），历史不足显示“—”。价格变化均不含股息，拆股调整价格不再重复调整。</p>
          <p>历史现金分派来自Yahoo Finance，按澳洲除息日统计12个日历月；模型只采用有来源的完整财年普通股息／经常性分派或明确的普通年度指引，再乘稳定系数，不默认一年派两次或四次。未核实或过期的依据不触发买入提醒。历史财年基数不保证未来收入；新财报、特别分派和指引变更需要更新披露记录，REIT分派包含经常性税务递延构成。</p>
          <p>这是买点初筛工具，不构成个人投资建议。Franking税后收益按澳洲公司税率30%、个人边际税率47%估算。</p>
        </footer>
      </main>
    </div>
  )
}
