// Mirrors api/src/pehchaan/domain/models.py. Keep in sync when the contract changes.

export type DocType = 'aadhaar' | 'pan' | 'voter_id' | 'passport' | 'driving_licence' | 'college_id' | 'unknown'
export type Decision = 'verified' | 'needs_review' | 'action_required' | 'not_eligible'
export type Effect = 'info' | 'penalty' | 'review' | 'action' | 'reject'
export type CheckStatus = 'pass' | 'warn' | 'fail' | 'skipped' | 'error'
export type Action =
  | 'retake_id_photo'
  | 'use_original_document'
  | 'upload_accepted_document'
  | 'upload_college_id'
  | 'retake_selfie'

/** 0 unusable · 1 read · 2 consistent · 3 proven · 4 present */
export type EvidenceLevel = 0 | 1 | 2 | 3 | 4

export interface Reason {
  code: string
  effect: Effect
  check: string
  message: string
}

export interface Finding {
  code: string
  params: Record<string, string | number>
}

export interface CheckResult {
  check: string
  status: CheckStatus
  findings: Finding[]
  duration_ms: number
  details: Record<string, unknown>
}

export interface VerificationResult {
  verification_id: string
  registration_id: string
  event_id: string
  decision: Decision
  confidence: number
  evidence_level: EvidenceLevel
  reasons: Reason[]
  actions: Action[]
  flags: { minor: boolean; guardian_consent_required: boolean; duplicate_suspected: boolean }
  document: { type: DocType; id_last4: string | null; age_on_event_date: number | null }
  policy_version: string
  checks: CheckResult[]
  created_at: string
}

export interface RegistrationForm {
  name: string
  dob?: string
  email?: string
  phone?: string
  institution?: string
}
