"use client";

import { useEffect, useRef, useState } from "react";
import {
  Download,
  Save,
  Loader2,
  Search,
  Replace,
  History,
  MessageSquare,
  Wand2,
  Check,
  X,
  FileText,
  Printer,
  Type,
  Clock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { DocumentDTO } from "@/lib/types";
import { useAppStore } from "@/lib/store";
import { toast } from "@/hooks/use-toast";
import { motion } from "framer-motion";
import { MoldeMode } from "./molde-mode";
import { CitationChecker } from "./citation-checker";

export function Editor() {
  const { currentDocId, setAppTab, writingStyle } = useAppStore();
  const [doc, setDoc] = useState<DocumentDTO | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [find, setFind] = useState("");
  const [replace, setReplace] = useState("");
  const [suggestion, setSuggestion] = useState<string | null>(null);
  const [suggLoading, setSuggLoading] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Word count and reading time (computed)
  const wordCount = content.split(/\s+/).filter(Boolean).length;
  const readMin = Math.max(1, Math.round(wordCount / 200));

  // Histórico de versões (in-memory)
  interface Version {
    id: string;
    timestamp: number;
    label: string;
    content: string;
    charCount: number;
  }
  const [versions, setVersions] = useState<Version[]>([]);
  const [showVersions, setShowVersions] = useState(false);
  const [dirty, setDirty] = useState(false);

  // Atalhos de teclado no editor
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ctrl/Cmd+S = salvar
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        if (doc) save();
      }
      // Ctrl/Cmd+Enter = pedir sugestão
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        // Dispara o dialog de sugestão
        const btn = document.querySelector<HTMLButtonElement>("[aria-label*=\"sugest\"]");
        btn?.click();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [doc, title, content]);

  // Detectar mudanças (dirty state)
  useEffect(() => {
    if (doc && content !== doc.generatedContent) {
      setDirty(true);
    } else {
      setDirty(false);
    }
  }, [content, doc]);

  // Auto-versionar a cada 2 min se houver mudanças
  useEffect(() => {
    if (!doc || !dirty) return;
    const interval = setInterval(() => {
      if (content !== doc.generatedContent && content.length > 50) {
        const v: Version = {
          id: `v-${Date.now()}`,
          timestamp: Date.now(),
          label: `Auto-save ${new Date().toLocaleTimeString("pt-BR")}`,
          content,
          charCount: content.length,
        };
        setVersions((prev) => [v, ...prev].slice(0, 10));
        setDirty(false);
      }
    }, 120000); // 2 min
    return () => clearInterval(interval);
  }, [doc, dirty, content]);

  useEffect(() => {
    if (currentDocId) {
      loadDoc(currentDocId);
    } else {
      // se não há doc atual, carrega o mais recente
      fetch("/api/documents")
        .then((r) => r.json())
        .then((d) => {
          if (d.documents?.length) {
            loadDoc(d.documents[0].id);
          }
        });
    }
  }, [currentDocId]);

  async function loadDoc(id: string) {
    setLoading(true);
    try {
      const res = await fetch("/api/documents");
      const data = await res.json();
      const found = (data.documents as DocumentDTO[]).find((d) => d.id === id);
      if (found) {
        setDoc(found);
        setTitle(found.title);
        setContent(found.generatedContent);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }

  async function save() {
    if (!doc) return;
    setSaving(true);
    try {
      await fetch("/api/documents", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: doc.id, content, title }),
      });
      toast({ title: "Documento salvo", description: title });
    } catch {
      toast({ title: "Erro ao salvar", variant: "destructive" });
    } finally {
      setSaving(false);
    }
  }

  function downloadMarkdown() {
    const blob = new Blob([`# ${title}\n\n${content}`], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title.replace(/[^\w\s-]/g, "")}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // Exporta um documento .doc (HTML com namespace Word, abre no Word/Google Docs)
  function downloadDocx() {
    const htmlBody = contentToHtml(content);
    const fullHtml = `<!DOCTYPE html><html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40"><head><meta charset="utf-8"><title>${esc(title)}</title>
    <!--[if gte mso 9]><xml><w:WordDocument><w:View>Print</w:View><w:Zoom>100</w:Zoom><w:DoNotOptimizeForBrowser/></w:WordDocument></xml><![endif]-->
    <style>
      @page Section1 { size: 21cm 29.7cm; margin: 2.5cm 2.5cm 2.5cm 2.5cm; }
      div.Section1 { page: Section1; }
      body { font-family: 'Times New Roman', Georgia, serif; font-size: 12pt; line-height: 1.75; color: #1a1a1a; }
      h1 { font-size: 16pt; text-transform: uppercase; margin: 0 0 12pt; text-align: center; }
      h2 { font-size: 13pt; text-transform: uppercase; margin: 18pt 0 8pt; }
      h3 { font-size: 12pt; margin: 14pt 0 6pt; }
      p { margin: 0 0 8pt; text-align: justify; text-indent: 1.25cm; }
      p:first-of-type { text-indent: 0; }
      ul, ol { margin: 0 0 8pt 1.5cm; }
      .header { text-align: center; border-bottom: 2px solid #333; padding-bottom: 8pt; margin-bottom: 16pt; }
      .footer { margin-top: 24pt; border-top: 1px solid #ccc; padding-top: 8pt; text-align: center; font-size: 9pt; color: #666; }
    </style></head><body><div class="Section1">
    <div class="header"><h1>${esc(title)}</h1></div>
    ${htmlBody}
    <div class="footer">Gerado por JuridIA — Inteligência Artificial para o Direito Brasileiro · ${new Date().toLocaleDateString("pt-BR")}</div>
    </div></body></html>`;
    const blob = new Blob(["\ufeff", fullHtml], { type: "application/msword" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title.replace(/[^\w\s-]/g, "")}.doc`;
    a.click();
    URL.revokeObjectURL(url);
    toast({ title: "Documento .doc exportado", description: "Abra no Word ou Google Docs." });
  }

  function downloadTxt() {
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title.replace(/[^\w\s-]/g, "")}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function printPdf() {
    const w = window.open("", "_blank", "width=800,height=900");
    if (!w) {
      toast({ title: "Popup bloqueado. Permita popups para exportar PDF.", variant: "destructive" });
      return;
    }
    const html = contentToHtml(content);
    w.document.write(`<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><title>${title}</title>
    <style>
      @page { margin: 2.5cm; }
      body { font-family: Georgia, 'Times New Roman', serif; font-size: 12pt; line-height: 1.75; color: #1a1a1a; }
      h1 { font-size: 16pt; text-transform: uppercase; margin: 0 0 12pt; }
      h2 { font-size: 13pt; text-transform: uppercase; margin: 18pt 0 8pt; }
      h3 { font-size: 12pt; margin: 14pt 0 6pt; }
      p { margin: 0 0 8pt; text-align: justify; }
      ul, ol { margin: 0 0 8pt 1.5em; }
      .header { text-align: center; border-bottom: 2px solid #333; padding-bottom: 8pt; margin-bottom: 16pt; }
      .header h1 { margin: 0; }
      .footer { margin-top: 24pt; border-top: 1px solid #ccc; padding-top: 8pt; text-align: center; font-size: 9pt; color: #666; }
      @media print { .no-print { display: none; } }
    </style></head><body>
    <div class="header"><h1>${title}</h1></div>
    ${html}
    <div class="footer">Gerado por JuridIA — Inteligência Artificial para o Direito Brasileiro · ${new Date().toLocaleDateString("pt-BR")}</div>
    <div class="no-print" style="text-align:center;padding:16pt;">
      <button onclick="window.print()" style="padding:8pt 24pt;font-size:11pt;background:#1a4d3a;color:white;border:none;border-radius:4pt;cursor:pointer;">Imprimir / Salvar PDF</button>
    </div>
    </body></html>`);
    w.document.close();
    toast({ title: "PDF aberto em nova aba", description: "Use Ctrl+P / Cmd+P para salvar como PDF." });
  }

  function contentToHtml(md: string): string {
    return md
      .split("\n")
      .map((line) => {
        if (line.startsWith("### ")) return `<h3>${esc(line.slice(4))}</h3>`;
        if (line.startsWith("## ")) return `<h2>${esc(line.slice(3))}</h2>`;
        if (line.startsWith("# ")) return `<h1>${esc(line.slice(2))}</h1>`;
        if (line.startsWith("- ")) return `<ul><li>${esc(line.slice(2))}</li></ul>`;
        if (/^\d+\.\s/.test(line)) return `<ol><li>${esc(line.replace(/^\d+\.\s/, ""))}</li></ol>`;
        if (line.trim() === "") return "";
        return `<p>${esc(line)}</p>`;
      })
      .join("\n");
  }

  function esc(s: string): string {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function doReplace() {
    if (!find) return;
    setContent((c) => c.split(find).join(replace));
    toast({ title: "Substituição aplicada" });
  }

  // Simula uma "sugestão" da IA (local, no cliente) — em produção chamaria /api/suggest
  async function askSuggestion(instruction: string) {
    setSuggLoading(true);
    setSuggestion(null);
    try {
      const res = await fetch("/api/suggest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          instruction,
          currentContent: content,
          templateName: doc?.templateName,
          style: writingStyle,
        }),
      });
      const data = await res.json();
      if (data.suggestion) {
        setSuggestion(data.suggestion);
        if (data.offline) {
          toast({
            title: "Modo offline",
            description: "IA indisponível, usando sugestão estruturada.",
          });
        }
      } else {
        toast({ title: "Sem sugestão disponível", variant: "destructive" });
      }
    } catch {
      toast({ title: "Erro ao gerar sugestão", variant: "destructive" });
    } finally {
      setSuggLoading(false);
    }
  }

  function acceptSuggestion() {
    if (!suggestion) return;
    setContent((c) => c + "\n\n" + suggestion);
    setSuggestion(null);
    setDirty(true);
    toast({ title: "Sugestão aceita", description: "Adicionada ao documento" });
  }

  if (loading) {
    return (
      <div className="container-juridia flex h-96 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  if (!doc) {
    return (
      <div className="container-juridia py-12 text-center">
        <FileText className="mx-auto h-12 w-12 text-muted-foreground/40" />
        <h2 className="mt-4 text-lg font-semibold">Nenhuma minuta aberta</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Gere uma minuta na aba “Gerar minuta” para vê-la aqui.
        </p>
        <Button className="mt-4" onClick={() => setAppTab("generator")}>
          Ir para o gerador
        </Button>
      </div>
    );
  }

  return (
    <div className="container-juridia py-6">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 flex-1">
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="border-0 px-0 text-xl font-bold focus-visible:ring-0"
            placeholder="Título da minuta"
          />
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="secondary">{doc.templateName}</Badge>
            <span>·</span>
            <span>Atualizado {new Date(doc.updatedAt).toLocaleString("pt-BR")}</span>
            {doc.skillSlugs.length > 0 && (
              <>
                <span>·</span>
                <span>{doc.skillSlugs.length} skill(s) aplicada(s)</span>
              </>
            )}
            <span>·</span>
            <span className="flex items-center gap-1">
              <Type className="h-3 w-3" />
              {wordCount.toLocaleString("pt-BR")} palavras
            </span>
            <span>·</span>
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {readMin} min de leitura
            </span>
            {dirty && (
              <>
                <span>·</span>
                <Badge variant="outline" className="gap-1 text-[10px] text-amber-600">
                  <span className="h-1.5 w-1.5 rounded-full bg-amber-500" /> não salvo
                </Badge>
              </>
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="outline" size="sm">
                <Wand2 className="mr-1.5 h-4 w-4" /> Pedir sugestão
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Sugestão de IA</DialogTitle>
              </DialogHeader>
              <div className="space-y-3">
                <Label htmlFor="instruction">O que você quer?</Label>
                <Input
                  id="instruction"
                  placeholder="Ex: fundamentar com responsabilidade civil"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      askSuggestion((e.target as HTMLInputElement).value);
                    }
                  }}
                />
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    askSuggestion("fundamentar com responsabilidade civil")
                  }
                >
                  Sugerir fundamentação
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => askSuggestion("completar pedidos")}
                >
                  Sugerir pedidos
                </Button>
                {suggLoading && (
                  <div className="flex items-center gap-2 text-sm">
                    <Loader2 className="h-4 w-4 animate-spin text-primary" />
                    Gerando sugestão...
                  </div>
                )}
                {suggestion && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="space-y-3"
                  >
                    <div className="rounded-md border border-dashed border-primary/40 bg-primary/5 p-3 text-sm">
                      <pre className="whitespace-pre-wrap font-mono text-xs">
                        {suggestion}
                      </pre>
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm" onClick={acceptSuggestion}>
                        <Check className="mr-1.5 h-4 w-4" /> Aceitar
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setSuggestion(null)}
                      >
                        <X className="mr-1.5 h-4 w-4" /> Rejeitar
                      </Button>
                    </div>
                  </motion.div>
                )}
              </div>
            </DialogContent>
          </Dialog>

          <Dialog>
            <DialogTrigger asChild>
              <Button variant="outline" size="sm">
                <Search className="mr-1.5 h-4 w-4" /> Localizar
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Localizar e substituir</DialogTitle>
              </DialogHeader>
              <div className="space-y-3">
                <div className="space-y-1">
                  <Label htmlFor="find">Localizar</Label>
                  <Input
                    id="find"
                    value={find}
                    onChange={(e) => setFind(e.target.value)}
                    placeholder="Ex: réu, [NOME_0001]"
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="replace">Substituir por</Label>
                  <Input
                    id="replace"
                    value={replace}
                    onChange={(e) => setReplace(e.target.value)}
                  />
                </div>
                <Button onClick={doReplace}>Substituir tudo</Button>
              </div>
            </DialogContent>
          </Dialog>

          <CitationChecker content={content} documentId={doc.id} />
          <Button variant="outline" size="sm" onClick={printPdf}>
            <Printer className="mr-1.5 h-4 w-4" /> PDF
          </Button>
          <Button variant="outline" size="sm" onClick={downloadDocx}>
            <Download className="mr-1.5 h-4 w-4" /> .doc
          </Button>
          <Button variant="outline" size="sm" onClick={downloadTxt}>
            <Download className="mr-1.5 h-4 w-4" /> .txt
          </Button>
          <Button variant="outline" size="sm" onClick={downloadMarkdown}>
            <Download className="mr-1.5 h-4 w-4" /> .md
          </Button>
          <Button size="sm" onClick={save} disabled={saving || !dirty} variant={dirty ? "default" : "outline"}>
            {saving ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-1.5 h-4 w-4" />
            )}
            {dirty ? "Salvar*" : "Salvo"}
          </Button>
        </div>
      </div>

      <Tabs defaultValue="edit">
        <div className="flex items-center gap-1 border-b border-border">
          <TabsList className="border-0 bg-transparent">
            <TabsTrigger value="edit" className="gap-1.5">
              <FileText className="h-3.5 w-3.5" /> Editar
            </TabsTrigger>
            <TabsTrigger value="preview" className="gap-1.5">
              <Wand2 className="h-3.5 w-3.5" /> Visualizar
            </TabsTrigger>
            <TabsTrigger value="anon" className="gap-1.5">
              <Search className="h-3.5 w-3.5" /> Marcadores
            </TabsTrigger>
            <TabsTrigger value="meta" className="gap-1.5">
              <History className="h-3.5 w-3.5" /> Metadados
            </TabsTrigger>
            <TabsTrigger value="versions" className="gap-1.5">
              <History className="h-3.5 w-3.5" /> Versões {versions.length > 0 && <Badge variant="secondary" className="ml-1 h-4 px-1 text-[10px]">{versions.length}</Badge>}
            </TabsTrigger>
            <TabsTrigger value="molde" className="gap-1.5">
              <Wand2 className="h-3.5 w-3.5" /> Modo Molde
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="edit" className="mt-4">
          <textarea
            ref={taRef}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="doc-page w-full resize-y rounded-md border border-border p-8 focus:outline-none focus:ring-2 focus:ring-primary/30 scrollbar-juridia"
            style={{ minHeight: "60vh", fontFamily: "Georgia, 'Times New Roman', serif" }}
          />
        </TabsContent>

        <TabsContent value="preview" className="mt-4">
          <div className="doc-page mx-auto max-w-3xl rounded-md">
            {content.split("\n").map((line, i) => {
              if (line.startsWith("### "))
                return (
                  <h3 key={i} className="mb-2 mt-4 text-base font-bold">
                    {line.slice(4)}
                  </h3>
                );
              if (line.startsWith("## "))
                return (
                  <h2 key={i} className="mb-3 mt-5 text-lg font-bold uppercase">
                    {line.slice(3)}
                  </h2>
                );
              if (line.startsWith("# "))
                return (
                  <h1 key={i} className="mb-3 text-xl font-bold uppercase">
                    {line.slice(2)}
                  </h1>
                );
              if (line.startsWith("- "))
                return (
                  <div key={i} className="ml-6 before:content-['•'] before:mr-2">
                    {line.slice(2)}
                  </div>
                );
              if (line.match(/^\d+\.\s/))
                return (
                  <div key={i} className="ml-6">
                    {line}
                  </div>
                );
              if (line.trim() === "") return <div key={i} className="h-3" />;
              return <p key={i} className="mb-2 text-justify">{line}</p>;
            })}
          </div>
        </TabsContent>

        <TabsContent value="anon" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Fatos anonimizados (o que a IA viu)</CardTitle>
            </CardHeader>
            <CardContent>
              <pre className="whitespace-pre-wrap rounded-md border border-border bg-secondary/50 p-3 font-mono text-xs">
                {doc.anonymizedFacts || "(sem fatos anonimizados registrados)"}
              </pre>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="meta" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Metadados</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Template</span>
                <span className="font-mono">{doc.templateSlug}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Status</span>
                <Badge variant="secondary">{doc.status}</Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Criado em</span>
                <span>{new Date(doc.createdAt).toLocaleString("pt-BR")}</span>
              </div>
              {doc.skillSlugs.length > 0 && (
                <div>
                  <div className="mb-1 text-muted-foreground">Skills aplicadas</div>
                  <div className="flex flex-wrap gap-1">
                    {doc.skillSlugs.map((s) => (
                      <Badge key={s} variant="outline" className="font-mono text-[10px]">
                        {s}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="versions" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between text-sm">
                <span>Histórico de versões</span>
                <Badge variant="outline" className="text-[10px]">{versions.length} versões</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {versions.length === 0 ? (
                <div className="py-8 text-center text-sm text-muted-foreground">
                  <History className="mx-auto mb-2 h-8 w-8 opacity-30" />
                  Nenhuma versão salva ainda.
                  <p className="mt-1 text-xs">
                    Versões automáticas são criadas a cada 2 minutos quando você edita.
                    Você também pode criar uma versão manualmente.
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="mt-3"
                    onClick={() => {
                      const v: Version = {
                        id: `v-${Date.now()}`,
                        timestamp: Date.now(),
                        label: `Versão manual ${new Date().toLocaleTimeString("pt-BR")}`,
                        content,
                        charCount: content.length,
                      };
                      setVersions((prev) => [v, ...prev].slice(0, 10));
                      toast({ title: "Versão criada", description: `${content.length} caracteres` });
                    }}
                  >
                    Criar versão agora
                  </Button>
                </div>
              ) : (
                <div className="space-y-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="mb-2 w-full"
                    onClick={() => {
                      const v: Version = {
                        id: `v-${Date.now()}`,
                        timestamp: Date.now(),
                        label: `Versão manual ${new Date().toLocaleTimeString("pt-BR")}`,
                        content,
                        charCount: content.length,
                      };
                      setVersions((prev) => [v, ...prev].slice(0, 10));
                      toast({ title: "Versão criada" });
                    }}
                  >
                    + Criar versão do estado atual
                  </Button>
                  {versions.map((v, i) => (
                    <div
                      key={v.id}
                      className="flex items-center gap-3 rounded-lg border border-border p-3 transition-colors hover:bg-accent/30"
                    >
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                        <History className="h-4 w-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium">{v.label}</div>
                        <div className="mt-0.5 text-xs text-muted-foreground">
                          {new Date(v.timestamp).toLocaleString("pt-BR")} · {v.charCount} caracteres
                        </div>
                      </div>
                      <div className="flex gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            setContent(v.content);
                            toast({ title: "Versão restaurada", description: v.label });
                          }}
                        >
                          Restaurar
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          aria-label="Excluir versão"
                          onClick={() => {
                            setVersions((prev) => prev.filter((x) => x.id !== v.id));
                          }}
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                  <p className="mt-3 text-center text-xs text-muted-foreground">
                    💡 As versões ficam em memória apenas nesta sessão. Salve o documento para persistir.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="molde" className="mt-4">
          {content && content.length > 50 ? (
            <MoldeMode
              baseContent={content}
              templateName={doc?.templateName || "minuta"}
              onApply={(newContent) => {
                setContent(newContent);
                setDirty(true);
                toast({ title: "Modo Molde aplicado", description: "Alterações aceitas incorporadas ao documento" });
              }}
            />
          ) : (
            <Card>
              <CardContent className="py-12 text-center text-sm text-muted-foreground">
                <Wand2 className="mx-auto mb-2 h-10 w-10 opacity-30" />
                Gere ou abra uma minuta primeiro para usar o Modo Molde.
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
