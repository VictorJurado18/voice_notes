# Objetivos do projeto — gravador_audio

## Propósito

Aplicação desktop Windows para gravar chamadas e reuniões em MP3, capturando microfone e áudio do sistema simultaneamente, com transcrição e síntese automática após a gravação.

---

## Objetivos funcionais

| # | Objetivo | Status |
|---|----------|--------|
| 1 | Gravar microfone em MP3 | Implementado |
| 2 | Gravar áudio do sistema (loopback WASAPI) em MP3 | Em correção |
| 3 | Mixar microfone + sistema em uma única gravação | Em correção |
| 4 | Interface gráfica simples (iniciar / parar / feedback visual) | Implementado |
| 5 | Interface CLI para automação | Implementado |
| 6 | Transcrição automática do MP3 com `faster-whisper` | Implementado |
| 7 | Síntese da transcrição (contexto, decisões, ações) via Claude | Implementado |
| 8 | Pasta de saída nomeada automaticamente com base no conteúdo | Implementado |
| 9 | Alerta quando espaço em disco estiver abaixo de 100 MB | Implementado |

---

## Objetivos de qualidade

- **Confiabilidade**: a gravação não pode perder áudio silenciosamente — o usuário precisa saber se algo falhou
- **Feedback em tempo real**: visualizador de nível de áudio (EQ) e nome dos dispositivos ativos na tela
- **Diagnóstico**: log de execução persistente em `gravador.log` na raiz do projeto
- **Segurança de dados**: nenhum áudio é enviado a serviços externos (transcrição é local, síntese usa Claude via API do usuário)

---

## Fora de escopo

- Suporte a macOS ou Linux
- Gravação em formatos além de MP3
- Edição de áudio
- Agendamento de gravações
- Upload ou compartilhamento automático

---

## Situação atual (2026-05-28)

O gravador e o pipeline de transcrição/síntese estão implementados. A gravação de áudio está passando por correções para garantir captura confiável com o headset G435 Wireless e o monitor LG ULTRAGEAR — ambos com drivers WASAPI de comportamento não-padrão para loopback.

O problema ativo: o loopback WASAPI desses dispositivos só dispara callbacks quando há áudio do sistema tocando, não entregando silêncio. A correção em andamento usa modo blocking em thread separada + acumuladores independentes por fonte.
