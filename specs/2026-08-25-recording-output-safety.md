# Gravação: escolhas explícitas e preservação do áudio

## Objetivo

Dar à pessoa controle claro sobre o que acontece depois de parar uma gravação e garantir que o áudio seja preservado antes de qualquer operação de IA.

## Decisões

- A aba **Gravar** oferece três resultados: somente áudio, áudio com transcrição, ou áudio com transcrição e resumo.
- O padrão continua sendo o fluxo completo: áudio, transcrição e resumo.
- O áudio é finalizado no destino escolhido antes de enfileirar a transcrição ou o resumo.
- Se a transcrição falhar, o MP3 permanece no destino original e aparece na Biblioteca como **somente áudio salvo**.
- O campo **Perfil** é documentado na própria tela: ele é um atalho para formato do resumo, modelo Whisper e separação de falantes; não altera nada em modo Personalizado.

## Critérios de aceite

- A pessoa consegue escolher somente salvar o áudio sem configurar provider de resumo.
- A pessoa consegue pedir apenas a transcrição, sem chamar o provider de resumo.
- O MP3 continua acessível quando o pipeline de IA falha.
- A Biblioteca lista MP3s ainda não processados.
