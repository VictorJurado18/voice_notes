# PROMPT.md

## Objetivo

Este arquivo funciona como orquestrador do fluxo de desenvolvimento orientado por especificação.

O agente deve usar este documento para saber quais arquivos ler, em qual ordem agir e como conduzir uma tarefa do início ao fim.

---

## Ordem obrigatória de leitura

Antes de executar qualquer ação, leia:

1. `AI_AGENT_RULES.md`
2. `AGENTS.md`
3. `OBJECTIVES.md`
4. `docs/PROJECT_CONTEXT.md`
5. `docs/STRUCTURE.md`
6. `docs/CURRENT_STATE.md`
7. A spec ativa em `docs/specs/<nome-da-feature>/`

Dentro da spec ativa, leia:

1. `PRD.md`
2. `PROPOSAL.md`
3. `PLAN.md`
4. `PROGRESS.md`
5. `TEST.md`

Se algum documento não existir, registre a ausência.

---

## Fluxo obrigatório para nova tarefa

Para uma nova tarefa:

1. Entender a solicitação do usuário.
2. Localizar ou criar a pasta da spec.
3. Ler `PRD.md`.
4. Analisar arquitetura com apoio de `STRUCTURE.md`.
5. Atualizar `PROPOSAL.md`, se necessário.
6. Gerar ou atualizar `PLAN.md`.
7. Gerar ou atualizar `TEST.md`.
8. Apresentar o plano ao usuário.
9. Aguardar aprovação explícita.
10. Executar somente o plano aprovado.
11. Atualizar `PROGRESS.md`.
12. Executar validações.
13. Atualizar `TEST.md`.
14. Resumir resultado final.

---

## Fluxo obrigatório para continuação de tarefa

Quando continuar uma tarefa já iniciada:

1. Ler `PROGRESS.md`.
2. Identificar último estado registrado.
3. Verificar pendências.
4. Comparar com `PLAN.md`.
5. Continuar somente a partir do próximo passo seguro.
6. Atualizar `PROGRESS.md` após cada etapa relevante.

---

## Regras de parada

Pare imediatamente se:

- houver risco de apagar dados;
- houver risco de expor segredo;
- houver divergência entre documentos;
- o ambiente de banco não estiver claro;
- a tarefa exigir mudança fora do escopo;
- for necessário commit ou push;
- for necessário executar comando destrutivo;
- a spec estiver incompleta para uma decisão segura;
- houver dependência nova sem justificativa;
- houver alteração estrutural sem aprovação.

---

## Resposta inicial esperada do agente

Ao receber uma tarefa, responda com:

```text
Entendimento:
- ...

Arquivos que vou analisar:
- ...

Riscos iniciais:
- ...

Próximo passo:
- criar/atualizar PLAN.md e aguardar aprovação antes de implementar.
```

---

## Execução

Após aprovação explícita, executar em etapas pequenas.

Depois de cada etapa relevante, atualizar `PROGRESS.md`.

Não executar fora do plano aprovado.

Se o plano se mostrar incorreto durante a execução, parar, explicar a divergência e solicitar aprovação para ajuste.

---

## Finalização

Ao finalizar, informar:

- o que foi alterado;
- arquivos modificados;
- testes executados;
- resultado dos testes;
- pendências;
- riscos restantes;
- próximos passos sugeridos.

Não fazer commit.
Não fazer push.