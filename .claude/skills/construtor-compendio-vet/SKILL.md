---
name: construtor-compendio-vet
description: >
  Constrói e popula o banco de dados do Compêndio Veterinário da Cuidar Vet a partir do Guia Terapêutico Veterinário (2ª Ed., Fernando A. Bretas Viana) e outras fontes oficiais. Use SEMPRE que precisar extrair, estruturar, validar ou importar registros de medicamentos veterinários: OCR do Guia, parsing de bulas, extração de princípio ativo/concentração/forma farmacêutica/espécie/posologia/NCM/CEST/EAN, batch processing de entradas, deduplicação, carga no banco. DIFERENÇA CRÍTICA do gestor-compendio-vet: aquele CONSULTA dados já existentes; este skill CONSTRÓI o banco do zero. Projeto ativo com ~27 entradas extraídas e ~300-400 pendentes. Fontes: Guia Terapêutico Veterinário (PDF/OCR), SIPEAGRO/MAPA, bulas oficiais. Acionado por: "construir compêndio", "extrair medicamentos do guia", "OCR guia veterinário", "popular banco compêndio", "batch compêndio vet", "importar medicamentos", "processar guia terapêutico", "entradas faltantes compêndio", "continuar extração", "Bretas Viana OCR".
---

# Construtor do Compêndio Veterinário — Cuidar Vet

## Contexto do Projeto

```
PRODUTO: Compêndio Vet — banco de dados de medicamentos veterinários
EMPRESA: Cuidar Vet (clínica + e-commerce veterinário)
FONTE PRINCIPAL: Guia Terapêutico Veterinário, 2ª Ed. — Fernando A. Bretas Viana
ESTADO ATUAL: ~27 entradas extraídas | ~300-400 entradas pendentes
CAMPOS NECESSÁRIOS: princípio ativo, concentração, forma farmacêutica, espécie, posologia, 
                    NCM, CEST, EAN, fabricante, registro MAPA, prescrição obrigatória
DESTINO: banco SQLite/PostgreSQL + integração com e-commerce Nuvemshop
```

---

## 1. Schema do Compêndio

```sql
CREATE TABLE IF NOT EXISTS medicamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Identificação
    nome_comercial TEXT NOT NULL,
    nome_generico TEXT,          -- princípio ativo
    fabricante TEXT,
    registro_mapa TEXT,          -- número de registro no MAPA/SIPEAGRO
    
    -- Composição
    principio_ativo TEXT NOT NULL,
    concentracao TEXT,           -- ex: "10 mg/mL", "50 mg/comprimido"
    forma_farmaceutica TEXT,     -- solução, comprimido, pasta, pomada, etc.
    volume_embalagem TEXT,       -- ex: "50 mL", "30 comprimidos"
    
    -- Uso clínico
    indicacao TEXT,              -- indicações terapêuticas
    especies TEXT,               -- cães, gatos, bovinos, equinos, etc.
    posologia TEXT,              -- dose + via + intervalo + duração
    contraindicacoes TEXT,
    periodo_carencia TEXT,       -- para animais de produção
    
    -- Regulatório
    prescricao_obrigatoria INTEGER DEFAULT 0,  -- 0=não, 1=sim
    classe_terapeutica TEXT,     -- antibiótico, anti-inflamatório, etc.
    
    -- Fiscal/Comercial
    ncm TEXT,                    -- Nomenclatura Comum do Mercosul
    cest TEXT,                   -- Código Especificador da Substituição Tributária
    ean TEXT,                    -- código de barras (EAN-13)
    preco_referencia REAL,       -- preço de custo para referência
    
    -- Metadados
    fonte TEXT DEFAULT 'guia_bretas_viana',
    pagina_guia INTEGER,         -- página no Guia para rastreabilidade
    validado INTEGER DEFAULT 0,  -- 0=extraído, 1=validado manualmente
    observacoes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_med_principio ON medicamentos(principio_ativo);
CREATE INDEX idx_med_nome ON medicamentos(nome_comercial);
CREATE INDEX idx_med_especie ON medicamentos(especies);
CREATE INDEX idx_med_ncm ON medicamentos(ncm);
```

---

## 2. Protocolo de Extração do Guia (OCR + Parsing)

### Estrutura típica de entrada no Guia Bretas Viana

```
NOME COMERCIAL (fabricante)
Princípio ativo: [nome]
Concentração: [valor + unidade]
Forma farmacêutica: [tipo]
Indicações: [texto]
Espécies: [lista]
Posologia: [texto]
Contraindicações: [texto]
Registro MAPA: [número]
```

### Pipeline de Extração

```python
# construtor_compendio/extractor.py
import re
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class MedicamentoEntry:
    nome_comercial: str = ""
    fabricante: str = ""
    principio_ativo: str = ""
    concentracao: str = ""
    forma_farmaceutica: str = ""
    indicacao: str = ""
    especies: str = ""
    posologia: str = ""
    contraindicacoes: str = ""
    periodo_carencia: str = ""
    registro_mapa: str = ""
    prescricao_obrigatoria: bool = False
    classe_terapeutica: str = ""
    ncm: str = ""
    cest: str = ""
    ean: str = ""
    pagina_guia: int = 0
    fonte: str = "guia_bretas_viana"
    observacoes: str = ""
    validado: int = 0

def parse_entry_block(text_block: str, page: int = 0) -> Optional[MedicamentoEntry]:
    """
    Parseia um bloco de texto do Guia Bretas Viana e retorna entrada estruturada.
    text_block: texto OCR de uma entrada do guia
    """
    entry = MedicamentoEntry(pagina_guia=page)

    # Nome comercial (geralmente na primeira linha, em CAPS ou negrito)
    lines = [l.strip() for l in text_block.strip().split('\n') if l.strip()]
    if lines:
        # Extrair nome comercial e fabricante (ex: "AMOXICILINA (Ourofino)")
        name_match = re.match(r'^(.+?)\s*[\(\[](.*?)[\)\]]', lines[0])
        if name_match:
            entry.nome_comercial = name_match.group(1).strip()
            entry.fabricante = name_match.group(2).strip()
        else:
            entry.nome_comercial = lines[0]

    # Campos com label
    field_patterns = {
        'principio_ativo': r'(?:princípio ativo|princípio|componente)[:\s]+(.+)',
        'concentracao': r'(?:concentração|conc\.?)[:\s]+(.+)',
        'forma_farmaceutica': r'(?:forma farmacêutica|apresentação)[:\s]+(.+)',
        'indicacao': r'(?:indicaç[õo]es?|uso indicado)[:\s]+(.+)',
        'especies': r'(?:espécies?|indicado para)[:\s]+(.+)',
        'posologia': r'(?:posologia|dose|dosagem)[:\s]+(.+)',
        'contraindicacoes': r'(?:contraindicaç[õo]es?)[:\s]+(.+)',
        'periodo_carencia': r'(?:período de carência|carência)[:\s]+(.+)',
        'registro_mapa': r'(?:registro|reg\.|n[°º]\s*registro)[:\s]+(\d[\d\.]+)',
    }

    full_text = text_block.lower()
    for field_name, pattern in field_patterns.items():
        match = re.search(pattern, full_text, re.IGNORECASE | re.MULTILINE)
        if match:
            setattr(entry, field_name, match.group(1).strip()[:500])

    # Detectar prescrição obrigatória
    if re.search(r'(prescriç[aã]o|receitu[aá]rio|uso veterinário)', full_text, re.IGNORECASE):
        entry.prescricao_obrigatoria = True

    # Classificar terapêutica por palavras-chave
    entry.classe_terapeutica = classify_therapeutic(entry.principio_ativo or full_text)

    return entry if entry.principio_ativo else None

def classify_therapeutic(text: str) -> str:
    """Classifica classe terapêutica por palavra-chave"""
    text = text.lower()
    classes = {
        "antibiótico": ["amoxicilina", "enrofloxacina", "doxiciclina", "penicilina", "cefalexina", "metronidazol"],
        "anti-inflamatório": ["meloxicam", "carprofeno", "cetoprofeno", "prednisona", "dexametasona"],
        "antiparasitário": ["ivermectina", "albendazol", "praziquantel", "fipronil", "imidacloprid"],
        "anestésico/sedativo": ["quetamina", "xilazina", "propofol", "midazolam", "acepromazina"],
        "hormonal": ["oxitocina", "prostaglandina", "estrógeno", "progesterona"],
        "vitamínico": ["vitamina", "complexo b", "ferro", "cálcio"],
        "antifúngico": ["fluconazol", "itraconazol", "cetoconazol", "griseofulvina"],
        "cardiovascular": ["digoxina", "furosemida", "atenolol", "enalapril"],
    }
    for classe, keywords in classes.items():
        if any(kw in text for kw in keywords):
            return classe
    return "outros"
```

---

## 3. NCM Padrão para Medicamentos Veterinários

```python
# construtor_compendio/ncm_map.py
# NCMs mais comuns — confirmar sempre com tabela TIPI vigente

NCM_VETERINARIO = {
    # Antibióticos veterinários
    "antibiotico_uso_vet": "3004.20.99",
    # Anti-inflamatórios veterinários
    "anti_inflamatorio_vet": "3004.90.99",
    # Antiparasitários
    "antiparasitario_oral": "3004.90.69",
    "antiparasitario_topico": "3808.91.29",
    # Vacinas veterinárias
    "vacina_vet": "3002.30.00",
    # Vitaminas e suplementos
    "vitamina_vet": "3004.50.90",
    # Anestésicos veterinários
    "anestesico_vet": "3004.90.99",
    # Medicamentos em geral não classificados
    "generico_uso_vet": "3004.90.99",
}

# CEST para medicamentos veterinários (Convênio ICMS)
CEST_MAP = {
    "3004.20.99": "13.001.00",
    "3004.90.99": "13.001.00",
    "3002.30.00": "13.002.00",
}

def get_ncm_cest(classe_terapeutica: str, forma: str) -> tuple[str, str]:
    """Retorna (NCM, CEST) baseado na classe e forma"""
    forma_lower = (forma or "").lower()
    
    if "vacina" in forma_lower:
        ncm = "3002.30.00"
    elif classe_terapeutica == "antiparasitário" and any(w in forma_lower for w in ["coleira", "spot", "spray", "pour-on"]):
        ncm = "3808.91.29"
    else:
        ncm = NCM_VETERINARIO.get(f"{classe_terapeutica.replace('-','_')}_vet", "3004.90.99")
    
    cest = CEST_MAP.get(ncm, "13.001.00")
    return ncm, cest
```

---

## 4. Processamento em Lote (Batch)

```python
# construtor_compendio/batch_processor.py
import sqlite3
from pathlib import Path

def process_batch_text(raw_entries: list[str], db_path: str, start_page: int = 0):
    """
    Processa lista de blocos de texto e salva no banco.
    raw_entries: lista de strings, cada uma sendo uma entrada do guia
    """
    conn = sqlite3.connect(db_path)
    
    stats = {"inserted": 0, "skipped": 0, "errors": 0}
    
    for i, block in enumerate(raw_entries):
        try:
            entry = parse_entry_block(block, page=start_page + i)
            if not entry or not entry.nome_comercial:
                stats["skipped"] += 1
                continue
            
            # Auto-preencher NCM/CEST
            entry.ncm, entry.cest = get_ncm_cest(entry.classe_terapeutica, entry.forma_farmaceutica)
            
            # Inserir no banco (ignorar duplicatas por nome_comercial)
            conn.execute("""
                INSERT OR IGNORE INTO medicamentos 
                (nome_comercial, fabricante, principio_ativo, concentracao, forma_farmaceutica,
                 indicacao, especies, posologia, contraindicacoes, periodo_carencia,
                 registro_mapa, prescricao_obrigatoria, classe_terapeutica, ncm, cest,
                 pagina_guia, fonte)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                entry.nome_comercial, entry.fabricante, entry.principio_ativo,
                entry.concentracao, entry.forma_farmaceutica, entry.indicacao,
                entry.especies, entry.posologia, entry.contraindicacoes,
                entry.periodo_carencia, entry.registro_mapa,
                int(entry.prescricao_obrigatoria), entry.classe_terapeutica,
                entry.ncm, entry.cest, entry.pagina_guia, entry.fonte
            ))
            
            if conn.execute("SELECT changes()").fetchone()[0]:
                stats["inserted"] += 1
            else:
                stats["skipped"] += 1  # duplicata
                
        except Exception as e:
            stats["errors"] += 1
            print(f"Erro no bloco {i}: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"Batch concluído: {stats['inserted']} inseridos | {stats['skipped']} ignorados | {stats['errors']} erros")
    return stats


def export_to_csv(db_path: str, output_path: str):
    """Exporta compêndio completo para CSV (Nuvemshop import)"""
    import csv
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT * FROM medicamentos ORDER BY principio_ativo").fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM medicamentos LIMIT 0").description]
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(zip(cols, row)))
    
    conn.close()
    print(f"Exportado: {len(rows)} registros → {output_path}")
```

---

## 5. Validação Pós-Extração

```python
def validate_entries(db_path: str) -> dict:
    """Relatório de qualidade das entradas extraídas"""
    conn = sqlite3.connect(db_path)
    
    total = conn.execute("SELECT COUNT(*) FROM medicamentos").fetchone()[0]
    sem_principio = conn.execute("SELECT COUNT(*) FROM medicamentos WHERE principio_ativo = ''").fetchone()[0]
    sem_especie = conn.execute("SELECT COUNT(*) FROM medicamentos WHERE especies = ''").fetchone()[0]
    sem_ncm = conn.execute("SELECT COUNT(*) FROM medicamentos WHERE ncm = ''").fetchone()[0]
    sem_posologia = conn.execute("SELECT COUNT(*) FROM medicamentos WHERE posologia = ''").fetchone()[0]
    nao_validados = conn.execute("SELECT COUNT(*) FROM medicamentos WHERE validado = 0").fetchone()[0]
    
    conn.close()
    
    return {
        "total": total,
        "completos": total - sem_principio - sem_especie,
        "sem_principio_ativo": sem_principio,
        "sem_especie": sem_especie,
        "sem_ncm": sem_ncm,
        "sem_posologia": sem_posologia,
        "pendentes_validacao": nao_validados,
        "qualidade_pct": round(((total - sem_principio) / total * 100), 1) if total > 0 else 0
    }
```

---

## 6. Fluxo de Trabalho Recomendado

```
SESSÃO DE EXTRAÇÃO (~50 entradas por vez):

1. Receber texto OCR do Guia (páginas X a Y)
2. Dividir em blocos por entrada (separador: linha em branco ou nome em CAPS)
3. Executar process_batch_text() → retorna stats
4. Executar validate_entries() → identificar gaps
5. Corrigir manualmente as entradas críticas (sem princípio ativo, sem espécie)
6. Validar NCM/CEST nas entradas corrigidas
7. Marcar como validado=1 após revisão

PROGRESSO ESPERADO:
  Atual: ~27 entradas
  Meta:  ~400 entradas (cobertura do Guia)
  Por sessão: ~30-50 entradas/hora (com revisão)
  Tempo estimado total: 8-12 horas de trabalho
```
