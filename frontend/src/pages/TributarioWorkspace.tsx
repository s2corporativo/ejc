import { Navigate, useLocation } from "react-router";

/**
 * Atalho de primeira classe para o núcleo tributário canônico.
 *
 * A implementação tributária continua em Áreas de Atuação/RamoBase para não
 * duplicar casos, ferramentas, RAG, guias ou motores fiscais. Esta página
 * existe somente para dar ao Tributário uma porta própria no menu do EJC.
 */
export default function TributarioWorkspace() {
  const { search, hash } = useLocation();

  return (
    <Navigate
      to={`/areas-de-atuacao/tributario${search}${hash}`}
      replace
    />
  );
}
