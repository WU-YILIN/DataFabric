import { useEffect, useMemo, useState } from 'react'
import { Archive, BookOpen, RefreshCw, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'

import {
  GenesisApi,
  type KnowledgeDocumentItem,
  type KnowledgeDocumentListResponse,
} from '../services/api'
import {
  FabricBadge,
  FabricEmptyState,
  FabricFilterSelect,
  FabricPageHeader,
  FabricPager,
  FabricSearchInput,
  FabricSection,
  FabricStatCard,
} from '../components/fabricUi'

const PAGE_SIZE = 12

function formatDateTime(value?: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function scopeLabel(item: KnowledgeDocumentItem) {
  return item.tags.includes('shared-memory') ? '公共记忆' : '项目记忆'
}

function statusTone(status: string) {
  const value = status.toUpperCase()
  if (value.includes('ARCHIVE')) return 'border-[var(--df-border)] bg-[var(--df-surface-2)] text-[var(--df-text-muted)]'
  if (value.includes('PUBLISH')) {
    return 'border-[color:color-mix(in srgb,var(--df-moss)_25%,white)] bg-[color:color-mix(in srgb,var(--df-moss)_10%,white)] text-[var(--df-moss)]'
  }
  if (value.includes('DRAFT')) {
    return 'border-[color:color-mix(in srgb,var(--df-amber)_28%,white)] bg-[color:color-mix(in srgb,var(--df-amber)_12%,white)] text-[color:color-mix(in srgb,var(--df-amber)_85%,black)]'
  }
  return 'border-[var(--df-border)] bg-[var(--df-surface-2)] text-[var(--df-text-muted)]'
}

export default function AIMemory() {
  const [response, setResponse] = useState<KnowledgeDocumentListResponse | null>(null)
  const [statsDocs, setStatsDocs] = useState<KnowledgeDocumentItem[]>([])
  const [loading, setLoading] = useState(true)
  const [operatingId, setOperatingId] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const [moduleFilter, setModuleFilter] = useState('ALL')
  const [levelFilter, setLevelFilter] = useState('ALL')
  const [scopeFilter, setScopeFilter] = useState<'ALL' | 'PROJECT' | 'SHARED'>('ALL')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [offset, setOffset] = useState(0)
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const includeShared = scopeFilter !== 'PROJECT'
      const sharedOnly = scopeFilter === 'SHARED'
      const [listData, statsData] = await Promise.all([
        GenesisApi.getKnowledgeDocuments({
          q: query.trim() || undefined,
          module: moduleFilter === 'ALL' ? undefined : moduleFilter,
          knowledge_level: levelFilter === 'ALL' ? undefined : levelFilter,
          status: statusFilter === 'ALL' ? undefined : statusFilter,
          include_shared: includeShared,
          shared_only: sharedOnly,
          limit: PAGE_SIZE,
          offset,
        }),
        GenesisApi.getKnowledgeDocuments({
          include_shared: true,
          limit: 200,
          offset: 0,
        }),
      ])
      setResponse(listData)
      setStatsDocs(statsData.items)
      if (!selectedId && listData.items.length > 0) {
        setSelectedId(listData.items[0].id)
      } else if (selectedId && !listData.items.some((item) => item.id === selectedId)) {
        setSelectedId(listData.items[0]?.id ?? null)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [query, moduleFilter, levelFilter, scopeFilter, statusFilter, offset])

  const moduleOptions = useMemo(() => {
    const modules = Array.from(new Set(statsDocs.map((item) => item.module).filter(Boolean))).sort()
    return [{ label: '全部模块', value: 'ALL' }, ...modules.map((item) => ({ label: item, value: item }))]
  }, [statsDocs])

  const levelOptions = useMemo(() => {
    const levels = Array.from(new Set(statsDocs.map((item) => item.knowledge_level).filter(Boolean))).sort()
    return [{ label: '全部层级', value: 'ALL' }, ...levels.map((item) => ({ label: item, value: item }))]
  }, [statsDocs])

  const selectedItem = useMemo(
    () => response?.items.find((item) => item.id === selectedId) ?? response?.items[0] ?? null,
    [response, selectedId],
  )

  const stats = useMemo(() => {
    const published = statsDocs.filter((item) => item.status === 'PUBLISHED').length
    const archived = statsDocs.filter((item) => item.status === 'ARCHIVED').length
    const shared = statsDocs.filter((item) => item.tags.includes('shared-memory')).length
    const fieldLevel = statsDocs.filter((item) => item.knowledge_level === 'FIELD').length
    return {
      total: statsDocs.length,
      project: statsDocs.length - shared,
      shared,
      published,
      archived,
      fieldLevel,
    }
  }, [statsDocs])

  const handleArchive = async (item: KnowledgeDocumentItem) => {
    setOperatingId(item.id)
    try {
      await GenesisApi.operateKnowledgeDocument(item.id, {
        action: item.status === 'ARCHIVED' ? 'UNARCHIVE' : 'ARCHIVE',
      })
      await load()
    } finally {
      setOperatingId(null)
    }
  }

  return (
    <div className="space-y-6">
      <FabricPageHeader
        eyebrow="AI 记忆"
        title="项目记忆与公共记忆"
        description="统一查看项目记忆、源记忆和同租户共享记忆。这里的内容会被对话、查询规划、主题域识别和治理判断共同引用。"
        actions={
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-2 rounded-[16px] border border-[var(--df-border)] bg-[var(--df-surface)] px-4 py-2 text-sm font-medium text-[var(--df-text)] hover:bg-[var(--df-surface-2)]"
          >
            <RefreshCw size={15} />
            刷新
          </button>
        }
      />

      <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
        <FabricStatCard label="记忆总数" value={stats.total} hint="当前项目与共享记忆合计" />
        <FabricStatCard label="项目记忆" value={stats.project} hint="仅当前项目可见" />
        <FabricStatCard label="公共记忆" value={stats.shared} hint="同租户共享" />
        <FabricStatCard label="字段级" value={stats.fieldLevel} hint="最细粒度知识对象" />
        <FabricStatCard label="已发布" value={stats.published} hint="可直接被引用" />
        <FabricStatCard label="已归档" value={stats.archived} hint="保留但默认弱化" />
      </div>

      <FabricSection
        title="记忆列表"
        subtitle="支持按模块、层级、范围、状态筛选。高数据量场景默认分页，不一次性加载全量结果。"
      >
        <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_160px_160px_160px_160px]">
          <FabricSearchInput
            value={query}
            placeholder="搜索标题、摘要、标签或作者"
            onChange={(value) => {
              setQuery(value)
              setOffset(0)
            }}
          />
          <FabricFilterSelect
            value={moduleFilter}
            onChange={(value) => {
              setModuleFilter(value)
              setOffset(0)
            }}
            options={moduleOptions}
          />
          <FabricFilterSelect
            value={levelFilter}
            onChange={(value) => {
              setLevelFilter(value)
              setOffset(0)
            }}
            options={levelOptions}
          />
          <FabricFilterSelect
            value={scopeFilter}
            onChange={(value) => {
              setScopeFilter(value as 'ALL' | 'PROJECT' | 'SHARED')
              setOffset(0)
            }}
            options={[
              { label: '全部范围', value: 'ALL' },
              { label: '仅项目', value: 'PROJECT' },
              { label: '仅共享', value: 'SHARED' },
            ]}
          />
          <FabricFilterSelect
            value={statusFilter}
            onChange={(value) => {
              setStatusFilter(value)
              setOffset(0)
            }}
            options={[
              { label: '全部状态', value: 'ALL' },
              { label: 'PUBLISHED', value: 'PUBLISHED' },
              { label: 'DRAFT', value: 'DRAFT' },
              { label: 'ARCHIVED', value: 'ARCHIVED' },
            ]}
          />
        </div>

        <div className="mt-5 grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(340px,0.85fr)]">
          <div className="min-w-0 space-y-3">
            {loading ? (
              <FabricEmptyState message="正在加载 AI 记忆..." />
            ) : (response?.items.length ?? 0) === 0 ? (
              <FabricEmptyState message="当前筛选条件下没有记忆内容。" />
            ) : (
              (response?.items ?? []).map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setSelectedId(item.id)}
                  className={`w-full rounded-2xl border p-4 text-left transition ${
                    selectedItem?.id === item.id
                      ? 'border-slate-900 bg-slate-900 text-white'
                      : 'border-slate-200 bg-slate-50 hover:border-slate-300 hover:bg-white'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="truncate text-base font-semibold">{item.title}</div>
                        <span
                          className={`rounded-full border px-2.5 py-1 text-xs font-medium ${
                            selectedItem?.id === item.id ? 'border-white/20 bg-white/10 text-white' : statusTone(item.status)
                          }`}
                        >
                          {item.status}
                        </span>
                        <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${selectedItem?.id === item.id ? 'border-white/20 bg-white/10 text-white' : 'border-slate-200 bg-white text-slate-600'}`}>
                          {item.knowledge_level}
                        </span>
                        <span
                          className={`rounded-full border px-2.5 py-1 text-xs font-medium ${
                            selectedItem?.id === item.id
                              ? 'border-white/20 bg-white/10 text-white'
                              : 'border-indigo-200 bg-indigo-50 text-indigo-700'
                          }`}
                        >
                          {scopeLabel(item)}
                        </span>
                      </div>
                      <div className={`mt-2 line-clamp-2 text-sm ${selectedItem?.id === item.id ? 'text-slate-200' : 'text-slate-600'}`}>
                        {item.summary || item.preview || '暂无摘要'}
                      </div>
                      <div className={`mt-3 flex flex-wrap gap-2 text-xs ${selectedItem?.id === item.id ? 'text-slate-300' : 'text-slate-500'}`}>
                        <span>模块：{item.module}</span>
                        <span>类型：{item.doc_type}</span>
                        <span>事实引用：{item.fact_ref_count}</span>
                        <span>更新时间：{formatDateTime(item.updated_at)}</span>
                      </div>
                    </div>
                  </div>
                </button>
              ))
            )}

            {response ? (
              <FabricPager total={response.total} limit={response.limit} offset={response.offset} onChange={setOffset} />
            ) : null}
          </div>

          <div className="min-w-0 rounded-[28px] border border-slate-200 bg-slate-50 p-5">
            {!selectedItem ? (
              <FabricEmptyState message="左侧选择一条记忆后，在这里查看内容、关联对象和事实引用。" />
            ) : (
              <div className="space-y-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                      <Sparkles size={14} />
                      记忆详情
                    </div>
                    <h3 className="mt-2 text-xl font-semibold tracking-tight text-slate-900">{selectedItem.title}</h3>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <FabricBadge value={selectedItem.status} />
                      <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600">
                        {selectedItem.knowledge_level}
                      </span>
                      <span className="rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700">
                        {scopeLabel(selectedItem)}
                      </span>
                      <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600">
                        {selectedItem.module}
                      </span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleArchive(selectedItem)}
                    disabled={operatingId === selectedItem.id}
                    className="inline-flex items-center gap-2 rounded-[16px] border border-[var(--df-border)] bg-[var(--df-surface)] px-3 py-2 text-sm text-[var(--df-text)] hover:bg-[var(--df-surface-2)] disabled:opacity-50"
                  >
                    <Archive size={15} />
                    {selectedItem.status === 'ARCHIVED' ? '恢复' : '归档'}
                  </button>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="text-sm font-semibold text-slate-900">内容摘要</div>
                  <div className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-600">
                    {selectedItem.summary || selectedItem.preview || '暂无摘要。'}
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="text-sm font-semibold text-slate-900">元信息</div>
                  <div className="mt-3 grid gap-2 text-sm text-slate-600 md:grid-cols-2">
                    <div>作者：{selectedItem.author}</div>
                    <div>最后编辑：{selectedItem.last_editor}</div>
                    <div>创建时间：{formatDateTime(selectedItem.created_at)}</div>
                    <div>更新时间：{formatDateTime(selectedItem.updated_at)}</div>
                    <div>评论数：{selectedItem.comment_count}</div>
                    <div>发布于：{formatDateTime(selectedItem.published_at)}</div>
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="text-sm font-semibold text-slate-900">标签与关联对象</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {selectedItem.tags.length > 0 ? (
                      selectedItem.tags.map((tag) => (
                        <span
                          key={tag}
                          className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-600"
                        >
                          {tag}
                        </span>
                      ))
                    ) : (
                      <span className="text-sm text-slate-500">暂无标签</span>
                    )}
                  </div>
                  <div className="mt-4 space-y-2">
                    {selectedItem.object_refs.length > 0 ? (
                      selectedItem.object_refs.map((item, index) => (
                        <div
                          key={`${String(item.object_type || item.source_type)}-${String(item.object_id || item.source_id)}-${index}`}
                          className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600"
                        >
                          {String(item.label || item.object_type || item.source_type || 'OBJECT')} · {String(item.object_id || item.source_id || '-')}
                        </div>
                      ))
                    ) : selectedItem.related_objects.length > 0 ? (
                      selectedItem.related_objects.map((item) => (
                        <div
                          key={`${item.source_type}-${item.source_id}`}
                          className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600"
                        >
                          {item.label || item.source_type} · {item.source_id}
                        </div>
                      ))
                    ) : (
                      <div className="text-sm text-slate-500">当前没有关联对象。</div>
                    )}
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-semibold text-slate-900">事实引用</div>
                    <span
                      className={`rounded-full border px-2.5 py-1 text-xs font-medium ${
                        selectedItem.has_fact_refs
                          ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                          : 'border-amber-200 bg-amber-50 text-amber-700'
                      }`}
                    >
                      {selectedItem.has_fact_refs ? `${selectedItem.fact_ref_count} 条事实引用` : '说明性内容'}
                    </span>
                  </div>
                  <div className="mt-3 space-y-2">
                    {selectedItem.fact_refs.length > 0 ? (
                      selectedItem.fact_refs.map((item, index) => (
                        <div
                          key={`${String(item.fact_type)}-${String(item.fact_id)}-${index}`}
                          className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600"
                        >
                          {String(item.fact_type || 'FACT')} · {String(item.fact_id || '-')}
                        </div>
                      ))
                    ) : (
                      <div className="text-sm text-slate-500">该知识对象暂无事实引用，仅作为说明性内容。</div>
                    )}
                  </div>
                </div>

                {selectedItem.meta_payload?.source_id ? (
                  <div className="flex flex-wrap gap-3">
                    <Link
                      to={`/knowledge?source_type=DATA_SOURCE&source_id=${selectedItem.meta_payload.source_id}`}
                      className="inline-flex items-center gap-2 rounded-[16px] border border-[var(--df-border)] bg-[var(--df-surface)] px-3 py-2 text-sm text-[var(--df-text)] hover:bg-[var(--df-surface-2)]"
                    >
                      <BookOpen size={15} />
                      查看关联知识文档
                    </Link>
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </div>
      </FabricSection>
    </div>
  )
}
