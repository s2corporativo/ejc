import{t as e}from"./createLucideIcon-DN0J77WO.js";var t=e(`file-type-corner`,[[`path`,{d:`M12 22h6a2 2 0 0 0 2-2V8a2.4 2.4 0 0 0-.706-1.706l-3.588-3.588A2.4 2.4 0 0 0 14 2H6a2 2 0 0 0-2 2v6`,key:`15usau`}],[`path`,{d:`M14 2v5a1 1 0 0 0 1 1h5`,key:`wfsgrz`}],[`path`,{d:`M3 16v-1.5a.5.5 0 0 1 .5-.5h7a.5.5 0 0 1 .5.5V16`,key:`s1gz5`}],[`path`,{d:`M6 22h2`,key:`194x9m`}],[`path`,{d:`M7 14v8`,key:`11ixej`}]]);function n(e,t=`export.csv`){if(!e.length)return;let n=Object.keys(e[0]),r=e=>{let t=e==null?``:String(e);return t.includes(`,`)||t.includes(`"`)||t.includes(`
`)?`"${t.replace(/"/g,`""`)}"`:t},i=[n.join(`,`),...e.map(e=>n.map(t=>r(e[t])).join(`,`))],a=new Blob([`﻿`+i.join(`\r
`)],{type:`text/csv;charset=utf-8;`}),o=URL.createObjectURL(a),s=document.createElement(`a`);s.href=o,s.download=t,s.click(),URL.revokeObjectURL(o)}function r(e){return String(e??``).replace(/&/g,`&amp;`).replace(/</g,`&lt;`).replace(/>/g,`&gt;`).replace(/"/g,`&quot;`).replace(/'/g,`&#039;`)}function i(e,t,n,i=`export.pdf`){let a=r(e),o=r(new Date().toLocaleDateString(`pt-BR`,{dateStyle:`full`})),s=n.map(e=>`<tr>${e.map(e=>`<td>${r(e)}</td>`).join(``)}</tr>`).join(``),c=t.map(e=>`<th>${r(e)}</th>`).join(``),l=`<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>${a}</title>
  <style>
    @page { margin: 1.6cm 1.35cm; }
    body {
      font-family: Inter, 'Segoe UI', Arial, sans-serif;
      font-size: 11px;
      color: #111827;
      padding: 0;
      background: #fff;
    }
    .letterhead {
      border-bottom: 3px solid #C9A227;
      padding-bottom: 10px;
      margin-bottom: 14px;
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-logo { height: 36px; }
    .brand { font-size: 17px; font-weight: 800; color: #6F5711; }
    .sub { font-size: 10px; color: #6b7280; margin-top: 3px; }
    .cover {
      border: 1px solid #dbe3ef;
      border-radius: 10px;
      background: #f8fafc;
      padding: 14px;
      margin-bottom: 14px;
    }
    .kicker {
      color: #8F7117;
      font-size: 9px;
      font-weight: 800;
      text-transform: uppercase;
      margin-bottom: 4px;
    }
    h1 { font-size: 18px; color: #111827; margin: 0; line-height: 1.25; }
    .review {
      border: 1px solid #e8d9a0;
      border-left: 4px solid #C9A227;
      background: #FBF7EA;
      color: #6F5711;
      padding: 8px 10px;
      border-radius: 8px;
      margin-bottom: 12px;
      font-size: 10px;
    }
    table { width: 100%; border-collapse: collapse; page-break-inside: auto; }
    th {
      background: #6F5711;
      color: #fff;
      padding: 7px 8px;
      text-align: left;
      font-size: 9px;
      text-transform: uppercase;
      font-weight: 800;
    }
    td { padding: 6px 8px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }
    tr:nth-child(even) td { background: #F7F1DC; }
    .footer { margin-top: 18px; border-top: 1px solid #e5e7eb; padding-top: 8px; color: #6b7280; font-size: 9px; }
  </style>
</head>
<body>
  <div class="letterhead">
    <img class="brand-logo" src="${window.location.origin}/brand/logo-hd.png"
         alt="" onerror="this.style.display='none'" />
    <div>
      <div class="brand">De Paula Teixeira Advogados Associados</div>
      <div class="sub">Sistema EJC | Relatorio gerado em ${o}</div>
    </div>
  </div>
  <section class="cover">
    <div class="kicker">Relatorio | Padrao Visual Law EJC</div>
    <h1>${a}</h1>
  </section>
  <div class="review">Documento gerado automaticamente. Conferir dados antes de envio externo, protocolo ou tomada de decisao.</div>
  <table>
    <thead><tr>${c}</tr></thead>
    <tbody>${s||`<tr><td colspan="99">Nenhum registro encontrado.</td></tr>`}</tbody>
  </table>
  <div class="footer">Uso interno - confidencial. Nome sugerido: ${r(i)}</div>
</body>
</html>`,u=window.open(``,`_blank`);u&&(u.document.write(l),u.document.close(),u.focus(),setTimeout(()=>{u.print()},300))}export{n,t as r,i as t};