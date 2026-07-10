# Patch seguro — `peca_service.py`

## Objetivo

Remover resíduos de apresentação como `rascunho IA` no pipeline de geração de peças, sem alterar RAG, SSE, pseudonimização, `AILog`, `LegalDoc`, `human_reviewed`, `status_hitl`, verificação de citações ou migrations.

## Arquivo

```text
backend/app/services/peca_service.py
```

## Linhas críticas confirmadas

No snapshot atual da `main`, o prompt final da etapa 7 ainda contém:

```python
"3. Toda saída é RASCUNHO — revisão humana obrigatória (OAB).\n"
```

E o `LegalDoc` ainda é salvo com:

```python
titulo=f"{nome_peca} - rascunho IA",
```

## Alteração 1 — prompt final da etapa 7

Substituir:

```python
"3. Toda saída é RASCUNHO — revisão humana obrigatória (OAB).\n"
"4. Use formatação jurídica padrão (Dos Fatos, Do Direito, Dos Pedidos)."
```

Por:

```python
"3. Diferencie fatos confirmados, inferências técnicas, lacunas documentais e pontos a conferir.\n"
"4. Use formatação jurídica padrão (Dos Fatos, Do Direito, Dos Pedidos)."
```

## Alteração 2 — título do `LegalDoc`

Substituir:

```python
titulo=f"{nome_peca} - rascunho IA",
```

Por:

```python
titulo=f"{nome_peca} - IA jurídica",
```

## O que não alterar

```python
status_hitl=AIStatusHITL.gerado
human_reviewed=False
ai_generated=True
"aviso": aviso_rascunho_ia()
```

Esses campos continuam úteis como trilha interna de auditoria e controle de conferência técnica. O ajuste necessário é de apresentação e prompt, não de governança.

## Validação mínima

```bash
cd backend
python -m compileall app
```

Teste funcional:

1. gerar uma peça;
2. confirmar que o prompt não instrui mais a IA a declarar `RASCUNHO`;
3. confirmar que o `LegalDoc.titulo` não salva `rascunho IA`;
4. confirmar que `ai_logs.status_hitl` e `legal_docs.human_reviewed` permanecem como controle interno.
