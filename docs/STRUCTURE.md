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
│       ├── audio_backend.py
│       ├── cli.py
│       ├── errors.py
│       ├── gui.py
│       ├── paths.py
│       ├── recording.py
│       └── windows_audio_backend.py
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
│       └── _template/
│           ├── PRD.md
│           ├── PROPOSAL.md
│           ├── PLAN.md
│           ├── PROGRESS.md
│           └── TEST.md
├── AI_AGENT_RULES.md
├── AGENTS.md
├── PROMPT.md
├── prompt_pai.md
├── pyproject.toml
├── README.md
├── Instalar.bat
├── Gravar.bat
└── Abrir Gravador.vbs
```

---

## Responsabilidades por arquivo/pasta

| Caminho | Responsabilidade |
|---|---|
| `src/gravador_audio/audio_backend.py` | Interface abstrata `AudioBackend` + `UnavailableAudioBackend` (stub) |
| `src/gravador_audio/windows_audio_backend.py` | Implementação real: captura via `soundcard`, mixagem via `numpy`, encode via `lameenc` |
| `src/gravador_audio/recording.py` | `RecordingService` — orquestra estados (`IDLE → RECORDING → FINALIZING → COMPLETED`), delega ao backend |
| `src/gravador_audio/cli.py` | Entrypoint CLI via `argparse` — executa gravação por duração fixa |
| `src/gravador_audio/gui.py` | Interface gráfica `tkinter` — permite gravar/parar interativamente |
| `src/gravador_audio/paths.py` | Retorna pasta padrão de saída (`~/Music/gravador_audio`) |
| `src/gravador_audio/errors.py` | Hierarquia de erros do domínio |
| `tests/` | Testes unitários com `unittest` |
| `scripts/install_windows.ps1` | Cria `.venv` e instala dependências via pip |
| `Instalar.bat` | Chama o script PowerShell de instalação |
| `Gravar.bat` | Abre terminal guiado para gravação via CLI |
| `Abrir Gravador.vbs` | Abre interface gráfica sem mostrar janela de prompt |

---

## Padrão de camadas

```text
gui.py / cli.py
    └── RecordingService (recording.py)
            └── AudioBackend (audio_backend.py)
                    └── WindowsAudioBackend (windows_audio_backend.py)
                            ├── soundcard  (captura de áudio)
                            ├── numpy      (mixagem de canais)
                            └── lameenc    (encode MP3)
```

---

## Fluxo de gravação

1. Usuário escolhe modo (microfone, sistema ou ambos) e pasta de saída
2. `RecordingService.start()` prepara o caminho de saída e chama `backend.start(path)`
3. `WindowsAudioBackend` inicia thread de captura, lê chunks de áudio em loop
4. Cada chunk é mixado (média entre fontes) e encodado em MP3 incrementalmente
5. Ao parar: `RecordingService.stop()` → `backend.stop()` → thread finaliza, flush do encoder, arquivo fechado

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

### Rodar via CLI

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.cli --duration 20
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.cli --duration 20 --microphone-only
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.cli --duration 20 --system-only
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
- O projeto usa `soundcard` que depende do WASAPI do Windows — não funciona em outros SOs.
- A thread de gravação é daemon (`daemon=True`) e erros são capturados e relançados em `stop()`.
- Não alterar `.env` (não existe, mas não criar).
- Não expor segredos.
- Não commitar arquivos sensíveis.
- Não rodar comando destrutivo.
