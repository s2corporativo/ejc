import { useEffect, useState } from "react";
import { Scale } from "lucide-react";

import api from "../lib/api";

type Grupo = {
  n: number;
  n_com_desfecho: number;
  procedencia: number;
  procedencia_parcial: number;
  improcedencia: number;
  acordo: number;
  sem_resolucao_merito: number;
  decididos_merito: number;
  taxa_procedencia: number | null;
  intervalo_confianca_95_procedencia?: {
    inferior: number;
    superior: number;
    nivel: number;
    metodo: string;
  } | null;
  taxa_acordo: number | null;
  intervalo_confianca_95_acordo?: {
    inferior: number;
    superior: number;
    nivel: number;
    metodo: string;
  } | null;
  amostra_pequena: boolean;
  tempo_sentenca: {
    n: number;
    mediana_dias: number | null;
    media_dias: number | null;
  };
};

type RecorteComplementar = {
  disponivel: boolean;
  fonte: string;
  escopo: {
    tribunal: string;
    segmento?: string;
    regiao?: string;
    municipios?: string[];
  };
  coleta?: {
    cache: boolean;
    coletado_em: string | null;
    n_documentos: number;
    truncado?: boolean;
    derivado_sem_nova_consulta?: boolean;
  };
  total?: Grupo;
  por_assunto?: Array<Grupo & { assunto_codigo: string; assunto: string }>;
  amostra_truncada?: boolean;
  aviso_amostragem?: string;
  erro?: string;
};

type Desfechos = {
  fonte: string;
  escopo: { tribunal: string; municipios: string[] };
  coleta: {
    cache: boolean;
    coletado_em: string | null;
    n_documentos: number;
    truncado?: boolean;
  };
  tpu: { versao: string };
  min_amostra: number;
  limitacoes: string[];
  total: Grupo;
  por_municipio: Array<Grupo & { municipio: string; nome: string }>;
  por_assunto: Array<Grupo & { assunto_codigo: string; assunto: string }>;
  por_municipio_assunto?: Array<
    Grupo & {
      municipio: string;
      municipio_nome: string;
      assunto_codigo: string;
      assunto: string;
    }
  >;
  amostra_truncada?: boolean;
  aviso_amostragem?: string;
  reforma_2grau: {
    n_com_recurso_julgado: number;
    provimento: number;
    provimento_parcial: number;
    nao_provimento: number;
    taxa_reforma: number | null;
    intervalo_confianca_95_reforma?: {
      inferior: number;
      superior: number;
      nivel: number;
      metodo: string;
    } | null;
    amostra_pequena: boolean;
    disponivel?: boolean;
    motivo?: string;
  };
  fontes_complementares?: {
    jec_tjmg?: RecorteComplementar;
    trt3?: RecorteComplementar;
  };
};

type Status = {
  habilitado: boolean;
  datajud_habilitado: boolean;
  tpu_versao: string;
};

function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${(v * 100).toFixed(1)}%`;
}

function pctGrupo(g: Grupo): string {
  return pct(g.amostra_pequena ? null : g.taxa_procedencia);
}

function ic95(
  valor:
    | { inferior: number; superior: number; nivel?: number; metodo?: string }
    | null
    | undefined,
): string | null {
  return valor
    ? `IC95% ${valor.inferior.toFixed(1)}%–${valor.superior.toFixed(1)}%`
    : null;
}

function Taxa({
  rotulo,
  valor,
  sub,
  pequena,
  intervalo,
}: {
  rotulo: string;
  valor: string;
  sub: string;
  pequena?: boolean;
  intervalo?: string | null;
}) {
  return (
    <div className="text-center p-3 bg-gray-50 rounded-lg border border-black/[0.05]">
      <p className="text-2xl font-bold text-gray-800">{valor}</p>
      <p className="text-xs text-gray-500">{rotulo}</p>
      <p className="text-[11px] text-gray-400">{sub}</p>
      {!pequena && intervalo && (
        <p className="text-[11px] text-gray-400">{intervalo}</p>
      )}
      {pequena && (
        <p className="text-[11px] text-amber-700 mt-1">
          amostra pequena — taxa não publicada
        </p>
      )}
    </div>
  );
}

function RecorteExterno({
  titulo,
  recorte,
}: {
  titulo: string;
  recorte?: RecorteComplementar;
}) {
  if (!recorte) return null;
  if (!recorte.disponivel || !recorte.total) {
    return (
      <div className="border border-black/[0.05] rounded-lg p-4">
        <h4 className="text-xs font-semibold text-gray-700 uppercase mb-1">
          {titulo}
        </h4>
        <p className="text-xs text-gray-500">
          {recorte.erro || "Fonte temporariamente indisponível."}
        </p>
      </div>
    );
  }

  const pequena = recorte.total.amostra_pequena;
  return (
    <div className="border border-black/[0.05] rounded-lg p-4">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <h4 className="text-xs font-semibold text-gray-700 uppercase">
            {titulo}
          </h4>
          <p className="text-[11px] text-gray-400">
            {recorte.escopo.segmento ||
              recorte.escopo.regiao ||
              recorte.escopo.tribunal}
          </p>
        </div>
        <span className="text-[11px] text-gray-400">
          n={recorte.coleta?.n_documentos ?? recorte.total.n}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Taxa
          rotulo="Procedência"
          valor={pct(pequena ? null : recorte.total.taxa_procedencia)}
          sub={`${recorte.total.decididos_merito} decididos no mérito`}
          intervalo={ic95(recorte.total.intervalo_confianca_95_procedencia)}
          pequena={pequena}
        />
        <Taxa
          rotulo="Acordo"
          valor={pct(pequena ? null : recorte.total.taxa_acordo)}
          sub={`${recorte.total.acordo} homologados`}
          intervalo={ic95(recorte.total.intervalo_confianca_95_acordo)}
          pequena={pequena}
        />
      </div>
      {recorte.amostra_truncada && (
        <p className="text-[11px] text-amber-700 mt-2">
          Limite de coleta atingido: taxas suprimidas. Restrinja período,
          classe ou assunto.
        </p>
      )}
      <p className="text-[11px] text-gray-400 mt-2">
        Fonte: {recorte.fonte}. Desfecho por movimento TPU; não é previsão de
        resultado futuro.
      </p>
    </div>
  );
}

export default function JurimetriaTribunais() {
  const [status, setStatus] = useState<Status | null>(null);
  const [dados, setDados] = useState<Desfechos | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [indisponivel, setIndisponivel] = useState<string | null>(null);

  useEffect(() => {
    let ativo = true;
    (async () => {
      try {
        const s = await api.get<Status>("/jurimetria/tribunais/status");
        if (!ativo) return;
        setStatus(s.data);
        if (!s.data.habilitado || !s.data.datajud_habilitado) {
          setIndisponivel(
            "Jurimetria dos tribunais não configurada neste ambiente (JURIMETRIA_TRIBUNAIS_ENABLED e DataJud).",
          );
          return;
        }
        const r = await api.get<Desfechos>("/jurimetria/tribunais/desfechos");
        if (ativo) setDados(r.data);
      } catch (e: any) {
        if (!ativo) return;
        const st = e?.response?.status;
        setIndisponivel(
          st === 503
            ? "Jurimetria dos tribunais não configurada neste ambiente."
            : st === 502
              ? "DataJud indisponível no momento. Tente novamente mais tarde."
              : "Não foi possível carregar a jurimetria dos tribunais.",
        );
      } finally {
        if (ativo) setCarregando(false);
      }
    })();
    return () => {
      ativo = false;
    };
  }, []);

  return (
    <section
      className="card p-5 mb-6"
      aria-labelledby="jurimetria-tribunais-titulo"
    >
      <div className="flex items-center gap-1.5 mb-1">
        <Scale size={16} className="text-primary-500" />
        <h3
          id="jurimetria-tribunais-titulo"
          className="font-semibold text-sm text-gray-700 uppercase"
        >
          Tribunais — TJMG, JEC/Turmas Recursais e TRT3
        </h3>
      </div>
      <p className="text-xs text-gray-500 mb-2">
        Histórico externo a partir do DataJud/CNJ. Não é o desempenho do
        escritório — esse permanece nos painéis de base interna.
      </p>
      <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-4">
        Revisão humana obrigatória: estes indicadores apoiam a estratégia do
        advogado, mas não substituem leitura dos autos, pesquisa dos precedentes
        aplicáveis nem avaliação profissional do caso concreto.
      </p>

      {carregando && (
        <p className="text-sm text-gray-500">Consultando o DataJud…</p>
      )}

      {!carregando && indisponivel && (
        <p
          className="text-sm text-gray-600 bg-gray-50 border border-black/[0.05] rounded-lg p-3"
          role="status"
        >
          {indisponivel}
        </p>
      )}

      {!carregando && dados && (
        <>
          {dados.amostra_truncada && (
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-3">
              Limite máximo de registros atingido. As contagens permanecem
              visíveis, mas taxas e tempos foram suprimidos. Restrinja período,
              classe ou assunto para um recorte não truncado.
            </p>
          )}

          <div className="mb-3">
            <h4 className="text-xs font-semibold text-gray-600 uppercase mb-2">
              TJMG — Betim, Contagem e Belo Horizonte
            </h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Taxa
                rotulo="Procedência (total + parcial)"
                valor={pct(
                  dados.total.amostra_pequena
                    ? null
                    : dados.total.taxa_procedencia,
                )}
                sub={`${dados.total.decididos_merito} decididos no mérito`}
                intervalo={ic95(
                  dados.total.intervalo_confianca_95_procedencia,
                )}
                pequena={dados.total.amostra_pequena}
              />
              <Taxa
                rotulo="Acordo homologado"
                valor={pct(
                  dados.total.amostra_pequena ? null : dados.total.taxa_acordo,
                )}
                sub={`${dados.total.acordo} de ${dados.total.n_com_desfecho} com desfecho`}
                intervalo={ic95(dados.total.intervalo_confianca_95_acordo)}
                pequena={dados.total.amostra_pequena}
              />
              <Taxa
                rotulo="Tempo até sentença (mediana)"
                valor={
                  dados.total.tempo_sentenca.mediana_dias != null
                    ? `${dados.total.tempo_sentenca.mediana_dias} dias`
                    : "—"
                }
                sub={`${dados.total.tempo_sentenca.n} sentenças de mérito com data`}
              />
              <Taxa
                rotulo="Reforma em 2º grau"
                valor={pct(dados.reforma_2grau.taxa_reforma)}
                sub={
                  dados.reforma_2grau.disponivel === false
                    ? "não publicada neste recorte geográfico"
                    : `${dados.reforma_2grau.n_com_recurso_julgado} recursos julgados na amostra`
                }
                intervalo={ic95(
                  dados.reforma_2grau.intervalo_confianca_95_reforma,
                )}
                pequena={
                  dados.reforma_2grau.disponivel !== false &&
                  dados.reforma_2grau.amostra_pequena
                }
              />
            </div>
          </div>

          <div className="grid md:grid-cols-2 gap-4 mt-4">
            <RecorteExterno
              titulo="Juizados Especiais / Turmas Recursais — TJMG"
              recorte={dados.fontes_complementares?.jec_tjmg}
            />
            <RecorteExterno
              titulo="Justiça do Trabalho — TRT3/MG"
              recorte={dados.fontes_complementares?.trt3}
            />
          </div>

          <div className="grid md:grid-cols-2 gap-4 mt-4">
            <div>
              <h4 className="text-xs font-semibold text-gray-600 uppercase mb-2">
                Por município — TJMG
              </h4>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-500">
                    <th className="py-1">Município</th>
                    <th className="py-1 text-right">n</th>
                    <th className="py-1 text-right">Procedência</th>
                    <th className="py-1 text-right">Acordo</th>
                  </tr>
                </thead>
                <tbody>
                  {dados.por_municipio.map((m) => (
                    <tr
                      key={m.municipio}
                      className="border-t border-black/[0.05]"
                    >
                      <td className="py-1">{m.nome}</td>
                      <td className="py-1 text-right">{m.n}</td>
                      <td className="py-1 text-right" title={
                          m.amostra_pequena
                            ? "amostra pequena"
                            : ic95(m.intervalo_confianca_95_procedencia) ?? undefined
                        }>
                        {pctGrupo(m)}
                      </td>
                      <td className="py-1 text-right">
                        {pct(m.amostra_pequena ? null : m.taxa_acordo)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div>
              <h4 className="text-xs font-semibold text-gray-600 uppercase mb-2">
                Por assunto — TJMG (top 8)
              </h4>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-500">
                    <th className="py-1">Assunto</th>
                    <th className="py-1 text-right">n</th>
                    <th className="py-1 text-right">Procedência</th>
                  </tr>
                </thead>
                <tbody>
                  {dados.por_assunto.slice(0, 8).map((a) => (
                    <tr
                      key={a.assunto_codigo || a.assunto}
                      className="border-t border-black/[0.05]"
                    >
                      <td className="py-1">{a.assunto}</td>
                      <td className="py-1 text-right">{a.n}</td>
                      <td className="py-1 text-right" title={
                          a.amostra_pequena
                            ? "amostra pequena"
                            : ic95(a.intervalo_confianca_95_procedencia) ?? undefined
                        }>
                        {pctGrupo(a)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {(dados.por_municipio_assunto?.length ?? 0) > 0 && (
            <div className="mt-4">
              <h4 className="text-xs font-semibold text-gray-600 uppercase mb-2">
                Município × assunto — TJMG (top 10)
              </h4>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-500">
                    <th className="py-1">Município</th>
                    <th className="py-1">Assunto</th>
                    <th className="py-1 text-right">n</th>
                    <th className="py-1 text-right">Procedência</th>
                  </tr>
                </thead>
                <tbody>
                  {dados.por_municipio_assunto?.slice(0, 10).map((r) => (
                    <tr
                      key={`${r.municipio}:${r.assunto_codigo}:${r.assunto}`}
                      className="border-t border-black/[0.05]"
                    >
                      <td className="py-1">{r.municipio_nome}</td>
                      <td className="py-1">{r.assunto}</td>
                      <td className="py-1 text-right">{r.n}</td>
                      <td className="py-1 text-right" title={
                          r.amostra_pequena
                            ? "amostra pequena"
                            : ic95(r.intervalo_confianca_95_procedencia) ?? undefined
                        }>
                        {pctGrupo(r)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="text-[11px] text-gray-400 mt-4">
            Fonte principal: {dados.fonte}. Amostra TJMG: {dados.coleta.n_documentos}{" "}
            registros{dados.coleta.truncado ? " (limite atingido)" : ""}
            {dados.coleta.coletado_em
              ? ` · coleta ${dados.coleta.coletado_em}`
              : ""}{" "}
            · TPU {dados.tpu.versao}. Desfecho inferido por código de movimento
            — proxy, não leitura da sentença.
          </p>
        </>
      )}

      {status && !status.habilitado && !carregando && (
        <p className="text-[11px] text-gray-400 mt-2">
          TPU de referência: versão {status.tpu_versao}.
        </p>
      )}
    </section>
  );
}
