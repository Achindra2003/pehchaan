import { useCallback, useEffect, useState } from 'react'
import { getCopilot, getStats, getUsage, getVerification, imageUrl, listVerifications, review } from '../api/client'
import type { Copilot, Stats, Usage, VerificationResult, VerificationSummary } from '../api/types'
import { Card, DecisionBadge, EvidenceLedger, LevelLadder, ReasonList } from './ui'

export default function Console() {
  const [queue, setQueue] = useState<VerificationSummary[]>([])
  const [openOnly, setOpenOnly] = useState(true)
  const [stats, setStats] = useState<Stats | null>(null)
  const [usage, setUsage] = useState<Usage | null>(null)
  const [selected, setSelected] = useState<VerificationResult | null>(null)
  const [copilot, setCopilot] = useState<Copilot | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [rows, s, u] = await Promise.all([listVerifications(openOnly), getStats(), getUsage()])
      setQueue(rows)
      setStats(s)
      setUsage(u)
    } catch (exc) {
      setError((exc as Error).message)
    }
  }, [openOnly])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 5000)
    return () => clearInterval(timer)
  }, [refresh])

  async function open(id: string) {
    setCopilot(null)
    setSelected(await getVerification(id))
    getCopilot(id).then(setCopilot).catch(() => setCopilot(null))
  }

  async function decide(action: string) {
    if (!selected) return
    setSelected(await review(selected.verification_id, action, 'organiser@hackingly'))
    refresh()
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Registrations" value={stats?.total ?? '—'} />
        <Stat
          label="Auto-verified"
          value={stats?.auto_verified_rate != null ? `${Math.round(stats.auto_verified_rate * 100)}%` : '—'}
        />
        <Stat label="Waiting for review" value={stats?.open_reviews ?? '—'} />
        <Stat label="Median time" value={stats?.p50_latency_ms != null ? `${(stats.p50_latency_ms / 1000).toFixed(1)}s` : '—'} />
        <Stat
          label="Cost each"
          value={usage?.cost_per_verification_usd != null ? `$${usage.cost_per_verification_usd.toFixed(4)}` : '—'}
        />
      </div>
      {error && <p className="text-sm text-bad">{error}</p>}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
        <Card className="max-h-[70vh] overflow-auto">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold">{openOnly ? 'Review queue' : 'All registrations'}</h2>
            <button className="text-sm text-accent underline" onClick={() => setOpenOnly(!openOnly)}>
              {openOnly ? 'Show all' : 'Show queue'}
            </button>
          </div>
          {queue.length === 0 && <p className="text-sm text-muted">Nothing here.</p>}
          <ul className="space-y-2">
            {queue.map((row) => (
              <li key={row.verification_id}>
                <button
                  onClick={() => open(row.verification_id)}
                  className={`w-full rounded-lg border p-3 text-left ${
                    selected?.verification_id === row.verification_id ? 'border-accent bg-accent-soft' : 'border-rule'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-mono text-sm">{row.registration_id}</span>
                    <DecisionBadge decision={row.decision} />
                  </div>
                  <p className="mt-1 line-clamp-2 text-sm text-muted">{row.top_reason ?? 'No blocking signals'}</p>
                  <p className="mt-1 font-mono text-[11px] text-muted">
                    L{row.evidence_level} · {Math.round(row.confidence * 100)}% · {row.evidence_source}
                    {row.flags.duplicate_suspected ? ' · duplicate' : ''}
                    {row.enforced ? '' : ' · shadow'}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          {!selected ? (
            <p className="text-sm text-muted">Pick a registration to see its evidence.</p>
          ) : (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <DecisionBadge decision={selected.decision} large />
                  <span className="font-mono text-sm text-muted">
                    {Math.round(selected.confidence * 100)}% · {selected.latency_ms} ms · {selected.policy_version}
                  </span>
                </div>
                {selected.review && (
                  <span className="text-sm text-muted">
                    {selected.review.action} by {selected.review.reviewer}
                  </span>
                )}
              </div>

              <LevelLadder level={selected.evidence_level} />

              <div className="grid gap-4 md:grid-cols-[200px_minmax(0,1fr)]">
                <img
                  src={imageUrl(selected.verification_id, 'id')}
                  alt="Uploaded ID"
                  className="w-full rounded-lg border border-rule bg-info-soft object-cover"
                  onError={(e) => ((e.target as HTMLImageElement).style.display = 'none')}
                />
                <div className="space-y-3">
                  <ReasonList reasons={selected.reasons} />
                  {copilot && (
                    <div className="rounded-lg bg-info-soft p-3 text-sm">
                      <p className="font-semibold">
                        Copilot <span className="font-normal text-muted">({copilot.source})</span>
                      </p>
                      <p className="mt-1">{copilot.summary}</p>
                      <p className="mt-1 text-muted">Suggests: {copilot.suggested_action.replace('_', ' ')}</p>
                    </div>
                  )}
                </div>
              </div>

              <details open>
                <summary className="cursor-pointer text-sm font-semibold">Evidence ledger</summary>
                <div className="mt-2 overflow-x-auto">
                  <EvidenceLedger checks={selected.checks} />
                </div>
              </details>

              <div className="flex flex-wrap gap-2 border-t border-rule pt-4">
                <button onClick={() => decide('approve')} className="rounded-lg bg-ok px-4 py-2 font-medium text-white">
                  Approve
                </button>
                <button onClick={() => decide('reject')} className="rounded-lg bg-bad px-4 py-2 font-medium text-white">
                  Reject
                </button>
                <button
                  onClick={() => decide('request_retake')}
                  className="rounded-lg border border-rule px-4 py-2 font-medium"
                >
                  Ask for a retake
                </button>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-rule bg-sheet p-3">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-0.5 text-xl font-semibold">{value}</p>
    </div>
  )
}
