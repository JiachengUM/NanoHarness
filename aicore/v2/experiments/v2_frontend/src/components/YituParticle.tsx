'use client';

import { useEffect, useRef } from 'react';
import * as THREE from 'three';

export type BotState = 'silent' | 'awake' | 'focus' | 'think';
export type Attention = { driver: boolean; passenger: boolean };
export type ParticleSettings = { density: number; socketSparse: number; pupilSize: number; flowSpeed: number };
export type LiveVoiceState = 'silent' | 'listen' | 'think' | 'speak';
export type LiveVoiceWeights = Record<LiveVoiceState, number>;
export type LiveExpression = {
  energy: number;
  openness: number;
  tension: number;
  focus: number;
  turbulence: number;
  warmth: number;
  valence: number;
  certainty: number;
  pulse: number;
  eyeCurve: number;
  eyeAperture: number;
  eyeSlant: number;
  eyeAsymmetry: number;
  pupilDilation: number;
  gazeX: number;
  gazeY: number;
};
type Props = {
  state: BotState;
  attention: Attention;
  settings: ParticleSettings;
  liveExpression?: LiveExpression;
  liveMode?: LiveVoiceState;
  liveWeights?: LiveVoiceWeights;
};

const MAX_BODY_PARTICLES = 64000;
const MAX_PUPIL_PARTICLES = 2600;
const PUPIL_SHELL_RADIUS = 0.97;

const bodyVertex = /* glsl */`
  uniform float uTime;
  uniform float uFlow;
  uniform float uPointScale;
  uniform float uBreath;
  uniform float uStateEnergy;
  uniform float uEyeOpen;
  uniform float uSocketSparse;
  uniform float uPupilSize;
  uniform float uDriverListen;
  uniform float uPassengerListen;
  uniform float uLiveMix;
  uniform float uLiveEnergy;
  uniform float uLiveOpenness;
  uniform float uLiveTension;
  uniform float uLiveTurbulence;
  uniform float uLiveWarmth;
  uniform float uLiveCertainty;
  uniform float uLivePulse;
  uniform float uLiveEyeCurve;
  uniform float uLiveEyeAperture;
  uniform float uLiveEyeSlant;
  uniform float uLiveEyeAsymmetry;
  uniform vec3 uLiveModes;
  uniform vec2 uEyeAim;
  attribute float aSeed;
  attribute float aSize;
  varying float vDepth;
  varying float vSeed;
  varying float vRadius;
  varying float vEyeGather;
  varying float vPupilInner;
  varying float vPupilBoundary;
  varying float vEyeVacuum;
  varying float vEyeMorph;
  varying float vFlowVisibility;
  varying float vInwardFlow;
  varying float vThinkFlow;
  varying vec3 vLocal;
  vec3 rotateX(vec3 v, float angle) {
    float c = cos(angle);
    float s = sin(angle);
    return vec3(v.x, v.y * c - v.z * s, v.y * s + v.z * c);
  }
  vec3 rotateY(vec3 v, float angle) {
    float c = cos(angle);
    float s = sin(angle);
    return vec3(v.x * c + v.z * s, v.y, -v.x * s + v.z * c);
  }
  void main() {
    vec3 p = position;
    float t = uTime * uFlow;
    vec3 normal = normalize(p);
    float waveA = sin(p.y * 5.7 + t * 0.72 + aSeed * 11.0);
    float waveB = sin(p.x * 7.1 - t * 0.51 + aSeed * 17.0);
    float waveC = cos((p.x + p.y) * 4.3 + t * 0.41 + aSeed * 7.0);
    float organic = (waveA + waveB * 0.65 + waveC * 0.45) * 0.013 * uStateEnergy;
    float breathing = sin(t * 0.9 + p.y * 0.8) * 0.025 * uBreath;
    p += normal * (organic + breathing);
    vec3 tangent = normalize(cross(normal, vec3(0.13, 1.0, 0.21)) + vec3(0.001));
    p += tangent * sin(t * 0.38 + aSeed * 23.0) * 0.006 * uStateEnergy;
    float liveTime = uTime * 0.46;
    float liveWave = sin(liveTime * (0.9 + uLiveEnergy * 1.4) - length(p) * 6.4 + aSeed * 8.0);
    float livePressure = liveWave * (0.008 + uLiveEnergy * 0.026) + sin(liveTime * 1.15 - p.y * 5.2 + aSeed * 1.6) * uLivePulse * 0.018;
    p += normal * livePressure * uLiveMix;
    vec3 liveBitangent = normalize(cross(normal, tangent) + vec3(0.001));
    float liveCurlA = sin(liveTime * (0.34 + uLiveTurbulence * 0.72) + aSeed * 29.0 + p.y * 4.0);
    float liveCurlB = cos(liveTime * (0.27 + uLiveTurbulence * 0.58) + aSeed * 17.0 - p.x * 4.5);
    float liveCurlStrength = (0.002 + uLiveTurbulence * 0.022) * mix(1.0, 0.42, uLiveCertainty);
    p += (tangent * liveCurlA + liveBitangent * liveCurlB) * liveCurlStrength * uLiveMix;
    float thinkWeight = uLiveModes.y;
    float speakWeight = uLiveModes.z;
    float thoughtPhase = liveTime * 1.10 + atan(p.z, p.x) * 2.4 + p.y * 4.6;
    float thoughtFlow = 0.5 + 0.5 * sin(thoughtPhase);
    vec3 thoughtAxis = normalize(vec3(0.16, 1.0, 0.08));
    vec3 thoughtTangent = normalize(cross(thoughtAxis, normal) + vec3(0.001));
    p += thoughtTangent * (thoughtFlow - 0.5) * 0.046 * thinkWeight * uLiveMix;
    p += normal * sin(thoughtPhase * 0.72) * 0.011 * thinkWeight * uLiveMix;
    p *= 1.0 - thinkWeight * 0.024 * uLiveMix;
    float speakEnvelope = 0.42 + 0.58 * sin(liveTime * 1.55 - p.y * 3.4 + aSeed * 0.8);
    p += normal * speakWeight * (0.010 + uLiveEnergy * 0.022) * speakEnvelope * uLiveMix;
    p += normal * (p.y * p.y - 0.28) * (uLiveOpenness - 0.5) * 0.036 * uLiveMix;
    p.x += p.y * (uLiveTension - 0.5) * 0.026 * sin(liveTime * 0.42 + aSeed * 3.0) * uLiveMix;
    float verticalPosition = clamp(p.y / 1.08, -1.0, 1.0);
    p.xz *= 1.0 - verticalPosition * 0.035;
    float gatherRadius = mix(0.35, 0.47, uSocketSparse);
    float eyeCenterX = 0.40;
    float eyeCenterY = 0.13;
    float leftGather = 1.0 - smoothstep(gatherRadius * 0.82, gatherRadius, length(p.xy - vec2(-eyeCenterX, eyeCenterY)));
    float rightGather = 1.0 - smoothstep(gatherRadius * 0.82, gatherRadius, length(p.xy - vec2(eyeCenterX, eyeCenterY)));
    float surfacePresence = smoothstep(0.54, 0.94, length(p) / 1.08);
    float frontPresence = smoothstep(-0.02, 0.38, p.z);
    float eyeGather = max(leftGather, rightGather) * surfacePresence * frontPresence;
    float leftWins = step(rightGather, leftGather);
    float pupilCenterZ = sqrt(0.975 * 0.975 - eyeCenterX * eyeCenterX - eyeCenterY * eyeCenterY);
    vec3 leftEyeDirection = normalize(vec3(-eyeCenterX, eyeCenterY, pupilCenterZ));
    vec3 rightEyeDirection = normalize(vec3(eyeCenterX, eyeCenterY, pupilCenterZ));
    float pupilAimYaw = uEyeAim.x * 0.28;
    float pupilAimPitch = -uEyeAim.y * 0.20;
    vec3 leftPupilDirection = rotateY(leftEyeDirection, pupilAimYaw);
    vec3 rightPupilDirection = rotateY(rightEyeDirection, pupilAimYaw);
    leftPupilDirection = rotateX(leftPupilDirection, pupilAimPitch);
    rightPupilDirection = rotateX(rightPupilDirection, pupilAimPitch);
    vec3 pupilDirection = mix(rightPupilDirection, leftPupilDirection, leftWins);
    float gatherStrength = smoothstep(0.04, 0.78, eyeGather) * uEyeOpen;
    float pupilSizeControl = clamp((uPupilSize - 0.44) / 0.82, 0.0, 1.0);
    float pupilRadiusScale = mix(0.54, 0.76, pupilSizeControl);
    vec3 shapeDirection = pupilDirection;
    vec3 pupilMappedDirection = normalize(mix(shapeDirection, normalize(p), pupilRadiusScale));
    vec3 gatheredDirection = normalize(mix(normalize(p), pupilMappedDirection, gatherStrength));
    vec3 pupilTangent = normalize(cross(pupilDirection, vec3(0.0, 1.0, 0.0)) + vec3(0.001));
    vec3 pupilBitangent = normalize(cross(pupilDirection, pupilTangent));
    vec3 shapeTangent = normalize(cross(shapeDirection, vec3(0.0, 1.0, 0.0)) + vec3(0.001));
    vec3 shapeBitangent = normalize(cross(shapeDirection, shapeTangent));
    float pupilRadius = gatherRadius * pupilRadiusScale;
    float pupilMotionPhase = t * 1.8 + aSeed * 19.0;
    float pupilMotionRadius = (0.014 + fract(aSeed * 13.7) * 0.014) * gatherStrength;
    vec3 pupilMotion = (pupilTangent * sin(pupilMotionPhase) + pupilBitangent * cos(pupilMotionPhase * 0.73)) * pupilMotionRadius;
    gatheredDirection = normalize(gatheredDirection + pupilMotion);
    float pupilShellRadius = 0.975 + (fract(aSeed * 31.71) - 0.5) * 0.012;
    float gatheredRadius = mix(length(p), pupilShellRadius, gatherStrength);
    gatheredRadius += sin(t * 1.15 + aSeed * 11.0) * 0.004 * gatherStrength;
    p = gatheredDirection * gatheredRadius;
    float liveConcern = uLiveTension * (1.0 - uLiveCertainty);
    float directedCurve = clamp(uLiveEyeCurve, -1.0, 1.0) * uLiveMix;
    float directedAperture = mix(0.18, 1.50, clamp(uLiveEyeAperture, 0.0, 1.0));
    float directedSlant = clamp(uLiveEyeSlant, -1.0, 1.0) * uLiveMix;
    float directedAsymmetry = clamp(uLiveEyeAsymmetry, -1.0, 1.0) * uLiveMix;
    vec3 preExpressionOffset = normalize(p) - shapeDirection;
    float preExpressionX = dot(preExpressionOffset, shapeTangent) / max(pupilRadius, 0.001);
    float preExpressionY = dot(preExpressionOffset, shapeBitangent);
    float eyeSideSign = mix(1.0, -1.0, leftWins);
    float curveArc = -(0.34 - preExpressionX * preExpressionX * 0.43) * pupilRadius * directedCurve;
    float slantArc = preExpressionX * eyeSideSign * pupilRadius * directedSlant * 0.30;
    float asymmetryArc = eyeSideSign * pupilRadius * directedAsymmetry * 0.12;
    float expressionArc = curveArc + slantArc + asymmetryArc;
    float expressionTargetY = preExpressionY * mix(1.0, directedAperture, uLiveMix) + expressionArc;
    p = normalize(p + shapeBitangent * (expressionTargetY - preExpressionY) * gatherStrength) * gatheredRadius;
    vec3 shapeOffset = normalize(p) - shapeDirection;
    float pupilTangentOffset = dot(shapeOffset, shapeTangent);
    float pupilBitangentOffset = dot(shapeOffset, shapeBitangent);
    float pupilVertical = (pupilBitangentOffset - expressionArc) / max(pupilRadius * mix(1.0, directedAperture, uLiveMix), 0.001);
    float pupilShapeX = pupilTangentOffset / max(pupilRadius, 0.001);
    float pupilShapeY = pupilVertical;
    float liveDelight = uLiveWarmth * uLiveEnergy * uLiveOpenness;
    float expressionEyeWidth = 1.0 + liveDelight * 0.06 - liveConcern * 0.04;
    float expressionEyeHeight = mix(0.94, 1.06, uLiveOpenness) * (1.0 - liveConcern * 0.05);
    pupilShapeX /= mix(1.0, expressionEyeWidth, uLiveMix);
    pupilShapeY /= mix(1.0, expressionEyeHeight, uLiveMix);
    pupilShapeY += pupilShapeX * (uLiveTension - 0.5) * 0.075 * uLiveMix;
    float shapeDistance = length(vec2(pupilShapeX, pupilShapeY)) * pupilRadius;
    float pupilCore = (1.0 - smoothstep(pupilRadius * 0.9, pupilRadius * 1.08, shapeDistance)) * gatherStrength;
    float pupilInner = 1.0 - step(pupilRadius * 0.62, shapeDistance);
    float pupilBoundary = 1.0 - smoothstep(pupilRadius * 0.012, pupilRadius * 0.052, abs(shapeDistance - pupilRadius * 0.62));
    float eyeShapeDistance = shapeDistance / max(pupilRadius, 0.001);
    float nearestPupilDistance = min(length(normalize(p) - leftPupilDirection), length(normalize(p) - rightPupilDirection));
    float circularEyeVacuum = 1.0 - smoothstep(pupilRadius + 0.045, pupilRadius + 0.085, nearestPupilDistance);
    float apertureDeviation = abs(directedAperture - 1.0) / 0.82;
    float expressionMorph = clamp(max(max(abs(directedCurve), abs(directedSlant)), max(abs(directedAsymmetry), apertureDeviation)), 0.0, 1.0);
    float shapedEyeVacuum = 1.0 - smoothstep(0.84, 1.18, eyeShapeDistance);
    float eyeVacuum = mix(circularEyeVacuum, shapedEyeVacuum, smoothstep(0.08, 0.46, expressionMorph));
    float surfaceBand = smoothstep(0.78, 0.96, length(p) / 1.08);
    float listeningDepthBand = smoothstep(-0.72, -0.22, p.z) * (1.0 - smoothstep(0.12, 0.42, p.z));
    float leftSectorAngle = abs(atan(p.y, max(-p.x, 0.001)));
    float rightSectorAngle = abs(atan(p.y, max(p.x, 0.001)));
    float leftSectorCore = 1.0 - smoothstep(0.24, 1.18, leftSectorAngle);
    float rightSectorCore = 1.0 - smoothstep(0.24, 1.18, rightSectorAngle);
    float leftCenterBias = pow(max(0.0, 1.0 - leftSectorAngle / 1.22), 1.18);
    float rightCenterBias = pow(max(0.0, 1.0 - rightSectorAngle / 1.22), 1.18);
    float leftNinetyDegreeWedge = smoothstep(0.04, 0.46, -p.x) * leftSectorCore * mix(0.26, 1.0, leftCenterBias);
    float rightNinetyDegreeWedge = smoothstep(0.04, 0.46, p.x) * rightSectorCore * mix(0.26, 1.0, rightCenterBias);
    float listeningWedge = max(uDriverListen * leftNinetyDegreeWedge, uPassengerListen * rightNinetyDegreeWedge);
    float flowNoise = fract(aSeed * 97.13 + sin(p.y * 11.7 + p.z * 7.9) * 0.21);
    float flowProbability = mix(0.10, 0.82, pow(listeningWedge, 0.76));
    float flowSelection = 1.0 - smoothstep(flowProbability - 0.10, flowProbability + 0.07, flowNoise);
    float flowTexture = mix(0.72, 1.08, fract(aSeed * 43.71));
    float flowAmount = clamp(surfaceBand * listeningDepthBand * listeningWedge * flowSelection * flowTexture * (1.0 - smoothstep(0.02, 0.35, gatherStrength)), 0.0, 1.0);
    float flowProgress = fract(t * 1.26 + aSeed * 1.73);
    float flowCycleAlpha = smoothstep(0.02, 0.10, flowProgress) * (1.0 - smoothstep(0.82, 0.98, flowProgress));
    p *= 1.0 - flowAmount * pow(flowProgress, 1.28) * 0.68;

    vec4 mvPosition = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mvPosition;
    float liveModePointScale = 1.0 - thinkWeight * 0.06 + speakWeight * (0.14 + uLivePulse * 0.20);
    gl_PointSize = aSize * uPointScale * (5.2 / -mvPosition.z) * (1.0 + pupilCore * 0.2 + flowAmount * flowCycleAlpha * 0.52) * mix(1.0, liveModePointScale, uLiveMix);
    vDepth = smoothstep(-1.15, 1.15, p.z);
    vSeed = aSeed;
    vRadius = clamp(length(p) / 1.08, 0.0, 1.0);
    vEyeGather = pupilCore;
    vPupilInner = pupilInner;
    vPupilBoundary = pupilBoundary;
    vEyeVacuum = eyeVacuum * uEyeOpen;
    vEyeMorph = expressionMorph;
    vFlowVisibility = mix(1.0, flowCycleAlpha, flowAmount);
    vInwardFlow = flowAmount * flowCycleAlpha;
    vThinkFlow = thoughtFlow * thinkWeight * uLiveMix;
    vLocal = p;
  }
`;

const bodyFragment = /* glsl */`
  uniform vec3 uColorA;
  uniform vec3 uColorB;
  uniform float uOpacity;
  uniform float uDensity;
  uniform float uSocketSparse;
  uniform float uEyeOpen;
  uniform float uHeadTurn;
  uniform float uLiveMix;
  uniform float uLiveEnergy;
  uniform float uLiveWarmth;
  uniform float uLiveCertainty;
  uniform vec3 uLiveModes;
  varying float vDepth;
  varying float vSeed;
  varying float vRadius;
  varying float vEyeGather;
  varying float vPupilInner;
  varying float vPupilBoundary;
  varying float vEyeVacuum;
  varying float vEyeMorph;
  varying float vFlowVisibility;
  varying float vInwardFlow;
  varying float vThinkFlow;
  varying vec3 vLocal;
  float socketField(vec2 p, vec2 center, float radius) {
    float d = length(p - center) / radius;
    return 1.0 - smoothstep(0.74, 0.98, d);
  }
  void main() {
    float pupilBoundaryMask = step(0.5, vPupilBoundary);
    float pupilRegionDensity = mix(0.34, 1.0, step(0.5, vPupilInner));
    float pupilDensity = mix(pupilRegionDensity, 0.12, pupilBoundaryMask);
    float entityDensity = mix(uDensity, pupilDensity, step(0.04, vEyeGather));
    if (fract(vSeed * 571.3) > entityDensity) discard;
    vec2 pc = gl_PointCoord - 0.5;
    float circle = 1.0 - smoothstep(0.18, 0.5, length(pc));
    if (circle < 0.01) discard;
    float socketRadius = mix(0.35, 0.47, uSocketSparse);
    float leftSocket = socketField(vLocal.xy, vec2(-0.40, 0.13), socketRadius);
    float rightSocket = socketField(vLocal.xy, vec2(0.40, 0.13), socketRadius);
    float sockets = max(leftSocket, rightSocket);
    float pupilPresence = smoothstep(0.05, 0.5, vEyeGather);
    float fixedSocketWeight = 1.0 - smoothstep(0.08, 0.46, vEyeMorph);
    float vacuumField = max(sockets * uEyeOpen * fixedSocketWeight, vEyeVacuum);
    float shallowSocketDepth = smoothstep(0.68, 0.94, vRadius) * smoothstep(0.08, 0.48, vLocal.z);
    float socketDepletion = vacuumField * shallowSocketDepth * (1.0 - pupilPresence);
    float socketDensity = mix(1.0, 0.14, socketDepletion);
    if (fract(vSeed * 713.7) > socketDensity) discard;
    float socketAlpha = mix(1.0, 0.38, socketDepletion);
    vec3 color = mix(uColorA, uColorB, vDepth * 0.78 + fract(vSeed * 7.0) * 0.22);
    color = mix(color, vec3(0.96, 0.78, 0.72), uLiveWarmth * uLiveMix * 0.22);
    color += vec3(0.08, 0.16, 0.24) * uLiveEnergy * uLiveMix;
    color = mix(color, vec3(0.34, 0.62, 1.08), uLiveModes.y * uLiveMix * 0.26);
    float thoughtHighlight = smoothstep(0.34, 0.92, vThinkFlow);
    color += vec3(0.12, 0.30, 0.52) * thoughtHighlight;
    color = mix(color, vec3(1.08, 0.98, 0.84), uLiveModes.z * uLiveMix * 0.30);
    float attentionSide = smoothstep(-0.8, 0.9, vLocal.x * sign(uHeadTurn));
    float turnSignal = abs(uHeadTurn);
    color = mix(color, uColorB, attentionSide * turnSignal * 0.22);
    float visibleEyeField = vEyeGather;
    color = mix(color, vec3(0.96, 1.18, 1.5), visibleEyeField * 0.82);
    color = mix(color, vec3(1.02, 1.24, 1.56), step(0.5, vPupilInner) * 0.16);
    color = mix(color, vec3(0.43, 0.62, 0.86), pupilBoundaryMask * 0.48);
    color = mix(color, vec3(0.88, 1.11, 1.4), min(1.0, vInwardFlow * 0.96));
    float flowCore = 1.0 - smoothstep(0.05, 0.27, length(pc));
    color += vec3(0.21, 0.33, 0.48) * flowCore * vInwardFlow;
    float rimGlow = pow(1.0 - abs(vLocal.z) / 1.25, 1.7);
    float radialPresence = mix(0.08, 1.0, pow(vRadius, 1.8));
    float directionalLift = 1.0 + attentionSide * turnSignal * 0.26;
    float flowHighlight = 1.0 + vInwardFlow * 0.55;
    float pupilGatherGlow = 1.0 + visibleEyeField * 0.82;
    float pupilBoundaryAlpha = mix(1.0, 0.58, pupilBoundaryMask);
    float depthPresence = mix(0.32, 1.0, vDepth);
    float livePresence = mix(1.0, mix(0.88, 1.08, uLiveCertainty), uLiveMix);
    livePresence *= mix(1.0, 0.94, uLiveModes.y * uLiveMix);
    livePresence *= 1.0 + thoughtHighlight * 0.34;
    livePresence *= mix(1.0, 1.14, uLiveModes.z * uLiveMix);
    float alpha = circle * uOpacity * socketAlpha * radialPresence * directionalLift * pupilGatherGlow * pupilBoundaryAlpha * flowHighlight * vFlowVisibility * depthPresence * (0.72 + rimGlow * 0.28) * livePresence;
    gl_FragColor = vec4(color, alpha);
  }
`;

const pupilVertex = /* glsl */`
  uniform float uTime;
  uniform float uFlow;
  uniform float uPointScale;
  uniform float uPupilSize;
  uniform vec2 uAttention;
  uniform float uThink;
  uniform float uEyeOpen;
  uniform float uLiveMix;
  uniform float uLiveEnergy;
  uniform float uLiveOpenness;
  uniform float uLiveTension;
  uniform float uLiveTurbulence;
  uniform float uLiveCertainty;
  uniform float uLivePulse;
  uniform float uLiveEyeCurve;
  uniform float uLiveEyeAperture;
  uniform float uLiveEyeSlant;
  uniform float uLiveEyeAsymmetry;
  uniform float uLivePupilDilation;
  uniform vec3 uLiveModes;
  attribute float aSeed;
  attribute float aSide;
  attribute float aSize;
  varying float vSeed;
  varying float vCore;
  varying float vFacing;
  varying float vReveal;
  vec3 rotateX(vec3 v, float angle) {
    float c = cos(angle);
    float s = sin(angle);
    return vec3(v.x, v.y * c - v.z * s, v.y * s + v.z * c);
  }
  vec3 rotateY(vec3 v, float angle) {
    float c = cos(angle);
    float s = sin(angle);
    return vec3(v.x * c + v.z * s, v.y, -v.x * s + v.z * c);
  }
  void main() {
    vec3 p = position;
    float shellBase = 0.97;
    float sourceCenterZ = sqrt(shellBase * shellBase - 0.38 * 0.38 - 0.13 * 0.13);
    vec3 sourceCenter = vec3(aSide * 0.38, 0.13, sourceCenterZ);
    float eyeCenterX = 0.38;
    float eyeCenterY = 0.13;
    float centerZ = sqrt(shellBase * shellBase - eyeCenterX * eyeCenterX - eyeCenterY * eyeCenterY);
    vec3 center = vec3(aSide * eyeCenterX, eyeCenterY, centerZ);
    vec3 offset = p - sourceCenter;
    vec3 eyeNormal = normalize(center);
    vec3 eyeTangent = normalize(cross(eyeNormal, vec3(0.0, 1.0, 0.0)) + vec3(0.001));
    vec3 eyeBitangent = normalize(cross(eyeNormal, eyeTangent) + vec3(0.001));
    float offsetNormal = dot(offset, eyeNormal);
    float offsetHorizontal = dot(offset, eyeTangent);
    float offsetVertical = dot(offset, eyeBitangent);
    float liveConcern = uLiveTension * (1.0 - uLiveCertainty);
    float liveDelight = uLiveEnergy * uLiveOpenness * (1.0 - uLiveTension * 0.35);
    float directedCurve = clamp(uLiveEyeCurve, -1.0, 1.0) * uLiveMix;
    float directedAperture = mix(0.18, 1.50, clamp(uLiveEyeAperture, 0.0, 1.0));
    float directedSlant = clamp(uLiveEyeSlant, -1.0, 1.0) * uLiveMix;
    float directedAsymmetry = clamp(uLiveEyeAsymmetry, -1.0, 1.0) * uLiveMix;
    float expressionWidth = 1.0 + liveDelight * 0.06 - liveConcern * 0.04;
    float expressionHeight = mix(1.0, directedAperture, uLiveMix);
    float normalizedEyeX = offsetHorizontal / 0.27;
    float curveArc = -(0.096 - normalizedEyeX * normalizedEyeX * 0.074) * directedCurve;
    float slantArc = normalizedEyeX * aSide * directedSlant * 0.080;
    float asymmetryArc = aSide * directedAsymmetry * 0.034;
    float expressionArc = curveArc + slantArc + asymmetryArc;
    offset = eyeNormal * offsetNormal
      + eyeTangent * offsetHorizontal * mix(1.0, expressionWidth, uLiveMix)
      + eyeBitangent * (offsetVertical * mix(1.0, expressionHeight, uLiveMix) + expressionArc);
    float shellRadius = length(p);
    float reveal = smoothstep(0.08, 0.94, uEyeOpen);
    float clusterScale = uPupilSize * mix(0.12, 1.0, reveal);
    float liveDilation = mix(0.78, 1.24, clamp(uLivePupilDilation, 0.0, 1.0));
    clusterScale *= mix(1.0, liveDilation, uLiveMix);
    p = normalize(center + offset * clusterScale) * shellRadius;
    p *= mix(0.82, 1.0, reveal);
    p = rotateY(p, uAttention.x * 0.22);
    p = rotateX(p, -uAttention.y * 0.18);
    float t = uTime * uFlow;
    float orbit = sin(t * 0.8 + aSeed * 17.0) * 0.006;
    float driftYaw = cos(aSeed * 31.0 + t * (0.25 + uThink * 0.7)) * orbit;
    float driftPitch = sin(aSeed * 27.0 + t * (0.31 + uThink * 0.9)) * orbit;
    p = rotateY(p, driftYaw);
    p = rotateX(p, driftPitch);
    vec3 liveNormal = normalize(p);
    vec3 liveTangent = normalize(cross(liveNormal, vec3(0.0, 1.0, 0.0)) + vec3(0.001));
    vec3 liveBitangent = normalize(cross(liveNormal, liveTangent) + vec3(0.001));
    float containedLiveMotion = (0.002 + uLiveTurbulence * 0.008) * mix(1.0, 0.52, uLiveCertainty) * uLiveMix;
    p += liveTangent * sin(uTime * 0.30 + aSeed * 33.0) * containedLiveMotion;
    p += liveBitangent * cos(uTime * 0.23 + aSeed * 25.0) * containedLiveMotion;
    p *= 1.0 - uLivePulse * uLiveMix * 0.005;
    vec4 mvPosition = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mvPosition;
    float liveModePointScale = 1.0 - uLiveModes.y * 0.06 + uLiveModes.z * (0.12 + uLivePulse * 0.12);
    gl_PointSize = aSize * uPointScale * (5.0 / -mvPosition.z) * 1.14 * mix(1.0, liveModePointScale, uLiveMix);
    vSeed = aSeed;
    vCore = 1.0 - smoothstep(0.0, 0.2, length(offset));
    vFacing = smoothstep(-0.12, 0.38, (modelViewMatrix * vec4(normalize(p), 0.0)).z);
    vReveal = smoothstep(0.32, 0.96, uEyeOpen);
  }
`;

const pupilFragment = /* glsl */`
  uniform float uTime;
  uniform vec3 uColor;
  uniform float uOpacity;
  uniform float uLiveMix;
  uniform float uLiveEnergy;
  uniform float uLiveWarmth;
  uniform float uLiveTension;
  uniform float uLiveCertainty;
  uniform vec3 uLiveModes;
  varying float vSeed;
  varying float vCore;
  varying float vFacing;
  varying float vReveal;
  void main() {
    vec2 pc = gl_PointCoord - 0.5;
    float particle = 1.0 - smoothstep(0.05, 0.5, length(pc));
    if (particle < 0.02) discard;
    float centerMask = smoothstep(0.02, 0.42, vCore);
    if (centerMask < 0.02) discard;
    float shimmer = 0.72 + fract(vSeed * 19.31) * 0.28;
    vec3 pupilGlow = uColor * (1.12 + vCore * 0.46);
    pupilGlow = mix(pupilGlow, vec3(1.06, 0.93, 0.88), uLiveWarmth * uLiveMix * 0.20);
    pupilGlow += vec3(0.12, 0.18, 0.24) * uLiveEnergy * uLiveMix;
    float liveConcern = uLiveTension * (1.0 - uLiveCertainty);
    pupilGlow = mix(pupilGlow, vec3(0.50, 0.66, 0.98), liveConcern * uLiveMix * 0.24);
    pupilGlow = mix(pupilGlow, vec3(0.46, 0.72, 1.18), uLiveModes.y * uLiveMix * 0.28);
    pupilGlow = mix(pupilGlow, vec3(1.16, 1.05, 0.90), uLiveModes.z * uLiveMix * 0.32);
    float thoughtPulse = 0.5 + 0.5 * sin(uTime * 0.72 + vSeed * 1.8);
    pupilGlow += vec3(0.08, 0.22, 0.42) * thoughtPulse * uLiveModes.y * uLiveMix;
    float liveModeAlpha = mix(1.0, 0.94 + thoughtPulse * 0.22, uLiveModes.y * uLiveMix) * mix(1.0, 1.18, uLiveModes.z * uLiveMix);
    float pupilAlpha = particle * uOpacity * shimmer * (0.76 + vCore * 0.46) * centerMask * vFacing * vReveal * liveModeAlpha;
    gl_FragColor = vec4(pupilGlow, pupilAlpha);
  }
`;

const palettes = {
  silent: { a: '#7187ff', b: '#b6c5ff', pupil: '#b7c7ff', opacity: 0.56, energy: 0.28, breath: 0.25 },
  awake: { a: '#69c5ff', b: '#d2e7ff', pupil: '#e4f4ff', opacity: 0.78, energy: 0.72, breath: 0.68 },
  focus: { a: '#8bcfff', b: '#f1f7ff', pupil: '#ffffff', opacity: 0.9, energy: 0.43, breath: 0.38 },
  think: { a: '#8b7dff', b: '#d8caff', pupil: '#f0eaff', opacity: 0.82, energy: 1, breath: 0.78 },
};

function seededRandom(seed: number) {
  let value = seed >>> 0;
  return () => { value = (value * 1664525 + 1013904223) >>> 0; return value / 4294967296; };
}

export default function YituParticle({ state, attention, settings, liveExpression, liveMode, liveWeights }: Props) {
  const mountRef = useRef<HTMLDivElement>(null);
  const propsRef = useRef({ state, attention, settings, liveExpression, liveMode, liveWeights });

  useEffect(() => {
    propsRef.current = { state, attention, settings, liveExpression, liveMode, liveWeights };
  }, [attention, liveExpression, liveMode, liveWeights, settings, state]);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(37, 1, 0.1, 100);
    camera.position.set(0, 0, 5.8);
    const renderer = new THREE.WebGLRenderer({ antialias: false, alpha: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.65));
    renderer.setClearColor(0x000000, 0);
    mount.appendChild(renderer.domElement);
    const root = new THREE.Group();
    scene.add(root);

    const bodyGeometry = new THREE.BufferGeometry();
    const bodyPositions = new Float32Array(MAX_BODY_PARTICLES * 3);
    const bodySeeds = new Float32Array(MAX_BODY_PARTICLES);
    const bodySizes = new Float32Array(MAX_BODY_PARTICLES);
    const random = seededRandom(8427);
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < MAX_BODY_PARTICLES; i += 1) {
      const radialSample = random();
      const exponentialFalloff = 9.0;
      const inwardDepth = -Math.log(1 - radialSample * (1 - Math.exp(-exponentialFalloff))) / exponentialFalloff;
      const radius = 1.08 * (1 - inwardDepth);
      const y = 1 - (i / (MAX_BODY_PARTICLES - 1)) * 2;
      const horizontal = Math.sqrt(Math.max(0, 1 - y * y));
      const theta = golden * i + (random() - 0.5) * 0.08;
      bodyPositions[i * 3] = Math.cos(theta) * horizontal * radius;
      bodyPositions[i * 3 + 1] = y * radius;
      bodyPositions[i * 3 + 2] = Math.sin(theta) * horizontal * radius;
      bodySeeds[i] = random(); bodySizes[i] = 2 + random() * 1.85;
    }
    bodyGeometry.setAttribute('position', new THREE.BufferAttribute(bodyPositions, 3));
    bodyGeometry.setAttribute('aSeed', new THREE.BufferAttribute(bodySeeds, 1));
    bodyGeometry.setAttribute('aSize', new THREE.BufferAttribute(bodySizes, 1));
    const bodyUniforms = {
      uTime: { value: 0 }, uFlow: { value: 0.65 }, uPointScale: { value: renderer.getPixelRatio() },
      uBreath: { value: 0.7 }, uStateEnergy: { value: 0.7 }, uEyeOpen: { value: state === 'silent' ? 0 : 1 },
      uPupilSize: { value: 0.44 + settings.pupilSize / 100 * 0.82 },
      uEyeAim: { value: new THREE.Vector2() },
      uDriverListen: { value: attention.driver && state !== 'silent' ? 1 : 0 },
      uPassengerListen: { value: attention.passenger && state !== 'silent' ? 1 : 0 },
      uColorA: { value: new THREE.Color('#69c5ff') }, uColorB: { value: new THREE.Color('#d2e7ff') },
      uOpacity: { value: 0.78 }, uDensity: { value: 0.78 }, uSocketSparse: { value: settings.socketSparse / 100 },
      uHeadTurn: { value: 0 },
      uLiveMix: { value: liveExpression ? 1 : 0 }, uLiveEnergy: { value: liveExpression?.energy ?? 0.4 },
      uLiveOpenness: { value: liveExpression?.openness ?? 0.5 }, uLiveTension: { value: liveExpression?.tension ?? 0.4 },
      uLiveTurbulence: { value: liveExpression?.turbulence ?? 0.2 },
      uLiveWarmth: { value: liveExpression?.warmth ?? 0.5 },
      uLiveCertainty: { value: liveExpression?.certainty ?? 0.6 },
      uLivePulse: { value: liveExpression?.pulse ?? 0 },
      uLiveEyeCurve: { value: liveExpression?.eyeCurve ?? 0 }, uLiveEyeAperture: { value: liveExpression?.eyeAperture ?? 0.62 },
      uLiveEyeSlant: { value: liveExpression?.eyeSlant ?? 0 }, uLiveEyeAsymmetry: { value: liveExpression?.eyeAsymmetry ?? 0 },
      uLiveModes: { value: new THREE.Vector3(liveMode === 'listen' ? 1 : 0, liveMode === 'think' ? 1 : 0, liveMode === 'speak' ? 1 : 0) },
    };
    const bodyMaterial = new THREE.ShaderMaterial({ uniforms: bodyUniforms, vertexShader: bodyVertex, fragmentShader: bodyFragment, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
    root.add(new THREE.Points(bodyGeometry, bodyMaterial));

    const pupilGeometry = new THREE.BufferGeometry();
    const pupilPositions = new Float32Array(MAX_PUPIL_PARTICLES * 3);
    const pupilSeeds = new Float32Array(MAX_PUPIL_PARTICLES);
    const pupilSides = new Float32Array(MAX_PUPIL_PARTICLES);
    const pupilSizes = new Float32Array(MAX_PUPIL_PARTICLES);
    for (let i = 0; i < MAX_PUPIL_PARTICLES; i += 1) {
      const side = i % 2 === 0 ? -1 : 1;
      const r = Math.pow(random(), 0.68);
      const angle = random() * Math.PI * 2;
      const centerZ = Math.sqrt(PUPIL_SHELL_RADIUS ** 2 - 0.38 ** 2 - 0.13 ** 2);
      const centerDirection = new THREE.Vector3(side * 0.38, 0.13, centerZ).normalize();
      const tangentX = new THREE.Vector3(centerDirection.z, 0, -centerDirection.x).normalize();
      const tangentY = new THREE.Vector3().crossVectors(centerDirection, tangentX).normalize();
      const arc = r * 0.27;
      const tangentDirection = tangentX.multiplyScalar(Math.cos(angle)).add(tangentY.multiplyScalar(Math.sin(angle)));
      const direction = centerDirection.multiplyScalar(Math.cos(arc)).add(tangentDirection.multiplyScalar(Math.sin(arc))).normalize();
      const particleRadius = PUPIL_SHELL_RADIUS + (random() - 0.5) * 0.045 * (1 - r * 0.35);
      pupilPositions[i * 3] = direction.x * particleRadius;
      pupilPositions[i * 3 + 1] = direction.y * particleRadius;
      pupilPositions[i * 3 + 2] = direction.z * particleRadius;
      pupilSeeds[i] = random(); pupilSides[i] = side; pupilSizes[i] = 2.3 + random() * 2.6;
    }
    pupilGeometry.setAttribute('position', new THREE.BufferAttribute(pupilPositions, 3));
    pupilGeometry.setAttribute('aSeed', new THREE.BufferAttribute(pupilSeeds, 1));
    pupilGeometry.setAttribute('aSide', new THREE.BufferAttribute(pupilSides, 1));
    pupilGeometry.setAttribute('aSize', new THREE.BufferAttribute(pupilSizes, 1));
    const pupilUniforms = {
      uTime: { value: 0 }, uFlow: { value: 0.65 }, uPointScale: { value: renderer.getPixelRatio() }, uPupilSize: { value: 0.8 },
      uAttention: { value: new THREE.Vector2() }, uThink: { value: 0 }, uEyeOpen: { value: state === 'silent' ? 0 : 1 },
      uColor: { value: new THREE.Color('#e4f4ff') }, uOpacity: { value: 0.78 },
      uLiveMix: { value: liveExpression ? 1 : 0 }, uLiveEnergy: { value: liveExpression?.energy ?? 0.4 },
      uLiveOpenness: { value: liveExpression?.openness ?? 0.5 }, uLiveTension: { value: liveExpression?.tension ?? 0.4 },
      uLiveTurbulence: { value: liveExpression?.turbulence ?? 0.2 },
      uLiveCertainty: { value: liveExpression?.certainty ?? 0.6 }, uLivePulse: { value: liveExpression?.pulse ?? 0 },
      uLiveWarmth: { value: liveExpression?.warmth ?? 0.5 },
      uLiveEyeCurve: { value: liveExpression?.eyeCurve ?? 0 }, uLiveEyeAperture: { value: liveExpression?.eyeAperture ?? 0.62 },
      uLiveEyeSlant: { value: liveExpression?.eyeSlant ?? 0 }, uLiveEyeAsymmetry: { value: liveExpression?.eyeAsymmetry ?? 0 },
      uLivePupilDilation: { value: liveExpression?.pupilDilation ?? 0.5 },
      uLiveModes: { value: new THREE.Vector3(liveMode === 'listen' ? 1 : 0, liveMode === 'think' ? 1 : 0, liveMode === 'speak' ? 1 : 0) },
    };
    const pupilMaterial = new THREE.ShaderMaterial({ uniforms: pupilUniforms, vertexShader: pupilVertex, fragmentShader: pupilFragment, transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending });
    root.add(new THREE.Points(pupilGeometry, pupilMaterial));

    const pointer = new THREE.Vector2();
    const pointerTarget = new THREE.Vector2();
    let isDragging = false;
    let lastPointerX = 0;
    let lastPointerY = 0;
    let dragYaw = 0;
    let dragPitch = 0;
    let yawVelocity = 0;
    let pitchVelocity = 0;
    const onPointerDown = (event: PointerEvent) => {
      isDragging = true;
      lastPointerX = event.clientX;
      lastPointerY = event.clientY;
      yawVelocity = 0;
      pitchVelocity = 0;
      renderer.domElement.setPointerCapture(event.pointerId);
      mount.classList.add('is-dragging');
    };
    const onPointerMove = (event: PointerEvent) => {
      const rect = mount.getBoundingClientRect();
      pointerTarget.x = THREE.MathUtils.clamp(((event.clientX - rect.left) / rect.width - 0.5) * 2, -1, 1);
      pointerTarget.y = THREE.MathUtils.clamp(-((event.clientY - rect.top) / rect.height - 0.5) * 2, -1, 1);
      if (!isDragging) return;
      const deltaX = event.clientX - lastPointerX;
      const deltaY = event.clientY - lastPointerY;
      lastPointerX = event.clientX;
      lastPointerY = event.clientY;
      yawVelocity = deltaX * 0.0036;
      pitchVelocity = deltaY * 0.0036;
      dragYaw = THREE.MathUtils.clamp(dragYaw + yawVelocity, -1.42, 1.42);
      dragPitch = THREE.MathUtils.clamp(dragPitch + pitchVelocity, -0.88, 0.88);
    };
    const onPointerUp = (event: PointerEvent) => {
      isDragging = false;
      if (renderer.domElement.hasPointerCapture(event.pointerId)) renderer.domElement.releasePointerCapture(event.pointerId);
      mount.classList.remove('is-dragging');
    };
    const onPointerLeave = () => { if (!isDragging) pointerTarget.set(0, 0); };
    mount.addEventListener('pointerdown', onPointerDown);
    mount.addEventListener('pointermove', onPointerMove);
    mount.addEventListener('pointerup', onPointerUp);
    mount.addEventListener('pointercancel', onPointerUp);
    mount.addEventListener('pointerleave', onPointerLeave);

    let baseRootX = 0.36;
    let baseRootY = 0.08;
    let baseRootScale = 1.22;
    const resize = () => {
      const { width, height } = mount.getBoundingClientRect();
      renderer.setSize(width, height, false); camera.aspect = width / Math.max(height, 1); camera.updateProjectionMatrix();
      const mobile = width < 700;
      baseRootX = mobile ? 0 : 0.36;
      baseRootY = mobile ? 0.28 : 0.08;
      baseRootScale = mobile ? 0.93 : 1.22;
      root.scale.setScalar(baseRootScale);
      root.position.set(baseRootX, baseRootY, 0);
      bodyUniforms.uPointScale.value = pupilUniforms.uPointScale.value = renderer.getPixelRatio();
    };
    const observer = new ResizeObserver(resize); observer.observe(mount); resize();

    const clock = new THREE.Clock();
    let frame = 0;
    let currentHeadTurn = 0;
    let liveListenWeight = liveMode === 'listen' ? 1 : 0;
    let liveThinkWeight = liveMode === 'think' ? 1 : 0;
    let liveSpeakWeight = liveMode === 'speak' ? 1 : 0;
    const colorATarget = new THREE.Color(); const colorBTarget = new THREE.Color(); const pupilColorTarget = new THREE.Color();
    const attentionTarget = new THREE.Vector2();
    const animate = () => {
      const elapsed = clock.getElapsedTime();
      const current = propsRef.current;
      const palette = palettes[current.state];
      const flow = 0.18 + current.settings.flowSpeed / 100 * 1.08;
      const density = 0.16 + current.settings.density / 100 * 0.84;
      const sparse = current.settings.socketSparse / 100;
      const pupilSize = 0.44 + current.settings.pupilSize / 100 * 0.82;
      const attentionX = current.attention.driver && !current.attention.passenger ? -0.72 : current.attention.passenger && !current.attention.driver ? 0.72 : 0;
      pointer.lerp(pointerTarget, 0.045);
      currentHeadTurn = THREE.MathUtils.lerp(currentHeadTurn, attentionX, 0.018);
      if (!isDragging) {
        yawVelocity = (yawVelocity - dragYaw * 0.052) * 0.845;
        pitchVelocity = (pitchVelocity - dragPitch * 0.052) * 0.845;
        dragYaw += yawVelocity;
        dragPitch += pitchVelocity;
        if (Math.abs(dragYaw) < 0.0001 && Math.abs(yawVelocity) < 0.0001) { dragYaw = 0; yawVelocity = 0; }
        if (Math.abs(dragPitch) < 0.0001 && Math.abs(pitchVelocity) < 0.0001) { dragPitch = 0; pitchVelocity = 0; }
      }
      const liveListenTarget = current.liveWeights?.listen ?? (current.liveMode === 'listen' ? 1 : 0);
      const liveThinkTarget = current.liveWeights?.think ?? (current.liveMode === 'think' ? 1 : 0);
      const liveSpeakTarget = current.liveWeights?.speak ?? (current.liveMode === 'speak' ? 1 : 0);
      liveListenWeight = THREE.MathUtils.lerp(liveListenWeight, liveListenTarget, 0.025);
      liveThinkWeight = THREE.MathUtils.lerp(liveThinkWeight, liveThinkTarget, 0.025);
      liveSpeakWeight = THREE.MathUtils.lerp(liveSpeakWeight, liveSpeakTarget, 0.025);
      bodyUniforms.uLiveModes.value.set(liveListenWeight, liveThinkWeight, liveSpeakWeight);
      pupilUniforms.uLiveModes.value.copy(bodyUniforms.uLiveModes.value);
      const liveVector = current.liveExpression;
      const liveEnergy = liveVector?.energy ?? 0.4;
      const liveOpenness = liveVector?.openness ?? 0.5;
      const liveTension = liveVector?.tension ?? 0.35;
      const liveWarmth = liveVector?.warmth ?? 0.5;
      const liveCertainty = liveVector?.certainty ?? 0.6;
      const livePulse = liveVector?.pulse ?? 0;
      const expressionConcern = liveTension * (1 - liveCertainty);
      const expressionCuriosity = liveOpenness * (1 - liveCertainty * 0.72);
      const expressionDelight = liveWarmth * liveEnergy * liveOpenness;
      const expressionComposure = liveCertainty * (1 - liveTension);
      const headYaw = currentHeadTurn * 0.36
        + liveListenWeight * Math.sin(elapsed * 0.15) * 0.045
        + liveThinkWeight * Math.sin(elapsed * 0.33) * 0.065
        + expressionCuriosity * Math.sin(elapsed * 0.31) * 0.075;
      const headPitch = Math.abs(currentHeadTurn) * 0.018
        + liveThinkWeight * (0.075 + Math.sin(elapsed * 0.20) * 0.018)
        + expressionConcern * 0.075
        - expressionDelight * 0.030;
      const headRoll = -currentHeadTurn * 0.045
        + liveThinkWeight * Math.sin(elapsed * 0.24) * 0.075
        + (liveWarmth - 0.5) * (1 - liveTension * 0.7) * 0.10
        + expressionCuriosity * Math.sin(elapsed * 0.23 + 1.2) * 0.035;
      root.rotation.set(dragPitch + headPitch, dragYaw + headYaw, Math.sin(elapsed * 0.18) * 0.012 + headRoll);
      root.scale.setScalar(baseRootScale * (1
        + liveSpeakWeight * (liveEnergy * 0.025 + livePulse * 0.038)
        + expressionDelight * 0.018
        + livePulse * 0.026
        - expressionConcern * 0.016));
      root.position.x = baseRootX + currentHeadTurn * 0.07;
      root.position.y = baseRootY + Math.abs(currentHeadTurn) * 0.014
        + expressionDelight * 0.030
        - expressionConcern * 0.026
        + Math.sin(elapsed * (0.42 + liveEnergy * 0.24)) * (0.004 + (1 - expressionComposure) * 0.008);
      bodyUniforms.uTime.value = pupilUniforms.uTime.value = elapsed;
      bodyUniforms.uFlow.value = THREE.MathUtils.lerp(bodyUniforms.uFlow.value, flow, 0.035);
      pupilUniforms.uFlow.value = bodyUniforms.uFlow.value;
      bodyUniforms.uDensity.value = THREE.MathUtils.lerp(bodyUniforms.uDensity.value, density, 0.06);
      bodyUniforms.uSocketSparse.value = THREE.MathUtils.lerp(bodyUniforms.uSocketSparse.value, sparse, 0.06);
      bodyUniforms.uPupilSize.value = THREE.MathUtils.lerp(bodyUniforms.uPupilSize.value, pupilSize, 0.055);
      bodyUniforms.uOpacity.value = THREE.MathUtils.lerp(bodyUniforms.uOpacity.value, palette.opacity, 0.035);
      bodyUniforms.uStateEnergy.value = THREE.MathUtils.lerp(bodyUniforms.uStateEnergy.value, palette.energy, 0.035);
      bodyUniforms.uBreath.value = THREE.MathUtils.lerp(bodyUniforms.uBreath.value, palette.breath, 0.035);
      bodyUniforms.uHeadTurn.value = currentHeadTurn;
      const driverListenTarget = current.attention.driver && current.state !== 'silent' ? 1 : 0;
      const passengerListenTarget = current.attention.passenger && current.state !== 'silent' ? 1 : 0;
      bodyUniforms.uDriverListen.value = THREE.MathUtils.lerp(bodyUniforms.uDriverListen.value, driverListenTarget, 0.035);
      bodyUniforms.uPassengerListen.value = THREE.MathUtils.lerp(bodyUniforms.uPassengerListen.value, passengerListenTarget, 0.035);
      const eyeOpenTarget = current.state === 'silent' ? 0 : 1;
      bodyUniforms.uEyeOpen.value = THREE.MathUtils.lerp(bodyUniforms.uEyeOpen.value, eyeOpenTarget, 0.022);
      pupilUniforms.uEyeOpen.value = bodyUniforms.uEyeOpen.value;
      pupilUniforms.uPupilSize.value = THREE.MathUtils.lerp(pupilUniforms.uPupilSize.value, pupilSize, 0.055);
      const eyeLead = attentionX * 0.85 + (attentionX - currentHeadTurn) * 0.55;
      const thoughtGazeX = liveThinkWeight * Math.sin(elapsed * 0.52) * 0.18;
      const thoughtGazeY = liveThinkWeight * (0.05 + Math.sin(elapsed * 0.39 + 1.1) * 0.10);
      const expressionGazeX = (liveVector?.gazeX ?? 0) * 0.46
        + expressionCuriosity * Math.sin(elapsed * 0.47 + 0.6) * 0.06;
      const expressionGazeY = (liveVector?.gazeY ?? 0) * 0.34
        + expressionCuriosity * Math.sin(elapsed * 0.34 + 1.8) * 0.04;
      attentionTarget.set(
        eyeLead + pointer.x * 0.32 + thoughtGazeX + expressionGazeX,
        pointer.y * 0.24 + thoughtGazeY + expressionGazeY,
      );
      bodyUniforms.uEyeAim.value.lerp(attentionTarget, 0.075);
      pupilUniforms.uAttention.value.lerp(attentionTarget, 0.075);
      pupilUniforms.uThink.value = THREE.MathUtils.lerp(pupilUniforms.uThink.value, current.state === 'think' ? 1 : 0, 0.035);
      pupilUniforms.uOpacity.value = THREE.MathUtils.lerp(pupilUniforms.uOpacity.value, Math.min(1, palette.opacity + 0.08), 0.035);
      const live = current.liveExpression;
      const liveMixTarget = live ? 1 : 0;
      bodyUniforms.uLiveMix.value = THREE.MathUtils.lerp(bodyUniforms.uLiveMix.value, liveMixTarget, 0.035);
      pupilUniforms.uLiveMix.value = bodyUniforms.uLiveMix.value;
      if (live) {
        bodyUniforms.uLiveEnergy.value = THREE.MathUtils.lerp(bodyUniforms.uLiveEnergy.value, live.energy, 0.045);
        bodyUniforms.uLiveOpenness.value = THREE.MathUtils.lerp(bodyUniforms.uLiveOpenness.value, live.openness, 0.045);
        bodyUniforms.uLiveTension.value = THREE.MathUtils.lerp(bodyUniforms.uLiveTension.value, live.tension, 0.045);
        bodyUniforms.uLiveTurbulence.value = THREE.MathUtils.lerp(bodyUniforms.uLiveTurbulence.value, live.turbulence, 0.045);
        bodyUniforms.uLiveWarmth.value = THREE.MathUtils.lerp(bodyUniforms.uLiveWarmth.value, live.warmth, 0.045);
        bodyUniforms.uLiveCertainty.value = THREE.MathUtils.lerp(bodyUniforms.uLiveCertainty.value, live.certainty, 0.045);
        bodyUniforms.uLivePulse.value = THREE.MathUtils.lerp(bodyUniforms.uLivePulse.value, live.pulse, 0.07);
        bodyUniforms.uLiveEyeCurve.value = THREE.MathUtils.lerp(bodyUniforms.uLiveEyeCurve.value, live.eyeCurve, 0.055);
        bodyUniforms.uLiveEyeAperture.value = THREE.MathUtils.lerp(bodyUniforms.uLiveEyeAperture.value, live.eyeAperture, 0.055);
        bodyUniforms.uLiveEyeSlant.value = THREE.MathUtils.lerp(bodyUniforms.uLiveEyeSlant.value, live.eyeSlant, 0.055);
        bodyUniforms.uLiveEyeAsymmetry.value = THREE.MathUtils.lerp(bodyUniforms.uLiveEyeAsymmetry.value, live.eyeAsymmetry, 0.055);
        pupilUniforms.uLiveEnergy.value = bodyUniforms.uLiveEnergy.value;
        pupilUniforms.uLiveOpenness.value = bodyUniforms.uLiveOpenness.value;
        pupilUniforms.uLiveTension.value = bodyUniforms.uLiveTension.value;
        pupilUniforms.uLiveTurbulence.value = bodyUniforms.uLiveTurbulence.value;
        pupilUniforms.uLiveCertainty.value = bodyUniforms.uLiveCertainty.value;
        pupilUniforms.uLivePulse.value = bodyUniforms.uLivePulse.value;
        pupilUniforms.uLiveWarmth.value = bodyUniforms.uLiveWarmth.value;
        pupilUniforms.uLiveEyeCurve.value = bodyUniforms.uLiveEyeCurve.value;
        pupilUniforms.uLiveEyeAperture.value = bodyUniforms.uLiveEyeAperture.value;
        pupilUniforms.uLiveEyeSlant.value = bodyUniforms.uLiveEyeSlant.value;
        pupilUniforms.uLiveEyeAsymmetry.value = bodyUniforms.uLiveEyeAsymmetry.value;
        pupilUniforms.uLivePupilDilation.value = THREE.MathUtils.lerp(pupilUniforms.uLivePupilDilation.value, live.pupilDilation, 0.055);
      }
      colorATarget.set(palette.a); colorBTarget.set(palette.b); pupilColorTarget.set(palette.pupil);
      bodyUniforms.uColorA.value.lerp(colorATarget, 0.025); bodyUniforms.uColorB.value.lerp(colorBTarget, 0.025); pupilUniforms.uColor.value.lerp(pupilColorTarget, 0.03);
      renderer.render(scene, camera); frame = requestAnimationFrame(animate);
    };
    animate();

    return () => {
      cancelAnimationFrame(frame); observer.disconnect();
      mount.removeEventListener('pointerdown', onPointerDown); mount.removeEventListener('pointermove', onPointerMove);
      mount.removeEventListener('pointerup', onPointerUp); mount.removeEventListener('pointercancel', onPointerUp);
      mount.removeEventListener('pointerleave', onPointerLeave);
      bodyGeometry.dispose(); pupilGeometry.dispose();
      bodyMaterial.dispose(); pupilMaterial.dispose(); renderer.dispose(); renderer.domElement.remove();
    };
    // The WebGL renderer is mounted once; live values are read through propsRef.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div className="particle-stage" ref={mountRef} aria-label="可交互的 YITU BOT 3D 粒子生命体" />;
}
