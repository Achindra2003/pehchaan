import { useEffect, useRef, useState } from 'react'
import { listEvents, submitVerification } from '../api/client'
import type { EventPolicy, VerificationResult } from '../api/types'
import { checkCapture } from '../lib/quality'
import { Card, DecisionBadge, Field, LevelLadder, ReasonList, inputClass } from './ui'

const ACTION_LABEL: Record<string, string> = {
  retake_id_photo: 'Take the ID photo again',
  use_original_document: 'Photograph the physical card, or upload the e-Aadhaar PDF',
  upload_accepted_document: 'Upload a different document',
  upload_college_id: 'Upload your college ID',
  retake_selfie: 'Take the selfie again',
}

export default function Verify() {
  const [events, setEvents] = useState<EventPolicy[]>([])
  const [eventId, setEventId] = useState('')
  const [name, setName] = useState('')
  const [dob, setDob] = useState('')
  const [consent, setConsent] = useState(false)
  const [idImage, setIdImage] = useState<File | null>(null)
  const [selfie, setSelfie] = useState<File | null>(null)
  const [captureWarning, setCaptureWarning] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<VerificationResult | null>(null)
  const idInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    listEvents()
      .then((policies) => {
        setEvents(policies)
        setEventId((current) => current || policies[0]?.event_id || '')
      })
      .catch((exc: Error) => setError(exc.message))
  }, [])

  async function onPickId(file: File | null) {
    setIdImage(file)
    setCaptureWarning(null)
    if (file && file.type.startsWith('image/')) {
      const check = await checkCapture(file)
      setCaptureWarning(check.warning)
    }
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!idImage) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      setResult(
        await submitVerification({
          registrationId: `reg-${Date.now()}`,
          eventId,
          name,
          dob,
          subjectId: name.toLowerCase().replace(/\s+/g, '-'),
          idImage,
          selfie,
          idFromCamera: Boolean(idInput.current?.getAttribute('capture')),
          selfieFromCamera: true,
        }),
      )
    } catch (exc) {
      setError((exc as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const policy = events.find((e) => e.event_id === eventId)

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <Card>
        <h2 className="text-lg font-semibold">Register</h2>
        <p className="mt-1 text-sm text-muted">
          {policy
            ? [
                `Event on ${policy.event_date}`,
                policy.min_age ? `${policy.min_age}+` : null,
                policy.max_age ? `up to ${policy.max_age}` : null,
                policy.student_only ? 'students only' : null,
                policy.mode === 'shadow' ? 'shadow mode' : null,
              ]
                .filter(Boolean)
                .join(' · ')
            : 'Pick an event'}
        </p>

        <form className="mt-4 space-y-4" onSubmit={onSubmit}>
          <Field label="Event">
            <select className={inputClass} value={eventId} onChange={(e) => setEventId(e.target.value)}>
              {events.map((event) => (
                <option key={event.event_id} value={event.event_id}>
                  {event.event_id}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Full name">
            <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} required />
          </Field>
          <Field label="Date of birth">
            <input className={inputClass} type="date" value={dob} onChange={(e) => setDob(e.target.value)} />
          </Field>
          <Field label="Photo of your ID">
            <input
              ref={idInput}
              className={inputClass}
              type="file"
              accept="image/*,application/pdf"
              capture="environment"
              onChange={(e) => onPickId(e.target.files?.[0] ?? null)}
              required
            />
          </Field>
          <Field label="Selfie (optional)">
            <input
              className={inputClass}
              type="file"
              accept="image/*"
              capture="user"
              onChange={(e) => setSelfie(e.target.files?.[0] ?? null)}
            />
          </Field>

          {captureWarning && (
            <p className="rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn">
              {captureWarning} <span className="text-muted">(checked on your device, nothing uploaded yet)</span>
            </p>
          )}

          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              required
            />
            <span>
              I agree that my ID may be checked to confirm I am eligible for this event. It is deleted after the
              event, and only kept longer if a person needs to review it.
            </span>
          </label>

          <button
            type="submit"
            disabled={busy || !idImage || !consent}
            className="w-full rounded-lg bg-accent px-4 py-3 font-semibold text-white disabled:opacity-40"
          >
            {busy ? 'Checking…' : 'Verify me'}
          </button>
          {error && <p className="text-sm text-bad">{error}</p>}
        </form>
      </Card>

      <Card className={result ? '' : 'hidden lg:block'}>
        {!result ? (
          <p className="text-sm text-muted">Your result appears here, with the reason for it.</p>
        ) : (
          <div className="space-y-5">
            <div className="flex items-center justify-between gap-3">
              <DecisionBadge decision={result.decision} large />
              <span className="font-mono text-sm text-muted">
                {Math.round(result.confidence * 100)}% · {result.latency_ms} ms
              </span>
            </div>

            <LevelLadder level={result.evidence_level} />

            {result.actions.length > 0 && (
              <div className="rounded-lg bg-accent-soft p-3">
                <p className="text-sm font-semibold text-accent">What to do next</p>
                <ul className="mt-1 space-y-1 text-sm">
                  {result.actions.map((action) => (
                    <li key={action}>{ACTION_LABEL[action] ?? action}</li>
                  ))}
                </ul>
              </div>
            )}

            <div>
              <h3 className="text-sm font-semibold">Why</h3>
              <div className="mt-2">
                <ReasonList reasons={result.reasons} />
              </div>
            </div>

            <dl className="grid grid-cols-2 gap-3 border-t border-rule pt-4 text-sm">
              <div>
                <dt className="text-muted">Document</dt>
                <dd className="font-medium">
                  {result.document.type.replace('_', ' ')}
                  {result.document.id_last4 ? ` ••${result.document.id_last4}` : ''}
                </dd>
              </div>
              <div>
                <dt className="text-muted">Age on event date</dt>
                <dd className="font-medium">{result.document.age_on_event_date ?? '—'}</dd>
              </div>
              {result.flags.guardian_consent_required && (
                <div className="col-span-2 rounded-lg bg-warn-soft px-3 py-2 text-warn">
                  Under 18: a parent or guardian needs to consent before the event.
                </div>
              )}
              {result.pehchaan_pass && (
                <div className="col-span-2 rounded-lg bg-ok-soft px-3 py-2 text-ok">
                  Pehchaan Pass issued: the next Hackingly event skips this check entirely.
                </div>
              )}
            </dl>
          </div>
        )}
      </Card>
    </div>
  )
}
