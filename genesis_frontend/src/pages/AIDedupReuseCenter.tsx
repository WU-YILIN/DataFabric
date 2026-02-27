import { useMemo, useState } from 'react'
import { CopyCheck, SearchCheck, Sparkles, TriangleAlert } from 'lucide-react'
import { useLanguage } from '../i18n/language'

type DedupItem = {
  id: string
  target: string
  similarTo: string
  score: number
  suggestion: string
}

const seed: DedupItem[] = [
  {
    id: '1',
    target: 'evt_order_paid_confirmed',
    similarTo: 'evt_order_paid',
    score: 0.93,
    suggestion: 'Reuse existing event and extend properties: payment_channel',
  },
  {
    id: '2',
    target: 'flink_order_paid_agg_v2',
    similarTo: 'flink_order_paid_agg',
    score: 0.88,
    suggestion: 'Clone SQL template and override window size only',
  },
]

const AIDedupReuseCenter = () => {
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'

  const [query, setQuery] = useState('')
  const [result, setResult] = useState<DedupItem[]>(seed)

  const highRisk = useMemo(() => result.filter((r) => r.score >= 0.9).length, [result])

  const onCheck = () => {
    if (!query.trim()) return
    setResult((prev) => [
      {
        id: String(Date.now()),
        target: query,
        similarTo: 'evt_order_paid',
        score: 0.91,
        suggestion: 'Prefer reusing evt_order_paid with additional property extension',
      },
      ...prev,
    ])
  }

  return (
    <div className="space-y-5 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <header className="rounded-2xl border border-slate-200 bg-white/80 p-5">
        <h2 className="text-2xl font-bold text-slate-900">{isZh ? 'AI 查重复用中心' : 'AI Dedup & Reuse Center'}</h2>
        <p className="mt-1 text-sm text-slate-600">
          {isZh
            ? '提交新事件/SQL/任务前自动查重，避免重复开发并给出复用建议。'
            : 'Check duplication before creating new events/SQL/tasks and get reuse suggestions.'}
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="text-xs text-slate-500">{isZh ? '重复风险项' : 'High Dup Risk'}</div>
          <div className="mt-1 text-2xl font-bold text-rose-700">{highRisk}</div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="text-xs text-slate-500">{isZh ? '建议复用项' : 'Reuse Suggestions'}</div>
          <div className="mt-1 text-2xl font-bold text-emerald-700">{result.length}</div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="text-xs text-slate-500">{isZh ? '模块状态' : 'Module Status'}</div>
          <div className="mt-1 inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-1 text-xs font-semibold text-emerald-700">
            <SearchCheck size={12} /> {isZh ? '可用' : 'Ready'}
          </div>
        </div>
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="mb-3 flex items-center gap-2 text-slate-900 font-semibold">
          <Sparkles size={16} /> {isZh ? '查重输入' : 'Dedup Input'}
        </div>
        <div className="flex flex-col gap-2 md:flex-row">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={
              isZh
                ? '输入新事件编码、SQL 任务名或需求描述'
                : 'Enter new event code, SQL task name, or requirement text'
            }
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
          />
          <button onClick={onCheck} className="rounded-lg bg-black px-3 py-2 text-sm text-white">
            {isZh ? 'AI 查重' : 'Run Dedup'}
          </button>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 overflow-auto">
        <div className="mb-3 flex items-center gap-2 text-slate-900 font-semibold">
          <CopyCheck size={16} /> {isZh ? '查重结果与复用建议' : 'Dedup Results & Reuse Suggestions'}
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-2">{isZh ? '目标项' : 'Target'}</th>
              <th className="py-2">{isZh ? '相似项' : 'Similar To'}</th>
              <th className="py-2">{isZh ? '相似度' : 'Score'}</th>
              <th className="py-2">{isZh ? '建议' : 'Suggestion'}</th>
            </tr>
          </thead>
          <tbody>
            {result.map((r) => (
              <tr key={r.id} className="border-b border-slate-100">
                <td className="py-2 font-medium text-slate-900">{r.target}</td>
                <td className="py-2">{r.similarTo}</td>
                <td className="py-2">
                  <span className={`rounded-full px-2 py-1 text-xs font-semibold ${
                    r.score >= 0.9 ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700'
                  }`}>
                    {(r.score * 100).toFixed(0)}%
                  </span>
                </td>
                <td className="py-2 text-slate-700">{r.suggestion}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
          <div className="inline-flex items-center gap-1 font-semibold"><TriangleAlert size={12} /> {isZh ? '执行建议' : 'Execution Tip'}</div>
          <div className="mt-1">
            {isZh
              ? '相似度 ≥ 90% 时默认走复用流程，只有业务确需差异时再新建。'
              : 'If similarity is ≥ 90%, default to reuse flow; create new only when business truly differs.'}
          </div>
        </div>
      </section>
    </div>
  )
}

export default AIDedupReuseCenter
