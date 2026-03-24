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
import { useLanguage } from '../i18n/language'
import { useBrowserErrorAlert } from '../hooks/useBrowserErrorAlert'

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

export default function DataQuality() {
  const navigate = useNavigate()
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const L = (cn: string, en: string) => (isZh ? cn : en)

  const [rules, setRules] = useState<DataQualityRule[]>([])
  const [events, setEvents] = useState<DataQualityRuleOptionEvent[]>([])
  const [assets, setAssets] = useState<DataQualityRuleOptionAsset[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  useBrowserErrorAlert(error)

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

  const formatDate = (value?: string | null) => {
    if (!value) return '-'
    return new Date(value).toLocaleString(isZh ? 'zh-CN' : 'en-US', { hour12: false })
  }

  const loadOptions = async () => {
    try {
      const data = await GenesisApi.getDataQualityRuleOptions()
      setEvents(data.events)
      setAssets(data.assets)
    } catch {
      // keep page usable
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
      setError(e?.response?.data?.message ?? L('加载数据质量规则失败', 'Failed to load data quality rules'))
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
      setError(e?.response?.data?.message ?? L('加载规则详情失败', 'Failed to load rule detail'))
    } finally {
      setDetailLoading(false)
    }
  }

  useEffect(() => {
    void Promise.all([loadOptions(), loadRules()])
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
        throw new Error(L('阈值必须是合法 JSON', 'Threshold must be valid JSON'))
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
        setNotice(L('规则已更新', 'Rule updated'))
      } else {
        await GenesisApi.createDataQualityRule(payload)
        setNotice(L('规则已创建', 'Rule created'))
      }

      setFormOpen(false)
      await loadRules()
      if (editingRule?.id) await loadRuleDetail(editingRule.id)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? e?.message ?? L('保存规则失败', 'Failed to save rule'))
    } finally {
      setFormSubmitting(false)
    }
  }

  const runRule = async (ruleId: number) => {
    setRunLoadingRuleId(ruleId)
    setError(null)
    setNotice(null)
    try {
      const result = await GenesisApi.runDataQualityRule(ruleId, { trigger_source: 'manual' })
      setNotice(`${L('规则执行完成', 'Rule executed')} #${ruleId}: ${result.result}`)
      await loadRules()
      if (selectedRuleId === ruleId) await loadRuleDetail(ruleId)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? L('执行规则失败', 'Failed to run rule'))
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
    <div className="mx-auto max-w-7xl animate-in fade-in slide-in-from-bottom-8 duration-700">
      <section className="mb-4 rounded-2xl border border-slate-200 bg-white/80 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-900">{L('推荐下一步', 'Recommended Next Step')}</p>
            <p className="text-xs text-slate-600">{L('规则配置完成后先执行一次校验，再到监控页确认告警链路。', 'Run validation once after rule setup, then verify alert pipeline in monitoring.')}</p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => navigate('/monitoring')} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs hover:bg-slate-50">{L('前往监控', 'Go Monitoring')}</button>
            <button onClick={() => navigate('/cost')} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs hover:bg-slate-50">{L('前往成本', 'Go Cost')}</button>
          </div>
        </div>
      </section>

      <div className="mb-6 flex items-center justify-between">
        <header>
          <h2 className="text-3xl font-bold tracking-tight text-slate-900">{L('数据质量', 'Data Quality')}</h2>
          <p className="text-base text-slate-500">{L('定义规则、执行检查并处置质量告警。', 'Define rules, execute checks, and triage quality alerts.')}</p>
        </header>
        <button onClick={openCreateModal} className="flex items-center gap-2 rounded-xl bg-cyan-600 px-4 py-2.5 font-semibold text-white hover:bg-cyan-500">
          <Plus size={18} />
          {L('新建规则', 'New Rule')}
        </button>
      </div>

      {notice && <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{notice}</div>}

      <div className="overflow-hidden rounded-3xl border border-gray-200/50 shadow-sm glass">
        <div className="grid grid-cols-1 gap-3 border-b border-gray-200/50 bg-gray-50/60 p-4 md:grid-cols-2 xl:grid-cols-7">
          <div className="relative md:col-span-2 xl:col-span-2">
            <Search className="absolute left-3 top-2.5 text-gray-400" size={16} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={L('搜索规则名称 / 类型 / 字段', 'Search rule name / type / field')} className="w-full rounded-xl border border-gray-200 bg-white py-2.5 pl-9 pr-3 outline-none focus:ring-2 focus:ring-cyan-300/60" />
          </div>
          <select value={assetIdFilter} onChange={(e) => setAssetIdFilter(e.target.value)} className="rounded-xl border border-gray-200 bg-white px-3 py-2.5 outline-none">
            <option value="">{L('全部资产', 'All Assets')}</option>
            {assets.map((asset) => <option key={asset.id} value={asset.id}>{asset.name} ({asset.asset_type})</option>)}
          </select>
          <select value={eventIdFilter} onChange={(e) => setEventIdFilter(e.target.value)} className="rounded-xl border border-gray-200 bg-white px-3 py-2.5 outline-none">
            <option value="">{L('全部事件', 'All Events')}</option>
            {events.map((event) => <option key={event.id} value={event.id}>{event.code}</option>)}
          </select>
          <select value={ruleTypeFilter} onChange={(e) => setRuleTypeFilter(e.target.value)} className="rounded-xl border border-gray-200 bg-white px-3 py-2.5 outline-none">
            <option value="">{L('全部类型', 'All Types')}</option>
            <option value="NOT_NULL">NOT_NULL</option>
            <option value="UNIQUENESS">UNIQUENESS</option>
            <option value="VALUE_RANGE">VALUE_RANGE</option>
            <option value="REGEX">REGEX</option>
            <option value="ENUM">ENUM</option>
            <option value="CUSTOM_SQL">CUSTOM_SQL</option>
          </select>
          <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)} className="rounded-xl border border-gray-200 bg-white px-3 py-2.5 outline-none">
            <option value="">{L('全部等级', 'All Severity')}</option>
            <option value="LOW">LOW</option>
            <option value="MEDIUM">MEDIUM</option>
            <option value="HIGH">HIGH</option>
            <option value="CRITICAL">CRITICAL</option>
          </select>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="rounded-xl border border-gray-200 bg-white px-3 py-2.5 outline-none">
            <option value="">{L('全部状态', 'All Status')}</option>
            <option value="ACTIVE">ACTIVE</option>
            <option value="PAUSED">PAUSED</option>
            <option value="DRAFT">DRAFT</option>
            <option value="DEPRECATED">DEPRECATED</option>
          </select>
          <button onClick={() => void loadRules()} className="flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 font-medium text-white hover:bg-slate-800 md:col-span-2 xl:col-span-7">
            <Filter size={16} />
            {L('应用筛选', 'Apply Filters')}
          </button>
        </div>

        <div className="bg-white/60">
          {loading ? (
            <div className="p-12 text-center text-gray-400">{L('正在加载规则...', 'Loading rules...')}</div>
          ) : (
            <ul className="divide-y divide-gray-100">
              {rules.map((rule) => (
                <li key={rule.id} className="group cursor-pointer transition-colors hover:bg-cyan-50/50" onClick={() => void loadRuleDetail(rule.id)}>
                  <div className="flex items-center gap-3 p-4 sm:px-6">
                    <div className="min-w-0 flex-1 grid grid-cols-1 items-center gap-3 md:grid-cols-7">
                      <div className="md:col-span-2">
                        <p className="truncate text-sm font-semibold text-slate-900">{rule.name}</p>
                        <p className="truncate text-xs text-slate-500">
                          {rule.asset?.name ?? assetMap.get(rule.asset_id ?? -1)?.name ?? '-'} | {rule.event?.code ?? eventMap.get(rule.event_id)?.code ?? '-'}
                        </p>
                      </div>
                      <div className="text-sm text-slate-700">{rule.rule_type}</div>
                      <div className="text-sm text-slate-700">{rule.target_field || '-'}</div>
                      <div>
                        <span className={clsx('rounded-full px-2 py-1 text-xs font-semibold', rule.severity === 'CRITICAL' ? 'bg-rose-100 text-rose-700' : rule.severity === 'HIGH' ? 'bg-amber-100 text-amber-700' : rule.severity === 'MEDIUM' ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-700')}>
                          {rule.severity}
                        </span>
                      </div>
                      <div>
                        <span className={clsx('rounded-full px-2 py-1 text-xs font-semibold', rule.status === 'ACTIVE' ? 'bg-emerald-100 text-emerald-700' : rule.status === 'PAUSED' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-700')}>
                          {rule.status}
                        </span>
                      </div>
                      <div className="text-sm text-slate-700">{rule.last_run ? `${Math.round(rule.last_run.pass_rate * 100)}%` : '-'}</div>
                    </div>
                    <button onClick={(e) => { e.stopPropagation(); void runRule(rule.id) }} disabled={runLoadingRuleId === rule.id} className="flex items-center gap-1 rounded-lg bg-indigo-100 px-2.5 py-1.5 text-xs text-indigo-700 hover:bg-indigo-200 disabled:opacity-50">
                      <Play size={12} />
                      {L('运行', 'Run')}
                    </button>
                    <ChevronRight size={18} className="text-gray-300 group-hover:text-cyan-600" />
                  </div>
                </li>
              ))}
              {!loading && rules.length === 0 && <li className="p-10 text-center text-slate-500">{L('当前筛选条件下没有规则。', 'No rules matched current filters.')}</li>}
            </ul>
          )}
        </div>
      </div>

      {selectedRuleId && (
        <>
          <div className="fixed inset-0 z-40 bg-black/25" onClick={() => { setSelectedRuleId(null); setDetail(null) }} />
          <aside className="fixed right-0 top-0 z-50 h-screen w-[620px] overflow-auto border-l border-slate-200 bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-200 p-5">
              <h3 className="text-lg font-bold text-slate-900">{L('质量规则详情', 'DQ Rule Detail')}</h3>
              <button onClick={() => { setSelectedRuleId(null); setDetail(null) }} className="rounded-lg p-2 hover:bg-slate-100"><X size={16} /></button>
            </div>

            {detailLoading || !detail ? (
              <div className="p-8 text-slate-500">{L('正在加载详情...', 'Loading detail...')}</div>
            ) : (
              <div className="space-y-6 p-5">
                <div className="space-y-1">
                  <p className="text-xs uppercase tracking-wide text-slate-500">{L('规则配置', 'Rule Config')}</p>
                  <p className="text-xl font-semibold text-slate-900">{detail.rule.name}</p>
                  <p className="text-sm text-slate-600">{L('类型', 'Type')}: {detail.rule.rule_type} | {L('字段', 'Field')}: {detail.rule.target_field || '-'} | {L('操作符', 'Operator')}: {detail.rule.operator || '-'}</p>
                  <p className="text-sm text-slate-600">{L('严重级别', 'Severity')}: {detail.rule.severity} | {L('状态', 'Status')}: {detail.rule.status} | {L('版本', 'Version')}: {detail.rule.version}</p>
                  <p className="text-sm text-slate-600">{L('资产', 'Asset')}: {detail.rule.asset?.name || '-'} | {L('事件', 'Event')}: {detail.rule.event?.code || '-'}</p>
                  <p className="text-sm text-slate-600">{L('告警通道', 'Channels')}: {detail.rule.alert_channels?.length ? detail.rule.alert_channels.join(', ') : '-'}</p>
                  <p className="text-sm text-slate-600">{detail.rule.description || '-'}</p>
                </div>

                <div>
                  <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">{L('阈值', 'Threshold')}</p>
                  <pre className="overflow-auto rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">{JSON.stringify(detail.rule.threshold, null, 2)}</pre>
                </div>

                <div>
                  <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">{L('最近结果', 'Recent Results')}</p>
                  <div className="space-y-2">
                    {detail.recent_results.length === 0 && <p className="text-sm text-slate-500">{L('暂无执行结果。', 'No execution results yet.')}</p>}
                    {detail.recent_results.map((item) => (
                      <div key={item.id} className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
                        <p className="font-semibold text-slate-800">{item.result} | pass_rate={Math.round(item.pass_rate * 100)}%</p>
                        <p className="mt-1 text-xs text-slate-500">checked={item.checked_count} | failed={item.failed_count} | {item.triggered_by}</p>
                        <p className="mt-1 text-xs text-slate-500">{formatDate(item.executed_at)}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">{L('告警', 'Alerts')}</p>
                  <div className="space-y-2">
                    {detail.alerts.length === 0 && <p className="text-sm text-slate-500">{L('暂无关联告警。', 'No related alerts.')}</p>}
                    {detail.alerts.map((item) => (
                      <div key={item.id} className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
                        <p className="font-semibold text-slate-800">{item.title}</p>
                        <p className="mt-1 text-xs text-slate-500">{item.severity} | {item.status} | {formatDate(item.created_at)}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">{L('版本历史', 'Version History')}</p>
                  <div className="space-y-2">
                    {detail.version_history.length === 0 && <p className="text-sm text-slate-500">{L('暂无规则更新历史。', 'No rule updates yet.')}</p>}
                    {detail.version_history.map((item) => (
                      <div key={item.id} className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
                        <p className="font-semibold text-slate-800">{item.from_version} {' -> '} {item.to_version}</p>
                        <pre className="mt-2 overflow-auto rounded bg-slate-50 p-2 text-[11px]">{JSON.stringify(item.diff, null, 2)}</pre>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-4 gap-3">
                  <button onClick={() => openEditModal(detail.rule)} className="rounded-xl bg-slate-900 px-3 py-2.5 font-medium text-white hover:bg-slate-800">{L('编辑规则', 'Edit Rule')}</button>
                  <button onClick={() => void runRule(detail.rule.id)} disabled={runLoadingRuleId === detail.rule.id} className="rounded-xl bg-indigo-600 px-3 py-2.5 font-medium text-white hover:bg-indigo-500 disabled:opacity-60">{L('运行规则', 'Run Rule')}</button>
                  <button onClick={() => openExploreForRule(detail.rule.id)} className="rounded-xl bg-indigo-600 px-3 py-2.5 font-medium text-white hover:bg-indigo-500">{L('在 Explore 中打开', 'Open in Explore')}</button>
                  <button onClick={() => openKnowledgeForRule(detail.rule.id)} className="rounded-xl bg-emerald-600 px-3 py-2.5 font-medium text-white hover:bg-emerald-500">{L('相关文档', 'Related Docs')}</button>
                </div>
              </div>
            )}
          </aside>
        </>
      )}

      {formOpen && (
        <>
          <div className="fixed inset-0 z-50 bg-black/30" onClick={() => setFormOpen(false)} />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
            <div className="max-h-[95vh] w-full max-w-3xl overflow-auto rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-lg font-semibold text-slate-900">{editingRule ? L('编辑规则', 'Edit Rule') : L('创建规则', 'Create Rule')}</h3>
                <button onClick={() => setFormOpen(false)} className="rounded p-2 hover:bg-slate-100"><X size={16} /></button>
              </div>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <input value={formState.name} onChange={(e) => setFormState((prev) => ({ ...prev, name: e.target.value }))} placeholder={L('规则名称', 'Rule Name')} className="md:col-span-2 rounded-xl border border-slate-200 px-3 py-2.5 outline-none" />
                <select value={formState.asset_id} onChange={(e) => setFormState((prev) => ({ ...prev, asset_id: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2.5 outline-none">
                  <option value="">{L('无资产', 'No Asset')}</option>
                  {assets.map((asset) => <option key={asset.id} value={asset.id}>{asset.name} ({asset.asset_type})</option>)}
                </select>
                <select value={formState.event_id} onChange={(e) => setFormState((prev) => ({ ...prev, event_id: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2.5 outline-none">
                  <option value="">{L('从资产自动推断', 'Auto derive from asset')}</option>
                  {events.map((event) => <option key={event.id} value={event.id}>{event.code} ({event.governance_status})</option>)}
                </select>
                <select value={formState.rule_type} onChange={(e) => setFormState((prev) => ({ ...prev, rule_type: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2.5 outline-none">
                  <option value="NOT_NULL">NOT_NULL</option>
                  <option value="UNIQUENESS">UNIQUENESS</option>
                  <option value="VALUE_RANGE">VALUE_RANGE</option>
                  <option value="REGEX">REGEX</option>
                  <option value="ENUM">ENUM</option>
                  <option value="CUSTOM_SQL">CUSTOM_SQL</option>
                </select>
                <input value={formState.target_field} onChange={(e) => setFormState((prev) => ({ ...prev, target_field: e.target.value }))} placeholder={L('目标字段', 'Target Field')} className="rounded-xl border border-slate-200 px-3 py-2.5 outline-none" />
                <input value={formState.operator} onChange={(e) => setFormState((prev) => ({ ...prev, operator: e.target.value }))} placeholder={L('操作符', 'Operator')} className="rounded-xl border border-slate-200 px-3 py-2.5 outline-none" />
                <input value={formState.alert_channels} onChange={(e) => setFormState((prev) => ({ ...prev, alert_channels: e.target.value }))} placeholder={L('告警通道（逗号分隔）', 'Alert Channels (comma separated)')} className="rounded-xl border border-slate-200 px-3 py-2.5 outline-none" />
                <select value={formState.severity} onChange={(e) => setFormState((prev) => ({ ...prev, severity: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2.5 outline-none">
                  <option value="LOW">LOW</option>
                  <option value="MEDIUM">MEDIUM</option>
                  <option value="HIGH">HIGH</option>
                  <option value="CRITICAL">CRITICAL</option>
                </select>
                <select value={formState.status} onChange={(e) => setFormState((prev) => ({ ...prev, status: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2.5 outline-none">
                  <option value="ACTIVE">ACTIVE</option>
                  <option value="PAUSED">PAUSED</option>
                  <option value="DRAFT">DRAFT</option>
                  <option value="DEPRECATED">DEPRECATED</option>
                </select>
                <textarea value={formState.description} onChange={(e) => setFormState((prev) => ({ ...prev, description: e.target.value }))} placeholder={L('描述', 'Description')} className="h-24 rounded-xl border border-slate-200 px-3 py-2.5 outline-none md:col-span-2" />
                <textarea value={formState.threshold} onChange={(e) => setFormState((prev) => ({ ...prev, threshold: e.target.value }))} placeholder={L('阈值 JSON', 'Threshold JSON')} className="h-40 rounded-xl border border-slate-200 px-3 py-2.5 font-mono text-sm outline-none md:col-span-2" />
              </div>

              <div className="mt-4 flex justify-end gap-2">
                <button onClick={() => setFormOpen(false)} className="rounded-xl border border-slate-200 px-4 py-2 text-slate-700 hover:bg-slate-50">{L('取消', 'Cancel')}</button>
                <button onClick={() => void submitForm()} disabled={formSubmitting} className="rounded-xl bg-cyan-600 px-4 py-2 font-medium text-white hover:bg-cyan-500 disabled:opacity-70">
                  {formSubmitting ? L('保存中...', 'Saving...') : editingRule ? L('保存修改', 'Save Changes') : L('创建规则', 'Create Rule')}
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
