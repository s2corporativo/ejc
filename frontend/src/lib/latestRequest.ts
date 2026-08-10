/**
 * Serializa apenas a APLICAÇÃO de respostas assíncronas concorrentes.
 *
 * O request antigo pode continuar no servidor (cancelar HTTP nem sempre
 * cancela processamento remoto), mas sua resposta deixa de poder sobrescrever
 * estado produzido por uma intenção mais recente do usuário.
 *
 * Complexidade: begin/isCurrent/invalidate = O(1), memória = O(1).
 */
export class LatestRequestGate {
  private generation = 0;

  begin(): number {
    this.generation += 1;
    return this.generation;
  }

  isCurrent(token: number): boolean {
    return token === this.generation;
  }

  invalidate(): void {
    this.generation += 1;
  }
}
