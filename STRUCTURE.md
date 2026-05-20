# STRUCTURE.md

## Objetivo

Este documento descreve a estrutura do repositório e onde cada responsabilidade deve viver.

Atualize este arquivo apenas quando houver mudança relevante na arquitetura, pastas, módulos, responsabilidades ou fluxo técnico.

---

## Estrutura geral

```text
/
├── app/
│   ├── api/
│   ├── core/
│   ├── db/
│   ├── models/
│   ├── schemas/
│   ├── services/
│   └── main.py
├── alembic/
├── tests/
├── docs/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## Responsabilidades por pasta

| Caminho | Responsabilidade |
|---|---|
| `app/` | Código principal da aplicação |
| `app/main.py` | Ponto de entrada da aplicação |
| `app/api/` | Rotas/endpoints da API |
| `app/core/` | Configurações centrais, settings e utilitários base |
| `app/db/` | Conexão com banco, sessão e base ORM |
| `app/models/` | Models SQLAlchemy |
| `app/schemas/` | Schemas Pydantic |
| `app/services/` | Regras de negócio |
| `app/repositories/` | Acesso a dados, se existir |
| `app/adapters/` | Integrações externas, se existir |
| `app/strategies/` | Estratégias específicas por fonte/site, se existir |
| `alembic/` | Migrations do banco |
| `tests/` | Testes automatizados |
| `docs/` | Documentação técnica e specs |
| `docs/specs/` | Especificações por feature/tarefa |

---

## Padrão de camadas

Fluxo preferencial:

```text
route -> schema -> service -> repository/db -> model
```

Para coleta/validação externa:

```text
search/fetch adapter -> parser -> validator -> service -> persistence
```

---

## Regras arquiteturais

- Rotas não devem concentrar regra de negócio complexa.
- Services devem conter regras de negócio.
- Models representam persistência.
- Schemas representam entrada/saída da API.
- Adapters lidam com integrações externas.
- Strategies isolam comportamento específico por site/fonte.
- Validações críticas devem ser explícitas.
- Persistência deve acontecer apenas depois da validação.
- Não criar hardcode de produto/site no service principal.
- Não alterar arquitetura sem plano.
- Não criar nova camada sem justificativa.

---

## Banco de dados

- Models ficam em `app/models/`.
- Migrations ficam em `alembic/versions/`.
- Não editar migrations antigas sem aprovação.
- Não rodar migrations sem revisar impacto.
- Não alterar schema fora do fluxo de migration.

---

## Testes

Testes devem ficar em `tests/`.

Padrões esperados:

```text
tests/
├── unit/
├── integration/
└── e2e/
```

Quando a estrutura real for diferente, documentar aqui.

---

## Documentação de specs

Cada feature relevante deve ter sua própria pasta:

```text
docs/specs/0001-nome-da-feature/
├── PRD.md
├── PROPOSAL.md
├── PLAN.md
├── PROGRESS.md
└── TEST.md
```

---

## Comandos comuns

### Rodar aplicação

```bash
<preencher comando>
```

### Rodar testes

```bash
<preencher comando>
```

### Rodar migrations

```bash
<preencher comando>
```

### Rodar lint/format

```bash
<preencher comando>
```

---

## Pontos de atenção

- Não alterar `.env`.
- Não expor segredos.
- Não commitar arquivos sensíveis.
- Não rodar comando destrutivo.
- Não modificar banco sem aprovação.
- Não quebrar funcionalidade existente.