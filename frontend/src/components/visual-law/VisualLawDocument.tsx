import type { ReactNode } from "react";
import { FileText, Scale, ShieldCheck } from "lucide-react";
import Markdown from "../Markdown";
import { cn } from "../../lib/cn";

type VisualLawStatus = "draft" | "review" | "approved" | "final";

const statusLabel: Record<VisualLawStatus, string> = {
  draft: "Minuta em elaboração",
  review: "Revisão obrigatória",
  approved: "Validado para uso interno",
  final: "Versão final",
};

export interface VisualLawDocumentProps {
  title: string;
  type?: string;
  version?: string | number;
  createdAt?: string;
  status?: VisualLawStatus;
  content?: string;
  children?: ReactNode;
  className?: string;
}

export function VisualLawDocument({
  title,
  type = "Documento jurídico",
  version,
  createdAt,
  status = "review",
  content,
  children,
  className,
}: VisualLawDocumentProps) {
  return (
    <article className={cn("visual-law-doc", className)}>
      <header className="visual-law-cover">
        <div className="visual-law-kicker">
          <Scale className="h-4 w-4" /> Visual Law EJC
        </div>
        <h1>{title}</h1>
        <p>
          Documento estruturado com hierarquia visual, revisão humana e controle
          de versão para leitura mais clara sem alterar o teor jurídico.
        </p>
        <div className="visual-law-meta-grid">
          <div>
            <span>Tipo</span>
            <strong>{type.replace(/_/g, " ")}</strong>
          </div>
          <div>
            <span>Versão</span>
            <strong>{version ? `v${version}` : "—"}</strong>
          </div>
          <div>
            <span>Status</span>
            <strong>{statusLabel[status]}</strong>
          </div>
          {createdAt && (
            <div>
              <span>Criação</span>
              <strong>{createdAt}</strong>
            </div>
          )}
        </div>
      </header>

      <section className="visual-law-review-box">
        <ShieldCheck className="h-4 w-4" />
        <div>
          <strong>Controle profissional</strong>
          <p>
            Peças geradas ou assistidas por IA devem ser revisadas por advogado
            responsável antes de assinatura, envio ou protocolo.
          </p>
        </div>
      </section>

      <section className="visual-law-body">
        {children ?? <Markdown source={content} />}
      </section>

      <footer className="visual-law-footer">
        <FileText className="h-4 w-4" /> Documento gerado no padrão Visual Law do EJC.
      </footer>
    </article>
  );
}
