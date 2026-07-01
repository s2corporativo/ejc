"""
EJC — Seed de checklists processuais por área (ramos faltantes).
Reusa checklist_templates + checklist_template_items. Idempotente por nome.
Os 8 ramos já cobertos (trabalhista/cível/empresarial/admin/tributário/penal/
ambiental/bancário) NÃO são tocados.

Execução: python -m app.seeds.checklists_seed
"""
import os
import sys
from uuid import uuid4

CHECKLISTS = [
    {
        "nome": "Consumidor — Ação Indenizatória",
        "area_juridica": "consumidor",
        "descricao": "Verificação para ação consumerista (CDC).",
        "itens": [
            "Confirmar relação de consumo (CDC arts. 2º e 3º)",
            "Verificar prazo: decadência (vício, art. 26) ou prescrição (fato, art. 27)",
            "Reunir comprovante de compra/contratação e do pagamento",
            "Obter protocolo de reclamação (SAC / PROCON / consumidor.gov.br)",
            "Documentar o vício/defeito ou a cobrança indevida",
            "Avaliar cabimento de devolução em dobro (art. 42 §ú)",
            "Avaliar dano moral (in re ipsa em hipóteses do STJ)",
            "Requerer inversão do ônus da prova (art. 6º, VIII)",
        ],
    },
    {
        "nome": "Família — Divórcio e Alimentos",
        "area_juridica": "familia",
        "descricao": "Documentos e providências para ação de família.",
        "itens": [
            "Certidão de casamento atualizada (ou prova de união estável)",
            "Pacto antenupcial / definição do regime de bens",
            "Documentos pessoais das partes e dos filhos (certidões)",
            "Relação e prova de titularidade dos bens a partilhar",
            "Comprovantes de renda das partes (para alimentos)",
            "Definir guarda, convivência e valor de alimentos",
            "Verificar necessidade de intervenção do Ministério Público (filhos menores)",
            "Avaliar consensual (escritura/cartório) vs litigioso",
        ],
    },
    {
        "nome": "Imobiliário — Compra e Venda / Locação",
        "area_juridica": "imobiliario",
        "descricao": "Due diligence imobiliária e contratual.",
        "itens": [
            "Matrícula atualizada do imóvel (cartório de registro)",
            "Certidões negativas do imóvel (ônus, IPTU, condomínio)",
            "Certidões pessoais do vendedor (cível, trabalhista, federal)",
            "Verificar regularidade da construção (habite-se / averbação)",
            "Conferir contrato e cláusulas essenciais (preço, prazo, multa)",
            "Vistoria do imóvel documentada (locação)",
            "Comprovantes de pagamento / sinal",
            "Recolhimento de ITBI (compra e venda)",
        ],
    },
    {
        "nome": "Previdenciário — Concessão de Benefício",
        "area_juridica": "previdenciario",
        "descricao": "Instrução para ação previdenciária contra o INSS.",
        "itens": [
            "Extrato CNIS atualizado",
            "Comprovar prévio requerimento administrativo (DER) e indeferimento",
            "Verificar qualidade de segurado e carência (Lei 8.213/91 art. 25)",
            "Laudos e exames médicos (benefícios por incapacidade)",
            "Provas de tempo especial / atividade rural, se aplicável",
            "Calcular tempo de contribuição e regra mais vantajosa",
            "Verificar decadência (10 anos) e prescrição de parcelas (5 anos)",
            "Avaliar competência: Juizado Especial Federal (até 60 SM) ou Vara Federal",
        ],
    },
    {
        "nome": "Digital/LGPD — Adequação e Incidentes",
        "area_juridica": "digital_lgpd",
        "descricao": "Conformidade à LGPD e resposta a incidentes.",
        "itens": [
            "Mapeamento de dados pessoais tratados (data mapping)",
            "Definir base legal para cada tratamento (LGPD art. 7º/11)",
            "Elaborar/atualizar Política de Privacidade e avisos",
            "Registro das operações de tratamento (RoPA)",
            "Relatório de Impacto (RIPD), quando aplicável",
            "Indicar Encarregado (DPO) e canal do titular",
            "Plano de resposta a incidentes (comunicação à ANPD em 3 dias úteis)",
            "Cláusulas de proteção de dados em contratos com operadores",
        ],
    },
    {
        "nome": "Trânsito — Defesa e Recursos",
        "area_juridica": "transito",
        "descricao": "Verificação para defesa de autuação de trânsito.",
        "itens": [
            "Notificação de autuação recebida no prazo (CTB art. 281 §ú)",
            "Auto de infração com dados completos (art. 280)",
            "Certificado de aferição válido do equipamento (radar/etilômetro)",
            "Conferir capitulação correta da infração no CTB",
            "Verificar identificação do condutor infrator",
            "Apresentar defesa prévia no prazo (15 dias)",
            "Recurso à JARI (30 dias) / CETRAN se mantido",
            "Avaliar pontuação acumulada e risco de suspensão (art. 261)",
        ],
    },
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
        for c in CHECKLISTS:
            row = s.execute(
                text("SELECT id FROM checklist_templates WHERE nome=:n AND deleted_at IS NULL"),
                {"n": c["nome"]},
            ).fetchone()
            if row:
                print(f"  ⏭️  Já existe: {c['nome']}"); skip += 1; continue
            tid = str(uuid4())
            s.execute(text("""
                INSERT INTO checklist_templates (id, nome, descricao, area_juridica, is_default)
                VALUES (:id, :nome, :descricao, :area, true)
            """), {"id": tid, "nome": c["nome"], "descricao": c["descricao"], "area": c["area_juridica"]})
            for i, txt in enumerate(c["itens"]):
                s.execute(text("""
                    INSERT INTO checklist_template_items (id, template_id, texto, obrigatorio, ordem)
                    VALUES (:id, :tid, :texto, true, :ordem)
                """), {"id": str(uuid4()), "tid": tid, "texto": txt, "ordem": i})
            print(f"  ✅ Inserido: {c['nome']} ({len(c['itens'])} itens)")
            ins += 1
        s.commit()
    print(f"\nCHECKLISTS SEED: inseridos={ins} ignorados={skip} total={len(CHECKLISTS)}")


if __name__ == "__main__":
    print("EJC — Checklists Seed\n")
    try:
        from dotenv import load_dotenv; load_dotenv()
    except ImportError:
        pass
    seed()
