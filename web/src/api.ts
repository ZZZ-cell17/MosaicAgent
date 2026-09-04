import type {
  AgentEvent,
  KnowledgeBase,
  KnowledgeFile,
  ReadyStatus,
  UploadResult,
} from './types'

const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/$/, '')
const API_BASE = configuredBase || ''

interface ApiEnvelope<T> {
  code: number
  msg: string
  data: T
}

export class ApiRequestError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
  }
}

function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}

async function responseError(response: Response): Promise<Error> {
  try {
    const payload = (await response.json()) as { detail?: string; message?: string }
    return new ApiRequestError(
      payload.detail || payload.message || `请求失败 (${response.status})`,
      response.status,
    )
  } catch {
    return new ApiRequestError(`请求失败 (${response.status})`, response.status)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), init)
  if (!response.ok) {
    throw await responseError(response)
  }
  return (await response.json()) as T
}

export function getReadyStatus(): Promise<ReadyStatus> {
  return request<ReadyStatus>('/ready')
}

export async function listKnowledgeBases(): Promise<KnowledgeBase[]> {
  const response = await request<ApiEnvelope<{ list: KnowledgeBase[] }>>(
    '/v1/documents/list_knowledge_base',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page_no: 1, page_size: 100 }),
    },
  )
  return response.data.list
}

export async function createKnowledgeBase(input: {
  kb_id?: string
  kb_name: string
  kb_desc?: string
}): Promise<KnowledgeBase> {
  const response = await request<ApiEnvelope<KnowledgeBase>>(
    '/v1/documents/create_knowledge_base',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...input, chunk_type: 'markdown' }),
    },
  )
  return response.data
}

export async function deleteKnowledgeBase(kbId: string): Promise<void> {
  await request('/v1/documents/delete_knowledge_base', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kb_id: kbId }),
  })
}

export async function listKnowledgeFiles(kbId: string): Promise<KnowledgeFile[]> {
  const response = await request<ApiEnvelope<{ records: KnowledgeFile[] }>>(
    '/v1/documents/list_kb_files',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kb_id: kbId, page_no: 1, page_size: 100 }),
    },
  )
  return response.data.records
}

export async function uploadDocument(file: File): Promise<UploadResult> {
  const form = new FormData()
  form.append('file', file)
  const response = await request<{
    success: boolean
    data: UploadResult
  }>('/v1/documents/upload', { method: 'POST', body: form })
  return response.data
}

export async function addUploadedFiles(
  kbId: string,
  uploads: Array<Pick<UploadResult, 'document_id' | 'filename'>>,
): Promise<void> {
  await request('/v1/documents/add_files', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kb_id: kbId, files: uploads }),
  })
}

export async function deleteKnowledgeFile(kbId: string, fileId: string): Promise<void> {
  await request('/v1/documents/delete_files', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kb_id: kbId, file_ids: [fileId] }),
  })
}

export async function consumeSseStream(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: AgentEvent) => void,
): Promise<void> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const consumeBlock = (block: string): boolean => {
    const data = block
      .split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n')
    if (!data) return false
    if (data === '[DONE]') return true
    onEvent(JSON.parse(data) as AgentEvent)
    return false
  }

  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() || ''
    if (blocks.some(consumeBlock)) return
    if (done) {
      if (buffer.trim()) consumeBlock(buffer)
      return
    }
  }
}

export async function queryAgent(
  input: {
    kbId: string
    question: string
    imageUrls: string[]
  },
  options: {
    signal: AbortSignal
    onEvent: (event: AgentEvent) => void
  },
): Promise<void> {
  const response = await fetch(apiUrl('/v1/mrag/query'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      kb_id: input.kbId,
      question: input.question,
      image_urls: input.imageUrls,
      include_trace: true,
    }),
    signal: options.signal,
  })
  if (!response.ok) throw await responseError(response)
  if (!response.body) throw new Error('浏览器未收到流式响应')
  await consumeSseStream(response.body, options.onEvent)
}
