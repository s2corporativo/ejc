import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, CircleAlert } from "lucide-react";
import api from "../lib/api";
import { asList } from "../lib/list";
import type { Case } from "../types";

type IntegrityState = {
  loading: boolean;
  items: string[];
};

export default function CaseIntegrityIndicator({ caso }: { caso: Case }) {
  const [state, setState] = useState<IntegrityState>({
    loading: true,
    items: [],
  });

  const baseItems = useMemo(() => {
    const items: string[] = [];
    if (!caso.proxima_acao?.trim()) items.push("Sem próxima ação");
    if (!caso.advogado_responsavel_id) items.push("Sem responsável");
    if (!caso.descricao_fatos?.trim()) items.push("Fatos incompletos");
    if (
      (caso.case_type === "judicial" || caso.numero_processo) &&
      !caso.valor_causa
    ) {
      items.push("Valor da causa ausente");
    }
    return items;
  }, [
    caso.advogado_responsavel_id,
    caso.case_type,
    caso.descricao_fatos,
    caso.numero_processo,
    caso.proxima_acao,
    caso.valor_causa,
  ]);

  useEffect(() => {
    let ativo = true;
    setState({ loading: true, items: baseItems });

    Promise.allSettled([
      caso.client_id
        ? api.get("/procuracoes/", { params: { client_id: caso.client_id } })
        : Promise.resolve({ data: [] }),
      api.get("/fees/", { params: { case_id: caso.id, page_size: 1 } }),
      api.get("/documents/", { params: { case_id: caso.id, page_size: 100 } }),
    ]).then(([procuracoes, contratos, documentos]) => {
      if (!ativo) return;
      const items = [...baseItems];

      if (
        procuracoes.status === "fulfilled" &&
        asList<any>(procuracoes.value.data).length === 0
      ) {
        items.push("Falta procuração");
      }

      if (
        contratos.status === "fulfilled" &&
        asList<any>(contratos.value.data).length === 0 &&
        (caso.classificacao_financeira ?? "normal") === "normal"
      ) {
        items.push("Honorários não cadastrados");
      }

      if (documentos.status === "fulfilled") {
        const pendentes = asList<any>(documentos.value.data).filter((doc) =>
          ["pendente", "processando", "erro", "aguardando"].includes(
            String(doc?.status || "").toLowerCase(),
          ),
        );
        if (pendentes.length > 0) {
          items.push(`${pendentes.length} documento(s) pendente(s)`);
        }
      }

      setState({ loading: false, items: Array.from(new Set(items)) });
    });

    return () => {
      ativo = false;
    };
  }, [baseItems, caso.client_id, caso.id]);

  if (state.loading && state.items.length === 0) {
    return (
      <span className="ejc-case-integrity is-loading">
        Verificando integridade…
      </span>
    );
  }

  if (state.items.length === 0) {
    return (
      <span className="ejc-case-integrity is-ok">
        <CheckCircle2 aria-hidden="true" />
        Caso completo
      </span>
    );
  }

  return (
    <span
      className="ejc-case-integrity is-warning"
      title={state.items.join(" · ")}
    >
      <CircleAlert aria-hidden="true" />
      {state.items.length} pendência(s)
      <span className="ejc-case-integrity__details">
        {state.items.slice(0, 3).join(" · ")}
      </span>
    </span>
  );
}
