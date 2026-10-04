"use client";

import { motion } from "framer-motion";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { HelpCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";

const FAQS = [
  {
    q: "A IA realmente não vê meus dados sensíveis?",
    a: "Não. O sistema de anonimização local (tarja-1) detecta CPFs, nomes, endereços, valores e outros dados sensíveis direto no seu navegador e os substitui por marcadores como [NOME_0001] e [CPF_0001] antes de qualquer conteúdo sair do seu computador. A IA trabalha apenas com os marcadores e, na volta, a desanonimização é feita localmente.",
  },
  {
    q: "O JuridIA está em conformidade com a LGPD?",
    a: "Sim. O uso de dados é restrito à geração da minuta solicitada, sem retenção para outras finalidades. Não treinamos modelos de IA com os dados dos usuários. Os dados em trânsito usam TLS e os dados em repouso usam AES-256 — padrão bancário de segurança. Você pode excluir minutas e dados a qualquer momento.",
  },
  {
    q: "O que é a Resolução CNJ 615/2025 e por que importa?",
    a: "A Resolução 615/2025 do Conselho Nacional de Justiça estabelece princípios para uso de IA no Poder Judiciário: transparência, explicabilidade, imparcialidade, supervisão humana, responsabilidade, segurança e privacidade. O JuridIA foi desenvolvido em conformidade com essas diretrizes, garantindo que toda decisão ou peça gerada com apoio de IA seja submetida a revisão humana.",
  },
  {
    q: "Posso usar o JuridIA em processos sob segredo de justiça?",
    a: "Sim. Para processos sob sigilo, perícias íntimas e inquéritos confidenciais, o sistema de anonimização local garante que o dado original nunca sai da máquina. Em segredo de justiça, recomendamos o plano Enterprise, com dados 100% segregados e infraestrutura dedicada.",
  },
  {
    q: "Como funcionam as habilidades (skills)?",
    a: "As habilidades são pacotes de conhecimento jurídico escrito em texto legível que orientam cada geração. Cada peça mostra quais habilidades participaram. Você pode fixar as inegociáveis com #, editar com o seu entendimento e receber atualizações do catálogo sem perder suas personalizações.",
  },
  {
    q: "Quais sistemas de processos eletrônicos são suportados?",
    a: "A extensão JuridIA Conecta suporta os principais sistemas: PJe, SEEU, Eproc, Projudi, e-SAJ, SEI, JPe, além de consulta direta ao STF e STJ. Inclui OCR para documentos digitalizados e exportação do inteiro teor com um único clique.",
  },
  {
    q: "Qual a diferença entre os planos?",
    a: "Individual I (R$140/mês, 100 minutas), Individual II (R$280, 200 minutas + treinamento) e Individual III (R$560, 400 minutas + suporte prioritário). Planos semestrais têm 10% de desconto e anuais 25%. Para escritórios há o plano Corporativo e, para tribunais/defensorias, o Enterprise com infraestrutura dedicada.",
  },
  {
    q: "A minuta gerada pode ser usada diretamente no processo?",
    a: "A minuta gerada pela IA é um rascunho de alta qualidade que deve ser revisado e aprovado por um advogado antes do protocolo. A IA acelera a redação, mas o entendimento jurídico — único, humano e insubstituível — permanece com você. Nunca protocolize uma minuta sem revisão humana.",
  },
];

export function Faq() {
  return (
    <section id="faq" className="border-b border-border bg-secondary/30">
      <div className="container-juridia py-20">
        <div className="mx-auto max-w-3xl">
          <div className="text-center">
            <Badge variant="secondary" className="mb-3">
              <HelpCircle className="mr-1 h-3 w-3" /> Perguntas frequentes
            </Badge>
            <h2 className="text-3xl font-bold tracking-tight text-balance sm:text-4xl">
              Tudo o que você precisa saber sobre o JuridIA
            </h2>
            <p className="mt-4 text-muted-foreground">
              Da privacidade dos dados à conformidade normativa. Se não encontrar
              sua resposta, fale com nosso time.
            </p>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="mt-10"
          >
            <Accordion type="single" collapsible className="space-y-3">
              {FAQS.map((item, i) => (
                <AccordionItem
                  key={i}
                  value={`item-${i}`}
                  className="rounded-lg border border-border bg-card px-4 data-[state=open]:shadow-sm"
                >
                  <AccordionTrigger className="text-left text-base font-medium hover:no-underline">
                    {item.q}
                  </AccordionTrigger>
                  <AccordionContent className="text-sm leading-relaxed text-muted-foreground">
                    {item.a}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
