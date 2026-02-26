import { FormEvent, useEffect, useMemo, useState } from 'react'
import { clsx } from 'clsx'
import { Beaker, Play, Rocket, RefreshCw } from 'lucide-react'

import {
  GenesisApi,
  type SandboxExperimentDetailResponse,
  type SandboxExperimentItem,
  type SandboxExperimentListResponse,
  type SandboxExperimentType,
  type SandboxOptionsResponse,
  type SandboxOverviewResponse,
} from '../services/api'

type Filters = {
  q: string
  status: string
  experiment_type: string
}

type CreateForm = {
  experiment_type: SandboxExperimentType
  title: string
  description: string
  source_type: string
  source_id: string
  config_json: string
}

const typeToSourceType: Record<SandboxExperimentType, string> = {
  EVENT_EXPERIMENT: 'TRACKING_EVENT',
  DQ_RULE_EXPERIMENT: 'DATA_QUALITY_RULE',
  PIPELINE_EXPERIMENT: 'PIPELINE',
  QUERY_EXPERIMENT: 'QUERY_TEMPLATE',
}

const SandboxExperimentation = () => {
  const [overview, setOverview] = useState<SandboxOverviewResponse | null>(null)
  const [options, setOptions] = useState<SandboxOptionsResponse | null>(null)
  const [listResp, setListResp] = useState<SandboxExperimentListResponse | null>(null)
  const [detail, setDetail] = useState<SandboxExperimentDetailResponse | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [filters, setFilters] = useState<Filters>({ q: '', status: 'ALL', experiment_type: 'ALL' })

  const [createForm, setCreateForm] = useState<CreateForm>({
    experiment_type: 'EVENT_EXPERIMENT',
    title: '',
    description: '',
    source_type: 'TRACKING_EVENT',
    source_id: '',
    config_json: '{\n  "strict": true\n}',
  })

  const [runForm, setRunForm] = useState({
    sample_size: '1000',
    traffic_ratio: '0.10',
    notes: '',
    candidate_json: '[\n  {\n    "key": "candidate_a",\n    "config": {}\n  }\n]',
  })

  const sourceOptions = useMemo(() => {
    if (!options) {
      return []
    }
    return (options.source_options[createForm.source_type as keyof SandboxOptionsResponse['source_options']] ?? [])
  }, [options, createForm.source_type])

  const safeParseJson = (text: string): { ok: true; data: unknown } | { ok: false; error: string } => {
    try {
      return { ok: true, data: JSON.parse(text) }
    } catch {
      return { ok: false, error: 'JSON 格式错误' }
    }
  }

  const loadOverview = async () => {
    const data = await GenesisApi.getSandboxOverview()
    setOverview(data)
  }

  const loadOptions = async (experimentType?: SandboxExperimentType) => {
    const data = await GenesisApi.getSandboxOptions(experimentType ? { experiment_type: experimentType } : undefined)
    setOptions(data)
  }

  const loadList = async () => {
    const params = {
      q: filters.q.trim() || undefined,
      status: filters.status === 'ALL' ? undefined : filters.status,
      experiment_type: filters.experiment_type === 'ALL' ? undefined : filters.experiment_type,
      limit: 200,
      offset: 0,
    }
    const data = await GenesisApi.getSandboxExperiments(params)
    setListResp(data)

    if (!selectedId && data.items.length > 0) {
      setSelectedId(data.items[0].id)
    }
    if (selectedId && !data.items.some((item) => item.id === selectedId)) {
      setSelectedId(data.items[0]?.id ?? null)
    }
  }

  const loadDetail = async (id: number) => {
    const data = await GenesisApi.getSandboxExperimentDetail(id)
    setDetail(data)
  }

  const refreshAll = async () => {
    setLoading(true)
    setError(null)
    try {
      await Promise.all([loadOverview(), loadList()])
      if (selectedId) {
        await loadDetail(selectedId)
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load sandbox data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setLoading(true)
    Promise.all([loadOverview(), loadOptions(createForm.experiment_type), loadList()])
      .catch((e: any) => {
        setError(e?.response?.data?.message ?? 'Failed to load sandbox data')
      })
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (selectedId != null) {
      void loadDetail(selectedId).catch(() => {
        setDetail(null)
      })
    } else {
      setDetail(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId])

  const onApplyFilters = async (event: FormEvent) => {
    event.preventDefault()
    await refreshAll()
  }

  const onCreate = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)

    const parsedConfig = safeParseJson(createForm.config_json)
    if (!parsedConfig.ok) {
      setError(`创建实验失败: ${parsedConfig.error}`)
      return
    }
    if (!createForm.source_id) {
      setError('创建实验失败: 请先选择 source')
      return
    }

    setLoading(true)
    try {
      const created = await GenesisApi.createSandboxExperiment({
        experiment_type: createForm.experiment_type,
        title: createForm.title.trim(),
        description: createForm.description.trim() || undefined,
        source_type: createForm.source_type,
        source_id: createForm.source_id,
        config_payload: parsedConfig.data as Record<string, unknown>,
      })
      await Promise.all([loadOverview(), loadList()])
      setSelectedId(created.id)
      await loadDetail(created.id)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? '创建实验失败')
    } finally {
      setLoading(false)
    }
  }

  const onRun = async () => {
    if (!selectedId) return
    setError(null)

    const parsedCandidates = safeParseJson(runForm.candidate_json)
    if (!parsedCandidates.ok || !Array.isArray(parsedCandidates.data)) {
      setError('运行实验失败: candidate_json 必须是数组 JSON')
      return
    }

    setLoading(true)
    try {
      await GenesisApi.runSandboxExperiment(selectedId, {
        sample_size: Number(runForm.sample_size),
        traffic_ratio: Number(runForm.traffic_ratio),
        notes: runForm.notes.trim() || undefined,
        candidate_payloads: parsedCandidates.data as Array<Record<string, unknown>>,
      })
      await Promise.all([loadOverview(), loadList(), loadDetail(selectedId)])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? '运行实验失败')
    } finally {
      setLoading(false)
    }
  }

  const onPromote = async () => {
    if (!selectedId) return
    setError(null)

    setLoading(true)
    try {
      await GenesisApi.promoteSandboxExperiment(selectedId, {
        note: 'Promoted from sandbox page',
      })
      await Promise.all([loadOverview(), loadList(), loadDetail(selectedId)])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? '推广失败')
    } finally {
      setLoading(false)
    }
  }

  const selectedExperiment: SandboxExperimentItem | null = detail?.experiment ?? null

  return (
    <div className="max-w-7xl mx-auto space-y-4 animate-in fade-in slide-in-from-bottom-8 duration-700">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">Sandbox & Experimentation</h2>
          <p className="text-slate-500 text-base">Create experiments, run candidates, compare metrics, then promote to production.</p>
        </div>
        <button
          onClick={() => void refreshAll()}
          disabled={loading}
          className="rounded-xl bg-slate-900 text-white px-4 py-2.5 font-medium hover:bg-slate-800 disabled:opacity-60 flex items-center gap-2"
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </header>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}

      <section className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Total</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.total_experiments ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Draft</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.draft_count ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Running</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.running_count ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Completed</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.completed_count ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Promoted</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.promoted_count ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Runs (7d)</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.runs_7d ?? 0}</p></div>
      </section>

      <form onSubmit={onApplyFilters} className="glass rounded-3xl border border-slate-200/60 p-4">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          <input value={filters.q} onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))} placeholder="search title/source id" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
          <select value={filters.status} onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
            <option value="ALL">ALL STATUS</option>
            {(listResp?.facets.statuses ?? []).map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <select value={filters.experiment_type} onChange={(e) => setFilters((prev) => ({ ...prev, experiment_type: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
            <option value="ALL">ALL TYPES</option>
            {(options?.experiment_types ?? []).map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <button type="submit" className="rounded-xl bg-cyan-600 text-white px-4 py-2 text-sm font-semibold">Apply Filters</button>
        </div>
      </form>

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="glass rounded-3xl border border-slate-200/60 p-4 xl:col-span-1 space-y-3">
          <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2"><Beaker size={16} /> Create Experiment</h3>
          <form onSubmit={onCreate} className="space-y-2">
            <select
              value={createForm.experiment_type}
              onChange={async (e) => {
                const nextType = e.target.value as SandboxExperimentType
                const nextSource = typeToSourceType[nextType]
                setCreateForm((prev) => ({ ...prev, experiment_type: nextType, source_type: nextSource, source_id: '' }))
                await loadOptions(nextType)
              }}
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
            >
              {(options?.experiment_types ?? []).map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <input value={createForm.title} onChange={(e) => setCreateForm((prev) => ({ ...prev, title: e.target.value }))} placeholder="experiment title" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" required />
            <input value={createForm.description} onChange={(e) => setCreateForm((prev) => ({ ...prev, description: e.target.value }))} placeholder="description" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <select value={createForm.source_type} onChange={(e) => setCreateForm((prev) => ({ ...prev, source_type: e.target.value, source_id: '' }))} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
              {(options?.source_types ?? []).map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select value={createForm.source_id} onChange={(e) => setCreateForm((prev) => ({ ...prev, source_id: e.target.value }))} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
              <option value="">Select source</option>
              {sourceOptions.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
            <textarea value={createForm.config_json} onChange={(e) => setCreateForm((prev) => ({ ...prev, config_json: e.target.value }))} rows={6} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-mono" />
            <button type="submit" disabled={loading} className="w-full rounded-xl bg-slate-900 text-white px-4 py-2 text-sm font-semibold disabled:opacity-60">Create</button>
          </form>
        </div>

        <div className="glass rounded-3xl border border-slate-200/60 p-4 xl:col-span-2">
          <h3 className="text-sm font-semibold text-slate-800 mb-3">Experiments</h3>
          <div className="space-y-2 max-h-80 overflow-auto">
            {(listResp?.items ?? []).map((item) => (
              <button
                key={item.id}
                onClick={() => setSelectedId(item.id)}
                className={clsx(
                  'w-full text-left rounded-xl border px-3 py-2 transition',
                  item.id === selectedId ? 'border-cyan-300 bg-cyan-50/70' : 'border-slate-200 bg-white hover:bg-slate-50',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold text-slate-800 text-sm">{item.title}</p>
                  <span className="text-xs text-slate-500">{item.status}</span>
                </div>
                <p className="text-xs text-slate-500 mt-1">{item.experiment_type} | {item.source_type}:{item.source_id}</p>
              </button>
            ))}
          </div>

          {selectedExperiment && (
            <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <h4 className="text-sm font-semibold text-slate-800 mb-2">Selected</h4>
                <p className="text-sm text-slate-700">{selectedExperiment.title}</p>
                <p className="text-xs text-slate-500 mt-1">{selectedExperiment.experiment_type} | {selectedExperiment.status}</p>
                <p className="text-xs text-slate-500">{selectedExperiment.source_type}:{selectedExperiment.source_id}</p>
                <p className="text-xs text-slate-500">updated {new Date(selectedExperiment.updated_at).toLocaleString()}</p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3 space-y-2">
                <h4 className="text-sm font-semibold text-slate-800">Run / Promote</h4>
                <input value={runForm.sample_size} onChange={(e) => setRunForm((prev) => ({ ...prev, sample_size: e.target.value }))} placeholder="sample_size" className="w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm" />
                <input value={runForm.traffic_ratio} onChange={(e) => setRunForm((prev) => ({ ...prev, traffic_ratio: e.target.value }))} placeholder="traffic_ratio" className="w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm" />
                <input value={runForm.notes} onChange={(e) => setRunForm((prev) => ({ ...prev, notes: e.target.value }))} placeholder="notes" className="w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm" />
                <textarea value={runForm.candidate_json} onChange={(e) => setRunForm((prev) => ({ ...prev, candidate_json: e.target.value }))} rows={6} className="w-full rounded-lg border border-slate-200 px-2 py-1.5 text-xs font-mono" />
                <div className="flex gap-2">
                  <button onClick={() => void onRun()} disabled={loading} className="flex-1 rounded-lg bg-cyan-600 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60 inline-flex items-center justify-center gap-1"><Play size={14} /> Run</button>
                  <button onClick={() => void onPromote()} disabled={loading} className="flex-1 rounded-lg bg-emerald-600 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60 inline-flex items-center justify-center gap-1"><Rocket size={14} /> Promote</button>
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="glass rounded-3xl border border-slate-200/60 p-4">
        <h3 className="text-sm font-semibold text-slate-800 mb-3">Latest Run Summary</h3>
        {detail?.latest_run ? (
          <div className="rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-700 space-y-1">
            <p>Run #{detail.latest_run.run_no} | status {detail.latest_run.status}</p>
            <p>Duration: {detail.latest_run.duration_ms ?? 0} ms</p>
            <p>Best Candidate: {String(detail.latest_run.recommendation_payload.best_candidate_key ?? '-')}</p>
            <p>Decision: {String(detail.latest_run.recommendation_payload.decision ?? '-')}</p>
          </div>
        ) : (
          <p className="text-sm text-slate-500">No runs yet.</p>
        )}
      </section>
    </div>
  )
}

export default SandboxExperimentation
