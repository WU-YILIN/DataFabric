import { useEffect, useMemo, useState } from 'react'
import { clsx } from 'clsx'
import {
  Activity,
  AlertTriangle,
  Database,
  HardDrive,
  Layers3,
  RefreshCw,
  SearchCode,
  Server,
  Workflow,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { GenesisApi, type InfrastructureOverviewResponse } from '../services/api'
import { useBrowserErrorAlert } from '../hooks/useBrowserErrorAlert'
import { useLanguage } from '../i18n/language'

const healthClass: Record<string, string> = {
  HEALTHY: 'bg-emerald-100 text-emerald-700',
  DEGRADED: 'bg-amber-100 text-amber-700',
  CRITICAL: 'bg-rose-100 text-rose-700',
}

const hotClass: Record<string, string> = {
  LOW: 'bg-slate-100 text-slate-700',
  MEDIUM: 'bg-amber-100 text-amber-700',
  HIGH: 'bg-rose-100 text-rose-700',
}

const Infrastructure = () => {
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const L = (cn: string, en: string) => (isZh ? cn : en)
  const navigate = useNavigate()
  const [data, setData] = useState<InfrastructureOverviewResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useBrowserErrorAlert(error)

  const [environmentFilter, setEnvironmentFilter] = useState('ALL')
  const [clusterFilter, setClusterFilter] = useState('ALL')

  const filterOptions = useMemo(
    () => ({
      environments: data?.filters.available_environments ?? [],
      clusters: data?.filters.available_clusters ?? [],
    }),
    [data],
  )

  const loadOverview = async () => {
    setLoading(true)
    setError(null)
    try {
      const overview = await GenesisApi.getInfrastructureOverview({
        environment: environmentFilter === 'ALL' ? undefined : environmentFilter,
        cluster: clusterFilter === 'ALL' ? undefined : clusterFilter,
      })
      setData(overview)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? L('加载基础设施总览失败', 'Failed to load infrastructure overview'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadOverview()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!data) {
      return
    }
    if (environmentFilter !== 'ALL' && !data.filters.available_environments.includes(environmentFilter)) {
      setEnvironmentFilter('ALL')
    }
    if (clusterFilter !== 'ALL' && !data.filters.available_clusters.includes(clusterFilter)) {
      setClusterFilter('ALL')
    }
  }, [clusterFilter, data, environmentFilter])

  const openExplore = (prefillLink: string | null | undefined) => {
    if (!prefillLink) {
      navigate('/explore')
      return
    }
    navigate(prefillLink)
  }

  return (
    <div className="max-w-7xl mx-auto animate-in fade-in slide-in-from-bottom-8 duration-700 space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">{L('基础设施', 'Infrastructure')}</h2>
          <p className="text-slate-500 text-base">
            {L('结合环境和集群筛选查看 Kafka / Flink / Storage 健康概览。', 'Kafka / Flink / Storage health overview with cluster and environment filters.')}
          </p>
        </div>
        <button
          onClick={() => void loadOverview()}
          disabled={loading}
          className="rounded-xl bg-slate-900 text-white px-4 py-2.5 font-medium hover:bg-slate-800 disabled:opacity-60 flex items-center gap-2"
        >
          <RefreshCw size={16} />
          {L('刷新', 'Refresh')}
        </button>
      </header>

      <section className="glass rounded-3xl border border-slate-200/60 p-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
          <div>
            <label className="text-xs text-slate-500 uppercase tracking-wide">{L('环境', 'Environment')}</label>
            <select
              value={environmentFilter}
              onChange={(e) => setEnvironmentFilter(e.target.value)}
              className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"
            >
              <option value="ALL">{L('全部环境', 'All Environments')}</option>
              {filterOptions.environments.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500 uppercase tracking-wide">{L('集群', 'Cluster')}</label>
            <select
              value={clusterFilter}
              onChange={(e) => setClusterFilter(e.target.value)}
              className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"
            >
              <option value="ALL">{L('全部集群', 'All Clusters')}</option>
              {filterOptions.clusters.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={() => void loadOverview()}
            className="rounded-xl bg-cyan-600 text-white px-4 py-2.5 font-medium hover:bg-cyan-500"
          >
            {L('应用筛选', 'Apply Filters')}
          </button>
          <div className="text-xs text-slate-500 md:text-right">
            {L('采集时间', 'Collected at')}:
            {' '}
            {data?.collected_at ? new Date(data.collected_at).toLocaleString() : '-'}
          </div>
        </div>
      </section>

      <section className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Kafka Clusters</p>
          <p className="text-2xl font-bold text-slate-900">{data?.summary.kafka_clusters ?? 0}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Kafka Topics</p>
          <p className="text-2xl font-bold text-slate-900">{data?.summary.kafka_topics ?? 0}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Flink Clusters</p>
          <p className="text-2xl font-bold text-slate-900">{data?.summary.flink_clusters ?? 0}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Flink Jobs</p>
          <p className="text-2xl font-bold text-slate-900">{data?.summary.flink_jobs ?? 0}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Storage Systems</p>
          <p className="text-2xl font-bold text-slate-900">{data?.summary.storage_systems ?? 0}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Open Alerts</p>
          <p className="text-2xl font-bold text-rose-700">{data?.summary.open_alerts ?? 0}</p>
        </div>
      </section>

      <section className="glass rounded-3xl border border-slate-200/60 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200/70 bg-slate-50/70 flex items-center gap-2">
          <Server size={16} className="text-slate-500" />
          <h3 className="text-sm font-semibold text-slate-800">Kafka Overview</h3>
        </div>
        <div className="p-4 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {(data?.kafka.clusters ?? []).map((cluster) => (
              <div key={`${cluster.environment}:${cluster.cluster_id}`} className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-slate-800">{cluster.cluster_id}</p>
                  <span className={clsx('px-2 py-0.5 rounded-full text-xs font-semibold', healthClass[cluster.health_status] ?? 'bg-slate-100 text-slate-700')}>
                    {cluster.health_status}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  env={cluster.environment} | version={cluster.version}
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  brokers {cluster.healthy_brokers}/{cluster.broker_count} | topics {cluster.topic_count}
                </p>
                <p className="text-xs text-slate-500 mt-1">warnings {cluster.warning_count}</p>
              </div>
            ))}
            {(data?.kafka.clusters.length ?? 0) === 0 && (
              <p className="text-sm text-slate-500">No Kafka cluster data under current filters.</p>
            )}
          </div>

          <div className="overflow-auto rounded-xl border border-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="text-left px-3 py-2">Topic</th>
                  <th className="text-left px-3 py-2">Status</th>
                  <th className="text-left px-3 py-2">Env/Cluster</th>
                  <th className="text-left px-3 py-2">Partitions</th>
                  <th className="text-left px-3 py-2">Backlog</th>
                  <th className="text-left px-3 py-2">Alerts</th>
                  <th className="text-left px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {(data?.kafka.topics ?? []).map((topic) => (
                  <tr key={topic.pipeline_id} className="border-t border-slate-100">
                    <td className="px-3 py-2">
                      <p className="font-semibold text-slate-800">{topic.topic_name}</p>
                      <p className="text-xs text-slate-500">{topic.event_code}</p>
                    </td>
                    <td className="px-3 py-2">{topic.status}</td>
                    <td className="px-3 py-2 text-xs text-slate-600">
                      {topic.environment}
                      {' / '}
                      {topic.cluster_id}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-600">
                      {topic.partitions}
                      {' / rf='}
                      {topic.replication_factor}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-600">{topic.estimated_backlog}</td>
                    <td className="px-3 py-2 text-xs text-slate-600">{topic.alert_count}</td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        <button
                          onClick={() => navigate('/pipelines')}
                          className="rounded-md bg-slate-100 text-slate-700 px-2 py-1 text-xs hover:bg-slate-200"
                        >
                          Pipelines
                        </button>
                        <button
                          onClick={() => navigate('/catalog')}
                          className="rounded-md bg-slate-100 text-slate-700 px-2 py-1 text-xs hover:bg-slate-200"
                        >
                          Catalog
                        </button>
                        <button
                          onClick={() => openExplore(topic.links.explore_prefill)}
                          className="rounded-md bg-indigo-100 text-indigo-700 px-2 py-1 text-xs hover:bg-indigo-200"
                        >
                          Explore
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {(data?.kafka.topics.length ?? 0) === 0 && (
                  <tr>
                    <td colSpan={7} className="px-3 py-4 text-sm text-slate-500">
                      No topic records under current filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="glass rounded-3xl border border-slate-200/60 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200/70 bg-slate-50/70 flex items-center gap-2">
          <Workflow size={16} className="text-slate-500" />
          <h3 className="text-sm font-semibold text-slate-800">Flink Overview</h3>
        </div>
        <div className="p-4 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {(data?.flink.clusters ?? []).map((cluster) => (
              <div key={`${cluster.environment}:${cluster.cluster_id}`} className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-slate-800">{cluster.cluster_id}</p>
                  <span className={clsx('px-2 py-0.5 rounded-full text-xs font-semibold', healthClass[cluster.health_status] ?? 'bg-slate-100 text-slate-700')}>
                    {cluster.health_status}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  env={cluster.environment} | version={cluster.version}
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  TM {cluster.taskmanagers_healthy}/{cluster.taskmanagers_total}
                  {' | slots '}
                  {cluster.slots_used}/{cluster.slots_total}
                </p>
                <p className="text-xs text-slate-500 mt-1">checkpoint={cluster.checkpoint_health}</p>
              </div>
            ))}
            {(data?.flink.clusters.length ?? 0) === 0 && (
              <p className="text-sm text-slate-500">No Flink cluster data under current filters.</p>
            )}
          </div>

          <div className="overflow-auto rounded-xl border border-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="text-left px-3 py-2">Job</th>
                  <th className="text-left px-3 py-2">State</th>
                  <th className="text-left px-3 py-2">Pipeline</th>
                  <th className="text-left px-3 py-2">Scheduler</th>
                  <th className="text-left px-3 py-2">Cluster</th>
                  <th className="text-left px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {(data?.flink.jobs ?? []).map((job) => (
                  <tr key={job.pipeline_id} className="border-t border-slate-100">
                    <td className="px-3 py-2">
                      <p className="font-semibold text-slate-800">{job.job_name}</p>
                      <p className="text-xs text-slate-500">{job.job_id}</p>
                    </td>
                    <td className="px-3 py-2">
                      <p>{job.state}</p>
                      <p className="text-xs text-slate-500">pipeline={job.pipeline_status}</p>
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-600">
                      #{job.pipeline_id}
                      {' | alerts '}
                      {job.alert_count}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-600">
                      dags:
                      {' '}
                      {job.scheduler_dag_ids.length ? job.scheduler_dag_ids.join(', ') : '-'}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-600">
                      {job.environment}
                      {' / '}
                      {job.cluster_id}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        <button
                          onClick={() => navigate('/pipelines')}
                          className="rounded-md bg-slate-100 text-slate-700 px-2 py-1 text-xs hover:bg-slate-200"
                        >
                          Pipelines
                        </button>
                        <button
                          onClick={() => navigate('/scheduler')}
                          className="rounded-md bg-slate-100 text-slate-700 px-2 py-1 text-xs hover:bg-slate-200"
                        >
                          Scheduler
                        </button>
                        <button
                          onClick={() => openExplore(job.links.explore_prefill)}
                          className="rounded-md bg-indigo-100 text-indigo-700 px-2 py-1 text-xs hover:bg-indigo-200"
                        >
                          Explore
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {(data?.flink.jobs.length ?? 0) === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-4 text-sm text-slate-500">
                      No Flink jobs under current filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="glass rounded-3xl border border-slate-200/60 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-200/70 bg-slate-50/70 flex items-center gap-2">
            <HardDrive size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">Storage Overview</h3>
          </div>
          <div className="p-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs text-slate-500">Capacity (GB)</p>
                <p className="text-lg font-bold text-slate-900">{data?.storage.overview.capacity_total_gb ?? 0}</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs text-slate-500">Used (GB)</p>
                <p className="text-lg font-bold text-slate-900">{data?.storage.overview.used_gb ?? 0}</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs text-slate-500">Usage Rate</p>
                <p className="text-lg font-bold text-slate-900">
                  {Math.round((data?.storage.overview.usage_rate ?? 0) * 100)}
                  %
                </p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs text-slate-500">Hot Paths</p>
                <p className="text-lg font-bold text-rose-700">{data?.storage.overview.hot_path_count ?? 0}</p>
              </div>
            </div>
            <div className="space-y-2">
              {(data?.storage.systems ?? []).map((system) => (
                <div key={`${system.environment}:${system.cluster_id}:${system.source_system}`} className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
                  <div className="flex items-center justify-between">
                    <p className="font-semibold text-slate-800">{system.source_system}</p>
                    <p className="text-xs text-slate-500">
                      {system.environment}
                      {' / '}
                      {system.cluster_id}
                    </p>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    assets {system.asset_count}
                    {' | used '}
                    {system.used_gb} GB
                    {' / '}
                    {system.capacity_gb} GB
                  </p>
                </div>
              ))}
              {(data?.storage.systems.length ?? 0) === 0 && (
                <p className="text-sm text-slate-500">No storage systems under current filters.</p>
              )}
            </div>
          </div>
        </div>

        <div className="glass rounded-3xl border border-slate-200/60 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-200/70 bg-slate-50/70 flex items-center gap-2">
            <Layers3 size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">Key Paths</h3>
          </div>
          <div className="p-4 space-y-2 max-h-[440px] overflow-auto">
            {(data?.storage.key_paths ?? []).map((path) => (
              <div key={`${path.path}:${path.cluster_id}`} className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold text-slate-800 text-sm">{path.path}</p>
                  <span className={clsx('px-2 py-0.5 rounded-full text-xs font-semibold', hotClass[path.hot_level] ?? 'bg-slate-100 text-slate-700')}>
                    {path.hot_level}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  {path.environment}
                  {' / '}
                  {path.cluster_id}
                  {' | assets '}
                  {path.asset_count}
                  {' | usage '}
                  {Math.round(path.usage_rate * 100)}
                  %
                </p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {path.sample_assets.map((asset) => (
                    <span key={asset.id} className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700">
                      {asset.object_name}
                    </span>
                  ))}
                </div>
                <div className="mt-2 flex gap-1">
                  <button
                    onClick={() => navigate('/catalog')}
                    className="rounded-md bg-slate-100 text-slate-700 px-2 py-1 text-xs hover:bg-slate-200"
                  >
                    Catalog
                  </button>
                  <button
                    onClick={() => openExplore(path.links.explore_prefill)}
                    className="rounded-md bg-indigo-100 text-indigo-700 px-2 py-1 text-xs hover:bg-indigo-200"
                  >
                    Explore
                  </button>
                </div>
              </div>
            ))}
            {(data?.storage.key_paths.length ?? 0) === 0 && (
              <p className="text-sm text-slate-500">No storage key-path records under current filters.</p>
            )}
          </div>
        </div>
      </section>

      <section className="glass rounded-3xl border border-slate-200/60 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200/70 bg-slate-50/70 flex items-center gap-2">
          <AlertTriangle size={16} className="text-slate-500" />
          <h3 className="text-sm font-semibold text-slate-800">Monitoring Alerts</h3>
        </div>
        <div className="p-4 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <div className="rounded-xl border border-slate-200 bg-white p-3">
              <p className="text-xs text-slate-500">Open</p>
              <p className="text-xl font-bold text-slate-900">{data?.alerts.open_count ?? 0}</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-3">
              <p className="text-xs text-slate-500">Critical</p>
              <p className="text-xl font-bold text-rose-700">{data?.alerts.critical_count ?? 0}</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-3">
              <p className="text-xs text-slate-500">High</p>
              <p className="text-xl font-bold text-amber-700">{data?.alerts.high_count ?? 0}</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-3">
              <p className="text-xs text-slate-500">Sources</p>
              <p className="text-xl font-bold text-slate-900">{data?.alerts.by_source.length ?? 0}</p>
            </div>
          </div>

          <div className="flex flex-wrap gap-1">
            {(data?.alerts.by_source ?? []).map((item) => (
              <span key={item.source_type} className="rounded-full bg-slate-100 text-slate-700 px-2.5 py-1 text-xs">
                {item.source_type}
                {' '}
                {item.count}
              </span>
            ))}
          </div>

          <div className="space-y-2">
            {(data?.alerts.recent ?? []).map((alert) => (
              <div key={alert.id} className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold text-slate-800 text-sm">{alert.title}</p>
                  <span className="text-xs text-slate-500">{alert.severity}</span>
                </div>
                <p className="text-xs text-slate-600 mt-1">{alert.description}</p>
                <p className="text-[11px] text-slate-500 mt-1">
                  {alert.source_type}:{alert.source_id}
                  {' | '}
                  {new Date(alert.created_at).toLocaleString()}
                </p>
                <div className="mt-2 flex flex-wrap gap-1">
                  <button
                    onClick={() => navigate('/pipelines')}
                    className="rounded-md bg-slate-100 text-slate-700 px-2 py-1 text-xs hover:bg-slate-200"
                  >
                    <Activity size={12} className="inline mr-1" />
                    Pipelines
                  </button>
                  <button
                    onClick={() => navigate('/data-quality')}
                    className="rounded-md bg-slate-100 text-slate-700 px-2 py-1 text-xs hover:bg-slate-200"
                  >
                    <Database size={12} className="inline mr-1" />
                    Data Quality
                  </button>
                  <button
                    onClick={() => navigate('/scheduler')}
                    className="rounded-md bg-slate-100 text-slate-700 px-2 py-1 text-xs hover:bg-slate-200"
                  >
                    <Layers3 size={12} className="inline mr-1" />
                    Scheduler
                  </button>
                  <button
                    onClick={() => openExplore(alert.links.explore_prefill)}
                    className="rounded-md bg-indigo-100 text-indigo-700 px-2 py-1 text-xs hover:bg-indigo-200"
                  >
                    <SearchCode size={12} className="inline mr-1" />
                    Explore
                  </button>
                </div>
              </div>
            ))}
            {(data?.alerts.recent.length ?? 0) === 0 && (
              <p className="text-sm text-slate-500">No alerts under current filters.</p>
            )}
          </div>
        </div>
      </section>
    </div>
  )
}

export default Infrastructure
