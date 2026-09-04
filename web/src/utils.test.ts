import { afterEach, describe, expect, it, vi } from 'vitest'

import { createClientId } from './utils'

describe('createClientId', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('returns a non-empty client identifier', () => {
    expect(createClientId('test')).toMatch(/.+/)
  })

  it('falls back when randomUUID is unavailable', () => {
    vi.stubGlobal('crypto', {})
    vi.spyOn(Date, 'now').mockReturnValue(123456)
    vi.spyOn(Math, 'random').mockReturnValue(0.25)

    expect(createClientId('test')).toMatch(/^test-2n9c-/)
  })
})
