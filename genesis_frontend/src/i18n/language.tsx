import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type Locale = 'zh-CN' | 'en-US'

const STORAGE_KEY = 'genesis_language_v1'
const DEFAULT_LOCALE: Locale = 'zh-CN'

const messages: Record<Locale, Record<string, string>> = {
  'zh-CN': {
    'app.brand': '控制平面',
    'app.noProject': '当前账号没有可用项目。',
    'app.tenant': '租户',
    'app.project': '项目',
    'app.logout': '退出登录',
    'app.loading': '加载中...',
    'app.placeholder': '页面建设中...',
    'nav.overview': '总览',
    'nav.governance': '治理',
    'nav.policy': '策略中心',
    'nav.release': '发布中心',
    'nav.reports': '自定义报表',
    'nav.marketplace': '数据市场',
    'nav.ingestion': '接入 SDK',
    'nav.events': '事件',
    'nav.catalog': '数据目录',
    'nav.dataQuality': '数据质量',
    'nav.explore': '探索',
    'nav.infrastructure': '基础设施',
    'nav.integrationHub': '集成中心',
    'nav.access': '权限',
    'nav.monitoring': '监控',
    'nav.incidents': '事故响应',
    'nav.collaboration': '协作',
    'nav.knowledge': '知识库',
    'nav.cost': '成本用量',
    'nav.sandbox': '沙箱',
    'nav.scheduler': '调度',
    'nav.pipelines': 'Pipelines',
    'nav.logs': '审计日志',
    'nav.settings': '设置',
    'login.title': '租户访问',
    'login.loginDesc': '登录后加载你的租户与项目工作区。',
    'login.registerDesc': '创建账号并加入默认租户工作区。',
    'login.login': '登录',
    'login.register': '注册',
    'login.name': '姓名',
    'login.email': '邮箱',
    'login.password': '密码',
    'login.confirmPassword': '确认密码',
    'login.signingIn': '登录中...',
    'login.creating': '创建账号中...',
    'login.defaultDemo': '默认演示账号：admin@demo.local / demo123456',
    'login.passwordMismatch': '两次密码不一致',
    'login.authFailed': '认证失败',
    'settings.languageTitle': '显示语言',
    'settings.languageDesc': '切换界面语言（中文 / English），会在本地浏览器保存。',
    'settings.languageLabel': '语言',
    'settings.tab.general': '通用',
    'settings.tab.members': '成员',
    'settings.tab.integrations': '集成',
    'settings.tab.security': '安全',
    'settings.header': '设置',
  },
  'en-US': {
    'app.brand': 'Control Plane',
    'app.noProject': 'No project is available for this account.',
    'app.tenant': 'Tenant',
    'app.project': 'Project',
    'app.logout': 'Log out',
    'app.loading': 'Loading...',
    'app.placeholder': 'Page under construction...',
    'nav.overview': 'Overview',
    'nav.governance': 'Governance',
    'nav.policy': 'Policy Center',
    'nav.release': 'Release Center',
    'nav.reports': 'Custom Reports',
    'nav.marketplace': 'Marketplace',
    'nav.ingestion': 'Ingestion SDK',
    'nav.events': 'Events',
    'nav.catalog': 'Data Catalog',
    'nav.dataQuality': 'Data Quality',
    'nav.explore': 'Explore',
    'nav.infrastructure': 'Infrastructure',
    'nav.integrationHub': 'Integration Hub',
    'nav.access': 'Access',
    'nav.monitoring': 'Monitoring',
    'nav.incidents': 'Incidents',
    'nav.collaboration': 'Collaboration',
    'nav.knowledge': 'Knowledge Docs',
    'nav.cost': 'Cost Usage',
    'nav.sandbox': 'Sandbox',
    'nav.scheduler': 'Scheduler',
    'nav.pipelines': 'Pipelines',
    'nav.logs': 'Audit Logs',
    'nav.settings': 'Settings',
    'login.title': 'Tenant Access',
    'login.loginDesc': 'Login to load your tenant and project workspace.',
    'login.registerDesc': 'Create an account and join the default tenant workspace.',
    'login.login': 'Login',
    'login.register': 'Register',
    'login.name': 'Name',
    'login.email': 'Email',
    'login.password': 'Password',
    'login.confirmPassword': 'Confirm Password',
    'login.signingIn': 'Signing in...',
    'login.creating': 'Creating account...',
    'login.defaultDemo': 'Default demo account: admin@demo.local / demo123456',
    'login.passwordMismatch': 'Passwords do not match',
    'login.authFailed': 'Authentication failed',
    'settings.languageTitle': 'Display Language',
    'settings.languageDesc': 'Switch UI language (Chinese / English). Saved in browser local storage.',
    'settings.languageLabel': 'Language',
    'settings.tab.general': 'General',
    'settings.tab.members': 'Members',
    'settings.tab.integrations': 'Integrations',
    'settings.tab.security': 'Security',
    'settings.header': 'Settings',
  },
}

const AUTO_ZH_MAP: Record<string, string> = {
  'Business Overview': '业务总览',
  'Core Flow': '核心流程',
  'Advanced': '高级模块',
  'Event Catalog': '事件目录',
  'Pipelines Console': '管道控制台',
  'Data Quality': '数据质量',
  'Monitoring & Alerts': '监控与告警',
  'Cost & Usage Analytics': '成本与用量分析',
  'Integration Hub': '集成中心',
  'Governance Workbench': '治理工作台',
  'Recent Activity': '最近活动',
  'Unhandled Alerts': '未处理告警',
  'High-Risk Events': '高风险事件',
  'Unhealthy Pipelines': '异常管道',
  'No open todo items.': '暂无待办事项。',
  'Failed to load event catalog': '加载事件目录失败',
  'Failed to load pipelines': '加载管道失败',
  'Failed to load data quality rules': '加载数据质量规则失败',
  'Failed to load rule detail': '加载规则详情失败',
  'Failed to load monitoring overview': '加载监控总览失败',
  'Failed to load alerts': '加载告警列表失败',
  'Failed to load alert detail': '加载告警详情失败',
  'Failed to load cost usage overview': '加载成本总览失败',
  'Failed to load resource costs': '加载资源成本失败',
  'Failed to load resource detail': '加载资源详情失败',

  Refresh: '刷新',
  Apply: '应用',
  'Apply Filters': '应用筛选',
  Create: '创建',
  Save: '保存',
  Publish: '发布',
  Archive: '归档',
  Unarchive: '取消归档',
  Approve: '批准',
  Reject: '拒绝',
  Cancel: '取消',
  Revoke: '撤销',
  Prev: '上一页',
  Next: '下一页',
  Export: '导出',
  'Export CSV': '导出 CSV',
  'Export JSON': '导出 JSON',
  'Loading...': '加载中...',
  'Loading detail...': '详情加载中...',
  'Loading logs...': '日志加载中...',
  'Loading settings...': '设置加载中...',
  'No data.': '暂无数据。',
  'No recent activity.': '暂无最近活动。',
  'No products found.': '未找到产品。',
  'No incidents found.': '未找到事故。',
  'No timeline entries.': '暂无时间线记录。',
  'No logs matched current filters.': '当前筛选条件下无日志。',
  'Select one incident to view details.': '请选择一个事故查看详情。',
  'Select one product to view details.': '请选择一个产品查看详情。',
  'Open Related Module': '打开相关模块',
  'Project Name': '项目名称',
  Description: '描述',
  'Default Domain': '默认域',
  'Tags (comma separated)': '标签（逗号分隔）',
  'Save General': '保存通用设置',
  'Invite Member': '邀请成员',
  Invite: '邀请',
  Members: '成员',
  'Pending Invitations': '待处理邀请',
  'No pending invitations.': '暂无待处理邀请。',
  Enabled: '启用',
  Test: '测试',
  'Save Security': '保存安全设置',
  'SSO Enabled': '启用 SSO',
  'MFA Required': '强制 MFA',
  'Password Min Length': '密码最小长度',
  'Audit Retention Days': '审计保留天数',
  Upper: '大写字母',
  Lower: '小写字母',
  Number: '数字',
  Symbol: '符号',
  'Audit Export Requires Approval': '审计导出需审批',
  'Max Exports / Day': '每日最大导出次数',
  Settings: '设置',
  'Audit Logs': '审计日志',
  'Data Product Marketplace': '数据产品市场',
  'Incident Response & Runbook Center': '事故响应与 Runbook 中心',
  Overview: '总览',
  Risks: '风险',
  Todos: '待办事项',
  total: '总计',
  offset: '偏移',
  Time: '时间',
  Action: '动作',
  Target: '目标',
  User: '用户',
  Status: '状态',
  Summary: '摘要',
  Context: '上下文',
  'Key Fields': '关键字段',
  'Operation Details': '操作详情',
  Diff: '变更差异',
}

const AUTO_EN_MAP: Record<string, string> = Object.fromEntries(
  Object.entries(AUTO_ZH_MAP).map(([en, zh]) => [zh, en]),
)

const textOriginalMap = new WeakMap<Text, string>()
const attrOriginalMap = new WeakMap<Element, Map<string, string>>()

interface LanguageContextValue {
  locale: Locale
  setLocale: (next: Locale) => void
  t: (key: string) => string
}

const LanguageContext = createContext<LanguageContextValue | null>(null)

function resolveInitialLocale(): Locale {
  if (typeof window === 'undefined') {
    return DEFAULT_LOCALE
  }
  const saved = window.localStorage.getItem(STORAGE_KEY)
  if (saved === 'zh-CN' || saved === 'en-US') {
    return saved
  }
  return DEFAULT_LOCALE
}

function translateToZh(raw: string): string {
  const trimmed = raw.trim()
  if (!trimmed) return raw

  let next = AUTO_ZH_MAP[trimmed] ?? trimmed
  next = next
    .replace(/^(\d+)\s+items$/i, '$1 条')
    .replace(/^(\d+)\s+logs$/i, '$1 条日志')
    .replace(/^Loading\s+(.+)\.\.\.$/i, '加载 $1 中...')
    .replace(/^No\s+(.+)\.$/i, '暂无$1。')

  if (next === trimmed) return raw
  const leading = raw.match(/^\s*/)?.[0] ?? ''
  const trailing = raw.match(/\s*$/)?.[0] ?? ''
  return leading + next + trailing
}

function translateToEn(raw: string): string {
  const trimmed = raw.trim()
  if (!trimmed) return raw

  const next = AUTO_EN_MAP[trimmed] ?? trimmed
  if (next === trimmed) return raw
  const leading = raw.match(/^\s*/)?.[0] ?? ''
  const trailing = raw.match(/\s*$/)?.[0] ?? ''
  return leading + next + trailing
}

function translateLoose(raw: string, locale: Locale): string {
  return locale === 'zh-CN' ? translateToZh(raw) : translateToEn(raw)
}

function shouldSkipTextNode(node: Text): boolean {
  const parent = node.parentElement
  if (!parent) {
    return true
  }
  if (parent.closest('script,style,pre,code')) {
    return true
  }
  return false
}

function localizeTextNode(node: Text, locale: Locale) {
  if (shouldSkipTextNode(node)) {
    return
  }
  if (!textOriginalMap.has(node)) {
    textOriginalMap.set(node, node.nodeValue ?? '')
  }
  const original = textOriginalMap.get(node) ?? ''
  const next = translateLoose(original, locale)
  if (node.nodeValue !== next) {
    node.nodeValue = next
  }
}

function localizeElementAttrs(el: Element, locale: Locale) {
  const attrs = ['placeholder', 'title', 'aria-label']
  let originalMap = attrOriginalMap.get(el)
  if (!originalMap) {
    originalMap = new Map<string, string>()
    attrOriginalMap.set(el, originalMap)
  }

  for (const attr of attrs) {
    const current = el.getAttribute(attr)
    if (current == null) {
      continue
    }
    if (!originalMap.has(attr)) {
      originalMap.set(attr, current)
    }
    const original = originalMap.get(attr) ?? current
    const next = translateLoose(original, locale)
    if (next !== current) {
      el.setAttribute(attr, next)
    }
  }

  if (el instanceof HTMLInputElement) {
    if (el.type === 'button' || el.type === 'submit' || el.type === 'reset') {
      if (!originalMap.has('value')) {
        originalMap.set('value', el.value)
      }
      const original = originalMap.get('value') ?? el.value
      const next = translateLoose(original, locale)
      if (el.value !== next) {
        el.value = next
      }
    }
  }
}

function localizeDom(locale: Locale) {
  if (typeof document === 'undefined') {
    return
  }
  const root = document.body
  if (!root) {
    return
  }

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  let textNode = walker.nextNode()
  while (textNode) {
    localizeTextNode(textNode as Text, locale)
    textNode = walker.nextNode()
  }

  localizeElementAttrs(root, locale)
  const elements = root.querySelectorAll('*')
  for (const el of elements) {
    localizeElementAttrs(el, locale)
  }
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(resolveInitialLocale)

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, locale)
    document.documentElement.lang = locale
  }, [locale])

  // NOTE: disable DOM mutation based auto-translation to avoid mixed-language residual artifacts.
  // Keep locale switching via explicit i18n keys/components only.
  useEffect(() => {
    // keep helper symbol referenced for strict TS, but do not mutate DOM to avoid mixed-language residue.
    void localizeDom
    return
  }, [locale])

  const value = useMemo<LanguageContextValue>(
    () => ({
      locale,
      setLocale: setLocaleState,
      t: (key: string) => messages[locale][key] ?? messages['en-US'][key] ?? key,
    }),
    [locale],
  )

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

export function useLanguage() {
  const context = useContext(LanguageContext)
  if (!context) {
    throw new Error('useLanguage must be used inside LanguageProvider')
  }
  return context
}

