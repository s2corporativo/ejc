"use client";

import { useEffect } from "react";
import {
  Brain,
  Wand2,
  FileText,
  FolderOpen,
  LayoutDashboard,
  Settings as SettingsIcon,
  Users,
  Network,
  Briefcase,
  Calendar,
  Search,
  Shield,
  ArrowRight,
} from "lucide-react";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAppStore } from "@/lib/store";
import { Generator } from "./generator";
import { Editor } from "./editor";
import { DocumentsList } from "./documents-list";
import { Dashboard } from "./dashboard";
import { Settings } from "./settings";
import { ClientsCases } from "./clients-cases";
import { Cerebro } from "./cerebro";
import { Inteligencia } from "./inteligencia";
import { Casos } from "./casos";

// ── Duas zonas: ERP (operacional) + IA (cognitivo) ─────────────────────────
// ERP é dono dos dados operacionais: Cliente, Caso, Processo, Documento, Prazo.
// IA é dona dos dados cognitivos: Evidence, Fact, Assertion, Graph, Issue, Thesis.

const ERP_TABS = [
  { id: "dashboard" as const, label: "Início", icon: LayoutDashboard, key: "1" },
  { id: "casos" as const, label: "Casos", icon: Briefcase, key: "k" },
  { id: "clients" as const, label: "Clientes", icon: Users, key: "c" },
  { id: "documents" as const, label: "Documentos", icon: FolderOpen, key: "d" },
];

const IA_TABS = [
  { id: "cerebro" as const, label: "1. Entrada", icon: Brain, key: "e" },
  { id: "intelligence" as const, label: "2. Inteligência", icon: Network, key: "i" },
  // 3. Legal Brain = Cérebro etapa 5-8 (já integrado no Cérebro)
  // 4. Pesquisa = JurisprudênciaIA + LegalSource (acessível via Cérebro)
  { id: "generator" as const, label: "5. Produção", icon: Wand2, key: "g" },
  { id: "editor" as const, label: "Editor", icon: FileText, key: "m" },
  // 6. Governança = Settings (AI Gateway, AgentRuns, Audit, HITL)
  { id: "settings" as const, label: "6. Governança", icon: Shield, key: "," },
];

const ALL_TABS = [...ERP_TABS, ...IA_TABS];

export function AppShell() {
  const { appTab, setAppTab } = useAppStore();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.isContentEditable || target?.tagName === "SELECT") return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const key = e.key.toLowerCase();
      const tab = ALL_TABS.find((t) => t.key === key);
      if (tab) { e.preventDefault(); setAppTab(tab.id); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [setAppTab]);

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-secondary/20">
      <div className="sticky top-16 z-40 border-b border-border bg-background/80 glass">
        <div className="container-juridia">
          <Tabs value={appTab} onValueChange={(v) => setAppTab(v as typeof appTab)}>
            <TabsList className="h-auto w-full justify-start gap-1 overflow-x-auto rounded-none border-0 bg-transparent p-2 scrollbar-juridia">
              {/* ZONA ERP */}
              <div className="flex items-center gap-2 pr-2">
                <Briefcase className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">ERP</span>
              </div>
              {ERP_TABS.map((t) => (
                <TabsTrigger key={t.id} value={t.id} className="gap-1.5 data-[state=active]:bg-primary/10 data-[state=active]:text-primary" title={`Atalho: ${t.key.toUpperCase()}`}>
                  <t.icon className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">{t.label}</span>
                  <kbd className="hidden rounded border border-border bg-muted px-1 py-0.5 font-mono text-[9px] text-muted-foreground lg:inline-block">{t.key}</kbd>
                </TabsTrigger>
              ))}

              {/* Separador visual entre zonas */}
              <div className="mx-2 flex items-center gap-1">
                <div className="h-6 w-px bg-border" />
                <ArrowRight className="h-3 w-3 text-muted-foreground/50" />
                <div className="h-6 w-px bg-border" />
              </div>

              {/* ZONA IA */}
              <div className="flex items-center gap-2 pr-2">
                <Brain className="h-3.5 w-3.5 text-primary" />
                <span className="text-[10px] font-bold uppercase tracking-wider text-primary">IA</span>
              </div>
              {IA_TABS.map((t) => (
                <TabsTrigger key={t.id} value={t.id} className="gap-1.5 data-[state=active]:bg-primary/10 data-[state=active]:text-primary" title={`Atalho: ${t.key.toUpperCase()}`}>
                  <t.icon className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">{t.label}</span>
                  <kbd className="hidden rounded border border-border bg-muted px-1 py-0.5 font-mono text-[9px] text-muted-foreground lg:inline-block">{t.key}</kbd>
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>
      </div>

      <div>
        {/* ERP */}
        {appTab === "dashboard" && <Dashboard />}
        {appTab === "casos" && <Casos />}
        {appTab === "clients" && <ClientsCases />}
        {appTab === "documents" && <DocumentsList />}
        {/* IA */}
        {appTab === "cerebro" && <Cerebro />}
        {appTab === "intelligence" && <Inteligencia />}
        {appTab === "generator" && <Generator />}
        {appTab === "editor" && <Editor />}
        {appTab === "settings" && <Settings />}
      </div>
    </div>
  );
}
