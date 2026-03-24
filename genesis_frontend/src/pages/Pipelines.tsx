import { useEffect, useMemo, useState } from 'react'
import { Pause, Play, RefreshCw, RotateCcw, Search, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import {
  GenesisApi,
  type Pipeline,
  type PipelineHistoryItem,
  type PipelineProvisionEventOption,
} from '../services/api'
import { useLanguage } from '../i18n/language'
import { useBrowserErrorAlert } from '../hooks/useBrowserErrorAlert'

const statusClass: Record<string, string> = {
  RUNNING: 'bg-emerald-100 text-emerald-700',
  FAILED: 'bg-rose-100 text-rose-700',
  PROVISIONING: 'bg-amber-100 text-amber-700',
  PENDING: 'bg-slate-100 text-slate-700',
  ROLLING_BACK: 'bg-orange-100 text-orange-700',
  STOPPED: 'bg-slate-200 text-slate-700',
}

const statusOptions = ['ALL', 'RUNNING', 'FAILED', 'PROVISIONING', 'PENDING', 'ROLLING_BACK', 'STOPPED']

export default function Pipelines() {
  const navigate = useNavigate()
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const L = (cn: string, en: string) => (isZh ? cn : en)

  const [pipelines, setPipelines] = useState<Pipeline[]>([])
  const [approvedEvents, setApprovedEvents] = useState<PipelineProvisionEventOption[]>([])
  const [history, setHistory] = useState<PipelineHistoryItem[]>([])
  const [selectedPipelineId, setSelectedPipelineId] = useState<number | null>(null)

  const [searchText, setSearchText] = useState('')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [autoRefresh, setAutoRefresh] = useState(true)

  const [eventCode, setEventCode] = useState('')
  const [partitions, setPartitions] = useState(6)
  const [replicationFactor, setReplicationFactor] = useState(3)
  const [retentionHours, setRetentionHours] = useState(168)
  const [resourceTier, setResourceTier] = useState('standard')
  const [topicPrefix, setTopicPrefix] = useState('tracking')
  const [jobNameTemplate, setJobNameTemplate] = useState('flink_{project_id}_{event_code}')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [operationLoadingId, setOperationLoadingId] = useState<number | null>(null)
  useBrowserErrorAlert(error)

  const selectedPipeline = useMemo(
    () => pipelines.find((item) => item.id === selectedPipelineId) ?? null,
    [pipelines, selectedPipelineId],
  )

  const formatDate = (value?: string | null) => {
    if (!value) return '-'
    return new Date(value).toLocaleString(isZh ? 'zh-CN' : 'en-US', { hour12: false })
  }

  const loadProvisionOptions = async () => {
    try {
      const data = await GenesisApi.getPipelineProvisionOptions()
      setApprovedEvents(data.approved_events)
      if (!eventCode && data.approved_events.length > 0) {
        setEventCode(data.approved_events[0].code)
      }
    } catch {
      // keep page usable
    }
  }

  const loadPipelines = async (silent = false) => {
    if (!silent) setLoading(true)
    setError(null)
    try {
      const rows = await GenesisApi.getPipelines({
        q: searchText.trim() || undefined,
        status: statusFilter === 'ALL' ? undefined : statusFilter,
      })
      setPipelines(rows)
      if (selectedPipelineId && !rows.some((item) => item.id === selectedPipelineId)) {
        setSelectedPipelineId(null)
        setHistory([])
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? L('加载管道失败', 'Failed to load pipelines'))
    } finally {
      if (!silent) setLoading(false)
    }
  }

  const loadHistory = async (pipelineId: number, silent = false) => {
    if (!silent) setLoading(true)
    setError(null)
    try {
      const rows = await GenesisApi.getPipelineHistory(pipelineId)
      setSelectedPipelineId(pipelineId)
      setHistory(rows)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? L('加载管道历史失败', 'Failed to load pipeline history'))
    } finally {
      if (!silent) setLoading(false)
    }
  }

  useEffect(() => {
    void Promise.all([loadProvisionOptions(), loadPipelines()])
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadPipelines(true)
    }, 250)
    return () => window.clearTimeout(timer)
  }, [searchText, statusFilter])

  useEffect(() => {
    if (!autoRefresh) return
    const timer = window.setInterval(() => {
      void loadPipelines(true)
      if (selectedPipelineId) void loadHistory(selectedPipelineId, true)
    }, 15000)
    return () => window.clearInterval(timer)
  }, [autoRefresh, selectedPipelineId, searchText, statusFilter])

  const onProvision = async () => {
    if (!eventCode.trim()) {
      setError(L('请先选择一个已批准事件', 'Please select an approved event first'))
      return
    }
    setLoading(true)
    setError(null)
    setNotice(null)
    try {
      const pipeline = await GenesisApi.provisionPipeline({
        event_code: eventCode.trim(),
        partitions,
        replication_factor: replicationFactor,
        retention_hours: retentionHours,
        resource_tier: resourceTier,
        topic_prefix: topicPrefix.trim() || 'tracking',
        job_name_template: jobNameTemplate.trim() || 'flink_{project_id}_{event_code}',
      })
      setNotice(`${L('管道已创建', 'Pipeline provisioned')} #${pipeline.id}`)
      await loadPipelines(true)
      await loadHistory(pipeline.id, true)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? L('创建管道失败', 'Failed to provision pipeline'))
    } finally {
      setLoading(false)
    }
  }

  const runPipelineOperation = async (pipelineId: number, operation: 'pause' | 'resume' | 'sync' | 'rollback') => {
    setOperationLoadingId(pipelineId)
    setError(null)
    setNotice(null)
    try {
      if (operation === 'pause') {
        await GenesisApi.pausePipeline(pipelineId)
        setNotice(`${L('管道已暂停', 'Pipeline paused')} #${pipelineId}`)
      }
      if (operation === 'resume') {
        await GenesisApi.resumePipeline(pipelineId)
        setNotice(`${L('管道已恢复', 'Pipeline resumed')} #${pipelineId}`)
      }
      if (operation === 'sync') {
        await GenesisApi.syncPipeline(pipelineId)
        setNotice(`${L('管道已同步', 'Pipeline synced')} #${pipelineId}`)
      }
      if (operation === 'rollback') {
        await GenesisApi.rollbackPipeline(pipelineId)
        setNotice(`${L('管道已回滚', 'Pipeline rolled back')} #${pipelineId}`)
      }
      await loadPipelines(true)
      if (selectedPipelineId === pipelineId) await loadHistory(pipelineId, true)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? `${L('管道操作失败', 'Pipeline operation failed')}: ${operation}`)
    } finally {
      setOperationLoadingId(null)
    }
  }

  const openKnowledgeForPipeline = (pipelineId: number) => {
    const params = new URLSearchParams({
      source_type: 'PIPELINE',
      source_id: String(pipelineId),
    })
    navigate(`/knowledge?${params.toString()}`)
  }

  return (
    <div className="mx-auto max-w-[1440px] animate-in fade-in slide-in-from-bottom-8 duration-700">
      <section className="mb-4 rounded-2xl border border-slate-200 bg-white/80 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-900">{L('推荐下一步', 'Recommended Next Step')}</p>
            <p className="text-xs text-slate-600">
              {L('管道稳定运行后，继续配置数据质量规则并开启监控告警。', 'After pipeline is stable, configure DQ rules and enable monitoring alerts.')}
            </p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => navigate('/data-quality')} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs hover:bg-slate-50">
              {L('前往数据质量', 'Go Data Quality')}
            </button>
            <button onClick={() => navigate('/monitoring')} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs hover:bg-slate-50">
              {L('前往监控', 'Go Monitoring')}
            </button>
          </div>
        </div>
      </section>

      <header className="mb-6">
        <h2 className="text-3xl font-bold tracking-tight text-gray-900">{L('管道控制台', 'Pipelines Console')}</h2>
        <p className="text-base text-gray-500">{L('创建事件管道、查看拓扑、跟踪状态时间线，并执行生命周期操作。', 'Provision event pipelines, inspect topology, track status timeline, and operate lifecycle.')}</p>
      </header>

      {notice && <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{notice}</div>}

      <section className="mb-4 rounded-2xl border border-gray-200/60 p-4 glass">
        <h3 className="mb-3 text-sm font-semibold uppercase text-slate-700">{L('创建管道', 'Create Pipeline')}</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="xl:col-span-2">
            <label className="mb-1 block text-xs text-slate-500">{L('已批准事件', 'Approved Event')}</label>
            <select value={eventCode} onChange={(e) => setEventCode(e.target.value)} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 outline-none">
              {approvedEvents.length === 0 && <option value="">{L('暂无可用已批准事件', 'No approved event available')}</option>}
              {approvedEvents.map((event) => (
                <option key={event.id} value={event.code}>
                  {event.code} | {event.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500">{L('分区数', 'Partitions')}</label>
            <input type="number" min={1} max={256} value={partitions} onChange={(e) => setPartitions(Number(e.target.value))} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 outline-none" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500">{L('副本数', 'Replication')}</label>
            <input type="number" min={1} max={5} value={replicationFactor} onChange={(e) => setReplicationFactor(Number(e.target.value))} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 outline-none" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500">{L('保留时长（小时）', 'Retention (hours)')}</label>
            <input type="number" min={1} max={24 * 365} value={retentionHours} onChange={(e) => setRetentionHours(Number(e.target.value))} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 outline-none" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500">{L('资源等级', 'Resource Tier')}</label>
            <select value={resourceTier} onChange={(e) => setResourceTier(e.target.value)} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 outline-none">
              <option value="small">small</option>
              <option value="standard">standard</option>
              <option value="large">large</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500">{L('Topic 前缀', 'Topic Prefix')}</label>
            <input value={topicPrefix} onChange={(e) => setTopicPrefix(e.target.value)} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 outline-none" />
          </div>
          <div className="xl:col-span-2">
            <label className="mb-1 block text-xs text-slate-500">{L('作业名模板', 'Job Name Template')}</label>
            <input value={jobNameTemplate} onChange={(e) => setJobNameTemplate(e.target.value)} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 font-mono text-sm outline-none" />
          </div>
        </div>
        <div className="mt-3 flex gap-2">
          <button onClick={() => void onProvision()} disabled={loading} className="rounded-xl bg-cyan-600 px-4 py-2.5 font-medium text-white hover:bg-cyan-500 disabled:opacity-50">
            {L('创建管道', 'Provision Pipeline')}
          </button>
          <button onClick={() => void Promise.all([loadProvisionOptions(), loadPipelines()])} disabled={loading} className="flex items-center gap-2 rounded-xl bg-slate-100 px-4 py-2.5 font-medium text-slate-700 hover:bg-slate-200 disabled:opacity-50">
            <RefreshCw size={14} />
            {L('刷新', 'Refresh')}
          </button>
        </div>
      </section>

      <section className="mb-4 rounded-2xl border border-gray-200/60 p-4 glass">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-[280px]">
            <Search className="absolute left-3 top-2.5 text-gray-400" size={16} />
            <input value={searchText} onChange={(e) => setSearchText(e.target.value)} placeholder={L('搜索事件 / topic / job...', 'Search event/topic/job...')} className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-9 pr-3 outline-none" />
          </div>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 outline-none">
            {statusOptions.map((status) => (
              <option key={status} value={status}>{status}</option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />
            {L('自动刷新（15秒）', 'Auto refresh (15s)')}
          </label>
          <span className="ml-auto text-xs text-slate-500">{L('总数', 'Total')} {pipelines.length}</span>
        </div>
      </section>

      <section className="overflow-auto rounded-2xl border border-gray-200/60 glass">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-4 py-3 text-left">ID</th>
              <th className="px-4 py-3 text-left">{L('事件', 'Event')}</th>
              <th className="px-4 py-3 text-left">Topic</th>
              <th className="px-4 py-3 text-left">Flink Job</th>
              <th className="px-4 py-3 text-left">{L('状态', 'Status')}</th>
              <th className="px-4 py-3 text-left">{L('最近同步', 'Last Sync')}</th>
              <th className="px-4 py-3 text-left">{L('操作', 'Actions')}</th>
            </tr>
          </thead>
          <tbody>
            {loading && pipelines.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-500">{L('正在加载管道...', 'Loading pipelines...')}</td></tr>
            ) : pipelines.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-500">{L('当前没有匹配的管道。', 'No pipeline found.')}</td></tr>
            ) : (
              pipelines.map((pipeline) => (
                <tr key={pipeline.id} className={`border-t border-slate-100 ${selectedPipelineId === pipeline.id ? 'bg-cyan-50/40' : ''}`}>
                  <td className="px-4 py-3">{pipeline.id}</td>
                  <td className="px-4 py-3 font-mono">{pipeline.event_code}</td>
                  <td className="px-4 py-3 font-mono">{pipeline.topic_name}</td>
                  <td className="px-4 py-3 font-mono">{pipeline.flink_job_name}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-1 text-xs font-semibold ${statusClass[pipeline.status] ?? 'bg-slate-100 text-slate-700'}`}>{pipeline.status}</span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">{formatDate(pipeline.last_sync_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      <button onClick={() => void loadHistory(pipeline.id)} className="rounded-lg bg-slate-100 px-2.5 py-1.5 text-xs text-slate-700 hover:bg-slate-200">{L('详情', 'Detail')}</button>
                      <button onClick={() => void runPipelineOperation(pipeline.id, 'pause')} disabled={operationLoadingId === pipeline.id} className="flex items-center gap-1 rounded-lg bg-amber-100 px-2.5 py-1.5 text-xs text-amber-700 hover:bg-amber-200 disabled:opacity-50"><Pause size={12} />{L('暂停', 'Pause')}</button>
                      <button onClick={() => void runPipelineOperation(pipeline.id, 'resume')} disabled={operationLoadingId === pipeline.id} className="flex items-center gap-1 rounded-lg bg-emerald-100 px-2.5 py-1.5 text-xs text-emerald-700 hover:bg-emerald-200 disabled:opacity-50"><Play size={12} />{L('恢复', 'Resume')}</button>
                      <button onClick={() => void runPipelineOperation(pipeline.id, 'sync')} disabled={operationLoadingId === pipeline.id} className="rounded-lg bg-blue-100 px-2.5 py-1.5 text-xs text-blue-700 hover:bg-blue-200 disabled:opacity-50">{L('同步', 'Sync')}</button>
                      <button onClick={() => void runPipelineOperation(pipeline.id, 'rollback')} disabled={operationLoadingId === pipeline.id} className="flex items-center gap-1 rounded-lg bg-rose-100 px-2.5 py-1.5 text-xs text-rose-700 hover:bg-rose-200 disabled:opacity-50"><RotateCcw size={12} />{L('回滚', 'Rollback')}</button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      {selectedPipeline && (
        <>
          <div className="fixed inset-0 z-40 bg-black/25" onClick={() => { setSelectedPipelineId(null); setHistory([]) }} />
          <aside className="fixed right-0 top-0 z-50 h-screen w-[560px] overflow-auto border-l border-slate-200 bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-200 p-5">
              <h3 className="text-lg font-bold text-slate-900">{L('管道详情', 'Pipeline Detail')} #{selectedPipeline.id}</h3>
              <button onClick={() => { setSelectedPipelineId(null); setHistory([]) }} className="rounded-lg p-2 hover:bg-slate-100"><X size={16} /></button>
            </div>
            <div className="space-y-6 p-5">
              <div>
                <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">{L('拓扑', 'Topology')}</p>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <div className="flex items-center justify-between gap-2 text-sm">
                    <div className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2">{L('事件', 'Event')}<p className="mt-1 font-mono text-xs text-slate-600">{selectedPipeline.event_code}</p></div>
                    <span className="text-slate-400">-&gt;</span>
                    <div className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2">Kafka Topic<p className="mt-1 font-mono text-xs text-slate-600">{selectedPipeline.topic_name}</p></div>
                    <span className="text-slate-400">-&gt;</span>
                    <div className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2">Flink Job<p className="mt-1 font-mono text-xs text-slate-600">{selectedPipeline.flink_job_name}</p></div>
                  </div>
                </div>
              </div>

              <div>
                <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">{L('状态快照', 'Status Snapshot')}</p>
                <div className="space-y-2 rounded-xl border border-slate-200 bg-white p-4 text-sm">
                  <p>{L('状态', 'Status')}: <span className={`rounded-full px-2 py-0.5 text-xs ${statusClass[selectedPipeline.status] ?? ''}`}>{selectedPipeline.status}</span></p>
                  <p>{L('重试次数', 'Retry count')}: {selectedPipeline.retry_count}</p>
                  <p>{L('最近同步', 'Last sync')}: {formatDate(selectedPipeline.last_sync_at)}</p>
                  <button onClick={() => openKnowledgeForPipeline(selectedPipeline.id)} className="mt-2 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500">{L('相关文档', 'Related Docs')}</button>
                </div>
              </div>

              <div>
                <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">{L('状态时间线', 'Status Timeline')}</p>
                {history.length === 0 ? (
                  <p className="text-sm text-slate-500">{L('暂无历史记录。', 'No history yet.')}</p>
                ) : (
                  <ol className="space-y-2">
                    {history.map((item) => (
                      <li key={item.id} className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
                        <p className="font-semibold text-slate-800">{item.from_status ?? 'NONE'} {'->'} {item.to_status}</p>
                        <p className="mt-1 text-xs text-slate-500">{formatDate(item.synced_at)} | source={item.source}</p>
                        {item.reason && <p className="mt-1 text-xs text-slate-600">{item.reason}</p>}
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </div>
          </aside>
        </>
      )}
    </div>
  )
}
