import { useMemo, useState } from 'react'
import { Activity, DatabaseBackup, PlayCircle, RotateCcw, ShieldCheck, TimerReset } from 'lucide-react'
import { useLanguage } from '../i18n/language'

type JobItem = {
  id: string
  name: string
  status: 'RUNNING' | 'FAILED' | 'RESTARTING'
  lastCk: string
  lastSavepoint: string
  lag: string
}

const seed: JobItem[] = [
  {
    id: 'job-001',
    name: 'flink_order_paid_agg',
    status: 'RUNNING',
    lastCk: '11:56:22',
    lastSavepoint: '11:45:10',
    lag: '120 ms',
  },
  {
    id: 'job-002',
    name: 'flink_payment_risk_detector',
    status: 'FAILED',
    lastCk: '11:40:08',
    lastSavepoint: '11:32:41',
    lag: 'N/A',
  },
]

const FlinkRuntimeOps = () => {
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'

  const [jobs, setJobs] = useState<JobItem[]>(seed)
  const [message, setMessage] = useState('')

  const running = useMemo(() => jobs.filter((j) => j.status === 'RUNNING').length, [jobs])
  const failed = useMemo(() => jobs.filter((j) => j.status === 'FAILED').length, [jobs])

  const triggerCheckpoint = (id: string) => {
    setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, lastCk: new Date().toLocaleTimeString() } : j)))
    setMessage(isZh ? `已触发 Checkpoint：${id}` : `Checkpoint triggered: ${id}`)
  }

  const triggerSavepoint = (id: string) => {
    setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, lastSavepoint: new Date().toLocaleTimeString() } : j)))
    setMessage(isZh ? `已触发 Savepoint：${id}` : `Savepoint triggered: ${id}`)
  }

  const restartJob = (id: string) => {
    setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, status: 'RESTARTING' } : j)))
    setTimeout(() => {
      setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, status: 'RUNNING', lag: '180 ms' } : j)))
      setMessage(isZh ? `任务已恢复运行：${id}` : `Job recovered: ${id}`)
    }, 900)
  }

  return (
    <div className="space-y-5 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <header className="rounded-2xl border border-slate-200 bg-white/80 p-5">
        <h2 className="text-2xl font-bold text-slate-900">{isZh ? 'Flink 任务运维台' : 'Flink Runtime Ops'}</h2>
        <p className="mt-1 text-sm text-slate-600">
          {isZh
            ? '统一管理任务状态、Checkpoint、Savepoint 与恢复动作。'
            : 'Unified control for job status, checkpoints, savepoints, and recovery actions.'}
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="text-xs text-slate-500">{isZh ? '运行中任务' : 'Running Jobs'}</div>
          <div className="mt-1 text-2xl font-bold text-emerald-700">{running}</div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="text-xs text-slate-500">{isZh ? '失败任务' : 'Failed Jobs'}</div>
          <div className="mt-1 text-2xl font-bold text-rose-700">{failed}</div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="text-xs text-slate-500">{isZh ? '最近操作' : 'Last Action'}</div>
          <div className="mt-1 text-sm font-semibold text-slate-900">{message || '-'}</div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="text-xs text-slate-500">{isZh ? '模块状态' : 'Module Status'}</div>
          <div className="mt-1 inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-1 text-xs font-semibold text-emerald-700">
            <ShieldCheck size={12} /> {isZh ? '可用' : 'Ready'}
          </div>
        </div>
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 overflow-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-2">{isZh ? '任务' : 'Job'}</th>
              <th className="py-2">{isZh ? '状态' : 'Status'}</th>
              <th className="py-2">Checkpoint</th>
              <th className="py-2">Savepoint</th>
              <th className="py-2">{isZh ? '延迟' : 'Lag'}</th>
              <th className="py-2">{isZh ? '操作' : 'Actions'}</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id} className="border-b border-slate-100">
                <td className="py-2 font-medium text-slate-900">{j.name}</td>
                <td className="py-2">
                  <span className={`rounded-full px-2 py-1 text-xs font-semibold ${
                    j.status === 'RUNNING'
                      ? 'bg-emerald-100 text-emerald-700'
                      : j.status === 'FAILED'
                        ? 'bg-rose-100 text-rose-700'
                        : 'bg-amber-100 text-amber-700'
                  }`}>
                    {j.status}
                  </span>
                </td>
                <td className="py-2">{j.lastCk}</td>
                <td className="py-2">{j.lastSavepoint}</td>
                <td className="py-2">{j.lag}</td>
                <td className="py-2">
                  <div className="flex flex-wrap gap-2">
                    <button onClick={() => triggerCheckpoint(j.id)} className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs hover:bg-slate-50">
                      <span className="inline-flex items-center gap-1"><Activity size={12} />CK</span>
                    </button>
                    <button onClick={() => triggerSavepoint(j.id)} className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs hover:bg-slate-50">
                      <span className="inline-flex items-center gap-1"><DatabaseBackup size={12} />SP</span>
                    </button>
                    <button onClick={() => restartJob(j.id)} className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs hover:bg-slate-50">
                      <span className="inline-flex items-center gap-1"><RotateCcw size={12} />{isZh ? '重启' : 'Restart'}</span>
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4">
        <div className="text-sm font-semibold text-slate-900 mb-2">{isZh ? '运维建议' : 'Ops Guidance'}</div>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-3 text-xs text-slate-600">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3"><span className="inline-flex items-center gap-1"><PlayCircle size={12} /> {isZh ? '发布前先做 Savepoint' : 'Take savepoint before release'}</span></div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3"><span className="inline-flex items-center gap-1"><TimerReset size={12} /> {isZh ? '异常恢复后观察 15 分钟' : 'Observe 15 min after recovery'}</span></div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3"><span className="inline-flex items-center gap-1"><Activity size={12} /> {isZh ? 'Checkpoint 连续失败需人工介入' : 'Manual action if checkpoint keeps failing'}</span></div>
        </div>
      </section>
    </div>
  )
}

export default FlinkRuntimeOps
