import { useEffect, useState } from "react";
import { toast } from "../components/Toast";
import api from "../lib/api";
import {
  PageHeader,
  Spinner,
  ErrorState,
  fmtDate,
  Modal,
} from "../components/UI";
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
  descricao?: string;
  expira_em?: string;
  max_acessos?: number;
  acessos_realizados: number;
  ativo: boolean;
}
interface LinkRecemGerado {
  url: string;
  expira_em?: string;
}

/**
 * Painel de Data Room — superfície única do recurso (sem segundo CRUD).
 *
 * Sem props: página global /data-room com todas as salas acessíveis ao
 * usuário (contrato §3 do plano 2026-09-20 mantém o menu Administration
 * para gestão geral). Com `caseId` (Onda 3 — Data Room → contexto de
 * Caso): lista só as salas vinculadas ao caso e novas salas já nascem
 * com case_id (o backend DataRoomIn aceita case_id/client_id).
 */
export function DataRoomPanel({ caseId }: { caseId?: string }) {
  const [rooms, setRooms] = useState<Room[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState(false);
  const [novo, setNovo] = useState(false);
  const [form, setForm] = useState({ nome: "", descricao: "" });
  const [aberta, setAberta] = useState<any>(null); // detalhe da sala
  const [docs, setDocs] = useState<any[]>([]);
  const [docSel, setDocSel] = useState("");
  const [linkRecemGerado, setLinkRecemGerado] =
    useState<LinkRecemGerado | null>(null);

  const carregar = () => {
    setLoading(true);
    setErro(false);
    api
      .get("/data-rooms?per_page=50")
      .then((r) => {
        const todas = asList<Room>(r.data);
        setRooms(caseId ? todas.filter((s) => s.case_id === caseId) : todas);
      })
      .catch(() => setErro(true))
      .finally(() => setLoading(false));
  };
  useEffect(() => {
    carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const criar = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.post("/data-rooms", caseId ? { ...form, case_id: caseId } : form);
    setNovo(false);
    setForm({ nome: "", descricao: "" });
    carregar();
  };

  const abrir = async (id: string, preservarLinkRecemGerado = false) => {
    if (!preservarLinkRecemGerado) setLinkRecemGerado(null);
    const { data } = await api.get(`/data-rooms/${id}`);
    setAberta(data);
    api
      .get("/documents/?per_page=100")
      .then((r) => setDocs(asList(r.data)))
      .catch(() => {});
  };

  const fecharSala = () => {
    setAberta(null);
    setLinkRecemGerado(null);
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

  const copiarUrl = (url: string) => {
    navigator.clipboard?.writeText(url);
    toast.info("Link copiado:\n" + url);
  };

  const gerarLink = async () => {
    // O backend persiste somente o hash do token e devolve o segredo uma única
    // vez. A UI deve capturar essa resposta — a listagem posterior não contém
    // (nem deve conter) o token em claro.
    try {
      const { data } = await api.post(`/data-rooms/${aberta.id}/links`, {
        expira_horas: 72,
      });
      const caminho = String(data?.url_acesso || "");
      if (!caminho.startsWith("/api/data-rooms/acesso/")) {
        throw new Error("Resposta de criação de link sem URL de acesso válida");
      }
      const url = new URL(caminho, location.origin).toString();
      await abrir(aberta.id, true);
      setLinkRecemGerado({ url, expira_em: data?.expira_em });
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        err?.message ||
        "Não foi possível gerar o link de acesso.";
      toast.error(String(msg));
    }
  };

  return (
    <div>
      <PageHeader
        title={caseId ? "Data Room do caso" : "Data Room"}
        subtitle={
          caseId
            ? "Salas seguras deste caso com links de acesso externo"
            : "Salas seguras de documentos com links de acesso externo"
        }
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
      ) : erro ? (
        <ErrorState
          message="Não foi possível carregar as salas de documentos. Tente novamente."
          onRetry={carregar}
        />
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
              {caseId
                ? "Nenhuma sala vinculada a este caso"
                : "Nenhuma sala criada"}
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
              <label className="label" htmlFor="sala-nome">
                Nome *
              </label>
              <input
                id="sala-nome"
                required
                value={form.nome}
                onChange={(e) =>
                  setForm((f) => ({ ...f, nome: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="label" htmlFor="sala-descricao">
                Descrição
              </label>
              <textarea
                id="sala-descricao"
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
          onClose={fecharSala}
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
                <button
                  onClick={gerarLink}
                  disabled={(aberta.arquivos?.length ?? 0) === 0}
                  title={
                    (aberta.arquivos?.length ?? 0) === 0
                      ? "Adicione ao menos um documento à sala para gerar um link."
                      : "Gera um link de acesso válido por 72 horas"
                  }
                  className="btn-secondary text-xs"
                >
                  + Gerar link (72h)
                </button>
              </div>

              {linkRecemGerado && (
                <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
                  <div className="font-medium text-amber-900">
                    Link recém-gerado — copie agora
                  </div>
                  <p className="mt-1 text-xs text-amber-800">
                    Por segurança, o token não fica armazenado em claro e este
                    URL não poderá ser recuperado depois que você fechar a sala.
                    Se perdê-lo, gere um novo link.
                  </p>
                  <div className="mt-2 flex items-center gap-2">
                    <input
                      readOnly
                      value={linkRecemGerado.url}
                      className="input min-w-0 flex-1 text-xs font-mono"
                      aria-label="URL recém-gerado do Data Room"
                    />
                    <button
                      type="button"
                      onClick={() => copiarUrl(linkRecemGerado.url)}
                      className="btn-primary text-xs"
                    >
                      Copiar URL
                    </button>
                  </div>
                  {linkRecemGerado.expira_em && (
                    <p className="mt-1 text-xs text-amber-700">
                      Expira {fmtDate(linkRecemGerado.expira_em)}
                    </p>
                  )}
                </div>
              )}

              <div className="space-y-1">
                {(aberta.links ?? []).map((lk: Link) => (
                  <div
                    key={lk.id}
                    className="card p-2 text-sm flex justify-between items-center"
                  >
                    <div>
                      <span className="font-mono text-xs">
                        Link …{lk.id.slice(-8)}
                      </span>
                      <span className="text-gray-400 text-xs ml-2">
                        {lk.acessos_realizados} acessos · expira{" "}
                        {fmtDate(lk.expira_em)}
                      </span>
                    </div>
                    <span className="text-gray-400 text-xs">
                      URL não recuperável
                    </span>
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

/** Superfície global /data-room — todas as salas acessíveis ao usuário. */
export default function DataRoom() {
  return <DataRoomPanel />;
}
