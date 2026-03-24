import { useState } from 'react'
import { Braces, Play, Sparkles, Wand2 } from 'lucide-react'
import { useLanguage } from '../i18n/language'

const demoSql = `-- AI Generated Flink SQL\nINSERT INTO dws_order_paid_10m\nSELECT\n  TUMBLE_START(ts, INTERVAL '10' MINUTE) AS window_start,\n  payment_channel,\n  COUNT(*) AS paid_cnt,\n  SUM(amount) AS paid_amount\nFROM evt_order_paid\nGROUP BY\n  TUMBLE(ts, INTERVAL '10' MINUTE),\n  payment_channel;`

const AIFlinkSqlStudio = () => {
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'

  const [requirement, setRequirement] = useState('')
  const [sql, setSql] = useState('')
  const [status, setStatus] = useState<'IDLE' | 'GENERATED' | 'VALIDATED'>('IDLE')

  const onGenerate = () => {
    if (!requirement.trim()) return
    setSql(demoSql)
    setStatus('GENERATED')
  }

  const onValidate = () => {
    if (!sql.trim()) return
    setStatus('VALIDATED')
  }

  return (
    <div className="space-y-5 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <header className="rounded-2xl border border-slate-200 bg-white/80 p-5">
        <h2 className="text-2xl font-bold text-slate-900">{isZh ? 'AI Flink SQL Studio' : 'AI Flink SQL Studio'}</h2>
        <p className="mt-1 text-sm text-slate-600">
          {isZh
            ? '通过业务需求自动生成 Flink SQL，并在提交前做基础校验。'
            : 'Generate Flink SQL from business intent and validate before submit.'}
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="text-xs text-slate-500">{isZh ? '生成状态' : 'Generation Status'}</div>
          <div className="mt-1 text-sm font-semibold text-slate-900">{status}</div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="text-xs text-slate-500">{isZh ? '目标引擎' : 'Target Engine'}</div>
          <div className="mt-1 text-sm font-semibold text-slate-900">Flink SQL</div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="text-xs text-slate-500">{isZh ? '模块状态' : 'Module Status'}</div>
          <div className="mt-1 inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-1 text-xs font-semibold text-emerald-700">
            <Sparkles size={12} /> {isZh ? '可用' : 'Ready'}
          </div>
        </div>
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="mb-3 flex items-center gap-2 text-slate-900 font-semibold">
          <Wand2 size={16} /> {isZh ? '需求输入' : 'Requirement Input'}
        </div>
        <textarea
          value={requirement}
          onChange={(e) => setRequirement(e.target.value)}
          rows={4}
          placeholder={
            isZh
              ? '示例：按支付渠道统计每 10 分钟支付订单数和金额。'
              : 'Example: aggregate paid orders and amount every 10 minutes by payment channel.'
          }
          className="w-full rounded-xl border border-slate-200 p-3 text-sm"
        />
        <div className="mt-3 flex gap-2">
          <button onClick={onGenerate} className="rounded-lg bg-black px-3 py-2 text-sm text-white">
            {isZh ? 'AI 生成 SQL' : 'Generate SQL'}
          </button>
          <button onClick={onValidate} disabled={!sql} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm disabled:opacity-40">
            <span className="inline-flex items-center gap-1"><Play size={14} /> {isZh ? '校验 SQL' : 'Validate SQL'}</span>
          </button>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="mb-3 flex items-center gap-2 text-slate-900 font-semibold">
          <Braces size={16} /> {isZh ? 'SQL 输出' : 'SQL Output'}
        </div>
        <pre className="overflow-auto rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs leading-6 text-slate-800">
{sql || (isZh ? '-- 尚未生成 SQL' : '-- SQL not generated yet')}
        </pre>
      </section>
    </div>
  )
}

export default AIFlinkSqlStudio
