# PROJECT_CONTEXT.md

## Nome do projeto

gravador_audio

---

## Objetivo

Aplicação desktop para Windows que grava áudio local em formato MP3, capturando microfone e/ou áudio do sistema (loopback do speaker) de forma simultânea ou separada.

---

## Problema que o projeto resolve

Usuários no Windows precisam gravar chamadas, reuniões, podcasts ou qualquer combinação de microfone e áudio do sistema sem depender de ferramentas pagas ou complexas. O projeto oferece uma solução simples, leve e sem dependências externas pesadas.

---

## Usuários ou público-alvo

- Usuários Windows que querem gravar reuniões ou chamadas
- Criadores de conteúdo que precisam capturar áudio do sistema e microfone juntos
- Usuários técnicos que preferem interface de linha de comando

---

## Stack principal

- Linguagem: Python 3.12+
- Captura de áudio: `pyaudiowpatch` (WASAPI loopback para Windows)
- Encoder MP3: `lameenc` (puro Python, sem binário externo)
- Mixagem e resampling: `numpy`
- Transcrição: `faster-whisper` (local, modelo small)
- Síntese: Claude API (`anthropic` SDK, claude-sonnet)
- Interface gráfica: `tkinter` (incluso no Python padrão)
- Interface CLI: `argparse`
- Containerização: Não utilizada
- IA/LLM: Claude API (apenas para síntese do resumo pós-gravação)
- APIs externas: Anthropic Claude API
- Cloud: Nenhuma (transcrição é local)
- Observabilidade: `gravador.log` na raiz do projeto

---

## Regras de negócio principais

- Gravação salva em `C:\Users\<usuario>\Music\gravador_audio\gravacao-YYYYMMDD-HHMMSS.mp3` por padrão
- Nome do arquivo inclui timestamp para evitar colisão
- Três modos de captura: microfone + sistema, somente microfone, somente sistema
- Áudio de múltiplas fontes é misturado por média e limitado a [-1.0, 1.0] antes de encodar
- Arquivo não é sobrescrito se já existir com o mesmo nome
- A pasta de saída é criada automaticamente se não existir

---

## Decisões já tomadas

- `pyaudiowpatch` para WASAPI com suporte a loopback (substituiu `soundcard` e `sounddevice`)
- `lameenc` para evitar dependência de binários externos (ex: ffmpeg)
- Arquitetura com backend abstrato (`AudioBackend`) para permitir troca futura de implementação
- `RecordingService` orquestra estado; `WindowsAudioBackend` faz a captura em thread separada
- Microfone via callback; loopback via thread blocking dedicada (contorna drivers wireless que não entregam silence em callback)
- Acumuladores numpy independentes por fonte com chunk de saída fixo de 100 ms
- `faster-whisper` local para transcrição (nenhum áudio enviado externamente)
- Claude API para síntese do resumo estruturado pós-gravação
- `tkinter` para GUI (sem dependências pesadas de UI)
- Log persistente em `gravador.log` para diagnóstico de problemas de hardware
- Projeto empacotado com `pyproject.toml` e instalado em `.venv` local

---

## Fora de escopo

- Suporte a macOS ou Linux
- Gravação em outros formatos além de MP3
- Upload ou compartilhamento de gravações
- Edição de áudio
- Agendamento de gravações
- Interface web ou servidor

---

## Riscos conhecidos

- Drivers WASAPI de headsets wireless (G435) e monitores HDMI não entregam silence frames em modo callback — callbacks só disparam quando há áudio tocando
- Diferentes dispositivos têm períodos nativos de buffer muito variáveis (480 a 242400 frames), exigindo acumuladores independentes
- Loopback blocking pode bloquear indefinidamente se o driver não entregar frames mesmo sem áudio tocando
- A síntese via Claude API requer `ANTHROPIC_API_KEY` válida e conexão com internet
- Gravações longas podem ocupar disco — alerta em < 100 MB implementado

---

## Observações para agentes

- Não presumir contexto ausente.
- A única plataforma suportada é Windows. Não propor soluções que dependam de APIs de outros sistemas.
- Não alterar arquitetura sem revisar `docs/STRUCTURE.md`.
- Não implementar solução fora do escopo da spec ativa.
- Em caso de dúvida, parar e pedir confirmação.
