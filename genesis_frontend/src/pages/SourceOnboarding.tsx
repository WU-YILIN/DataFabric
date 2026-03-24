import { useEffect, useMemo, useState } from 'react'
import { useRef } from 'react'
import {
  Activity,
  BadgePlus,
  BellRing,
  Boxes,
  Cable,
  Eye,
  FileSearch,
  Filter,
  LineChart as LineChartIcon,
  Loader2,
  Network,
  RefreshCw,
  Search,
  Server,
  Waves,
  X,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import {
  GenesisApi,
  type ConnectorDefinition,
  type ConnectorConfigField,
  type SourceAsset,
  type SourceCandidate,
  type SourceChangeEvent,
  type SourceField,
  type SourceFieldProfile,
  type SourceInstance,
  type SourceInstanceTelemetry,
  type SourceIntakePagedResponse,
  type SemanticCandidate,
  type SourceTelemetryOverview,
  type SourceTelemetryPoint,
  type SourceTelemetrySeriesResponse,
} from '../services/api'

const PAGE_SIZE = 12
const TAB_ITEMS = [
  { key: 'instances', label: '实例', icon: Server },
  { key: 'changes', label: '候选变化', icon: BellRing },
  { key: 'assets', label: '资产目录', icon: Boxes },
  { key: 'connectors', label: '连接器目录', icon: Cable },
  { key: 'telemetry', label: '遥测', icon: Waves },
] as const

type TabKey = (typeof TAB_ITEMS)[number]['key']
type DraftState = {
  instance_name: string
  memory_scope_default: string
  watch_enabled: boolean
  watch_interval_seconds: number
  config: Record<string, unknown>
}
type CreateState = { instance_name: string; connector_key: string; memory_scope_default: string; config: Record<string, unknown> }
const DEFAULT_CREATE_STATE: CreateState = { instance_name: '', connector_key: '', memory_scope_default: 'PRIVATE', config: {} }
const CREATE_STEPS = [
  { key: 1, label: '选择连接器', helper: '先确定实例类型和能力边界' },
  { key: 2, label: '填写配置', helper: '补齐连接、认证与发现范围' },
  { key: 3, label: '确认创建', helper: '检查写入范围与必填项' },
] as const
const WATCH_INTERVAL_OPTIONS = [
  { value: 60, label: '1 分钟' },
  { value: 300, label: '5 分钟' },
  { value: 900, label: '15 分钟' },
  { value: 1800, label: '30 分钟' },
  { value: 3600, label: '1 小时' },
] as const

function formatDate(value?: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

function formatNumber(value?: number | null) {
  return new Intl.NumberFormat('zh-CN').format(value ?? 0)
}

function formatBytes(value?: number | null) {
  const num = Number(value || 0)
  if (!Number.isFinite(num) || num <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let current = num
  let index = 0
  while (current >= 1024 && index < units.length - 1) {
    current /= 1024
    index += 1
  }
  return `${current.toFixed(current >= 100 || index === 0 ? 0 : 1)} ${units[index]}`
}

function memoryScopeLabel(value?: string | null) {
  return value === 'TENANT' ? '公共记忆' : '项目记忆'
}

function statusTone(status?: string | null) {
  const value = String(status || '').toUpperCase()
  if (value.includes('FAIL')) return 'bg-rose-50 text-rose-700 border-rose-200'
  if (value.includes('OPEN') || value.includes('DISCOVERED')) return 'bg-amber-50 text-amber-700 border-amber-200'
  if (value.includes('SHARED')) return 'bg-indigo-50 text-indigo-700 border-indigo-200'
  if (value.includes('SUCCESS') || value.includes('ACTIVE') || value.includes('PROMOTED') || value.includes('CONNECTED')) return 'bg-emerald-50 text-emerald-700 border-emerald-200'
  return 'bg-slate-100 text-slate-600 border-slate-200'
}

function heatTone(heat?: string | null) {
  const value = String(heat || '').toUpperCase()
  if (value === 'HOT') return 'bg-rose-50 text-rose-700 border-rose-200'
  if (value === 'WARM') return 'bg-amber-50 text-amber-700 border-amber-200'
  return 'bg-slate-100 text-slate-600 border-slate-200'
}

function normalizeSourceSeries(series: Record<string, SourceTelemetryPoint[]>) {
  const merged = new Map<string, { sample_at: string; load_score: number; throughput_mb_per_hour: number; scan_duration_ms: number; failure_rate: number; count: number }>()
  Object.values(series || {}).forEach((points) => {
    points.forEach((point) => {
      if (!point.sample_at) return
      const current = merged.get(point.sample_at) || { sample_at: point.sample_at, load_score: 0, throughput_mb_per_hour: 0, scan_duration_ms: 0, failure_rate: 0, count: 0 }
      current.load_score += Number(point.load_score || 0)
      current.throughput_mb_per_hour += Number(point.throughput_mb_per_hour || 0)
      current.scan_duration_ms += Number(point.scan_duration_ms || 0)
      current.failure_rate += Number(point.failure_rate || 0)
      current.count += 1
      merged.set(point.sample_at, current)
    })
  })
  return Array.from(merged.values()).sort((a, b) => a.sample_at.localeCompare(b.sample_at)).map((item) => ({
    sample_at: item.sample_at.slice(5, 16).replace('T', ' '),
    load_score: Number((item.load_score / Math.max(item.count, 1)).toFixed(2)),
    throughput_mb_per_hour: Number(item.throughput_mb_per_hour.toFixed(2)),
    scan_duration_ms: Math.round(item.scan_duration_ms / Math.max(item.count, 1)),
    failure_rate: Number((item.failure_rate / Math.max(item.count, 1)).toFixed(4)),
  }))
}

function normalizeNodeSeries(series: Record<string, SourceTelemetryPoint[]>) {
  const merged = new Map<string, { sample_at: string; cpu_pct: number; memory_pct: number; disk_throughput_mb: number; network_throughput_mb: number; queue_backlog: number; count: number }>()
  Object.values(series || {}).forEach((points) => {
    points.forEach((point) => {
      if (!point.sample_at) return
      const current = merged.get(point.sample_at) || { sample_at: point.sample_at, cpu_pct: 0, memory_pct: 0, disk_throughput_mb: 0, network_throughput_mb: 0, queue_backlog: 0, count: 0 }
      current.cpu_pct += Number(point.cpu_pct || 0)
      current.memory_pct += Number(point.memory_pct || 0)
      current.disk_throughput_mb += Number(point.disk_throughput_mb || 0)
      current.network_throughput_mb += Number(point.network_throughput_mb || 0)
      current.queue_backlog += Number(point.queue_backlog || 0)
      current.count += 1
      merged.set(point.sample_at, current)
    })
  })
  return Array.from(merged.values()).sort((a, b) => a.sample_at.localeCompare(b.sample_at)).map((item) => ({
    sample_at: item.sample_at.slice(5, 16).replace('T', ' '),
    cpu_pct: Number((item.cpu_pct / Math.max(item.count, 1)).toFixed(2)),
    memory_pct: Number((item.memory_pct / Math.max(item.count, 1)).toFixed(2)),
    disk_throughput_mb: Number((item.disk_throughput_mb / Math.max(item.count, 1)).toFixed(2)),
    network_throughput_mb: Number((item.network_throughput_mb / Math.max(item.count, 1)).toFixed(2)),
    queue_backlog: Math.round(item.queue_backlog / Math.max(item.count, 1)),
  }))
}

function buildHeatDistribution(items: Array<Record<string, unknown>>) {
  const counts = { HOT: 0, WARM: 0, COLD: 0 }
  items.forEach((item) => {
    const heat = String(item.heat_level || 'COLD').toUpperCase()
    if (heat === 'HOT' || heat === 'WARM' || heat === 'COLD') counts[heat] += 1
  })
  return [
    { name: 'HOT', value: counts.HOT, fill: '#fb7185' },
    { name: 'WARM', value: counts.WARM, fill: '#f59e0b' },
    { name: 'COLD', value: counts.COLD, fill: '#94a3b8' },
  ]
}

function Pager({ total, page, totalPages, onChange }: { total: number; page: number; totalPages: number; onChange: (page: number) => void }) {
  return (
    <div className="mt-4 flex items-center justify-between text-sm text-slate-500">
      <div>共 {formatNumber(total)} 条</div>
      <div className="flex items-center gap-2">
        <button type="button" disabled={page <= 1} onClick={() => onChange(Math.max(page - 1, 1))} className="rounded-xl border border-slate-200 px-3 py-1.5 disabled:cursor-not-allowed disabled:opacity-40">上一页</button>
        <div className="rounded-xl bg-slate-50 px-3 py-1.5">{page}/{totalPages}</div>
        <button type="button" disabled={page >= totalPages} onClick={() => onChange(page + 1)} className="rounded-xl border border-slate-200 px-3 py-1.5 disabled:cursor-not-allowed disabled:opacity-40">下一页</button>
      </div>
    </div>
  )
}

function StatCard({ label, value, helper, icon: Icon }: { label: string; value: string | number; helper?: string; icon: any }) {
  return <div className="min-w-0 rounded-[24px] border border-[var(--df-border)] bg-white p-4 shadow-sm"><div className="flex items-start justify-between gap-3"><div className="min-w-0 flex-1"><div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--df-text-soft)]">{label}</div><div className="df-display mt-2 text-2xl font-semibold tracking-tight text-[var(--df-text)]">{value}</div>{helper ? <div className="mt-2 line-clamp-2 text-xs leading-5 text-[var(--df-text-muted)]">{helper}</div> : null}</div><div className="shrink-0 rounded-2xl border border-[var(--df-border)] bg-[var(--df-surface-2)] p-3 text-[var(--df-ink)]"><Icon size={18} /></div></div></div>
}

function Section({ title, subtitle, actions, children }: { title: string; subtitle?: string; actions?: React.ReactNode; children: React.ReactNode }) {
  return <section className="df-surface min-w-0 p-6"><div className="mb-4 flex items-start justify-between gap-4"><div className="min-w-0"><h3 className="df-display text-xl font-semibold tracking-tight text-[var(--df-text)]">{title}</h3>{subtitle ? <p className="mt-1 text-sm text-[var(--df-text-muted)]">{subtitle}</p> : null}</div>{actions}</div>{children}</section>
}

function Badge({ label, tone }: { label: string; tone: string }) {
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${tone}`}>{label}</span>
}

function SafeResponsiveChart({
  heightClassName,
  minHeight,
  emptyText = '暂无图表数据',
  dataPoints,
  children,
}: {
  heightClassName: string
  minHeight: number
  emptyText?: string
  dataPoints?: number
  children: React.ReactNode
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const element = containerRef.current
    if (!element) return

    const update = () => {
      const rect = element.getBoundingClientRect()
      setReady(rect.width > 0 && rect.height > 0)
    }

    update()
    const observer = new ResizeObserver(() => update())
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={containerRef} className={`${heightClassName} min-w-0`}>
      {!ready || (typeof dataPoints === 'number' && dataPoints === 0) ? (
        <div className="flex h-full items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-500">
          {emptyText}
        </div>
      ) : (
        <ResponsiveContainer width="100%" height="100%" minWidth={240} minHeight={minHeight}>
          {children}
        </ResponsiveContainer>
      )}
    </div>
  )
}

function MeasuredChart({
  heightClassName,
  minHeight,
  emptyText = '暂无图表数据',
  children,
}: {
  heightClassName: string
  minHeight: number
  emptyText?: string
  children: (size: { width: number; height: number }) => React.ReactNode
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })

  useEffect(() => {
    const element = containerRef.current
    if (!element) return

    const update = () => {
      const rect = element.getBoundingClientRect()
      setSize({
        width: Math.max(Math.floor(rect.width), 0),
        height: Math.max(Math.floor(rect.height), minHeight),
      })
    }

    update()
    const observer = new ResizeObserver(() => update())
    observer.observe(element)
    return () => observer.disconnect()
  }, [minHeight])

  return (
    <div ref={containerRef} className={`${heightClassName} min-w-0`}>
      {size.width <= 0 ? (
        <div className="flex h-full items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-500">
          {emptyText}
        </div>
      ) : (
        children(size)
      )}
    </div>
  )
}

function getCreateFieldGroup(field: ConnectorConfigField) {
  const key = field.key.toLowerCase()
  if (key.includes('password') || key.includes('secret') || key.includes('access_key') || key.includes('username') || key.includes('token') || key.includes('uri')) return '认证信息'
  if (key.includes('schema') || key.includes('prefix') || key.includes('bucket') || key.includes('database') || key.includes('namespace') || key.includes('topic') || key.includes('path')) return '发现范围'
  return '连接信息'
}

function getCreateFieldValue(field: ConnectorConfigField, value: CreateState) {
  return String(value.config[field.key] ?? field.default ?? '')
}

function getCreateFieldHint(field: ConnectorConfigField) {
  const key = field.key.toLowerCase()
  if (key.includes('host') || key.includes('endpoint')) return '填写实例访问地址或服务端点。'
  if (key.includes('port')) return '使用数据源实例对外提供的监听端口。'
  if (key.includes('database') || key.includes('schema') || key.includes('namespace')) return '限定本次发现的默认范围，后续仍可在实例详情中调整。'
  if (key.includes('bucket') || key.includes('prefix') || key.includes('path')) return '用于限定对象存储或文件型数据源的发现范围。'
  if (key.includes('username') || key.includes('access_key')) return '填写具备只读发现权限的访问账号。'
  if (key.includes('password') || key.includes('secret') || key.includes('token')) return '建议使用具备最小权限的凭证。'
  if (key.includes('bootstrap') || key.includes('uri')) return '使用实例的标准连接串或集群入口地址。'
  return '该字段将用于测试连接、执行发现和实例监听。'
}

function fieldSelectOptions(field: ConnectorConfigField) {
  if (field.key === 'has_header') {
    return [
      { value: 'true', label: '是' },
      { value: 'false', label: '否' },
    ]
  }
  if (field.key === 'memory_scope_default') {
    return [
      { value: 'PRIVATE', label: '项目记忆' },
      { value: 'TENANT', label: '公共记忆' },
    ]
  }
  return []
}

function CreateInstanceModal({ open, connectors, value, onChange, onClose, onSubmit, submitting }: { open: boolean; connectors: ConnectorDefinition[]; value: CreateState; onChange: (next: CreateState) => void; onClose: () => void; onSubmit: () => void; submitting: boolean }) {
  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [connectorQuery, setConnectorQuery] = useState('')
  const [connectorCategoryFilter, setConnectorCategoryFilter] = useState('ALL')
  const connector = connectors.find((item) => item.connector_key === value.connector_key) || null
  const configGroups = useMemo(() => {
    const grouped = new Map<string, ConnectorConfigField[]>()
    ;(connector?.config_schema || []).forEach((field) => {
      if (field.key === 'memory_scope_default') return
      const group = getCreateFieldGroup(field)
      const fields = grouped.get(group) || []
      fields.push(field)
      grouped.set(group, fields)
    })
    return Array.from(grouped.entries())
  }, [connector])
  const requiredFields = useMemo(() => (connector?.config_schema || []).filter((field) => field.required && field.key !== 'memory_scope_default'), [connector])
  const missingFields = useMemo(
    () =>
      requiredFields.filter((field) => {
        const raw = value.config[field.key]
        if (field.type === 'number') return raw === null || raw === undefined || String(raw) === ''
        return !String(raw ?? '').trim()
      }),
    [requiredFields, value.config],
  )
  const canMoveToConfig = Boolean(value.connector_key)
  const canMoveToReview = Boolean(value.instance_name.trim()) && missingFields.length === 0
  const selectedCategoryCount = useMemo(
    () => new Set((connector?.config_schema || []).filter((field) => field.key !== 'memory_scope_default').map((field) => getCreateFieldGroup(field))).size,
    [connector],
  )
  const connectorCategories = useMemo(() => ['ALL', ...Array.from(new Set(connectors.map((item) => item.category)))], [connectors])
  const visibleConnectors = useMemo(
    () =>
      connectors.filter((item) => {
        const matchesCategory = connectorCategoryFilter === 'ALL' || item.category === connectorCategoryFilter
        const keyword = connectorQuery.trim().toLowerCase()
        const matchesQuery =
          !keyword ||
          item.display_name.toLowerCase().includes(keyword) ||
          item.category.toLowerCase().includes(keyword) ||
          item.runtime_family.toLowerCase().includes(keyword) ||
          item.connector_key.toLowerCase().includes(keyword)
        return matchesCategory && matchesQuery
      }),
    [connectors, connectorCategoryFilter, connectorQuery],
  )

  useEffect(() => {
    if (!open || value.connector_key || connectors.length === 0) return
    const firstActive = connectors.find((item) => item.status === 'ACTIVE') || connectors[0]
    const nextConfig: Record<string, unknown> = {}
    firstActive.config_schema.forEach((field) => {
      nextConfig[field.key] = field.default ?? ''
    })
    nextConfig.memory_scope_default = nextConfig.memory_scope_default || 'PRIVATE'
    onChange({ instance_name: '', connector_key: firstActive.connector_key, memory_scope_default: String(nextConfig.memory_scope_default), config: nextConfig })
  }, [open, connectors, value.connector_key, onChange])

  useEffect(() => {
    if (open) {
      setStep(1)
      setConnectorQuery('')
      setConnectorCategoryFilter('ALL')
    }
  }, [open])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/40 p-6">
      <div className="w-full max-w-6xl rounded-[28px] border border-slate-200 bg-white p-6 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500"><BadgePlus size={14} />新增实例</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">创建数据源实例</h2>
            <p className="mt-2 text-sm text-slate-500">按步骤完成连接器选择、连接配置和创建确认。默认写入项目记忆，公共记忆需要在候选变化中确认提升。</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600 hover:bg-slate-100">关闭</button>
        </div>

        <div className="mt-6 grid gap-3 rounded-3xl border border-slate-200 bg-slate-50 p-4 md:grid-cols-3">
          {CREATE_STEPS.map((item) => {
            const active = step === item.key
            const completed = step > item.key
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => {
                  if (item.key === 2 && !canMoveToConfig) return
                  if (item.key === 3 && !canMoveToReview) return
                  setStep(item.key)
                }}
                className={`rounded-2xl border px-4 py-3 text-left transition ${active ? 'border-slate-900 bg-white shadow-sm' : completed ? 'border-emerald-200 bg-emerald-50' : 'border-slate-200 bg-white/70'}`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-semibold text-slate-900">{item.label}</div>
                  <div className={`inline-flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${active ? 'bg-slate-900 text-white' : completed ? 'bg-emerald-600 text-white' : 'bg-slate-200 text-slate-600'}`}>{item.key}</div>
                </div>
                <div className="mt-1 text-xs text-slate-500">{item.helper}</div>
              </button>
            )
          })}
        </div>

        <div className="mt-6 grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_320px]">
          <div className="space-y-4">
            {step === 1 ? (
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="text-sm font-semibold text-slate-900">选择连接器</div>
                <div className="mt-1 text-sm text-slate-500">先确定实例类型。创建之后仍可在详情页修改配置、测试连接并执行发现或监听。</div>
                <div className="mt-4 space-y-3">
                  <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_220px]">
                    <div className="relative">
                      <Search size={15} className="absolute left-3 top-3 text-slate-400" />
                      <input value={connectorQuery} onChange={(event) => setConnectorQuery(event.target.value)} placeholder="搜索连接器名称、分类或运行时族" className="w-full rounded-2xl border border-slate-200 bg-white px-10 py-2.5 text-sm text-slate-700 outline-none" />
                    </div>
                    <select value={connectorCategoryFilter} onChange={(event) => setConnectorCategoryFilter(event.target.value)} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700">
                      {connectorCategories.map((item) => <option key={item} value={item}>{item === 'ALL' ? '全部分类' : item}</option>)}
                    </select>
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs text-slate-500">
                    <span>共 {visibleConnectors.length} 个连接器</span>
                    <span>·</span>
                    <span>已激活 {visibleConnectors.filter((item) => item.status === 'ACTIVE').length} 个</span>
                  </div>
                </div>
                <div className="mt-4 rounded-2xl border border-slate-200 bg-white">
                  {visibleConnectors.length === 0 ? (
                    <div className="px-4 py-10 text-center text-sm text-slate-500">没有匹配的连接器，请调整关键词或分类。</div>
                  ) : (
                    <div className="max-h-[420px] overflow-auto">
                      {visibleConnectors.map((item, index) => {
                        const active = item.connector_key === value.connector_key
                        return (
                          <button
                            key={item.connector_key}
                            type="button"
                            onClick={() => {
                              const nextConfig: Record<string, unknown> = {}
                              item.config_schema.forEach((field) => {
                                nextConfig[field.key] = field.default ?? ''
                              })
                              nextConfig.memory_scope_default = nextConfig.memory_scope_default || 'PRIVATE'
                              onChange({ instance_name: '', connector_key: item.connector_key, memory_scope_default: String(nextConfig.memory_scope_default), config: nextConfig })
                            }}
                            className={`flex w-full items-center justify-between gap-4 px-4 py-3 text-left transition ${index > 0 ? 'border-t border-slate-100' : ''} ${active ? 'bg-slate-900 text-white' : 'hover:bg-slate-50'}`}
                          >
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2">
                                <div className={`truncate text-sm font-semibold ${active ? 'text-white' : 'text-slate-900'}`}>{item.display_name}</div>
                                <span className={`rounded-full px-2 py-0.5 text-[10px] ${active ? 'bg-white/10 text-slate-200' : 'bg-slate-100 text-slate-600'}`}>{item.category}</span>
                              </div>
                              <div className={`mt-1 truncate text-xs ${active ? 'text-slate-300' : 'text-slate-500'}`}>{item.runtime_family} · {item.capabilities.length} 项能力 · {item.auth_modes.length} 种认证</div>
                            </div>
                            <Badge label={item.status} tone={active ? 'bg-white/10 text-white border-white/20' : statusTone(item.status)} />
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>
              </div>
            ) : null}

            {step === 2 ? (
              <div className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-700">实例名称</label>
                    <input value={value.instance_name} onChange={(event) => onChange({ ...value, instance_name: event.target.value })} className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none" placeholder="例如：华东业务 MySQL 实例" />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-700">默认记忆范围</label>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <button type="button" onClick={() => onChange({ ...value, memory_scope_default: 'PRIVATE', config: { ...value.config, memory_scope_default: 'PRIVATE' } })} className={`rounded-2xl border p-3 text-left ${value.memory_scope_default === 'PRIVATE' ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-700'}`}>
                        <div className="font-medium">项目记忆</div>
                        <div className={`mt-1 text-xs ${value.memory_scope_default === 'PRIVATE' ? 'text-slate-300' : 'text-slate-500'}`}>仅当前项目可见</div>
                      </button>
                      <button type="button" onClick={() => onChange({ ...value, memory_scope_default: 'TENANT', config: { ...value.config, memory_scope_default: 'TENANT' } })} className={`rounded-2xl border p-3 text-left ${value.memory_scope_default === 'TENANT' ? 'border-indigo-700 bg-indigo-700 text-white' : 'border-slate-200 bg-white text-slate-700'}`}>
                        <div className="font-medium">公共记忆</div>
                        <div className={`mt-1 text-xs ${value.memory_scope_default === 'TENANT' ? 'text-indigo-100' : 'text-slate-500'}`}>写入同租户共享记忆</div>
                      </button>
                    </div>
                  </div>
                </div>

                {configGroups.map(([group, fields]) => (
                  <div key={group} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="text-sm font-semibold text-slate-900">{group}</div>
                    <div className="mt-3 grid gap-4 md:grid-cols-2">
                      {fields.map((field) => {
                        const inputType = field.type === 'password' ? 'password' : field.type === 'number' ? 'number' : 'text'
                        const selectOptions = field.type === 'select' ? fieldSelectOptions(field) : []
                        return (
                          <div key={field.key} className="space-y-2">
                            <label className="text-sm font-medium text-slate-700">
                              {field.label}
                              {field.required ? <span className="ml-1 text-rose-500">*</span> : null}
                            </label>
                            {field.type === 'select' ? (
                              <select
                                value={getCreateFieldValue(field, value)}
                                onChange={(event) =>
                                  onChange({
                                    ...value,
                                    config: {
                                      ...value.config,
                                      [field.key]: event.target.value,
                                    },
                                  })
                                }
                                className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none"
                              >
                                {selectOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                              </select>
                            ) : (
                              <input
                                type={inputType}
                                value={getCreateFieldValue(field, value)}
                                onChange={(event) =>
                                  onChange({
                                    ...value,
                                    config: {
                                      ...value.config,
                                      [field.key]: field.type === 'number' ? Number(event.target.value) : event.target.value,
                                    },
                                  })
                                }
                                className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none"
                                placeholder={field.placeholder || ''}
                              />
                            )}
                            <div className="text-xs text-slate-500">{getCreateFieldHint(field)}</div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            ) : null}

            {step === 3 ? (
              <div className="space-y-4">
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="text-sm font-semibold text-slate-900">创建确认</div>
                  <div className="mt-2 text-sm text-slate-600">创建后该实例会进入实例列表。后续发现结果先进入候选区，再决定是否纳入项目记忆或公共记忆。</div>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">实例信息</div>
                    <div className="mt-3 space-y-2 text-sm text-slate-700">
                      <div>实例名称：<span className="font-medium text-slate-900">{value.instance_name || '-'}</span></div>
                      <div>连接器：<span className="font-medium text-slate-900">{connector?.display_name || '-'}</span></div>
                      <div>运行时族：<span className="font-medium text-slate-900">{connector?.runtime_family || '-'}</span></div>
                      <div>默认记忆：<span className="font-medium text-slate-900">{memoryScopeLabel(value.memory_scope_default)}</span></div>
                    </div>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">校验结果</div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Badge label={missingFields.length === 0 ? '配置完整' : `缺少 ${missingFields.length} 个必填项`} tone={missingFields.length === 0 ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-amber-50 text-amber-700 border-amber-200'} />
                      <Badge label={`${selectedCategoryCount} 组配置`} tone="bg-slate-100 text-slate-700 border-slate-200" />
                      <Badge label={`${connector?.capabilities.length || 0} 项能力`} tone="bg-slate-100 text-slate-700 border-slate-200" />
                    </div>
                    {missingFields.length > 0 ? (
                      <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                        <div className="font-medium">仍需补齐以下字段</div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {missingFields.map((field) => <span key={field.key} className="rounded-full border border-amber-200 bg-white px-2.5 py-1 text-xs">{field.label}</span>)}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-950 p-4">
                  <div className="text-sm font-semibold text-slate-100">将要写入的配置</div>
                  <pre className="mt-3 max-h-64 overflow-auto text-xs text-slate-100">{JSON.stringify({ instance_name: value.instance_name, connector_key: value.connector_key, memory_scope_default: value.memory_scope_default, config: value.config }, null, 2)}</pre>
                </div>
              </div>
            ) : null}
          </div>

          <div className="space-y-4">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-sm font-semibold text-slate-900">当前选择</div>
              {connector ? (
                <div className="mt-3 space-y-3">
                  <div>
                    <div className="text-base font-semibold text-slate-900">{connector.display_name}</div>
                    <div className="mt-1 text-xs text-slate-500">{connector.category} · {connector.runtime_family}</div>
                  </div>
                  <div className="text-sm text-slate-600">{connector.description || '暂无说明'}</div>
                  <div className="flex flex-wrap gap-2">
                    <Badge label={connector.status} tone={statusTone(connector.status)} />
                    <Badge label={`${connector.auth_modes.length} 种认证`} tone="bg-slate-100 text-slate-700 border-slate-200" />
                    <Badge label={`${connector.capabilities.length} 项能力`} tone="bg-slate-100 text-slate-700 border-slate-200" />
                  </div>
                </div>
              ) : <div className="mt-3 text-sm text-slate-500">请先选择一个连接器。</div>}
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="text-sm font-semibold text-slate-900">能力与写入说明</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {(connector?.capabilities || []).map((item) => <span key={item} className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-600">{item}</span>)}
              </div>
              <div className="mt-4 rounded-2xl border border-indigo-200 bg-indigo-50 p-3 text-sm text-indigo-800">
                <div className="font-medium">创建后会发生什么</div>
                <ul className="mt-2 space-y-1 text-xs leading-5">
                  <li>1. 实例进入“实例列表”，可继续测试连接、执行发现与监听。</li>
                  <li>2. 结构变化默认进入“候选变化”，不会直接正式纳管。</li>
                  <li>3. 候选确认后才会写入项目记忆或公共记忆。</li>
                </ul>
              </div>
            </div>

            <div className="flex items-center justify-between gap-3">
              <button type="button" onClick={onClose} className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50">取消</button>
              <div className="flex items-center gap-3">
                {step > 1 ? <button type="button" onClick={() => setStep((current) => Math.max(1, current - 1) as 1 | 2 | 3)} className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50">上一步</button> : null}
                {step < 3 ? (
                  <button type="button" onClick={() => setStep((current) => Math.min(3, current + 1) as 1 | 2 | 3)} disabled={(step === 1 && !canMoveToConfig) || (step === 2 && !canMoveToReview)} className="rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50">下一步</button>
                ) : (
                  <button type="button" onClick={onSubmit} disabled={submitting || !canMoveToReview} className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50">{submitting ? <Loader2 size={15} className="animate-spin" /> : <BadgePlus size={15} />}创建实例</button>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function SourceOnboarding() {
  const [activeTab, setActiveTab] = useState<TabKey>('instances')
  const [connectors, setConnectors] = useState<ConnectorDefinition[]>([])
  const [connectorCategory, setConnectorCategory] = useState('ALL')
  const [loading, setLoading] = useState(true)
  const [instances, setInstances] = useState<SourceIntakePagedResponse<SourceInstance> | null>(null)
  const [instanceQuery, setInstanceQuery] = useState('')
  const [instanceConnector, setInstanceConnector] = useState('ALL')
  const [instanceStatus, setInstanceStatus] = useState('ALL')
  const [instanceHeat, setInstanceHeat] = useState('ALL')
  const [instancePage, setInstancePage] = useState(1)
  const [selectedInstanceId, setSelectedInstanceId] = useState<number | null>(null)
  const [selectedInstance, setSelectedInstance] = useState<SourceInstance | null>(null)
  const [instanceDraft, setInstanceDraft] = useState<DraftState>({
    instance_name: '',
    memory_scope_default: 'PRIVATE',
    watch_enabled: false,
    watch_interval_seconds: 300,
    config: {},
  })
  const [instanceTelemetry, setInstanceTelemetry] = useState<SourceInstanceTelemetry | null>(null)
  const [instanceAssets, setInstanceAssets] = useState<SourceIntakePagedResponse<SourceAsset> | null>(null)
  const [changes, setChanges] = useState<SourceIntakePagedResponse<SourceChangeEvent> | null>(null)
  const [changeQuery, setChangeQuery] = useState('')
  const [changeStatus, setChangeStatus] = useState('ALL')
  const [changeSeverity, setChangeSeverity] = useState('ALL')
  const [changePage, setChangePage] = useState(1)
  const [candidates, setCandidates] = useState<SourceIntakePagedResponse<SourceCandidate> | null>(null)
  const [candidateQuery, setCandidateQuery] = useState('')
  const [candidateStatus, setCandidateStatus] = useState('ALL')
  const [candidateType, setCandidateType] = useState('ALL')
  const [candidateScope, setCandidateScope] = useState('ALL')
  const [candidatePage, setCandidatePage] = useState(1)
  const [assets, setAssets] = useState<SourceIntakePagedResponse<SourceAsset> | null>(null)
  const [assetQuery, setAssetQuery] = useState('')
  const [assetType, setAssetType] = useState('ALL')
  const [assetHeat, setAssetHeat] = useState('ALL')
  const [assetStatus, setAssetStatus] = useState('ALL')
  const [assetPage, setAssetPage] = useState(1)
  const [selectedAsset, setSelectedAsset] = useState<SourceAsset | null>(null)
  const [assetFields, setAssetFields] = useState<SourceIntakePagedResponse<SourceField> | null>(null)
  const [fieldQuery, setFieldQuery] = useState('')
  const [fieldStatus, setFieldStatus] = useState('ALL')
  const [fieldCandidateType, setFieldCandidateType] = useState('ALL')
  const [fieldPage, setFieldPage] = useState(1)
  const [selectedFieldId, setSelectedFieldId] = useState<number | null>(null)
  const [selectedField, setSelectedField] = useState<SourceField | null>(null)
  const [fieldProfiles, setFieldProfiles] = useState<SourceFieldProfile[]>([])
  const [fieldCandidates, setFieldCandidates] = useState<SemanticCandidate[]>([])
  const [telemetryOverview, setTelemetryOverview] = useState<SourceTelemetryOverview | null>(null)
  const [sourceTelemetry, setSourceTelemetry] = useState<SourceTelemetrySeriesResponse | null>(null)
  const [nodeTelemetry, setNodeTelemetry] = useState<SourceTelemetrySeriesResponse | null>(null)
  const [telemetryWindow, setTelemetryWindow] = useState<'24h' | '7d'>('24h')
  const [createOpen, setCreateOpen] = useState(false)
  const [createState, setCreateState] = useState<CreateState>(DEFAULT_CREATE_STATE)
  const [submittingCreate, setSubmittingCreate] = useState(false)
  const [savingInstance, setSavingInstance] = useState(false)
  const [runningAction, setRunningAction] = useState<string | null>(null)

  const loadConnectors = async () => {
    const data = await GenesisApi.listSourceIntakeConnectors()
    setConnectors(data.items)
  }

  const loadInstances = async () => {
    const data = await GenesisApi.listSourceInstances({ q: instanceQuery || undefined, connector_key: instanceConnector === 'ALL' ? undefined : instanceConnector, status: instanceStatus === 'ALL' ? undefined : instanceStatus, heat: instanceHeat === 'ALL' ? undefined : instanceHeat, page: instancePage, page_size: PAGE_SIZE })
    setInstances(data)
    if (!selectedInstanceId || !data.items.some((item) => item.id === selectedInstanceId)) setSelectedInstanceId(data.items[0]?.id ?? null)
  }

  const loadSelectedInstance = async (instanceId: number) => {
    const [instance, telemetry, previewAssets] = await Promise.all([GenesisApi.getSourceInstance(instanceId), GenesisApi.getInstanceTelemetry(instanceId, { window: telemetryWindow }), GenesisApi.listInstanceAssets(instanceId, { page: 1, page_size: 6 })])
    setSelectedInstance(instance)
    setInstanceDraft({
      instance_name: instance.instance_name,
      memory_scope_default: instance.memory_scope_default || 'PRIVATE',
      watch_enabled: Boolean(instance.watch_enabled),
      watch_interval_seconds: Number(instance.watch_interval_seconds || 300),
      config: { ...(instance.config || {}) },
    })
    setInstanceTelemetry(telemetry)
    setInstanceAssets(previewAssets)
  }

  const loadChanges = async () => setChanges(await GenesisApi.listSourceChangeEvents({ q: changeQuery || undefined, status: changeStatus === 'ALL' ? undefined : changeStatus, severity: changeSeverity === 'ALL' ? undefined : changeSeverity, page: changePage, page_size: PAGE_SIZE }))
  const loadCandidates = async () => setCandidates(await GenesisApi.listSourceCandidates({ q: candidateQuery || undefined, status: candidateStatus === 'ALL' ? undefined : candidateStatus, candidate_type: candidateType === 'ALL' ? undefined : candidateType, memory_scope_target: candidateScope === 'ALL' ? undefined : candidateScope, page: candidatePage, page_size: PAGE_SIZE }))
  const loadAssets = async () => {
    const data = await GenesisApi.listSourceAssets({ q: assetQuery || undefined, asset_type: assetType === 'ALL' ? undefined : assetType, heat: assetHeat === 'ALL' ? undefined : assetHeat, status: assetStatus === 'ALL' ? undefined : assetStatus, page: assetPage, page_size: PAGE_SIZE })
    setAssets(data)
    if (!selectedAsset || !data.items.some((item) => item.id === selectedAsset.id)) setSelectedAsset(data.items[0] ?? null)
  }
  const loadAssetFields = async (assetId: number) => {
    const data = await GenesisApi.listSourceAssetFields(assetId, {
      q: fieldQuery || undefined,
      status: fieldStatus === 'ALL' ? undefined : fieldStatus,
      candidate_type: fieldCandidateType === 'ALL' ? undefined : fieldCandidateType,
      page: fieldPage,
      page_size: PAGE_SIZE,
    })
    setAssetFields(data)
    const nextFieldId = selectedFieldId && data.items.some((item) => item.id === selectedFieldId) ? selectedFieldId : data.items[0]?.id ?? null
    setSelectedFieldId(nextFieldId)
  }
  const loadFieldDetail = async (fieldId: number) => {
    const [field, profiles, candidates] = await Promise.all([
      GenesisApi.getSourceField(fieldId),
      GenesisApi.getSourceFieldProfiles(fieldId),
      GenesisApi.getSourceFieldCandidates(fieldId),
    ])
    setSelectedField(field)
    setFieldProfiles(profiles)
    setFieldCandidates(candidates)
  }
  const loadTelemetry = async () => {
    const [overview, sourceSeries, nodeSeries] = await Promise.all([GenesisApi.getSourceTelemetryOverview(), GenesisApi.getSourceTelemetrySeries({ window: telemetryWindow }), GenesisApi.getNodeTelemetrySeries({ window: telemetryWindow })])
    setTelemetryOverview(overview)
    setSourceTelemetry(sourceSeries)
    setNodeTelemetry(nodeSeries)
  }

  useEffect(() => { const run = async () => { setLoading(true); try { await Promise.all([loadConnectors(), loadInstances(), loadChanges(), loadCandidates(), loadAssets(), loadTelemetry()]) } finally { setLoading(false) } }; void run() }, [])
  useEffect(() => { void loadInstances() }, [instanceQuery, instanceConnector, instanceStatus, instanceHeat, instancePage])
  useEffect(() => { if (!selectedInstanceId) { setSelectedInstance(null); setInstanceTelemetry(null); setInstanceAssets(null); return }; void loadSelectedInstance(selectedInstanceId) }, [selectedInstanceId, telemetryWindow])
  useEffect(() => { void loadChanges() }, [changeQuery, changeStatus, changeSeverity, changePage])
  useEffect(() => { void loadCandidates() }, [candidateQuery, candidateStatus, candidateType, candidateScope, candidatePage])
  useEffect(() => { void loadAssets() }, [assetQuery, assetType, assetHeat, assetStatus, assetPage])
  useEffect(() => {
    if (!selectedAsset?.id) {
      setAssetFields(null)
      setSelectedFieldId(null)
      setSelectedField(null)
      setFieldProfiles([])
      setFieldCandidates([])
      return
    }
    void loadAssetFields(selectedAsset.id)
  }, [selectedAsset?.id, fieldQuery, fieldStatus, fieldCandidateType, fieldPage])
  useEffect(() => {
    if (!selectedFieldId) {
      setSelectedField(null)
      setFieldProfiles([])
      setFieldCandidates([])
      return
    }
    void loadFieldDetail(selectedFieldId)
  }, [selectedFieldId])
  useEffect(() => { void loadTelemetry() }, [telemetryWindow])

  const groupedConnectors = useMemo(() => {
    const map = new Map<string, ConnectorDefinition[]>()
    connectors.forEach((item) => {
      if (connectorCategory !== 'ALL' && item.category !== connectorCategory) return
      const group = map.get(item.category) || []
      group.push(item)
      map.set(item.category, group)
    })
    return Array.from(map.entries())
  }, [connectors, connectorCategory])
  const selectedConnector = useMemo(() => connectors.find((item) => item.connector_key === selectedInstance?.connector_key) || null, [connectors, selectedInstance])
  const sourceTrend = useMemo(() => normalizeSourceSeries(sourceTelemetry?.series || {}), [sourceTelemetry])
  const nodeTrend = useMemo(() => normalizeNodeSeries(nodeTelemetry?.series || {}), [nodeTelemetry])
  const heatDistribution = useMemo(() => buildHeatDistribution((telemetryOverview?.source_load as Array<Record<string, unknown>>) || []), [telemetryOverview])
  const instanceTrend = useMemo(() => normalizeSourceSeries(instanceTelemetry?.source_series || {}), [instanceTelemetry])

  const handleCreateInstance = async () => {
    setSubmittingCreate(true)
    try {
      await GenesisApi.createSourceInstance({ instance_name: createState.instance_name, connector_key: createState.connector_key, config: { ...createState.config, memory_scope_default: createState.memory_scope_default } })
      setCreateOpen(false)
      setCreateState(DEFAULT_CREATE_STATE)
      setInstancePage(1)
      await loadInstances()
    } finally {
      setSubmittingCreate(false)
    }
  }

  const handleSaveInstance = async () => {
    if (!selectedInstance) return
    setSavingInstance(true)
    try {
      await GenesisApi.updateSourceInstance(selectedInstance.id, {
        instance_name: instanceDraft.instance_name,
        memory_scope_default: instanceDraft.memory_scope_default,
        watch_enabled: instanceDraft.watch_enabled,
        watch_interval_seconds: instanceDraft.watch_interval_seconds,
        config: { ...instanceDraft.config, memory_scope_default: instanceDraft.memory_scope_default },
      })
      await Promise.all([loadInstances(), loadSelectedInstance(selectedInstance.id)])
    } finally {
      setSavingInstance(false)
    }
  }

  const handleInstanceAction = async (action: 'test' | 'discover' | 'watch' | 'delete') => {
    if (!selectedInstance) return
    setRunningAction(action)
    try {
      if (action === 'test') await GenesisApi.testSourceInstance(selectedInstance.id)
      if (action === 'discover') await GenesisApi.discoverSourceInstance(selectedInstance.id)
      if (action === 'watch') await GenesisApi.runSourceWatch(selectedInstance.id)
      if (action === 'delete') { await GenesisApi.deleteSourceInstance(selectedInstance.id); setSelectedInstanceId(null) }
      await Promise.all([loadInstances(), loadChanges(), loadCandidates(), loadAssets(), loadTelemetry()])
      if (action !== 'delete') await loadSelectedInstance(selectedInstance.id)
    } finally {
      setRunningAction(null)
    }
  }

  const handleCandidateAction = async (candidateId: number, action: 'promote' | 'share' | 'dismiss') => {
    setRunningAction(`${action}-${candidateId}`)
    try {
      if (action === 'promote') await GenesisApi.promoteSourceCandidate(candidateId)
      if (action === 'share') await GenesisApi.shareSourceCandidate(candidateId)
      if (action === 'dismiss') await GenesisApi.dismissSourceCandidate(candidateId)
      await Promise.all([loadCandidates(), loadChanges()])
      if (selectedInstanceId) await loadSelectedInstance(selectedInstanceId)
    } finally {
      setRunningAction(null)
    }
  }

  return (
    <div className="space-y-6">
      <section className="df-surface p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-[var(--df-border)] bg-[var(--df-surface-2)] px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--df-text-soft)]"><Cable size={14} />数据源接入</div>
            <h1 className="df-display mt-3 text-3xl font-semibold tracking-tight text-[var(--df-text)]">实例优先的数据源接入工作台</h1>
            <p className="mt-2 max-w-4xl text-sm leading-7 text-[var(--df-text-muted)]">统一管理连接器、实例、资产、变化候选、AI 简报和遥测数据。保持现有三段式壳层不变，仅在本模块内完成实例发现与候选纳管。</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button type="button" onClick={() => setCreateOpen(true)} className="inline-flex items-center gap-2 rounded-xl bg-[var(--df-ink)] px-4 py-2.5 text-sm font-medium text-white"><BadgePlus size={15} />新增实例</button>
            <button type="button" onClick={() => void Promise.all([loadInstances(), loadChanges(), loadCandidates(), loadAssets(), loadTelemetry()])} className="inline-flex items-center gap-2 rounded-xl border border-[var(--df-border)] bg-white px-4 py-2.5 text-sm font-medium text-[var(--df-text-muted)] hover:bg-[var(--df-surface-2)]"><RefreshCw size={15} />刷新数据</button>
          </div>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
        <StatCard label="实例总数" value={telemetryOverview?.summary.instance_count ?? instances?.total ?? 0} helper="当前已纳管的数据源实例" icon={Server} />
        <StatCard label="热点实例" value={telemetryOverview?.summary.hot_instances ?? 0} helper="最近一轮发现中的高热实例" icon={Activity} />
        <StatCard label="开放候选" value={telemetryOverview?.summary.open_candidates ?? 0} helper="等待确认纳管的变化候选" icon={BellRing} />
        <StatCard label="开放变化" value={telemetryOverview?.summary.open_changes ?? 0} helper="等待确认的结构变化事件" icon={FileSearch} />
      </div>

      <div className="flex flex-wrap gap-2">
        {TAB_ITEMS.map((tab) => {
          const active = activeTab === tab.key
          return <button key={tab.key} type="button" onClick={() => setActiveTab(tab.key)} className={`inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition ${active ? 'border-[var(--df-ink)] bg-[var(--df-ink)] text-white' : 'border-[var(--df-border)] bg-white text-[var(--df-text-muted)] hover:bg-[var(--df-surface-2)]'}`}><tab.icon size={15} />{tab.label}</button>
        })}
      </div>

      {activeTab === 'instances' ? (
        <div className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)] 2xl:grid-cols-[420px_minmax(0,1fr)]">
          <Section title="实例列表" subtitle="按实例管理接入对象，支持搜索、过滤、分页和冷热查看。">
            <div className="space-y-3">
              <div className="relative"><Search size={15} className="absolute left-3 top-3 text-slate-400" /><input value={instanceQuery} onChange={(event) => { setInstanceQuery(event.target.value); setInstancePage(1) }} placeholder="搜索实例名称或连接器" className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-10 py-2.5 text-sm text-slate-700 outline-none" /></div>
              <div className="grid gap-3 sm:grid-cols-3">
                <select value={instanceConnector} onChange={(event) => { setInstanceConnector(event.target.value); setInstancePage(1) }} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"><option value="ALL">全部连接器</option>{connectors.map((item) => <option key={item.connector_key} value={item.connector_key}>{item.display_name}</option>)}</select>
                <select value={instanceStatus} onChange={(event) => { setInstanceStatus(event.target.value); setInstancePage(1) }} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"><option value="ALL">全部状态</option>{Array.from(new Set((instances?.items || []).map((item) => item.status))).map((item) => <option key={item} value={item}>{item}</option>)}</select>
                <select value={instanceHeat} onChange={(event) => { setInstanceHeat(event.target.value); setInstancePage(1) }} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"><option value="ALL">全部热度</option><option value="HOT">HOT</option><option value="WARM">WARM</option><option value="COLD">COLD</option></select>
              </div>
            </div>
            <div className="mt-5 rounded-2xl border border-slate-200 bg-white">
              {loading ? (
                <div className="py-12 text-center text-sm text-slate-500">正在加载实例...</div>
              ) : (instances?.items.length ?? 0) === 0 ? (
                <div className="px-4 py-10 text-center text-sm text-slate-500">当前没有可显示的实例，请先创建实例或调整筛选条件。</div>
              ) : (
                <div className="max-h-[720px] overflow-auto">
                  {instances?.items.map((item, index) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setSelectedInstanceId(item.id)}
                      className={`flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left transition ${index > 0 ? 'border-t border-slate-100' : ''} ${selectedInstanceId === item.id ? 'bg-slate-900 text-white' : 'hover:bg-slate-50'}`}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <div className={`truncate text-sm font-semibold ${selectedInstanceId === item.id ? 'text-white' : 'text-slate-900'}`}>{item.instance_name}</div>
                          <span className={`rounded-full px-2 py-0.5 text-[10px] ${selectedInstanceId === item.id ? 'bg-white/10 text-slate-200' : 'bg-slate-100 text-slate-600'}`}>{item.connector_name}</span>
                        </div>
                        <div className={`mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] ${selectedInstanceId === item.id ? 'text-slate-300' : 'text-slate-500'}`}>
                          <span>资产 {formatNumber(item.asset_count)}</span>
                          <span>行数 {formatNumber(item.row_count_estimate)}</span>
                          <span>大小 {formatBytes(item.estimated_bytes)}</span>
                        </div>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-1.5">
                        <Badge label={item.heat_level} tone={selectedInstanceId === item.id ? 'bg-white/10 text-white border-white/20' : heatTone(item.heat_level)} />
                        <Badge label={item.status} tone={selectedInstanceId === item.id ? 'bg-white/10 text-white border-white/20' : statusTone(item.status)} />
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
            {instances ? <Pager total={instances.total} page={instances.page} totalPages={instances.total_pages} onChange={setInstancePage} /> : null}
          </Section>

          <Section title={selectedInstance ? `实例详情 · ${selectedInstance.instance_name}` : '实例详情'} subtitle="连接信息、支持能力、最近发现、最近同步与最近简报。" actions={selectedInstance ? <Badge label={selectedInstance.status} tone={statusTone(selectedInstance.status)} /> : null}>
            {!selectedInstance ? <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-16 text-center text-sm text-slate-500">左侧选择一个实例后，可在这里查看连接配置、测试连接、执行发现与实例监听。</div> : <div className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4"><div className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div className="text-xs uppercase tracking-[0.16em] text-slate-500">连接器</div><div className="mt-2 text-lg font-semibold text-slate-900">{selectedInstance.connector_name}</div><div className="mt-1 text-sm text-slate-500">{selectedInstance.runtime_family}</div></div><div className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div className="text-xs uppercase tracking-[0.16em] text-slate-500">资产 / 行数</div><div className="mt-2 text-lg font-semibold text-slate-900">{formatNumber(selectedInstance.asset_count)} / {formatNumber(selectedInstance.row_count_estimate)}</div><div className="mt-1 text-sm text-slate-500">{formatBytes(selectedInstance.estimated_bytes)}</div></div><div className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div className="text-xs uppercase tracking-[0.16em] text-slate-500">最近发现</div><div className="mt-2 text-lg font-semibold text-slate-900">{selectedInstance.last_discover_status || '-'}</div><div className="mt-1 text-sm text-slate-500">{formatDate(selectedInstance.last_discovered_at)}</div></div><div className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div className="text-xs uppercase tracking-[0.16em] text-slate-500">自动监听</div><div className="mt-2 text-lg font-semibold text-slate-900">{selectedInstance.watch_enabled ? '已启用' : '未启用'}</div><div className="mt-1 text-sm text-slate-500">下次执行 {formatDate(selectedInstance.watch_next_run_at)}</div></div></div>
              <div className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,0.9fr)]"><div className="min-w-0 space-y-4"><div className="grid gap-4 md:grid-cols-2"><div className="space-y-2"><label className="text-sm font-medium text-slate-700">实例名称</label><input value={instanceDraft.instance_name} onChange={(event) => setInstanceDraft((prev) => ({ ...prev, instance_name: event.target.value }))} className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none" /></div><div className="space-y-2"><label className="text-sm font-medium text-slate-700">默认记忆范围</label><select value={instanceDraft.memory_scope_default} onChange={(event) => setInstanceDraft((prev) => ({ ...prev, memory_scope_default: event.target.value, config: { ...prev.config, memory_scope_default: event.target.value } }))} className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none"><option value="PRIVATE">项目记忆</option><option value="TENANT">公共记忆</option></select></div></div>
              <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px_180px]"><div className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div className="text-sm font-semibold text-slate-900">自动监听</div><div className="mt-1 text-xs text-slate-500">启用后由后台定时轮询实例变化，不需要手工反复点击。</div><label className="mt-4 inline-flex items-center gap-3 text-sm font-medium text-slate-700"><input type="checkbox" checked={instanceDraft.watch_enabled} onChange={(event) => setInstanceDraft((prev) => ({ ...prev, watch_enabled: event.target.checked }))} className="h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-900" />启用自动监听</label></div><div className="space-y-2"><label className="text-sm font-medium text-slate-700">监听间隔</label><select value={instanceDraft.watch_interval_seconds} onChange={(event) => setInstanceDraft((prev) => ({ ...prev, watch_interval_seconds: Number(event.target.value) }))} className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none">{WATCH_INTERVAL_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div><div className="space-y-2"><div className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div className="text-xs uppercase tracking-[0.16em] text-slate-500">监听状态</div><div className="mt-2 text-sm font-semibold text-slate-900">{selectedInstance.last_watch_status || '-'}</div><div className="mt-1 text-xs text-slate-500">失败次数 {formatNumber(selectedInstance.watch_failure_count)}</div><div className="mt-1 text-xs text-slate-500">下次执行 {formatDate(selectedInstance.watch_next_run_at)}</div></div></div></div>
              <div className="grid gap-4 md:grid-cols-2">{(selectedConnector?.config_schema || []).map((field) => { if (field.key === 'memory_scope_default') return null; const fieldValue = String(instanceDraft.config[field.key] ?? ''); const inputType = field.type === 'password' ? 'password' : field.type === 'number' ? 'number' : 'text'; return <div key={field.key} className="space-y-2"><label className="text-sm font-medium text-slate-700">{field.label}</label><input type={inputType} value={fieldValue} onChange={(event) => setInstanceDraft((prev) => ({ ...prev, config: { ...prev.config, [field.key]: field.type === 'number' ? Number(event.target.value) : event.target.value } }))} className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none" placeholder={field.placeholder || ''} /></div>})}</div>
              <div className="flex flex-wrap gap-3"><button type="button" onClick={() => void handleSaveInstance()} disabled={savingInstance} className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50">{savingInstance ? <Loader2 size={15} className="animate-spin" /> : <Activity size={15} />}保存配置</button><button type="button" onClick={() => void handleInstanceAction('test')} disabled={runningAction !== null} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">{runningAction === 'test' ? <Loader2 size={15} className="animate-spin" /> : <Network size={15} />}测试连接</button><button type="button" onClick={() => void handleInstanceAction('discover')} disabled={runningAction !== null} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">{runningAction === 'discover' ? <Loader2 size={15} className="animate-spin" /> : <FileSearch size={15} />}执行发现</button><button type="button" onClick={() => void handleInstanceAction('watch')} disabled={runningAction !== null} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">{runningAction === 'watch' ? <Loader2 size={15} className="animate-spin" /> : <BellRing size={15} />}立即执行监听</button><button type="button" onClick={() => void handleInstanceAction('delete')} disabled={runningAction !== null} className="inline-flex items-center gap-2 rounded-xl border border-rose-200 bg-white px-4 py-2.5 text-sm font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-50">{runningAction === 'delete' ? <Loader2 size={15} className="animate-spin" /> : <X size={15} />}删除实例</button></div></div>
              <div className="min-w-0 space-y-4"><div className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div className="flex items-center justify-between gap-3"><div><div className="text-sm font-semibold text-slate-900">最近简报</div><div className="mt-1 text-xs text-slate-500">每次发现或监听完成后自动生成。</div></div><Badge label={memoryScopeLabel(selectedInstance.memory_scope_default)} tone="bg-indigo-50 text-indigo-700 border-indigo-200" /></div><div className="mt-4 space-y-3">{(selectedInstance.recent_briefs || []).length === 0 ? <div className="text-sm text-slate-500">当前实例还没有简报。</div> : (selectedInstance.recent_briefs || []).map((brief) => <div key={brief.id} className="rounded-2xl border border-slate-200 bg-white p-3"><div className="font-medium text-slate-900">{brief.title || '未命名简报'}</div><div className="mt-1 text-sm text-slate-600">{brief.summary || '暂无摘要。'}</div><div className="mt-2 text-xs text-slate-500">{formatDate(brief.created_at)}</div></div>)}</div></div><div className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div className="flex items-center justify-between gap-3"><div><div className="text-sm font-semibold text-slate-900">最近负载趋势</div><div className="mt-1 text-xs text-slate-500">实例级嵌入折线图。</div></div><LineChartIcon size={16} className="text-slate-400" /></div><div className="mt-4"><MeasuredChart heightClassName="h-28" minHeight={112} emptyText="暂无实例负载趋势">{(size) => <LineChart width={size.width} height={size.height} data={instanceTrend}><Line type="monotone" dataKey="load_score" stroke="#111827" strokeWidth={2} dot={false} /><Tooltip /></LineChart>}</MeasuredChart></div></div></div></div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div className="flex items-center justify-between gap-3"><div><div className="text-sm font-semibold text-slate-900">最近资产预览</div><div className="mt-1 text-xs text-slate-500">默认展示最近 6 个资产。</div></div><Eye size={16} className="text-slate-400" /></div><div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{(instanceAssets?.items || []).length === 0 ? <div className="text-sm text-slate-500">当前实例还没有资产，请先执行发现。</div> : instanceAssets?.items.map((asset) => <div key={asset.id} className="rounded-2xl border border-slate-200 bg-white p-3"><div className="flex items-center justify-between gap-2"><div className="truncate font-medium text-slate-900">{asset.display_name}</div><Badge label={asset.heat_level} tone={heatTone(asset.heat_level)} /></div><div className="mt-1 truncate text-xs text-slate-500">{asset.qualified_name}</div><div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-500"><div>类型：{asset.asset_type}</div><div>列数：{formatNumber(asset.column_count)}</div><div>行数：{formatNumber(asset.row_count_estimate)}</div><div>大小：{formatBytes(asset.estimated_bytes)}</div></div></div>)}</div></div>
            </div>}
          </Section>
        </div>
      ) : null}
      {activeTab === 'changes' ? (
        <div className="space-y-6">
          <Section title="变化事件" subtitle="监听发现的新数据库、新表、字段变化、删除和刷新模式变化。">
            <div className="grid gap-3 md:grid-cols-3"><div className="relative"><Search size={15} className="absolute left-3 top-3 text-slate-400" /><input value={changeQuery} onChange={(event) => { setChangeQuery(event.target.value); setChangePage(1) }} placeholder="搜索变化标题或摘要" className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-10 py-2.5 text-sm text-slate-700 outline-none" /></div><select value={changeStatus} onChange={(event) => { setChangeStatus(event.target.value); setChangePage(1) }} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"><option value="ALL">全部状态</option><option value="OPEN">OPEN</option><option value="RESOLVED">RESOLVED</option><option value="DISMISSED">DISMISSED</option></select><select value={changeSeverity} onChange={(event) => { setChangeSeverity(event.target.value); setChangePage(1) }} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"><option value="ALL">全部级别</option><option value="HIGH">HIGH</option><option value="MEDIUM">MEDIUM</option><option value="LOW">LOW</option></select></div>
            <div className="mt-5 space-y-3">{(changes?.items || []).map((item) => <div key={item.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div className="flex flex-wrap items-center gap-2"><Badge label={item.severity} tone={statusTone(item.severity)} /><Badge label={item.status} tone={statusTone(item.status)} /><Badge label={item.event_type} tone="bg-slate-100 text-slate-700 border-slate-200" /></div><div className="mt-3 text-base font-semibold text-slate-900">{item.title}</div><div className="mt-1 text-sm text-slate-600">{item.summary || '暂无摘要。'}</div><div className="mt-3 text-xs text-slate-500">推荐动作：{item.recommended_action || '-'} · 发现时间：{formatDate(item.detected_at)}</div></div>)}</div>
            {changes ? <Pager total={changes.total} page={changes.page} totalPages={changes.total_pages} onChange={setChangePage} /> : null}
          </Section>

          <Section title="候选变化" subtitle="变化默认先进入候选区，再人工确认纳入项目或公共记忆。">
            <div className="grid gap-3 md:grid-cols-4"><div className="relative"><Search size={15} className="absolute left-3 top-3 text-slate-400" /><input value={candidateQuery} onChange={(event) => { setCandidateQuery(event.target.value); setCandidatePage(1) }} placeholder="搜索候选标题或摘要" className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-10 py-2.5 text-sm text-slate-700 outline-none" /></div><select value={candidateStatus} onChange={(event) => { setCandidateStatus(event.target.value); setCandidatePage(1) }} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"><option value="ALL">全部状态</option><option value="OPEN">OPEN</option><option value="PROMOTED">PROMOTED</option><option value="SHARED">SHARED</option><option value="DISMISSED">DISMISSED</option></select><select value={candidateType} onChange={(event) => { setCandidateType(event.target.value); setCandidatePage(1) }} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"><option value="ALL">全部候选类型</option><option value="NEW_ASSET">NEW_ASSET</option><option value="ASSET_CHANGE">ASSET_CHANGE</option><option value="ASSET_REMOVED">ASSET_REMOVED</option></select><select value={candidateScope} onChange={(event) => { setCandidateScope(event.target.value); setCandidatePage(1) }} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"><option value="ALL">全部目标范围</option><option value="PRIVATE">项目记忆</option><option value="TENANT">公共记忆</option></select></div>
            <div className="mt-5 space-y-3">{(candidates?.items || []).map((item) => <div key={item.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><Badge label={item.status} tone={statusTone(item.status)} /><Badge label={item.candidate_type} tone="bg-slate-100 text-slate-700 border-slate-200" /><Badge label={memoryScopeLabel(item.memory_scope_target)} tone="bg-indigo-50 text-indigo-700 border-indigo-200" /></div><div className="mt-3 text-base font-semibold text-slate-900">{item.title}</div><div className="mt-1 text-sm text-slate-600">{item.summary || '暂无摘要。'}</div>{item.asset ? <div className="mt-3 text-xs text-slate-500">关联资产：{item.asset.qualified_name} · 热度 {item.asset.heat_level} · 行数 {formatNumber(item.asset.row_count_estimate)}</div> : null}</div><div className="flex flex-wrap gap-2 lg:justify-end"><button type="button" onClick={() => void handleCandidateAction(item.id, 'promote')} disabled={runningAction === `promote-${item.id}` || item.status !== 'OPEN'} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50">纳入项目</button><button type="button" onClick={() => void handleCandidateAction(item.id, 'share')} disabled={runningAction === `share-${item.id}` || item.status !== 'OPEN'} className="rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm text-indigo-700 hover:bg-indigo-100 disabled:opacity-50">提升公共记忆</button><button type="button" onClick={() => void handleCandidateAction(item.id, 'dismiss')} disabled={runningAction === `dismiss-${item.id}` || item.status !== 'OPEN'} className="rounded-xl border border-rose-200 bg-white px-3 py-2 text-sm text-rose-600 hover:bg-rose-50 disabled:opacity-50">忽略</button></div></div></div>)}</div>
            {candidates ? <Pager total={candidates.total} page={candidates.page} totalPages={candidates.total_pages} onChange={setCandidatePage} /> : null}
          </Section>
        </div>
      ) : null}

      {activeTab === 'assets' ? (
        <div className="grid gap-6 xl:grid-cols-[420px_minmax(0,1fr)]">
          <Section title="资产目录" subtitle="统一展示 database / schema / table / topic / file / index 等资产。">
            <div className="grid gap-3 md:grid-cols-2"><div className="relative md:col-span-2"><Search size={15} className="absolute left-3 top-3 text-slate-400" /><input value={assetQuery} onChange={(event) => { setAssetQuery(event.target.value); setAssetPage(1) }} placeholder="搜索资产名称、限定名或主题域" className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-10 py-2.5 text-sm text-slate-700 outline-none" /></div><select value={assetType} onChange={(event) => { setAssetType(event.target.value); setAssetPage(1) }} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"><option value="ALL">全部资产类型</option><option value="DATABASE">DATABASE</option><option value="TABLE">TABLE</option><option value="FILESET">FILESET</option><option value="FILE">FILE</option><option value="FOLDER">FOLDER</option></select><select value={assetHeat} onChange={(event) => { setAssetHeat(event.target.value); setAssetPage(1) }} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"><option value="ALL">全部热度</option><option value="HOT">HOT</option><option value="WARM">WARM</option><option value="COLD">COLD</option></select><select value={assetStatus} onChange={(event) => { setAssetStatus(event.target.value); setAssetPage(1) }} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 md:col-span-2"><option value="ALL">全部状态</option><option value="DISCOVERED">DISCOVERED</option><option value="ACTIVE">ACTIVE</option><option value="SHARED">SHARED</option><option value="MISSING">MISSING</option></select></div>
            <div className="mt-5 space-y-3">{(assets?.items || []).map((item) => <button key={item.id} type="button" onClick={() => setSelectedAsset(item)} className={`w-full rounded-2xl border p-4 text-left transition ${selectedAsset?.id === item.id ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-slate-50 hover:border-slate-300 hover:bg-white'}`}><div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="truncate text-base font-semibold">{item.display_name}</div><div className={`mt-1 truncate text-xs ${selectedAsset?.id === item.id ? 'text-slate-300' : 'text-slate-500'}`}>{item.qualified_name}</div></div><Badge label={item.heat_level} tone={heatTone(item.heat_level)} /></div><div className={`mt-3 flex flex-wrap gap-2 text-xs ${selectedAsset?.id === item.id ? 'text-slate-200' : 'text-slate-500'}`}><span>类型：{item.asset_type}</span><span>主题域：{item.inferred_domain || '通用域'}</span><span>更新语义：{item.update_mode}</span></div></button>)}</div>
            {assets ? <Pager total={assets.total} page={assets.page} totalPages={assets.total_pages} onChange={setAssetPage} /> : null}
          </Section>

          <Section title={selectedAsset ? `资产详情 · ${selectedAsset.display_name}` : '资产详情'} subtitle="展示资产事实、字段级证据和待确认语义候选。">
            {!selectedAsset ? (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-16 text-center text-sm text-slate-500">左侧选择资产后，在这里查看资产事实、字段统计和候选语义。</div>
            ) : (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge label={selectedAsset.asset_type} tone="bg-slate-100 text-slate-700 border-slate-200" />
                  <Badge label={selectedAsset.status} tone={statusTone(selectedAsset.status)} />
                  <Badge label={selectedAsset.heat_level} tone={heatTone(selectedAsset.heat_level)} />
                  <Badge label={`字段 ${formatNumber(selectedAsset.field_count ?? selectedAsset.column_count)}`} tone="bg-indigo-50 text-indigo-700 border-indigo-200" />
                  <Badge label={`候选 ${formatNumber(selectedAsset.semantic_candidate_count ?? 0)}`} tone="bg-amber-50 text-amber-700 border-amber-200" />
                </div>

                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="text-sm font-semibold text-slate-900">资产事实</div>
                  <div className="mt-3 grid gap-3 md:grid-cols-2 text-sm text-slate-600">
                    <div>限定名：{selectedAsset.qualified_name}</div>
                    <div>主题域：{selectedAsset.inferred_domain || '通用域'}</div>
                    <div>估算行数：{formatNumber(selectedAsset.row_count_estimate)}</div>
                    <div>估算大小：{formatBytes(selectedAsset.estimated_bytes)}</div>
                    <div>字段数：{formatNumber(selectedAsset.field_count ?? selectedAsset.column_count)}</div>
                    <div>更新语义：{selectedAsset.update_mode}</div>
                    <div>最近发现：{formatDate(selectedAsset.last_seen_at)}</div>
                    <div>最近更新：{formatDate(selectedAsset.updated_at)}</div>
                  </div>
                </div>

                <div className="grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold text-slate-900">字段列表</div>
                        <div className="mt-1 text-xs text-slate-500">字段级事实、统计证据和候选语义。</div>
                      </div>
                    </div>
                    <div className="mt-4 grid gap-3 md:grid-cols-3">
                      <div className="relative md:col-span-3">
                        <Search size={15} className="absolute left-3 top-3 text-slate-400" />
                        <input value={fieldQuery} onChange={(event) => { setFieldQuery(event.target.value); setFieldPage(1) }} placeholder="搜索字段名称" className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-10 py-2.5 text-sm text-slate-700 outline-none" />
                      </div>
                      <select value={fieldStatus} onChange={(event) => { setFieldStatus(event.target.value); setFieldPage(1) }} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700">
                        <option value="ALL">全部状态</option>
                        <option value="DISCOVERED">DISCOVERED</option>
                        <option value="ACTIVE">ACTIVE</option>
                        <option value="MISSING">MISSING</option>
                      </select>
                      <select value={fieldCandidateType} onChange={(event) => { setFieldCandidateType(event.target.value); setFieldPage(1) }} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 md:col-span-2">
                        <option value="ALL">全部候选类型</option>
                        <option value="IDENTITY_FIELD">IDENTITY_FIELD</option>
                        <option value="TIME_FIELD">TIME_FIELD</option>
                        <option value="STATUS_FIELD">STATUS_FIELD</option>
                        <option value="JOIN_KEY">JOIN_KEY</option>
                      </select>
                    </div>
                    <div className="mt-4 space-y-2">
                      {(assetFields?.items || []).map((field) => (
                        <button
                          key={field.id}
                          type="button"
                          onClick={() => setSelectedFieldId(field.id)}
                          className={`w-full rounded-2xl border p-3 text-left transition ${selectedFieldId === field.id ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-slate-50 hover:border-slate-300 hover:bg-white'}`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="truncate text-sm font-semibold">{field.field_name}</div>
                              <div className={`mt-1 text-xs ${selectedFieldId === field.id ? 'text-slate-300' : 'text-slate-500'}`}>
                                {field.physical_type} · {field.nullable ? '可空' : '非空'}
                              </div>
                            </div>
                            <div className="flex flex-wrap justify-end gap-1.5">
                              {field.is_primary_key_candidate ? <Badge label="主键候选" tone={selectedFieldId === field.id ? 'bg-white/10 text-white border-white/20' : 'bg-emerald-50 text-emerald-700 border-emerald-200'} /> : null}
                              {field.is_time_field_candidate ? <Badge label="时间候选" tone={selectedFieldId === field.id ? 'bg-white/10 text-white border-white/20' : 'bg-indigo-50 text-indigo-700 border-indigo-200'} /> : null}
                              {field.candidates.length > 0 ? <Badge label={`${field.candidates.length} 个候选`} tone={selectedFieldId === field.id ? 'bg-white/10 text-white border-white/20' : 'bg-amber-50 text-amber-700 border-amber-200'} /> : null}
                            </div>
                          </div>
                        </button>
                      ))}
                      {(assetFields?.items.length ?? 0) === 0 ? (
                        <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-10 text-center text-sm text-slate-500">当前资产还没有字段事实，请先重新执行发现。</div>
                      ) : null}
                    </div>
                    {assetFields ? <Pager total={assetFields.total} page={assetFields.page} totalPages={assetFields.total_pages} onChange={setFieldPage} /> : null}
                  </div>

                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    {!selectedField ? (
                      <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-16 text-center text-sm text-slate-500">左侧选择一个字段后，在这里查看事实、证据、候选和知识提示。</div>
                    ) : (
                      <div className="space-y-4">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="text-lg font-semibold text-slate-900">{selectedField.field_name}</div>
                            <div className="mt-1 text-sm text-slate-500">{selectedField.display_name} · {selectedField.physical_type}</div>
                          </div>
                          <Badge label={selectedField.status} tone={statusTone(selectedField.status)} />
                        </div>
                        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                          <div className="text-sm font-semibold text-slate-900">字段事实</div>
                          <div className="mt-3 grid gap-2 text-sm text-slate-600 md:grid-cols-2">
                            <div>字段键：{selectedField.field_key}</div>
                            <div>位置：{selectedField.ordinal_position}</div>
                            <div>可空：{selectedField.nullable ? '是' : '否'}</div>
                            <div>最近发现：{formatDate(selectedField.last_seen_at)}</div>
                          </div>
                        </div>
                        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                          <div className="text-sm font-semibold text-slate-900">字段证据</div>
                          {fieldProfiles.length > 0 ? (
                            <div className="mt-3 grid gap-2 text-sm text-slate-600 md:grid-cols-2">
                              <div>空值率：{Number(fieldProfiles[0].null_ratio || 0).toFixed(4)}</div>
                              <div>去重率：{Number(fieldProfiles[0].distinct_ratio || 0).toFixed(4)}</div>
                              <div>最小值：{fieldProfiles[0].min_value || '-'}</div>
                              <div>最大值：{fieldProfiles[0].max_value || '-'}</div>
                              <div className="md:col-span-2">样本值：{fieldProfiles[0].sample_values.length > 0 ? fieldProfiles[0].sample_values.join('，') : '-'}</div>
                            </div>
                          ) : (
                            <div className="mt-3 text-sm text-slate-500">当前字段暂无统计证据。</div>
                          )}
                        </div>
                        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                          <div className="text-sm font-semibold text-slate-900">候选判断</div>
                          {fieldCandidates.length > 0 ? (
                            <div className="mt-3 space-y-2">
                              {fieldCandidates.map((candidate) => (
                                <div key={candidate.id} className="rounded-2xl border border-slate-200 bg-white px-3 py-3 text-sm text-slate-600">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <Badge label={candidate.candidate_type} tone="bg-amber-50 text-amber-700 border-amber-200" />
                                    <Badge label={candidate.status} tone={statusTone(candidate.status)} />
                                    <span>置信度：{Number(candidate.confidence || 0).toFixed(2)}</span>
                                  </div>
                                  <div className="mt-2">{candidate.reasoning || '暂无推理说明'}</div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="mt-3 text-sm text-slate-500">当前字段暂无候选语义。</div>
                          )}
                        </div>
                        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                          <div className="text-sm font-semibold text-slate-900">知识与治理</div>
                          <div className="mt-3 text-sm leading-6 text-slate-600">
                            字段级知识对象会在 AI 记忆和知识文档页按层级展示。当前字段的正式说明需要基于事实引用创建；候选语义保持为“待确认”，不会直接作为正式事实发布。
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-slate-950 p-4">
                  <div className="mb-3 text-sm font-semibold text-slate-100">Schema 与统计原始载荷</div>
                  <pre className="max-h-[320px] overflow-auto text-xs text-slate-100">{JSON.stringify({ schema: selectedAsset.schema_payload, metrics: selectedAsset.metrics_payload }, null, 2)}</pre>
                </div>
              </div>
            )}
          </Section>
        </div>
      ) : null}
      {activeTab === 'connectors' ? (
        <Section title="连接器目录" subtitle="按连接器能力声明统一纳管，而不是按单一产品硬编码流程。" actions={<select value={connectorCategory} onChange={(event) => setConnectorCategory(event.target.value)} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"><option value="ALL">全部分类</option>{Array.from(new Set(connectors.map((item) => item.category))).map((item) => <option key={item} value={item}>{item}</option>)}</select>}>
          <div className="space-y-5">{groupedConnectors.map(([category, items]) => <div key={category} className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div className="text-base font-semibold text-slate-900">{category}</div><div className="mt-4 grid gap-4 xl:grid-cols-2">{items.map((item) => <div key={item.connector_key} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><div className="flex items-start justify-between gap-3"><div><div className="text-base font-semibold text-slate-900">{item.display_name}</div><div className="mt-1 text-xs text-slate-500">{item.runtime_family}</div></div><Badge label={item.status} tone={statusTone(item.status)} /></div><div className="mt-3 text-sm text-slate-600">{item.description || '暂无说明'}</div><div className="mt-4 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">支持能力</div><div className="mt-2 flex flex-wrap gap-2">{item.capabilities.map((capability) => <span key={capability} className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-600">{capability}</span>)}</div><div className="mt-4 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">认证方式</div><div className="mt-2 flex flex-wrap gap-2">{item.auth_modes.map((mode) => <span key={mode} className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-600">{mode}</span>)}</div></div>)}</div></div>)}</div>
        </Section>
      ) : null}

      {activeTab === 'telemetry' ? (
        <div className="space-y-6">
          <Section title="遥测总览" subtitle="源级与节点级遥测统一展示为图表和数据。" actions={<div className="flex items-center gap-2"><Filter size={15} className="text-slate-400" /><select value={telemetryWindow} onChange={(event) => setTelemetryWindow(event.target.value as '24h' | '7d')} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"><option value="24h">近 24 小时</option><option value="7d">近 7 天</option></select></div>}>
            <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4"><StatCard label="实例" value={telemetryOverview?.summary.instance_count ?? 0} icon={Server} /><StatCard label="热点实例" value={telemetryOverview?.summary.hot_instances ?? 0} icon={Activity} /><StatCard label="开放候选" value={telemetryOverview?.summary.open_candidates ?? 0} icon={BellRing} /><StatCard label="开放变化" value={telemetryOverview?.summary.open_changes ?? 0} icon={FileSearch} /></div>
          </Section>

          <div className="grid gap-6 xl:grid-cols-2">
            <Section title="源级负载趋势" subtitle="显示近时间窗口内的平均负载、吞吐与扫描耗时。"><SafeResponsiveChart heightClassName="h-72" minHeight={288} dataPoints={sourceTrend.length}><LineChart data={sourceTrend}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="sample_at" tick={{ fontSize: 12 }} /><YAxis tick={{ fontSize: 12 }} /><Tooltip /><Legend /><Line type="monotone" dataKey="load_score" name="负载分数" stroke="#111827" strokeWidth={2} dot={false} /><Line type="monotone" dataKey="throughput_mb_per_hour" name="吞吐 MB/h" stroke="#0f766e" strokeWidth={2} dot={false} /><Line type="monotone" dataKey="scan_duration_ms" name="扫描耗时 ms" stroke="#2563eb" strokeWidth={2} dot={false} /></LineChart></SafeResponsiveChart></Section>
            <Section title="失败率趋势" subtitle="发现链路的失败率变化。"><SafeResponsiveChart heightClassName="h-72" minHeight={288} dataPoints={sourceTrend.length}><AreaChart data={sourceTrend}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="sample_at" tick={{ fontSize: 12 }} /><YAxis tick={{ fontSize: 12 }} /><Tooltip /><Area type="monotone" dataKey="failure_rate" name="失败率" stroke="#dc2626" fill="#fecaca" strokeWidth={2} /></AreaChart></SafeResponsiveChart></Section>
            <Section title="热点与吞吐 Top N" subtitle="查看当前最热实例及其吞吐和扫描耗时。"><SafeResponsiveChart heightClassName="h-72" minHeight={288} dataPoints={(((telemetryOverview?.source_load as Array<Record<string, unknown>>) || []).slice(0, 10)).length}><BarChart data={((telemetryOverview?.source_load as Array<Record<string, unknown>>) || []).slice(0, 10)}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="instance_name" tick={{ fontSize: 11 }} interval={0} angle={-18} height={70} /><YAxis tick={{ fontSize: 12 }} /><Tooltip /><Legend /><Bar dataKey="throughput_mb_per_hour" name="吞吐 MB/h" fill="#0f766e" radius={[6, 6, 0, 0]} /><Bar dataKey="scan_duration_ms" name="扫描耗时 ms" fill="#2563eb" radius={[6, 6, 0, 0]} /></BarChart></SafeResponsiveChart></Section>
            <Section title="冷热分布" subtitle="按实例热度统计 HOT / WARM / COLD 分布。"><SafeResponsiveChart heightClassName="h-72" minHeight={288} dataPoints={heatDistribution.reduce((sum, item) => sum + Number(item.value || 0), 0)}><PieChart><Pie data={heatDistribution} dataKey="value" nameKey="name" outerRadius={110} innerRadius={54} paddingAngle={4} /><Tooltip /><Legend /></PieChart></SafeResponsiveChart></Section>
          </div>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,0.9fr)]">
            <Section title="节点级指标趋势" subtitle="CPU、内存、磁盘吞吐、网络吞吐与队列积压。"><SafeResponsiveChart heightClassName="h-72" minHeight={288} dataPoints={nodeTrend.length}><LineChart data={nodeTrend}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="sample_at" tick={{ fontSize: 12 }} /><YAxis tick={{ fontSize: 12 }} /><Tooltip /><Legend /><Line type="monotone" dataKey="cpu_pct" name="CPU %" stroke="#7c3aed" strokeWidth={2} dot={false} /><Line type="monotone" dataKey="memory_pct" name="内存 %" stroke="#0f766e" strokeWidth={2} dot={false} /><Line type="monotone" dataKey="disk_throughput_mb" name="磁盘吞吐 MB" stroke="#ea580c" strokeWidth={2} dot={false} /><Line type="monotone" dataKey="network_throughput_mb" name="网络吞吐 MB" stroke="#2563eb" strokeWidth={2} dot={false} /><Line type="monotone" dataKey="queue_backlog" name="队列积压" stroke="#dc2626" strokeWidth={2} dot={false} /></LineChart></SafeResponsiveChart></Section>
            <Section title="节点健康" subtitle="当前节点角色、健康状态与关键资源指标。"><div className="space-y-3">{(((telemetryOverview?.nodes as Array<Record<string, unknown>>) || [])).map((node) => <div key={String(node.scope_key || node.node_name)} className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div className="flex items-start justify-between gap-3"><div><div className="font-semibold text-slate-900">{String(node.node_name || node.scope_key || 'unknown-node')}</div><div className="mt-1 text-xs text-slate-500">角色：{String(node.role || '-')}</div></div><Badge label={String(node.health || 'HEALTHY')} tone={statusTone(String(node.health || 'HEALTHY'))} /></div><div className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-2"><div>CPU：{Number(node.cpu_pct || 0).toFixed(1)}%</div><div>内存：{Number(node.memory_pct || 0).toFixed(1)}%</div><div>磁盘吞吐：{Number(node.disk_throughput_mb || 0).toFixed(2)} MB</div><div>网络吞吐：{Number(node.network_throughput_mb || 0).toFixed(2)} MB</div><div className="sm:col-span-2">积压：{formatNumber(Number(node.queue_backlog || 0))}</div></div></div>)}</div></Section>
          </div>
        </div>
      ) : null}

      <CreateInstanceModal open={createOpen} connectors={connectors} value={createState} onChange={setCreateState} onClose={() => { setCreateOpen(false); setCreateState(DEFAULT_CREATE_STATE) }} onSubmit={() => void handleCreateInstance()} submitting={submittingCreate} />
    </div>
  )
}
