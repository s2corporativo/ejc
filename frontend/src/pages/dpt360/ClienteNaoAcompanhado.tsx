// Estado vazio de negócio do DPT Empresarial 360: o backend responde 404 em
// /dpt360/companies/{id} e /dpt360/diagnostics/readiness/{id} quando o
// cliente existe mas está fora do programa (não é PJ ativa dentro do escopo).
// Isso não é falha técnica — a página comunica o enquadramento em vez de
// exibir seções vazias ou erro genérico.
import { ArrowRight, Building2 } from "lucide-react";
import { Link } from "react-router";
import { Empty } from "../../components/UI";

// 404 nessas duas rotas é estado de negócio, não erro de rede/servidor.
export function isClienteForaDoPrograma(error: unknown): boolean {
  return (
    (error as { response?: { status?: number } } | undefined)?.response
      ?.status === 404
  );
}

export default function ClienteNaoAcompanhado({
  clientId,
}: {
  clientId?: string;
}) {
  return (
    <Empty
      icon={Building2}
      titulo="Cliente não acompanhado no DPT Empresarial 360"
      descricao="O DPT 360 acompanha clientes pessoa jurídica ativos do EJC, dentro do seu escopo de acesso. Para enquadrar este cliente, confirme no cadastro canônico que ele é PJ e está ativo — nenhum cadastro paralelo é criado."
      acao={
        clientId ? (
          <Link
            to={`/clientes/${clientId}`}
            className="inline-flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white dark:bg-white dark:text-slate-950"
          >
            Abrir cadastro do cliente <ArrowRight className="h-4 w-4" />
          </Link>
        ) : undefined
      }
    />
  );
}
