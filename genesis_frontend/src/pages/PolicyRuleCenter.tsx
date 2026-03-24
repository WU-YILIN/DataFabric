import { FormEvent, useEffect, useMemo, useState } from 'react'
import { clsx } from 'clsx'
import { FileStack, PlayCircle, RefreshCw, Scale, ShieldAlert } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useLanguage } from '../i18n/language'

import {
  GenesisApi,
  type PolicyRuleDetailResponse,
  type PolicyRuleItem,
  type PolicyRuleListResponse,
  type PolicyTemplateItem,
} from '../services/api'
import { useBrowserErrorAlert } from '../hooks/useBrowserErrorAlert'

const PolicyRuleCenterPage = () => {
  const navigate = useNavigate()
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const [overview, setOverview] = useState<any>(null)
  const [templates, setTemplates] = useState<PolicyTemplateItem[]>([])
  const [listResp, setListResp] = useState<PolicyRuleListResponse | null>(null)
  const [detail, setDetail] = useState<PolicyRuleDetailResponse | null>(null)
  const [selectedRuleId, setSelectedRuleId] = useState<number | null>(null)

  const [filters, setFilters] = useState({
    q: '',
    rule_type: 'ALL',
    scope_type: 'ALL',
    status: 'ALL',
    severity: 'ALL',
  })

  const [createForm, setCreateForm] = useState({
    template_key: 'EVENT_NAMING_STANDARD',
    name: '',
    severity: 'MEDIUM',
    status: 'DRAFT',
    scope_type: 'PROJECT',
    scope_value: '',
    conditionsJson: '{}',
    actionsJson: '{}',
    contentJson: '{}',
    prompt_text: '',
  })

  const [editForm, setEditForm] = useState({
    name: '',
    description: '',
    severity: 'MEDIUM',
    status: 'DRAFT',
    scope_type: 'PROJECT',
    scope_value: '',
    conditionsJson: '{}',
    actionsJson: '{}',
    contentJson: '{}',
    prompt_text: '',
    change_note: '',
  })

  const [actionForm, setActionForm] = useState({
    action: 'ACTIVATE',
    change_note: '',
  })

  const [evaluateForm, setEvaluateForm] = useState({
    module: 'GOVERNANCE',
    action: 'APPROVE',
    include_draft: false,
    contextJson: '{\n  "event_name": "commerce.order_created",\n  "failure_rate": 0.02,\n  "risk_score": 0.55,\n  "fields": {\n    "user_id": "string",\n    "order_id": "string"\n  }\n}',
  })
  const [evaluateResult, setEvaluateResult] = useState<any>(null)

  const [loading, setLoading] = useState(false)
  const [operating, setOperating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useBrowserErrorAlert(error)
  const [message, setMessage] = useState<string | null>(null)

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
    const data = await GenesisApi.getPolicyOverview()
    setOverview(data)
  }

  const loadTemplates = async () => {
    const data = await GenesisApi.getPolicyTemplates()
    setTemplates(data.items)
  }

  const loadRules = async () => {
    const data = await GenesisApi.getPolicyRules({
      q: filters.q.trim() || undefined,
      rule_type: filters.rule_type === 'ALL' ? undefined : filters.rule_type,
      scope_type: filters.scope_type === 'ALL' ? undefined : filters.scope_type,
      status: filters.status === 'ALL' ? undefined : filters.status,
      severity: filters.severity === 'ALL' ? undefined : filters.severity,
      limit: 200,
      offset: 0,
    })
    setListResp(data)
    if (!selectedRuleId && data.items.length > 0) {
      setSelectedRuleId(data.items[0].id)
    }
    if (selectedRuleId && !data.items.some((item) => item.id === selectedRuleId)) {
      setSelectedRuleId(data.items[0]?.id ?? null)
    }
  }

  const loadDetail = async (ruleId: number) => {
    const data = await GenesisApi.getPolicyRuleDetail(ruleId)
    setDetail(data)
    const rule = data.rule
    setEditForm({
      name: rule.name,
      description: rule.description ?? '',
      severity: rule.severity,
      status: rule.status,
      scope_type: rule.scope.scope_type,
      scope_value: rule.scope.scope_value ?? '',
      conditionsJson: JSON.stringify(rule.conditions_payload ?? {}, null, 2),
      actionsJson: JSON.stringify(rule.actions_payload ?? {}, null, 2),
      contentJson: JSON.stringify(rule.content_payload ?? {}, null, 2),
      prompt_text: rule.prompt_text ?? '',
      change_note: '',
    })
  }

  const refreshAll = async () => {
    setLoading(true)
    setError(null)
    try {
      await Promise.all([loadOverview(), loadTemplates(), loadRules()])
      if (selectedRuleId != null) {
        await loadDetail(selectedRuleId)
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load policy center')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refreshAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (selectedRuleId != null) {
      void loadDetail(selectedRuleId).catch(() => setDetail(null))
    } else {
      setDetail(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRuleId])

  const onApplyFilters = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await loadRules()
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load rules')
    } finally {
      setLoading(false)
    }
  }

  const onCreateRule = async (event: FormEvent) => {
    event.preventDefault()
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const created = await GenesisApi.createPolicyRule({
        template_key: createForm.template_key,
        name: createForm.name.trim() || undefined,
        severity: createForm.severity,
        status: createForm.status,
        scope_type: createForm.scope_type,
        scope_value: createForm.scope_value.trim() || undefined,
        conditions_payload: parseJsonObject(createForm.conditionsJson) ?? undefined,
        actions_payload: parseJsonObject(createForm.actionsJson) ?? undefined,
        content_payload: parseJsonObject(createForm.contentJson) ?? undefined,
        prompt_text: createForm.prompt_text.trim() || undefined,
      })
      setMessage(`Rule #${created.id} created`)
      setCreateForm((prev) => ({ ...prev, name: '' }))
      await Promise.all([loadOverview(), loadRules()])
      setSelectedRuleId(created.id)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Create rule failed')
    } finally {
      setOperating(false)
    }
  }

  const onUpdateRule = async () => {
    if (!detail) return
    const conditions = parseJsonObject(editForm.conditionsJson)
    const actions = parseJsonObject(editForm.actionsJson)
    const content = parseJsonObject(editForm.contentJson)
    if (!conditions || !actions || !content) {
      setError('Edit JSON payloads must be objects')
      return
    }
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const updated = await GenesisApi.updatePolicyRule(detail.rule.id, {
        name: editForm.name.trim(),
        description: editForm.description.trim() || undefined,
        severity: editForm.severity,
        status: editForm.status,
        scope_type: editForm.scope_type,
        scope_value: editForm.scope_value.trim() || undefined,
        conditions_payload: conditions,
        actions_payload: actions,
        content_payload: content,
        prompt_text: editForm.prompt_text.trim() || undefined,
        change_note: editForm.change_note.trim() || undefined,
      })
      setMessage(`Rule #${updated.id} updated`)
      await Promise.all([loadOverview(), loadRules(), loadDetail(updated.id)])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Update rule failed')
    } finally {
      setOperating(false)
    }
  }

  const onOperateRule = async () => {
    if (!detail) return
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const updated = await GenesisApi.operatePolicyRule(detail.rule.id, {
        action: actionForm.action,
        change_note: actionForm.change_note.trim() || undefined,
      })
      setMessage(`Rule action applied: ${updated.status}`)
      await Promise.all([loadOverview(), loadRules(), loadDetail(updated.id)])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Rule action failed')
    } finally {
      setOperating(false)
    }
  }

  const onRollback = async (versionId: number) => {
    if (!detail) return
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const updated = await GenesisApi.rollbackPolicyRuleVersion(detail.rule.id, versionId, {
        change_note: 'rollback from policy center',
      })
      setMessage(`Rolled back to snapshot version from #${versionId}`)
      await Promise.all([loadOverview(), loadRules(), loadDetail(updated.id)])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Rollback failed')
    } finally {
      setOperating(false)
    }
  }

  const onEvaluate = async () => {
    const contextPayload = parseJsonObject(evaluateForm.contextJson)
    if (!contextPayload) {
      setError('Evaluation context must be JSON object')
      return
    }
    setOperating(true)
    setError(null)
    try {
      const result = await GenesisApi.evaluatePolicy({
        module: evaluateForm.module,
        action: evaluateForm.action,
        include_draft: evaluateForm.include_draft,
        context_payload: contextPayload,
        limit: 200,
      })
      setEvaluateResult(result)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Evaluate failed')
    } finally {
      setOperating(false)
    }
  }

  const ruleTypes = useMemo(() => ['ALL', ...(listResp?.facets.rule_types.map((item) => item.rule_type) ?? [])], [listResp?.facets.rule_types])
  const scopeTypes = useMemo(() => ['ALL', ...(listResp?.facets.scope_types.map((item) => item.scope_type) ?? [])], [listResp?.facets.scope_types])
  const statuses = useMemo(() => ['ALL', ...(listResp?.facets.statuses.map((item) => item.status) ?? [])], [listResp?.facets.statuses])
  const severities = useMemo(() => ['ALL', ...(listResp?.facets.severities.map((item) => item.severity) ?? [])], [listResp?.facets.severities])

  const selectedRule: PolicyRuleItem | null = detail?.rule ?? null

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white/80 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-900">{isZh ? '下一步建议' : 'Recommended Next Step'}</p>
            <p className="text-xs text-slate-600">
              {isZh ? '策略评估通过后，建议前往发布中心执行变更并在审计日志确认留痕。' : 'After policy validation, proceed to Release Center and verify traces in audit logs.'}
            </p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => navigate('/release-center')} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs hover:bg-slate-50">
              {isZh ? '去发布中心' : 'Go Release Center'}
            </button>
            <button onClick={() => navigate('/logs')} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs hover:bg-slate-50">
              {isZh ? '看审计日志' : 'View Audit Logs'}
            </button>
          </div>
        </div>
      </section>
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">Policy & Rule Center</h2>
          <p className="text-slate-500 text-base">Create policies, track versions, evaluate runtime decisions, and govern rule lifecycle.</p>
        </div>
        <button
          onClick={() => void refreshAll()}
          disabled={loading || operating}
          className="rounded-xl bg-slate-900 text-white px-4 py-2.5 font-medium hover:bg-slate-800 disabled:opacity-60 flex items-center gap-2"
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </header>
      {message && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>}

      <section className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Total Rules</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.total_rules ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Active</p><p className="text-2xl font-bold text-emerald-700">{overview?.summary.active_rules ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Draft</p><p className="text-2xl font-bold text-amber-700">{overview?.summary.draft_rules ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Inactive</p><p className="text-2xl font-bold text-slate-700">{overview?.summary.inactive_rules ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Archived</p><p className="text-2xl font-bold text-slate-700">{overview?.summary.archived_rules ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Project Scope</p><p className="text-2xl font-bold text-cyan-700">{overview?.summary.project_scoped_rules ?? 0}</p></div>
      </section>

      <form onSubmit={onApplyFilters} className="glass rounded-3xl border border-slate-200/60 p-4">
        <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
          <input value={filters.q} onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))} placeholder="search by name/type/scope" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
          <select value={filters.rule_type} onChange={(e) => setFilters((prev) => ({ ...prev, rule_type: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{ruleTypes.map((item) => <option key={item} value={item}>{item}</option>)}</select>
          <select value={filters.scope_type} onChange={(e) => setFilters((prev) => ({ ...prev, scope_type: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{scopeTypes.map((item) => <option key={item} value={item}>{item}</option>)}</select>
          <select value={filters.status} onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{statuses.map((item) => <option key={item} value={item}>{item}</option>)}</select>
          <select value={filters.severity} onChange={(e) => setFilters((prev) => ({ ...prev, severity: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{severities.map((item) => <option key={item} value={item}>{item}</option>)}</select>
          <button type="submit" className="rounded-xl bg-cyan-600 text-white px-4 py-2 text-sm font-semibold">Apply Filters</button>
        </div>
      </form>

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="space-y-4">
          <div className="glass rounded-3xl border border-slate-200/60 p-4">
            <h3 className="text-sm font-semibold text-slate-800 mb-3 flex items-center gap-2"><Scale size={16} /> Rules</h3>
            <div className="space-y-2 max-h-[30rem] overflow-auto">
              {(listResp?.items ?? []).map((item) => (
                <button key={item.id} onClick={() => setSelectedRuleId(item.id)} className={clsx('w-full text-left rounded-xl border px-3 py-2 transition', selectedRuleId === item.id ? 'border-cyan-300 bg-cyan-50/70' : 'border-slate-200 bg-white hover:bg-slate-50')}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-semibold text-slate-800 text-sm">{item.name}</p>
                    <span className={clsx('px-2 py-0.5 rounded-full text-xs font-semibold', item.status === 'ACTIVE' ? 'bg-emerald-100 text-emerald-700' : item.status === 'DRAFT' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600')}>{item.status}</span>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">{item.rule_type} | {item.scope.scope_type} | {item.severity}</p>
                </button>
              ))}
            </div>
          </div>

          <form onSubmit={onCreateRule} className="glass rounded-3xl border border-slate-200/60 p-4 space-y-2">
            <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2"><FileStack size={16} /> New Rule</h3>
            <select value={createForm.template_key} onChange={(e) => setCreateForm((prev) => ({ ...prev, template_key: e.target.value }))} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
              {templates.map((item) => <option key={item.key} value={item.key}>{item.key} | {item.name}</option>)}
            </select>
            <input value={createForm.name} onChange={(e) => setCreateForm((prev) => ({ ...prev, name: e.target.value }))} placeholder="override rule name (optional)" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <div className="grid grid-cols-2 gap-2">
              <select value={createForm.severity} onChange={(e) => setCreateForm((prev) => ({ ...prev, severity: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
                <option value="LOW">LOW</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="HIGH">HIGH</option>
                <option value="CRITICAL">CRITICAL</option>
              </select>
              <select value={createForm.status} onChange={(e) => setCreateForm((prev) => ({ ...prev, status: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
                <option value="DRAFT">DRAFT</option>
                <option value="ACTIVE">ACTIVE</option>
              </select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <select value={createForm.scope_type} onChange={(e) => setCreateForm((prev) => ({ ...prev, scope_type: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
                <option value="PROJECT">PROJECT</option>
                <option value="TENANT">TENANT</option>
                <option value="GLOBAL">GLOBAL</option>
                <option value="DOMAIN">DOMAIN</option>
              </select>
              <input value={createForm.scope_value} onChange={(e) => setCreateForm((prev) => ({ ...prev, scope_value: e.target.value }))} placeholder="scope value/domain" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            </div>
            <button type="submit" disabled={operating} className="w-full rounded-xl bg-cyan-600 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60">Create</button>
          </form>
        </div>

        <div className="xl:col-span-2 space-y-4">
          {!selectedRule ? (
            <div className="glass rounded-3xl border border-slate-200/60 p-8 text-sm text-slate-500">Select a rule to view details.</div>
          ) : (
            <>
              <div className="glass rounded-3xl border border-slate-200/60 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-slate-900">{selectedRule.name}</h3>
                  <span className={clsx('px-2.5 py-1 rounded-full text-xs font-semibold', selectedRule.status === 'ACTIVE' ? 'bg-emerald-100 text-emerald-700' : selectedRule.status === 'DRAFT' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-700')}>{selectedRule.status}</span>
                </div>
                <p className="text-xs text-slate-500">{selectedRule.rule_type} | {selectedRule.scope.scope_type} | v{selectedRule.version_no}</p>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                  <div className="rounded-2xl border border-slate-200 bg-white p-3 space-y-2">
                    <input value={editForm.name} onChange={(e) => setEditForm((prev) => ({ ...prev, name: e.target.value }))} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                    <input value={editForm.description} onChange={(e) => setEditForm((prev) => ({ ...prev, description: e.target.value }))} placeholder="description" className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                    <div className="grid grid-cols-2 gap-2">
                      <select value={editForm.severity} onChange={(e) => setEditForm((prev) => ({ ...prev, severity: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm"><option value="LOW">LOW</option><option value="MEDIUM">MEDIUM</option><option value="HIGH">HIGH</option><option value="CRITICAL">CRITICAL</option></select>
                      <select value={editForm.status} onChange={(e) => setEditForm((prev) => ({ ...prev, status: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm"><option value="DRAFT">DRAFT</option><option value="ACTIVE">ACTIVE</option><option value="INACTIVE">INACTIVE</option><option value="ARCHIVED">ARCHIVED</option></select>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <select value={editForm.scope_type} onChange={(e) => setEditForm((prev) => ({ ...prev, scope_type: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm"><option value="PROJECT">PROJECT</option><option value="TENANT">TENANT</option><option value="GLOBAL">GLOBAL</option><option value="DOMAIN">DOMAIN</option></select>
                      <input value={editForm.scope_value} onChange={(e) => setEditForm((prev) => ({ ...prev, scope_value: e.target.value }))} placeholder="scope value" className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                    </div>
                    <textarea value={editForm.conditionsJson} onChange={(e) => setEditForm((prev) => ({ ...prev, conditionsJson: e.target.value }))} rows={5} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-mono" />
                    <textarea value={editForm.actionsJson} onChange={(e) => setEditForm((prev) => ({ ...prev, actionsJson: e.target.value }))} rows={4} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-mono" />
                    <textarea value={editForm.contentJson} onChange={(e) => setEditForm((prev) => ({ ...prev, contentJson: e.target.value }))} rows={4} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-mono" />
                    <textarea value={editForm.prompt_text} onChange={(e) => setEditForm((prev) => ({ ...prev, prompt_text: e.target.value }))} rows={3} placeholder="prompt text (optional)" className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-mono" />
                    <input value={editForm.change_note} onChange={(e) => setEditForm((prev) => ({ ...prev, change_note: e.target.value }))} placeholder="change note" className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                    <button onClick={() => void onUpdateRule()} disabled={operating} className="w-full rounded-xl bg-cyan-600 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60">Save New Version</button>
                  </div>

                  <div className="rounded-2xl border border-slate-200 bg-white p-3 space-y-3">
                    <div>
                      <p className="text-xs text-slate-500 mb-1">Rule Action</p>
                      <div className="grid grid-cols-2 gap-2">
                        <select value={actionForm.action} onChange={(e) => setActionForm((prev) => ({ ...prev, action: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm">
                          <option value="ACTIVATE">ACTIVATE</option>
                          <option value="DEACTIVATE">DEACTIVATE</option>
                          <option value="ARCHIVE">ARCHIVE</option>
                          <option value="DRAFT">DRAFT</option>
                        </select>
                        <input value={actionForm.change_note} onChange={(e) => setActionForm((prev) => ({ ...prev, change_note: e.target.value }))} placeholder="action note" className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                      </div>
                      <button onClick={() => void onOperateRule()} disabled={operating} className="mt-2 w-full rounded-xl bg-slate-900 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60 inline-flex items-center justify-center gap-1"><PlayCircle size={14} /> Apply Action</button>
                    </div>

                    <div>
                      <p className="text-xs text-slate-500 mb-1">Version History</p>
                      <div className="space-y-2 max-h-80 overflow-auto">
                        {detail?.versions.map((version) => (
                          <div key={version.id} className="rounded-lg border border-slate-200 p-2 text-xs text-slate-700">
                            <div className="flex items-center justify-between">
                              <span className="font-semibold">v{version.version_no}</span>
                              <button onClick={() => void onRollback(version.id)} disabled={operating} className="rounded-md border border-slate-300 px-2 py-0.5 text-[11px] hover:bg-slate-50 disabled:opacity-50">Rollback</button>
                            </div>
                            <p>{version.change_note || '-'}</p>
                            <p className="text-slate-500">{version.created_by}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}

          <div className="glass rounded-3xl border border-slate-200/60 p-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2"><ShieldAlert size={16} /> Runtime Evaluate</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              <input value={evaluateForm.module} onChange={(e) => setEvaluateForm((prev) => ({ ...prev, module: e.target.value.toUpperCase() }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
              <input value={evaluateForm.action} onChange={(e) => setEvaluateForm((prev) => ({ ...prev, action: e.target.value.toUpperCase() }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
              <label className="text-xs text-slate-500 inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2">
                <input type="checkbox" checked={evaluateForm.include_draft} onChange={(e) => setEvaluateForm((prev) => ({ ...prev, include_draft: e.target.checked }))} />
                Include DRAFT
              </label>
            </div>
            <textarea value={evaluateForm.contextJson} onChange={(e) => setEvaluateForm((prev) => ({ ...prev, contextJson: e.target.value }))} rows={8} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-mono" />
            <button onClick={() => void onEvaluate()} disabled={operating} className="rounded-xl bg-indigo-600 text-white px-4 py-2 text-sm font-semibold disabled:opacity-60">Evaluate</button>
            {evaluateResult && (
              <div className={clsx('rounded-xl border px-3 py-2 text-sm', evaluateResult.decision === 'REJECT' ? 'border-rose-200 bg-rose-50 text-rose-700' : evaluateResult.decision === 'WARN' ? 'border-amber-200 bg-amber-50 text-amber-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700')}>
                Decision: {evaluateResult.decision} | matched {evaluateResult.matched_rule_count} | violations {evaluateResult.violation_count}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  )
}

export default PolicyRuleCenterPage
