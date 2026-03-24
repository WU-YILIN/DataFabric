import { useEffect, useMemo, useState } from 'react'
import { Download, FileSearch, Filter, RefreshCw, Search } from 'lucide-react'

import {
  GenesisApi,
  type AuditLogDetailResponse,
  type AuditLogListItem,
  type AuditLogListResponse,
  type AuditLogStatus,
  type FabricContextRef,
  type FabricTraceResponse,
} from '../services/api'
import { useBrowserErrorAlert } from '../hooks/useBrowserErrorAlert'

const PAGE_SIZES = [50, 100, 200]

const statusTone: Record<AuditLogStatus, string> = {
  SUCCESS: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  FAILURE: 'border-rose-200 bg-rose-50 text-rose-700',
}

function formatDate(value?: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function JsonBlock({ data }: { data: unknown }) {
  return (
    <pre className="overflow-x-auto rounded-2xl bg-slate-950 px-4 py-4 text-xs leading-6 text-slate-100">
      {JSON.stringify(data ?? {}, null, 2)}
    </pre>
  )
}

function isContextRef(value: unknown): value is FabricContextRef {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    'object_type' in value &&
    typeof (value as { object_type?: unknown }).object_type === 'string'
  )
}

function normalizeContextRefs(value: unknown): FabricContextRef[] {
  if (!Array.isArray(value)) return []
  return value.filter(isContextRef)
}

function contextReasonLabel(reason?: string | null) {
  switch (reason) {
    case 'matched_field':
      return '字段直匹配'
    case 'matched_source':
      return '数据源命中'
    case 'matched_memory':
      return '记忆命中'
    case 'matched_contract':
      return '契约命中'
    case 'knowledge_object_ref':
      return '知识对象引用'
    case 'knowledge_fact_ref':
      return '知识事实引用'
    case 'field_fact':
      return '字段事实'
    default:
      return reason || '规划命中'
  }
}

function contextEvidenceLabel(mode?: string | null) {
  switch (mode) {
    case 'FACT':
      return '事实'
    case 'KNOWLEDGE':
      return '知识'
    case 'CONTRACT':
      return '契约'
    case 'CANDIDATE':
      return '候选'
    default:
      return mode || '上下文'
  }
}

function contextObjectLabel(type?: string | null) {
  switch (type) {
    case 'FIELD':
    case 'SOURCE_FIELD':
      return '字段'
    case 'ASSET':
    case 'SOURCE_ASSET':
      return '资产'
    case 'DOCUMENT':
    case 'KNOWLEDGE':
      return '文档'
    case 'SOURCE':
    case 'SOURCE_INSTANCE':
      return '数据源'
    case 'CONTRACT':
      return '契约'
    default:
      return type || '对象'
  }
}

function getTraceContextGroups(trace: FabricTraceResponse | null) {
  const raw = trace?.plan?.plan_payload?.context_refs
  if (!raw || typeof raw !== 'object') return []
  const mapping = raw as Record<string, unknown>
  const groups: Array<{ key: string; title: string; items: FabricContextRef[] }> = [
    { key: 'fields', title: '命中字段', items: normalizeContextRefs(mapping.fields) },
    { key: 'assets', title: '命中资产', items: normalizeContextRefs(mapping.assets) },
    { key: 'documents', title: '命中文档', items: normalizeContextRefs(mapping.documents) },
    { key: 'sources', title: '命中数据源', items: normalizeContextRefs(mapping.sources) },
    { key: 'contracts', title: '命中契约', items: normalizeContextRefs(mapping.contracts) },
  ]
  return groups.filter((group) => group.items.length > 0)
}

export default function AuditLogs() {
  const [listData, setListData] = useState<AuditLogListResponse | null>(null)
  const [rows, setRows] = useState<AuditLogListItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [selectedLogId, setSelectedLogId] = useState<number | null>(null)
  const [detail, setDetail] = useState<AuditLogDetailResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [traceDetail, setTraceDetail] = useState<FabricTraceResponse | null>(null)
  const [traceLoading, setTraceLoading] = useState(false)
  const [exportingFormat, setExportingFormat] = useState<'csv' | 'json' | null>(null)
  useBrowserErrorAlert(error)

  const [q, setQ] = useState('')
  const [actionFilter, setActionFilter] = useState('')
  const [entityTypeFilter, setEntityTypeFilter] = useState('')
  const [traceIdFilter, setTraceIdFilter] = useState('')
  const [userFilter, setUserFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [pageSize, setPageSize] = useState(100)
  const [offset, setOffset] = useState(0)

  const total = listData?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const currentPage = total === 0 ? 1 : Math.floor(offset / pageSize) + 1

  const loadLogs = async (nextOffset = offset) => {
    setLoading(true)
    setError(null)
    try {
      const data = await GenesisApi.getAuditLogs({
        q: q || undefined,
        action: actionFilter || undefined,
        entity_type: entityTypeFilter || undefined,
        trace_id: traceIdFilter || undefined,
        user: userFilter || undefined,
        status: (statusFilter || undefined) as AuditLogStatus | undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        limit: pageSize,
        offset: nextOffset,
      })
      setListData(data)
      setRows(data.items)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? '加载审计日志失败')
    } finally {
      setLoading(false)
    }
  }

  const openDetail = async (id: number) => {
    setSelectedLogId(id)
    setDetail(null)
    setTraceDetail(null)
    setDetailLoading(true)
    setTraceLoading(false)
    setError(null)
    try {
      const data = await GenesisApi.getAuditLogDetail(id)
      setDetail(data)
      if (data.trace_id) {
        setTraceLoading(true)
        try {
          const trace = await GenesisApi.getFabricTrace(data.trace_id)
          setTraceDetail(trace)
        } catch {
          setTraceDetail(null)
        } finally {
          setTraceLoading(false)
        }
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? '加载审计详情失败')
    } finally {
      setDetailLoading(false)
    }
  }

  const exportLogs = async (format: 'csv' | 'json') => {
    setExportingFormat(format)
    setNotice(null)
    setError(null)
    try {
      const data = await GenesisApi.exportAuditLogs({
        format,
        q: q || undefined,
        action: actionFilter || undefined,
        entity_type: entityTypeFilter || undefined,
        trace_id: traceIdFilter || undefined,
        user: userFilter || undefined,
        status: (statusFilter || undefined) as AuditLogStatus | undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      })
      const blob = new Blob([data.content], { type: data.mime_type })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = data.filename
      document.body.appendChild(anchor)
      anchor.click()
      document.body.removeChild(anchor)
      URL.revokeObjectURL(url)
      setNotice(`已导出 ${data.row_count} 条日志：${data.filename}`)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? '导出审计日志失败')
    } finally {
      setExportingFormat(null)
    }
  }

  useEffect(() => {
    void loadLogs(0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    void loadLogs(offset)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset, pageSize])

  const applyFilters = () => {
    setOffset(0)
    void loadLogs(0)
  }

  const pageSummary = useMemo(() => {
    if (total === 0) return '0 / 0'
    return `${currentPage} / ${totalPages}`
  }, [currentPage, total, totalPages])
  const traceContextGroups = useMemo(() => getTraceContextGroups(traceDetail), [traceDetail])

  return (
    <div className="space-y-6">
      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">审计日志</div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">操作、规划与执行追踪</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              统一查看用户操作、治理动作、查询规划、执行追踪和导出记录。新的 Query Intent、Query Plan 和 Query Run
              也会通过这里沉淀成可追溯链路。
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void loadLogs(0)}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              <RefreshCw size={15} />
              刷新
            </button>
            <button
              type="button"
              onClick={() => void exportLogs('csv')}
              disabled={Boolean(exportingFormat)}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              <Download size={15} />
              {exportingFormat === 'csv' ? '导出中…' : '导出 CSV'}
            </button>
            <button
              type="button"
              onClick={() => void exportLogs('json')}
              disabled={Boolean(exportingFormat)}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              <Download size={15} />
              {exportingFormat === 'json' ? '导出中…' : '导出 JSON'}
            </button>
          </div>
        </div>
      </div>

      {notice ? (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{notice}</div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.45fr_0.95fr]">
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div className="relative md:col-span-2">
              <Search size={16} className="absolute left-3 top-3 text-slate-400" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="搜索动作、实体、摘要或 trace"
                className="w-full rounded-xl border border-slate-200 bg-white px-9 py-2.5 text-sm text-slate-700"
              />
            </div>

            <select
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"
            >
              <option value="">全部动作</option>
              {(listData?.facets.actions ?? []).map((action) => (
                <option key={action} value={action}>
                  {action}
                </option>
              ))}
            </select>

            <select
              value={entityTypeFilter}
              onChange={(e) => setEntityTypeFilter(e.target.value)}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"
            >
              <option value="">全部实体</option>
              {(listData?.facets.entity_types ?? []).map((entityType) => (
                <option key={entityType} value={entityType}>
                  {entityType}
                </option>
              ))}
            </select>

            <input
              value={traceIdFilter}
              onChange={(e) => setTraceIdFilter(e.target.value)}
              list="audit-traces"
              placeholder="Trace ID"
              className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"
            />

            <input
              value={userFilter}
              onChange={(e) => setUserFilter(e.target.value)}
              list="audit-users"
              placeholder="用户"
              className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"
            />

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"
            >
              <option value="">全部状态</option>
              <option value="SUCCESS">SUCCESS</option>
              <option value="FAILURE">FAILURE</option>
            </select>

            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"
            />

            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"
            />
          </div>

          <datalist id="audit-users">
            {(listData?.facets.users ?? []).map((item) => (
              <option key={item} value={item} />
            ))}
          </datalist>

          <datalist id="audit-traces">
            {(listData?.facets.trace_ids ?? []).map((item) => (
              <option key={item} value={item} />
            ))}
          </datalist>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <div className="inline-flex items-center gap-2 text-sm text-slate-500">
              <Filter size={14} />
              共 {total} 条日志，当前第 {pageSummary} 页
            </div>
            <div className="flex items-center gap-3">
              <select
                value={pageSize}
                onChange={(e) => {
                  const next = Number(e.target.value)
                  setPageSize(next)
                  setOffset(0)
                }}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
              >
                {PAGE_SIZES.map((size) => (
                  <option key={size} value={size}>
                    {size} / 页
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={applyFilters}
                className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
              >
                <FileSearch size={15} />
                应用筛选
              </button>
            </div>
          </div>

          <div className="mt-5 overflow-hidden rounded-2xl border border-slate-200">
            <div className="max-h-[680px] overflow-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-left text-slate-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">时间</th>
                    <th className="px-4 py-3 font-medium">动作</th>
                    <th className="px-4 py-3 font-medium">实体</th>
                    <th className="px-4 py-3 font-medium">目标</th>
                    <th className="px-4 py-3 font-medium">Trace</th>
                    <th className="px-4 py-3 font-medium">用户</th>
                    <th className="px-4 py-3 font-medium">状态</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {loading ? (
                    <tr>
                      <td className="px-4 py-8 text-center text-slate-500" colSpan={7}>
                        正在加载…
                      </td>
                    </tr>
                  ) : rows.length === 0 ? (
                    <tr>
                      <td className="px-4 py-8 text-center text-slate-500" colSpan={7}>
                        当前条件下没有审计日志。
                      </td>
                    </tr>
                  ) : (
                    rows.map((row) => (
                      <tr
                        key={row.id}
                        onClick={() => void openDetail(row.id)}
                        className={`cursor-pointer transition hover:bg-slate-50 ${
                          row.id === selectedLogId ? 'bg-indigo-50' : ''
                        }`}
                      >
                        <td className="px-4 py-3 text-slate-600">{formatDate(row.timestamp)}</td>
                        <td className="px-4 py-3">
                          <div className="font-medium text-slate-900">{row.action}</div>
                          <div className="mt-1 text-xs text-slate-500">{row.details_summary}</div>
                        </td>
                        <td className="px-4 py-3 text-slate-600">{row.entity_type}</td>
                        <td className="px-4 py-3 text-slate-600">{row.target || row.entity_id}</td>
                        <td className="px-4 py-3 font-mono text-xs text-slate-500">{row.trace_id || '-'}</td>
                        <td className="px-4 py-3 text-slate-600">{row.user}</td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${statusTone[row.status]}`}
                          >
                            {row.status}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="mt-4 flex items-center justify-between text-sm text-slate-500">
            <div>{total === 0 ? '0 / 0' : `${offset + 1}-${Math.min(offset + pageSize, total)} / ${total}`}</div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={offset <= 0}
                onClick={() => setOffset(Math.max(offset - pageSize, 0))}
                className="rounded-xl border border-slate-200 px-3 py-1.5 disabled:cursor-not-allowed disabled:opacity-50"
              >
                上一页
              </button>
              <div className="rounded-xl bg-slate-50 px-3 py-1.5">
                {currentPage}/{totalPages}
              </div>
              <button
                type="button"
                disabled={offset + pageSize >= total}
                onClick={() => setOffset(offset + pageSize)}
                className="rounded-xl border border-slate-200 px-3 py-1.5 disabled:cursor-not-allowed disabled:opacity-50"
              >
                下一页
              </button>
            </div>
          </div>
        </section>

        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4">
            <div className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">详情面板</div>
            <h2 className="mt-2 text-xl font-semibold tracking-tight text-slate-950">
              {detail ? `${detail.action} · ${detail.target || detail.entity_id}` : '选择一条日志查看详情'}
            </h2>
          </div>

          {detailLoading ? (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-10 text-center text-sm text-slate-500">
              正在加载详情…
            </div>
          ) : !detail ? (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-10 text-center text-sm text-slate-500">
              请选择左侧一条日志，查看对象、差异、导航信息和 trace 线索。
            </div>
          ) : (
            <div className="space-y-5">
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">状态</div>
                  <div className="mt-2 flex items-center gap-2">
                    <span
                      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${statusTone[detail.status]}`}
                    >
                      {detail.status}
                    </span>
                    <span className="text-sm text-slate-600">{formatDate(detail.timestamp)}</span>
                  </div>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">用户与上下文</div>
                  <div className="mt-2 space-y-1 text-sm text-slate-700">
                    <div>用户：{detail.user}</div>
                    <div>租户：{detail.context?.tenant_id ?? '-'}</div>
                    <div>项目：{detail.context?.project_id ?? '-'}</div>
                    <div className="break-all font-mono text-xs text-slate-500">Trace：{detail.trace_id || '-'}</div>
                  </div>
                </div>
              </div>

              <div>
                <div className="mb-2 text-sm font-semibold text-slate-900">摘要</div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700">
                  {detail.details_summary}
                </div>
              </div>

              <div>
                <div className="mb-2 text-sm font-semibold text-slate-900">关键字段</div>
                <JsonBlock data={detail.operation.key_fields} />
              </div>

              <div>
                <div className="mb-2 text-sm font-semibold text-slate-900">详细内容</div>
                <JsonBlock data={detail.operation.details} />
              </div>

              <div>
                <div className="mb-2 text-sm font-semibold text-slate-900">差异</div>
                <JsonBlock data={detail.diff} />
              </div>

              <div>
                <div className="mb-2 text-sm font-semibold text-slate-900">导航信息</div>
                <JsonBlock data={detail.navigation} />
              </div>

              {detail.trace_id ? (
                <div>
                  <div className="mb-2 text-sm font-semibold text-slate-900">Trace 上下文</div>
                  {traceLoading ? (
                    <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">
                      正在加载 trace 上下文…
                    </div>
                  ) : !traceDetail || !traceDetail.plan ? (
                    <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">
                      当前 trace 没有可展示的规划上下文。
                    </div>
                  ) : (
                    <div className="space-y-3 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div className="flex flex-wrap gap-2">
                        <span className="inline-flex rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600">
                          {traceDetail.intent?.intent_type || 'UNKNOWN'}
                        </span>
                        <span className="inline-flex rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600">
                          {traceDetail.plan.selected_path}
                        </span>
                        <span className="inline-flex rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600">
                          {traceDetail.plan.plan_status}
                        </span>
                      </div>

                      <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm leading-7 text-slate-600">
                        {traceDetail.plan.rationale}
                      </div>

                      {traceContextGroups.length > 0 ? (
                        <div className="space-y-3">
                          {traceContextGroups.map((group) => (
                            <div key={group.key}>
                              <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
                                {group.title}
                              </div>
                              <div className="flex flex-wrap gap-2">
                                {group.items.slice(0, 8).map((item) => (
                                  <div
                                    key={`${group.key}-${item.object_type}-${item.id}`}
                                    className="min-w-[180px] rounded-2xl border border-slate-200 bg-white px-3 py-2"
                                  >
                                    <div className="truncate text-sm font-medium text-slate-900">
                                      {item.label || `${contextObjectLabel(item.object_type)} ${item.id}`}
                                    </div>
                                    <div className="mt-1 text-[11px] leading-5 text-slate-500">
                                      {contextObjectLabel(item.object_type)} · {contextReasonLabel(item.reason)} ·{' '}
                                      {contextEvidenceLabel(item.evidence_mode)}
                                    </div>
                                  </div>
                                ))}
                                {group.items.length > 8 ? (
                                  <div className="rounded-2xl border border-dashed border-slate-200 px-3 py-2 text-xs text-slate-500">
                                    +{group.items.length - 8} 个未展开
                                  </div>
                                ) : null}
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="rounded-2xl border border-dashed border-slate-200 bg-white px-4 py-4 text-sm text-slate-500">
                          当前 trace 没有命中对象列表。
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
