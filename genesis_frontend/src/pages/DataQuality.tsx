import { useEffect, useMemo, useState } from 'react'
import { ChevronRight, Filter, Play, Plus, Search, X } from 'lucide-react'

import { clsx } from 'clsx'
import { useNavigate } from 'react-router-dom'
import {
  GenesisApi,
  type DataQualityRule,
  type DataQualityRuleDetailResponse,
  type DataQualityRuleOptionAsset,
  type DataQualityRuleOptionEvent,
} from '../services/api'

type RuleFormState = {
  name: string
  asset_id: string
  event_id: string
  rule_type: string
  target_field: string
  operator: string
  threshold: string
  alert_channels: string
  severity: string
  status: string
  description: string
}

const defaultRuleForm: RuleFormState = {
  name: '',
  asset_id: '',
  event_id: '',
  rule_type: 'NOT_NULL',
  target_field: '',
  operator: '',
  threshold: '{\n  "max_failure_rate": 0.01\n}',
  alert_channels: 'email',
  severity: 'MEDIUM',
  status: 'ACTIVE',
  description: '',
}

const DataQuality = () => {
  const navigate = useNavigate()
  const [rules, setRules] = useState<DataQualityRule[]>([])
  const [events, setEvents] = useState<DataQualityRuleOptionEvent[]>([])
  const [assets, setAssets] = useState<DataQualityRuleOptionAsset[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const [q, setQ] = useState('')
  const [ruleTypeFilter, setRuleTypeFilter] = useState('')
  const [severityFilter, setSeverityFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [assetIdFilter, setAssetIdFilter] = useState('')
  const [eventIdFilter, setEventIdFilter] = useState('')

  const [selectedRuleId, setSelectedRuleId] = useState<number | null>(null)
  const [detail, setDetail] = useState<DataQualityRuleDetailResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [formOpen, setFormOpen] = useState(false)
  const [editingRule, setEditingRule] = useState<DataQualityRule | null>(null)
  const [formState, setFormState] = useState<RuleFormState>(defaultRuleForm)
  const [formSubmitting, setFormSubmitting] = useState(false)
  const [runLoadingRuleId, setRunLoadingRuleId] = useState<number | null>(null)

  const assetMap = useMemo(() => new Map(assets.map((item) => [item.id, item])), [assets])
  const eventMap = useMemo(() => new Map(events.map((item) => [item.id, item])), [events])

  const loadOptions = async () => {
    try {
      const data = await GenesisApi.getDataQualityRuleOptions()
      setEvents(data.events)
      setAssets(data.assets)
    } catch {
      // keep page usable even if options fail
    }
  }

  const loadRules = async () => {
    setLoading(true)
    setError(null)
    try {
      const rows = await GenesisApi.getDataQualityRules({
        q: q || undefined,
        asset_id: assetIdFilter ? Number(assetIdFilter) : undefined,
        event_id: eventIdFilter ? Number(eventIdFilter) : undefined,
        rule_type: ruleTypeFilter || undefined,
        severity: severityFilter || undefined,
        status: statusFilter || undefined,
      })
      setRules(rows)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load data quality rules')
    } finally {
      setLoading(false)
    }
  }

  const loadRuleDetail = async (ruleId: number) => {
    setSelectedRuleId(ruleId)
    setDetailLoading(true)
    setError(null)
    setDetail(null)
    try {
      const data = await GenesisApi.getDataQualityRuleDetail(ruleId)
      setDetail(data)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load rule detail')
    } finally {
      setDetailLoading(false)
    }
  }

  useEffect(() => {
    void Promise.all([loadOptions(), loadRules()])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const openCreateModal = () => {
    setEditingRule(null)
    setFormState(defaultRuleForm)
    setFormOpen(true)
  }

  const openEditModal = (rule: DataQualityRule) => {
    setEditingRule(rule)
    setFormState({
      name: rule.name,
      asset_id: rule.asset_id != null ? String(rule.asset_id) : '',
      event_id: String(rule.event_id),
      rule_type: rule.rule_type,
      target_field: rule.target_field ?? '',
      operator: rule.operator ?? '',
      threshold: JSON.stringify(rule.threshold ?? {}, null, 2),
      alert_channels: (rule.alert_channels ?? []).join(', '),
      severity: rule.severity,
      status: rule.status,
      description: rule.description ?? '',
    })
    setFormOpen(true)
  }

  const submitForm = async () => {
    setFormSubmitting(true)
    setError(null)
    setNotice(null)
    try {
      let parsedThreshold: Record<string, unknown> = {}
      try {
        parsedThreshold = JSON.parse(formState.threshold || '{}')
      } catch {
        throw new Error('Threshold must be valid JSON')
      }
      const alertChannels = formState.alert_channels
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)

      const payload = {
        name: formState.name,
        asset_id: formState.asset_id ? Number(formState.asset_id) : null,
        event_id: formState.event_id ? Number(formState.event_id) : null,
        rule_type: formState.rule_type,
        target_field: formState.target_field || null,
        operator: formState.operator || null,
        threshold: parsedThreshold,
        alert_channels: alertChannels,
        severity: formState.severity,
        status: formState.status,
        description: formState.description || null,
      }

      if (editingRule) {
        await GenesisApi.updateDataQualityRule(editingRule.id, payload)
        setNotice('Rule updated')
      } else {
        await GenesisApi.createDataQualityRule(payload)
        setNotice('Rule created')
      }
      setFormOpen(false)
      await loadRules()
      if (editingRule?.id) {
        await loadRuleDetail(editingRule.id)
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? e?.message ?? 'Failed to save rule')
    } finally {
      setFormSubmitting(false)
    }
  }

  const runRule = async (ruleId: number) => {
    setRunLoadingRuleId(ruleId)
    setError(null)
    setNotice(null)
    try {
      const result = await GenesisApi.runDataQualityRule(ruleId, {
        trigger_source: 'manual',
      })
      setNotice(`Rule #${ruleId} executed: ${result.result}`)
      await loadRules()
      if (selectedRuleId === ruleId) {
        await loadRuleDetail(ruleId)
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to run rule')
    } finally {
      setRunLoadingRuleId(null)
    }
  }

  const openExploreForRule = (ruleId: number) => {
    const params = new URLSearchParams({
      source_type: 'DATA_QUALITY_RULE',
      source_id: String(ruleId),
    })
    navigate(`/explore?${params.toString()}`)
  }

  const openKnowledgeForRule = (ruleId: number) => {
    const params = new URLSearchParams({
      source_type: 'DATA_QUALITY_RULE',
      source_id: String(ruleId),
    })
    navigate(`/knowledge?${params.toString()}`)
  }

  return (
    <div className="max-w-7xl mx-auto animate-in fade-in slide-in-from-bottom-8 duration-700">
      <div className="flex justify-between items-center mb-6">
        <header>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">Data Quality</h2>
          <p className="text-slate-500 text-base">Define rules, execute checks, and triage quality alerts.</p>
        </header>
        <button
          onClick={openCreateModal}
          className="rounded-xl bg-cyan-600 text-white px-4 py-2.5 font-semibold flex items-center gap-2 hover:bg-cyan-500"
        >
          <Plus size={18} />
          New Rule
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-rose-700 text-sm">{error}</div>
      )}
      {notice && (
        <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-emerald-700 text-sm">
          {notice}
        </div>
      )}

      <div className="glass rounded-3xl overflow-hidden shadow-sm border border-gray-200/50">
        <div className="p-4 border-b border-gray-200/50 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-7 gap-3 bg-gray-50/60">
          <div className="relative md:col-span-2 xl:col-span-2">
            <Search className="absolute left-3 top-2.5 text-gray-400" size={16} />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search rule name / type / field"
              className="w-full pl-9 pr-3 py-2.5 bg-white border border-gray-200 rounded-xl outline-none focus:ring-2 focus:ring-cyan-300/60"
            />
          </div>
          <select
            value={assetIdFilter}
            onChange={(e) => setAssetIdFilter(e.target.value)}
            className="px-3 py-2.5 bg-white border border-gray-200 rounded-xl outline-none"
          >
            <option value="">All Assets</option>
            {assets.map((asset) => (
              <option key={asset.id} value={asset.id}>
                {asset.name} ({asset.asset_type})
              </option>
            ))}
          </select>
          <select
            value={eventIdFilter}
            onChange={(e) => setEventIdFilter(e.target.value)}
            className="px-3 py-2.5 bg-white border border-gray-200 rounded-xl outline-none"
          >
            <option value="">All Events</option>
            {events.map((event) => (
              <option key={event.id} value={event.id}>
                {event.code}
              </option>
            ))}
          </select>
          <select
            value={ruleTypeFilter}
            onChange={(e) => setRuleTypeFilter(e.target.value)}
            className="px-3 py-2.5 bg-white border border-gray-200 rounded-xl outline-none"
          >
            <option value="">All Types</option>
            <option value="NOT_NULL">NOT_NULL</option>
            <option value="UNIQUENESS">UNIQUENESS</option>
            <option value="VALUE_RANGE">VALUE_RANGE</option>
            <option value="REGEX">REGEX</option>
            <option value="ENUM">ENUM</option>
            <option value="CUSTOM_SQL">CUSTOM_SQL</option>
          </select>
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="px-3 py-2.5 bg-white border border-gray-200 rounded-xl outline-none"
          >
            <option value="">All Severity</option>
            <option value="LOW">LOW</option>
            <option value="MEDIUM">MEDIUM</option>
            <option value="HIGH">HIGH</option>
            <option value="CRITICAL">CRITICAL</option>
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2.5 bg-white border border-gray-200 rounded-xl outline-none"
          >
            <option value="">All Status</option>
            <option value="ACTIVE">ACTIVE</option>
            <option value="PAUSED">PAUSED</option>
            <option value="DRAFT">DRAFT</option>
            <option value="DEPRECATED">DEPRECATED</option>
          </select>
          <button
            onClick={loadRules}
            className="md:col-span-2 xl:col-span-7 rounded-xl bg-slate-900 text-white px-4 py-2.5 font-medium flex items-center justify-center gap-2 hover:bg-slate-800"
          >
            <Filter size={16} />
            Apply Filters
          </button>
        </div>

        <div className="bg-white/60">
          {loading ? (
            <div className="p-12 text-center text-gray-400">Loading rules...</div>
          ) : (
            <ul className="divide-y divide-gray-100">
              {rules.map((rule) => (
                <li
                  key={rule.id}
                  className="group hover:bg-cyan-50/50 transition-colors cursor-pointer"
                  onClick={() => void loadRuleDetail(rule.id)}
                >
                  <div className="flex items-center p-4 sm:px-6 gap-3">
                    <div className="min-w-0 flex-1 grid grid-cols-1 md:grid-cols-7 gap-3 items-center">
                      <div className="md:col-span-2">
                        <p className="text-sm font-semibold text-slate-900 truncate">{rule.name}</p>
                        <p className="text-xs text-slate-500 truncate">
                          {rule.asset?.name ?? assetMap.get(rule.asset_id ?? -1)?.name ?? '-'} | {rule.event?.code ?? eventMap.get(rule.event_id)?.code ?? '-'}
                        </p>
                      </div>
                      <div className="text-sm text-slate-700">{rule.rule_type}</div>
                      <div className="text-sm text-slate-700">{rule.target_field || '-'}</div>
                      <div>
                        <span
                          className={clsx(
                            'px-2 py-1 rounded-full text-xs font-semibold',
                            rule.severity === 'CRITICAL'
                              ? 'bg-rose-100 text-rose-700'
                              : rule.severity === 'HIGH'
                                ? 'bg-amber-100 text-amber-700'
                                : rule.severity === 'MEDIUM'
                                  ? 'bg-indigo-100 text-indigo-700'
                                  : 'bg-slate-100 text-slate-700',
                          )}
                        >
                          {rule.severity}
                        </span>
                      </div>
                      <div>
                        <span
                          className={clsx(
                            'px-2 py-1 rounded-full text-xs font-semibold',
                            rule.status === 'ACTIVE'
                              ? 'bg-emerald-100 text-emerald-700'
                              : rule.status === 'PAUSED'
                                ? 'bg-amber-100 text-amber-700'
                                : 'bg-slate-100 text-slate-700',
                          )}
                        >
                          {rule.status}
                        </span>
                      </div>
                      <div className="text-sm text-slate-700">
                        {rule.last_run ? `${Math.round(rule.last_run.pass_rate * 100)}%` : '-'}
                      </div>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        void runRule(rule.id)
                      }}
                      disabled={runLoadingRuleId === rule.id}
                      className="rounded-lg bg-indigo-100 text-indigo-700 px-2.5 py-1.5 text-xs hover:bg-indigo-200 disabled:opacity-50 flex items-center gap-1"
                    >
                      <Play size={12} />
                      Run
                    </button>
                    <ChevronRight size={18} className="text-gray-300 group-hover:text-cyan-600" />
                  </div>
                </li>
              ))}
              {!loading && rules.length === 0 && (
                <li className="p-10 text-center text-slate-500">No rules matched current filters.</li>
              )}
            </ul>
          )}
        </div>
      </div>

      {selectedRuleId && (
        <>
          <div
            className="fixed inset-0 bg-black/25 z-40"
            onClick={() => {
              setSelectedRuleId(null)
              setDetail(null)
            }}
          />
          <aside className="fixed right-0 top-0 h-screen w-[620px] bg-white z-50 border-l border-slate-200 shadow-2xl overflow-auto">
            <div className="p-5 border-b border-slate-200 flex items-center justify-between">
              <h3 className="font-bold text-slate-900 text-lg">DQ Rule Detail</h3>
              <button
                onClick={() => {
                  setSelectedRuleId(null)
                  setDetail(null)
                }}
                className="p-2 rounded-lg hover:bg-slate-100"
              >
                <X size={16} />
              </button>
            </div>

            {detailLoading || !detail ? (
              <div className="p-8 text-slate-500">Loading detail...</div>
            ) : (
              <div className="p-5 space-y-6">
                <div className="space-y-1">
                  <p className="text-xs text-slate-500 uppercase tracking-wide">Rule Config</p>
                  <p className="text-xl font-semibold text-slate-900">{detail.rule.name}</p>
                  <p className="text-sm text-slate-600">
                    Type: {detail.rule.rule_type} | Field: {detail.rule.target_field || '-'} | Operator: {detail.rule.operator || '-'}
                  </p>
                  <p className="text-sm text-slate-600">
                    Severity: {detail.rule.severity} | Status: {detail.rule.status} | Version: {detail.rule.version}
                  </p>
                  <p className="text-sm text-slate-600">
                    Asset: {detail.rule.asset?.name || '-'} | Event: {detail.rule.event?.code || '-'}
                  </p>
                  <p className="text-sm text-slate-600">
                    Channels: {detail.rule.alert_channels?.length ? detail.rule.alert_channels.join(', ') : '-'}
                  </p>
                  <p className="text-sm text-slate-600">{detail.rule.description || '-'}</p>
                </div>

                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Threshold</p>
                  <pre className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs overflow-auto text-slate-700">
                    {JSON.stringify(detail.rule.threshold, null, 2)}
                  </pre>
                </div>

                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Recent Results</p>
                  <div className="space-y-2">
                    {detail.recent_results.length === 0 && <p className="text-sm text-slate-500">No execution results yet.</p>}
                    {detail.recent_results.map((item) => (
                      <div key={item.id} className="rounded-xl border border-slate-200 p-3 bg-white text-sm">
                        <p className="font-semibold text-slate-800">
                          {item.result} | pass_rate={Math.round(item.pass_rate * 100)}%
                        </p>
                        <p className="text-xs text-slate-500 mt-1">
                          checked={item.checked_count} | failed={item.failed_count} | {item.triggered_by}
                        </p>
                        <p className="text-xs text-slate-500 mt-1">{new Date(item.executed_at).toLocaleString()}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Alerts</p>
                  <div className="space-y-2">
                    {detail.alerts.length === 0 && <p className="text-sm text-slate-500">No related alerts.</p>}
                    {detail.alerts.map((item) => (
                      <div key={item.id} className="rounded-xl border border-slate-200 p-3 bg-white text-sm">
                        <p className="font-semibold text-slate-800">{item.title}</p>
                        <p className="text-xs text-slate-500 mt-1">
                          {item.severity} | {item.status} | {new Date(item.created_at).toLocaleString()}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Version History</p>
                  <div className="space-y-2">
                    {detail.version_history.length === 0 && <p className="text-sm text-slate-500">No rule updates yet.</p>}
                    {detail.version_history.map((item) => (
                      <div key={item.id} className="rounded-xl border border-slate-200 p-3 bg-white text-sm">
                        <p className="font-semibold text-slate-800">
                          {item.from_version}
                          {' -> '}
                          {item.to_version}
                        </p>
                        <pre className="mt-2 text-[11px] bg-slate-50 rounded p-2 overflow-auto">
                          {JSON.stringify(item.diff, null, 2)}
                        </pre>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-4 gap-3">
                  <button
                    onClick={() => openEditModal(detail.rule)}
                    className="rounded-xl bg-slate-900 text-white px-3 py-2.5 font-medium hover:bg-slate-800"
                  >
                    Edit Rule
                  </button>
                  <button
                    onClick={() => void runRule(detail.rule.id)}
                    disabled={runLoadingRuleId === detail.rule.id}
                    className="rounded-xl bg-indigo-600 text-white px-3 py-2.5 font-medium hover:bg-indigo-500 disabled:opacity-60"
                  >
                    Run Rule
                  </button>
                  <button
                    onClick={() => openExploreForRule(detail.rule.id)}
                    className="rounded-xl bg-indigo-600 text-white px-3 py-2.5 font-medium hover:bg-indigo-500"
                  >
                    Open in Explore
                  </button>
                  <button
                    onClick={() => openKnowledgeForRule(detail.rule.id)}
                    className="rounded-xl bg-emerald-600 text-white px-3 py-2.5 font-medium hover:bg-emerald-500"
                  >
                    Related Docs
                  </button>
                </div>
              </div>
            )}
          </aside>
        </>
      )}

      {formOpen && (
        <>
          <div className="fixed inset-0 bg-black/30 z-50" onClick={() => setFormOpen(false)} />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
            <div className="w-full max-w-3xl rounded-2xl border border-slate-200 bg-white shadow-2xl p-5 space-y-4 max-h-[95vh] overflow-auto">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-slate-900">{editingRule ? 'Edit Rule' : 'Create Rule'}</h3>
                <button onClick={() => setFormOpen(false)} className="p-2 rounded hover:bg-slate-100">
                  <X size={16} />
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <input
                  value={formState.name}
                  onChange={(e) => setFormState((prev) => ({ ...prev, name: e.target.value }))}
                  placeholder="Rule Name"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none md:col-span-2"
                />
                <select
                  value={formState.asset_id}
                  onChange={(e) => setFormState((prev) => ({ ...prev, asset_id: e.target.value }))}
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                >
                  <option value="">No Asset</option>
                  {assets.map((asset) => (
                    <option key={asset.id} value={asset.id}>
                      {asset.name} ({asset.asset_type})
                    </option>
                  ))}
                </select>
                <select
                  value={formState.event_id}
                  onChange={(e) => setFormState((prev) => ({ ...prev, event_id: e.target.value }))}
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                >
                  <option value="">Auto derive from asset</option>
                  {events.map((event) => (
                    <option key={event.id} value={event.id}>
                      {event.code} ({event.governance_status})
                    </option>
                  ))}
                </select>
                <select
                  value={formState.rule_type}
                  onChange={(e) => setFormState((prev) => ({ ...prev, rule_type: e.target.value }))}
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                >
                  <option value="NOT_NULL">NOT_NULL</option>
                  <option value="UNIQUENESS">UNIQUENESS</option>
                  <option value="VALUE_RANGE">VALUE_RANGE</option>
                  <option value="REGEX">REGEX</option>
                  <option value="ENUM">ENUM</option>
                  <option value="CUSTOM_SQL">CUSTOM_SQL</option>
                </select>
                <input
                  value={formState.target_field}
                  onChange={(e) => setFormState((prev) => ({ ...prev, target_field: e.target.value }))}
                  placeholder="Target Field"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                />
                <input
                  value={formState.operator}
                  onChange={(e) => setFormState((prev) => ({ ...prev, operator: e.target.value }))}
                  placeholder="Operator"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                />
                <input
                  value={formState.alert_channels}
                  onChange={(e) => setFormState((prev) => ({ ...prev, alert_channels: e.target.value }))}
                  placeholder="Alert Channels (comma separated)"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                />
                <select
                  value={formState.severity}
                  onChange={(e) => setFormState((prev) => ({ ...prev, severity: e.target.value }))}
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                >
                  <option value="LOW">LOW</option>
                  <option value="MEDIUM">MEDIUM</option>
                  <option value="HIGH">HIGH</option>
                  <option value="CRITICAL">CRITICAL</option>
                </select>
                <select
                  value={formState.status}
                  onChange={(e) => setFormState((prev) => ({ ...prev, status: e.target.value }))}
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                >
                  <option value="ACTIVE">ACTIVE</option>
                  <option value="PAUSED">PAUSED</option>
                  <option value="DRAFT">DRAFT</option>
                  <option value="DEPRECATED">DEPRECATED</option>
                </select>
                <textarea
                  value={formState.description}
                  onChange={(e) => setFormState((prev) => ({ ...prev, description: e.target.value }))}
                  placeholder="Description"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none md:col-span-2 h-24"
                />
                <textarea
                  value={formState.threshold}
                  onChange={(e) => setFormState((prev) => ({ ...prev, threshold: e.target.value }))}
                  placeholder="Threshold JSON"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none md:col-span-2 h-40 font-mono text-sm"
                />
              </div>

              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setFormOpen(false)}
                  className="px-4 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  onClick={() => void submitForm()}
                  disabled={formSubmitting}
                  className="px-4 py-2 rounded-xl bg-cyan-600 text-white font-medium hover:bg-cyan-500 disabled:opacity-70"
                >
                  {formSubmitting ? 'Saving...' : editingRule ? 'Save Changes' : 'Create Rule'}
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default DataQuality
