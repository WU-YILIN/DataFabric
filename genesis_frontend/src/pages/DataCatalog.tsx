import { useEffect, useMemo, useState } from 'react'
import { ChevronRight, Filter, Plus, Search, X } from 'lucide-react'

import { clsx } from 'clsx'
import { useNavigate } from 'react-router-dom'
import { GenesisApi, type DataAsset, type DataAssetDetailResponse } from '../services/api'

type DataAssetFormState = {
  name: string
  asset_type: string
  source_system: string
  database_name: string
  object_name: string
  domain: string
  owner: string
  status: string
  tags: string
  description: string
  schema_definition: string
  upstream_asset_ids: string
  downstream_asset_ids: string
}

const defaultFormState: DataAssetFormState = {
  name: '',
  asset_type: 'TABLE',
  source_system: 'warehouse',
  database_name: '',
  object_name: '',
  domain: '',
  owner: '',
  status: 'ACTIVE',
  tags: '',
  description: '',
  schema_definition: '{\n  "columns": [\n    {"name": "id", "type": "string"}\n  ]\n}',
  upstream_asset_ids: '',
  downstream_asset_ids: '',
}

const DataCatalog = () => {
  const navigate = useNavigate()
  const [assets, setAssets] = useState<DataAsset[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [q, setQ] = useState('')
  const [assetTypeFilter, setAssetTypeFilter] = useState('')
  const [domainFilter, setDomainFilter] = useState('')
  const [sourceSystemFilter, setSourceSystemFilter] = useState('')
  const [ownerFilter, setOwnerFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const [selectedAssetId, setSelectedAssetId] = useState<number | null>(null)
  const [detail, setDetail] = useState<DataAssetDetailResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [formOpen, setFormOpen] = useState(false)
  const [editingAsset, setEditingAsset] = useState<DataAsset | null>(null)
  const [formState, setFormState] = useState<DataAssetFormState>(defaultFormState)
  const [formSubmitting, setFormSubmitting] = useState(false)

  const domains = useMemo(() => Array.from(new Set(assets.map((item) => item.domain).filter(Boolean))).sort(), [assets])
  const sourceSystems = useMemo(
    () => Array.from(new Set(assets.map((item) => item.source_system).filter(Boolean))).sort(),
    [assets],
  )
  const owners = useMemo(
    () => Array.from(new Set(assets.map((item) => item.owner).filter((item): item is string => Boolean(item)))).sort(),
    [assets],
  )

  const loadAssets = async () => {
    setLoading(true)
    setError(null)
    try {
      const rows = await GenesisApi.getDataAssets({
        q: q || undefined,
        asset_type: assetTypeFilter || undefined,
        domain: domainFilter || undefined,
        source_system: sourceSystemFilter || undefined,
        owner: ownerFilter || undefined,
        status: statusFilter || undefined,
      })
      setAssets(rows)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load data assets')
    } finally {
      setLoading(false)
    }
  }

  const loadDetail = async (assetId: number) => {
    setSelectedAssetId(assetId)
    setDetailLoading(true)
    setDetail(null)
    setError(null)
    try {
      const data = await GenesisApi.getDataAssetDetail(assetId)
      setDetail(data)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load data asset detail')
    } finally {
      setDetailLoading(false)
    }
  }

  useEffect(() => {
    void loadAssets()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const openCreateModal = () => {
    setEditingAsset(null)
    setFormState(defaultFormState)
    setFormOpen(true)
  }

  const openEditModal = (asset: DataAsset) => {
    setEditingAsset(asset)
    setFormState({
      name: asset.name,
      asset_type: asset.asset_type,
      source_system: asset.source_system,
      database_name: asset.database_name ?? '',
      object_name: asset.object_name,
      domain: asset.domain,
      owner: asset.owner ?? '',
      status: asset.status,
      tags: (asset.tags ?? []).join(', '),
      description: asset.description ?? '',
      schema_definition: JSON.stringify(asset.schema_definition ?? {}, null, 2),
      upstream_asset_ids: detail ? detail.lineage.upstream.map((item) => item.id).join(', ') : '',
      downstream_asset_ids: detail ? detail.lineage.downstream.map((item) => item.id).join(', ') : '',
    })
    setFormOpen(true)
  }

  const parseAssetIdList = (raw: string): number[] =>
    raw
      .split(',')
      .map((item) => Number(item.trim()))
      .filter((item) => Number.isFinite(item))

  const submitForm = async () => {
    setFormSubmitting(true)
    setError(null)
    try {
      let parsedSchema: Record<string, unknown> = {}
      try {
        parsedSchema = JSON.parse(formState.schema_definition || '{}')
      } catch {
        throw new Error('Schema definition must be valid JSON')
      }

      const tags = formState.tags
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)
      const upstream = parseAssetIdList(formState.upstream_asset_ids)
      const downstream = parseAssetIdList(formState.downstream_asset_ids)

      if (editingAsset) {
        await GenesisApi.updateDataAsset(editingAsset.id, {
          name: formState.name,
          source_system: formState.source_system,
          database_name: formState.database_name || null,
          object_name: formState.object_name,
          domain: formState.domain,
          owner: formState.owner || null,
          status: formState.status,
          tags,
          description: formState.description || null,
          schema_definition: parsedSchema,
          upstream_asset_ids: upstream,
          downstream_asset_ids: downstream,
        })
      } else {
        await GenesisApi.createDataAsset({
          name: formState.name,
          asset_type: formState.asset_type,
          source_system: formState.source_system,
          database_name: formState.database_name || null,
          object_name: formState.object_name,
          domain: formState.domain,
          owner: formState.owner || null,
          status: formState.status,
          tags,
          description: formState.description || null,
          schema_definition: parsedSchema,
          upstream_asset_ids: upstream,
          downstream_asset_ids: downstream,
        })
      }

      setFormOpen(false)
      await loadAssets()
      if (editingAsset?.id) {
        await loadDetail(editingAsset.id)
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? e?.message ?? 'Failed to save data asset')
    } finally {
      setFormSubmitting(false)
    }
  }

  const openExploreForAsset = (assetId: number) => {
    const params = new URLSearchParams({
      source_type: 'DATA_ASSET',
      source_id: String(assetId),
    })
    navigate(`/explore?${params.toString()}`)
  }

  const openKnowledgeForAsset = (assetId: number) => {
    const params = new URLSearchParams({
      source_type: 'DATA_ASSET',
      source_id: String(assetId),
    })
    navigate(`/knowledge?${params.toString()}`)
  }

  return (
    <div className="max-w-7xl mx-auto animate-in fade-in slide-in-from-bottom-8 duration-700">
      <div className="flex justify-between items-center mb-6">
        <header>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">Data Catalog</h2>
          <p className="text-slate-500 text-base">Register and track data assets, lineage, quality, and dependencies.</p>
        </header>
        <button
          onClick={openCreateModal}
          className="rounded-xl bg-cyan-600 text-white px-4 py-2.5 font-semibold flex items-center gap-2 hover:bg-cyan-500"
        >
          <Plus size={18} />
          Register Asset
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-rose-700 text-sm">{error}</div>
      )}

      <div className="glass rounded-3xl overflow-hidden shadow-sm border border-gray-200/50">
        <div className="p-4 border-b border-gray-200/50 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-6 gap-3 bg-gray-50/60">
          <div className="relative md:col-span-2 xl:col-span-2">
            <Search className="absolute left-3 top-2.5 text-gray-400" size={16} />
            <input
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search name / object / domain"
              className="w-full pl-9 pr-3 py-2.5 bg-white border border-gray-200 rounded-xl outline-none focus:ring-2 focus:ring-cyan-300/60"
            />
          </div>
          <select
            value={assetTypeFilter}
            onChange={(e) => setAssetTypeFilter(e.target.value)}
            className="px-3 py-2.5 bg-white border border-gray-200 rounded-xl outline-none"
          >
            <option value="">All Types</option>
            <option value="TABLE">TABLE</option>
            <option value="TOPIC">TOPIC</option>
            <option value="VIEW">VIEW</option>
            <option value="METRIC">METRIC</option>
          </select>
          <input
            value={domainFilter}
            onChange={(e) => setDomainFilter(e.target.value)}
            list="catalog-domains"
            placeholder="Domain"
            className="px-3 py-2.5 bg-white border border-gray-200 rounded-xl outline-none"
          />
          <input
            value={sourceSystemFilter}
            onChange={(e) => setSourceSystemFilter(e.target.value)}
            list="catalog-systems"
            placeholder="Source System"
            className="px-3 py-2.5 bg-white border border-gray-200 rounded-xl outline-none"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2.5 bg-white border border-gray-200 rounded-xl outline-none"
          >
            <option value="">All Status</option>
            <option value="ACTIVE">ACTIVE</option>
            <option value="DRAFT">DRAFT</option>
            <option value="DEPRECATED">DEPRECATED</option>
          </select>

          <input
            value={ownerFilter}
            onChange={(e) => setOwnerFilter(e.target.value)}
            list="catalog-owners"
            placeholder="Owner"
            className="px-3 py-2.5 bg-white border border-gray-200 rounded-xl outline-none"
          />

          <button
            onClick={loadAssets}
            className="md:col-span-2 xl:col-span-5 rounded-xl bg-slate-900 text-white px-4 py-2.5 font-medium flex items-center justify-center gap-2 hover:bg-slate-800"
          >
            <Filter size={16} />
            Apply Filters
          </button>
          <datalist id="catalog-domains">
            {domains.map((item) => (
              <option key={item} value={item} />
            ))}
          </datalist>
          <datalist id="catalog-systems">
            {sourceSystems.map((item) => (
              <option key={item} value={item} />
            ))}
          </datalist>
          <datalist id="catalog-owners">
            {owners.map((item) => (
              <option key={item} value={item} />
            ))}
          </datalist>
        </div>

        <div className="bg-white/60">
          {loading ? (
            <div className="p-12 text-center text-gray-400">Loading assets...</div>
          ) : (
            <ul className="divide-y divide-gray-100">
              {assets.map((asset) => (
                <li
                  key={asset.id}
                  className="group hover:bg-cyan-50/50 transition-colors cursor-pointer"
                  onClick={() => void loadDetail(asset.id)}
                >
                  <div className="flex items-center p-4 sm:px-6">
                    <div className="min-w-0 flex-1 grid grid-cols-1 md:grid-cols-7 gap-3 items-center">
                      <div className="md:col-span-2">
                        <p className="text-sm font-semibold text-slate-900 truncate">{asset.name}</p>
                        <p className="text-xs text-slate-500 truncate font-mono">{asset.object_name}</p>
                      </div>
                      <div className="text-sm text-slate-700">{asset.asset_type}</div>
                      <div className="text-sm text-slate-700">{asset.source_system}</div>
                      <div className="text-sm text-slate-700">{asset.domain}</div>
                      <div className="text-sm text-slate-600">{asset.owner ?? '-'}</div>
                      <div>
                        <span
                          className={clsx(
                            'px-2 py-1 rounded-full text-xs font-semibold',
                            asset.status === 'ACTIVE'
                              ? 'bg-emerald-100 text-emerald-700'
                              : asset.status === 'DEPRECATED'
                                ? 'bg-rose-100 text-rose-700'
                                : 'bg-slate-100 text-slate-700',
                          )}
                        >
                          {asset.status}
                        </span>
                      </div>
                    </div>
                    <ChevronRight size={18} className="text-gray-300 group-hover:text-cyan-600" />
                  </div>
                </li>
              ))}
              {!loading && assets.length === 0 && (
                <li className="p-10 text-center text-slate-500">No assets matched current filters.</li>
              )}
            </ul>
          )}
        </div>
      </div>

      {selectedAssetId && (
        <>
          <div
            className="fixed inset-0 bg-black/25 z-40"
            onClick={() => {
              setSelectedAssetId(null)
              setDetail(null)
            }}
          />
          <aside className="fixed right-0 top-0 h-screen w-[620px] bg-white z-50 border-l border-slate-200 shadow-2xl overflow-auto">
            <div className="p-5 border-b border-slate-200 flex items-center justify-between">
              <h3 className="font-bold text-slate-900 text-lg">Asset Detail</h3>
              <button
                onClick={() => {
                  setSelectedAssetId(null)
                  setDetail(null)
                }}
                className="p-2 rounded-lg hover:bg-slate-100"
              >
                <X size={16} />
              </button>
            </div>

            {detailLoading || !detail ? (
              <div className="p-8 text-slate-500">Loading detail...</div>
            ) : (
              <div className="p-5 space-y-6">
                <div className="space-y-1">
                  <p className="text-xs text-slate-500 uppercase tracking-wide">Basic Info</p>
                  <p className="text-xl font-semibold text-slate-900">{detail.asset.name}</p>
                  <p className="text-sm text-slate-600 font-mono">{detail.asset.object_name}</p>
                  <p className="text-sm text-slate-600">
                    Type: {detail.asset.asset_type} | System: {detail.asset.source_system} | Domain: {detail.asset.domain}
                  </p>
                  <p className="text-sm text-slate-600">
                    Owner: {detail.asset.owner || '-'} | Status: {detail.asset.status} | Version: {detail.asset.version}
                  </p>
                  <p className="text-sm text-slate-600">Tags: {detail.asset.tags?.length ? detail.asset.tags.join(', ') : '-'}</p>
                  <p className="text-sm text-slate-600">{detail.asset.description || '-'}</p>
                </div>

                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Schema</p>
                  <pre className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs overflow-auto text-slate-700">
                    {JSON.stringify(detail.asset.schema_definition, null, 2)}
                  </pre>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Lineage Upstream</p>
                    <div className="space-y-2">
                      {detail.lineage.upstream.length === 0 && <p className="text-sm text-slate-500">No upstream assets.</p>}
                      {detail.lineage.upstream.map((item) => (
                        <button
                          key={item.id}
                          onClick={() => void loadDetail(item.id)}
                          className="w-full text-left rounded-xl border border-slate-200 p-3 bg-white text-sm hover:bg-slate-50"
                        >
                          <p className="font-semibold text-slate-800">{item.name}</p>
                          <p className="text-xs text-slate-500 mt-1">
                            {item.asset_type} | {item.object_name}
                          </p>
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Lineage Downstream</p>
                    <div className="space-y-2">
                      {detail.lineage.downstream.length === 0 && <p className="text-sm text-slate-500">No downstream assets.</p>}
                      {detail.lineage.downstream.map((item) => (
                        <button
                          key={item.id}
                          onClick={() => void loadDetail(item.id)}
                          className="w-full text-left rounded-xl border border-slate-200 p-3 bg-white text-sm hover:bg-slate-50"
                        >
                          <p className="font-semibold text-slate-800">{item.name}</p>
                          <p className="text-xs text-slate-500 mt-1">
                            {item.asset_type} | {item.object_name}
                          </p>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Quality Rules</p>
                  <div className="space-y-2">
                    {detail.quality.rules.length === 0 && <p className="text-sm text-slate-500">No related quality rule.</p>}
                    {detail.quality.rules.map((item) => (
                      <div key={item.id} className="rounded-xl border border-slate-200 p-3 bg-white text-sm">
                        <p className="font-semibold text-slate-800">
                          {item.name} <span className="text-xs text-slate-500">({item.rule_type})</span>
                        </p>
                        <p className="text-xs text-slate-500 mt-1">
                          severity={item.severity} | status={item.status} | field={item.target_field || '-'}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Recent Alerts</p>
                  <div className="space-y-2">
                    {detail.quality.alerts.length === 0 && <p className="text-sm text-slate-500">No related alert.</p>}
                    {detail.quality.alerts.map((item) => (
                      <div key={item.id} className="rounded-xl border border-slate-200 p-3 bg-white text-sm">
                        <p className="font-semibold text-slate-800">{item.title}</p>
                        <p className="text-xs text-slate-500 mt-1">
                          {item.severity} | {item.status} | {new Date(item.created_at).toLocaleString()}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Related Events & Pipelines</p>
                  <div className="space-y-2">
                    {detail.relations.events.length === 0 && detail.relations.pipelines.length === 0 && (
                      <p className="text-sm text-slate-500">No direct dependencies found.</p>
                    )}
                    {detail.relations.events.map((item) => (
                      <div key={`event-${item.id}`} className="rounded-xl border border-slate-200 p-3 bg-white text-sm">
                        <p className="font-semibold text-slate-800">{item.code}</p>
                        <p className="text-xs text-slate-500 mt-1">
                          {item.name} | governance={item.governance_status}
                        </p>
                      </div>
                    ))}
                    {detail.relations.pipelines.map((item) => (
                      <div key={`pipeline-${item.id}`} className="rounded-xl border border-slate-200 p-3 bg-white text-sm">
                        <p className="font-semibold text-slate-800">
                          #{item.id} {item.flink_job_name}
                        </p>
                        <p className="text-xs text-slate-500 mt-1">
                          {item.status} | {item.topic_name}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Version History</p>
                  <div className="space-y-2">
                    {detail.version_history.length === 0 && <p className="text-sm text-slate-500">No version changes yet.</p>}
                    {detail.version_history.map((item) => (
                      <div key={item.id} className="rounded-xl border border-slate-200 p-3 bg-white text-sm">
                        <p className="font-semibold text-slate-800">
                          {item.from_version}
                          {' -> '}
                          {item.to_version}
                        </p>
                        <pre className="mt-2 text-[11px] bg-slate-50 rounded p-2 overflow-auto">
                          {JSON.stringify(item.diff, null, 2)}
                        </pre>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <button
                    onClick={() => openEditModal(detail.asset)}
                    className="rounded-xl bg-slate-900 text-white px-3 py-2.5 font-medium hover:bg-slate-800"
                  >
                    Edit Asset
                  </button>
                  <button
                    onClick={() => openExploreForAsset(detail.asset.id)}
                    className="rounded-xl bg-indigo-600 text-white px-3 py-2.5 font-medium hover:bg-indigo-500"
                  >
                    Open in Explore
                  </button>
                  <button
                    onClick={() => openKnowledgeForAsset(detail.asset.id)}
                    className="rounded-xl bg-emerald-600 text-white px-3 py-2.5 font-medium hover:bg-emerald-500"
                  >
                    Related Docs
                  </button>
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
            <div className="w-full max-w-3xl rounded-2xl border border-slate-200 bg-white shadow-2xl p-5 space-y-4 max-h-[95vh] overflow-auto">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-slate-900">{editingAsset ? 'Edit Asset' : 'Register Asset'}</h3>
                <button onClick={() => setFormOpen(false)} className="p-2 rounded hover:bg-slate-100">
                  <X size={16} />
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <input
                  value={formState.name}
                  onChange={(e) => setFormState((prev) => ({ ...prev, name: e.target.value }))}
                  placeholder="Name"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                />
                <select
                  value={formState.asset_type}
                  onChange={(e) => setFormState((prev) => ({ ...prev, asset_type: e.target.value }))}
                  disabled={Boolean(editingAsset)}
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                >
                  <option value="TABLE">TABLE</option>
                  <option value="TOPIC">TOPIC</option>
                  <option value="VIEW">VIEW</option>
                  <option value="METRIC">METRIC</option>
                </select>
                <input
                  value={formState.source_system}
                  onChange={(e) => setFormState((prev) => ({ ...prev, source_system: e.target.value }))}
                  placeholder="Source System"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                />
                <input
                  value={formState.database_name}
                  onChange={(e) => setFormState((prev) => ({ ...prev, database_name: e.target.value }))}
                  placeholder="Database Name"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                />
                <input
                  value={formState.object_name}
                  onChange={(e) => setFormState((prev) => ({ ...prev, object_name: e.target.value }))}
                  placeholder="Object Name (table/topic/view)"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                />
                <input
                  value={formState.domain}
                  onChange={(e) => setFormState((prev) => ({ ...prev, domain: e.target.value }))}
                  placeholder="Domain"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                />
                <input
                  value={formState.owner}
                  onChange={(e) => setFormState((prev) => ({ ...prev, owner: e.target.value }))}
                  placeholder="Owner"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                />
                <select
                  value={formState.status}
                  onChange={(e) => setFormState((prev) => ({ ...prev, status: e.target.value }))}
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                >
                  <option value="ACTIVE">ACTIVE</option>
                  <option value="DRAFT">DRAFT</option>
                  <option value="DEPRECATED">DEPRECATED</option>
                </select>
                <input
                  value={formState.tags}
                  onChange={(e) => setFormState((prev) => ({ ...prev, tags: e.target.value }))}
                  placeholder="Tags (comma separated)"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none md:col-span-2"
                />
                <textarea
                  value={formState.description}
                  onChange={(e) => setFormState((prev) => ({ ...prev, description: e.target.value }))}
                  placeholder="Description"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none md:col-span-2 h-24"
                />
                <textarea
                  value={formState.schema_definition}
                  onChange={(e) => setFormState((prev) => ({ ...prev, schema_definition: e.target.value }))}
                  placeholder="Schema Definition JSON"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none md:col-span-2 h-44 font-mono text-sm"
                />
                <input
                  value={formState.upstream_asset_ids}
                  onChange={(e) => setFormState((prev) => ({ ...prev, upstream_asset_ids: e.target.value }))}
                  placeholder="Upstream Asset IDs (comma separated)"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                />
                <input
                  value={formState.downstream_asset_ids}
                  onChange={(e) => setFormState((prev) => ({ ...prev, downstream_asset_ids: e.target.value }))}
                  placeholder="Downstream Asset IDs (comma separated)"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                />
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
                  {formSubmitting ? 'Saving...' : editingAsset ? 'Save Changes' : 'Register Asset'}
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default DataCatalog
