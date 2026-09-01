# Voice Notes — instruções de release

## Regra inegociável: versão e instalador

Para toda PR autorizada pelo usuário que entregue alteração funcional do app,
trate-a como uma release nova, salvo se o usuário disser explicitamente que não
quer publicar/gerar instalador.

Antes de fazer o commit e abrir a PR:

1. Defina a próxima versão (normalmente incremento de patch) a partir da versão
   publicada mais recente.
2. Atualize **a mesma versão** em `pyproject.toml` e em
   `installer/VoiceNotes.iss` (`MyAppVersion`).
3. Confirme por leitura que os dois valores são idênticos e que o nome do
   instalador resultante será `VoiceNotes-Setup-x.y.z.exe`.
4. Execute a suíte de testes aplicável e só então faça push/PR.
5. Na entrega, informe explicitamente a versão que será publicada e que o
   merge na `main` acionará o GitHub Actions para gerar o novo instalador.

Nunca afirme que uma PR gerará instalador/release se o incremento de versão não
estiver incluído. Para PRs de documentação, testes internos ou alterações que o
usuário declarar como não publicáveis, registre explicitamente que não haverá
nova versão.
