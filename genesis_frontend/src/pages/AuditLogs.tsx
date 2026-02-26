import { useEffect, useState } from 'react'
import { clsx } from 'clsx'
import { Download, Filter, Search, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import {
  GenesisApi,
  type AuditLogDetailResponse,
  type AuditLogListItem,
  type AuditLogListResponse,
  type AuditLogStatus,
} from '../services/api'
import { useLanguage } from '../i18n/language'

const statusClass: Record<AuditLogStatus, string> = {
  SUCCESS: 'bg-emerald-100 text-emerald-700',
  FAILURE: 'bg-rose-100 text-rose-700',
}

const AuditLogs = () => {
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const navigate = useNavigate()

  const [listData, setListData] = useState<AuditLogListResponse | null>(null)
  const [rows, setRows] = useState<AuditLogListItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const [q, setQ] = useState('')
  const [actionFilter, setActionFilter] = useState('')
  const [entityTypeFilter, setEntityTypeFilter] = useState('')
  const [userFilter, setUserFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [pageSize, setPageSize] = useState(100)
  const [offset, setOffset] = useState(0)

  const [selectedLogId, setSelectedLogId] = useState<number | null>(null)
  const [detail, setDetail] = useState<AuditLogDetailResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [exportingFormat, setExportingFormat] = useState<'csv' | 'json' | null>(null)

  const total = listData?.total ?? 0

  const loadLogs = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await GenesisApi.getAuditLogs({
        q: q || undefined,
        action: actionFilter || undefined,
        entity_type: entityTypeFilter || undefined,
        user: userFilter || undefined,
        status: (statusFilter || undefined) as AuditLogStatus | undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        limit: pageSize,
        offset,
      })
      setListData(data)
      setRows(data.items)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? (isZh ? '加载审计日志失败' : 'Failed to load audit logs'))
    } finally {
      setLoading(false)
    }
  }

  const openDetail = async (id: number) => {
    setSelectedLogId(id)
    setDetail(null)
    setDetailLoading(true)
    setError(null)
    try {
      const data = await GenesisApi.getAuditLogDetail(id)
      setDetail(data)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? (isZh ? '加载审计详情失败' : 'Failed to load audit detail'))
    } finally {
      setDetailLoading(false)
    }
  }

  const exportLogs = async (format: 'csv' | 'json') => {
    setExportingFormat(format)
    setError(null)
    setNotice(null)
    try {
      const data = await GenesisApi.exportAuditLogs({
        format,
        q: q || undefined,
        action: actionFilter || undefined,
        entity_type: entityTypeFilter || undefined,
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
      setNotice(isZh ? `已导出 ${data.row_count} 条日志：${data.filename}` : `Exported ${data.row_count} log(s) as ${data.filename}`)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? (isZh ? '导出审计日志失败' : 'Failed to export audit logs'))
    } finally {
      setExportingFormat(null)
    }
  }

  useEffect(() => {
    void loadLogs()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (offset === 0) {
      return
    }
    void loadLogs()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset, pageSize])

  const applyFilters = () => {
    setOffset(0)
    void loadLogs()
  }

  return (
    <div className="max-w-7xl mx-auto animate-in fade-in slide-in-from-bottom-8 duration-700 space-y-4">
      <header>
        <h2 className="text-3xl font-bold text-slate-900 tracking-tight">{isZh ? '审计日志' : 'Audit Logs'}</h2>
        <p className="text-slate-500 text-base">
          {isZh
            ? '检索不可变更的操作记录，查看变更细节，并按筛选导出。'
            : 'Search immutable operation records, inspect change details, and export by filter.'}
        </p>
      </header>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
      )}
      {notice && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {notice}
        </div>
      )}

      <section className="glass rounded-3xl border border-slate-200/60 p-4">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-7 gap-3">
          <div className="xl:col-span-2 relative">
            <Search size={16} className="absolute left-3 top-3 text-slate-400" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={isZh ? '搜索动作 / 实体 / 详情' : 'Search action / entity / details'}
              className="w-full rounded-xl border border-slate-200 bg-white px-9 py-2.5 text-sm text-slate-700"
            />
          </div>
          <select
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"
          >
            <option value="">{isZh ? '全部动作' : 'All Actions'}</option>
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
            <option value="">{isZh ? '全部实体' : 'All Entities'}</option>
            {(listData?.facets.entity_types ?? []).map((entityType) => (
              <option key={entityType} value={entityType}>
                {entityType}
              </option>
            ))}
          </select>
          <input
            value={userFilter}
            onChange={(e) => setUserFilter(e.target.value)}
            list="audit-users"
            placeholder={isZh ? '用户' : 'User'}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"
          >
            <option value="">{isZh ? '全部状态' : 'All Status'}</option>
            <option value="SUCCESS">SUCCESS</option>
            <option value="FAILURE">FAILURE</option>
          </select>
          <select
            value={String(pageSize)}
            onChange={(e) => setPageSize(Number(e.target.value))}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"
          >
            <option value={50}>{isZh ? '50 / 页' : '50 / page'}</option>
            <option value={100}>{isZh ? '100 / 页' : '100 / page'}</option>
            <option value={200}>{isZh ? '200 / 页' : '200 / page'}</option>
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
          <button
            onClick={applyFilters}
            className="rounded-xl bg-slate-900 text-white px-4 py-2.5 text-sm font-medium hover:bg-slate-800 flex items-center justify-center gap-2"
          >
            <Filter size={14} />
            {isZh ? '应用' : 'Apply'}
          </button>
          <button
            onClick={() => void exportLogs('csv')}
            disabled={Boolean(exportingFormat)}
            className="rounded-xl bg-slate-100 text-slate-700 px-4 py-2.5 text-sm font-medium hover:bg-slate-200 disabled:opacity-60 flex items-center justify-center gap-2"
          >
            <Download size={14} />
            {exportingFormat === 'csv' ? (isZh ? '导出 CSV 中...' : 'Exporting CSV...') : isZh ? '导出 CSV' : 'Export CSV'}
          </button>
          <button
            onClick={() => void exportLogs('json')}
            disabled={Boolean(exportingFormat)}
            className="rounded-xl bg-slate-100 text-slate-700 px-4 py-2.5 text-sm font-medium hover:bg-slate-200 disabled:opacity-60 flex items-center justify-center gap-2"
          >
            <Download size={14} />
            {exportingFormat === 'json' ? (isZh ? '导出 JSON 中...' : 'Exporting JSON...') : isZh ? '导出 JSON' : 'Export JSON'}
          </button>
        </div>
        <datalist id="audit-users">
          {(listData?.facets.users ?? []).map((item) => (
            <option key={item} value={item} />
          ))}
        </datalist>
      </section>

      <section className="glass rounded-3xl border border-slate-200/60 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200/70 bg-slate-50/70 text-sm text-slate-600 flex justify-between">
          <span>
            {isZh ? '总计' : 'total'}
            {' '}
            {total}
            {isZh ? ' 条日志' : ' logs'}
          </span>
          <span>
            {isZh ? '偏移' : 'offset'}
            {' '}
            {offset}
          </span>
        </div>
        <div className="overflow-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">{isZh ? '时间' : 'Time'}</th>
                <th className="text-left px-3 py-2">{isZh ? '动作' : 'Action'}</th>
                <th className="text-left px-3 py-2">{isZh ? '目标' : 'Target'}</th>
                <th className="text-left px-3 py-2">{isZh ? '用户' : 'User'}</th>
                <th className="text-left px-3 py-2">{isZh ? '状态' : 'Status'}</th>
                <th className="text-left px-3 py-2">{isZh ? '摘要' : 'Summary'}</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-3 py-4 text-slate-500">
                    {isZh ? '日志加载中...' : 'Loading logs...'}
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-3 py-4 text-slate-500">
                    {isZh ? '当前筛选条件下无日志。' : 'No logs matched current filters.'}
                  </td>
                </tr>
              ) : (
                rows.map((item) => (
                  <tr
                    key={item.id}
                    onClick={() => void openDetail(item.id)}
                    className="border-t border-slate-100 cursor-pointer hover:bg-cyan-50/40"
                  >
                    <td className="px-3 py-2 text-xs text-slate-600">{new Date(item.timestamp).toLocaleString()}</td>
                    <td className="px-3 py-2 font-semibold text-slate-800">{item.action}</td>
                    <td className="px-3 py-2 text-xs text-slate-600">{item.target}</td>
                    <td className="px-3 py-2 text-xs text-slate-600">{item.user}</td>
                    <td className="px-3 py-2">
                      <span className={clsx('px-2 py-0.5 rounded-full text-xs font-semibold', statusClass[item.status])}>
                        {item.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-600">{item.details_summary}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="px-4 py-3 border-t border-slate-200/70 bg-slate-50/70 flex justify-end gap-2">
          <button
            onClick={() => setOffset(Math.max(0, offset - pageSize))}
            disabled={offset <= 0 || loading}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {isZh ? '上一页' : 'Prev'}
          </button>
          <button
            onClick={() => setOffset(offset + pageSize)}
            disabled={offset + pageSize >= total || loading}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {isZh ? '下一页' : 'Next'}
          </button>
        </div>
      </section>

      {selectedLogId !== null && (
        <>
          <div
            className="fixed inset-0 bg-black/25 z-40"
            onClick={() => {
              setSelectedLogId(null)
              setDetail(null)
            }}
          />
          <aside className="fixed right-0 top-0 h-screen w-[620px] bg-white z-50 border-l border-slate-200 shadow-2xl overflow-auto">
            <div className="p-5 border-b border-slate-200 flex items-center justify-between">
              <h3 className="font-bold text-slate-900 text-lg">{isZh ? '审计详情' : 'Audit Detail'}</h3>
              <button
                onClick={() => {
                  setSelectedLogId(null)
                  setDetail(null)
                }}
                className="p-2 rounded-lg hover:bg-slate-100"
              >
                <X size={16} />
              </button>
            </div>
            {detailLoading || !detail ? (
              <div className="p-8 text-slate-500">{isZh ? '详情加载中...' : 'Loading detail...'}</div>
            ) : (
              <div className="p-5 space-y-4">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
                  <p className="font-semibold text-slate-900">{detail.action}</p>
                  <p className="text-xs text-slate-600 mt-1">
                    {detail.target}
                    {' | '}
                    {new Date(detail.timestamp).toLocaleString()}
                  </p>
                  <p className="text-xs text-slate-600 mt-1">
                    user=
                    {detail.user}
                    {' | status='}
                    {detail.status}
                  </p>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
                  <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">{isZh ? '上下文' : 'Context'}</p>
                  <p className="text-slate-700">
                    tenant=
                    {String(detail.context.tenant_id ?? '-')}
                    {' | project='}
                    {String(detail.context.project_id ?? '-')}
                    {' | ip='}
                    {detail.context.ip_address ?? '-'}
                  </p>
                  <p className="text-xs text-slate-500 mt-1">actor_raw={detail.context.actor_raw ?? '-'}</p>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
                  <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">{isZh ? '关键字段' : 'Key Fields'}</p>
                  <pre className="text-xs bg-slate-50 rounded p-2 overflow-auto text-slate-700">
                    {JSON.stringify(detail.operation.key_fields, null, 2)}
                  </pre>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
                  <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">{isZh ? '操作详情' : 'Operation Details'}</p>
                  <pre className="text-xs bg-slate-50 rounded p-2 overflow-auto text-slate-700">
                    {JSON.stringify(detail.operation.details, null, 2)}
                  </pre>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
                  <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">Diff</p>
                  <pre className="text-xs bg-slate-50 rounded p-2 overflow-auto text-slate-700">
                    {JSON.stringify(detail.diff, null, 2)}
                  </pre>
                </div>

                {detail.navigation.module_route && (
                  <button
                    onClick={() => navigate(detail.navigation.module_route || '/logs')}
                    className="w-full rounded-xl bg-cyan-600 text-white px-3 py-2.5 font-medium hover:bg-cyan-500"
                  >
                    {isZh ? '打开相关模块' : 'Open Related Module'}
                  </button>
                )}
              </div>
            )}
          </aside>
        </>
      )}
    </div>
  )
}

export default AuditLogs
