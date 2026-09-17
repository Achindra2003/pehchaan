import type { RegistrationForm, VerificationResult } from './types'

const API_KEY = import.meta.env.VITE_PEHCHAAN_API_KEY ?? ''

export async function health(): Promise<{ status: string; version: string }> {
  const response = await fetch('/healthz')
  if (!response.ok) throw new Error(`API unavailable (${response.status})`)
  return response.json()
}

export async function createVerification(input: {
  registrationId: string
  eventId: string
  form: RegistrationForm
  idImage: File
  selfie?: File
  attempt: number
}): Promise<VerificationResult> {
  const body = new FormData()
  body.append(
    'payload',
    JSON.stringify({ registration_id: input.registrationId, event_id: input.eventId, form: input.form }),
  )
  body.append('id_image', input.idImage)
  if (input.selfie) body.append('selfie', input.selfie)

  const response = await fetch('/v1/verifications', {
    method: 'POST',
    headers: { 'X-API-Key': API_KEY, 'Idempotency-Key': `${input.registrationId}-${input.attempt}` },
    body,
  })
  if (!response.ok) throw new Error(`Verification failed (${response.status})`)
  return response.json()
}
