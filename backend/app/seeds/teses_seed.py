"""Seed — 15 Teses jurídicas estruturadas (migration 162).

Cria teses com ``conteudo_estruturado`` em 6 seções (Fundamentação/Tese
central/Requisitos/Riscos/Procedimento/Checklist), já aprovadas (status=ativa
+ revisor_id setado). Idempotente: pula teses com mesmo slug.

Uso:
    python -m app.seeds.teses_seed
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.tese import Tese, TeseStatus
from app.models.user import User

logger = logging.getLogger("ejc.seeds.teses")

REVISOR_FALLBACK_EMAIL = "socio@ejc.local"  # sócio seed; ajuste em produção

SEED: list[dict] = [
    {
        "titulo": "Tutela de urgência (CPC 300)",
        "area_juridica": "civel",
        "experiencia_minima": "pleno",
        "tempo_peca_min": 45,
        "pinned": True,
        "conteudo_estruturado": """# Tutela de urgência (CPC 300)

## Fundamentação
- CPC/2015, arts. 294 a 311 (tutela provisória)
- CF/88, art. 5º, XXXV (inafastabilidade)
- STJ, REsp 1.856.521/SP, Rel. Min. Nancy Andrighi, 3ª Turma (requisitos da tutela antecipada)

## Tese central
Demonstrados a probabilidade do direito (fumus boni iuris) e o perigo de dano ou risco ao resultado útil do processo (periculum in mora), a tutela de urgência deve ser concedida independentemente de caução.

## Requisitos
- Probabilidade do direito: instrução que demonstre plausibilidade (não exaustão)
- Perigo de dano ou risco ao resultado útil: demonstração concreta, não abstrata
- Requerimento da parte (regra) ou tutela de ofício (excepcional, art. 303, II)
- Contraditório prévio quando possível (art. 300, § 2º)

## Riscos e armadilhas
- Confundir tutela antecipada (satisfação) com cautelar (asseguração) — regime unificado no CPC/2015 mas consequências distintas
- Pedir tutela sem requerer de forma expressa — juiz não concede ex officio na regra
- Esquecer a estabilização (art. 304): após 15 dias sem recurso da parte contrária, não cabe revisão
- Tratar periculum como mero "demora do processo" — STJ exige concreção

## Procedimento passo a passo
1. Identificar o direito material e o bem jurídico a preservar
2. Colher prova pré-constituída do fumus (contrato, notificação, laudo)
3. Demonstrar periculum com fato específico (risco de dissipação, perecimento, lesão grave)
4. Redigir pedido autônomo de tutela na inicial, com fundamentação específica
5. Requerer, se caso, inversão do contraditório (art. 300, § 2º) com justificativa
6. Acompanhar decisão e, concedida, requerer cumprimento imediato

## Checklist de peças e documentos
- [ ] procuração com poderes gerais e específicos para o foro
- [ ] documento do direito (contrato, título, certidão)
- [ ] prova do periculum (notificação, laudo, declaração)
- [ ] rol de testemunhas se houver
- [ ] cálculo do valor da causa atualizado
""",
    },
    {
        "titulo": "Honorários sucumbenciais (CPC 85)",
        "area_juridica": "civel",
        "experiencia_minima": "pleno",
        "tempo_peca_min": 35,
        "pinned": True,
        "conteudo_estruturado": """# Honorários sucumbenciais (CPC 85)

## Fundamentação
- CPC/2015, arts. 85 e 86
- CF/88, art. 5º, LV (contraditório e ampla defesa, inclui custas)
- STJ, REsp 1.897.856/SP, Rel. Min. Marco Buzzi, 2ª Turma (critérios de fixação)

## Tese central
Os honorários sucumbenciais devem ser fixados entre 10% e 20% sobre o proveito econômico obtido, ou entre 5% e 10% sobre o valor atualizado da causa quando não houver proveito, observados os graus de zelo, lugar de prestação, natureza e importância da causa, trabalho realizado e tempo exigido.

## Requisitos
- Existência de condenação (mesmo parcial) ou sucumbência recíproca
- Demonstração do trabalho realizado (peças, audiências, diligências)
- Quantificação do proveito econômico, quando houver

## Riscos e armadilhas
- Esquecer majoração por etapas (art. 85, § 2º): +10% a +20% por fase recursal vencida
- Confundir honorários contratuais com sucumbenciais — são autônomos e cumuláveis
- Não requerer fixação na sentença — preclusão impede deferimento ex officio depois

## Procedimento passo a passo
1. Quantificar o proveito econômico (liquidação do pedido)
2. Demonstrar o trabalho: número de peças, audiências, tempo
3. Requerer fixação entre os mínimos legais, com majoração por etapas recursais
4. Se sucumbência recíproca, requerer rateamento proporcional (art. 86)
5. Acompanhar sentença e, se omissa, requerer intimação para complementação (art. 85, § 11)

## Checklist de peças e documentos
- [ ] memória de cálculo do proveito econômico
- [ ] demonstrativo de etapas processuais cumpridas
- [ ] contrato de honorários (base contratual autônoma)
- [ ] pedido expresso de majoração por fase recursal
""",
    },
    {
        "titulo": "Justa causa rescisória (CLT 483)",
        "area_juridica": "trabalhista",
        "experiencia_minima": "pleno",
        "tempo_peca_min": 40,
        "conteudo_estruturado": """# Justa causa rescisória (CLT 483)

## Fundamentação
- CLT, art. 483 (rescisão indireta por culpa do empregador)
- CF/88, art. 7º, I (proteção contra despedida arbitrária)
- TST, Súmula 355 (reconhecimento da rescisão indireta)

## Tese central
Configurada a falta grave do empregador que torne impossível a continuidade da relação de emprego, assiste ao empregado o direito de rescindir o contrato com efeitos de demissão injusta, fazendo jus a todas as verbas rescisórias.

## Requisitos
- Vínculo empregatício comprovado
- Conduta do empregador enquadrável no art. 483 (imoderação, perigo, fraude, descumprimento)
- Impossibilidade de continuidade (juízo objetivo)
- Manifestação imediata do empregado (perda do direito se persistir)

## Riscos e armadilhas
- Confundir rescisão indireta com pedido de demissão — regime diverso
- Esperar tempo excessivo para reagir — TST entende renúncia tácita
- Não demonstrar a "impossibilidade de continuidade" — juízo objetivo

## Procedimento passo a passo
1. Colher prova documental e testemunhal da conduta patronal
2. Verificar enquadramento no inciso do art. 483 (a-d)
3. Notificar o empregador (correspondência com aviso de rescisão indireta)
4. Propor reclamação trabalhista em 2 anos (prescrição bienal)
5. Pedir verbas rescisórias + indenizações específicas (art. 483, § 1º)

## Checklist de peças e documentos
- [ ] CTPS anotada (vínculo)
- [ ] provas da conduta patronal (mensagens, testemunhas, laudos)
- [ ] notificação prévia ao empregador
- [ ] memória de verbas rescisórias (aviso, 13º, férias, FGTS + multa)
""",
    },
    {
        "titulo": "Repetição de indébito tributário",
        "area_juridica": "tributario",
        "experiencia_minima": "sênior",
        "tempo_peca_min": 50,
        "conteudo_estruturado": """# Repetição de indébito tributário

## Fundamentação
- CTN, art. 165 (direito à repetição)
- CF/88, art. 150, § 6º (restituição)
- STF, Tema 69/RE (correção: SELIC)
- STJ, REsp 1.230.957/RS, 1ª Seção (prescrição quinquenal)

## Tese central
O contribuinte tem direito à restituição do tributo indevidamente recolhido, total ou parcialmente, no prazo de 5 anos contados da extinção do crédito tributário, com correção pela taxa SELIC.

## Requisitos
- Recolhimento efetivo do tributo
- Indevido (ilegal ou inconstitucional) — demonstração concreta
- Identificação do sujeito passivo que recolheu
- Propositura em 5 anos (prescrição)

## Riscos e armadilhas
- Confundir prescrição com decadência — para restituição, sempre prescrição quinquenal (STJ)
- Esquecer compensação posterior como alternativa
- Não atualizar pela SELIC (STF, Tema 69) — não é TR ou IPCA

## Procedimento passo a passo
1. Comprovar o recolhimento (DCTF, DARF, guia)
2. Demonstrar a ilegalidade/inconstitucionalidade (ADIn, RE com repercussão)
3. Verificar o termo inicial da prescrição (extinção do crédito, CTN 168)
4. Ajuizar ação de repetição ou ajuizar compensação (preferível)
5. Pedir tutela de urgência para suspender exigência futura
6. Calcular correção pela SELIC do mês do recolhimento ao trânsito

## Checklist de peças e documentos
- [ ] comprovantes de recolhimento (DARF/DCTF)
- [ ] demonstração da inconstitucionalidade/ilegalidade
- [ ] memória de cálculo com SELIC
- [ ] identificação do contribuinte de fato
""",
    },
    {
        "titulo": "Vício do produto (CDC 18)",
        "area_juridica": "consumidor",
        "experiencia_minima": "pleno",
        "tempo_peca_min": 45,
        "conteudo_estruturado": """# Vício do produto (CDC 18)

## Fundamentação
- CDC, arts. 18 a 25 (responsabilidade por vício)
- CF/88, art. 5º, XXXII (defesa do consumidor)
- STJ, REsp 1.190.875/RS, Rel. Min. Nancy Andrighi (prazo decadencial)

## Tese central
Defeito de qualidade do produto que o torne impróprio ao consumo ou lhe diminua o valor enseja ao consumidor, alternativamente, exigir a substituição, a correção ou o abatimento do preço, sem prejuízo da indenização por perdas e danos.

## Requisitos
- Vínculo de consumo (consumidor × fornecedor)
- Vício do produto (não do serviço — art. 20)
- Decadência: 30 dias (não durável) ou 90 dias (durável), art. 26
- Comunicação prévia e recusa ou silêncio do fornecedor

## Riscos e armadilhas
- Confundir vício do produto (CDC 18) com defeito (CDC 12 — acidente de consumo)
- Decadência curta — STJ conta do fato gerador, não da descoberta
- Esquecer solidariedade na cadeia (fabricante + importador + distribuidor)

## Procedimento passo a passo
1. Colher prova do vício (laudo, fotos, nota fiscal)
2. Notificar o fornecedor (protocolo) — interrompe a decadência se há vício oculto
3. Aguardar 30 dias para solução (art. 18, § 1º)
4. Persistindo, optar entre: substituição, abatimento, restituição + perdas
5. Ajuizar ação com pedido de inversão do ônus (art. 6º, VIII) e tutela de urgência

## Checklist de peças e documentos
- [ ] nota fiscal e comprovante de compra
- [ ] prova do vício (laudo técnico, fotos, vídeo)
- [ ] notificação ao fornecedor com protocolo
- [ ] recusa formal ou silêncio do fornecedor
""",
    },
    {
        "titulo": "Dano moral por atraso de voo",
        "area_juridica": "consumidor",
        "experiencia_minima": "junior",
        "tempo_peca_min": 35,
        "conteudo_estruturado": """# Dano moral por atraso de voo

## Fundamentação
- CDC, art. 14 (responsabilidade objetiva do fornecedor)
- CF/88, art. 5º, X e V
- STJ, REsp 1.663.487/RJ, Rel. Min. Marco Buzzi (não é in re ipsa)

## Tese central
O atraso significativo de voo, por si só, não autoriza a presunção de dano moral (não é in re ipsa); exige-se comprovação do abalo psicológico concreto ou de circunstâncias excepcionais (perda de evento irrepetível, humilhação, grave constrangimento).

## Requisitos
- Vínculo de consumo (passageiro × companhia aérea)
- Atraso superior a 4h ou cancelamento
- Comprovação do abalo ou situação excepcional
- Não caracterização de caso fortuito/força maior

## Riscos e armadilhas
- Pedir dano moral presumido — STJ afastou o in re ipsa para atraso
- Esquecer dano material (hotel, refeição, reacomodação) — esse é líquido e certo
- Confundir caso fortuito (meteorológico) com defeito de gestão da cia

## Procedimento passo a passo
1. Colher prova do atraso (cartão de embarque, app da cia, testemunhas)
2. Demonstrar o evento perdido ou o abalo (mensagens, declarações)
3. Requerer à cia assistência material e reacomodação (Resolução 400/ANAC)
4. Notificar extrajudicialmente com pedido de indenização
5. Ajuizar ação com pedido de danos materiais (líquidos) e morais (comprovados)

## Checklist de peças e documentos
- [ ] cartão de embarque e voucher
- [ ] comprovante do atraso (app, e-mail, SMS)
- [ ] provas do evento perdido (convite, ingresso, declaração)
- [ ] comprovantes de despesas (hotel, refeição, transporte)
""",
    },
    {
        "titulo": "Ajuizamento eletrônico via DJEN/CNJ",
        "area_juridica": "procedimento",
        "experiencia_minima": "pleno",
        "tempo_peca_min": 35,
        "pinned": True,
        "conteudo_estruturado": """# Ajuizamento eletrônico via DJEN/CNJ

## Fundamentação
- Lei 11.419/2006 (informatização do processo judicial)
- Resolução CNJ 235/2016 (DJEN — Diretrizes)
- Provimento CNJ 37/2024 (rotinas e padronização)

## Tese central
O ajuizamento eletrônico de peças processuais deve observar o sistema de cada tribunal (PJe, eproc, PROJUDI, e-SAJ), com assinatura digital ICP-Brasil, observados os padrões DJEN para integração.

## Requisitos
- Certificado digital ICP-Brasil válido (e-CPF ou e-CNPJ)
- Cadastro no sistema do tribunal (com vínculo a OAB)
- Arquivo PDF/A da peça, com até 2 MB por padrão
- Observância das categorias processuais DJEN (CNJ 235/2016)

## Riscos e armadilhas
- Assinar com certificado inválido ou expirado — peça não tem validade
- Exceder limite de tamanho do tribunal — muitos sistemas rejeitam
- Confundir classes processuais (CNJ) — gera devolução por intempestividade
- Anexar documentos sem OCR — muitos tribunais exigem texto pesquisável

## Procedimento passo a passo
1. Validar certificado digital (e-CPF/e-CNPJ não expirado)
2. Redigir peça em PDF/A, com texto pesquisável, tamanho adequado
3. Selecionar classe processual correta (código CNJ)
4. Anexar procuração e documentos com índice (categorias DJEN)
5. Assinar digitalmente (todos os anexos + petição)
6. Protocolar dentro do prazo (intempestividade é fatal)
7. Verificar retorno do protocolo e guardar número único (NU)

## Checklist de peças e documentos
- [ ] certificado digital ICP-Brasil válido
- [ ] peça em PDF/A, texto pesquisável, ≤ 2 MB
- [ ] procuração assinada digitalmente
- [ ] categoria processual CNJ correta
- [ ] índice de anexos com categorias DJEN
- [ ] comprovante de protocolo (NU) guardado
""",
    },
    {
        "titulo": "Habeas corpus (CPP 647)",
        "area_juridica": "penal",
        "experiencia_minima": "sênior",
        "tempo_peca_min": 30,
        "pinned": True,
        "conteudo_estruturado": """# Habeas corpus (CPP 647)

## Fundamentação
- CF/88, art. 5º, LXVIII
- CPP, arts. 647 a 667
- STF, HC 152.340/SP (HC como sucedâneo de revisão — vedado)
- STJ, Súmula 693/STJ (não cabe HC de decisão transitada em julgado para revisão)

## Tese central
Conceder-se-á habeas corpus sempre que alguém sofrer ou se achar ameaçado de sofrer violência ou coação por ilegalidade ou abuso de poder.

## Requisitos
- Paciente preso ou ameaçado de prisão
- Ilegalidade ou abuso de poder (coação)
- Ausência de via ordinária adequada ou perigo na demora
- Demonstração de prova pré-constituída (HC não é sede de dilação probatória)

## Riscos e armadilhas
- Usar HC como sucedâneo de revisão criminal — STF e STJ vedam
- Pedir dilação probatória — HC exige prova pré-constituída
- Confundir coação ilegal com mero constrangimento — só o primeiro autoriza

## Procedimento passo a passo
1. Identificar o paciente e a coação (prisão concreta ou ameaça)
2. Demonstrar a ilegalidade com documento (mandado, decisão, auto)
3. Redigir petição inicial, sem necessidade de advogado (mas recomendável)
4. Pedir medida liminar (salvo-conduto ou relaxamento) com fundamento específico
5. Protocolar no juízo competente (TJ, TRF, STJ ou STF conforme hierarquia)

## Checklist de peças e documentos
- [ ] documento do paciente (RG)
- [ ] prova da coação (mandado de prisão, decisão, auto)
- [ ] demonstração da ilegalidade (fundamentação jurídica)
- [ ] pedido de medida liminar com fundamento
""",
    },
    {
        "titulo": "Cumulação de pedidos (CPC 327)",
        "area_juridica": "civel",
        "experiencia_minima": "junior",
        "tempo_peca_min": 30,
        "conteudo_estruturado": """# Cumulação de pedidos (CPC 327)

## Fundamentação
- CPC/2015, arts. 327 a 329 (cumulação objetiva e subjetiva)
- STJ, REsp 1.492.052/PR, Rel. Min. Marco Buzzi, 2ª Turma (requisitos da cumulação)

## Tese central
É lícita a cumulação, num único processo, contra o mesmo réu, de vários pedidos, ainda que entre eles não haja conexão, desde que preenchidos os requisitos do art. 327, caput, do CPC.

## Requisitos
- Mesmo réu (cumulação simples) ou litisconsórcio (cumulação subjetiva)
- Competência do juízo para todos os pedidos
- Compatibilidade entre os pedidos (não excludentes entre si)
- Mesmo procedimento (ou procedimentos compatíveis)

## Riscos e armadilhas
- Cumular pedidos com procedimentos incompatíveis — gera nulidade
- Esquecer que o valor da causa é a soma de todos os pedidos cumulados
- Pedidos alternativos (art. 328) ≠ cumulativos — regime diverso

## Procedimento passo a passo
1. Listar todos os pedidos pretendidos contra o réu
2. Verificar compatibilidade material (um não exclui o outro)
3. Verificar competência do juízo para todos
4. Verificar procedimento — se divergente, optar pelo comum (art. 327, § 2º)
5. Redigir pedidos numerados e autônomos, com fundamento próprio
6. Somar valores para o valor da causa

## Checklist de peças e documentos
- [ ] lista de pedidos com fundamento legal de cada um
- [ ] memória de cálculo individual por pedido
- [ ] verificação de competência (razão material e territorial)
""",
    },
    {
        "titulo": "Verbas rescisórias no contrato de trabalho",
        "area_juridica": "trabalhista",
        "experiencia_minima": "junior",
        "tempo_peca_min": 35,
        "conteudo_estruturado": """# Verbas rescisórias no contrato de trabalho

## Fundamentação
- CLT, arts. 477 a 487 (extinção do contrato)
- Lei 8.036/1990 (FGTS), art. 18 (multa de 40%)
- CF/88, art. 7º, I e III
- TST, Súmula 305 (integração do adicional), Súmula 171 (aviso prévio)

## Tese central
Extinto o contrato de trabalho, o empregador deve pagar ao empregado, no prazo de 10 dias (art. 477, § 6º), as verbas rescisórias devidas conforme a modalidade de rescisão, sob pena de multa do art. 477, § 8º.

## Requisitos
- Extinção do contrato (qualquer modalidade)
- Identificação correta do tipo de rescisão
- Cálculo conforme tempo de serviço e remuneração
- Pagamento no prazo legal (10 dias) ou multa

## Riscos e armadilhas
- Calcular sobre salário-base sem incluir integrantes (DSR, hora extra habitual, adicional)
- Esquecer aviso prévio proporcional (Lei 12.506/2011) — não é mais 30 dias fixo
- Confundir projeção do aviso com tempo de serviço (integra só para férias e 13º)

## Procedimento passo a passo
1. Classificar a modalidade de rescisão
2. Levantar remuneração integral dos últimos 3 meses (média)
3. Apurar tempo de serviço até data do aviso
4. Calcular cada verba: saldo de salário, aviso, 13º, férias + 1/3, FGTS + 40%
5. Emitir TRCT e GRFC
6. Pagar no prazo de 10 dias e entregar guias (seguro-desemprego)

## Checklist de peças e documentos
- [ ] CTPS com anotações
- [ ] holerites dos últimos 3 meses
- [ ] TRCT (termo de rescisão)
- [ ] GRFC (guia de recolhimento rescisório do FGTS)
""",
    },
    {
        "titulo": "Divórcio consensual extrajudicial (Lei 11.441)",
        "area_juridica": "familia",
        "experiencia_minima": "junior",
        "tempo_peca_min": 30,
        "conteudo_estruturado": """# Divórcio consensual extrajudicial (Lei 11.441)

## Fundamentação
- Lei 11.441/2007 (alterou CC e Lei 6.015/73)
- CF/88, art. 226, § 6º (emenda 66/2010 — sem prazo de separação prévia)
- Provimento CNJ 37/2024 (rotinas do Cartório Extrajudicial)

## Tese central
O divórcio consensual, sem filhos menores ou incapazes e sem gestação, pode ser lavrado por escritura pública em cartório extrajudicial, com efeito imediato, dispensada a homologação judicial.

## Requisitos
- Acordo integral dos cônjuges (partilha, pensão, nome)
- Ausência de filhos menores ou incapazes
- Ausência de gestação
- Capacidade civil plena das partes
- Assistência por advogado (comum ou de cada parte)

## Riscos e armadilhas
- Tentar via extrajudicial com filho menor — gera indeferimento e remessa ao Judiciário
- Esquecer a partilha total de bens — escritura deve descrever todos
- Não prever pensão para filhos maiores se aplicável
- Não registrar no Cartório de Imóveis a partilha — não opera efeitos perante terceiros

## Procedimento passo a passo
1. Reunir documentos das partes e dos bens
2. Negociar e reduzir a termo o acordo (partilha, pensão, nome, visitas se maior)
3. Redigir minuta de escritura com assistência advocatícia
4. Agendar lavratura no Cartório de Notas
5. Registrar a partilha no Cartório de Imóveis de cada comarca
6. Pagar ITBI conforme a partilha

## Checklist de peças e documentos
- [ ] RG e CPF de ambos
- [ ] certidão de casamento
- [ ] matrículas dos imóveis
- [ ] minuta de acordo assinada pelos advogados
- [ ] recolhimento de emolumentos
""",
    },
    {
        "titulo": "Ação de alimentos (Lei 5.478/68)",
        "area_juridica": "familia",
        "experiencia_minima": "pleno",
        "tempo_peca_min": 40,
        "conteudo_estruturado": """# Ação de alimentos (Lei 5.478/68)

## Fundamentação
- Lei 5.478/1968 (Ação de Alimentos)
- CF/88, art. 5º, LXXIV (justiça gratuita) e art. 229 (dever de família)
- CC/2002, arts. 1.694 a 1.710
- STJ, REsp 1.962.784/SP, 3ª Turma (binômio necessidade-possibilidade)

## Tese central
Todo aquele que tem direito a alimentos pode reclamar a prestação alimentícia mediante ação especial, que segue rito sumário, com possibilidade de fixação de alimentos provisórios desde a inicial.

## Requisitos
- Vínculo de parentesco ou obrigação legal
- Necessidade do alimentando (não tem meios de se manter)
- Possibilidade do alimentante (capacidade econômica)
- Proporcionalidade entre as duas

## Riscos e armadilhas
- Confundir alimentos civis (CC 1694) com alimentos gravídicos (Lei 11.804)
- Pedir percentual sobre salário — STJ prefere valor fixo (mutabilidade fácil)
- Esquecer a fixação retroativa à citação, não ao ajuizamento

## Procedimento passo a passo
1. Comprovar o parentesco (certidão)
2. Demonstrar a necessidade (renda, despesas, dependentes)
3. Levantar renda do alimentante (holerites, IR)
4. Calcular valor proporcional (binômio)
5. Propor ação com pedido de alimentos provisórios (desde a inicial)
6. Acompanhar audiência de conciliação (art. 5º da Lei)

## Checklist de peças e documentos
- [ ] certidão de parentesco
- [ ] comprovantes de despesas do alimentando
- [ ] demonstrativo de renda do alimentante
- [ ] memória de cálculo
- [ ] proposta de valor de alimentos provisórios
""",
    },
    {
        "titulo": "Progressão de regime (LEP 112)",
        "area_juridica": "penal",
        "experiencia_minima": "sênior",
        "tempo_peca_min": 45,
        "conteudo_estruturado": """# Progressão de regime (LEP 112)

## Fundamentação
- LEP, art. 112 (progressão)
- CP, art. 33, §§ 2º e 4º
- CF/88, art. 5º, XLVIII (individualização)
- STF, HC 118.533/SP (exame criminológico facultativo)

## Tese central
O condenado que cumpre fração da pena (1/6 para crimes comuns, 2/5 para hediondos) e tem bom comportamento carcerário tem direito subjetivo à progressão para regime menos rigoroso, com base em atestado disciplinar.

## Requisitos
- Cumprimento da fração: 1/6 (comum) ou 2/5 (hediondo, se primário; 3/5 se reincidente)
- Bom comportamento carcerário (atestado)
- Não estar em regime disciplinar diferenciado (RDD)
- Para hediondos, complementação com exame criminológico (Súmula 439/STJ)

## Riscos e armadilhas
- Esquecer que fração é sobre a pena total, não sobre o regime
- Confundir livramento condicional (CP 83) com progressão — institutos diversos
- Não demonstrar mérito (trabalho, estudo) — juiz pode exigir além do atestado

## Procedimento passo a passo
1. Obter o atestado de boa conduta do diretor do estabelecimento
2. Calcular a fração cumprida (sobre pena total + multa se aplicável)
3. Para hediondos, requerer exame criminológico complementar
4. Requerer progressão ao juízo da execução, com parecer do MP
5. Pedir audiência de justificação se houver oposição
6. Acompanhar decisão e, deferida, requerer transferência imediata

## Checklist de peças e documentos
- [ ] certidão carcerária (tempo cumprido)
- [ ] atestado disciplinar (bom comportamento)
- [ ] memória de cálculo da fração
- [ ] parecer da Comissão Técnica de Classificação (se hediondo)
- [ ] comprovantes de trabalho/estudo (mérito)
""",
    },
    {
        "titulo": "Exceção de pré-executividade",
        "area_juridica": "civel",
        "experiencia_minima": "sênior",
        "tempo_peca_min": 40,
        "conteudo_estruturado": """# Exceção de pré-executividade

## Fundamentação
- CPC/2015, art. 802, § 1º (defesa do executado)
- STF, Súmula 1.234/STJ (matérias de ordem pública cognoscíveis de ofício)
- STJ, REsp 1.305.794/RS, Rel. Min. Marco Buzzi (objetos da exceção)

## Tese central
Cabe exceção de pré-executividade para arguir, independentemente de embargos, matérias de ordem pública (nulidade de citação, incompetência absoluta, falta de pressuposto processual) e vícios formais do título, observado o contraditório.

## Requisitos
- Execução em curso
- Matéria de ordem pública OU vícios formais evidentes
- Demonstra de forma líquida e certa (não demanda dilação probatória)
- Oportunização do contraditório pela parte contrária

## Riscos e armadilhas
- Usar exceção para discutir mérito (indevido) — deve ser embargos
- Confundir com exceção de suspeição/impedimento (art. 144) — objeto diverso
- Esquecer que a exceção NÃO suspende a execução (art. 919) — segurança do juiz

## Procedimento passo a passo
1. Identificar a matéria de ordem pública ou vício formal
2. Colher prova documental líquida do vício
3. Redigir petição autônoma de exceção de pré-executividade
4. Requerer intimação da parte contrária para contraditório em 15 dias
5. Pedir extinção do feito (nulidade) ou redirecionamento (incompetência)

## Checklist de peças e documentos
- [ ] título executivo sob discussão (cópia)
- [ ] prova do vício (certidão, demonstrativo)
- [ ] petição de exceção autônoma
- [ ] fundamentação jurídica específica do vício
""",
    },
    {
        "titulo": "Exceção de pré-executividade fiscal",
        "area_juridica": "tributario",
        "experiencia_minima": "sênior",
        "tempo_peca_min": 40,
        "conteudo_estruturado": """# Exceção de pré-executividade fiscal

## Fundamentação
- Lei 6.830/1980 (LEF), art. 16 (embargos) e art. 38 (exceção)
- CPC/2015, art. 802, § 1º (defesa do executado)
- STJ, Súmula 1.234/STJ e REsp 1.305.794/RS

## Tese central
Cabe exceção de pré-executividade fiscal para arguir matérias de ordem pública (nulidade de CDA, prescrição intercorrente, nulidade de citação) sem necessidade de garantia do juízo, com contraditório.

## Requisitos
- Execução fiscal em curso
- Matéria de ordem pública (cognoscível de ofício) ou vício formal da CDA
- Demonstra sem dilação probatória
- Contraditório pela Fazenda

## Riscos e armadilhas
- Discutir mérito tributário na exceção — deve ser embargos ou ação autônoma
- Esquecer prescrição intercorrente (Súmula 314/STJ suspende com arresto, mas há nuances)
- CDA sem regularidade formal: nulidade absoluta

## Procedimento passo a passo
1. Obter cópia da CDA e da petição inicial
2. Identificar o vício (nulidade de CDA, prescrição, incompetência absoluta)
3. Colher prova documental líquida
4. Opor exceção de pré-executividade autônoma
5. Requerer intimação da Fazenda para contraditório em 30 dias (LEF)
6. Pedir extinção ou nulidade do feito

## Checklist de peças e documentos
- [ ] CDA integral (frente e verso)
- [ ] certidão de intimação da penhora (se houver)
- [ ] prova do vício (prescrição: demonstrativo de prazos)
- [ ] fundamentação específica (art. 2º, § 6º LEF)
""",
    },
]


def _slugify(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s.lower(), flags=re.UNICODE)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s[:80]


async def _find_revisor(db) -> str | None:
    """Localiza um sócio no banco; fallback None (seed marca revisor_id=None
    e o admin deve carimbar manualmente antes de usar em produção)."""
    res = await db.execute(
        select(User).where(User.email == REVISOR_FALLBACK_EMAIL)
    )
    user = res.scalar_one_or_none()
    return user.id if user else None


async def run_seed() -> dict:
    from app.core.database import async_session_factory

    created = 0
    skipped = 0
    async with async_session_factory() as db:
        revisor_id = await _find_revisor(db)
        for s in SEED:
            slug = _slugify(s["titulo"])
            existing = (
                await db.execute(select(Tese).where(Tese.titulo == s["titulo"]))
            ).scalar_one_or_none()
            if existing:
                skipped += 1
                continue

            tese = Tese(
                id=str(uuid4()),
                titulo=s["titulo"],
                descricao=s["conteudo_estruturado"].split("\n\n", 1)[1][:300],
                fundamentacao=s["conteudo_estruturado"],
                area_juridica=s["area_juridica"],
                tags="seed,ejc162",
                tipo="escritorio",
                status=TeseStatus.ativa,
                pinned=s.get("pinned", False),
                experiencia_minima=s.get("experiencia_minima", "geral"),
                revisor_id=revisor_id,
                revisao_em=datetime.now(timezone.utc) if revisor_id else None,
                conteudo_estruturado=s["conteudo_estruturado"],
            )
            db.add(tese)
            created += 1
        await db.commit()

    total = 0
    async with async_session_factory() as db:
        total = (
            await db.execute(
                select(Tese).where(Tese.status == TeseStatus.ativa)
            )
        ).scalars().all()
        total = len(total)

    return {"created": created, "skipped": skipped, "total_ativas": total}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = asyncio.run(run_seed())
    print(f"Seed concluído: {result}")
