export interface KnowledgeBase {
  kb_id: string
  kb_name?: string | null
  kb_desc?: string | null
  chunk_type?: string | null
  chunk_size?: number | null
  chunk_overlap_size?: number | null
  create_time?: string | null
}

export type IngestionStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED'

export interface KnowledgeFile {
  kb_id: string
  file_id: string
  file_url: string
  title: string
  file_ext?: string | null
  source_type?: string | null
  file_status?: IngestionStatus | null
  task_status?: {
    global_status?: IngestionStatus
    error?: string
  } | null
  create_time?: string | null
}

export interface UploadResult {
  document_id: string
  filename: string
  permanent_url: string
}

export type AgentEventName =
  | 'run_started'
  | 'query_planned'
  | 'retrieval_completed'
  | 'evidence_evaluated'
  | 'rerank_completed'
  | 'route_selected'
  | 'generation_started'
  | 'answer_delta'
  | 'run_completed'
  | 'run_failed'

export interface AgentReference {
  ref_id: string
  content_type: string
  filename?: string
  file_id?: string
  url?: string
  score?: number
  text_preview?: string
}

export interface AgentEvent {
  event: AgentEventName
  run_id: string
  timestamp: string
  round_no?: number | null
  data: Record<string, unknown>
}

export interface QueryImage {
  id: string
  file: File
  previewUrl: string
}

export type TurnStatus = 'streaming' | 'completed' | 'failed' | 'stopped'

export interface ChatTurn {
  id: string
  question: string
  imagePreviews: string[]
  answer: string
  references: AgentReference[]
  status: TurnStatus
  error?: string
  route?: 'llm' | 'vlm'
}

export interface ReadyStatus {
  status: string
  ready: boolean
  storage: {
    configured: boolean
    mode: string
    missing: string[]
  }
  models: Record<string, { configured: boolean; missing: string[] }>
  configuration: {
    configured: boolean
    errors: string[]
  }
}
