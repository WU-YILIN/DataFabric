import { FormEvent, useState } from 'react'
import { Loader2, Lock, Mail, User } from 'lucide-react'

import { useSession } from '../auth/session'

type AuthMode = 'login' | 'register'

const Login = () => {
  const { login, register } = useSession()
  const [mode, setMode] = useState<AuthMode>('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('admin@demo.local')
  const [password, setPassword] = useState('demo123456')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    try {
      if (mode === 'login') {
        await login(email, password)
      } else {
        if (password !== confirmPassword) {
          window.alert('两次输入的密码不一致。')
          return
        }
        await register({ email, password, name })
      }
    } catch (err: any) {
      if (!err?.response) {
        window.alert(err?.message ?? '认证失败。')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen w-screen items-center justify-center bg-gradient-to-br from-slate-100 via-cyan-50 to-emerald-100 p-6">
      <div className="glass w-full max-w-md rounded-3xl p-8 shadow-xl">
        <div className="mb-6 text-center">
          <p className="text-sm uppercase tracking-[0.22em] text-slate-500">DataFabric</p>
          <h1 className="mt-2 text-3xl font-bold text-slate-900">工作区登录</h1>
          <p className="mt-2 text-sm text-slate-600">
            {mode === 'login' ? '登录后加载当前项目工作区。' : '创建账号并初始化你的工作区。'}
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
            登录
          </button>
          <button
            className={`rounded-lg py-2 text-sm font-semibold ${
              mode === 'register' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500'
            }`}
            onClick={() => setMode('register')}
            type="button"
          >
            注册
          </button>
        </div>

        <form className="space-y-4" onSubmit={onSubmit}>
          {mode === 'register' ? (
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-slate-700">名称</span>
              <div className="relative">
                <User className="pointer-events-none absolute left-3 top-3 text-slate-400" size={16} />
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-10 pr-3 outline-none ring-cyan-400/40 focus:ring-2"
                  required
                />
              </div>
            </label>
          ) : null}

          <label className="block">
            <span className="mb-1 block text-sm font-medium text-slate-700">邮箱</span>
            <div className="relative">
              <Mail className="pointer-events-none absolute left-3 top-3 text-slate-400" size={16} />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-10 pr-3 outline-none ring-cyan-400/40 focus:ring-2"
                required
              />
            </div>
          </label>

          <label className="block">
            <span className="mb-1 block text-sm font-medium text-slate-700">密码</span>
            <div className="relative">
              <Lock className="pointer-events-none absolute left-3 top-3 text-slate-400" size={16} />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-10 pr-3 outline-none ring-cyan-400/40 focus:ring-2"
                required
              />
            </div>
          </label>

          {mode === 'register' ? (
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-slate-700">确认密码</span>
              <div className="relative">
                <Lock className="pointer-events-none absolute left-3 top-3 text-slate-400" size={16} />
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-10 pr-3 outline-none ring-cyan-400/40 focus:ring-2"
                  required
                />
              </div>
            </label>
          ) : null}

          <button
            type="submit"
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-600 py-2.5 font-semibold text-white transition hover:bg-cyan-500 disabled:opacity-70"
          >
            {loading ? (
              <>
                <Loader2 className="animate-spin" size={16} />
                {mode === 'login' ? '登录中...' : '创建账号中...'}
              </>
            ) : mode === 'login' ? (
              '登录'
            ) : (
              '注册'
            )}
          </button>
        </form>

        <p className="mt-4 text-center text-xs text-slate-500">
          演示账号：admin@demo.local / demo123456
        </p>
      </div>
    </div>
  )
}

export default Login
