import type { Copilot, DemoSample, EventPolicy, Stats, Usage, VerificationResult, VerificationSummary } from './types'

const KEY = import.meta.env.VITE_PEHCHAAN_API_KEY ?? 'demo-key'

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...init, headers: { 'X-API-Key': KEY, ...(init.headers ?? {}) } })
  if (!response.ok) throw new Error(await errorText(response))
  return response.json() as Promise<T>
}

async function errorText(response: Response): Promise<string> {
  try {
    const body = await response.json()
    return typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`
  } catch {
    return `Request failed (${response.status})`
  }
}

export const imageUrl = (verificationId: string, kind: 'id' | 'selfie') =>
  `/v1/verifications/${verificationId}/images/${kind}?key=${encodeURIComponent(KEY)}`

export const listEvents = () => call<EventPolicy[]>('/v1/events')

/** Demo cards served by the API so a live demo never opens a file picker. Dev only. */
export async function listSamples(): Promise<DemoSample[]> {
  const response = await fetch('/demo/samples')
  return response.ok ? response.json() : []
}

export async function loadSample(file: string): Promise<File> {
  const response = await fetch(`/demo/samples/${file}`)
  if (!response.ok) throw new Error('Could not load the demo card')
  return new File([await response.blob()], file, { type: 'image/jpeg' })
}
export const getStats = (eventId?: string) => call<Stats>(`/v1/stats${eventId ? `?event_id=${eventId}` : ''}`)
export const getUsage = () => call<Usage>('/v1/usage')
export const getVerification = (id: string) => call<VerificationResult>(`/v1/verifications/${id}`)
export const getCopilot = (id: string) => call<Copilot>(`/v1/verifications/${id}/copilot`)

export const listVerifications = (openOnly: boolean) =>
  call<VerificationSummary[]>(`/v1/verifications?limit=50${openOnly ? '&open_only=true' : ''}`)

export const review = (id: string, action: string, reviewer: string, note = '') =>
  call<VerificationResult>(`/v1/verifications/${id}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, reviewer, note }),
  })

export interface SubmitInput {
  registrationId: string
  eventId: string
  name: string
  dob?: string
  email?: string
  subjectId?: string
  idImage: File
  selfie?: File | null
  idFromCamera: boolean
  selfieFromCamera: boolean
}

export async function submitVerification(input: SubmitInput): Promise<VerificationResult> {
  const body = new FormData()
  body.append(
    'payload',
    JSON.stringify({
      registration_id: input.registrationId,
      event_id: input.eventId,
      subject_id: input.subjectId || undefined,
      form: { name: input.name, dob: input.dob || undefined, email: input.email || undefined },
      capture: {
        id_source: input.idFromCamera ? 'camera' : 'upload',
        selfie_source: input.selfie ? (input.selfieFromCamera ? 'camera' : 'upload') : 'unknown',
      },
      consent: { accepted: true, notice_version: 'hackingly-idv-2026-09', accepted_at: new Date().toISOString() },
    }),
  )
  body.append('id_image', input.idImage)
  if (input.selfie) body.append('selfie', input.selfie)

  const response = await fetch('/v1/verifications', {
    method: 'POST',
    headers: { 'X-API-Key': KEY, 'Idempotency-Key': `${input.registrationId}-${Date.now()}` },
    body,
  })
  if (response.status === 202) return pollJob((await response.json()).job_id)
  if (!response.ok) throw new Error(await errorText(response))
  return response.json()
}

async function pollJob(jobId: string): Promise<VerificationResult> {
  for (let attempt = 0; attempt < 120; attempt++) {
    await new Promise((resolve) => setTimeout(resolve, 500))
    const job = await call<{ status: string; verification_id: string | null; error: string | null }>(`/v1/jobs/${jobId}`)
    if (job.status === 'done' && job.verification_id) return getVerification(job.verification_id)
    if (job.status === 'failed') throw new Error(job.error ?? 'Verification failed')
  }
  throw new Error('Verification is taking longer than usual')
}
