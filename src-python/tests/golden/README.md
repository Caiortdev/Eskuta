# Reuniões golden — eval framework Eskuta

Este diretório guarda as **reuniões de referência** usadas pelo eval
framework (`src-python/evaluation/`) pra medir WER, DER e ata-score.

> ⚠️ Os áudios reais NÃO ficam no repo (são grandes e podem conter
> dados sensíveis). Adicione paths via `.gitignore` ou Git LFS conforme
> sua estratégia de team. Aqui versionamos só os **manifests** e as
> referências textuais.

## Estrutura esperada por golden

```
tests/golden/
├── manifest.json                            # lista de goldens
├── sprint-planning-01/
│   ├── audio.mp3                            # 🚫 NÃO commitado (gitignore)
│   ├── reference.transcript.txt             # ✅ commitado
│   ├── reference.diarization.json           # ✅ commitado (opcional)
│   └── reference.minutes.json               # ✅ commitado (opcional)
└── 1on1-feedback-02/
    └── ...
```

## Schema do `manifest.json`

Validado por `evaluation.manifest.BenchmarkManifest`. Exemplo mínimo:

```json
{
  "name": "MVP golden suite v1",
  "description": "5 reuniões reais transcritas humanamente.",
  "goldens": [
    {
      "id": "sprint-planning-01",
      "audio_path": "sprint-planning-01/audio.mp3",
      "reference_transcript_path": "sprint-planning-01/reference.transcript.txt",
      "reference_diarization_path": "sprint-planning-01/reference.diarization.json",
      "reference_minutes_path": "sprint-planning-01/reference.minutes.json",
      "duration_sec": 3600.0,
      "language": "pt",
      "notes": "Planning de sprint da equipe Eskuta. 3 participantes."
    }
  ]
}
```

## Schema dos arquivos de referência

### `reference.transcript.txt`

Texto puro UTF-8, idealmente revisado por humano. Pontuação OK. WER
do jiwer normaliza casing/whitespace por default; pra customizar,
ver `evaluation.metrics.compute_wer`.

### `reference.diarization.json`

Array JSON com `{start_sec, end_sec, speaker_id}`:

```json
[
  { "start_sec": 0.0, "end_sec": 5.2, "speaker_id": "JOAO" },
  { "start_sec": 5.5, "end_sec": 12.1, "speaker_id": "MARIA" },
  { "start_sec": 12.3, "end_sec": 18.7, "speaker_id": "JOAO" }
]
```

Speakers podem ser nomes humanos OU IDs anônimos — DER do
`pyannote.metrics` é resiliente a relabeling.

### `reference.minutes.json`

JSON no schema `app.services.minutes.schemas.MinutesOutput` —
exatamente o que o LLM deveria emitir. Use o `FEW_SHOT_EXAMPLE_MINUTES`
do `prompts.py` como template.

## Hypothesis files (saída do pipeline real)

Pra rodar `evaluation.runner` end-to-end, o pipeline precisa produzir
arquivos hypothesis com naming convention:

- `{id}.transcript.hyp.txt`
- `{id}.diarization.hyp.json`
- `{id}.minutes.hyp.json`

Esses ficam GITIGNORED — são reproduzidos a cada run.

## Como adicionar uma golden real

1. Faça upload do áudio + revisão humana da transcrição
2. (Opcional) marque diarização manualmente — ferramentas: ELAN, Praat,
   ou exporte do pyannote e edite
3. (Opcional) escreva uma ata "ideal" no schema `MinutesOutput`
4. Adicione entry em `manifest.json`
5. Rode `python -m evaluation.runner tests/golden/manifest.json` pra
   gerar o primeiro baseline

## Goldens recomendadas pro MVP (5 reuniões alvo)

Por diversidade de cenário:

1. **Sprint planning** (~60min, 3-5 speakers, tópicos técnicos)
2. **1on1 feedback** (~30min, 2 speakers, conteúdo sensível)
3. **All-hands** (~45min, 1 speaker dominante, perguntas no fim)
4. **Reunião com cliente** (~45min, 3 speakers, contratos/prazos)
5. **Brainstorm** (~30min, 4-5 speakers, sobreposição alta)

Cada uma estressa um aspecto diferente do pipeline (chunking, diarização,
LLM extraction, anti-alucinação).
