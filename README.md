<div align="center">

<img src="assets/voice-notes.png" alt="Voice Notes" width="96">

# Voice Notes

**Grave, transcreva e resuma reuniões, aulas e chamadas — direto no seu Windows.**

[![Release](https://img.shields.io/github/v/release/VictorJurado18/voice-notes-releases?label=vers%C3%A3o)](https://github.com/VictorJurado18/voice-notes-releases/releases/latest)
![Plataforma](https://img.shields.io/badge/Windows-10%20%7C%2011%20(64--bit)-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![Whisper](https://img.shields.io/badge/transcri%C3%A7%C3%A3o-Whisper%20local-6E56CF)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green)](LICENSE)

[**Baixar o instalador**](https://github.com/VictorJurado18/voice-notes-releases/releases/latest) ·
[Primeiros passos](#primeiros-passos) ·
[Solução de problemas](#solução-de-problemas) ·
[Desenvolvimento](DEVELOPMENT.md)

</div>

---

O **Voice Notes** captura o microfone, o áudio do sistema ou ambos, transcreve localmente com [Whisper](https://github.com/SYSTRAN/faster-whisper) e, se você quiser, gera resumos estruturados com Codex, Claude Code ou qualquer API de IA compatível. O áudio nunca sai do seu computador.

## Índice

- [Recursos](#recursos)
- [Requisitos](#requisitos)
- [Primeiros passos](#primeiros-passos)
- [Configuração](#configuração)
- [Outras formas de uso](#outras-formas-de-uso)
- [Solução de problemas](#solução-de-problemas)
- [Privacidade](#privacidade)
- [Tecnologias](#tecnologias)
- [Contribuindo](#contribuindo)
- [Licença](#licença)

## Recursos

| | |
|---|---|
| 🎙️ **Gravação** | Microfone, áudio do sistema ou os dois ao mesmo tempo. O áudio é salvo antes de qualquer processamento. |
| 📝 **Transcrição local** | Whisper rodando na sua máquina, com aceleração por GPU NVIDIA e fallback automático para CPU. |
| 👥 **Separação de falantes** | Identificação opcional de *Pessoa 1*, *Pessoa 2*… com pyannote, também local. |
| ✨ **Resumos com IA** | Modelos de resumo para reunião, aula, entrevista e plano de ação. |
| 📥 **Importação** | Arquivos de áudio, transcrições prontas (`.txt`/`.md`) e vídeos do YouTube autorizados. |
| 📚 **Biblioteca** | Busca, filtros, favoritos, etiquetas, edição e exportação em PDF ou DOCX. |
| ⚙️ **Processamento em segundo plano** | Fila de trabalhos com retomada, ícone na bandeja e atualizações pelo próprio app. |

## Requisitos

- Windows 10 ou 11, 64 bits
- Internet no primeiro uso de cada modelo Whisper (download único)
- *Opcional:* GPU NVIDIA compatível para transcrição acelerada
- *Opcional:* conta Codex, Claude Code ou chave de API para resumos

O instalador já inclui tudo o que o app precisa — não é necessário instalar Python nem usar terminal.

## Primeiros passos

1. **Instale.** Baixe `VoiceNotes-Setup-x.y.z.exe` na [página de versões](https://github.com/VictorJurado18/voice-notes-releases/releases/latest) e execute. Se quiser resumos via Codex CLI ou Claude Code, marque a instalação opcional deles.
2. **Configure a gravação.** Abra **Voice Notes** pelo menu Iniciar. Na página **Gravar**, escolha a **Fonte de áudio** e confira a pasta em **Salvar em**.
3. **Escolha o resultado.** Em **Depois de parar**, selecione **Salvar só o áudio**, **Áudio + transcrição** ou **Áudio + transcrição + resumo**.
4. **Grave.** Clique em **Iniciar gravação** e, ao terminar, em **Parar**. Acompanhe o processamento em **Processos** — você pode ocultar a janela enquanto ele roda.

Cada gravação ganha sua própria pasta, por padrão em `Música\record-transcript-resume`:

```text
recording-AAAAMMDD-HHMMSS/
├── recording-AAAAMMDD-HHMMSS.mp3
├── transcription.md   # se transcrito
└── summary.md         # se resumido
```

Gravações salvas só como áudio podem ser processadas depois pela **Biblioteca**.

## Configuração

### Resumos com IA

Em **Ajustes → Resumos e IA**:

- **Codex ou Claude Code** — clique em **Conectar conta no navegador** e conclua o login.
- **API por token** — clique em **+ Novo Provider** e informe URL, modelo e chave. A chave é guardada no Cofre de Credenciais do Windows.

A transcrição funciona sem nenhum provider configurado. Use **Ajustes → Diagnóstico** para testar a conexão (o teste pode consumir uso da sua conta).

### Transcrição

Em **Ajustes → Transcrição**, escolha idioma e modelo:

| Modelo | Indicado para |
|---|---|
| `tiny`, `base` | Máquinas modestas, rascunhos rápidos |
| `small` | **Ponto de partida recomendado** — bom equilíbrio |
| `medium`, `large-v3` | Máxima qualidade, exige mais memória e tempo |

**Testar modelo** confirma que o modelo carrega e mostra se está usando GPU ou CPU. GPUs AMD e Intel usam a CPU nesta versão.

### Separação de falantes

1. Aceite as condições do modelo [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) no Hugging Face.
2. Crie um token de **leitura** e salve-o em **Ajustes → Transcrição**.
3. Ative **Separar falantes** em cada gravação ou importação onde quiser usar.

A opção fica desligada por padrão. Os nomes reais não são descobertos automaticamente — revise as sugestões e aplique nomes na **Biblioteca**.

## Outras formas de uso

| Se você já tem… | Abra | E faça |
|---|---|---|
| Um arquivo de áudio | **Arquivo** | Importe e escolha transcrição, resumo ou ambos |
| Um texto transcrito | **Arquivo** | Cole o texto ou abra um `.txt`/`.md` para resumir |
| Um vídeo autorizado | **YouTube** | Cole o link e escolha o resultado |
| Uma gravação salva | **Biblioteca** | Ouça, edite, exporte ou processe depois |

A importação preserva o arquivo original e cria uma cópia na pasta de resultados. Na Biblioteca, **Escolher pasta** permite navegar por outro local sem alterar o destino das próximas gravações.

**Minimizar** reduz o app a uma etiqueta flutuante; **Ocultar** o envia para a bandeja do Windows. Novas versões podem ser instaladas em **Ajustes → Atualizações**.

## Solução de problemas

| Sintoma | O que verificar |
|---|---|
| A janela sumiu | Procure o ícone perto do relógio (inclusive na seta `^`) e dê dois cliques. |
| O resumo não foi gerado | Confira o provider em **Ajustes → Resumos e IA** e teste em **Diagnóstico**. A transcrição continua salva. |
| A transcrição falhou | Veja **Processos → Ver erro** e use **Testar modelo** em **Ajustes → Transcrição**. |
| Erro 403 na separação de falantes | Confirme que aceitou as condições no Hugging Face e que o token tem permissão de leitura. |
| O áudio do sistema não foi gravado | Use **Sistema** ou **Microfone + sistema** e confira o dispositivo de saída padrão do Windows. |

**Ajustes → Diagnóstico** verifica pasta de saída, microfone, áudio do sistema e serviços de IA. O log técnico fica em `%LOCALAPPDATA%\Voice Notes\recorder.log` — anexe-o ao [abrir uma issue](https://github.com/VictorJurado18/voice_notes/issues), removendo qualquer conteúdo confidencial.

## Privacidade

- **Gravação, transcrição e separação de falantes** acontecem inteiramente no seu computador.
- **Resumos** enviam apenas o *texto* transcrito ao provider escolhido. Verifique os termos desse serviço antes de processar material sensível.
- **YouTube** acessa somente o link informado para baixar o áudio.
- Todos os arquivos ficam na pasta que você definiu.

## Tecnologias

| Camada | Ferramentas |
|---|---|
| Interface | CustomTkinter / Tk, pystray |
| Captura de áudio | PyAudioWPatch (WASAPI), lameenc |
| Transcrição | faster-whisper (CTranslate2), pyannote.audio |
| Resumos | Codex CLI, Claude Code, APIs compatíveis |
| Exportação | python-docx, ReportLab |
| Importação | yt-dlp, imageio-ffmpeg |
| Distribuição | PyInstaller, Inno Setup, GitHub Actions |

## Contribuindo

Configuração do ambiente, CLI, testes, build do instalador e processo de release estão em [DEVELOPMENT.md](DEVELOPMENT.md). Bugs e sugestões são bem-vindos nas [issues](https://github.com/VictorJurado18/voice_notes/issues).

Os instaladores publicados e o histórico de versões ficam em [voice-notes-releases](https://github.com/VictorJurado18/voice-notes-releases/releases).

## Licença

Distribuído sob a [licença MIT](LICENSE). Componentes de terceiros incluídos no instalador mantêm suas próprias licenças — veja [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

<div align="center">
Feito por <a href="https://github.com/VictorJurado18">Victor Nemeth Jurado</a>
</div>
