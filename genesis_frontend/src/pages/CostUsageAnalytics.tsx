import { FormEvent, useEffect, useMemo, useState } from 'react'
import { clsx } from 'clsx'
import {
  ArrowRight,
  Coins,
  DollarSign,
  Gauge,
  Layers,
  RefreshCw,
  Search,
  TrendingUp,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import {
  GenesisApi,
  type CostUsageOverviewResponse,
  type CostUsageResourceDetailResponse,
  type CostUsageResourceItem,
  type CostUsageResourceListResponse,
} from '../services/api'
import { useLanguage } from '../i18n/language'

type DatePreset = '7D' | '30D' | 'CUSTOM'

const formatMoney = (value: number) => `$${value.toFixed(3)}`

const toInputDate = (value: Date) => {
  const year = value.getUTCFullYear()
  const month = `${value.getUTCMonth() + 1}`.padStart(2, '0')
  const day = `${value.getUTCDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

const buildRange = (preset: DatePreset, customFrom: string, customTo: string) => {
  if (preset === 'CUSTOM') {
    return { date_from: customFrom || undefined, date_to: customTo || undefined, window_days: undefined }
  }
  const now = new Date()
  const days = preset === '7D' ? 7 : 30
  const from = new Date(now.getTime() - days * 24 * 3600 * 1000)
  return {
    date_from: toInputDate(from),
    date_to: toInputDate(now),
    window_days: undefined,
  }
}

const CostUsageAnalytics = () => {
  const navigate = useNavigate()
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const [overview, setOverview] = useState<CostUsageOverviewResponse | null>(null)
  const [resourcesResp, setResourcesResp] = useState<CostUsageResourceListResponse | null>(null)
  const [detail, setDetail] = useState<CostUsageResourceDetailResponse | null>(null)
  const [selectedResourceKey, setSelectedResourceKey] = useState<string | null>(null)

  const [loadingOverview, setLoadingOverview] = useState(false)
  const [loadingResources, setLoadingResources] = useState(false)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [filters, setFilters] = useState({
    scope: 'PROJECT',
    project_id: '',
    module: 'ALL',
    resource_type: 'ALL',
    granularity: 'DAY',
    sort_by: 'COST',
    q: '',
    date_preset: '30D' as DatePreset,
    date_from: toInputDate(new Date(Date.now() - 30 * 24 * 3600 * 1000)),
    date_to: toInputDate(new Date()),
  })

  const selectedResource = useMemo(() => {
    if (!resourcesResp || !selectedResourceKey) {
      return null
    }
    return (
      resourcesResp.items.find((item) => `${item.project_id}:${item.source_type}:${item.source_id}` === selectedResourceKey) ?? null
    )
  }, [resourcesResp, selectedResourceKey])

  const moduleOptions = useMemo(
    () => ['ALL', ...(overview?.filters.modules ?? [])],
    [overview?.filters.modules],
  )
  const resourceTypeOptions = useMemo(
    () => ['ALL', ...(overview?.filters.resource_types ?? [])],
    [overview?.filters.resource_types],
  )

  const queryParams = useMemo(() => {
    const range = buildRange(filters.date_preset, filters.date_from, filters.date_to)
    return {
      scope: filters.scope,
      project_id: filters.project_id ? Number(filters.project_id) : undefined,
      module: filters.module === 'ALL' ? undefined : filters.module,
      resource_type: filters.resource_type === 'ALL' ? undefined : filters.resource_type,
      granularity: filters.granularity,
      q: filters.q.trim() || undefined,
      sort_by: filters.sort_by,
      date_from: range.date_from,
      date_to: range.date_to,
      window_days: range.window_days,
    }
  }, [filters])

  const loadOverview = async () => {
    setLoadingOverview(true)
    try {
      const data = await GenesisApi.getCostUsageOverview({
        scope: queryParams.scope,
        project_id: queryParams.project_id,
        module: queryParams.module,
        resource_type: queryParams.resource_type,
        granularity: queryParams.granularity,
        date_from: queryParams.date_from,
        date_to: queryParams.date_to,
        window_days: queryParams.window_days,
      })
      setOverview(data)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? (isZh ? '加载成本总览失败' : 'Failed to load cost usage overview'))
    } finally {
      setLoadingOverview(false)
    }
  }

  const loadResources = async () => {
    setLoadingResources(true)
    try {
      const data = await GenesisApi.getCostUsageResources({
        scope: queryParams.scope,
        project_id: queryParams.project_id,
        module: queryParams.module,
        resource_type: queryParams.resource_type,
        q: queryParams.q,
        sort_by: queryParams.sort_by,
        date_from: queryParams.date_from,
        date_to: queryParams.date_to,
        window_days: queryParams.window_days,
        limit: 120,
        offset: 0,
      })
      setResourcesResp(data)
      if (!selectedResourceKey && data.items.length > 0) {
        setSelectedResourceKey(`${data.items[0].project_id}:${data.items[0].source_type}:${data.items[0].source_id}`)
      }
      if (
        selectedResourceKey &&
        !data.items.some((item) => `${item.project_id}:${item.source_type}:${item.source_id}` === selectedResourceKey)
      ) {
        setSelectedResourceKey(
          data.items[0] ? `${data.items[0].project_id}:${data.items[0].source_type}:${data.items[0].source_id}` : null,
        )
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? (isZh ? '加载资源成本失败' : 'Failed to load resource costs'))
    } finally {
      setLoadingResources(false)
    }
  }

  const loadDetail = async (resource: CostUsageResourceItem) => {
    setLoadingDetail(true)
    try {
      const data = await GenesisApi.getCostUsageResourceDetail(resource.source_type, resource.source_id, {
        scope: queryParams.scope,
        project_id: resource.project_id,
        date_from: queryParams.date_from,
        date_to: queryParams.date_to,
        window_days: queryParams.window_days,
        granularity: queryParams.granularity,
      })
      setDetail(data)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? (isZh ? '加载资源详情失败' : 'Failed to load resource detail'))
      setDetail(null)
    } finally {
      setLoadingDetail(false)
    }
  }

  useEffect(() => {
    void Promise.all([loadOverview(), loadResources()])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (selectedResource) {
      void loadDetail(selectedResource)
    } else {
      setDetail(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedResourceKey, resourcesResp])

  const applyFilters = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    await Promise.all([loadOverview(), loadResources()])
  }

  const refreshAll = async () => {
    await Promise.all([loadOverview(), loadResources()])
    if (selectedResource) {
      await loadDetail(selectedResource)
    }
  }

  const jumpToRoute = (route: string, resource: CostUsageResourceItem) => {
    const params = new URLSearchParams({
      source_type: resource.source_type,
      source_id: resource.source_id,
    })
    navigate(`${route}?${params.toString()}`)
  }

  return (
    <div className="max-w-7xl mx-auto space-y-4 animate-in fade-in slide-in-from-bottom-8 duration-700">
      <section className="rounded-2xl border border-slate-200 bg-white/80 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-900">{isZh ? '下一步建议' : 'Recommended Next Step'}</p>
            <p className="text-xs text-slate-600">
              {isZh ? '识别 Top 成本资源后，回到管道和质量模块做针对性优化。' : 'After identifying top cost resources, optimize related pipelines and DQ rules.'}
            </p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => navigate('/pipelines')} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs hover:bg-slate-50">
              {isZh ? '去管道' : 'Go Pipelines'}
            </button>
            <button onClick={() => navigate('/data-quality')} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs hover:bg-slate-50">
              {isZh ? '去数据质量' : 'Go Data Quality'}
            </button>
          </div>
        </div>
      </section>
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">{isZh ? '成本与用量分析' : 'Cost & Usage Analytics'}</h2>
          <p className="text-slate-500 text-base">
            Analyze spend by module/resource, identify high-cost objects, and jump to optimization actions.
          </p>
        </div>
        <button
          onClick={() => void refreshAll()}
          disabled={loadingOverview || loadingResources || loadingDetail}
          className="rounded-xl bg-slate-900 text-white px-4 py-2.5 font-medium hover:bg-slate-800 disabled:opacity-60 flex items-center gap-2"
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </header>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}

      <form onSubmit={applyFilters} className="glass rounded-3xl border border-slate-200/60 p-4">
        <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
          <select
            value={filters.scope}
            onChange={(e) => setFilters((prev) => ({ ...prev, scope: e.target.value }))}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
          >
            <option value="PROJECT">PROJECT</option>
            <option value="TENANT">TENANT</option>
          </select>
          <select
            value={filters.module}
            onChange={(e) => setFilters((prev) => ({ ...prev, module: e.target.value }))}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
          >
            {moduleOptions.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select
            value={filters.resource_type}
            onChange={(e) => setFilters((prev) => ({ ...prev, resource_type: e.target.value }))}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
          >
            {resourceTypeOptions.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select
            value={filters.granularity}
            onChange={(e) => setFilters((prev) => ({ ...prev, granularity: e.target.value }))}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
          >
            <option value="DAY">DAY</option>
            <option value="HOUR">HOUR</option>
          </select>
          <select
            value={filters.sort_by}
            onChange={(e) => setFilters((prev) => ({ ...prev, sort_by: e.target.value }))}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
          >
            <option value="COST">COST</option>
            <option value="USAGE">USAGE</option>
            <option value="NAME">NAME</option>
            <option value="UPDATED">UPDATED</option>
          </select>
          <select
            value={filters.date_preset}
            onChange={(e) => setFilters((prev) => ({ ...prev, date_preset: e.target.value as DatePreset }))}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
          >
            <option value="7D">Last 7 days</option>
            <option value="30D">Last 30 days</option>
            <option value="CUSTOM">Custom</option>
          </select>
          <input
            value={filters.project_id}
            onChange={(e) => setFilters((prev) => ({ ...prev, project_id: e.target.value }))}
            placeholder="project_id (optional)"
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
          />
          <div className="relative md:col-span-2">
            <Search size={14} className="absolute left-2.5 top-2.5 text-slate-400" />
            <input
              value={filters.q}
              onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))}
              placeholder="search resource / project / driver"
              className="w-full rounded-xl border border-slate-200 bg-white pl-8 pr-3 py-2 text-sm"
            />
          </div>
          {filters.date_preset === 'CUSTOM' && (
            <>
              <input
                type="date"
                value={filters.date_from}
                onChange={(e) => setFilters((prev) => ({ ...prev, date_from: e.target.value }))}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
              />
              <input
                type="date"
                value={filters.date_to}
                onChange={(e) => setFilters((prev) => ({ ...prev, date_to: e.target.value }))}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
              />
            </>
          )}
          <button type="submit" className="rounded-xl bg-cyan-600 text-white px-4 py-2 text-sm font-semibold">
            Apply Filters
          </button>
        </div>
      </form>

      <section className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Total Cost</p>
          <p className="text-2xl font-bold text-slate-900">{formatMoney(overview?.summary.total_cost ?? 0)}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Compute</p>
          <p className="text-2xl font-bold text-cyan-700">{formatMoney(overview?.summary.cost_components.compute ?? 0)}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Storage</p>
          <p className="text-2xl font-bold text-indigo-700">{formatMoney(overview?.summary.cost_components.storage ?? 0)}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Network</p>
          <p className="text-2xl font-bold text-amber-700">{formatMoney(overview?.summary.cost_components.network ?? 0)}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">LLM</p>
          <p className="text-2xl font-bold text-rose-700">{formatMoney(overview?.summary.cost_components.llm ?? 0)}</p>
        </div>
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="glass rounded-3xl border border-slate-200/60 p-4 xl:col-span-2">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">Cost Trend</h3>
          </div>
          <div className="overflow-auto rounded-xl border border-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="text-left px-3 py-2">Time</th>
                  <th className="text-left px-3 py-2">Total</th>
                  <th className="text-left px-3 py-2">Compute</th>
                  <th className="text-left px-3 py-2">Storage</th>
                  <th className="text-left px-3 py-2">Network</th>
                  <th className="text-left px-3 py-2">LLM</th>
                </tr>
              </thead>
              <tbody>
                {(overview?.trend ?? []).map((item) => (
                  <tr key={item.timestamp} className="border-t border-slate-100">
                    <td className="px-3 py-2 text-xs text-slate-600">{new Date(item.timestamp).toLocaleString()}</td>
                    <td className="px-3 py-2">{formatMoney(item.total_cost)}</td>
                    <td className="px-3 py-2">{formatMoney(item.compute_cost)}</td>
                    <td className="px-3 py-2">{formatMoney(item.storage_cost)}</td>
                    <td className="px-3 py-2">{formatMoney(item.network_cost)}</td>
                    <td className="px-3 py-2">{formatMoney(item.llm_cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="glass rounded-3xl border border-slate-200/60 p-4">
          <div className="flex items-center gap-2 mb-3">
            <Layers size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">Project Ranking</h3>
          </div>
          <div className="space-y-2 max-h-72 overflow-auto">
            {(overview?.project_ranking ?? []).map((item) => (
              <div key={item.project_id} className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-slate-800">{item.project_name}</p>
                  <span
                    className={clsx(
                      'px-2 py-0.5 rounded-full text-xs font-semibold',
                      item.trend === 'UP'
                        ? 'bg-rose-100 text-rose-700'
                        : item.trend === 'DOWN'
                          ? 'bg-emerald-100 text-emerald-700'
                          : 'bg-slate-100 text-slate-700',
                    )}
                  >
                    {item.trend}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">{formatMoney(item.cost)} | delta7d {item.delta_7d.toFixed(3)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="glass rounded-3xl border border-slate-200/60 p-4">
          <div className="flex items-center gap-2 mb-3">
            <Coins size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">Resources</h3>
          </div>
          <div className="space-y-2 max-h-[620px] overflow-auto">
            {loadingResources && <p className="text-sm text-slate-500">Loading resources...</p>}
            {(resourcesResp?.items ?? []).map((item) => {
              const key = `${item.project_id}:${item.source_type}:${item.source_id}`
              return (
                <button
                  key={key}
                  onClick={() => setSelectedResourceKey(key)}
                  className={clsx(
                    'w-full text-left rounded-xl border p-3 transition',
                    selectedResourceKey === key
                      ? 'border-cyan-500 bg-cyan-50'
                      : 'border-slate-200 bg-white hover:border-slate-300',
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-semibold text-slate-800 text-sm">{item.resource_name}</p>
                    <span className="text-xs font-semibold text-slate-700">{formatMoney(item.total_cost)}</span>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    {item.project_name} | {item.module}/{item.resource_type}
                  </p>
                  <p className="text-xs text-slate-600 mt-1 line-clamp-2">{item.driver}</p>
                </button>
              )
            })}
          </div>
        </div>

        <div className="glass rounded-3xl border border-slate-200/60 p-4">
          <div className="flex items-center gap-2 mb-3">
            <Gauge size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">Resource Detail & Optimization</h3>
          </div>
          {!detail && <p className="text-sm text-slate-500">Select one resource to inspect detail.</p>}
          {loadingDetail && <p className="text-sm text-slate-500">Loading detail...</p>}
          {detail && (
            <div className="space-y-3">
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold text-slate-800">{detail.resource.resource_name}</p>
                  <span className="text-xs font-semibold text-slate-700">{formatMoney(detail.resource.total_cost)}</span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  {detail.resource.module} / {detail.resource.resource_type} | rank {detail.comparison.module_rank}/{detail.comparison.module_size}
                </p>
                <p className="text-xs text-slate-500 mt-1">module avg {formatMoney(detail.comparison.module_average_cost)}</p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold text-slate-700 mb-2">Cost Components</p>
                <div className="grid grid-cols-2 gap-2 text-xs text-slate-700">
                  <div>Compute: {formatMoney(detail.resource.cost_components.compute)}</div>
                  <div>Storage: {formatMoney(detail.resource.cost_components.storage)}</div>
                  <div>Network: {formatMoney(detail.resource.cost_components.network)}</div>
                  <div>LLM: {formatMoney(detail.resource.cost_components.llm)}</div>
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold text-slate-700 mb-2">Optimization Actions</p>
                <div className="space-y-2">
                  {detail.optimization_actions.map((action, index) => (
                    <div key={`${action.action}-${index}`} className="rounded-lg border border-slate-200 p-2">
                      <p className="text-sm text-slate-800 font-medium">{action.action}</p>
                      <p className="text-xs text-slate-500 mt-1">{action.reason}</p>
                      <div className="mt-2 flex items-center justify-between">
                        <span className="text-xs text-emerald-700 font-semibold">
                          potential save {formatMoney(action.estimated_saving)}
                        </span>
                        <button
                          onClick={() => jumpToRoute(action.target_route, detail.resource)}
                          className="rounded-lg bg-cyan-600 text-white px-2 py-1 text-xs"
                        >
                          Open <ArrowRight size={12} className="inline ml-1" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold text-slate-700 mb-2">Candidate List</p>
                <div className="space-y-2 max-h-48 overflow-auto">
                  {(overview?.optimization_candidates ?? []).slice(0, 10).map((item, index) => (
                    <button
                      key={`${item.resource.source_type}-${item.resource.source_id}-${index}`}
                      onClick={() => setSelectedResourceKey(`${item.resource.project_id}:${item.resource.source_type}:${item.resource.source_id}`)}
                      className="block w-full text-left border-b border-slate-100 pb-1"
                    >
                      <p className="text-sm text-slate-800">{item.resource.resource_name}</p>
                      <p className="text-xs text-slate-500">
                        {item.recommended_action.action} | potential {formatMoney(item.potential_saving)}
                      </p>
                    </button>
                  ))}
                </div>
              </div>

              <button
                onClick={() => jumpToRoute(detail.navigation.module_route, detail.resource)}
                className="w-full rounded-xl bg-slate-900 text-white px-4 py-2.5 text-sm font-semibold hover:bg-slate-800"
              >
                Open Resource Module
              </button>
            </div>
          )}
        </div>
      </section>

      <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="glass rounded-3xl border border-slate-200/60 p-4">
          <div className="flex items-center gap-2 mb-2">
            <DollarSign size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">Module Breakdown</h3>
          </div>
          <div className="space-y-2">
            {(overview?.module_breakdown ?? []).map((item) => (
              <div key={item.module} className="rounded-xl border border-slate-200 bg-white p-2 text-sm flex items-center justify-between">
                <span>{item.module}</span>
                <span className="font-semibold">{formatMoney(item.cost)} ({(item.percentage * 100).toFixed(1)}%)</span>
              </div>
            ))}
          </div>
        </div>
        <div className="glass rounded-3xl border border-slate-200/60 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Layers size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">Resource Type Breakdown</h3>
          </div>
          <div className="space-y-2">
            {(overview?.resource_type_breakdown ?? []).map((item) => (
              <div key={item.resource_type} className="rounded-xl border border-slate-200 bg-white p-2 text-sm flex items-center justify-between">
                <span>{item.resource_type}</span>
                <span className="font-semibold">{formatMoney(item.cost)} ({(item.percentage * 100).toFixed(1)}%)</span>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}

export default CostUsageAnalytics
