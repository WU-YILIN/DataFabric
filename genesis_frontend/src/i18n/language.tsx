import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type Locale = 'zh-CN' | 'en-US'

const STORAGE_KEY = 'genesis_language_v1'
const DEFAULT_LOCALE: Locale = 'zh-CN'

const messages: Record<Locale, Record<string, string>> = {
  'zh-CN': {
    'app.brand': '控制平台',
    'app.noProject': '当前账号没有可用项目。',
    'app.tenant': '租户',
    'app.project': '项目',
    'app.logout': '退出登录',
    'app.loading': '加载中...',
    'app.placeholder': '页面建设中...',
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
    'settings.languageDesc': '在这里切换全局界面语言。语言设置会保存在当前浏览器中。',
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
    'settings.languageDesc': 'Switch the global UI language here. The selection is saved in this browser.',
    'settings.languageLabel': 'Language',
    'settings.tab.general': 'General',
    'settings.tab.members': 'Members',
    'settings.tab.integrations': 'Integrations',
    'settings.tab.security': 'Security',
    'settings.header': 'Settings',
  },
}

interface LanguageContextValue {
  locale: Locale
  setLocale: (next: Locale) => void
  t: (key: string) => string
}

const LanguageContext = createContext<LanguageContextValue | null>(null)

function resolveInitialLocale(): Locale {
  if (typeof window === 'undefined') return DEFAULT_LOCALE
  const saved = window.localStorage.getItem(STORAGE_KEY)
  if (saved === 'zh-CN' || saved === 'en-US') return saved
  return DEFAULT_LOCALE
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(resolveInitialLocale)

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, locale)
    document.documentElement.lang = locale
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
