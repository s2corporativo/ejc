// Modal "Novo caso por documento — IA assistida" (auditoria §2.6 #10).
//
// Extraído do monólito Casos.tsx: componente PRESENTACIONAL do passo 1 do
// fluxograma documental (análise + formulário). O estado do form e as ações
// (salvar/reanexar/concluir/descartar/revisar) permanecem na página.
import { AlertTriangle, FileUp, PenLine, RotateCw } from "lucide-react";
import { Button, Modal, SigiloReforcadoField } from "../../components/UI";
import ImportarDocumento from "../../components/ImportarDocumento";
import { NOVO_CASO_MANUAL_PATH } from "../../lib/novoCaso";
import type { IntakePendencia, IntakeRascunho } from "../../lib/intakeRascunho";
import type { Client, User } from "../../types";
import { CASE_TYPES, EXTRAJ_TYPES, PRESCRICAO } from "./casosCatalogo";

export default function NovoCasoDocumentoModal({
  open,
  onClose,
  onIrCadastroManual,
  form,
  setForm,
  areas,
  clientes,
  advogados,
  pendencia,
  rascunhoSalvo,
  salvando,
  reanexando,
  onReanexar,
  onConcluirSemDocumento,
  onDescartarRascunho,
  onAbrirRevisao,
}: {
  open: boolean;
  onClose: () => void;
  onIrCadastroManual: () => void;
  form: any;
  setForm: (fn: (f: any) => any) => void;
  areas: { slug: string; nome: string }[];
  clientes: Client[];
  advogados: User[];
  pendencia: IntakePendencia | null;
  rascunhoSalvo: IntakeRascunho | null;
  salvando: boolean;
  reanexando: boolean;
  onReanexar: () => void;
  onConcluirSemDocumento: () => void;
  onDescartarRascunho: () => void;
  onAbrirRevisao: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Novo caso por documento — IA assistida"
      wide
    >
      <div className="mb-5 flex flex-col gap-3 rounded-xl border border-primary-200 bg-primary-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-primary-800">
            1. Analise o documento · 2. Revise os dados · 3. Confirme a jornada
          </p>
          <p className="mt-1 text-xs leading-5 text-primary-700">
            Nada é gravado silenciosamente: cliente, caso, partes, área e prazos
            só são aplicados após sua conferência.
          </p>
        </div>
        <Button
          size="sm"
          variant="secondary"
          icon={<PenLine className="h-3.5 w-3.5" />}
          onClick={onIrCadastroManual}
        >
          Prefiro cadastrar sem IA
        </Button>
      </div>
      {pendencia && (
        <div className="mb-5 rounded-xl border border-warn-200 bg-warn-100 px-4 py-3">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn-700" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-warn-800">
                O caso “{pendencia.caseTitulo}” foi criado, mas{" "}
                {pendencia.batchId
                  ? "os documentos importados não foram vinculados."
                  : "o documento não foi anexado."}
              </p>
              <p className="mt-1 text-xs leading-5 text-warn-700">
                Nada foi perdido: o caso está salvo (em triagem)
                {pendencia.batchId
                  ? " e os arquivos do lote importado continuam no servidor. Tente vincular de novo — nenhum arquivo será duplicado."
                  : pendencia.arquivo
                    ? ` e o documento “${pendencia.arquivo.name}” continua aqui. Tente anexar de novo — o caso não será duplicado.`
                    : ` — só falta o documento “${pendencia.tituloDoc}”, que não sobreviveu ao recarregamento da página. Reenvie-o abaixo (o caso não será duplicado) ou anexe-o pela GED do caso.`}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {(pendencia.batchId || pendencia.arquivo) && (
                  <Button
                    size="sm"
                    variant="primary"
                    icon={<RotateCw className="h-3.5 w-3.5" />}
                    onClick={onReanexar}
                    disabled={reanexando}
                  >
                    {reanexando
                      ? pendencia.batchId
                        ? "Vinculando..."
                        : "Anexando..."
                      : pendencia.batchId
                        ? "Tentar vincular novamente"
                        : "Tentar anexar novamente"}
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={onConcluirSemDocumento}
                  disabled={reanexando}
                >
                  Concluir sem o documento
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
      {!pendencia && rascunhoSalvo && (
        <div className="mb-5 rounded-xl border border-primary-200 bg-primary-50 px-4 py-3">
          <div className="flex items-start gap-2">
            <FileUp className="mt-0.5 h-4 w-4 shrink-0 text-primary-600" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-primary-800">
                Cadastro por documento não finalizado
              </p>
              <p className="mt-1 text-xs leading-5 text-primary-700">
                {rascunhoSalvo.arquivoNome
                  ? `Havia um cadastro em andamento com o documento “${rascunhoSalvo.arquivoNome}”. `
                  : "Havia um cadastro por documento em andamento. "}
                Reenvie o documento abaixo para retomar, ou descarte este
                rascunho.
              </p>
              <div className="mt-3">
                <Button size="sm" variant="ghost" onClick={onDescartarRascunho}>
                  Descartar rascunho
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
      <ImportarDocumento
        onPrefill={(p) => setForm((f: any) => ({ ...f, ...p }))}
      />
      {/* ── Cliente & responsável ── */}
      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400 border-b border-slate-100 pb-1.5 mb-3">
        Cliente & responsável
      </p>
      <div className="grid sm:grid-cols-2 gap-4 mb-5">
        <div>
          <label className="label">Cliente *</label>
          <select
            className="input"
            value={form.client_id || ""}
            onChange={(e) => setForm({ ...form, client_id: e.target.value })}
          >
            <option value="">Selecione...</option>
            {clientes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nome || c.razao_social}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Advogado responsável</label>
          <select
            className="input"
            value={form.advogado_responsavel_id || ""}
            onChange={(e) =>
              setForm({ ...form, advogado_responsavel_id: e.target.value })
            }
          >
            <option value="">Eu mesmo (padrão)</option>
            {advogados.map((u) => (
              <option key={u.id} value={u.id}>
                {u.full_name}
                {u.oab_number ? ` — OAB ${u.oab_number}` : ""}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* ── Classificação ── */}
      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400 border-b border-slate-100 pb-1.5 mb-3">
        Classificação
      </p>
      <div className="grid sm:grid-cols-2 gap-4 mb-5">
        <div className="sm:col-span-2">
          <label className="label">Título *</label>
          <input
            className="input"
            value={form.titulo || ""}
            onChange={(e) => setForm({ ...form, titulo: e.target.value })}
          />
        </div>
        <div>
          <label className="label">Área *</label>
          <select
            className="input"
            value={form.area}
            onChange={(e) => setForm({ ...form, area: e.target.value })}
          >
            {areas.map((a) => (
              <option key={a.slug} value={a.slug}>
                {a.nome}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Prioridade</label>
          <select
            className="input"
            value={form.prioridade}
            onChange={(e) => setForm({ ...form, prioridade: e.target.value })}
          >
            <option value="baixa">Baixa</option>
            <option value="media">Média</option>
            <option value="alta">Alta</option>
            <option value="critica">Crítica</option>
          </select>
        </div>
        <SigiloReforcadoField
          checked={!!form.sigilo_reforcado}
          onChange={(v) => setForm({ ...form, sigilo_reforcado: v })}
        />
        <div>
          <label className="label">Tipo de caso</label>
          <select
            className="input"
            value={form.case_type}
            onChange={(e) =>
              setForm({
                ...form,
                case_type: e.target.value,
                extrajudicial_type:
                  e.target.value === "extrajudicial"
                    ? form.extrajudicial_type
                    : undefined,
              })
            }
          >
            {CASE_TYPES.map((t) => (
              <option key={t.k} value={t.k}>
                {t.l}
              </option>
            ))}
          </select>
        </div>
        {form.case_type === "extrajudicial" && (
          <div>
            <label className="label">Subtipo extrajudicial</label>
            <select
              className="input"
              value={form.extrajudicial_type || ""}
              onChange={(e) =>
                setForm({ ...form, extrajudicial_type: e.target.value })
              }
            >
              <option value="">Selecione...</option>
              {EXTRAJ_TYPES.map((t) => (
                <option key={t.k} value={t.k}>
                  {t.l}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* ── Localização processual ── */}
      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400 border-b border-slate-100 pb-1.5 mb-3">
        Localização processual
      </p>
      <div className="grid sm:grid-cols-2 gap-4 mb-5">
        <div>
          <label className="label">Nº do processo (se houver)</label>
          <input
            className="input"
            value={form.numero_processo || ""}
            onChange={(e) =>
              setForm({ ...form, numero_processo: e.target.value })
            }
            placeholder="0000000-00.0000.0.00.0000"
          />
        </div>
        <div>
          <label className="label">Tribunal</label>
          <input
            className="input"
            value={form.tribunal || ""}
            onChange={(e) => setForm({ ...form, tribunal: e.target.value })}
            placeholder="TJMG, TRT-3, STJ..."
          />
        </div>
        <div>
          <label className="label">Comarca</label>
          <input
            className="input"
            value={form.comarca || ""}
            onChange={(e) => setForm({ ...form, comarca: e.target.value })}
            placeholder="Betim/MG"
          />
        </div>
        <div>
          <label className="label">Vara</label>
          <input
            className="input"
            value={form.vara || ""}
            onChange={(e) => setForm({ ...form, vara: e.target.value })}
            placeholder="5ª Vara Cível"
          />
        </div>
        <div className="sm:col-span-2">
          <label className="label">Parte contrária</label>
          <input
            className="input"
            value={form.parte_contraria || ""}
            onChange={(e) =>
              setForm({ ...form, parte_contraria: e.target.value })
            }
          />
        </div>
      </div>

      {/* ── Prazo prescricional / decadencial ── */}
      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400 border-b border-slate-100 pb-1.5 mb-3">
        Prazo prescricional / decadencial
      </p>
      <div className="grid sm:grid-cols-2 gap-4 mb-2">
        <div>
          <label className="label">Tipo de pretensão</label>
          <select
            className="input"
            value={form.tipo_acao_prescricao || ""}
            onChange={(e) =>
              setForm({ ...form, tipo_acao_prescricao: e.target.value })
            }
          >
            <option value="">Não calcular agora</option>
            {PRESCRICAO.map((g) => (
              <optgroup key={g.grupo} label={g.grupo}>
                {g.itens.map((i) => (
                  <option key={i.k} value={i.k}>
                    {i.nm} · {i.base}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>
        <div>
          <label className="label">
            Termo inicial (fato / violação / ciência)
          </label>
          <input
            className="input"
            type="date"
            value={form.data_fato_prescricao || ""}
            onChange={(e) =>
              setForm({ ...form, data_fato_prescricao: e.target.value })
            }
          />
        </div>
      </div>
      <p className="text-[11px] text-warn-800 bg-warn-50 border border-warn-200 rounded-md px-3 py-2 mb-5">
        Minuta automática (revisão obrigatória): informando o tipo + termo
        inicial, o sistema calcula a data-limite na abertura do caso. Suspensões
        e interrupções (CC arts. 197–204) e particularidades do caso devem ser
        conferidas pelo advogado.
      </p>

      {/* ── Valor & fatos ── */}
      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400 border-b border-slate-100 pb-1.5 mb-3">
        Valor & fatos
      </p>
      <div className="grid sm:grid-cols-2 gap-4">
        <div>
          <label className="label">Valor da causa (R$)</label>
          <input
            className="input"
            type="number"
            value={form.valor_causa || ""}
            onChange={(e) => setForm({ ...form, valor_causa: e.target.value })}
          />
        </div>
        <div className="sm:col-span-2">
          <label className="label">
            Descrição dos fatos (usada pela IA p/ sugerir teses)
          </label>
          <textarea
            className="input min-h-[100px]"
            value={form.descricao_fatos || ""}
            onChange={(e) =>
              setForm({ ...form, descricao_fatos: e.target.value })
            }
          />
        </div>
        <div className="sm:col-span-2">
          <label className="label">Próxima ação *</label>
          <input
            className="input"
            placeholder="Ex.: Protocolar contestação, Agendar reunião"
            value={form.proxima_acao || ""}
            onChange={(e) => setForm({ ...form, proxima_acao: e.target.value })}
          />
          <p className="mt-1 text-xs text-slate-400">
            O que precisa ser feito agora neste caso? Obrigatório para casos
            ativos.
          </p>
        </div>
      </div>
      <div className="flex justify-end mt-5">
        <button
          className="btn-primary"
          disabled={salvando}
          onClick={onAbrirRevisao}
        >
          {salvando ? "Criando caso..." : "Revisar e criar o caso"}
        </button>
      </div>
    </Modal>
  );
}
