// Validação offline de CPF/CNPJ (dígitos verificadores, módulo 11).
// Espelha backend/app/services/validators_service.py — mesma regra nas duas
// pontas para o erro aparecer antes do submit, sem depender de round-trip.

export function somenteDigitos(valor: string): string {
  return (valor || "").replace(/\D/g, "");
}

export function validarCpf(cpf: string): boolean {
  const d = somenteDigitos(cpf);
  if (d.length !== 11 || d === d[0].repeat(11)) return false;
  for (const i of [9, 10]) {
    let soma = 0;
    for (let j = 0; j < i; j += 1) soma += Number(d[j]) * (i + 1 - j);
    const dv = ((soma * 10) % 11) % 10;
    if (dv !== Number(d[i])) return false;
  }
  return true;
}

export function validarCnpj(cnpj: string): boolean {
  const d = somenteDigitos(cnpj);
  if (d.length !== 14 || d === d[0].repeat(14)) return false;
  const pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  const pesos2 = [6, ...pesos1];
  for (const [pesos, pos] of [
    [pesos1, 12],
    [pesos2, 13],
  ] as const) {
    let soma = 0;
    for (let i = 0; i < pos; i += 1) soma += Number(d[i]) * pesos[i];
    let dv = 11 - (soma % 11);
    if (dv >= 10) dv = 0;
    if (dv !== Number(d[pos])) return false;
  }
  return true;
}

/**
 * Classifica e valida um documento digitado em campo único "CPF/CNPJ".
 * 11 dígitos = CPF; 14 = CNPJ; vazio é permitido (documento opcional);
 * qualquer outro comprimento ou DV inválido retorna erro — nunca truncar.
 */
export function classificarDocumento(valor: string):
  | { tipo: "vazio"; cpf: null; cnpj: null }
  | { tipo: "cpf"; cpf: string; cnpj: null }
  | { tipo: "cnpj"; cpf: null; cnpj: string }
  | { tipo: "erro"; mensagem: string } {
  const d = somenteDigitos(valor);
  if (d.length === 0) return { tipo: "vazio", cpf: null, cnpj: null };
  if (d.length === 11) {
    if (!validarCpf(d))
      return { tipo: "erro", mensagem: "CPF com dígito verificador inválido." };
    return { tipo: "cpf", cpf: d, cnpj: null };
  }
  if (d.length === 14) {
    if (!validarCnpj(d))
      return { tipo: "erro", mensagem: "CNPJ com dígito verificador inválido." };
    return { tipo: "cnpj", cpf: null, cnpj: d };
  }
  return {
    tipo: "erro",
    mensagem: `Documento com ${d.length} dígitos — informe CPF (11) ou CNPJ (14).`,
  };
}
