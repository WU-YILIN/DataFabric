import type { ReactNode } from 'react'
import { Search } from 'lucide-react'

export function FabricPageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string
  title: string
  description: string
  actions?: ReactNode
}) {
  return (
    <section className="df-surface rounded-[32px] p-6 md:p-7">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--df-text-soft)]">
            {eyebrow}
          </div>
          <h1 className="df-display mt-2 text-[30px] tracking-[-0.04em] text-[var(--df-text)] md:text-[34px]">
            {title}
          </h1>
          <p className="df-body mt-3 max-w-4xl text-[15px] leading-7 text-[var(--df-text-muted)]">
            {description}
          </p>
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </div>
    </section>
  )
}

export function FabricStatCard({
  label,
  value,
  hint,
}: {
  label: string
  value: string | number
  hint?: string
}) {
  return (
    <div className="rounded-[26px] border border-[var(--df-border)] bg-[var(--df-surface)] p-5 shadow-[var(--df-shadow-soft)]">
      <div className="text-xs uppercase tracking-[0.2em] text-[var(--df-text-soft)]">{label}</div>
      <div className="df-display mt-2 text-[34px] tracking-[-0.04em] text-[var(--df-text)]">{value}</div>
      {hint ? <div className="mt-2 text-xs leading-5 text-[var(--df-text-muted)]">{hint}</div> : null}
    </div>
  )
}

export function FabricSection({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle: string
  children: ReactNode
}) {
  return (
    <section className="df-surface rounded-[30px] p-6">
      <div className="mb-4">
        <h2 className="df-display text-[20px] tracking-[-0.03em] text-[var(--df-text)]">{title}</h2>
        <p className="mt-1 text-sm leading-6 text-[var(--df-text-muted)]">{subtitle}</p>
      </div>
      {children}
    </section>
  )
}

export function FabricSearchInput({
  value,
  placeholder,
  onChange,
}: {
  value: string
  placeholder: string
  onChange: (value: string) => void
}) {
  return (
    <div className="relative">
      <Search size={15} className="absolute left-3 top-3 text-[var(--df-text-soft)]" />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full rounded-[18px] border border-[var(--df-border)] bg-[var(--df-surface-2)] px-10 py-2.5 text-sm text-[var(--df-text)] outline-none placeholder:text-[var(--df-text-soft)] focus:border-[var(--df-border-strong)]"
      />
    </div>
  )
}

export function FabricFilterSelect({
  value,
  options,
  onChange,
}: {
  value: string
  options: Array<{ label: string; value: string }>
  onChange: (value: string) => void
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="rounded-[18px] border border-[var(--df-border)] bg-[var(--df-surface)] px-3 py-2.5 text-sm text-[var(--df-text)]"
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  )
}

export function FabricPager({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number
  limit: number
  offset: number
  onChange: (offset: number) => void
}) {
  const currentPage = total === 0 ? 1 : Math.floor(offset / limit) + 1
  const totalPages = Math.max(Math.ceil(total / limit), 1)

  return (
    <div className="mt-4 flex items-center justify-between text-sm text-[var(--df-text-muted)]">
      <div>{total === 0 ? '0' : `${offset + 1}-${Math.min(offset + limit, total)}`} / {total}</div>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={offset <= 0}
          onClick={() => onChange(Math.max(offset - limit, 0))}
          className="rounded-[14px] border border-[var(--df-border)] bg-[var(--df-surface)] px-3 py-1.5 text-[var(--df-text)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          上一页
        </button>
        <div className="rounded-[14px] bg-[var(--df-surface-2)] px-3 py-1.5 text-[var(--df-text)]">
          {currentPage}/{totalPages}
        </div>
        <button
          type="button"
          disabled={offset + limit >= total}
          onClick={() => onChange(offset + limit)}
          className="rounded-[14px] border border-[var(--df-border)] bg-[var(--df-surface)] px-3 py-1.5 text-[var(--df-text)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          下一页
        </button>
      </div>
    </div>
  )
}

export function FabricEmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-[22px] border border-dashed border-[var(--df-border)] bg-[var(--df-surface-2)] px-4 py-10 text-center text-sm text-[var(--df-text-muted)]">
      {message}
    </div>
  )
}

export function formatFabricBytes(value?: number) {
  const bytes = Number(value || 0)
  if (bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const exp = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const num = bytes / 1024 ** exp
  return `${num.toFixed(num >= 10 || exp === 0 ? 0 : 1)} ${units[exp]}`
}

export function heatTone(heat?: string) {
  if (heat === 'HOT')
    return 'border-[color:color-mix(in srgb,var(--df-rose)_28%,white)] bg-[color:color-mix(in srgb,var(--df-rose)_10%,white)] text-[var(--df-rose)]'
  if (heat === 'WARM')
    return 'border-[color:color-mix(in srgb,var(--df-amber)_28%,white)] bg-[color:color-mix(in srgb,var(--df-amber)_12%,white)] text-[color:color-mix(in srgb,var(--df-amber)_85%,black)]'
  return 'border-[var(--df-border)] bg-[var(--df-surface-2)] text-[var(--df-text-muted)]'
}

export function statusTone(status?: string) {
  if (!status) return 'border-[var(--df-border)] bg-[var(--df-surface-2)] text-[var(--df-text-muted)]'
  const normalized = status.toUpperCase()
  if (normalized.includes('FAIL')) {
    return 'border-[color:color-mix(in srgb,var(--df-rose)_28%,white)] bg-[color:color-mix(in srgb,var(--df-rose)_10%,white)] text-[var(--df-rose)]'
  }
  if (normalized.includes('RUN') || normalized.includes('PUBLISH') || normalized.includes('READY')) {
    return 'border-[color:color-mix(in srgb,var(--df-moss)_25%,white)] bg-[color:color-mix(in srgb,var(--df-moss)_10%,white)] text-[var(--df-moss)]'
  }
  if (normalized.includes('PLAN') || normalized.includes('OPEN') || normalized.includes('PENDING')) {
    return 'border-[color:color-mix(in srgb,var(--df-amber)_28%,white)] bg-[color:color-mix(in srgb,var(--df-amber)_12%,white)] text-[color:color-mix(in srgb,var(--df-amber)_85%,black)]'
  }
  return 'border-[var(--df-border)] bg-[var(--df-surface-2)] text-[var(--df-text-muted)]'
}

export function FabricBadge({
  value,
  tone = 'status',
}: {
  value: string
  tone?: 'status' | 'heat'
}) {
  const klass = tone === 'heat' ? heatTone(value) : statusTone(value)
  return <span className={`rounded-full border px-2.5 py-1 text-xs font-medium tracking-[0.01em] ${klass}`}>{value}</span>
}
