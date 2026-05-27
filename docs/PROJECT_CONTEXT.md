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
- Backend de áudio: `soundcard` (captura microfone e loopback do speaker)
- Encoder MP3: `lameenc` (encoder puro Python, sem binário externo)
- Processamento de áudio: `numpy`
- Interface gráfica: `tkinter` (incluso no Python padrão)
- Interface CLI: `argparse`
- Containerização: Não utilizada
- IA/LLM: Não utilizada
- APIs externas: Nenhuma
- Cloud: Nenhuma
- Observabilidade: Nenhuma

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

- Uso de `soundcard` para acesso ao loopback do speaker no Windows (WASAPI)
- Uso de `lameenc` para evitar dependência de binários externos (ex: ffmpeg)
- Arquitetura com backend abstrato (`AudioBackend`) para permitir troca futura de implementação
- Separação de responsabilidades: `RecordingService` orquestra estado, `WindowsAudioBackend` faz a captura
- Interface gráfica com `tkinter` para não adicionar dependências pesadas de UI
- Projeto empacotado com `pyproject.toml` e instalado em `.venv` local

---

## Fora de escopo

- Suporte a macOS ou Linux
- Gravação em outros formatos além de MP3
- Upload ou compartilhamento de gravações
- Edição de áudio
- Transcrição automática
- Agendamento de gravações

---

## Riscos conhecidos

- `soundcard` pode não funcionar em todos os dispositivos de áudio Windows (depende de suporte WASAPI)
- O loopback do speaker exige que o dispositivo de saída padrão suporte captura — nem todo hardware/driver suporta
- Se microfone e loopback tiverem taxas de amostragem diferentes, a mixagem pode produzir artefatos
- Gravações longas podem ocupar espaço em disco silenciosamente (sem alerta de espaço)

---

## Observações para agentes

- Não presumir contexto ausente.
- A única plataforma suportada é Windows. Não propor soluções que dependam de APIs de outros sistemas.
- Não alterar arquitetura sem revisar `docs/STRUCTURE.md`.
- Não implementar solução fora do escopo da spec ativa.
- Em caso de dúvida, parar e pedir confirmação.
