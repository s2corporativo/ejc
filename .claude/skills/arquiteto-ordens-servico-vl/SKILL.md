---
name: arquiteto-ordens-servico-vl
description: >
  Projeta e implementa o módulo de Ordens de Serviço (OS) digitais para a Verde Limp Serviços e Terceirização Ltda. Use SEMPRE que precisar construir, evoluir ou corrigir o sistema de OS da Verde Limp: criação de OS pelo escritório, check-in de equipe via WhatsApp ou app, upload de fotos de execução, assinatura digital do cliente, geração automática de PDF da OS, histórico por cliente. Este módulo é o coração operacional da Verde Limp — cada OS é evidência contratual. Integra com sistema-gestao-operacional-vl (banco de dados), integrador-whatsapp-business (notificações) e gerador-relatorios-pdf-dinamicos (PDF da OS). Acionado por: "OS digital verde limp", "ordem de serviço app", "check-in equipe campo", "foto execução OS", "assinatura digital cliente vl", "PDF ordem de serviço", "histórico OS cliente", "OS vl sistema", "comprovante serviço verde limp".
---

# Módulo de Ordens de Serviço Digitais — Verde Limp

## Contexto

```
EMPRESA: Verde Limp Serviços e Terceirização Ltda
OBJETIVO: digitalizar 100% do ciclo de OS — criação → execução → evidência → assinatura → relatório
CANAL EQUIPE: WhatsApp (check-in/check-out e fotos via WhatsApp — sem app adicional)
CANAL OFFICE: sistema web (gestor cria e acompanha OS)
CANAL CLIENTE: PDF por email/WhatsApp após conclusão

FLUXO COMPLETO:
  1. Escritório cria OS no sistema (contrato + data + equipe + serviço)
  2. Sistema envia WhatsApp para líder da equipe com dados da OS
  3. Líder faz check-in no horário de início (responde "INÍCIO VL-2026-001")
  4. Equipe executa o serviço, tira fotos e envia por WhatsApp
  5. Líder faz check-out ("FIM VL-2026-001 [observações]")
  6. Sistema gera PDF com dados + fotos + assinatura
  7. PDF enviado ao cliente por email e/ou WhatsApp
```

---

## 1. Schema de Banco (extensão do sistema-gestao-operacional-vl)

```sql
-- Extensão da tabela service_orders (adicionar campos de campo)
ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS
  checkin_time TEXT,           -- hora real de início
  checkout_time TEXT,          -- hora real de término
  checkin_location TEXT,       -- coordenadas GPS (lat,lng) se disponível
  checkout_location TEXT,
  client_signature TEXT,       -- base64 da assinatura
  client_signed_at TEXT,
  client_signed_name TEXT,
  weather TEXT,                -- condição climática no dia
  issues_found TEXT,           -- problemas encontrados durante execução
  materials_used TEXT,         -- JSON: lista de materiais/insumos usados
  next_service_date TEXT;      -- sugestão de próxima OS

-- Fotos da OS (tabela separada para múltiplas fotos)
CREATE TABLE IF NOT EXISTS os_photos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  os_id INTEGER REFERENCES service_orders(id) ON DELETE CASCADE,
  photo_type TEXT NOT NULL,  -- 'antes', 'durante', 'depois', 'problema', 'equipe'
  file_path TEXT NOT NULL,
  file_name TEXT,
  file_size INTEGER,
  caption TEXT,
  taken_at TEXT DEFAULT CURRENT_TIMESTAMP,
  source TEXT DEFAULT 'whatsapp'  -- 'whatsapp', 'upload_web', 'app'
);

CREATE INDEX idx_os_photos_os_id ON os_photos(os_id);
CREATE INDEX idx_service_orders_contract_date ON service_orders(contract_id, service_date);
```

---

## 2. Lógica de Negócio — Ciclo de Vida da OS

```python
# verde_limp/os_lifecycle.py
from enum import Enum
from datetime import datetime
import re

class OSStatus(str, Enum):
    PROGRAMADA = "programada"       # criada, aguardando data
    AGUARDANDO_EQUIPE = "aguardando_equipe"  # notificação enviada
    EM_EXECUCAO = "em_execucao"    # check-in realizado
    CONCLUIDA = "concluida"        # check-out realizado
    PENDENTE_ASSINATURA = "pendente_assinatura"
    FINALIZADA = "finalizada"      # assinatura + PDF gerado
    CANCELADA = "cancelada"

def process_whatsapp_message(from_phone: str, message: str, db) -> str:
    """
    Interpreta mensagens WhatsApp da equipe e atualiza status da OS.
    Comandos suportados:
      INÍCIO VL-2026-001           → check-in
      FIM VL-2026-001              → check-out sem observações
      FIM VL-2026-001 [texto]      → check-out com observações
      FOTO VL-2026-001 [tipo]      → registrar próxima foto enviada
      PROBLEMA VL-2026-001 [texto] → registrar problema encontrado
    """
    message = message.strip().upper()
    
    # Padrão de número de OS
    os_pattern = r'VL-\d{4}-\d{3,4}'
    
    # CHECK-IN
    if message.startswith("INÍCIO") or message.startswith("INICIO"):
        os_match = re.search(os_pattern, message)
        if os_match:
            os_number = os_match.group()
            result = do_checkin(os_number, from_phone, db)
            return result
        return "Formato inválido. Use: INÍCIO VL-2026-001"
    
    # CHECK-OUT
    if message.startswith("FIM"):
        os_match = re.search(os_pattern, message)
        if os_match:
            os_number = os_match.group()
            # Observações após o número da OS
            obs_match = re.search(os_pattern + r'\s*(.*)', message)
            observations = obs_match.group(1).strip() if obs_match else ""
            result = do_checkout(os_number, from_phone, observations, db)
            return result
        return "Formato inválido. Use: FIM VL-2026-001 [observações]"
    
    return None  # mensagem não reconhecida como comando OS

def do_checkin(os_number: str, phone: str, db) -> str:
    os_row = db.execute(
        "SELECT * FROM service_orders WHERE os_number = ?", (os_number,)
    ).fetchone()
    
    if not os_row:
        return f"OS {os_number} não encontrada. Verifique o número."
    
    if os_row['status'] not in ('programada', 'aguardando_equipe'):
        return f"OS {os_number} já possui check-in registrado (status: {os_row['status']})"
    
    now = datetime.now()
    db.execute(
        "UPDATE service_orders SET status=?, checkin_time=? WHERE os_number=?",
        (OSStatus.EM_EXECUCAO, now.isoformat(), os_number)
    )
    db.commit()
    
    contract = db.execute(
        "SELECT client_name FROM contracts WHERE id=?", (os_row['contract_id'],)
    ).fetchone()
    
    return (
        f"✅ CHECK-IN registrado!\n"
        f"OS: {os_number}\n"
        f"Cliente: {contract['client_name'] if contract else 'N/D'}\n"
        f"Início: {now.strftime('%H:%M')}\n\n"
        f"📸 Envie fotos ANTES do serviço agora.\n"
        f"Ao terminar, envie: FIM {os_number}"
    )

def do_checkout(os_number: str, phone: str, observations: str, db) -> str:
    os_row = db.execute(
        "SELECT * FROM service_orders WHERE os_number = ?", (os_number,)
    ).fetchone()
    
    if not os_row or os_row['status'] != OSStatus.EM_EXECUCAO:
        return f"OS {os_number} não está em execução."
    
    now = datetime.now()
    db.execute(
        "UPDATE service_orders SET status=?, checkout_time=?, notes=? WHERE os_number=?",
        (OSStatus.CONCLUIDA, now.isoformat(), observations or os_row['notes'], os_number)
    )
    db.commit()
    
    # Trigger: gerar PDF e notificar cliente
    # (executar em background)
    
    return (
        f"✅ CHECK-OUT registrado!\n"
        f"OS: {os_number}\n"
        f"Término: {now.strftime('%H:%M')}\n"
        f"{f'Obs: {observations}' if observations else ''}\n\n"
        f"📄 Relatório sendo gerado e enviado ao cliente."
    )
```

---

## 3. Recebimento e Armazenamento de Fotos

```python
# verde_limp/photo_handler.py
import httpx, os, uuid
from datetime import datetime

PHOTOS_DIR = os.getenv("VL_PHOTOS_DIR", "/opt/verde-limp/uploads/photos")

async def save_whatsapp_photo(
    os_number: str,
    media_url: str,
    photo_type: str,
    db,
    caption: str = ""
) -> dict:
    """Baixa e salva foto recebida via WhatsApp"""
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    
    os_row = db.execute(
        "SELECT id FROM service_orders WHERE os_number=?", (os_number,)
    ).fetchone()
    
    if not os_row:
        return {"error": f"OS {os_number} não encontrada"}
    
    # Download da mídia
    async with httpx.AsyncClient() as client:
        response = await client.get(media_url)
        response.raise_for_status()
    
    # Salvar arquivo
    ext = "jpg"  # WhatsApp geralmente envia JPEG
    filename = f"{os_number}_{photo_type}_{uuid.uuid4().hex[:8]}.{ext}"
    file_path = os.path.join(PHOTOS_DIR, filename)
    
    with open(file_path, "wb") as f:
        f.write(response.content)
    
    # Registrar no banco
    db.execute("""
        INSERT INTO os_photos (os_id, photo_type, file_path, file_name, file_size, caption, source)
        VALUES (?, ?, ?, ?, ?, ?, 'whatsapp')
    """, (os_row['id'], photo_type, file_path, filename, len(response.content), caption))
    db.commit()
    
    return {"saved": True, "file": filename, "type": photo_type}
```

---

## 4. Endpoints da API

```python
# verde_limp/routers/os_api.py
from flask import Blueprint, request, jsonify, send_file
import json

os_bp = Blueprint('os', __name__, url_prefix='/api/os')

@os_bp.route('/', methods=['GET'])
def list_os():
    """Lista OS com filtros"""
    contract_id = request.args.get('contract_id')
    status = request.args.get('status')
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    # ... query com filtros
    return jsonify({"data": [], "total": 0})

@os_bp.route('/', methods=['POST'])
def create_os():
    """Cria nova OS e notifica equipe"""
    data = request.json
    # Validar campos obrigatórios
    # Gerar número OS
    # Salvar no banco
    # Enviar WhatsApp para líder da equipe
    return jsonify({"os_number": "VL-2026-001", "status": "programada"}), 201

@os_bp.route('/<os_number>', methods=['GET'])
def get_os(os_number):
    """Retorna OS com fotos"""
    # Buscar OS + fotos + dados do contrato
    return jsonify({})

@os_bp.route('/<os_number>/photos', methods=['POST'])
def upload_photo(os_number):
    """Upload de foto via formulário web"""
    file = request.files.get('photo')
    photo_type = request.form.get('type', 'depois')
    # Salvar arquivo + registrar no banco
    return jsonify({"saved": True})

@os_bp.route('/<os_number>/pdf', methods=['GET'])
def get_os_pdf(os_number):
    """Gera e retorna PDF da OS"""
    # Buscar dados + fotos
    # Chamar gerador-relatorios-pdf-dinamicos
    # Retornar FileResponse
    return send_file("path/to/os.pdf", as_attachment=True, download_name=f"{os_number}.pdf")
```

---

## 5. Template WhatsApp — Notificação de OS para Equipe

```python
def notify_team_new_os(leader_phone: str, os_data: dict) -> str:
    return (
        f"📋 *NOVA ORDEM DE SERVIÇO — Verde Limp*\n\n"
        f"OS: *{os_data['os_number']}*\n"
        f"Cliente: {os_data['client_name']}\n"
        f"Data: {os_data['service_date']}\n"
        f"Serviço: {os_data['service_description']}\n"
        f"Endereço: {os_data['address']}\n\n"
        f"👤 Equipe: {os_data['team_names']}\n\n"
        f"▶️ Ao chegar, envie:\n"
        f"*INÍCIO {os_data['os_number']}*\n\n"
        f"📸 Envie fotos antes e depois do serviço.\n\n"
        f"⏹️ Ao concluir, envie:\n"
        f"*FIM {os_data['os_number']} [observações]*"
    )
```

---

## 6. Regras Operacionais

- OS sem check-in após 2h do horário programado: alerta automático para gestor
- Mínimo 2 fotos obrigatórias para concluir OS (1 antes + 1 depois)
- OS só pode ser faturada quando status = `finalizada`
- Fotos mantidas por 2 anos (evidência contratual)
- Assinatura digital do cliente opcional mas recomendada para contratos acima de R$ 5.000/mês
- Cancelamento de OS: registrar motivo obrigatório
- Relatório PDF enviado ao cliente em até 24h após conclusão
