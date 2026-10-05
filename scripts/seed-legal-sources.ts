// ⚠️  DEPRECATED — NÃO RODAR EM PRODUÇÃO
// Este script popula o banco com dados fictícios (skills, fontes, advogados fake, etc.)
// Para produção, use apenas fontes REAIS oficiais (Planalto, CNJ, STJ, STF).
// Em desenvolvimento: pode rodar para popular a base de conhecimento,
// mas NÃO deve ser incluído em deploy scripts ou CI/CD.
import { db } from "@/lib/db";

// ── GUARD: bloqueia execução em produção ──────────────────────────────────
if (process.env.NODE_ENV === "production") {
  console.error("❌ Este script de seed NÃO deve rodar em produção.");
  console.error("   Use apenas fontes REAIS oficiais (Planalto, CNJ, STJ, STF).");
  process.exit(1);
}


// Base curada de fontes jurídicas para o Citation Gate
// Fontes oficiais: planalto.gov.br/ccivil_03, stj.jus.br, stf.jus.br, tst.jus.br
const sources = [
  // ── Código Civil (Lei 10.406/2002) ──────────────────────────────────
  { tipo: "artigo_lei", diploma: "CC", numero: "art. 186", tribunal: null, textoTrecho: "Aquele que, por ação ou omissão voluntária, negligência ou imprudência, violar direito e causar dano a outrem, ainda que exclusivamente moral, comete ato ilícito.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm", revisadoPor: "curador" },
  { tipo: "artigo_lei", diploma: "CC", numero: "art. 927", tribunal: null, textoTrecho: "Aquele que, por ato ilícito, causar dano a outrem, fica obrigado a repará-lo. Parágrafo único. Haverá obrigação de reparar o dano, independentemente de culpa, nos casos especificados em lei, ou quando a atividade normalmente desenvolvida pelo autor do dano implicar, por sua natureza, risco para os direitos de outrem.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm", revisadoPor: "curador" },
  { tipo: "artigo_lei", diploma: "CC", numero: "art. 932", tribunal: null, textoTrecho: "São responsáveis pela reparação civil os pais pelos filhos menores que estiverem em sua poder e em sua companhia; o tutor e o curador pelos pupilos e curatelados; o empregador ou comitente por seus empregados, serviais e prepostos; os donos de edifícios; os que a título oneroso exploram atividades de risco.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm", revisadoPor: "curador" },
  { tipo: "artigo_lei", diploma: "CC", numero: "art. 938", tribunal: null, textoTrecho: "Aquele que habitar prédio que não pertence como inquilino, ou como possuidor em nome aquisitivo, responde pelos danos a que der causa.", vigente: false, urlOficial: "http://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm", revisadoPor: "curador" },

  // ── Código de Processo Civil (Lei 13.105/2015) ─────────────────────
  { tipo: "artigo_lei", diploma: "CPC", numero: "art. 203", tribunal: null, textoTrecho: "Decisão interlocutória é todo pronunciamento judicial de natureza decisória que não se enquadre no art. 261 deste Código.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm", revisadoPor: "curador" },
  { tipo: "artigo_lei", diploma: "CPC", numero: "art. 300", tribunal: null, textoTrecho: "A tutela de urgência, consistente na antecipação dos efeitos, total ou parcial, de provimento jurisdicional, quando houver elementos que evidenciem a probabilidade do direito e o perigo de dano ou o risco ao resultado útil do processo.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm", revisadoPor: "curador" },
  { tipo: "artigo_lei", diploma: "CPC", numero: "art. 311", tribunal: null, textoTrecho: "A tutela de evidência, caracterizada pela independência de demonstração de perigo de dano ou de risco ao resultado útil do processo, pode ser concedida quando fumar boni iuris ou houver tese firmada.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm", revisadoPor: "curador" },
  { tipo: "artigo_lei", diploma: "CPC", numero: "art. 319", tribunal: null, textoTrecho: "A petição inicial indicará: I - o juízo a que é dirigida; II - os nomes, prenomes, estado civil, profissão, CPF; III - o fato e os fundamentos jurídicos do pedido; IV - o pedido com suas especificações; V - o valor da causa; VI - as provas; VII - a opção pela audiência de conciliação.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm", revisadoPor: "curador" },
  { tipo: "artigo_lei", diploma: "CPC", numero: "art. 334", tribunal: null, textoTrecho: "Se a petição inicial preencher os requisitos essenciais e não for o caso de improcedência liminar do pedido, o juiz designará audiência de conciliação ou de mediação.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm", revisadoPor: "curador" },
  { tipo: "artigo_lei", diploma: "CPC", numero: "art. 489", tribunal: null, textoTrecho: "A sentença conterá: I - relatório; II - fundamentação; III - dispositivo. A fundamentação deve ser clara, precisa e fundamentada.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm", revisadoPor: "curador" },
  { tipo: "artigo_lei", diploma: "CPC", numero: "art. 85", tribunal: null, textoTrecho: "A sentença condenará o vencido a pagar honorários ao advogado do vencedor, de 10% a 20% sobre o valor da condenação ou do proveito econômico obtido.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm", revisadoPor: "curador" },
  { tipo: "artigo_lei", diploma: "CPC", numero: "art. 1009", tribunal: null, textoTrecho: "Da sentença caberá apelação. As apelações serão recebidas no duplo efeito, salvo quando a lei dispuser de modo diverso.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm", revisadoPor: "curador" },
  { tipo: "artigo_lei", diploma: "CPC", numero: "art. 355", tribunal: null, textoTrecho: "O juiz julgará antecipadamente o pedido, total ou parcialmente, quando não houver necessidade de produção de provas em audiência.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm", revisadoPor: "curador" },
  { tipo: "artigo_lei", diploma: "CPC", numero: "art. 202", tribunal: null, textoTrecho: "A prescrição é interrompida por qualquer ato que constitua em juízo, por despacho do juiz, inclusive a citação.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm", revisadoPor: "curador" },

  // ── Código de Defesa do Consumidor (Lei 8.078/90) ──────────────────
  { tipo: "artigo_lei", diploma: "CDC", numero: "art. 6", tribunal: null, textoTrecho: "São direitos básicos do consumidor: VIII - a facilitação de defesa de seus direitos, inclusive com a inversão do ônus da prova a seu favor.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm", revisadoPor: "curador" },
  { tipo: "artigo_lei", diploma: "CDC", numero: "art. 14", tribunal: null, textoTrecho: "O fornecedor responde pela reparção dos danos causados aos consumidores por defeitos relativos a produtos e serviços, independentemente de culpa.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm", revisadoPor: "curador" },
  { tipo: "artigo_lei", diploma: "CDC", numero: "art. 51", tribunal: null, textoTrecho: "São nulas de pleno direito as cláusulas contratuais que estabeleçam disposições potencialmente abusivas, como renúncia a direitos, multas desproporcionais.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm", revisadoPor: "curador" },

  // ── Súmulas STJ ─────────────────────────────────────────────────────
  { tipo: "sumula", diploma: "Súmula", numero: "Súmula 381", tribunal: "STJ", textoTrecho: "Nos feitos trabalhistas, os juros de mora incidem até a data do efetivo pagamento do débito.", vigente: true, urlOficial: "https://www.stj.jus.br/sites/portal-de-documentos-e-normas/sumulas-ab2023.html", revisadoPor: "curador" },
  { tipo: "sumula", diploma: "Súmula", numero: "Súmula 482", tribunal: "STJ", textoTrecho: "A taxa de juros em mora é de 0,5% ao mês, desde a Lei 4.421/64.", vigente: false, urlOficial: "https://www.stj.jus.br/sites/portal-de-documentos-e-normas/sumulas-ab2023.html", revisadoPor: "curador" },
  { tipo: "sumula", diploma: "Súmula", numero: "Súmula 332", tribunal: "STJ", textoTrecho: "A constituição em mora do devedor de prestação positiva, não ocorre automaticamente, depende de interpelação.", vigente: false, urlOficial: "https://www.stj.jus.br/sites/portal-de-documentos-e-normas/sumulas-ab2023.html", revisadoPor: "curador" },

  // ── Súmulas STF ────────────────────────────────────────────────────
  { tipo: "sumula", diploma: "Súmula", numero: "Súmula 7", tribunal: "STF", textoTrecho: "A ação de anos, prescreve em vinte anos, contados do nascimento do direito.", vigente: false, urlOficial: "https://www.stf.jus.br/portal/jurisprudencia/sumulas.asp", revisadoPor: "curador" },

  // ── Súmulas TST ─────────────────────────────────────────────────────
  { tipo: "sumula", diploma: "Súmula", numero: "Súmula 308", tribunal: "TST", textoTrecho: "A prescrição intercorrente na Justiça do Trabalho não atinge o direito do trabalhador de receber as parcelas constantes da certidão de crédito.", vigente: true, urlOficial: "https://www.tst.jus.br/sumulas", revisadoPor: "curador" },
  { tipo: "sumula", diploma: "Súmula", numero: "Súmula 381", tribunal: "TST", textoTrecho: "Nos feitos trabalhistas, os juros de mora incidem até a data do efetivo pagamento do débito. (revogada pela Lei 12.506/2011)", vigente: false, urlOficial: "https://www.tst.jus.br/sumulas", revisadoPor: "curador" },
  { tipo: "sumula", diploma: "Súmula", numero: "Súmula 277", tribunal: "TST", textoTrecho: "As partes devem ser intimadas da decisão que acolhe ou rejeita os embargos declaratórios para interposição de recurso, no prazo de 8 dias.", vigente: true, urlOficial: "https://www.tst.jus.br/sumulas", revisadoPor: "curador" },

  // ── CLT ─────────────────────────────────────────────────────────────
  { tipo: "artigo_lei", diploma: "CLT", numero: "art. 840", tribunal: null, textoTrecho: "A reclamação trabalhista poderá ser apresentada por empregado ou empregador, observado o procedimento sumaríssimo para causas de até 40 salários mínimos.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/decreto-lei/del5452.htm", revisadoPor: "curador" },
  { tipo: "artigo_lei", diploma: "CLT", numero: "art. 11", tribunal: null, textoTrecho: "O direito de ação quanto a créditos resultantes das relações de trabalho prescreve em 5 anos para o trabalhador urbano, limitado a 2 anos após a extinção do contrato.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/decreto-lei/del5452.htm", revisadoPor: "curador" },

  // ── Código Penal ───────────────────────────────────────────────────
  { tipo: "artigo_lei", diploma: "CP", numero: "art. 138", tribunal: null, textoTrecho: "Calúnia: caluniar alguém, imputando-lhe fato definido como crime, pena de detenção de 6 meses a 2 anos, e multa.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm", revisadoPor: "curador" },
  { tipo: "artigo_lei", diploma: "CP", numero: "art. 139", tribunal: null, textoTrecho: "Difamação: difamar alguém, imputando-lhe fato ofensivo à reputação, pena de detenção de 3 meses a 1 ano, e multa.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm", revisadoPor: "curador" },
  { tipo: "artigo_lei", diploma: "CP", numero: "art. 140", tribunal: null, textoTrecho: "Injúria: injuriar alguém, ofendendo-lhe a dignidade ou o decoro, pena de detenção de 1 a 6 meses, ou multa.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm", revisadoPor: "curador" },

  // ── CTN (Código Tributário Nacional) ────────────────────────────────
  { tipo: "artigo_lei", diploma: "CTN", numero: "art. 142", tribunal: null, textoTrecho: "Compete privativamente à autoridade administrativa constituir o crédito tributário pelo lançamento.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/leis/l5172compilado.htm", revisadoPor: "curador" },
  { tipo: "artigo_lei", diploma: "CTN", numero: "art. 173", tribunal: null, textoTrecho: "A ação para a constituição de crédito tributário prescreve em 5 anos, contados da data em que poderia ter sido constituído.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/leis/l5172compilado.htm", revisadoPor: "curador" },

  // ── Constituição Federal ───────────────────────────────────────────
  { tipo: "artigo_lei", diploma: "CF", numero: "art. 5", tribunal: null, textoTrecho: "Todos são iguais perante a lei, sem distinção de qualquer natureza. X - são invioláveis a intimidade, vida privada, honra e imagem das pessoas.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm", revisadoPor: "curador" },
  { tipo: "artigo_lei", diploma: "CF", numero: "art. 133", tribunal: null, textoTrecho: "O advogado é indispensável à administração da justiça, sendo inviolável por seus atos e manifestos no exercício da profissão.", vigente: true, urlOficial: "http://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm", revisadoPor: "curador" },
];

async function seed() {
  console.log("🌱 Populando base de fontes jurídicas...");
  let created = 0;
  let skipped = 0;

  for (const s of sources) {
    try {
      await db.legalSource.create({
        data: {
          ...s,
          dataConsulta: s.urlOficial ? new Date("2026-10-01") : null,
        },
      });
      created++;
      console.log(`  ✓ ${s.diploma} ${s.numero} (${s.tribunal || "—"})`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      if (msg.includes("Unique constraint")) {
        skipped++;
      } else {
        console.error(`  ✗ ${s.diploma} ${s.numero}:`, msg);
      }
    }
  }

  console.log(`\n✅ ${created} fontes criadas, ${skipped} já existiam`);
  console.log(`📊 Total na base: ${await db.legalSource.count()}`);
}

seed()
  .catch((e) => { console.error(e); process.exit(1); })
  .finally(async () => { await db.$disconnect(); });
