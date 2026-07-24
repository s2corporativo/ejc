import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import ProvasCaso from "../../components/ProvasCaso";
import { toast } from "../../components/Toast";
import { Empty, Spinner, fmtDate, fmtMoney } from "../../components/UI";
import api from "../../lib/api";
import { asList } from "../../lib/list";

export const ARQUIVO_SECOES = [
  { key: "documentos", label: "Documentos" },
  { key: "provas", label: "Provas" },
  { key: "contratos", label: "Contratos" },
  { key: "procuracoes", label: "Procurações" },
] as const;

export type ArquivoSecao = (typeof ARQUIVO_SECOES)[number]["key"];

interface TabArquivosProps {
  caseId: string;
  clientId?: string | null;
  secaoAtiva: ArquivoSecao;
  onSecaoChange: (secao: ArquivoSecao) => void;
}

interface ListaRemotaProps {
  titulo: string;
  endpoint: string;
  empty: string;
  renderItem: (item: any) => React.JSX.Element;
}

async function baixarDocumento(docId: string, filename: string) {
  try {
    const response = await api.get(`/documents/${docId}/download`, {
      responseType: "blob",
    });
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename || "documento";
    anchor.click();
    URL.revokeObjectURL(url);
  } catch {
    toast.error("Não foi possível baixar o documento.");
  }
}

function ListaRemota({
  titulo,
  endpoint,
  empty,
  renderItem,
}: ListaRemotaProps) {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    let ativo = true;
    setLoading(true);
    setErro(false);

    api
      .get(endpoint)
      .then((response) => {
        if (ativo) setItems(asList(response.data));
      })
      .catch(() => {
        if (ativo) {
          setItems([]);
          setErro(true);
        }
      })
      .finally(() => {
        if (ativo) setLoading(false);
      });

    return () => {
      ativo = false;
    };
  }, [endpoint]);

  if (loading) return <Spinner />;
  if (erro) {
    return (
      <Empty message={`Não foi possível carregar ${titulo.toLowerCase()}`} />
    );
  }

  return (
    <div className="space-y-4">
      <h3 className="font-semibold">
        {titulo} ({items.length})
      </h3>
      <div className="space-y-2">
        {items.map((item, index) => (
          <div key={item.id || index}>{renderItem(item)}</div>
        ))}
        {items.length === 0 && <Empty message={empty} />}
      </div>
    </div>
  );
}

export default function TabArquivos({
  caseId,
  clientId,
  secaoAtiva,
  onSecaoChange,
}: TabArquivosProps) {
  const renderConteudo = () => {
    switch (secaoAtiva) {
      case "documentos":
        return (
          <ListaRemota
            titulo="Documentos"
            endpoint={`/documents/?case_id=${encodeURIComponent(caseId)}`}
            empty="Nenhum documento vinculado a este caso"
            renderItem={(documento) => (
              <button
                type="button"
                className="card flex w-full items-center justify-between p-3 text-left text-sm hover:bg-slate-50"
                onClick={() =>
                  baixarDocumento(
                    documento.id,
                    documento.filename ||
                      documento.nome_arquivo ||
                      documento.titulo,
                  )
                }
                title="Baixar documento"
              >
                <span className="text-gray-800">
                  {documento.titulo ||
                    documento.filename ||
                    documento.nome_arquivo}
                </span>
                <span className="text-xs text-gray-400">
                  {documento.tipo_peca || documento.tipo}
                </span>
              </button>
            )}
          />
        );
      case "provas":
        return <ProvasCaso caseId={caseId} />;
      case "contratos":
        return (
          <ListaRemota
            titulo="Contratos"
            endpoint={`/contratos?case_id=${encodeURIComponent(caseId)}`}
            empty="Nenhum contrato vinculado"
            renderItem={(contrato) => (
              <div className="card flex items-center justify-between p-3 text-sm">
                <span className="text-gray-800">
                  {contrato.titulo || contrato.tipo_contrato}
                </span>
                <span className="text-gray-500">
                  {fmtMoney(contrato.valor_total)}
                </span>
              </div>
            )}
          />
        );
      case "procuracoes":
        if (!clientId?.trim()) {
          return (
            <Empty message="O cliente do caso não foi identificado. As procurações não serão consultadas." />
          );
        }
        return (
          <ListaRemota
            titulo="Procurações"
            endpoint={`/procuracoes/?client_id=${encodeURIComponent(clientId)}`}
            empty="Nenhuma procuração do cliente"
            renderItem={(procuracao) => (
              <div className="card flex items-center justify-between p-3 text-sm">
                <span className="text-gray-800">
                  {procuracao.tipo_poderes || "Procuração"}
                </span>
                {procuracao.data_validade && (
                  <span className="text-xs text-gray-400">
                    Vence: {fmtDate(procuracao.data_validade)}
                  </span>
                )}
              </div>
            )}
          />
        );
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="font-semibold">Arquivos do caso</h2>
          <p className="text-xs text-slate-400">
            Documentos, provas, contratos e procurações em uma única área.
          </p>
        </div>
        {secaoAtiva === "documentos" && (
          <Link
            to={`/documentos?caso=${caseId}`}
            className="btn-secondary self-start text-xs"
          >
            Anexar documento
          </Link>
        )}
      </div>

      <div
        role="tablist"
        aria-label="Tipos de arquivo do caso"
        className="flex gap-2 overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 p-2 scrollbar-thin"
      >
        {ARQUIVO_SECOES.map((secao) => {
          const ativa = secao.key === secaoAtiva;
          return (
            <button
              key={secao.key}
              type="button"
              role="tab"
              aria-selected={ativa}
              onClick={() => onSecaoChange(secao.key)}
              className={`h-9 flex-shrink-0 rounded-lg px-3 text-sm font-medium transition-colors ${
                ativa
                  ? "bg-slate-950 text-white"
                  : "bg-white text-slate-600 hover:text-slate-950"
              }`}
            >
              {secao.label}
            </button>
          );
        })}
      </div>

      <div role="tabpanel">{renderConteudo()}</div>
    </div>
  );
}
