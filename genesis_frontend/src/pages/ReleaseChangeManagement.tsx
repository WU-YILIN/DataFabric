import { FormEvent, useEffect, useMemo, useState } from 'react'
import { clsx } from 'clsx'
import { CheckCircle2, Clock3, RefreshCw, ShieldAlert } from 'lucide-react'

import {
  GenesisApi,
  type ReleaseChangeDetailResponse,
  type ReleaseChangeItem,
  type ReleaseChangeListResponse,
  type ReleaseExecuteResponse,
  type ReleaseOverviewResponse,
} from '../services/api'
import { useBrowserErrorAlert } from '../hooks/useBrowserErrorAlert'
import { useLanguage } from '../i18n/language'

const CHANGE_TYPE_OPTIONS = [
  'EVENT_CHANGE',
  'DQ_RULE_CHANGE',
  'PIPELINE_CHANGE',
  'SCHEDULER_CHANGE',
  'POLICY_CHANGE',
  'INTEGRATION_CHANGE',
  'ACCESS_CHANGE',
  'OTHER',
]

const PRIORITY_OPTIONS = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']

const statusClassName = (status: string): string => {
  if (status === 'COMPLETED') return 'bg-emerald-100 text-emerald-700'
  if (status === 'FAILED') return 'bg-rose-100 text-rose-700'
  if (status === 'ROLLED_BACK') return 'bg-amber-100 text-amber-700'
  if (status === 'PENDING_APPROVAL' || status === 'REVISION_REQUIRED') return 'bg-sky-100 text-sky-700'
  if (status === 'APPROVED' || status === 'SCHEDULED' || status === 'IN_PROGRESS') return 'bg-indigo-100 text-indigo-700'
  return 'bg-slate-100 text-slate-700'
}

const riskClassName = (riskLevel: string): string => {
  if (riskLevel === 'HIGH') return 'bg-rose-100 text-rose-700'
  if (riskLevel === 'MEDIUM') return 'bg-amber-100 text-amber-700'
  return 'bg-emerald-100 text-emerald-700'
}

const availableActions = (status: string): string[] => {
  if (status === 'PENDING_APPROVAL' || status === 'REVISION_REQUIRED') {
    return ['APPROVE', 'REQUEST_REVISION', 'REJECT', 'CANCEL']
  }
  if (status === 'APPROVED') {
    return ['SCHEDULE', 'EXECUTE', 'REQUEST_REVISION', 'REJECT', 'CANCEL']
  }
  if (status === 'SCHEDULED') {
    return ['EXECUTE', 'REQUEST_REVISION', 'REJECT', 'CANCEL']
  }
  if (status === 'FAILED' || status === 'COMPLETED' || status === 'IN_PROGRESS') {
    return ['ROLLBACK']
  }
  return []
}

const jsonPretty = (value: unknown): string => JSON.stringify(value ?? {}, null, 2)

const ReleaseChangeManagement = () => {
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const L = (cn: string, en: string) => (isZh ? cn : en)
  const [overview, setOverview] = useState<ReleaseOverviewResponse | null>(null)
  const [listResp, setListResp] = useState<ReleaseChangeListResponse | null>(null)
  const [detail, setDetail] = useState<ReleaseChangeDetailResponse | null>(null)
  const [selectedChangeId, setSelectedChangeId] = useState<number | null>(null)

  const [filters, setFilters] = useState({
    q: '',
    change_type: 'ALL',
    status: 'ALL',
    priority: 'ALL',
    source_type: '',
    requested_by: '',
  })

  const [createForm, setCreateForm] = useState({
    change_type: 'PIPELINE_CHANGE',
    source_type: 'PIPELINE',
    source_id: '',
    title: '',
    description: '',
    priority: 'MEDIUM',
    impact_scope_text: '{\n  "project_ids": []\n}',
    before_payload_text: '{\n  "status": "OLD"\n}',
    after_payload_text: '{\n  "status": "NEW"\n}',
    release_plan_text: '{\n  "window": "offpeak",\n  "strategy": "rolling"\n}',
    rollback_plan_text: '{\n  "strategy": "restore_previous_version"\n}',
    manual_review_note: '',
  })

  const [actionForm, setActionForm] = useState({
    note: '',
    scheduled_at: '',
    simulate_failure: false,
    failure_reason: 'Simulated release failure in module 22',
    trigger_rollback: true,
  })

  const [loading, setLoading] = useState(false)
  const [operating, setOperating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useBrowserErrorAlert(error)
  const [message, setMessage] = useState<string | null>(null)

  const parseJsonObject = (text: string, field: string): Record<string, unknown> | null => {
    try {
      const value = JSON.parse(text)
      if (!value || typeof value !== 'object' || Array.isArray(value)) {
        setError(`${field} ${L('必须是 JSON 对象', 'must be a JSON object')}`)
        return null
      }
      return value as Record<string, unknown>
    } catch {
      setError(`${field} ${L('必须是合法 JSON', 'must be valid JSON')}`)
      return null
    }
  }

  const loadOverview = async () => {
    const data = await GenesisApi.getReleaseOverview()
    setOverview(data)
  }

  const loadChanges = async () => {
    const data = await GenesisApi.getReleaseChanges({
      q: filters.q.trim() || undefined,
      change_type: filters.change_type === 'ALL' ? undefined : filters.change_type,
      status: filters.status === 'ALL' ? undefined : filters.status,
      priority: filters.priority === 'ALL' ? undefined : filters.priority,
      source_type: filters.source_type.trim() || undefined,
      requested_by: filters.requested_by.trim() || undefined,
      limit: 200,
      offset: 0,
    })
    setListResp(data)
    if (!selectedChangeId && data.items.length > 0) {
      setSelectedChangeId(data.items[0].id)
      return
    }
    if (selectedChangeId && !data.items.find((item) => item.id === selectedChangeId)) {
      setSelectedChangeId(data.items[0]?.id ?? null)
    }
  }

  const loadDetail = async (changeId: number) => {
    const data = await GenesisApi.getReleaseChangeDetail(changeId)
    setDetail(data)
  }

  const refreshAll = async () => {
    setLoading(true)
    setError(null)
    try {
      await Promise.all([loadOverview(), loadChanges()])
      if (selectedChangeId != null) {
        await loadDetail(selectedChangeId)
      }
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? L('加载发布中心失败', 'Failed to load release center'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refreshAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (selectedChangeId != null) {
      void loadDetail(selectedChangeId).catch(() => setDetail(null))
      return
    }
    setDetail(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedChangeId])

  const onApplyFilters = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await loadChanges()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? L('加载变更失败', 'Failed to load changes'))
    } finally {
      setLoading(false)
    }
  }

  const onCreateChange = async (event: FormEvent) => {
    event.preventDefault()
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const impactScope = parseJsonObject(createForm.impact_scope_text, 'impact_scope')
      const beforePayload = parseJsonObject(createForm.before_payload_text, 'before_payload')
      const afterPayload = parseJsonObject(createForm.after_payload_text, 'after_payload')
      const releasePlan = parseJsonObject(createForm.release_plan_text, 'release_plan_payload')
      const rollbackPlan = parseJsonObject(createForm.rollback_plan_text, 'rollback_plan_payload')
      if (!impactScope || !beforePayload || !afterPayload || !releasePlan || !rollbackPlan) {
        return
      }

      const created = await GenesisApi.createReleaseChange({
        change_type: createForm.change_type,
        source_type: createForm.source_type.trim().toUpperCase(),
        source_id: createForm.source_id.trim(),
        title: createForm.title.trim(),
        description: createForm.description.trim() || undefined,
        priority: createForm.priority,
        impact_scope: impactScope,
        before_payload: beforePayload,
        after_payload: afterPayload,
        release_plan_payload: releasePlan,
        rollback_plan_payload: rollbackPlan,
        manual_review_note: createForm.manual_review_note.trim() || undefined,
      })

      setMessage(`${L('变更已创建', 'Created change')} #${created.id}`)
      setCreateForm((prev) => ({
        ...prev,
        source_id: '',
        title: '',
        description: '',
        manual_review_note: '',
      }))
      await Promise.all([loadOverview(), loadChanges()])
      setSelectedChangeId(created.id)
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? L('创建变更失败', 'Create change failed'))
    } finally {
      setOperating(false)
    }
  }

  const onOperateChange = async (action: string) => {
    if (!detail) return
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      if (action === 'SCHEDULE' && !actionForm.scheduled_at.trim()) {
        setError(L('SCHEDULE 操作必须填写 scheduled_at', 'scheduled_at is required for SCHEDULE action'))
        return
      }

      const result = await GenesisApi.operateReleaseChange(detail.change.id, {
        action,
        note: actionForm.note.trim() || undefined,
        scheduled_at: action === 'SCHEDULE' ? actionForm.scheduled_at : undefined,
        simulate_failure: action === 'EXECUTE' ? actionForm.simulate_failure : undefined,
        failure_reason: action === 'EXECUTE' ? actionForm.failure_reason.trim() || undefined : undefined,
        trigger_rollback: action === 'EXECUTE' ? actionForm.trigger_rollback : undefined,
      })

      const hasExecution = 'execution' in result
      const updated = (hasExecution ? (result as ReleaseExecuteResponse).change : result) as ReleaseChangeItem
      setMessage(`Action ${action} applied, status: ${updated.status}`)
      await Promise.all([loadOverview(), loadChanges(), loadDetail(updated.id)])
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? 'Operate change failed')
    } finally {
      setOperating(false)
    }
  }

  const statusOptions = useMemo(
    () => ['ALL', ...(listResp?.facets.statuses.map((item) => item.status) ?? [])],
    [listResp?.facets.statuses],
  )
  const changeTypeOptions = useMemo(
    () => ['ALL', ...(listResp?.facets.change_types.map((item) => item.change_type) ?? CHANGE_TYPE_OPTIONS)],
    [listResp?.facets.change_types],
  )
  const priorityOptions = useMemo(
    () => ['ALL', ...(listResp?.facets.priorities.map((item) => item.priority) ?? PRIORITY_OPTIONS)],
    [listResp?.facets.priorities],
  )

  const selectedRiskLevel = (detail?.change.risk_assessment.final?.risk_level ?? 'LOW').toUpperCase()

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">{L('???????', 'Release & Change Management')}</h2>
          <p className="text-slate-500 text-base">{L('??????????????????????????', 'Track approvals, execute release windows, and manage rollback with full audit history.')}</p>
        </div>
        <button
          onClick={() => void refreshAll()}
          disabled={loading || operating}
          className="rounded-xl bg-slate-900 text-white px-4 py-2.5 font-medium hover:bg-slate-800 disabled:opacity-60 flex items-center gap-2"
        >
          <RefreshCw size={16} />
          {L('??', 'Refresh')}
        </button>
      </header>
      {message && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>}

      <section className="grid grid-cols-2 md:grid-cols-7 gap-3">
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">{L('??', 'Total')}</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.total_changes ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">{L('???', 'Pending')}</p><p className="text-2xl font-bold text-sky-700">{overview?.summary.pending_approval ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">{L('???', 'In Progress')}</p><p className="text-2xl font-bold text-indigo-700">{overview?.summary.in_progress ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">{L('???', 'Completed')}</p><p className="text-2xl font-bold text-emerald-700">{overview?.summary.completed ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">{L('??', 'Failed')}</p><p className="text-2xl font-bold text-rose-700">{overview?.summary.failed ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">{L('???', 'Rolled Back')}</p><p className="text-2xl font-bold text-amber-700">{overview?.summary.rolled_back ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">{L('??????', 'High Risk Open')}</p><p className="text-2xl font-bold text-rose-700">{overview?.summary.high_risk_open ?? 0}</p></div>
      </section>

      <form onSubmit={onApplyFilters} className="glass rounded-3xl border border-slate-200/60 p-4">
        <div className="grid grid-cols-1 md:grid-cols-7 gap-3">
          <input value={filters.q} onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))} placeholder={L('???????????', 'search title/source/requester')} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
          <select value={filters.change_type} onChange={(e) => setFilters((prev) => ({ ...prev, change_type: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{changeTypeOptions.map((item) => <option key={item} value={item}>{item}</option>)}</select>
          <select value={filters.status} onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{statusOptions.map((item) => <option key={item} value={item}>{item}</option>)}</select>
          <select value={filters.priority} onChange={(e) => setFilters((prev) => ({ ...prev, priority: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{priorityOptions.map((item) => <option key={item} value={item}>{item}</option>)}</select>
          <input value={filters.source_type} onChange={(e) => setFilters((prev) => ({ ...prev, source_type: e.target.value }))} placeholder={L('????', 'source type')} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
          <input value={filters.requested_by} onChange={(e) => setFilters((prev) => ({ ...prev, requested_by: e.target.value }))} placeholder={L('???', 'requested by')} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
          <button type="submit" className="rounded-xl bg-cyan-600 text-white px-4 py-2 text-sm font-semibold">{L('????', 'Apply Filters')}</button>
        </div>
      </form>

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="space-y-4">
          <div className="glass rounded-3xl border border-slate-200/60 p-4">
            <h3 className="text-sm font-semibold text-slate-800 mb-3 flex items-center gap-2"><Clock3 size={16} /> {L('???', 'Change Orders')}</h3>
            <div className="space-y-2 max-h-[28rem] overflow-auto">
              {(listResp?.items ?? []).map((item) => (
                <button key={item.id} onClick={() => setSelectedChangeId(item.id)} className={clsx('w-full text-left rounded-xl border px-3 py-2 transition', selectedChangeId === item.id ? 'border-cyan-300 bg-cyan-50/70' : 'border-slate-200 bg-white hover:bg-slate-50')}>
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-semibold text-slate-800 text-sm line-clamp-2">{item.title}</p>
                    <span className={clsx('px-2 py-0.5 rounded-full text-[11px] font-semibold', statusClassName(item.status))}>{item.status}</span>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">{item.change_type} | {item.source.source_type}:{item.source.source_id}</p>
                  <div className="mt-2 flex items-center justify-between">
                    <span className="text-[11px] text-slate-500">{item.requested_by}</span>
                    <span className={clsx('px-2 py-0.5 rounded-full text-[11px] font-semibold', riskClassName((item.risk_assessment.final?.risk_level ?? 'LOW').toUpperCase()))}>
                      {(item.risk_assessment.final?.risk_level ?? 'LOW').toUpperCase()}
                    </span>
                  </div>
                </button>
              ))}
              {(listResp?.items.length ?? 0) === 0 && <p className="text-sm text-slate-500">{L('????????', 'No change requests found.')}</p>}
            </div>
          </div>

          <form onSubmit={onCreateChange} className="glass rounded-3xl border border-slate-200/60 p-4 space-y-2">
            <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2"><ShieldAlert size={16} /> {L('??????', 'New Change Request')}</h3>
            <div className="grid grid-cols-2 gap-2">
              <select value={createForm.change_type} onChange={(e) => setCreateForm((prev) => ({ ...prev, change_type: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{CHANGE_TYPE_OPTIONS.map((item) => <option key={item} value={item}>{item}</option>)}</select>
              <select value={createForm.priority} onChange={(e) => setCreateForm((prev) => ({ ...prev, priority: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{PRIORITY_OPTIONS.map((item) => <option key={item} value={item}>{item}</option>)}</select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <input value={createForm.source_type} onChange={(e) => setCreateForm((prev) => ({ ...prev, source_type: e.target.value }))} placeholder={L('????', 'source type')} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
              <input value={createForm.source_id} onChange={(e) => setCreateForm((prev) => ({ ...prev, source_id: e.target.value }))} placeholder={L('?? ID', 'source id')} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            </div>
            <input value={createForm.title} onChange={(e) => setCreateForm((prev) => ({ ...prev, title: e.target.value }))} placeholder={L('??', 'title')} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <textarea value={createForm.description} onChange={(e) => setCreateForm((prev) => ({ ...prev, description: e.target.value }))} rows={2} placeholder={L('??', 'description')} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <textarea value={createForm.impact_scope_text} onChange={(e) => setCreateForm((prev) => ({ ...prev, impact_scope_text: e.target.value }))} rows={4} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-mono" />
            <textarea value={createForm.before_payload_text} onChange={(e) => setCreateForm((prev) => ({ ...prev, before_payload_text: e.target.value }))} rows={4} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-mono" />
            <textarea value={createForm.after_payload_text} onChange={(e) => setCreateForm((prev) => ({ ...prev, after_payload_text: e.target.value }))} rows={4} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-mono" />
            <textarea value={createForm.release_plan_text} onChange={(e) => setCreateForm((prev) => ({ ...prev, release_plan_text: e.target.value }))} rows={3} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-mono" />
            <textarea value={createForm.rollback_plan_text} onChange={(e) => setCreateForm((prev) => ({ ...prev, rollback_plan_text: e.target.value }))} rows={3} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-mono" />
            <textarea value={createForm.manual_review_note} onChange={(e) => setCreateForm((prev) => ({ ...prev, manual_review_note: e.target.value }))} rows={2} placeholder={L('??????????', 'manual review note (optional)')} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <button type="submit" disabled={operating} className="w-full rounded-xl bg-cyan-600 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60">{L('????', 'Create Change')}</button>
          </form>
        </div>

        <div className="xl:col-span-2 space-y-4">
          {!detail ? (
            <div className="glass rounded-3xl border border-slate-200/60 p-8 text-sm text-slate-500">{L('?????????????', 'Select one change request to view details.')}</div>
          ) : (
            <div className="glass rounded-3xl border border-slate-200/60 p-4 space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-lg font-semibold text-slate-900">{detail.change.title}</h3>
                  <p className="text-sm text-slate-500">{detail.change.change_type} | {detail.change.source.source_type}:{detail.change.source.source_id}</p>
                  <p className="text-xs text-slate-500">Requested by {detail.change.requested_by}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={clsx('px-2 py-1 rounded-full text-xs font-semibold', statusClassName(detail.change.status))}>{detail.change.status}</span>
                  <span className={clsx('px-2 py-1 rounded-full text-xs font-semibold', riskClassName(selectedRiskLevel))}>{selectedRiskLevel}</span>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">{L('???', 'Priority')}</p><p className="font-semibold text-slate-800">{detail.change.priority}</p></div>
                <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">{L('????', 'Approver Role')}</p><p className="font-semibold text-slate-800">{detail.change.current_approver_role ?? '-'}</p></div>
                <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">{L('???', 'Approved By')}</p><p className="font-semibold text-slate-800">{detail.change.approved_by ?? '-'}</p></div>
                <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">{L('???', 'Rejected By')}</p><p className="font-semibold text-slate-800">{detail.change.rejected_by ?? '-'}</p></div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <h4 className="text-sm font-semibold text-slate-800 mb-2">{L('????', 'Impact Scope')}</h4>
                  <pre className="text-xs text-slate-700 whitespace-pre-wrap break-all bg-slate-50 border border-slate-200 rounded-xl p-3">{jsonPretty(detail.change.impact_scope)}</pre>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <h4 className="text-sm font-semibold text-slate-800 mb-2">{L('????', 'Risk Assessment')}</h4>
                  <pre className="text-xs text-slate-700 whitespace-pre-wrap break-all bg-slate-50 border border-slate-200 rounded-xl p-3">{jsonPretty(detail.change.risk_assessment)}</pre>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <h4 className="text-sm font-semibold text-slate-800 mb-2">{L('????', 'Diff Payload')}</h4>
                  <pre className="text-xs text-slate-700 whitespace-pre-wrap break-all bg-slate-50 border border-slate-200 rounded-xl p-3">{jsonPretty(detail.change.diff_payload)}</pre>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <h4 className="text-sm font-semibold text-slate-800 mb-2">{L('?? / ????', 'Release / Rollback Plan')}</h4>
                  <pre className="text-xs text-slate-700 whitespace-pre-wrap break-all bg-slate-50 border border-slate-200 rounded-xl p-3">{jsonPretty({ release_plan: detail.change.release_plan, rollback_plan: detail.change.rollback_plan })}</pre>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-2">
                <h4 className="text-sm font-semibold text-slate-800 flex items-center gap-2"><CheckCircle2 size={15} /> {L('??????', 'Operate Change')}</h4>
                <textarea value={actionForm.note} onChange={(e) => setActionForm((prev) => ({ ...prev, note: e.target.value }))} rows={2} placeholder={L('????', 'action note')} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  <input type="datetime-local" value={actionForm.scheduled_at} onChange={(e) => setActionForm((prev) => ({ ...prev, scheduled_at: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                  <input value={actionForm.failure_reason} onChange={(e) => setActionForm((prev) => ({ ...prev, failure_reason: e.target.value }))} placeholder={L('????????', 'failure reason for execute simulate')} className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                </div>
                <div className="flex flex-wrap items-center gap-4 text-sm text-slate-700">
                  <label className="inline-flex items-center gap-2">
                    <input type="checkbox" checked={actionForm.simulate_failure} onChange={(e) => setActionForm((prev) => ({ ...prev, simulate_failure: e.target.checked }))} />
                    {L('??????', 'simulate execution failure')}
                  </label>
                  <label className="inline-flex items-center gap-2">
                    <input type="checkbox" checked={actionForm.trigger_rollback} onChange={(e) => setActionForm((prev) => ({ ...prev, trigger_rollback: e.target.checked }))} />
                    {L('???????', 'auto rollback on failure')}
                  </label>
                </div>
                <div className="flex flex-wrap gap-2">
                  {availableActions(detail.change.status).map((action) => (
                    <button key={action} onClick={() => void onOperateChange(action)} disabled={operating} className="rounded-xl bg-slate-900 text-white px-3 py-2 text-xs font-semibold disabled:opacity-60">
                      {action}
                    </button>
                  ))}
                  {availableActions(detail.change.status).length === 0 && <p className="text-sm text-slate-500">{L('???????????', 'No operation available for current status.')}</p>}
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <h4 className="text-sm font-semibold text-slate-800 mb-2">{L('????', 'Action History')}</h4>
                <div className="space-y-2 max-h-64 overflow-auto">
                  {detail.history.map((item) => (
                    <div key={item.id} className="rounded-xl border border-slate-200 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-semibold text-slate-800">{item.action}</p>
                        <p className="text-xs text-slate-500">{item.created_at ? new Date(item.created_at).toLocaleString() : '-'}</p>
                      </div>
                      <p className="text-xs text-slate-500">{item.actor}</p>
                      {item.note && <p className="text-sm text-slate-700 mt-1">{item.note}</p>}
                      <pre className="text-xs text-slate-700 whitespace-pre-wrap break-all bg-slate-50 border border-slate-200 rounded-lg p-2 mt-2">{jsonPretty(item.payload)}</pre>
                    </div>
                  ))}
                  {detail.history.length === 0 && <p className="text-sm text-slate-500">{L('???????', 'No history records.')}</p>}
                </div>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

export default ReleaseChangeManagement
