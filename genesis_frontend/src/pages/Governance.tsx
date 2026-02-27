import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, CheckCircle, HelpCircle, Loader2, ShieldCheck, Sparkles } from 'lucide-react'
import { clsx } from 'clsx'
import { useSearchParams, useNavigate } from 'react-router-dom'

import { GenesisApi, type GovernanceResult } from '../services/api'
import { useLanguage } from '../i18n/language'

type GovernanceFormState = {
  name: string
  description: string
  properties: string
}

const Governance = () => {
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const eventId = useMemo(() => {
    const raw = searchParams.get('event_id')
    if (!raw) {
      return null
    }
    const parsed = Number(raw)
    return Number.isFinite(parsed) ? parsed : null
  }, [searchParams])

  const [formData, setFormData] = useState<GovernanceFormState>({
    name: searchParams.get('name') ?? '',
    description: searchParams.get('description') ?? '',
    properties: searchParams.get('properties') ?? '{\n  "user_id": "uuid",\n  "timestamp": "iso8601"\n}',
  })
  const [loadingContext, setLoadingContext] = useState(false)
  const [checking, setChecking] = useState(false)
  const [applying, setApplying] = useState(false)
  const [savingDraft, setSavingDraft] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [result, setResult] = useState<GovernanceResult | null>(null)
  const [selectedSuggestionIndexes, setSelectedSuggestionIndexes] = useState<number[]>([])

  useEffect(() => {
    if (!eventId) {
      return
    }

    const loadEventContext = async () => {
      setLoadingContext(true)
      setError(null)
      try {
        const detail = await GenesisApi.getEventDetail(eventId)
        setFormData({
          name: detail.event.name ?? '',
          description: detail.event.description ?? '',
          properties: JSON.stringify(detail.event.properties ?? {}, null, 2),
        })
      } catch (e: any) {
        setError(e?.response?.data?.message ?? (isZh ? '加载事件上下文失败' : 'Failed to load event context'))
      } finally {
        setLoadingContext(false)
      }
    }

    void loadEventContext()
  }, [eventId, isZh])

  const submitGovernanceCheck = async () => {
    setChecking(true)
    setError(null)
    setNotice(null)
    setResult(null)

    try {
      const data = await GenesisApi.checkGovernance(eventId, formData.name, formData.description, formData.properties)
      setResult(data)
      setSelectedSuggestionIndexes(data.suggestions.map((_, idx) => idx))
    } catch (e: any) {
      setError(e?.response?.data?.message ?? (isZh ? '治理检查失败' : 'Failed to check governance'))
    } finally {
      setChecking(false)
    }
  }

  const saveDraftEvent = async () => {
    if (!eventId) {
      return
    }
    setSavingDraft(true)
    setError(null)
    setNotice(null)
    try {
      let parsedProperties: Record<string, unknown> = {}
      try {
        parsedProperties = JSON.parse(formData.properties || '{}')
      } catch {
        throw new Error(isZh ? 'Properties 必须是合法 JSON' : 'Properties must be valid JSON')
      }
      await GenesisApi.updateEvent(eventId, {
        name: formData.name,
        description: formData.description,
        properties: parsedProperties,
      })
      setNotice(isZh ? '草稿已保存到 Event Catalog' : 'Draft changes saved to Event Catalog')
    } catch (e: any) {
      setError(e?.response?.data?.message ?? e?.message ?? (isZh ? '保存草稿失败' : 'Failed to save draft'))
    } finally {
      setSavingDraft(false)
    }
  }

  const applySelectedSuggestions = async () => {
    if (!result || !eventId) {
      return
    }
    setApplying(true)
    setError(null)
    setNotice(null)
    try {
      const applied = await GenesisApi.applyGovernanceSuggestions(result.check_id, {
        event_id: eventId,
        suggestion_indexes: selectedSuggestionIndexes,
      })
      setFormData({
        name: applied.event.name ?? '',
        description: applied.event.description ?? '',
        properties: JSON.stringify(applied.event.properties ?? {}, null, 2),
      })
      setNotice(isZh ? '已应用选中治理建议并生成新版本' : 'Selected governance suggestions were applied and versioned')
    } catch (e: any) {
      setError(e?.response?.data?.message ?? (isZh ? '应用建议失败' : 'Failed to apply suggestions'))
    } finally {
      setApplying(false)
    }
  }

  const toggleSuggestion = (index: number) => {
    setSelectedSuggestionIndexes((prev) =>
      prev.includes(index) ? prev.filter((item) => item !== index) : [...prev, index],
    )
  }

  return (
    <div className="max-w-6xl mx-auto animate-in fade-in zoom-in-95 duration-500">
      <section className="mb-4 rounded-2xl border border-slate-200 bg-white/80 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-900">{isZh ? '下一步建议' : 'Recommended Next Step'}</p>
            <p className="text-xs text-slate-600">
              {isZh ? '治理通过后，立即进入管道开通并绑定数据质量规则。' : 'After governance pass, provision pipeline and bind data quality rules.'}
            </p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => navigate('/pipelines')} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs hover:bg-slate-50">
              {isZh ? '去管道' : 'Go Pipelines'}
            </button>
            <button onClick={() => navigate('/data-quality')} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs hover:bg-slate-50">
              {isZh ? '去数据质量' : 'Go Data Quality'}
            </button>
          </div>
        </div>
      </section>
      <header className="mb-6">
        <h2 className="text-3xl font-bold text-gray-900 tracking-tight">{isZh ? '治理工作台' : 'Governance Workbench'}</h2>
        <p className="text-gray-500 text-base">
          {isZh
            ? '校验事件定义，审阅 AI 风险与建议，应用修改并进行下一轮治理检查。'
            : 'Validate event definition, review AI risks/suggestions, apply changes, and re-check in governance loop.'}
        </p>
      </header>

      {error && (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
      )}
      {notice && (
        <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {notice}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className="glass p-6 rounded-3xl">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-900">Event Definition</h3>
            {eventId && <span className="text-xs rounded-full px-2 py-1 bg-slate-100 text-slate-700">event_id={eventId}</span>}
          </div>

          {loadingContext ? (
            <div className="py-12 text-center text-slate-500">{isZh ? '加载事件上下文中...' : 'Loading event context...'}</div>
          ) : (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">{isZh ? '事件名称' : 'Event Name'}</label>
                <input
                  type="text"
                  className="ios-input"
                  value={formData.name}
                  onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">{isZh ? '描述' : 'Description'}</label>
                <textarea
                  className="ios-input h-28 resize-none"
                  value={formData.description}
                  onChange={(e) => setFormData((prev) => ({ ...prev, description: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">{isZh ? 'Properties (JSON Schema)' : 'Properties (JSON Schema)'}</label>
                <textarea
                  className="ios-input h-56 resize-none font-mono text-sm"
                  value={formData.properties}
                  onChange={(e) => setFormData((prev) => ({ ...prev, properties: e.target.value }))}
                />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <button
                  onClick={() => void submitGovernanceCheck()}
                  disabled={checking || loadingContext}
                  className="ios-btn-primary py-3 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {checking ? (
                    <>
                      <Loader2 className="animate-spin" size={18} />
                      {isZh ? '检查中...' : 'Checking...'}
                    </>
                  ) : (
                    isZh ? '提交治理检查' : 'Submit Governance Check'
                  )}
                </button>
                <button
                  onClick={() => void saveDraftEvent()}
                  disabled={!eventId || savingDraft || loadingContext}
                  className="rounded-xl border border-slate-200 bg-white text-slate-700 font-medium py-3 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {savingDraft ? (isZh ? '保存中...' : 'Saving...') : isZh ? '保存草稿' : 'Save Draft'}
                </button>
              </div>
            </div>
          )}
        </section>

        <section className="flex flex-col gap-4">
          {!result && !checking && (
            <div className="glass border-dashed border-2 border-gray-300/50 rounded-3xl p-8 text-center text-gray-400">
              <div className="bg-gray-100 p-4 rounded-full inline-flex mb-3">
                <ShieldCheck size={36} className="text-gray-300" />
              </div>
              <p className="font-medium text-lg">Governance result pending</p>
              <p className="text-sm mt-2">Submit a check to get verdict, risks, and actionable suggestions.</p>
            </div>
          )}

          {checking && (
            <div className="glass p-8 rounded-3xl flex flex-col items-center justify-center text-center animate-pulse">
              <div className="w-16 h-16 border-4 border-ios-indigo border-t-transparent rounded-full animate-spin mb-4"></div>
              <p className="text-gray-700 font-semibold">Evaluating governance rules...</p>
              <p className="text-gray-400 text-sm mt-1">LLM + vector search + historical context</p>
            </div>
          )}

          {result && (
            <>
              <div
                className={clsx(
                  'glass p-6 rounded-3xl border',
                  result.verdict === 'APPROVE'
                    ? 'border-emerald-200'
                    : result.verdict === 'REJECT'
                      ? 'border-rose-200'
                      : 'border-amber-200',
                )}
              >
                <div className="flex items-center gap-3 mb-4">
                  <div
                    className={clsx(
                      'p-2 rounded-full',
                      result.verdict === 'APPROVE'
                        ? 'bg-emerald-100 text-emerald-600'
                        : result.verdict === 'REJECT'
                          ? 'bg-rose-100 text-rose-600'
                          : 'bg-amber-100 text-amber-600',
                    )}
                  >
                    {result.verdict === 'APPROVE' && <CheckCircle size={22} />}
                    {result.verdict === 'REJECT' && <AlertCircle size={22} />}
                    {result.verdict === 'NEEDS_REVISION' && <HelpCircle size={22} />}
                  </div>
                  <div>
                    <p className="text-xs uppercase text-slate-500">Verdict</p>
                    <p className="text-xl font-bold text-slate-900">{result.verdict}</p>
                  </div>
                  <div className="ml-auto text-right">
                    <p className="text-xs uppercase text-slate-500">Confidence</p>
                    <p className="font-semibold text-slate-900">{(result.score * 100).toFixed(1)}%</p>
                  </div>
                </div>
                <div className="w-full bg-gray-200 h-2 rounded-full overflow-hidden mb-4">
                  <div
                    className={clsx(
                      'h-full rounded-full',
                      result.score > 0.8 ? 'bg-emerald-500' : result.score > 0.5 ? 'bg-amber-500' : 'bg-rose-500',
                    )}
                    style={{ width: `${Math.max(2, result.score * 100)}%` }}
                  ></div>
                </div>
                <p className="text-sm text-slate-700">{result.reasoning}</p>
                <p className="text-xs text-slate-500 mt-2">model: {result.model_name}</p>
              </div>

              <div className="glass p-6 rounded-3xl">
                <h4 className="text-sm font-semibold text-slate-700 uppercase mb-2">Risks</h4>
                {result.risks.length === 0 ? (
                  <p className="text-sm text-slate-500">No explicit risks returned.</p>
                ) : (
                  <ul className="space-y-2">
                    {result.risks.map((risk, idx) => (
                      <li key={`risk-${idx}`} className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                        {risk}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="glass p-6 rounded-3xl">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-sm font-semibold text-slate-700 uppercase">Suggestions</h4>
                  <button
                    onClick={() => setSelectedSuggestionIndexes(result.suggestions.map((_, idx) => idx))}
                    className="text-xs text-cyan-700 hover:text-cyan-600"
                  >
                    Select all
                  </button>
                </div>
                {result.suggestions.length === 0 ? (
                  <p className="text-sm text-slate-500">No suggestions from model.</p>
                ) : (
                  <div className="space-y-3">
                    {result.suggestions.map((item, idx) => (
                      <label key={`sugg-${idx}`} className="block rounded-xl border border-slate-200 bg-white p-3">
                        <div className="flex gap-2 items-start">
                          <input
                            type="checkbox"
                            checked={selectedSuggestionIndexes.includes(idx)}
                            onChange={() => toggleSuggestion(idx)}
                            className="mt-1"
                          />
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-semibold text-slate-900">{item.title}</p>
                            <p className="text-xs text-slate-600 mt-1">{item.rationale}</p>
                            <pre className="mt-2 text-[11px] bg-slate-50 rounded p-2 overflow-auto text-slate-700">
                              {JSON.stringify(item.patch, null, 2)}
                            </pre>
                          </div>
                        </div>
                      </label>
                    ))}
                    <button
                      onClick={() => void applySelectedSuggestions()}
                      disabled={!eventId || applying || selectedSuggestionIndexes.length === 0}
                      className="w-full rounded-xl bg-cyan-600 text-white py-2.5 font-medium hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    >
                      {applying ? (
                        <>
                          <Loader2 className="animate-spin" size={16} />
                          Applying...
                        </>
                      ) : (
                        <>
                          <Sparkles size={16} />
                          Apply Selected Suggestions
                        </>
                      )}
                    </button>
                  </div>
                )}
              </div>

              <div className="glass p-6 rounded-3xl">
                <h4 className="text-sm font-semibold text-slate-700 uppercase mb-2">Similar Events</h4>
                {result.similar_events.length === 0 ? (
                  <p className="text-sm text-slate-500">No similar events found.</p>
                ) : (
                  <div className="space-y-2">
                    {result.similar_events.map((row) => (
                      <div key={String(row.id)} className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
                        <p className="font-semibold text-slate-800">{String(row.payload?.name ?? row.id)}</p>
                        <p className="text-xs text-slate-500 mt-1">
                          source={row.source} | score={Number(row.score ?? 0).toFixed(3)}
                        </p>
                        <p className="text-xs text-slate-600 mt-1">{String(row.payload?.description ?? '')}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  )
}

export default Governance
