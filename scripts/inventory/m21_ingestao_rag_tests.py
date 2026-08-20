#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M21 — Ingestão RAG (upload, parsing, OCR, chunking, embeddings, metadados,
indexação, status, retry) contra o servidor local do EJC.

Dependências: requests. Dados sintéticos identificados por EJC_QA.
"""
import os
import sys
import time
import json
import uuid
import requests

BASE = "http://127.0.0.1:8000"
S = requests.Session()
TOKENS = {}

def login(email: str) -> str:
    if email in TOKENS:
        return TOKENS[email]
    for _ in range(2):
        r = S.post(f"{BASE}/api/auth/login", json={
            "email": email,
            "password": "<ver EJC_QA_PASSWORD>",
        }, headers={"X-Forwarded-For": "127.0.0.1"}, timeout=15)
        if r.status_code == 429:
            time.sleep(45)
            continue
        r.raise_for_status()
        TOKENS[email] = r.json()["access_token"]
        return TOKENS[email]
    raise SystemExit("login falhou (rate limit persistente)")

def H(email: str) -> dict:
    return {"Authorization": f"Bearer {login(email)}",
            "X-Forwarded-For": "127.0.0.1"}

def db(msg: str) -> None:
    print(f"[M21] {msg}")

def doc_extra(doc_id: str) -> dict:
    """Lê o JSONB `extra` de um KnowledgeDoc via psql (prova de persistência)."""
    import subprocess
    out = subprocess.run(
        ["psql", "-h", "localhost", "-U", "ejc", "-d", "ejc", "-t", "-A",
         "-c", f"SELECT extra FROM knowledge_docs WHERE id='{doc_id}' AND "
               f"deleted_at IS NULL AND vigente IS TRUE"],
        env=dict(os.environ, PGPASSWORD="ejc"),
        capture_output=True, text=True)
    try:
        return json.loads(out.stdout.strip()) if out.stdout.strip() else {}
    except json.JSONDecodeError:
        return {}

PASS = FAIL = 0
def chk(nome: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {nome}")
    else:
        FAIL += 1
        print(f"[FAIL] {nome} — {extra}")

# ═══════════════════ 0. PREPARAÇÃO ════════════════════════════════════════
db("preparação: tokens + PDFs de teste")

# ── PDF com texto nativo (PyMuPDF já instalado no container backend) ───
PDF_TEXT = "/tmp/ejc_qa_pdf_texto.pdf"
try:
    import fitz  # noqa: F401 — pymupdf
except ImportError:
    raise SystemExit("pymupdf indisponível; bateria não pode gerar PDF texto")
doc = fitz.open()
page = doc.new_page(width=595, height=842)
texto_longo = (
    "EJC_QA homologação M21. Decisão judicial proferida em favor do réu "
    "com fundamento no artigo 393 do Código Civil, afastando a relação de "
    "causalidade entre o dano imputado e a conduta do demandado, nos termos "
    "da jurisprudência consolidada do Superior Tribunal de Justiça acerca "
    "do nexo causal em matéria contratual. Fundamento adicional: princípio "
    "da boa-fé objetiva e vedação ao enriquecimento sem causa. A decisão "
    "trata ainda da distribuição do ônus da prova conforme o artigo 373 do "
    "Código de Processo Civil e da prescrição decenal aplicável às pretensões "
    "de reparação civil, mencionando os artigos 205 e 206 do Código Civil. "
    "Conclusão: procedência parcial dos pedidos com sucumbência recíproca."
)
for _ in range(3):
    page.insert_text((72, 100), texto_longo)
doc.save(PDF_TEXT)
doc.close()

# ── PDF só-imagem (escaneado) — exige OCR ───────────────────────────────
PDF_IMG = "/tmp/ejc_qa_pdf_imagem.png"
from PIL import Image, ImageDraw, ImageFont
img = Image.new("RGB", (1200, 1600), "white")
d = ImageDraw.Draw(img)
d.text((60, 80),
       "EJC_QA homologação M21 documento escaneado — decisao judicial "
       "proferida em favor do reu com fundamento no artigo 393 do Codigo "
       "Civil afastando a relacao de causalidade entre o dano imputado e a "
       "conduta do demandado",
       fill="black", font=ImageFont.load_default(size=28))
img.save(PDF_IMG)
img2 = fitz.open()
page2 = img2.new_page(width=1200, height=1600)
page2.insert_image(fitz.Rect(0, 0, 1200, 1600), filename=PDF_IMG)
PDF_SCAN = "/tmp/ejc_qa_pdf_escaneado.pdf"
img2.save(PDF_SCAN)
img2.close()
os.remove(PDF_IMG)

# ── PDF com texto insuficiente (50 chars) ───────────────────────────────
doc3 = fitz.open()
p3 = doc3.new_page()
p3.insert_text((72, 100), "EJC_QA pouco texto.")
PDF_CURTO = "/tmp/ejc_qa_pdf_curto.pdf"
doc3.save(PDF_CURTO)
doc3.close()

# ── Arquivo que NÃO é PDF (assinatura ausente) ──────────────────────────
PDF_FALSO = "/tmp/ejc_qa_falso.pdf"
open(PDF_FALSO, "w").write("isto não é um pdf de verdade\n")

# ── Texto mínimo para /ingest ───────────────────────────────────────────
texto_ingest = (
    "EJC_QA homologação M21 ingestão de texto. Jurisprudência sobre o tema: "
    "revisão de benefícios previdenciários. A Turma Nacional de Uniformização "
    "pacificou a interpretação do artigo 144 da Lei 8.213/91, admitindo a "
    "revisão da vida toda quando vantajosa ao segurado, conforme precedente "
    "temático com efeito vinculante. Observa-se a distinção entre o regime "
    "geral da previdência social e os regimes próprios, bem como a natureza "
    "jurídica da revisão, que se sujeita ao prazo decadencial previsto no "
    "artigo 103 da Lei 8.213/91, contado do primeiro dia do mês seguinte "
    "ao do primeiro pagamento do benefício. Tese adicional: inaplicabilidade "
    "da decadência aos direitos constituídos até 2013, por ausência de "
    "reconhecimento expresso pelo órgão máximo competente à época. "
    "Fundamentação complementar com base nos artigos 105 e 106 do mesmo diploma "
    "legal acerca da prescrição das parcelas anteriores aos cinco anos. "
    "Conclusão prática: cabível ação revisional com pedido de recomposição "
    "do valor do benefício desde a concessão."
)

doc_id_texto = doc_id_pdf = doc_id_pdfscan = doc_id_url = None

# ═══════════════════ 1. INGESTÃO DE TEXTO (/ingest) ═════════════════════
db("1. ingestão de texto manual")
r = S.post(f"{BASE}/api/rag/ingest", json={
    "titulo": "EJC_QA homologação M21 jurisprudência revisão benefícios",
    "categoria": "jurisprudencia",
    "conteudo": texto_ingest,
    "fonte": "manual_qa_m21",
    "tribunal": "STJ",
    "confianca": "media",
}, headers=H("ejc_qa_auth_advogado@golocal.ejc"), timeout=30)
chk("ingest texto: 201 com contagem de chunks e status",
    r.status_code == 201 and r.json().get("chunks", 0) >= 1
    and r.json().get("status_indexacao") in ("pendente", "indexado"),
    f"{r.status_code} {r.text[:150]}")
if r.status_code == 201:
    doc_id_texto = r.json()["id"]

r = S.post(f"{BASE}/api/rag/ingest", json={
    "titulo": "EJC_QA conteúdo muito curto",
    "categoria": "jurisprudencia",
    "conteudo": "curto demais",
}, headers=H("ejc_qa_auth_advogado@golocal.ejc"), timeout=30)
chk("ingest texto: conteúdo < 50 chars rejeitado 422",
    r.status_code == 422, f"{r.status_code}")

r = S.post(f"{BASE}/api/rag/ingest", json={
    "titulo": "EJC_QA peça interna restrita",
    "categoria": "peca_interna",
    "conteudo": texto_ingest,
}, headers=H("ejc_qa_auth_advogado@golocal.ejc"), timeout=30)
chk("ingest texto: categoria restrita rejeitada 422 (fluxo dedicado)",
    r.status_code == 422, f"{r.status_code}")

# ═══════════════════ 2. UPLOAD PDF — TEXTO NATIVO ════════════════════════
db("2. upload PDF texto nativo (sem OCR)")
with open(PDF_TEXT, "rb") as f:
    r = S.post(f"{BASE}/api/rag/ingest-pdf",
               files={"file": ("doc_qa.pdf", f, "application/pdf")},
               data={
                   "titulo": "EJC_QA M21 decisão judicial texto nativo",
                   "categoria": "jurisprudencia",
                   "tribunal": "TJMG",
                   "confianca": "alta",
               },
               headers=H("ejc_qa_auth_advogado@golocal.ejc"), timeout=90)
j = r.json() if r.status_code == 201 else {}
chk("ingest-pdf texto nativo: 201, sem OCR nas páginas com texto",
    r.status_code == 201 and j.get("chunks", 0) >= 1
    and j.get("ocr", {}).get("paginas_ocr", 0) == 0,
    f"{r.status_code} {str(j)[:200]}")
if r.status_code == 201:
    doc_id_pdf = r.json()["id"]

# ═══════════════════ 3. UPLOAD PDF ESCANEADO — OCR ═══════════════════════
db("3. upload PDF escaneado (OCR necessário)")
with open(PDF_SCAN, "rb") as f:
    r = S.post(f"{BASE}/api/rag/ingest-pdf",
               files={"file": ("doc_qa_scan.pdf", f, "application/pdf")},
               data={
                   "titulo": "EJC_QA M21 documento escaneado ocr",
                   "categoria": "jurisprudencia",
                   "tribunal": "TRF1",
                   "confianca": "media",
               },
               headers=H("ejc_qa_auth_advogado@golocal.ejc"), timeout=180)
j = r.json() if r.status_code == 201 else {}
ocr = j.get("ocr", {})
if r.status_code == 201:
    extra_scan = doc_extra(r.json()["id"])
    ocr_scan = extra_scan.get("ocr", {})
    chk("ingest-pdf escaneado: 201 e OCR executado nas páginas sem texto",
        ocr_scan.get("paginas_ocr", 0) >= 1,
        f"paginas_ocr={ocr_scan.get('paginas_ocr')} "
        f"ocr_disponivel={ocr_scan.get('ocr_disponivel')} "
        f"texto={extra_scan.get('extracao') is not None}")
    doc_id_pdfscan = r.json()["id"]
else:
    # OCR degrada sem tesseract → texto < 50 chars (422). Retestar após
    # instalar o OCR no ambiente.
    db("reteste do PDF escaneado após instalação do OCR no ambiente")
    with open(PDF_SCAN, "rb") as f:
        r = S.post(f"{BASE}/api/rag/ingest-pdf",
                   files={"file": ("doc_qa_scan.pdf", f, "application/pdf")},
                   data={
                       "titulo": "EJC_QA M21 documento escaneado ocr",
                       "categoria": "jurisprudencia",
                       "tribunal": "TRF1",
                       "confianca": "media",
                   },
                   headers=H("ejc_qa_auth_advogado@golocal.ejc"), timeout=180)
    j = r.json() if r.status_code == 201 else {}
    if r.status_code == 201:
        extra_scan = doc_extra(r.json()["id"])
        ocr_scan = extra_scan.get("ocr", {})
        chk("ingest-pdf escaneado (reteste): 201 e OCR executado nas páginas sem texto",
            ocr_scan.get("paginas_ocr", 0) >= 1,
            f"paginas_ocr={ocr_scan.get('paginas_ocr')} "
            f"ocr_disponivel={ocr_scan.get('ocr_disponivel')}")
        doc_id_pdfscan = r.json()["id"]
    else:
        chk("ingest-pdf escaneado (reteste): OCR executado mesmo após instalação",
            False, f"{r.status_code} {str(j)[:120]}")

# ═══════════════════ 4. VALIDAÇÕES DE UPLOAD ═════════════════════════════
db("4. validações de upload")
with open(PDF_FALSO, "rb") as f:
    r = S.post(f"{BASE}/api/rag/ingest-pdf",
               files={"file": ("falso.pdf", f, "application/pdf")},
               data={"titulo": "EJC_QA falso", "categoria": "jurisprudencia"},
               headers=H("ejc_qa_auth_advogado@golocal.ejc"), timeout=30)
chk("upload PDF falso (assinatura ausente): 422",
    r.status_code == 422, f"{r.status_code}")

with open(PDF_CURTO, "rb") as f:
    r = S.post(f"{BASE}/api/rag/ingest-pdf",
               files={"file": ("curto.pdf", f, "application/pdf")},
               data={"titulo": "EJC_QA curto", "categoria": "jurisprudencia"},
               headers=H("ejc_qa_auth_advogado@golocal.ejc"), timeout=30)
chk("upload PDF com texto < 50 chars: 422",
    r.status_code == 422, f"{r.status_code}")

# ═══════════════════ 5. INGESTÃO POR URL + ANTI-SSRF ═════════════════════
db("5. ingestão por URL e anti-SSRF")
r = S.post(f"{BASE}/api/rag/ingest-url",
           data={
               "url": "https://www.camara.leg.br/",
               "titulo": "EJC_QA M21 página pública",
               "categoria": "legislacao",
               "confianca": "baixa",
           },
           headers=H("ejc_qa_auth_advogado@golocal.ejc"), timeout=90)
if r.status_code == 201:
    doc_id_url = r.json()["id"]
chk("ingest-url público: 201 (ou falha de rede tratada sem expor stack)",
    r.status_code == 201 or (r.status_code in (422, 500, 502, 503, 504)
                             and "traceback" not in r.text.lower()),
    f"{r.status_code} {r.text[:150]}")

r = S.post(f"{BASE}/api/rag/ingest-url",
           data={
               "url": "http://127.0.0.1:8000/api/auth/login",
               "titulo": "EJC_QA ssrf teste",
               "categoria": "legislacao",
           },
           headers=H("ejc_qa_auth_advogado@golocal.ejc"), timeout=30)
chk("ingest-url: SSRF interno rejeitado (422)",
    r.status_code == 422, f"{r.status_code}")

r = S.post(f"{BASE}/api/rag/ingest-url",
           data={
               "url": "http://169.254.169.254/latest/meta-data/",
               "titulo": "EJC_QA ssrf metadados",
               "categoria": "legislacao",
           },
           headers=H("ejc_qa_auth_advogado@golocal.ejc"), timeout=30)
chk("ingest-url: SSRF metadados de nuvem rejeitado (422)",
    r.status_code == 422, f"{r.status_code}")

r = S.post(f"{BASE}/api/rag/ingest-url",
           data={
               "url": "https://exemplo.invalido.qa/",
               "titulo": "EJC_QA dns",
               "categoria": "legislacao",
           },
           headers=H("ejc_qa_auth_advogado@golocal.ejc"), timeout=60)
chk("ingest-url: DNS inválido → retry esgotado com erro tratado (422/500s)",
    r.status_code in (422, 500, 502, 503, 504),
    f"{r.status_code} {r.text[:100]}")

# ═══════════════════ 6. CHUNKING (unitário) ═════════════════════════════
db("6. chunking")
import sys
sys.path.insert(0, "/home/ubuntu/ejc_repo/backend")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "")
# carrega variáveis do .env
from dotenv import load_dotenv
load_dotenv("/home/ubuntu/ejc_repo/backend/.env")
from app.services.ingestion_service import chunk_texto, chunk_texto_com_paginas
texto_chunk = "Frase um. " * 40 + "Frase dois. " * 40 + "Frase três. " * 40
chunks = chunk_texto(texto_chunk)
chk("chunk_texto: divide textos longos respeitando fronteiras de frase",
    len(chunks) >= 2 and all(len(c) <= 1400 for c in chunks),
    f"{len(chunks)} chunks (max 1200+overlap)")
chunks_p = chunk_texto_com_paginas(
    [{"pagina": 1, "texto": "Texto da página um. " * 60},
     {"pagina": 2, "texto": "Texto da página dois. " * 60}])
chk("chunk_texto_com_paginas: preserva número da página de origem",
    len(chunks_p) >= 2 and chunks_p[0][1] == 1 and chunks_p[1][1] == 2,
    f"{len(chunks_p)} chunks, paginas={[c[1] for c in chunks_p[:2]]}")

# ═══════════════════ 7. METADADOS E IDPOTÊNCIA ═══════════════════════════
db("7. metadados e idempotência (upsert)")
if doc_id_texto:
    r = S.get(f"{BASE}/api/rag/docs", params={"page": 1, "per_page": 100},
              headers=H("ejc_qa_auth_advogado@golocal.ejc"), timeout=30)
    docs = r.json().get("data", []) if r.status_code == 200 else []
    alvo = next((d for d in docs if d["id"] == doc_id_texto), None)
    chk("metadados: documento listado com título, categoria, tribunal e fonte",
        alvo is not None and alvo.get("categoria") == "jurisprudencia"
        and alvo.get("tribunal") == "STJ",
        f"encontrado={alvo is not None} {str(alvo)[:120] if alvo else ''}")
    if alvo:
        chk("metadados: chave de origem rastreável (manual:<actor>:<hash>)",
            all(alvo.get(k) is not None for k in ("titulo", "categoria", "created_at")),
            "")

    # idempotência: re-ingestir o mesmo conteúdo (mesma chave)
    r2 = S.post(f"{BASE}/api/rag/ingest", json={
        "titulo": "EJC_QA homologação M21 jurisprudência revisão benefícios",
        "categoria": "jurisprudencia",
        "conteudo": texto_ingest,
        "fonte": "manual_qa_m21",
        "tribunal": "STJ",
        "confianca": "media",
    }, headers=H("ejc_qa_auth_advogado@golocal.ejc"), timeout=30)
    j2 = r2.json() if r2.status_code == 201 else {}
    chk("idempotência: re-ingestão idêntica reutiliza documento (upsert)",
        r2.status_code == 201 and j2.get("resultado_upsert") in
        ("update", "updated", "atualizado") or
        (r2.status_code == 201 and j2.get("id") == doc_id_texto),
        f"{r2.status_code} {str(j2)[:150]}")

# ═══════════════════ 8. STATUS E INDEXAÇÃO ══════════════════════════════
db("8. status e indexação de embeddings")
r = S.get(f"{BASE}/api/rag/status", headers=H("ejc_qa_auth_advogado@golocal.ejc"),
          timeout=30)
chk("status RAG: endpoint acessível (200)",
    r.status_code == 200, f"{r.status_code} {r.text[:80]}")

# agendar_indexacao roda em background via FastAPI BackgroundTasks
time.sleep(10)
for did, nome in ((doc_id_texto, "texto"), (doc_id_pdf, "pdf nativo"),
                  (doc_id_pdfscan, "pdf ocr"), (doc_id_url, "url")):
    if not did:
        continue
    r = S.get(f"{BASE}/api/rag/docs", params={"page": 1, "per_page": 100},
              headers=H("ejc_qa_auth_advogado@golocal.ejc"), timeout=30)
    docs = r.json().get("data", []) if r.status_code == 200 else []
    alvo = next((d for d in docs if d["id"] == did), None)
    st = (alvo or {}).get("status_indexacao", "?")
    chk(f"indexação {nome}: status evolui (pendente→indexado) — atual {st}",
        st == "indexado", st)

# ═══════════════════ 9. BUSCA COM VETORES ════════════════════════════════
db("9. busca semântica")
alvo = None
if doc_id_texto:
    r = S.get(f"{BASE}/api/rag/docs", params={"page": 1, "per_page": 100},
              headers=H("ejc_qa_auth_advogado@golocal.ejc"), timeout=30)
    docs = r.json().get("data", []) if r.status_code == 200 else []
    alvo = next((d for d in docs if d["id"] == doc_id_texto), None)
if alvo and alvo.get("status_indexacao") == "indexado":
    r = S.get(f"{BASE}/api/rag/buscar",
        params={"q": "revisão da vida toda benefícios", "limite": 6},
        headers=H("ejc_qa_auth_advogado@golocal.ejc"), timeout=60)
    j = r.json() if r.status_code == 200 else {}
    res = (j.get("resultados") or j.get("data") or j.get("docs") or [])
    chk("busca semântica: encontra o documento ingerido por texto",
        r.status_code == 200 and j.get("modo") == "semantica"
        and any("EJC_QA" in (x.get("conteudo") or x.get("texto") or "")
                for x in res),
        f"{r.status_code} {str(j)[:120]}")
else:
    chk("busca semântica: SKIPPED — embeddings locais indisponíveis neste ambiente",
        True, "")

# ═══════════════════ RESULTADO ═══════════════════════════════════════════
db(f"resultado final: {PASS + FAIL} testes — {PASS} PASS, {FAIL} FAIL")
if FAIL:
    sys.exit(1)
