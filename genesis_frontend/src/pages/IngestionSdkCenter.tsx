import { FormEvent, useEffect, useMemo, useState } from 'react'
import { clsx } from 'clsx'
import { CloudUpload, KeyRound, RefreshCw, ServerCog, Wifi } from 'lucide-react'

import {
  GenesisApi,
  type IngestionChannelDetailResponse,
  type IngestionChannelItem,
  type IngestionChannelListResponse,
  type IngestionOptionsResponse,
  type IngestionOverviewResponse,
} from '../services/api'

const IngestionSdkCenter = () => {
  const [overview, setOverview] = useState<IngestionOverviewResponse | null>(null)
  const [options, setOptions] = useState<IngestionOptionsResponse | null>(null)
  const [listResp, setListResp] = useState<IngestionChannelListResponse | null>(null)
  const [detail, setDetail] = useState<IngestionChannelDetailResponse | null>(null)
  const [selectedChannelId, setSelectedChannelId] = useState<number | null>(null)

  const [filters, setFilters] = useState({
    q: '',
    platform: 'ALL',
    environment: 'ALL',
    status: 'ALL',
  })

  const [createForm, setCreateForm] = useState({
    platform: 'WEB',
    app_name: '',
    environment: 'PROD',
    endpoint_domain: 'ingest.genesis.local',
    sampling_mode: 'ALL',
    sampling_rate: 1,
    blocked_events_text: '',
    sdk_version: '1.0.0',
  })

  const [editForm, setEditForm] = useState({
    status: 'ACTIVE',
    sampling_mode: 'ALL',
    sampling_rate: 1,
    blocked_events_text: '',
    sdk_version: '1.0.0',
    endpoint_domain: '',
    endpoint_path: '/api/v1/ingestion/gateway/events',
  })

  const [sampleEventForm, setSampleEventForm] = useState({
    event_name: 'commerce.order_created',
    event_ts: new Date().toISOString(),
    payloadJson: '{\n  "order_id": "o_1001",\n  "user_id": "u_1001"\n}',
  })
  const [gatewayResult, setGatewayResult] = useState<{
    status: string
    reason_code?: string | null
    request_id: string
  } | null>(null)

  const [loading, setLoading] = useState(false)
  const [operating, setOperating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const parseJsonObject = (text: string): Record<string, unknown> | null => {
    try {
      const value = JSON.parse(text)
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        return value as Record<string, unknown>
      }
    } catch {
      return null
    }
    return null
  }

  const loadOverview = async () => {
    const data = await GenesisApi.getIngestionOverview()
    setOverview(data)
  }

  const loadOptions = async () => {
    const data = await GenesisApi.getIngestionOptions()
    setOptions(data)
  }

  const loadChannels = async () => {
    const data = await GenesisApi.getIngestionChannels({
      q: filters.q.trim() || undefined,
      platform: filters.platform === 'ALL' ? undefined : filters.platform,
      environment: filters.environment === 'ALL' ? undefined : filters.environment,
      status: filters.status === 'ALL' ? undefined : filters.status,
      limit: 200,
      offset: 0,
    })
    setListResp(data)
    if (!selectedChannelId && data.items.length > 0) {
      setSelectedChannelId(data.items[0].id)
    }
    if (selectedChannelId && !data.items.find((item) => item.id === selectedChannelId)) {
      setSelectedChannelId(data.items[0]?.id ?? null)
    }
  }

  const loadDetail = async (channelId: number) => {
    const data = await GenesisApi.getIngestionChannelDetail(channelId)
    setDetail(data)
    const c = data.channel
    setEditForm({
      status: c.status,
      sampling_mode: c.sampling_mode,
      sampling_rate: c.sampling_rate,
      blocked_events_text: (c.blocked_events ?? []).join(', '),
      sdk_version: c.sdk_version,
      endpoint_domain: c.endpoint_domain,
      endpoint_path: c.endpoint_path,
    })
  }

  const refreshAll = async () => {
    setLoading(true)
    setError(null)
    try {
      await Promise.all([loadOverview(), loadOptions(), loadChannels()])
      if (selectedChannelId != null) {
        await loadDetail(selectedChannelId)
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load ingestion center')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refreshAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (selectedChannelId != null) {
      void loadDetail(selectedChannelId).catch(() => setDetail(null))
    } else {
      setDetail(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedChannelId])

  const onApplyFilters = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await loadChannels()
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load channels')
    } finally {
      setLoading(false)
    }
  }

  const onCreateChannel = async (event: FormEvent) => {
    event.preventDefault()
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const created = await GenesisApi.createIngestionChannel({
        platform: createForm.platform,
        app_name: createForm.app_name.trim(),
        environment: createForm.environment,
        endpoint_domain: createForm.endpoint_domain.trim(),
        sampling_mode: createForm.sampling_mode,
        sampling_rate: Number(createForm.sampling_rate),
        blocked_events: createForm.blocked_events_text
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
        sdk_version: createForm.sdk_version.trim(),
      })
      setMessage(`Channel created: ${created.channel.app_id}`)
      setCreateForm((prev) => ({ ...prev, app_name: '', blocked_events_text: '' }))
      await Promise.all([loadOverview(), loadChannels()])
      setSelectedChannelId(created.channel.id)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Create channel failed')
    } finally {
      setOperating(false)
    }
  }

  const onUpdateChannel = async () => {
    if (!detail) return
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const updated = await GenesisApi.updateIngestionChannel(detail.channel.id, {
        status: editForm.status,
        sampling_mode: editForm.sampling_mode,
        sampling_rate: Number(editForm.sampling_rate),
        blocked_events: editForm.blocked_events_text
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
        sdk_version: editForm.sdk_version.trim(),
        endpoint_domain: editForm.endpoint_domain.trim(),
        endpoint_path: editForm.endpoint_path.trim(),
      })
      setMessage(`Channel updated: ${updated.channel.app_id}`)
      await Promise.all([loadOverview(), loadChannels(), loadDetail(updated.channel.id)])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Update channel failed')
    } finally {
      setOperating(false)
    }
  }

  const onRotateKey = async () => {
    if (!detail) return
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const rotated = await GenesisApi.rotateIngestionChannelKey(detail.channel.id, {
        reason: 'Rotate from ingestion sdk center',
      })
      setMessage(`Key rotated for ${rotated.channel.app_id}`)
      await Promise.all([loadOverview(), loadChannels(), loadDetail(rotated.channel.id)])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Rotate key failed')
    } finally {
      setOperating(false)
    }
  }

  const onSendSampleEvent = async () => {
    if (!detail) return
    const payload = parseJsonObject(sampleEventForm.payloadJson)
    if (!payload) {
      setError('Sample payload must be JSON object')
      return
    }

    const ingestKey = detail.quickstart.headers['X-INGEST-KEY']
    if (!ingestKey) {
      setError('No ingest key available in quickstart')
      return
    }

    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const result = await GenesisApi.ingestGatewayEvent(ingestKey, {
        app_id: detail.channel.app_id,
        event_name: sampleEventForm.event_name.trim(),
        event_ts: sampleEventForm.event_ts,
        sdk_version: detail.channel.sdk_version,
        payload,
      })
      setGatewayResult({
        status: result.status,
        reason_code: result.reason_code,
        request_id: result.request_id,
      })
      setMessage(`Gateway result: ${result.status}`)
      await Promise.all([loadOverview(), loadChannels(), loadDetail(detail.channel.id)])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Gateway send failed')
    } finally {
      setOperating(false)
    }
  }

  const selectedChannel: IngestionChannelItem | null = detail?.channel ?? null
  const platforms = useMemo(() => ['ALL', ...(listResp?.facets.platforms.map((item) => item.platform) ?? options?.platforms ?? [])], [listResp?.facets.platforms, options?.platforms])
  const environments = useMemo(() => ['ALL', ...(listResp?.facets.environments.map((item) => item.environment) ?? options?.environments ?? [])], [listResp?.facets.environments, options?.environments])
  const statuses = useMemo(() => ['ALL', ...(listResp?.facets.statuses.map((item) => item.status) ?? options?.statuses ?? [])], [listResp?.facets.statuses, options?.statuses])

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">Ingestion & SDK Center</h2>
          <p className="text-slate-500 text-base">Manage ingestion channels, SDK config, and verify gateway acceptance flow.</p>
        </div>
        <button onClick={() => void refreshAll()} disabled={loading || operating} className="rounded-xl bg-slate-900 text-white px-4 py-2.5 font-medium hover:bg-slate-800 disabled:opacity-60 flex items-center gap-2">
          <RefreshCw size={16} />
          Refresh
        </button>
      </header>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
      {message && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>}

      <section className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Channels</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.total_channels ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Active</p><p className="text-2xl font-bold text-emerald-700">{overview?.summary.active_channels ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Inactive</p><p className="text-2xl font-bold text-slate-700">{overview?.summary.inactive_channels ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Events 7d</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.events_7d ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Accepted 7d</p><p className="text-2xl font-bold text-emerald-700">{overview?.summary.accepted_7d ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">Rejected 7d</p><p className="text-2xl font-bold text-rose-700">{overview?.summary.rejected_7d ?? 0}</p></div>
      </section>

      <form onSubmit={onApplyFilters} className="glass rounded-3xl border border-slate-200/60 p-4">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          <input value={filters.q} onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))} placeholder="search app/platform/environment" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
          <select value={filters.platform} onChange={(e) => setFilters((prev) => ({ ...prev, platform: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{platforms.map((item) => <option key={item} value={item}>{item}</option>)}</select>
          <select value={filters.environment} onChange={(e) => setFilters((prev) => ({ ...prev, environment: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{environments.map((item) => <option key={item} value={item}>{item}</option>)}</select>
          <select value={filters.status} onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{statuses.map((item) => <option key={item} value={item}>{item}</option>)}</select>
          <button type="submit" className="rounded-xl bg-cyan-600 text-white px-4 py-2 text-sm font-semibold">Apply Filters</button>
        </div>
      </form>

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="space-y-4">
          <div className="glass rounded-3xl border border-slate-200/60 p-4">
            <h3 className="text-sm font-semibold text-slate-800 mb-3 flex items-center gap-2"><Wifi size={16} /> Channels</h3>
            <div className="space-y-2 max-h-[30rem] overflow-auto">
              {(listResp?.items ?? []).map((item) => (
                <button key={item.id} onClick={() => setSelectedChannelId(item.id)} className={clsx('w-full text-left rounded-xl border px-3 py-2 transition', selectedChannelId === item.id ? 'border-cyan-300 bg-cyan-50/70' : 'border-slate-200 bg-white hover:bg-slate-50')}>
                  <div className="flex items-center justify-between">
                    <p className="font-semibold text-slate-800 text-sm">{item.app_name}</p>
                    <span className={clsx('px-2 py-0.5 rounded-full text-xs font-semibold', item.status === 'ACTIVE' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600')}>{item.status}</span>
                  </div>
                  <p className="text-xs text-slate-500">{item.platform} | {item.environment}</p>
                  <p className="text-xs text-slate-500">{item.app_id}</p>
                </button>
              ))}
            </div>
          </div>

          <form onSubmit={onCreateChannel} className="glass rounded-3xl border border-slate-200/60 p-4 space-y-2">
            <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2"><CloudUpload size={16} /> New Channel</h3>
            <div className="grid grid-cols-2 gap-2">
              <select value={createForm.platform} onChange={(e) => setCreateForm((prev) => ({ ...prev, platform: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{(options?.platforms ?? ['WEB']).map((item) => <option key={item} value={item}>{item}</option>)}</select>
              <select value={createForm.environment} onChange={(e) => setCreateForm((prev) => ({ ...prev, environment: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{(options?.environments ?? ['PROD']).map((item) => <option key={item} value={item}>{item}</option>)}</select>
            </div>
            <input value={createForm.app_name} onChange={(e) => setCreateForm((prev) => ({ ...prev, app_name: e.target.value }))} placeholder="app name" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <input value={createForm.endpoint_domain} onChange={(e) => setCreateForm((prev) => ({ ...prev, endpoint_domain: e.target.value }))} placeholder="endpoint domain" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <div className="grid grid-cols-2 gap-2">
              <select value={createForm.sampling_mode} onChange={(e) => setCreateForm((prev) => ({ ...prev, sampling_mode: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{(options?.sampling_modes ?? ['ALL']).map((item) => <option key={item} value={item}>{item}</option>)}</select>
              <input type="number" min={0} max={1} step={0.01} value={createForm.sampling_rate} onChange={(e) => setCreateForm((prev) => ({ ...prev, sampling_rate: Number(e.target.value || 0) }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            </div>
            <input value={createForm.sdk_version} onChange={(e) => setCreateForm((prev) => ({ ...prev, sdk_version: e.target.value }))} placeholder="sdk version" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <input value={createForm.blocked_events_text} onChange={(e) => setCreateForm((prev) => ({ ...prev, blocked_events_text: e.target.value }))} placeholder="blocked events (comma separated)" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <button type="submit" disabled={operating} className="w-full rounded-xl bg-cyan-600 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60">Create</button>
          </form>
        </div>

        <div className="xl:col-span-2 space-y-4">
          {!selectedChannel ? (
            <div className="glass rounded-3xl border border-slate-200/60 p-8 text-sm text-slate-500">Select one channel to view details.</div>
          ) : (
            <>
              <div className="glass rounded-3xl border border-slate-200/60 p-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="text-lg font-semibold text-slate-900">{selectedChannel.app_name}</h3>
                    <p className="text-sm text-slate-500">{selectedChannel.app_id} | {selectedChannel.platform} | {selectedChannel.environment}</p>
                    <p className="text-xs text-slate-500">Ingest key: {selectedChannel.ingest_key}</p>
                  </div>
                  <button onClick={() => void onRotateKey()} disabled={operating} className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60 inline-flex items-center gap-2">
                    <KeyRound size={14} />
                    Rotate Key
                  </button>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                  <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Accepted</p><p className="font-semibold text-slate-800">{selectedChannel.accepted_events_count}</p></div>
                  <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Rejected</p><p className="font-semibold text-slate-800">{selectedChannel.rejected_events_count}</p></div>
                  <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Last Seen</p><p className="font-semibold text-slate-800">{selectedChannel.last_seen_at ? new Date(selectedChannel.last_seen_at).toLocaleString() : '-'}</p></div>
                  <div className="rounded-lg border border-slate-200 p-2"><p className="text-slate-500">Endpoint</p><p className="font-semibold text-slate-800 break-all">{selectedChannel.endpoint}</p></div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-2">
                    <h4 className="text-sm font-semibold text-slate-800 flex items-center gap-2"><ServerCog size={15} /> Channel Config</h4>
                    <div className="grid grid-cols-2 gap-2">
                      <select value={editForm.status} onChange={(e) => setEditForm((prev) => ({ ...prev, status: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm">
                        <option value="ACTIVE">ACTIVE</option>
                        <option value="INACTIVE">INACTIVE</option>
                      </select>
                      <select value={editForm.sampling_mode} onChange={(e) => setEditForm((prev) => ({ ...prev, sampling_mode: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm">
                        <option value="ALL">ALL</option>
                        <option value="RATE">RATE</option>
                        <option value="NONE">NONE</option>
                      </select>
                    </div>
                    <input type="number" min={0} max={1} step={0.01} value={editForm.sampling_rate} onChange={(e) => setEditForm((prev) => ({ ...prev, sampling_rate: Number(e.target.value || 0) }))} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                    <input value={editForm.endpoint_domain} onChange={(e) => setEditForm((prev) => ({ ...prev, endpoint_domain: e.target.value }))} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                    <input value={editForm.endpoint_path} onChange={(e) => setEditForm((prev) => ({ ...prev, endpoint_path: e.target.value }))} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                    <input value={editForm.sdk_version} onChange={(e) => setEditForm((prev) => ({ ...prev, sdk_version: e.target.value }))} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                    <input value={editForm.blocked_events_text} onChange={(e) => setEditForm((prev) => ({ ...prev, blocked_events_text: e.target.value }))} placeholder="blocked events comma separated" className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                    <button onClick={() => void onUpdateChannel()} disabled={operating} className="w-full rounded-xl bg-cyan-600 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60">Save Config</button>
                  </div>

                  <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-2">
                    <h4 className="text-sm font-semibold text-slate-800 flex items-center gap-2"><CloudUpload size={15} /> Gateway Test</h4>
                    <input value={sampleEventForm.event_name} onChange={(e) => setSampleEventForm((prev) => ({ ...prev, event_name: e.target.value }))} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                    <input value={sampleEventForm.event_ts} onChange={(e) => setSampleEventForm((prev) => ({ ...prev, event_ts: e.target.value }))} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                    <textarea value={sampleEventForm.payloadJson} onChange={(e) => setSampleEventForm((prev) => ({ ...prev, payloadJson: e.target.value }))} rows={7} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-mono" />
                    <button onClick={() => void onSendSampleEvent()} disabled={operating} className="w-full rounded-xl bg-slate-900 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60">Send Sample Event</button>
                    {gatewayResult && (
                      <div className={clsx('rounded-xl border px-3 py-2 text-xs', gatewayResult.status === 'ACCEPTED' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : gatewayResult.status === 'SAMPLED_OUT' ? 'border-amber-200 bg-amber-50 text-amber-700' : 'border-rose-200 bg-rose-50 text-rose-700')}>
                        {gatewayResult.status} | {gatewayResult.reason_code ?? '-'} | {gatewayResult.request_id}
                      </div>
                    )}
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <h4 className="text-sm font-semibold text-slate-800 mb-2">SDK Quickstart</h4>
                  <pre className="text-xs text-slate-700 whitespace-pre-wrap break-all bg-slate-50 border border-slate-200 rounded-xl p-3">{detail?.quickstart.snippet}</pre>
                </div>
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  )
}

export default IngestionSdkCenter
