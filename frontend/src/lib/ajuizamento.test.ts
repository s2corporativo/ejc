import { describe, expect, it } from "vitest";
import {
  CONFIRMACAO_REVISAO,
  ETAPAS,
  checklistHomologacao,
  etapaDoEstado,
  montarPayloadFiling,
  podeAprovar,
  podeAssinar,
  podeEditar,
  podeProtocolar,
  protocoloEletronicoLiberado,
  resumoCapacidade,
  type Filing,
  type MatrizCapacidades,
  type PerfilTribunal,
} from "./ajuizamento";

const matriz = (
  estado: MatrizCapacidades["operacoes"][string]["estado"],
  liberado: boolean,
): MatrizCapacidades => ({
  conector: "pje_mni",
  sistema: "pje_mni",
  tribunal: "TJMG",
  ambiente: "producao",
  operacoes: { file_new_case: { estado, motivo: "perfil não homologado" } },
  requisitos_autorizacao: liberado
    ? []
    : ["homologação com o tribunal não concluída"],
  protocolo_real_liberado: liberado,
});

const perfil = (over: Partial<PerfilTribunal> = {}): PerfilTribunal =>
  ({
    id: "p1",
    tribunal_code: "TJMG",
    segment: "estadual",
    degree: "1",
    system: "pje_mni",
    environment: "producao",
    integration_type: "rest",
    auth_type: "oidc_client_credentials",
    certificate_required: false,
    filing_supported: true,
    append_petition_supported: true,
    process_query_supported: true,
    movement_query_supported: true,
    document_download_supported: true,
    notice_query_supported: true,
    callback_supported: false,
    authorized: true,
    production_endpoint_verified: true,
    credentials_valid: true,
    homologated_at: "2026-08-01T00:00:00Z",
    status: "SUPPORTED",
    ativo: true,
    ...over,
  }) as PerfilTribunal;

describe("ajuizamento — etapas e estados", () => {
  it("tem as onze etapas do fluxo, na ordem", () => {
    expect(ETAPAS[0]).toBe("Caso de origem");
    expect(ETAPAS[ETAPAS.length - 1]).toBe("Resultado");
    expect(ETAPAS).toHaveLength(11);
  });

  it("abre o wizard na etapa correspondente ao estado", () => {
    expect(etapaDoEstado("DRAFT")).toBe(1);
    expect(etapaDoEstado("INVALID")).toBe(7);
    expect(etapaDoEstado("READY_FOR_REVIEW")).toBe(8);
    expect(etapaDoEstado("READY_TO_SUBMIT")).toBe(9);
    expect(etapaDoEstado("CONFIRMED")).toBe(10);
  });

  it("bloqueia edição depois do protocolo", () => {
    expect(podeEditar("DRAFT")).toBe(true);
    expect(podeEditar("INVALID")).toBe(true);
    expect(podeEditar("SUBMITTED")).toBe(false);
    expect(podeEditar("CONFIRMED")).toBe(false);
    expect(podeEditar("CANCELLED")).toBe(false);
  });

  it("só aprova com preflight pronto (revisão humana)", () => {
    expect(
      podeAprovar({
        estado: "READY_FOR_REVIEW",
        preflight: { ready: true },
      } as Filing),
    ).toBe(true);
    expect(
      podeAprovar({
        estado: "READY_FOR_REVIEW",
        preflight: { ready: false },
      } as Filing),
    ).toBe(false);
    expect(
      podeAprovar({ estado: "DRAFT", preflight: { ready: true } } as Filing),
    ).toBe(false);
    expect(CONFIRMACAO_REVISAO).toBe("REVISAR E PROTOCOLAR");
  });

  it("só assina depois de aprovado e só protocola depois de assinado", () => {
    expect(podeAssinar("APPROVED")).toBe(true);
    expect(podeAssinar("READY_FOR_REVIEW")).toBe(false);
    expect(
      podeProtocolar({
        estado: "READY_TO_SUBMIT",
        assinatura: { a: 1 },
      } as unknown as Filing),
    ).toBe(true);
    expect(
      podeProtocolar({
        estado: "READY_TO_SUBMIT",
        assinatura: null,
      } as unknown as Filing),
    ).toBe(false);
    expect(
      podeProtocolar({
        estado: "APPROVED",
        assinatura: { a: 1 },
      } as unknown as Filing),
    ).toBe(false);
    // Depois de falha ou pendência de autorização, reenviar continua possível.
    expect(
      podeProtocolar({
        estado: "FAILED",
        assinatura: { a: 1 },
      } as unknown as Filing),
    ).toBe(true);
    expect(
      podeProtocolar({
        estado: "REQUIRES_AUTHORIZATION",
        assinatura: { a: 1 },
      } as unknown as Filing),
    ).toBe(true);
  });
});

describe("ajuizamento — capacidades", () => {
  it("resume o estado do conector para o operador", () => {
    expect(resumoCapacidade(matriz("SUPPORTED", true))).toContain("liberado");
    expect(resumoCapacidade(matriz("REQUIRES_AUTHORIZATION", false))).toContain(
      "Requer autorização",
    );
    expect(resumoCapacidade(null)).toContain("Nenhum conector");
  });

  it("não declara protocolo liberado sem a matriz dizer", () => {
    expect(protocoloEletronicoLiberado(matriz("SUPPORTED", true))).toBe(true);
    expect(protocoloEletronicoLiberado(matriz("SUPPORTED", false))).toBe(false);
    expect(protocoloEletronicoLiberado(undefined)).toBe(false);
  });

  it("checklist de homologação reflete os quatro selos", () => {
    expect(checklistHomologacao(perfil()).every((i) => i.ok)).toBe(true);
    const parcial = checklistHomologacao(
      perfil({ credentials_valid: false, homologated_at: null }),
    );
    expect(parcial.filter((i) => !i.ok).map((i) => i.chave)).toEqual([
      "homologated_at",
      "credentials_valid",
    ]);
  });
});

describe("ajuizamento — payload", () => {
  it("envia só o que foi preenchido e limpa assuntos vazios", () => {
    const payload = montarPayloadFiling({
      case_id: "caso-1",
      tribunal_code: "TJMG",
      classe_codigo: "7",
      jurisdicao: "",
      assuntos: [
        { codigo: " 10375 ", nome: "Dano moral", principal: true },
        { codigo: "", nome: "" },
      ],
      gratuidade: false,
      nivel_sigilo: 0,
    });
    expect(payload.case_id).toBe("caso-1");
    expect(payload.tribunal_code).toBe("TJMG");
    expect(payload).not.toHaveProperty("jurisdicao");
    expect(payload.assuntos).toEqual([
      { codigo: "10375", nome: "Dano moral", principal: true },
    ]);
    // Booleanos e zero são valores legítimos — não podem sumir do payload.
    expect(payload.gratuidade).toBe(false);
    expect(payload.nivel_sigilo).toBe(0);
  });

  it("não inventa campos quando o formulário está vazio", () => {
    expect(montarPayloadFiling({})).toEqual({});
  });
});
