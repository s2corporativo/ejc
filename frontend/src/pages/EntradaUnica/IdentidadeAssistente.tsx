// Identidade visual do assistente na Entrada Única (Dashboard `embedded` e
// tela cheia `/entrada`).
//
// O mockup aprovado pelo Titular desenhava aqui uma ilustração de pássaro
// ("Sabiá"). A decisão do Titular foi TROCAR esse slot pela marca do
// escritório: a identidade do assistente é a própria logomarca DT, não um
// desenho paralelo. Por isso este componente não aceita `src` — ele sempre
// lê `officeBranding.logoPath`, para que nenhuma cópia do asset vire caminho
// hardcoded em outro lugar do código.
//
// Robustez: se o arquivo de imagem não carregar no ambiente implantado
// (PNG ausente, proxy sem o asset, `VITE_EJC_LOGO_PATH` apontando para um
// caminho que não existe), a marca cai num monograma tipográfico "DT". Um
// `<img>` quebrado em branco dentro do círculo dourado do herói destoaria da
// composição e continua ocupando o mesmo espaço — o layout não pode depender
// da imagem carregar.
import { useCallback, useState } from "react";
import { officeBranding } from "../../config/officeBranding";

/** Iniciais de fallback — "De Paula Teixeira" → DT. */
const INICIAIS = "DT";

/** `alt` único para as duas variantes: descreve a marca, nunca vazio. */
const TEXTO_ALTERNATIVO = `${officeBranding.officeName} — assistente da Entrada Jurídica`;

export function IdentidadeAssistente({
  variante,
  className,
}: {
  /**
   * "heroi" ocupa o círculo do cabeçalho do herói do Dashboard;
   * "pill" é a marca compacta dentro da pílula da Entrada Única.
   * O tamanho real vem das classes que o chamador passa — este componente
   * não impõe dimensões, para não duplicar o que o CSS já resolve.
   */
  variante: "heroi" | "pill";
  className?: string;
}) {
  const [falhou, setFalhou] = useState(false);

  // Callback estável (nunca arrow inline no JSX): mantém a regra de
  // `react/jsx-no-bind` satisfeita caso o projeto a adote depois.
  const registrarFalha = useCallback(() => setFalhou(true), []);

  const classe = className ? `ejc-assistente ${className}` : "ejc-assistente";
  // `data-variante` só para depuração/estilo; o comportamento é o mesmo.
  const marcador = variante === "heroi" ? "heroi" : "pill";

  if (falhou) {
    return (
      <span
        className={`${classe} ejc-assistente--fallback`}
        data-variante={marcador}
        role="img"
        aria-label={TEXTO_ALTERNATIVO}
      >
        {INICIAIS}
      </span>
    );
  }

  return (
    <img
      className={classe}
      data-variante={marcador}
      src={officeBranding.logoPath}
      alt={TEXTO_ALTERNATIVO}
      onError={registrarFalha}
    />
  );
}
