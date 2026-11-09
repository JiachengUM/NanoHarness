import type { LiveExpression, LiveVoiceState, LiveVoiceWeights } from '../components/YituParticle';

export type SemanticReading = {
  vector: LiveExpression;
  confidence: number;
};

const clamp = (value: number) => Math.max(0, Math.min(1, value));

export const neutralExpression: LiveExpression = {
  energy: 0.42,
  openness: 0.52,
  tension: 0.34,
  focus: 0.62,
  turbulence: 0.24,
  warmth: 0.50,
  valence: 0.55,
  certainty: 0.56,
  pulse: 0,
  eyeCurve: 0,
  eyeAperture: 0.62,
  eyeSlant: 0,
  eyeAsymmetry: 0,
  pupilDilation: 0.50,
  gazeX: 0,
  gazeY: 0,
};

export function fuseExpression(prosody: LiveExpression, semantic: SemanticReading): LiveExpression {
  const influence = semantic.confidence * 0.86;
  const fieldInfluence: Record<keyof LiveExpression, number> = {
    energy: 0.46,
    openness: 0.78,
    tension: 0.72,
    focus: 0.82,
    turbulence: 0.48,
    warmth: 1,
    valence: 1,
    certainty: 1,
    pulse: 0.34,
    eyeCurve: 1,
    eyeAperture: 1,
    eyeSlant: 1,
    eyeAsymmetry: 1,
    pupilDilation: 1,
    gazeX: 1,
    gazeY: 1,
  };
  const signedFields = new Set<keyof LiveExpression>(['eyeCurve', 'eyeSlant', 'eyeAsymmetry', 'gazeX', 'gazeY']);
  const fused = {} as LiveExpression;
  (Object.keys(prosody) as (keyof LiveExpression)[]).forEach((field) => {
    const amount = influence * fieldInfluence[field];
    const value = prosody[field] * (1 - amount) + semantic.vector[field] * amount;
    fused[field] = signedFields.has(field) ? Math.max(-1, Math.min(1, value)) : clamp(value);
  });
  fused.pulse = clamp(Math.max(prosody.pulse, fused.pulse + semantic.vector.pulse * influence * 0.28));
  return fused;
}

export function manualVoiceWeights(state: LiveVoiceState): LiveVoiceWeights {
  return {
    silent: state === 'silent' ? 1 : 0,
    listen: state === 'listen' ? 1 : 0,
    think: state === 'think' ? 1 : 0,
    speak: state === 'speak' ? 1 : 0,
  };
}
