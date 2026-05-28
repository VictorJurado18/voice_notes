# STRUCTURE.md

> **Fonte de verdade**: [`docs/STRUCTURE.md`](docs/STRUCTURE.md)
> Este arquivo é uma cópia de conveniência na raiz. Em caso de divergência, o arquivo em `docs/` prevalece.

---

## Objetivo

Este documento descreve a estrutura real do repositório e onde cada responsabilidade vive.

Atualize apenas quando houver mudança relevante na arquitetura, pastas, módulos ou fluxo técnico.

---

## Estrutura geral

```text
/
├── src/
│   └── gravador_audio/
│       ├── __init__.py
│       ├── audio_backend.py        — interface abstrata AudioBackend
│       ├── cli.py                  — entrypoint CLI
│       ├── errors.py               — hierarquia de erros do domínio
│       ├── gui.py                  — interface gráfica tkinter
│       ├── log.py                  — log persistente em gravador.log
│       ├── paths.py                — pasta padrão de saída
│       ├── pipeline.py             — pipeline pós-gravação (transcrição + síntese)
│       ├── recording.py            — RecordingService (orquestrador de estado)
│       ├── synthesis.py            — síntese via Claude API
│       ├── transcription.py        — transcrição via faster-whisper
│       └── windows_audio_backend.py — captura WASAPI (mic callback + loopback blocking)
├── tests/
│   ├── test_paths.py
│   ├── test_recording_service.py
│   └── test_windows_audio_backend.py
├── scripts/
│   └── install_windows.ps1
├── docs/
│   ├── PROJECT_CONTEXT.md
│   ├── STRUCTURE.md
│   ├── CURRENT_STATE.md
│   └── specs/
│       ├── _template/
│       │   ├── PRD.md
│       │   ├── PROPOSAL.md
│       │   ├── PLAN.md
│       │   ├── PROGRESS.md
│       │   └── TEST.md
│       ├── 0001-disk-space-alert/
│       └── 0002-post-recording-pipeline/
├── gravacoes/                      — saída padrão das gravações (git-ignorado)
├── gravador.log                    — log de diagnóstico de execução
├── AI_AGENT_RULES.md
├── AGENTS.md
├── CLAUDE.md
├── OBJECTIVES.md
├── PROJECT_CONTEXT.md
├── PROMPT.md
├── prompt_pai.md
├── pyproject.toml
├── README.md
├── STRUCTURE.md
├── Instalar.bat
├── Gravar.bat
└── Abrir Gravador.vbs
```

---

## Responsabilidades por arquivo

| Caminho | Responsabilidade |
|---|---|
| `src/gravador_audio/audio_backend.py` | Interface abstrata `AudioBackend` + `UnavailableAudioBackend` (stub) |
| `src/gravador_audio/windows_audio_backend.py` | Captura WASAPI: mic via callback, loopback via thread blocking + acumuladores independentes |
| `src/gravador_audio/recording.py` | `RecordingService` — máquina de estados (`IDLE → RECORDING → FINALIZING → COMPLETED → ERROR`) |
| `src/gravador_audio/pipeline.py` | Orquestra pipeline pós-gravação: transcrição → síntese → salva arquivos |
| `src/gravador_audio/transcription.py` | Chama `faster-whisper` localmente, retorna texto com timestamps |
| `src/gravador_audio/synthesis.py` | Chama Claude API para gerar resumo estruturado |
| `src/gravador_audio/cli.py` | Entrypoint CLI via `argparse` — gravação por duração fixa |
| `src/gravador_audio/gui.py` | Interface `tkinter` — iniciar/parar, EQ visualizer, feedback de dispositivos e erros |
| `src/gravador_audio/log.py` | `log()` e `log_exception()` — escreve em `gravador.log` na raiz |
| `src/gravador_audio/paths.py` | Retorna pasta padrão de saída (`~/Music/gravador_audio`) |
| `src/gravador_audio/errors.py` | `RecordingError`, `AudioBackendUnavailableError`, etc. |
| `tests/` | Testes unitários com `unittest` |
| `scripts/install_windows.ps1` | Cria `.venv` e instala dependências via pip |
| `gravador.log` | Log de diagnóstico gerado em runtime (não versionado) |
| `OBJECTIVES.md` | Objetivos funcionais e de qualidade do projeto, com status atual |

---

## Padrão de camadas

```text
gui.py / cli.py
    └── RecordingService (recording.py)
            └── WindowsAudioBackend (windows_audio_backend.py)
                    ├── pyaudiowpatch  (captura WASAPI — mic e loopback)
                    ├── numpy          (mixagem e resampling)
                    └── lameenc        (encode MP3 incremental)

    └── pipeline.py
            ├── transcription.py  →  faster-whisper  (local)
            └── synthesis.py      →  Claude API       (anthropic SDK)
```

---

## Fluxo de gravação

1. Usuário escolhe modo e pasta → `RecordingService.start()` → `WindowsAudioBackend.start(path)`
2. Backend abre streams: mic em callback, loopback em blocking thread separada
3. Loop principal drena ambas as filas com `get_nowait()`, acumula em buffers numpy independentes
4. A cada 100 ms de dados disponíveis: mixagem → encode MP3 → escrita incremental no arquivo
5. `stop()` → sinaliza evento → loop encerra → flush do encoder → arquivo fechado

---

## Hierarquia de erros

```text
RecordingError
├── InvalidRecordingStateError   (ex: stop() sem gravação ativa)
├── AudioBackendUnavailableError (ex: dispositivo WASAPI não encontrado)
└── OutputPathError              (ex: pasta inválida)
```

---

## Comandos reais

### Instalar

```powershell
powershell -File scripts\install_windows.ps1
# ou duplo clique em Instalar.bat
```

### Interface gráfica

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.gui
# ou duplo clique em "Abrir Gravador.vbs"
```

### CLI — gravação

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.cli gravar --duration 20
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.cli gravar --duration 20 --microphone-only
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.cli gravar --duration 20 --system-only
```

### CLI — processar MP3 existente

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.cli processar caminho\para\arquivo.mp3
```

### Testes

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m unittest discover -s tests
```

### Lint/format

Não identificado no repositório.

---

## Pontos de atenção

- `PYTHONPATH=src` é obrigatório para rodar sem instalar o pacote.
- `pyaudiowpatch` depende do WASAPI do Windows — não funciona em outros SOs.
- A thread de gravação é daemon (`daemon=True`); erros são capturados e relançados em `stop()`.
- `gravador.log` é o primeiro lugar a verificar quando algo não funciona.
- Síntese requer `ANTHROPIC_API_KEY` — não expor nem commitar.
- Não alterar `.env` (não existe, mas não criar).
