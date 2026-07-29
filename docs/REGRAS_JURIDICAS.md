# REGRAS JURÍDICAS IMPLEMENTADAS EM CÓDIGO — EJC

> **Este documento não pode ser gerado automaticamente.** Cada linha exige verificação de
> fonte oficial e de vigência por profissional habilitado. Preenchimento por inferência
> de agente é vedado por `docs/GOVERNANCA_IA.md`, Seção 9 (Regras jurídicas), e pela
> regra 5 de `CLAUDE.md`: toda regra jurídica precisa de fonte oficial, vigência e teste.

| Campo | Valor |
|---|---|
| Última verificação de vigência | _(data)_ |
| Responsável pela verificação | _(OAB)_ |
| Próxima revisão obrigatória | _(data — recomendado: semestral)_ |

---

## 1. Registro de regras

Uma linha por regra implementada. Regra sem fonte oficial não é mesclável.

| ID | Regra | Dispositivo | Fonte oficial (URL) | Vigência verificada em | Módulo/arquivo | Teste | Exceções tratadas | Estado |
|---|---|---|---|---|---|---|---|---|
| RJ-001 | | | | | | | | |
| RJ-002 | | | | | | | | |

Estados admitidos: `VIGENTE` · `ALTERADA` · `REVOGADA` · `EM VERIFICAÇÃO` · `PENDENTE DE FONTE`

Regra em `PENDENTE DE FONTE` deve estar desativada em produção.

---

## 2. Regras de prazo

Contagem processual é a principal fonte de dano ao cliente. Cada entrada exige teste de virada de fim de semana, feriado e suspensão.

| ID | Ato | Prazo | Contagem | Termo inicial | Suspensão/interrupção | Dispositivo | Fonte | Teste |
|---|---|---|---|---|---|---|---|---|
| | | | dias úteis / corridos | | | | | |

Pontos de atenção obrigatórios ao implementar contagem:
- Dias úteis versus corridos varia por rito. Não generalizar de um rito para outro.
- Exclusão do dia inicial e inclusão do dia final.
- Suspensão de prazos e feriados forenses, incluindo feriados locais do tribunal competente.
- Prorrogação quando o vencimento cai em dia sem expediente.
- Contagem em dobro, quando aplicável ao caso.

Calendário de feriados deve ser dado versionado e auditável, nunca constante embutida em código.

---

## 3. Regras de cálculo

| ID | Cálculo | Base normativa | Índice/critério | Fonte do índice | Periodicidade de atualização | Módulo | Teste |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

Índice econômico é dado externo com atualização periódica: exige data de referência registrada em cada resultado.

---

## 4. Vedações e limites

| ID | Vedação | Dispositivo | Onde é aplicada no sistema | Teste |
|---|---|---|---|---|
| | | | | |

Incluir obrigatoriamente: limites de publicidade da advocacia; vedação de promessa de resultado; sigilo profissional; conflito de interesses; retenção e exclusão de dados sob a LGPD.

---

## 5. Avisos obrigatórios na interface

| Onde | Texto exibido | Motivo | Dispositivo |
|---|---|---|---|
| Saída de IA | Minuta sujeita a revisão do advogado responsável | Vedação de aconselhamento automatizado | |
| Cálculo de prazo | Fonte normativa e data da verificação | Rastreabilidade | |
| Cálculo de valor | Índice, data-base e critério | Auditabilidade | |

---

## 6. Protocolo de atualização normativa

1. Alteração legislativa identificada é registrada como Issue com label `juridico` e prioridade P0.
2. A regra afetada muda para `EM VERIFICAÇÃO` neste documento.
3. Verificação de vigência com fonte oficial, datada e assinada pelo responsável.
4. Implementação com teste do caso novo **e** teste de regressão do caso anterior.
5. Registro do histórico na Seção 7.
6. Nenhuma regra em `EM VERIFICAÇÃO` permanece ativa em produção.

---

## 7. Histórico de alterações normativas

| Data | Regra | Alteração | Norma alteradora | Fonte | Impacto no sistema | PR |
|---|---|---|---|---|---|---|
| | | | | | | |
