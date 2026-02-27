import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  Clock3,
  GitBranch,
  PenSquare,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  SkipForward,
  X,
} from 'lucide-react'
import { clsx } from 'clsx'
import { useNavigate } from 'react-router-dom'

import {
  GenesisApi,
  type SchedulerDagDetailResponse,
  type SchedulerDagEdge,
  type SchedulerDagNode,
  type SchedulerDagSummary,
  type SchedulerNodeRun,
  type SchedulerOptionAsset,
  type SchedulerRun,
  type SchedulerRunDetailResponse,
} from '../services/api'
import { useLanguage } from '../i18n/language'

type NodeForm = {
  node_key: string
  name: string
  task_type: string
  input_assets: string
  output_assets: string
  logic_description: string
  config_json: string
}

type EdgeForm = {
  from_node_key: string
  to_node_key: string
  condition_json: string
}

type DagFormState = {
  name: string
  description: string
  status: string
  trigger_mode: string
  cron_expr: string
  timezone: string
  dependency_mode: string
  retry_max_retries: string
  retry_backoff_seconds: string
  schedule_config_json: string
  nodes: NodeForm[]
  edges: EdgeForm[]
}

const statusClass: Record<string, string> = {
  ACTIVE: 'bg-emerald-100 text-emerald-700',
  PAUSED: 'bg-amber-100 text-amber-700',
  DRAFT: 'bg-slate-100 text-slate-700',
  DEPRECATED: 'bg-rose-100 text-rose-700',
  RUNNING: 'bg-blue-100 text-blue-700',
  SUCCESS: 'bg-emerald-100 text-emerald-700',
  FAILED: 'bg-rose-100 text-rose-700',
  PARTIAL: 'bg-amber-100 text-amber-700',
  SKIPPED: 'bg-slate-200 text-slate-700',
  PENDING: 'bg-slate-100 text-slate-700',
}

const defaultFormState: DagFormState = {
  name: '',
  description: '',
  status: 'ACTIVE',
  trigger_mode: 'MANUAL',
  cron_expr: '*/5 * * * *',
  timezone: 'UTC',
  dependency_mode: 'ALL_SUCCESS',
  retry_max_retries: '1',
  retry_backoff_seconds: '30',
  schedule_config_json: '{\n  "owner": "platform"\n}',
  nodes: [
    {
      node_key: 'extract',
      name: 'Extract',
      task_type: 'BATCH',
      input_assets: '',
      output_assets: 'staging.extract',
      logic_description: '',
      config_json: '{\n  "sql": "select * from source"\n}',
    },
    {
      node_key: 'publish',
      name: 'Publish',
      task_type: 'SYNC',
      input_assets: 'staging.extract',
      output_assets: 'warehouse.fact',
      logic_description: '',
      config_json: '{\n  "target": "warehouse.fact"\n}',
    },
  ],
  edges: [
    {
      from_node_key: 'extract',
      to_node_key: 'publish',
      condition_json: '{}',
    },
  ],
}

const Scheduler = () => {
  const navigate = useNavigate()
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const [dags, setDags] = useState<SchedulerDagSummary[]>([])
  const [assets, setAssets] = useState<SchedulerOptionAsset[]>([])
  const [taskTypes, setTaskTypes] = useState<string[]>([])

  const [q, setQ] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [triggerModeFilter, setTriggerModeFilter] = useState('')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const [selectedDagId, setSelectedDagId] = useState<number | null>(null)
  const [dagDetail, setDagDetail] = useState<SchedulerDagDetailResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)
  const [runDetail, setRunDetail] = useState<SchedulerRunDetailResponse | null>(null)
  const [runDetailLoading, setRunDetailLoading] = useState(false)

  const [formOpen, setFormOpen] = useState(false)
  const [editingDag, setEditingDag] = useState<SchedulerDagSummary | null>(null)
  const [formState, setFormState] = useState<DagFormState>(defaultFormState)
  const [formSubmitting, setFormSubmitting] = useState(false)

  const [engineTickLoading, setEngineTickLoading] = useState(false)
  const [runLoadingDagId, setRunLoadingDagId] = useState<number | null>(null)
  const [nodeActionLoadingId, setNodeActionLoadingId] = useState<number | null>(null)

  const assetMap = useMemo(() => new Map(assets.map((item) => [String(item.id), item.name])), [assets])

  const loadOptions = async () => {
    try {
      const data = await GenesisApi.getSchedulerOptions()
      setAssets(data.assets)
      setTaskTypes(data.task_types)
    } catch {
      // keep module usable when options API fails
    }
  }

  const loadDags = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await GenesisApi.getSchedulerDags({
        q: q || undefined,
        status: statusFilter || undefined,
        trigger_mode: triggerModeFilter || undefined,
      })
      setDags(data)
      if (selectedDagId && !data.some((item) => item.id === selectedDagId)) {
        setSelectedDagId(null)
        setDagDetail(null)
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load scheduler DAGs')
    } finally {
      setLoading(false)
    }
  }

  const loadDagDetail = async (dagId: number) => {
    setSelectedDagId(dagId)
    setDetailLoading(true)
    setError(null)
    try {
      const detail = await GenesisApi.getSchedulerDagDetail(dagId)
      setDagDetail(detail)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load DAG detail')
    } finally {
      setDetailLoading(false)
    }
  }

  const loadRunDetail = async (runId: number) => {
    setSelectedRunId(runId)
    setRunDetailLoading(true)
    setError(null)
    try {
      const detail = await GenesisApi.getSchedulerRunDetail(runId)
      setRunDetail(detail)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load run detail')
    } finally {
      setRunDetailLoading(false)
    }
  }

  useEffect(() => {
    void Promise.all([loadOptions(), loadDags()])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const openCreateModal = () => {
    setEditingDag(null)
    setFormState(defaultFormState)
    setFormOpen(true)
  }

  const openEditModal = (dag: SchedulerDagSummary) => {
    if (!dagDetail || dagDetail.dag.id !== dag.id) {
      void loadDagDetail(dag.id)
    }
    setEditingDag(dag)

    const sourceNodes =
      dagDetail && dagDetail.dag.id === dag.id
        ? dagDetail.topology.nodes
        : [
            {
              id: 0,
              dag_id: dag.id,
              project_id: dag.project_id,
              node_key: 'extract',
              name: 'Extract',
              task_type: 'BATCH',
              input_assets: [],
              output_assets: [],
              logic_description: '',
              config: {},
              position: {},
              is_active: true,
              created_at: '',
              updated_at: '',
            } as SchedulerDagNode,
          ]
    const sourceEdges =
      dagDetail && dagDetail.dag.id === dag.id
        ? dagDetail.topology.edges
        : [
            {
              id: 0,
              dag_id: dag.id,
              from_node_id: 0,
              to_node_id: 0,
              from_node_key: 'extract',
              to_node_key: 'publish',
              condition: {},
              created_at: '',
              updated_at: '',
            } as SchedulerDagEdge,
          ]

    setFormState({
      name: dag.name,
      description: dag.description ?? '',
      status: dag.status,
      trigger_mode: dag.trigger_mode,
      cron_expr: dag.cron_expr ?? '*/5 * * * *',
      timezone: dag.timezone ?? 'UTC',
      dependency_mode: dag.dependency_mode ?? 'ALL_SUCCESS',
      retry_max_retries: String((dag.retry_policy?.max_retries as number | undefined) ?? 1),
      retry_backoff_seconds: String((dag.retry_policy?.backoff_seconds as number | undefined) ?? 30),
      schedule_config_json: JSON.stringify(dag.schedule_config ?? {}, null, 2),
      nodes: sourceNodes.map((node) => ({
        node_key: node.node_key,
        name: node.name,
        task_type: node.task_type,
        input_assets: (node.input_assets ?? []).join(', '),
        output_assets: (node.output_assets ?? []).join(', '),
        logic_description: node.logic_description ?? '',
        config_json: JSON.stringify(node.config ?? {}, null, 2),
      })),
      edges: sourceEdges.map((edge) => ({
        from_node_key: edge.from_node_key ?? '',
        to_node_key: edge.to_node_key ?? '',
        condition_json: JSON.stringify(edge.condition ?? {}, null, 2),
      })),
    })
    setFormOpen(true)
  }

  const submitForm = async () => {
    setFormSubmitting(true)
    setError(null)
    setNotice(null)
    try {
      let scheduleConfig: Record<string, unknown> = {}
      try {
        scheduleConfig = JSON.parse(formState.schedule_config_json || '{}')
      } catch {
        throw new Error('Schedule Config must be valid JSON')
      }

      const nodesPayload = formState.nodes.map((node) => {
        let parsedConfig: Record<string, unknown> = {}
        try {
          parsedConfig = JSON.parse(node.config_json || '{}')
        } catch {
          throw new Error(`Node ${node.node_key} config must be valid JSON`)
        }
        return {
          node_key: node.node_key.trim(),
          name: node.name.trim(),
          task_type: node.task_type.trim(),
          input_assets: node.input_assets
            .split(',')
            .map((item) => item.trim())
            .filter(Boolean),
          output_assets: node.output_assets
            .split(',')
            .map((item) => item.trim())
            .filter(Boolean),
          logic_description: node.logic_description || null,
          config: parsedConfig,
          position: {},
        }
      })

      const edgesPayload = formState.edges
        .map((edge) => {
          let parsedCondition: Record<string, unknown> = {}
          try {
            parsedCondition = JSON.parse(edge.condition_json || '{}')
          } catch {
            throw new Error(`Edge ${edge.from_node_key} -> ${edge.to_node_key} condition must be valid JSON`)
          }
          return {
            from_node_key: edge.from_node_key.trim(),
            to_node_key: edge.to_node_key.trim(),
            condition: parsedCondition,
          }
        })
        .filter((edge) => edge.from_node_key && edge.to_node_key)

      const payload = {
        name: formState.name.trim(),
        description: formState.description || null,
        status: formState.status,
        trigger_mode: formState.trigger_mode,
        cron_expr: formState.trigger_mode === 'CRON' ? formState.cron_expr.trim() : null,
        timezone: formState.timezone,
        dependency_mode: formState.dependency_mode,
        retry_policy: {
          max_retries: Number(formState.retry_max_retries || 1),
          backoff_seconds: Number(formState.retry_backoff_seconds || 30),
        },
        schedule_config: scheduleConfig,
        nodes: nodesPayload,
        edges: edgesPayload,
      }

      if (editingDag) {
        await GenesisApi.updateSchedulerDag(editingDag.id, payload)
        setNotice('Scheduler DAG updated')
      } else {
        await GenesisApi.createSchedulerDag(payload)
        setNotice('Scheduler DAG created')
      }

      setFormOpen(false)
      await loadDags()
      if (selectedDagId) {
        await loadDagDetail(selectedDagId)
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? e?.message ?? 'Failed to save DAG')
    } finally {
      setFormSubmitting(false)
    }
  }

  const runDag = async (dagId: number) => {
    setRunLoadingDagId(dagId)
    setError(null)
    setNotice(null)
    try {
      const data = await GenesisApi.runSchedulerDag(dagId, { trigger_source: 'manual' })
      setNotice(`DAG #${dagId} executed: ${data.run.status}`)
      await loadDags()
      await loadDagDetail(dagId)
      await loadRunDetail(data.run.id)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to execute DAG')
    } finally {
      setRunLoadingDagId(null)
    }
  }

  const runEngineTick = async () => {
    setEngineTickLoading(true)
    setError(null)
    setNotice(null)
    try {
      const result = await GenesisApi.tickSchedulerEngine({ run_immediately: true, limit: 100 })
      setNotice(`Scheduler tick completed. Executed ${result.executed_count} run(s).`)
      await loadDags()
      if (selectedDagId) {
        await loadDagDetail(selectedDagId)
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to trigger scheduler engine tick')
    } finally {
      setEngineTickLoading(false)
    }
  }

  const applyNodeAction = async (
    run: SchedulerRun,
    nodeRun: SchedulerNodeRun,
    action: 'RETRY' | 'SKIP' | 'MARK_SUCCESS',
  ) => {
    setNodeActionLoadingId(nodeRun.id)
    setError(null)
    setNotice(null)
    try {
      const result = await GenesisApi.applySchedulerRunAction(run.id, {
        action,
        node_run_id: nodeRun.id,
        reason: `${action.toLowerCase()} from UI`,
      })
      setNotice(`Run #${run.id} ${action} applied. Current status: ${result.run.status}`)
      await loadRunDetail(run.id)
      await loadDags()
      if (selectedDagId) {
        await loadDagDetail(selectedDagId)
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to apply run action')
    } finally {
      setNodeActionLoadingId(null)
    }
  }

  const addNode = () => {
    setFormState((prev) => ({
      ...prev,
      nodes: [
        ...prev.nodes,
        {
          node_key: `node_${prev.nodes.length + 1}`,
          name: `Node ${prev.nodes.length + 1}`,
          task_type: taskTypes[0] ?? 'BATCH',
          input_assets: '',
          output_assets: '',
          logic_description: '',
          config_json: '{}',
        },
      ],
    }))
  }

  const addEdge = () => {
    setFormState((prev) => ({
      ...prev,
      edges: [...prev.edges, { from_node_key: '', to_node_key: '', condition_json: '{}' }],
    }))
  }

  const openExploreForDag = (dagId: number) => {
    const params = new URLSearchParams({
      source_type: 'SCHEDULER_DAG',
      source_id: String(dagId),
    })
    navigate(`/explore?${params.toString()}`)
  }

  const openKnowledgeForDag = (dagId: number) => {
    const params = new URLSearchParams({
      source_type: 'SCHEDULER_DAG',
      source_id: String(dagId),
    })
    navigate(`/knowledge?${params.toString()}`)
  }

  return (
    <div className="max-w-7xl mx-auto animate-in fade-in slide-in-from-bottom-8 duration-700">
      <section className="mb-4 rounded-2xl border border-slate-200 bg-white/80 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-900">{isZh ? '下一步建议' : 'Recommended Next Step'}</p>
            <p className="text-xs text-slate-600">
              {isZh ? '调度稳定后，前往监控页观察告警并在成本页检查资源效率。' : 'After scheduler stabilizes, review alerts in monitoring and efficiency in cost analytics.'}
            </p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => navigate('/monitoring')} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs hover:bg-slate-50">
              {isZh ? '去监控' : 'Go Monitoring'}
            </button>
            <button onClick={() => navigate('/cost')} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs hover:bg-slate-50">
              {isZh ? '去成本' : 'Go Cost'}
            </button>
          </div>
        </div>
      </section>
      <div className="flex justify-between items-center mb-6 gap-3">
        <header>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">Scheduler</h2>
          <p className="text-slate-500 text-base">Manage DAG topology, schedule policies, and run instances.</p>
        </header>
        <div className="flex gap-2">
          <button
            onClick={() => void runEngineTick()}
            disabled={engineTickLoading}
            className="rounded-xl bg-slate-100 text-slate-700 px-4 py-2.5 font-semibold flex items-center gap-2 hover:bg-slate-200 disabled:opacity-60"
          >
            <RefreshCw size={16} />
            Engine Tick
          </button>
          <button
            onClick={openCreateModal}
            className="rounded-xl bg-cyan-600 text-white px-4 py-2.5 font-semibold flex items-center gap-2 hover:bg-cyan-500"
          >
            <Plus size={18} />
            New DAG
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-rose-700 text-sm">{error}</div>
      )}
      {notice && (
        <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-emerald-700 text-sm">
          {notice}
        </div>
      )}

      <div className="glass rounded-3xl overflow-hidden shadow-sm border border-gray-200/50 mb-4">
        <div className="p-4 border-b border-gray-200/50 grid grid-cols-1 md:grid-cols-4 gap-3 bg-gray-50/60">
          <div className="relative md:col-span-2">
            <Search className="absolute left-3 top-2.5 text-gray-400" size={16} />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search DAG name / description"
              className="w-full pl-9 pr-3 py-2.5 bg-white border border-gray-200 rounded-xl outline-none focus:ring-2 focus:ring-cyan-300/60"
            />
          </div>
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
          <select
            value={triggerModeFilter}
            onChange={(e) => setTriggerModeFilter(e.target.value)}
            className="px-3 py-2.5 bg-white border border-gray-200 rounded-xl outline-none"
          >
            <option value="">All Trigger Modes</option>
            <option value="MANUAL">MANUAL</option>
            <option value="CRON">CRON</option>
            <option value="DEPENDENCY">DEPENDENCY</option>
          </select>
        </div>
        <div className="p-4 bg-white/70 flex justify-end">
          <button
            onClick={() => void loadDags()}
            className="rounded-xl bg-slate-900 text-white px-4 py-2.5 font-medium hover:bg-slate-800"
          >
            Apply Filters
          </button>
        </div>
      </div>

      <div className="glass rounded-3xl overflow-hidden shadow-sm border border-gray-200/50">
        <div className="overflow-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="text-left px-4 py-3">DAG</th>
                <th className="text-left px-4 py-3">Trigger</th>
                <th className="text-left px-4 py-3">Topology</th>
                <th className="text-left px-4 py-3">Latest Run</th>
                <th className="text-left px-4 py-3">Schedule</th>
                <th className="text-left px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="p-10 text-center text-slate-500">
                    Loading DAGs...
                  </td>
                </tr>
              ) : dags.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-10 text-center text-slate-500">
                    No scheduler DAG found.
                  </td>
                </tr>
              ) : (
                dags.map((dag) => (
                  <tr key={dag.id} className="border-t border-slate-100 hover:bg-cyan-50/40">
                    <td className="px-4 py-3">
                      <p className="font-semibold text-slate-900">{dag.name}</p>
                      <p className="text-xs text-slate-500">{dag.description || '-'}</p>
                      <span
                        className={clsx(
                          'inline-block mt-1 px-2 py-0.5 rounded-full text-[11px] font-semibold',
                          statusClass[dag.status] ?? 'bg-slate-100 text-slate-700',
                        )}
                      >
                        {dag.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-slate-700">{dag.trigger_mode}</p>
                      <p className="text-xs text-slate-500 font-mono">{dag.cron_expr || '-'}</p>
                    </td>
                    <td className="px-4 py-3 text-slate-700">
                      <div className="flex items-center gap-2">
                        <GitBranch size={14} className="text-slate-400" />
                        {dag.node_count} nodes / {dag.edge_count} edges
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {dag.latest_run ? (
                        <>
                          <span
                            className={clsx(
                              'px-2 py-1 rounded-full text-xs font-semibold',
                              statusClass[dag.latest_run.status] ?? 'bg-slate-100 text-slate-700',
                            )}
                          >
                            {dag.latest_run.status}
                          </span>
                          <p className="text-xs text-slate-500 mt-1">
                            {new Date(dag.latest_run.started_at).toLocaleString()}
                          </p>
                        </>
                      ) : (
                        <span className="text-slate-400">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      <div className="flex items-center gap-1">
                        <Clock3 size={12} /> next: {dag.next_scheduled_at ? new Date(dag.next_scheduled_at).toLocaleString() : '-'}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button
                          onClick={() => void loadDagDetail(dag.id)}
                          className="rounded-lg bg-slate-100 text-slate-700 px-2.5 py-1.5 text-xs hover:bg-slate-200"
                        >
                          Detail
                        </button>
                        <button
                          onClick={() => openEditModal(dag)}
                          className="rounded-lg bg-indigo-100 text-indigo-700 px-2.5 py-1.5 text-xs hover:bg-indigo-200 flex items-center gap-1"
                        >
                          <PenSquare size={12} />
                          Edit
                        </button>
                        <button
                          onClick={() => void runDag(dag.id)}
                          disabled={runLoadingDagId === dag.id}
                          className="rounded-lg bg-cyan-100 text-cyan-700 px-2.5 py-1.5 text-xs hover:bg-cyan-200 flex items-center gap-1 disabled:opacity-50"
                        >
                          <Play size={12} />
                          Run
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selectedDagId && (
        <>
          <div
            className="fixed inset-0 bg-black/25 z-40"
            onClick={() => {
              setSelectedDagId(null)
              setDagDetail(null)
            }}
          />
          <aside className="fixed right-0 top-0 h-screen w-[700px] bg-white z-50 border-l border-slate-200 shadow-2xl overflow-auto">
            <div className="p-5 border-b border-slate-200 flex items-center justify-between">
              <h3 className="font-bold text-slate-900 text-lg">Scheduler DAG Detail</h3>
              <button
                onClick={() => {
                  setSelectedDagId(null)
                  setDagDetail(null)
                }}
                className="p-2 rounded-lg hover:bg-slate-100"
              >
                <X size={16} />
              </button>
            </div>

            {detailLoading || !dagDetail ? (
              <div className="p-8 text-slate-500">Loading DAG detail...</div>
            ) : (
              <div className="p-5 space-y-6">
                <div className="space-y-1">
                  <p className="text-xl font-semibold text-slate-900">{dagDetail.dag.name}</p>
                  <p className="text-sm text-slate-600">{dagDetail.dag.description || '-'}</p>
                  <p className="text-sm text-slate-600">
                    Status: {dagDetail.dag.status} | Trigger: {dagDetail.dag.trigger_mode} | Version: {dagDetail.dag.version}
                  </p>
                  <div className="pt-1 flex gap-2">
                    <button
                      onClick={() => openExploreForDag(dagDetail.dag.id)}
                      className="rounded-lg bg-indigo-600 text-white px-3 py-1.5 text-xs font-medium hover:bg-indigo-500"
                    >
                      Open in Explore
                    </button>
                    <button
                      onClick={() => openKnowledgeForDag(dagDetail.dag.id)}
                      className="rounded-lg bg-emerald-600 text-white px-3 py-1.5 text-xs font-medium hover:bg-emerald-500"
                    >
                      Related Docs
                    </button>
                  </div>
                </div>

                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Topology</p>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 space-y-2">
                    <div className="flex flex-wrap gap-2">
                      {dagDetail.topology.nodes.map((node) => (
                        <div key={node.id} className="rounded-lg border border-slate-200 bg-white p-2 text-xs min-w-[180px]">
                          <p className="font-semibold text-slate-800">{node.node_key}</p>
                          <p className="text-slate-500">{node.task_type}</p>
                          <p className="text-slate-500">in: {node.input_assets.map((item) => assetMap.get(item) || item).join(', ') || '-'}</p>
                          <p className="text-slate-500">out: {node.output_assets.join(', ') || '-'}</p>
                          {node.latest_status && (
                            <span
                              className={clsx(
                                'inline-block mt-1 px-2 py-0.5 rounded-full text-[11px] font-semibold',
                                statusClass[node.latest_status] ?? 'bg-slate-100 text-slate-700',
                              )}
                            >
                              {node.latest_status}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-2 text-xs text-slate-600">
                      {dagDetail.topology.edges.length === 0
                        ? 'No edges defined.'
                        : dagDetail.topology.edges.map((edge) => `${edge.from_node_key} -> ${edge.to_node_key}`).join(' | ')}
                    </div>
                  </div>
                </div>

                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Schedule</p>
                  <div className="rounded-xl border border-slate-200 bg-white p-3 text-sm space-y-1">
                    <p>Mode: {dagDetail.schedule.trigger_mode}</p>
                    <p>Cron: {dagDetail.schedule.cron_expr || '-'}</p>
                    <p>Dependency: {dagDetail.schedule.dependency_mode}</p>
                    <p>Retry: {JSON.stringify(dagDetail.schedule.retry_policy)}</p>
                    <p>Next: {dagDetail.schedule.next_scheduled_at ? new Date(dagDetail.schedule.next_scheduled_at).toLocaleString() : '-'}</p>
                  </div>
                </div>

                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Recent Runs</p>
                  <div className="space-y-2">
                    {dagDetail.recent_runs.length === 0 && <p className="text-sm text-slate-500">No runs yet.</p>}
                    {dagDetail.recent_runs.map((run) => (
                      <button
                        key={run.id}
                        onClick={() => void loadRunDetail(run.id)}
                        className="w-full text-left rounded-xl border border-slate-200 p-3 bg-white hover:bg-slate-50"
                      >
                        <div className="flex items-center justify-between">
                          <p className="font-semibold text-slate-800">Run #{run.id}</p>
                          <span
                            className={clsx(
                              'px-2 py-1 rounded-full text-xs font-semibold',
                              statusClass[run.status] ?? 'bg-slate-100 text-slate-700',
                            )}
                          >
                            {run.status}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 mt-1">
                          {new Date(run.started_at).toLocaleString()} | source={run.trigger_source}
                        </p>
                        <p className="text-xs text-slate-500 mt-1">duration={run.duration_ms ?? '-'} ms</p>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </aside>
        </>
      )}

      {selectedRunId && (
        <>
          <div
            className="fixed inset-0 bg-black/30 z-50"
            onClick={() => {
              setSelectedRunId(null)
              setRunDetail(null)
            }}
          />
          <aside className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[980px] max-h-[90vh] overflow-auto bg-white z-[60] rounded-2xl border border-slate-200 shadow-2xl">
            <div className="p-5 border-b border-slate-200 flex items-center justify-between">
              <h3 className="font-bold text-slate-900 text-lg">Run Detail</h3>
              <button
                onClick={() => {
                  setSelectedRunId(null)
                  setRunDetail(null)
                }}
                className="p-2 rounded-lg hover:bg-slate-100"
              >
                <X size={16} />
              </button>
            </div>

            {runDetailLoading || !runDetail ? (
              <div className="p-8 text-slate-500">Loading run detail...</div>
            ) : (
              <div className="p-5 space-y-4">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
                  <p className="font-semibold text-slate-900">{runDetail.dag.name} / Run #{runDetail.run.id}</p>
                  <p className="text-slate-600">
                    Status: {runDetail.run.status} | Source: {runDetail.run.trigger_source} | Duration: {runDetail.run.duration_ms ?? '-'} ms
                  </p>
                  <p className="text-slate-500 text-xs mt-1">{new Date(runDetail.run.started_at).toLocaleString()}</p>
                </div>

                <div className="space-y-2">
                  {runDetail.node_runs.map((nodeRun) => (
                    <div key={nodeRun.id} className="rounded-xl border border-slate-200 bg-white p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="font-semibold text-slate-800">
                            {nodeRun.node_key} (attempt {nodeRun.attempt})
                          </p>
                          <p className="text-xs text-slate-500 mt-1">{nodeRun.log_summary || '-'}</p>
                          {nodeRun.error_message && <p className="text-xs text-rose-600 mt-1">{nodeRun.error_message}</p>}
                        </div>
                        <div className="flex items-center gap-2">
                          <span
                            className={clsx(
                              'px-2 py-1 rounded-full text-xs font-semibold',
                              statusClass[nodeRun.status] ?? 'bg-slate-100 text-slate-700',
                            )}
                          >
                            {nodeRun.status}
                          </span>
                          <button
                            onClick={() => void applyNodeAction(runDetail.run, nodeRun, 'RETRY')}
                            disabled={nodeActionLoadingId === nodeRun.id}
                            className="rounded-lg bg-blue-100 text-blue-700 px-2 py-1 text-xs hover:bg-blue-200 disabled:opacity-50 flex items-center gap-1"
                          >
                            <RotateCcw size={12} />
                            Retry
                          </button>
                          <button
                            onClick={() => void applyNodeAction(runDetail.run, nodeRun, 'SKIP')}
                            disabled={nodeActionLoadingId === nodeRun.id}
                            className="rounded-lg bg-amber-100 text-amber-700 px-2 py-1 text-xs hover:bg-amber-200 disabled:opacity-50 flex items-center gap-1"
                          >
                            <SkipForward size={12} />
                            Skip
                          </button>
                          <button
                            onClick={() => void applyNodeAction(runDetail.run, nodeRun, 'MARK_SUCCESS')}
                            disabled={nodeActionLoadingId === nodeRun.id}
                            className="rounded-lg bg-emerald-100 text-emerald-700 px-2 py-1 text-xs hover:bg-emerald-200 disabled:opacity-50"
                          >
                            Mark Success
                          </button>
                        </div>
                      </div>

                      <div className="mt-2 text-xs text-slate-500 flex items-center gap-4">
                        <span>
                          <Activity size={12} className="inline mr-1" /> {nodeRun.duration_ms ?? '-'} ms
                        </span>
                        <span>upstream: {Object.keys(nodeRun.upstream_snapshot || {}).length}</span>
                      </div>
                    </div>
                  ))}
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
            <div className="w-full max-w-6xl rounded-2xl border border-slate-200 bg-white shadow-2xl p-5 space-y-4 max-h-[95vh] overflow-auto">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-slate-900">{editingDag ? 'Edit Scheduler DAG' : 'Create Scheduler DAG'}</h3>
                <button onClick={() => setFormOpen(false)} className="p-2 rounded hover:bg-slate-100">
                  <X size={16} />
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <input
                  value={formState.name}
                  onChange={(e) => setFormState((prev) => ({ ...prev, name: e.target.value }))}
                  placeholder="DAG Name"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none md:col-span-2"
                />
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
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none md:col-span-3 h-20"
                />

                <select
                  value={formState.trigger_mode}
                  onChange={(e) => setFormState((prev) => ({ ...prev, trigger_mode: e.target.value }))}
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                >
                  <option value="MANUAL">MANUAL</option>
                  <option value="CRON">CRON</option>
                  <option value="DEPENDENCY">DEPENDENCY</option>
                </select>
                <input
                  value={formState.cron_expr}
                  onChange={(e) => setFormState((prev) => ({ ...prev, cron_expr: e.target.value }))}
                  placeholder="Cron (e.g. */5 * * * *)"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                />
                <input
                  value={formState.timezone}
                  onChange={(e) => setFormState((prev) => ({ ...prev, timezone: e.target.value }))}
                  placeholder="Timezone"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                />
                <input
                  value={formState.dependency_mode}
                  onChange={(e) => setFormState((prev) => ({ ...prev, dependency_mode: e.target.value }))}
                  placeholder="Dependency Mode"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                />
                <input
                  value={formState.retry_max_retries}
                  onChange={(e) => setFormState((prev) => ({ ...prev, retry_max_retries: e.target.value }))}
                  placeholder="Max Retries"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                />
                <input
                  value={formState.retry_backoff_seconds}
                  onChange={(e) => setFormState((prev) => ({ ...prev, retry_backoff_seconds: e.target.value }))}
                  placeholder="Backoff Seconds"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                />
                <textarea
                  value={formState.schedule_config_json}
                  onChange={(e) => setFormState((prev) => ({ ...prev, schedule_config_json: e.target.value }))}
                  placeholder="Schedule Config JSON"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none md:col-span-3 h-28 font-mono text-sm"
                />
              </div>

              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                <div className="rounded-xl border border-slate-200 p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <h4 className="font-semibold text-slate-900">Nodes</h4>
                    <button
                      onClick={addNode}
                      className="rounded-lg bg-slate-100 text-slate-700 px-2 py-1 text-xs hover:bg-slate-200"
                    >
                      + Add Node
                    </button>
                  </div>
                  {formState.nodes.map((node, index) => (
                    <div key={`${node.node_key}-${index}`} className="rounded-lg border border-slate-200 p-2 grid grid-cols-2 gap-2">
                      <input
                        value={node.node_key}
                        onChange={(e) =>
                          setFormState((prev) => ({
                            ...prev,
                            nodes: prev.nodes.map((item, i) => (i === index ? { ...item, node_key: e.target.value } : item)),
                          }))
                        }
                        placeholder="node_key"
                        className="px-2 py-1.5 border border-slate-200 rounded text-sm"
                      />
                      <input
                        value={node.name}
                        onChange={(e) =>
                          setFormState((prev) => ({
                            ...prev,
                            nodes: prev.nodes.map((item, i) => (i === index ? { ...item, name: e.target.value } : item)),
                          }))
                        }
                        placeholder="node name"
                        className="px-2 py-1.5 border border-slate-200 rounded text-sm"
                      />
                      <select
                        value={node.task_type}
                        onChange={(e) =>
                          setFormState((prev) => ({
                            ...prev,
                            nodes: prev.nodes.map((item, i) => (i === index ? { ...item, task_type: e.target.value } : item)),
                          }))
                        }
                        className="px-2 py-1.5 border border-slate-200 rounded text-sm"
                      >
                        {(taskTypes.length > 0 ? taskTypes : ['BATCH', 'VALIDATION', 'SYNC', 'CUSTOM']).map((type) => (
                          <option key={type} value={type}>
                            {type}
                          </option>
                        ))}
                      </select>
                      <button
                        onClick={() =>
                          setFormState((prev) => ({ ...prev, nodes: prev.nodes.filter((_, i) => i !== index) }))
                        }
                        className="px-2 py-1.5 rounded text-xs bg-rose-100 text-rose-700 hover:bg-rose-200"
                      >
                        Remove
                      </button>
                      <input
                        value={node.input_assets}
                        onChange={(e) =>
                          setFormState((prev) => ({
                            ...prev,
                            nodes: prev.nodes.map((item, i) =>
                              i === index ? { ...item, input_assets: e.target.value } : item,
                            ),
                          }))
                        }
                        placeholder="input assets (comma separated)"
                        className="px-2 py-1.5 border border-slate-200 rounded text-sm col-span-2"
                      />
                      <input
                        value={node.output_assets}
                        onChange={(e) =>
                          setFormState((prev) => ({
                            ...prev,
                            nodes: prev.nodes.map((item, i) =>
                              i === index ? { ...item, output_assets: e.target.value } : item,
                            ),
                          }))
                        }
                        placeholder="output assets (comma separated)"
                        className="px-2 py-1.5 border border-slate-200 rounded text-sm col-span-2"
                      />
                      <textarea
                        value={node.logic_description}
                        onChange={(e) =>
                          setFormState((prev) => ({
                            ...prev,
                            nodes: prev.nodes.map((item, i) =>
                              i === index ? { ...item, logic_description: e.target.value } : item,
                            ),
                          }))
                        }
                        placeholder="logic description"
                        className="px-2 py-1.5 border border-slate-200 rounded text-sm col-span-2 h-14"
                      />
                      <textarea
                        value={node.config_json}
                        onChange={(e) =>
                          setFormState((prev) => ({
                            ...prev,
                            nodes: prev.nodes.map((item, i) =>
                              i === index ? { ...item, config_json: e.target.value } : item,
                            ),
                          }))
                        }
                        placeholder="config JSON"
                        className="px-2 py-1.5 border border-slate-200 rounded text-sm col-span-2 h-20 font-mono"
                      />
                    </div>
                  ))}
                </div>

                <div className="rounded-xl border border-slate-200 p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <h4 className="font-semibold text-slate-900">Edges</h4>
                    <button
                      onClick={addEdge}
                      className="rounded-lg bg-slate-100 text-slate-700 px-2 py-1 text-xs hover:bg-slate-200"
                    >
                      + Add Edge
                    </button>
                  </div>
                  {formState.edges.map((edge, index) => (
                    <div key={`${edge.from_node_key}-${edge.to_node_key}-${index}`} className="rounded-lg border border-slate-200 p-2 grid grid-cols-2 gap-2">
                      <input
                        value={edge.from_node_key}
                        onChange={(e) =>
                          setFormState((prev) => ({
                            ...prev,
                            edges: prev.edges.map((item, i) =>
                              i === index ? { ...item, from_node_key: e.target.value } : item,
                            ),
                          }))
                        }
                        placeholder="from node_key"
                        className="px-2 py-1.5 border border-slate-200 rounded text-sm"
                      />
                      <input
                        value={edge.to_node_key}
                        onChange={(e) =>
                          setFormState((prev) => ({
                            ...prev,
                            edges: prev.edges.map((item, i) =>
                              i === index ? { ...item, to_node_key: e.target.value } : item,
                            ),
                          }))
                        }
                        placeholder="to node_key"
                        className="px-2 py-1.5 border border-slate-200 rounded text-sm"
                      />
                      <textarea
                        value={edge.condition_json}
                        onChange={(e) =>
                          setFormState((prev) => ({
                            ...prev,
                            edges: prev.edges.map((item, i) =>
                              i === index ? { ...item, condition_json: e.target.value } : item,
                            ),
                          }))
                        }
                        placeholder="condition JSON"
                        className="px-2 py-1.5 border border-slate-200 rounded text-sm col-span-2 h-20 font-mono"
                      />
                      <button
                        onClick={() =>
                          setFormState((prev) => ({ ...prev, edges: prev.edges.filter((_, i) => i !== index) }))
                        }
                        className="px-2 py-1.5 rounded text-xs bg-rose-100 text-rose-700 hover:bg-rose-200 col-span-2"
                      >
                        Remove Edge
                      </button>
                    </div>
                  ))}
                </div>
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
                  {formSubmitting ? 'Saving...' : editingDag ? 'Save Changes' : 'Create DAG'}
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default Scheduler
