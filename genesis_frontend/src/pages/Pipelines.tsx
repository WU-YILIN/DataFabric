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

const statusClass: Record<string, string> = {
  RUNNING: 'bg-emerald-100 text-emerald-700',
  FAILED: 'bg-rose-100 text-rose-700',
  PROVISIONING: 'bg-amber-100 text-amber-700',
  PENDING: 'bg-slate-100 text-slate-700',
  ROLLING_BACK: 'bg-orange-100 text-orange-700',
  STOPPED: 'bg-slate-200 text-slate-700',
}

const statusOptions = [
  'ALL',
  'RUNNING',
  'FAILED',
  'PROVISIONING',
  'PENDING',
  'ROLLING_BACK',
  'STOPPED',
]

const Pipelines = () => {
  const navigate = useNavigate()
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
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

  const selectedPipeline = useMemo(
    () => pipelines.find((item) => item.id === selectedPipelineId) ?? null,
    [pipelines, selectedPipelineId],
  )

  const loadProvisionOptions = async () => {
    try {
      const data = await GenesisApi.getPipelineProvisionOptions()
      setApprovedEvents(data.approved_events)
      if (!eventCode && data.approved_events.length > 0) {
        setEventCode(data.approved_events[0].code)
      }
    } catch {
      // keep page usable even if options call fails
    }
  }

  const loadPipelines = async (silent = false) => {
    if (!silent) {
      setLoading(true)
    }
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
      setError(e?.response?.data?.message ?? (isZh ? '加载管道失败' : 'Failed to load pipelines'))
    } finally {
      if (!silent) {
        setLoading(false)
      }
    }
  }

  const loadHistory = async (pipelineId: number, silent = false) => {
    if (!silent) {
      setLoading(true)
    }
    setError(null)
    try {
      const rows = await GenesisApi.getPipelineHistory(pipelineId)
      setSelectedPipelineId(pipelineId)
      setHistory(rows)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load pipeline history')
    } finally {
      if (!silent) {
        setLoading(false)
      }
    }
  }

  useEffect(() => {
    void Promise.all([loadProvisionOptions(), loadPipelines()])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadPipelines(true)
    }, 250)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchText, statusFilter])

  useEffect(() => {
    if (!autoRefresh) {
      return
    }
    const timer = window.setInterval(() => {
      void loadPipelines(true)
      if (selectedPipelineId) {
        void loadHistory(selectedPipelineId, true)
      }
    }, 15000)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, selectedPipelineId, searchText, statusFilter])

  const onProvision = async () => {
    if (!eventCode.trim()) {
      setError('Please select an approved event first')
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
      setNotice(`Pipeline #${pipeline.id} provisioned`)
      await loadPipelines(true)
      await loadHistory(pipeline.id, true)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to provision pipeline')
    } finally {
      setLoading(false)
    }
  }

  const runPipelineOperation = async (
    pipelineId: number,
    operation: 'pause' | 'resume' | 'sync' | 'rollback',
  ) => {
    setOperationLoadingId(pipelineId)
    setError(null)
    setNotice(null)
    try {
      if (operation === 'pause') {
        await GenesisApi.pausePipeline(pipelineId)
        setNotice(`Pipeline #${pipelineId} paused`)
      }
      if (operation === 'resume') {
        await GenesisApi.resumePipeline(pipelineId)
        setNotice(`Pipeline #${pipelineId} resumed`)
      }
      if (operation === 'sync') {
        await GenesisApi.syncPipeline(pipelineId)
        setNotice(`Pipeline #${pipelineId} synced`)
      }
      if (operation === 'rollback') {
        await GenesisApi.rollbackPipeline(pipelineId)
        setNotice(`Pipeline #${pipelineId} rolled back`)
      }
      await loadPipelines(true)
      if (selectedPipelineId === pipelineId) {
        await loadHistory(pipelineId, true)
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? `Pipeline ${operation} failed`)
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
    <div className="max-w-[1440px] mx-auto animate-in fade-in slide-in-from-bottom-8 duration-700">
      <section className="mb-4 rounded-2xl border border-slate-200 bg-white/80 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-900">{isZh ? '下一步建议' : 'Recommended Next Step'}</p>
            <p className="text-xs text-slate-600">
              {isZh ? '管道运行稳定后，请进入数据质量页配置规则并开启监控告警。' : 'After pipeline is stable, configure DQ rules and enable monitoring alerts.'}
            </p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => navigate('/data-quality')} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs hover:bg-slate-50">
              {isZh ? '去数据质量' : 'Go Data Quality'}
            </button>
            <button onClick={() => navigate('/monitoring')} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs hover:bg-slate-50">
              {isZh ? '去监控' : 'Go Monitoring'}
            </button>
          </div>
        </div>
      </section>
      <header className="mb-6">
        <h2 className="text-3xl font-bold text-gray-900 tracking-tight">{isZh ? '管道控制台' : 'Pipelines Console'}</h2>
        <p className="text-gray-500 text-base">
          Provision event pipelines, inspect topology, track status timeline, and operate lifecycle.
        </p>
      </header>

      {error && (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
      )}
      {notice && (
        <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {notice}
        </div>
      )}

      <section className="glass rounded-2xl p-4 border border-gray-200/60 mb-4">
        <h3 className="text-sm font-semibold text-slate-700 uppercase mb-3">Create Pipeline</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
          <div className="xl:col-span-2">
            <label className="text-xs text-slate-500 mb-1 block">Approved Event</label>
            <select
              value={eventCode}
              onChange={(e) => setEventCode(e.target.value)}
              className="w-full px-3 py-2.5 rounded-xl border border-slate-200 bg-white outline-none"
            >
              {approvedEvents.length === 0 && <option value="">No approved event available</option>}
              {approvedEvents.map((event) => (
                <option key={event.id} value={event.code}>
                  {event.code} | {event.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500 mb-1 block">Partitions</label>
            <input
              type="number"
              min={1}
              max={256}
              value={partitions}
              onChange={(e) => setPartitions(Number(e.target.value))}
              className="w-full px-3 py-2.5 rounded-xl border border-slate-200 bg-white outline-none"
            />
          </div>
          <div>
            <label className="text-xs text-slate-500 mb-1 block">Replication</label>
            <input
              type="number"
              min={1}
              max={5}
              value={replicationFactor}
              onChange={(e) => setReplicationFactor(Number(e.target.value))}
              className="w-full px-3 py-2.5 rounded-xl border border-slate-200 bg-white outline-none"
            />
          </div>
          <div>
            <label className="text-xs text-slate-500 mb-1 block">Retention (hours)</label>
            <input
              type="number"
              min={1}
              max={24 * 365}
              value={retentionHours}
              onChange={(e) => setRetentionHours(Number(e.target.value))}
              className="w-full px-3 py-2.5 rounded-xl border border-slate-200 bg-white outline-none"
            />
          </div>
          <div>
            <label className="text-xs text-slate-500 mb-1 block">Resource Tier</label>
            <select
              value={resourceTier}
              onChange={(e) => setResourceTier(e.target.value)}
              className="w-full px-3 py-2.5 rounded-xl border border-slate-200 bg-white outline-none"
            >
              <option value="small">small</option>
              <option value="standard">standard</option>
              <option value="large">large</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500 mb-1 block">Topic Prefix</label>
            <input
              value={topicPrefix}
              onChange={(e) => setTopicPrefix(e.target.value)}
              className="w-full px-3 py-2.5 rounded-xl border border-slate-200 bg-white outline-none"
            />
          </div>
          <div className="xl:col-span-2">
            <label className="text-xs text-slate-500 mb-1 block">Job Name Template</label>
            <input
              value={jobNameTemplate}
              onChange={(e) => setJobNameTemplate(e.target.value)}
              className="w-full px-3 py-2.5 rounded-xl border border-slate-200 bg-white outline-none font-mono text-sm"
            />
          </div>
        </div>
        <div className="mt-3 flex gap-2">
          <button
            onClick={() => void onProvision()}
            disabled={loading}
            className="rounded-xl bg-cyan-600 text-white px-4 py-2.5 font-medium hover:bg-cyan-500 disabled:opacity-50"
          >
            Provision Pipeline
          </button>
          <button
            onClick={() => void Promise.all([loadProvisionOptions(), loadPipelines()])}
            disabled={loading}
            className="rounded-xl bg-slate-100 text-slate-700 px-4 py-2.5 font-medium hover:bg-slate-200 disabled:opacity-50 flex items-center gap-2"
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>
      </section>

      <section className="glass rounded-2xl p-4 border border-gray-200/60 mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-[280px]">
            <Search className="absolute left-3 top-2.5 text-gray-400" size={16} />
            <input
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              placeholder="Search event/topic/job..."
              className="w-full pl-9 pr-3 py-2.5 rounded-xl bg-white border border-slate-200 outline-none"
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2.5 rounded-xl bg-white border border-slate-200 outline-none"
          >
            {statusOptions.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
          <label className="text-sm text-slate-600 flex items-center gap-2">
            <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />
            Auto refresh (15s)
          </label>
          <span className="text-xs text-slate-500 ml-auto">Total {pipelines.length}</span>
        </div>
      </section>

      <section className="glass rounded-2xl overflow-auto border border-gray-200/60">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="text-left px-4 py-3">ID</th>
              <th className="text-left px-4 py-3">Event</th>
              <th className="text-left px-4 py-3">Topic</th>
              <th className="text-left px-4 py-3">Flink Job</th>
              <th className="text-left px-4 py-3">Status</th>
              <th className="text-left px-4 py-3">Last Sync</th>
              <th className="text-left px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && pipelines.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-slate-500">
                  Loading pipelines...
                </td>
              </tr>
            ) : pipelines.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-slate-500">
                  No pipeline found.
                </td>
              </tr>
            ) : (
              pipelines.map((pipeline) => (
                <tr
                  key={pipeline.id}
                  className={`border-t border-slate-100 ${selectedPipelineId === pipeline.id ? 'bg-cyan-50/40' : ''}`}
                >
                  <td className="px-4 py-3">{pipeline.id}</td>
                  <td className="px-4 py-3 font-mono">{pipeline.event_code}</td>
                  <td className="px-4 py-3 font-mono">{pipeline.topic_name}</td>
                  <td className="px-4 py-3 font-mono">{pipeline.flink_job_name}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-1 rounded-full text-xs font-semibold ${
                        statusClass[pipeline.status] ?? 'bg-slate-100 text-slate-700'
                      }`}
                    >
                      {pipeline.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {pipeline.last_sync_at ? new Date(pipeline.last_sync_at).toLocaleString() : '-'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() => void loadHistory(pipeline.id)}
                        className="px-2.5 py-1.5 rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 text-xs"
                      >
                        Detail
                      </button>
                      <button
                        onClick={() => void runPipelineOperation(pipeline.id, 'pause')}
                        disabled={operationLoadingId === pipeline.id}
                        className="px-2.5 py-1.5 rounded-lg bg-amber-100 text-amber-700 hover:bg-amber-200 text-xs flex items-center gap-1 disabled:opacity-50"
                      >
                        <Pause size={12} />
                        Pause
                      </button>
                      <button
                        onClick={() => void runPipelineOperation(pipeline.id, 'resume')}
                        disabled={operationLoadingId === pipeline.id}
                        className="px-2.5 py-1.5 rounded-lg bg-emerald-100 text-emerald-700 hover:bg-emerald-200 text-xs flex items-center gap-1 disabled:opacity-50"
                      >
                        <Play size={12} />
                        Resume
                      </button>
                      <button
                        onClick={() => void runPipelineOperation(pipeline.id, 'sync')}
                        disabled={operationLoadingId === pipeline.id}
                        className="px-2.5 py-1.5 rounded-lg bg-blue-100 text-blue-700 hover:bg-blue-200 text-xs disabled:opacity-50"
                      >
                        Sync
                      </button>
                      <button
                        onClick={() => void runPipelineOperation(pipeline.id, 'rollback')}
                        disabled={operationLoadingId === pipeline.id}
                        className="px-2.5 py-1.5 rounded-lg bg-rose-100 text-rose-700 hover:bg-rose-200 text-xs flex items-center gap-1 disabled:opacity-50"
                      >
                        <RotateCcw size={12} />
                        Rollback
                      </button>
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
          <div
            className="fixed inset-0 bg-black/25 z-40"
            onClick={() => {
              setSelectedPipelineId(null)
              setHistory([])
            }}
          />
          <aside className="fixed right-0 top-0 h-screen w-[560px] bg-white z-50 border-l border-slate-200 shadow-2xl overflow-auto">
            <div className="p-5 border-b border-slate-200 flex items-center justify-between">
              <h3 className="font-bold text-slate-900 text-lg">Pipeline Detail #{selectedPipeline.id}</h3>
              <button
                onClick={() => {
                  setSelectedPipelineId(null)
                  setHistory([])
                }}
                className="p-2 rounded-lg hover:bg-slate-100"
              >
                <X size={16} />
              </button>
            </div>

            <div className="p-5 space-y-6">
              <div>
                <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Topology</p>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <div className="flex items-center justify-between gap-2 text-sm">
                    <div className="flex-1 rounded-lg bg-white border border-slate-200 px-3 py-2">
                      Event
                      <p className="font-mono text-xs text-slate-600 mt-1">{selectedPipeline.event_code}</p>
                    </div>
                    <span className="text-slate-400">-&gt;</span>
                    <div className="flex-1 rounded-lg bg-white border border-slate-200 px-3 py-2">
                      Kafka Topic
                      <p className="font-mono text-xs text-slate-600 mt-1">{selectedPipeline.topic_name}</p>
                    </div>
                    <span className="text-slate-400">-&gt;</span>
                    <div className="flex-1 rounded-lg bg-white border border-slate-200 px-3 py-2">
                      Flink Job
                      <p className="font-mono text-xs text-slate-600 mt-1">{selectedPipeline.flink_job_name}</p>
                    </div>
                  </div>
                </div>
              </div>

              <div>
                <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Status Snapshot</p>
                <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm space-y-2">
                  <p>
                    Status:{' '}
                    <span className={`px-2 py-0.5 rounded-full text-xs ${statusClass[selectedPipeline.status] ?? ''}`}>
                      {selectedPipeline.status}
                    </span>
                  </p>
                  <p>Retry count: {selectedPipeline.retry_count}</p>
                  <p>Last sync: {selectedPipeline.last_sync_at ? new Date(selectedPipeline.last_sync_at).toLocaleString() : '-'}</p>
                  <p className="text-xs text-slate-500">Error: {selectedPipeline.error_message || 'None'}</p>
                  <button
                    onClick={() => openKnowledgeForPipeline(selectedPipeline.id)}
                    className="mt-2 rounded-lg bg-emerald-600 text-white px-3 py-1.5 text-xs font-medium hover:bg-emerald-500"
                  >
                    Related Docs
                  </button>
                </div>
              </div>

              <div>
                <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Status Timeline</p>
                {history.length === 0 ? (
                  <p className="text-sm text-slate-500">No history yet.</p>
                ) : (
                  <ol className="space-y-2">
                    {history.map((item) => (
                      <li key={item.id} className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
                        <p className="font-semibold text-slate-800">
                          {item.from_status ?? 'NONE'} {'->'} {item.to_status}
                        </p>
                        <p className="text-xs text-slate-500 mt-1">
                          {new Date(item.synced_at).toLocaleString()} | source={item.source}
                        </p>
                        {item.reason && <p className="text-xs text-slate-600 mt-1">{item.reason}</p>}
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

export default Pipelines
