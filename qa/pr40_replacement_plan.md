# Substituição segura do PR #40

O PR #40 ficou antigo, grande e não mergeável após as remediações posteriores da `main`.

Estratégia adotada:

1. Presets de peças por rito — já existe base equivalente na `main` via `ESTRUTURA_TIPO`.
2. Guia Empresarial — já existe na `main` em `frontend/src/components/GuiaEmpresarial.tsx`.
3. Precedentes multi-fonte — recriado neste PR menor e isolado.
4. Aprendizado de estilo — deve virar PR separado, com migration própria.
5. Deep Research — deve virar PR separado, depois de Precedentes e Estilo.

Este PR entrega apenas o bloco 3, sem migration e sem tocar fluxos jurídicos/financeiros existentes.
