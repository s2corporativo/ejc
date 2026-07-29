// Setup global do vitest — só folga de tempo, nenhuma mudança de comportamento.
//
// O CI roda num runner self-hosted que divide a VPS com a produção, e a suíte
// executa 47 arquivos jsdom em paralelo. Nessas condições o padrão de 1s do
// `waitFor` da @testing-library estoura em testes legítimos: em 2026-07-29 o
// `SalaJuridica.test.tsx` falhou no CI ("Cliente possivelmente já cadastrado")
// e passou 5/5 localmente e isolado — instabilidade por contenção de recurso,
// não defeito de produto.
//
// Aumentar o ORÇAMENTO DE ESPERA não enfraquece asserção nenhuma: o teste
// continua exigindo exatamente o mesmo estado final. O que muda é quanto tempo
// ele aceita esperar antes de desistir. Um teste realmente quebrado segue
// falhando — só demora um pouco mais para reprovar.
import { configure } from "@testing-library/react";

configure({ asyncUtilTimeout: 5000 });
