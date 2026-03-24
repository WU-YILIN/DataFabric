import axios from 'axios'
import { type FormEvent, Fragment, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Check, CheckCircle2, CircleDashed, Copy, FolderKanban, Send } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

import { useSession } from '../auth/session'
import {
  GenesisApi,
  type AssistantChatCitation,
  type AssistantChatMessage,
  type FabricContextRef,
  type AssistantRuntimeConfigPayload,
  type FabricQuerySubmission,
} from '../services/api'
import { getAssistantRuntimeConfig } from '../utils/assistantConfig'
import {
  createConversationId,
  getChatConversation,
  summarizeConversationTitle,
  upsertChatConversation,
  type StoredChatConversation,
} from '../utils/chatWorkspace'
import { getConfirmedProjectId } from '../utils/workspaceSelection'

type UiMessage = AssistantChatMessage & {
  id: string
  citations?: AssistantChatCitation[]
  mode?: string
  queryTrace?: FabricQuerySubmission
}

const MAX_CHAT_MESSAGES = 30
const MAX_CHAT_CONTENT_LENGTH = 12000

const STARTER_PROMPTS = [
  '总结当前项目里最重要的业务链路',
  '列出这次回答命中的字段级事实和待确认候选',
  '解释当前问题为什么走这条查询路径',
  '基于项目记忆输出一份结构化简报',
]

function createWelcomeMessage(): UiMessage {
  return {
    id: 'welcome',
    role: 'assistant',
    content:
      '我是 DataFabric AI 助手。你可以直接问业务问题、字段含义、项目记忆、知识文档和治理建议。我会优先引用字段级事实，其次才是资产级知识和简报。',
  }
}

function sanitizeChatMessages(input: UiMessage[]): AssistantChatMessage[] {
  return input
    .filter((message) => message.id !== 'welcome')
    .map((message) => ({
      role: message.role,
      content: (message.content || '').trim().slice(0, MAX_CHAT_CONTENT_LENGTH),
    }))
    .filter((message) => message.content.length > 0)
    .slice(-MAX_CHAT_MESSAGES)
}

function getRuntimePayload(): AssistantRuntimeConfigPayload | undefined {
  const config = getAssistantRuntimeConfig()
  const payload: AssistantRuntimeConfigPayload = {}
  if (config.apiKey.trim()) payload.api_key = config.apiKey.trim()
  if (config.baseUrl.trim()) payload.base_url = config.baseUrl.trim()
  if (config.model.trim()) payload.model = config.model.trim()
  return Object.keys(payload).length > 0 ? payload : undefined
}

function normalizeAssistantContent(content: string) {
  return content
    .replace(/\r/g, '')
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .replace(/^\s*("""|'''|```markdown|```md|```text)\s*/i, '')
    .replace(/\s*("""|'''|```)\s*$/i, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function renderInline(text: string) {
  const chunks = text.split(/(`[^`]+`)/g).filter(Boolean)
  return chunks.map((chunk, index) => {
    if (chunk.startsWith('`') && chunk.endsWith('`')) {
      return (
        <code
          key={`${chunk}-${index}`}
          className="df-mono rounded-md bg-white px-1.5 py-0.5 text-[0.92em] text-[var(--df-ink)] ring-1 ring-[var(--df-border)]"
        >
          {chunk.slice(1, -1)}
        </code>
      )
    }
    return <Fragment key={`${chunk}-${index}`}>{chunk}</Fragment>
  })
}

function MarkdownPreview({ content }: { content: string }) {
  const [copiedBlock, setCopiedBlock] = useState<string | null>(null)
  const normalized = normalizeAssistantContent(content)
  const segments = normalized.split(/```/)

  async function copyCode(code: string) {
    try {
      await navigator.clipboard.writeText(code)
      setCopiedBlock(code)
      window.setTimeout(() => setCopiedBlock(null), 1200)
    } catch {
      setCopiedBlock(null)
    }
  }

  return segments.map((segment, segmentIndex) => {
    if (segmentIndex % 2 === 1) {
      const lines = segment.replace(/^\n+|\n+$/g, '').split('\n')
      const languageCandidate = (lines[0] || '').trim()
      const hasLanguage = /^[a-zA-Z0-9_+#.-]+$/.test(languageCandidate)
      const language = hasLanguage ? languageCandidate : ''
      const code = hasLanguage ? lines.slice(1).join('\n') : lines.join('\n')

      return (
        <div key={`code-${segmentIndex}`} className="my-4 overflow-hidden rounded-2xl border border-[var(--df-border)] bg-white">
          <div className="flex items-center justify-between border-b border-[var(--df-border)] bg-white px-4 py-2.5">
            <div className="text-[11px] uppercase tracking-[0.16em] text-[var(--df-text-soft)]">
              {language || 'code'}
            </div>
            <button
              type="button"
              onClick={() => void copyCode(code)}
              className="inline-flex items-center gap-1 rounded-full border border-[var(--df-border)] bg-white px-2.5 py-1 text-[11px] text-[var(--df-text-muted)] transition hover:border-[var(--df-border-strong)] hover:text-[var(--df-text)]"
            >
              {copiedBlock === code ? <Check size={12} /> : <Copy size={12} />}
              <span>{copiedBlock === code ? '已复制' : '复制代码'}</span>
            </button>
          </div>
          <pre className="df-mono overflow-x-auto px-4 py-4 text-[13px] leading-6 text-[var(--df-text)]">
            <code>{code}</code>
          </pre>
        </div>
      )
    }

    const blocks = segment
      .split(/\n{2,}/)
      .map((item) => item.trim())
      .filter(Boolean)

    return blocks.map((block, blockIndex) => {
      const lines = block.split('\n').map((line) => line.trim()).filter(Boolean)
      if (lines.length === 0) return null

      if (lines.length === 1 && /^#{1,3}\s+/.test(lines[0])) {
        const depth = lines[0].match(/^#+/)?.[0].length ?? 1
        const text = lines[0].replace(/^#{1,3}\s+/, '')
        const className =
          depth === 1
            ? 'df-display text-[22px] font-semibold leading-8 text-[var(--df-text)]'
            : depth === 2
              ? 'df-display text-[18px] font-semibold leading-7 text-[var(--df-text)]'
              : 'text-[16px] font-semibold leading-7 text-[var(--df-text)]'

        return (
          <h3 key={`h-${segmentIndex}-${blockIndex}`} className={className}>
            {renderInline(text)}
          </h3>
        )
      }

      if (lines.every((line) => /^[-*]\s+/.test(line))) {
        return (
          <ul key={`ul-${segmentIndex}-${blockIndex}`} className="space-y-2 pl-5 text-[15px] leading-8 text-[var(--df-text)]">
            {lines.map((line, index) => (
              <li key={`${line}-${index}`} className="list-disc">
                {renderInline(line.replace(/^[-*]\s+/, ''))}
              </li>
            ))}
          </ul>
        )
      }

      if (lines.every((line) => /^\d+\.\s+/.test(line))) {
        return (
          <ol key={`ol-${segmentIndex}-${blockIndex}`} className="space-y-2 pl-5 text-[15px] leading-8 text-[var(--df-text)]">
            {lines.map((line, index) => (
              <li key={`${line}-${index}`} className="list-decimal">
                {renderInline(line.replace(/^\d+\.\s+/, ''))}
              </li>
            ))}
          </ol>
        )
      }

      return (
        <p
          key={`p-${segmentIndex}-${blockIndex}`}
          className="df-body whitespace-pre-wrap text-[15px] leading-[2.08] tracking-[0.002em] text-[var(--df-text)]"
        >
          {renderInline(lines.join('\n'))}
        </p>
      )
    })
  })
}

function groupCitations(citations?: AssistantChatCitation[]) {
  const fact: AssistantChatCitation[] = []
  const candidate: AssistantChatCitation[] = []
  const memory: AssistantChatCitation[] = []

  for (const item of citations || []) {
    if (item.kind === 'FACT' || item.evidence_mode === 'FACT') {
      fact.push(item)
      continue
    }
    if (item.kind === 'CANDIDATE' || item.evidence_mode === 'CANDIDATE') {
      candidate.push(item)
      continue
    }
    memory.push(item)
  }

  return { fact, candidate, memory }
}

function CitationBlock({
  title,
  items,
  tone,
  icon,
}: {
  title: string
  items: AssistantChatCitation[]
  tone: string
  icon: ReactNode
}) {
  if (items.length === 0) return null

  return (
    <div className="mt-4">
      <div className="mb-2 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.16em] text-[var(--df-text-soft)]">
        {icon}
        <span>{title}</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <span key={`${item.type}-${item.id}-${item.label}`} className={`rounded-full border px-2.5 py-1 text-xs ${tone}`}>
            {item.label}
            {item.status ? ` · ${item.status}` : ''}
          </span>
        ))}
      </div>
    </div>
  )
}

type ContextRefGroup = {
  key: string
  title: string
  items: FabricContextRef[]
}

function isFabricContextRef(value: unknown): value is FabricContextRef {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    'object_type' in value &&
    typeof (value as { object_type?: unknown }).object_type === 'string'
  )
}

function normalizeContextRefList(value: unknown): FabricContextRef[] {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => {
      if (isFabricContextRef(item)) return item
      if (typeof item === 'number' || typeof item === 'string') {
        return {
          id: item,
          object_type: 'UNKNOWN',
          label: String(item),
        } satisfies FabricContextRef
      }
      return null
    })
    .filter((item): item is FabricContextRef => item != null)
}

function getContextRefGroups(trace: FabricQuerySubmission): ContextRefGroup[] {
  const raw = trace.plan.plan_payload?.context_refs
  if (!raw || typeof raw !== 'object') return []
  const mapping = raw as Record<string, unknown>
  const order: Array<[string, string]> = [
    ['fields', '命中字段'],
    ['assets', '命中资产'],
    ['documents', '命中文档'],
    ['sources', '命中数据源'],
    ['contracts', '命中契约'],
  ]

  return order
    .map(([key, title]) => ({
      key,
      title,
      items: normalizeContextRefList(mapping[key]),
    }))
    .filter((group) => group.items.length > 0)
}

function contextReasonLabel(reason?: string | null) {
  switch (reason) {
    case 'matched_field':
      return '字段直匹配'
    case 'matched_source':
      return '数据源命中'
    case 'matched_memory':
      return '记忆命中'
    case 'knowledge_object_ref':
      return '知识对象引用'
    case 'knowledge_fact_ref':
      return '知识事实引用'
    case 'field_fact':
      return '字段事实'
    case 'matched_contract':
      return '契约命中'
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

function TraceCard({ trace }: { trace: FabricQuerySubmission }) {
  const contextGroups = getContextRefGroups(trace)

  return (
    <details className="mt-4 rounded-2xl border border-[var(--df-border)] bg-white px-4 py-3 text-sm text-[var(--df-text-muted)]">
      <summary className="cursor-pointer list-none text-[11px] font-medium uppercase tracking-[0.16em] text-[var(--df-text-soft)]">
        执行线索
      </summary>

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <div className="rounded-2xl bg-white px-4 py-3">
          <div className="text-[11px] uppercase tracking-[0.16em] text-[var(--df-text-soft)]">主题域</div>
          <div className="mt-1 text-sm font-medium text-[var(--df-text)]">{trace.intent.domain || '通用主题'}</div>
        </div>
        <div className="rounded-2xl bg-white px-4 py-3">
          <div className="text-[11px] uppercase tracking-[0.16em] text-[var(--df-text-soft)]">执行模式</div>
          <div className="mt-1 text-sm font-medium text-[var(--df-text)]">{trace.run.execution_mode}</div>
        </div>
      </div>

      <div className="mt-3 rounded-2xl bg-white px-4 py-4">
        <div className="text-[11px] uppercase tracking-[0.16em] text-[var(--df-text-soft)]">路由说明</div>
        <p className="mt-2 text-sm leading-7 text-[var(--df-text-muted)]">{trace.plan.rationale}</p>
      </div>

      {contextGroups.length > 0 ? (
        <div className="mt-3 rounded-2xl bg-white px-4 py-4">
          <div className="text-[11px] uppercase tracking-[0.16em] text-[var(--df-text-soft)]">命中对象</div>
          <div className="mt-3 space-y-3">
            {contextGroups.map((group) => (
              <div key={group.key}>
                <div className="mb-2 text-xs font-medium text-[var(--df-text)]">{group.title}</div>
                <div className="flex flex-wrap gap-2">
                  {group.items.slice(0, 6).map((item) => (
                    <div
                      key={`${group.key}-${item.object_type}-${item.id}`}
                      className="min-w-[180px] rounded-2xl border border-[var(--df-border)] bg-white px-3 py-2"
                    >
                      <div className="truncate text-sm font-medium text-[var(--df-text)]">
                        {item.label || `${contextObjectLabel(item.object_type)} ${item.id}`}
                      </div>
                      <div className="mt-1 text-[11px] leading-5 text-[var(--df-text-soft)]">
                        {contextObjectLabel(item.object_type)} · {contextReasonLabel(item.reason)} ·{' '}
                        {contextEvidenceLabel(item.evidence_mode)}
                      </div>
                    </div>
                  ))}
                  {group.items.length > 6 ? (
                    <div className="rounded-2xl border border-dashed border-[var(--df-border)] px-3 py-2 text-xs text-[var(--df-text-soft)]">
                      +{group.items.length - 6} 个未展开
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-2">
        <span className="rounded-full border border-[var(--df-border)] bg-white px-2.5 py-1 text-xs text-[var(--df-text-muted)]">
          {trace.intent.intent_type}
        </span>
        <span className="rounded-full border border-[var(--df-border)] bg-white px-2.5 py-1 text-xs text-[var(--df-text-muted)]">
          {trace.plan.selected_path}
        </span>
        <span className="rounded-full border border-[var(--df-border)] bg-white px-2.5 py-1 text-xs text-[var(--df-text-muted)]">
          {trace.run.status}
        </span>
      </div>

      <div className="mt-3 break-all text-[11px] text-[var(--df-text-soft)]">Trace ID: {trace.trace_id}</div>
    </details>
  )
}

function AssistantMessage({ message }: { message: UiMessage }) {
  const sections = groupCitations(message.citations)

  return (
    <div className="w-full">
      <div className="mx-auto w-full max-w-[1080px] px-6 py-7">
        <div className="rounded-[28px] border border-[var(--df-border-strong)] bg-white px-6 py-5 shadow-[0_10px_20px_rgba(31,41,51,0.06)]">
          <div className="space-y-4">
            {normalizeAssistantContent(message.content) ? (
              <MarkdownPreview content={message.content} />
            ) : (
              <p className="df-body text-[15px] leading-8 text-[var(--df-text-muted)]">当前没有可展示的回答内容。</p>
            )}
          </div>
        </div>

        <CitationBlock
          title="已确认事实"
          items={sections.fact}
          tone="border-emerald-200 bg-emerald-50 text-emerald-700"
          icon={<CheckCircle2 size={12} />}
        />
        <CitationBlock
          title="候选判断"
          items={sections.candidate}
          tone="border-amber-200 bg-amber-50 text-amber-700"
          icon={<CircleDashed size={12} />}
        />
        <CitationBlock
          title="引用记忆"
          items={sections.memory}
          tone="border-[var(--df-border)] bg-white text-[var(--df-text-muted)]"
          icon={<FolderKanban size={12} />}
        />
        {message.queryTrace ? <TraceCard trace={message.queryTrace} /> : null}
      </div>
    </div>
  )
}

function UserMessage({ message }: { message: UiMessage }) {
  return (
    <div className="w-full">
      <div className="mx-auto flex w-full max-w-[1080px] justify-end px-6 py-5">
        <div className="max-w-[68%] rounded-full bg-white px-5 py-3 text-[15px] leading-7 text-[var(--df-text)] shadow-sm ring-1 ring-black/5">
          {message.content}
        </div>
      </div>
    </div>
  )
}

export default function AIChat() {
  const { activeProject, isLoading: sessionLoading } = useSession()
  const confirmedProjectId = getConfirmedProjectId()
  const [searchParams, setSearchParams] = useSearchParams()
  const conversationIdFromUrl = searchParams.get('conversation')

  const [conversationId, setConversationId] = useState<string | null>(conversationIdFromUrl)
  const [messages, setMessages] = useState<UiMessage[]>([createWelcomeMessage()])
  const [draft, setDraft] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [includeKnowledge, setIncludeKnowledge] = useState(true)
  const [includeSources, setIncludeSources] = useState(true)
  const [runtimeHint, setRuntimeHint] = useState('')
  const [pendingSuggestions, setPendingSuggestions] = useState<string[]>([])

  const scrollViewportRef = useRef<HTMLDivElement | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  const isProjectConfirmed = activeProject?.id != null && confirmedProjectId === activeProject.id
  const messageFeed = useMemo(() => messages.filter((message) => message.id !== 'welcome' || messages.length === 1), [messages])

  useEffect(() => {
    const nextConversationId = searchParams.get('conversation')
    setConversationId(nextConversationId)
    if (!nextConversationId) {
      setMessages([createWelcomeMessage()])
      return
    }
    const conversation = getChatConversation(nextConversationId)
    if (!conversation) {
      setMessages([createWelcomeMessage()])
      return
    }
    const restoredMessages = sanitizeChatMessages(
      conversation.messages.map((item, index) => ({
        ...item,
        id: `${nextConversationId}-restored-${index}`,
      })),
    )
    setMessages([
      createWelcomeMessage(),
      ...restoredMessages.map((item, index) => ({
        ...item,
        id: `${nextConversationId}-${index}`,
      })),
    ])
  }, [searchParams])

  useEffect(() => {
    const viewport = scrollViewportRef.current
    if (!viewport) return
    viewport.scrollTo({ top: viewport.scrollHeight, behavior: 'smooth' })
  }, [messages, isSubmitting])

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = '0px'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`
  }, [draft])

  function persistConversation(nextMessages: UiMessage[], nextConversationId: string) {
    if (!activeProject?.id) return
    const storedMessages = sanitizeChatMessages(nextMessages)

    const title = summarizeConversationTitle(storedMessages, '新对话')
    const payload: StoredChatConversation = {
      id: nextConversationId,
      projectId: activeProject.id,
      title,
      updatedAt: new Date().toISOString(),
      messages: storedMessages,
    }
    upsertChatConversation(payload)
  }

  function appendUserMessage(content: string, nextConversationId: string) {
    const next: UiMessage[] = [
      ...messages,
      {
        id: `${nextConversationId}-user-${Date.now()}`,
        role: 'user',
        content,
      },
    ]
    setMessages(next)
    persistConversation(next, nextConversationId)
    return next
  }

  async function handleSubmit(event?: FormEvent<HTMLFormElement>, overridePrompt?: string) {
    event?.preventDefault()
    const question = (overridePrompt ?? draft).trim()
    if (!question || isSubmitting || !activeProject?.id) return
    if (!isProjectConfirmed) {
      setError('请先在项目管理中确认当前项目，再开始提问。')
      return
    }

    setError(null)
    setPendingSuggestions([])
    setRuntimeHint('')
    setDraft(overridePrompt ? draft : '')

    const nextConversationId = conversationId ?? createConversationId()
    if (!conversationId) {
      setConversationId(nextConversationId)
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set('conversation', nextConversationId)
        return next
      })
    }

    const nextMessages = appendUserMessage(question, nextConversationId)
    setIsSubmitting(true)

    try {
      const outgoingMessages = sanitizeChatMessages(nextMessages)
      if (outgoingMessages.length === 0) {
        throw new Error('当前没有可发送的有效消息。')
      }

      const response = await GenesisApi.assistantChat({
        messages: outgoingMessages,
        include_knowledge: includeKnowledge,
        include_sources: includeSources,
        runtime_config: getRuntimePayload(),
      })

      const assistantMessage: UiMessage = {
        id: `${nextConversationId}-assistant-${Date.now()}`,
        role: 'assistant',
        content: response.answer,
        citations: response.citations,
        mode: response.mode,
        queryTrace: response.query_trace,
      }

      const combined = [...nextMessages, assistantMessage]
      setMessages(combined)
      persistConversation(combined, nextConversationId)
      setPendingSuggestions(response.suggestions || [])
      if (response.mode && response.mode !== 'llm') {
        setRuntimeHint(`当前回答模式：${response.mode}`)
      }
    } catch (submitError) {
      let message = submitError instanceof Error ? submitError.message : '发送失败，请稍后重试。'
      if (axios.isAxiosError(submitError)) {
        const status = submitError.response?.status
        const detail = submitError.response?.data?.detail
        if (status === 422) {
          message = '本次对话历史不符合接口要求。系统已自动裁剪为最近 30 条有效消息，请重新发送一次。'
        } else if (typeof detail === 'string' && detail.trim()) {
          message = detail.trim()
        } else if (detail && typeof detail === 'object' && typeof detail.message === 'string') {
          message = detail.message
        }
      }
      setError(message)
    } finally {
      setIsSubmitting(false)
      textareaRef.current?.focus()
    }
  }

  const emptyState = messageFeed.length <= 1

  return (
    <div className="flex h-[calc(100vh-96px)] min-h-0 flex-col bg-white">
      {!isProjectConfirmed ? (
        <div className="mx-auto mt-4 w-full max-w-[1080px] px-6">
          <div className="rounded-[28px] border border-[var(--df-border)] bg-white px-6 py-6 shadow-[var(--df-shadow-soft)]">
            <div className="df-display text-xl font-semibold text-[var(--df-text)]">先确认项目，再开始对话</div>
            <p className="mt-3 text-[15px] leading-7 text-[var(--df-text-muted)]">
              Chat 会绑定当前项目的记忆、知识文档、字段事实和查询追踪。请先在项目管理中选择并确认项目。
            </p>
            <div className="mt-4">
              <Link
                to="/projects"
                className="inline-flex rounded-full border border-[var(--df-border)] bg-white px-4 py-2 text-sm text-[var(--df-text)] shadow-sm transition hover:border-[var(--df-border-strong)]"
              >
                前往确认项目
              </Link>
            </div>
          </div>
        </div>
      ) : null}

      <div ref={scrollViewportRef} className="min-h-0 flex-1 overflow-y-auto">
        {emptyState ? (
          <div className="mx-auto flex h-full w-full max-w-[1080px] flex-col justify-end px-6 pb-28 pt-8">
            <div className="grid w-full gap-3 sm:grid-cols-2">
              {STARTER_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => {
                    setDraft(prompt)
                    requestAnimationFrame(() => textareaRef.current?.focus())
                  }}
                  className="rounded-3xl border border-[var(--df-border)] bg-white px-5 py-4 text-left text-sm leading-7 text-[var(--df-text)] shadow-sm transition hover:-translate-y-0.5 hover:border-[var(--df-border-strong)] hover:shadow-[var(--df-shadow-soft)]"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="pb-32 pt-2">
            {messageFeed.map((message) =>
              message.role === 'assistant' ? (
                <AssistantMessage key={message.id} message={message} />
              ) : (
                <UserMessage key={message.id} message={message} />
              ),
            )}

            {isSubmitting ? (
              <div className="w-full">
                <div className="mx-auto w-full max-w-[1080px] px-6 py-7 text-[15px] text-[var(--df-text-muted)]">
                  正在整理回答…
                </div>
              </div>
            ) : null}

            {pendingSuggestions.length > 0 ? (
              <div className="mx-auto mt-2 w-full max-w-[1080px] px-6 pb-6">
                <div className="flex flex-wrap gap-2">
                  {pendingSuggestions.slice(0, 4).map((item) => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => void handleSubmit(undefined, item)}
                      className="rounded-full border border-[var(--df-border)] bg-white px-3 py-1.5 text-xs text-[var(--df-text-muted)] transition hover:border-[var(--df-border-strong)] hover:bg-white hover:text-[var(--df-text)]"
                    >
                      {item}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        )}
      </div>

      <div className="pointer-events-none fixed bottom-0 left-0 right-0 z-20 bg-white/96">
        <div className="pointer-events-auto mx-auto w-full max-w-[1200px] px-6 pb-4 pt-3">
          <div className="rounded-[22px] border border-[var(--df-border)] bg-white px-2.5 py-2.5 shadow-[0_10px_18px_rgba(31,41,51,0.08)]">
            <form onSubmit={handleSubmit}>
              <div className="overflow-hidden rounded-[18px] border border-[var(--df-border)] bg-white transition focus-within:border-[var(--df-border-strong)]">
                <textarea
                  ref={textareaRef}
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault()
                      void handleSubmit()
                    }
                  }}
                  placeholder="给 DataFabric 发送消息"
                  rows={1}
                  className="block max-h-40 min-h-[48px] w-full resize-none border-0 bg-transparent px-3.5 py-3 text-[15px] leading-7 text-[var(--df-text)] outline-none placeholder:text-[var(--df-text-soft)]"
                />
                <div className="flex items-center justify-between gap-2 border-t border-[var(--df-border)] px-3 py-2">
                  <div className="flex flex-wrap items-center gap-2 text-[10px] text-[var(--df-text-soft)]">
                    <label className="inline-flex items-center gap-2">
                      <input
                        type="checkbox"
                        className="h-3.5 w-3.5 rounded border-[var(--df-border)] text-[var(--df-ink)] focus:ring-[var(--df-ink)]"
                        checked={includeKnowledge}
                        onChange={(event) => setIncludeKnowledge(event.target.checked)}
                      />
                      <span>引用记忆</span>
                    </label>
                    <label className="inline-flex items-center gap-2">
                      <input
                        type="checkbox"
                        className="h-3.5 w-3.5 rounded border-[var(--df-border)] text-[var(--df-ink)] focus:ring-[var(--df-ink)]"
                        checked={includeSources}
                        onChange={(event) => setIncludeSources(event.target.checked)}
                      />
                      <span>引用数据源</span>
                    </label>
                    {runtimeHint ? <span>{runtimeHint}</span> : null}
                  </div>

                  <button
                    type="submit"
                    disabled={isSubmitting || !draft.trim() || !isProjectConfirmed || sessionLoading}
                    className="inline-flex h-9 items-center justify-center gap-1.5 rounded-full bg-[#111827] px-3 text-white shadow-sm transition hover:bg-black disabled:cursor-not-allowed disabled:bg-slate-300"
                    aria-label="发送消息"
                  >
                    <Send size={18} />
                    <span className="text-[13px]">发送</span>
                  </button>
                </div>
              </div>
            </form>

            {error ? <div className="mt-3 text-sm text-[var(--df-rose)]">{error}</div> : null}
          </div>
        </div>
      </div>
    </div>
  )
}
