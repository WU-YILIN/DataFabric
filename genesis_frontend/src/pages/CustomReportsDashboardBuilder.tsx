import { FormEvent, useEffect, useMemo, useState } from 'react'
import { clsx } from 'clsx'
import { BarChart3, Copy, Download, RefreshCw, Save, Share2 } from 'lucide-react'

import {
  GenesisApi,
  type ReportDashboardItem,
  type ReportDetailResponse,
  type ReportListResponse,
  type ReportOverviewResponse,
  type ReportTemplateListResponse,
} from '../services/api'

const KIND_OPTIONS = ['ALL', 'DASHBOARD', 'REPORT']
const STATUS_OPTIONS = ['ALL', 'DRAFT', 'PUBLISHED', 'ARCHIVED']

const statusClassName = (status: string): string => {
  if (status === 'PUBLISHED') return 'bg-emerald-100 text-emerald-700'
  if (status === 'ARCHIVED') return 'bg-slate-200 text-slate-700'
  return 'bg-sky-100 text-sky-700'
}

const parseJsonObject = (value: string): Record<string, unknown> | null => {
  try {
    const parsed = JSON.parse(value)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
  } catch {
    return null
  }
  return null
}

const renderSimpleWidget = (widget: Record<string, unknown>) => {
  const title = String(widget.title ?? 'Widget')
  const kpi = widget.kpi as { value?: unknown; unit?: unknown } | undefined
  const series = Array.isArray(widget.series) ? (widget.series as Array<Record<string, unknown>>) : null
  const table = Array.isArray(widget.table) ? (widget.table as Array<Record<string, unknown>>) : null

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4" key={String(widget.widget_id ?? title)}>
      <h5 className="text-sm font-semibold text-slate-800">{title}</h5>
      {kpi && (
        <div className="mt-2">
          <p className="text-2xl font-bold text-slate-900">{String(kpi.value ?? '-')}</p>
          <p className="text-xs text-slate-500">{String(kpi.unit ?? '')}</p>
        </div>
      )}
      {series && (
        <div className="mt-2 space-y-1">
          {series.slice(0, 10).map((row, index) => (
            <div key={`${title}-s-${index}`} className="flex items-center justify-between text-xs">
              <span className="text-slate-500">{String(row.label ?? row.bucket ?? '-')}</span>
              <span className="font-semibold text-slate-800">{String(row.value ?? '-')}</span>
            </div>
          ))}
        </div>
      )}
      {table && table.length > 0 && (
        <div className="mt-2 overflow-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500">
                {Object.keys(table[0]).map((key) => (
                  <th key={`${title}-h-${key}`} className="py-1 pr-2">
                    {key}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.slice(0, 8).map((row, rowIndex) => (
                <tr key={`${title}-r-${rowIndex}`} className="border-t border-slate-100">
                  {Object.keys(table[0]).map((key) => (
                    <td key={`${title}-c-${rowIndex}-${key}`} className="py-1 pr-2 text-slate-700">
                      {String(row[key] ?? '-')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!kpi && !series && !table && <p className="mt-2 text-xs text-slate-500">No data.</p>}
    </div>
  )
}

const CustomReportsDashboardBuilder = () => {
  const [overview, setOverview] = useState<ReportOverviewResponse | null>(null)
  const [templates, setTemplates] = useState<ReportTemplateListResponse | null>(null)
  const [listResp, setListResp] = useState<ReportListResponse | null>(null)
  const [detail, setDetail] = useState<ReportDetailResponse | null>(null)
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null)

  const [filters, setFilters] = useState({
    q: '',
    kind: 'ALL',
    status: 'ALL',
    creator: '',
    scenario: '',
    tag: '',
  })
  const [createForm, setCreateForm] = useState({
    template_key: 'OPS_MONITORING',
    kind: 'DASHBOARD',
    name: '',
    scenario: '',
    status: 'DRAFT',
    tags_text: 'ops, monitoring',
  })
  const [detailForm, setDetailForm] = useState({
    runtime_filters_text: '{}',
    time_window_days: 30,
    note: '',
    clone_name: '',
    view_name: '',
    export_format: 'LINK',
    share_payload_text: JSON.stringify(
      {
        visibility: 'PROJECT',
        viewer_roles: ['VIEWER', 'EDITOR', 'APPROVER', 'ADMIN', 'OWNER'],
        editor_roles: ['EDITOR', 'APPROVER', 'ADMIN', 'OWNER'],
        clone_roles: ['EDITOR', 'APPROVER', 'ADMIN', 'OWNER'],
      },
      null,
      2,
    ),
  })

  const [loading, setLoading] = useState(false)
  const [operating, setOperating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const loadOverview = async () => {
    const data = await GenesisApi.getReportsOverview()
    setOverview(data)
  }

  const loadTemplates = async () => {
    const data = await GenesisApi.getReportTemplates()
    setTemplates(data)
  }

  const loadItems = async () => {
    const data = await GenesisApi.getReportItems({
      q: filters.q.trim() || undefined,
      kind: filters.kind === 'ALL' ? undefined : filters.kind,
      status: filters.status === 'ALL' ? undefined : filters.status,
      creator: filters.creator.trim() || undefined,
      scenario: filters.scenario.trim() || undefined,
      tag: filters.tag.trim() || undefined,
      limit: 200,
      offset: 0,
    })
    setListResp(data)
    if (!selectedItemId && data.items.length > 0) {
      setSelectedItemId(data.items[0].id)
      return
    }
    if (selectedItemId && !data.items.find((item) => item.id === selectedItemId)) {
      setSelectedItemId(data.items[0]?.id ?? null)
    }
  }

  const loadDetail = async (itemId: number) => {
    const data = await GenesisApi.getReportItemDetail(itemId, {
      include_data: true,
      time_window_days: detailForm.time_window_days,
      runtime_filters: detailForm.runtime_filters_text.trim(),
    })
    setDetail(data)
  }

  const refreshAll = async () => {
    setLoading(true)
    setError(null)
    try {
      await Promise.all([loadOverview(), loadTemplates(), loadItems()])
      if (selectedItemId != null) {
        await loadDetail(selectedItemId)
      }
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? 'Failed to load report center')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refreshAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (selectedItemId != null) {
      void loadDetail(selectedItemId).catch(() => setDetail(null))
    } else {
      setDetail(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedItemId])

  const onApplyFilters = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await loadItems()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? 'Failed to load items')
    } finally {
      setLoading(false)
    }
  }

  const onCreateItem = async (event: FormEvent) => {
    event.preventDefault()
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const created = await GenesisApi.createReportItem({
        template_key: createForm.template_key || undefined,
        kind: createForm.kind,
        name: createForm.name.trim() || undefined,
        scenario: createForm.scenario.trim() || undefined,
        status: createForm.status,
        tags: createForm.tags_text
          .split(',')
          .map((row) => row.trim())
          .filter(Boolean),
      })
      setMessage(`Created item #${created.id}`)
      await Promise.all([loadOverview(), loadItems()])
      setSelectedItemId(created.id)
      setCreateForm((prev) => ({ ...prev, name: '' }))
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? 'Create item failed')
    } finally {
      setOperating(false)
    }
  }

  const onOperateItem = async (action: string) => {
    if (!detail) return
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const runtimeFilters = parseJsonObject(detailForm.runtime_filters_text)
      const sharePayload = parseJsonObject(detailForm.share_payload_text)
      if ((action === 'REFRESH_CACHE' || action === 'SAVE_VIEW') && runtimeFilters == null) {
        setError('runtime filters must be valid JSON object')
        return
      }
      if (action === 'SHARE' && sharePayload == null) {
        setError('share payload must be valid JSON object')
        return
      }

      await GenesisApi.operateReportItem(detail.item.id, {
        action,
        note: detailForm.note.trim() || undefined,
        clone_name: action === 'CLONE' ? detailForm.clone_name.trim() || undefined : undefined,
        view_name: action === 'SAVE_VIEW' || action === 'EXPORT' ? detailForm.view_name.trim() || undefined : undefined,
        view_filter_payload: action === 'REFRESH_CACHE' || action === 'SAVE_VIEW' || action === 'EXPORT' ? runtimeFilters ?? {} : undefined,
        export_format: action === 'EXPORT' ? detailForm.export_format : undefined,
        time_window_days: action === 'REFRESH_CACHE' ? detailForm.time_window_days : undefined,
        share_payload: action === 'SHARE' ? sharePayload ?? {} : undefined,
      })

      setMessage(`Action ${action} applied`)
      await Promise.all([loadOverview(), loadItems(), loadDetail(detail.item.id)])
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? `Action ${action} failed`)
    } finally {
      setOperating(false)
    }
  }

  const itemKinds = useMemo(
    () => ['ALL', ...(listResp?.facets.kinds.map((row) => row.kind) ?? KIND_OPTIONS.slice(1))],
    [listResp?.facets.kinds],
  )
  const itemStatuses = useMemo(
    () => ['ALL', ...(listResp?.facets.statuses.map((row) => row.status) ?? STATUS_OPTIONS.slice(1))],
    [listResp?.facets.statuses],
  )
  const selectedItem: ReportDashboardItem | null = detail?.item ?? null

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">Custom Reports & Dashboard Builder</h2>
          <p className="text-slate-500 text-base">Build project dashboards/reports with template, sharing, caching, and export flow.</p>
        </div>
        <button onClick={() => void refreshAll()} disabled={loading || operating} className="rounded-xl bg-slate-900 text-white px-4 py-2.5 font-medium hover:bg-slate-800 disabled:opacity-60 flex items-center gap-2">
          <RefreshCw size={16} />
          Refresh
        </button>
      </header>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
      {message && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>}

      <section className="grid grid-cols-2 md:grid-cols-7 gap-3">
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Total</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.total_items ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Dashboards</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.dashboards ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Reports</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.reports ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Draft</p><p className="text-2xl font-bold text-sky-700">{overview?.summary.draft_items ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Published</p><p className="text-2xl font-bold text-emerald-700">{overview?.summary.published_items ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Archived</p><p className="text-2xl font-bold text-slate-700">{overview?.summary.archived_items ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Saved Views</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.saved_views ?? 0}</p></div>
      </section>

      <form onSubmit={onApplyFilters} className="glass rounded-3xl border border-slate-200/60 p-4">
        <div className="grid grid-cols-1 md:grid-cols-7 gap-3">
          <input value={filters.q} onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))} placeholder="search name/desc/tag" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
          <select value={filters.kind} onChange={(e) => setFilters((prev) => ({ ...prev, kind: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{itemKinds.map((row) => <option key={row} value={row}>{row}</option>)}</select>
          <select value={filters.status} onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{itemStatuses.map((row) => <option key={row} value={row}>{row}</option>)}</select>
          <input value={filters.creator} onChange={(e) => setFilters((prev) => ({ ...prev, creator: e.target.value }))} placeholder="creator" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
          <input value={filters.scenario} onChange={(e) => setFilters((prev) => ({ ...prev, scenario: e.target.value }))} placeholder="scenario" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
          <input value={filters.tag} onChange={(e) => setFilters((prev) => ({ ...prev, tag: e.target.value }))} placeholder="tag" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
          <button type="submit" className="rounded-xl bg-cyan-600 text-white px-4 py-2 text-sm font-semibold">Apply Filters</button>
        </div>
      </form>

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="space-y-4">
          <div className="glass rounded-3xl border border-slate-200/60 p-4">
            <h3 className="text-sm font-semibold text-slate-800 mb-3 flex items-center gap-2"><BarChart3 size={16} /> Reports / Dashboards</h3>
            <div className="space-y-2 max-h-[28rem] overflow-auto">
              {(listResp?.items ?? []).map((row) => (
                <button key={row.id} onClick={() => setSelectedItemId(row.id)} className={clsx('w-full text-left rounded-xl border px-3 py-2 transition', selectedItemId === row.id ? 'border-cyan-300 bg-cyan-50/70' : 'border-slate-200 bg-white hover:bg-slate-50')}>
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-semibold text-slate-800 text-sm line-clamp-2">{row.name}</p>
                    <span className={clsx('px-2 py-0.5 rounded-full text-[11px] font-semibold', statusClassName(row.status))}>{row.status}</span>
                  </div>
                  <p className="text-xs text-slate-500">{row.kind} | {row.scenario ?? 'UNSET'}</p>
                  <p className="text-xs text-slate-500">{row.created_by}</p>
                </button>
              ))}
              {(listResp?.items.length ?? 0) === 0 && <p className="text-sm text-slate-500">No items found.</p>}
            </div>
          </div>

          <form onSubmit={onCreateItem} className="glass rounded-3xl border border-slate-200/60 p-4 space-y-2">
            <h3 className="text-sm font-semibold text-slate-800">Create New</h3>
            <select value={createForm.template_key} onChange={(e) => setCreateForm((prev) => ({ ...prev, template_key: e.target.value }))} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
              {(templates?.items ?? []).map((row) => <option key={row.key} value={row.key}>{row.key}</option>)}
            </select>
            <div className="grid grid-cols-2 gap-2">
              <select value={createForm.kind} onChange={(e) => setCreateForm((prev) => ({ ...prev, kind: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"><option value="DASHBOARD">DASHBOARD</option><option value="REPORT">REPORT</option></select>
              <select value={createForm.status} onChange={(e) => setCreateForm((prev) => ({ ...prev, status: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"><option value="DRAFT">DRAFT</option><option value="PUBLISHED">PUBLISHED</option></select>
            </div>
            <input value={createForm.name} onChange={(e) => setCreateForm((prev) => ({ ...prev, name: e.target.value }))} placeholder="name (optional if template)" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <input value={createForm.scenario} onChange={(e) => setCreateForm((prev) => ({ ...prev, scenario: e.target.value }))} placeholder="scenario (optional)" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <input value={createForm.tags_text} onChange={(e) => setCreateForm((prev) => ({ ...prev, tags_text: e.target.value }))} placeholder="tags comma separated" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <button type="submit" disabled={operating} className="w-full rounded-xl bg-cyan-600 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60">Create</button>
          </form>
        </div>

        <div className="xl:col-span-2 space-y-4">
          {!selectedItem ? (
            <div className="glass rounded-3xl border border-slate-200/60 p-8 text-sm text-slate-500">Select one report/dashboard to view details.</div>
          ) : (
            <div className="glass rounded-3xl border border-slate-200/60 p-4 space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-lg font-semibold text-slate-900">{selectedItem.name}</h3>
                  <p className="text-sm text-slate-500">{selectedItem.kind} | {selectedItem.scenario ?? 'UNSET'} | {selectedItem.created_by}</p>
                </div>
                <span className={clsx('px-2 py-1 rounded-full text-xs font-semibold', statusClassName(selectedItem.status))}>{selectedItem.status}</span>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Widgets</p><p className="font-semibold text-slate-800">{selectedItem.widget_count}</p></div>
                <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Template</p><p className="font-semibold text-slate-800">{selectedItem.template_key ?? '-'}</p></div>
                <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Last Refresh</p><p className="font-semibold text-slate-800">{selectedItem.last_data_refresh_at ? new Date(selectedItem.last_data_refresh_at).toLocaleString() : '-'}</p></div>
                <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Tags</p><p className="font-semibold text-slate-800">{selectedItem.tags.join(', ') || '-'}</p></div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-2">
                <h4 className="text-sm font-semibold text-slate-800">Runtime & Actions</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  <input value={detailForm.view_name} onChange={(e) => setDetailForm((prev) => ({ ...prev, view_name: e.target.value }))} placeholder="view name (save/export)" className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                  <input value={detailForm.clone_name} onChange={(e) => setDetailForm((prev) => ({ ...prev, clone_name: e.target.value }))} placeholder="clone name" className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                </div>
                <input type="number" min={1} max={180} value={detailForm.time_window_days} onChange={(e) => setDetailForm((prev) => ({ ...prev, time_window_days: Number(e.target.value || 30) }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm w-40" />
                <textarea value={detailForm.runtime_filters_text} onChange={(e) => setDetailForm((prev) => ({ ...prev, runtime_filters_text: e.target.value }))} rows={4} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-mono" />
                <textarea value={detailForm.share_payload_text} onChange={(e) => setDetailForm((prev) => ({ ...prev, share_payload_text: e.target.value }))} rows={5} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-mono" />
                <input value={detailForm.note} onChange={(e) => setDetailForm((prev) => ({ ...prev, note: e.target.value }))} placeholder="action note" className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  <button onClick={() => void onOperateItem('PUBLISH')} disabled={operating || !selectedItem.capabilities.can_edit} className="rounded-xl bg-emerald-600 text-white px-3 py-2 text-xs font-semibold disabled:opacity-60">Publish</button>
                  <button onClick={() => void onOperateItem('ARCHIVE')} disabled={operating || !selectedItem.capabilities.can_edit} className="rounded-xl bg-slate-700 text-white px-3 py-2 text-xs font-semibold disabled:opacity-60">Archive</button>
                  <button onClick={() => void onOperateItem('UNARCHIVE')} disabled={operating || !selectedItem.capabilities.can_edit} className="rounded-xl bg-cyan-700 text-white px-3 py-2 text-xs font-semibold disabled:opacity-60">Unarchive</button>
                  <button onClick={() => void onOperateItem('REFRESH_CACHE')} disabled={operating || !selectedItem.capabilities.can_edit} className="rounded-xl bg-slate-900 text-white px-3 py-2 text-xs font-semibold disabled:opacity-60 inline-flex items-center justify-center gap-1"><RefreshCw size={12} />Cache</button>
                  <button onClick={() => void onOperateItem('SAVE_VIEW')} disabled={operating} className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-60 inline-flex items-center justify-center gap-1"><Save size={12} />Save View</button>
                  <button onClick={() => void onOperateItem('CLONE')} disabled={operating || !selectedItem.capabilities.can_clone} className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-60 inline-flex items-center justify-center gap-1"><Copy size={12} />Clone</button>
                  <button onClick={() => void onOperateItem('SHARE')} disabled={operating || !selectedItem.capabilities.can_edit} className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-60 inline-flex items-center justify-center gap-1"><Share2 size={12} />Share</button>
                  <div className="flex items-center gap-2">
                    <select value={detailForm.export_format} onChange={(e) => setDetailForm((prev) => ({ ...prev, export_format: e.target.value }))} className="rounded-xl border border-slate-300 bg-white px-2 py-2 text-xs"><option value="LINK">LINK</option><option value="PDF">PDF</option><option value="IMAGE">IMAGE</option></select>
                    <button onClick={() => void onOperateItem('EXPORT')} disabled={operating} className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-60 inline-flex items-center justify-center gap-1"><Download size={12} />Export</button>
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <h4 className="text-sm font-semibold text-slate-800 mb-2">Data Widgets</h4>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                  {(detail?.data_payload?.widgets ?? []).map((widget, index) => renderSimpleWidget({ ...(widget as Record<string, unknown>), _index: index }))}
                  {(detail?.data_payload?.widgets?.length ?? 0) === 0 && <p className="text-sm text-slate-500">No computed widgets.</p>}
                </div>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

export default CustomReportsDashboardBuilder
