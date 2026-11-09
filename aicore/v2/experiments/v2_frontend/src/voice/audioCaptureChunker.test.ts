import { describe, expect, test } from 'vitest'
import { CaptureChunker } from './audioCaptureChunker'

describe('CaptureChunker', () => {
  test('buffers two half chunks into one 6400-byte mic chunk', () => {
    const chunker = new CaptureChunker()
    const chunks: ArrayBuffer[] = []

    chunker.processCaptureSamples(new Float32Array(1600).fill(0.25), 16000, (chunk) => {
      chunks.push(chunk)
    })
    chunker.processCaptureSamples(new Float32Array(1600).fill(-0.25), 16000, (chunk) => {
      chunks.push(chunk)
    })

    expect(chunks).toHaveLength(1)
    expect(chunks[0].byteLength).toBe(6400)
    expect(Array.from(new Int16Array(chunks[0]).slice(0, 3))).toEqual([8191, 8191, 8191])
    expect(Array.from(new Int16Array(chunks[0]).slice(3197, 3200))).toEqual([
      -8192,
      -8192,
      -8192,
    ])
  })

  test('preserves fractional capture resampling progress across callbacks', () => {
    const chunker = new CaptureChunker()
    const chunks: ArrayBuffer[] = []

    for (let i = 0; i < 4; i += 1) {
      chunker.processCaptureSamples(new Float32Array(2205).fill(0.1), 44100, (chunk) => {
        chunks.push(chunk)
      })
    }

    expect(chunks).toHaveLength(1)
    expect(chunks[0].byteLength).toBe(6400)
  })

  test('does not lose fractional capture samples across short 44100 Hz callbacks', () => {
    const chunker = new CaptureChunker()
    const chunks: ArrayBuffer[] = []

    for (let i = 0; i < 196; i += 1) {
      chunker.processCaptureSamples(new Float32Array(45).fill(0.1), 44100, (chunk) => {
        chunks.push(chunk)
      })
    }

    expect(chunks).toHaveLength(1)
    expect(chunks[0].byteLength).toBe(6400)
  })

  test('emits two chunks from one 6400-sample callback at 16000 Hz', () => {
    const chunker = new CaptureChunker()
    const chunks: ArrayBuffer[] = []

    chunker.processCaptureSamples(new Float32Array(6400).fill(0.2), 16000, (chunk) => {
      chunks.push(chunk)
    })

    expect(chunks).toHaveLength(2)
    expect(chunks.every((chunk) => chunk.byteLength === 6400)).toBe(true)
  })

  test('reset clears buffered partial samples', () => {
    const chunker = new CaptureChunker()
    const chunks: ArrayBuffer[] = []

    chunker.processCaptureSamples(new Float32Array(1600).fill(0.5), 16000, (chunk) => {
      chunks.push(chunk)
    })
    chunker.reset()
    chunker.processCaptureSamples(new Float32Array(1600).fill(0.5), 16000, (chunk) => {
      chunks.push(chunk)
    })

    expect(chunks).toHaveLength(0)
  })
})
