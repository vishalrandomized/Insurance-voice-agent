import { base64ToArrayBuffer, INPUT_SAMPLE_RATE } from "./pcm";

export class StreamingAudioPlayer {
  private context: AudioContext | null = null;
  private nextStartTime = 0;
  private generationId = 0;
  private sources = new Set<AudioBufferSourceNode>();

  private async getContext(): Promise<AudioContext> {
    if (!this.context) {
      // Match the context rate to the incoming PCM rate so each chunk plays
      // natively: no per-chunk resampling means contiguous chunks join
      // sample-exactly with no boundary clicks. Falls back to the default
      // rate if the browser refuses a custom rate.
      try {
        this.context = new AudioContext({ sampleRate: INPUT_SAMPLE_RATE });
      } catch {
        this.context = new AudioContext();
      }
    }
    await this.context.resume();
    return this.context;
  }

  // Create and unlock the AudioContext while a user gesture is still on the
  // call stack (e.g. the "Start conversation" click). Browsers will not start
  // audio for a context first touched later from an async WebSocket callback.
  async prime(): Promise<void> {
    await this.getContext();
  }

  setGeneration(generationId: number): void {
    if (generationId <= this.generationId) return;
    this.stop();
    this.generationId = generationId;
  }

  async enqueue(base64Audio: string, generationId: number): Promise<void> {
    if (generationId < this.generationId) return;
    if (generationId > this.generationId) this.setGeneration(generationId);

    const context = await this.getContext();
    if (generationId !== this.generationId) return;

    const pcmBuffer = base64ToArrayBuffer(base64Audio);
    const pcm = decodePcm16(pcmBuffer);
    const buffer = context.createBuffer(1, pcm.length, INPUT_SAMPLE_RATE);
    const channel = buffer.getChannelData(0);

    for (let index = 0; index < pcm.length; index += 1) {
      channel[index] = pcm[index] ?? 0;
    }

    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);

    const startAt = Math.max(context.currentTime + 0.06, this.nextStartTime);
    this.nextStartTime = startAt + buffer.duration;
    this.sources.add(source);
    source.onended = () => this.sources.delete(source);
    source.start(startAt);
  }

  // Milliseconds of audio still scheduled to play. Used by the session to
  // know when the agent has finished speaking so it can re-open the mic.
  getRemainingMs(): number {
    if (!this.context) return 0;
    return Math.max(0, (this.nextStartTime - this.context.currentTime) * 1000);
  }

  stop(): void {
    this.sources.forEach((source) => {
      try {
        source.stop();
      } catch {
        // The node may already have completed.
      }
    });
    this.sources.clear();
    this.nextStartTime = 0;
  }

  async close(): Promise<void> {
    this.stop();
    await this.context?.close();
    this.context = null;
  }
}

function decodePcm16(buffer: ArrayBuffer): Float32Array {
  const view = new DataView(buffer);
  const samples = new Float32Array(buffer.byteLength / 2);
  for (let index = 0; index < samples.length; index += 1) {
    samples[index] = view.getInt16(index * 2, true) / 0x8000;
  }
  return samples;
}
