# Voice Notes

O Voice Notes é um widget para Windows que grava reuniões, aulas e chamadas, transforma o áudio em texto no próprio computador e cria resumos em português. Também processa arquivos de áudio, transcrições prontas e vídeos do YouTube que você tenha autorização para usar.

---

## Comece por aqui — guia para usar o aplicativo

Você não precisa instalar Python, abrir terminal ou criar uma conta técnica para gravar e transcrever. Siga os passos abaixo.

### 1. Baixar e instalar

1. Baixe o arquivo mais recente `VoiceNotes-Setup-x.y.z.exe` nas [Releases públicas](https://github.com/VictorJurado18/voice-notes-releases/releases). Não baixe o código-fonte (`.zip`) para instalar o aplicativo.
2. Clique duas vezes no instalador baixado.
3. Mantenha marcada a opção **Iniciar automaticamente com o Windows** se quiser deixar o widget sempre disponível perto do relógio.
4. Mantenha marcada a opção de instalar **Codex CLI e Claude Code** se quiser usar um deles para criar resumos. A preparação pode levar alguns minutos e requer internet.
5. Clique em **Instalar** e, ao terminar, em **Abrir o widget Voice Notes**.

O aplicativo é instalado só para o seu usuário, em `%LOCALAPPDATA%\Programs\Voice Notes`. Não exige conta de administrador, Python ou uma `.venv` no computador de destino.

Quando houver uma nova versão publicada nas [Releases públicas de distribuição](https://github.com/VictorJurado18/voice-notes-releases/releases), o Voice Notes avisa em **Ajustes** › **Provider e API**. Você pode escolher **Atualizar agora** para baixar o instalador, verificar sua integridade, fechar o widget e iniciar a versão nova sem usar terminal.

> O Windows pode mostrar uma tela de proteção ao abrir um instalador ainda não reconhecido. Confira se o arquivo veio da fonte esperada antes de escolher qualquer opção para continuar.

### 2. Encontrar e mover o widget

O Voice Notes funciona como um widget, sem a barra branca tradicional das janelas do Windows.

- Arraste a área superior para mover o widget pela tela.
- Arraste o próprio canto inferior direito para alterar o tamanho. A cápsula, os controles e a tipografia crescem ou diminuem juntos, mantendo a proporção e os cantos arredondados.
- Clique em **Minimizar** para transformar o app em uma etiqueta discreta. Ela reduz no mesmo local do widget, continua sobre os outros programas, mostra o estado e o nível de áudio e oferece **Iniciar** e **Parar**.
- Arraste a área informativa da etiqueta para movê-la. Um clique curto nessa área restaura o widget completo no tamanho anterior.
- Clique em **Ocultar** para escondê-lo de verdade e continuar usando o menu do ícone do Voice Notes perto do relógio. Ele pode estar dentro da seta `^` de **itens ocultos**.
- O menu do ícone na bandeja permite mostrar, ocultar ou encerrar o aplicativo.

### 3. Escolher como o resumo será criado

A transcrição é feita localmente pelo Whisper; ela funciona mesmo antes de você configurar uma IA de resumo. Para gerar resumos, abra **Ajustes** › **Provider e API** e escolha uma opção:

| Opção | Quando escolher | Primeiro uso |
|---|---|---|
| **Codex** | Você usa uma conta OpenAI/Codex. | Clique em **Conectar conta no navegador**; nenhuma janela de terminal é aberta. |
| **Claude Code** | Você usa uma conta Claude Code. | Clique em **Conectar conta no navegador**; nenhuma janela de terminal é aberta. |
| **API por token** | Você tem uma chave de uma API de IA. | Clique em **+ Novo Provider**, informe nome, URL, modelo e token. |

O Codex é a opção inicial. O login pertence ao provider escolhido; o Voice Notes não pede sua senha dentro do widget nem abre uma janela preta de terminal.

Para APIs compatíveis com OpenAI, basta informar a URL base, o modelo e o token. Para outros serviços JSON, abra **Opções avançadas** e informe o formato da requisição e o caminho da resposta. O token é salvo no **Cofre de Credenciais do Windows**, não no arquivo de configuração.

### 4. Fazer a primeira gravação

1. Abra a página **Gravar**.
2. Em **Fonte de áudio**, escolha:
   - **Microfone + sistema** para registrar sua voz e o som do computador;
   - **Microfone** para registrar apenas sua voz;
   - **Sistema** para registrar apenas o som reproduzido pelo Windows.
3. Em **Salvar em**, confira a pasta ou clique em **Alterar**. Por padrão, os arquivos vão para `Música\record-transcript-resume`.
4. Escolha o **Formato do resumo**: reunião, aula, entrevista, call comercial, brainstorm, resumo executivo, estudo ou plano de ação.
5. Se desejar, defina **Parar após** um número de minutos ou horas. Deixe vazio para gravar até você parar manualmente.
6. Clique em **Iniciar gravação**.
7. Ao terminar, clique em **Parar** ou aguarde o tempo programado.

O widget mostra as etapas. Você pode ocultá-lo enquanto o áudio é transcrito ou resumido: o trabalho continua em segundo plano. Se você tentar encerrar o aplicativo durante uma gravação, transcrição ou resumo, ele será protegido e irá para a bandeja em vez de perder o trabalho.

Ao final, uma pasta semelhante a esta é criada:

```text
Música\record-transcript-resume\reuniao-de-planejamento\
    recording-AAAAMMDD-HHMMSS.mp3
    transcription.md
    summary.md
```

### 5. Escolher a qualidade da transcrição

Em **Ajustes** › **Transcrição**, escolha o idioma e o modelo Whisper. No primeiro uso de cada modelo, ele será baixado e ficará guardado no computador.

| Modelo | Melhor para | Observação curta |
|---|---|---|
| `tiny` | Testes | Muito rápido, menos preciso. |
| `base` | Áudio simples | Rápido e básico. |
| `small` | Reuniões do dia a dia | Equilíbrio recomendado. |
| `medium` | Áudio difícil | Mais preciso, mais lento. |
| `large-v3` | Maior qualidade | Mais pesado e demorado. |

### 6. Separar as pessoas que falaram

O Voice Notes pode identificar blocos como **Pessoa 1**, **Pessoa 2** e assim por diante. Ele não adivinha nomes por conta própria, mas a Biblioteca pode sugerir uma troca quando uma autoapresentação for muito clara — você sempre confirma antes de aplicar.

Para ativar essa opção:

1. Crie uma conta gratuita no Hugging Face.
2. Acesse [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) e aceite as condições de uso do modelo.
3. Crie um token de leitura no Hugging Face.
4. No Voice Notes, abra **Ajustes** › **Falantes**, cole o token e habilite **Separar falantes**. Use **Mostrar/Ocultar**, **Copiar** e **Salvar token** quando precisar conferir ou reutilizar a chave.

O modelo é baixado e executado localmente. O token fica no Cofre de Credenciais do Windows. Se um token autorizado já estiver salvo, a separação vem habilitada por padrão.

### 7. Processar algo que você já possui

Use a página certa para cada situação:

| Você tem… | Onde ir | O que fazer |
|---|---|---|
| Um MP3, WAV, M4A ou outro áudio | **Arquivo** | Importe o áudio; o Voice Notes cria a transcrição e o resumo. |
| Um texto já transcrito | **Arquivo** | Cole o texto ou abra um arquivo `.txt`/`.md`, depois gere somente o resumo. |
| Um vídeo do YouTube autorizado | **YouTube** | Cole o link — com ou sem `https://` — e escolha transcrição e resumo, só transcrição ou só resumo. |
| Uma transcrição/resumo que deseja corrigir | **Biblioteca** | Abra o documento, edite, salve e use **Salvar e gerar resumo**. |

Na **Biblioteca**, também é possível abrir a pasta original e exportar o documento aberto para **DOCX** ou **PDF**.

Na página **YouTube**, a opção **Só resumo** ainda transcreve o áudio localmente para ter conteúdo para resumir, mas não guarda o arquivo `transcription.md`. Escolha **Só transcrição** se não quiser enviar texto a um provider de IA.

### 8. Resolver problemas comuns

#### O widget não aparece

Procure o ícone do Voice Notes perto do relógio do Windows, inclusive dentro de `^` (**itens ocultos**), e dê dois cliques nele. Se o ícone não estiver lá, abra **Voice Notes** pelo menu Iniciar.

#### A transcrição terminou, mas não houve resumo

Abra **Ajustes** › **Provider e API** e confirme o provider. Se for necessário entrar na conta, conclua o login no Prompt de Comando aberto. Depois abra **Arquivo** ou **Biblioteca** e use a opção para tentar o resumo novamente. A transcrição é preservada mesmo quando o resumo falha.

#### Não foi possível separar os falantes (erro 403)

Seu token ainda não tem permissão para o modelo do Hugging Face. Acesse a página do modelo, aceite as condições, aguarde a aprovação se ela for solicitada e use um novo token de leitura.

#### O áudio do sistema não foi gravado

Confirme que existe um dispositivo de saída ativo no Windows e que você escolheu **Sistema** ou **Microfone + sistema**. Em chamadas, confira se o programa de reunião está reproduzindo som no dispositivo de saída padrão.

#### Não quero abrir junto com o Windows

Execute o instalador novamente e desmarque **Iniciar automaticamente com o Windows**, ou remova o atalho `Voice Notes` da pasta:

```text
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
```

#### Onde fica o log técnico?

O log fica em `%LOCALAPPDATA%\Voice Notes\recorder.log`. Anexe esse arquivo ao relatar um erro; evite enviar áudios ou transcrições confidenciais sem necessidade.

### Privacidade e uso responsável

- O áudio é gravado e transcrito localmente no computador.
- Para gerar um resumo, somente o texto transcrito é enviado ao Codex, Claude Code ou à API que você escolheu.
- Ao usar YouTube, o aplicativo acessa o link informado para baixar o áudio. Processe somente conteúdo próprio, público ou autorizado.
- Os arquivos produzidos ficam na pasta escolhida por você.
- Antes de processar conteúdo sensível, leia as políticas do provider de IA escolhido.

---

## Referência técnica — para desenvolvimento e manutenção

### Visão geral da arquitetura

```text
Microfone / áudio do sistema / arquivo / YouTube
                    │
                    ▼
             MP3 ou áudio de entrada
                    │
                    ▼
     Whisper local (faster-whisper / CTranslate2)
                    │
                    ├── opcional: diarização local com pyannote
                    ▼
             transcription.md
                    │
                    ▼
 Codex CLI / Claude Code / API JSON configurável
                    │
                    ▼
               summary.md
```

O processo pesado de transcrição e resumo roda em um subprocesso separado. Assim, uma falha nativa do modelo não encerra diretamente a interface. Trabalhos pendentes são armazenados no diretório de dados do aplicativo e podem ser retomados quando o MP3 original ainda existir.

### Tecnologias principais

| Componente | Uso |
|---|---|
| Python 3.12+ | Aplicação e ferramentas de desenvolvimento. |
| CustomTkinter + Tk | Widget sem borda, páginas e controles. |
| PyAudioWPatch | Microfone e loopback de áudio do Windows. |
| faster-whisper / CTranslate2 | Transcrição local. |
| pyannote.audio | Diarização opcional de falantes. |
| Codex CLI / Claude Code | Providers de resumo via login do usuário. |
| `urllib` + Keyring | Provider por token e armazenamento seguro de credenciais. |
| yt-dlp + imageio-ffmpeg | Download autorizado de áudio do YouTube. |
| python-docx + ReportLab | Exportação para DOCX e PDF. |
| PyInstaller + Inno Setup | Empacotamento e instalador para Windows. |

### Requisitos de desenvolvimento

| Ferramenta | Requisito |
|---|---|
| Sistema operacional | Windows 10 ou 11, 64 bits |
| Python | 3.12 ou superior |
| Inno Setup | 6, apenas para gerar o instalador |
| Internet | Dependências, modelos Whisper, CLIs e YouTube |

### Preparar o ambiente

```powershell
git clone <URL_DO_REPOSITORIO>
cd voice_recorder_ai
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_windows.ps1
```

O script cria `.venv` e instala as dependências. Para executar a interface a partir do código:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m record_transcript_resume.gui
```

Atalhos úteis no repositório:

| Arquivo | Uso |
|---|---|
| `Open Recorder.vbs` | Abre o widget sem terminal. |
| `Open Recorder.bat` | Abre o widget com terminal para diagnóstico. |
| `Open Widget.vbs` | Atalho equivalente para o widget. |
| `Record.bat` | Gravação guiada pelo terminal. |
| `Build Installer.bat` | Gera o executável e o instalador. |

### Linha de comando

Execute os comandos abaixo na raiz do repositório:

```powershell
$env:PYTHONPATH = "src"
```

```powershell
# Gravar 20 segundos usando microfone e sistema
.\.venv\Scripts\python.exe -m record_transcript_resume.cli record --duration 20

# Gravar apenas o microfone
.\.venv\Scripts\python.exe -m record_transcript_resume.cli record --duration 20 --microphone-only

# Processar um MP3 existente com Codex
.\.venv\Scripts\python.exe -m record_transcript_resume.cli process .\reuniao.mp3 --language pt --model small --provider codex

# Processar com Claude Code
.\.venv\Scripts\python.exe -m record_transcript_resume.cli process .\reuniao.mp3 --language pt --model small --provider claude
```

Opções relevantes:

| Comando | Opção | Descrição |
|---|---|---|
| `record` | `--output-dir <pasta>` | Pasta de saída. |
| `record` | `--duration <segundos>` | Duração fixa. |
| `record` | `--microphone-only` | Captura apenas o microfone. |
| `record` | `--system-only` | Captura apenas o áudio do sistema. |
| `record` | `--no-pipeline` | Não transcreve nem resume ao encerrar. |
| `record` / `process` | `--provider codex\|claude\|api` | Provider do resumo. `api` usa a configuração e o token já salvos pelo widget. |
| `process` | `--language <código>` | Ex.: `pt`, `en`, `es`. |
| `process` | `--model <modelo>` | Ex.: `small`, `medium`, `large-v3`. |

### Testes

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest -q
```

### Gerar o instalador

Com o Inno Setup 6 instalado na máquina de desenvolvimento:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1
```

Ou use `Build Installer.bat`. O processo gera um executável autocontido com PyInstaller e depois o instalador Inno Setup em `dist\VoiceNotes-Setup.exe`. A máquina de destino não precisa de Python nem de `.venv`.

Para gerar somente a pasta do aplicativo, sem compactar o instalador:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1 -SkipInstaller
```

### Checklist de release

Antes de distribuir uma versão nova:

1. Atualize a mesma versão em `pyproject.toml` e em `installer/VoiceNotes.iss`.
2. Execute `pytest -q` na `.venv`.
3. Gere o instalador e instale-o em uma conta Windows de teste, confirmando: inicialização pela bandeja, gravação, transcrição, resumo e abertura da Biblioteca.
4. Antes do merge, aumente a versão em `pyproject.toml` e `installer/VoiceNotes.iss`. Após o merge na `main`, o GitHub Actions testa, gera e publica automaticamente `VoiceNotes-Setup-x.y.z.exe` no repositório público `VictorJurado18/voice-notes-releases`.
5. Quando houver distribuição pública, publique também um checksum SHA-256 e considere assinar o instalador. Isso reduz alertas do Microsoft Defender SmartScreen e permite ao usuário verificar a origem do arquivo.

### Estrutura do projeto

```text
src/record_transcript_resume/
    gui.py                    # Widget, navegação e fluxos de interface
    recording.py              # Coordenação de gravação
    windows_audio_backend.py  # Microfone e loopback do Windows
    transcription.py          # Whisper local
    diarization.py            # Separação opcional de falantes
    synthesis.py              # Codex, Claude Code e formatos de resumo
    api_provider.py           # Provider REST JSON configurável por token
    pipeline.py               # Orquestração de transcrição e resumo
    library.py                # Descoberta de resultados salvos
    exports.py                # DOCX e PDF
    jobs.py                   # Fila e retomada de tarefas
    resources/install_providers.ps1 # Node local, Codex CLI e Claude Code
installer/
    VoiceNotes.iss            # Configuração do Inno Setup
tests/                        # Testes automatizados
```
