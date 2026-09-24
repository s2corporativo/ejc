# E2E Homologação - Playwright

## Instalação

```bash
cd frontend
npm install -D playwright
npx playwright install chromium
```

## Execução

Crie um arquivo `.env.e2e` com as credenciais (NUNCA commitar!):

```bash
EJC_BASE_URL=https://ejc.depaulateixeira.adv.br
EJC_USER_EMAIL=admin@depaulateixeira.adv.br
EJC_USER_PASSWORD=sua_senha_aqui
```

Ou passe via variáveis de ambiente:

```bash
EJC_BASE_URL=https://ejc.depaulateixeira.adv.br \
EJC_USER_EMAIL=admin@depaulateixeira.adv.br \
EJC_USER_PASSWORD=sua_senha \
node tests/e2e-homologacao.mjs
```

## Testes Cobertos

1. ✅ Login com credenciais válidas
2. ✅ Sidebar visível após login
3. ✅ Navegação para Casos
4. ✅ Navegação para Clientes
5. ✅ Navegação para Atividades
6. ✅ Navegação para Financeiro
7. ✅ Logout funciona

## Adicionar Novos Testes

```javascript
await runTest("Nome do teste", async () => {
  // Seu código aqui
  await page.goto(`${BASE_URL}/sua-rota`);
  // Verificações...
});
```
