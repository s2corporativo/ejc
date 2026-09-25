// Entrada Única (/entrada) — porta de entrada principal de casos.
// Fluxo canônico:
//   A) relato + documentos → análise preliminar;
//   B) confirmação editável → criação do caso;
//   C) dossiê jurídico profundo → aprovação HITL → Motor de Peça.
// A complexidade fica no EJC; a superfície inicial continua simples.
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import api from "../lib/api";
import { toast } from "../components/Toast";
import { PageHeader } from "../components/UI";
import { useAuth } from "../stores/auth";
import type { User } from "../types";
import CadastroManual from "./CadastroManual";
import { Confirmacao } from "./EntradaUnica/Confirmacao";
import DossieJuridico from "./EntradaUnica/DossieJuridico";
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

type Fase = "inicial" | "analisando" | "confirmar" | "dossie";

type ClienteContexto = {
  id: string;
  nome: string;
};

const PAPEIS_ENTRADA_IA = new Set(["superadmin", "admin", "socio", "advogado"]);

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

function nomeClienteContexto(raw: unknown): string {
  if (!raw || typeof raw !== "object") return "";
  const cliente = raw as Record<string, unknown>;
  for (const campo of [
    "nome",
    "razao_social",
    "nome_fantasia",
    "nome_exibicao",
  ]) {
    const valor = cliente[campo];
    if (typeof valor === "string" && valor.trim()) return valor.trim();
  }
  return "";
}

/**
 * Entrada Jurídica é a única porta visível. O modo manual reutiliza a tela
 * canônica sem IA. Perfis sem acesso à IA permanecem na mesma porta e recebem
 * o cadastro manual; backend continua autoritativo para cada operação.
 */
export default function EntradaUnica() {
  const [searchParams] = useSearchParams();
  const { user } = useAuth();
  const role = user?.role || "";
  const modoManual = searchParams.get("modo") === "manual";
  if (modoManual || !PAPEIS_ENTRADA_IA.has(role)) return <CadastroManual />;
  return <EntradaInteligente />;
}

/** Reutilizada no Dashboard para que / e /entrada usem a MESMA Entrada Única. */
export function EntradaInteligente({ embedded = false }: { embedded?: boolean }) {
  const [searchParams] = useSearchParams();
  const { user } = useAuth();
  const meuId = user?.id ?? "";
  const clientIdContexto = searchParams.get("client_id")?.trim() || null;

  const [fase, setFase] = useState<Fase>("inicial");
  const [texto, setTexto] = useState("");
  const [arquivos, setArquivos] = useState<File[]>([]);
  const [meta, setMeta] = useState<EntradaMeta>(META_PADRAO);
  const [uploadPct, setUploadPct] = useState(0);
  const [proposta, setProposta] = useState<Proposta | null>(null);
  const [usuarios, setUsuarios] = useState<User[]>([]);
  const [criando, setCriando] = useState(false);
  const [erro409, setErro409] = useState<string | null>(null);
  const [caseCriadoId, setCaseCriadoId] = useState<string | null>(null);
  const [clienteContexto, setClienteContexto] =
    useState<ClienteContexto | null>(null);
  const [clienteContextoInvalido, setClienteContextoInvalido] = useState(false);

  useEffect(() => {
    if (!clientIdContexto) {
      setClienteContexto(null);
      setClienteContextoInvalido(false);
      return;
    }
    let ativo = true;
    setClienteContexto(null);
    setClienteContextoInvalido(false);
    api
      .get(`/clients/${clientIdContexto}`)
      .then((r) => {
        if (!ativo) return;
        setClienteContexto({
          id: clientIdContexto,
          nome: nomeClienteContexto(r.data) || "Cliente selecionado",
        });
      })
      .catch(() => {
        if (!ativo) return;
        setClienteContextoInvalido(true);
      });
    return () => {
      ativo = false;
    };
  }, [clientIdContexto]);

  useEffect(() => {
    const salvo = carregarRascunho();
    if (salvo) {
      setProposta(salvo);
      setFase("confirmar");
    }
  }, []);

  useEffect(() => {
    api
      .get("/entrada-universal/meta")
      .then((r) => setMeta(normalizarMeta(r.data)))
      .catch(() => {
        /* fallback META_PADRAO já aplicado */
      });
  }, []);

  useEffect(() => {
    if (fase !== "confirmar") return;
    api
      .get("/users/")
      .then((r) => setUsuarios(asLista<User>(r.data)))
      .catch(() => setUsuarios([]));
  }, [fase]);

  useEffect(() => {
    if (proposta) salvarRascunho(proposta);
  }, [proposta]);

  useEffect(() => {
    if (!proposta || !clienteContexto) return;
    if (proposta.clienteId === clienteContexto.id) return;
    setProposta((atual) =>
      atual
        ? {
            ...atual,
            clienteId: clienteContexto.id,
            clienteNome: clienteContexto.nome,
            clienteOrigem: "contexto_cliente",
            clienteJaCadastrada: true,
            avisos: [
              ...atual.avisos.filter(
                (item) => item !== "Cliente fixado pela Ficha Mestra.",
              ),
              "Cliente fixado pela Ficha Mestra.",
            ],
          }
        : atual,
    );
  }, [clienteContexto, proposta]);

  const analisar = useCallback(async () => {
    if (clientIdContexto && !clienteContexto) {
      if (clienteContextoInvalido) {
        toast.error(
          "O cliente informado não está disponível para o seu perfil. Abra a Entrada Jurídica sem esse vínculo ou retorne à sua carteira.",
        );
      } else {
        toast.info("Aguarde a validação do cliente selecionado.");
      }
      return;
    }
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
      let nova = normalizarAnalise(data, meuId);
      if (!nova) {
        toast.error(
          "A análise respondeu sem identificador de rascunho. Tente novamente.",
        );
        setFase("inicial");
        return;
      }
      if (clientIdContexto && clienteContexto) {
        nova = {
          ...nova,
          clienteId: clienteContexto.id,
          clienteNome: clienteContexto.nome,
          clienteOrigem: "contexto_cliente",
          clienteJaCadastrada: true,
          avisos: [...nova.avisos, "Cliente fixado pela Ficha Mestra."],
        };
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
  }, [
    arquivos,
    texto,
    meuId,
    clientIdContexto,
    clienteContexto,
    clienteContextoInvalido,
  ]);

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
      setCaseCriadoId(caseId);
      setProposta(null);
      toast.success(
        data?.reconciliado
          ? data?.numero_interno
            ? `Processo vinculado ao caso ${data.numero_interno}.`
            : "Processo vinculado ao caso existente."
          : data?.ja_convertido
            ? data?.numero_interno
              ? `Caso ${data.numero_interno} existente selecionado.`
              : "Caso existente selecionado."
            : data?.numero_interno
              ? `Caso ${data.numero_interno} criado. Iniciando leitura jurídica completa.`
              : "Caso criado. Iniciando leitura jurídica completa.",
      );
      setFase("dossie");
    } catch (err) {
      const status = (err as { response?: { status?: number } } | undefined)
        ?.response?.status;
      if (status === 409) {
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
  }, [proposta]);

  const descartar = useCallback(() => {
    limparRascunho();
    setProposta(null);
    setErro409(null);
    setFase("inicial");
  }, []);

  const novaEntrada = useCallback(() => {
    limparRascunho();
    setCaseCriadoId(null);
    setProposta(null);
    setTexto("");
    setArquivos([]);
    setErro409(null);
    setFase("inicial");
  }, []);

  return (
    <div>
      {!embedded && fase !== "dossie" && (
        <PageHeader
          title="Entrada Jurídica"
          subtitle={
            clienteContexto
              ? `Novo caso para ${clienteContexto.nome}: cole o relato, arraste os documentos, ou os dois.`
              : "Conte o caso, cole o conteúdo ou envie os documentos. O EJC organiza o restante."
          }
        />
      )}
      {fase === "inicial" && (
        <TelaInicial
          texto={texto}
          onTexto={setTexto}
          arquivos={arquivos}
          onArquivos={setArquivos}
          meta={meta}
          onAnalisar={analisar}
          variant={embedded ? "pill" : "full"}
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
      {fase === "dossie" && caseCriadoId && (
        <DossieJuridico caseId={caseCriadoId} onNovo={novaEntrada} />
      )}
    </div>
  );
}
