# STRUCTURE.md

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
│       ├── pipeline.py             — pipeline pós-gravação
│       ├── recording.py            — RecordingService (orquestrador de estado)
│       ├── synthesis.py            — síntese via Claude API
│       ├── transcription.py        — transcrição via faster-whisper
│       └── windows_audio_backend.py — captura WASAPI
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
├── gravacoes/                      — saída das gravações (git-ignorado)
├── gravador.log                    — log de diagnóstico (gerado em runtime)
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

## Responsabilidades por arquivo/pasta

| Caminho | Responsabilidade |
|---|---|
| `src/gravador_audio/audio_backend.py` | Interface abstrata `AudioBackend` + `UnavailableAudioBackend` (stub) |
| `src/gravador_audio/windows_audio_backend.py` | Captura WASAPI: mic via callback, loopback via thread blocking + acumuladores por fonte |
| `src/gravador_audio/recording.py` | `RecordingService` — máquina de estados (`IDLE → RECORDING → FINALIZING → COMPLETED → ERROR`) |
| `src/gravador_audio/pipeline.py` | Orquestra pipeline pós-gravação: transcrição → síntese → salva arquivos .md |
| `src/gravador_audio/transcription.py` | Chama `faster-whisper` localmente, retorna texto com timestamps |
| `src/gravador_audio/synthesis.py` | Chama Claude API para gerar resumo estruturado (Contexto, Decisões, Plano de ação) |
| `src/gravador_audio/cli.py` | Entrypoint CLI via `argparse` — subcomandos `gravar` e `processar` |
| `src/gravador_audio/gui.py` | Interface `tkinter` — iniciar/parar, EQ visualizer, feedback de dispositivos e erros |
| `src/gravador_audio/log.py` | `log()` e `log_exception()` — escreve em `gravador.log` na raiz |
| `src/gravador_audio/paths.py` | Retorna pasta padrão de saída (`~/Music/gravador_audio`) |
| `src/gravador_audio/errors.py` | Hierarquia de erros do domínio |
| `tests/` | Testes unitários com `unittest` |
| `scripts/install_windows.ps1` | Cria `.venv` e instala dependências via pip |
| `gravador.log` | Log de diagnóstico gerado em runtime (não versionado) |
| `Instalar.bat` | Chama o script PowerShell de instalação |
| `Gravar.bat` | Abre terminal guiado para gravação via CLI |
| `Abrir Gravador.vbs` | Abre interface gráfica sem mostrar janela de prompt |

---

## Padrão de camadas

```text
gui.py / cli.py
    └── RecordingService (recording.py)
            └── WindowsAudioBackend (windows_audio_backend.py)
                    ├── pyaudiowpatch  (mic callback + loopback blocking thread)
                    ├── numpy          (mixagem, resampling, acumuladores)
                    └── lameenc        (encode MP3 incremental)

    └── pipeline.py
            ├── transcription.py  →  faster-whisper  (local)
            └── synthesis.py      →  Claude API       (anthropic SDK)
```

---

## Fluxo de gravação

1. Usuário escolhe modo e pasta → `RecordingService.start()` → `WindowsAudioBackend.start(path)`
2. Backend resolve dispositivos WASAPI (mic e loopback), abre streams
3. Mic: stream callback → put em `mic_q`; Loopback: thread blocking → read + put em `loop_q`
4. Loop principal drena ambas as filas com `get_nowait()`, acumula em buffers numpy separados
5. A cada 100 ms disponíveis em qualquer fonte: mixagem → encode MP3 → escrita incremental
6. `stop()` → sinaliza evento → loop encerra → flush encoder → arquivo fechado
7. Opcionalmente: `pipeline.py` transcribe + sintetiza → salva `transcricao.md` e `resumo.md`

---

## Hierarquia de erros

```text
RecordingError
├── InvalidRecordingStateError  (ex: stop() sem gravação em andamento)
├── AudioBackendUnavailableError (ex: dispositivo não encontrado)
└── OutputPathError             (ex: pasta inválida, arquivo já existe)
```

---

## Comandos reais

### Instalar

```powershell
# Duplo clique em Instalar.bat
# Ou diretamente:
powershell -File scripts\install_windows.ps1
```

### Rodar interface gráfica

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.gui
```

### Rodar via CLI — gravação

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.cli gravar --duration 20
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.cli gravar --duration 20 --microphone-only
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.cli gravar --duration 20 --system-only
```

### Rodar via CLI — processar MP3 existente

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.cli processar caminho\para\arquivo.mp3
```

### Rodar testes

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
- `ANTHROPIC_API_KEY` é necessária para síntese — não expor nem commitar.
- Não alterar `.env` (não existe, mas não criar).
- Não expor segredos.
- Não commitar arquivos sensíveis.
- Não rodar comando destrutivo.
