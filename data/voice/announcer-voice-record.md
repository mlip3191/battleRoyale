# Announcer voice record (DECISIONS D-67)

This is the consent and provenance record for the announcer's reference clip,
`data/voice/announcer-reference.wav`. `ANNOUNCER_VOICE_CONSENT_FILE` points here.

## What the voice is

- **Synthetic.** The voice was designed by an AI voice-design model from a short text
  description. It is not a recording of anyone, and it is not modeled on, or prompted after,
  any real person, announcer, or celebrity (ARCHITECTURE §11, D-09, D-67).
- No person's voice was recorded, uploaded, or cloned to make it, so there is no voice owner
  whose consent is needed. This record stands in for the consent note.

## Tool and license

- **Model:** `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign`
  (https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign), model card metadata
  `license: apache-2.0`.
- **Package:** `qwen-tts` 0.1.1 from PyPI (license `Apache-2.0`); source repository
  https://github.com/QwenLM/Qwen3-TTS (license file: Apache License 2.0).
- **License terms:** Apache License 2.0 (https://www.apache.org/licenses/LICENSE-2.0), a
  permissive license that grants a "perpetual, worldwide, non-exclusive, no-charge,
  royalty-free, irrevocable copyright license to reproduce, prepare Derivative Works of,
  publicly display, publicly perform, sublicense, and distribute the Work". It has no clause
  that restricts how audio generated with the model is used, so using that audio in this
  public course project is allowed. (The model weights themselves are not in the repo.)
- **How it was used:** once, by hand, on a team member's own computer (CPU, float32, eager
  attention). The app never calls this tool: no SDK, package, or API for it is in the repo.
  At run time the app only sends this clip as the reference voice on the course TTS
  service's existing speech request.

## Exact generation settings

- **Method:** `Qwen3TTSModel.generate_voice_design(text=..., instruct=..., language="English")`
- **Voice description (instruct), exact:**
  `Deep male arena fight announcer with a raspier, rougher, more weathered throat, still booming and slow, gravel on every line`
- **Spoken script, exact:**
  `Ladies and gentlemen! Welcome to the main event of the evening! In this corner, weighing in at over one thousand pounds, the apex predator of the Arctic, the polar bear! And in the opposite corner, hunting as one, a pack of six gray wolves! It's time... to... battle!`
- **Seed:** 1043 (second take of this description)
- **Generated:** 2026-11-19 (America/Denver)

## Processing

1. Loudness-normalized to -16 LUFS integrated, -1.5 dBTP (ffmpeg `loudnorm`, two passes),
   24 kHz mono. Full take: 20.72 s.
2. Trimmed for the repo on 2026-11-20 to the first 12.65 s (cut in the pause after
   "the polar bear!", with a 0.1 s fade-out), 16-bit PCM WAV, 24 kHz mono.
   The clip says: "Ladies and gentlemen! Welcome to the main event of the evening! In this
   corner, weighing in at over one thousand pounds, the apex predator of the Arctic, the polar
   bear!"

## The file in the repo

- `data/voice/announcer-reference.wav`: 12.65 s, 24 kHz, mono, 16-bit PCM, 607,244 bytes
- SHA-256: `80eee7817131611be44fb129e75077b2de3466062d7e48e5adc8bc4dd95d4443`

## Approval

Approved by the PM on issue #45 (2026-11-20) with these guardrails: synthetic only with a
generic prompt; the tool's license allows public use of the output and is recorded here;
the app stays on course services; if the reference voice fails at run time the show falls
back to the `default` voice or captions; shipped as a separate small PR.
