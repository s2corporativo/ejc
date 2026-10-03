// ── Registro eager dos rascunhos (complemento do contrato.ts) ──────────────
// O registro do contrato é preenchido por efeito colateral de import. Para
// rascunho em sessionStorage isso basta por construção: o dado só existe se
// o módulo da página carregou NESTA aba (logo, está registrado). Já os
// rascunhos PERSISTIDOS (intake documental com TTL 48h e a fila offline do
// cadastro manual, ambos em localStorage) podem existir como sobra de uma
// sessão anterior sem que o módulo correspondente tenha carregado nesta —
// e o logout ainda assim precisa limpá-los (LGPD).
//
// Este módulo garante a carga dos módulos de rascunho persistido e registra
// a limpeza do rascunho de sessão (varredura de prefixo, chave fonte única
// no contrato). Chamadores (lib/api.ts, stores/auth.ts) devem importar
// limparTodosRascunhos DAQUI — nunca direto do contrato — para que a
// garantia de carga viaje com a função.
import {
  registrarLimpezaRascunho,
  RASCUNHO_ENTRADA_PREFIXO,
  storageSessao,
} from "./contrato";
// Efeitos colaterais garantidos: cada módulo se registra ao carregar.
import "../../stores/cadastroManual";
import "../intakeRascunho";

// Rascunho da Entrada Única (sessionStorage): a limpeza varre o prefixo
// INTEIRO — ponteiro ("…_atual") incluído, pois também começa com o prefixo —
// removendo o rascunho atual e chaves órfãs. A lógica da página
// (pages/EntradaUnica/rascunhoStorage.ts) fica com salvar/carregar/limpar do
// fluxo; a limpeza de logout mora aqui para não criar dependência lib→pages.
registrarLimpezaRascunho(() => {
  const s = storageSessao();
  if (!s) return;
  try {
    for (let i = s.length - 1; i >= 0; i--) {
      const chave = s.key(i);
      if (chave && chave.startsWith(RASCUNHO_ENTRADA_PREFIXO)) {
        s.removeItem(chave);
      }
    }
  } catch {
    // storage indisponível não pode quebrar o logout
  }
});

export { limparTodosRascunhos } from "./contrato";
