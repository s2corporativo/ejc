// src/components/GuiaTributario.tsx
// Guia Operacional de Direito Tributário — De Paula Teixeira Advogados Associados
// Dr. Clovis José Soares — OAB/MG | Junho/2026
import { useEffect, useState } from "react";
import {
  BookOpen,
  Clock,
  ListChecks,
  Scale,
  AlertTriangle,
  Calculator,
  FileText,
  ShieldCheck,
  Building2,
  Lock,
  Gavel,
  Users,
} from "lucide-react";

function Sec({ icon: Icon, titulo, children, aberto = false }: any) {
  return (
    <details
      open={aberto}
      className="group border border-bronze-pale rounded-lg overflow-hidden"
    >
      <summary className="flex items-center gap-2 px-4 py-2.5 cursor-pointer bg-bronze-50/40 hover:bg-bronze-50 text-sm font-medium text-navy-900 select-none">
        <Icon size={15} className="text-bronze" /> {titulo}
        <span className="ml-auto text-slate-400 group-open:rotate-180 transition-transform">
          ▾
        </span>
      </summary>
      <div className="px-4 py-3 text-xs text-slate-700 space-y-2 leading-relaxed">
        {children}
      </div>
    </details>
  );
}

function Tab({
  head,
  rows,
}: {
  head: string[];
  rows: (string | React.ReactNode)[][];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="text-left text-ink-light border-b border-bronze-50">
            {head.map((h) => (
              <th key={h} className="py-1 pr-3 font-semibold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={i}
              className="border-t border-bronze-50 hover:bg-slate-50/40"
            >
              {r.map((c, j) => (
                <td key={j} className="py-1.5 pr-3 align-top">
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Flow({ children }: { children: string }) {
  return (
    <pre className="text-[10px] bg-slate-50 border border-slate-100 rounded p-3 overflow-x-auto leading-relaxed whitespace-pre-wrap text-slate-700">
      {children}
    </pre>
  );
}

const CHECKLIST = [
  "Identificar o tributo (federal, estadual, municipal) e a autoridade competente",
  "Identificar o tipo de processo: AI administrativo, execução fiscal ou crime tributário",
  "Verificar IMEDIATAMENTE a data de ciência/notificação → calcular prazo de impugnação (30 dias)",
  "Se já em execução fiscal: verificar se houve penhora → calcular 30 dias para embargos",
  "Calcular decadência: data do FG → verificar se o lançamento é tempestivo",
  "Calcular prescrição: data da constituição definitiva → verificar se está prescrita",
  "Verificar situação da CND / CPD-EN (cliente precisa de certidão para contrato/habilitação em geral?)",
  "Identificar se há outros processos do mesmo cliente → consolidar défices",
  "Verificar parcelamentos ativos: há inadimplência que pode causar exclusão?",
  "Verificar responsabilidade de sócios: algum sendo redirecionado na execução?",
  "Verificar se há possibilidade de denúncia espontânea (CTN art. 138) antes de fiscalização",
  "Calcular viabilidade de depósito judicial para suspender exigibilidade + obter CPD-EN",
  "Consultar e-CAC (situação fiscal) e REGULARIZE (dívida ativa + parcelamentos federais)",
];

export default function GuiaTributario() {
  const [marcados, setMarcados] = useState<Record<number, boolean>>({});
  useEffect(() => {
    try {
      setMarcados(
        JSON.parse(localStorage.getItem("guia_tributario_chk") || "{}"),
      );
    } catch {}
  }, []);
  const toggle = (i: number) => {
    const novo = { ...marcados, [i]: !marcados[i] };
    setMarcados(novo);
    localStorage.setItem("guia_tributario_chk", JSON.stringify(novo));
  };
  const feitos = Object.values(marcados).filter(Boolean).length;

  return (
    <div className="card p-4 mb-4 border-l-4 border-warn-500">
      <div className="flex items-center gap-2 mb-1">
        <BookOpen size={16} className="text-bronze" />
        <h2 className="font-serif font-semibold text-navy text-sm">
          Guia Operacional de Direito Tributário
        </h2>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        De Paula Teixeira Advogados Associados · Dr. Clovis José Soares —
        OAB/MG. Instrumento interno. Toda peça exige revisão. Verificar
        legislação atualizada: CTN, resoluções CARF, portarias RFB, legislação
        MG/Betim vigente.
      </p>

      {/* No sistema — ferramenta de recuperação de créditos fiscais */}
      <div className="mb-3 rounded-lg border border-gold-light bg-gold-50/60 p-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <span className="text-[10px] font-semibold uppercase text-slate-400">
          No sistema
        </span>
        <span className="text-slate-600 flex-1 min-w-[200px]">
          <b className="text-navy">Recuperação de Créditos Fiscais</b> — envie
          os XMLs de NF-e do cliente e obtenha o diagnóstico por tese (Tema 69
          STF e outras) com estimativa de valores.
        </span>
        <a
          href="#tributario-fiscal"
          onClick={(e) => {
            e.preventDefault();
            document
              .getElementById("tributario-fiscal")
              ?.scrollIntoView({ behavior: "smooth" });
          }}
          className="text-gold-700 hover:text-gold-600 underline decoration-gold-200 underline-offset-2 font-medium"
        >
          Abrir ferramenta ↑
        </a>
      </div>

      <div className="space-y-2">
        {/* 1. BASE LEGAL */}
        <Sec
          icon={Building2}
          titulo="1. Base legal e competências tributárias"
          aberto
        >
          <Tab
            head={["Norma", "Conteúdo", "Aplicação"]}
            rows={[
              [
                "CF/88, arts. 145–162",
                "Competências, limitações, imunidades",
                "Base constitucional",
              ],
              [
                "CTN — Lei 5.172/1966",
                "Normas gerais de direito tributário",
                "Nacional — LC vinculante",
              ],
              [
                "Dec. 70.235/1972",
                "Processo Administrativo Fiscal Federal (PAF)",
                "Federais: IRPJ, IPI, PIS, COFINS…",
              ],
              [
                "Lei 9.430/1996",
                "Lançamento, penalidades, juros federais",
                "RFB / PGFN",
              ],
              [
                "Lei 14.689/2023",
                "Voto de qualidade CARF favorável ao contribuinte",
                "Mudança estrutural",
              ],
              [
                "Lei 6.830/1980",
                "Execução Fiscal",
                "Cobrança judicial de dívida ativa",
              ],
              ["LC 123/2006", "Simples Nacional", "MEI, ME, EPP"],
              [
                "Lei 6.763/1975",
                "Código Tributário Estadual MG (ICMS/IPVA/ITCD)",
                "Estado de MG",
              ],
            ]}
          />
          <p className="font-semibold text-slate-600 mt-2">
            Competências por ente:
          </p>
          <Tab
            head={["Ente", "Tributos", "Processo Adm."]}
            rows={[
              [
                "União",
                "IRPJ, IRPF, CSLL, PIS, COFINS, IPI, IOF, CIDE, INSS (PJ)",
                "Dec. 70.235/72 → CARF",
              ],
              ["MG", "ICMS, IPVA, ITCMD", "Lei 6.763/75 → CC/MG"],
              [
                "Betim/MG",
                "ISS, IPTU, ITBI, Contribuições de Melhoria",
                "LC Municipal → Junta Revisora",
              ],
            ]}
          />
          <p className="font-semibold text-slate-600 mt-2">
            Regimes de tributação:
          </p>
          <Tab
            head={["Regime", "Tributos", "Atenção"]}
            rows={[
              [
                "Simples Nacional",
                "DAS unificado",
                "Vedações de atividades; sublimites por receita",
              ],
              [
                "Lucro Presumido",
                "IRPJ + CSLL + PIS + COFINS",
                "Presunção de lucro por CNAE; até R$ 78M",
              ],
              [
                "Lucro Real",
                "Todos; IRPJ sobre lucro efetivo",
                "Complexo; permite compensar prejuízo fiscal",
              ],
              [
                "MEI",
                "INSS + ISS ou ICMS (valor fixo)",
                "Limites de receita anual; atividades permitidas",
              ],
            ]}
          />
        </Sec>

        {/* 2. PAF FEDERAL */}
        <Sec
          icon={FileText}
          titulo="2. PAF Federal — fluxo completo (Dec. 70.235/72)"
        >
          <Flow>{`ETAPA 1 — LANÇAMENTO / AUTO DE INFRAÇÃO
│
├─ RFB lavra Auto de Infração (AI) ou Notificação de Lançamento (NL)
│  Notificação: pessoal (domicílio tributário) ou eletrônica (DTE via e-CAC)
│  ⚠️ Prazo começa na DATA DE CIÊNCIA da notificação
│
├─── PRAZO 1: 30 dias → IMPUGNAÇÃO
│    Base: Dec. 70.235/72, art. 15, I
│    Efeito: SUSPENDE a exigibilidade (CTN art. 151, III)
│    Apresentar: e-CAC (digital) ou DRF da jurisdição
│
▼
ETAPA 2 — DRJ (1ª instância)
│
├─ Prazo de julgamento: meta interna 360 dias (Lei 11.457/07 art. 24)
├─ Favorável ao Fisco → PRAZO 2: 30 dias → Recurso Voluntário ao CARF
├─ Favorável ao Contribuinte → Fisco pode interpor Recurso de Ofício (> R$ 15M)
│
▼
ETAPA 3 — CARF (2ª instância)
│
├─ 50% conselheiros RFB + 50% contribuintes
├─ LEI 14.689/2023: empate → FAVORÁVEL AO CONTRIBUINTE (voto de qualidade invertido)
├─ Desfavorável → PRAZO 3: 15 dias → Recurso Especial à CSRF
│
▼
ETAPA 4 — CSRF (decisão final administrativa)
│
├─── PRAZO 4: 120 dias → MANDADO DE SEGURANÇA (Lei 12.016/09, art. 23)
└─── PRAZO 5: 5 anos → AÇÃO ANULATÓRIA (Dec. 20.910/32)`}</Flow>
          <p className="font-semibold text-slate-600 mt-2">
            Suspensão da exigibilidade — CTN art. 151:
          </p>
          <Flow>{`CAUSAS DE SUSPENSÃO (impede execução fiscal, penhora e restrição cadastral):
I.   Moratória
II.  Depósito integral do valor em juízo (garante CND)
III. Reclamações e recursos administrativos pendentes
IV.  Concessão de liminar em mandado de segurança
V.   Concessão de tutela antecipada em ação judicial
VI.  Parcelamento
→ Contribuinte tem direito à CPD-EN (mesmos efeitos da CND — CTN art. 206)`}</Flow>
        </Sec>

        {/* 3. PAF ESTADUAL E MUNICIPAL */}
        <Sec icon={Building2} titulo="3. PAF Estadual e Municipal (MG)">
          <p>
            <b>ICMS — SEFAZ-MG (Lei 6.763/75):</b>
          </p>
          <Flow>{`1. AUTO DE INFRAÇÃO (AI) — lavrado por AFRE
2. IMPUGNAÇÃO → 30 dias da ciência (art. 107 Lei 6.763/75) — via SARA online
3. DJEJ — 1ª instância estadual (monocrática)
4. RECURSO ORDINÁRIO → 30 dias → Câmara Especial CC/MG
5. CÂMARA DE RECURSOS ESPECIAIS do CC/MG → última instância administrativa
6. MS ou AÇÃO ANULATÓRIA → judicial (TJ/MG ou TRF1)
Portais: sef.mg.gov.br | e-PTA MG (processo tributário eletrônico)`}</Flow>
          <p className="mt-2">
            <b>ISS / IPTU / ITBI — Município de Betim/MG:</b>
          </p>
          <p>
            Verificar LC Municipal de Betim (Código Tributário Municipal).
            Impugnação: geralmente 30 dias da notificação. Recurso: Junta de
            Revisão Fiscal ou órgão equivalente. Após esgotamento: CDA municipal
            → execução fiscal → TJ/MG.
          </p>
          <p>
            ISS Betim: alíquotas 2%–5% (LC 116/2003). IPTU: lançamento anual;
            prazo para impugnar 30 dias da entrega do carnê; base PGV pode ser
            contestada por avaliação contraditória.
          </p>
        </Sec>

        {/* 4. TABELA DE PRAZOS */}
        <Sec icon={Clock} titulo="4. Tabela mestra de prazos">
          <Tab
            head={["#", "Gatilho", "Prazo", "Ato", "Base"]}
            rows={[
              [
                "1",
                "Ciência do AI/NL federal",
                "30 dias",
                "Impugnação federal (suspende exigibilidade)",
                "Dec. 70.235/72, art. 15, I",
              ],
              [
                "2",
                "Ciência do AI estadual",
                "30 dias",
                "Impugnação ICMS/MG",
                "Lei 6.763/75, art. 107",
              ],
              [
                "3",
                "Ciência do AI municipal",
                "30 dias",
                "Impugnação ISS/IPTU/ITBI",
                "LC Municipal",
              ],
              [
                "4",
                "Acórdão DRJ desfavorável",
                "30 dias",
                "Recurso Voluntário ao CARF",
                "Dec. 70.235/72, art. 33",
              ],
              [
                "5",
                "Acórdão CARF desfavorável",
                "15 dias",
                "Recurso Especial à CSRF",
                "Dec. 70.235/72, art. 37, §2°",
              ],
              [
                "6",
                "Decisão final administrativa",
                "120 dias",
                "Mandado de Segurança",
                "Lei 12.016/09, art. 23",
              ],
              [
                "7",
                "Penhora em execução fiscal",
                "30 dias",
                "Embargos à Execução Fiscal",
                "Lei 6.830/80, art. 16, §1°",
              ],
              [
                "8",
                "FG (tributos por homologação)",
                "5 anos",
                "Decadência (sem dolo/fraude)",
                "CTN art. 150, §4°",
              ],
              [
                "9",
                "1° dia do exercício seguinte",
                "5 anos",
                "Decadência (com dolo/fraude)",
                "CTN art. 173, I",
              ],
              [
                "10",
                "Constituição definitiva do crédito",
                "5 anos",
                "Prescrição da cobrança",
                "CTN art. 174",
              ],
            ]}
          />
          <Flow>{`DECADÊNCIA (direito de LANÇAR):
Sem dolo/fraude: FG + 5 anos (CTN art. 150, §4°)
Com dolo/fraude: 1° dia do exercício seguinte + 5 anos (CTN art. 173, I)

PRESCRIÇÃO (direito de COBRAR):
5 anos da constituição definitiva (CTN art. 174)
Autodeclaração sem pagamento: prescreve da data da declaração (STJ Súmula 436)

INTERRUPÇÃO DA PRESCRIÇÃO (CTN art. 174, §único):
→ Despacho do juiz que ordena a citação na execução fiscal
→ Reconhecimento do débito (parcelamento, confissão)
⚠️ Aderir a parcelamento = reconhece o débito = interrompe prescrição!

SUSPENSÃO DA PRESCRIÇÃO:
→ Durante todo o processo administrativo pendente (CTN art. 151, III)`}</Flow>
        </Sec>

        {/* 5. DEFESAS */}
        <Sec icon={Scale} titulo="5. Defesas administrativas — teses técnicas">
          <p className="font-semibold text-slate-600">
            5.1 Teses Formais (nulidade do lançamento — CTN art. 142):
          </p>
          <Flow>{`□ Falta de fundamentação legal da penalidade → nulidade parcial (da multa)
□ Identificação incorreta do sujeito passivo (CNPJ, CPF, nome)
□ Período de apuração errado
□ Base de cálculo não fundamentada ou calculada incorretamente
□ Ausência de relatório fiscal circunstanciado (Súmula CARF 159)
□ Cerceamento de defesa: negativa de acesso ao processo ou provas
□ Nulidade da notificação: endereço errado, DTE inativo sem aviso`}</Flow>
          <p className="font-semibold text-slate-600 mt-2">5.2 IRPJ / CSLL:</p>
          <Flow>{`□ Dedução de despesas operacionais negada indevidamente (RIR/2018, art. 311)
□ Adição de receitas não tributáveis (dividendos, equivalência patrimonial)
□ Prejuízo fiscal não aproveitado: limite de 30% por período
□ Preços de transferência: novo regime Lei 14.596/2023
□ PLR: requisitos de dedutibilidade (Lei 10.101/2000)`}</Flow>
          <p className="font-semibold text-slate-600 mt-2">5.3 PIS / COFINS:</p>
          <Flow>{`□ Não-cumulatividade: créditos indevidos ou negados (Lei 10.637/02 + 10.833/03)
□ Exclusão do ICMS da base de cálculo do PIS/COFINS
  → STF RE 574.706 (Tema 69): ICMS destacado na NF deve ser excluído
  ⚠️ Modulação: créditos recuperáveis apenas a partir de 15/03/2017
□ Insumos: conceito amplo — STJ REsp 1.221.170 (Tema 779)
  → Tudo que integra o processo produtivo de forma essencial e relevante`}</Flow>
          <p className="font-semibold text-slate-600 mt-2">5.4 ICMS (MG):</p>
          <Flow>{`□ Creditamento indevido negado: verificar se é insumo do processo produtivo
□ DIFAL: STF ADI 5469 (modulação a partir de jan/2022)
□ Transferência entre filiais do mesmo contribuinte: STF RE 1.490.708 (Tema 1.367)
  → NÃO incide ICMS em transferência entre estabelecimentos do mesmo contribuinte
□ Crédito extemporâneo: MG prazo de 5 anos
□ Guerra fiscal: glosa de crédito de benefício de outro estado → contestar`}</Flow>
          <p className="font-semibold text-slate-600 mt-2">5.5 ISS:</p>
          <Flow>{`□ Competência: local do estabelecimento prestador (regra LC 116/03, art. 3°)
  Exceções nos incisos I–XXII: local da prestação efetiva
□ Enquadramento na lista LC 116/03: serviço não listado = não incide ISS
□ Exportação de serviços: imunidade (LC 116/03, art. 2°, I)
□ Alíquota: mínima 2% (art. 8°-A) e máxima 5% (art. 8°)`}</Flow>
          <p className="font-semibold text-slate-600 mt-2">
            5.6 Teses transversais:
          </p>
          <Flow>{`□ DECADÊNCIA / PRESCRIÇÃO: lançamento ou cobrança fora do prazo → extinção
□ RETROATIVIDADE BENÉFICA (CTN art. 106, II): lei posterior que reduz penalidade
   aplica-se ao fato gerador anterior (não transitado em julgado)
□ DENÚNCIA ESPONTÂNEA (CTN art. 138): pagamento integral ANTES da fiscalização
   → EXTINGUE A MULTA (não extingue juros/correção)
   → Condição: comunicar + pagar integralmente antes de qualquer procedimento fiscal
□ MULTA CONFISCATÓRIA: STF reduz multas acima de 100% do tributo
   → Multa de ofício: 75% (Lei 9.430/96, art. 44, I) — razoável
   → Com fraude: 150% — pode ser contestada
□ VOTO DE QUALIDADE CARF (Lei 14.689/2023): empate = favorável ao contribuinte`}</Flow>
        </Sec>

        {/* 6. DECADÊNCIA E PRESCRIÇÃO */}
        <Sec icon={Calculator} titulo="6. Decadência e prescrição tributária">
          <p>
            <b>Decadência — direito de lançar (CTN arts. 150 e 173):</b>
          </p>
          <p>
            <b>Regra 1 — lançamento por homologação</b> (IRPJ, CSLL, PIS,
            COFINS, IPI, ICMS, ISS): Sem fraude/dolo = 5 anos do FG. Com
            fraude/dolo = 5 anos do 1° dia do exercício seguinte (STJ Súmula
            555: contribuinte que não declarou → prazo conta do 1° dia do
            exercício seguinte).
          </p>
          <p>
            <b>Regra 2 — lançamento de ofício</b> (IPTU, IPVA, ITCMD): CTN art.
            173, I — 5 anos do 1° dia do exercício seguinte ao que o lançamento
            poderia ter sido efetuado.
          </p>
          <p className="mt-2">
            <b>Prescrição — direito de cobrar (CTN art. 174):</b>
          </p>
          <Flow>{`PRAZO: 5 anos da constituição definitiva
Com impugnação/recurso: conta do acórdão final
Sem impugnação: conta do vencimento do prazo de 30 dias para impugnar
Autodeclaração (DCTF, GIA, PGDAS): conta da data da declaração (Súmula 436 STJ)

EXEMPLO PRÁTICO:
AI notificado em 15/03/2019
Contribuinte não impugnou → prazo: 14/04/2019
Prescrição: 14/04/2024
Se PGFN ajuizou em 30/06/2024 → PRESCRITA!`}</Flow>
          <Tab
            head={["Tributo", "Tipo", "Regra", "Ex: FG 2019"]}
            rows={[
              [
                "IRPJ (sem fraude)",
                "Homologação",
                "CTN art. 150, §4°",
                "Decai em 31/12/2024",
              ],
              [
                "IRPJ (com fraude)",
                "Homologação",
                "CTN art. 173, I",
                "Decai em 01/01/2025",
              ],
              [
                "ICMS (sem declaração)",
                "Homologação",
                "CTN art. 173, I (Súm. 555 STJ)",
                "Decai em 01/01/2025",
              ],
              [
                "IPTU Betim",
                "De ofício",
                "CTN art. 173, I",
                "Decai em 01/01/2025",
              ],
              [
                "ITCMD/MG",
                "De ofício",
                "CTN art. 173, I",
                "Depende do lançamento",
              ],
              [
                "Autodeclarado (DCTF)",
                "Homologação",
                "Súmula 436 STJ",
                "Prescreve 5 anos da declaração",
              ],
            ]}
          />
        </Sec>

        {/* 7. EXECUÇÃO FISCAL */}
        <Sec icon={Gavel} titulo="7. Execução fiscal — Lei 6.830/80">
          <Flow>{`ETAPAS:
1. Inscrição em Dívida Ativa → CDA
2. Ajuizamento da Execução Fiscal (PGFN / PGE-MG / PGM-Betim)
3. CITAÇÃO → 5 dias para pagar ou nomear bens (art. 8°, I)
4. Não pagando → PENHORA (ordem preferencial abaixo)
5. Auto de penhora → PRAZO 30 dias → Embargos à Execução
6. Avaliação dos bens → Hasta pública ou adjudicação

ORDEM DE PREFERÊNCIA NA PENHORA (Lei 6.830/80, art. 11):
1° Dinheiro/depósito bancário/aplicações (SISBAJUD)
2° Título da dívida pública
3° Título de crédito negociável em bolsa
4° Ações de S.A.   5° Pedras e metais preciosos
6° Imóvel   7° Navios e aeronaves   8° Veículos
9° Móveis e utensílios   10° Direitos e ações

SISBAJUD (penhora on-line de contas bancárias):
→ Bloqueio sem aviso prévio (execução imediata)
→ Defesa: mínimo existencial (PF) ou necessidade operacional da empresa
→ Pedir desbloqueio parcial ou substituição por outro bem`}</Flow>
          <p className="font-semibold text-slate-600 mt-2">
            Embargos à Execução (LEF art. 16):
          </p>
          <p>
            Prazo: 30 dias do auto de penhora. Pré-requisito: garantia do juízo.
            Efeito: suspensivo. Matérias: pagamento, prescrição/decadência,
            nulidade da CDA, excesso de execução, causas extintivas do crédito
            (CTN arts. 156–174). STJ Súmula 392: Fisco pode substituir a CDA até
            a sentença dos embargos para correção de erro material ou formal,
            vedada mudança do sujeito passivo.
          </p>
          <p className="font-semibold text-slate-600 mt-2">
            Exceção de Pré-Executividade (EPE):
          </p>
          <Flow>{`QUANDO USAR: matérias de ordem pública + prova pré-constituída (sem dilação probatória)
VANTAGEM: não exige garantia do juízo — pode ser antes da penhora
MATÉRIAS:
□ Decadência / Prescrição (mais forte — prova documental)
□ Ilegitimidade de parte (CPF/CNPJ errado)
□ Incompetência absoluta do juízo
□ Nulidade absoluta da CDA (vício insanável)
□ Pagamento antes do ajuizamento (comprovado documentalmente)
RISCO: se exige produção de prova → EPE rejeitada → usar embargos`}</Flow>
        </Sec>

        {/* 8. RECURSOS JUDICIAIS */}
        <Sec icon={Scale} titulo="8. Recursos judiciais">
          <p>
            <b>Mandado de Segurança tributário (Lei 12.016/09):</b>
          </p>
          <Flow>{`PRAZO: 120 dias do ato coator
CASOS:
□ Negativa de expedição de certidão negativa sem motivo legal
□ Exigência de tributo com inconstitucionalidade manifesta
□ Autuação baseada em IN inconstitucional
□ Bloqueio SISBAJUD acima do valor da dívida
□ Violação ao contraditório no processo administrativo
□ Cobrança prescrita mantida

LIMINAR (art. 7°, §2°): demonstrar relevância + periculum in mora
→ Liminar suspende exigibilidade → direito à CPD-EN

Autoridade coatora: Delegado RFB / Procurador PGFN / Presidente CARF (Federal)
Sec. Fazenda MG / Dir. SEFAZ-MG (Estadual) | Sec. Municipal de Finanças (Municipal)`}</Flow>
          <p className="font-semibold text-slate-600 mt-2">Ação Anulatória:</p>
          <p>
            Prazo: 5 anos (Dec. 20.910/32). Pedidos: nulidade do crédito +
            tutela antecipada (suspensão da cobrança) + repetição de indébito.
            Para suspender sem penhora: depósito judicial integral (CTN art.
            151, II) → garante CPD-EN durante o processo. Se ganhar: levanta o
            depósito + Selic. Se perder: depósito converte em renda.
          </p>
          <p className="font-semibold text-slate-600 mt-2">
            Repetição de Indébito (CTN art. 165):
          </p>
          <Flow>{`PRAZO: 5 anos do pagamento indevido (CTN art. 168, I)
CORREÇÃO: SELIC (substitui correção + juros — cumulação proibida, STJ)
VIA ADMINISTRATIVA: PER/DCOMP na RFB → compensar com débitos futuros
→ Prazo de análise RFB: 360 dias; silêncio = denegação tácita → recurso
VIA JUDICIAL: ação ordinária ou JEF federal (≤ 60 SM) — TRF1 (MG)
TESE DO SÉCULO (STF RE 574.706): ICMS da base PIS/COFINS — só após 15/03/2017
SELIC s/ restituição (STF RE 1.063.187): não incide IR/CSLL sobre Selic na restituição`}</Flow>
        </Sec>

        {/* 9. PARCELAMENTOS */}
        <Sec icon={Calculator} titulo="9. Parcelamentos">
          <p>
            <b>Parcelamento Ordinário Federal (Lei 10.522/2002):</b> até 60
            meses, SELIC + encargos. Acesso: regularize.rfb.gov.br ou e-CAC.
            Efeitos: suspende exigibilidade → CPD-EN. Atenção: 3 parcelas em
            atraso = exclusão automática. <b>Interrompe a prescrição</b>{" "}
            (reconhecimento do débito).
          </p>
          <p>
            <b>PERT (Lei 13.496/2017):</b> 84 meses. Reduções: à vista = 100%
            multa + 100% juros + encargos; parcelado 84x = redução de 50% multa
            + 25% juros. Uso de prejuízo fiscal IRPJ/CSLL para quitar até 80% da
            dívida (PJ). Status: encerrado em jan/2018 — monitorar reabertura de
            janela.
          </p>
          <p>
            <b>Simples Nacional (LC 123/2006):</b> 60 meses, SELIC. Acesso:
            simples.receita.fazenda.gov.br. Exclusão por débito: notificação +
            30 dias para regularizar ou impugnar. Defesa: demonstrar
            parcelamento em vigor na data de exclusão ou que os débitos não
            existem.
          </p>
          <p className="text-warn-700">
            ⚠ Aderir a parcelamento = reconhecer débito = interromper
            prescrição. Confirmar se prescrição não estava consumada antes de
            aderir.
          </p>
        </Sec>

        {/* 10. RESPONSABILIDADE SÓCIO */}
        <Sec
          icon={Users}
          titulo="10. Responsabilidade tributária do sócio (CTN art. 135)"
        >
          <p>
            <b>Regra geral:</b> sócio <b>não</b> responde pelas dívidas
            tributárias da empresa. STJ Súmula 430: mero inadimplemento da
            empresa não gera responsabilidade pessoal do sócio.
          </p>
          <p>
            <b>Exceção — redirecionamento para o sócio quando:</b>
          </p>
          <Flow>{`1. DISSOLUÇÃO IRREGULAR (mais frequente):
   STJ Súmula 435: "Presume-se dissolvida irregularmente a empresa que
   deixar de funcionar no seu domicílio fiscal sem comunicação aos órgãos
   competentes, legitimando o redirecionamento da execução fiscal para o sócio-gerente."
   Indícios: retorno de correspondência, empresa não localizada no endereço cadastral

2. FRAUDE / SONEGAÇÃO:
   Uso da PJ para fraudar o Fisco, NFs inidôneas, omissão dolosa de receitas

3. EXCESSO DE PODERES:
   Ato fora do objeto social ou sem autorização estatutária`}</Flow>
          <p className="font-semibold text-slate-600 mt-2">
            Defesas do sócio redirecionado:
          </p>
          <Flow>{`□ ILEGITIMIDADE PASSIVA:
   Sócio não era administrador na época do FG ou da dissolução
   Provar com: contrato social + alterações contratuais (datas de entrada/saída)

□ PRESCRIÇÃO DO REDIRECIONAMENTO:
   STJ (EAREsp 1.608.014): 5 anos para redirecionar, contados da dissolução irregular
   Se citação da empresa + 5 anos > redirecionamento → prescrito

□ EMPRESA AINDA EXISTE:
   Há bens da empresa → Fisco deve penhorar bens da PJ primeiro
   Redirecionamento prematuro é ilegítimo

□ DISSOLUÇÃO REGULAR:
   Baixa regular em todos os órgãos, sem confusão patrimonial

□ GRUPO ECONÔMICO IRREGULAR:
   Verificar: unidade de comando + confusão patrimonial + intenção fraudulenta`}</Flow>
        </Sec>

        {/* 11. CND */}
        <Sec icon={ShieldCheck} titulo="11. Certidão negativa — CND e CPD-EN">
          <Tab
            head={["Certidão", "Quando emitida", "Validade", "Portal"]}
            rows={[
              [
                "CND (CTN art. 205)",
                "Sem débitos em aberto",
                "180 dias",
                "certidoes.receita.fazenda.gov.br",
              ],
              [
                "CPD-EN (CTN art. 206)",
                "Débitos com exigibilidade suspensa",
                "Igual à CND",
                "Mesmo portal",
              ],
              [
                "CND PGFN",
                "Dívida ativa federal regularizada",
                "180 dias",
                "regularize.pgfn.gov.br",
              ],
              [
                "CNDT (débitos trabalhistas)",
                "Sem débitos TST/TRTs",
                "180 dias",
                "cndt.tst.jus.br",
              ],
              ["CRF FGTS", "FGTS em dia (Caixa)", "30 dias", "caixa.gov.br"],
            ]}
          />
          <p className="font-semibold text-slate-600 mt-2">
            Estratégia para obter CPD-EN com débitos:
          </p>
          <Flow>{`PROBLEMA: cliente tem débitos e precisa de certidão para contrato/habilitação em geral
SOLUÇÕES:
1. Parcelamento ordinário → CPD-EN imediata após adesão
2. Depósito judicial integral → CPD-EN após confirmação (1-3 dias úteis)
3. Recurso administrativo pendente → CPD-EN enquanto não decidido
4. Liminar em MS → CPD-EN após juntada da decisão

⚠️ RISCO: parcelamento interrompe prescrição — confirmar se prescrição
   não estava consumada antes de aderir`}</Flow>
        </Sec>

        {/* 12. CRIMES TRIBUTÁRIOS */}
        <Sec icon={Lock} titulo="12. Crimes tributários — Lei 8.137/90">
          <Tab
            head={["Art.", "Crime", "Pena"]}
            rows={[
              [
                "Art. 1°, I",
                "Omitir informação ou prestar declaração falsa ao Fisco",
                "2–5 anos ou multa",
              ],
              [
                "Art. 1°, II",
                "Fraudar a fiscalização tributária",
                "2–5 anos ou multa",
              ],
              [
                "Art. 1°, III",
                "Falsificar/alterar NF ou documento fiscal",
                "2–5 anos ou multa",
              ],
              [
                "Art. 1°, IV",
                "Elaborar/distribuir documento que induz erro ao Fisco",
                "2–5 anos ou multa",
              ],
              [
                "Art. 1°, V",
                "Negar ou deixar de fornecer NF obrigatória",
                "2–5 anos ou multa",
              ],
              [
                "Art. 2°, II",
                "Deixar de recolher tributo retido (ex: IRRF)",
                "6 meses–2 anos",
              ],
            ]}
          />
          <p className="font-semibold text-slate-600 mt-2">
            Extinção da punibilidade pelo pagamento:
          </p>
          <Flow>{`BASE: Lei 9.249/95, art. 34 + STF RE 791.364 (2023 — Plenário)

ANTES do recebimento da denúncia:
→ Pagamento integral (tributo + juros + multa) → EXTINGUE a punibilidade
→ Direito subjetivo — MP não pode se opor (Lei 9.249/95, art. 34)

APÓS o recebimento da denúncia:
→ STF RE 791.364 (2023): pagamento integral TAMBÉM extingue punibilidade
→ Princípio da intervenção mínima + bem jurídico (arrecadação) satisfeito

PARCELAMENTO: apenas suspende a pretensão punitiva enquanto em dia
→ Quitação integral: extingue a punibilidade definitivamente

ESTRATÉGIA: priorizar pagamento antes do recebimento da denúncia
            Mesmo após: pagar imediatamente e requerer extinção`}</Flow>
        </Sec>

        {/* 13. CHECKLIST */}
        <Sec
          icon={ListChecks}
          titulo={`13. Checklist operacional (${feitos}/${CHECKLIST.length})`}
        >
          <div className="space-y-1.5">
            {CHECKLIST.map((item, i) => (
              <label key={i} className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={!!marcados[i]}
                  onChange={() => toggle(i)}
                  className="mt-0.5"
                />
                <span
                  className={
                    marcados[i]
                      ? "line-through text-slate-400"
                      : "text-slate-700"
                  }
                >
                  {item}
                </span>
              </label>
            ))}
          </div>
          <div className="mt-3 p-3 bg-slate-50 rounded-lg text-[11px] text-slate-600 space-y-1">
            <p className="font-semibold text-slate-500 uppercase tracking-wide text-[10px] mb-1">
              Fontes de consulta
            </p>
            <p>
              <b>Federal:</b> e-CAC (situação fiscal) · REGULARIZE (dívida ativa
              + parcelamentos) · SISBAJUD · SISLEG CARF
              (acordaos.carf.fazenda.gov.br) · STJ · STF
            </p>
            <p>
              <b>MG:</b> sef.mg.gov.br · e-PTA MG · PGE-MG (dívida ativa
              estadual) · CC/MG
            </p>
          </div>
        </Sec>
      </div>

      <p className="text-[10px] text-warn-700 mt-3 flex items-start gap-1">
        <AlertTriangle size={12} className="mt-0.5 shrink-0" />
        Instrumento interno. Verificar legislação CARF, programas de
        parcelamento vigentes, teses repetitivas STJ/STF e LC Municipal de
        Betim. Versão: junho/2026.
      </p>
    </div>
  );
}
