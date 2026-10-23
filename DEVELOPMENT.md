# Desenvolvimento do Voice Notes

[← Voltar ao README](README.md)

## Visão geral

```text
Microfone / áudio do sistema / arquivo / YouTube
                         ↓
                   Áudio de entrada
                         ↓
        Whisper local (faster-whisper / CTranslate2)
                         ├── separação opcional com pyannote
                         ↓
                  transcription.md
                         ↓
          Codex CLI / Claude Code / API configurada
                         ↓
                     summary.md
```

A transcrição e o resumo rodam em um subprocesso separado da interface. Trabalhos pendentes são guardados nos dados do aplicativo e podem ser retomados enquanto o áudio original existir.

O aplicativo usa Python 3.12+, CustomTkinter/Tk para a interface, PyAudioWPatch para captura no Windows e PyInstaller/Inno Setup para o instalador. A exportação usa python-docx e ReportLab; a importação do YouTube usa yt-dlp e imageio-ffmpeg.

## Preparar o ambiente

Requisitos: Windows 10 ou 11 de 64 bits, Python 3.12+ e internet para instalar dependências. Inno Setup 6 só é necessário para gerar o instalador.

```powershell
git clone https://github.com/VictorJurado18/voice_notes.git
cd voice_notes
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_windows.ps1
```

O script cria `.venv`. Para abrir a interface a partir do código:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m record_transcript_resume.gui
```

`Open Recorder.vbs` abre o widget sem terminal; `Open Recorder.bat` mantém o terminal visível para diagnóstico. `Record.bat` inicia a gravação guiada pela CLI.

## Linha de comando

Na raiz do repositório, com `$env:PYTHONPATH = "src"`:

```powershell
# Gravar microfone e áudio do sistema por 20 segundos
.\.venv\Scripts\python.exe -m record_transcript_resume.cli record --duration 20

# Gravar apenas o microfone
.\.venv\Scripts\python.exe -m record_transcript_resume.cli record --duration 20 --microphone-only

# Processar um arquivo existente
.\.venv\Scripts\python.exe -m record_transcript_resume.cli process .\reuniao.mp3 --language pt --model small --provider codex
```

`record` aceita `--output-dir`, `--duration`, `--microphone-only`, `--system-only` e `--no-pipeline`. `process` aceita `--language` e `--model`. Ambos aceitam `--provider codex|claude|api`; `api` usa a configuração salva pelo widget.

## Testes e instalador

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest -q
```

Com o Inno Setup 6 instalado:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1
```

O instalador resultante é `dist\VoiceNotes-Setup-x.y.z.exe`, com a versão definida em `installer/VoiceNotes.iss`. Para gerar apenas a pasta do aplicativo em `dist\VoiceNotes`, use `-SkipInstaller` no mesmo script.

## Publicação

Para uma alteração funcional que será publicada:

1. Atualize a **mesma versão** em `pyproject.toml` e `installer/VoiceNotes.iss`.
2. Atualize os destaques em `src/record_transcript_resume/release_notes.py` com o que realmente entrou na versão.
3. Execute os testes e confira a gravação, transcrição, resumo, Biblioteca e inicialização pela bandeja em uma instalação de teste.
4. Faça a PR. O merge na `main` aciona o GitHub Actions, que testa e tenta gerar e publicar `VoiceNotes-Setup-x.y.z.exe` nas [releases deste repositório](https://github.com/VictorJurado18/voice_notes/releases).

A versão 0.10.30 também será publicada no [repositório antigo](https://github.com/VictorJurado18/voice-notes-releases/releases) para atualizar instalações que ainda consultam aquele endereço. A partir dela, o app consulta as releases deste repositório.

Confira o workflow e o resultado da publicação antes de anunciar um instalador como disponível. Alterações só de documentação não mudam a versão.

## Mapa do código

| Caminho | Responsabilidade |
|---|---|
| `src/record_transcript_resume/gui.py` | Interface e navegação |
| `src/record_transcript_resume/recording.py` e `windows_audio_backend.py` | Captura de áudio |
| `src/record_transcript_resume/transcription.py` e `diarization.py` | Transcrição e falantes |
| `src/record_transcript_resume/pipeline.py` e `synthesis.py` | Processamento e resumos |
| `src/record_transcript_resume/library.py` e `exports.py` | Biblioteca e exportações |
| `src/record_transcript_resume/jobs.py` | Fila e retomada |
| `installer/VoiceNotes.iss` | Configuração do instalador |
| `tests/` | Testes automatizados |
