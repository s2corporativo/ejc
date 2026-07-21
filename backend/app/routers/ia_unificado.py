"""
Router unificado de IA - Consolida endpoints de IA分散s
Substitui: ai.py, ai_core.py, ai_tools.py, ia_extra.py (parcialmente)
Organizado por domínio: /api/ia/{analise|extracao|chat|governanca}
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import logging

from app.core.database import get_db
from app.core.auth_middleware import get_current_user
from app.models.user import User
from app.services.ai_gateway import AIGateway
from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ia", tags=["IA Unificada"])

# ── Schemas ──────────────────────────────────────────────────────────────────
class AnaliseDocumentoRequest(BaseModel):
    texto: str
    tipo_analise: str  # "contratual", "processual", "risco"
    contexto: Optional[str] = None

class ExtracaoDadosRequest(BaseModel):
    documento_id: int
    campos: List[str]

class ChatIARequest(BaseModel):
    mensagem: str
    caso_id: Optional[int] = None
    historico: Optional[List[Dict[str, str]]] = None
    modelo: Optional[str] = "groq-llama"

class RespostaIA(BaseModel):
    sucesso: bool
    dados: Dict[str, Any]
    mensagem: Optional[str] = None
    provider_usado: Optional[str] = None

# ── Health Check Unificado ───────────────────────────────────────────────────
@router.get("/health")
async def health_check():
    """Verifica status de todos os providers de IA"""
    settings = get_settings()
    gateway = AIGateway()
    
    providers = {
        "groq": {"ativo": False, "configurado": False},
        "anthropic": {"ativo": False, "configurado": False},
        "ollama": {"ativo": False, "configurado": settings.OLLAMA_ENABLED},
    }
    
    # Verifica configuração
    if settings.GROQ_API_KEY:
        providers["groq"]["configurado"] = True
        providers["groq"]["ativo"] = await gateway.groq_provider.health()
    
    if settings.ANTHROPIC_ENABLED and settings.ANTHROPIC_API_KEY:
        providers["anthropic"]["configurado"] = True
        providers["anthropic"]["ativo"] = await gateway.anthropic_provider.health()
    
    return {
        "status": "operacional" if any(p["ativo"] for p in providers.values()) else "degradado",
        "providers": providers,
        "gateway_ativo": settings.AI_ENABLED
    }

# ── Análise de Documentos ────────────────────────────────────────────────────
@router.post("/analise/documento", response_model=RespostaIA)
async def analisar_documento(
    request: AnaliseDocumentoRequest,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """
    Análise jurídica de documentos usando IA
    Tipos: contratual, processual, risco, compliance
    """
    try:
        gateway = AIGateway()
        
        prompt_map = {
            "contratual": "Analise este contrato identificando cláusulas problemáticas, riscos e recomendações:",
            "processual": "Analise este documento processual extraindo partes, pedidos, fundamentos e prazos:",
            "risco": "Identifique riscos jurídicos neste documento e classifique por gravidade:",
            "compliance": "Verifique conformidade legal e regulatória deste documento:"
        }
        
        if request.tipo_analise not in prompt_map:
            raise HTTPException(status_code=400, detail=f"Tipo de análise '{request.tipo_analise}' não suportado")
        
        prompt = f"{prompt_map[request.tipo_analise]}\n\n{request.texto}"
        if request.contexto:
            prompt = f"Contexto: {request.contexto}\n\n{prompt}"
        
        resposta = await gateway.completar(prompt, max_tokens=2000)
        
        return RespostaIA(
            sucesso=True,
            dados={
                "analise": resposta,
                "tipo": request.tipo_analise,
                "usuario_id": current_user.id
            },
            provider_usado=gateway.last_provider
        )
        
    except Exception as e:
        logger.error(f"Erro na análise de documento: {e}")
        raise HTTPException(status_code=500, detail="Erro ao processar análise com IA")

# ── Extração de Dados Estruturados ───────────────────────────────────────────
@router.post("/extracao/dados", response_model=RespostaIA)
async def extrair_dados(
    request: ExtracaoDadosRequest,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """
    Extrai campos específicos de documentos jurídicos
    """
    try:
        from app.models.documento import Documento
        doc = db.query(Documento).filter(Documento.id == request.documento_id).first()
        
        if not doc:
            raise HTTPException(status_code=404, detail="Documento não encontrado")
        
        gateway = AIGateway()
        campos_str = ", ".join(request.campos)
        
        prompt = f"""Extraia os seguintes campos deste documento jurídico:
Campos: {campos_str}

Retorne APENAS um JSON válido com os campos solicitados. Se algum campo não for encontrado, use null.

Documento:
{doc.conteudo or doc.arquivo_url}
"""
        
        resposta = await gateway.completar(prompt, max_tokens=500)
        
        return RespostaIA(
            sucesso=True,
            dados={
                "documento_id": request.documento_id,
                "extracao": resposta,
                "campos_solicitados": request.campos
            },
            provider_usado=gateway.last_provider
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro na extração de dados: {e}")
        raise HTTPException(status_code=500, detail="Erro ao extrair dados com IA")

# ── Chat com IA (Contextual) ─────────────────────────────────────────────────
@router.post("/chat", response_model=RespostaIA)
async def chat_ia(
    request: ChatIARequest,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """
    Chat com IA contextualizado com caso jurídico (opcional)
    Suporta RAG quando caso_id é fornecido
    """
    try:
        gateway = AIGateway()
        
        # Constrói contexto do caso se fornecido
        contexto_caso = ""
        if request.caso_id:
            from app.models.caso import Caso
            caso = db.query(Caso).filter(Caso.id == request.caso_id).first()
            if caso:
                contexto_caso = f"""
                CONTEXTO DO CASO:
                - Número: {caso.numero_processo}
                - Área: {caso.area}
                - Cliente: {caso.cliente_nome}
                - Fase: {caso.fase}
                - Resumo: {caso.resumo}
                
                """
        
        # Constrói histórico da conversa
        historico_str = ""
        if request.historico:
            historico_str = "\n".join([f"{m['role']}: {m['content']}" for m in request.historico[-5:]])
        
        prompt = f"""{contexto_caso}
Você é um assistente jurídico especializado. Responda de forma clara e técnica.

{historico_str}

Usuário: {request.mensagem}
Assistente:"""
        
        resposta = await gateway.completar(prompt, max_tokens=1500, model=request.modelo)
        
        # Salva no histórico se houver caso
        if request.caso_id:
            from app.models.caso_ia_log import CasoIALog
            log = CasoIALog(
                caso_id=request.caso_id,
                usuario_id=current_user.id,
                prompt=request.mensagem,
                resposta=resposta,
                provider=gateway.last_provider
            )
            db.add(log)
            db.commit()
        
        return RespostaIA(
            sucesso=True,
            dados={
                "resposta": resposta,
                "caso_id": request.caso_id,
                "modelo": request.modelo
            },
            provider_usado=gateway.last_provider
        )
        
    except Exception as e:
        logger.error(f"Erro no chat IA: {e}")
        raise HTTPException(status_code=500, detail="Erro ao processar mensagem com IA")

# ── Upload e Processamento de Documentos ─────────────────────────────────────
@router.post("/documentos/upload", response_model=RespostaIA)
async def upload_documento_ia(
    file: UploadFile = File(...),
    tipo_analise: str = Form(default="geral"),
    current_user: User = Depends(get_current_user),
    db = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """
    Upload de documento para processamento com IA
    Formatos aceitos: PDF, DOCX, TXT, JPG, PNG
    Retorna análise preliminar assíncrona
    """
    formatos_aceitos = {
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "text/plain": ".txt",
        "image/jpeg": ".jpg",
        "image/png": ".png"
    }
    
    if file.content_type not in formatos_aceitos:
        raise HTTPException(
            status_code=400, 
            detail=f"Formato não suportado. Aceitamos: {', '.join(formatos_aceitos.keys())}"
        )
    
    try:
        # Salva arquivo temporariamente
        import tempfile
        import os
        from pathlib import Path
        
        extensao = formatos_aceitos[file.content_type]
        with tempfile.NamedTemporaryFile(delete=False, suffix=extensao) as tmp:
            conteudo = await file.read()
            tmp.write(conteudo)
            tmp_path = tmp.name
        
        # Processamento assíncrono
        async def processar_documento():
            try:
                gateway = AIGateway()
                
                # Extrai texto (implementação simplificada)
                texto = ""
                if extensao == ".txt":
                    with open(tmp_path, 'r', encoding='utf-8') as f:
                        texto = f.read()
                elif extensao == ".pdf":
                    # Usar PyPDF2 ou pdfplumber em produção
                    texto = f"[PDF {file.filename} - {len(conteudo)} bytes]"
                else:
                    texto = f"[Arquivo {file.filename} - {len(conteudo)} bytes]"
                
                # Análise preliminar
                prompt = f"Faça uma análise preliminar deste documento jurídico ({tipo_analise}):\n\n{texto[:5000]}"
                analise = await gateway.completar(prompt, max_tokens=1000)
                
                # Salva resultado
                from app.models.documento import Documento
                doc = Documento(
                    nome=file.filename,
                    conteudo=texto[:10000],  # Primeiros 10k chars
                    analise_ia=analise,
                    usuario_id=current_user.id,
                    tipo=tipo_analise
                )
                db.add(doc)
                db.commit()
                
            except Exception as e:
                logger.error(f"Erro processamento assíncrono: {e}")
            finally:
                os.unlink(tmp_path)
        
        if background_tasks:
            background_tasks.add_task(processar_documento)
        
        return RespostaIA(
            sucesso=True,
            dados={
                "mensagem": "Documento recebido e processamento iniciado",
                "filename": file.filename,
                "tamanho": len(conteudo),
                "formato": file.content_type,
                "tipo_analise": tipo_analise
            },
            mensagem="Processamento completo disponível em breve"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro upload documento: {e}")
        raise HTTPException(status_code=500, detail="Erro ao processar upload")

# ── Governança de IA ─────────────────────────────────────────────────────────
@router.get("/governanca/status", response_model=RespostaIA)
async def governanca_status(
    current_user: User = Depends(get_current_user)
):
    """
    Status de governança de IA: logs, custos, uso por usuário
    """
    try:
        from sqlalchemy import func
        from app.models.caso_ia_log import CasoIALog
        
        db = next(get_db())
        
        # Estatísticas de uso
        total_usos = db.query(func.count(CasoIALog.id)).scalar() or 0
        usuarios_ativos = db.query(func.count(func.distinct(CasoIALog.usuario_id))).scalar() or 0
        
        # Uso por provider
        uso_por_provider = db.query(
            CasoIALog.provider,
            func.count(CasoIALog.id).label('total')
        ).group_by(CasoIALog.provider).all()
        
        # Top usuários
        top_usuarios = db.query(
            CasoIALog.usuario_id,
            func.count(CasoIALog.id).label('total')
        ).group_by(CasoIALog.usuario_id).order_by(func.count(CasoIALog.id).desc()).limit(5).all()
        
        return RespostaIA(
            sucesso=True,
            dados={
                "total_usos": total_usos,
                "usuarios_ativos": usuarios_ativos,
                "uso_por_provider": {p.provider: p.total for p in uso_por_provider},
                "top_usuarios": [{"usuario_id": u.usuario_id, "usos": u.total} for u in top_usuarios]
            }
        )
        
    except Exception as e:
        logger.error(f"Erro governança IA: {e}")
        raise HTTPException(status_code=500, detail="Erro ao obter status de governança")

# ── Endpoints Legados (Redirecionamento) ─────────────────────────────────────
# Manter compatibilidade com rotas antigas por 30 dias
@router.get("/legacy/status")
async def legacy_status():
    """Endpoint legado - será removido em 30 dias"""
    return {
        "aviso": "Este endpoint será descontinuado. Use /ia/health",
        "nova_rota": "/api/ia/health"
    }
