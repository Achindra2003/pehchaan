// Mirrors api/src/pehchaan/domain/models.py. Keep in sync when the contract changes.

export type DocType = 'aadhaar' | 'pan' | 'voter_id' | 'passport' | 'driving_licence' | 'college_id' | 'unknown'
export type Decision = 'verified' | 'needs_review' | 'action_required' | 'not_eligible'
export type Effect = 'info' | 'penalty' | 'review' | 'action' | 'reject'
export type CheckStatus = 'pass' | 'warn' | 'fail' | 'skipped' | 'error'
export type EvidenceSource = 'document' | 'pass' | 'aadhaar_app'
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

export interface CheckResult {
  check: string
  status: CheckStatus
  findings: { code: string; params: Record<string, string | number> }[]
  duration_ms: number
  details: Record<string, unknown>
}

export interface Flags {
  minor: boolean
  guardian_consent_required: boolean
  duplicate_suspected: boolean
}

export interface DocumentSummary {
  type: DocType
  id_last4: string | null
  age_on_event_date: number | null
}

export interface VerificationResult {
  verification_id: string
  registration_id: string
  event_id: string
  decision: Decision
  automated_decision: Decision
  enforced: boolean
  confidence: number
  evidence_level: EvidenceLevel
  evidence_source: EvidenceSource
  reasons: Reason[]
  actions: Action[]
  flags: Flags
  document: DocumentSummary
  policy_version: string
  checks: CheckResult[]
  review: { action: string; reviewer: string; note: string; reviewed_at: string } | null
  usage: { ocr_provider: string | null; compute_ms: number; estimated_cost_usd: number }
  pehchaan_pass: { pass_id: string; token: string; level: EvidenceLevel; expires_at: string } | null
  latency_ms: number
  created_at: string
}

export interface VerificationSummary {
  verification_id: string
  registration_id: string
  event_id: string
  decision: Decision
  automated_decision: Decision
  confidence: number
  evidence_level: EvidenceLevel
  flags: Flags
  document: DocumentSummary
  evidence_source: EvidenceSource
  enforced: boolean
  reviewed: boolean
  priority: number
  top_reason: string | null
  created_at: string
}

export interface EventPolicy {
  event_id: string
  title: string
  event_date: string
  min_age: number | null
  max_age: number | null
  student_only: boolean
  require_selfie: boolean
  mode: 'enforce' | 'shadow'
}

export interface Stats {
  total: number
  by_decision: Record<Decision, number>
  auto_verified_rate: number | null
  open_reviews: number
  p50_latency_ms: number | null
  p95_latency_ms: number | null
}

export interface Usage {
  verifications: number
  estimated_cost_usd: number
  cost_per_verification_usd: number | null
  manual_review_minutes_avoided: number
  passes_issued: number
}

export interface Copilot {
  summary: string
  suggested_action: 'approve' | 'reject' | 'request_retake' | 'investigate'
  source: 'llm' | 'rules'
}

export interface DemoSample {
  file: string
  label: string
  name: string
  dob: string
  event: string
  note: string
}
