export class SpeechFallbackPlayer {
  private utterances: SpeechSynthesisUtterance[] = [];
  private generation = 0;

  speak(
    text: string,
    callbacks?: {
      onStart?: () => void;
      onEnd?: () => void;
    },
  ): void {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const prepared = prepareForSpeech(text);
    if (!prepared) return;

    this.stop();
    this.generation += 1;
    const currentGeneration = this.generation;
    const chunks = chunkSpeech(prepared);
    this.utterances = chunks.map((chunk) => {
      const utterance = new SpeechSynthesisUtterance(chunk);
      utterance.rate = 1;
      utterance.pitch = 1;
      utterance.volume = 1;
      return utterance;
    });

    let index = 0;
    const playNext = () => {
      if (currentGeneration !== this.generation) return;
      const utterance = this.utterances[index];
      if (!utterance) {
        callbacks?.onEnd?.();
        return;
      }
      if (index === 0) callbacks?.onStart?.();
      utterance.onend = () => {
        index += 1;
        playNext();
      };
      utterance.onerror = () => {
        index += 1;
        playNext();
      };
      window.speechSynthesis.speak(utterance);
    };

    playNext();
  }

  stop(callbacks?: { onEnd?: () => void }): void {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    this.generation += 1;
    window.speechSynthesis.cancel();
    this.utterances = [];
    callbacks?.onEnd?.();
  }
}

function prepareForSpeech(text: string): string {
  return text
    .replace(/\[C\d+\]/g, "")
    .replace(/&amp;/g, "and")
    .replace(/&quot;/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function chunkSpeech(text: string): string[] {
  const sentences = text
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);

  if (!sentences.length) return [];

  const chunks: string[] = [];
  let current = "";

  for (const sentence of sentences) {
    const candidate = current ? `${current} ${sentence}` : sentence;
    if (candidate.length <= 220) {
      current = candidate;
      continue;
    }
    if (current) chunks.push(current);
    current = sentence;
  }

  if (current) chunks.push(current);
  return chunks;
}
