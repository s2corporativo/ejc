// Entrada Única (/entrada) — porta de entrada principal de casos.
// Duas telas na mesma rota (docs/DESENHO_BLOCO3_TELAS.md, seções 2-4):
//   A) relato + documentos → POST /entrada/analisar (multipart);
//   B) confirmação editável → POST /entrada/{rascunho_id}/criar-caso.
// Regras: nada que o sistema possa inferir é perguntado antes de inferir;
// resposta que CHEGOU nunca vira tela de erro (degradado = confirmação com
// campos vazios); rascunho sobrevive ao F5 via sessionStorage.
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router";
import api from "../lib/api";
import { toast } from "../components/Toast";
import { PageHeader } from "../components/UI";
import { useAuth } from "../stores/auth";
import type { User } from "../types";
import { Confirmacao } from "./EntradaUnica/Confirmacao";
import { TelaAnalisando, TelaInicial } from "./EntradaUnica/TelaEnvio";
import {
  carregarRascunho,
  limparRascunho,
  salvarRascunho,
} from "./EntradaUnica/rascunhoStorage";
import {
  META_PADRAO,
  montarPayloadCriacao,
  normalizarAnalise,
  normalizarMeta,
  textoDeAchado,
  type EntradaMeta,
  type Proposta,
} from "./EntradaUnica/types";

type Fase = "inicial" | "analisando" | "confirmar";

function asLista<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) return payload as T[];
  const data = (payload as { data?: unknown })?.data;
  return Array.isArray(data) ? (data as T[]) : [];
}

/** Mensagem humana a partir de um detail de erro HTTP (nunca objeto cru). */
function mensagemDeErro(err: unknown, fallback: string): string {
  const detail = (
    err as { response?: { data?: { detail?: unknown } } } | undefined
  )?.response?.data?.detail;
  const texto = textoDeAchado(detail);
  return texto || fallback;
}

export default function EntradaUnica() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const meuId = user?.id ?? "";

  const [fase, setFase] = useState<Fase>("inicial");
  const [texto, setTexto] = useState("");
  const [arquivos, setArquivos] = useState<File[]>([]);
  const [meta, setMeta] = useState<EntradaMeta>(META_PADRAO);
  const [uploadPct, setUploadPct] = useState(0);
  const [proposta, setProposta] = useState<Proposta | null>(null);
  const [usuarios, setUsuarios] = useState<User[]>([]);
  const [criando, setCriando] = useState(false);
  const [erro409, setErro409] = useState<string | null>(null);

  // Rascunho sobrevive ao F5: reidrata a proposta editada da sessão.
  useEffect(() => {
    const salvo = carregarRascunho();
    if (salvo) {
      setProposta(salvo);
      setFase("confirmar");
    }
  }, []);

  // Limites/formatos reais do backend, com fallback estático.
  useEffect(() => {
    api
      .get("/entrada-universal/meta")
      .then((r) => setMeta(normalizarMeta(r.data)))
      .catch(() => {
        /* fallback META_PADRAO já aplicado */
      });
  }, []);

  // Advogados para os seletores de responsável — falha silenciosa (o
  // default "eu" continua válido mesmo sem a lista).
  useEffect(() => {
    if (fase !== "confirmar") return;
    api
      .get("/users/")
      .then((r) => setUsuarios(asLista<User>(r.data)))
      .catch(() => setUsuarios([]));
  }, [fase]);

  // Toda edição da confirmação é persistida (chave por rascunho).
  useEffect(() => {
    if (proposta) salvarRascunho(proposta);
  }, [proposta]);

  const analisar = useCallback(async () => {
    setFase("analisando");
    setUploadPct(arquivos.length > 0 ? 0 : 100);
    const form = new FormData();
    const relato = texto.trim();
    if (relato) form.append("texto", relato);
    for (const arquivo of arquivos) form.append("files", arquivo);
    try {
      const { data } = await api.post("/entrada/analisar", form, {
        onUploadProgress: (evento) => {
          const total = evento.total ?? 0;
          setUploadPct(
            total > 0 ? Math.round((evento.loaded / total) * 100) : 50,
          );
        },
      });
      const nova = normalizarAnalise(data, meuId);
      if (!nova) {
        // Resposta sem rascunho_id: sem destino para o criar-caso. Volta ao
        // formulário preservando relato e arquivos — nada se perde.
        toast.error(
          "A análise respondeu sem identificador de rascunho. Tente novamente.",
        );
        setFase("inicial");
        return;
      }
      setErro409(null);
      setProposta(nova);
      setFase("confirmar");
    } catch (err) {
      toast.error(
        mensagemDeErro(
          err,
          "Não foi possível analisar agora. Nada foi perdido — tente novamente.",
        ),
      );
      setFase("inicial");
    }
  }, [arquivos, texto, meuId]);

  const atualizarProposta = useCallback((patch: Partial<Proposta>) => {
    setProposta((atual) => (atual ? { ...atual, ...patch } : atual));
  }, []);

  const criarCaso = useCallback(async () => {
    if (!proposta) return;
    setCriando(true);
    setErro409(null);
    try {
      const { data } = await api.post(
        `/entrada/${proposta.rascunhoId}/criar-caso`,
        montarPayloadCriacao(proposta),
      );
      const caseId =
        typeof data?.case_id === "string" && data.case_id ? data.case_id : null;
      if (data?.ja_convertido && !caseId) {
        toast.info("Este rascunho já foi convertido em caso.");
        limparRascunho();
        setProposta(null);
        setFase("inicial");
        return;
      }
      if (!caseId) {
        toast.error("O servidor não devolveu o caso criado. Tente novamente.");
        return;
      }
      limparRascunho();
      toast.success(
        data?.numero_interno
          ? `Caso ${data.numero_interno} criado`
          : "Caso criado",
      );
      navigate(`/casos/${caseId}`);
    } catch (err) {
      const status = (err as { response?: { status?: number } } | undefined)
        ?.response?.status;
      if (status === 409) {
        // Achados do servidor viram blocos na tela (nunca toast de objeto
        // cru): a mensagem entra no banner e os checkboxes reaparecem.
        // Chaves REAIS do detail do backend (paridade com a conversão da
        // Sala Jurídica): alertas_conflito, clientes_possivelmente_duplicados
        // e casos_ativos_do_cliente. Casos ativos entram na mesma lista de
        // duplicidade — é o que faz o checkbox aparecer também para cliente
        // EXISTENTE (sem isso o 409 virava beco sem saída).
        const detail =
          (err as { response?: { data?: { detail?: unknown } } }).response?.data
            ?.detail ?? {};
        const d =
          detail && typeof detail === "object"
            ? (detail as Record<string, unknown>)
            : {};
        const alertas = (
          Array.isArray(d.alertas_conflito)
            ? d.alertas_conflito
            : Array.isArray(d.alertas)
              ? d.alertas
              : []
        )
          .map(textoDeAchado)
          .filter(Boolean);
        const clientesDup = Array.isArray(d.clientes_possivelmente_duplicados)
          ? d.clientes_possivelmente_duplicados
          : Array.isArray(
                (d.duplicados as { clientes?: unknown[] } | undefined)
                  ?.clientes,
              )
            ? ((d.duplicados as { clientes: unknown[] }).clientes as unknown[])
            : [];
        const casosAtivos = Array.isArray(d.casos_ativos_do_cliente)
          ? d.casos_ativos_do_cliente
          : [];
        const dupes = [
          ...clientesDup.map((c) => ({
            clientId:
              typeof (c as { client_id?: unknown })?.client_id === "string"
                ? ((c as { client_id: string }).client_id ?? null)
                : typeof (c as { id?: unknown })?.id === "string"
                  ? (c as { id: string }).id
                  : null,
            rotulo: textoDeAchado(c) || "Cliente semelhante encontrado",
          })),
          ...casosAtivos.map((c) => {
            const o =
              c && typeof c === "object" ? (c as Record<string, unknown>) : {};
            const numero =
              typeof o.numero_interno === "string" && o.numero_interno
                ? `${o.numero_interno} · `
                : "";
            return {
              clientId: null,
              rotulo: `Caso ativo do cliente: ${numero}${
                textoDeAchado(o.titulo) || "sem título"
              }`,
            };
          }),
        ];
        setProposta((atual) =>
          atual
            ? {
                ...atual,
                conflitoAlertas: alertas.length
                  ? alertas
                  : atual.conflitoAlertas,
                duplicados: dupes.length ? dupes : atual.duplicados,
                conflictConfirmed: false,
                duplicateConfirmed: false,
              }
            : atual,
        );
        setErro409(
          mensagemDeErro(err, "Há achados pendentes de revisão humana."),
        );
        return;
      }
      toast.error(mensagemDeErro(err, "Não foi possível criar o caso agora."));
    } finally {
      setCriando(false);
    }
  }, [proposta, navigate]);

  const descartar = useCallback(() => {
    limparRascunho();
    setProposta(null);
    setErro409(null);
    setFase("inicial");
  }, []);

  return (
    <div>
      <PageHeader
        title="Novo caso"
        subtitle="Cole o relato, arraste os documentos, ou os dois."
      />
      {fase === "inicial" && (
        <TelaInicial
          texto={texto}
          onTexto={setTexto}
          arquivos={arquivos}
          onArquivos={setArquivos}
          meta={meta}
          onAnalisar={analisar}
        />
      )}
      {fase === "analisando" && (
        <TelaAnalisando numArquivos={arquivos.length} uploadPct={uploadPct} />
      )}
      {fase === "confirmar" && proposta && (
        <Confirmacao
          proposta={proposta}
          onChange={atualizarProposta}
          usuarios={usuarios}
          criando={criando}
          erro409={erro409}
          onCriar={criarCaso}
          onDescartar={descartar}
        />
      )}
    </div>
  );
}
