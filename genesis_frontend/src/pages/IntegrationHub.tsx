import { FormEvent, useEffect, useMemo, useState } from 'react'
import { clsx } from 'clsx'
import { Cable, CheckCircle2, Plug, RefreshCw, Send, ShieldAlert, TestTubeDiagonal } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import {
  GenesisApi,
  type IntegrationHubDetailResponse,
  type IntegrationHubItem,
  type IntegrationHubListResponse,
  type IntegrationHubOverviewResponse,
} from '../services/api'
import { useLanguage } from '../i18n/language'

type Filters = {
  q: string
  integration_type: string
  category: string
  enabled: string
  health_status: string
}

const IntegrationHub = () => {
  const navigate = useNavigate()
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const [overview, setOverview] = useState<IntegrationHubOverviewResponse | null>(null)
  const [listResp, setListResp] = useState<IntegrationHubListResponse | null>(null)
  const [detail, setDetail] = useState<IntegrationHubDetailResponse | null>(null)
  const [selectedType, setSelectedType] = useState<string | null>(null)

  const [filters, setFilters] = useState<Filters>({
    q: '',
    integration_type: 'ALL',
    category: 'ALL',
    enabled: 'ALL',
    health_status: 'ALL',
  })

  const [form, setForm] = useState({
    enabled: true,
    configJson: '{\n  "endpoint": "https://hooks.example.com/events"\n}',
  })
  const [invokeForm, setInvokeForm] = useState({
    caller_module: 'GOVERNANCE',
    action: 'CREATE_TICKET',
    payloadJson: '{\n  "title": "Investigate data quality drift",\n  "priority": "HIGH"\n}',
    simulate_failure: false,
    error_code: 'DOWNSTREAM_TIMEOUT',
    note: 'simulated from integration hub page',
  })

  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [banner, setBanner] = useState<string | null>(null)

  const parseJsonObject = (text: string): Record<string, unknown> | null => {
    try {
      const value = JSON.parse(text)
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        return value as Record<string, unknown>
      }
    } catch {
      return null
    }
    return null
  }

  const loadOverview = async () => {
    const data = await GenesisApi.getIntegrationHubOverview()
    setOverview(data)
  }

  const loadList = async () => {
    const data = await GenesisApi.getIntegrationHubIntegrations({
      q: filters.q.trim() || undefined,
      integration_type: filters.integration_type === 'ALL' ? undefined : filters.integration_type,
      category: filters.category === 'ALL' ? undefined : filters.category,
      enabled:
        filters.enabled === 'ALL'
          ? undefined
          : filters.enabled === 'TRUE'
            ? true
            : false,
      health_status: filters.health_status === 'ALL' ? undefined : filters.health_status,
      limit: 200,
      offset: 0,
    })
    setListResp(data)

    if (!selectedType && data.items.length > 0) {
      setSelectedType(data.items[0].integration_type)
    }
    if (selectedType && !data.items.some((item) => item.integration_type === selectedType)) {
      setSelectedType(data.items[0]?.integration_type ?? null)
    }
  }

  const loadDetail = async (integrationType: string) => {
    const data = await GenesisApi.getIntegrationHubDetail(integrationType)
    setDetail(data)
    const prettyConfig = JSON.stringify(data.template, null, 2)
    setForm((prev) => ({ ...prev, configJson: prettyConfig }))
  }

  const refreshAll = async () => {
    setLoading(true)
    setError(null)
    try {
      await Promise.all([loadOverview(), loadList()])
      if (selectedType) {
        await loadDetail(selectedType)
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load integration hub')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setLoading(true)
    Promise.all([loadOverview(), loadList()])
      .catch((e: any) => {
        setError(e?.response?.data?.message ?? 'Failed to load integration hub')
      })
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (selectedType) {
      void loadDetail(selectedType).catch(() => {
        setDetail(null)
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedType])

  const selectedIntegration: IntegrationHubItem | null = detail?.integration ?? null

  const categories = useMemo(() => {
    return ['ALL', ...(listResp?.facets.categories ?? [])]
  }, [listResp?.facets.categories])

  const types = useMemo(() => {
    return ['ALL', ...(listResp?.facets.types ?? [])]
  }, [listResp?.facets.types])

  const healthStatuses = useMemo(() => {
    return ['ALL', ...(listResp?.facets.health_statuses ?? [])]
  }, [listResp?.facets.health_statuses])

  const onApplyFilters = async (event: FormEvent) => {
    event.preventDefault()
    await refreshAll()
  }

  const onTest = async () => {
    if (!selectedType) return
    const config = parseJsonObject(form.configJson)
    if (!config) {
      setError('Config JSON format is invalid')
      return
    }

    setSaving(true)
    setError(null)
    try {
      const result = await GenesisApi.testIntegrationHub({
        integration_type: selectedType,
        config,
      })
      setBanner(`${selectedType} test: ${result.status} (${result.message})`)
      await Promise.all([loadOverview(), loadList(), loadDetail(selectedType)])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Integration test failed')
    } finally {
      setSaving(false)
    }
  }

  const onSave = async () => {
    if (!selectedType) return
    const config = parseJsonObject(form.configJson)
    if (!config) {
      setError('Config JSON format is invalid')
      return
    }

    setSaving(true)
    setError(null)
    try {
      await GenesisApi.saveIntegrationHub(selectedType, {
        enabled: form.enabled,
        config,
      })
      setBanner(`${selectedType} saved`)
      await Promise.all([loadOverview(), loadList(), loadDetail(selectedType)])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Integration save failed')
    } finally {
      setSaving(false)
    }
  }

  const onInvoke = async () => {
    if (!selectedType) return
    const payload = parseJsonObject(invokeForm.payloadJson)
    if (!payload) {
      setError('Invoke payload JSON format is invalid')
      return
    }

    setSaving(true)
    setError(null)
    try {
      const result = await GenesisApi.invokeIntegrationHub(selectedType, {
        caller_module: invokeForm.caller_module,
        action: invokeForm.action,
        payload,
        simulate_failure: invokeForm.simulate_failure,
        error_code: invokeForm.error_code,
        note: invokeForm.note,
      })
      setBanner(`${selectedType} invoke: ${result.status}`)
      await Promise.all([loadOverview(), loadList(), loadDetail(selectedType)])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Integration invoke failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-7xl mx-auto space-y-4 animate-in fade-in slide-in-from-bottom-8 duration-700">
      <section className="rounded-2xl border border-slate-200 bg-white/80 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-900">{isZh ? '下一步建议' : 'Recommended Next Step'}</p>
            <p className="text-xs text-slate-600">
              {isZh ? '集成连接测试通过后，建议到监控页确认告警通知链路。' : 'After integration test passes, verify alert notification flow in Monitoring.'}
            </p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => navigate('/monitoring')} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs hover:bg-slate-50">
              {isZh ? '去监控' : 'Go Monitoring'}
            </button>
            <button onClick={() => navigate('/logs')} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs hover:bg-slate-50">
              {isZh ? '看审计日志' : 'View Audit Logs'}
            </button>
          </div>
        </div>
      </section>
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">Integration Hub</h2>
          <p className="text-slate-500 text-base">Configure connectors, verify connectivity, and route module actions to external systems.</p>
        </div>
        <button
          onClick={() => void refreshAll()}
          disabled={loading || saving}
          className="rounded-xl bg-slate-900 text-white px-4 py-2.5 font-medium hover:bg-slate-800 disabled:opacity-60 flex items-center gap-2"
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </header>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
      {banner && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{banner}</div>}

      <section className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Configured</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.configured_count ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Enabled</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.enabled_count ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Healthy</p><p className="text-2xl font-bold text-emerald-700">{overview?.summary.healthy_count ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Unhealthy</p><p className="text-2xl font-bold text-rose-700">{overview?.summary.unhealthy_count ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Coverage</p><p className="text-2xl font-bold text-slate-900">{Math.round((overview?.summary.coverage_ratio ?? 0) * 100)}%</p></div>
      </section>

      <form onSubmit={onApplyFilters} className="glass rounded-3xl border border-slate-200/60 p-4">
        <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
          <input
            value={filters.q}
            onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))}
            placeholder="search type/category/module"
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
          />
          <select value={filters.integration_type} onChange={(e) => setFilters((prev) => ({ ...prev, integration_type: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
            {types.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <select value={filters.category} onChange={(e) => setFilters((prev) => ({ ...prev, category: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
            {categories.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <select value={filters.enabled} onChange={(e) => setFilters((prev) => ({ ...prev, enabled: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
            <option value="ALL">ALL ENABLED</option>
            <option value="TRUE">ENABLED</option>
            <option value="FALSE">DISABLED</option>
          </select>
          <select value={filters.health_status} onChange={(e) => setFilters((prev) => ({ ...prev, health_status: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
            {healthStatuses.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <button type="submit" className="rounded-xl bg-cyan-600 text-white px-4 py-2 text-sm font-semibold">Apply Filters</button>
        </div>
      </form>

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="glass rounded-3xl border border-slate-200/60 p-4 xl:col-span-1">
          <h3 className="text-sm font-semibold text-slate-800 mb-3 flex items-center gap-2"><Plug size={16} /> Integrations</h3>
          <div className="space-y-2 max-h-[34rem] overflow-auto">
            {(listResp?.items ?? []).map((item) => (
              <button
                key={item.integration_type}
                onClick={() => setSelectedType(item.integration_type)}
                className={clsx(
                  'w-full text-left rounded-xl border px-3 py-2 transition',
                  selectedType === item.integration_type ? 'border-cyan-300 bg-cyan-50/70' : 'border-slate-200 bg-white hover:bg-slate-50',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold text-slate-800 text-sm">{item.integration_type}</p>
                  <span className={clsx('px-2 py-0.5 rounded-full text-xs font-semibold', item.enabled ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600')}>
                    {item.enabled ? 'ENABLED' : 'DISABLED'}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">{item.category} | health {item.health.status}</p>
              </button>
            ))}
          </div>
        </div>

        <div className="glass rounded-3xl border border-slate-200/60 p-4 xl:col-span-2 space-y-4">
          {!selectedIntegration ? (
            <p className="text-sm text-slate-500">Select one integration to view details.</p>
          ) : (
            <>
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex items-center justify-between gap-3 mb-2">
                  <h3 className="text-lg font-semibold text-slate-900">{selectedIntegration.integration_type}</h3>
                  <span className={clsx('px-2.5 py-1 rounded-full text-xs font-semibold', selectedIntegration.health.status === 'HEALTHY' ? 'bg-emerald-100 text-emerald-700' : selectedIntegration.health.status === 'UNHEALTHY' ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700')}>
                    {selectedIntegration.health.status}
                  </span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                  <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Calls (7d)</p><p className="font-semibold text-slate-800">{selectedIntegration.health.total_calls_7d}</p></div>
                  <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Success Rate</p><p className="font-semibold text-slate-800">{Math.round(selectedIntegration.health.success_rate_7d * 100)}%</p></div>
                  <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Failures (7d)</p><p className="font-semibold text-slate-800">{selectedIntegration.health.failure_calls_7d}</p></div>
                  <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Last Heartbeat</p><p className="font-semibold text-slate-800">{selectedIntegration.health.last_heartbeat_at ? new Date(selectedIntegration.health.last_heartbeat_at).toLocaleString() : '-'}</p></div>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-2">
                  <h4 className="text-sm font-semibold text-slate-800 flex items-center gap-2"><Cable size={15} /> Config</h4>
                  <label className="text-xs text-slate-500 inline-flex items-center gap-2">
                    <input type="checkbox" checked={form.enabled} onChange={(e) => setForm((prev) => ({ ...prev, enabled: e.target.checked }))} />
                    Enabled
                  </label>
                  <textarea value={form.configJson} onChange={(e) => setForm((prev) => ({ ...prev, configJson: e.target.value }))} rows={10} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-mono" />
                  <div className="flex gap-2">
                    <button onClick={() => void onTest()} disabled={saving} className="flex-1 rounded-xl bg-indigo-600 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60 inline-flex items-center justify-center gap-1"><TestTubeDiagonal size={14} /> Test</button>
                    <button onClick={() => void onSave()} disabled={saving} className="flex-1 rounded-xl bg-cyan-600 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60 inline-flex items-center justify-center gap-1"><CheckCircle2 size={14} /> Save</button>
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-2">
                  <h4 className="text-sm font-semibold text-slate-800 flex items-center gap-2"><Send size={15} /> Invoke</h4>
                  <input value={invokeForm.caller_module} onChange={(e) => setInvokeForm((prev) => ({ ...prev, caller_module: e.target.value.toUpperCase() }))} placeholder="caller_module" className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                  <input value={invokeForm.action} onChange={(e) => setInvokeForm((prev) => ({ ...prev, action: e.target.value.toUpperCase() }))} placeholder="action" className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                  <textarea value={invokeForm.payloadJson} onChange={(e) => setInvokeForm((prev) => ({ ...prev, payloadJson: e.target.value }))} rows={7} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-mono" />
                  <label className="text-xs text-slate-500 inline-flex items-center gap-2"><input type="checkbox" checked={invokeForm.simulate_failure} onChange={(e) => setInvokeForm((prev) => ({ ...prev, simulate_failure: e.target.checked }))} />Simulate failure</label>
                  {invokeForm.simulate_failure && (
                    <>
                      <input value={invokeForm.error_code} onChange={(e) => setInvokeForm((prev) => ({ ...prev, error_code: e.target.value.toUpperCase() }))} placeholder="error_code" className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                      <input value={invokeForm.note} onChange={(e) => setInvokeForm((prev) => ({ ...prev, note: e.target.value }))} placeholder="failure note" className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                    </>
                  )}
                  <button onClick={() => void onInvoke()} disabled={saving} className="w-full rounded-xl bg-slate-900 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60 inline-flex items-center justify-center gap-1"><ShieldAlert size={14} /> Invoke</button>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <h4 className="text-sm font-semibold text-slate-800 mb-2">Usage Scenarios</h4>
                  <div className="space-y-2 max-h-60 overflow-auto">
                    {selectedIntegration.usage_scenarios.map((item) => (
                      <div key={item.module} className="rounded-lg border border-slate-200 p-2 text-xs text-slate-700">
                        <p className="font-semibold">{item.module}</p>
                        <p>calls {item.calls} | success {item.success_calls} | failure {item.failure_calls}</p>
                      </div>
                    ))}
                    {selectedIntegration.usage_scenarios.length === 0 && <p className="text-xs text-slate-500">No usage data</p>}
                  </div>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <h4 className="text-sm font-semibold text-slate-800 mb-2">Error Distribution</h4>
                  <div className="space-y-2 max-h-60 overflow-auto">
                    {selectedIntegration.health.error_code_distribution.map((item) => (
                      <div key={item.error_code} className="rounded-lg border border-slate-200 p-2 text-xs text-slate-700 flex items-center justify-between">
                        <span>{item.error_code}</span>
                        <span className="font-semibold">{item.count}</span>
                      </div>
                    ))}
                    {selectedIntegration.health.error_code_distribution.length === 0 && <p className="text-xs text-slate-500">No errors in recent window</p>}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  )
}

export default IntegrationHub