import { FormEvent, useEffect, useMemo, useState } from 'react'
import { clsx } from 'clsx'
import { MessageSquare, RefreshCw, Send, Users2, Workflow } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import {
  GenesisApi,
  type CollaborationOverviewResponse,
  type CollaborationWorkflowDetailResponse,
  type CollaborationWorkflowListResponse,
} from '../services/api'

const statusClass: Record<string, string> = {
  PENDING_APPROVAL: 'bg-amber-100 text-amber-700',
  IN_PROGRESS: 'bg-cyan-100 text-cyan-700',
  REVISION_REQUIRED: 'bg-rose-100 text-rose-700',
  COMPLETED: 'bg-emerald-100 text-emerald-700',
  REJECTED: 'bg-slate-200 text-slate-700',
}

const CollaborationWorkflowPage = () => {
  const navigate = useNavigate()
  const [overview, setOverview] = useState<CollaborationOverviewResponse | null>(null)
  const [workflows, setWorkflows] = useState<CollaborationWorkflowListResponse | null>(null)
  const [detail, setDetail] = useState<CollaborationWorkflowDetailResponse | null>(null)
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<number | null>(null)

  const [loadingOverview, setLoadingOverview] = useState(false)
  const [loadingList, setLoadingList] = useState(false)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [operating, setOperating] = useState(false)

  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const [filters, setFilters] = useState({
    q: '',
    status: 'ALL',
    initiated_by_me: false,
    my_todos_only: false,
  })

  const [createForm, setCreateForm] = useState({
    workflow_type: 'EVENT_GOVERNANCE',
    source_type: 'TRACKING_EVENT',
    source_id: '',
    title: '',
    description: '',
    priority: 'MEDIUM',
    assignee_role: 'APPROVER',
  })
  const [commentText, setCommentText] = useState('')
  const [actionNote, setActionNote] = useState('')

  const availableStatuses = useMemo(
    () => ['PENDING_APPROVAL', 'IN_PROGRESS', 'REVISION_REQUIRED', 'COMPLETED', 'REJECTED'],
    [],
  )

  const loadOverview = async () => {
    setLoadingOverview(true)
    setError(null)
    try {
      const data = await GenesisApi.getCollaborationOverview()
      setOverview(data)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load collaboration overview')
    } finally {
      setLoadingOverview(false)
    }
  }

  const loadWorkflows = async () => {
    setLoadingList(true)
    setError(null)
    try {
      const data = await GenesisApi.getCollaborationWorkflows({
        q: filters.q.trim() || undefined,
        status: filters.status === 'ALL' ? undefined : filters.status,
        initiated_by_me: filters.initiated_by_me || undefined,
        my_todos_only: filters.my_todos_only || undefined,
        limit: 100,
        offset: 0,
      })
      setWorkflows(data)
      if (!selectedWorkflowId && data.items.length > 0) {
        setSelectedWorkflowId(data.items[0].id)
      }
      if (selectedWorkflowId && !data.items.find((item) => item.id === selectedWorkflowId)) {
        setSelectedWorkflowId(data.items[0]?.id ?? null)
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load workflows')
    } finally {
      setLoadingList(false)
    }
  }

  const loadDetail = async (workflowId: number) => {
    setLoadingDetail(true)
    setError(null)
    try {
      const data = await GenesisApi.getCollaborationWorkflowDetail(workflowId)
      setDetail(data)
      setCommentText('')
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load workflow detail')
      setDetail(null)
    } finally {
      setLoadingDetail(false)
    }
  }

  useEffect(() => {
    void loadOverview()
    void loadWorkflows()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (selectedWorkflowId != null) {
      void loadDetail(selectedWorkflowId)
    } else {
      setDetail(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedWorkflowId])

  const onRefresh = async () => {
    await Promise.all([loadOverview(), loadWorkflows()])
    if (selectedWorkflowId != null) {
      await loadDetail(selectedWorkflowId)
    }
  }

  const onApplyFilters = async (event: FormEvent) => {
    event.preventDefault()
    await loadWorkflows()
  }

  const onCreateWorkflow = async (event: FormEvent) => {
    event.preventDefault()
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const created = await GenesisApi.createCollaborationWorkflow({
        workflow_type: createForm.workflow_type,
        source_type: createForm.source_type,
        source_id: createForm.source_id.trim(),
        title: createForm.title.trim(),
        description: createForm.description.trim() || null,
        priority: createForm.priority,
        assignee_role: createForm.assignee_role,
      })
      setMessage(`Workflow #${created.workflow.id} created`)
      setCreateForm((prev) => ({
        ...prev,
        source_id: '',
        title: '',
        description: '',
      }))
      await Promise.all([loadOverview(), loadWorkflows()])
      setSelectedWorkflowId(created.workflow.id)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to create workflow')
    } finally {
      setOperating(false)
    }
  }

  const onAddComment = async () => {
    if (!detail || !commentText.trim()) {
      return
    }
    setOperating(true)
    setError(null)
    try {
      await GenesisApi.addCollaborationComment(detail.workflow.id, { content: commentText.trim() })
      await loadDetail(detail.workflow.id)
      await loadOverview()
      setCommentText('')
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to add comment')
    } finally {
      setOperating(false)
    }
  }

  const operateWorkflow = async (action: 'APPROVE' | 'REJECT' | 'REQUEST_REVISION' | 'START' | 'COMPLETE') => {
    if (!detail) {
      return
    }
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      await GenesisApi.operateCollaborationWorkflow(detail.workflow.id, {
        action,
        note: actionNote.trim() || undefined,
      })
      setMessage(`Action ${action} applied`)
      await Promise.all([loadOverview(), loadWorkflows(), loadDetail(detail.workflow.id)])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? `Failed to ${action.toLowerCase()} workflow`)
    } finally {
      setOperating(false)
    }
  }

  const openKnowledgeForLinkedObject = () => {
    if (!detail) {
      return
    }
    const params = new URLSearchParams({
      source_type: detail.linked_object.source_type,
      source_id: detail.linked_object.source_id,
    })
    navigate(`/knowledge?${params.toString()}`)
  }

  return (
    <div className="max-w-7xl mx-auto space-y-4 animate-in fade-in slide-in-from-bottom-8 duration-700">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">Collaboration & Workflow</h2>
          <p className="text-slate-500 text-base">Manage todo items, approvals, comments, and workflow history.</p>
        </div>
        <button
          onClick={() => void onRefresh()}
          disabled={loadingOverview || loadingList || loadingDetail}
          className="rounded-xl bg-slate-900 text-white px-4 py-2.5 font-medium hover:bg-slate-800 disabled:opacity-60 flex items-center gap-2"
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </header>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
      {message && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>
      )}

      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Total Workflows</p>
          <p className="text-2xl font-bold text-slate-900">{overview?.summary.total_workflows ?? 0}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">My Open Todos</p>
          <p className="text-2xl font-bold text-amber-700">{overview?.summary.open_todos ?? 0}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Initiated By Me</p>
          <p className="text-2xl font-bold text-cyan-700">{overview?.summary.initiated_count ?? 0}</p>
        </div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3">
          <p className="text-xs text-slate-500">Pending Approval</p>
          <p className="text-2xl font-bold text-rose-700">{overview?.summary.status_counts.PENDING_APPROVAL ?? 0}</p>
        </div>
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="glass rounded-3xl border border-slate-200/60 p-4">
          <div className="flex items-center gap-2 mb-3">
            <Workflow size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">Create Workflow</h3>
          </div>
          <form onSubmit={onCreateWorkflow} className="space-y-2">
            <input
              value={createForm.title}
              onChange={(e) => setCreateForm((prev) => ({ ...prev, title: e.target.value }))}
              placeholder="Title"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              required
            />
            <div className="grid grid-cols-2 gap-2">
              <input
                value={createForm.workflow_type}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, workflow_type: e.target.value }))}
                placeholder="Workflow Type"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                required
              />
              <input
                value={createForm.source_type}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, source_type: e.target.value }))}
                placeholder="Source Type"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                required
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <input
                value={createForm.source_id}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, source_id: e.target.value }))}
                placeholder="Source ID"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                required
              />
              <select
                value={createForm.priority}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, priority: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              >
                <option value="LOW">LOW</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="HIGH">HIGH</option>
                <option value="CRITICAL">CRITICAL</option>
              </select>
            </div>
            <input
              value={createForm.assignee_role}
              onChange={(e) => setCreateForm((prev) => ({ ...prev, assignee_role: e.target.value }))}
              placeholder="Assignee Role (e.g. APPROVER)"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <textarea
              rows={3}
              value={createForm.description}
              onChange={(e) => setCreateForm((prev) => ({ ...prev, description: e.target.value }))}
              placeholder="Description / context"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <button
              type="submit"
              disabled={operating}
              className="w-full rounded-lg bg-cyan-600 text-white py-2 text-sm font-semibold disabled:opacity-50"
            >
              Create
            </button>
          </form>
        </div>

        <div className="glass rounded-3xl border border-slate-200/60 p-4 xl:col-span-2">
          <div className="flex items-center gap-2 mb-3">
            <Users2 size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">My Todos & Initiated Flows</h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="rounded-xl border border-slate-200 bg-white p-3 max-h-48 overflow-auto">
              <p className="text-xs font-semibold text-slate-700 mb-2">My Todos</p>
              {(overview?.my_todos ?? []).map((todo) => (
                <button
                  key={todo.id}
                  onClick={() => setSelectedWorkflowId(todo.workflow_id)}
                  className="block w-full text-left border-b border-slate-100 pb-2 mb-2"
                >
                  <p className="text-sm font-medium text-slate-800">{todo.title}</p>
                  <p className="text-xs text-slate-500">wf#{todo.workflow_id} | {todo.priority}</p>
                </button>
              ))}
              {(overview?.my_todos.length ?? 0) === 0 && <p className="text-sm text-slate-500">No open todo.</p>}
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-3 max-h-48 overflow-auto">
              <p className="text-xs font-semibold text-slate-700 mb-2">Initiated By Me</p>
              {(overview?.initiated_workflows ?? []).map((wf) => (
                <button
                  key={wf.id}
                  onClick={() => setSelectedWorkflowId(wf.id)}
                  className="block w-full text-left border-b border-slate-100 pb-2 mb-2"
                >
                  <p className="text-sm font-medium text-slate-800">{wf.title}</p>
                  <p className="text-xs text-slate-500">{wf.status}</p>
                </button>
              ))}
              {(overview?.initiated_workflows.length ?? 0) === 0 && (
                <p className="text-sm text-slate-500">No initiated workflows.</p>
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="glass rounded-3xl border border-slate-200/60 p-4">
          <form onSubmit={onApplyFilters} className="grid grid-cols-1 md:grid-cols-4 gap-2 mb-3">
            <input
              value={filters.q}
              onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))}
              placeholder="search title/source"
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm md:col-span-2"
            />
            <select
              value={filters.status}
              onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))}
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
              <option value="ALL">All Status</option>
              {availableStatuses.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
            <button type="submit" className="rounded-lg bg-slate-900 text-white px-3 py-2 text-sm font-semibold">
              Filter
            </button>
          </form>

          <div className="mb-3 flex flex-wrap gap-2 text-xs">
            <label className="inline-flex items-center gap-1 text-slate-600">
              <input
                type="checkbox"
                checked={filters.initiated_by_me}
                onChange={(e) => setFilters((prev) => ({ ...prev, initiated_by_me: e.target.checked }))}
              />
              Initiated by me
            </label>
            <label className="inline-flex items-center gap-1 text-slate-600">
              <input
                type="checkbox"
                checked={filters.my_todos_only}
                onChange={(e) => setFilters((prev) => ({ ...prev, my_todos_only: e.target.checked }))}
              />
              My todos only
            </label>
          </div>

          <div className="space-y-2 max-h-[620px] overflow-auto">
            {loadingList && <p className="text-sm text-slate-500">Loading workflows...</p>}
            {(workflows?.items ?? []).map((item) => (
              <button
                key={item.id}
                onClick={() => setSelectedWorkflowId(item.id)}
                className={clsx(
                  'w-full text-left rounded-xl border p-3 transition',
                  selectedWorkflowId === item.id ? 'border-cyan-500 bg-cyan-50' : 'border-slate-200 bg-white hover:border-slate-300',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold text-slate-800 text-sm">{item.title}</p>
                  <span className={clsx('px-2 py-0.5 rounded-full text-xs font-semibold', statusClass[item.status] ?? 'bg-slate-100 text-slate-700')}>
                    {item.status}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  {item.workflow_type} | {item.source_type}:{item.source_id}
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  open tasks {item.open_task_count} | my todo {item.is_my_todo ? 'yes' : 'no'}
                </p>
              </button>
            ))}
            {(workflows?.items.length ?? 0) === 0 && !loadingList && (
              <p className="text-sm text-slate-500">No workflows under current filters.</p>
            )}
          </div>
        </div>

        <div className="glass rounded-3xl border border-slate-200/60 p-4">
          {!detail && <p className="text-sm text-slate-500">Select one workflow to inspect details.</p>}
          {loadingDetail && <p className="text-sm text-slate-500">Loading detail...</p>}
          {detail && (
            <div className="space-y-3">
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-slate-800">{detail.workflow.title}</p>
                  <span className={clsx('px-2 py-0.5 rounded-full text-xs font-semibold', statusClass[detail.workflow.status] ?? 'bg-slate-100 text-slate-700')}>
                    {detail.workflow.status}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  initiated by {detail.workflow.initiator} | {detail.workflow.workflow_type}
                </p>
                <p className="text-xs text-slate-600 mt-1">{detail.workflow.description ?? '-'}</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    onClick={() => navigate(detail.linked_object.route)}
                    className="rounded-lg border border-slate-300 px-3 py-1 text-xs text-slate-700"
                  >
                    Open linked object ({detail.linked_object.source_type}:{detail.linked_object.source_id})
                  </button>
                  <button
                    onClick={openKnowledgeForLinkedObject}
                    className="rounded-lg bg-emerald-600 text-white px-3 py-1 text-xs"
                  >
                    Related Docs
                  </button>
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold text-slate-700 mb-2">Context</p>
                <pre className="text-xs bg-slate-50 p-2 rounded-lg overflow-auto text-slate-700">
{JSON.stringify(detail.workflow.context_payload, null, 2)}
                </pre>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold text-slate-700 mb-2">Tasks</p>
                <div className="space-y-2 max-h-40 overflow-auto">
                  {detail.tasks.map((task) => (
                    <div key={task.id} className="border-b border-slate-100 pb-1">
                      <p className="text-sm text-slate-800">{task.title}</p>
                      <p className="text-xs text-slate-500">{task.status} | {task.action_type} | {task.priority}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold text-slate-700 mb-2">Comments</p>
                <div className="space-y-2 max-h-36 overflow-auto">
                  {detail.comments.map((comment) => (
                    <div key={comment.id} className="border-b border-slate-100 pb-1">
                      <p className="text-xs text-slate-600">{comment.author} | {new Date(comment.created_at).toLocaleString()}</p>
                      <p className="text-sm text-slate-800">{comment.content}</p>
                    </div>
                  ))}
                  {detail.comments.length === 0 && <p className="text-sm text-slate-500">No comments.</p>}
                </div>
                <div className="mt-2 flex gap-2">
                  <input
                    value={commentText}
                    onChange={(e) => setCommentText(e.target.value)}
                    placeholder="Add comment and mention with @user"
                    className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  />
                  <button
                    onClick={() => void onAddComment()}
                    disabled={operating || !commentText.trim()}
                    className="rounded-lg bg-cyan-600 text-white px-3 py-2 text-sm disabled:opacity-50"
                  >
                    <Send size={14} />
                  </button>
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex items-center gap-2 mb-2">
                  <MessageSquare size={14} className="text-slate-500" />
                  <p className="text-xs font-semibold text-slate-700">Workflow Actions</p>
                </div>
                <textarea
                  rows={2}
                  value={actionNote}
                  onChange={(e) => setActionNote(e.target.value)}
                  placeholder="action note (optional)"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                />
                <div className="mt-2 flex flex-wrap gap-2">
                  <button onClick={() => void operateWorkflow('START')} className="rounded-lg bg-cyan-600 text-white px-3 py-1.5 text-sm">Start</button>
                  <button onClick={() => void operateWorkflow('APPROVE')} className="rounded-lg bg-emerald-600 text-white px-3 py-1.5 text-sm">Approve</button>
                  <button onClick={() => void operateWorkflow('REQUEST_REVISION')} className="rounded-lg bg-amber-500 text-white px-3 py-1.5 text-sm">Request Revision</button>
                  <button onClick={() => void operateWorkflow('REJECT')} className="rounded-lg bg-rose-600 text-white px-3 py-1.5 text-sm">Reject</button>
                  <button onClick={() => void operateWorkflow('COMPLETE')} className="rounded-lg bg-slate-700 text-white px-3 py-1.5 text-sm">Complete</button>
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold text-slate-700 mb-2">Action History</p>
                <div className="space-y-2 max-h-44 overflow-auto">
                  {detail.action_history.map((item) => (
                    <div key={item.id} className="border-b border-slate-100 pb-1">
                      <p className="text-sm text-slate-800">{item.action} by {item.actor}</p>
                      <p className="text-xs text-slate-500">{new Date(item.created_at).toLocaleString()}</p>
                      {item.note && <p className="text-xs text-slate-600">{item.note}</p>}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

export default CollaborationWorkflowPage
