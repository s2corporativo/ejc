# Política de Continuidade — RPO e RTO do EJC

**Versão:** 2026-08-05  
**Escopo:** EJC — Ecossistema Jurídico Clovis  
**Responsáveis pela aprovação:** técnico, jurídico/LGPD e titular do produto

## 1. Finalidade

Definir os objetivos máximos de perda de dados e de retomada do EJC, sem confundir meta com capacidade comprovada.

- **RPO — Recovery Point Objective:** intervalo máximo aceitável entre o último ponto recuperável e o incidente.
- **RTO — Recovery Time Objective:** prazo máximo aceitável para restaurar o serviço em condição operacional mínima.

Esta política não substitui backup, restauração, rollback nem homologação. Um objetivo só é considerado **comprovado** quando medido em teste documentado com banco e uploads.

## 2. Classificação operacional

### 2.1 Piloto controlado

Objetivos aprováveis para o piloto:

- **RPO: 24 horas**;
- **RTO: 4 horas**.

Fundamento operacional: o mecanismo atual possui agenda diária de backup e monitoramento de recência. O RPO de 24 horas somente é válido se o backup diário estiver habilitado, cifrado, com cópia externa e sem falha silenciosa.

O RTO de 4 horas é uma meta condicionada. Antes do piloto, a restauração de banco e uploads deve ser executada e medida em ambiente isolado. Se o tempo observado superar quatro horas, o piloto permanece não certificado até ajuste da infraestrutura ou aprovação formal de objetivo mais conservador.

### 2.2 Produção plena

Objetivos mínimos pretendidos:

- **RPO: 6 horas**;
- **RTO: 4 horas**.

A produção plena não pode ser aprovada enquanto a infraestrutura continuar dependendo exclusivamente de um backup diário. Para cumprir RPO de seis horas, é necessário:

1. aumentar a frequência de pontos recuperáveis para no máximo seis horas;
2. manter banco e uploads no mesmo ciclo lógico ou registrar a defasagem entre eles;
3. manter cópia externa cifrada;
4. monitorar falha, atraso e ausência de qualquer um dos dois artefatos;
5. testar restauração periódica e registrar o tempo real.

Caso a frequência de seis horas não seja implementada, a decisão permitida é apenas **piloto controlado com RPO de 24 horas**, nunca produção plena apresentada como RPO de seis horas.

## 3. Escopo dos dados recuperáveis

A prova de continuidade deve abranger cumulativamente:

- banco PostgreSQL;
- uploads e documentos;
- migrations e versão da aplicação;
- configurações operacionais não secretas;
- referência à custódia externa das chaves necessárias à descriptografia;
- capacidade de iniciar backend, frontend e worker;
- login e consulta de massa fictícia após restauração.

A existência de dump do banco sem uploads, ou de uploads sem banco, não satisfaz o RPO/RTO do EJC.

## 4. Regras de medição

O relógio do RTO começa no registro formal do incidente ou no início do exercício de recuperação, o que ocorrer primeiro, e termina quando:

1. banco e uploads estiverem restaurados;
2. migrations e integridade estiverem verificadas;
3. health e readiness responderem;
4. login fictício funcionar;
5. um caso e um documento fictícios forem consultados;
6. filas essenciais estiverem operacionais.

O RPO é calculado comparando o horário do incidente simulado com o timestamp do ponto recuperado mais recente e íntegro.

## 5. Frequência de testes

### Piloto

- prova integral antes da entrada no piloto;
- teste de restauração pelo menos trimestral;
- novo teste após alteração relevante em banco, backup, armazenamento, criptografia ou deploy.

### Produção plena

- monitoramento diário do backup;
- restauração técnica trimestral;
- exercício completo de continuidade semestral;
- teste extraordinário após incidente, alteração de provedor, mudança de chave ou migration estrutural de alto risco.

## 6. Critérios de reprovação

A continuidade é reprovada quando ocorrer qualquer um dos seguintes:

- backup sem criptografia;
- ausência de cópia externa;
- falta do artefato de banco ou de uploads;
- chave de recuperação indisponível;
- restauração não inicia a aplicação;
- integridade ou migrations inconsistentes;
- tempo real acima do RTO aprovado;
- ponto recuperado mais antigo que o RPO aprovado;
- segredo exposto em log, issue ou artefato;
- evidência ligada a SHA diferente da release certificada.

## 7. Exceções

Exceção só pode ser aceita para piloto controlado, com:

- risco descrito objetivamente;
- prazo de correção;
- responsável;
- controles compensatórios;
- aprovação técnica, jurídica/LGPD e do titular.

Não existe exceção tácita. Produção plena não admite RPO/RTO não comprovados.

## 8. Registro no manifesto da release

Para piloto controlado, após teste real aprovado:

```json
{
  "status": "APPROVED",
  "rpo_hours": 24,
  "rto_hours": 4
}
```

Para produção plena, somente após aumento da frequência e nova prova:

```json
{
  "status": "APPROVED",
  "rpo_hours": 6,
  "rto_hours": 4
}
```

O campo `status` deve permanecer `PENDENTE` enquanto os tempos não tiverem sido medidos e aprovados.

## 9. Rollback da política

Alterar os objetivos exige nova versão deste documento e aprovação dos três responsáveis. Reduzir a exigência de continuidade não pode ocorrer apenas por mudança de configuração ou edição do manifesto de uma release.
