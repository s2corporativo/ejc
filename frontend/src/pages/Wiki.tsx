import { useEffect, useState } from "react";
import api from "../lib/api";
import {
  PageHeader,
  Spinner,
  Modal,
  Empty,
  ConfirmModal,
} from "../components/UI";

export default function Wiki() {
  const [paginas, setPaginas] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [sel, setSel] = useState<any>(null);
  const [edit, setEdit] = useState<any>(null);
  const [pendenteExcluir, setPendenteExcluir] = useState<string | null>(null);

  const carregar = () => {
    setLoading(true);
    api
      .get("/wiki")
      .then((r) => setPaginas(r.data || []))
      .finally(() => setLoading(false));
  };
  useEffect(() => {
    carregar();
  }, []);

  const abrir = (id: string) =>
    api.get(`/wiki/${id}`).then((r) => setSel(r.data));
  const salvar = () => {
    const body = {
      titulo: edit.titulo,
      categoria: edit.categoria,
      conteudo: edit.conteudo,
    };
    const req = edit.id
      ? api.patch(`/wiki/${edit.id}`, body)
      : api.post("/wiki", body);
    req.then(() => {
      setEdit(null);
      carregar();
    });
  };
  const excluir = (id: string) => {
    setPendenteExcluir(id);
  };
  const confirmarExclusao = () => {
    if (!pendenteExcluir) return;
    api.delete(`/wiki/${pendenteExcluir}`).then(() => {
      setPendenteExcluir(null);
      setSel(null);
      carregar();
    });
  };

  if (loading)
    return (
      <div className="flex justify-center py-20">
        <Spinner />
      </div>
    );

  return (
    <div>
      <PageHeader
        eyebrow="Operação"
        title="Wiki Interna"
        subtitle="Procedimentos, contatos e conhecimento do escritório"
        actions={
          <button
            className="btn-primary text-sm"
            onClick={() =>
              setEdit({ titulo: "", categoria: "procedimentos", conteudo: "" })
            }
          >
            + Nova página
          </button>
        }
      />

      {paginas.length === 0 && (
        <Empty message="Nenhuma página ainda — crie a primeira" />
      )}
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {paginas.map((p) => (
          <button
            key={p.id}
            onClick={() => abrir(p.id)}
            className="card p-4 text-left hover:shadow-card-hover transition-shadow"
          >
            {p.categoria && (
              <span className="text-[10px] font-bold bg-bronze-50 text-bronze-deep px-2 py-0.5 rounded-full">
                {p.categoria}
              </span>
            )}
            <h3 className="font-semibold text-navy mt-1.5">{p.titulo}</h3>
          </button>
        ))}
      </div>

      <Modal
        open={!!sel}
        onClose={() => setSel(null)}
        title={sel?.titulo || ""}
        wide
      >
        {sel && (
          <>
            <pre className="text-sm whitespace-pre-wrap text-slate-700 mb-4">
              {sel.conteudo || "(sem conteúdo)"}
            </pre>
            <div className="flex gap-2">
              <button
                className="btn-outline text-sm"
                onClick={() => {
                  setEdit(sel);
                  setSel(null);
                }}
              >
                Editar
              </button>
              <button
                className="btn-danger text-sm"
                onClick={() => excluir(sel.id)}
              >
                Excluir
              </button>
            </div>
          </>
        )}
      </Modal>

      <Modal
        open={!!edit}
        onClose={() => setEdit(null)}
        title={edit?.id ? "Editar página" : "Nova página"}
        wide
      >
        {edit && (
          <div className="space-y-3">
            <input
              className="input w-full"
              placeholder="Título"
              value={edit.titulo}
              onChange={(e) => setEdit({ ...edit, titulo: e.target.value })}
            />
            <input
              className="input w-full"
              placeholder="Categoria (ex: procedimentos, contatos)"
              value={edit.categoria || ""}
              onChange={(e) => setEdit({ ...edit, categoria: e.target.value })}
            />
            <textarea
              className="input w-full"
              rows={12}
              placeholder="Conteúdo"
              value={edit.conteudo || ""}
              onChange={(e) => setEdit({ ...edit, conteudo: e.target.value })}
            />
            <button
              className="btn-primary"
              onClick={salvar}
              disabled={!edit.titulo}
            >
              Salvar
            </button>
          </div>
        )}
      </Modal>

      <ConfirmModal
        open={pendenteExcluir !== null}
        onClose={() => setPendenteExcluir(null)}
        onConfirm={confirmarExclusao}
        title="Remover página"
        message="Remover esta página?"
        confirmLabel="Remover"
        variant="danger"
      />
    </div>
  );
}
