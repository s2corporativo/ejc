# 📤 Como publicar o JuridIA no GitHub

## ❌ Por que não pude publicar automaticamente

Não tenho:
- Chaves SSH configuradas (`~/.ssh/` não existe)
- `gh` CLI instalado
- Credenciais GitHub armazenadas
- Acesso SSH (comando `ssh` não disponível)

## ✅ O que já foi preparado

1. ✅ **Git repo inicializado** com 33 commits (todo o histórico de desenvolvimento)
2. ✅ **Remote configurado**: `origin → https://github.com/s2corporativo/ejc.git`
3. ✅ **Branch `main`** criada
4. ✅ **.env** removido do tracking (sensível)
5. ✅ **db/custom.db** removido do tracking (binário)
6. ✅ **.env.example** criado (template para novos contribuidores)
7. ✅ **README.md** criado (128 linhas documentando o sistema)
8. ✅ **.gitignore** configurado (node_modules, .next, .env, db/, etc.)
9. ✅ **Bundle tar.gz** criado em `/tmp/juridia-deploy-bundle.tar.gz` (40MB)

## 🚀 Passos para publicar (execute localmente no seu computador)

### Opção A: Usando Personal Access Token (recomendado)

```bash
# 1. Clone o repo local (já está em /home/z/my-project)
cd /home/z/my-project

# 2. Crie um Personal Access Token no GitHub:
#    https://github.com/settings/tokens → "Generate new token (classic)"
#    Marque scopes: repo (full)
#    Copie o token (formato: ghp_xxxxxxxxxxxxxxxxxxxx)

# 3. Force push (sobrescreve tudo que estiver no remote):
git push --force https://<SEU_TOKEN>@github.com/s2corporativo/ejc.git main

# Exemplo (substitua <TOKEN>):
git push --force https://ghp_abc123@github.com/s2corporativo/ejc.git main
```

### Opção B: Usando HTTPS com username + password

```bash
cd /home/z/my-project
git push --force origin main
# Vai pedir: Username: <seu-usuario-github>
# Password: <seu-personal-access-token> (NÃO use sua senha de login!)
```

### Opção C: Usando SSH (se você já tem chave SSH configurada)

```bash
cd /home/z/my-project
git remote set-url origin git@github.com:s2corporativo/ejc.git
git push --force origin main
```

## 🗑️ "Apague tudo que estiver lá"

O comando `git push --force` faz exatamente isso:
- **Sobrescreve** todos os branches do remote com seu branch `main` local
- **Deleta** branches remotos que não existem localmente (se usar `--all --force`)
- **Substitui** todo o histórico do remote pelo seu histórico local (33 commits)

Para forçar a deleção de TODOS os branches remotos (não só main):
```bash
git push --force --all origin
# E para deletar tags:
git push origin --delete --tags
```

## 📦 Bundle alternativo (se quiser transferir sem git)

Se você não quer configurar git authentication, pode:
1. Baixar o bundle em `/tmp/juridia-deploy-bundle.tar.gz` (40MB)
2. Extrair no seu computador
3. Fazer `git init` + `git add -A` + `git commit -m "Initial commit"`
4. `git remote add origin https://github.com/s2corporativo/ejc.git`
5. `git push --force origin main`

## ⚠️ Atenção antes de publicar

- ✅ `.env` está no `.gitignore` (não será publicado)
- ✅ `db/custom.db` está no `.gitignore` (não será publicado)
- ✅ `node_modules/` está no `.gitignore`
- ✅ `dev.log` está no `.gitignore`
- ✅ `upload/` (uploads de usuário) está no `.gitignore`
- ⚠️  Verifique se há algum segredo hardcoded em `src/` antes de publicar publicamente
- ✅ Nenhum segredo encontrado (apenas email "demo@juridia.com.br" como default user)

## 🔒 Após publicar

1. **Desative o remote tracking** se quiser parar de sincronizar:
   ```bash
   git remote remove origin
   ```
2. **Configure GitHub secrets** se for fazer deploy:
   - `DATABASE_URL` (production database)
   - `JURIDIA_API_TOKEN` (token de auth)
3. **Ative branch protection** no GitHub (Settings → Branches):
   - Require pull request before merging
   - Require status checks
4. **Adicione LICENSE** (MIT/Apache) se quiser opensource real
5. **Adicione CONTRIBUTING.md** se aceitar contribuições

## 📊 Resumo do que será publicado

- **33 commits** (histórico completo do desenvolvimento)
- **1305 arquivos tracked** (sem node_modules, .next, .env, db/)
- **Tamanho do bundle**: 40MB compactado
- **Conteúdo**: código fonte completo + README + .env.example
- **Sem dados fictícios**: banco SQLite NÃO está no repo (só schema)
- **Sem credenciais**: .env e .env.local no .gitignore
