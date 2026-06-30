#!/usr/bin/env python3
# ── seeds/seed_all.py ────────────────────────────────────────────────────────
# Seed inicial do EJC: usuário admin, feriados 2026-2030 (fixos + móveis),
# súmulas-chave STF/STJ/TST para a base de conhecimento RAG.
#
# Uso (dentro do container backend):
#   python seeds/seed_all.py
#
# Idempotente: pode rodar várias vezes sem duplicar.
# ─────────────────────────────────────────────────────────────────────────────
import asyncio
import os
import sys
from datetime import date, timedelta
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.user import User, UserRole
from app.models.feriado import Feriado
from app.models.rag import KnowledgeDoc, KnowledgeChunk
from app.services.deadline_calculator import calcular_pascoa, FERIADOS_FIXOS

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@depaulateixeira.adv.br")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "TrocarSenha@2026")


NOMES_FIXOS = {
    (1, 1): "Confraternização Universal", (21, 4): "Tiradentes",
    (1, 5): "Dia do Trabalho", (7, 9): "Independência",
    (12, 10): "N. Sra. Aparecida", (2, 11): "Finados",
    (15, 11): "Proclamação da República", (20, 11): "Consciência Negra",
    (25, 12): "Natal",
}

# Feriados MUNICIPAIS de Betim/MG — datas fixas verificadas em fonte oficial
# (Prefeitura de Betim; Dia da Padroeira instituído pela Lei mun. 4.731/2008).
# Entram no cálculo de prazos como dia NÃO útil no município.
#
# ⚠️ Minas Gerais NÃO possui feriado estadual pago de observância geral distinto
# dos nacionais — por isso não há entradas "estaduais" aqui. Se uma lei estadual
# for confirmada, acrescente em FERIADOS_ESTADUAIS_MG no mesmo formato.
# ⚠️ Suspensões processuais por tribunal (TJMG/TRT3) seguem portarias próprias e
# NÃO devem ser semeadas aqui.
FERIADOS_BETIM = {
    (16, 7):  "N. Sra. do Carmo — padroeira de Betim (Lei mun. 4.731/2008)",
    (17, 12): "Aniversário de Betim (emancipação política)",
}
FERIADOS_ESTADUAIS_MG: dict[tuple[int, int], str] = {}  # confirmar por lei antes de preencher

# Súmulas-chave (amostra inicial — script ingest completa via APIs)
SUMULAS_SEED = [
    # STJ
    ("STJ", "Súmula 297", "O Código de Defesa do Consumidor é aplicável às instituições financeiras."),
    ("STJ", "Súmula 385", "Da anotação irregular em cadastro de proteção ao crédito, não cabe indenização por dano moral, quando preexistente legítima inscrição, ressalvado o direito ao cancelamento."),
    ("STJ", "Súmula 479", "As instituições financeiras respondem objetivamente pelos danos gerados por fortuito interno relativo a fraudes e delitos praticados por terceiros no âmbito de operações bancárias."),
    ("STJ", "Súmula 54", "Os juros moratórios fluem a partir do evento danoso, em caso de responsabilidade extracontratual."),
    ("STJ", "Súmula 362", "A correção monetária do valor da indenização do dano moral incide desde a data do arbitramento."),
    ("STJ", "Súmula 7", "A pretensão de simples reexame de prova não enseja recurso especial."),
    ("STJ", "Súmula 613", "Não se admite a aplicação da teoria do fato consumado em tema de Direito Ambiental."),
    ("STJ", "Súmula 618", "A inversão do ônus da prova aplica-se às ações de degradação ambiental."),
    ("STJ", "Súmula 623", "As obrigações ambientais possuem natureza propter rem, sendo admissível cobrá-las do proprietário ou possuidor atual e/ou dos anteriores, à escolha do credor."),
    ("STJ", "Súmula 629", "Quanto ao dano ambiental, é admitida a condenação do réu à obrigação de fazer ou à de não fazer cumulada com a de indenizar."),
    # STF
    ("STF", "Súmula Vinculante 25", "É ilícita a prisão civil de depositário infiel, qualquer que seja a modalidade do depósito."),
    ("STF", "Súmula Vinculante 37", "Não cabe ao Poder Judiciário, que não tem função legislativa, aumentar vencimentos de servidores públicos sob o fundamento de isonomia."),
    ("STF", "Súmula 473", "A administração pode anular seus próprios atos, quando eivados de vícios que os tornam ilegais, porque deles não se originam direitos; ou revogá-los, por motivo de conveniência ou oportunidade, respeitados os direitos adquiridos, e ressalvada, em todos os casos, a apreciação judicial."),
    # TST
    ("TST", "Súmula 338", "É ônus do empregador que conta com mais de 10 empregados o registro da jornada de trabalho na forma do art. 74, § 2º, da CLT. A não apresentação injustificada dos controles de frequência gera presunção relativa de veracidade da jornada de trabalho alegada na inicial."),
    ("TST", "Súmula 437", "Após a edição da Lei nº 8.923/94, a não concessão ou a concessão parcial do intervalo intrajornada mínimo, para repouso e alimentação, a empregados urbanos e rurais, implica o pagamento total do período correspondente, e não apenas daquele suprimido."),
    ("TST", "Súmula 443", "Presume-se discriminatória a despedida de empregado portador do vírus HIV ou de outra doença grave que suscite estigma ou preconceito. Inválido o ato, o empregado tem direito à reintegração no emprego."),
    ("TST", "Súmula 90", "O tempo despendido pelo empregado, em condução fornecida pelo empregador, até o local de trabalho de difícil acesso, ou não servido por transporte público regular, e para o seu retorno é computável na jornada de trabalho."),
    ("TST", "Súmula 6", "Para os fins previstos no § 2º do art. 461 da CLT, só é válido o quadro de pessoal organizado em carreira quando homologado pelo Ministério do Trabalho."),
]


async def seed_admin(db):
    exists = (await db.execute(
        select(User).where(User.email == ADMIN_EMAIL)
    )).scalar_one_or_none()
    if exists:
        print(f"  ↷ Admin já existe: {ADMIN_EMAIL}")
        return
    db.add(User(
        id=str(uuid4()), email=ADMIN_EMAIL,
        hashed_password=get_password_hash(ADMIN_PASSWORD),
        full_name="Dr. Clovis José Soares",
        role=UserRole.superadmin,
        oab_number="OAB/MG",
        is_active=True,
        must_change_password=True,   # força troca no 1º login
    ))
    print(f"  ✅ Admin criado: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print(f"     ⚠️  TROQUE A SENHA no primeiro login!")


async def seed_feriados(db):
    count = 0
    for ano in range(2026, 2031):
        # Fixos
        for (dia, mes) in FERIADOS_FIXOS:
            d = date(ano, mes, dia)
            exists = (await db.execute(
                select(Feriado).where(Feriado.data == d)
            )).scalar_one_or_none()
            if not exists:
                db.add(Feriado(
                    id=str(uuid4()), data=d,
                    nome=NOMES_FIXOS.get((dia, mes), "Feriado Nacional"),
                    tipo="nacional", movel=False,
                ))
                count += 1
        # Móveis (Páscoa via Gauss)
        pascoa = calcular_pascoa(ano)
        moveis = [
            (pascoa - timedelta(days=48), "Segunda de Carnaval"),
            (pascoa - timedelta(days=47), "Terça de Carnaval"),
            (pascoa - timedelta(days=2),  "Sexta-feira Santa"),
            (pascoa + timedelta(days=60), "Corpus Christi"),
        ]
        for d, nome in moveis:
            exists = (await db.execute(
                select(Feriado).where(Feriado.data == d)
            )).scalar_one_or_none()
            if not exists:
                db.add(Feriado(
                    id=str(uuid4()), data=d, nome=nome,
                    tipo="nacional", movel=True,
                ))
                count += 1
        # Municipais Betim (+ estaduais MG, se confirmados)
        for fonte, tp in ((FERIADOS_BETIM, "municipal"),
                           (FERIADOS_ESTADUAIS_MG, "estadual")):
            for (dia, mes), nome in fonte.items():
                d = date(ano, mes, dia)
                exists = (await db.execute(
                    select(Feriado).where(Feriado.data == d)
                )).scalar_one_or_none()
                if not exists:
                    db.add(Feriado(
                        id=str(uuid4()), data=d, nome=nome,
                        tipo=tp, movel=False,
                    ))
                    count += 1
    print(f"  ✅ Feriados 2026-2030: {count} inseridos")


async def seed_sumulas(db):
    count = 0
    for tribunal, numero, texto_sumula in SUMULAS_SEED:
        titulo = f"{tribunal} — {numero}"
        exists = (await db.execute(
            select(KnowledgeDoc).where(KnowledgeDoc.titulo == titulo)
        )).scalar_one_or_none()
        if exists:
            continue
        categoria = f"sumula_{tribunal.lower()}"
        doc = KnowledgeDoc(
            id=str(uuid4()), titulo=titulo, categoria=categoria,
            tribunal=tribunal,
            fonte=f"https://www.{tribunal.lower()}.jus.br",
        )
        db.add(doc)
        await db.flush()   # garante doc inserido antes do chunk (FK)
        db.add(KnowledgeChunk(
            id=str(uuid4()), doc_id=doc.id, chunk_index=0,
            conteudo=f"{titulo}: {texto_sumula}",
        ))
        count += 1
    print(f"  ✅ Súmulas-chave: {count} inseridas na base RAG")


TEMPLATES_SEED = [
    ("Procuração Ad Judicia", "procuracao", None, """# PROCURAÇÃO AD JUDICIA

**OUTORGANTE:** {{cliente_nome}}, CPF/CNPJ {{cliente_cpf_cnpj}}, residente/sediado em {{cliente_endereco}}.

**OUTORGADO:** {{advogado_nome}}, {{advogado_oab}}, com escritório em Betim/MG.

**PODERES:** Pelo presente instrumento, o outorgante nomeia o outorgado seu procurador, conferindo-lhe os poderes da cláusula *ad judicia* (CPC, art. 105), para o foro em geral, podendo propor ações, contestar, recorrer, transigir, firmar compromissos, receber e dar quitação, substabelecer com ou sem reserva de poderes.

{{comarca}}, {{data_hoje}}.

___________________________________
{{cliente_nome}}"""),

    ("Notificação Extrajudicial — Cobrança", "notificacao_extrajudicial", "civil", """# NOTIFICAÇÃO EXTRAJUDICIAL

**NOTIFICANTE:** {{cliente_nome}}, CPF/CNPJ {{cliente_cpf_cnpj}}.

**NOTIFICADO:** {{parte_contraria}}.

Pela presente, fica V.Sa. **NOTIFICADO(A)** acerca do débito em aberto no valor de {{valor_causa}}, concedendo-se o prazo de **5 (cinco) dias úteis** para quitação, sob pena das medidas judiciais cabíveis, acrescidas de juros, correção monetária, custas e honorários advocatícios.

O pagamento poderá ser tratado diretamente com este escritório.

{{comarca}}, {{data_hoje}}.

{{advogado_nome}} — {{advogado_oab}}"""),

    ("Contestação — Estrutura Base", "contestacao", None, """# CONTESTAÇÃO

**EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO DA {{vara}} DA COMARCA DE {{comarca}}**

Processo nº {{numero_processo}}

**{{cliente_nome}}**, já qualificado(a), por seu advogado, nos autos da ação que lhe move **{{parte_contraria}}**, vem, tempestivamente, apresentar **CONTESTAÇÃO**, pelos fatos e fundamentos a seguir.

## I — PRELIMINARES
*(analisar: incompetência, ilegitimidade, inépcia, conexão)*

## II — DO MÉRITO
*(impugnação específica dos fatos — CPC art. 341)*

## III — DOS PEDIDOS
Ante o exposto, requer:
a) o acolhimento das preliminares;
b) no mérito, a improcedência total dos pedidos;
c) a condenação do autor em custas e honorários.

Protesta por todas as provas em direito admitidas.

{{comarca}}, {{data_hoje}}.

{{advogado_nome}} — {{advogado_oab}}"""),
]


async def seed_templates(db):
    from app.models.template import DocTemplate
    count = 0
    for titulo, tipo, area, conteudo in TEMPLATES_SEED:
        exists = (await db.execute(
            select(DocTemplate).where(DocTemplate.titulo == titulo)
        )).scalar_one_or_none()
        if exists:
            continue
        db.add(DocTemplate(
            id=str(uuid4()), titulo=titulo, tipo_peca=tipo,
            area=area, conteudo=conteudo, ativo=True,
        ))
        count += 1
    print(f"  ✅ Templates de peças: {count} inseridos")


async def main():
    print("═══ EJC v3.0 — Seed Inicial ═══")
    async with AsyncSessionLocal() as db:
        await seed_admin(db)
        await seed_feriados(db)
        await seed_sumulas(db)
        await seed_templates(db)
        await db.commit()
    print("═══ Seed concluído ═══")


if __name__ == "__main__":
    asyncio.run(main())
