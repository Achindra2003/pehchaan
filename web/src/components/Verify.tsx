import { useEffect, useState } from 'react'
import { listEvents, listSamples, loadSample, submitVerification } from '../api/client'
import type { DemoSample, EventPolicy, VerificationResult } from '../api/types'
import { checkCapture } from '../lib/quality'
import SelfieCapture from './SelfieCapture'
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
  const [samples, setSamples] = useState<DemoSample[]>([])
  const [eventId, setEventId] = useState('')
  const [name, setName] = useState('')
  const [dob, setDob] = useState('')
  const [consent, setConsent] = useState(false)
  const [idImage, setIdImage] = useState<File | null>(null)
  const [selfie, setSelfie] = useState<File | null>(null)
  const [selfieSource, setSelfieSource] = useState<'camera' | 'upload'>('upload')
  const [captureWarning, setCaptureWarning] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<VerificationResult | null>(null)

  useEffect(() => {
    listEvents()
      .then((policies) => {
        setEvents(policies)
        setEventId((current) => current || policies[0]?.event_id || '')
      })
      .catch((exc: Error) => setError(exc.message))
    listSamples().then(setSamples).catch(() => setSamples([]))
  }, [])

  async function onPickId(file: File | null) {
    setIdImage(file)
    setCaptureWarning(null)
    if (file && file.type.startsWith('image/')) {
      setCaptureWarning((await checkCapture(file)).warning)
    }
  }

  async function verify(input: { name: string; dob: string; eventId: string; image: File; selfieFile?: File | null }) {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      setResult(
        await submitVerification({
          registrationId: `reg-${Date.now()}`,
          eventId: input.eventId,
          name: input.name,
          dob: input.dob,
          subjectId: input.name.toLowerCase().replace(/\s+/g, '-'),
          idImage: input.image,
          selfie: input.selfieFile ?? null,
          // A file input can't tell us whether the camera or the gallery produced this, so we don't claim it did.
          idFromCamera: false,
          selfieFromCamera: selfieSource === 'camera',
        }),
      )
    } catch (exc) {
      setError((exc as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function runSample(sample: DemoSample) {
    setName(sample.name)
    setDob(sample.dob)
    setEventId(sample.event)
    setConsent(true)
    setCaptureWarning(null)
    try {
      const image = await loadSample(sample.file)
      setIdImage(image)
      await verify({ name: sample.name, dob: sample.dob, eventId: sample.event, image })
    } catch (exc) {
      setError((exc as Error).message)
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
                `${policy.event_date}`,
                policy.min_age ? `${policy.min_age}+` : null,
                policy.max_age ? `up to ${policy.max_age}` : null,
                policy.student_only ? 'students only' : null,
                policy.mode === 'shadow' ? 'shadow mode: decisions recorded, not enforced' : null,
              ]
                .filter(Boolean)
                .join(' · ')
            : 'Pick an event'}
        </p>

        {samples.length > 0 && (
          <div className="mt-4 rounded-lg border border-dashed border-rule p-3">
            <p className="text-xs font-semibold tracking-wide text-muted uppercase">Demo cards (synthetic specimens)</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {samples.map((sample) => (
                <button
                  key={sample.file}
                  type="button"
                  disabled={busy}
                  title={sample.note}
                  onClick={() => runSample(sample)}
                  className="rounded-full border border-rule px-3 py-1 text-sm hover:border-accent hover:text-accent disabled:opacity-40"
                >
                  {sample.label}
                </button>
              ))}
            </div>
          </div>
        )}

        <form
          className="mt-4 space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (idImage) verify({ name, dob, eventId, image: idImage, selfieFile: selfie })
          }}
        >
          <Field label="Event">
            <select className={inputClass} value={eventId} onChange={(e) => setEventId(e.target.value)}>
              {events.map((event) => (
                <option key={event.event_id} value={event.event_id}>
                  {event.title || event.event_id}
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
              className={inputClass}
              type="file"
              accept="image/*,application/pdf"
              capture="environment"
              onChange={(e) => onPickId(e.target.files?.[0] ?? null)}
            />
          </Field>
          <SelfieCapture
            onCapture={(file, source) => {
              setSelfie(file)
              setSelfieSource(source)
            }}
          />

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
            />
            <span>
              I agree that my ID may be checked to confirm I am eligible for this event. It is deleted after the
              event, and only kept longer if a person needs to review it.
            </span>
          </label>

          <button
            type="submit"
            disabled={busy || !idImage || !consent}
            className="w-full rounded-lg bg-accent px-4 py-3 font-semibold text-white transition disabled:opacity-40"
          >
            {busy ? 'Checking…' : 'Verify me'}
          </button>
          {error && <p className="text-sm text-bad">{error}</p>}
        </form>
      </Card>

      <Card>
        {busy ? (
          <Working />
        ) : !result ? (
          <p className="text-sm text-muted">
            Your result appears here: the decision, how sure we are, and the reason for it.
          </p>
        ) : (
          <Result result={result} />
        )}
      </Card>
    </div>
  )
}

function Working() {
  return (
    <div className="space-y-3">
      <div className="h-6 w-40 animate-pulse rounded bg-info-soft" />
      <div className="h-2 w-full animate-pulse rounded bg-info-soft" />
      <p className="text-sm text-muted">Reading the document, checking the signature, looking for duplicates…</p>
    </div>
  )
}

function Result({ result }: { result: VerificationResult }) {
  const passed = result.checks.filter((check) => check.status === 'pass').length
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <DecisionBadge decision={result.decision} large />
        <span className="font-mono text-sm text-muted">
          {Math.round(result.confidence * 100)}% sure · {(result.latency_ms / 1000).toFixed(1)}s
        </span>
      </div>

      <div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-info-soft">
          <div
            className={`h-full ${result.decision === 'not_eligible' ? 'bg-bad' : result.decision === 'verified' ? 'bg-ok' : 'bg-warn'}`}
            style={{ width: `${Math.round(result.confidence * 100)}%` }}
          />
        </div>
        <p className="mt-1 text-xs text-muted">
          {passed} of {result.checks.length} checks passed · evidence from {result.evidence_source.replace('_', ' ')}
        </p>
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
        {result.flags.duplicate_suspected && (
          <div className="col-span-2 rounded-lg bg-warn-soft px-3 py-2 text-warn">
            This ID, photo or face appears on another registration. Both are waiting for a person to look.
          </div>
        )}
        {result.pehchaan_pass && (
          <div className="col-span-2 rounded-lg bg-ok-soft px-3 py-2 text-ok">
            Pehchaan Pass issued: the next Hackingly event skips this check entirely, at no OCR cost.
          </div>
        )}
        {!result.enforced && (
          <div className="col-span-2 rounded-lg bg-info-soft px-3 py-2 text-muted">
            Shadow mode: this decision was recorded for comparison, not enforced.
          </div>
        )}
      </dl>
    </div>
  )
}
