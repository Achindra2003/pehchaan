import type { CheckResult, Decision, EvidenceLevel, Reason } from '../api/types'

const DECISION_STYLE: Record<Decision, { label: string; className: string }> = {
  verified: { label: 'Verified', className: 'bg-ok-soft text-ok' },
  needs_review: { label: 'Needs review', className: 'bg-warn-soft text-warn' },
  action_required: { label: 'Action required', className: 'bg-accent-soft text-accent' },
  not_eligible: { label: 'Not eligible', className: 'bg-bad-soft text-bad' },
}

const LEVELS: { level: EvidenceLevel; name: string; hint: string }[] = [
  { level: 0, name: 'L0', hint: 'Unusable' },
  { level: 1, name: 'L1', hint: 'Read' },
  { level: 2, name: 'L2', hint: 'Consistent' },
  { level: 3, name: 'L3', hint: 'Proven' },
  { level: 4, name: 'L4', hint: 'Present' },
]

const STATUS_STYLE: Record<string, string> = {
  pass: 'text-ok',
  warn: 'text-warn',
  fail: 'text-bad',
  error: 'text-bad',
  skipped: 'text-muted',
}

export function DecisionBadge({ decision, large = false }: { decision: Decision; large?: boolean }) {
  const style = DECISION_STYLE[decision]
  return (
    <span
      className={`inline-block rounded-full font-semibold ${style.className} ${large ? 'px-4 py-1.5 text-lg' : 'px-2.5 py-0.5 text-sm'}`}
    >
      {style.label}
    </span>
  )
}

export function LevelLadder({ level }: { level: EvidenceLevel }) {
  return (
    <div className="flex gap-1.5" aria-label={`Evidence level ${level} of 4`}>
      {LEVELS.map((step) => (
        <div key={step.name} className="flex-1 text-center">
          <div className={`h-1.5 rounded-full ${step.level <= level ? 'bg-accent' : 'bg-rule'}`} />
          <div className={`mt-1 font-mono text-[11px] ${step.level <= level ? 'text-accent' : 'text-muted'}`}>
            {step.name}
          </div>
          <div className="text-[10px] text-muted">{step.hint}</div>
        </div>
      ))}
    </div>
  )
}

export function ReasonList({ reasons }: { reasons: Reason[] }) {
  const shown = reasons.filter((reason) => reason.effect !== 'info')
  if (shown.length === 0) return <p className="text-sm text-muted">Every check passed with nothing to flag.</p>
  return (
    <ul className="space-y-2">
      {shown.map((reason) => (
        <li key={reason.code} className="flex gap-2 text-sm">
          <span aria-hidden className={reason.effect === 'reject' ? 'text-bad' : 'text-warn'}>
            ●
          </span>
          <span>
            {reason.message}
            <span className="ml-1.5 font-mono text-[11px] text-muted">[{reason.check}]</span>
          </span>
        </li>
      ))}
    </ul>
  )
}

export function EvidenceLedger({ checks }: { checks: CheckResult[] }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-rule text-left font-mono text-[11px] tracking-wide text-muted uppercase">
          <th className="py-1.5">Check</th>
          <th>Result</th>
          <th>Findings</th>
          <th className="text-right">ms</th>
        </tr>
      </thead>
      <tbody>
        {checks.map((check) => (
          <tr key={check.check} className="border-b border-rule/60">
            <td className="py-1.5 font-mono text-[12px]">{check.check}</td>
            <td className={`font-medium ${STATUS_STYLE[check.status] ?? ''}`}>{check.status}</td>
            <td className="font-mono text-[11px] text-muted">
              {check.findings.map((f) => f.code).join(', ') || '—'}
            </td>
            <td className="text-right font-mono text-[11px] text-muted">{check.duration_ms}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <section className={`rounded-xl border border-rule bg-sheet p-5 ${className}`}>{children}</section>
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-muted">{label}</span>
      {children}
    </label>
  )
}

export const inputClass =
  'w-full rounded-lg border border-rule bg-sheet px-3 py-2.5 text-base outline-none focus:border-accent focus:ring-2 focus:ring-accent/25'
