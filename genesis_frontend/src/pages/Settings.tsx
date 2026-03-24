import { FormEvent, useEffect, useMemo, useState } from 'react'
import { clsx } from 'clsx'

import { useSession } from '../auth/session'
import { useLanguage } from '../i18n/language'
import {
  GenesisApi,
  type SettingsMember,
  type SettingsPendingInvitation,
  type SettingsSecurity,
} from '../services/api'
import { useBrowserErrorAlert } from '../hooks/useBrowserErrorAlert'
import { getAssistantRuntimeConfig, saveAssistantRuntimeConfig } from '../utils/assistantConfig'

type SettingsTab = 'general' | 'members' | 'integrations' | 'security'

interface IntegrationDraft {
  enabled: boolean
  configText: string
  lastTestMessage?: string
  lastTestStatus?: string
}

const ROLE_OPTIONS = ['VIEWER', 'EDITOR', 'APPROVER', 'ADMIN']

export default function SettingsPage() {
  const { user, updateProfile } = useSession()
  const { locale, setLocale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const L = (cn: string, en: string) => (isZh ? cn : en)

  const [activeTab, setActiveTab] = useState<SettingsTab>('general')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  useBrowserErrorAlert(error)

  const [permissions, setPermissions] = useState({
    can_manage_general: false,
    can_manage_members: false,
    can_manage_integrations: false,
    can_manage_security: false,
  })
  const [general, setGeneral] = useState({
    project_id: 0,
    tenant_id: 0,
    name: '',
    description: '',
    default_domain: '',
    tagsText: '',
    updated_at: '',
  })
  const [displayName, setDisplayName] = useState('')
  const [assistantRuntime, setAssistantRuntime] = useState(() => getAssistantRuntimeConfig())
  const [members, setMembers] = useState<SettingsMember[]>([])
  const [pendingInvitations, setPendingInvitations] = useState<SettingsPendingInvitation[]>([])
  const [inviteForm, setInviteForm] = useState({ email: '', name: '', role: 'VIEWER' })
  const [integrationDrafts, setIntegrationDrafts] = useState<Record<string, IntegrationDraft>>({})
  const [security, setSecurity] = useState<SettingsSecurity | null>(null)

  const tabs = useMemo(
    () => [
      { key: 'general' as const, label: L('通用设置', 'General') },
      { key: 'members' as const, label: L('成员管理', 'Members') },
      { key: 'integrations' as const, label: L('集成配置', 'Integrations') },
      { key: 'security' as const, label: L('安全设置', 'Security') },
    ],
    [isZh],
  )

  useEffect(() => {
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await GenesisApi.getSettingsOverview()
        setPermissions(data.permissions)
        setGeneral({
          project_id: data.general.project_id,
          tenant_id: data.general.tenant_id,
          name: data.general.name,
          description: data.general.description ?? '',
          default_domain: data.general.default_domain ?? '',
          tagsText: (data.general.tags ?? []).join(', '),
          updated_at: data.general.updated_at,
        })
        setDisplayName(user?.name ?? '')
        setMembers(data.members.items ?? [])
        setPendingInvitations(data.members.pending_invitations ?? [])
        setSecurity(data.security)
        const drafts: Record<string, IntegrationDraft> = {}
        for (const item of data.integrations) {
          drafts[item.integration_type] = {
            enabled: item.enabled,
            configText: JSON.stringify(item.config ?? {}, null, 2),
            lastTestMessage: item.last_test?.message,
            lastTestStatus: item.last_test?.status,
          }
        }
        setIntegrationDrafts(drafts)
      } catch (err: any) {
        setError(err?.response?.data?.message ?? err?.message ?? 'Failed to load settings')
      } finally {
        setLoading(false)
      }
    })()
  }, [user?.name])

  const withBanner = (value: string) => {
    setMessage(value)
    setError(null)
  }

  const reloadMembers = async () => {
    const data = await GenesisApi.getSettingsMembers()
    setMembers(data.items ?? [])
    setPendingInvitations(data.pending_invitations ?? [])
  }

  const parseIntegrationConfig = (integrationType: string): Record<string, unknown> | null => {
    const draft = integrationDrafts[integrationType]
    if (!draft) return {}
    try {
      const value = JSON.parse(draft.configText || '{}')
      if (value && typeof value === 'object' && !Array.isArray(value)) return value as Record<string, unknown>
      setError(`${integrationType} config must be a JSON object`)
      return null
    } catch {
      setError(`${integrationType} config is invalid JSON`)
      return null
    }
  }

  const onSaveProfile = async (event: FormEvent) => {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await updateProfile({ name: displayName.trim() })
      withBanner(L('个人名称已更新', 'Display name updated'))
    } catch (err: any) {
      setError(err?.response?.data?.message ?? err?.message ?? 'Failed to update display name')
    } finally {
      setSaving(false)
    }
  }

  const onSaveAssistantRuntime = (event: FormEvent) => {
    event.preventDefault()
    saveAssistantRuntimeConfig(assistantRuntime)
    withBanner(L('助手模型配置已保存', 'Assistant runtime saved'))
  }

  const onSaveGeneral = async (event: FormEvent) => {
    event.preventDefault()
    if (!permissions.can_manage_general) return
    setSaving(true)
    setError(null)
    try {
      const payload = {
        name: general.name.trim(),
        description: general.description.trim() || null,
        default_domain: general.default_domain.trim() || null,
        tags: general.tagsText.split(',').map((item) => item.trim()).filter(Boolean),
      }
      const updated = await GenesisApi.updateSettingsGeneral(payload)
      setGeneral((prev) => ({
        ...prev,
        name: updated.name,
        description: updated.description ?? '',
        default_domain: updated.default_domain ?? '',
        tagsText: (updated.tags ?? []).join(', '),
        updated_at: updated.updated_at,
      }))
      withBanner(L('项目通用设置已更新', 'Project general settings updated'))
    } catch (err: any) {
      setError(err?.response?.data?.message ?? err?.message ?? 'Failed to update general settings')
    } finally {
      setSaving(false)
    }
  }

  const onInviteMember = async (event: FormEvent) => {
    event.preventDefault()
    if (!permissions.can_manage_members) return
    setSaving(true)
    setError(null)
    try {
      await GenesisApi.inviteSettingsMember({
        email: inviteForm.email.trim(),
        name: inviteForm.name.trim() || undefined,
        role: inviteForm.role,
      })
      await reloadMembers()
      setInviteForm({ email: '', name: '', role: 'VIEWER' })
      withBanner(L('成员邀请已发送', 'Member invitation processed'))
    } catch (err: any) {
      setError(err?.response?.data?.message ?? err?.message ?? 'Failed to invite member')
    } finally {
      setSaving(false)
    }
  }

  const onUpdateMemberRole = async (member: SettingsMember, role: string) => {
    if (!permissions.can_manage_members || role === member.project_role) return
    setSaving(true)
    setError(null)
    try {
      await GenesisApi.updateSettingsMemberRole(member.user_id, { role })
      await reloadMembers()
      withBanner(L('成员角色已更新', 'Member role updated'))
    } catch (err: any) {
      setError(err?.response?.data?.message ?? err?.message ?? 'Failed to update role')
    } finally {
      setSaving(false)
    }
  }

  const onRemoveMember = async (member: SettingsMember) => {
    if (!permissions.can_manage_members) return
    setSaving(true)
    setError(null)
    try {
      await GenesisApi.removeSettingsMember(member.user_id)
      await reloadMembers()
      withBanner(L('成员已移除', 'Member removed'))
    } catch (err: any) {
      setError(err?.response?.data?.message ?? err?.message ?? 'Failed to remove member')
    } finally {
      setSaving(false)
    }
  }

  const onTestIntegration = async (integrationType: string) => {
    const config = parseIntegrationConfig(integrationType)
    if (!config || !permissions.can_manage_integrations) return
    setSaving(true)
    try {
      const result = await GenesisApi.testSettingsIntegration({ integration_type: integrationType, config })
      setIntegrationDrafts((prev) => ({
        ...prev,
        [integrationType]: {
          ...prev[integrationType],
          lastTestStatus: result.status,
          lastTestMessage: result.message,
        },
      }))
      withBanner(`${integrationType} ${result.status}`)
    } catch (err: any) {
      setError(err?.response?.data?.message ?? err?.message ?? `Failed to test ${integrationType}`)
    } finally {
      setSaving(false)
    }
  }

  const onSaveIntegration = async (integrationType: string) => {
    const config = parseIntegrationConfig(integrationType)
    if (!config || !permissions.can_manage_integrations) return
    const draft = integrationDrafts[integrationType]
    setSaving(true)
    try {
      const updated = await GenesisApi.saveSettingsIntegration(integrationType, {
        enabled: Boolean(draft?.enabled),
        config,
      })
      setIntegrationDrafts((prev) => ({
        ...prev,
        [integrationType]: {
          ...prev[integrationType],
          enabled: updated.enabled,
          configText: JSON.stringify(updated.config ?? {}, null, 2),
          lastTestStatus: updated.last_test?.status,
          lastTestMessage: updated.last_test?.message,
        },
      }))
      withBanner(`${integrationType} ${L('配置已保存', 'settings saved')}`)
    } catch (err: any) {
      setError(err?.response?.data?.message ?? err?.message ?? `Failed to save ${integrationType}`)
    } finally {
      setSaving(false)
    }
  }

  const onSaveSecurity = async (event: FormEvent) => {
    event.preventDefault()
    if (!permissions.can_manage_security || !security) return
    setSaving(true)
    try {
      const updated = await GenesisApi.updateSettingsSecurity({
        sso_enabled: security.sso_enabled,
        mfa_required: security.mfa_required,
        password_min_length: security.password_policy.min_length,
        password_require_upper: security.password_policy.require_upper,
        password_require_lower: security.password_policy.require_lower,
        password_require_number: security.password_policy.require_number,
        password_require_symbol: security.password_policy.require_symbol,
        audit_log_retention_days: security.audit_policy.retention_days,
        audit_export_requires_approval: security.audit_policy.export_requires_approval,
        max_exports_per_day: security.audit_policy.max_exports_per_day,
      })
      setSecurity(updated)
      withBanner(L('安全设置已更新', 'Security settings updated'))
    } catch (err: any) {
      setError(err?.response?.data?.message ?? err?.message ?? 'Failed to update security settings')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-slate-500 shadow-sm">Loading settings...</div>
  }

  return (
    <div className="space-y-6">
      <header className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-semibold text-slate-900">{L('个人设置', 'Personal Settings')}</h1>
        <p className="mt-1 text-sm text-slate-500">
          {L('管理昵称、语言、助手模型配置，以及当前项目的成员、集成与安全策略。', 'Manage your nickname, language, assistant runtime, and the current project settings.')}
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={clsx(
              'rounded-xl px-4 py-2 text-sm font-medium transition',
              activeTab === tab.key ? 'bg-slate-900 text-white' : 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50',
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {message && <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>}

      {activeTab === 'general' && (
        <div className="space-y-6">
          <form onSubmit={onSaveProfile} className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900">{L('个人资料', 'Profile')}</h2>
            <div className="mt-4 max-w-md">
              <label className="mb-1 block text-sm font-medium text-slate-700">{L('显示名称', 'Display Name')}</label>
              <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
            </div>
            <div className="mt-4 flex justify-end">
              <button type="submit" disabled={saving} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
                {L('保存名称', 'Save Name')}
              </button>
            </div>
          </form>

          <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900">{L('显示语言', 'Display Language')}</h2>
            <div className="mt-4 max-w-xs">
              <label className="mb-1 block text-sm font-medium text-slate-700">{L('语言', 'Language')}</label>
              <select value={locale} onChange={(e) => setLocale(e.target.value as 'zh-CN' | 'en-US')} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm">
                <option value="zh-CN">中文</option>
                <option value="en-US">English</option>
              </select>
            </div>
          </section>

          <form onSubmit={onSaveAssistantRuntime} className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900">{L('助手运行时配置', 'Assistant Runtime')}</h2>
            <p className="mt-1 text-sm text-slate-500">
              {L('聊天模块会优先使用这里保存的 API Key、Base URL 和模型名。', 'Chat prefers the API key, base URL, and model saved here.')}
            </p>
            <div className="mt-4 space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">API Key</label>
                <input type="password" value={assistantRuntime.apiKey} onChange={(e) => setAssistantRuntime((prev) => ({ ...prev, apiKey: e.target.value }))} placeholder="sk-..." className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">Base URL</label>
                  <input value={assistantRuntime.baseUrl} onChange={(e) => setAssistantRuntime((prev) => ({ ...prev, baseUrl: e.target.value }))} placeholder="https://api.openai.com/v1" className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">{L('模型名称', 'Model')}</label>
                  <input value={assistantRuntime.model} onChange={(e) => setAssistantRuntime((prev) => ({ ...prev, model: e.target.value }))} placeholder="gpt-5.4" className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
                </div>
              </div>
            </div>
            <div className="mt-4 flex justify-end">
              <button type="submit" className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white">
                {L('保存助手配置', 'Save Assistant Settings')}
              </button>
            </div>
          </form>

          <form onSubmit={onSaveGeneral} className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm space-y-4">
            <h2 className="text-lg font-semibold text-slate-900">{L('项目通用设置', 'Project General')}</h2>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">{L('项目名称', 'Project Name')}</label>
                <input value={general.name} onChange={(e) => setGeneral((prev) => ({ ...prev, name: e.target.value }))} disabled={!permissions.can_manage_general} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">{L('默认域', 'Default Domain')}</label>
                <input value={general.default_domain} onChange={(e) => setGeneral((prev) => ({ ...prev, default_domain: e.target.value }))} disabled={!permissions.can_manage_general} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">{L('描述', 'Description')}</label>
              <textarea rows={3} value={general.description} onChange={(e) => setGeneral((prev) => ({ ...prev, description: e.target.value }))} disabled={!permissions.can_manage_general} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">{L('标签（逗号分隔）', 'Tags (comma separated)')}</label>
              <input value={general.tagsText} onChange={(e) => setGeneral((prev) => ({ ...prev, tagsText: e.target.value }))} disabled={!permissions.can_manage_general} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-500">{L('最后更新时间', 'Last updated')}: {general.updated_at}</span>
              <button type="submit" disabled={!permissions.can_manage_general || saving} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
                {L('保存项目设置', 'Save Project Settings')}
              </button>
            </div>
          </form>
        </div>
      )}

      {activeTab === 'members' && (
        <div className="space-y-6">
          <form onSubmit={onInviteMember} className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900">{L('邀请成员', 'Invite Member')}</h2>
            <div className="mt-4 grid gap-3 md:grid-cols-4">
              <input type="email" placeholder="email" value={inviteForm.email} onChange={(e) => setInviteForm((prev) => ({ ...prev, email: e.target.value }))} disabled={!permissions.can_manage_members} className="rounded-lg border border-slate-200 px-3 py-2 text-sm" />
              <input placeholder={L('名称（可选）', 'Name (optional)')} value={inviteForm.name} onChange={(e) => setInviteForm((prev) => ({ ...prev, name: e.target.value }))} disabled={!permissions.can_manage_members} className="rounded-lg border border-slate-200 px-3 py-2 text-sm" />
              <select value={inviteForm.role} onChange={(e) => setInviteForm((prev) => ({ ...prev, role: e.target.value }))} disabled={!permissions.can_manage_members} className="rounded-lg border border-slate-200 px-3 py-2 text-sm">
                {ROLE_OPTIONS.map((role) => <option key={role} value={role}>{role}</option>)}
              </select>
              <button type="submit" disabled={!permissions.can_manage_members || saving} className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">
                {L('发送邀请', 'Invite')}
              </button>
            </div>
          </form>

          <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900">{L('项目成员', 'Project Members')}</h2>
            <div className="mt-4 space-y-2">
              {members.map((member) => (
                <div key={member.user_id} className="grid items-center gap-3 rounded-2xl border border-slate-100 p-4 md:grid-cols-5">
                  <div className="md:col-span-2">
                    <div className="font-medium text-slate-900">{member.name}</div>
                    <div className="text-xs text-slate-500">{member.email}</div>
                  </div>
                  <div className="text-xs text-slate-500">{member.joined_at ?? '-'}</div>
                  <select value={member.project_role} disabled={!permissions.can_manage_members || member.project_role === 'OWNER'} onChange={(e) => void onUpdateMemberRole(member, e.target.value)} className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm">
                    {member.project_role === 'OWNER' && <option value="OWNER">OWNER</option>}
                    {ROLE_OPTIONS.map((role) => <option key={role} value={role}>{role}</option>)}
                  </select>
                  <button onClick={() => void onRemoveMember(member)} disabled={!permissions.can_manage_members || member.project_role === 'OWNER'} className="rounded-lg border border-rose-200 px-3 py-1.5 text-sm text-rose-600 disabled:opacity-50">
                    {L('移除', 'Remove')}
                  </button>
                </div>
              ))}
            </div>

            <div className="mt-6">
              <h3 className="text-sm font-semibold text-slate-900">{L('待处理邀请', 'Pending Invitations')}</h3>
              {pendingInvitations.length === 0 ? (
                <p className="mt-2 text-sm text-slate-500">{L('暂无待处理邀请。', 'No pending invitations.')}</p>
              ) : (
                <div className="mt-3 space-y-2">
                  {pendingInvitations.map((item) => (
                    <div key={item.id} className="rounded-2xl border border-slate-100 p-4">
                      <div className="text-sm font-medium text-slate-800">{item.email}</div>
                      <div className="mt-1 text-xs text-slate-500">{item.role} · {item.expires_at}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        </div>
      )}

      {activeTab === 'integrations' && (
        <div className="space-y-6">
          {Object.entries(integrationDrafts).map(([integrationType, draft]) => (
            <section key={integrationType} className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-slate-900">{integrationType}</h2>
                  <div className="mt-1 text-sm text-slate-500">{draft.lastTestStatus ?? L('尚未测试', 'Not tested')}</div>
                </div>
                <label className="flex items-center gap-2 text-sm text-slate-700">
                  <input type="checkbox" checked={draft.enabled} disabled={!permissions.can_manage_integrations} onChange={(e) => setIntegrationDrafts((prev) => ({ ...prev, [integrationType]: { ...prev[integrationType], enabled: e.target.checked } }))} />
                  {L('启用', 'Enabled')}
                </label>
              </div>
              <textarea rows={8} value={draft.configText} onChange={(e) => setIntegrationDrafts((prev) => ({ ...prev, [integrationType]: { ...prev[integrationType], configText: e.target.value } }))} disabled={!permissions.can_manage_integrations} className="mt-4 w-full rounded-2xl border border-slate-200 px-3 py-3 font-mono text-xs" />
              {draft.lastTestMessage && <div className="mt-3 text-xs text-slate-500">{draft.lastTestMessage}</div>}
              <div className="mt-4 flex justify-end gap-3">
                <button onClick={() => void onTestIntegration(integrationType)} disabled={!permissions.can_manage_integrations || saving} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-700 disabled:opacity-50">
                  {L('测试连接', 'Test')}
                </button>
                <button onClick={() => void onSaveIntegration(integrationType)} disabled={!permissions.can_manage_integrations || saving} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
                  {L('保存配置', 'Save')}
                </button>
              </div>
            </section>
          ))}
        </div>
      )}

      {activeTab === 'security' && security && (
        <form onSubmit={onSaveSecurity} className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm space-y-6">
          <h2 className="text-lg font-semibold text-slate-900">{L('安全策略', 'Security Policies')}</h2>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={security.sso_enabled} disabled={!permissions.can_manage_security} onChange={(e) => setSecurity((prev) => prev ? { ...prev, sso_enabled: e.target.checked } : prev)} />
              SSO
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={security.mfa_required} disabled={!permissions.can_manage_security} onChange={(e) => setSecurity((prev) => prev ? { ...prev, mfa_required: e.target.checked } : prev)} />
              MFA
            </label>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">{L('最小密码长度', 'Password Min Length')}</label>
              <input type="number" value={security.password_policy.min_length} min={8} max={64} disabled={!permissions.can_manage_security} onChange={(e) => setSecurity((prev) => prev ? { ...prev, password_policy: { ...prev.password_policy, min_length: Number(e.target.value) } } : prev)} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">{L('审计日志保留天数', 'Audit Retention Days')}</label>
              <input type="number" value={security.audit_policy.retention_days} min={7} max={3650} disabled={!permissions.can_manage_security} onChange={(e) => setSecurity((prev) => prev ? { ...prev, audit_policy: { ...prev.audit_policy, retention_days: Number(e.target.value) } } : prev)} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={security.password_policy.require_upper} disabled={!permissions.can_manage_security} onChange={(e) => setSecurity((prev) => prev ? { ...prev, password_policy: { ...prev.password_policy, require_upper: e.target.checked } } : prev)} />
              {L('需要大写字母', 'Require Uppercase')}
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={security.password_policy.require_number} disabled={!permissions.can_manage_security} onChange={(e) => setSecurity((prev) => prev ? { ...prev, password_policy: { ...prev.password_policy, require_number: e.target.checked } } : prev)} />
              {L('需要数字', 'Require Number')}
            </label>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-500">{L('更新时间', 'Updated at')}: {security.updated_at}</span>
            <button type="submit" disabled={!permissions.can_manage_security || saving} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
              {L('保存安全设置', 'Save Security')}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
