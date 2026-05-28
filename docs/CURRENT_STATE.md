# CURRENT_STATE.md

## Objetivo

Este arquivo registra o estado atual do projeto em alto nível.

Use para retomada de contexto entre sessões, agentes e conversas.

---

## Status geral

Em desenvolvimento ativo — captura de áudio validada; bug no pipeline pós-gravação via GUI

---

## Última atualização

2026-05-28

---

## Resumo atual

A captura de áudio foi validada: gravação de 20s com G435 Wireless produziu chunks=202 e MP3 de duração completa (CT-01 ✅). O pipeline de transcrição e síntese está implementado. Novo problema ativo: ao clicar em "Parar gravação" na GUI, a aplicação fecha em vez de disparar automaticamente o pipeline (transcrição → síntese → pasta nomeada). O fluxo de "Processar MP3 existente" não foi afetado.

---

## Funcionalidades já implementadas

- [x] Gravação em MP3 via microfone (WASAPI)
- [x] Gravação em MP3 via áudio do sistema (loopback WASAPI)
- [x] Gravação simultânea microfone + sistema (mixagem por média)
- [x] Interface gráfica (tkinter) com iniciar/parar, EQ visualizer, feedback de dispositivos
- [x] Exibição do nome dos dispositivos ativos na GUI
- [x] Surfacing de erros do backend em tempo real na GUI
- [x] Interface CLI com subcomandos `gravar` e `processar`
- [x] Script de instalação Windows (`Instalar.bat` + `install_windows.ps1`)
- [x] Máquina de estados (`IDLE → RECORDING → FINALIZING → COMPLETED → ERROR`)
- [x] Backend abstrato (`AudioBackend`) com implementação real (`WindowsAudioBackend`)
- [x] Alerta de espaço em disco insuficiente (< 100 MB) durante gravação
- [x] Log persistente em `gravador.log` na raiz para diagnóstico
- [x] Pipeline pós-gravação: transcrição (faster-whisper small) + síntese (Claude API)
- [x] Pasta nomeada automaticamente com base no conteúdo via Claude
- [x] `transcricao.md` com timestamps `[HH:MM:SS]`
- [x] `resumo.md` com síntese estruturada (Contexto, Decisões, Plano de ação)
- [x] Botão "Processar MP3 existente" na GUI com seletor de idioma
- [x] Seleção de modelo Whisper na GUI (detecta modelos já baixados, default `small`)
- [x] 35 testes unitários passando

---

## Funcionalidades em andamento

Nenhuma no momento.

---

## Funcionalidades planejadas

- [ ] Teste end-to-end do pipeline com MP3 real de chamada
- [ ] Validar EQ visualizer com a nova arquitetura de captura

---

## Decisões recentes

| Data | Decisão | Motivo |
|---|---|---|
| 2026-05-28 | `soundcard` → `pyaudiowpatch` | soundcard incompatível com G435 (assert falha em WAVE_FORMAT_EXTENSIBLE) |
| 2026-05-28 | Loopback: callback → blocking thread dedicada | Callback do G435/LG ULTRAGEAR não dispara quando áudio do sistema é silencioso |
| 2026-05-28 | Acumuladores numpy independentes por fonte + chunk fixo 100 ms | Dispositivos têm períodos nativos incompatíveis (480 a 242400 frames) |
| 2026-05-28 | `encoder.flush()` guardado por `chunk_count > 0` | lameenc levanta RuntimeError se flush chamado sem encode anterior |
| 2026-05-21 | Estrutura documental inicializada | Repositório preparado para Spec-Driven Development |
| 2026-05-21 | Alerta de espaço em disco implementado (spec 0001) | Risco de gravação truncada sem aviso |
| 2026-05-21 | Pipeline pós-gravação implementado (spec 0002) | Automatizar transcrição + síntese que era feita manualmente |

---

## Riscos atuais
- Loopback blocking pode bloquear indefinidamente se driver não entregar frames — `stop()` fecha o stream para desbloquear
- CT-02 (mic + sistema) ainda não executado; comportamento com áudio do sistema tocando não validado
- `ANTHROPIC_API_KEY` ausente ou inválida interrompe o pipeline (síntese falha, transcrição fica salva)
- GUI e CLI não têm testes automatizados

---

## Pendências

- Investigar e corrigir: GUI fecha após stop em vez de iniciar o pipeline
- Executar CT-02 com mic + áudio do sistema simultâneos
- Confirmar que EQ visualizer anima corretamente com a nova arquitetura
- Atualizar testes unitários de `WindowsAudioBackend` para refletir a nova implementação

---

## Próximo passo recomendado

Investigar o fluxo `_stop_recording_worker → _show_completed → _start_pipeline` na GUI para entender por que a aplicação fecha em vez de executar o pipeline após parar a gravação.

---

## Observações para o próximo agente

- Leia `AI_AGENT_RULES.md` antes de qualquer ação.
- O `gravador.log` na raiz é o principal instrumento de diagnóstico — sempre leia antes de propor correção.
- A implementação está em transição — não presuma que o código está estável; verifique o log.
- `PYTHONPATH=src` é obrigatório para rodar sem instalar o pacote.
- Não presuma que este arquivo substitui o PRD ou o PLAN.
