# gravador_audio

Aplicacao para Windows que grava audio local em `.mp3`, incluindo microfone e audio do sistema.

## Requisitos

- Windows.
- Python 3.12 ou superior.
- Na instalacao do Python, marque `Add python.exe to PATH`.

## Como usar no Windows

### 1. Baixar o projeto

Baixe ou clone este repositorio no Windows.

Se usar Git:

```powershell
git clone https://github.com/VictorJurado18/gavador_audio.git
cd gavador_audio
```

### 2. Instalar

Duas vezes clique em:

```text
Instalar.bat
```

Esse script cria o ambiente local `.venv` e instala as dependencias de audio.

### 3. Abrir a interface

Duas vezes clique em:

```text
Abrir Gravador.vbs
```

Esse arquivo abre a interface sem mostrar uma janela de prompt.

Na janela, escolha o modo de captura e clique em `Iniciar gravacao`. Para finalizar, clique em `Parar gravacao`.

Os arquivos gerados ficam por padrao em:

```text
C:\Users\<seu-usuario>\Music\gravador_audio\
```

Na interface, voce pode escolher outra pasta antes de iniciar.

### Alternativa: gravar pelo modo guiado no terminal

Duas vezes clique em:

```text
Gravar.bat
```

O programa pergunta:

- quantos segundos deseja gravar;
- se quer gravar microfone + sistema, so microfone ou so sistema.

## Uso tecnico

Abrir interface:

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.gui
```

Rodar uma gravacao de 20 segundos:

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.cli --duration 20
```

Somente microfone:

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.cli --duration 20 --microphone-only
```

Somente audio do sistema:

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m gravador_audio.cli --duration 20 --system-only
```

Rodar testes:

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m unittest discover -s tests
```
