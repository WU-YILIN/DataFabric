import { type ComponentType, useEffect, useMemo, useState } from 'react'
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import {
  BarChart3,
  Bell,
  BookOpen,
  Boxes,
  BrainCircuit,
  Cable,
  ChevronDown,
  Coins,
  Database,
  Download,
  FileSearch,
  FlaskConical,
  FolderKanban,
  LibraryBig,
  LogOut,
  MessageSquarePlus,
  Palette,
  Pencil,
  PlugZap,
  Rocket,
  Search,
  Server,
  Settings,
  ShieldCheck,
  Siren,
  Store,
  Users,
  Waypoints,
  Waves,
  Workflow,
  X,
} from 'lucide-react'
import { useSession } from './auth/session'
import Login from './pages/Login'
import AIChat from './pages/AIChat'
import ProjectManagement from './pages/ProjectManagement'
import P0Module from './pages/P0Module'
import SourceOnboarding from './pages/SourceOnboarding'
import Pipelines from './pages/Pipelines'
import DataCatalog from './pages/DataCatalog'
import DataQuality from './pages/DataQuality'
import Infrastructure from './pages/Infrastructure'
import Scheduler from './pages/Scheduler'
import AuditLogs from './pages/AuditLogs'
import SettingsPage from './pages/Settings'
import MonitoringAlerts from './pages/MonitoringAlerts'
import CollaborationWorkflowPage from './pages/CollaborationWorkflow'
import KnowledgeDocs from './pages/KnowledgeDocs'
import CostUsageAnalytics from './pages/CostUsageAnalytics'
import SandboxExperimentation from './pages/SandboxExperimentation'
import IntegrationHub from './pages/IntegrationHub'
import PolicyRuleCenterPage from './pages/PolicyRuleCenter'
import IngestionSdkCenter from './pages/IngestionSdkCenter'
import ReleaseChangeManagement from './pages/ReleaseChangeManagement'
import CustomReportsDashboardBuilder from './pages/CustomReportsDashboardBuilder'
import DataProductMarketplace from './pages/DataProductMarketplace'
import IncidentResponseCenter from './pages/IncidentResponseCenter'
import AIMemory from './pages/AIMemory'
import FabricSourceProfiles from './pages/FabricSourceProfiles'
import FabricUpdateSemantics from './pages/FabricUpdateSemantics'
import FabricSemanticDomains from './pages/FabricSemanticDomains'
import FabricPlanner from './pages/FabricPlanner'
import FabricMaterializations from './pages/FabricMaterializations'
import FabricTelemetry from './pages/FabricTelemetry'
import DesignPreview from './pages/DesignPreview'
import { CHAT_CONVERSATIONS_CHANGED, deleteChatConversation, listChatConversations, type StoredChatConversation } from './utils/chatWorkspace'
import { getConfirmedProjectId, setConfirmedProjectId } from './utils/workspaceSelection'

type IconType = ComponentType<{ size?: string | number; className?: string }>
type PlatformGroup = '数据接入' | '语义与记忆' | '执行与交付' | '观测与治理' | '内部控制'
type PlatformModule = { key: string; to: string; icon: IconType; label: string; group: PlatformGroup; order: number; defaultVisible: boolean }
type PlatformSettings = { version: 2; enabledKeys: string[]; orderedKeys: string[] }

const GROUPS: PlatformGroup[] = ['数据接入', '语义与记忆', '执行与交付', '观测与治理', '内部控制']
const STORAGE_KEY = 'datafabric.platform.modules.v2'
const WORKSPACE_ITEMS = [
  { to: '/projects', icon: FolderKanban, label: '项目管理' },
  { to: '/knowledge', icon: BookOpen, label: '知识文档' },
  { to: '/memory', icon: BrainCircuit, label: 'AI 记忆' },
]
const PLATFORM_MODULES: PlatformModule[] = [
  { key: 'source-intake', to: '/source-onboarding', icon: Cable, label: '数据源接入', group: '数据接入', order: 10, defaultVisible: true },
  { key: 'integration-hub', to: '/integration-hub', icon: PlugZap, label: '集成中心', group: '数据接入', order: 20, defaultVisible: false },
  { key: 'ingestion-sdk', to: '/ingestion', icon: Download, label: '采集 SDK', group: '数据接入', order: 30, defaultVisible: false },
  { key: 'memory', to: '/memory', icon: BrainCircuit, label: 'AI 记忆', group: '语义与记忆', order: 40, defaultVisible: true },
  { key: 'source-profiles', to: '/fabric/source-profiles', icon: LibraryBig, label: '源画像', group: '语义与记忆', order: 50, defaultVisible: false },
  { key: 'domains', to: '/fabric/domains', icon: Waypoints, label: '主题域', group: '语义与记忆', order: 60, defaultVisible: false },
  { key: 'planner', to: '/fabric/planner', icon: Workflow, label: '查询规划', group: '语义与记忆', order: 70, defaultVisible: true },
  { key: 'pipelines', to: '/pipelines', icon: Workflow, label: '交付管道', group: '执行与交付', order: 80, defaultVisible: false },
  { key: 'materializations', to: '/fabric/materializations', icon: Boxes, label: '物化中心', group: '执行与交付', order: 90, defaultVisible: true },
  { key: 'catalog', to: '/catalog', icon: Database, label: '数据目录', group: '执行与交付', order: 100, defaultVisible: false },
  { key: 'data-quality', to: '/data-quality', icon: ShieldCheck, label: '数据质量', group: '执行与交付', order: 110, defaultVisible: false },
  { key: 'reports', to: '/reports', icon: BarChart3, label: '报表中心', group: '执行与交付', order: 120, defaultVisible: false },
  { key: 'marketplace', to: '/marketplace', icon: Store, label: '数据市场', group: '执行与交付', order: 130, defaultVisible: false },
  { key: 'scheduler', to: '/scheduler', icon: Workflow, label: '调度中心', group: '执行与交付', order: 140, defaultVisible: false },
  { key: 'telemetry', to: '/fabric/telemetry', icon: Waves, label: '遥测中心', group: '观测与治理', order: 150, defaultVisible: true },
  { key: 'logs', to: '/logs', icon: FileSearch, label: '审计日志', group: '观测与治理', order: 160, defaultVisible: true },
  { key: 'monitoring', to: '/monitoring', icon: Bell, label: '监控告警', group: '观测与治理', order: 170, defaultVisible: false },
  { key: 'cost', to: '/cost', icon: Coins, label: '成本分析', group: '观测与治理', order: 180, defaultVisible: false },
  { key: 'infrastructure', to: '/infrastructure', icon: Server, label: '基础设施', group: '观测与治理', order: 190, defaultVisible: false },
  { key: 'collaboration', to: '/collaboration', icon: Users, label: '协同流程', group: '观测与治理', order: 200, defaultVisible: false },
  { key: 'policy-center', to: '/policy-center', icon: ShieldCheck, label: '规则中心', group: '观测与治理', order: 210, defaultVisible: false },
  { key: 'release-center', to: '/release-center', icon: Rocket, label: '变更发布', group: '观测与治理', order: 220, defaultVisible: false },
  { key: 'sandbox', to: '/sandbox', icon: FlaskConical, label: '沙箱实验', group: '观测与治理', order: 230, defaultVisible: false },
  { key: 'incidents', to: '/incidents', icon: Siren, label: '故障响应', group: '观测与治理', order: 240, defaultVisible: false },
  { key: 'p0', to: '/p0', icon: FileSearch, label: 'P0 模块', group: '内部控制', order: 250, defaultVisible: true },
  { key: 'design-preview', to: '/design-preview', icon: Palette, label: '设计预览', group: '内部控制', order: 255, defaultVisible: false },
]

const routes = [
  { path: '/', element: <AIChat /> },
  { path: '/projects', element: <ProjectManagement /> },
  { path: '/knowledge', element: <KnowledgeDocs /> },
  { path: '/memory', element: <AIMemory /> },
  { path: '/source-onboarding', element: <SourceOnboarding /> },
  { path: '/fabric/source-profiles', element: <FabricSourceProfiles /> },
  { path: '/fabric/update-semantics', element: <FabricUpdateSemantics /> },
  { path: '/fabric/domains', element: <FabricSemanticDomains /> },
  { path: '/fabric/planner', element: <FabricPlanner /> },
  { path: '/fabric/materializations', element: <FabricMaterializations /> },
  { path: '/fabric/telemetry', element: <FabricTelemetry /> },
  { path: '/p0', element: <P0Module /> },
  { path: '/logs', element: <AuditLogs /> },
  { path: '/settings', element: <SettingsPage /> },
  { path: '/pipelines', element: <Pipelines /> },
  { path: '/catalog', element: <DataCatalog /> },
  { path: '/data-quality', element: <DataQuality /> },
  { path: '/scheduler', element: <Scheduler /> },
  { path: '/monitoring', element: <MonitoringAlerts /> },
  { path: '/cost', element: <CostUsageAnalytics /> },
  { path: '/infrastructure', element: <Infrastructure /> },
  { path: '/integration-hub', element: <IntegrationHub /> },
  { path: '/incidents', element: <IncidentResponseCenter /> },
  { path: '/collaboration', element: <CollaborationWorkflowPage /> },
  { path: '/policy-center', element: <PolicyRuleCenterPage /> },
  { path: '/release-center', element: <ReleaseChangeManagement /> },
  { path: '/reports', element: <CustomReportsDashboardBuilder /> },
  { path: '/marketplace', element: <DataProductMarketplace /> },
  { path: '/ingestion', element: <IngestionSdkCenter /> },
  { path: '/sandbox', element: <SandboxExperimentation /> },
  { path: '/design-preview', element: <DesignPreview /> },
]

function defaultSettings(): PlatformSettings {
  return { version: 2, enabledKeys: PLATFORM_MODULES.map((m) => m.key), orderedKeys: PLATFORM_MODULES.slice().sort((a, b) => a.order - b.order).map((m) => m.key) }
}

function readSettings(): PlatformSettings {
  if (typeof window === 'undefined') return defaultSettings()
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return defaultSettings()
    const parsed = JSON.parse(raw) as Partial<PlatformSettings>
    const valid = new Set(PLATFORM_MODULES.map((m) => m.key))
    const enabledKeys = Array.isArray(parsed.enabledKeys) ? parsed.enabledKeys.filter((k): k is string => typeof k === 'string' && valid.has(k)) : defaultSettings().enabledKeys
    const orderedKeys = Array.isArray(parsed.orderedKeys) ? parsed.orderedKeys.filter((k): k is string => typeof k === 'string' && valid.has(k)) : defaultSettings().orderedKeys
    return { version: 2, enabledKeys, orderedKeys: Array.from(new Set([...orderedKeys, ...defaultSettings().orderedKeys])) }
  } catch {
    return defaultSettings()
  }
}

function saveSettings(settings: PlatformSettings) {
  if (typeof window !== 'undefined') window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
}

function pageTitle(pathname: string) {
  const found = PLATFORM_MODULES.find((m) => m.to === pathname)
  if (found) return found.label
  if (pathname === '/') return 'AI 对话'
  if (pathname === '/projects') return '项目管理'
  if (pathname === '/knowledge') return '知识文档'
  if (pathname === '/settings') return '个人设置'
  return 'DataFabric'
}

function moveKey(keys: string[], key: string, dir: 'up' | 'down') {
  const i = keys.indexOf(key)
  if (i < 0) return keys
  if (dir === 'up' && i === 0) return keys
  if (dir === 'down' && i === keys.length - 1) return keys
  const next = [...keys]
  const j = dir === 'up' ? i - 1 : i + 1
  ;[next[i], next[j]] = [next[j], next[i]]
  return next
}

function NavLink({ to, icon: Icon, label }: { to: string; icon: IconType; label: string }) {
  const location = useLocation()
  const active = location.pathname === to
  return <Link to={to} className="flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm transition" style={{ backgroundColor: active ? '#eef2ff' : 'transparent', color: active ? '#111827' : '#475569' }}><Icon size={16} /><span className="truncate font-medium">{label}</span></Link>
}

function RailLink({ item, expanded }: { item: PlatformModule; expanded: boolean }) {
  const location = useLocation()
  const active = location.pathname === item.to
  const Icon = item.icon
  return <Link to={item.to} title={item.label} className={`group flex items-center rounded-2xl border transition ${expanded ? 'h-11 w-full justify-start gap-3 px-4' : 'h-11 w-11 justify-center'}`} style={{ backgroundColor: active ? '#111827' : '#ffffff', color: active ? '#ffffff' : '#475569', borderColor: active ? '#111827' : '#e2e8f0' }}><Icon size={18} />{expanded ? <span className="truncate text-sm font-medium">{item.label}</span> : null}</Link>
}

function ConversationRow({ conversation, active, onDelete }: { conversation: StoredChatConversation; active: boolean; onDelete: (id: string) => void }) {
  return <div className={`group rounded-2xl border px-3 py-3 transition ${active ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-slate-50 text-slate-700'}`}><div className="flex items-start justify-between gap-3"><Link to={`/?conversation=${conversation.id}`} className="min-w-0 flex-1"><div className="truncate text-sm font-medium">{conversation.title || '新对话'}</div><div className={`mt-1 text-xs ${active ? 'text-slate-300' : 'text-slate-500'}`}>{new Date(conversation.updatedAt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</div></Link><button type="button" onClick={() => onDelete(conversation.id)} className={`rounded-lg px-2 py-1 text-xs opacity-0 transition group-hover:opacity-100 ${active ? 'bg-white/10 text-white' : 'bg-slate-200 text-slate-600'}`}>删除</button></div></div>
}

export default function App() {
  const { isLoading, isAuthenticated, user, activeTenant, activeProject, activeProjectId, logout } = useSession()
  const location = useLocation()
  const [conversations, setConversations] = useState<StoredChatConversation[]>([])
  const [conversationQuery, setConversationQuery] = useState('')
  const [confirmedProjectId, setConfirmedProjectIdState] = useState<number | null>(() => getConfirmedProjectId())
  const [profileMenuOpen, setProfileMenuOpen] = useState(false)
  const [platformRailExpanded, setPlatformRailExpanded] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [moduleSearch, setModuleSearch] = useState('')
  const [settings, setSettings] = useState<PlatformSettings>(() => readSettings())
  const projectReady = Boolean(activeProjectId && confirmedProjectId && activeProjectId === confirmedProjectId)
  const isChatPage = location.pathname === '/'

  useEffect(() => {
    const syncConfirmed = () => setConfirmedProjectIdState(getConfirmedProjectId())
    syncConfirmed()
    window.addEventListener('storage', syncConfirmed)
    return () => window.removeEventListener('storage', syncConfirmed)
  }, [])

  useEffect(() => {
    const syncConversations = () => setConversations(projectReady ? listChatConversations(activeProjectId) : [])
    syncConversations()
    window.addEventListener(CHAT_CONVERSATIONS_CHANGED, syncConversations)
    window.addEventListener('storage', syncConversations)
    return () => {
      window.removeEventListener(CHAT_CONVERSATIONS_CHANGED, syncConversations)
      window.removeEventListener('storage', syncConversations)
    }
  }, [activeProjectId, projectReady])

  const currentConversationId = useMemo(() => new URLSearchParams(location.search).get('conversation'), [location.search])
  const filteredConversations = useMemo(() => {
    const q = conversationQuery.trim().toLowerCase()
    const source = q ? conversations.filter((item) => item.title.toLowerCase().includes(q)) : conversations
    return source.slice(0, 10)
  }, [conversationQuery, conversations])
  const moduleMap = useMemo(() => new Map(PLATFORM_MODULES.map((m) => [m.key, m])), [])
  const orderedModules = useMemo(() => settings.orderedKeys.map((key) => moduleMap.get(key)).filter((item): item is PlatformModule => Boolean(item)), [settings.orderedKeys, moduleMap])
  const enabledModules = useMemo(() => {
    const enabled = new Set(settings.enabledKeys)
    return orderedModules.filter((item) => enabled.has(item.key))
  }, [orderedModules, settings.enabledKeys])
  const collapsedModules = useMemo(() => enabledModules.filter((item) => item.defaultVisible), [enabledModules])
  const expandedGroups = useMemo(() => GROUPS.map((group) => ({ group, items: enabledModules.filter((item) => item.group === group) })).filter((group) => group.items.length > 0), [enabledModules])
  const drawerGroups = useMemo(() => {
    const q = moduleSearch.trim().toLowerCase()
    return GROUPS.map((group) => ({
      group,
      items: orderedModules.filter((item) => item.group === group && (!q || item.label.toLowerCase().includes(q))),
    })).filter((group) => group.items.length > 0)
  }, [moduleSearch, orderedModules])

  const updateSettings = (updater: (current: PlatformSettings) => PlatformSettings) =>
    setSettings((current) => {
      const next = updater(current)
      saveSettings(next)
      return next
    })

  const handleLogout = () => {
    setConfirmedProjectId(null)
    logout()
  }

  if (isLoading) return <div className="flex min-h-screen items-center justify-center bg-[#eef2f7]"><div className="h-10 w-10 animate-spin rounded-full border-4 border-slate-900 border-t-transparent" /></div>
  if (!isAuthenticated) return <Routes><Route path="*" element={<Login />} /></Routes>
  if (!activeTenant || !activeProject) return <div className="flex min-h-screen items-center justify-center bg-[#f8fafc] text-slate-600">当前没有可用项目，请先初始化租户和项目上下文。</div>

  return (
    <div className="h-screen overflow-hidden bg-[#eef2f7] text-slate-900">
      <div className="flex h-full">
        <aside className="flex h-full w-[300px] shrink-0 flex-col border-r border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-5 py-5">
            <div className="text-[11px] font-semibold uppercase tracking-[0.26em] text-indigo-600">DataFabric</div>
            <div className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">DataFabric</div>
            <div className="mt-1 text-sm text-slate-500">面向离线数据重构的智能数据操作系统</div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
            <div className="mb-8">
              <div className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">会话区</div>
              <Link to={projectReady ? '/' : '/projects'} className={`flex items-center justify-center gap-2 rounded-2xl px-4 py-3 text-sm font-semibold transition ${projectReady ? 'bg-indigo-600 text-white hover:bg-indigo-500' : 'bg-slate-200 text-slate-700 hover:bg-slate-300'}`}>
                <MessageSquarePlus size={16} />
                新建对话
              </Link>
              <div className="relative mt-4">
                <Search size={16} className="absolute left-3 top-3 text-slate-400" />
                <input value={conversationQuery} onChange={(event) => setConversationQuery(event.target.value)} placeholder="搜索会话" className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-9 py-2.5 text-sm text-slate-700 outline-none" disabled={!projectReady} />
              </div>
              {!projectReady ? (
                <div className="mt-4 rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-sm leading-6 text-slate-500">请先到“项目管理”中确认一个项目，然后再创建和保存对话。</div>
              ) : filteredConversations.length === 0 ? (
                <div className="mt-4 rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-sm leading-6 text-slate-500">当前项目还没有保存的会话。</div>
              ) : (
                <div className="mt-4 space-y-3">
                  {filteredConversations.map((conversation) => <ConversationRow key={conversation.id} conversation={conversation} active={conversation.id === currentConversationId} onDelete={deleteChatConversation} />)}
                  {conversations.length > 10 ? <div className="text-xs text-slate-400">默认展示最近 10 条会话，可通过搜索定位更多结果。</div> : null}
                </div>
              )}
            </div>
            <div>
              <div className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">工作区</div>
              <div className="space-y-1.5">
                {WORKSPACE_ITEMS.map((item) => <NavLink key={item.to} to={item.to} icon={item.icon} label={item.label} />)}
              </div>
            </div>
          </div>
          <div className="relative border-t border-slate-200 p-4">
            <button type="button" onClick={() => setProfileMenuOpen((value) => !value)} className="flex w-full items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-left transition hover:bg-slate-100">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-900 text-sm font-semibold text-white">{(user?.name || user?.email || 'U').slice(0, 1).toUpperCase()}</div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold text-slate-900">{user?.name || '未命名用户'}</div>
                <div className="truncate text-xs text-slate-500">{user?.email}</div>
              </div>
              <ChevronDown size={16} className="text-slate-500" />
            </button>
            {profileMenuOpen ? <div className="absolute bottom-[82px] left-4 right-4 z-30 rounded-2xl border border-slate-200 bg-white p-2 shadow-xl"><Link to="/settings" onClick={() => setProfileMenuOpen(false)} className="flex items-center gap-3 rounded-xl px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"><Settings size={16} />个人设置</Link><button type="button" onClick={handleLogout} className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm text-rose-600 hover:bg-rose-50"><LogOut size={16} />退出登录</button></div> : null}
          </div>
        </aside>

        <main className="min-w-0 flex-1 overflow-hidden">
          <div className="h-full overflow-y-auto px-8 py-8">
            {!isChatPage ? (
              <div className="mb-6 flex items-start justify-between gap-6">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">{pageTitle(location.pathname)}</div>
                  <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">{pageTitle(location.pathname)}</h1>
                  <div className="mt-2 text-sm text-slate-500">{activeProject.name} / {activeTenant.name}</div>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 shadow-sm">
                  <div className="font-medium text-slate-900">当前项目</div>
                  <div className="mt-1">{activeProject.name}</div>
                </div>
              </div>
            ) : null}
            <Routes>
              {routes.map((item) => <Route key={item.path} path={item.path} element={item.element} />)}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </div>
        </main>

        <aside className={`relative h-full shrink-0 border-l border-slate-200 bg-white/90 backdrop-blur transition-all ${platformRailExpanded ? 'w-[280px]' : 'w-[76px]'}`} onMouseEnter={() => setPlatformRailExpanded(true)} onMouseLeave={() => setPlatformRailExpanded(false)}>
          <div className="flex h-full flex-col">
            <div className="flex items-center justify-between gap-2 border-b border-slate-200 px-4 py-4">
              {platformRailExpanded ? <div><div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">平台能力</div><div className="mt-1 text-sm text-slate-600">按分组查看全部功能模块</div></div> : <div className="w-8" />}
              <button type="button" onClick={() => setDrawerOpen(true)} className="flex h-10 w-10 items-center justify-center rounded-2xl border border-slate-200 bg-white text-slate-600 hover:bg-slate-50" title="编辑平台能力">
                <Pencil size={16} />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
              {platformRailExpanded ? (
                <div className="space-y-5">
                  {expandedGroups.map((section) => (
                    <div key={section.group} className="space-y-2">
                      <div className="sticky top-0 rounded-xl bg-white/95 px-2 py-1 text-xs font-semibold tracking-[0.18em] text-slate-400 backdrop-blur">{section.group}</div>
                      <div className="space-y-2">{section.items.map((item) => <RailLink key={item.key} item={item} expanded />)}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="space-y-3">{collapsedModules.map((item) => <RailLink key={item.key} item={item} expanded={false} />)}</div>
              )}
            </div>
          </div>

          {drawerOpen ? (
            <div className="absolute inset-y-0 right-0 z-40 w-[380px] border-l border-slate-200 bg-white shadow-2xl">
              <div className="flex h-full flex-col">
                <div className="border-b border-slate-200 px-5 py-5">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">平台能力</div>
                      <div className="mt-2 text-xl font-semibold tracking-tight text-slate-900">编辑模块显示</div>
                      <div className="mt-1 text-sm text-slate-500">支持搜索、分组开关、排序和恢复默认。</div>
                    </div>
                    <button type="button" onClick={() => setDrawerOpen(false)} className="rounded-2xl border border-slate-200 p-2 text-slate-500 hover:bg-slate-50"><X size={16} /></button>
                  </div>
                  <div className="relative mt-4">
                    <Search size={15} className="absolute left-3 top-3 text-slate-400" />
                    <input value={moduleSearch} onChange={(event) => setModuleSearch(event.target.value)} placeholder="搜索模块名称" className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-9 py-2.5 text-sm text-slate-700 outline-none" />
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button type="button" onClick={() => updateSettings(() => defaultSettings())} className="rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50">恢复默认</button>
                    <button type="button" onClick={() => updateSettings((current) => ({ ...current, enabledKeys: PLATFORM_MODULES.map((m) => m.key) }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50">全部显示</button>
                    <button type="button" onClick={() => updateSettings((current) => ({ ...current, enabledKeys: [] }))} className="rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50">全部隐藏</button>
                    <button type="button" onClick={() => setDrawerOpen(false)} className="rounded-xl bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800">保存</button>
                  </div>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
                  <div className="space-y-5">
                    {drawerGroups.map((section) => {
                      const sectionKeys = section.items.map((item) => item.key)
                      const allChecked = sectionKeys.every((key) => settings.enabledKeys.includes(key))
                      return (
                        <div key={section.group} className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
                          <div className="flex items-center justify-between gap-3">
                            <div><div className="text-sm font-semibold text-slate-900">{section.group}</div><div className="mt-1 text-xs text-slate-500">{section.items.length} 个模块</div></div>
                            <button type="button" onClick={() => updateSettings((current) => { const enabled = new Set(current.enabledKeys); if (allChecked) sectionKeys.forEach((key) => enabled.delete(key)); else sectionKeys.forEach((key) => enabled.add(key)); return { ...current, enabledKeys: Array.from(enabled) } })} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-100">{allChecked ? '本组全隐藏' : '本组全显示'}</button>
                          </div>
                          <div className="mt-4 space-y-2">
                            {section.items.map((item) => {
                              const enabled = settings.enabledKeys.includes(item.key)
                              return (
                                <div key={item.key} className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-3 py-3">
                                  <item.icon size={16} className="text-slate-500" />
                                  <div className="min-w-0 flex-1"><div className="truncate text-sm font-medium text-slate-900">{item.label}</div><div className="truncate text-xs text-slate-500">{item.group}</div></div>
                                  <label className="flex items-center gap-2 text-xs text-slate-500"><span>{enabled ? '显示' : '隐藏'}</span><input type="checkbox" checked={enabled} onChange={(event) => updateSettings((current) => ({ ...current, enabledKeys: event.target.checked ? Array.from(new Set([...current.enabledKeys, item.key])) : current.enabledKeys.filter((key) => key !== item.key) }))} /></label>
                                  <div className="flex items-center gap-1">
                                    <button type="button" onClick={() => updateSettings((current) => ({ ...current, orderedKeys: moveKey(current.orderedKeys, item.key, 'up') }))} className="rounded-lg border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50">上移</button>
                                    <button type="button" onClick={() => updateSettings((current) => ({ ...current, orderedKeys: moveKey(current.orderedKeys, item.key, 'down') }))} className="rounded-lg border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50">下移</button>
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </aside>
      </div>
    </div>
  )
}
