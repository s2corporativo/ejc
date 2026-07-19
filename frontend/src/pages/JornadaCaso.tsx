import { Link, useParams } from "react-router-dom";
import { Gavel } from "lucide-react";
import OrquestradorPanel from "../components/OrquestradorPanel";
import CaseBreadcrumb from "../components/CaseBreadcrumb";
import { Button, EmptyState, PageHeader } from "../components/UI";

/**
 * Rota histórica `/casos/:id/jornada` mantida para favoritos e deep-links.
 * A experiência usa o mesmo OrquestradorPanel da aba do caso, evitando duas
 * implementações e duas interpretações do estado jurídico.
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

  return (
    <div className="space-y-6">
      <CaseBreadcrumb caseId={id} titulo="Caso" tela="Jornada" />
      <PageHeader
        eyebrow="Fluxo jurídico do caso"
        title="Jornada do Caso"
        subtitle="Estado, pendências e próxima ação calculados pelo Orquestrador Jurídico a partir dos artefatos reais do caso."
        actions={
          <Link to={`/casos/${id}?tab=orquestrador`}>
            <Button variant="secondary" icon={<Gavel className="h-4 w-4" />}>
              Abrir no caso
            </Button>
          </Link>
        }
      />
      <OrquestradorPanel caseId={id} />
    </div>
  );
}
