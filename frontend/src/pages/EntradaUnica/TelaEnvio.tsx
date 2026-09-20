// Tela A da Entrada Única: estado inicial (relato + dropzone) e estado
// "analisando" com progresso honesto por etapa (wireframes A.1 e A.2 de
// docs/DESENHO_BLOCO3_TELAS.md).
// Variantes: "full" (página /entrada, relato + dropzone) e "pill" (herói da
// Entrada Única no Dashboard — pílula branca da referência DPT, mesma lógica,
// mesmas validações e mesmo fluxo de análise).
import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  FileText,
  Loader2,
  Paperclip,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { Button, Card, Textarea, cn } from "../../components/UI";
import { toast } from "../../components/Toast";
import type { EntradaMeta } from "./types";

export const MINIMO_RELATO = 40;

export function podeAnalisar(texto: string, arquivos: File[]): boolean {
  return texto.trim().length >= MINIMO_RELATO || arquivos.length >= 1;
}

function tamanhoTotal(arquivos: File[]): number {
  return arquivos.reduce((soma, f) => soma + f.size, 0);
}

export function TelaInicial({
  texto,
  onTexto,
  arquivos,
  onArquivos,
  meta,
  onAnalisar,
  variant = "full",
}: {
  texto: string;
  onTexto: (v: string) => void;
  arquivos: File[];
  onArquivos: (v: File[]) => void;
  meta: EntradaMeta;
  onAnalisar: () => void;
  variant?: "full" | "pill";
}) {
  const [arrastando, setArrastando] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const pillRef = useRef<HTMLTextAreaElement>(null);

  const adicionar = (novos: FileList | File[] | null) => {
    if (!novos) return;
    const candidatos = [...arquivos, ...Array.from(novos)];
    if (candidatos.length > meta.maxArquivos) {
      toast.error(`Limite de ${meta.maxArquivos} arquivos por envio`);
      return;
    }
    if (tamanhoTotal(candidatos) > meta.maxLoteMb * 1024 * 1024) {
      toast.error(`O lote excede ${meta.maxLoteMb} MB`);
      return;
    }
    onArquivos(candidatos);
  };

  const submeterPill = () => {
    if (!podeAnalisar(texto, arquivos)) {
      toast.info(
        `Descreva o caso com pelo menos ${MINIMO_RELATO} caracteres ou anexe um documento para analisar.`,
      );
      return;
    }
    onAnalisar();
  };

  // Pílula canônica do herói do Dashboard (referência DPT): mesma lógica da
  // TelaInicial — relato + anexos + análise — na superfície compacta branca.
  if (variant === "pill") {
    return (
      <div className="ejc-entry-pillzone">
        <div
          role="group"
          aria-label="Entrada Única: relato e documentos"
          onDragOver={(e) => {
            e.preventDefault();
            setArrastando(true);
          }}
          onDragLeave={() => setArrastando(false)}
          onDrop={(e) => {
            e.preventDefault();
            setArrastando(false);
            adicionar(e.dataTransfer?.files ?? null);
          }}
          className={cn("ejc-entry-pill", arrastando && "is-drag")}
        >
          <Sparkles className="ejc-entry-pill__spark" aria-hidden="true" />
          <textarea
            ref={pillRef}
            className="ejc-entry-pill__input"
            value={texto}
            onChange={(e) => onTexto(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submeterPill();
              }
            }}
            rows={1}
            placeholder="Digite aqui o seu pedido, descreva o caso ou anexe documentos…"
            aria-label="Relato do cliente"
          />
          <button
            type="button"
            className="ejc-entry-pill__clip"
            onClick={() => inputRef.current?.click()}
            aria-label="Anexar documentos"
          >
            <Paperclip aria-hidden="true" />
          </button>
          <button
            type="button"
            className="ejc-entry-pill__send"
            onClick={submeterPill}
            aria-label="Analisar relato e documentos"
          >
            <ArrowRight aria-hidden="true" />
          </button>
          <input
            ref={inputRef}
            data-testid="entrada-file-input"
            type="file"
            multiple
            accept={meta.formatos.join(",")}
            className="hidden"
            onChange={(e) => {
              adicionar(e.target.files);
              e.target.value = "";
            }}
          />
        </div>
        {arquivos.length > 0 && (
          <ul className="ejc-entry-pillzone__files">
            {arquivos.map((arquivo, i) => (
              <li key={`${arquivo.name}-${i}`}>
                <FileText aria-hidden="true" />
                <span>{arquivo.name}</span>
                <small>{(arquivo.size / 1024 / 1024).toFixed(1)} MB</small>
                <button
                  type="button"
                  aria-label={`Remover ${arquivo.name}`}
                  onClick={() => onArquivos(arquivos.filter((_, j) => j !== i))}
                >
                  <X aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <Textarea
        value={texto}
        onChange={(e) => onTexto(e.target.value)}
        placeholder="Cole aqui o que o cliente contou."
        rows={7}
        aria-label="Relato do cliente"
      />

      <div
        role="button"
        tabIndex={0}
        aria-label="Arraste documentos aqui ou clique para escolher"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setArrastando(true);
        }}
        onDragLeave={() => setArrastando(false)}
        onDrop={(e) => {
          e.preventDefault();
          setArrastando(false);
          adicionar(e.dataTransfer?.files ?? null);
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-all duration-150",
          arrastando
            ? "border-primary-500 bg-primary-50 shadow-card dark:bg-primary-900/20"
            : "border-slate-300 hover:border-primary-400 hover:bg-slate-50 hover:shadow-soft dark:border-slate-600",
        )}
      >
        <Upload
          className={cn(
            "h-6 w-6 transition-colors duration-150",
            arrastando ? "text-primary-600" : "text-slate-400",
          )}
          aria-hidden="true"
        />
        <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
          Arraste documentos aqui · ou clique para escolher
        </p>
        <p className="text-xs text-slate-500">
          PDF, DOCX, imagens, ZIP · até {meta.maxArquivos} arquivos,{" "}
          {meta.maxLoteMb} MB
        </p>
        <input
          ref={inputRef}
          data-testid="entrada-file-input"
          type="file"
          multiple
          accept={meta.formatos.join(",")}
          className="hidden"
          onChange={(e) => {
            adicionar(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {arquivos.length > 0 && (
        <Card className="divide-y divide-slate-100 p-0 dark:divide-slate-700">
          {arquivos.map((arquivo, i) => (
            <div
              key={`${arquivo.name}-${i}`}
              className="flex items-center gap-3 px-4 py-2.5 text-sm"
            >
              <FileText
                className="h-4 w-4 shrink-0 text-slate-400"
                aria-hidden="true"
              />
              <span className="min-w-0 flex-1 truncate text-slate-700 dark:text-slate-200">
                {arquivo.name}
              </span>
              <span className="shrink-0 text-xs text-slate-400">
                {(arquivo.size / 1024 / 1024).toFixed(1)} MB
              </span>
              <button
                type="button"
                aria-label={`Remover ${arquivo.name}`}
                onClick={() => onArquivos(arquivos.filter((_, j) => j !== i))}
                className="shrink-0 rounded p-1 text-slate-400 hover:text-danger-500"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
        </Card>
      )}

      <div className="flex justify-end">
        <Button
          size="lg"
          disabled={!podeAnalisar(texto, arquivos)}
          onClick={onAnalisar}
        >
          Analisar
        </Button>
      </div>
    </div>
  );
}

type EstadoEtapa = "feita" | "andamento" | "pendente";

function IconeEtapa({ estado }: { estado: EstadoEtapa }) {
  if (estado === "feita") {
    return (
      <CheckCircle2
        className="h-4 w-4 text-success-600 dark:text-success-300"
        aria-hidden="true"
      />
    );
  }
  if (estado === "andamento") {
    return (
      <Loader2
        className="h-4 w-4 animate-spin text-primary-500"
        aria-hidden="true"
      />
    );
  }
  return (
    <span
      className="inline-block h-4 w-4 rounded-full border border-slate-300"
      aria-hidden="true"
    />
  );
}

/**
 * Progresso otimista/temporal: o POST é um só, então a única etapa medida de
 * verdade é o upload (onUploadProgress). As demais avançam por tempo — o que
 * importa é não parecer travamento durante OCR longo.
 */
export function TelaAnalisando({
  numArquivos,
  uploadPct,
}: {
  numArquivos: number;
  uploadPct: number;
}) {
  const uploadConcluido = uploadPct >= 100;
  const [etapaTemporal, setEtapaTemporal] = useState(0);

  useEffect(() => {
    if (!uploadConcluido) return;
    const t1 = window.setTimeout(() => setEtapaTemporal(1), 2000);
    const t2 = window.setTimeout(() => setEtapaTemporal(2), 5000);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [uploadConcluido]);

  const etapas: { rotulo: string; detalhe?: string; estado: EstadoEtapa }[] = [
    {
      rotulo: "Documentos recebidos e preservados",
      detalhe:
        numArquivos > 0
          ? `${numArquivos} arquivo${numArquivos > 1 ? "s" : ""}`
          : "sem arquivos",
      estado: uploadConcluido ? "feita" : "andamento",
    },
    {
      rotulo: "Texto extraído",
      estado: !uploadConcluido
        ? "pendente"
        : etapaTemporal >= 1
          ? "feita"
          : "andamento",
    },
    {
      rotulo: "Classificando e cruzando com o relato",
      estado:
        !uploadConcluido || etapaTemporal < 1
          ? "pendente"
          : etapaTemporal >= 2
            ? "feita"
            : "andamento",
    },
    {
      rotulo: "Procurando o cliente na base",
      estado: etapaTemporal >= 2 ? "andamento" : "pendente",
    },
  ];

  return (
    <div className="mx-auto max-w-2xl">
      <Card className="space-y-4 p-6">
        <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
          Analisando…
        </h2>
        <ul className="space-y-3">
          {etapas.map((etapa) => (
            <li key={etapa.rotulo} className="flex items-center gap-3 text-sm">
              <IconeEtapa estado={etapa.estado} />
              <span
                className={cn(
                  "flex-1",
                  etapa.estado === "pendente"
                    ? "text-slate-400"
                    : "text-slate-700 dark:text-slate-200",
                )}
              >
                {etapa.rotulo}
              </span>
              {etapa.detalhe && (
                <span className="text-xs text-slate-400">{etapa.detalhe}</span>
              )}
            </li>
          ))}
        </ul>
        {!uploadConcluido && numArquivos > 0 && (
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700">
            <div
              className="h-full rounded-full bg-primary-500 transition-all"
              style={{ width: `${Math.min(uploadPct, 100)}%` }}
            />
          </div>
        )}
        {uploadConcluido && (
          <p className="text-xs text-slate-500">
            Os originais já estão salvos. Se algo falhar daqui em diante, nada
            se perde.
          </p>
        )}
      </Card>
    </div>
  );
}
