// ── components/CalculadorasJuridicas.tsx ────────────────────────────────────
// V2-5.1 (plano-mestre): expõe as calculadoras jurídicas determinísticas que
// já existem no backend mas nenhuma tela consumia. Form-runner genérico —
// nunca hardcode por ferramenta: campos vêm de config/calculadorasJuridicas.ts,
// resultado é renderizado por FORMA do valor (não por endpoint), justamente
// para que as ~44 ferramentas restantes do mesmo padrão entrem só como novas
// entradas na config, sem tocar este componente.
import { useMemo, useState } from "react";
import { Calculator, Gavel, Loader2, Scale } from "lucide-react";
import api from "../lib/api";
import { Alert, Badge, Button, Card, FieldLabel, Input, Select } from "./UI";
import {
  CALCULADORAS_JURIDICAS,
  type CampoConfig,
  type FerramentaConfig,
} from "../config/calculadorasJuridicas";

type ValoresFormulario = Record<string, string | number | boolean | undefined>;

const ICONE_AREA: Record<string, typeof Scale> = {
  Cível: Scale,
  Penal: Gavel,
};

function valoresIniciais(config: FerramentaConfig): ValoresFormulario {
  const valores: ValoresFormulario = {};
  for (const campo of config.campos) {
    if (campo.valorPadrao !== undefined) valores[campo.nome] = campo.valorPadrao;
  }
  return valores;
}

function mensagemErro(erro: unknown): string {
  const detail = (erro as { response?: { data?: { detail?: unknown } } })?.response?.data
    ?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (item && typeof item === "object" && "msg" in item ? String(item.msg) : String(item)))
      .join("; ");
  }
  return "Não foi possível calcular. Tente novamente.";
}

function serializarParams(
  campos: CampoConfig[],
  valores: ValoresFormulario,
): Record<string, string | number | boolean> {
  const params: Record<string, string | number | boolean> = {};
  for (const campo of campos) {
    const valor = valores[campo.nome];
    if (valor === undefined || valor === "") continue; // omite opcionais vazios
    params[campo.nome] = valor;
  }
  return params;
}

export default function CalculadorasJuridicas() {
  const areas = useMemo(
    () => Array.from(new Set(CALCULADORAS_JURIDICAS.map((f) => f.area))),
    [],
  );
  const [selecionada, setSelecionada] = useState<FerramentaConfig>(
    CALCULADORAS_JURIDICAS[0],
  );

  return (
    <div className="space-y-4">
      {areas.map((area) => {
        const IconeArea = ICONE_AREA[area] ?? Calculator;
        return (
          <div key={area}>
            <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              <IconeArea className="h-3.5 w-3.5" />
              {area}
            </p>
            <div className="flex flex-wrap gap-2">
              {CALCULADORAS_JURIDICAS.filter((f) => f.area === area).map((ferramenta) => (
                <button
                  key={ferramenta.chave}
                  type="button"
                  onClick={() => setSelecionada(ferramenta)}
                  className={
                    ferramenta.chave === selecionada.chave
                      ? "rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-semibold text-white"
                      : "rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:border-primary-200 dark:border-white/10 dark:bg-white/[0.02] dark:text-slate-200"
                  }
                >
                  {ferramenta.titulo}
                </button>
              ))}
            </div>
          </div>
        );
      })}

      <FormularioCalculadora key={selecionada.chave} config={selecionada} />
    </div>
  );
}

function FormularioCalculadora({ config }: { config: FerramentaConfig }) {
  const [valores, setValores] = useState<ValoresFormulario>(() => valoresIniciais(config));
  const [resultado, setResultado] = useState<Record<string, unknown> | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const camposVisiveis = config.campos.filter((c) => !c.exibirSe || c.exibirSe(valores));
  const valido = camposVisiveis.every((c) => {
    if (!c.obrigatorio) return true;
    const v = valores[c.nome];
    return v !== undefined && v !== "";
  });

  const alterarCampo = (nome: string, valor: string | number | boolean | undefined) => {
    setValores((atual) => ({ ...atual, [nome]: valor }));
  };

  const calcular = async () => {
    setCarregando(true);
    setErro(null);
    setResultado(null);
    try {
      const params = serializarParams(camposVisiveis, valores);
      const { data } = await api.get(config.endpoint, { params });
      setResultado(data);
    } catch (e) {
      setErro(mensagemErro(e));
    } finally {
      setCarregando(false);
    }
  };

  return (
    <Card className="space-y-4 p-4">
      <div>
        <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-50">
          {config.titulo}
        </h3>
        <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-300">
          {config.descricao}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {camposVisiveis.map((campo) => (
          <CampoFormulario
            key={campo.nome}
            campo={campo}
            valor={valores[campo.nome]}
            onChange={(v) => alterarCampo(campo.nome, v)}
          />
        ))}
      </div>

      <div className="flex items-center gap-3">
        <Button
          onClick={calcular}
          disabled={!valido || carregando}
          icon={carregando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Calculator className="h-4 w-4" />}
        >
          {carregando ? "Calculando…" : "Calcular"}
        </Button>
      </div>

      {erro && <Alert variant="danger">{erro}</Alert>}
      {resultado && <ResultadoCalculadora data={resultado} />}
    </Card>
  );
}

function CampoFormulario({
  campo,
  valor,
  onChange,
}: {
  campo: CampoConfig;
  valor: string | number | boolean | undefined;
  onChange: (valor: string | number | boolean | undefined) => void;
}) {
  if (campo.tipo === "boolean") {
    return (
      <label className="flex items-center gap-2 pt-5 text-sm text-slate-700 dark:text-slate-200">
        <input
          type="checkbox"
          checked={Boolean(valor)}
          onChange={(e) => onChange(e.target.checked)}
          className="h-4 w-4 rounded border-slate-300"
        />
        {campo.label}
      </label>
    );
  }

  if (campo.tipo === "select" || campo.tipo === "sim_nao") {
    const opcoes = campo.tipo === "sim_nao"
      ? [{ value: "sim", label: "Sim" }, { value: "nao", label: "Não" }]
      : campo.opcoes ?? [];
    return (
      <div>
        <FieldLabel required={campo.obrigatorio}>{campo.label}</FieldLabel>
        <Select
          value={typeof valor === "string" ? valor : ""}
          onChange={(e) => onChange(e.target.value || undefined)}
        >
          <option value="">Selecione…</option>
          {opcoes.map((opcao) => (
            <option key={opcao.value} value={opcao.value}>
              {opcao.label}
            </option>
          ))}
        </Select>
        {campo.ajuda && <p className="mt-1 text-xs text-slate-400">{campo.ajuda}</p>}
      </div>
    );
  }

  return (
    <div>
      <FieldLabel required={campo.obrigatorio}>{campo.label}</FieldLabel>
      <Input
        type={campo.tipo === "number" ? "number" : campo.tipo === "date" ? "date" : "text"}
        min={campo.min}
        max={campo.max}
        value={valor === undefined ? "" : String(valor)}
        onChange={(e) => {
          const raw = e.target.value;
          if (campo.tipo === "number") {
            onChange(raw === "" ? undefined : Number(raw));
          } else {
            onChange(raw === "" ? undefined : raw);
          }
        }}
      />
      {campo.ajuda && <p className="mt-1 text-xs text-slate-400">{campo.ajuda}</p>}
    </div>
  );
}

// ── Renderizador genérico de resultado ───────────────────────────────────
// Trata por FORMA do valor, não por endpoint — "razoável, não perfeito":
// cobre os 6 formatos reais já lidos no código-fonte; formato futuro não
// previsto cai no fallback JSON.stringify (aceitável para o MVP).
const CHAVES_RODAPE = new Set(["vigencia_regra", "versao_regra"]);
const CHAVES_JA_TRATADAS = new Set(["aviso", "fontes", ...CHAVES_RODAPE]);

function prettificar(chave: string): string {
  return chave.charAt(0).toUpperCase() + chave.slice(1).replace(/_/g, " ");
}

function ResultadoCalculadora({ data }: { data: Record<string, unknown> }) {
  const aviso = typeof data.aviso === "string" ? data.aviso : null;
  const fontes = Array.isArray(data.fontes) ? (data.fontes as unknown[]) : null;
  const booleans = Object.entries(data).filter(([, v]) => typeof v === "boolean");
  const rodape = Object.entries(data).filter(([k]) => CHAVES_RODAPE.has(k));
  const resto = Object.entries(data).filter(
    ([k, v]) => !CHAVES_JA_TRATADAS.has(k) && typeof v !== "boolean",
  );

  return (
    <div className="space-y-3 border-t border-slate-100 pt-3 dark:border-white/10">
      {aviso && <Alert variant="warning">{aviso}</Alert>}

      {booleans.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {booleans.map(([chave, valor]) => (
            <Badge key={chave} tone={valor ? "green" : "red"}>
              {prettificar(chave)}: {valor ? "Sim" : "Não"}
            </Badge>
          ))}
        </div>
      )}

      {resto.map(([chave, valor]) => (
        <ValorResultado key={chave} rotulo={prettificar(chave)} valor={valor} />
      ))}

      {fontes && fontes.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Fontes
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm text-slate-700 dark:text-slate-200">
            {fontes.map((f, i) => (
              <li key={i}>{String(f)}</li>
            ))}
          </ul>
        </div>
      )}

      {rodape.length > 0 && (
        <p className="text-xs text-slate-400">
          {rodape.map(([, v]) => String(v)).join(" · ")}
        </p>
      )}
    </div>
  );
}

function ValorResultado({ rotulo, valor }: { rotulo: string; valor: unknown }) {
  if (valor === null || valor === undefined || valor === "") return null;

  if (typeof valor === "string" || typeof valor === "number") {
    return (
      <p className="text-sm text-slate-700 dark:text-slate-200">
        <span className="font-semibold text-slate-950 dark:text-slate-50">{rotulo}:</span>{" "}
        {String(valor)}
      </p>
    );
  }

  if (Array.isArray(valor)) {
    if (valor.length === 0) return null;
    const todosPrimitivos = valor.every((v) => typeof v === "string" || typeof v === "number");
    if (todosPrimitivos) {
      return (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{rotulo}</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm text-slate-700 dark:text-slate-200">
            {valor.map((v, i) => (
              <li key={i}>{String(v)}</li>
            ))}
          </ul>
        </div>
      );
    }
    // Array de objetos (ex.: `prazos`, `requisitos[]`): cada item vira um card.
    return (
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{rotulo}</p>
        <div className="mt-1 space-y-1.5">
          {valor.map((item, i) => (
            <ItemLista key={i} item={item} />
          ))}
        </div>
      </div>
    );
  }

  if (typeof valor === "object") {
    const entradas = Object.entries(valor as Record<string, unknown>).filter(
      ([, v]) => v !== null && v !== undefined && v !== "",
    );
    if (entradas.length === 0) return null;
    return (
      <div className="rounded-lg bg-slate-50 p-3 dark:bg-white/[0.04]">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{rotulo}</p>
        <div className="mt-1 space-y-0.5 text-sm text-slate-700 dark:text-slate-200">
          {entradas.map(([k, v]) => (
            <p key={k}>
              <span className="font-medium">{prettificar(k)}:</span>{" "}
              {typeof v === "object" ? JSON.stringify(v) : String(v)}
            </p>
          ))}
        </div>
      </div>
    );
  }

  return null;
}

function ItemLista({ item }: { item: unknown }) {
  if (typeof item === "string") {
    return <p className="rounded-lg bg-slate-50 p-2 text-sm dark:bg-white/[0.04]">{item}</p>;
  }
  if (!item || typeof item !== "object") {
    return <p className="rounded-lg bg-slate-50 p-2 text-sm dark:bg-white/[0.04]">{String(item)}</p>;
  }
  const obj = item as Record<string, unknown>;
  const titulo =
    obj.titulo ?? obj.evento ?? obj.requisito ?? obj.parcela ?? Object.values(obj)[0];
  const status = typeof obj.atendido === "boolean" ? obj.atendido : undefined;
  const demais = Object.entries(obj).filter(
    ([k, v]) =>
      !["titulo", "evento", "requisito", "parcela", "atendido"].includes(k) &&
      v !== null &&
      v !== undefined &&
      v !== "" &&
      typeof v !== "object",
  );
  return (
    <div className="rounded-lg bg-slate-50 p-2.5 dark:bg-white/[0.04]">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-slate-900 dark:text-slate-50">{String(titulo)}</p>
        {status !== undefined && (
          <Badge tone={status ? "green" : "red"}>{status ? "Atendido" : "Pendente"}</Badge>
        )}
      </div>
      {demais.length > 0 && (
        <div className="mt-1 space-y-0.5 text-xs text-slate-500 dark:text-slate-300">
          {demais.map(([k, v]) => (
            <p key={k}>
              {prettificar(k)}: {String(v)}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
