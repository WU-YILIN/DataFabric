import { FormEvent, useEffect, useMemo, useState } from 'react'
import { clsx } from 'clsx'
import { CheckCircle2, Copy, KeyRound, RefreshCw, Store } from 'lucide-react'

import {
  GenesisApi,
  type MarketplaceDetailResponse,
  type MarketplaceListResponse,
  type MarketplaceOverviewResponse,
  type MarketplaceProductItem,
  type MarketplaceSubscriptionItem,
} from '../services/api'
import { useLanguage } from '../i18n/language'

const STATUS_OPTIONS = ['ALL', 'DRAFT', 'PUBLISHED', 'ARCHIVED']
const VISIBILITY_OPTIONS = ['ALL', 'PROJECT', 'PRIVATE', 'ROLE_BASED']

const statusClassName = (status: string): string => {
  if (status === 'PUBLISHED') return 'bg-emerald-100 text-emerald-700'
  if (status === 'ARCHIVED') return 'bg-slate-200 text-slate-700'
  return 'bg-sky-100 text-sky-700'
}

const subscriptionStatusClass = (status: string): string => {
  if (status === 'APPROVED') return 'bg-emerald-100 text-emerald-700'
  if (status === 'PENDING') return 'bg-amber-100 text-amber-700'
  if (status === 'REJECTED') return 'bg-rose-100 text-rose-700'
  if (status === 'REVOKED') return 'bg-slate-200 text-slate-700'
  return 'bg-slate-100 text-slate-700'
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

const DataProductMarketplace = () => {
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const [overview, setOverview] = useState<MarketplaceOverviewResponse | null>(null)
  const [listResp, setListResp] = useState<MarketplaceListResponse | null>(null)
  const [detail, setDetail] = useState<MarketplaceDetailResponse | null>(null)
  const [selectedProductId, setSelectedProductId] = useState<number | null>(null)
  const [selectedSubscriptionId, setSelectedSubscriptionId] = useState<number | null>(null)

  const [filters, setFilters] = useState({
    q: '',
    status: 'ALL',
    visibility: 'ALL',
    owner: '',
    domain: '',
    tag: '',
  })
  const [createForm, setCreateForm] = useState({
    name: '',
    description: '',
    domain: 'core',
    category: 'analytics',
    status: 'DRAFT',
    visibility: 'PROJECT',
    tags_text: 'marketplace, shared',
    asset_ids_text: '',
    schema_payload_text: '{\n  "columns": []\n}',
    sla_payload_text: '{\n  "freshness_minutes": 60,\n  "availability_sla": 0.99\n}',
    access_policy_payload_text:
      '{\n  "viewer_roles": ["VIEWER", "EDITOR", "APPROVER", "ADMIN", "OWNER"],\n  "editor_roles": ["EDITOR", "APPROVER", "ADMIN", "OWNER"]\n}',
  })
  const [actionForm, setActionForm] = useState({
    note: '',
    request_reason: 'Need access for analytics dashboard',
    expires_hours: 720,
    usage_quota_payload_text: '{\n  "daily_calls": 5000,\n  "monthly_rows": 1000000\n}',
  })

  const [loading, setLoading] = useState(false)
  const [operating, setOperating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const loadOverview = async () => {
    const data = await GenesisApi.getMarketplaceOverview()
    setOverview(data)
  }

  const loadProducts = async () => {
    const data = await GenesisApi.getMarketplaceProducts({
      q: filters.q.trim() || undefined,
      status: filters.status === 'ALL' ? undefined : filters.status,
      visibility: filters.visibility === 'ALL' ? undefined : filters.visibility,
      owner: filters.owner.trim() || undefined,
      domain: filters.domain.trim() || undefined,
      tag: filters.tag.trim() || undefined,
      limit: 200,
      offset: 0,
    })
    setListResp(data)
    if (!selectedProductId && data.items.length > 0) {
      setSelectedProductId(data.items[0].id)
      return
    }
    if (selectedProductId && !data.items.find((item) => item.id === selectedProductId)) {
      setSelectedProductId(data.items[0]?.id ?? null)
    }
  }

  const loadDetail = async (productId: number) => {
    const data = await GenesisApi.getMarketplaceProductDetail(productId)
    setDetail(data)
    if (data.subscriptions.length > 0) {
      setSelectedSubscriptionId(data.subscriptions[0].id)
    } else {
      setSelectedSubscriptionId(null)
    }
  }

  const refreshAll = async () => {
    setLoading(true)
    setError(null)
    try {
      await Promise.all([loadOverview(), loadProducts()])
      if (selectedProductId != null) {
        await loadDetail(selectedProductId)
      }
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? (isZh ? '加载数据市场失败' : 'Failed to load marketplace'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refreshAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (selectedProductId != null) {
      void loadDetail(selectedProductId).catch(() => setDetail(null))
    } else {
      setDetail(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProductId])

  const onApplyFilters = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await loadProducts()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? (isZh ? '筛选产品失败' : 'Failed to filter products'))
    } finally {
      setLoading(false)
    }
  }

  const onCreateProduct = async (event: FormEvent) => {
    event.preventDefault()
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const schemaPayload = parseJsonObject(createForm.schema_payload_text)
      const slaPayload = parseJsonObject(createForm.sla_payload_text)
      const accessPolicyPayload = parseJsonObject(createForm.access_policy_payload_text)
      if (!schemaPayload || !slaPayload || !accessPolicyPayload) {
        setError(isZh ? 'Schema/SLA/Access policy 必须是合法 JSON 对象' : 'Schema/SLA/Access policy must be valid JSON objects')
        return
      }
      const created = await GenesisApi.createMarketplaceProduct({
        name: createForm.name.trim(),
        description: createForm.description.trim() || undefined,
        domain: createForm.domain.trim() || undefined,
        category: createForm.category.trim() || undefined,
        status: createForm.status,
        visibility: createForm.visibility,
        schema_payload: schemaPayload,
        asset_ids: createForm.asset_ids_text
          .split(',')
          .map((row) => Number(row.trim()))
          .filter((num) => Number.isFinite(num) && num > 0),
        tags: createForm.tags_text
          .split(',')
          .map((row) => row.trim())
          .filter(Boolean),
        sla_payload: slaPayload,
        access_policy_payload: accessPolicyPayload,
      })
      setMessage(isZh ? `已创建数据产品 #${created.id}` : `Created product #${created.id}`)
      setCreateForm((prev) => ({ ...prev, name: '', description: '', asset_ids_text: '' }))
      await Promise.all([loadOverview(), loadProducts()])
      setSelectedProductId(created.id)
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? (isZh ? '创建数据产品失败' : 'Create product failed'))
    } finally {
      setOperating(false)
    }
  }

  const onOperateProduct = async (action: string) => {
    if (!detail) return
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const quotaPayload = parseJsonObject(actionForm.usage_quota_payload_text)
      if (!quotaPayload) {
        setError(isZh ? 'usage_quota_payload 必须是合法 JSON 对象' : 'Usage quota payload must be valid JSON object')
        return
      }
      if (
        ['APPROVE_SUBSCRIPTION', 'REJECT_SUBSCRIPTION', 'CANCEL_SUBSCRIPTION', 'REVOKE_SUBSCRIPTION', 'ROTATE_TOKEN'].includes(action) &&
        !selectedSubscriptionId
      ) {
        setError(isZh ? '请先选择一个订阅记录' : 'Please select one subscription row first')
        return
      }
      await GenesisApi.operateMarketplaceProduct(detail.product.id, {
        action,
        note: actionForm.note.trim() || undefined,
        request_reason: action === 'REQUEST_SUBSCRIPTION' ? actionForm.request_reason.trim() || undefined : undefined,
        expires_hours: action === 'APPROVE_SUBSCRIPTION' || action === 'ROTATE_TOKEN' ? actionForm.expires_hours : undefined,
        usage_quota_payload:
          action === 'REQUEST_SUBSCRIPTION' || action === 'APPROVE_SUBSCRIPTION' ? quotaPayload : undefined,
        subscription_id:
          ['APPROVE_SUBSCRIPTION', 'REJECT_SUBSCRIPTION', 'CANCEL_SUBSCRIPTION', 'REVOKE_SUBSCRIPTION', 'ROTATE_TOKEN'].includes(action)
            ? selectedSubscriptionId ?? undefined
            : undefined,
      })
      setMessage(isZh ? `已执行动作 ${action}` : `Action ${action} applied`)
      await Promise.all([loadOverview(), loadProducts(), loadDetail(detail.product.id)])
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? (isZh ? `动作 ${action} 执行失败` : `Action ${action} failed`))
    } finally {
      setOperating(false)
    }
  }

  const statuses = useMemo(
    () => ['ALL', ...(listResp?.facets.statuses.map((row) => row.status) ?? STATUS_OPTIONS.slice(1))],
    [listResp?.facets.statuses],
  )

  const selectedProduct: MarketplaceProductItem | null = detail?.product ?? null
  const selectedSubscription: MarketplaceSubscriptionItem | null =
    detail?.subscriptions.find((row) => row.id === selectedSubscriptionId) ?? null

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">{isZh ? '数据产品市场' : 'Data Product Marketplace'}</h2>
          <p className="text-slate-500 text-base">
            {isZh
              ? '发布数据产品、处理订阅审批，并在审计链路下轮转访问令牌。'
              : 'Publish data products, manage subscription approvals, and rotate access tokens with audit trail.'}
          </p>
        </div>
        <button onClick={() => void refreshAll()} disabled={loading || operating} className="rounded-xl bg-slate-900 text-white px-4 py-2.5 font-medium hover:bg-slate-800 disabled:opacity-60 flex items-center gap-2">
          <RefreshCw size={16} />
          {isZh ? '刷新' : 'Refresh'}
        </button>
      </header>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
      {message && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>}

      <section className="grid grid-cols-2 md:grid-cols-7 gap-3">
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Products</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.total_products ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Draft</p><p className="text-2xl font-bold text-sky-700">{overview?.summary.draft_products ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Published</p><p className="text-2xl font-bold text-emerald-700">{overview?.summary.published_products ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Archived</p><p className="text-2xl font-bold text-slate-700">{overview?.summary.archived_products ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Pending Subs</p><p className="text-2xl font-bold text-amber-700">{overview?.summary.pending_subscriptions ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Approved Subs</p><p className="text-2xl font-bold text-emerald-700">{overview?.summary.approved_subscriptions ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Rejected Subs</p><p className="text-2xl font-bold text-rose-700">{overview?.summary.rejected_subscriptions ?? 0}</p></div>
      </section>

      <form onSubmit={onApplyFilters} className="glass rounded-3xl border border-slate-200/60 p-4">
        <div className="grid grid-cols-1 md:grid-cols-7 gap-3">
          <input value={filters.q} onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))} placeholder="search product" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
          <select value={filters.status} onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{statuses.map((row) => <option key={row} value={row}>{row}</option>)}</select>
          <select value={filters.visibility} onChange={(e) => setFilters((prev) => ({ ...prev, visibility: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{VISIBILITY_OPTIONS.map((row) => <option key={row} value={row}>{row}</option>)}</select>
          <input value={filters.owner} onChange={(e) => setFilters((prev) => ({ ...prev, owner: e.target.value }))} placeholder="owner" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
          <input value={filters.domain} onChange={(e) => setFilters((prev) => ({ ...prev, domain: e.target.value }))} placeholder="domain" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
          <input value={filters.tag} onChange={(e) => setFilters((prev) => ({ ...prev, tag: e.target.value }))} placeholder="tag" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
          <button type="submit" className="rounded-xl bg-cyan-600 text-white px-4 py-2 text-sm font-semibold">{isZh ? '应用筛选' : 'Apply Filters'}</button>
        </div>
      </form>

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="space-y-4">
          <div className="glass rounded-3xl border border-slate-200/60 p-4">
            <h3 className="text-sm font-semibold text-slate-800 mb-3 flex items-center gap-2"><Store size={16} /> Products</h3>
            <div className="space-y-2 max-h-[28rem] overflow-auto">
              {(listResp?.items ?? []).map((row) => (
                <button key={row.id} onClick={() => setSelectedProductId(row.id)} className={clsx('w-full text-left rounded-xl border px-3 py-2 transition', selectedProductId === row.id ? 'border-cyan-300 bg-cyan-50/70' : 'border-slate-200 bg-white hover:bg-slate-50')}>
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-semibold text-slate-800 text-sm line-clamp-2">{row.name}</p>
                    <span className={clsx('px-2 py-0.5 rounded-full text-[11px] font-semibold', statusClassName(row.status))}>{row.status}</span>
                  </div>
                  <p className="text-xs text-slate-500">{row.product_key}</p>
                  <p className="text-xs text-slate-500">{row.owner}</p>
                </button>
              ))}
              {(listResp?.items.length ?? 0) === 0 && <p className="text-sm text-slate-500">No products found.</p>}
            </div>
          </div>

          <form onSubmit={onCreateProduct} className="glass rounded-3xl border border-slate-200/60 p-4 space-y-2">
            <h3 className="text-sm font-semibold text-slate-800">{isZh ? '创建数据产品' : 'Create Product'}</h3>
            <input value={createForm.name} onChange={(e) => setCreateForm((prev) => ({ ...prev, name: e.target.value }))} placeholder="product name" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <textarea value={createForm.description} onChange={(e) => setCreateForm((prev) => ({ ...prev, description: e.target.value }))} rows={2} placeholder="description" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <div className="grid grid-cols-2 gap-2">
              <input value={createForm.domain} onChange={(e) => setCreateForm((prev) => ({ ...prev, domain: e.target.value }))} placeholder="domain" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
              <input value={createForm.category} onChange={(e) => setCreateForm((prev) => ({ ...prev, category: e.target.value }))} placeholder="category" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <select value={createForm.status} onChange={(e) => setCreateForm((prev) => ({ ...prev, status: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"><option value="DRAFT">DRAFT</option><option value="PUBLISHED">PUBLISHED</option></select>
              <select value={createForm.visibility} onChange={(e) => setCreateForm((prev) => ({ ...prev, visibility: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"><option value="PROJECT">PROJECT</option><option value="PRIVATE">PRIVATE</option><option value="ROLE_BASED">ROLE_BASED</option></select>
            </div>
            <input value={createForm.tags_text} onChange={(e) => setCreateForm((prev) => ({ ...prev, tags_text: e.target.value }))} placeholder="tags comma separated" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <input value={createForm.asset_ids_text} onChange={(e) => setCreateForm((prev) => ({ ...prev, asset_ids_text: e.target.value }))} placeholder="asset ids comma separated" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <textarea value={createForm.schema_payload_text} onChange={(e) => setCreateForm((prev) => ({ ...prev, schema_payload_text: e.target.value }))} rows={3} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-mono" />
            <textarea value={createForm.sla_payload_text} onChange={(e) => setCreateForm((prev) => ({ ...prev, sla_payload_text: e.target.value }))} rows={3} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-mono" />
            <textarea value={createForm.access_policy_payload_text} onChange={(e) => setCreateForm((prev) => ({ ...prev, access_policy_payload_text: e.target.value }))} rows={4} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-mono" />
            <button type="submit" disabled={operating} className="w-full rounded-xl bg-cyan-600 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60">{isZh ? '创建' : 'Create'}</button>
          </form>
        </div>

        <div className="xl:col-span-2 space-y-4">
          {!selectedProduct ? (
            <div className="glass rounded-3xl border border-slate-200/60 p-8 text-sm text-slate-500">{isZh ? '请选择一个产品查看详情。' : 'Select one product to view details.'}</div>
          ) : (
            <div className="glass rounded-3xl border border-slate-200/60 p-4 space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-lg font-semibold text-slate-900">{selectedProduct.name}</h3>
                  <p className="text-sm text-slate-500">{selectedProduct.product_key} | {selectedProduct.domain ?? 'UNSET'} | {selectedProduct.owner}</p>
                </div>
                <span className={clsx('px-2 py-1 rounded-full text-xs font-semibold', statusClassName(selectedProduct.status))}>{selectedProduct.status}</span>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Visibility</p><p className="font-semibold text-slate-800">{selectedProduct.visibility}</p></div>
                <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Asset Count</p><p className="font-semibold text-slate-800">{selectedProduct.asset_ids.length}</p></div>
                <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Subscriptions</p><p className="font-semibold text-slate-800">{detail?.usage_summary.subscription_total ?? 0}</p></div>
                <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Active Tokens</p><p className="font-semibold text-slate-800">{detail?.usage_summary.active_tokens ?? 0}</p></div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-2">
                <h4 className="text-sm font-semibold text-slate-800 flex items-center gap-2"><CheckCircle2 size={15} /> Product Actions</h4>
                <textarea value={actionForm.note} onChange={(e) => setActionForm((prev) => ({ ...prev, note: e.target.value }))} rows={2} placeholder="action note" className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                <input value={actionForm.request_reason} onChange={(e) => setActionForm((prev) => ({ ...prev, request_reason: e.target.value }))} placeholder="request reason" className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                <div className="grid grid-cols-2 gap-2">
                  <input type="number" min={1} max={8760} value={actionForm.expires_hours} onChange={(e) => setActionForm((prev) => ({ ...prev, expires_hours: Number(e.target.value || 720) }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                  <input value={selectedSubscriptionId ?? ''} onChange={(e) => setSelectedSubscriptionId(Number(e.target.value || 0) || null)} placeholder="subscription id" className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                </div>
                <textarea value={actionForm.usage_quota_payload_text} onChange={(e) => setActionForm((prev) => ({ ...prev, usage_quota_payload_text: e.target.value }))} rows={3} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-mono" />
                <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                  <button onClick={() => void onOperateProduct('PUBLISH')} disabled={operating || !selectedProduct.capabilities.can_edit} className="rounded-xl bg-emerald-600 text-white px-3 py-2 text-xs font-semibold disabled:opacity-60">Publish</button>
                  <button onClick={() => void onOperateProduct('ARCHIVE')} disabled={operating || !selectedProduct.capabilities.can_edit} className="rounded-xl bg-slate-700 text-white px-3 py-2 text-xs font-semibold disabled:opacity-60">Archive</button>
                  <button onClick={() => void onOperateProduct('UNARCHIVE')} disabled={operating || !selectedProduct.capabilities.can_edit} className="rounded-xl bg-cyan-700 text-white px-3 py-2 text-xs font-semibold disabled:opacity-60">Unarchive</button>
                  <button onClick={() => void onOperateProduct('REQUEST_SUBSCRIPTION')} disabled={operating} className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-60 inline-flex justify-center items-center gap-1"><Store size={12} />Request</button>
                  <button onClick={() => void onOperateProduct('APPROVE_SUBSCRIPTION')} disabled={operating} className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-60 inline-flex justify-center items-center gap-1"><CheckCircle2 size={12} />Approve</button>
                  <button onClick={() => void onOperateProduct('REJECT_SUBSCRIPTION')} disabled={operating} className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-60">Reject</button>
                  <button onClick={() => void onOperateProduct('CANCEL_SUBSCRIPTION')} disabled={operating} className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-60">Cancel</button>
                  <button onClick={() => void onOperateProduct('REVOKE_SUBSCRIPTION')} disabled={operating} className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-60">Revoke</button>
                  <button onClick={() => void onOperateProduct('ROTATE_TOKEN')} disabled={operating} className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-60 inline-flex justify-center items-center gap-1"><KeyRound size={12} />Rotate</button>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <h4 className="text-sm font-semibold text-slate-800 mb-2">Versions</h4>
                  <div className="space-y-2 max-h-64 overflow-auto">
                    {(detail?.versions ?? []).map((row) => (
                      <div key={row.id} className="rounded-xl border border-slate-200 p-2">
                        <div className="flex items-center justify-between">
                          <p className="text-xs font-semibold text-slate-800">v{row.version_no}</p>
                          <p className="text-xs text-slate-500">{row.created_at ? new Date(row.created_at).toLocaleString() : '-'}</p>
                        </div>
                        <p className="text-xs text-slate-500">{row.created_by}</p>
                        <p className="text-xs text-slate-700">{row.change_note ?? '-'}</p>
                      </div>
                    ))}
                    {(detail?.versions.length ?? 0) === 0 && <p className="text-sm text-slate-500">No versions.</p>}
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <h4 className="text-sm font-semibold text-slate-800 mb-2 flex items-center gap-2"><Copy size={14} /> Subscriptions</h4>
                  <div className="space-y-2 max-h-64 overflow-auto">
                    {(detail?.subscriptions ?? []).map((row) => (
                      <button key={row.id} onClick={() => setSelectedSubscriptionId(row.id)} className={clsx('w-full text-left rounded-xl border p-2', selectedSubscriptionId === row.id ? 'border-cyan-300 bg-cyan-50/70' : 'border-slate-200 bg-white')}>
                        <div className="flex items-center justify-between">
                          <p className="text-xs font-semibold text-slate-800">#{row.id} {row.subscriber}</p>
                          <span className={clsx('px-2 py-0.5 rounded-full text-[11px] font-semibold', subscriptionStatusClass(row.status))}>{row.status}</span>
                        </div>
                        <p className="text-xs text-slate-500">{row.request_reason ?? '-'}</p>
                        <p className="text-xs text-slate-500">{row.access_token ?? '-'}</p>
                      </button>
                    ))}
                    {(detail?.subscriptions.length ?? 0) === 0 && <p className="text-sm text-slate-500">No subscriptions.</p>}
                  </div>
                  {selectedSubscription && (
                    <div className="mt-2 rounded-xl border border-slate-200 bg-slate-50 p-2 text-xs text-slate-700">
                      Selected: #{selectedSubscription.id} | {selectedSubscription.subscriber} | {selectedSubscription.status}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

export default DataProductMarketplace
