import EntradaUniversalDocumentos, { EntradaUniversalResultado } from "./EntradaUniversalDocumentos";
import { useAreas } from "../lib/areas";

type Patch = Record<string, any>;
const first = (value: unknown) => Array.isArray(value) ? value[0] : value;

/** Entrada inicial obrigatória do Novo Caso, sem remover o cadastro manual. */
export default function ImportarDocumento({ onPrefill }: { onPrefill: (patch: Patch) => void }) {
  const areas = useAreas();
  const aplicar = (resultado: EntradaUniversalResultado) => {
    // Só pré-preenche a área se a classificação da IA existir na taxonomia
    // canônica (GET /areas, com fallback estático) — evita slug inválido no caso.
    const areasPermitidas = new Set(areas.map((a) => a.slug));
    const classificacao = resultado.classificacao || {};
    const identificacao = resultado.identificacao_processual || {};
    const partes = resultado.partes || {};
    const pessoais = resultado.dados_pessoais || {};
    const resumo = resultado.resumo_executivo || {};
    const estrategia = resultado.estrategia || {};
    const principal = resultado.documentos?.[0];
    const prazo = resultado.prazo || {};
    const dataPrazo = prazo.data_expressa || prazo.termo_final || null;
    const area = String(classificacao.area || "").toLowerCase();
    const tipoPrazo = ["administrativo", "ambiental", "transito"].includes(area) ? "administrativo" : "processual";
    const prazos = dataPrazo ? [{
      titulo: prazo.evento || prazo.providencia || "Prazo identificado na importação",
      tipo: tipoPrazo,
      termo_final: dataPrazo,
      fatal: true,
      base_legal: prazo.regra || "Confirmar regra e termo inicial",
      documento: principal?.filename,
      pagina: prazo.pagina,
      confirmado: false,
    }] : [];
    const titulo = resumo.providencia_principal || resumo.situacao || principal?.classification?.nome || principal?.filename || "Novo caso importado";
    const patch: Patch = {
      titulo: String(titulo).slice(0, 255),
      area: areasPermitidas.has(area) ? area : undefined,
      numero_processo: identificacao.numero_processo || undefined,
      tribunal: identificacao.tribunal || undefined,
      comarca: identificacao.comarca || undefined,
      vara: identificacao.vara || undefined,
      parte_contraria: partes.reu || first(partes.terceiros) || undefined,
      descricao_fatos: resumo.fatos || resumo.situacao || undefined,
      prioridade: resultado.nivel_prontidao === "nao_apto_para_redacao" ? "alta" : "media",
      _cliente_candidato: { nome: pessoais.nome || partes.autor || undefined, cpf: pessoais.cpf || undefined, cnpj: pessoais.cnpj || undefined },
      _tipo_documento: classificacao.tipo_documento || principal?.classification?.tipo || undefined,
      _arquivo_original: resultado._arquivos_locais?.[0],
      _entrada_universal_batch_id: resultado.batch_id,
      _extracao: {
        origem: "entrada_universal", batch_id: resultado.batch_id, classificacao,
        identificacao_processual: identificacao, partes, dados_pessoais: pessoais,
        resumo_executivo: resumo, estrategia, prontidao: resultado.prontidao,
        documentos_faltantes: resultado.documentos_faltantes || [],
        comparacoes: resultado.comparacoes || [], matriz_vicios_teses: resultado.matriz_vicios_teses || [],
        datas_eventos: resultado.datas_eventos || [], prazo, prazos,
        origem_documento_id: principal?.document_id || null,
        documentos: resultado.documentos || [],
      },
    };
    Object.keys(patch).forEach((key) => patch[key] === undefined && delete patch[key]);
    onPrefill(patch);
  };

  return (
    <div className="mb-5">
      <EntradaUniversalDocumentos
        onProcessado={aplicar}
        compact
        titulo="Importar documentos para iniciar o caso"
        descricao="PDF, Word, fotos, HEIC, planilhas ou ZIP. A IA organiza o pacote, identifica área, fase, partes e pendências e pré-preenche o caso; o cadastro manual permanece disponível."
        processarLabel="Ler documentos e pré-preencher o caso"
      />
    </div>
  );
}
