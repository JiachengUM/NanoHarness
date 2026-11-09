export const INPUT_SAMPLE_RATE = 16000
export const OUTPUT_SAMPLE_RATE = 24000
const CHUNK_SAMPLES = 3200

function floatTo16BitPCM(samples: ArrayLike<number>): Int16Array {
  const int16 = new Int16Array(samples.length)
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]))
    int16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
  }
  return int16
}

export class CaptureChunker {
  private pcmBuffer: number[] = []
  private resampleInputRate: number | null = null
  private resamplePosition = 0

  reset(): void {
    this.pcmBuffer = []
    this.resampleInputRate = null
    this.resamplePosition = 0
  }

  processCaptureSamples(
    samples: Float32Array,
    sampleRate: number,
    onChunk: (bytes: ArrayBuffer) => void,
  ): void {
    const downsampled = this.resample(samples, sampleRate)
    for (let i = 0; i < downsampled.length; i += 1) {
      this.pcmBuffer.push(downsampled[i])
    }

    while (this.pcmBuffer.length >= CHUNK_SAMPLES) {
      const chunk = this.pcmBuffer.splice(0, CHUNK_SAMPLES)
      const pcm = floatTo16BitPCM(chunk)
      onChunk(pcm.buffer.slice(0))
    }
  }

  private resample(samples: Float32Array, sampleRate: number): Float32Array {
    if (this.resampleInputRate !== sampleRate) {
      this.resampleInputRate = sampleRate
      this.resamplePosition = 0
    }

    if (sampleRate === INPUT_SAMPLE_RATE && this.resamplePosition === 0) {
      return samples
    }

    const ratio = sampleRate / INPUT_SAMPLE_RATE
    const output: number[] = []
    let position = this.resamplePosition
    while (position < samples.length) {
      output.push(samples[Math.floor(position)])
      position += ratio
    }

    this.resamplePosition = position - samples.length
    return Float32Array.from(output)
  }
}
