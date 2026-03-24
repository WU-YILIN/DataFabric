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
import { useBrowserErrorAlert } from '../hooks/useBrowserErrorAlert'

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

export default function MonitoringAlerts() {
  const navigate = useNavigate()
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const L = (cn: string, en: string) => (isZh ? cn : en)

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
  useBrowserErrorAlert(error)

  const [filters, setFilters] = useState({
    q: '',
    severity: 'ALL',
    status: 'ALL',
    source_module: 'ALL',
  })
  const [noteText, setNoteText] = useState('')

  const availableModules = useMemo(() => overview?.filters.available_modules ?? [], [overview])

  const formatDate = (value?: string | null) => {
    if (!value) return '-'
    return new Date(value).toLocaleString(isZh ? 'zh-CN' : 'en-US', { hour12: false })
  }

  const loadOverview = async () => {
    setLoadingOverview(true)
    setError(null)
    try {
      const data = await GenesisApi.getMonitoringOverview({
        modules: filters.source_module === 'ALL' ? undefined : filters.source_module,
      })
      setOverview(data)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? L('加载监控总览失败', 'Failed to load monitoring overview'))
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
      if (!selectedAlertId && data.items.length > 0) setSelectedAlertId(data.items[0].id)
      if (selectedAlertId && !data.items.find((item) => item.id === selectedAlertId)) {
        setSelectedAlertId(data.items[0]?.id ?? null)
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? L('加载告警列表失败', 'Failed to load alerts'))
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
      setError(e?.response?.data?.message ?? L('加载告警详情失败', 'Failed to load alert detail'))
      setDetail(null)
    } finally {
      setLoadingDetail(false)
    }
  }

  useEffect(() => {
    void loadOverview()
    void loadAlerts()
  }, [])

  useEffect(() => {
    if (selectedAlertId != null) void loadDetail(selectedAlertId)
    else setDetail(null)
  }, [selectedAlertId])

  const onApplyFilters = async (event: FormEvent) => {
    event.preventDefault()
    await Promise.all([loadOverview(), loadAlerts()])
  }

  const operate = async (action: 'CLAIM' | 'RESOLVE' | 'NOTE') => {
    if (!detail) return
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      await GenesisApi.operateMonitoringAlert(detail.alert.id, {
        action,
        note: noteText.trim() || undefined,
      })
      setMessage(`${L('操作完成', 'Action completed')}: ${action}`)
      await Promise.all([loadOverview(), loadAlerts(), loadDetail(detail.alert.id)])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? `${L('告警操作失败', 'Alert operation failed')}: ${action}`)
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
    <div className="mx-auto max-w-7xl space-y-4 animate-in fade-in slide-in-from-bottom-8 duration-700">
      <section className="rounded-2xl border border-slate-200 bg-white/80 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-900">{L('推荐下一步', 'Recommended Next Step')}</p>
            <p className="text-xs text-slate-600">{L('优先处理 P0/P1 告警，处理完成后再回到成本页确认异常波动影响。', 'Resolve P0/P1 alerts first, then validate anomaly impact on cost page.')}</p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => navigate('/cost')} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs hover:bg-slate-50">{L('前往成本', 'Go Cost')}</button>
            <button onClick={() => navigate('/logs')} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs hover:bg-slate-50">{L('查看审计日志', 'View Audit Logs')}</button>
          </div>
        </div>
      </section>

      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-slate-900">{L('监控与告警', 'Monitoring & Alerts')}</h2>
          <p className="text-base text-slate-500">{L('统一查看系统与业务指标，并完成完整的告警处置流程。', 'System and business metrics with full alert triage workflow.')}</p>
        </div>
        <button
          onClick={() => {
            void loadOverview()
            void loadAlerts()
            if (selectedAlertId != null) void loadDetail(selectedAlertId)
          }}
          disabled={loadingOverview || loadingAlerts || loadingDetail}
          className="flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 font-medium text-white hover:bg-slate-800 disabled:opacity-60"
        >
          <RefreshCw size={16} />
          {L('刷新', 'Refresh')}
        </button>
      </header>

      {message && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>}

      <form onSubmit={onApplyFilters} className="rounded-3xl border border-slate-200/60 p-4 glass">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
          <div className="md:col-span-2">
            <label className="text-xs uppercase tracking-wide text-slate-500">{L('搜索', 'Search')}</label>
            <div className="relative mt-1">
              <Search size={14} className="absolute left-2.5 top-2.5 text-slate-400" />
              <input value={filters.q} onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))} placeholder={L('标题 / 来源 / 描述', 'title / source / description')} className="w-full rounded-xl border border-slate-200 bg-white py-2 pl-8 pr-3 text-sm" />
            </div>
          </div>
          <div>
            <label className="text-xs uppercase tracking-wide text-slate-500">{L('严重级别', 'Severity')}</label>
            <select value={filters.severity} onChange={(e) => setFilters((prev) => ({ ...prev, severity: e.target.value }))} className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
              <option value="ALL">{L('全部', 'All')}</option>
              <option value="CRITICAL">CRITICAL</option>
              <option value="HIGH">HIGH</option>
              <option value="MEDIUM">MEDIUM</option>
              <option value="LOW">LOW</option>
            </select>
          </div>
          <div>
            <label className="text-xs uppercase tracking-wide text-slate-500">{L('状态', 'Status')}</label>
            <select value={filters.status} onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))} className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
              <option value="ALL">{L('全部', 'All')}</option>
              <option value="OPEN">OPEN</option>
              <option value="ACKNOWLEDGED">ACKNOWLEDGED</option>
              <option value="RESOLVED">RESOLVED</option>
            </select>
          </div>
          <div>
            <label className="text-xs uppercase tracking-wide text-slate-500">{L('模块', 'Module')}</label>
            <select value={filters.source_module} onChange={(e) => setFilters((prev) => ({ ...prev, source_module: e.target.value }))} className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
              <option value="ALL">{L('全部', 'All')}</option>
              {availableModules.map((module) => <option key={module} value={module}>{module}</option>)}
            </select>
          </div>
        </div>
        <div className="mt-3">
          <button type="submit" className="rounded-xl bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-500">{L('应用筛选', 'Apply Filters')}</button>
        </div>
      </form>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <div className="rounded-2xl border border-slate-200/60 p-3 glass"><p className="text-xs text-slate-500">{L('打开告警', 'Open Alerts')}</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.open_alerts ?? 0}</p></div>
        <div className="rounded-2xl border border-slate-200/60 p-3 glass"><p className="text-xs text-slate-500">{L('严重', 'Critical')}</p><p className="text-2xl font-bold text-rose-700">{overview?.summary.critical_alerts ?? 0}</p></div>
        <div className="rounded-2xl border border-slate-200/60 p-3 glass"><p className="text-xs text-slate-500">Ack</p><p className="text-2xl font-bold text-amber-700">{overview?.summary.acknowledged_alerts ?? 0}</p></div>
        <div className="rounded-2xl border border-slate-200/60 p-3 glass"><p className="text-xs text-slate-500">{L('已解决', 'Resolved')}</p><p className="text-2xl font-bold text-emerald-700">{overview?.summary.resolved_alerts ?? 0}</p></div>
        <div className="rounded-2xl border border-slate-200/60 p-3 glass"><p className="text-xs text-slate-500">{L('总数', 'Total')}</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.total_alerts ?? 0}</p></div>
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="rounded-3xl border border-slate-200/60 p-4 glass xl:col-span-2">
          <div className="mb-3 flex items-center gap-2">
            <Activity size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">{L('指标趋势', 'Metric Trends')}</h3>
          </div>
          <div className="overflow-auto rounded-xl border border-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="px-3 py-2 text-left">{L('时间', 'Time')}</th>
                  <th className="px-3 py-2 text-left">QPS</th>
                  <th className="px-3 py-2 text-left">Latency(ms)</th>
                  <th className="px-3 py-2 text-left">{L('失败率', 'Failure Rate')}</th>
                  <th className="px-3 py-2 text-left">{L('告警数', 'Alert Count')}</th>
                </tr>
              </thead>
              <tbody>
                {(overview?.trends ?? []).map((point) => (
                  <tr key={point.timestamp} className="border-t border-slate-100">
                    <td className="px-3 py-2 text-xs text-slate-600">{new Date(point.timestamp).toLocaleTimeString(isZh ? 'zh-CN' : 'en-US')}</td>
                    <td className="px-3 py-2">{point.qps.toFixed(3)}</td>
                    <td className="px-3 py-2">{point.latency_ms.toFixed(1)}</td>
                    <td className="px-3 py-2">{(point.failure_rate * 100).toFixed(2)}%</td>
                    <td className="px-3 py-2">{point.alert_count}</td>
                  </tr>
                ))}
                {(overview?.trends.length ?? 0) === 0 && <tr><td colSpan={5} className="px-3 py-4 text-sm text-slate-500">{L('暂无趋势数据。', 'No trend points available.')}</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-3xl border border-slate-200/60 p-4 glass">
          <div className="mb-3 flex items-center gap-2">
            <CheckCircle2 size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">{L('模块健康度', 'Module Health')}</h3>
          </div>
          <div className="space-y-2">
            {(overview?.module_health ?? []).map((item) => (
              <div key={item.module} className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-slate-800">{item.module}</p>
                  <span className={clsx('rounded-full px-2 py-0.5 text-xs font-semibold', moduleStatusClass[item.status] ?? 'bg-slate-100 text-slate-700')}>{item.status}</span>
                </div>
                <p className="mt-1 text-xs text-slate-500">score {item.score} | open {item.open_alerts} | critical {item.critical_alerts}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="rounded-3xl border border-slate-200/60 p-4 glass">
          <div className="mb-3 flex items-center gap-2">
            <AlertTriangle size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">{L('告警列表', 'Alert List')}</h3>
          </div>
          <div className="max-h-[620px] space-y-2 overflow-auto">
            {loadingAlerts && <p className="text-sm text-slate-500">{L('正在加载告警...', 'Loading alerts...')}</p>}
            {(alertsResp?.items ?? []).map((item) => (
              <button key={item.id} onClick={() => setSelectedAlertId(item.id)} className={clsx('w-full rounded-xl border p-3 text-left transition', selectedAlertId === item.id ? 'border-cyan-500 bg-cyan-50' : 'border-slate-200 bg-white hover:border-slate-300')}>
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-slate-800">{item.title}</p>
                  <span className={clsx('rounded-full px-2 py-0.5 text-xs font-semibold', severityClass[item.severity] ?? 'bg-slate-100 text-slate-700')}>{item.severity}</span>
                </div>
                <p className="mt-1 text-xs text-slate-500">{item.source_module} | {item.status} | {formatDate(item.created_at)}</p>
                <p className="mt-1 line-clamp-2 text-xs text-slate-600">{item.description}</p>
              </button>
            ))}
            {(alertsResp?.items.length ?? 0) === 0 && !loadingAlerts && <p className="text-sm text-slate-500">{L('当前筛选条件下没有告警。', 'No alerts under current filters.')}</p>}
          </div>
        </div>

        <div className="rounded-3xl border border-slate-200/60 p-4 glass">
          <div className="mb-3 flex items-center gap-2">
            <Search size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">{L('告警详情', 'Alert Detail')}</h3>
          </div>
          {!detail && <p className="text-sm text-slate-500">{L('请选择一条告警查看详情。', 'Select one alert to inspect details.')}</p>}
          {loadingDetail && <p className="text-sm text-slate-500">{L('正在加载详情...', 'Loading detail...')}</p>}
          {detail && (
            <div className="space-y-3">
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold text-slate-800">{detail.alert.title}</p>
                  <span className={clsx('rounded-full px-2 py-0.5 text-xs font-semibold', severityClass[detail.alert.severity] ?? 'bg-slate-100 text-slate-700')}>{detail.alert.severity}</span>
                </div>
                <p className="mt-1 text-xs text-slate-500">{detail.metadata.source_module} | {detail.alert.status} | alert#{detail.alert.id}</p>
                <p className="mt-2 text-xs text-slate-600">{detail.alert.description}</p>
                <div className="mt-2 text-xs text-slate-500">tenant={detail.metadata.tenant_id ?? '-'} | project={detail.metadata.project_id} | source={detail.metadata.source_type}:{detail.metadata.source_id}</div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="mb-2 text-xs font-semibold text-slate-700">{L('上下文指标', 'Context Metrics')} ({detail.context_metrics.window_minutes}m)</p>
                <div className="max-h-40 space-y-1 overflow-auto">
                  {detail.context_metrics.timeline.map((item) => (
                    <div key={item.from} className="border-b border-slate-100 pb-1 text-xs text-slate-600">
                      {new Date(item.from).toLocaleTimeString(isZh ? 'zh-CN' : 'en-US')} - {new Date(item.to).toLocaleTimeString(isZh ? 'zh-CN' : 'en-US')}
                      {' | qps '} {item.qps.toFixed(3)}
                      {' | latency '} {item.latency_ms.toFixed(1)}
                      {' | fail '} {(item.failure_rate * 100).toFixed(2)}%
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="mb-2 text-xs font-semibold text-slate-700">{L('操作', 'Operations')}</p>
                <textarea rows={3} value={noteText} onChange={(e) => setNoteText(e.target.value)} placeholder={L('认领 / 解决备注', 'claim/resolve note')} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
                <div className="mt-2 flex flex-wrap gap-2">
                  <button onClick={() => void operate('CLAIM')} disabled={operating || detail.alert.status === 'RESOLVED'} className="rounded-lg bg-amber-500 px-3 py-1.5 text-sm text-white disabled:opacity-50">{L('认领', 'Claim')}</button>
                  <button onClick={() => void operate('RESOLVE')} disabled={operating || detail.alert.status === 'RESOLVED'} className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm text-white disabled:opacity-50">{L('解决', 'Resolve')}</button>
                  <button onClick={() => void operate('NOTE')} disabled={operating} className="rounded-lg bg-cyan-600 px-3 py-1.5 text-sm text-white disabled:opacity-50">{L('添加备注', 'Add Note')}</button>
                  <button onClick={() => openRelated(detail.alert)} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700">{L('打开关联模块', 'Open Related Module')}</button>
                  <button onClick={() => openKnowledgeForAlert(detail.alert)} className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm text-white">{L('相关文档', 'Related Docs')}</button>
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="mb-2 text-xs font-semibold text-slate-700">{L('操作历史', 'Action History')}</p>
                <div className="max-h-52 space-y-2 overflow-auto">
                  {detail.history.map((item) => (
                    <div key={item.id} className="border-b border-slate-100 pb-2">
                      <p className="text-xs font-medium text-slate-700">{item.action} by {item.actor}</p>
                      <p className="text-[11px] text-slate-500">{formatDate(item.created_at)}</p>
                      {item.note && <p className="mt-1 text-xs text-slate-600">{item.note}</p>}
                    </div>
                  ))}
                  {detail.history.length === 0 && <p className="text-sm text-slate-500">{L('暂无历史记录。', 'No history yet.')}</p>}
                </div>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
