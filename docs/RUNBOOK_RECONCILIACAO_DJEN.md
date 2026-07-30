# Reconciliação independente EJC × DJEN

## Objetivo

Detectar falhas silenciosas na captura de intimações comparando o EJC com uma
consulta manual e independente no portal oficial do DJEN/CNJ. O estado técnico
“captura executada com sucesso” não prova, sozinho, que o total capturado está
correto.

Fontes oficiais:

- Portal de Comunicações Processuais/DJEN: <https://comunica.pje.jus.br/>
- Página institucional do CNJ: <https://www.cnj.jus.br/programas-e-acoes/processo-judicial-eletronico-pje/comunicacoes-processuais/>
- Resolução CNJ nº 455/2022, texto vigente: <https://atos.cnj.jus.br/atos/detalhar/4509>

## Separação obrigatória das fontes

A amostra oficial deve ser levantada manualmente no portal público do DJEN por
um operador autorizado. Não use, como “fonte independente”, a mesma resposta da
API Comunica consumida pelo job do EJC: isso reproduziria uma eventual falha
comum e não cumpriria a finalidade da auditoria.

O comparador não acessa produção, não chama o DJEN e não calcula prazos. Ele
apenas confronta dois CSVs preparados por pessoas autorizadas.

## Escopo mínimo da amostra

1. Escolha um período fechado em que o job já tenha concluído.
2. Consulte no portal oficial a mesma inscrição OAB/UF monitorada pelo EJC.
3. Registre somente:
   - data de disponibilização;
   - número CNJ;
   - tribunal;
   - tipo de comunicação;
   - identificador externo, se visível nas duas fontes.
4. Extraia do EJC os mesmos campos para o mesmo período.
5. Não copie inteiro teor, nomes, CPF/CNPJ, e-mail, partes ou número da OAB para
   os CSVs.

Use os modelos:

- `docs/templates/djen_amostra_ejc.csv`
- `docs/templates/djen_amostra_oficial.csv`

Os arquivos reais e o relatório não devem ser versionados no GitHub. Guarde-os
somente no repositório confidencial aprovado para a auditoria.

## Execução

Defina uma chave efêmera com pelo menos 16 caracteres sem gravá-la no comando:

```bash
read -rsp "Chave efêmera da reconciliação: " DJEN_RECONCILIACAO_CHAVE
export DJEN_RECONCILIACAO_CHAVE
python scripts/djen/reconciliar_amostra.py \
  --ejc /caminho/seguro/ejc.csv \
  --djen /caminho/seguro/djen-oficial.csv \
  --inicio AAAA-MM-DD \
  --fim AAAA-MM-DD \
  --saida /caminho/seguro/relatorio-djen.json
unset DJEN_RECONCILIACAO_CHAVE
```

Códigos de saída:

- `0`: amostras conformes;
- `2`: divergência encontrada;
- `1`: entrada inválida ou falha operacional.

O relatório contém apenas totais, SHA-256 dos arquivos-fonte e HMACs truncados
das chaves divergentes. Ele não contém número de processo nem identificador em
claro.

## Decisão e resposta

| Resultado | Ação |
|---|---|
| Conforme | Registrar data, período, hashes e revisor. Não interpretar como garantia permanente. |
| Faltante no EJC | Suspender confiança exclusiva no alerta automatizado, conferir manualmente o período e abrir incidente com prioridade alta. |
| Extra no EJC | Conferir filtros, duplicidade e intervalo de datas antes de descartar qualquer comunicação. |
| Identificador divergente | Conferir o registro no portal e no banco; não resolver automaticamente. |
| Entrada inválida | Corrigir a amostra; nunca completar dados por inferência. |

Nenhum resultado deste processo autoriza criação automática de prazo. A
publicação e a contagem aplicável devem ser revisadas pelo advogado responsável.

## Cadência e evidência

Como implantação, execute semanalmente por quatro semanas. Se não houver
divergência e o job permanecer saudável, a gestão pode aprovar cadência mensal.
Repita imediatamente após mudanças na integração, incidentes, indisponibilidade
do CNJ ou relato de intimação ausente.

Cada execução requer operador e revisor distintos. Registre apenas: período,
data/hora, status, hashes dos CSVs, hash do relatório, responsável e revisor.
