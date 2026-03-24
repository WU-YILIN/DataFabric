import { useEffect, useMemo, useState } from 'react'
import { RefreshCw, ScanSearch, Search, Server } from 'lucide-react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import {
  GenesisApi,
  type SourceInstance,
  type SourceTelemetryOverview,
  type SourceTelemetryPoint,
} from '../services/api'
import {
  FabricBadge,
  FabricEmptyState,
  FabricPageHeader,
  FabricSection,
  FabricStatCard,
} from '../components/fabricUi'

const HEAT_COLORS: Record<string, string> = {
  HOT: '#ef4444',
  WARM: '#f59e0b',
  COLD: '#3b82f6',
}

function metricPoints(seriesMap: Record<string, SourceTelemetryPoint[]>, key: keyof SourceTelemetryPoint) {
  const firstSeries = Object.values(seriesMap)[0] ?? []
  return firstSeries.map((item) => ({
    sample_at: String(item.sample_at).slice(11, 16),
    value: Number(item[key] ?? 0),
    heat_level: item.heat_level || 'COLD',
  }))
}

export default function FabricTelemetry() {
  const [instances, setInstances] = useState<SourceInstance[]>([])
  const [instanceKeyword, setInstanceKeyword] = useState('')
  const [selectedInstanceId, setSelectedInstanceId] = useState<number | 'ALL'>('ALL')
  const [window, setWindow] = useState<'24h' | '7d'>('24h')
  const [overview, setOverview] = useState<SourceTelemetryOverview | null>(null)
  const [sourceSeries, setSourceSeries] = useState<Record<string, SourceTelemetryPoint[]>>({})
  const [instanceOverview, setInstanceOverview] = useState<Record<string, unknown> | null>(null)
  const [instanceNodes, setInstanceNodes] = useState<Array<Record<string, unknown>>>([])
  const [loading, setLoading] = useState(true)
  const [detecting, setDetecting] = useState(false)

  const selectedInstance = useMemo(
    () => instances.find((item) => item.id === selectedInstanceId) ?? null,
    [instances, selectedInstanceId],
  )

  const filteredInstances = useMemo(() => {
    const keyword = instanceKeyword.trim().toLowerCase()
    if (!keyword) return instances
    return instances.filter((item) => {
      return (
        item.instance_name.toLowerCase().includes(keyword) ||
        item.connector_name.toLowerCase().includes(keyword) ||
        item.status.toLowerCase().includes(keyword) ||
        item.heat_level.toLowerCase().includes(keyword)
      )
    })
  }, [instances, instanceKeyword])

  const load = async () => {
    setLoading(true)
    try {
      const instanceList = await GenesisApi.listSourceInstances({ page: 1, page_size: 100 })
      setInstances(instanceList.items)

      if (selectedInstanceId === 'ALL') {
        const [overviewData, sourceData] = await Promise.all([
          GenesisApi.getSourceTelemetryOverview(),
          GenesisApi.getSourceTelemetrySeries({ window }),
        ])
        setOverview(overviewData)
        setSourceSeries(sourceData.series)
        setInstanceOverview(null)
        setInstanceNodes([])
      } else {
        const [overviewData, sourceData, detail] = await Promise.all([
          GenesisApi.getSourceTelemetryOverview({ instance_id: selectedInstanceId }),
          GenesisApi.getSourceTelemetrySeries({ window, instance_id: selectedInstanceId }),
          GenesisApi.getInstanceTelemetry(selectedInstanceId, { window }),
        ])
        setOverview(overviewData)
        setSourceSeries(sourceData.series)
        setInstanceOverview(detail.overview ?? null)
        setInstanceNodes(detail.latest_nodes ?? [])
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [selectedInstanceId, window])

  const handleDetect = async () => {
    if (selectedInstanceId === 'ALL') return
    setDetecting(true)
    try {
      await GenesisApi.runSourceWatch(selectedInstanceId)
      await load()
    } finally {
      setDetecting(false)
    }
  }

  const summary = overview?.summary
  const sourceLoadRows = overview?.source_load ?? []
  const nodeRows = selectedInstanceId === 'ALL' ? overview?.nodes ?? [] : instanceNodes

  const heatSeries = useMemo(
    () => [
      { name: 'HOT', value: sourceLoadRows.filter((item) => item.heat_level === 'HOT').length },
      { name: 'WARM', value: sourceLoadRows.filter((item) => item.heat_level === 'WARM').length },
      { name: 'COLD', value: sourceLoadRows.filter((item) => item.heat_level === 'COLD').length },
    ],
    [sourceLoadRows],
  )

  const loadTrend = metricPoints(sourceSeries, 'load_score')
  const scanTrend = metricPoints(sourceSeries, 'scan_duration_ms')
  const failureTrend = metricPoints(sourceSeries, 'failure_rate')
  const heatChartData = heatSeries.map((item) => ({
    sample_at: item.name,
    value: item.value,
    heat_level: item.name,
  }))

  return (
    <div className="space-y-6">
      <FabricPageHeader
        eyebrow="遥测中心"
        title="实例负载、吞吐与节点响应"
        description="查看当前项目的源级与节点级遥测。可以切换到单个实例，并直接对该实例执行检测。"
        actions={
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={window}
              onChange={(event) => setWindow(event.target.value as '24h' | '7d')}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
            >
              <option value="24h">最近 24 小时</option>
              <option value="7d">最近 7 天</option>
            </select>
            <button
              type="button"
              onClick={handleDetect}
              disabled={selectedInstanceId === 'ALL' || detecting}
              className="inline-flex items-center gap-2 rounded-[16px] border border-[var(--df-border)] bg-[var(--df-surface)] px-4 py-2 text-sm font-medium text-[var(--df-text)] hover:bg-[var(--df-surface-2)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <ScanSearch size={15} />
              {detecting ? '检测中…' : '检测当前实例'}
            </button>
            <button
              type="button"
              onClick={() => void load()}
              className="inline-flex items-center gap-2 rounded-[16px] border border-[var(--df-border)] bg-[var(--df-surface)] px-4 py-2 text-sm font-medium text-[var(--df-text)] hover:bg-[var(--df-surface-2)]"
            >
              <RefreshCw size={15} />
              刷新
            </button>
          </div>
        }
      />

      <div className="grid gap-4 md:grid-cols-4">
        <FabricStatCard label="实例数" value={summary?.instance_count ?? 0} />
        <FabricStatCard label="热点实例" value={summary?.hot_instances ?? 0} />
        <FabricStatCard label="待处理候选" value={summary?.open_candidates ?? 0} />
        <FabricStatCard label="待处理变化" value={summary?.open_changes ?? 0} />
      </div>

      <FabricSection
        title="实例切换"
        subtitle="按实例筛选遥测，并对指定实例执行检测。列表已改成固定高度滚动，不再无限拉长页面。"
      >
        <div className="grid gap-4 xl:grid-cols-[300px_1fr]">
          <div className="space-y-3 rounded-3xl border border-slate-200 bg-white p-4">
            <div className="relative">
              <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                value={instanceKeyword}
                onChange={(event) => setInstanceKeyword(event.target.value)}
                placeholder="搜索实例名、连接器、状态"
                className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2 pl-9 pr-3 text-sm text-slate-700 outline-none placeholder:text-slate-400"
              />
            </div>

            <button
              type="button"
              onClick={() => setSelectedInstanceId('ALL')}
              className={`flex w-full items-center justify-between rounded-2xl border px-4 py-3 text-left transition ${
                selectedInstanceId === 'ALL'
                  ? 'border-slate-900 bg-slate-900 text-white'
                  : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
              }`}
            >
              <div>
                <div className="font-medium">全部实例</div>
                <div className={`mt-1 text-sm ${selectedInstanceId === 'ALL' ? 'text-slate-300' : 'text-slate-500'}`}>
                  查看项目整体的源级和节点级遥测
                </div>
              </div>
            </button>

            <div className="max-h-[360px] space-y-2 overflow-y-auto pr-1">
              {filteredInstances.length === 0 ? (
                <FabricEmptyState message="没有匹配到实例。" />
              ) : (
                filteredInstances.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSelectedInstanceId(item.id)}
                    className={`flex w-full items-center justify-between rounded-2xl border px-4 py-3 text-left transition ${
                      selectedInstanceId === item.id
                        ? 'border-slate-900 bg-slate-900 text-white'
                        : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                    }`}
                  >
                    <div className="min-w-0">
                      <div className="truncate font-medium">{item.instance_name}</div>
                      <div className={`mt-1 truncate text-sm ${selectedInstanceId === item.id ? 'text-slate-300' : 'text-slate-500'}`}>
                        {item.connector_name} · 资产 {item.asset_count} · 估算行数 {item.row_count_estimate}
                      </div>
                    </div>
                    <div className="ml-3 flex shrink-0 items-center gap-2">
                      <FabricBadge value={item.heat_level} />
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>

          <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            {selectedInstance ? (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-400">当前实例</div>
                    <div className="mt-1 text-xl font-semibold text-slate-900">{selectedInstance.instance_name}</div>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-slate-500">
                      <FabricBadge value={selectedInstance.connector_name} />
                      <FabricBadge value={selectedInstance.heat_level} />
                      <FabricBadge value={selectedInstance.status} />
                    </div>
                  </div>
                  {instanceOverview ? (
                    <div className="grid gap-3 md:grid-cols-3">
                      <div className="rounded-2xl bg-slate-50 px-4 py-3">
                        <div className="text-[11px] uppercase tracking-[0.16em] text-slate-400">负载分数</div>
                        <div className="mt-1 text-lg font-semibold text-slate-900">{String(instanceOverview.load_score ?? 0)}</div>
                      </div>
                      <div className="rounded-2xl bg-slate-50 px-4 py-3">
                        <div className="text-[11px] uppercase tracking-[0.16em] text-slate-400">吞吐 MB/h</div>
                        <div className="mt-1 text-lg font-semibold text-slate-900">{String(instanceOverview.throughput_mb_per_hour ?? 0)}</div>
                      </div>
                      <div className="rounded-2xl bg-slate-50 px-4 py-3">
                        <div className="text-[11px] uppercase tracking-[0.16em] text-slate-400">扫描耗时 ms</div>
                        <div className="mt-1 text-lg font-semibold text-slate-900">{String(instanceOverview.scan_duration_ms ?? 0)}</div>
                      </div>
                    </div>
                  ) : null}
                </div>

                <div className="grid gap-3 md:grid-cols-3 text-sm text-slate-600">
                  <div className="rounded-2xl bg-slate-50 px-4 py-3">
                    <div className="text-[11px] uppercase tracking-[0.16em] text-slate-400">资产数</div>
                    <div className="mt-1 font-semibold text-slate-900">{selectedInstance.asset_count}</div>
                  </div>
                  <div className="rounded-2xl bg-slate-50 px-4 py-3">
                    <div className="text-[11px] uppercase tracking-[0.16em] text-slate-400">估算行数</div>
                    <div className="mt-1 font-semibold text-slate-900">{selectedInstance.row_count_estimate}</div>
                  </div>
                  <div className="rounded-2xl bg-slate-50 px-4 py-3">
                    <div className="text-[11px] uppercase tracking-[0.16em] text-slate-400">监听状态</div>
                    <div className="mt-1 font-semibold text-slate-900">{selectedInstance.last_watch_status || '未执行'}</div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="text-xs uppercase tracking-[0.16em] text-slate-400">当前视图</div>
                <div className="text-xl font-semibold text-slate-900">全部实例总览</div>
                <p className="text-sm leading-7 text-slate-500">
                  当前显示项目整体的源级负载、冷热分布和节点级遥测。选择左侧任一实例后，图表会自动切换为单实例视角。
                </p>
              </div>
            )}
          </div>
        </div>
      </FabricSection>

      <div className={`grid gap-6 ${selectedInstance ? '' : 'xl:grid-cols-[1.2fr_1fr]'}`}>
        <FabricSection
          title={selectedInstance ? '指定实例负载趋势' : '源级负载趋势'}
          subtitle={selectedInstance ? '只查看当前实例的负载、吞吐、扫描耗时与失败率。' : '查看项目内全部实例的源级负载与吞吐情况。'}
        >
          {loading ? (
            <FabricEmptyState message="正在加载源级遥测..." />
          ) : sourceLoadRows.length === 0 ? (
            <FabricEmptyState message="当前没有可用的源级遥测数据。" />
          ) : (
            <div className="space-y-5">
              <div className="h-72 rounded-2xl border border-slate-200 bg-white p-3">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={selectedInstance ? loadTrend : sourceLoadRows}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey={selectedInstance ? 'sample_at' : 'instance_name'} tick={{ fill: '#475569', fontSize: 12 }} />
                    <YAxis tick={{ fill: '#475569', fontSize: 12 }} />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="load_score" name="负载分数" stroke="#0f172a" strokeWidth={2} />
                    <Line type="monotone" dataKey="throughput_mb_per_hour" name="吞吐 MB/h" stroke="#2563eb" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <div className="h-64 rounded-2xl border border-slate-200 bg-white p-3">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={selectedInstance ? scanTrend : sourceLoadRows}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey={selectedInstance ? 'sample_at' : 'instance_name'} tick={{ fill: '#475569', fontSize: 12 }} />
                      <YAxis tick={{ fill: '#475569', fontSize: 12 }} />
                      <Tooltip />
                      <Bar dataKey="scan_duration_ms" name="扫描耗时(ms)" fill="#14b8a6" radius={[8, 8, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="h-64 rounded-2xl border border-slate-200 bg-white p-3">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={selectedInstance ? failureTrend : heatChartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="sample_at" tick={{ fill: '#475569', fontSize: 12 }} />
                      <YAxis tick={{ fill: '#475569', fontSize: 12 }} />
                      <Tooltip />
                      {selectedInstance ? (
                        <Bar dataKey="value" name="失败率" fill="#f97316" radius={[8, 8, 0, 0]} />
                      ) : (
                        <Bar dataKey="value" name="实例数量" radius={[8, 8, 0, 0]}>
                          {heatChartData.map((entry) => (
                            <Cell key={entry.sample_at} fill={HEAT_COLORS[entry.heat_level]} />
                          ))}
                        </Bar>
                      )}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          )}
        </FabricSection>

        {!selectedInstance ? (
          <FabricSection title="节点级遥测" subtitle="查看项目内节点 CPU、内存、磁盘吞吐和队列积压。">
            {loading ? (
              <FabricEmptyState message="正在加载节点遥测..." />
            ) : nodeRows.length === 0 ? (
              <FabricEmptyState message="当前没有可用的节点遥测数据。" />
            ) : (
              <div className="space-y-5">
                <div className="h-72 rounded-2xl border border-slate-200 bg-white p-3">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={nodeRows}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="node_name" tick={{ fill: '#475569', fontSize: 12 }} />
                      <YAxis tick={{ fill: '#475569', fontSize: 12 }} />
                      <Tooltip />
                      <Legend />
                      <Area type="monotone" dataKey="cpu_pct" name="CPU%" stroke="#8b5cf6" fill="#c4b5fd" />
                      <Area type="monotone" dataKey="memory_pct" name="内存%" stroke="#06b6d4" fill="#a5f3fc" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>

                <div className="space-y-3">
                  {nodeRows.map((item, index) => (
                    <div
                      key={String(item.scope_key ?? item.node_name ?? index)}
                      className="rounded-2xl border border-slate-200 bg-slate-50 p-4"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="inline-flex items-center gap-2 font-semibold text-slate-900">
                          <Server size={16} />
                          {String(item.node_name ?? item.scope_key ?? `node-${index + 1}`)}
                        </div>
                        {item.health ? <FabricBadge value={String(item.health)} /> : null}
                      </div>
                      <div className="mt-3 grid grid-cols-3 gap-3 text-sm text-slate-600">
                        <div>
                          <div className="text-xs uppercase tracking-[0.16em] text-slate-500">CPU</div>
                          <div className="mt-1 font-medium text-slate-900">{String(item.cpu_pct ?? 0)}%</div>
                        </div>
                        <div>
                          <div className="text-xs uppercase tracking-[0.16em] text-slate-500">内存</div>
                          <div className="mt-1 font-medium text-slate-900">{String(item.memory_pct ?? 0)}%</div>
                        </div>
                        <div>
                          <div className="text-xs uppercase tracking-[0.16em] text-slate-500">队列积压</div>
                          <div className="mt-1 font-medium text-slate-900">{String(item.queue_backlog ?? 0)}</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </FabricSection>
        ) : null}
      </div>
    </div>
  )
}
