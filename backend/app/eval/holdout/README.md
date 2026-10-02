# Holdout jurídico secreto do EJC

Arquivos reais de holdout **não pertencem ao Git**. Mantenha os JSONL em diretório
privado/volume seguro e passe o caminho apenas na execução do benchmark.

Regras:
- nunca usar o holdout para ajustar prompt, provider, threshold ou RAG;
- pseudonimizar antes de armazenar;
- curadoria humana + fonte oficial + vigência conferida;
- registrar apenas o hash/manifesto no relatório de certificação;
- abrir o holdout somente na rodada final da versão congelada.

Validação:

```bash
python -m app.eval.holdout_guard /caminho/privado/holdout.jsonl
```

O diretório ignora `*.jsonl` deliberadamente para impedir commit acidental.
