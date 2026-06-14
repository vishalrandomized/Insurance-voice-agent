import {
  float32ToPcm16,
  INPUT_SAMPLE_RATE,
  pcm16ToBase64,
} from "./pcm";

type MicrophoneOptions = {
  onAudio: (base64Audio: string) => void;
  onVoiceStart?: () => void;
  onVoiceEnd?: () => void;
  voiceThreshold?: number;
  sustainedFrames?: number;
  silenceFrames?: number;
  // Barge-in: fired when the customer talks over the agent. Uses a SEPARATE,
  // higher threshold + longer sustained window than the normal VAD, active only
  // while the agent is speaking (toggled via setAgentSpeaking), so the agent's
  // own audio leaking past echo-cancellation won't trip it.
  onBargeIn?: () => void;
  bargeInThreshold?: number;
  bargeInSustainedMs?: number;
  bargeInHeadGraceMs?: number;
};

const WORKLET_SOURCE = `
class PcmCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (input) this.port.postMessage(input.slice(0));
    return true;
  }
}
registerProcessor("pcm-capture-processor", PcmCaptureProcessor);
`;

function downsample(
  input: Float32Array,
  sourceRate: number,
  targetRate: number,
): Float32Array {
  if (sourceRate === targetRate) return input;

  const ratio = sourceRate / targetRate;
  const outputLength = Math.max(1, Math.round(input.length / ratio));
  const output = new Float32Array(outputLength);

  for (let index = 0; index < outputLength; index += 1) {
    const start = Math.floor(index * ratio);
    const end = Math.min(input.length, Math.floor((index + 1) * ratio));
    let sum = 0;

    for (let sourceIndex = start; sourceIndex < end; sourceIndex += 1) {
      sum += input[sourceIndex] ?? 0;
    }

    output[index] = sum / Math.max(1, end - start);
  }

  return output;
}

// AssemblyAI v3 streaming requires each audio message to carry between 50 ms
// and 1000 ms of audio. A raw AudioWorklet quantum is only 128 samples
// (~2.7 ms), so we accumulate downsampled samples and flush ~100 ms at a time.
const SEND_BATCH_SAMPLES = Math.round(0.1 * INPUT_SAMPLE_RATE);

export class MicrophoneCapture {
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private worklet: AudioWorkletNode | null = null;
  private mutedSink: GainNode | null = null;
  private workletUrl: string | null = null;
  private voicedFrames = 0;
  private silentFrames = 0;
  private voiceTriggered = false;
  private sendBuffer: Float32Array[] = [];
  private sendBufferLen = 0;
  private agentSpeaking = false;
  private bargeInVoicedFrames = 0;
  private agentSpeakingSince = 0;

  /**
   * Toggle whether the agent is currently speaking. While true, the barge-in
   * detector is armed (see start()). Call true when agent audio starts, false
   * when it finishes / is interrupted.
   */
  setAgentSpeaking(speaking: boolean): void {
    if (speaking && !this.agentSpeaking) {
      this.agentSpeakingSince = this.context?.currentTime ?? 0;
    }
    this.agentSpeaking = speaking;
    this.bargeInVoicedFrames = 0;
  }

  async start(options: MicrophoneOptions): Promise<void> {
    if (this.context) return;

    const {
      onAudio,
      onVoiceStart,
      onVoiceEnd,
      onBargeIn,
      voiceThreshold = 0.04,
      bargeInThreshold = 0.1,
      bargeInSustainedMs = 180,
      bargeInHeadGraceMs = 250,
    } = options;

    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    });

    this.context = new AudioContext();
    await this.context.resume();

    // The worklet posts one 128-sample frame per callback; convert speech /
    // end-of-turn windows from milliseconds so turn-taking is natural and
    // independent of the device sample rate. ~120 ms of speech arms a turn;
    // ~700 ms of trailing silence ends it (so normal mid-sentence pauses don't
    // chop the user off — that was happening at the old ~48 ms threshold).
    const frameMs = (1000 * 128) / this.context.sampleRate;
    const sustainedFrames = options.sustainedFrames ?? Math.max(2, Math.round(120 / frameMs));
    const silenceFrames = options.silenceFrames ?? Math.max(8, Math.round(700 / frameMs));
    const bargeInSustainedFrames = Math.max(2, Math.round(bargeInSustainedMs / frameMs));

    const blob = new Blob([WORKLET_SOURCE], { type: "text/javascript" });
    this.workletUrl = URL.createObjectURL(blob);
    await this.context.audioWorklet.addModule(this.workletUrl);

    this.source = this.context.createMediaStreamSource(this.stream);
    this.worklet = new AudioWorkletNode(
      this.context,
      "pcm-capture-processor",
    );
    this.mutedSink = this.context.createGain();
    this.mutedSink.gain.value = 0;

    this.worklet.port.onmessage = (event: MessageEvent<Float32Array>) => {
      const samples = event.data;
      const rms = Math.sqrt(
        samples.reduce((total, sample) => total + sample * sample, 0) /
          Math.max(samples.length, 1),
      );

      // Barge-in detector: independent of the normal VAD state below, active
      // only while the agent is speaking. Requires sustained loud speech past a
      // short head-grace (AEC is still adapting at speech onset) so the agent's
      // own leaked audio / brief noise won't self-interrupt.
      if (this.agentSpeaking && onBargeIn) {
        const graceElapsedMs =
          ((this.context?.currentTime ?? 0) - this.agentSpeakingSince) * 1000;
        if (graceElapsedMs >= bargeInHeadGraceMs) {
          if (rms >= bargeInThreshold) {
            this.bargeInVoicedFrames += 1;
            if (this.bargeInVoicedFrames >= bargeInSustainedFrames) {
              this.bargeInVoicedFrames = 0;
              this.agentSpeaking = false; // one-shot until re-armed
              onBargeIn();
            }
          } else {
            // Leaky decay (not hard reset): speech naturally dips below the
            // threshold between syllables, so a hard reset would never let the
            // counter accumulate. Decaying tolerates those brief dips while
            // still requiring genuinely sustained speech.
            this.bargeInVoicedFrames = Math.max(0, this.bargeInVoicedFrames - 1);
          }
        }
      }

      if (rms >= voiceThreshold) {
        this.voicedFrames += 1;
        this.silentFrames = 0;
        if (!this.voiceTriggered && this.voicedFrames >= sustainedFrames) {
          this.voiceTriggered = true;
          onVoiceStart?.();
        }
      } else {
        this.voicedFrames = 0;
        if (this.voiceTriggered) {
          this.silentFrames += 1;
          if (this.silentFrames >= silenceFrames) {
            this.voiceTriggered = false;
            this.silentFrames = 0;
            onVoiceEnd?.();
          }
        }
      }

      const downsampled = downsample(
        samples,
        this.context?.sampleRate ?? INPUT_SAMPLE_RATE,
        INPUT_SAMPLE_RATE,
      );
      this.sendBuffer.push(downsampled);
      this.sendBufferLen += downsampled.length;
      if (this.sendBufferLen >= SEND_BATCH_SAMPLES) {
        const merged = new Float32Array(this.sendBufferLen);
        let offset = 0;
        for (const frame of this.sendBuffer) {
          merged.set(frame, offset);
          offset += frame.length;
        }
        this.sendBuffer = [];
        this.sendBufferLen = 0;
        onAudio(pcm16ToBase64(float32ToPcm16(merged)));
      }
    };

    this.source.connect(this.worklet);
    this.worklet.connect(this.mutedSink);
    this.mutedSink.connect(this.context.destination);
  }

  async stop(): Promise<void> {
    this.worklet?.disconnect();
    this.source?.disconnect();
    this.mutedSink?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    await this.context?.close();

    if (this.workletUrl) URL.revokeObjectURL(this.workletUrl);

    this.context = null;
    this.stream = null;
    this.source = null;
    this.worklet = null;
    this.mutedSink = null;
    this.workletUrl = null;
    this.voicedFrames = 0;
    this.silentFrames = 0;
    this.voiceTriggered = false;
    this.sendBuffer = [];
    this.sendBufferLen = 0;
    this.agentSpeaking = false;
    this.bargeInVoicedFrames = 0;
    this.agentSpeakingSince = 0;
  }
}
