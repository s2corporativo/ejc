import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../lib/api";
import { useCaseContext } from "../stores/caseContext";

/**
 * Resolve o filtro de caso dos módulos globais (Documentos, Peças, Prazos).
 *
 * Regra: `?caso=` na URL SEMPRE vence; quando não há query, o caso ativo do
 * Modo Caso preenche o filtro. O usuário pode remover o chip — isso limpa a
 * query e passa a ignorar o contexto apenas nesta tela (até remontar).
 */
export function useCasoFiltro(): {
  /** id do caso a enviar como `case_id` na listagem (ou undefined). */
  casoFiltro: string | undefined;
  /** Título do caso para o chip "Filtrando por: {caso}". */
  casoFiltroNome: string | undefined;
  /** Remove o filtro (limpa `?caso=` e ignora o contexto na tela). */
  removerFiltro: () => void;
} {
  const [searchParams, setSearchParams] = useSearchParams();
  const casoUrl = searchParams.get("caso") || undefined;
  const casoAtivo = useCaseContext((state) => state.caso);
  const [ignorarContexto, setIgnorarContexto] = useState(false);

  const casoFiltro =
    casoUrl ?? (ignorarContexto ? undefined : casoAtivo?.id);

  // Nome do caso quando o filtro veio da URL e não é o caso ativo — busca
  // pontual só para rotular o chip (falha silenciosa: chip mostra fallback).
  const [nomeResolvido, setNomeResolvido] = useState<{
    id: string;
    nome: string;
  } | null>(null);
  useEffect(() => {
    if (!casoFiltro || casoFiltro === casoAtivo?.id) return;
    let cancelado = false;
    api
      .get(`/cases/${casoFiltro}`)
      .then((r) => {
        if (!cancelado && r.data?.titulo) {
          setNomeResolvido({ id: casoFiltro, nome: r.data.titulo });
        }
      })
      .catch(() => {});
    return () => {
      cancelado = true;
    };
  }, [casoFiltro, casoAtivo?.id]);

  const casoFiltroNome = !casoFiltro
    ? undefined
    : casoFiltro === casoAtivo?.id
      ? casoAtivo?.titulo
      : nomeResolvido?.id === casoFiltro
        ? nomeResolvido.nome
        : undefined;

  const removerFiltro = () => {
    setIgnorarContexto(true);
    if (casoUrl) {
      const params = new URLSearchParams(searchParams);
      params.delete("caso");
      // replace: remover um chip de filtro não deve criar entrada no histórico.
      setSearchParams(params, { replace: true });
    }
  };

  return { casoFiltro, casoFiltroNome, removerFiltro };
}
