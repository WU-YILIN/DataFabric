import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
    Building2,
    FolderOpen,
    Plus,
    Pencil,
    Trash2,
    ChevronDown,
    ChevronRight,
    KeyRound,
    Copy,
    Check,
    ArrowLeft,
} from 'lucide-react'
import { clsx } from 'clsx'
import axios from 'axios'
import { Link } from 'react-router-dom'

import { useSession } from '../auth/session'
import { useLanguage } from '../i18n/language'

const api = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000',
    timeout: 20000,
})

export default function TenantProjectManagement() {
    const { t } = useLanguage()
    const { accessToken, activeTenantId, activeProjectId, refreshProfile } = useSession()
    const queryClient = useQueryClient()

    const [expandedTenantId, setExpandedTenantId] = useState<number | null>(null)
    const [showCreateTenant, setShowCreateTenant] = useState(false)
    const [showCreateProject, setShowCreateProject] = useState<number | null>(null)
    const [editTenant, setEditTenant] = useState<any>(null)
    const [editProject, setEditProject] = useState<any>(null)
    const [copiedKey, setCopiedKey] = useState<number | null>(null)

    // Form states
    const [tenantName, setTenantName] = useState('')
    const [tenantSlug, setTenantSlug] = useState('')
    const [projectName, setProjectName] = useState('')
    const [projectDesc, setProjectDesc] = useState('')

    const headers: Record<string, string> = {}
    if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`
    if (activeProjectId != null) headers['X-PROJECT-ID'] = String(activeProjectId)
    if (activeTenantId != null) headers['X-TENANT-ID'] = String(activeTenantId)

    // ── Queries ──
    const { data: tenantsData, isLoading } = useQuery({
        queryKey: ['admin-tenants'],
        queryFn: async () => {
            const res = await api.get('/api/v1/admin/tenants', { headers })
            return res.data?.data
        },
    })

    const { data: projectsData } = useQuery({
        queryKey: ['admin-projects', expandedTenantId],
        queryFn: async () => {
            if (!expandedTenantId) return null
            const res = await api.get(`/api/v1/admin/tenants/${expandedTenantId}/projects`, { headers })
            return res.data?.data
        },
        enabled: !!expandedTenantId,
    })

    // ── Mutations ──
    const createTenantMutation = useMutation({
        mutationFn: async () => {
            return api.post('/api/v1/admin/tenants', { name: tenantName, slug: tenantSlug }, { headers })
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-tenants'] })
            setShowCreateTenant(false)
            setTenantName('')
            setTenantSlug('')
            refreshProfile()
        },
    })

    const updateTenantMutation = useMutation({
        mutationFn: async ({ id, name }: { id: number; name: string }) => {
            return api.patch(`/api/v1/admin/tenants/${id}`, { name }, { headers })
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-tenants'] })
            setEditTenant(null)
            refreshProfile()
        },
    })

    const archiveTenantMutation = useMutation({
        mutationFn: async (id: number) => {
            return api.delete(`/api/v1/admin/tenants/${id}`, { headers })
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-tenants'] })
            refreshProfile()
        },
    })

    const createProjectMutation = useMutation({
        mutationFn: async (tenantId: number) => {
            return api.post(`/api/v1/admin/tenants/${tenantId}/projects`, { name: projectName, description: projectDesc }, { headers })
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-projects', expandedTenantId] })
            queryClient.invalidateQueries({ queryKey: ['admin-tenants'] })
            setShowCreateProject(null)
            setProjectName('')
            setProjectDesc('')
            refreshProfile()
        },
    })

    const updateProjectMutation = useMutation({
        mutationFn: async ({ id, name, description }: { id: number; name: string; description: string }) => {
            return api.patch(`/api/v1/admin/projects/${id}`, { name, description }, { headers })
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-projects', expandedTenantId] })
            setEditProject(null)
            refreshProfile()
        },
    })

    const deleteProjectMutation = useMutation({
        mutationFn: async (id: number) => {
            return api.delete(`/api/v1/admin/projects/${id}`, { headers })
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-projects', expandedTenantId] })
            queryClient.invalidateQueries({ queryKey: ['admin-tenants'] })
            refreshProfile()
        },
    })

    const copyApiKey = (projectId: number, key: string) => {
        navigator.clipboard.writeText(key)
        setCopiedKey(projectId)
        setTimeout(() => setCopiedKey(null), 2000)
    }

    const tenants = tenantsData?.items || []
    const projects = projectsData?.items || []

    if (isLoading) {
        return <div className="p-8 text-center text-slate-500">Loading...</div>
    }

    return (
        <div className="animate-in fade-in zoom-in-95 duration-200">
            {/* Header */}
            <div className="mb-6 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <Link to="/settings" className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500 hover:bg-slate-50">
                        <ArrowLeft size={18} />
                    </Link>
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 to-indigo-600 text-white shadow-md">
                        <Building2 size={24} />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold tracking-tight text-slate-900">{t('Organization Management')}</h1>
                        <p className="text-sm text-slate-500">{t('Create and manage tenants and projects')}</p>
                    </div>
                </div>
                <button
                    onClick={() => { setShowCreateTenant(true); setTenantName(''); setTenantSlug('') }}
                    className="flex items-center gap-2 rounded-xl bg-black px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800 shadow-sm"
                >
                    <Plus size={16} />
                    {t('New Tenant')}
                </button>
            </div>

            {/* Create Tenant Modal */}
            {showCreateTenant && (
                <div className="mb-6 rounded-2xl border border-indigo-200 bg-indigo-50/50 p-5">
                    <h3 className="mb-3 text-sm font-semibold text-indigo-900">{t('Create New Tenant')}</h3>
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                        <input
                            className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
                            placeholder={t('Tenant Name')}
                            value={tenantName}
                            onChange={(e) => setTenantName(e.target.value)}
                        />
                        <input
                            className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-mono focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
                            placeholder={t('Slug (lowercase, e.g. acme-corp)')}
                            value={tenantSlug}
                            onChange={(e) => setTenantSlug(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''))}
                        />
                    </div>
                    <div className="mt-3 flex gap-2">
                        <button
                            onClick={() => createTenantMutation.mutate()}
                            disabled={!tenantName || !tenantSlug || createTenantMutation.isPending}
                            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                        >
                            {createTenantMutation.isPending ? t('Creating...') : t('Create')}
                        </button>
                        <button
                            onClick={() => setShowCreateTenant(false)}
                            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
                        >
                            {t('Cancel')}
                        </button>
                    </div>
                </div>
            )}

            {/* Tenant List */}
            <div className="space-y-3">
                {tenants.length === 0 && (
                    <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center">
                        <Building2 className="mx-auto mb-3 text-slate-300" size={48} />
                        <p className="text-slate-500">{t('No tenants yet. Create your first tenant to get started.')}</p>
                    </div>
                )}

                {tenants.map((tenant: any) => {
                    const isExpanded = expandedTenantId === tenant.id

                    return (
                        <div key={tenant.id} className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                            {/* Tenant Header */}
                            <div
                                className="flex items-center justify-between px-5 py-4 cursor-pointer hover:bg-slate-50 transition-colors"
                                onClick={() => setExpandedTenantId(isExpanded ? null : tenant.id)}
                            >
                                <div className="flex items-center gap-3">
                                    {isExpanded ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronRight size={16} className="text-slate-400" />}
                                    <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-slate-100 to-slate-200 text-slate-600">
                                        <Building2 size={18} />
                                    </div>
                                    <div>
                                        {editTenant?.id === tenant.id ? (
                                            <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                                                <input
                                                    className="rounded-lg border border-indigo-300 px-2 py-1 text-sm"
                                                    value={editTenant.name}
                                                    onChange={(e) => setEditTenant({ ...editTenant, name: e.target.value })}
                                                />
                                                <button
                                                    onClick={() => updateTenantMutation.mutate({ id: tenant.id, name: editTenant.name })}
                                                    className="rounded bg-indigo-600 px-2 py-1 text-xs text-white"
                                                >
                                                    Save
                                                </button>
                                                <button onClick={() => setEditTenant(null)} className="text-xs text-slate-500">Cancel</button>
                                            </div>
                                        ) : (
                                            <>
                                                <h3 className="text-sm font-semibold text-slate-900">{tenant.name}</h3>
                                                <p className="text-xs text-slate-500">
                                                    <span className="font-mono">{tenant.slug}</span>
                                                    <span className="mx-2 text-slate-300">·</span>
                                                    {tenant.project_count} {t('projects')}
                                                    <span className="mx-2 text-slate-300">·</span>
                                                    <span className={clsx('inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium',
                                                        tenant.status === 'ACTIVE' ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-500'
                                                    )}>
                                                        {tenant.status}
                                                    </span>
                                                </p>
                                            </>
                                        )}
                                    </div>
                                </div>
                                <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                                    <button
                                        onClick={() => setEditTenant({ id: tenant.id, name: tenant.name })}
                                        className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                                        title="Edit"
                                    >
                                        <Pencil size={14} />
                                    </button>
                                    <button
                                        onClick={() => { if (confirm(t('Archive this tenant?'))) archiveTenantMutation.mutate(tenant.id) }}
                                        className="rounded-lg p-2 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                                        title="Archive"
                                    >
                                        <Trash2 size={14} />
                                    </button>
                                </div>
                            </div>

                            {/* Expanded: Projects */}
                            {isExpanded && (
                                <div className="border-t border-slate-100 bg-slate-50/50 px-5 py-4">
                                    <div className="mb-3 flex items-center justify-between">
                                        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">{t('Projects')}</h4>
                                        <button
                                            onClick={() => { setShowCreateProject(tenant.id); setProjectName(''); setProjectDesc('') }}
                                            className="flex items-center gap-1 rounded-lg bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100"
                                        >
                                            <Plus size={12} />
                                            {t('New Project')}
                                        </button>
                                    </div>

                                    {/* Create Project Form */}
                                    {showCreateProject === tenant.id && (
                                        <div className="mb-4 rounded-xl border border-indigo-200 bg-white p-4">
                                            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                                                <input
                                                    className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400"
                                                    placeholder={t('Project Name')}
                                                    value={projectName}
                                                    onChange={(e) => setProjectName(e.target.value)}
                                                />
                                                <input
                                                    className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400"
                                                    placeholder={t('Description (optional)')}
                                                    value={projectDesc}
                                                    onChange={(e) => setProjectDesc(e.target.value)}
                                                />
                                            </div>
                                            <div className="mt-2 flex gap-2">
                                                <button
                                                    onClick={() => createProjectMutation.mutate(tenant.id)}
                                                    disabled={!projectName || createProjectMutation.isPending}
                                                    className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                                                >
                                                    {createProjectMutation.isPending ? t('Creating...') : t('Create Project')}
                                                </button>
                                                <button
                                                    onClick={() => setShowCreateProject(null)}
                                                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-500 hover:bg-slate-50"
                                                >
                                                    {t('Cancel')}
                                                </button>
                                            </div>
                                        </div>
                                    )}

                                    {/* Projects Table */}
                                    {projects.length === 0 ? (
                                        <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-400">
                                            {t('No projects under this tenant')}
                                        </div>
                                    ) : (
                                        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
                                            <table className="w-full text-left text-sm">
                                                <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                                                    <tr>
                                                        <th className="px-4 py-2.5 font-medium">{t('Project')}</th>
                                                        <th className="px-4 py-2.5 font-medium">{t('API Key')}</th>
                                                        <th className="px-4 py-2.5 font-medium">{t('Created')}</th>
                                                        <th className="px-4 py-2.5 font-medium text-right">{t('Actions')}</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-slate-100">
                                                    {projects.map((project: any) => (
                                                        <tr key={project.id} className="hover:bg-slate-50">
                                                            <td className="px-4 py-3">
                                                                {editProject?.id === project.id ? (
                                                                    <div className="flex items-center gap-2">
                                                                        <input
                                                                            className="rounded border border-indigo-300 px-2 py-1 text-xs w-28"
                                                                            value={editProject.name}
                                                                            onChange={(e) => setEditProject({ ...editProject, name: e.target.value })}
                                                                        />
                                                                        <button
                                                                            onClick={() => updateProjectMutation.mutate({ id: project.id, name: editProject.name, description: editProject.description || '' })}
                                                                            className="rounded bg-indigo-600 px-2 py-0.5 text-[10px] text-white"
                                                                        >
                                                                            Save
                                                                        </button>
                                                                        <button onClick={() => setEditProject(null)} className="text-[10px] text-slate-400">Cancel</button>
                                                                    </div>
                                                                ) : (
                                                                    <div className="flex items-center gap-2">
                                                                        <FolderOpen size={14} className="text-indigo-500" />
                                                                        <div>
                                                                            <span className="font-medium text-slate-900">{project.name}</span>
                                                                            {project.description && <p className="text-xs text-slate-400 mt-0.5">{project.description}</p>}
                                                                        </div>
                                                                    </div>
                                                                )}
                                                            </td>
                                                            <td className="px-4 py-3">
                                                                <div className="flex items-center gap-1.5">
                                                                    <KeyRound size={12} className="text-slate-400" />
                                                                    <code className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600 max-w-[160px] truncate">
                                                                        {project.api_key}
                                                                    </code>
                                                                    <button
                                                                        onClick={() => copyApiKey(project.id, project.api_key || '')}
                                                                        className="text-slate-400 hover:text-slate-600"
                                                                    >
                                                                        {copiedKey === project.id ? <Check size={12} className="text-green-500" /> : <Copy size={12} />}
                                                                    </button>
                                                                </div>
                                                            </td>
                                                            <td className="px-4 py-3 text-xs text-slate-500">
                                                                {project.created_at ? new Date(project.created_at).toLocaleDateString() : '-'}
                                                            </td>
                                                            <td className="px-4 py-3 text-right">
                                                                <div className="flex items-center justify-end gap-1">
                                                                    <button
                                                                        onClick={() => setEditProject({ id: project.id, name: project.name, description: project.description })}
                                                                        className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                                                                    >
                                                                        <Pencil size={13} />
                                                                    </button>
                                                                    <button
                                                                        onClick={() => { if (confirm(t('Delete this project permanently?'))) deleteProjectMutation.mutate(project.id) }}
                                                                        className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                                                                    >
                                                                        <Trash2 size={13} />
                                                                    </button>
                                                                </div>
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    )
                })}
            </div>
        </div>
    )
}
