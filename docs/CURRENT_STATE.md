# CURRENT_STATE.md

## Objetivo

Este arquivo registra o estado atual do projeto em alto nível.

Use para retomada de contexto entre sessões, agentes e conversas.

---

## Status geral

Estável

---

## Última atualização

2026-05-21

---

## Resumo atual

O projeto tem implementação completa e funcional. CLI e interface gráfica estão prontos. Testes unitários cobrem `RecordingService` e `WindowsAudioBackend`. A estrutura documental foi inicializada nesta sessão. Nenhuma feature nova está em desenvolvimento.

---

## Funcionalidades já implementadas

- [x] Gravação em MP3 via microfone
- [x] Gravação em MP3 via áudio do sistema (loopback)
- [x] Gravação simultânea microfone + sistema (mixagem por média)
- [x] Interface gráfica (tkinter) com controles iniciar/parar, escolha de modo e pasta
- [x] Interface CLI com subcomandos `gravar` e `processar`
- [x] Script de instalação Windows (`Instalar.bat` + `install_windows.ps1`)
- [x] Máquina de estados de gravação (`IDLE → RECORDING → FINALIZING → COMPLETED → ERROR`)
- [x] Backend abstrato (`AudioBackend`) com implementação real (`WindowsAudioBackend`)
- [x] Alerta de espaço em disco insuficiente (< 100 MB) durante gravação
- [x] Pipeline pós-gravação automático: transcrição (faster-whisper small) + síntese (claude -p)
- [x] Pasta nomeada automaticamente com base no conteúdo da conversa
- [x] `transcricao.md` com timestamps `[HH:MM:SS]`
- [x] `resumo.md` com síntese estruturada (Contexto, Decisões, Plano de ação, etc.)
- [x] Botão "Processar MP3 existente" na GUI com seletor de idioma
- [x] 25 testes unitários passando

---

## Funcionalidades em andamento

Nenhuma.

---

## Funcionalidades planejadas

- [ ] Teste manual end-to-end do pipeline com MP3 real

---

## Decisões recentes

| Data | Decisão | Motivo |
|---|---|---|
| 2026-05-21 | Estrutura documental inicializada | Repositório clonado e docs preenchidos com base no código existente |
| 2026-05-21 | Alerta de espaço em disco implementado (spec 0001) | Risco de gravação truncada sem aviso |
| 2026-05-21 | Pipeline pós-gravação implementado (spec 0002) | Automatizar transcrição + síntese que era feita manualmente |

---

## Riscos atuais

- `soundcard` pode não funcionar em hardware com drivers sem suporte a WASAPI loopback
- Sem alertas de espaço em disco — gravações longas podem falhar silenciosamente ao esgotar disco
- `gui.py` e `cli.py` não têm testes automatizados

---

## Pendências

- Preencher primeira spec em `docs/specs/0001-*/` com uma feature real a desenvolver (aguarda decisão do responsável)
- Validar se testes passam no ambiente local após instalação

---

## Próximo passo recomendado

Definir qual feature evoluir primeiro e criar spec completa em `docs/specs/0001-<nome>/`. Candidatas: alerta de disco, testes de integração ou suporte a formato WAV.

---

## Observações para o próximo agente

- Leia `AI_AGENT_RULES.md` antes de qualquer ação.
- Leia `AGENTS.md` e `PROMPT.md` em seguida.
- A implementação está completa — não altere código sem spec e aprovação.
- Não presuma que este arquivo substitui o PRD ou o PLAN.
- Os testes existentes usam `unittest` e rodam com `PYTHONPATH=src`.
