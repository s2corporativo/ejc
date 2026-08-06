import { Navigate, useParams } from "react-router";
import { EmptyState } from "../components/UI";

/**
 * Rota histórica `/casos/:id/jornada` mantida para favoritos e deep-links.
 * Fase 1 do plano de simplificação: a jornada e a próxima ação do Orquestrador
 * vivem embutidas na Visão do caso (aba resumo), então esta rota apenas
 * redireciona — sem 404 e sem duas interpretações do estado jurídico.
 */
export default function JornadaCaso() {
  const { id } = useParams<{ id: string }>();

  if (!id) {
    return (
      <EmptyState
        title="Caso não identificado"
        message="Abra a Jornada a partir de um caso válido."
      />
    );
  }

  return <Navigate to={`/casos/${id}?tab=resumo`} replace />;
}
