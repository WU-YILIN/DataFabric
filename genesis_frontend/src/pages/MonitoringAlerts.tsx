import { FormEvent, useEffect, useMemo, useState } from 'react'
import { clsx } from 'clsx'
import { Activity, AlertTriangle, CheckCircle2, RefreshCw, Search } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import {
  GenesisApi,
  type MonitoringAlertDetailResponse,
  type MonitoringAlertListItem,
  type MonitoringAlertListResponse,
  type MonitoringOverviewResponse,
} from '../services/api'
import { useLanguage } from '../i18n/language'

const severityClass: Record<string, string> = {
  CRITICAL: 'bg-rose-100 text-rose-700',
  HIGH: 'bg-amber-100 text-amber-700',
  MEDIUM: 'bg-cyan-100 text-cyan-700',
  LOW: 'bg-slate-100 text-slate-700',
}

const moduleStatusClass: Record<string, string> = {
  GREEN: 'bg-emerald-100 text-emerald-700',
  YELLOW: 'bg-amber-100 text-amber-700',
  RED: 'bg-rose-100 text-rose-700',
}

const MonitoringAlerts = () => {
  const navigate = useNavigate()
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const [overview, setOverview] = useState<MonitoringOverviewResponse | null>(null)
  const [alertsResp, setAlertsResp] = useState<MonitoringAlertListResponse | null>(null)
  const [selectedAlertId, setSelectedAlertId] = useState<number | null>(null)
  const [detail, setDetail] = useState<MonitoringAlertDetailResponse | null>(null)

  const [loadingOverview, setLoadingOverview] = useState(false)
  const [loadingAlerts, setLoadingAlerts] = useState(false)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [operating, setOperating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const [filters, setFilters] = useState({
    q: '',
    severity: 'ALL',
    status: 'ALL',
    source_module: 'ALL',
  })
  const [noteText, setNoteText] = useState('')

  const availableModules = useMemo(
    () => overview?.filters.available_modules ?? [],
    [overview],
  )

  const loadOverview = async () => {
    setLoadingOverview(true)
    setError(null)
    try {
      const data = await GenesisApi.getMonitoringOverview({
        modules: filters.source_module === 'ALL' ? undefined : filters.source_module,
      })
      setOverview(data)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? (isZh ? '加载监控总览失败' : 'Failed to load monitoring overview'))
    } finally {
      setLoadingOverview(false)
    }
  }

  const loadAlerts = async () => {
    setLoadingAlerts(true)
    setError(null)
    try {
      const data = await GenesisApi.getMonitoringAlerts({
        q: filters.q.trim() || undefined,
        severity: filters.severity === 'ALL' ? undefined : filters.severity,
        status: filters.status === 'ALL' ? undefined : filters.status,
        source_module: filters.source_module === 'ALL' ? undefined : filters.source_module,
        limit: 50,
        offset: 0,
      })
      setAlertsResp(data)
      if (!selectedAlertId && data.items.length > 0) {
        setSelectedAlertId(data.items[0].id)
      }
      if (selectedAlertId && !data.items.find((item) => item.id === selectedAlertId)) {
        setSelectedAlertId(data.items[0]?.id ?? null)
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? (isZh ? '加载告警列表失败' : 'Failed to load alerts'))
    } finally {
      setLoadingAlerts(false)
    }
  }

  const loadDetail = async (alertId: number) => {
    setLoadingDetail(true)
    setError(null)
    try {
      const data = await GenesisApi.getMonitoringAlertDetail(alertId)
      setDetail(data)
      setNoteText(data.alert.last_note ?? '')
    } catch (e: any) {
      setError(e?.response?.data?.message ?? (isZh ? '加载告警详情失败' : 'Failed to load alert detail'))
      setDetail(null)
    } finally {
      setLoadingDetail(false)
    }
  }

  useEffect(() => {
    void loadOverview()
    void loadAlerts()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (selectedAlertId != null) {
      void loadDetail(selectedAlertId)
    } else {
      setDetail(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAlertId])

  const onApplyFilters = async (event: FormEvent) => {
    event.preventDefault()
    await Promise.all([loadOverview(), loadAlerts()])
  }

  const operate = async (action: 'CLAIM' | 'RESOLVE' | 'NOTE') => {
    if (!detail) {
      return
    }
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      await GenesisApi.operateMonitoringAlert(detail.alert.id, {
        action,
        note: noteText.trim() || undefined,
      })
      setMessage(`Action ${action} completed`)
      await Promise.all([loadOverview(), loadAlerts(), loadDetail(detail.alert.id)])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? `Failed to ${action.toLowerCase()} alert`)
    } finally {
      setOperating(false)
    }
  }

  const openRelated = (alert: MonitoringAlertListItem) => {
    const route = alert.links.module_route || '/logs'
    navigate(route)
  }

  const openKnowledgeForAlert = (alert: MonitoringAlertListItem) => {
    const params = new URLSearchParams({
      source_type: 'ALERT',
      source_id: String(alert.id),
    })
    navigate(`/knowledge?${params.toString()}`)
  }

  return (
    <div className="max-w-7xl mx-auto space-y-4 animate-in fade-in slide-in-from-bottom-8 duration-700">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">{isZh ? '监控与告警' : 'Monitoring & Alerts'}</h2>
          <p className="text-slate-500 text-base">
            System and business metrics with full alert triage workflow.
          </p>
        </div>
        <button
          onClick={() => {
            void loadOverview()
            void loadAlerts()
            if (selectedAlertId != null) {
              void loadDetail(selectedAlertId)
            }
          }}
          disabled={loadingOverview || loadingAlerts || loadingDetail}
          className="rounded-xl bg-slate-900 text-white px-4 py-2.5 font-medium hover:bg-slate-800 disabled:opacity-60 flex items-center gap-2"
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </header>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
      {message && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>
      )}

      <form onSubmit={onApplyFilters} className="glass rounded-3xl border border-slate-200/60 p-4">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          <div className="md:col-span-2">
            <label className="text-xs text-slate-500 uppercase tracking-wide">Search</label>
            <div className="mt-1 relative">
              <Search size={14} className="absolute left-2.5 top-2.5 text-slate-400" />
              <input
                value={filters.q}
                onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))}
                placeholder="title / source / description"
                className="w-full rounded-xl border border-slate-200 bg-white pl-8 pr-3 py-2 text-sm"
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-slate-500 uppercase tracking-wide">Severity</label>
            <select
              value={filters.severity}
              onChange={(e) => setFilters((prev) => ({ ...prev, severity: e.target.value }))}
              className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
            >
              <option value="ALL">All</option>
              <option value="CRITICAL">CRITICAL</option>
              <option value="HIGH">HIGH</option>
              <option value="MEDIUM">MEDIUM</option>
              <option value="LOW">LOW</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500 uppercase tracking-wide">Status</label>
            <select
              value={filters.status}
              onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))}
              className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
            >
              <option value="ALL">All</option>
              <option value="OPEN">OPEN</option>
              <option value="ACKNOWLEDGED">ACKNOWLEDGED</option>
              <option value="RESOLVED">RESOLVED</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500 uppercase tracking-wide">Module</label>
            <select
              value={filters.source_module}
              onChange={(e) => setFilters((prev) => ({ ...prev, source_module: e.target.value }))}
              className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
            >
              <option value="ALL">All</option>
              {availableModules.map((module) => (
                <option key={module} value={module}>
                  {module}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="mt-3">
          <button
            type="submit"
            className="rounded-xl bg-cyan-600 text-white px-4 py-2 text-sm font-semibold hover:bg-cyan-500"
          >
            Apply Filters
          </button>
        </div>
      </form>

      <section className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Open Alerts</p>
          <p className="text-2xl font-bold text-slate-900">{overview?.summary.open_alerts ?? 0}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Critical</p>
          <p className="text-2xl font-bold text-rose-700">{overview?.summary.critical_alerts ?? 0}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Ack</p>
          <p className="text-2xl font-bold text-amber-700">{overview?.summary.acknowledged_alerts ?? 0}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Resolved</p>
          <p className="text-2xl font-bold text-emerald-700">{overview?.summary.resolved_alerts ?? 0}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Total</p>
          <p className="text-2xl font-bold text-slate-900">{overview?.summary.total_alerts ?? 0}</p>
        </div>
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="glass rounded-3xl border border-slate-200/60 p-4 xl:col-span-2">
          <div className="flex items-center gap-2 mb-3">
            <Activity size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">Metric Trends</h3>
          </div>
          <div className="overflow-auto rounded-xl border border-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="text-left px-3 py-2">Time</th>
                  <th className="text-left px-3 py-2">QPS</th>
                  <th className="text-left px-3 py-2">Latency(ms)</th>
                  <th className="text-left px-3 py-2">Failure Rate</th>
                  <th className="text-left px-3 py-2">Alert Count</th>
                </tr>
              </thead>
              <tbody>
                {(overview?.trends ?? []).map((point) => (
                  <tr key={point.timestamp} className="border-t border-slate-100">
                    <td className="px-3 py-2 text-xs text-slate-600">{new Date(point.timestamp).toLocaleTimeString()}</td>
                    <td className="px-3 py-2">{point.qps.toFixed(3)}</td>
                    <td className="px-3 py-2">{point.latency_ms.toFixed(1)}</td>
                    <td className="px-3 py-2">{(point.failure_rate * 100).toFixed(2)}%</td>
                    <td className="px-3 py-2">{point.alert_count}</td>
                  </tr>
                ))}
                {(overview?.trends.length ?? 0) === 0 && (
                  <tr>
                    <td colSpan={5} className="px-3 py-4 text-sm text-slate-500">
                      No trend points available.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="glass rounded-3xl border border-slate-200/60 p-4">
          <div className="flex items-center gap-2 mb-3">
            <CheckCircle2 size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">Module Health</h3>
          </div>
          <div className="space-y-2">
            {(overview?.module_health ?? []).map((item) => (
              <div key={item.module} className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-slate-800">{item.module}</p>
                  <span className={clsx('px-2 py-0.5 rounded-full text-xs font-semibold', moduleStatusClass[item.status] ?? 'bg-slate-100 text-slate-700')}>
                    {item.status}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  score {item.score} | open {item.open_alerts} | critical {item.critical_alerts}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="glass rounded-3xl border border-slate-200/60 p-4">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">Alert List</h3>
          </div>
          <div className="space-y-2 max-h-[620px] overflow-auto">
            {loadingAlerts && <p className="text-sm text-slate-500">Loading alerts...</p>}
            {(alertsResp?.items ?? []).map((item) => (
              <button
                key={item.id}
                onClick={() => setSelectedAlertId(item.id)}
                className={clsx(
                  'w-full text-left rounded-xl border p-3 transition',
                  selectedAlertId === item.id ? 'border-cyan-500 bg-cyan-50' : 'border-slate-200 bg-white hover:border-slate-300',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold text-slate-800 text-sm">{item.title}</p>
                  <span className={clsx('px-2 py-0.5 rounded-full text-xs font-semibold', severityClass[item.severity] ?? 'bg-slate-100 text-slate-700')}>
                    {item.severity}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  {item.source_module} | {item.status} | {new Date(item.created_at).toLocaleString()}
                </p>
                <p className="text-xs text-slate-600 mt-1 line-clamp-2">{item.description}</p>
              </button>
            ))}
            {(alertsResp?.items.length ?? 0) === 0 && !loadingAlerts && (
              <p className="text-sm text-slate-500">No alerts under current filters.</p>
            )}
          </div>
        </div>

        <div className="glass rounded-3xl border border-slate-200/60 p-4">
          <div className="flex items-center gap-2 mb-3">
            <Search size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">Alert Detail</h3>
          </div>
          {!detail && <p className="text-sm text-slate-500">Select one alert to inspect details.</p>}
          {loadingDetail && <p className="text-sm text-slate-500">Loading detail...</p>}
          {detail && (
            <div className="space-y-3">
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold text-slate-800">{detail.alert.title}</p>
                  <span className={clsx('px-2 py-0.5 rounded-full text-xs font-semibold', severityClass[detail.alert.severity] ?? 'bg-slate-100 text-slate-700')}>
                    {detail.alert.severity}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  {detail.metadata.source_module} | {detail.alert.status} | alert#{detail.alert.id}
                </p>
                <p className="text-xs text-slate-600 mt-2">{detail.alert.description}</p>
                <div className="mt-2 text-xs text-slate-500">
                  tenant={detail.metadata.tenant_id ?? '-'} | project={detail.metadata.project_id} | source={detail.metadata.source_type}:{detail.metadata.source_id}
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold text-slate-700 mb-2">Context Metrics (±{detail.context_metrics.window_minutes}m)</p>
                <div className="space-y-1 max-h-40 overflow-auto">
                  {detail.context_metrics.timeline.map((item) => (
                    <div key={item.from} className="text-xs text-slate-600 border-b border-slate-100 pb-1">
                      {new Date(item.from).toLocaleTimeString()} - {new Date(item.to).toLocaleTimeString()}
                      {' | qps '}
                      {item.qps.toFixed(3)}
                      {' | latency '}
                      {item.latency_ms.toFixed(1)}
                      {' | fail '}
                      {(item.failure_rate * 100).toFixed(2)}%
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold text-slate-700 mb-2">Operations</p>
                <textarea
                  rows={3}
                  value={noteText}
                  onChange={(e) => setNoteText(e.target.value)}
                  placeholder="claim/resolve note"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                />
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    onClick={() => void operate('CLAIM')}
                    disabled={operating || detail.alert.status === 'RESOLVED'}
                    className="rounded-lg bg-amber-500 text-white px-3 py-1.5 text-sm disabled:opacity-50"
                  >
                    Claim
                  </button>
                  <button
                    onClick={() => void operate('RESOLVE')}
                    disabled={operating || detail.alert.status === 'RESOLVED'}
                    className="rounded-lg bg-emerald-600 text-white px-3 py-1.5 text-sm disabled:opacity-50"
                  >
                    Resolve
                  </button>
                  <button
                    onClick={() => void operate('NOTE')}
                    disabled={operating}
                    className="rounded-lg bg-cyan-600 text-white px-3 py-1.5 text-sm disabled:opacity-50"
                  >
                    Add Note
                  </button>
                  <button
                    onClick={() => openRelated(detail.alert)}
                    className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700"
                  >
                    Open Related Module
                  </button>
                  <button
                    onClick={() => openKnowledgeForAlert(detail.alert)}
                    className="rounded-lg bg-emerald-600 text-white px-3 py-1.5 text-sm"
                  >
                    Related Docs
                  </button>
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold text-slate-700 mb-2">Action History</p>
                <div className="space-y-2 max-h-52 overflow-auto">
                  {detail.history.map((item) => (
                    <div key={item.id} className="border-b border-slate-100 pb-2">
                      <p className="text-xs text-slate-700 font-medium">
                        {item.action} by {item.actor}
                      </p>
                      <p className="text-[11px] text-slate-500">{new Date(item.created_at).toLocaleString()}</p>
                      {item.note && <p className="text-xs text-slate-600 mt-1">{item.note}</p>}
                    </div>
                  ))}
                  {detail.history.length === 0 && <p className="text-sm text-slate-500">No history yet.</p>}
                </div>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

export default MonitoringAlerts
