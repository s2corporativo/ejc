import { useEffect, useState } from "react";
import { useLocation, useSearchParams } from "react-router";
import api from "../lib/api";
import { useCaseContext } from "../stores/caseContext";

/**
 * Resolve o filtro de caso dos módulos globais (Documentos, Peças, Prazos)
 * e dos mesmos workspaces quando montados DENTRO de /casos/:id.
 *
 * Precedência:
 * 1) `?caso=` explícito;
 * 2) id da própria rota `/casos/:id` (contexto obrigatório e imediato);
 * 3) caso ativo do Modo Caso.
 *
 * O contexto de rota evita um primeiro render da fila global enquanto o store
 * assíncrono ainda carrega o caso e não pode ser removido sem sair do Caso.
 */
export function useCasoFiltro(): {
  casoFiltro: string | undefined;
  casoFiltroNome: string | undefined;
  removerFiltro: () => void;
} {
  const { pathname } = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const casoUrl = searchParams.get("caso")?.trim() || undefined;
  const casoAtivo = useCaseContext((state) => state.caso);
  const [ignorarContexto, setIgnorarContexto] = useState(false);

  const matchCaso = /^\/casos\/([^/]+)(?:\/|$)/.exec(pathname);
  const rawCasoRota = matchCaso?.[1];
  const casoRota =
    rawCasoRota && rawCasoRota !== "novo"
      ? decodeURIComponent(rawCasoRota)
      : undefined;

  const casoFiltro =
    casoUrl ?? casoRota ?? (ignorarContexto ? undefined : casoAtivo?.id);

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
    // Dentro de /casos/:id o contexto não é um filtro opcional: remover só
    // faria a tela mostrar dados globais sem o usuário ter saído do Caso.
    if (casoRota) return;
    setIgnorarContexto(true);
    if (casoUrl) {
      const params = new URLSearchParams(searchParams);
      params.delete("caso");
      setSearchParams(params, { replace: true });
    }
  };

  return { casoFiltro, casoFiltroNome, removerFiltro };
}
