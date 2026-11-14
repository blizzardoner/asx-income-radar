import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
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
  isCore: true,
  isProxyHolding: true,
  holdingWeight: .01,
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
      screening: { historicalCashYield: .0766, averageDailyValue: 2000000, liquiditySessions: 60, paidYears: 5, coveredYears: 5,
        annualCashDividends: [2021,2022,2023,2024,2025].map(year => ({ year, dps: .72, complete: year !== 2021 })) },
      annualOrdinaryCashDps: 0.72,
      dividendBasis: { status: 'verified' as const, annualDpsAud: 0.72, dps: 0.72,
        currency: 'AUD', kind: 'reported' as const, periodEnd: '2026-06-30',
        announcedOn: '2026-08-01', validUntil: '2099-01-01',
        sources: ['https://company.example/fy26'] },
    },
  },
}

describe('App', () => {
  it('does not call an unreviewed annual basis a new disclosure', () => {
    render(<App initialUniverse={[{ ...universe[0], risk: undefined }]} initialMarketData={{ ...marketData, stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'], dividendBasis: undefined,
      disclosureUpdate: { status: 'needs_review', checkedAt: '2026-11-14' } } } }} />)
    expect(within(screen.getByLabelText('市场摘要')).getByText('新披露待复核').closest('article')?.querySelector('strong')).toHaveTextContent('0')
    expect(screen.getByText('披露更新：年度股息待复核')).toBeInTheDocument()
    expect(screen.getByText('尚未完成个股风险复核；历史高分派可能含一次性项目。')).toBeInTheDocument()
  })
  it('shows incomplete zero history as unknown and labels watch-only holdings outside the proxy', () => {
    const base = marketData.stocks['TEST.AX']
    render(<App initialUniverse={[{ ...universe[0], isProxyHolding: false }]} initialMarketData={{ ...marketData, stocks: { 'TEST.AX': { ...base,
      screening: { ...base.screening, annualCashDividends: [{ year: 2021, dps: 0, complete: false }] } } } }} />)
    fireEvent.change(screen.getByLabelText('范围'), { target: { value: 'core' } })
    expect(screen.getByText(/代理外重点观察/)).toBeInTheDocument()
    expect(screen.getByText('2021').parentElement?.querySelector('strong')).toHaveTextContent('—')
  })
  it.each([
    { kind: 'latest_payment', reviewedOn: '2026-11-14' },
    { kind: 'annual_ordinary', reviewedOn: '2026-11-15' },
    { kind: 'annual_ordinary', reviewedOn: 'not-a-date' },
    { kind: 'annual_ordinary', reviewedOn: undefined },
    { kind: undefined, reviewedOn: '2026-11-14' },
  ])('rejects cached franking without valid annual review metadata %j', metadata => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData, stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'],
      franking: { status: 'verified', rate: 1, periodEnd: '2026-06-30', sources: ['https://company.example/fr'], ...metadata } } } }} />)
    expect(screen.getByText('Franking率：未知')).toBeInTheDocument()
    expect(screen.getByText('Franking调整毛收益率').parentElement?.querySelector('strong')).toHaveTextContent('—')
  })
  it.each(['2026-11-01', '2026-11-15', '2026-02-31'])('marks a broad holding quote %s stale and excludes its ordinary yield from verification filters', marketDate => {
    render(<App initialUniverse={[{ ...universe[0], isCore: false }]} initialMarketData={{ ...marketData, stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'], marketDate, dataAgeDays: 0 } } }} />)
    expect(screen.getByText('数据过期')).toBeInTheDocument()
    expect(document.querySelector('.buy-block strong')).toHaveTextContent('—')
    fireEvent.click(screen.getByLabelText('仅看已核实普通年度股息'))
    expect(screen.queryByText('TEST')).not.toBeInTheDocument()
  })
  it.each(['infrastructure', 'reit'])('does not apply an all-cash taxable net yield formula to %s distributions', type => {
    render(<App initialUniverse={[{ ...universe[0], type }]} initialMarketData={{ ...marketData, stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'],
      franking: { status: 'verified', kind: 'annual_ordinary', reviewedOn: '2026-11-14', rate: .27401, periodEnd: '2026-06-30', sources: ['https://company.example/tax'] } } } }} />)
    expect(screen.getByText('假设边际税率47%：税后收益估算').parentElement?.querySelector('strong')).toHaveTextContent('—')
    expect(screen.getByText(/税后无法估算：税务成分复杂/)).toBeInTheDocument()
    expect(screen.getByText('Franking率：27.4%')).toBeInTheDocument()
  })
  it('wires broad filters, allows zero-income holdings, and includes watch-only names only in core scope', () => {
    const stocks = [
      { ...universe[0], ticker: 'A.AX', name: 'Alpha', isCore: true },
      { ...universe[0], ticker: 'B.AX', name: 'Beta', sector: 'Mining', isCore: false },
      { ...universe[0], ticker: 'ZERO.AX', name: 'Zero', isCore: false },
      { ...universe[0], ticker: 'OUT.AX', name: 'Outside', isProxyHolding: false },
    ]
    const base = marketData.stocks['TEST.AX']
    render(<App initialUniverse={stocks} initialMarketData={{ ...marketData, stocks: {
      'A.AX': base, 'B.AX': { ...base, dividendBasis: undefined, screening: { ...base.screening, paidYears: 2, historicalCashYield: .12, averageDailyValue: null } },
      'ZERO.AX': { ...base, screening: { ...base.screening, historicalCashYield: 0, paidYears: 0 } }, 'OUT.AX': base,
    } }} />)
    const tickers = () => [...document.querySelectorAll('.ticker')].map(e => e.textContent)
    expect(tickers()).toEqual(['A','B'])
    fireEvent.change(screen.getByLabelText('排序'), { target: { value: 'yield' } })
    expect(tickers()).toEqual(['B','A'])
    fireEvent.change(screen.getByLabelText('排序'), { target: { value: 'ordinary' } })
    expect(tickers()).toEqual(['A','B'])
    fireEvent.click(screen.getByLabelText('仅看有历史现金分派'))
    expect(tickers()).toContain('ZERO')
    fireEvent.click(screen.getByLabelText('仅看有历史现金分派'))
    fireEvent.change(screen.getByLabelText('最低日均成交额（A$）'), { target: { value: '1' } })
    expect(tickers()).toEqual(['A'])
    fireEvent.change(screen.getByLabelText('最低日均成交额（A$）'), { target: { value: '0' } })
    fireEvent.change(screen.getByLabelText('行业'), { target: { value: 'Mining' } })
    expect(tickers()).toEqual(['B'])
    fireEvent.change(screen.getByLabelText('行业'), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText('最低历史收益率（%）'), { target: { value: '10' } })
    expect(tickers()).toEqual(['B'])
    fireEvent.change(screen.getByLabelText('最低历史收益率（%）'), { target: { value: '0' } })
    fireEvent.change(screen.getByLabelText('最低历史派息年数'), { target: { value: '5' } })
    expect(tickers()).toEqual(['A'])
    fireEvent.change(screen.getByLabelText('最低历史派息年数'), { target: { value: '0' } })
    fireEvent.click(screen.getByLabelText('仅看已核实普通年度股息'))
    expect(tickers()).toEqual(['A'])
    fireEvent.change(screen.getByLabelText('范围'), { target: { value: 'core' } })
    expect(tickers()).toEqual(['A','OUT'])
  })
  it('accepts sourced forward ordinary annual guidance without pretending it is a reported fiscal year', () => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData, stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'], marketDate: '2026-11-14',
      dividendBasis: { ...marketData.stocks['TEST.AX'].dividendBasis, kind: 'guidance', periodEnd: '2027-06-30' } } } }} />)
    expect(screen.getByText('普通年度股息指引（非保证）')).toBeInTheDocument()
    expect(screen.getByText('买入区')).toBeInTheDocument()
  })
  it('requires a disclosure check in schema 2 but preserves legacy snapshot compatibility', () => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData, schemaVersion: 2 }} />)
    expect(screen.queryByText('买入区')).not.toBeInTheDocument()
  })
  it.each(['2026-11-07', '2026-11-14T00:00:00Z', '2026-11-14T11:00:00+11:00',
    '2026-11-14T00:00:00.123456Z', '2026-11-14T11:00:00.123456+11:00',
    '2026-11-07T01:00:00Z'])('accepts a current disclosure check at %s', checkedAt => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData, schemaVersion: 2, stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'],
      disclosureUpdate: { status: 'current', checkedAt } } } }} />)
    expect(screen.getByText('买入区')).toBeInTheDocument()
  })
  it.each(['2026-11-14T00:00:00', '2026-11-14T00:00:00.123456'])('rejects a schema 2 disclosure datetime without an explicit timezone: %s', checkedAt => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData, schemaVersion: 2, stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'],
      disclosureUpdate: { status: 'current', checkedAt } } } }} />)
    const card = screen.getByText('TEST').closest('details')!
    expect(card).toHaveClass('status-unverified')
    expect(within(card).queryByText('买入区')).not.toBeInTheDocument()
    expect(within(card).getByText('股息待核实')).toBeInTheDocument()
    expect(within(card).getByText('披露更新：检查过期或无效')).toBeInTheDocument()
  })
  it.each(['2026-11-14T01:00:01Z', '2026-11-07T00:59:59Z', '2026-02-31T00:00:00Z'])('rejects a future, too-old or invalid disclosure timestamp: %s', checkedAt => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData, schemaVersion: 2, stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'],
      disclosureUpdate: { status: 'current', checkedAt } } } }} />)
    expect(screen.getByText('TEST').closest('details')).toHaveClass('status-unverified')
    expect(screen.queryByText('买入区')).not.toBeInTheDocument()
  })
  it.each([1, 2])('preserves date-only disclosure calendar handling in schema %s', schemaVersion => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData, schemaVersion, stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'],
      disclosureUpdate: { status: 'current', checkedAt: '2026-11-07' } } } }} />)
    expect(screen.getByText('TEST').closest('details')).toHaveClass('status-buy')
  })
  it.each(['2026-11-06', '2026-11-15', 'not-a-date'])('blocks cached annual basis when disclosure check date is %s', checkedAt => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData, stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'], marketDate: '2026-11-14',
      disclosureUpdate: { status: 'current', checkedAt } } } }} />)
    expect(screen.queryByText('买入区')).not.toBeInTheDocument()
    expect(screen.getByText('股息待核实')).toBeInTheDocument()
    expect(screen.getByText('披露更新：检查过期或无效')).toBeInTheDocument()
  })
  it('rechecks the Sydney date on a timer while the app remains open across midnight', () => {
    vi.setSystemTime(new Date('2026-11-14T12:59:30Z'))
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData, stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'], marketDate: '2026-11-14',
      dividendBasis: { ...marketData.stocks['TEST.AX'].dividendBasis, validUntil: '2026-11-14' } } } }} />)
    expect(screen.getByText('买入区')).toBeInTheDocument()
    act(() => { vi.advanceTimersByTime(60000) })
    expect(screen.queryByText('买入区')).not.toBeInTheDocument()
    expect(screen.getByText('股息待核实')).toBeInTheDocument()
  })
  it('rechecks stale offline quotes when returning to the tab without a timer firing', () => {
    render(<App initialUniverse={universe} initialMarketData={marketData} />)
    expect(screen.getByText('买入区')).toBeInTheDocument()
    act(() => { vi.setSystemTime(new Date('2026-11-16T01:00:00Z')); document.dispatchEvent(new Event('visibilitychange')) })
    expect(screen.queryByText('买入区')).not.toBeInTheDocument()
    expect(screen.getByText('数据过期')).toBeInTheDocument()
  })
  it.each([
    ['missing', undefined],
    ['unknown despite legacy 100%', { status: 'unknown' as const, rate: null, sources: [] }],
    ['wrong fiscal period', { status: 'verified' as const, rate: 1, periodEnd: '2025-06-30', sources: ['https://company.example/fr'] }],
    ['missing source', { status: 'verified' as const, rate: 1, periodEnd: '2026-06-30', sources: [] }],
    ['blank source', { status: 'verified' as const, rate: 1, periodEnd: '2026-06-30', sources: [''] }],
    ['invalid fraction', { status: 'verified' as const, rate: 1.1, periodEnd: '2026-06-30', sources: ['https://company.example/fr'] }],
  ])('does not estimate gross or net income with %s franking', (_label, franking) => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData, stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'], franking: franking ? { kind: 'annual_ordinary', reviewedOn: '2026-11-14', ...franking } : undefined } } }} />)
    expect(screen.getByText('Franking率：未知')).toBeInTheDocument()
    for (const label of ['Franking调整毛收益率', '假设边际税率47%：税后收益估算']) expect(screen.getByText(label).parentElement?.querySelector('strong')).toHaveTextContent('—')
  })
  it.each([[0, '0.0%', '7.7%', '4.1%'], [.5, '50.0%', '9.3%', '4.9%'], [1, '100.0%', '10.9%', '5.8%']])('supports exact verified franking rate %s, including real zero', (rate, label, gross, net) => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData, stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'],
      franking: { status: 'verified', kind: 'annual_ordinary', reviewedOn: '2026-11-14', rate: Number(rate), periodEnd: '2026-06-30', sources: ['https://company.example/fr'] } } } }} />)
    expect(screen.getByText(`Franking率：${label}`)).toBeInTheDocument()
    expect(screen.getByText('Franking调整毛收益率').parentElement?.querySelector('strong')).toHaveTextContent(String(gross))
    expect(screen.getByText('假设边际税率47%：税后收益估算').parentElement?.querySelector('strong')).toHaveTextContent(String(net))
    expect(screen.getByRole('link', { name: 'Franking来源 1' })).toHaveAttribute('href', 'https://company.example/fr')
  })
  it.each(['needs_review', 'unavailable'] as const)('blocks cached verified annual basis when disclosure check is %s', status => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData, stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'], marketDate: '2026-11-14',
      disclosureUpdate: { status, checkedAt: '2026-11-14', reason: '新披露需复核', latestRelevant: { headline: 'New annual result', date: '2026-11-13', url: 'https://company.example/new' } } } } }} />)
    expect(screen.queryByText('买入区')).not.toBeInTheDocument()
    expect(screen.getByText('股息待核实')).toBeInTheDocument()
    expect(screen.getByText(/新披露需复核/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /New annual result/ })).toHaveAttribute('href', 'https://company.example/new')
  })
  it.each([
    { sources: [] }, { sources: [''] }, { periodEnd: '' }, { periodEnd: '2026-02-31' }, { announcedOn: '2026-02-31' }, { validUntil: '2099-99-99' }, { periodEnd: '2027-06-30' },
  ])('rejects source or fiscal/date invalid verified annual basis %j', override => {
    render(<App initialUniverse={universe} initialMarketData={{ ...marketData, stocks: { 'TEST.AX': { ...marketData.stocks['TEST.AX'], marketDate: '2026-11-14',
      dividendBasis: { ...marketData.stocks['TEST.AX'].dividendBasis, ...override } } } }} />)
    expect(screen.getByText('股息待核实')).toBeInTheDocument()
    expect(screen.queryByText('买入区')).not.toBeInTheDocument()
  })
  it('shows the dated official proxy, priced coverage, transparent broad ranking and unavailable names', () => {
    const newcomer = { ticker: 'NEW.AX', name: 'New Proxy', sector: 'Mining', type: 'equity', isCore: false, isProxyHolding: true, holdingWeight: .002 }
    render(<App initialUniverse={[...universe, newcomer, { ...newcomer, ticker: 'FAIL.AX', name: 'Failed Quote' }]}
      initialMarketData={{ ...marketData, universe: { kind: 'vas_proxy', name: 'VAS', sourceUrl: 'https://vanguard.example/holdings', asOf: '2026-10-31', retrievedAt: '2026-11-14', holdingCount: 3, watchOnlyCount: 0, excludedRows: 2 },
        failures: [{ ticker: 'FAIL.AX', error: 'quote unavailable' }], stocks: { ...marketData.stocks, 'NEW.AX': { ...marketData.stocks['TEST.AX'], dividendBasis: undefined } } }} />)
    expect(screen.getByText('ASX300代理（VAS持仓）')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /VAS官方持仓/ })).toHaveAttribute('href', 'https://vanguard.example/holdings')
    expect(screen.getByText(/2026-10-31/)).toBeInTheDocument()
    expect(screen.getByText(/不是标普/)).toBeInTheDocument()
    expect(screen.getByText('2 / 3')).toBeInTheDocument()
    expect(screen.getByText('FAIL.AX · Failed Quote')).toBeInTheDocument()
    const card = screen.getByText('NEW').closest('details')!
    expect(within(card).queryByText('买入区')).not.toBeInTheDocument()
    expect(within(card).getByText(/排序依据/)).toHaveTextContent('5年')
    expect(within(card).getByText('历史现金分派收益率（含特别）')).toBeInTheDocument()
    expect(within(card).getByText('2021')).toBeInTheDocument()
    expect(within(card).getByText('不完整')).toBeInTheDocument()
    expect(within(card).getByText(/60个交易日/)).toBeInTheDocument()
    expect(within(card).getByText('Franking率：未知')).toBeInTheDocument()
    expect(screen.queryByText(/\d+分$/)).not.toBeInTheDocument()
  })
  it.each([
    ['expired', { rate: 1.5, asOf: '2026-11-06', source: 'test' }],
    ['future', { rate: 1.5, asOf: '2026-11-15', source: 'test' }],
    ['missing date', { rate: 1.5, asOf: '', source: 'test' }],
    ['invalid date', { rate: 1.5, asOf: 'not-a-date', source: 'test' }],
    ['missing FX', undefined],
    ['missing source', { rate: 1.5, asOf: '2026-11-14', source: '' }],
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
    expect(within(card).getByText('可持续现金收益率').parentElement?.querySelector('strong')).toHaveTextContent('—')
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

    expect(screen.getByText('可持续现金收益率').parentElement?.querySelector('strong')).toHaveTextContent('7.7%')
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
    expect(screen.getByText('可持续现金收益率').parentElement?.querySelector('strong')).toHaveTextContent('7.7%')
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
