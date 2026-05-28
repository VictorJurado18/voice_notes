# CURRENT_STATE.md

## Objetivo

Este arquivo registra o estado atual do projeto em alto nível.

Use para retomada de contexto entre sessões, agentes e conversas.

---

## Status geral

Em desenvolvimento ativo — confiabilidade do gravador de áudio em correção

---

## Última atualização

2026-05-28

---

## Resumo atual

O pipeline de transcrição e síntese está implementado e funcional. A interface gráfica e a CLI estão prontas. O problema ativo é a confiabilidade da gravação de áudio: drivers WASAPI de headsets wireless (G435) e monitores HDMI têm comportamento não-padrão — callbacks de loopback só disparam quando há áudio do sistema tocando, não entregam silence frames. A correção atual usa modo blocking em thread separada para loopback + acumuladores independentes por fonte com chunk de saída fixo (100 ms).

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
- [x] 25 testes unitários passando

---

## Funcionalidades em andamento

- [ ] **Confiabilidade do gravador de áudio** — captura correta com quaisquer dispositivos WASAPI
  - Problema: loopback de G435 wireless e LG ULTRAGEAR HDMI só dispara callback quando há áudio tocando
  - Correção em teste: loopback em thread blocking + acumuladores independentes por fonte

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

- Loopback blocking pode bloquear indefinidamente se driver não entregar frames mesmo sem áudio — thread fica presa em `read()`; `stop()` fecha o stream para desbloquear
- G435 e LG ULTRAGEAR têm comportamentos distintos; outros dispositivos podem apresentar variações não testadas
- `ANTHROPIC_API_KEY` ausente ou inválida interrompe o pipeline (síntese falha, transcrição fica salva)
- GUI e CLI não têm testes automatizados

---

## Pendências

- Confirmar que gravação funciona com audio do sistema tocando (cenário real de chamada)
- Confirmar que EQ visualizer anima corretamente com a nova arquitetura
- Atualizar testes unitários de `WindowsAudioBackend` para refletir a nova implementação

---

## Próximo passo recomendado

Gravar um teste de 20 segundos com áudio do sistema tocando (simular chamada) e verificar no log se `chunk_count` é ~200 e o MP3 tem duração completa.

---

## Observações para o próximo agente

- Leia `AI_AGENT_RULES.md` antes de qualquer ação.
- O `gravador.log` na raiz é o principal instrumento de diagnóstico — sempre leia antes de propor correção.
- A implementação está em transição — não presuma que o código está estável; verifique o log.
- `PYTHONPATH=src` é obrigatório para rodar sem instalar o pacote.
- Não presuma que este arquivo substitui o PRD ou o PLAN.
