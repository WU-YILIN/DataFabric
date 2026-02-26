import { useEffect, useMemo, useState } from 'react'
import { clsx } from 'clsx'
import { Braces, Database, Download, Play, Search, Table2 } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import {
  GenesisApi,
  type ExploreAssetProfile,
  type ExploreCatalogSourceNode,
  type ExploreQueryResponse,
  type ExploreSourceSummary,
} from '../services/api'

const ALL_SOURCES_VALUE = '__ALL__'

const Explore = () => {
  const [searchParams] = useSearchParams()

  const [sources, setSources] = useState<ExploreSourceSummary[]>([])
  const [selectedSourceSystem, setSelectedSourceSystem] = useState<string>(ALL_SOURCES_VALUE)
  const [catalogTree, setCatalogTree] = useState<ExploreCatalogSourceNode[]>([])
  const [treeLoading, setTreeLoading] = useState(false)

  const [selectedAssetId, setSelectedAssetId] = useState<number | null>(null)
  const [assetProfile, setAssetProfile] = useState<ExploreAssetProfile | null>(null)
  const [profileLoading, setProfileLoading] = useState(false)

  const [sql, setSql] = useState('SELECT * FROM catalog_assets LIMIT 100')
  const [executedSql, setExecutedSql] = useState('')
  const [pageSize, setPageSize] = useState(50)

  const [queryResult, setQueryResult] = useState<ExploreQueryResponse | null>(null)
  const [queryLoading, setQueryLoading] = useState(false)
  const [exportingFormat, setExportingFormat] = useState<'csv' | 'json' | null>(null)

  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const [prefillApplied, setPrefillApplied] = useState(false)

  const sampleColumns = useMemo(() => {
    if (!assetProfile || assetProfile.sample_rows.length === 0) {
      return []
    }
    const first = assetProfile.sample_rows[0]
    return Object.keys(first)
  }, [assetProfile])

  const loadSources = async () => {
    try {
      const rows = await GenesisApi.getExploreSources()
      setSources(rows)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load source list')
    }
  }

  const loadCatalogTree = async (sourceSystem?: string) => {
    setTreeLoading(true)
    setError(null)
    try {
      const rows = await GenesisApi.getExploreCatalogTree({
        source_system: sourceSystem || undefined,
      })
      setCatalogTree(rows)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load catalog tree')
    } finally {
      setTreeLoading(false)
    }
  }

  const loadAssetProfile = async (assetId: number) => {
    setSelectedAssetId(assetId)
    setProfileLoading(true)
    setError(null)
    try {
      const data = await GenesisApi.getExploreAssetProfile(assetId)
      setAssetProfile(data)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to load asset profile')
    } finally {
      setProfileLoading(false)
    }
  }

  const executeQuery = async (targetPage = 1) => {
    setQueryLoading(true)
    setError(null)
    setNotice(null)
    try {
      const data = await GenesisApi.runExploreQuery({
        sql,
        page: targetPage,
        page_size: pageSize,
      })
      setQueryResult(data)
      setExecutedSql(sql)
      setNotice(`Query succeeded in ${data.execution_ms.toFixed(2)} ms, total ${data.total_rows} row(s).`)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Query execution failed')
    } finally {
      setQueryLoading(false)
    }
  }

  const exportResult = async (format: 'csv' | 'json') => {
    const sqlToExport = executedSql || sql
    setExportingFormat(format)
    setError(null)
    setNotice(null)
    try {
      const data = await GenesisApi.exportExploreQuery({ sql: sqlToExport, format })
      const blob = new Blob([data.content], { type: data.mime_type })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = data.filename
      document.body.appendChild(anchor)
      anchor.click()
      document.body.removeChild(anchor)
      URL.revokeObjectURL(url)
      setNotice(`Exported ${data.row_count} row(s) as ${data.filename}.`)
    } catch (e: any) {
      setError(e?.response?.data?.message ?? 'Failed to export query result')
    } finally {
      setExportingFormat(null)
    }
  }

  const insertTableToSql = (mode: 'from' | 'join') => {
    if (!assetProfile) {
      return
    }
    const table = assetProfile.asset.virtual_table
    if (mode === 'from') {
      setSql(`SELECT *\nFROM ${table}\nLIMIT 100`)
      return
    }
    const nextSql = `${sql.trim()}\nJOIN ${table} ON /* TODO: fill join condition */`
    setSql(nextSql)
  }

  const useSuggestedSql = (nextSql: string) => {
    setSql(nextSql)
    setNotice('Applied suggested SQL into editor.')
  }

  useEffect(() => {
    void loadSources()
  }, [])

  useEffect(() => {
    const source = selectedSourceSystem === ALL_SOURCES_VALUE ? undefined : selectedSourceSystem
    void loadCatalogTree(source)
  }, [selectedSourceSystem])

  useEffect(() => {
    if (prefillApplied) {
      return
    }
    const sourceType = searchParams.get('source_type')
    const sourceId = searchParams.get('source_id')
    if (!sourceType || !sourceId) {
      setPrefillApplied(true)
      return
    }
    const applyPrefill = async () => {
      try {
        const data = await GenesisApi.getExplorePrefill({
          source_type: sourceType,
          source_id: sourceId,
        })
        setSql(data.sql)
        setNotice(`Prefill loaded: ${data.title}`)
        if (sourceType.toUpperCase() === 'DATA_ASSET') {
          const assetId = Number(sourceId)
          if (Number.isFinite(assetId)) {
            await loadAssetProfile(assetId)
          }
        }
      } catch (e: any) {
        setError(e?.response?.data?.message ?? 'Failed to apply prefilled SQL')
      } finally {
        setPrefillApplied(true)
      }
    }
    void applyPrefill()
  }, [prefillApplied, searchParams])

  return (
    <div className="max-w-7xl mx-auto animate-in fade-in slide-in-from-bottom-8 duration-700 space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">Explore</h2>
          <p className="text-slate-500 text-base">
            Read-only SQL workspace with catalog tree, field preview, pagination and export.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-slate-600">Source</label>
          <select
            value={selectedSourceSystem}
            onChange={(e) => setSelectedSourceSystem(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"
          >
            <option value={ALL_SOURCES_VALUE}>All Sources</option>
            {sources.map((source) => (
              <option key={source.source_system} value={source.source_system}>
                {source.source_system} ({source.asset_count} assets)
              </option>
            ))}
          </select>
        </div>
      </header>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-rose-700 text-sm">{error}</div>
      )}
      {notice && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-emerald-700 text-sm">
          {notice}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
        <section className="xl:col-span-4 glass rounded-3xl border border-slate-200/60 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-200/70 bg-slate-50/70 flex items-center gap-2">
            <Database size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">Catalog Tree</h3>
          </div>
          <div className="p-3 max-h-[520px] overflow-auto space-y-3">
            {treeLoading ? (
              <p className="text-sm text-slate-500">Loading catalog tree...</p>
            ) : catalogTree.length === 0 ? (
              <p className="text-sm text-slate-500">No assets found in current context.</p>
            ) : (
              catalogTree.map((sourceNode) => (
                <div key={sourceNode.source_system} className="rounded-xl border border-slate-200 bg-white">
                  <div className="px-3 py-2 border-b border-slate-100 flex items-center justify-between">
                    <p className="text-sm font-semibold text-slate-800">{sourceNode.source_system}</p>
                    <span className="text-xs text-slate-500">
                      {sourceNode.databases.reduce((acc, db) => acc + db.assets.length, 0)} assets
                    </span>
                  </div>
                  <div className="p-2 space-y-2">
                    {sourceNode.databases.map((database) => (
                      <div key={`${sourceNode.source_system}:${database.database_name}`} className="rounded-lg border border-slate-100">
                        <div className="px-2 py-1.5 text-xs font-semibold text-slate-500 bg-slate-50 rounded-t-lg">
                          {database.database_name}
                        </div>
                        <div className="p-2 space-y-1">
                          {database.assets.map((asset) => (
                            <button
                              key={asset.id}
                              onClick={() => void loadAssetProfile(asset.id)}
                              className={clsx(
                                'w-full text-left rounded-lg border px-2 py-2 transition-colors',
                                selectedAssetId === asset.id
                                  ? 'border-cyan-300 bg-cyan-50'
                                  : 'border-slate-200 bg-white hover:bg-slate-50',
                              )}
                            >
                              <p className="text-xs font-semibold text-slate-800 truncate">{asset.object_name}</p>
                              <p className="text-[11px] text-slate-500 truncate">
                                {asset.asset_type} | {asset.column_count} cols | {asset.domain}
                              </p>
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="xl:col-span-8 space-y-4">
          <div className="glass rounded-3xl border border-slate-200/60 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200/70 bg-slate-50/70 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Table2 size={16} className="text-slate-500" />
                <h3 className="text-sm font-semibold text-slate-800">Asset Profile</h3>
              </div>
              {assetProfile && (
                <div className="flex gap-2">
                  <button
                    onClick={() => insertTableToSql('from')}
                    className="rounded-lg bg-slate-900 text-white px-2.5 py-1.5 text-xs hover:bg-slate-800"
                  >
                    Insert FROM
                  </button>
                  <button
                    onClick={() => insertTableToSql('join')}
                    className="rounded-lg bg-slate-100 text-slate-700 px-2.5 py-1.5 text-xs hover:bg-slate-200"
                  >
                    Insert JOIN
                  </button>
                </div>
              )}
            </div>
            <div className="p-4">
              {profileLoading ? (
                <p className="text-sm text-slate-500">Loading asset profile...</p>
              ) : !assetProfile ? (
                <p className="text-sm text-slate-500">Select an asset from catalog tree to view columns and samples.</p>
              ) : (
                <div className="space-y-4">
                  <div className="rounded-xl border border-slate-200 p-3 bg-white">
                    <p className="text-sm font-semibold text-slate-900">{assetProfile.asset.name}</p>
                    <p className="text-xs text-slate-500 mt-1 font-mono">
                      table: {assetProfile.asset.virtual_table} | object: {assetProfile.asset.object_name}
                    </p>
                    <p className="text-xs text-slate-500 mt-1">
                      {assetProfile.asset.asset_type} | {assetProfile.asset.source_system} | {assetProfile.asset.domain}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {assetProfile.suggested_queries.map((item) => (
                        <button
                          key={item.title}
                          onClick={() => useSuggestedSql(item.sql)}
                          className="rounded-lg bg-indigo-50 text-indigo-700 px-2.5 py-1.5 text-xs hover:bg-indigo-100"
                        >
                          {item.title}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div className="rounded-xl border border-slate-200 p-3 bg-white">
                      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Columns</p>
                      <div className="space-y-1 max-h-44 overflow-auto">
                        {assetProfile.columns.map((column) => (
                          <div key={column.query_name} className="text-xs flex items-center justify-between gap-2">
                            <span className="font-mono text-slate-700">{column.query_name}</span>
                            <span className="text-slate-500">{column.type}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-200 p-3 bg-white">
                      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Sample Rows</p>
                      {assetProfile.sample_rows.length === 0 ? (
                        <p className="text-xs text-slate-500">No sample rows available.</p>
                      ) : (
                        <div className="overflow-auto max-h-44">
                          <table className="w-full text-xs">
                            <thead className="text-slate-500">
                              <tr>
                                {sampleColumns.map((column) => (
                                  <th key={column} className="text-left px-2 py-1 font-semibold">
                                    {column}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {assetProfile.sample_rows.map((row, rowIndex) => (
                                <tr key={`sample-${rowIndex}`} className="border-t border-slate-100">
                                  {sampleColumns.map((column) => (
                                    <td key={`${rowIndex}:${column}`} className="px-2 py-1 text-slate-700">
                                      {String(row[column] ?? '')}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="glass rounded-3xl border border-slate-200/60 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200/70 bg-slate-50/70 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Braces size={16} className="text-slate-500" />
                <h3 className="text-sm font-semibold text-slate-800">SQL Editor (Read-only)</h3>
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={pageSize}
                  onChange={(e) => setPageSize(Number(e.target.value))}
                  className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs text-slate-700"
                >
                  <option value={20}>20 / page</option>
                  <option value={50}>50 / page</option>
                  <option value={100}>100 / page</option>
                </select>
                <button
                  onClick={() => void executeQuery(1)}
                  disabled={queryLoading}
                  className="rounded-lg bg-cyan-600 text-white px-2.5 py-1.5 text-xs hover:bg-cyan-500 disabled:opacity-60 flex items-center gap-1"
                >
                  <Play size={12} />
                  Execute
                </button>
              </div>
            </div>
            <div className="p-4 space-y-3">
              <textarea
                value={sql}
                onChange={(e) => setSql(e.target.value)}
                className="w-full h-44 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-mono text-slate-800 outline-none focus:ring-2 focus:ring-cyan-300/60"
              />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-slate-500 flex items-center gap-1">
                  <Search size={12} />
                  Allowed: SELECT / WITH / EXPLAIN. Mutating SQL is blocked.
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => void exportResult('csv')}
                    disabled={Boolean(exportingFormat)}
                    className="rounded-lg bg-slate-100 text-slate-700 px-2.5 py-1.5 text-xs hover:bg-slate-200 disabled:opacity-60 flex items-center gap-1"
                  >
                    <Download size={12} />
                    {exportingFormat === 'csv' ? 'Exporting CSV...' : 'Export CSV'}
                  </button>
                  <button
                    onClick={() => void exportResult('json')}
                    disabled={Boolean(exportingFormat)}
                    className="rounded-lg bg-slate-100 text-slate-700 px-2.5 py-1.5 text-xs hover:bg-slate-200 disabled:opacity-60 flex items-center gap-1"
                  >
                    <Download size={12} />
                    {exportingFormat === 'json' ? 'Exporting JSON...' : 'Export JSON'}
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div className="glass rounded-3xl border border-slate-200/60 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200/70 bg-slate-50/70 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-800">Query Result</h3>
              {queryResult && (
                <p className="text-xs text-slate-500">
                  page {queryResult.page}/{queryResult.total_pages} | {queryResult.total_rows} rows | {queryResult.execution_ms.toFixed(2)} ms
                </p>
              )}
            </div>
            <div className="p-4">
              {queryLoading ? (
                <p className="text-sm text-slate-500">Executing query...</p>
              ) : !queryResult ? (
                <p className="text-sm text-slate-500">Run SQL to see results.</p>
              ) : (
                <div className="space-y-3">
                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                    {queryResult.guidance}
                  </div>
                  <div className="overflow-auto rounded-xl border border-slate-200">
                    <table className="w-full text-xs">
                      <thead className="bg-slate-50 text-slate-600">
                        <tr>
                          {queryResult.columns.map((column) => (
                            <th key={column} className="text-left px-3 py-2 font-semibold">
                              {column}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {queryResult.rows.length === 0 ? (
                          <tr>
                            <td className="px-3 py-4 text-slate-500" colSpan={Math.max(queryResult.columns.length, 1)}>
                              Query returned 0 rows.
                            </td>
                          </tr>
                        ) : (
                          queryResult.rows.map((row, rowIndex) => (
                            <tr key={`result-row-${rowIndex}`} className="border-t border-slate-100">
                              {queryResult.columns.map((column) => (
                                <td key={`${rowIndex}:${column}`} className="px-3 py-2 text-slate-700 align-top">
                                  {String(row[column] ?? '')}
                                </td>
                              ))}
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={() => void executeQuery(Math.max(1, (queryResult.page ?? 1) - 1))}
                      disabled={queryResult.page <= 1 || queryLoading}
                      className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                    >
                      Prev
                    </button>
                    <button
                      onClick={() => void executeQuery(Math.min(queryResult.total_pages, queryResult.page + 1))}
                      disabled={queryResult.page >= queryResult.total_pages || queryLoading}
                      className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

export default Explore
