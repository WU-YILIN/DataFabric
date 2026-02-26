import { FormEvent, useState } from 'react'
import { AlertCircle, Loader2, Lock, Mail, User } from 'lucide-react'

import { useSession } from '../auth/session'
import { useLanguage } from '../i18n/language'

type AuthMode = 'login' | 'register'

const Login = () => {
  const { login, register } = useSession()
  const { t } = useLanguage()
  const [mode, setMode] = useState<AuthMode>('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('admin@demo.local')
  const [password, setPassword] = useState('demo123456')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError(null)
    try {
      if (mode === 'login') {
        await login(email, password)
      } else {
        if (password !== confirmPassword) {
          throw new Error(t('login.passwordMismatch'))
        }
        await register({ email, password, name })
      }
    } catch (err: any) {
      setError(err?.response?.data?.message ?? err?.message ?? t('login.authFailed'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen w-screen bg-gradient-to-br from-slate-100 via-cyan-50 to-emerald-100 flex items-center justify-center p-6">
      <div className="w-full max-w-md glass rounded-3xl p-8 shadow-xl">
        <div className="mb-6 text-center">
          <p className="text-sm uppercase tracking-[0.22em] text-slate-500">Genesis</p>
          <h1 className="mt-2 text-3xl font-bold text-slate-900">{t('login.title')}</h1>
          <p className="mt-2 text-sm text-slate-600">
            {mode === 'login'
              ? t('login.loginDesc')
              : t('login.registerDesc')}
          </p>
        </div>

        <div className="mb-5 grid grid-cols-2 rounded-xl bg-slate-100 p-1">
          <button
            className={`rounded-lg py-2 text-sm font-semibold ${
              mode === 'login' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500'
            }`}
            onClick={() => setMode('login')}
            type="button"
          >
            {t('login.login')}
          </button>
          <button
            className={`rounded-lg py-2 text-sm font-semibold ${
              mode === 'register' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500'
            }`}
            onClick={() => setMode('register')}
            type="button"
          >
            {t('login.register')}
          </button>
        </div>

        <form className="space-y-4" onSubmit={onSubmit}>
          {mode === 'register' && (
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-slate-700">{t('login.name')}</span>
              <div className="relative">
                <User className="pointer-events-none absolute left-3 top-3 text-slate-400" size={16} />
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 bg-white pl-10 pr-3 py-2.5 outline-none ring-cyan-400/40 focus:ring-2"
                  required
                />
              </div>
            </label>
          )}

          <label className="block">
            <span className="mb-1 block text-sm font-medium text-slate-700">{t('login.email')}</span>
            <div className="relative">
              <Mail className="pointer-events-none absolute left-3 top-3 text-slate-400" size={16} />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-xl border border-slate-200 bg-white pl-10 pr-3 py-2.5 outline-none ring-cyan-400/40 focus:ring-2"
                required
              />
            </div>
          </label>

          <label className="block">
            <span className="mb-1 block text-sm font-medium text-slate-700">{t('login.password')}</span>
            <div className="relative">
              <Lock className="pointer-events-none absolute left-3 top-3 text-slate-400" size={16} />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-xl border border-slate-200 bg-white pl-10 pr-3 py-2.5 outline-none ring-cyan-400/40 focus:ring-2"
                required
              />
            </div>
          </label>

          {mode === 'register' && (
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-slate-700">{t('login.confirmPassword')}</span>
              <div className="relative">
                <Lock className="pointer-events-none absolute left-3 top-3 text-slate-400" size={16} />
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 bg-white pl-10 pr-3 py-2.5 outline-none ring-cyan-400/40 focus:ring-2"
                  required
                />
              </div>
            </label>
          )}

          {error && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 flex items-start gap-2">
              <AlertCircle size={16} className="mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-cyan-600 py-2.5 font-semibold text-white transition hover:bg-cyan-500 disabled:opacity-70 flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="animate-spin" size={16} />
                {mode === 'login' ? t('login.signingIn') : t('login.creating')}
              </>
            ) : mode === 'login' ? (
              t('login.login')
            ) : (
              t('login.register')
            )}
          </button>
        </form>

        <p className="mt-4 text-xs text-slate-500 text-center">
          {t('login.defaultDemo')}
        </p>
      </div>
    </div>
  )
}

export default Login
