import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiRequestError, consumeSseStream, getReadyStatus } from './api'
import type { AgentEvent } from './types'

describe('consumeSseStream', () => {
  it('parses events split across transport chunks and stops at DONE', async () => {
    const encoder = new TextEncoder()
    const chunks = [
      'event: answer_delta\r\ndata: {"event":"answer_delta","run_id":"run-1",',
      '"timestamp":"2026-01-01T00:00:00Z","data":{"content":"hello"}}\r\n\r\n',
      'data: [DONE]\r\n\r\n',
    ]
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)))
        controller.close()
      },
    })
    const events: AgentEvent[] = []

    await consumeSseStream(stream, (event) => events.push(event))

    expect(events).toHaveLength(1)
    expect(events[0].event).toBe('answer_delta')
    expect(events[0].data.content).toBe('hello')
  })
})

describe('API errors', () => {
  afterEach(() => vi.restoreAllMocks())

  it('preserves the HTTP status for readiness errors', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      JSON.stringify({ detail: '模型配置缺失' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } },
    ))

    await expect(getReadyStatus()).rejects.toEqual(
      expect.objectContaining<ApiRequestError>({
        name: 'ApiRequestError',
        message: '模型配置缺失',
        status: 503,
      }),
    )
  })
})
