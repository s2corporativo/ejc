/**
 * Base LOCAL e auditável de mensagens do dia exibidas no cabeçalho —
 * versículos bíblicos (redação corrente das traduções Almeida, conferível
 * pela referência) e nenhuma dependência de API externa. A rotação é
 * determinística por dia do ano, então todos os usuários veem a mesma
 * mensagem no mesmo dia.
 *
 * Para acrescentar/editar mensagens, altere esta lista em PR — nunca gere
 * versículo por IA nem insira texto sem referência conferida.
 */

export type MensagemDoDia = {
  texto: string;
  /** Referência bíblica (livro capítulo:versículo) quando aplicável. */
  referencia?: string;
};

export const MENSAGENS_DO_DIA: readonly MensagemDoDia[] = [
  {
    texto: "Entrega o teu caminho ao Senhor; confia nele, e ele tudo fará.",
    referencia: "Salmos 37:5",
  },
  {
    texto:
      "Confia no Senhor de todo o teu coração e não te estribes no teu próprio entendimento.",
    referencia: "Provérbios 3:5",
  },
  {
    texto: "Posso todas as coisas naquele que me fortalece.",
    referencia: "Filipenses 4:13",
  },
  {
    texto:
      "Sê forte e corajoso; não temas, porque o Senhor, teu Deus, é contigo por onde quer que andares.",
    referencia: "Josué 1:9",
  },
  {
    texto: "O Senhor é o meu pastor; nada me faltará.",
    referencia: "Salmos 23:1",
  },
  {
    texto:
      "Não temas, porque eu sou contigo; não te assombres, porque eu sou o teu Deus.",
    referencia: "Isaías 41:10",
  },
  {
    texto:
      "Buscai primeiro o Reino de Deus e a sua justiça, e todas estas coisas vos serão acrescentadas.",
    referencia: "Mateus 6:33",
  },
  {
    texto:
      "Elevo os meus olhos para os montes: de onde me virá o socorro? O meu socorro vem do Senhor.",
    referencia: "Salmos 121:1-2",
  },
  {
    texto: "Todas as coisas cooperam para o bem daqueles que amam a Deus.",
    referencia: "Romanos 8:28",
  },
  {
    texto:
      "Confia ao Senhor as tuas obras, e os teus desígnios serão estabelecidos.",
    referencia: "Provérbios 16:3",
  },
  {
    texto:
      "Deus é o nosso refúgio e fortaleza, socorro bem presente nas tribulações.",
    referencia: "Salmos 46:1",
  },
  {
    texto: "Todas as vossas coisas sejam feitas com amor.",
    referencia: "1 Coríntios 16:14",
  },
  {
    texto:
      "Não nos cansemos de fazer o bem, pois no tempo próprio colheremos, se não desanimarmos.",
    referencia: "Gálatas 6:9",
  },
  {
    texto:
      "Se algum de vós tem falta de sabedoria, peça-a a Deus, que a todos dá liberalmente.",
    referencia: "Tiago 1:5",
  },
  {
    texto:
      "Seja sobre nós a graça do Senhor, nosso Deus; confirma sobre nós as obras das nossas mãos.",
    referencia: "Salmos 90:17",
  },
  {
    texto:
      "Que pratiques a justiça, e ames a misericórdia, e andes humildemente com o teu Deus.",
    referencia: "Miqueias 6:8",
  },
  {
    texto: "E conhecereis a verdade, e a verdade vos libertará.",
    referencia: "João 8:32",
  },
  {
    texto: "A justiça, somente a justiça seguirás.",
    referencia: "Deuteronômio 16:20",
  },
  {
    texto: "Aprendei a fazer o bem; buscai a justiça.",
    referencia: "Isaías 1:17",
  },
  {
    texto: "O exercício da justiça é motivo de alegria para o justo.",
    referencia: "Provérbios 21:15",
  },
  {
    texto:
      "Corra, porém, o juízo como as águas, e a justiça como ribeiro perene.",
    referencia: "Amós 5:24",
  },
  {
    texto:
      "Bem-aventurados os que guardam o direito, o que pratica a justiça em todo tempo.",
    referencia: "Salmos 106:3",
  },
  {
    texto:
      "O coração do sábio adquire o conhecimento, e o ouvido dos sábios busca o saber.",
    referencia: "Provérbios 18:15",
  },
  {
    texto:
      "Tudo tem o seu tempo determinado, e há tempo para todo propósito debaixo do céu.",
    referencia: "Eclesiastes 3:1",
  },
  {
    texto:
      "Tudo quanto fizerdes, fazei-o de todo o coração, como para o Senhor.",
    referencia: "Colossenses 3:23",
  },
  {
    texto:
      "Se o Senhor não edificar a casa, em vão trabalham os que a edificam.",
    referencia: "Salmos 127:1",
  },
  {
    texto:
      "Sem conselho, os planos se frustram; com muitos conselheiros, há bom êxito.",
    referencia: "Provérbios 15:22",
  },
  {
    texto: "Os que esperam no Senhor renovam as suas forças.",
    referencia: "Isaías 40:31",
  },
  {
    texto:
      "Que as palavras da minha boca e a meditação do meu coração sejam agradáveis a ti, Senhor.",
    referencia: "Salmos 19:14",
  },
  {
    texto: "A resposta branda desvia o furor.",
    referencia: "Provérbios 15:1",
  },
];

/** Dia do ano (1-366) da data informada, no horário local. */
export function diaDoAno(data: Date): number {
  const inicio = new Date(data.getFullYear(), 0, 1);
  const diff = data.getTime() - inicio.getTime();
  return Math.floor(diff / 86_400_000) + 1;
}

/**
 * Mensagem determinística do dia: mesma data → mesma mensagem, com fallback
 * seguro para a primeira da lista.
 */
export function mensagemDoDia(data: Date = new Date()): MensagemDoDia {
  if (MENSAGENS_DO_DIA.length === 0) {
    return { texto: "Bom trabalho." };
  }
  const indice = diaDoAno(data) % MENSAGENS_DO_DIA.length;
  return MENSAGENS_DO_DIA[indice] ?? MENSAGENS_DO_DIA[0];
}
