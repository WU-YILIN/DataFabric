import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import {
  GenesisApi,
  type AuthTenant,
  type AuthUser,
  setApiAuthContext,
} from '../services/api'

const STORAGE_KEY = 'genesis_session_v1'

interface SessionState {
  accessToken: string | null
  expiresAt: string | null
  user: AuthUser | null
  tenants: AuthTenant[]
  activeTenantId: number | null
  activeProjectId: number | null
}

interface SessionContextValue extends SessionState {
  isLoading: boolean
  isSwitchingContext: boolean
  contextVersion: string
  isAuthenticated: boolean
  activeTenant: AuthTenant | null
  activeProject: { id: number; name: string; role: string } | null
  login: (email: string, password: string) => Promise<void>
  register: (payload: { email: string; password: string; name: string }) => Promise<void>
  logout: () => void
  switchTenant: (tenantId: number) => Promise<void>
  switchProject: (projectId: number) => Promise<void>
  refreshProfile: () => Promise<void>
}

const SessionContext = createContext<SessionContextValue | null>(null)

function chooseDefaultContext(tenants: AuthTenant[]): { tenantId: number | null; projectId: number | null } {
  for (const tenant of tenants) {
    if (tenant.projects.length > 0) {
      return { tenantId: tenant.id, projectId: tenant.projects[0].id }
    }
  }
  return { tenantId: null, projectId: null }
}

function normalizeContext(
  tenants: AuthTenant[],
  activeTenantId: number | null,
  activeProjectId: number | null,
) {
  if (activeTenantId == null || activeProjectId == null) {
    return chooseDefaultContext(tenants)
  }
  const tenant = tenants.find((item) => item.id === activeTenantId)
  if (!tenant) {
    return chooseDefaultContext(tenants)
  }
  const project = tenant.projects.find((item) => item.id === activeProjectId)
  if (!project) {
    if (tenant.projects.length === 0) {
      return chooseDefaultContext(tenants)
    }
    return { tenantId: tenant.id, projectId: tenant.projects[0].id }
  }
  return { tenantId: tenant.id, projectId: project.id }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>(() => {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      return {
        accessToken: null,
        expiresAt: null,
        user: null,
        tenants: [],
        activeTenantId: null,
        activeProjectId: null,
      }
    }
    try {
      return JSON.parse(raw) as SessionState
    } catch {
      return {
        accessToken: null,
        expiresAt: null,
        user: null,
        tenants: [],
        activeTenantId: null,
        activeProjectId: null,
      }
    }
  })
  const [isLoading, setIsLoading] = useState(Boolean(state.accessToken))
  const [isSwitchingContext, setIsSwitchingContext] = useState(false)

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
    setApiAuthContext({
      accessToken: state.accessToken,
      tenantId: state.activeTenantId,
      projectId: state.activeProjectId,
    })
  }, [state])

  useEffect(() => {
    if (!state.accessToken) {
      setIsLoading(false)
      return
    }
    void (async () => {
      try {
        await refreshProfileInternal()
      } catch {
        logoutInternal()
      } finally {
        setIsLoading(false)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function refreshProfileInternal() {
    const profile = await GenesisApi.getMe()
    setState((prev) => {
      const normalized = normalizeContext(profile.tenants, prev.activeTenantId, prev.activeProjectId)
      return {
        ...prev,
        user: profile.user,
        tenants: profile.tenants,
        activeTenantId: normalized.tenantId,
        activeProjectId: normalized.projectId,
      }
    })
  }

  async function applyContext(tenantId: number, projectId: number) {
    setIsSwitchingContext(true)
    try {
      const result = await GenesisApi.switchContext({
        tenant_id: tenantId,
        project_id: projectId,
      })
      setState((prev) => ({
        ...prev,
        user: result.user,
        tenants: result.tenants,
        activeTenantId: result.context.tenant_id,
        activeProjectId: result.context.project_id,
      }))
    } finally {
      setIsSwitchingContext(false)
    }
  }

  function logoutInternal() {
    setState({
      accessToken: null,
      expiresAt: null,
      user: null,
      tenants: [],
      activeTenantId: null,
      activeProjectId: null,
    })
  }

  async function login(email: string, password: string) {
    const result = await GenesisApi.login({ email, password })
    const normalized = result.default_context
      ? { tenantId: result.default_context.tenant_id, projectId: result.default_context.project_id }
      : chooseDefaultContext(result.tenants)

    setState({
      accessToken: result.access_token,
      expiresAt: result.expires_at,
      user: result.user,
      tenants: result.tenants,
      activeTenantId: normalized.tenantId,
      activeProjectId: normalized.projectId,
    })
  }

  async function register(payload: { email: string; password: string; name: string }) {
    const result = await GenesisApi.register(payload)
    const normalized = result.default_context
      ? { tenantId: result.default_context.tenant_id, projectId: result.default_context.project_id }
      : chooseDefaultContext(result.tenants)

    setState({
      accessToken: result.access_token,
      expiresAt: result.expires_at,
      user: result.user,
      tenants: result.tenants,
      activeTenantId: normalized.tenantId,
      activeProjectId: normalized.projectId,
    })
  }

  async function switchTenant(tenantId: number) {
    const tenant = state.tenants.find((item) => item.id === tenantId)
    if (!tenant || tenant.projects.length === 0) {
      return
    }
    await applyContext(tenant.id, tenant.projects[0].id)
  }

  async function switchProject(projectId: number) {
    if (state.activeTenantId == null) {
      return
    }
    await applyContext(state.activeTenantId, projectId)
  }

  const value = useMemo<SessionContextValue>(() => {
    const activeTenant =
      state.activeTenantId == null
        ? null
        : state.tenants.find((item) => item.id === state.activeTenantId) ?? null
    const activeProject =
      activeTenant && state.activeProjectId != null
        ? activeTenant.projects.find((item) => item.id === state.activeProjectId) ?? null
        : null

    return {
      ...state,
      isLoading,
      isSwitchingContext,
      contextVersion: `${state.activeTenantId ?? 'none'}:${state.activeProjectId ?? 'none'}`,
      isAuthenticated: Boolean(state.accessToken && state.user),
      activeTenant,
      activeProject,
      login,
      register,
      logout: logoutInternal,
      switchTenant,
      switchProject,
      refreshProfile: refreshProfileInternal,
    }
  }, [isLoading, isSwitchingContext, state])

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession() {
  const context = useContext(SessionContext)
  if (!context) {
    throw new Error('useSession must be used inside SessionProvider')
  }
  return context
}
