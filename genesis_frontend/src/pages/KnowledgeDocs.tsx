import { FormEvent, useEffect, useMemo, useState } from 'react'
import { clsx } from 'clsx'
import {
  Archive,
  BookCopy,
  FileText,
  History,
  Link2,
  MessageSquare,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
  UploadCloud,
} from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'

import {
  GenesisApi,
  type KnowledgeDocumentDetailResponse,
  type KnowledgeDocumentItem,
  type KnowledgeDocumentListResponse,
  type KnowledgeOverviewResponse,
  type KnowledgeTemplateItem,
} from '../services/api'

const statusClass: Record<string, string> = {
  DRAFT: 'bg-amber-100 text-amber-700',
  PUBLISHED: 'bg-emerald-100 text-emerald-700',
  ARCHIVED: 'bg-slate-200 text-slate-700',
}

type CreateFormState = {
  template_key: string
  doc_type: string
  module: string
  title: string
  summary: string
  content: string
  format: string
  status: string
  tags: string
  related_source_type: string
  related_source_id: string
  related_label: string
  meta_payload_text: string
  change_note: string
}

type EditFormState = {
  title: string
  summary: string
  content: string
  tags: string
  related_objects_text: string
  meta_payload_text: string
  change_note: string
}

const defaultCreateForm: CreateFormState = {
  template_key: '',
  doc_type: 'RUNBOOK',
  module: 'MONITORING',
  title: '',
  summary: '',
  content: '',
  format: 'MARKDOWN',
  status: 'DRAFT',
  tags: '',
  related_source_type: '',
  related_source_id: '',
  related_label: '',
  meta_payload_text: '{}',
  change_note: '',
}

const defaultEditForm: EditFormState = {
  title: '',
  summary: '',
  content: '',
  tags: '',
  related_objects_text: '[]',
  meta_payload_text: '{}',
  change_note: '',
}

const lineDelta = (base: string, target: string) => {
  const baseLines = base.split('\n').map((item) => item.trim()).filter(Boolean)
  const targetLines = target.split('\n').map((item) => item.trim()).filter(Boolean)
  const baseSet = new Set(baseLines)
  const targetSet = new Set(targetLines)
  const added = targetLines.filter((item) => !baseSet.has(item)).length
  const removed = baseLines.filter((item) => !targetSet.has(item)).length
  return { added, removed }
}

const KnowledgeDocs = () => {
  const navigate = useNavigate()
  const location = useLocation()

  const [overview, setOverview] = useState<KnowledgeOverviewResponse | null>(null)
  const [templates, setTemplates] = useState<KnowledgeTemplateItem[]>([])
  const [docsResp, setDocsResp] = useState<KnowledgeDocumentListResponse | null>(null)
  const [detail, setDetail] = useState<KnowledgeDocumentDetailResponse | null>(null)
  const [selectedDocId, setSelectedDocId] = useState<number | null>(null)
  const [compareVersionId, setCompareVersionId] = useState<number | null>(null)

  const [loadingOverview, setLoadingOverview] = useState(false)
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [operating, setOperating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const [filters, setFilters] = useState({
    q: '',
    module: 'ALL',
    doc_type: 'ALL',
    status: 'ALL',
    tag: '',
    updated_by_me: false,
    related_source_type: '',
    related_source_id: '',
  })

  const [createForm, setCreateForm] = useState<CreateFormState>(defaultCreateForm)
  const [editForm, setEditForm] = useState<EditFormState>(defaultEditForm)
  const [commentText, setCommentText] = useState('')
  const [actionNote, setActionNote] = useState('')

  const selectedTemplate = useMemo(
    () => templates.find((item) => item.key === createForm.template_key) ?? null,
    [templates, createForm.template_key],
  )

  const selectedDocument = detail?.document ?? null
  const selectedCompareVersion = useMemo(
    () => detail?.version_history.find((item) => item.id === compareVersionId) ?? null,
    [detail, compareVersionId],
  )

  const loadOverview = async () => {
    setLoadingOverview(true)
    try {
      const data = await GenesisApi.getKnowledgeOverview()
      setOverview(data)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load knowledge overview')
    } finally {
      setLoadingOverview(false)
    }
  }

  const loadTemplates = async () => {
    try {
      const data = await GenesisApi.getKnowledgeTemplates()
      setTemplates(data)
    } catch {
      // template fallback is optional for page loading.
    }
  }

  const loadDocuments = async () => {
    setLoadingDocs(true)
    try {
      const data = await GenesisApi.getKnowledgeDocuments({
        q: filters.q.trim() || undefined,
        module: filters.module === 'ALL' ? undefined : filters.module,
        doc_type: filters.doc_type === 'ALL' ? undefined : filters.doc_type,
        status: filters.status === 'ALL' ? undefined : filters.status,
        tag: filters.tag.trim() || undefined,
        updated_by_me: filters.updated_by_me || undefined,
        related_source_type: filters.related_source_type.trim() || undefined,
        related_source_id: filters.related_source_id.trim() || undefined,
        limit: 100,
        offset: 0,
      })
      setDocsResp(data)
      if (!selectedDocId && data.items.length > 0) {
        setSelectedDocId(data.items[0].id)
      }
      if (selectedDocId != null && !data.items.some((item) => item.id === selectedDocId)) {
        setSelectedDocId(data.items[0]?.id ?? null)
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load documents')
    } finally {
      setLoadingDocs(false)
    }
  }

  const loadDetail = async (docId: number) => {
    setLoadingDetail(true)
    try {
      const data = await GenesisApi.getKnowledgeDocumentDetail(docId)
      setDetail(data)
      setCompareVersionId(data.version_history[0]?.id ?? null)
      const doc = data.document
      setEditForm({
        title: doc.title,
        summary: doc.summary ?? '',
        content: doc.content,
        tags: (doc.tags ?? []).join(', '),
        related_objects_text: JSON.stringify(
          (doc.related_objects ?? []).map((item) => ({
            source_type: item.source_type,
            source_id: item.source_id,
            label: item.label ?? undefined,
            module: item.module ?? undefined,
          })),
          null,
          2,
        ),
        meta_payload_text: JSON.stringify(doc.meta_payload ?? {}, null, 2),
        change_note: '',
      })
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load document detail')
      setDetail(null)
    } finally {
      setLoadingDetail(false)
    }
  }

  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const sourceType = params.get('source_type') ?? ''
    const sourceId = params.get('source_id') ?? ''
    if (sourceType && sourceId) {
      setFilters((prev) => ({
        ...prev,
        related_source_type: sourceType,
        related_source_id: sourceId,
      }))
      setCreateForm((prev) => ({
        ...prev,
        related_source_type: sourceType,
        related_source_id: sourceId,
      }))
    }
    void Promise.all([loadOverview(), loadTemplates(), loadDocuments()])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (selectedDocId != null) {
      void loadDetail(selectedDocId)
    } else {
      setDetail(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDocId])

  const refreshAll = async () => {
    await Promise.all([loadOverview(), loadDocuments()])
    if (selectedDocId != null) {
      await loadDetail(selectedDocId)
    }
  }

  const parseTagList = (value: string) =>
    value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)

  const parseJsonObject = (value: string): Record<string, unknown> => {
    const parsed = JSON.parse(value || '{}')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('meta payload must be a JSON object')
    }
    return parsed as Record<string, unknown>
  }

  const parseRelatedObjects = (value: string) => {
    const parsed = JSON.parse(value || '[]')
    if (!Array.isArray(parsed)) {
      throw new Error('related_objects must be a JSON array')
    }
    return parsed.map((item) => ({
      source_type: String(item?.source_type ?? ''),
      source_id: String(item?.source_id ?? ''),
      label: item?.label != null ? String(item.label) : undefined,
      module: item?.module != null ? String(item.module) : undefined,
    }))
  }

  const applyFilters = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    await loadDocuments()
  }

  const createDocument = async (event: FormEvent) => {
    event.preventDefault()
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const relatedObjects =
        createForm.related_source_type.trim() && createForm.related_source_id.trim()
          ? [
              {
                source_type: createForm.related_source_type.trim(),
                source_id: createForm.related_source_id.trim(),
                label: createForm.related_label.trim() || undefined,
              },
            ]
          : []
      const created = await GenesisApi.createKnowledgeDocument({
        doc_type: createForm.doc_type.trim(),
        module: createForm.module.trim(),
        title: createForm.title.trim(),
        summary: createForm.summary.trim() || null,
        content: createForm.content.trim() || undefined,
        format: createForm.format,
        status: createForm.status,
        tags: parseTagList(createForm.tags),
        related_objects: relatedObjects,
        meta_payload: parseJsonObject(createForm.meta_payload_text),
        template_key: createForm.template_key || undefined,
        change_note: createForm.change_note.trim() || undefined,
      })
      setMessage(`Document #${created.document.id} created`)
      setCreateForm((prev) => ({
        ...prev,
        title: '',
        summary: '',
        content: '',
        tags: '',
        change_note: '',
      }))
      await Promise.all([loadOverview(), loadDocuments()])
      setSelectedDocId(created.document.id)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? e?.message ?? 'Failed to create document')
    } finally {
      setOperating(false)
    }
  }

  const updateDocument = async () => {
    if (!selectedDocument) {
      return
    }
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      await GenesisApi.updateKnowledgeDocument(selectedDocument.id, {
        title: editForm.title.trim(),
        summary: editForm.summary.trim() || null,
        content: editForm.content,
        tags: parseTagList(editForm.tags),
        related_objects: parseRelatedObjects(editForm.related_objects_text),
        meta_payload: parseJsonObject(editForm.meta_payload_text),
        change_note: editForm.change_note.trim() || undefined,
      })
      setMessage('Document updated')
      await Promise.all([loadOverview(), loadDocuments(), loadDetail(selectedDocument.id)])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? e?.message ?? 'Failed to update document')
    } finally {
      setOperating(false)
    }
  }

  const addComment = async () => {
    if (!selectedDocument || !commentText.trim()) {
      return
    }
    setOperating(true)
    setError(null)
    try {
      await GenesisApi.addKnowledgeDocumentComment(selectedDocument.id, { content: commentText.trim() })
      setCommentText('')
      await Promise.all([loadOverview(), loadDetail(selectedDocument.id), loadDocuments()])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to add comment')
    } finally {
      setOperating(false)
    }
  }

  const runAction = async (action: 'PUBLISH' | 'ARCHIVE' | 'UNARCHIVE') => {
    if (!selectedDocument) {
      return
    }
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      await GenesisApi.operateKnowledgeDocument(selectedDocument.id, {
        action,
        change_note: actionNote.trim() || undefined,
      })
      setMessage(`Action ${action} applied`)
      await Promise.all([loadOverview(), loadDocuments(), loadDetail(selectedDocument.id)])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? `Failed to ${action.toLowerCase()}`)
    } finally {
      setOperating(false)
    }
  }

  const restoreVersion = async (versionId: number) => {
    if (!selectedDocument) {
      return
    }
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      await GenesisApi.restoreKnowledgeDocumentVersion(selectedDocument.id, versionId, {
        change_note: actionNote.trim() || undefined,
      })
      setMessage(`Version #${versionId} restored`)
      await Promise.all([loadOverview(), loadDocuments(), loadDetail(selectedDocument.id)])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to restore version')
    } finally {
      setOperating(false)
    }
  }

  const openRelatedObject = (item: KnowledgeDocumentItem['related_objects'][number]) => {
    const route = item.module_route || '/logs'
    navigate(route)
  }

  const moduleOptions = useMemo(
    () => ['ALL', ...(docsResp?.facets.modules ?? [])],
    [docsResp?.facets.modules],
  )
  const docTypeOptions = useMemo(
    () => ['ALL', ...(docsResp?.facets.doc_types ?? [])],
    [docsResp?.facets.doc_types],
  )
  const statusOptions = useMemo(
    () => ['ALL', ...(docsResp?.facets.statuses ?? [])],
    [docsResp?.facets.statuses],
  )

  return (
    <div className="max-w-7xl mx-auto space-y-4 animate-in fade-in slide-in-from-bottom-8 duration-700">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">Knowledge & Documentation Center</h2>
          <p className="text-slate-500 text-base">Document runbooks, specs, and operational knowledge with version history.</p>
        </div>
        <button
          onClick={() => void refreshAll()}
          disabled={loadingOverview || loadingDocs || loadingDetail}
          className="rounded-xl bg-slate-900 text-white px-4 py-2.5 font-medium hover:bg-slate-800 disabled:opacity-60 flex items-center gap-2"
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </header>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
      {message && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>}

      <section className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Total Docs</p>
          <p className="text-2xl font-bold text-slate-900">{overview?.summary.total_docs ?? 0}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Published</p>
          <p className="text-2xl font-bold text-emerald-700">{overview?.summary.published_docs ?? 0}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Draft</p>
          <p className="text-2xl font-bold text-amber-700">{overview?.summary.draft_docs ?? 0}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Archived</p>
          <p className="text-2xl font-bold text-slate-700">{overview?.summary.archived_docs ?? 0}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Updated 7d</p>
          <p className="text-2xl font-bold text-cyan-700">{overview?.summary.updated_docs_7d ?? 0}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Comments 7d</p>
          <p className="text-2xl font-bold text-indigo-700">{overview?.summary.comments_7d ?? 0}</p>
        </div>
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="glass rounded-3xl border border-slate-200/60 p-4">
          <div className="flex items-center gap-2 mb-3">
            <BookCopy size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">Create Document</h3>
          </div>
          <form onSubmit={createDocument} className="space-y-2">
            <select
              value={createForm.template_key}
              onChange={(e) => {
                const key = e.target.value
                const template = templates.find((item) => item.key === key)
                setCreateForm((prev) => ({
                  ...prev,
                  template_key: key,
                  doc_type: template?.doc_type ?? prev.doc_type,
                  module: template?.module ?? prev.module,
                  title: template ? '' : prev.title,
                  summary: template ? template.summary : prev.summary,
                  content: template ? '' : prev.content,
                }))
              }}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
              <option value="">No template</option>
              {templates.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.key} - {item.title}
                </option>
              ))}
            </select>
            {selectedTemplate && (
              <p className="text-xs text-slate-500 rounded-lg bg-slate-50 px-2 py-1">
                {selectedTemplate.summary}
              </p>
            )}
            <div className="grid grid-cols-2 gap-2">
              <input
                value={createForm.doc_type}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, doc_type: e.target.value }))}
                placeholder="Doc Type"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                required
              />
              <input
                value={createForm.module}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, module: e.target.value }))}
                placeholder="Module"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                required
              />
            </div>
            <input
              value={createForm.title}
              onChange={(e) => setCreateForm((prev) => ({ ...prev, title: e.target.value }))}
              placeholder="Title"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              required
            />
            <textarea
              rows={2}
              value={createForm.summary}
              onChange={(e) => setCreateForm((prev) => ({ ...prev, summary: e.target.value }))}
              placeholder="Summary"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <textarea
              rows={6}
              value={createForm.content}
              onChange={(e) => setCreateForm((prev) => ({ ...prev, content: e.target.value }))}
              placeholder="Markdown / rich content"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-mono"
            />
            <div className="grid grid-cols-2 gap-2">
              <select
                value={createForm.format}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, format: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              >
                <option value="MARKDOWN">MARKDOWN</option>
                <option value="RICH_TEXT">RICH_TEXT</option>
              </select>
              <select
                value={createForm.status}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, status: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              >
                <option value="DRAFT">DRAFT</option>
                <option value="PUBLISHED">PUBLISHED</option>
              </select>
            </div>
            <input
              value={createForm.tags}
              onChange={(e) => setCreateForm((prev) => ({ ...prev, tags: e.target.value }))}
              placeholder="tags (comma separated)"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <div className="grid grid-cols-2 gap-2">
              <input
                value={createForm.related_source_type}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, related_source_type: e.target.value }))}
                placeholder="Related source_type"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
              <input
                value={createForm.related_source_id}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, related_source_id: e.target.value }))}
                placeholder="Related source_id"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </div>
            <input
              value={createForm.related_label}
              onChange={(e) => setCreateForm((prev) => ({ ...prev, related_label: e.target.value }))}
              placeholder="Related label (optional)"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <textarea
              rows={3}
              value={createForm.meta_payload_text}
              onChange={(e) => setCreateForm((prev) => ({ ...prev, meta_payload_text: e.target.value }))}
              placeholder="meta payload JSON"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-mono"
            />
            <input
              value={createForm.change_note}
              onChange={(e) => setCreateForm((prev) => ({ ...prev, change_note: e.target.value }))}
              placeholder="change note"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <button
              type="submit"
              disabled={operating}
              className="w-full rounded-lg bg-cyan-600 text-white py-2 text-sm font-semibold disabled:opacity-50"
            >
              Create Document
            </button>
          </form>
        </div>

        <div className="glass rounded-3xl border border-slate-200/60 p-4 xl:col-span-2">
          <div className="flex items-center gap-2 mb-3">
            <History size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">Directory & Filters</h3>
          </div>
          <form onSubmit={applyFilters} className="grid grid-cols-1 md:grid-cols-6 gap-2">
            <div className="md:col-span-2 relative">
              <Search size={14} className="absolute left-2.5 top-2.5 text-slate-400" />
              <input
                value={filters.q}
                onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))}
                placeholder="search title/summary/content"
                className="w-full rounded-lg border border-slate-200 pl-8 pr-3 py-2 text-sm"
              />
            </div>
            <select
              value={filters.module}
              onChange={(e) => setFilters((prev) => ({ ...prev, module: e.target.value }))}
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
              {moduleOptions.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
            <select
              value={filters.doc_type}
              onChange={(e) => setFilters((prev) => ({ ...prev, doc_type: e.target.value }))}
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
              {docTypeOptions.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
            <select
              value={filters.status}
              onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))}
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
              {statusOptions.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
            <button type="submit" className="rounded-lg bg-slate-900 text-white px-3 py-2 text-sm font-semibold">
              Apply
            </button>
            <input
              value={filters.tag}
              onChange={(e) => setFilters((prev) => ({ ...prev, tag: e.target.value }))}
              placeholder="tag"
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm md:col-span-2"
            />
            <input
              value={filters.related_source_type}
              onChange={(e) => setFilters((prev) => ({ ...prev, related_source_type: e.target.value }))}
              placeholder="related source_type"
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <input
              value={filters.related_source_id}
              onChange={(e) => setFilters((prev) => ({ ...prev, related_source_id: e.target.value }))}
              placeholder="related source_id"
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <label className="inline-flex items-center gap-2 text-xs text-slate-600 px-2">
              <input
                type="checkbox"
                checked={filters.updated_by_me}
                onChange={(e) => setFilters((prev) => ({ ...prev, updated_by_me: e.target.checked }))}
              />
              Updated by me
            </label>
          </form>
          <div className="mt-3 flex flex-wrap gap-2">
            {(overview?.directory.top_tags ?? []).slice(0, 10).map(([tag, count]) => (
              <button
                key={tag}
                onClick={() => setFilters((prev) => ({ ...prev, tag }))}
                className="px-2 py-1 rounded-full bg-slate-100 text-xs text-slate-700 hover:bg-slate-200"
              >
                {tag} ({count})
              </button>
            ))}
          </div>
          <div className="mt-4 space-y-2 max-h-80 overflow-auto">
            {loadingDocs && <p className="text-sm text-slate-500">Loading documents...</p>}
            {(docsResp?.items ?? []).map((item) => (
              <button
                key={item.id}
                onClick={() => setSelectedDocId(item.id)}
                className={clsx(
                  'w-full text-left rounded-xl border p-3 transition',
                  selectedDocId === item.id
                    ? 'border-cyan-500 bg-cyan-50'
                    : 'border-slate-200 bg-white hover:border-slate-300',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold text-slate-800 text-sm">{item.title}</p>
                  <span className={clsx('px-2 py-0.5 rounded-full text-xs font-semibold', statusClass[item.status] ?? 'bg-slate-100 text-slate-700')}>
                    {item.status}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  {item.module} / {item.doc_type} / v{item.version_no}
                </p>
                <p className="text-xs text-slate-600 mt-1 line-clamp-2">{item.summary || item.preview}</p>
              </button>
            ))}
            {(docsResp?.items.length ?? 0) === 0 && !loadingDocs && (
              <p className="text-sm text-slate-500">No documents under current filters.</p>
            )}
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="glass rounded-3xl border border-slate-200/60 p-4">
          <div className="flex items-center gap-2 mb-3">
            <FileText size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">Document Detail</h3>
          </div>
          {!detail && <p className="text-sm text-slate-500">Select one document to inspect details.</p>}
          {loadingDetail && <p className="text-sm text-slate-500">Loading detail...</p>}
          {detail && (
            <div className="space-y-3">
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold text-slate-800">{detail.document.title}</p>
                  <span className={clsx('px-2 py-0.5 rounded-full text-xs font-semibold', statusClass[detail.document.status] ?? 'bg-slate-100 text-slate-700')}>
                    {detail.document.status}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  {detail.document.module} / {detail.document.doc_type} / version {detail.document.version_no}
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  author {detail.document.author} | editor {detail.document.last_editor}
                </p>
                <p className="text-sm text-slate-600 mt-2">{detail.document.summary || '-'}</p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold text-slate-700 mb-2">Content</p>
                <pre className="text-xs bg-slate-50 p-3 rounded-lg overflow-auto text-slate-700 whitespace-pre-wrap max-h-80">
{detail.document.content}
                </pre>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex items-center gap-2 mb-2">
                  <Link2 size={14} className="text-slate-500" />
                  <p className="text-xs font-semibold text-slate-700">Related Objects</p>
                </div>
                <div className="space-y-2 max-h-40 overflow-auto">
                  {detail.document.related_objects.map((item, index) => (
                    <div key={`${item.source_type}-${item.source_id}-${index}`} className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2">
                      <div>
                        <p className="text-sm text-slate-800">
                          {item.source_type}:{item.source_id}
                        </p>
                        <p className="text-xs text-slate-500">
                          module {item.module || '-'} | exists {item.exists == null ? '-' : item.exists ? 'yes' : 'no'}
                        </p>
                      </div>
                      <button
                        onClick={() => openRelatedObject(item)}
                        className="rounded-lg border border-slate-300 px-2 py-1 text-xs text-slate-700"
                      >
                        Open
                      </button>
                    </div>
                  ))}
                  {detail.document.related_objects.length === 0 && <p className="text-sm text-slate-500">No related objects.</p>}
                </div>
                <p className="text-xs text-slate-500 mt-2">tags: {(detail.document.tags ?? []).join(', ') || '-'}</p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex items-center gap-2 mb-2">
                  <MessageSquare size={14} className="text-slate-500" />
                  <p className="text-xs font-semibold text-slate-700">Comments</p>
                </div>
                <div className="space-y-2 max-h-40 overflow-auto">
                  {detail.comments.map((comment) => (
                    <div key={comment.id} className="border-b border-slate-100 pb-1">
                      <p className="text-xs text-slate-600">
                        {comment.author} | {new Date(comment.created_at).toLocaleString()}
                      </p>
                      <p className="text-sm text-slate-800">{comment.content}</p>
                    </div>
                  ))}
                  {detail.comments.length === 0 && <p className="text-sm text-slate-500">No comments.</p>}
                </div>
                <div className="mt-2 flex gap-2">
                  <input
                    value={commentText}
                    onChange={(e) => setCommentText(e.target.value)}
                    placeholder="Add comment, mention with @user"
                    className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  />
                  <button
                    onClick={() => void addComment()}
                    disabled={operating || !commentText.trim()}
                    className="rounded-lg bg-cyan-600 text-white px-3 py-2 text-sm disabled:opacity-50"
                  >
                    <Send size={14} />
                  </button>
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold text-slate-700 mb-2">Document Actions</p>
                <input
                  value={actionNote}
                  onChange={(e) => setActionNote(e.target.value)}
                  placeholder="action note (optional)"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                />
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    onClick={() => void runAction('PUBLISH')}
                    disabled={operating}
                    className="rounded-lg bg-emerald-600 text-white px-3 py-1.5 text-sm disabled:opacity-50"
                  >
                    <UploadCloud size={14} className="inline mr-1" />
                    Publish
                  </button>
                  <button
                    onClick={() => void runAction('ARCHIVE')}
                    disabled={operating}
                    className="rounded-lg bg-slate-700 text-white px-3 py-1.5 text-sm disabled:opacity-50"
                  >
                    <Archive size={14} className="inline mr-1" />
                    Archive
                  </button>
                  <button
                    onClick={() => void runAction('UNARCHIVE')}
                    disabled={operating}
                    className="rounded-lg bg-amber-500 text-white px-3 py-1.5 text-sm disabled:opacity-50"
                  >
                    Unarchive
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="glass rounded-3xl border border-slate-200/60 p-4">
          <div className="flex items-center gap-2 mb-3">
            <RotateCcw size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">Versioning & Edit</h3>
          </div>
          {!detail && <p className="text-sm text-slate-500">Choose a document to edit and inspect versions.</p>}
          {detail && (
            <div className="space-y-3">
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold text-slate-700 mb-2">Edit Current Document</p>
                <div className="space-y-2">
                  <input
                    value={editForm.title}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, title: e.target.value }))}
                    placeholder="title"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  />
                  <textarea
                    rows={2}
                    value={editForm.summary}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, summary: e.target.value }))}
                    placeholder="summary"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  />
                  <textarea
                    rows={8}
                    value={editForm.content}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, content: e.target.value }))}
                    placeholder="content"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-mono"
                  />
                  <input
                    value={editForm.tags}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, tags: e.target.value }))}
                    placeholder="tags (comma separated)"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  />
                  <textarea
                    rows={4}
                    value={editForm.related_objects_text}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, related_objects_text: e.target.value }))}
                    placeholder="related_objects JSON array"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-mono"
                  />
                  <textarea
                    rows={4}
                    value={editForm.meta_payload_text}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, meta_payload_text: e.target.value }))}
                    placeholder="meta payload JSON"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-mono"
                  />
                  <input
                    value={editForm.change_note}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, change_note: e.target.value }))}
                    placeholder="change note"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  />
                  <button
                    onClick={() => void updateDocument()}
                    disabled={operating}
                    className="w-full rounded-lg bg-cyan-600 text-white py-2 text-sm font-semibold disabled:opacity-50"
                  >
                    Save Update
                  </button>
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold text-slate-700 mb-2">Version History</p>
                <div className="space-y-2 max-h-52 overflow-auto">
                  {detail.version_history.map((version) => (
                    <div key={version.id} className="border-b border-slate-100 pb-2">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm text-slate-800">
                          v{version.version_no} {version.action}
                        </p>
                        <div className="flex gap-1">
                          <button
                            onClick={() => setCompareVersionId(version.id)}
                            className="rounded border border-slate-300 px-2 py-0.5 text-xs text-slate-700"
                          >
                            Compare
                          </button>
                          <button
                            onClick={() => void restoreVersion(version.id)}
                            disabled={operating}
                            className="rounded border border-amber-300 px-2 py-0.5 text-xs text-amber-700 disabled:opacity-50"
                          >
                            Restore
                          </button>
                        </div>
                      </div>
                      <p className="text-[11px] text-slate-500">
                        {new Date(version.created_at).toLocaleString()} | {version.editor}
                      </p>
                      {version.change_note && <p className="text-xs text-slate-600">{version.change_note}</p>}
                    </div>
                  ))}
                </div>
              </div>

              {selectedCompareVersion && selectedDocument && (
                <div className="rounded-xl border border-slate-200 bg-white p-3">
                  <p className="text-xs font-semibold text-slate-700 mb-2">
                    Compare current (v{selectedDocument.version_no}) with v{selectedCompareVersion.version_no}
                  </p>
                  <p className="text-xs text-slate-600 mb-2">
                    {(() => {
                      const diff = lineDelta(selectedDocument.content, selectedCompareVersion.content)
                      return `added lines ${diff.added}, removed lines ${diff.removed}`
                    })()}
                  </p>
                  <pre className="text-xs bg-slate-50 p-2 rounded-lg overflow-auto max-h-36 whitespace-pre-wrap">
{selectedCompareVersion.content}
                  </pre>
                </div>
              )}

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold text-slate-700 mb-2">Related Documents</p>
                <div className="space-y-2 max-h-36 overflow-auto">
                  {detail.related_documents.map((item) => (
                    <button
                      key={item.id}
                      onClick={() => setSelectedDocId(item.id)}
                      className="block w-full text-left border-b border-slate-100 pb-1"
                    >
                      <p className="text-sm text-slate-800">{item.title}</p>
                      <p className="text-xs text-slate-500">{item.module} / {item.doc_type}</p>
                    </button>
                  ))}
                  {detail.related_documents.length === 0 && <p className="text-sm text-slate-500">No related documents.</p>}
                </div>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

export default KnowledgeDocs
