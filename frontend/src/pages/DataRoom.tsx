import { useEffect, useState } from "react";
import { toast } from "../components/Toast";
import api from "../lib/api";
import { PageHeader, Spinner, fmtDate, Modal } from "../components/UI";
import { asList } from "../lib/list";

interface Room {
  id: string;
  nome: string;
  descricao?: string;
  case_id?: string;
  client_id?: string;
  created_at?: string;
}
interface Arquivo {
  id: string;
  document_id: string;
  nome_exibicao?: string;
  added_at?: string;
}
interface Link {
  id: string;
  token: string;
  descricao?: string;
  expira_em?: string;
  max_acessos?: number;
  acessos_realizados: number;
  ativo: boolean;
}

export default function DataRoom() {
  const [rooms, setRooms] = useState<Room[]>([]);
  const [loading, setLoading] = useState(true);
  const [novo, setNovo] = useState(false);
  const [form, setForm] = useState({ nome: "", descricao: "" });
  const [aberta, setAberta] = useState<any>(null); // detalhe da sala
  const [docs, setDocs] = useState<any[]>([]);
  const [docSel, setDocSel] = useState("");

  const carregar = () => {
    setLoading(true);
    api
      .get("/data-rooms?per_page=50")
      .then((r) => setRooms(asList<Room>(r.data)))
      .catch(() => {})
      .finally(() => setLoading(false));
  };
  useEffect(() => {
    carregar();
  }, []);

  const criar = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.post("/data-rooms", form);
    setNovo(false);
    setForm({ nome: "", descricao: "" });
    carregar();
  };

  const abrir = async (id: string) => {
    const { data } = await api.get(`/data-rooms/${id}`);
    setAberta(data);
    api
      .get("/documents/?per_page=100")
      .then((r) => setDocs(asList(r.data)))
      .catch(() => {});
  };

  const addArquivo = async () => {
    if (!docSel) return;
    const doc = docs.find((d) => d.id === docSel);
    await api.post(`/data-rooms/${aberta.id}/arquivos`, {
      document_id: docSel,
      nome_exibicao: doc?.titulo,
    });
    setDocSel("");
    abrir(aberta.id);
  };

  const gerarLink = async () => {
    await api.post(`/data-rooms/${aberta.id}/links`, { expira_horas: 72 });
    abrir(aberta.id);
  };

  const copiar = (token: string) => {
    const url = `${location.origin}/api/data-rooms/acesso/${token}`;
    navigator.clipboard?.writeText(url);
    toast.info("Link copiado:\n" + url);
  };

  return (
    <div>
      <PageHeader
        title="Data Room"
        subtitle="Salas seguras de documentos com links de acesso externo"
        actions={
          <button onClick={() => setNovo(true)} className="btn-primary text-sm">
            + Nova sala
          </button>
        }
      />

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {rooms.map((r) => (
            <button
              key={r.id}
              onClick={() => abrir(r.id)}
              className="card p-4 text-left hover:shadow-md transition-shadow"
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg">🔒</span>
                <span className="font-medium text-gray-900">{r.nome}</span>
              </div>
              {r.descricao && (
                <p className="text-xs text-gray-500 mb-2">{r.descricao}</p>
              )}
              <p className="text-xs text-gray-400">{fmtDate(r.created_at)}</p>
            </button>
          ))}
          {rooms.length === 0 && (
            <p className="text-gray-400 text-sm col-span-full text-center py-12">
              Nenhuma sala criada
            </p>
          )}
        </div>
      )}

      {/* Criar sala */}
      {novo && (
        <Modal
          open={novo}
          onClose={() => setNovo(false)}
          title="Nova sala de documentos"
        >
          <form onSubmit={criar} className="space-y-3">
            <div>
              <label className="label">Nome *</label>
              <input
                required
                value={form.nome}
                onChange={(e) =>
                  setForm((f) => ({ ...f, nome: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="label">Descrição</label>
              <textarea
                rows={2}
                value={form.descricao}
                onChange={(e) =>
                  setForm((f) => ({ ...f, descricao: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div className="flex gap-2">
              <button type="submit" className="btn-primary text-sm">
                Criar
              </button>
              <button
                type="button"
                onClick={() => setNovo(false)}
                className="btn-secondary text-sm"
              >
                Cancelar
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Detalhe da sala */}
      {aberta && (
        <Modal
          open={!!aberta}
          onClose={() => setAberta(null)}
          title={`🔒 ${aberta.nome}`}
          wide
        >
          <div className="space-y-5">
            <section>
              <h3 className="font-semibold text-sm text-gray-500 uppercase mb-2">
                Documentos ({aberta.arquivos?.length ?? 0})
              </h3>
              <div className="flex gap-2 mb-2">
                <select
                  value={docSel}
                  onChange={(e) => setDocSel(e.target.value)}
                  className="input flex-1 text-sm"
                >
                  <option value="">Selecione um documento…</option>
                  {docs.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.titulo || d.filename}
                    </option>
                  ))}
                </select>
                <button
                  onClick={addArquivo}
                  disabled={!docSel}
                  className="btn-secondary text-sm"
                >
                  Adicionar
                </button>
              </div>
              <div className="space-y-1">
                {(aberta.arquivos ?? []).map((a: Arquivo) => (
                  <div
                    key={a.id}
                    className="card p-2 text-sm flex justify-between"
                  >
                    <span>{a.nome_exibicao || a.document_id}</span>
                    <span className="text-gray-400 text-xs">
                      {fmtDate(a.added_at)}
                    </span>
                  </div>
                ))}
                {(aberta.arquivos?.length ?? 0) === 0 && (
                  <p className="text-gray-400 text-xs text-center py-2">
                    Nenhum documento
                  </p>
                )}
              </div>
            </section>

            <section>
              <div className="flex justify-between items-center mb-2">
                <h3 className="font-semibold text-sm text-gray-500 uppercase">
                  Links de acesso ({aberta.links?.length ?? 0})
                </h3>
                <button onClick={gerarLink} className="btn-secondary text-xs">
                  + Gerar link (72h)
                </button>
              </div>
              <div className="space-y-1">
                {(aberta.links ?? []).map((lk: Link) => (
                  <div
                    key={lk.id}
                    className="card p-2 text-sm flex justify-between items-center"
                  >
                    <div>
                      <span className="font-mono text-xs">
                        …{lk.token.slice(-8)}
                      </span>
                      <span className="text-gray-400 text-xs ml-2">
                        {lk.acessos_realizados} acessos · expira{" "}
                        {fmtDate(lk.expira_em)}
                      </span>
                    </div>
                    <button
                      onClick={() => copiar(lk.token)}
                      className="text-primary-600 hover:underline text-xs"
                    >
                      Copiar URL
                    </button>
                  </div>
                ))}
                {(aberta.links?.length ?? 0) === 0 && (
                  <p className="text-gray-400 text-xs text-center py-2">
                    Nenhum link ativo
                  </p>
                )}
              </div>
            </section>
          </div>
        </Modal>
      )}
    </div>
  );
}
