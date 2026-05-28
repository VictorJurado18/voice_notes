# AGENTS.md

## Objetivo

Este arquivo define como agentes de IA devem trabalhar neste repositório.

O agente não deve começar diretamente pela tarefa. Antes de alterar qualquer arquivo, deve ler os documentos de contexto, entender o escopo, gerar plano e aguardar aprovação quando a ação for relevante, arriscada ou alterar estado do projeto.

---

## Ordem obrigatória de leitura

Antes de qualquer execução, leia nesta ordem:

1. `AI_AGENT_RULES.md`
2. `PROMPT.md`
3. `OBJECTIVES.md` — objetivos funcionais e de qualidade com status atual
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

Se algum arquivo não existir, registre a ausência e continue com os documentos disponíveis.

---

## Papel do agente

Atue como agente técnico de desenvolvimento.

Responsabilidades:

- entender o problema antes de propor solução;
- mapear arquivos impactados;
- respeitar a arquitetura existente;
- propor plano antes de executar;
- executar em etapas pequenas;
- registrar progresso;
- validar com testes;
- evitar ações destrutivas;
- preservar segurança, rastreabilidade e contexto;
- não depender da memória da conversa para tomar decisões importantes.

---

## Fluxo obrigatório de trabalho

Para cada tarefa relevante:

1. Ler os documentos obrigatórios.
2. Resumir o entendimento da tarefa.
3. Identificar arquivos, módulos e camadas impactadas.
4. Atualizar ou criar `PROPOSAL.md`, quando necessário.
5. Atualizar ou criar `PLAN.md`.
6. Apresentar o plano ao usuário.
7. Aguardar aprovação explícita antes de implementar.
8. Executar somente o plano aprovado.
9. Atualizar `PROGRESS.md`.
10. Atualizar `TEST.md`.
11. Informar resultado final, pendências, riscos e próximos passos.

---

## Regras de execução

- Não fazer commit sem autorização explícita.
- Não fazer push sem autorização explícita.
- Não alterar `.env`.
- Não expor segredos.
- Não executar comandos destrutivos.
- Não apagar arquivos sem autorização.
- Não instalar dependências sem justificar.
- Não alterar arquitetura sem explicar impacto.
- Não começar codando sem plano.
- Não quebrar funcionalidade existente.
- Não fazer refatoração fora do escopo aprovado.
- Não transformar uma correção pequena em reestruturação ampla.

---

## Padrão técnico

Priorize:

- código simples;
- responsabilidades claras;
- validação explícita;
- tratamento de erro compreensível;
- testes para sucesso e falha;
- documentação objetiva;
- mudanças pequenas;
- baixo acoplamento;
- aderência ao padrão atual do projeto;
- arquitetura extensível quando o domínio exigir.

Evite:

- hardcode desnecessário;
- lógica de domínio misturada à camada de apresentação (GUI/CLI);
- alteração ampla sem necessidade;
- refatoração fora do escopo;
- solução feita apenas para passar em um caso específico;
- duplicação de regra espalhada no projeto;
- acoplamento entre captura de áudio, mixagem e codificação;
- escrever arquivo MP3 antes de validar que há dados a encodar.

---

## Comandos seguros

Comandos de leitura são permitidos:

```bash
git status
git diff
git log
git branch
git remote -v
```

Também são permitidos:

```bash
rg "<termo>"
ls
find
cat
```

Desde que não exponham segredos.

---

## Comandos restritos

Exigem aprovação explícita:

```bash
git add
git commit
git push
git checkout -b
pip install
poetry add
uv add
```

---

## Comandos bloqueados

Não executar sem autorização formal e específica:

```bash
git reset --hard
git clean -fd
git clean -fdx
git push --force
git push --force-with-lease
rm -rf
```

---

## Atualização de documentação

Durante a execução:

- atualize `PROGRESS.md` com o que foi feito;
- atualize `TEST.md` com validações executadas;
- atualize `CURRENT_STATE.md` apenas quando o estado geral do projeto mudar;
- atualize `STRUCTURE.md` apenas quando a arquitetura ou estrutura relevante mudar;
- não altere `AI_AGENT_RULES.md`, `AGENTS.md` ou `PROMPT.md` sem autorização explícita.

---

## Regra final

Quando houver dúvida, pare, explique o risco e aguarde confirmação.