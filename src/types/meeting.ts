/**
 * Tipos TypeScript que espelham os schemas Pydantic do backend
 * (`app/api/meetings.py` e `app/api/keys.py`). Mantê-los em sync é
 * responsabilidade do dev — quando o Pydantic muda, ajustar aqui.
 *
 * Convenção: nomes BEM próximos do Pydantic (snake_case nos campos JSON,
 * camelCase só nos helpers). Datas vêm como string ISO 8601.
 */

// =============================================================
// Meetings
// =============================================================

export type MeetingStatus =
  | "pending"
  | "converting"
  | "detecting_speech"
  | "chunking"
  | "transcribing"
  | "diarizing"
  | "generating_minutes"
  | "validating"
  | "completed"
  | "failed";

export interface MeetingListItem {
  id: string;
  title: string | null;
  original_filename: string | null;
  duration_sec: number | null;
  file_size_bytes: number | null;
  language: string;
  source: string;
  status: MeetingStatus;
  created_at: string;
}

export interface MeetingListResponse {
  meetings: MeetingListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface MeetingStatusResponse {
  id: string;
  status: MeetingStatus;
  error: string | null;
  error_type: string | null;
}

export interface Evidence {
  quote: string;
  speaker: string | null;
  timestamp_sec: number | null;
}

export interface DecisionItem {
  id: string;
  description: string;
  evidence: Evidence | null;
}

export interface ActionItem {
  id: string;
  description: string;
  assigned_to: string | null;
  deadline_raw: string | null;
  deadline_parsed: string | null; // ISO date YYYY-MM-DD
  priority: "low" | "normal" | "high";
  status: "pending" | "done" | "cancelled";
  evidence: Evidence | null;
}

export interface TopicJson {
  title: string;
  summary: string;
  evidence: {
    quote: string;
    speaker?: string | null;
    timestamp_sec?: number | null;
  };
}

export interface Minutes {
  id: string;
  title: string;
  date_extracted: string | null;
  executive_summary: string;
  participants: string[];
  topics: TopicJson[];
  open_questions: string[];
  decisions: DecisionItem[];
  action_items: ActionItem[];
  llm_provider: string;
  llm_model: string;
  tokens_input: number;
  tokens_output: number;
  cost_usd: number;
  validation_passed: boolean;
  validation_issues: Record<string, unknown>[] | null;
}

export interface TranscriptSegment {
  start_sec: number;
  end_sec: number;
  text: string;
  speaker_id: string | null;
  confidence: number | null;
}

export interface Transcript {
  id: string;
  full_text: string;
  language_detected: string | null;
  provider_used: string;
  model_used: string;
  word_count: number | null;
  segments: TranscriptSegment[];
}

export interface MeetingDetail {
  id: string;
  title: string | null;
  original_filename: string | null;
  audio_path: string;
  audio_hash: string;
  duration_sec: number | null;
  file_size_bytes: number | null;
  language: string;
  source: string;
  status: MeetingStatus;
  speaker_map: Record<string, string> | null;
  extra_metadata: Record<string, unknown> | null;
  started_at: string | null;
  created_at: string;
  updated_at: string | null;
  transcript: Transcript | null;
  minutes: Minutes | null;
}

export interface MeetingCreated {
  id: string;
  status: MeetingStatus;
  title: string | null;
  original_filename: string;
  file_size_bytes: number;
}

export interface SpeakerMap {
  id: string;
  speaker_map: Record<string, string>;
}

export interface DeleteResponse {
  id: string;
  deleted: boolean;
}

// =============================================================
// API keys
// =============================================================

export type ApiKeyProvider =
  | "groq"
  | "assemblyai"
  | "anthropic"
  | "openai"
  | "google";

export interface ProviderStatus {
  provider: ApiKeyProvider;
  is_configured: boolean;
  last_validated_at: string | null;
  last_validation_status: "success" | "failed" | "invalid" | null;
  notes: string | null;
}

export interface ProvidersListResponse {
  providers: ProviderStatus[];
}

export interface SimpleStatusResponse {
  provider: ApiKeyProvider;
  is_configured: boolean;
}
