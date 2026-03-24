import { FormEvent, useEffect, useMemo, useState } from 'react'
import { Archive, BookOpenText, Plus, RefreshCw, Search, Send } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'

import {
  GenesisApi,
  type KnowledgeDocumentCommentItem,
  type KnowledgeDocumentDetailResponse,
  type KnowledgeDocumentItem,
  type KnowledgeDocumentListResponse,
  type KnowledgeOverviewResponse,
} from '../services/api'

const PAGE_SIZE = 12

type CreateFormState = {
  title: string
  summary: string
  content: string
  module: string
  docType: string
  knowledgeLevel: string
  status: string
  tags: string
}

const DEFAULT_FORM: CreateFormState = {
  title: '',
  summary: '',
  content: '',
  module: 'GENERAL',
  docType: 'RUNBOOK',
  knowledgeLevel: 'BRIEF',
  status: 'DRAFT',
  tags: '',
}

function formatDate(value?: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

function parseTags(value: string) {
  return value.split(',').map((item) => item.trim()).filter(Boolean)
}

function levelLabel(level: string) {
  switch (level) {
    case 'INSTANCE':
      return '实例级'
    case 'ASSET':
      return '资产级'
    case 'FIELD':
      return '字段级'
    case 'DOMAIN':
      return '主题域'
    case 'CONTRACT':
      return '契约级'
    case 'BRIEF':
      return '简报'
    default:
      return level || '未分类'
  }
}

function tone(status: string) {
  if (status === 'PUBLISHED') return 'border-emerald-200 bg-emerald-50 text-emerald-700'
  if (status === 'ARCHIVED') return 'border-slate-200 bg-slate-100 text-slate-600'
  return 'border-amber-200 bg-amber-50 text-amber-700'
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-[26px] border border-[var(--df-border)] bg-[var(--df-surface)] p-5 shadow-[var(--df-shadow-soft)]">
      <div className="text-xs uppercase tracking-[0.2em] text-[var(--df-text-soft)]">{label}</div>
      <div className="df-display mt-2 text-[34px] tracking-[-0.04em] text-[var(--df-text)]">{value}</div>
    </div>
  )
}

function RefBlock({ title, items, empty }: { title: string; items: Array<Record<string, unknown>>; empty: string }) {
  return (
    <div className="rounded-[26px] border border-[var(--df-border)] bg-[var(--df-surface)] p-5 shadow-[var(--df-shadow-soft)]">
      <div className="df-display text-[18px] tracking-[-0.03em] text-[var(--df-text)]">{title}</div>
      {items.length === 0 ? (
        <div className="mt-3 rounded-[20px] border border-dashed border-[var(--df-border)] bg-[var(--df-surface-2)] px-4 py-6 text-sm text-[var(--df-text-muted)]">
          {empty}
        </div>
      ) : (
        <div className="mt-3 space-y-2">
          {items.map((item, index) => (
            <div key={index} className="rounded-[18px] border border-[var(--df-border)] bg-[var(--df-surface-2)] p-3 text-sm text-[var(--df-text-muted)]">
              {Object.entries(item).map(([key, value]) => (
                <div key={key} className="break-all">
                  <span className="font-medium text-[var(--df-text)]">{key}</span>: {String(value)}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function KnowledgeDocs() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = useMemo(() => new URLSearchParams(location.search), [location.search])
  const sourceType = params.get('source_type') ?? ''
  const sourceId = params.get('source_id') ?? ''
  const linkedSource = useMemo(
    () => (sourceType && sourceId ? { sourceType, sourceId } : null),
    [sourceId, sourceType],
  )

  const [overview, setOverview] = useState<KnowledgeOverviewResponse | null>(null)
  const [listResponse, setListResponse] = useState<KnowledgeDocumentListResponse | null>(null)
  const [detail, setDetail] = useState<KnowledgeDocumentDetailResponse | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const [query, setQuery] = useState('')
  const [moduleFilter, setModuleFilter] = useState('ALL')
  const [levelFilter, setLevelFilter] = useState('ALL')
  const [docTypeFilter, setDocTypeFilter] = useState('ALL')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [offset, setOffset] = useState(0)

  const [loadingOverview, setLoadingOverview] = useState(true)
  const [loadingList, setLoadingList] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [banner, setBanner] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState<CreateFormState>(DEFAULT_FORM)
  const [commentText, setCommentText] = useState('')

  const selectedDocument = detail?.document ?? null

  const loadOverview = async () => {
    setLoadingOverview(true)
    try {
      setOverview(await GenesisApi.getKnowledgeOverview())
    } finally {
      setLoadingOverview(false)
    }
  }

  const loadDocuments = async (preferredId?: number | null) => {
    setLoadingList(true)
    try {
      const data = await GenesisApi.getKnowledgeDocuments({
        q: query.trim() || undefined,
        module: moduleFilter === 'ALL' ? undefined : moduleFilter,
        knowledge_level: levelFilter === 'ALL' ? undefined : levelFilter,
        doc_type: docTypeFilter === 'ALL' ? undefined : docTypeFilter,
        status: statusFilter === 'ALL' ? undefined : statusFilter,
        related_source_type: linkedSource?.sourceType,
        related_source_id: linkedSource?.sourceId,
        include_shared: true,
        limit: PAGE_SIZE,
        offset,
      })
      setListResponse(data)
      const nextId = preferredId ?? selectedId ?? data.items[0]?.id ?? null
      setSelectedId(nextId && data.items.some((item) => item.id === nextId) ? nextId : data.items[0]?.id ?? null)
    } finally {
      setLoadingList(false)
    }
  }

  const loadDetail = async (docId: number) => {
    setLoadingDetail(true)
    try {
      setDetail(await GenesisApi.getKnowledgeDocumentDetail(docId))
    } finally {
      setLoadingDetail(false)
    }
  }

  useEffect(() => {
    void loadOverview()
  }, [])

  useEffect(() => {
    void loadDocuments()
  }, [query, moduleFilter, levelFilter, docTypeFilter, statusFilter, offset, linkedSource?.sourceId, linkedSource?.sourceType])

  useEffect(() => {
    if (selectedId == null) {
      setDetail(null)
      return
    }
    void loadDetail(selectedId)
  }, [selectedId])

  const refreshAll = async (preferredId?: number | null) => {
    await Promise.all([loadOverview(), loadDocuments(preferredId)])
    const nextId = preferredId ?? selectedId
    if (nextId != null) await loadDetail(nextId)
  }

  const createDocument = async () => {
    if (!form.title.trim()) {
      window.alert('标题不能为空。')
      return
    }
    setSubmitting(true)
    try {
      const created = await GenesisApi.createKnowledgeDocument({
        title: form.title.trim(),
        summary: form.summary.trim() || undefined,
        content: form.content.trim() || undefined,
        module: form.module.trim().toUpperCase(),
        doc_type: form.docType.trim().toUpperCase(),
        knowledge_level: form.knowledgeLevel,
        status: form.status,
        format: 'MARKDOWN',
        tags: parseTags(form.tags),
        related_objects: linkedSource ? [{ source_type: linkedSource.sourceType, source_id: linkedSource.sourceId, label: `${linkedSource.sourceType}:${linkedSource.sourceId}`, module: 'KNOWLEDGE' }] : undefined,
        object_refs: linkedSource ? [{ object_type: 'INSTANCE', object_id: linkedSource.sourceId, source_type: linkedSource.sourceType }] : undefined,
      })
      setBanner(`已创建知识对象：${created.document.title}`)
      setShowCreate(false)
      setForm(DEFAULT_FORM)
      setOffset(0)
      await refreshAll(created.document.id)
    } finally {
      setSubmitting(false)
    }
  }

  const addComment = async (event: FormEvent) => {
    event.preventDefault()
    if (!selectedDocument || !commentText.trim()) return
    setSubmitting(true)
    try {
      await GenesisApi.addKnowledgeDocumentComment(selectedDocument.id, { content: commentText.trim() })
      setCommentText('')
      await loadDetail(selectedDocument.id)
    } finally {
      setSubmitting(false)
    }
  }

  const runAction = async (action: 'PUBLISH' | 'ARCHIVE' | 'UNARCHIVE') => {
    if (!selectedDocument) return
    setSubmitting(true)
    try {
      const next = await GenesisApi.operateKnowledgeDocument(selectedDocument.id, { action })
      setBanner(`操作 ${action} 已完成：${next.document.title}`)
      await refreshAll(selectedDocument.id)
    } finally {
      setSubmitting(false)
    }
  }

  const facets = listResponse?.facets
  const items = listResponse?.items ?? []
  const objectRefs = (selectedDocument?.object_refs ?? []) as Array<Record<string, unknown>>
  const factRefs = (selectedDocument?.fact_refs ?? []) as Array<Record<string, unknown>>

  return (
    <div className="space-y-6">
      <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
              <BookOpenText size={14} />
              知识对象
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">知识与记忆工作台</h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-600">按实例级、资产级、字段级、主题域和契约级管理知识对象。带事实引用的条目会优先进入 AI 检索。</p>
          </div>
          <div className="flex gap-3">
            <button type="button" onClick={() => void refreshAll()} disabled={loadingOverview || loadingList || submitting} className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">
              <RefreshCw size={15} />
              {loadingOverview || loadingList ? '刷新中...' : '刷新'}
            </button>
            <button type="button" onClick={() => setShowCreate(true)} className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800">
              <Plus size={15} />
              新建知识
            </button>
          </div>
        </div>
        {linkedSource ? (
          <div className="mt-5 flex items-center gap-3 rounded-2xl border border-indigo-100 bg-indigo-50 px-4 py-3 text-sm text-indigo-700">
            当前按来源筛选：{linkedSource.sourceType}:{linkedSource.sourceId}
            <button type="button" onClick={() => navigate('/knowledge')} className="rounded-full border border-indigo-200 bg-white px-3 py-1 text-xs">
              清除
            </button>
          </div>
        ) : null}
        {banner ? <div className="mt-5 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{banner}</div> : null}
      </section>

      <div className="grid gap-4 md:grid-cols-5">
        <StatCard label="知识总数" value={overview?.summary.total_docs ?? 0} />
        <StatCard label="已发布" value={overview?.summary.published_docs ?? 0} />
        <StatCard label="草稿" value={overview?.summary.draft_docs ?? 0} />
        <StatCard label="已归档" value={overview?.summary.archived_docs ?? 0} />
        <StatCard label="近 7 天更新" value={overview?.summary.updated_docs_7d ?? 0} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(420px,0.95fr)]">
        <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_150px_150px_150px_150px]">
            <div className="relative">
              <Search size={15} className="absolute left-3 top-3 text-slate-400" />
              <input value={query} onChange={(event) => { setOffset(0); setQuery(event.target.value) }} className="w-full rounded-2xl border border-slate-200 bg-slate-50 py-3 pl-10 pr-4 text-sm text-slate-700 outline-none" placeholder="搜索标题、摘要、标签或正文" />
            </div>
            <select value={moduleFilter} onChange={(event) => { setOffset(0); setModuleFilter(event.target.value) }} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none">
              <option value="ALL">全部模块</option>
              {(facets?.modules ?? []).map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select value={levelFilter} onChange={(event) => { setOffset(0); setLevelFilter(event.target.value) }} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none">
              <option value="ALL">全部层级</option>
              {(facets?.knowledge_levels ?? []).map((item) => <option key={item} value={item}>{levelLabel(item)}</option>)}
            </select>
            <select value={docTypeFilter} onChange={(event) => { setOffset(0); setDocTypeFilter(event.target.value) }} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none">
              <option value="ALL">全部类型</option>
              {(facets?.doc_types ?? []).map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select value={statusFilter} onChange={(event) => { setOffset(0); setStatusFilter(event.target.value) }} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none">
              {['ALL', 'DRAFT', 'REVIEW', 'PUBLISHED', 'ARCHIVED'].map((item) => <option key={item} value={item}>{item === 'ALL' ? '全部状态' : item}</option>)}
            </select>
          </div>

          <div className="mt-6 space-y-3">
            {loadingList ? (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-12 text-center text-sm text-slate-500">正在加载知识对象...</div>
            ) : items.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-12 text-center text-sm text-slate-500">当前没有匹配的知识对象。</div>
            ) : items.map((item) => (
              <button key={item.id} type="button" onClick={() => setSelectedId(item.id)} className={`w-full rounded-2xl border p-4 text-left transition ${item.id === selectedId ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-slate-50 text-slate-900 hover:border-slate-300 hover:bg-white'}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${tone(item.status)}`}>{item.status}</span>
                  <span className="rounded-full border border-slate-200 bg-white/70 px-2.5 py-1 text-xs text-slate-700">{levelLabel(item.knowledge_level)}</span>
                  {!item.has_fact_refs ? <span className="rounded-full border border-slate-200 bg-white/70 px-2.5 py-1 text-xs text-slate-500">说明性内容</span> : null}
                </div>
                <div className="mt-3 text-base font-semibold">{item.title}</div>
                <div className={`mt-2 text-sm ${item.id === selectedId ? 'text-slate-200' : 'text-slate-600'}`}>{item.summary || item.preview}</div>
                <div className={`mt-3 flex flex-wrap gap-2 text-xs ${item.id === selectedId ? 'text-slate-300' : 'text-slate-500'}`}>
                  <span>{item.module}</span><span>|</span><span>{item.doc_type}</span><span>|</span><span>事实 {item.fact_ref_count}</span><span>|</span><span>对象 {item.object_refs.length}</span><span>|</span><span>{formatDate(item.updated_at)}</span>
                </div>
              </button>
            ))}
          </div>

          <div className="mt-5 flex items-center justify-between text-sm text-slate-500">
            <div>{listResponse?.total ? `${(listResponse.offset ?? 0) + 1}-${Math.min((listResponse.offset ?? 0) + (listResponse.limit ?? PAGE_SIZE), listResponse.total)}` : '0'} / {listResponse?.total ?? 0}</div>
            <div className="flex gap-2">
              <button type="button" disabled={(listResponse?.offset ?? 0) <= 0} onClick={() => setOffset(Math.max(offset - PAGE_SIZE, 0))} className="rounded-xl border border-slate-200 px-3 py-1.5 disabled:opacity-50">上一页</button>
              <button type="button" disabled={(listResponse?.offset ?? 0) + (listResponse?.limit ?? PAGE_SIZE) >= (listResponse?.total ?? 0)} onClick={() => setOffset(offset + PAGE_SIZE)} className="rounded-xl border border-slate-200 px-3 py-1.5 disabled:opacity-50">下一页</button>
            </div>
          </div>
        </section>

        <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
          {selectedDocument == null ? (
            <div className="flex min-h-[560px] items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-6 text-center text-sm text-slate-500">请选择一条知识对象查看详情。</div>
          ) : loadingDetail ? (
            <div className="flex min-h-[560px] items-center justify-center text-sm text-slate-500">正在加载详情...</div>
          ) : (
            <div className="space-y-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${tone(selectedDocument.status)}`}>{selectedDocument.status}</span>
                    <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-700">{levelLabel(selectedDocument.knowledge_level)}</span>
                    <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-700">{selectedDocument.module}</span>
                    <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-700">{selectedDocument.doc_type}</span>
                  </div>
                  <h2 className="mt-3 text-2xl font-semibold tracking-tight text-slate-900">{selectedDocument.title}</h2>
                  <p className="mt-2 text-sm text-slate-600">{selectedDocument.summary || selectedDocument.preview}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {selectedDocument.status !== 'PUBLISHED' ? <button type="button" onClick={() => void runAction('PUBLISH')} disabled={submitting} className="rounded-2xl bg-slate-900 px-3.5 py-2 text-sm font-medium text-white disabled:opacity-50">发布</button> : null}
                  <button type="button" onClick={() => void runAction(selectedDocument.status === 'ARCHIVED' ? 'UNARCHIVE' : 'ARCHIVE')} disabled={submitting} className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 disabled:opacity-50">
                    <Archive size={15} />
                    {selectedDocument.status === 'ARCHIVED' ? '恢复' : '归档'}
                  </button>
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-4">
                <StatCard label="版本" value={selectedDocument.version_no} />
                <StatCard label="事实引用" value={selectedDocument.fact_ref_count} />
                <StatCard label="对象引用" value={selectedDocument.object_refs.length} />
                <StatCard label="评论数" value={detail?.comments.length ?? 0} />
              </div>

              {!selectedDocument.has_fact_refs ? <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">当前条目暂无事实引用，仅作为说明性内容。</div> : null}

              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                <div className="text-sm font-semibold text-slate-900">内容</div>
                <div className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-700">{selectedDocument.content}</div>
              </div>

              <div className="grid gap-4 xl:grid-cols-2">
                <RefBlock title="关联对象" items={objectRefs} empty="当前没有对象引用。" />
                <RefBlock title="事实引用" items={factRefs} empty="当前没有事实引用。" />
              </div>

              <div className="grid gap-4 xl:grid-cols-2">
                <div className="rounded-2xl border border-slate-200 bg-white p-5">
                  <div className="text-sm font-semibold text-slate-900">评论</div>
                  <div className="mt-3 space-y-3">
                    {(detail?.comments ?? []).map((comment: KnowledgeDocumentCommentItem) => (
                      <div key={comment.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-sm font-medium text-slate-900">{comment.author}</div>
                          <div className="text-xs text-slate-500">{formatDate(comment.created_at)}</div>
                        </div>
                        <div className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{comment.content}</div>
                      </div>
                    ))}
                    {(detail?.comments.length ?? 0) === 0 ? <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">当前没有评论。</div> : null}
                  </div>
                  <form onSubmit={addComment} className="mt-4">
                    <textarea value={commentText} onChange={(event) => setCommentText(event.target.value)} className="min-h-[92px] w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none" placeholder="补充评论或协同说明" />
                    <div className="mt-3 flex justify-end">
                      <button type="submit" disabled={submitting || !commentText.trim()} className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50">
                        <Send size={15} />
                        添加评论
                      </button>
                    </div>
                  </form>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-5">
                  <div className="text-sm font-semibold text-slate-900">关联知识对象</div>
                  <div className="mt-3 space-y-3">
                    {(detail?.related_documents ?? []).slice(0, 6).map((item: KnowledgeDocumentItem) => (
                      <button key={item.id} type="button" onClick={() => setSelectedId(item.id)} className="w-full rounded-2xl border border-slate-200 bg-slate-50 p-3 text-left hover:border-slate-300 hover:bg-white">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`rounded-full border px-2 py-0.5 text-[11px] ${tone(item.status)}`}>{item.status}</span>
                          <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[11px] text-slate-700">{levelLabel(item.knowledge_level)}</span>
                        </div>
                        <div className="mt-2 font-medium text-slate-900">{item.title}</div>
                        <div className="mt-1 text-sm text-slate-600">{item.summary || item.preview}</div>
                      </button>
                    ))}
                    {(detail?.related_documents.length ?? 0) === 0 ? <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">当前没有关联知识对象。</div> : null}
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>
      </div>

      {showCreate ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/40 p-6">
          <div className="w-full max-w-3xl rounded-[28px] border border-slate-200 bg-white p-6 shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">新建知识对象</div>
                <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">创建知识条目</h2>
              </div>
              <button type="button" onClick={() => { setShowCreate(false); setForm(DEFAULT_FORM) }} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">关闭</button>
            </div>
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <input value={form.title} onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none" placeholder="标题" />
              <input value={form.tags} onChange={(event) => setForm((prev) => ({ ...prev, tags: event.target.value }))} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none" placeholder="tag-a, tag-b" />
              <input value={form.module} onChange={(event) => setForm((prev) => ({ ...prev, module: event.target.value.toUpperCase() }))} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none" placeholder="模块" />
              <input value={form.docType} onChange={(event) => setForm((prev) => ({ ...prev, docType: event.target.value.toUpperCase() }))} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none" placeholder="文档类型" />
              <select value={form.knowledgeLevel} onChange={(event) => setForm((prev) => ({ ...prev, knowledgeLevel: event.target.value }))} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none">
                {['BRIEF', 'INSTANCE', 'ASSET', 'FIELD', 'DOMAIN', 'CONTRACT'].map((item) => <option key={item} value={item}>{levelLabel(item)}</option>)}
              </select>
              <select value={form.status} onChange={(event) => setForm((prev) => ({ ...prev, status: event.target.value }))} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none">
                {['DRAFT', 'REVIEW', 'PUBLISHED'].map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
              <textarea value={form.summary} onChange={(event) => setForm((prev) => ({ ...prev, summary: event.target.value }))} className="min-h-[88px] rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none md:col-span-2" placeholder="摘要" />
              <textarea value={form.content} onChange={(event) => setForm((prev) => ({ ...prev, content: event.target.value }))} className="min-h-[220px] rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none md:col-span-2" placeholder="正文" />
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button type="button" onClick={() => { setShowCreate(false); setForm(DEFAULT_FORM) }} className="rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700">取消</button>
              <button type="button" onClick={() => void createDocument()} disabled={submitting} className="rounded-2xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50">{submitting ? '创建中...' : '创建知识对象'}</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
