import { useEffect, useMemo, useState } from 'react'
import { ChevronRight, Filter, Plus, Search, X } from 'lucide-react'
import { clsx } from 'clsx'
import { useNavigate } from 'react-router-dom'

import { GenesisApi, type EventDetailResponse, type TrackingEvent } from '../services/api'

type EventFormState = {
  code: string
  name: string
  description: string
  domain: string
  owner: string
  tags: string
  status: string
  properties: string
}

const defaultFormState: EventFormState = {
  code: '',
  name: '',
  description: '',
  domain: '',
  owner: '',
  tags: '',
  status: 'draft',
  properties: '{\n  "user_id": "string",\n  "timestamp": "iso8601"\n}',
}

const Events = () => {
  const navigate = useNavigate()
  const [events, setEvents] = useState<TrackingEvent[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [governanceFilter, setGovernanceFilter] = useState('')
  const [ownerFilter, setOwnerFilter] = useState('')
  const [domainFilter, setDomainFilter] = useState('')

  const [selectedEventId, setSelectedEventId] = useState<number | null>(null)
  const [detail, setDetail] = useState<EventDetailResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [formOpen, setFormOpen] = useState(false)
  const [editingEvent, setEditingEvent] = useState<TrackingEvent | null>(null)
  const [formState, setFormState] = useState<EventFormState>(defaultFormState)
  const [formSubmitting, setFormSubmitting] = useState(false)

  const owners = useMemo(
    () =>
      Array.from(
        new Set(events.map((event) => event.owner).filter((owner): owner is string => Boolean(owner))),
      ),
    [events],
  )
  const domains = useMemo(
    () => Array.from(new Set(events.map((event) => event.domain).filter(Boolean))).sort(),
    [events],
  )

  const loadEvents = async () => {
    setLoading(true)
    setError(null)
    try {
      const rows = await GenesisApi.searchEvents({
        q: query || undefined,
        status: statusFilter || undefined,
        governance_status: governanceFilter || undefined,
        owner: ownerFilter || undefined,
        domain: domainFilter || undefined,
      })
      setEvents(rows)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load event catalog')
    } finally {
      setLoading(false)
    }
  }

  const loadEventDetail = async (eventId: number) => {
    setSelectedEventId(eventId)
    setDetailLoading(true)
    setError(null)
    setDetail(null)
    try {
      const data = await GenesisApi.getEventDetail(eventId)
      setDetail(data)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load event detail')
    } finally {
      setDetailLoading(false)
    }
  }

  useEffect(() => {
    void loadEvents()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const openCreateModal = () => {
    setEditingEvent(null)
    setFormState(defaultFormState)
    setFormOpen(true)
  }

  const openEditModal = (event: TrackingEvent) => {
    setEditingEvent(event)
    setFormState({
      code: event.code,
      name: event.name,
      description: event.description ?? '',
      domain: event.domain,
      owner: event.owner ?? '',
      tags: (event.tags ?? []).join(', '),
      status: event.status,
      properties: JSON.stringify(event.properties ?? {}, null, 2),
    })
    setFormOpen(true)
  }

  const submitForm = async () => {
    setFormSubmitting(true)
    setError(null)
    try {
      let parsedProperties: Record<string, unknown> = {}
      try {
        parsedProperties = JSON.parse(formState.properties)
      } catch {
        throw new Error('Properties must be valid JSON')
      }

      const tags = formState.tags
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)

      if (editingEvent) {
        await GenesisApi.updateEvent(editingEvent.id, {
          name: formState.name,
          description: formState.description,
          domain: formState.domain,
          owner: formState.owner || null,
          tags,
          status: formState.status,
          properties: parsedProperties,
        })
      } else {
        await GenesisApi.createEvent({
          code: formState.code.trim(),
          name: formState.name,
          description: formState.description,
          domain: formState.domain,
          owner: formState.owner || null,
          tags,
          status: formState.status,
          properties: parsedProperties,
        })
      }

      setFormOpen(false)
      await loadEvents()
      if (editingEvent?.id) {
        await loadEventDetail(editingEvent.id)
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? e?.message ?? 'Failed to save event')
    } finally {
      setFormSubmitting(false)
    }
  }

  const launchGovernance = async (eventId: number) => {
    try {
      const payload = await GenesisApi.getEventGovernancePayload(eventId)
      const params = new URLSearchParams({
        event_id: String(payload.event_id),
        name: payload.name,
        description: payload.description,
        properties: JSON.stringify(payload.properties ?? {}, null, 2),
      })
      navigate(`/governance?${params.toString()}`)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to prepare governance payload')
    }
  }

  const openExploreForEvent = (eventId: number) => {
    const params = new URLSearchParams({
      source_type: 'EVENT',
      source_id: String(eventId),
    })
    navigate(`/explore?${params.toString()}`)
  }

  const openKnowledgeForEvent = (eventId: number) => {
    const params = new URLSearchParams({
      source_type: 'TRACKING_EVENT',
      source_id: String(eventId),
    })
    navigate(`/knowledge?${params.toString()}`)
  }

  return (
    <div className="max-w-7xl mx-auto animate-in fade-in slide-in-from-bottom-8 duration-700">
      <div className="flex justify-between items-center mb-6">
        <header>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">Event Catalog</h2>
          <p className="text-slate-500 text-base">Tenant/project scoped event definitions and governance history.</p>
        </header>
        <button
          onClick={openCreateModal}
          className="rounded-xl bg-cyan-600 text-white px-4 py-2.5 font-semibold flex items-center gap-2 hover:bg-cyan-500"
        >
          <Plus size={18} />
          New Event
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-rose-700 text-sm">
          {error}
        </div>
      )}

      <div className="glass rounded-3xl overflow-hidden shadow-sm border border-gray-200/50">
        <div className="p-4 border-b border-gray-200/50 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-6 gap-3 bg-gray-50/60">
          <div className="relative md:col-span-2 xl:col-span-2">
            <Search className="absolute left-3 top-2.5 text-gray-400" size={16} />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search code / name / domain"
              className="w-full pl-9 pr-3 py-2.5 bg-white border border-gray-200 rounded-xl outline-none focus:ring-2 focus:ring-cyan-300/60"
            />
          </div>
          <input
            value={domainFilter}
            onChange={(e) => setDomainFilter(e.target.value)}
            list="event-domains"
            placeholder="Domain"
            className="px-3 py-2.5 bg-white border border-gray-200 rounded-xl outline-none"
          />
          <input
            value={ownerFilter}
            onChange={(e) => setOwnerFilter(e.target.value)}
            list="event-owners"
            placeholder="Owner"
            className="px-3 py-2.5 bg-white border border-gray-200 rounded-xl outline-none"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2.5 bg-white border border-gray-200 rounded-xl outline-none"
          >
            <option value="">All status</option>
            <option value="draft">draft</option>
            <option value="active">active</option>
            <option value="deprecated">deprecated</option>
          </select>
          <select
            value={governanceFilter}
            onChange={(e) => setGovernanceFilter(e.target.value)}
            className="px-3 py-2.5 bg-white border border-gray-200 rounded-xl outline-none"
          >
            <option value="">All governance</option>
            <option value="NOT_CHECKED">NOT_CHECKED</option>
            <option value="APPROVED">APPROVED</option>
            <option value="NEEDS_REVISION">NEEDS_REVISION</option>
            <option value="REJECTED">REJECTED</option>
          </select>

          <button
            onClick={loadEvents}
            className="md:col-span-2 xl:col-span-6 mt-1 rounded-xl bg-slate-900 text-white px-4 py-2.5 font-medium flex items-center justify-center gap-2 hover:bg-slate-800"
          >
            <Filter size={16} />
            Apply Filters
          </button>
          <datalist id="event-domains">
            {domains.map((domain) => (
              <option key={domain} value={domain} />
            ))}
          </datalist>
          <datalist id="event-owners">
            {owners.map((owner) => (
              <option key={owner} value={owner} />
            ))}
          </datalist>
        </div>

        <div className="bg-white/60">
          {loading ? (
            <div className="p-12 text-center text-gray-400">Loading events...</div>
          ) : (
            <ul className="divide-y divide-gray-100">
              {events.map((event) => (
                <li
                  key={event.id}
                  className="group hover:bg-cyan-50/50 transition-colors cursor-pointer"
                  onClick={() => void loadEventDetail(event.id)}
                >
                  <div className="flex items-center p-4 sm:px-6">
                    <div className="min-w-0 flex-1 grid grid-cols-1 md:grid-cols-6 gap-3 items-center">
                      <div className="md:col-span-2">
                        <p className="text-xs font-semibold text-cyan-700 truncate font-mono">{event.code}</p>
                        <p className="text-sm font-semibold text-slate-900 truncate">{event.name}</p>
                      </div>
                      <div className="text-sm text-slate-700">{event.domain}</div>
                      <div className="text-sm text-slate-600">{event.owner ?? '-'}</div>
                      <div>
                        <span className="px-2 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700">
                          {event.status}
                        </span>
                      </div>
                      <div>
                        <span
                          className={clsx(
                            'px-2 py-1 rounded-full text-xs font-semibold',
                            event.governance_status === 'APPROVED'
                              ? 'bg-emerald-100 text-emerald-700'
                              : event.governance_status === 'REJECTED'
                                ? 'bg-rose-100 text-rose-700'
                                : event.governance_status === 'NEEDS_REVISION'
                                  ? 'bg-amber-100 text-amber-700'
                                  : 'bg-slate-100 text-slate-600',
                          )}
                        >
                          {event.governance_status}
                        </span>
                      </div>
                    </div>
                    <ChevronRight size={18} className="text-gray-300 group-hover:text-cyan-600" />
                  </div>
                </li>
              ))}
              {!loading && events.length === 0 && (
                <li className="p-10 text-center text-slate-500">No events matched current filters.</li>
              )}
            </ul>
          )}
        </div>
      </div>

      {selectedEventId && (
        <>
          <div
            className="fixed inset-0 bg-black/25 z-40"
            onClick={() => {
              setSelectedEventId(null)
              setDetail(null)
            }}
          />
          <aside className="fixed right-0 top-0 h-screen w-[560px] bg-white z-50 border-l border-slate-200 shadow-2xl overflow-auto">
            <div className="p-5 border-b border-slate-200 flex items-center justify-between">
              <h3 className="font-bold text-slate-900 text-lg">Event Detail</h3>
              <button
                onClick={() => {
                  setSelectedEventId(null)
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
                  <p className="text-sm font-semibold text-cyan-700 font-mono">{detail.event.code}</p>
                  <p className="text-xl font-semibold text-slate-900">{detail.event.name}</p>
                  <p className="text-sm text-slate-600">{detail.event.description || '-'}</p>
                  <p className="text-sm text-slate-600">Owner: {detail.event.owner || '-'}</p>
                  <p className="text-sm text-slate-600">
                    Tags: {detail.event.tags && detail.event.tags.length ? detail.event.tags.join(', ') : '-'}
                  </p>
                  <p className="text-sm text-slate-600">
                    Version: {detail.event.version} | Governance: {detail.event.governance_status}
                  </p>
                </div>

                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Schema</p>
                  <pre className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs overflow-auto text-slate-700">
                    {JSON.stringify(detail.event.properties, null, 2)}
                  </pre>
                </div>

                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Governance Records</p>
                  <div className="space-y-2">
                    {detail.governance_records.length === 0 && (
                      <p className="text-sm text-slate-500">No governance records yet.</p>
                    )}
                    {detail.governance_records.map((row) => (
                      <div key={row.id} className="rounded-xl border border-slate-200 p-3 bg-white">
                        <p className="text-sm font-semibold text-slate-900">
                          {row.verdict} ({Math.round(row.score * 100)}%)
                        </p>
                        <p className="text-xs text-slate-500 mt-1">{row.reasoning}</p>
                        <p className="text-[11px] text-slate-400 mt-1">
                          {row.actor_id} | {new Date(row.created_at).toLocaleString()}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Related Pipelines</p>
                  <div className="space-y-2">
                    {detail.related_pipelines.length === 0 && (
                      <p className="text-sm text-slate-500">No related pipeline.</p>
                    )}
                    {detail.related_pipelines.map((row) => (
                      <div key={row.id} className="rounded-xl border border-slate-200 p-3 bg-white text-sm">
                        <p className="font-semibold text-slate-800">
                          #{row.id} {row.flink_job_name}
                        </p>
                        <p className="text-xs text-slate-500 mt-1">
                          {row.status} | {row.topic_name}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Data Quality Rules</p>
                  <div className="space-y-2">
                    {detail.data_quality_rules.length === 0 && (
                      <p className="text-sm text-slate-500">No linked data quality rules.</p>
                    )}
                    {detail.data_quality_rules.map((row) => (
                      <div key={row.id} className="rounded-xl border border-slate-200 p-3 bg-white text-sm">
                        <div className="flex items-center justify-between gap-2">
                          <p className="font-semibold text-slate-800">{row.name}</p>
                          <span className="text-[11px] rounded-full px-2 py-0.5 bg-slate-100 text-slate-700">
                            {row.severity}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 mt-1">
                          {row.rule_type}
                          {row.target_field ? ` | field: ${row.target_field}` : ''}
                          {row.operator ? ` | op: ${row.operator}` : ''}
                        </p>
                        {row.description && <p className="text-xs text-slate-600 mt-1">{row.description}</p>}
                        <pre className="mt-2 text-[11px] bg-slate-50 rounded p-2 overflow-auto text-slate-700">
                          {JSON.stringify(row.threshold ?? {}, null, 2)}
                        </pre>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Version History</p>
                  <div className="space-y-2">
                    {detail.version_history.length === 0 && (
                      <p className="text-sm text-slate-500">No version changes yet.</p>
                    )}
                    {detail.version_history.map((row) => (
                      <div key={row.id} className="rounded-xl border border-slate-200 p-3 bg-white text-sm">
                        <p className="font-semibold text-slate-800">
                          {row.from_version}
                          {' -> '}
                          {row.to_version}
                        </p>
                        <pre className="mt-2 text-[11px] bg-slate-50 rounded p-2 overflow-auto">
                          {JSON.stringify(row.diff, null, 2)}
                        </pre>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-4 gap-3">
                  <button
                    onClick={() => openEditModal(detail.event)}
                    className="rounded-xl bg-slate-900 text-white px-3 py-2.5 font-medium hover:bg-slate-800"
                  >
                    Edit Event
                  </button>
                  <button
                    onClick={() => void launchGovernance(detail.event.id)}
                    className="rounded-xl bg-cyan-600 text-white px-3 py-2.5 font-medium hover:bg-cyan-500"
                  >
                    Submit Governance
                  </button>
                  <button
                    onClick={() => openExploreForEvent(detail.event.id)}
                    className="rounded-xl bg-indigo-600 text-white px-3 py-2.5 font-medium hover:bg-indigo-500"
                  >
                    Open in Explore
                  </button>
                  <button
                    onClick={() => openKnowledgeForEvent(detail.event.id)}
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
            <div className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white shadow-2xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-slate-900">
                  {editingEvent ? 'Edit Event' : 'Create Event'}
                </h3>
                <button onClick={() => setFormOpen(false)} className="p-2 rounded hover:bg-slate-100">
                  <X size={16} />
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <input
                  disabled={Boolean(editingEvent)}
                  value={formState.code}
                  onChange={(e) => setFormState((prev) => ({ ...prev, code: e.target.value }))}
                  placeholder="Code (evt_xxx)"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                />
                <input
                  value={formState.name}
                  onChange={(e) => setFormState((prev) => ({ ...prev, name: e.target.value }))}
                  placeholder="Name"
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
                <input
                  value={formState.tags}
                  onChange={(e) => setFormState((prev) => ({ ...prev, tags: e.target.value }))}
                  placeholder="Tags (comma separated)"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none md:col-span-2"
                />
                <select
                  value={formState.status}
                  onChange={(e) => setFormState((prev) => ({ ...prev, status: e.target.value }))}
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none"
                >
                  <option value="draft">draft</option>
                  <option value="active">active</option>
                  <option value="deprecated">deprecated</option>
                </select>
                <textarea
                  value={formState.description}
                  onChange={(e) => setFormState((prev) => ({ ...prev, description: e.target.value }))}
                  placeholder="Description"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none md:col-span-2 h-24"
                />
                <textarea
                  value={formState.properties}
                  onChange={(e) => setFormState((prev) => ({ ...prev, properties: e.target.value }))}
                  placeholder="Schema JSON"
                  className="px-3 py-2.5 border border-slate-200 rounded-xl outline-none md:col-span-2 h-44 font-mono text-sm"
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
                  {formSubmitting ? 'Saving...' : editingEvent ? 'Save Changes' : 'Create Draft'}
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default Events
