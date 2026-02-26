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

type SettingsTab = 'general' | 'members' | 'integrations' | 'security'

interface IntegrationDraft {
  enabled: boolean
  configText: string
  lastTestMessage?: string
  lastTestStatus?: string
}

const ROLE_OPTIONS = ['VIEWER', 'EDITOR', 'APPROVER', 'ADMIN']

const SettingsPage = () => {
  const { user, logout } = useSession()
  const { locale, setLocale, t } = useLanguage()
  const [activeTab, setActiveTab] = useState<SettingsTab>('general')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

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

  const [members, setMembers] = useState<SettingsMember[]>([])
  const [pendingInvitations, setPendingInvitations] = useState<SettingsPendingInvitation[]>([])
  const [inviteForm, setInviteForm] = useState({
    email: '',
    name: '',
    role: 'VIEWER',
  })

  const [integrationDrafts, setIntegrationDrafts] = useState<Record<string, IntegrationDraft>>({})
  const [security, setSecurity] = useState<SettingsSecurity | null>(null)

  const tabs = useMemo(
    () => [
      { key: 'general' as const, label: t('settings.tab.general') },
      { key: 'members' as const, label: t('settings.tab.members') },
      { key: 'integrations' as const, label: t('settings.tab.integrations') },
      { key: 'security' as const, label: t('settings.tab.security') },
    ],
    [t],
  )

  const loadSettings = async () => {
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
  }

  useEffect(() => {
    void loadSettings()
  }, [])

  const withBanner = (nextMessage: string) => {
    setMessage(nextMessage)
    setError(null)
  }

  const onSaveGeneral = async (event: FormEvent) => {
    event.preventDefault()
    if (!permissions.can_manage_general) {
      return
    }
    setSaving(true)
    setError(null)
    try {
      const payload = {
        name: general.name.trim(),
        description: general.description.trim() || null,
        default_domain: general.default_domain.trim() || null,
        tags: general.tagsText
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
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
      withBanner('General settings updated')
    } catch (err: any) {
      setError(err?.response?.data?.message ?? err?.message ?? 'Failed to update general settings')
    } finally {
      setSaving(false)
    }
  }

  const reloadMembers = async () => {
    const data = await GenesisApi.getSettingsMembers()
    setMembers(data.items ?? [])
    setPendingInvitations(data.pending_invitations ?? [])
  }

  const onInviteMember = async (event: FormEvent) => {
    event.preventDefault()
    if (!permissions.can_manage_members) {
      return
    }
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
      withBanner('Member invitation processed')
    } catch (err: any) {
      setError(err?.response?.data?.message ?? err?.message ?? 'Failed to invite member')
    } finally {
      setSaving(false)
    }
  }

  const onUpdateMemberRole = async (member: SettingsMember, role: string) => {
    if (!permissions.can_manage_members || role === member.project_role) {
      return
    }
    setSaving(true)
    setError(null)
    try {
      await GenesisApi.updateSettingsMemberRole(member.user_id, { role })
      await reloadMembers()
      withBanner('Member role updated')
    } catch (err: any) {
      setError(err?.response?.data?.message ?? err?.message ?? 'Failed to update role')
    } finally {
      setSaving(false)
    }
  }

  const onRemoveMember = async (member: SettingsMember) => {
    if (!permissions.can_manage_members) {
      return
    }
    setSaving(true)
    setError(null)
    try {
      await GenesisApi.removeSettingsMember(member.user_id)
      await reloadMembers()
      withBanner('Member removed')
    } catch (err: any) {
      setError(err?.response?.data?.message ?? err?.message ?? 'Failed to remove member')
    } finally {
      setSaving(false)
    }
  }

  const parseIntegrationConfig = (integrationType: string): Record<string, unknown> | null => {
    const draft = integrationDrafts[integrationType]
    if (!draft) {
      return {}
    }
    try {
      const value = JSON.parse(draft.configText || '{}')
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        return value as Record<string, unknown>
      }
      setError(`${integrationType} config must be a JSON object`)
      return null
    } catch {
      setError(`${integrationType} config is invalid JSON`)
      return null
    }
  }

  const onTestIntegration = async (integrationType: string) => {
    if (!permissions.can_manage_integrations) {
      return
    }
    const config = parseIntegrationConfig(integrationType)
    if (!config) {
      return
    }
    setSaving(true)
    setError(null)
    try {
      const result = await GenesisApi.testSettingsIntegration({
        integration_type: integrationType,
        config,
      })
      setIntegrationDrafts((prev) => ({
        ...prev,
        [integrationType]: {
          ...prev[integrationType],
          lastTestStatus: result.status,
          lastTestMessage: result.message,
        },
      }))
      withBanner(`${integrationType} test: ${result.status}`)
    } catch (err: any) {
      setError(err?.response?.data?.message ?? err?.message ?? `Failed to test ${integrationType}`)
    } finally {
      setSaving(false)
    }
  }

  const onSaveIntegration = async (integrationType: string) => {
    if (!permissions.can_manage_integrations) {
      return
    }
    const config = parseIntegrationConfig(integrationType)
    if (!config) {
      return
    }
    const draft = integrationDrafts[integrationType]
    setSaving(true)
    setError(null)
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
      withBanner(`${integrationType} settings saved`)
    } catch (err: any) {
      setError(err?.response?.data?.message ?? err?.message ?? `Failed to save ${integrationType}`)
    } finally {
      setSaving(false)
    }
  }

  const onSaveSecurity = async (event: FormEvent) => {
    event.preventDefault()
    if (!permissions.can_manage_security || !security) {
      return
    }
    setSaving(true)
    setError(null)
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
      withBanner('Security settings updated')
    } catch (err: any) {
      setError(err?.response?.data?.message ?? err?.message ?? 'Failed to update security settings')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="rounded-2xl bg-white p-8 text-center text-slate-500 shadow-sm border border-slate-200">
        Loading settings...
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-2xl font-bold text-slate-900">{t('settings.header')}</h2>
        <p className="mt-1 text-sm text-slate-600">
          Tenant {general.tenant_id} / Project {general.project_id}
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={clsx(
              'rounded-lg px-4 py-2 text-sm font-semibold border transition',
              activeTab === tab.key
                ? 'border-cyan-600 bg-cyan-600 text-white'
                : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50',
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
      {message && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>
      )}

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-semibold text-slate-900">{t('settings.languageTitle')}</h3>
        <p className="mt-1 text-sm text-slate-600">{t('settings.languageDesc')}</p>
        <div className="mt-4 max-w-xs">
          <label className="block text-sm font-medium text-slate-700 mb-1">{t('settings.languageLabel')}</label>
          <select
            value={locale}
            onChange={(e) => setLocale(e.target.value as 'zh-CN' | 'en-US')}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm bg-white"
          >
            <option value="zh-CN">中文</option>
            <option value="en-US">English</option>
          </select>
        </div>
      </section>

      {activeTab === 'general' && (
        <form onSubmit={onSaveGeneral} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Project Name</label>
            <input
              value={general.name}
              onChange={(e) => setGeneral((prev) => ({ ...prev, name: e.target.value }))}
              disabled={!permissions.can_manage_general}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Description</label>
            <textarea
              rows={3}
              value={general.description}
              onChange={(e) => setGeneral((prev) => ({ ...prev, description: e.target.value }))}
              disabled={!permissions.can_manage_general}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Default Domain</label>
              <input
                value={general.default_domain}
                onChange={(e) => setGeneral((prev) => ({ ...prev, default_domain: e.target.value }))}
                disabled={!permissions.can_manage_general}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Tags (comma separated)</label>
              <input
                value={general.tagsText}
                onChange={(e) => setGeneral((prev) => ({ ...prev, tagsText: e.target.value }))}
                disabled={!permissions.can_manage_general}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-500">Last updated: {general.updated_at}</span>
            <button
              type="submit"
              disabled={!permissions.can_manage_general || saving}
              className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              Save General
            </button>
          </div>
        </form>
      )}

      {activeTab === 'members' && (
        <div className="space-y-4">
          <form onSubmit={onInviteMember} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h3 className="text-lg font-semibold text-slate-900">Invite Member</h3>
            <div className="mt-4 grid gap-3 md:grid-cols-4">
              <input
                type="email"
                placeholder="email"
                value={inviteForm.email}
                onChange={(e) => setInviteForm((prev) => ({ ...prev, email: e.target.value }))}
                disabled={!permissions.can_manage_members}
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
              <input
                placeholder="name (optional)"
                value={inviteForm.name}
                onChange={(e) => setInviteForm((prev) => ({ ...prev, name: e.target.value }))}
                disabled={!permissions.can_manage_members}
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
              <select
                value={inviteForm.role}
                onChange={(e) => setInviteForm((prev) => ({ ...prev, role: e.target.value }))}
                disabled={!permissions.can_manage_members}
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
              >
                {ROLE_OPTIONS.map((role) => (
                  <option key={role} value={role}>
                    {role}
                  </option>
                ))}
              </select>
              <button
                type="submit"
                disabled={!permissions.can_manage_members || saving}
                className="rounded-lg bg-cyan-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                Invite
              </button>
            </div>
          </form>

          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h3 className="text-lg font-semibold text-slate-900 mb-4">Members</h3>
            <div className="space-y-2">
              {members.map((member) => (
                <div key={member.user_id} className="grid gap-3 rounded-lg border border-slate-100 p-3 md:grid-cols-5 items-center">
                  <div className="md:col-span-2">
                    <div className="font-medium text-slate-900">{member.name}</div>
                    <div className="text-xs text-slate-500">{member.email}</div>
                  </div>
                  <div className="text-xs text-slate-600">{member.joined_at ?? '-'}</div>
                  <select
                    value={member.project_role}
                    disabled={!permissions.can_manage_members || member.project_role === 'OWNER'}
                    onChange={(e) => void onUpdateMemberRole(member, e.target.value)}
                    className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
                  >
                    {member.project_role === 'OWNER' && <option value="OWNER">OWNER</option>}
                    {ROLE_OPTIONS.map((role) => (
                      <option key={role} value={role}>
                        {role}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={() => void onRemoveMember(member)}
                    disabled={!permissions.can_manage_members || member.project_role === 'OWNER'}
                    className="rounded-lg border border-rose-200 px-3 py-1.5 text-sm text-rose-600 disabled:opacity-50"
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h3 className="text-lg font-semibold text-slate-900 mb-4">Pending Invitations</h3>
            {pendingInvitations.length === 0 ? (
              <p className="text-sm text-slate-500">No pending invitations.</p>
            ) : (
              <div className="space-y-2">
                {pendingInvitations.map((item) => (
                  <div key={item.id} className="flex items-center justify-between rounded-lg border border-slate-100 p-3">
                    <div>
                      <div className="text-sm font-medium text-slate-800">{item.email}</div>
                      <div className="text-xs text-slate-500">
                        {item.role} | expires {item.expires_at}
                      </div>
                    </div>
                    <span className="text-xs rounded-full bg-amber-100 px-2 py-1 text-amber-700">{item.status}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'integrations' && (
        <div className="space-y-4">
          {Object.entries(integrationDrafts).map(([integrationType, draft]) => (
            <div key={integrationType} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-slate-900">{integrationType}</h3>
                <label className="flex items-center gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={draft.enabled}
                    disabled={!permissions.can_manage_integrations}
                    onChange={(e) =>
                      setIntegrationDrafts((prev) => ({
                        ...prev,
                        [integrationType]: {
                          ...prev[integrationType],
                          enabled: e.target.checked,
                        },
                      }))
                    }
                  />
                  Enabled
                </label>
              </div>
              <textarea
                rows={7}
                value={draft.configText}
                disabled={!permissions.can_manage_integrations}
                onChange={(e) =>
                  setIntegrationDrafts((prev) => ({
                    ...prev,
                    [integrationType]: {
                      ...prev[integrationType],
                      configText: e.target.value,
                    },
                  }))
                }
                className="mt-3 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-mono"
              />
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <button
                  onClick={() => void onTestIntegration(integrationType)}
                  disabled={!permissions.can_manage_integrations || saving}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 disabled:opacity-50"
                >
                  Test
                </button>
                <button
                  onClick={() => void onSaveIntegration(integrationType)}
                  disabled={!permissions.can_manage_integrations || saving}
                  className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                >
                  Save
                </button>
                <span className="text-xs text-slate-500">
                  Last test: {draft.lastTestStatus ?? '-'} {draft.lastTestMessage ? `| ${draft.lastTestMessage}` : ''}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {activeTab === 'security' && security && (
        <form onSubmit={onSaveSecurity} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={security.sso_enabled}
                disabled={!permissions.can_manage_security}
                onChange={(e) => setSecurity((prev) => (prev ? { ...prev, sso_enabled: e.target.checked } : prev))}
              />
              SSO Enabled
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={security.mfa_required}
                disabled={!permissions.can_manage_security}
                onChange={(e) => setSecurity((prev) => (prev ? { ...prev, mfa_required: e.target.checked } : prev))}
              />
              MFA Required
            </label>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Password Min Length</label>
              <input
                type="number"
                value={security.password_policy.min_length}
                min={8}
                max={64}
                disabled={!permissions.can_manage_security}
                onChange={(e) =>
                  setSecurity((prev) =>
                    prev
                      ? {
                          ...prev,
                          password_policy: {
                            ...prev.password_policy,
                            min_length: Number(e.target.value),
                          },
                        }
                      : prev,
                  )
                }
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Audit Retention Days</label>
              <input
                type="number"
                value={security.audit_policy.retention_days}
                min={7}
                max={3650}
                disabled={!permissions.can_manage_security}
                onChange={(e) =>
                  setSecurity((prev) =>
                    prev
                      ? {
                          ...prev,
                          audit_policy: {
                            ...prev.audit_policy,
                            retention_days: Number(e.target.value),
                          },
                        }
                      : prev,
                  )
                }
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-4">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={security.password_policy.require_upper}
                disabled={!permissions.can_manage_security}
                onChange={(e) =>
                  setSecurity((prev) =>
                    prev
                      ? {
                          ...prev,
                          password_policy: {
                            ...prev.password_policy,
                            require_upper: e.target.checked,
                          },
                        }
                      : prev,
                  )
                }
              />
              Upper
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={security.password_policy.require_lower}
                disabled={!permissions.can_manage_security}
                onChange={(e) =>
                  setSecurity((prev) =>
                    prev
                      ? {
                          ...prev,
                          password_policy: {
                            ...prev.password_policy,
                            require_lower: e.target.checked,
                          },
                        }
                      : prev,
                  )
                }
              />
              Lower
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={security.password_policy.require_number}
                disabled={!permissions.can_manage_security}
                onChange={(e) =>
                  setSecurity((prev) =>
                    prev
                      ? {
                          ...prev,
                          password_policy: {
                            ...prev.password_policy,
                            require_number: e.target.checked,
                          },
                        }
                      : prev,
                  )
                }
              />
              Number
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={security.password_policy.require_symbol}
                disabled={!permissions.can_manage_security}
                onChange={(e) =>
                  setSecurity((prev) =>
                    prev
                      ? {
                          ...prev,
                          password_policy: {
                            ...prev.password_policy,
                            require_symbol: e.target.checked,
                          },
                        }
                      : prev,
                  )
                }
              />
              Symbol
            </label>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={security.audit_policy.export_requires_approval}
                disabled={!permissions.can_manage_security}
                onChange={(e) =>
                  setSecurity((prev) =>
                    prev
                      ? {
                          ...prev,
                          audit_policy: {
                            ...prev.audit_policy,
                            export_requires_approval: e.target.checked,
                          },
                        }
                      : prev,
                  )
                }
              />
              Audit Export Requires Approval
            </label>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Max Exports / Day</label>
              <input
                type="number"
                value={security.audit_policy.max_exports_per_day}
                min={1}
                max={10000}
                disabled={!permissions.can_manage_security}
                onChange={(e) =>
                  setSecurity((prev) =>
                    prev
                      ? {
                          ...prev,
                          audit_policy: {
                            ...prev.audit_policy,
                            max_exports_per_day: Number(e.target.value),
                          },
                        }
                      : prev,
                  )
                }
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </div>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-500">Updated at: {security.updated_at}</span>
            <button
              type="submit"
              disabled={!permissions.can_manage_security || saving}
              className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              Save Security
            </button>
          </div>
        </form>
      )}

      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm flex items-center justify-between">
        <div className="text-sm text-slate-600">User: {user?.email ?? 'unknown'}</div>
        <button onClick={logout} className="rounded-lg border border-rose-200 px-3 py-1.5 text-sm text-rose-600">
          Log Out
        </button>
      </div>
    </div>
  )
}

export default SettingsPage
