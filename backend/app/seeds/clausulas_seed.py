"""
EJC — Seed de cláusulas contratuais reutilizáveis.
Insere em doc_templates (tipo_peca='contrato', area='contratos', título "Cláusula — X").
Reusa a biblioteca de peças (Pecas.tsx já lista e gera). Idempotente por título.
Sem migration — blocos de montagem de contrato.

Execução: python -m app.seeds.clausulas_seed
"""
import os
import sys
from uuid import uuid4

# Placeholders renderizados pelo /templates/{id}/gerar: {{comarca}}, {{data_hoje}} etc.
CLAUSULAS = [
    ("Cláusula — Foro de Eleição",
     "CLÁUSULA [N] — DO FORO\nAs partes elegem o foro da Comarca de {{comarca}}, com "
     "renúncia a qualquer outro por mais privilegiado que seja, para dirimir as questões "
     "oriundas do presente contrato."),
    ("Cláusula — Rescisão e Multa",
     "CLÁUSULA [N] — DA RESCISÃO\nO presente contrato poderá ser rescindido por qualquer "
     "das partes mediante notificação prévia de [30] dias. A rescisão imotivada antes do "
     "termo sujeitará a parte à multa de [DESENVOLVER %/valor], sem prejuízo das obrigações "
     "vencidas e das perdas e danos apurados."),
    ("Cláusula — Confidencialidade (NDA)",
     "CLÁUSULA [N] — DA CONFIDENCIALIDADE\nAs partes obrigam-se a manter sigilo sobre todas "
     "as informações confidenciais a que tiverem acesso em razão deste contrato, não as "
     "divulgando a terceiros sem autorização escrita, obrigação que subsiste por [5] anos "
     "após o término, sob pena de responsabilização por perdas e danos."),
    ("Cláusula — Proteção de Dados (LGPD)",
     "CLÁUSULA [N] — DA PROTEÇÃO DE DADOS PESSOAIS\nAs partes comprometem-se a tratar os "
     "dados pessoais estritamente para as finalidades deste contrato, em conformidade com a "
     "Lei 13.709/2018 (LGPD), adotando medidas técnicas e administrativas de segurança e "
     "comunicando incidentes sem demora injustificada. Encerrado o contrato, os dados serão "
     "eliminados ou devolvidos, salvo obrigação legal de retenção."),
    ("Cláusula — Vigência e Renovação",
     "CLÁUSULA [N] — DA VIGÊNCIA\nO presente contrato vigorará pelo prazo de [12] meses, a "
     "contar de {{data_hoje}}, renovando-se automaticamente por iguais períodos caso não haja "
     "manifestação em contrário de qualquer das partes com antecedência mínima de [30] dias."),
    ("Cláusula — Reajuste",
     "CLÁUSULA [N] — DO REAJUSTE\nOs valores serão reajustados anualmente pela variação "
     "acumulada do [IPCA/IGP-M], ou, na sua extinção, por índice oficial que o substitua, "
     "tomando-se por base a data de assinatura."),
    ("Cláusula — Caso Fortuito e Força Maior",
     "CLÁUSULA [N] — DO CASO FORTUITO E FORÇA MAIOR\nNenhuma das partes responderá por "
     "inadimplemento decorrente de caso fortuito ou força maior, nos termos do art. 393 do "
     "Código Civil, devendo comunicar a outra parte de imediato e adotar medidas para mitigar "
     "os efeitos do evento."),
    ("Cláusula — Não Concorrência",
     "CLÁUSULA [N] — DA NÃO CONCORRÊNCIA\nDurante a vigência e pelo prazo de [12] meses após "
     "o término, a parte obriga-se a não exercer, direta ou indiretamente, atividade "
     "concorrente no território de [DESENVOLVER], mediante a contrapartida ajustada, sob pena "
     "da multa prevista neste contrato."),
    ("Cláusula — Cessão e Sucessão",
     "CLÁUSULA [N] — DA CESSÃO\nÉ vedada a cessão ou transferência dos direitos e obrigações "
     "deste contrato a terceiros sem o consentimento prévio e escrito da outra parte. O "
     "presente instrumento obriga as partes e seus sucessores a qualquer título."),
    ("Cláusula — Penalidades por Inadimplemento",
     "CLÁUSULA [N] — DAS PENALIDADES\nO atraso no cumprimento de obrigação pecuniária "
     "sujeitará a parte inadimplente a multa de [2]% sobre o valor em atraso, juros de mora "
     "de [1]% ao mês e correção monetária, sem prejuízo das demais sanções legais e "
     "contratuais."),
    ("Cláusula — Disposições Gerais",
     "CLÁUSULA [N] — DAS DISPOSIÇÕES GERAIS\nA tolerância quanto a eventual descumprimento não "
     "implicará novação ou renúncia. A nulidade de qualquer cláusula não afetará as demais. "
     "Alterações somente terão validade se formalizadas por aditivo escrito e assinado pelas "
     "partes."),
]


def seed():
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    url = os.getenv("DATABASE_URL_SYNC") or os.getenv("DATABASE_URL", "")
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg2")
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://")
    if not url:
        print("❌ DATABASE_URL(_SYNC) não configurada."); sys.exit(1)

    engine = create_engine(url)
    ins = skip = 0
    with Session(engine) as s:
        for titulo, conteudo in CLAUSULAS:
            row = s.execute(
                text("SELECT id FROM doc_templates WHERE titulo=:t AND deleted_at IS NULL"),
                {"t": titulo},
            ).fetchone()
            if row:
                print(f"  ⏭️  Já existe: {titulo}"); skip += 1; continue
            s.execute(text("""
                INSERT INTO doc_templates (id, titulo, tipo_peca, area, descricao, conteudo, ativo)
                VALUES (:id, :titulo, 'contrato', 'contratos', :descricao, :conteudo, true)
            """), {"id": str(uuid4()), "titulo": titulo,
                   "descricao": "Cláusula contratual reutilizável (bloco de montagem).",
                   "conteudo": conteudo + "\n\n[MINUTA — ajustar [N] e colchetes; revisão humana obrigatória.]"})
            print(f"  ✅ Inserida: {titulo}")
            ins += 1
        s.commit()
    print(f"\nCLÁUSULAS SEED: inseridas={ins} ignoradas={skip} total={len(CLAUSULAS)}")


if __name__ == "__main__":
    print("EJC — Cláusulas Seed\n")
    try:
        from dotenv import load_dotenv; load_dotenv()
    except ImportError:
        pass
    seed()
