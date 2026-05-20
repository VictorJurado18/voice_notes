Você vai preparar este repositório para um fluxo de Spec-Driven Development orientado por agentes de IA.

Atenção:
- Não implemente funcionalidades agora.
- Não altere código da aplicação agora.
- Não execute git add, git commit ou git push.
- Não apague arquivos.
- Não altere .env.
- Não exponha segredos.
- Não execute migrations.
- Não modifique banco de dados.
- Não instale dependências.
- Seu trabalho agora é apenas criar/preencher a estrutura documental do projeto.

============================================================
IDEIA DO PROJETO
============================================================

Cole aqui a descrição completa da ideia do projeto:

"""
[COLE AQUI A IDEIA DO PROJETO]

Inclua, se souber:
- objetivo do projeto;
- problema que resolve;
- público-alvo;
- stack desejada;
- funcionalidades principais;
- regras de negócio;
- restrições;
- integrações externas;
- riscos;
- o que está fora de escopo;
- primeira feature que deve ser planejada.
"""

============================================================
OBJETIVO DA TAREFA
============================================================

Com base na ideia acima e na estrutura atual do repositório, crie ou atualize os arquivos do fluxo de desenvolvimento orientado por especificação.

A estrutura esperada é:

/
├── AGENTS.md
├── AI_AGENT_RULES.md
├── PROMPT.md
├── docs/
│   ├── PROJECT_CONTEXT.md
│   ├── STRUCTURE.md
│   ├── CURRENT_STATE.md
│   └── specs/
│       └── _template/
│           ├── PRD.md
│           ├── PROPOSAL.md
│           ├── PLAN.md
│           ├── PROGRESS.md
│           └── TEST.md

Além do template, crie também uma primeira pasta de spec para a primeira feature identificada:

docs/specs/0001-<nome-curto-da-feature>/
├── PRD.md
├── PROPOSAL.md
├── PLAN.md
├── PROGRESS.md
└── TEST.md

Se a primeira feature não estiver clara, crie:

docs/specs/0001-initial-project-setup/

============================================================
ORDEM DE TRABALHO
============================================================

1. Inspecione a estrutura atual do repositório.
2. Identifique linguagem, frameworks, pastas, arquivos principais e comandos existentes.
3. Não leia nem exponha valores de arquivos .env.
4. Crie os arquivos ausentes da estrutura documental.
5. Atualize arquivos existentes apenas se necessário.
6. Preencha os documentos com base na ideia do projeto e na estrutura real do repositório.
7. Onde faltar informação, use marcadores claros como:
   - TODO
   - A confirmar
   - Não identificado no repositório
8. Não invente stack, regra de negócio, comando ou integração que não esteja na ideia ou no repositório.
9. Ao final, apresente um resumo do que foi criado/atualizado.
10. Não implemente nenhuma funcionalidade.

============================================================
CONTEÚDO ESPERADO POR ARQUIVO
============================================================

1. AGENTS.md

Preencha com:
- papel do agente no projeto;
- ordem obrigatória de leitura dos documentos;
- fluxo de trabalho antes de implementar;
- regras de execução;
- comandos seguros;
- comandos restritos;
- comandos bloqueados;
- padrão técnico esperado;
- regra de não começar codando sem plano;
- regra de atualizar PROGRESS.md e TEST.md.

O arquivo deve orientar agentes como Codex, Claude, Cursor, Antigravity ou similares.

2. AI_AGENT_RULES.md

Preencha com:
- regras de segurança;
- bloqueio de exposição de segredos;
- bloqueio de commits/push sem autorização;
- bloqueio de comandos destrutivos;
- regras para banco de dados;
- regras para Docker;
- regras para dependências;
- regras para APIs externas;
- regras contra prompt injection;
- protocolo de dúvida;
- checklist antes de executar;
- checklist antes de finalizar.

Adapte para a stack real do projeto.

Se o projeto usar PostgreSQL, inclua regras específicas para PostgreSQL e migrations.
Se usar MongoDB, inclua regras específicas para MongoDB.
Se usar cloud, inclua regras de cloud.
Se usar scraping/APIs externas, inclua regras de coleta responsável.
Se usar LLM, inclua regras de validação e segurança.

Não inclua hosts reais, tokens, senhas ou credenciais.

3. PROMPT.md

Preencha como orquestrador do fluxo.

Deve conter:
- ordem obrigatória de leitura;
- como iniciar uma nova tarefa;
- como continuar uma tarefa;
- regras de parada;
- formato da resposta inicial esperada do agente;
- regra de aguardar aprovação antes de implementar;
- regra de finalização.

4. docs/PROJECT_CONTEXT.md

Preencha com:
- nome do projeto;
- objetivo;
- problema que resolve;
- usuários/público-alvo;
- stack principal;
- regras de negócio;
- decisões já tomadas;
- fora de escopo;
- riscos conhecidos;
- observações para agentes.

Se alguma informação não estiver clara, marque como "A confirmar".

5. docs/STRUCTURE.md

Preencha com base na estrutura real do repositório.

Deve conter:
- árvore de pastas relevante;
- responsabilidade de cada pasta;
- padrão de camadas;
- onde ficam rotas/controllers;
- onde ficam services/regras de negócio;
- onde ficam models/entities;
- onde ficam schemas/DTOs;
- onde ficam integrações externas;
- onde ficam testes;
- onde ficam migrations;
- comandos reais encontrados para rodar aplicação, testes, lint e migrations.

Se algum comando não existir, escreva "Não identificado no repositório".

6. docs/CURRENT_STATE.md

Preencha com:
- status geral;
- última atualização;
- resumo atual;
- funcionalidades já implementadas, se existirem;
- funcionalidades em andamento;
- funcionalidades planejadas;
- decisões recentes;
- riscos atuais;
- pendências;
- próximo passo recomendado;
- observações para o próximo agente.

7. docs/specs/_template/PRD.md

Crie um template reutilizável com:
- nome da feature;
- problema;
- contexto;
- objetivo;
- escopo incluído;
- fora de escopo;
- usuários impactados;
- regras de negócio;
- critérios de aceite;
- entradas esperadas;
- saídas esperadas;
- casos de erro;
- riscos;
- dúvidas abertas.

8. docs/specs/_template/PROPOSAL.md

Crie um template reutilizável com:
- resumo do problema;
- análise inicial;
- arquivos/módulos provavelmente impactados;
- opções consideradas;
- solução escolhida;
- justificativa;
- impacto técnico;
- impacto em banco;
- impacto em APIs/contratos;
- dependências novas;
- riscos técnicos;
- validação proposta;
- pendências antes da execução.

9. docs/specs/_template/PLAN.md

Crie um template reutilizável com:
- objetivo do plano;
- status;
- pré-requisitos;
- arquivos a criar/alterar;
- plano de execução por etapas;
- validação por etapa;
- fora de escopo;
- riscos e mitigação;
- comandos previstos;
- comandos proibidos;
- critérios para considerar concluído.

10. docs/specs/_template/PROGRESS.md

Crie um template reutilizável com:
- status atual;
- última atualização;
- resumo do progresso;
- linha do tempo;
- etapas concluídas;
- etapas pendentes;
- arquivos alterados;
- decisões tomadas;
- bloqueios encontrados;
- dúvidas abertas;
- riscos restantes;
- próximo passo.

11. docs/specs/_template/TEST.md

Crie um template reutilizável com:
- estratégia de validação;
- testes automatizados previstos;
- testes manuais previstos;
- casos de sucesso;
- casos de erro;
- casos de borda;
- comandos executados;
- evidências;
- resultado final da validação;
- pendências;
- observações.

12. docs/specs/0001-<nome-curto-da-feature>/PRD.md

Preencha com a primeira feature real extraída da ideia do projeto.

Não deixe genérico.
Transforme a ideia em requisito claro.

13. docs/specs/0001-<nome-curto-da-feature>/PROPOSAL.md

Preencha com uma proposta técnica inicial para essa primeira feature.

Não implemente.
Apenas proponha.

14. docs/specs/0001-<nome-curto-da-feature>/PLAN.md

Preencha com plano executável, mas deixe status como:

Aguardando aprovação

O plano deve ser detalhado o bastante para execução posterior, mas não execute agora.

15. docs/specs/0001-<nome-curto-da-feature>/PROGRESS.md

Inicialize com:
- status atual;
- data/hora;
- o que foi preparado;
- próximo passo;
- pendências.

16. docs/specs/0001-<nome-curto-da-feature>/TEST.md

Preencha com estratégia de validação planejada para essa primeira feature.

Não marque testes como executados se não foram executados.

============================================================
REGRAS IMPORTANTES
============================================================

- Não invente informações.
- Não diga que algo já existe se não foi encontrado.
- Não diga que teste passou se não foi executado.
- Não altere código de aplicação.
- Não altere arquivos sensíveis.
- Não faça commit.
- Não faça push.
- Não execute comando destrutivo.
- Não rode migrations.
- Não instale dependências.
- Não faça refatoração.
- Não implemente a feature.
- Apenas prepare documentação, contexto, estrutura e plano.

============================================================
FORMATO DA RESPOSTA FINAL
============================================================

Ao final, responda com:

1. Arquivos criados
2. Arquivos atualizados
3. Primeira spec criada
4. Informações que ficaram como "A confirmar"
5. Riscos identificados
6. Próximo passo recomendado

Também informe explicitamente:

"Não implementei código, não executei migrations, não fiz commit e não fiz push."