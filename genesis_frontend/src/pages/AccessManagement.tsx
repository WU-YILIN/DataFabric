import { FormEvent, useEffect, useMemo, useState } from 'react'
import { clsx } from 'clsx'
import { KeyRound, RefreshCw, ShieldCheck, UserPlus, Users2 } from 'lucide-react'

import { useSession } from '../auth/session'
import {
  GenesisApi,
  type AccessOverviewResponse,
  type AccessRoleTemplateItem,
  type AccessUserDetailResponse,
  type AccessUserItem,
  type AccessUserListResponse,
} from '../services/api'
import { useBrowserErrorAlert } from '../hooks/useBrowserErrorAlert'
import { useLanguage } from '../i18n/language'

const AccessManagementPage = () => {
  const { locale } = useLanguage()
  void locale
  const isZh = false
  const L = (cn: string, en: string) => (isZh ? cn : en)
  const { activeProjectId } = useSession()
  const [overview, setOverview] = useState<AccessOverviewResponse | null>(null)
  const [users, setUsers] = useState<AccessUserListResponse | null>(null)
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null)
  const [detail, setDetail] = useState<AccessUserDetailResponse | null>(null)
  const [templates, setTemplates] = useState<AccessRoleTemplateItem[]>([])
  const [selectedTemplateKey, setSelectedTemplateKey] = useState<string>('')

  const [loading, setLoading] = useState(false)
  const [operating, setOperating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useBrowserErrorAlert(error)
  const [message, setMessage] = useState<string | null>(null)

  const [filters, setFilters] = useState({
    q: '',
    role: 'ALL',
    status: 'ALL',
  })

  const [inviteForm, setInviteForm] = useState({
    email: '',
    tenant_role: 'MEMBER',
    project_role: 'VIEWER',
    expires_in_hours: 168,
  })

  const [roleForm, setRoleForm] = useState({
    tenant_role_action: 'UPSERT',
    tenant_role: 'MEMBER',
    project_role_action: 'UPSERT',
    project_role: 'VIEWER',
  })

  const [templateForm, setTemplateForm] = useState({
    name: '',
    description: '',
    is_active: true,
    matrixJson: '{\n  "modules": {\n    "OVERVIEW": ["VIEW"]\n  }\n}',
  })

  const [evaluateForm, setEvaluateForm] = useState({
    module: 'GOVERNANCE',
    action: 'APPROVE',
  })
  const [evaluateResult, setEvaluateResult] = useState<{
    allow: boolean
    reason: string
    effective_role?: string | null
  } | null>(null)

  const roleOptions = useMemo(
    () => ['ALL', 'OWNER', 'ADMIN', 'APPROVER', 'EDITOR', 'VIEWER', 'MEMBER'],
    [],
  )

  const selectedUser: AccessUserItem | null = detail?.user ?? null
  const selectedTemplate = useMemo(
    () => templates.find((item) => item.template_key === selectedTemplateKey) ?? null,
    [templates, selectedTemplateKey],
  )

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
    const data = await GenesisApi.getAccessOverview()
    setOverview(data)
  }

  const loadUsers = async () => {
    const data = await GenesisApi.getAccessUsers({
      q: filters.q.trim() || undefined,
      role: filters.role === 'ALL' ? undefined : filters.role,
      status: filters.status === 'ALL' ? undefined : filters.status,
      limit: 200,
      offset: 0,
    })
    setUsers(data)
    if (!selectedUserId && data.items.length > 0) {
      setSelectedUserId(data.items[0].user_id)
    }
    if (selectedUserId && !data.items.find((item) => item.user_id === selectedUserId)) {
      setSelectedUserId(data.items[0]?.user_id ?? null)
    }
  }

  const loadDetail = async (userId: number) => {
    const data = await GenesisApi.getAccessUserDetail(userId)
    setDetail(data)
    const tenantRole = data.user.tenant_roles[0]?.role ?? 'MEMBER'
    const projectRole = data.user.project_roles.find((item) => item.project_id === activeProjectId)?.role ?? data.user.project_roles[0]?.role ?? 'VIEWER'
    setRoleForm({
      tenant_role_action: 'UPSERT',
      tenant_role: tenantRole,
      project_role_action: 'UPSERT',
      project_role: projectRole,
    })
  }

  const loadTemplates = async () => {
    const data = await GenesisApi.getAccessRoleTemplates()
    setTemplates(data.items)
    if (!selectedTemplateKey && data.items.length > 0) {
      setSelectedTemplateKey(data.items[0].template_key)
    }
    if (selectedTemplateKey && !data.items.find((item) => item.template_key === selectedTemplateKey)) {
      setSelectedTemplateKey(data.items[0]?.template_key ?? '')
    }
  }

  const refreshAll = async () => {
    setLoading(true)
    setError(null)
    try {
      await Promise.all([loadOverview(), loadUsers(), loadTemplates()])
      if (selectedUserId != null) {
        await loadDetail(selectedUserId)
      }
    } catch (e: any) {
      setError(e?.response?.data?.message ?? L('????????', 'Failed to load access management'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refreshAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (selectedUserId != null) {
      void loadDetail(selectedUserId).catch(() => setDetail(null))
    } else {
      setDetail(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedUserId, activeProjectId])

  useEffect(() => {
    if (!selectedTemplate) return
    setTemplateForm({
      name: selectedTemplate.name,
      description: selectedTemplate.description ?? '',
      is_active: selectedTemplate.is_active,
      matrixJson: JSON.stringify(selectedTemplate.permission_matrix, null, 2),
    })
  }, [selectedTemplate])

  const onApplyFilters = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await loadUsers()
    } catch (e: any) {
      setError(e?.response?.data?.message ?? L('??????', 'Failed to load users'))
    } finally {
      setLoading(false)
    }
  }

  const onInvite = async (event: FormEvent) => {
    event.preventDefault()
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const result = await GenesisApi.inviteAccessUser({
        email: inviteForm.email.trim(),
        tenant_role: inviteForm.tenant_role,
        project_role: inviteForm.project_role,
        expires_in_hours: inviteForm.expires_in_hours,
      })
      setMessage(`${L('?????', 'Invite processed')}: ${result.mode}`)
      setInviteForm((prev) => ({ ...prev, email: '' }))
      await Promise.all([loadOverview(), loadUsers()])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? L('????', 'Invite failed'))
    } finally {
      setOperating(false)
    }
  }

  const onUpdateRoles = async () => {
    if (!selectedUser || !activeProjectId) return
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      await GenesisApi.updateAccessUserRoles(selectedUser.user_id, {
        tenant_role_action: roleForm.tenant_role_action,
        tenant_role: roleForm.tenant_role,
        project_roles: [
          {
            project_id: activeProjectId,
            action: roleForm.project_role_action,
            role: roleForm.project_role_action === 'UPSERT' ? roleForm.project_role : undefined,
          },
        ],
      })
      setMessage(L('???????', 'User roles updated'))
      await Promise.all([loadOverview(), loadUsers(), loadDetail(selectedUser.user_id)])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? L('??????', 'Role update failed'))
    } finally {
      setOperating(false)
    }
  }

  const onToggleStatus = async () => {
    if (!selectedUser) return
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      await GenesisApi.updateAccessUserStatus(selectedUser.user_id, {
        is_active: selectedUser.status !== 'ACTIVE',
      })
      setMessage(L('???????', 'User status updated'))
      await Promise.all([loadOverview(), loadUsers(), loadDetail(selectedUser.user_id)])
    } catch (e: any) {
      setError(e?.response?.data?.message ?? L('??????', 'Status update failed'))
    } finally {
      setOperating(false)
    }
  }

  const onSaveTemplate = async () => {
    if (!selectedTemplateKey) return
    const matrix = parseJsonObject(templateForm.matrixJson)
    if (!matrix) {
      setError(L('???? JSON ?????', 'Permission matrix JSON must be object'))
      return
    }
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      const updated = await GenesisApi.saveAccessRoleTemplate(selectedTemplateKey, {
        name: templateForm.name.trim(),
        description: templateForm.description.trim() || undefined,
        permission_matrix: matrix as { modules: Record<string, string[]> },
        is_active: templateForm.is_active,
      })
      setMessage(`${L('?????', 'Template saved')}: ${updated.template_key}`)
      await loadTemplates()
    } catch (e: any) {
      setError(e?.response?.data?.message ?? L('??????', 'Template save failed'))
    } finally {
      setOperating(false)
    }
  }

  const onDeleteTemplate = async () => {
    if (!selectedTemplate || selectedTemplate.is_system) return
    setOperating(true)
    setError(null)
    setMessage(null)
    try {
      await GenesisApi.deleteAccessRoleTemplate(selectedTemplate.template_key)
      setMessage(`${L('?????', 'Template deleted')}: ${selectedTemplate.template_key}`)
      await loadTemplates()
    } catch (e: any) {
      setError(e?.response?.data?.message ?? L('??????', 'Template delete failed'))
    } finally {
      setOperating(false)
    }
  }

  const onEvaluate = async () => {
    if (!selectedUser || !activeProjectId) return
    setOperating(true)
    setError(null)
    try {
      const result = await GenesisApi.evaluateAccessDecision({
        user_id: selectedUser.user_id,
        module: evaluateForm.module,
        action: evaluateForm.action,
        project_id: activeProjectId,
      })
      setEvaluateResult(result)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? L('??????', 'Evaluate failed'))
    } finally {
      setOperating(false)
    }
  }

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">{L('???????', 'User & Access Management')}</h2>
          <p className="text-slate-500 text-base">{L('???????????????????????', 'Manage users, role bindings, and permission templates in current tenant scope.')}</p>
        </div>
        <button
          onClick={() => void refreshAll()}
          disabled={loading || operating}
          className="rounded-xl bg-slate-900 text-white px-4 py-2.5 font-medium hover:bg-slate-800 disabled:opacity-60 flex items-center gap-2"
        >
          <RefreshCw size={16} />
          {L('??', 'Refresh')}
        </button>
      </header>
      {message && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>}

      <section className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">{L('???', 'Users')}</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.total_users ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">{L('???', 'Active')}</p><p className="text-2xl font-bold text-emerald-700">{overview?.summary.active_users ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">{L('???', 'Inactive')}</p><p className="text-2xl font-bold text-slate-700">{overview?.summary.inactive_users ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">{L('?????', 'Pending Invites')}</p><p className="text-2xl font-bold text-amber-700">{overview?.summary.pending_invitations ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">{L('?????', 'Admin Users')}</p><p className="text-2xl font-bold text-cyan-700">{overview?.summary.admin_users ?? 0}</p></div>
        <div className="glass rounded-2xl border border-slate-200/60 p-3"><p className="text-xs text-slate-500">{L('????', 'Role Templates')}</p><p className="text-2xl font-bold text-slate-900">{overview?.summary.role_templates ?? 0}</p></div>
      </section>

      <form onSubmit={onApplyFilters} className="glass rounded-3xl border border-slate-200/60 p-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <input
            value={filters.q}
            onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))}
            placeholder={L('???????????', 'search by email/name/role')}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
          />
          <select value={filters.role} onChange={(e) => setFilters((prev) => ({ ...prev, role: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
            {roleOptions.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <select value={filters.status} onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
            <option value="ALL">{L('????', 'ALL STATUS')}</option>
            <option value="ACTIVE">ACTIVE</option>
            <option value="INACTIVE">INACTIVE</option>
          </select>
          <button type="submit" className="rounded-xl bg-cyan-600 text-white px-4 py-2 text-sm font-semibold">{L('????', 'Apply Filters')}</button>
        </div>
      </form>

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="space-y-4">
          <div className="glass rounded-3xl border border-slate-200/60 p-4">
            <h3 className="text-sm font-semibold text-slate-800 mb-3 flex items-center gap-2"><Users2 size={16} /> {L('???', 'Users')}</h3>
            <div className="space-y-2 max-h-[30rem] overflow-auto">
              {(users?.items ?? []).map((item) => (
                <button
                  key={item.user_id}
                  onClick={() => setSelectedUserId(item.user_id)}
                  className={clsx(
                    'w-full text-left rounded-xl border px-3 py-2 transition',
                    selectedUserId === item.user_id ? 'border-cyan-300 bg-cyan-50/70' : 'border-slate-200 bg-white hover:bg-slate-50',
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-semibold text-slate-800 text-sm">{item.name}</p>
                    <span className={clsx('px-2 py-0.5 rounded-full text-xs font-semibold', item.status === 'ACTIVE' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600')}>
                      {item.status}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">{item.email}</p>
                  <p className="text-xs text-slate-500">{L('????', 'highest')} {item.highest_role ?? '-'}</p>
                </button>
              ))}
            </div>
          </div>

          <form onSubmit={onInvite} className="glass rounded-3xl border border-slate-200/60 p-4 space-y-2">
            <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2"><UserPlus size={16} /> {L('????', 'Invite User')}</h3>
            <input value={inviteForm.email} onChange={(e) => setInviteForm((prev) => ({ ...prev, email: e.target.value }))} placeholder="user@example.com" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <div className="grid grid-cols-2 gap-2">
              <select value={inviteForm.tenant_role} onChange={(e) => setInviteForm((prev) => ({ ...prev, tenant_role: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
                <option value="MEMBER">MEMBER</option>
                <option value="ADMIN">ADMIN</option>
              </select>
              <select value={inviteForm.project_role} onChange={(e) => setInviteForm((prev) => ({ ...prev, project_role: e.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
                <option value="VIEWER">VIEWER</option>
                <option value="EDITOR">EDITOR</option>
                <option value="APPROVER">APPROVER</option>
                <option value="ADMIN">ADMIN</option>
              </select>
            </div>
            <input type="number" min={1} value={inviteForm.expires_in_hours} onChange={(e) => setInviteForm((prev) => ({ ...prev, expires_in_hours: Number(e.target.value || 1) }))} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" />
            <button type="submit" disabled={operating} className="w-full rounded-xl bg-cyan-600 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60">{L('????', 'Send Invite')}</button>
          </form>
        </div>

        <div className="xl:col-span-2 space-y-4">
          {!selectedUser ? (
            <div className="glass rounded-3xl border border-slate-200/60 p-8 text-sm text-slate-500">{L('???????????', 'Select one user to view details.')}</div>
          ) : (
            <>
              <div className="glass rounded-3xl border border-slate-200/60 p-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="text-lg font-semibold text-slate-900">{selectedUser.name}</h3>
                    <p className="text-sm text-slate-500">{selectedUser.email} | {selectedUser.auth_provider}</p>
                  </div>
                  <button onClick={() => void onToggleStatus()} disabled={operating} className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60">
                    {L('??', 'Set')} {selectedUser.status === 'ACTIVE' ? L('???', 'Inactive') : L('???', 'Active')}
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="rounded-2xl border border-slate-200 bg-white p-3">
                    <p className="text-xs text-slate-500 mb-1">{L('????', 'Tenant Roles')}</p>
                    <div className="space-y-1">
                      {selectedUser.tenant_roles.map((item) => (
                        <div key={`${item.tenant_id}-${item.role}`} className="text-xs text-slate-700">{item.tenant_id} | {item.role}</div>
                      ))}
                      {selectedUser.tenant_roles.length === 0 && <p className="text-xs text-slate-500">{L('??????', 'No tenant role')}</p>}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-white p-3">
                    <p className="text-xs text-slate-500 mb-1">{L('????', 'Project Roles')}</p>
                    <div className="space-y-1">
                      {selectedUser.project_roles.map((item) => (
                        <div key={`${item.project_id}-${item.role}`} className="text-xs text-slate-700">{item.project_name} ({item.project_id}) | {item.role}</div>
                      ))}
                      {selectedUser.project_roles.length === 0 && <p className="text-xs text-slate-500">{L('??????', 'No project role')}</p>}
                    </div>
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-3 space-y-2">
                  <p className="text-xs text-slate-500">{L('????????????', 'Role Binding Update (current project)')}</p>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    <select value={roleForm.tenant_role_action} onChange={(e) => setRoleForm((prev) => ({ ...prev, tenant_role_action: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm">
                      <option value="UPSERT">{L('??????', 'Tenant UPSERT')}</option>
                      <option value="REMOVE">{L('??????', 'Tenant REMOVE')}</option>
                    </select>
                    <select value={roleForm.tenant_role} onChange={(e) => setRoleForm((prev) => ({ ...prev, tenant_role: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm">
                      <option value="MEMBER">MEMBER</option>
                      <option value="ADMIN">ADMIN</option>
                      <option value="OWNER">OWNER</option>
                    </select>
                    <select value={roleForm.project_role_action} onChange={(e) => setRoleForm((prev) => ({ ...prev, project_role_action: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm">
                      <option value="UPSERT">{L('??????', 'Project UPSERT')}</option>
                      <option value="REMOVE">{L('??????', 'Project REMOVE')}</option>
                    </select>
                    <select value={roleForm.project_role} onChange={(e) => setRoleForm((prev) => ({ ...prev, project_role: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm">
                      <option value="VIEWER">VIEWER</option>
                      <option value="EDITOR">EDITOR</option>
                      <option value="APPROVER">APPROVER</option>
                      <option value="ADMIN">ADMIN</option>
                      <option value="OWNER">OWNER</option>
                    </select>
                  </div>
                  <button onClick={() => void onUpdateRoles()} disabled={operating} className="rounded-xl bg-cyan-600 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60">{L('????', 'Update Roles')}</button>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-3">
                  <p className="text-xs text-slate-500 mb-2">{L('??????', 'Recent Security Actions')}</p>
                  <div className="space-y-2 max-h-48 overflow-auto">
                    {detail?.audit_summary.recent_actions.map((item) => (
                      <div key={item.id} className="rounded-lg border border-slate-200 p-2 text-xs text-slate-700">
                        <p className="font-semibold">{item.action}</p>
                        <p>{item.summary || `${item.entity_type}:${item.entity_id}`}</p>
                      </div>
                    ))}
                    {!detail?.audit_summary.recent_actions.length && <p className="text-xs text-slate-500">{L('??????', 'No action records')}</p>}
                  </div>
                </div>
              </div>

              <div className="glass rounded-3xl border border-slate-200/60 p-4 space-y-3">
                <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2"><ShieldCheck size={16} /> {L('????', 'Access Evaluate')}</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                  <input value={evaluateForm.module} onChange={(e) => setEvaluateForm((prev) => ({ ...prev, module: e.target.value.toUpperCase() }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                  <input value={evaluateForm.action} onChange={(e) => setEvaluateForm((prev) => ({ ...prev, action: e.target.value.toUpperCase() }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                  <button onClick={() => void onEvaluate()} disabled={operating} className="rounded-xl bg-slate-900 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60">{L('??', 'Evaluate')}</button>
                </div>
                {evaluateResult && (
                  <div className={clsx('rounded-xl border px-3 py-2 text-sm', evaluateResult.allow ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-rose-200 bg-rose-50 text-rose-700')}>
                    {evaluateResult.allow ? L('??', 'ALLOW') : L('??', 'DENY')} | {evaluateResult.effective_role ?? '-'} | {evaluateResult.reason}
                  </div>
                )}
              </div>
            </>
          )}

          <div className="glass rounded-3xl border border-slate-200/60 p-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2"><KeyRound size={16} /> {L('????', 'Role Templates')}</h3>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
              <div className="space-y-2 max-h-72 overflow-auto">
                {templates.map((item) => (
                  <button
                    key={item.template_key}
                    onClick={() => setSelectedTemplateKey(item.template_key)}
                    className={clsx(
                      'w-full text-left rounded-xl border px-3 py-2 text-sm',
                      selectedTemplateKey === item.template_key ? 'border-cyan-300 bg-cyan-50/70' : 'border-slate-200 bg-white',
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold">{item.template_key}</span>
                      <span className="text-xs text-slate-500">{item.source}</span>
                    </div>
                    <p className="text-xs text-slate-500">{item.name}</p>
                  </button>
                ))}
              </div>

              <div className="lg:col-span-2 rounded-2xl border border-slate-200 bg-white p-3 space-y-2">
                <input value={templateForm.name} onChange={(e) => setTemplateForm((prev) => ({ ...prev, name: e.target.value }))} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder={L('????', 'template name')} />
                <input value={templateForm.description} onChange={(e) => setTemplateForm((prev) => ({ ...prev, description: e.target.value }))} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder={L('??', 'description')} />
                <label className="text-xs text-slate-500 inline-flex items-center gap-2">
                  <input type="checkbox" checked={templateForm.is_active} onChange={(e) => setTemplateForm((prev) => ({ ...prev, is_active: e.target.checked }))} />
                  {L('???', 'Active')}
                </label>
                <textarea value={templateForm.matrixJson} onChange={(e) => setTemplateForm((prev) => ({ ...prev, matrixJson: e.target.value }))} rows={9} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-mono" />
                <div className="flex gap-2">
                  <button onClick={() => void onSaveTemplate()} disabled={operating || !selectedTemplateKey} className="rounded-xl bg-cyan-600 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60">{L('????', 'Save Template')}</button>
                  <button onClick={() => void onDeleteTemplate()} disabled={operating || !selectedTemplate || selectedTemplate.is_system} className="rounded-xl bg-rose-600 text-white px-3 py-2 text-sm font-semibold disabled:opacity-60">{L('???????', 'Delete Custom')}</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}

export default AccessManagementPage
