import { FormEvent, useEffect, useMemo, useState } from 'react'
import { clsx } from 'clsx'
import { AlertTriangle, ClipboardList, RefreshCw, ShieldCheck } from 'lucide-react'

import {
  GenesisApi,
  type IncidentCaseItem,
  type IncidentDetailResponse,
  type IncidentListResponse,
  type IncidentOverviewResponse,
  type IncidentTimelineItem,
} from '../services/api'
import { useLanguage } from '../i18n/language'

const STATUS_OPTIONS = ['ALL', 'OPEN', 'TRIAGED', 'INVESTIGATING', 'MITIGATED', 'RESOLVED', 'CLOSED']
const SEVERITY_OPTIONS = ['ALL', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
const SOURCE_OPTIONS = ['ALL', 'ALERT', 'PIPELINE', 'DQ_RULE', 'EVENT', 'RELEASE_CHANGE', 'REPORT', 'OTHER']

const statusClassName = (status: string): string => {
  if (status === 'OPEN') return 'bg-rose-100 text-rose-700'
  if (status === 'TRIAGED') return 'bg-amber-100 text-amber-700'
  if (status === 'INVESTIGATING') return 'bg-orange-100 text-orange-700'
  if (status === 'MITIGATED') return 'bg-cyan-100 text-cyan-700'
  if (status === 'RESOLVED') return 'bg-emerald-100 text-emerald-700'
  if (status === 'CLOSED') return 'bg-slate-200 text-slate-700'
  return 'bg-slate-100 text-slate-700'
}

const severityClassName = (severity: string): string => {
  if (severity === 'CRITICAL') return 'bg-rose-100 text-rose-700'
  if (severity === 'HIGH') return 'bg-orange-100 text-orange-700'
  if (severity === 'MEDIUM') return 'bg-amber-100 text-amber-700'
  if (severity === 'LOW') return 'bg-emerald-100 text-emerald-700'
  return 'bg-slate-100 text-slate-700'
}

const parseJsonObject = (value: string): Record<string, unknown> | null => {
  try {
    const parsed = JSON.parse(value)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
  } catch {
    return null
  }
  return null
}

const prettyJson = (value: unknown): string => JSON.stringify(value ?? {}, null, 2)

const IncidentResponseCenter = () => {
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const [overview, setOverview] = useState<IncidentOverviewResponse | null>(null)
  const [listResp, setListResp] = useState<IncidentListResponse | null>(null)
  const [detail, setDetail] = useState<IncidentDetailResponse | null>(null)
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(null)

  const [filters, setFilters] = useState({
    q: '',
    status: 'ALL',
    severity: 'ALL',
    owner: '',
    assignee: '',
    source_type: 'ALL',
  })

  const [createForm, setCreateForm] = useState({
    source_type: 'ALERT',
    source_id: '',
    title: '',
    summary: '',
    severity: 'HIGH',
    assignee: '',
    note: '',
    runbook_doc_id_text: '',
    context_payload_text: '{\n  "trigger": "manual"\n}',
    impact_payload_text: '{\n  "affected_scope": []\n}',
    resolution_payload_text: '{\n  "plan": []\n}',
  })

  const [updateForm, setUpdateForm] = useState({
    title: '',
    summary: '',
    severity: 'HIGH',
    assignee: '',
    note: '',
    runbook_doc_id_text: '',
    context_payload_text: '{\n  "trigger": "manual"\n}',
    impact_payload_text: '{\n  "affected_scope": []\n}',
    resolution_payload_text: '{\n  "plan": []\n}',
  })

  const [actionForm, setActionForm] = useState({
    note: '',
    assignee: '',
    runbook_doc_id_text: '',
    impact_payload_text: '{\n  "impact": "contained"\n}',
    resolution_payload_text: '{\n  "root_cause": "",\n  "fix": ""\n}',
  })

  const [loading, setLoading] = useState(false)
  const [operating, setOperating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const loadOverview = async () => {
    const data = await GenesisApi.getIncidentOverview()
    setOverview(data)
  }

  const loadCases = async () => {
    const data = await GenesisApi.getIncidentCases({
      q: filters.q.trim() || undefined,
      status: filters.status === 'ALL' ? undefined : filters.status,
      severity: filters.severity === 'ALL' ? undefined : filters.severity,
      owner: filters.owner.trim() || undefined,
      assignee: filters.assignee.trim() || undefined,
      source_type: filters.source_type === 'ALL' ? undefined : filters.source_type,
      limit: 200,
      offset: 0,
    })
    setListResp(data)
    if (!selectedCaseId && data.items.length > 0) {
      setSelectedCaseId(data.items[0].id)
      return
    }
    if (selectedCaseId && !data.items.find((row) => row.id === selectedCaseId)) {
      setSelectedCaseId(data.items[0]?.id ?? null)
    }
  }

  const loadDetail = async (caseId: number) => {
    const data = await GenesisApi.getIncidentCaseDetail(caseId)
    setDetail(data)
  }

  const refreshAll = async () => {
    setLoading(true)
    setError(null)
    try {
      await Promise.all([loadOverview(), loadCases()])
      if (selectedCaseId != null) {
        await loadDetail(selectedCaseId)
      }
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? (isZh ? '加载事故中心失败' : 'Failed to load incident center'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refreshAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (selectedCaseId != null) {
      void loadDetail(selectedCaseId).catch(() => setDetail(null))
    } else {
      setDetail(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCaseId])

  useEffect(() => {
    if (!detail?.case) return
    const row = detail.case
    setUpdateForm({
      title: row.title ?? '',
      summary: row.summary ?? '',
      severity: row.severity ?? 'HIGH',
      assignee: row.assignee ?? '',
      note: '',
      runbook_doc_id_text: row.runbook_doc_id ? String(row.runbook_doc_id) : '',
      context_payload_text: prettyJson(row.context_payload),
      impact_payload_text: prettyJson(row.impact_payload),
      resolution_payload_text: prettyJson(row.resolution_payload),
    })
  }, [detail?.case.id])

  const onApplyFilters = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await loadCases()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? (isZh ? '查询事故列表失败' : 'Failed to query incidents'))
    } finally {
      setLoading(false)
    }
  }

  const onCreateCase = async (event: FormEvent) => {
    event.preventDefault()
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const contextPayload = parseJsonObject(createForm.context_payload_text)
      const impactPayload = parseJsonObject(createForm.impact_payload_text)
      const resolutionPayload = parseJsonObject(createForm.resolution_payload_text)
      if (!contextPayload || !impactPayload || !resolutionPayload) {
        setError(isZh ? '创建 payload 必须是合法 JSON 对象' : 'Create payloads must be valid JSON objects')
        return
      }

      const created = await GenesisApi.createIncidentCase({
        source_type: createForm.source_type,
        source_id: createForm.source_id.trim(),
        title: createForm.title.trim(),
        summary: createForm.summary.trim() || undefined,
        severity: createForm.severity,
        assignee: createForm.assignee.trim() || undefined,
        note: createForm.note.trim() || undefined,
        runbook_doc_id: createForm.runbook_doc_id_text.trim()
          ? Number(createForm.runbook_doc_id_text.trim())
          : undefined,
        context_payload: contextPayload,
        impact_payload: impactPayload,
        resolution_payload: resolutionPayload,
      })
      setMessage(isZh ? `已创建事故 #${created.id}` : `Created incident #${created.id}`)
      setCreateForm((prev) => ({
        ...prev,
        source_id: '',
        title: '',
        summary: '',
        assignee: '',
        note: '',
        runbook_doc_id_text: '',
      }))
      await Promise.all([loadOverview(), loadCases()])
      setSelectedCaseId(created.id)
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? (isZh ? '创建事故失败' : 'Create incident failed'))
    } finally {
      setOperating(false)
    }
  }

  const onUpdateCase = async (event: FormEvent) => {
    event.preventDefault()
    if (!detail?.case) return
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const contextPayload = parseJsonObject(updateForm.context_payload_text)
      const impactPayload = parseJsonObject(updateForm.impact_payload_text)
      const resolutionPayload = parseJsonObject(updateForm.resolution_payload_text)
      if (!contextPayload || !impactPayload || !resolutionPayload) {
        setError(isZh ? '更新 payload 必须是合法 JSON 对象' : 'Update payloads must be valid JSON objects')
        return
      }

      const updated = await GenesisApi.updateIncidentCase(detail.case.id, {
        title: updateForm.title.trim(),
        summary: updateForm.summary.trim() || '',
        severity: updateForm.severity,
        assignee: updateForm.assignee.trim() || '',
        runbook_doc_id: updateForm.runbook_doc_id_text.trim()
          ? Number(updateForm.runbook_doc_id_text.trim())
          : undefined,
        context_payload: contextPayload,
        impact_payload: impactPayload,
        resolution_payload: resolutionPayload,
        note: updateForm.note.trim() || undefined,
      })
      setMessage(isZh ? `已更新事故 #${updated.id}` : `Updated incident #${updated.id}`)
      await Promise.all([loadOverview(), loadCases(), loadDetail(updated.id)])
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? (isZh ? '更新事故失败' : 'Update incident failed'))
    } finally {
      setOperating(false)
    }
  }

  const onOperateCase = async (action: string) => {
    if (!detail?.case) return
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const impactPayload = parseJsonObject(actionForm.impact_payload_text)
      const resolutionPayload = parseJsonObject(actionForm.resolution_payload_text)
      if (!impactPayload || !resolutionPayload) {
        setError(isZh ? '动作 payload 必须是合法 JSON 对象' : 'Action payloads must be valid JSON objects')
        return
      }

      const updated = await GenesisApi.operateIncidentCase(detail.case.id, {
        action,
        note: actionForm.note.trim() || undefined,
        assignee: action === 'ASSIGN' ? actionForm.assignee.trim() || undefined : undefined,
        runbook_doc_id:
          action === 'LINK_RUNBOOK' && actionForm.runbook_doc_id_text.trim()
            ? Number(actionForm.runbook_doc_id_text.trim())
            : undefined,
        impact_payload: action === 'MITIGATE' ? impactPayload : undefined,
        resolution_payload: action === 'RESOLVE' ? resolutionPayload : undefined,
      })
      setMessage(isZh ? `已执行动作 ${action}` : `Action ${action} applied`)
      await Promise.all([loadOverview(), loadCases(), loadDetail(updated.id)])
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? (isZh ? `动作 ${action} 执行失败` : `Action ${action} failed`))
    } finally {
      setOperating(false)
    }
  }

  const statusFilters = useMemo(
    () => ['ALL', ...(listResp?.facets.statuses.map((row) => row.status) ?? STATUS_OPTIONS.slice(1))],
    [listResp?.facets.statuses],
  )
  const severityFilters = useMemo(
    () => ['ALL', ...(listResp?.facets.severities.map((row) => row.severity) ?? SEVERITY_OPTIONS.slice(1))],
    [listResp?.facets.severities],
  )
  const selectedCase: IncidentCaseItem | null = detail?.case ?? null
  const selectedTimeline: IncidentTimelineItem[] = detail?.timeline ?? []

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">{isZh ? '事故响应与 Runbook 中心' : 'Incident Response & Runbook Center'}</h2>
          <p className="text-slate-500 text-base">
            {isZh
              ? '管理事故生命周期、时间线证据与 Runbook 关联。'
              : 'Manage incident lifecycle, timeline evidence, and runbook linkage across project operations.'}
          </p>
        </div>
        <button
          onClick={() => void refreshAll()}
          disabled={loading || operating}
          className="rounded-xl bg-slate-900 text-white px-4 py-2.5 font-medium hover:bg-slate-800 disabled:opacity-60 inline-flex items-center gap-2"
        >
          <RefreshCw size={16} />
          {isZh ? '刷新' : 'Refresh'}
        </button>
      </header>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
      {message && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>
      )}

      <section className="grid grid-cols-2 md:grid-cols-7 gap-3">
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Total</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.total_incidents ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Open</p><p className="text-2xl font-bold text-rose-700">{overview?.summary.open_incidents ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Investigating</p><p className="text-2xl font-bold text-orange-700">{overview?.summary.investigating_incidents ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Mitigated</p><p className="text-2xl font-bold text-cyan-700">{overview?.summary.mitigated_incidents ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Resolved</p><p className="text-2xl font-bold text-emerald-700">{overview?.summary.resolved_incidents ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Closed</p><p className="text-2xl font-bold text-slate-700">{overview?.summary.closed_incidents ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">MTTR(min)</p><p className="text-2xl font-bold text-indigo-700">{overview?.summary.mttr_minutes ?? 0}</p></div>
      </section>

      <form onSubmit={onApplyFilters} className="glass rounded-3xl border border-slate-200/60 p-4">
        <div className="grid grid-cols-1 md:grid-cols-7 gap-3">
          <input value={filters.q} onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))} placeholder="search by title/source/owner" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
          <select value={filters.status} onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{statusFilters.map((row) => <option key={row} value={row}>{row}</option>)}</select>
          <select value={filters.severity} onChange={(e) => setFilters((prev) => ({ ...prev, severity: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{severityFilters.map((row) => <option key={row} value={row}>{row}</option>)}</select>
          <select value={filters.source_type} onChange={(e) => setFilters((prev) => ({ ...prev, source_type: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{SOURCE_OPTIONS.map((row) => <option key={row} value={row}>{row}</option>)}</select>
          <input value={filters.owner} onChange={(e) => setFilters((prev) => ({ ...prev, owner: e.target.value }))} placeholder="owner" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
          <input value={filters.assignee} onChange={(e) => setFilters((prev) => ({ ...prev, assignee: e.target.value }))} placeholder="assignee" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
          <button type="submit" className="rounded-xl bg-cyan-600 text-white px-4 py-2 text-sm font-semibold">{isZh ? '应用筛选' : 'Apply Filters'}</button>
        </div>
      </form>

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="space-y-4">
          <div className="glass rounded-3xl border border-slate-200/60 p-4">
            <h3 className="text-sm font-semibold text-slate-800 mb-3 flex items-center gap-2">
              <ClipboardList size={16} />
              Incident Cases
            </h3>
            <div className="space-y-2 max-h-[28rem] overflow-auto">
              {(listResp?.items ?? []).map((row) => (
                <button
                  key={row.id}
                  onClick={() => setSelectedCaseId(row.id)}
                  className={clsx(
                    'w-full text-left rounded-xl border px-3 py-2 transition',
                    selectedCaseId === row.id ? 'border-cyan-300 bg-cyan-50/70' : 'border-slate-200 bg-white hover:bg-slate-50',
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-semibold text-slate-800 text-sm line-clamp-2">{row.title}</p>
                    <span className={clsx('px-2 py-0.5 rounded-full text-[11px] font-semibold', statusClassName(row.status))}>
                      {row.status}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center gap-2">
                    <span className={clsx('px-2 py-0.5 rounded-full text-[11px] font-semibold', severityClassName(row.severity))}>
                      {row.severity}
                    </span>
                    <span className="text-xs text-slate-500">{row.source_type}:{row.source_id}</span>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">{row.owner} / {row.assignee ?? 'unassigned'}</p>
                </button>
              ))}
              {(listResp?.items.length ?? 0) === 0 && <p className="text-sm text-slate-500">No incidents found.</p>}
            </div>
          </div>

          <form onSubmit={onCreateCase} className="glass rounded-3xl border border-slate-200/60 p-4 space-y-2">
            <h3 className="text-sm font-semibold text-slate-800">{isZh ? '创建事故' : 'Create Incident'}</h3>
            <div className="grid grid-cols-2 gap-2">
              <select value={createForm.source_type} onChange={(e) => setCreateForm((prev) => ({ ...prev, source_type: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{SOURCE_OPTIONS.slice(1).map((row) => <option key={row} value={row}>{row}</option>)}</select>
              <input value={createForm.source_id} onChange={(e) => setCreateForm((prev) => ({ ...prev, source_id: e.target.value }))} placeholder="source id" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            </div>
            <input value={createForm.title} onChange={(e) => setCreateForm((prev) => ({ ...prev, title: e.target.value }))} placeholder="incident title" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <textarea value={createForm.summary} onChange={(e) => setCreateForm((prev) => ({ ...prev, summary: e.target.value }))} rows={2} placeholder="summary" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <div className="grid grid-cols-2 gap-2">
              <select value={createForm.severity} onChange={(e) => setCreateForm((prev) => ({ ...prev, severity: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{SEVERITY_OPTIONS.slice(1).map((row) => <option key={row} value={row}>{row}</option>)}</select>
              <input value={createForm.assignee} onChange={(e) => setCreateForm((prev) => ({ ...prev, assignee: e.target.value }))} placeholder="assignee email/name" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            </div>
            <input value={createForm.runbook_doc_id_text} onChange={(e) => setCreateForm((prev) => ({ ...prev, runbook_doc_id_text: e.target.value }))} placeholder="runbook doc id (optional)" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <textarea value={createForm.note} onChange={(e) => setCreateForm((prev) => ({ ...prev, note: e.target.value }))} rows={2} placeholder="creation note" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <textarea value={createForm.context_payload_text} onChange={(e) => setCreateForm((prev) => ({ ...prev, context_payload_text: e.target.value }))} rows={3} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-mono" />
            <textarea value={createForm.impact_payload_text} onChange={(e) => setCreateForm((prev) => ({ ...prev, impact_payload_text: e.target.value }))} rows={3} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-mono" />
            <textarea value={createForm.resolution_payload_text} onChange={(e) => setCreateForm((prev) => ({ ...prev, resolution_payload_text: e.target.value }))} rows={3} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-mono" />
            <button type="submit" disabled={operating} className="w-full rounded-xl bg-cyan-600 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60">{isZh ? '创建' : 'Create'}</button>
          </form>
        </div>

        <div className="xl:col-span-2 space-y-4">
          {!selectedCase ? (
            <div className="glass rounded-3xl border border-slate-200/60 p-8 text-sm text-slate-500">{isZh ? '请选择一个事故查看详情。' : 'Select one incident to view details.'}</div>
          ) : (
            <div className="glass rounded-3xl border border-slate-200/60 p-4 space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-lg font-semibold text-slate-900">{selectedCase.title}</h3>
                  <p className="text-sm text-slate-500">{selectedCase.source_type}:{selectedCase.source_id} | owner {selectedCase.owner}</p>
                  <p className="text-xs text-slate-500">{selectedCase.summary ?? 'No summary'}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={clsx('px-2 py-1 rounded-full text-xs font-semibold', severityClassName(selectedCase.severity))}>
                    {selectedCase.severity}
                  </span>
                  <span className={clsx('px-2 py-1 rounded-full text-xs font-semibold', statusClassName(selectedCase.status))}>
                    {selectedCase.status}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
                <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Assignee</p><p className="font-semibold text-slate-800">{selectedCase.assignee ?? '-'}</p></div>
                <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Runbook ID</p><p className="font-semibold text-slate-800">{selectedCase.runbook_doc_id ?? '-'}</p></div>
                <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Started</p><p className="font-semibold text-slate-800">{selectedCase.started_at ? new Date(selectedCase.started_at).toLocaleString() : '-'}</p></div>
                <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Resolved</p><p className="font-semibold text-slate-800">{selectedCase.resolved_at ? new Date(selectedCase.resolved_at).toLocaleString() : '-'}</p></div>
                <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Updated</p><p className="font-semibold text-slate-800">{selectedCase.updated_at ? new Date(selectedCase.updated_at).toLocaleString() : '-'}</p></div>
              </div>

              <form onSubmit={onUpdateCase} className="rounded-2xl border border-slate-200 bg-white p-4 space-y-2">
                <h4 className="text-sm font-semibold text-slate-800 flex items-center gap-2"><ShieldCheck size={15} /> Case Metadata</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  <input value={updateForm.title} onChange={(e) => setUpdateForm((prev) => ({ ...prev, title: e.target.value }))} placeholder="title" className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                  <input value={updateForm.assignee} onChange={(e) => setUpdateForm((prev) => ({ ...prev, assignee: e.target.value }))} placeholder="assignee" className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                </div>
                <textarea value={updateForm.summary} onChange={(e) => setUpdateForm((prev) => ({ ...prev, summary: e.target.value }))} rows={2} placeholder="summary" className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                <div className="grid grid-cols-2 gap-2">
                  <select value={updateForm.severity} onChange={(e) => setUpdateForm((prev) => ({ ...prev, severity: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm">{SEVERITY_OPTIONS.slice(1).map((row) => <option key={row} value={row}>{row}</option>)}</select>
                  <input value={updateForm.runbook_doc_id_text} onChange={(e) => setUpdateForm((prev) => ({ ...prev, runbook_doc_id_text: e.target.value }))} placeholder="runbook doc id" className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                </div>
                <textarea value={updateForm.note} onChange={(e) => setUpdateForm((prev) => ({ ...prev, note: e.target.value }))} rows={2} placeholder="update note" className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                <textarea value={updateForm.context_payload_text} onChange={(e) => setUpdateForm((prev) => ({ ...prev, context_payload_text: e.target.value }))} rows={3} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-mono" />
                <textarea value={updateForm.impact_payload_text} onChange={(e) => setUpdateForm((prev) => ({ ...prev, impact_payload_text: e.target.value }))} rows={3} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-mono" />
                <textarea value={updateForm.resolution_payload_text} onChange={(e) => setUpdateForm((prev) => ({ ...prev, resolution_payload_text: e.target.value }))} rows={3} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-mono" />
                <button type="submit" disabled={operating || !selectedCase.capabilities.can_edit} className="rounded-xl bg-cyan-600 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60">{isZh ? '更新事故' : 'Update Case'}</button>
              </form>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-2">
                <h4 className="text-sm font-semibold text-slate-800 flex items-center gap-2"><AlertTriangle size={15} /> Incident Actions</h4>
                <textarea value={actionForm.note} onChange={(e) => setActionForm((prev) => ({ ...prev, note: e.target.value }))} rows={2} placeholder="action note" className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                <div className="grid grid-cols-2 gap-2">
                  <input value={actionForm.assignee} onChange={(e) => setActionForm((prev) => ({ ...prev, assignee: e.target.value }))} placeholder="assign to" className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                  <input value={actionForm.runbook_doc_id_text} onChange={(e) => setActionForm((prev) => ({ ...prev, runbook_doc_id_text: e.target.value }))} placeholder="runbook doc id" className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                </div>
                <textarea value={actionForm.impact_payload_text} onChange={(e) => setActionForm((prev) => ({ ...prev, impact_payload_text: e.target.value }))} rows={3} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-mono" />
                <textarea value={actionForm.resolution_payload_text} onChange={(e) => setActionForm((prev) => ({ ...prev, resolution_payload_text: e.target.value }))} rows={3} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-mono" />
                <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                  <button onClick={() => void onOperateCase('TRIAGE')} disabled={operating || !selectedCase.capabilities.can_edit} className="rounded-xl bg-amber-600 text-white px-3 py-2 text-xs font-semibold disabled:opacity-60">TRIAGE</button>
                  <button onClick={() => void onOperateCase('START_INVESTIGATION')} disabled={operating || !selectedCase.capabilities.can_edit} className="rounded-xl bg-orange-600 text-white px-3 py-2 text-xs font-semibold disabled:opacity-60">INVESTIGATE</button>
                  <button onClick={() => void onOperateCase('MITIGATE')} disabled={operating || !selectedCase.capabilities.can_edit} className="rounded-xl bg-cyan-700 text-white px-3 py-2 text-xs font-semibold disabled:opacity-60">MITIGATE</button>
                  <button onClick={() => void onOperateCase('RESOLVE')} disabled={operating || !selectedCase.capabilities.can_edit} className="rounded-xl bg-emerald-700 text-white px-3 py-2 text-xs font-semibold disabled:opacity-60">RESOLVE</button>
                  <button onClick={() => void onOperateCase('CLOSE')} disabled={operating || !selectedCase.capabilities.can_edit} className="rounded-xl bg-slate-700 text-white px-3 py-2 text-xs font-semibold disabled:opacity-60">CLOSE</button>
                  <button onClick={() => void onOperateCase('REOPEN')} disabled={operating || !selectedCase.capabilities.can_edit} className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-60">REOPEN</button>
                  <button onClick={() => void onOperateCase('ASSIGN')} disabled={operating || !selectedCase.capabilities.can_edit} className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-60">ASSIGN</button>
                  <button onClick={() => void onOperateCase('LINK_RUNBOOK')} disabled={operating || !selectedCase.capabilities.can_edit} className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-60">LINK_RUNBOOK</button>
                  <button onClick={() => void onOperateCase('ADD_NOTE')} disabled={operating || !selectedCase.capabilities.can_edit} className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-60">ADD_NOTE</button>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <h4 className="text-sm font-semibold text-slate-800 mb-2">{isZh ? '时间线' : 'Timeline'}</h4>
                <div className="space-y-2 max-h-72 overflow-auto">
                  {selectedTimeline.map((row) => (
                    <div key={row.id} className="rounded-xl border border-slate-200 p-2">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-xs font-semibold text-slate-800">{row.action}</p>
                        <p className="text-xs text-slate-500">{row.created_at ? new Date(row.created_at).toLocaleString() : '-'}</p>
                      </div>
                      <p className="text-xs text-slate-500">{row.actor}</p>
                      <p className="text-xs text-slate-700 whitespace-pre-wrap">{row.note ?? '-'}</p>
                      <pre className="mt-1 rounded-lg bg-slate-50 border border-slate-200 p-2 text-[11px] text-slate-700 overflow-auto">
                        {prettyJson(row.payload)}
                      </pre>
                    </div>
                  ))}
                  {selectedTimeline.length === 0 && <p className="text-sm text-slate-500">{isZh ? '暂无时间线记录。' : 'No timeline entries.'}</p>}
                </div>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

export default IncidentResponseCenter
