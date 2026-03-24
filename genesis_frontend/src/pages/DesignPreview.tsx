import type { ReactNode } from 'react'

const palettes = [
  { name: '主背景', token: '--df-bg', value: '#F5F2EA', swatchClass: 'bg-[#f5f2ea]' },
  { name: '主表面', token: '--df-surface', value: '#FFFDF8', swatchClass: 'bg-[#fffdf8]' },
  { name: '次表面', token: '--df-surface-2', value: '#F8F5EE', swatchClass: 'bg-[#f8f5ee]' },
  { name: '墨蓝', token: '--df-ink', value: '#153B52', swatchClass: 'bg-[#153b52] text-white' },
  { name: '执行青', token: '--df-cyan', value: '#157A8A', swatchClass: 'bg-[#157a8a] text-white' },
  { name: '知识绿', token: '--df-moss', value: '#4D6B4A', swatchClass: 'bg-[#4d6b4a] text-white' },
  { name: '候选琥珀', token: '--df-amber', value: '#A96B12', swatchClass: 'bg-[#a96b12] text-white' },
  { name: '风险玫瑰', token: '--df-rose', value: '#B54352', swatchClass: 'bg-[#b54352] text-white' },
]

function Section({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <section className="df-surface p-6">
      <div className="mb-5">
        <div className="df-display text-2xl font-semibold tracking-tight text-[var(--df-text)]">{title}</div>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--df-text-muted)]">{subtitle}</p>
      </div>
      {children}
    </section>
  )
}

function Chip({
  label,
  tone,
}: {
  label: string
  tone: 'fact' | 'candidate' | 'knowledge' | 'brief'
}) {
  const map = {
    fact: 'border-[#bcd0db] bg-[#edf4f8] text-[#153b52]',
    candidate: 'border-[#e7cf9c] bg-[#fff7e7] text-[#8a5a0f]',
    knowledge: 'border-[#c4d5c2] bg-[#edf5ec] text-[#365538]',
    brief: 'border-[var(--df-border)] bg-white text-[var(--df-text-muted)]',
  }

  return <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-medium ${map[tone]}`}>{label}</span>
}

export default function DesignPreview() {
  return (
    <div className="space-y-6">
      <div className="df-surface overflow-hidden p-8">
        <div className="text-xs font-semibold uppercase tracking-[0.28em] text-[var(--df-text-soft)]">Design Preview</div>
        <h1 className="df-display mt-3 text-4xl font-semibold tracking-tight text-[var(--df-text)]">
          DataFabric Editorial Operations Console
        </h1>
        <p className="mt-4 max-w-4xl text-[15px] leading-8 text-[var(--df-text-muted)]">
          这是一个设计系统预览页，用来统一校验 DataFabric 的颜色、字体、状态 chip、卡片层级、Chat 回答样式和执行线索。
          它不是业务页面，而是后续页面统一改版时的视觉基线。
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Chip label="已确认事实" tone="fact" />
          <Chip label="待确认候选" tone="candidate" />
          <Chip label="已发布知识" tone="knowledge" />
          <Chip label="AI 简报" tone="brief" />
        </div>
      </div>

      <Section
        title="Typography"
        subtitle="标题采用更有辨识度的 Display 体系，正文与操作信息使用 IBM Plex Sans，证据和 trace 使用 IBM Plex Mono。"
      >
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="df-surface-muted p-5">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--df-text-soft)]">Display</div>
            <div className="df-display mt-3 text-3xl font-semibold tracking-tight text-[var(--df-text)]">字段级可信理解</div>
            <p className="mt-3 text-sm leading-6 text-[var(--df-text-muted)]">Space Grotesk 用于页面锚点和重要区块标题。</p>
          </div>
          <div className="df-surface-muted p-5">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--df-text-soft)]">Body</div>
            <div className="df-body mt-3 text-base leading-7 text-[var(--df-text)]">
              业务问题、数据解释、候选说明和知识内容都使用更稳定、更长文友好的正文系统。
            </div>
          </div>
          <div className="df-surface-muted p-5">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--df-text-soft)]">Mono</div>
            <div className="df-mono mt-3 text-sm leading-7 text-[var(--df-text)]">
              trace_0fa3d91a3f2c
              <br />
              orders.user_id
              <br />
              SELECT province, gender, COUNT(*)
            </div>
          </div>
        </div>
      </Section>

      <Section
        title="Color Tokens"
        subtitle="主界面保持克制，只有在事实、候选、执行和风险上才使用更强的状态色。"
      >
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {palettes.map((item) => (
            <div key={item.token} className="df-surface-muted p-4">
              <div className={`h-16 rounded-2xl border border-black/5 ${item.swatchClass}`} />
              <div className="mt-3 text-sm font-medium text-[var(--df-text)]">{item.name}</div>
              <div className="mt-1 text-xs text-[var(--df-text-soft)]">{item.token}</div>
              <div className="df-mono mt-2 text-xs text-[var(--df-text-muted)]">{item.value}</div>
            </div>
          ))}
        </div>
      </Section>

      <Section
        title="Chat Response Pattern"
        subtitle="回答正文必须最先被读到；事实、候选、记忆和执行线索都存在，但不能抢正文。"
      >
        <div className="grid gap-6 lg:grid-cols-[1.35fr_0.95fr]">
          <div className="df-surface-muted p-5">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--df-text-soft)]">Assistant Answer</div>
            <div className="mt-4 rounded-[20px] border border-[var(--df-border)] bg-white px-5 py-5">
              <div className="df-body text-[15px] leading-8 text-[var(--df-text)]">
                当前项目里已经发现 <span className="df-mono">customer_profile.gender</span> 和{' '}
                <span className="df-mono">customer_profile.birth_date</span>。系统确认{' '}
                <span className="df-mono">birth_date</span> 可用于年龄计算，<span className="df-mono">gender</span>{' '}
                可用于性别分组。由于尚未发现明确的省份字段，当前还不能直接计算“江苏地区”用户占比。
              </div>
              <div className="mt-5 space-y-4">
                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--df-text-soft)]">已确认事实</div>
                  <div className="flex flex-wrap gap-2">
                    <Chip label="customer_profile.gender" tone="fact" />
                    <Chip label="customer_profile.birth_date" tone="fact" />
                  </div>
                </div>
                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--df-text-soft)]">候选判断</div>
                  <div className="flex flex-wrap gap-2">
                    <Chip label="birth_date -> 年龄计算字段（待确认）" tone="candidate" />
                  </div>
                </div>
                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--df-text-soft)]">引用记忆</div>
                  <div className="flex flex-wrap gap-2">
                    <Chip label="[Source Brief] customer_profile" tone="brief" />
                    <Chip label="用户主题域说明" tone="knowledge" />
                  </div>
                </div>
                <div className="rounded-2xl border border-[#d4e6eb] bg-[#f4fbfc] px-4 py-3">
                  <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--df-text-soft)]">执行线索</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Chip label="MEMORY" tone="fact" />
                    <Chip label="WAITING_CONFIRMATION" tone="candidate" />
                    <Chip label="ASYNC PLAN" tone="brief" />
                  </div>
                  <div className="df-mono mt-3 text-xs text-[var(--df-text-soft)]">trace_0fa3d91a3f2c1ab0c9d7e42</div>
                </div>
              </div>
            </div>
          </div>

          <div className="df-surface-muted p-5">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--df-text-soft)]">Design Rules</div>
            <ul className="mt-4 space-y-3 text-sm leading-7 text-[var(--df-text-muted)]">
              <li>1. 回答正文优先，不允许被 trace 和标签区抢戏。</li>
              <li>2. 事实、候选、知识必须分开展示，不能混在同一段里。</li>
              <li>3. trace 默认弱化，只在用户愿意时展开细节。</li>
              <li>4. 没证据时必须明确承认“当前没有足够证据”。</li>
            </ul>
          </div>
        </div>
      </Section>

      <Section
        title="Operational Surfaces"
        subtitle="列表允许更高信息密度，但详情和解释层必须更松弛。推荐默认使用“列表 + 详情抽屉”模式。"
      >
        <div className="grid gap-6 lg:grid-cols-[0.92fr_1.08fr]">
          <div className="df-surface-muted p-4">
            <div className="mb-3 text-sm font-semibold text-[var(--df-text)]">字段列表</div>
            <div className="space-y-2">
              {[
                ['user_id', 'TEXT', '事实'],
                ['birth_date', 'TEXT', '候选'],
                ['province_name', 'TEXT', '待补充'],
              ].map(([name, type, state]) => (
                <div key={name} className="flex items-center justify-between rounded-2xl border border-[var(--df-border)] bg-white px-3 py-3">
                  <div>
                    <div className="df-mono text-sm text-[var(--df-text)]">{name}</div>
                    <div className="mt-1 text-xs text-[var(--df-text-soft)]">{type}</div>
                  </div>
                  <Chip label={state} tone={state === '事实' ? 'fact' : state === '候选' ? 'candidate' : 'brief'} />
                </div>
              ))}
            </div>
          </div>

          <div className="df-surface-muted p-5">
            <div className="mb-4 flex items-start justify-between gap-4">
              <div>
                <div className="text-xs uppercase tracking-[0.18em] text-[var(--df-text-soft)]">Field Detail Drawer</div>
                <div className="df-display mt-2 text-2xl font-semibold tracking-tight text-[var(--df-text)]">birth_date</div>
              </div>
              <Chip label="时间候选" tone="candidate" />
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-2xl border border-[var(--df-border)] bg-white p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-[var(--df-text-soft)]">事实</div>
                <div className="mt-3 text-sm leading-7 text-[var(--df-text)]">TEXT，nullable = false，来自 customer_profile。</div>
              </div>
              <div className="rounded-2xl border border-[var(--df-border)] bg-white p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-[var(--df-text-soft)]">证据</div>
                <div className="df-mono mt-3 whitespace-pre-line text-xs leading-6 text-[var(--df-text-muted)]">
                  {'null_ratio=0.00\n'}
                  {'distinct_ratio=0.94'}
                </div>
              </div>
              <div className="rounded-2xl border border-[var(--df-border)] bg-white p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-[var(--df-text-soft)]">候选</div>
                <div className="mt-3 text-sm leading-7 text-[var(--df-text)]">可用于年龄计算，但仍需确认按自然年龄还是年龄段聚合。</div>
              </div>
              <div className="rounded-2xl border border-[var(--df-border)] bg-white p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-[var(--df-text-soft)]">知识</div>
                <div className="mt-3 text-sm leading-7 text-[var(--df-text)]">当前暂无字段级说明，建议在确认年龄口径后沉淀为正式知识对象。</div>
              </div>
            </div>
          </div>
        </div>
      </Section>
    </div>
  )
}
