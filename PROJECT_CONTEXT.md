# PROJECT_CONTEXT.md

> **Fonte de verdade**: [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md)
> Este arquivo é uma cópia de conveniência na raiz. Em caso de divergência, o arquivo em `docs/` prevalece.

---

## Nome do projeto

gravador_audio

---

## Objetivo

Aplicação desktop Windows para gravar chamadas e reuniões em MP3, capturando microfone
e áudio do sistema simultaneamente, com transcrição local e síntese automática
(contexto, decisões, plano de ação) via Claude API após a gravação.

---

## Problema que o projeto resolve

Profissionais que participam de chamadas frequentes precisam registrar ambas as vozes
(microfone local + áudio remoto via speaker) e obter um resumo estruturado sem trabalho
manual. Ferramentas pagas resolvem parcialmente; este projeto oferece solução local,
gratuita e controlada pelo usuário.

---

## Usuários ou público-alvo

- Profissionais com muitas reuniões e chamadas que querem registro automático
- Criadores de conteúdo que gravam microfone + áudio do sistema juntos
- Usuários técnicos que preferem linha de comando e controle total sobre os dados

---

## Stack principal

- Linguagem: Python 3.12+
- Captura de áudio: `pyaudiowpatch` (WASAPI loopback para Windows)
- Encoder MP3: `lameenc` (puro Python, sem binário externo)
- Mixagem: `numpy`
- Transcrição: `faster-whisper` (local, modelo small)
- Síntese: Claude API (`anthropic` SDK, modelo claude-sonnet)
- Interface gráfica: `tkinter` (incluso no Python padrão)
- Interface CLI: `argparse`
- Containerização: Não utilizada
- Cloud: Apenas Claude API para síntese (nenhum áudio enviado externamente)
- Observabilidade: `gravador.log` na raiz do projeto

---

## Regras de negócio principais

- Arquivo salvo em `~/Music/gravador_audio/gravacao-YYYYMMDD-HHMMSS.mp3` por padrão
- Timestamp no nome evita colisão entre gravações
- Três modos de captura: microfone + sistema, somente microfone, somente sistema
- Áudio mixado por média entre fontes, limitado a `[-1.0, 1.0]` antes de encodar
- Pasta de saída criada automaticamente se não existir
- Pipeline pós-gravação gera `transcricao.md` (com timestamps) e `resumo.md`
- Pasta da gravação nomeada automaticamente com base no conteúdo via Claude

---

## Decisões já tomadas

- `pyaudiowpatch` para captura WASAPI com suporte a loopback (substituiu `soundcard` e `sounddevice`)
- `lameenc` para encoder MP3 sem dependências binárias externas
- Backend abstrato (`AudioBackend`) para permitir troca de implementação sem mudar a GUI/CLI
- `RecordingService` orquestra estado; `WindowsAudioBackend` faz a captura em thread separada
- Callbacks para microfone + thread blocking para loopback (contorna comportamento de drivers wireless)
- Acumuladores independentes por fonte com chunk de saída fixo (100 ms) para suportar qualquer buffer nativo
- `faster-whisper` local para transcrição (sem envio de áudio a serviços externos)
- `tkinter` para GUI (sem dependências pesadas de UI)
- Log persistente em `gravador.log` na raiz para diagnóstico de problemas de hardware

---

## Fora de escopo

- Suporte a macOS ou Linux
- Gravação em formatos além de MP3
- Upload ou compartilhamento de gravações
- Edição de áudio
- Agendamento de gravações
- Interface web ou servidor

---

## Riscos conhecidos

- Drivers WASAPI de headsets wireless e monitores HDMI não entregam silence frames em
  modo callback — callbacks só disparam quando há áudio tocando
- Dispositivos diferentes têm períodos nativos de buffer muito variáveis (480 a 242400 frames)
- A síntese via Claude API requer `ANTHROPIC_API_KEY` válida e conexão com internet
- Gravações longas podem ocupar disco — alerta em < 100 MB implementado

---

## Observações para agentes

- A única plataforma suportada é Windows. Não propor soluções que dependam de APIs de outros SOs.
- Não alterar arquitetura sem revisar `docs/STRUCTURE.md`.
- Não implementar solução fora do escopo da spec ativa.
- `PYTHONPATH=src` é obrigatório para rodar sem instalar o pacote.
- Não presumir contexto ausente; em caso de dúvida, parar e pedir confirmação.
