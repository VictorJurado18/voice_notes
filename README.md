# gravador_audio

Aplicacao para Windows que grava audio local em `.mp3` (microfone e audio do sistema), transcreve automaticamente com Whisper e gera um resumo estruturado via Claude.

## O que faz

1. Grava microfone e/ou audio do sistema simultaneamente em MP3
2. Ao parar, transcreve o audio localmente com `faster-whisper`
3. Envia a transcricao para o Claude e gera `resumo.md` com contexto, decisoes e plano de acao
4. Cria uma pasta nomeada automaticamente com base no conteudo da reuniao

Cada gravacao resulta em:

```
Music\gravador_audio\<nome-da-reuniao>\
    gravacao-YYYYMMDD-HHMMSS.mp3
    transcricao.md
    resumo.md
```

---

## Requisitos

| Requisito | Versao minima | Observacao |
|---|---|---|
| Windows | 10 ou 11 | Unica plataforma suportada |
| Python | 3.12+ | Marque `Add python.exe to PATH` na instalacao |
| Claude Code CLI | qualquer | Necessario para gerar o resumo pos-gravacao |

### Instalar o Claude Code CLI

```powershell
npm install -g @anthropic-ai/claude-code
```

Depois autentique:

```powershell
claude
```

Siga o fluxo de login. O CLI precisa estar autenticado para que a sintese funcione. Se `claude` nao estiver no PATH, a transcricao e salva mas o resumo nao e gerado.

---

## Instalacao

1. Clone ou baixe este repositorio:

```powershell
git clone https://github.com/VictorJurado18/gavador_audio.git
cd gavador_audio
```

2. Clique duas vezes em:

```
Instalar.bat
```

Cria o ambiente local `.venv` e instala todas as dependencias de audio e transcricao.

> Na primeira gravacao o modelo Whisper e baixado automaticamente (modelo `small` ~244 MB, `medium` ~1.5 GB). Isso ocorre uma unica vez.

---

## Como usar

### Interface grafica

Clique duas vezes em:

```
Abrir Gravador.vbs
```

Abre a interface sem janela de terminal. Escolha o modo de captura, selecione o modelo Whisper e clique em `Iniciar gravacao`. Ao parar, o pipeline de transcricao e sintese inicia automaticamente.

Para abrir com janela de terminal (util para ver erros):

```
Abrir Gravador.bat
```

### Gravar pelo terminal (modo guiado)

```
Gravar.bat
```

Pergunta duracao e modo de captura. Executa o pipeline ao terminar.

---

## Uso tecnico

Abrir interface:

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.gui
```

Gravar 20 segundos (microfone + sistema):

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.cli gravar --duration 20
```

Gravar so microfone:

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.cli gravar --duration 20 --microphone-only
```

Gravar so audio do sistema:

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.cli gravar --duration 20 --system-only
```

Gravar sem executar o pipeline:

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.cli gravar --duration 20 --no-pipeline
```

Transcrever e sintetizar um MP3 existente:

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.cli processar caminho\para\gravacao.mp3 --idioma pt --modelo medium
```

Rodar testes:

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest tests\
```

---

## Configuracao

### Pasta de saida

Por padrao os arquivos vao para `C:\Users\<usuario>\Music\gravador_audio\`. Na interface grafica e possivel alterar antes de iniciar a gravacao.

### Modelo Whisper

A interface permite selecionar o modelo. Modelos disponiveis dependem do que ja foi baixado:

| Modelo | Tamanho | Qualidade |
|---|---|---|
| `tiny` | ~74 MB | baixa |
| `base` | ~142 MB | basica |
| `small` | ~244 MB | boa (padrao) |
| `medium` | ~1.5 GB | alta |
| `large-v3` | ~3 GB | maxima |

O modelo e baixado automaticamente na primeira vez que e usado.

---

## Diagnostico

Erros de audio e pipeline sao registrados em `gravador.log` na raiz do projeto.

Se o Claude Code CLI nao estiver instalado ou autenticado, a sintese falha mas a `transcricao.md` e sempre salva.
