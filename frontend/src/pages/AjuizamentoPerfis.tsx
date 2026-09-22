// ── src/pages/AjuizamentoPerfis.tsx ──────────────────────────────────────────
// Administração dos perfis de integração por tribunal (JudicialIntegrationProfile).
// Segredos NUNCA são digitados aqui: os campos de credencial recebem apenas a
// REFERÊNCIA ao Cofre (`provider_key:field_key`). O checklist de homologação é
// o que libera — ou não — o protocolo eletrônico real.
import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, CircleOff, Plus, ShieldCheck } from "lucide-react";

import api from "../lib/api";
import { asList } from "../lib/list";
import { toast } from "../components/Toast";
import {
  Alert,
  Badge,
  Button,
  EmptyState,
  ErrorState,
  FieldLabel,
  Input,
  Modal,
  PageHeader,
  SectionCard,
  Select,
  Spinner,
} from "../components/UI";
import {
  ROTULO_CAPACIDADE,
  checklistHomologacao,
  type PerfilTribunal,
} from "../lib/ajuizamento";

const VAZIO = {
  tribunal_code: "",
  tribunal_nome: "",
  segment: "estadual",
  degree: "1",
  system: "pje_mni",
  environment: "homologacao",
  integration_type: "rest",
  base_url: "",
  api_version: "",
  auth_type: "none",
  client_id_ref: "",
  certificate_ref: "",
  documentation_url: "",
};

export default function AjuizamentoPerfis() {
  const [perfis, setPerfis] = useState<PerfilTribunal[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState(false);
  const [form, setForm] = useState({ ...VAZIO });
  const [aberto, setAberto] = useState(false);
  const [salvando, setSalvando] = useState(false);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(false);
    try {
      const r = await api.get("/ajuizamento/perfis");
      setPerfis(asList<PerfilTribunal>(r.data));
    } catch {
      setErro(true);
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function criar() {
    setSalvando(true);
    try {
      const payload: Record<string, unknown> = {};
      Object.entries(form).forEach(([k, v]) => {
        if (v !== "") payload[k] = v;
      });
      await api.post("/ajuizamento/perfis", payload);
      toast.success("Perfil cadastrado.");
      setAberto(false);
      setForm({ ...VAZIO });
      await carregar();
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: unknown } } })
        ?.response?.data?.detail;
      toast.error(
        typeof detail === "string"
          ? detail
          : "Não foi possível cadastrar o perfil.",
      );
    } finally {
      setSalvando(false);
    }
  }

  async function alternar(p: PerfilTribunal, campo: keyof PerfilTribunal) {
    try {
      const corpo: Record<string, unknown> = { [campo]: !p[campo] };
      if (campo === "authorized" && !p.authorized)
        corpo.homologated_at = new Date().toISOString();
      const r = await api.patch(`/ajuizamento/perfis/${p.id}`, corpo);
      setPerfis((lista) => lista.map((x) => (x.id === p.id ? r.data : x)));
    } catch {
      toast.error("Não foi possível atualizar o perfil.");
    }
  }

  return (
    <div className="p-4 sm:p-6">
      <PageHeader
        eyebrow="Ajuizamento"
        title="Perfis de integração por tribunal"
        subtitle="Endpoint, versão, capacidades e homologação de cada tribunal. Credenciais entram só como referência ao Cofre."
        actions={
          <Button onClick={() => setAberto(true)}>
            <Plus className="mr-1 h-4 w-4" /> Novo perfil
          </Button>
        }
      />

      <Alert variant="info" title="Protocolo real exige os quatro selos">
        Habilitação institucional, homologação com o tribunal, endpoint de
        produção verificado e credencial validada. Sem os quatro, o conector
        responde REQUIRES_AUTHORIZATION e o protocolo é registrado manualmente.
      </Alert>

      {carregando && (
        <div className="flex justify-center py-10">
          <Spinner />
        </div>
      )}
      {erro && <ErrorState onRetry={carregar} />}
      {!carregando && !erro && perfis.length === 0 && (
        <EmptyState
          title="Nenhum perfil cadastrado"
          message="Cadastre o primeiro tribunal para habilitar a matriz de capacidades."
          icon={ShieldCheck}
        />
      )}

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {perfis.map((p) => (
          <SectionCard
            key={p.id}
            title={`${p.tribunal_code} · ${p.system} · ${p.degree}º grau (${p.environment})`}
          >
            <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
              <Badge>{ROTULO_CAPACIDADE[p.status]}</Badge>
              {!p.ativo && <span className="text-slate-500">inativo</span>}
              {p.api_version && (
                <span className="text-slate-500">MNI {p.api_version}</span>
              )}
            </div>
            <dl className="mb-3 grid gap-1 text-sm">
              <div>
                <dt className="text-xs uppercase text-slate-500">Endpoint</dt>
                <dd className="break-all text-slate-700">
                  {p.base_url || "não informado"}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-slate-500">
                  Credencial (referência)
                </dt>
                <dd className="text-slate-700">{p.client_id_ref || "—"}</dd>
              </div>
            </dl>
            <ul className="space-y-1 text-sm">
              {checklistHomologacao(p).map((item) => (
                <li key={item.chave} className="flex items-center gap-2">
                  {item.ok ? (
                    <CheckCircle2 className="h-4 w-4 text-ok-600" />
                  ) : (
                    <CircleOff className="h-4 w-4 text-slate-400" />
                  )}
                  <span
                    className={item.ok ? "text-slate-700" : "text-slate-500"}
                  >
                    {item.rotulo}
                  </span>
                  {item.chave !== "homologated_at" && (
                    <button
                      type="button"
                      className="ml-auto text-xs text-primary-700 underline"
                      onClick={() =>
                        alternar(p, item.chave as keyof PerfilTribunal)
                      }
                    >
                      alternar
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </SectionCard>
        ))}
      </div>

      <Modal
        open={aberto}
        onClose={() => setAberto(false)}
        title="Novo perfil de tribunal"
        size="lg"
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <FieldLabel>Tribunal (sigla)</FieldLabel>
            <Input
              value={form.tribunal_code}
              onChange={(e) =>
                setForm({
                  ...form,
                  tribunal_code: e.target.value.toUpperCase(),
                })
              }
              placeholder="TJMG"
            />
          </div>
          <div>
            <FieldLabel>Nome</FieldLabel>
            <Input
              value={form.tribunal_nome}
              onChange={(e) =>
                setForm({ ...form, tribunal_nome: e.target.value })
              }
            />
          </div>
          <div>
            <FieldLabel>Sistema</FieldLabel>
            <Select
              value={form.system}
              onChange={(e) => setForm({ ...form, system: e.target.value })}
            >
              <option value="pje_mni">PJe (MNI)</option>
              <option value="pdpj">PDPJ-Br</option>
              <option value="eproc">eproc</option>
              <option value="datajud">DataJud</option>
              <option value="manual">Manual</option>
            </Select>
          </div>
          <div>
            <FieldLabel>Segmento</FieldLabel>
            <Select
              value={form.segment}
              onChange={(e) => setForm({ ...form, segment: e.target.value })}
            >
              {[
                "estadual",
                "federal",
                "trabalhista",
                "eleitoral",
                "militar",
                "superior",
              ].map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <FieldLabel>Grau</FieldLabel>
            <Select
              value={form.degree}
              onChange={(e) => setForm({ ...form, degree: e.target.value })}
            >
              <option value="1">1º grau</option>
              <option value="2">2º grau</option>
            </Select>
          </div>
          <div>
            <FieldLabel>Ambiente</FieldLabel>
            <Select
              value={form.environment}
              onChange={(e) =>
                setForm({ ...form, environment: e.target.value })
              }
            >
              <option value="homologacao">Homologação</option>
              <option value="producao">Produção</option>
            </Select>
          </div>
          <div>
            <FieldLabel>Endpoint base (https)</FieldLabel>
            <Input
              value={form.base_url}
              onChange={(e) => setForm({ ...form, base_url: e.target.value })}
              placeholder="https://pje.tjmg.jus.br/mni-client"
            />
          </div>
          <div>
            <FieldLabel>Versão da API</FieldLabel>
            <Input
              value={form.api_version}
              onChange={(e) =>
                setForm({ ...form, api_version: e.target.value })
              }
              placeholder="2.2.2"
            />
          </div>
          <div>
            <FieldLabel>Autenticação</FieldLabel>
            <Select
              value={form.auth_type}
              onChange={(e) => setForm({ ...form, auth_type: e.target.value })}
            >
              {[
                "none",
                "oidc_client_credentials",
                "mni_consultante",
                "certificado",
                "api_key",
              ].map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <FieldLabel>Referência da credencial no Cofre</FieldLabel>
            <Input
              value={form.client_id_ref}
              onChange={(e) =>
                setForm({ ...form, client_id_ref: e.target.value })
              }
              placeholder="pdpj:PDPJ_CLIENT_ID"
            />
            <p className="mt-1 text-xs text-slate-500">
              Formato <code>provider_key:field_key</code>. Nunca digite o valor
              da credencial.
            </p>
          </div>
          <div className="sm:col-span-2">
            <FieldLabel>Documentação oficial do tribunal</FieldLabel>
            <Input
              value={form.documentation_url}
              onChange={(e) =>
                setForm({ ...form, documentation_url: e.target.value })
              }
            />
          </div>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setAberto(false)}>
            Cancelar
          </Button>
          <Button onClick={criar} disabled={salvando || !form.tribunal_code}>
            {salvando ? "Salvando…" : "Cadastrar"}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
