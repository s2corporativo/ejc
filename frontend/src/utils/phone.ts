/**
 * Remove tudo que não for dígito de um telefone.
 * Base para montar links de WhatsApp (wa.me), onde só os dígitos importam.
 * Null-safe: entradas vazias/nulas retornam "".
 */
export function soDigitos(phone?: string | null): string {
  return (phone ?? "").replace(/\D/g, "");
}
