# Especificações de experiência e confiabilidade

Data: 2026-08-24

## 1. Borda do widget ao trocar de aba

**Problema:** a base do widget pode parecer reta após alternar entre Gravar, Arquivo, YouTube, Biblioteca e Ajustes.

**Comportamento esperado:** a janela inteira permanece com o mesmo raio arredondado, inclusive nos dois cantos inferiores, durante e depois de cada troca de página e redimensionamento.

**Aceite:** cada destino reaplica o recorte nativo da janela; a superfície externa usa o mesmo raio visual; o conteúdo não muda o formato da janela.

## 2. Token para separar falantes

**Problema:** o token do Hugging Face fica permanentemente oculto, impedindo conferência e cópia.

**Comportamento esperado:** em Ajustes > Falantes, a pessoa pode alternar Mostrar/Ocultar, copiar o valor e salvá-lo no Cofre de Credenciais do Windows. O valor inicia oculto e só é revelado por ação explícita.

**Aceite:** Mostrar revela o token sem modificá-lo; Copiar envia o token para a área de transferência; Salvar persiste-o no keyring e habilita a separação de falantes.

## 3. Instalação automática do Codex CLI e Claude Code

**Problema:** uma falha na etapa opcional do instalador deixa o app sem provider e exige Node.js, npm e PATH configurados manualmente.

**Comportamento esperado:** quando o provider selecionado não existir, o app instala em segundo plano um Node.js privado e os CLIs em `%LOCALAPPDATA%\Voice Notes\tools`, sem depender de PATH. O resultado e o arquivo de log são informados no widget.

**Aceite:** o instalador e a recuperação no app usam o mesmo script; os executáveis locais são localizados antes de PATH; falhas não abrem terminal e podem ser diagnosticadas pelo log.

## 4. Nenhuma janela preta

**Problema:** comandos acionados pela interface podem exibir `cmd.exe`/PowerShell para a pessoa usuária.

**Comportamento esperado:** verificações, workers, instalação e login não criam janela de console. O login é opt-in por “Conectar conta no navegador”; nunca é disparado automaticamente ao abrir o widget.

**Aceite:** subprocessos Windows usam `CREATE_NO_WINDOW`; não há chamada a `cmd.exe /k`; tarefas longas atualizam a UI sem bloquear a gravação.

## 5. Atualização rápida do repositório

**Problema:** uma cópia Git do projeto não avisa quando a origem possui commits novos.

**Comportamento esperado:** em Ajustes > Provider e API, o app consulta a última Release do repositório público de distribuição, compara a versão instalada e habilita “Atualizar agora” quando houver um instalador mais recente. Após confirmação, baixa o setup, verifica o SHA-256 quando publicado, fecha o widget e executa a atualização.

**Aceite:** a consulta não abre terminal; a versão instalada é comparada à Release; somente o instalador `VoiceNotes-Setup-x.y.z.exe` é aceito; a pessoa confirma antes do download; o app é reiniciado após sucesso.

### Publicação automática

**Comportamento esperado:** ao receber um merge na `main` com uma versão ainda não publicada, o GitHub Actions executa os testes, constrói o instalador e publica a Release no repositório público de distribuição. Um token limitado ao repositório de distribuição é usado apenas no job de publicação.
