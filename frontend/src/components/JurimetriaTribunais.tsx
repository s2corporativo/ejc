import { useEffect, useState } from "react";
import { Scale } from "lucide-react";

import api from "../lib/api";

/**
 * Jurimetria dos TRIBUNAIS (Issue #1527): como o TJMG — Betim, Contagem e
 * Belo Horizonte — decide cada assunto, a partir do DataJud/CNJ. Coexiste
 * com a jurimetria do escritório na mesma página, rotulada: o leitor nunca
 * deve confundir "o tribunal decide assim" com "o escritório obteve isso".
 *
 * Contrato: GET /jurimetria/tribunais/status (sem I/O externo) e
 * GET /jurimetria/tribunais/desfechos (DataJud, cacheado no backend).
 * 503 = não configurado (flag ou DataJud desligados) — estado normal em
 * ambientes sem a integração, exibido como aviso, não como erro.
 */

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
  taxa_acordo: number | null;
  amostra_pequena: boolean;
  tempo_sentenca: { n: number; mediana_dias: number | null; media_dias: number | null };
};

type Desfechos = {
  fonte: string;
  escopo: { tribunal: string; municipios: string[] };
  coleta: { cache: boolean; coletado_em: string | null; n_documentos: number; truncado?: boolean };
  tpu: { versao: string };
  min_amostra: number;
  limitacoes: string[];
  total: Grupo;
  por_municipio: Array<Grupo & { municipio: string; nome: string }>;
  por_assunto: Array<Grupo & { assunto_codigo: string; assunto: string }>;
  reforma_2grau: {
    n_com_recurso_julgado: number;
    provimento: number;
    provimento_parcial: number;
    nao_provimento: number;
    taxa_reforma: number | null;
    amostra_pequena: boolean;
  };
};

type Status = { habilitado: boolean; datajud_habilitado: boolean; tpu_versao: string };

function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${(v * 100).toFixed(1)}%`;
}

function Taxa({ rotulo, valor, sub, pequena }: { rotulo: string; valor: string; sub: string; pequena?: boolean }) {
  return (
    <div className="text-center p-3 bg-gray-50 rounded-lg border border-black/[0.05]">
      <p className="text-2xl font-bold text-gray-800">{valor}</p>
      <p className="text-xs text-gray-500">{rotulo}</p>
      <p className="text-[11px] text-gray-400">{sub}</p>
      {pequena && (
        <p className="text-[11px] text-amber-700 mt-1">amostra pequena — leia com cautela</p>
      )}
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
    <section className="card p-5 mb-6" aria-labelledby="jurimetria-tribunais-titulo">
      <div className="flex items-center gap-1.5 mb-1">
        <Scale size={16} className="text-primary-500" />
        <h3 id="jurimetria-tribunais-titulo" className="font-semibold text-sm text-gray-700 uppercase">
          Tribunais — TJMG (Betim, Contagem, Belo Horizonte)
        </h3>
      </div>
      <p className="text-xs text-gray-500 mb-4">
        Como o tribunal decide, a partir do DataJud/CNJ. Não é o desempenho do escritório — esse está nos
        painéis acima, rotulados "base interna".
      </p>

      {carregando && <p className="text-sm text-gray-500">Consultando o DataJud…</p>}

      {!carregando && indisponivel && (
        <p className="text-sm text-gray-600 bg-gray-50 border border-black/[0.05] rounded-lg p-3" role="status">
          {indisponivel}
        </p>
      )}

      {!carregando && dados && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Taxa
              rotulo="Procedência (total + parcial)"
              valor={pct(dados.total.taxa_procedencia)}
              sub={`${dados.total.decididos_merito} decididos no mérito`}
              pequena={dados.total.amostra_pequena}
            />
            <Taxa
              rotulo="Acordo homologado"
              valor={pct(dados.total.taxa_acordo)}
              sub={`${dados.total.acordo} de ${dados.total.n_com_desfecho} com desfecho`}
            />
            <Taxa
              rotulo="Tempo até sentença (mediana)"
              valor={dados.total.tempo_sentenca.mediana_dias != null ? `${dados.total.tempo_sentenca.mediana_dias} dias` : "—"}
              sub={`${dados.total.tempo_sentenca.n} sentenças de mérito com data`}
            />
            <Taxa
              rotulo="Reforma em 2º grau"
              valor={pct(dados.reforma_2grau.taxa_reforma)}
              sub={`${dados.reforma_2grau.n_com_recurso_julgado} recursos julgados na amostra`}
              pequena={dados.reforma_2grau.amostra_pequena}
            />
          </div>

          <div className="grid md:grid-cols-2 gap-4 mt-4">
            <div>
              <h4 className="text-xs font-semibold text-gray-600 uppercase mb-2">Por município</h4>
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
                    <tr key={m.municipio} className="border-t border-black/[0.05]">
                      <td className="py-1">{m.nome}</td>
                      <td className="py-1 text-right">{m.n}</td>
                      <td className="py-1 text-right">{pct(m.taxa_procedencia)}</td>
                      <td className="py-1 text-right">{pct(m.taxa_acordo)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div>
              <h4 className="text-xs font-semibold text-gray-600 uppercase mb-2">Por assunto (top 8)</h4>
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
                    <tr key={a.assunto_codigo || a.assunto} className="border-t border-black/[0.05]">
                      <td className="py-1">{a.assunto}</td>
                      <td className="py-1 text-right">{a.n}</td>
                      <td className="py-1 text-right">{pct(a.taxa_procedencia)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <p className="text-[11px] text-gray-400 mt-4">
            Fonte: {dados.fonte}. Amostra: {dados.coleta.n_documentos} registros
            {dados.coleta.truncado ? " (limite atingido)" : ""}
            {dados.coleta.coletado_em ? ` · coleta ${dados.coleta.coletado_em}` : " · resultado em cache"} ·
            TPU {dados.tpu.versao}. Desfecho inferido por código de movimento — proxy, não leitura da sentença.
          </p>
        </>
      )}

      {status && !status.habilitado && !carregando && (
        <p className="text-[11px] text-gray-400 mt-2">TPU de referência: versão {status.tpu_versao}.</p>
      )}
    </section>
  );
}
