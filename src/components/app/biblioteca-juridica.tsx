"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  BookOpen,
  Search,
  FileText,
  Scale,
  Gavel,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { toast } from "@/hooks/use-toast";

interface Skill {
  id: string;
  slug: string;
  name: string;
  category: string;
  description: string;
  content?: string;
}

interface LegalSource {
  id: string;
  tipo: string;
  diploma: string;
  numero: string;
  tribunal: string | null;
  textoTrecho: string;
  vigente: boolean;
}

interface JurisprudenceResult {
  title: string;
  url: string;
  snippet: string;
  host_name?: string;
}

export function BibliotecaJuridica() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [sources, setSources] = useState<LegalSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchSkills, setSearchSkills] = useState("");
  const [searchSources, setSearchSources] = useState("");
  const [searchJurisprudence, setSearchJurisprudence] = useState("");
  const [jurisprudenceResults, setJurisprudenceResults] = useState<JurisprudenceResult[]>([]);
  const [jurisprudenceLoading, setJurisprudenceLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [skillsRes, sourcesRes] = await Promise.all([
        fetch("/api/skills"),
        fetch("/api/legal-sources"),
      ]);
      const skillsData = await skillsRes.json();
      const sourcesData = await sourcesRes.json();
      setSkills(skillsData.skills || []);
      setSources(sourcesData.sources || sourcesData || []);
    } catch {
      toast({ title: "Erro ao carregar biblioteca", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function searchJurisprudenceFn() {
    if (searchJurisprudence.trim().length < 3) {
      toast({ title: "Digite pelo menos 3 caracteres", variant: "destructive" });
      return;
    }
    setJurisprudenceLoading(true);
    try {
      const res = await fetch("/api/jurisprudence", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: searchJurisprudence }),
      });
      const data = await res.json();
      setJurisprudenceResults(data.results || []);
      toast({ title: `${data.results?.length || 0} resultados encontrados` });
    } catch {
      toast({ title: "Erro na busca de jurisprudência", variant: "destructive" });
    } finally {
      setJurisprudenceLoading(false);
    }
  }

  const filteredSkills = skills.filter(s =>
    !searchSkills ||
    s.name.toLowerCase().includes(searchSkills.toLowerCase()) ||
    s.slug.toLowerCase().includes(searchSkills.toLowerCase()) ||
    s.category.toLowerCase().includes(searchSkills.toLowerCase())
  );

  const filteredSources = sources.filter(s =>
    !searchSources ||
    s.diploma.toLowerCase().includes(searchSources.toLowerCase()) ||
    s.numero.toLowerCase().includes(searchSources.toLowerCase()) ||
    (s.tribunal || "").toLowerCase().includes(searchSources.toLowerCase())
  );

  return (
    <div className="container-juridia py-8">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-lg">
            <BookOpen className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Biblioteca Jurídica</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Skills, fontes legais e jurisprudência — base do Cérebro Jurídico.
            </p>
          </div>
        </div>
        <Button onClick={load} variant="outline" size="sm" disabled={loading}>
          {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
          Atualizar
        </Button>
      </div>

      <Tabs defaultValue="skills">
        <TabsList className="mb-4">
          <TabsTrigger value="skills" className="gap-1.5">
            <FileText className="h-4 w-4" />
            Skills ({skills.length})
          </TabsTrigger>
          <TabsTrigger value="sources" className="gap-1.5">
            <Scale className="h-4 w-4" />
            Fontes ({sources.length})
          </TabsTrigger>
          <TabsTrigger value="jurisprudence" className="gap-1.5">
            <Gavel className="h-4 w-4" />
            Jurisprudência
          </TabsTrigger>
        </TabsList>

        {/* Skills */}
        <TabsContent value="skills">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Habilidades jurídicas curadas</CardTitle>
              <Input
                placeholder="Buscar por nome, slug ou categoria..."
                value={searchSkills}
                onChange={(e) => setSearchSkills(e.target.value)}
                className="mt-2"
              />
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-primary" />
                </div>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {filteredSkills.map((s, i) => (
                    <motion.div
                      key={s.id}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.03 }}
                    >
                      <Card className="h-full hover:shadow-md transition-shadow">
                        <CardHeader className="pb-2">
                          <div className="flex items-start justify-between gap-2">
                            <CardTitle className="text-sm font-medium leading-tight">{s.name}</CardTitle>
                            <Badge variant="secondary" className="text-[9px] shrink-0">{s.category}</Badge>
                          </div>
                        </CardHeader>
                        <CardContent className="pt-0">
                          <p className="text-xs text-muted-foreground line-clamp-3">{s.description}</p>
                          <code className="mt-2 block text-[10px] text-muted-foreground font-mono">{s.slug}</code>
                        </CardContent>
                      </Card>
                    </motion.div>
                  ))}
                </div>
              )}
              {filteredSkills.length === 0 && !loading && (
                <p className="text-center text-sm text-muted-foreground py-8">Nenhuma skill encontrada.</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Fontes */}
        <TabsContent value="sources">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Fontes legais oficiais</CardTitle>
              <Input
                placeholder="Buscar por diploma, número ou tribunal..."
                value={searchSources}
                onChange={(e) => setSearchSources(e.target.value)}
                className="mt-2"
              />
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-primary" />
                </div>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {filteredSources.map((s, i) => (
                    <motion.div
                      key={s.id}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.03 }}
                    >
                      <Card className="h-full hover:shadow-md transition-shadow">
                        <CardHeader className="pb-2">
                          <div className="flex items-start justify-between gap-2">
                            <CardTitle className="text-sm font-medium leading-tight">{s.diploma}</CardTitle>
                            <div className="flex flex-col gap-1 shrink-0">
                              <Badge variant={s.vigente ? "default" : "outline"} className="text-[9px]">
                                {s.vigente ? "Vigente" : "Revogado"}
                              </Badge>
                              <Badge variant="secondary" className="text-[9px]">{s.tipo}</Badge>
                            </div>
                          </div>
                        </CardHeader>
                        <CardContent className="pt-0">
                          <p className="text-xs text-muted-foreground line-clamp-3">{s.textoTrecho}</p>
                          <div className="mt-2 flex items-center gap-2 text-[10px] text-muted-foreground">
                            <code className="font-mono">{s.numero}</code>
                            {s.tribunal && <Badge variant="outline" className="text-[9px]">{s.tribunal}</Badge>}
                          </div>
                        </CardContent>
                      </Card>
                    </motion.div>
                  ))}
                </div>
              )}
              {filteredSources.length === 0 && !loading && (
                <p className="text-center text-sm text-muted-foreground py-8">Nenhuma fonte encontrada.</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Jurisprudência */}
        <TabsContent value="jurisprudence">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Busca de jurisprudência</CardTitle>
              <p className="text-xs text-muted-foreground">
                Busca real na web via IA — retorna decisões de STJ, STF, TJs e tribunais brasileiros.
              </p>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex gap-2">
                <Input
                  placeholder="Ex.: dano moral negativação indevida serasa"
                  value={searchJurisprudence}
                  onChange={(e) => setSearchJurisprudence(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") searchJurisprudenceFn(); }}
                />
                <Button onClick={searchJurisprudenceFn} disabled={jurisprudenceLoading}>
                  {jurisprudenceLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                  Buscar
                </Button>
              </div>
              {jurisprudenceResults.length > 0 && (
                <div className="space-y-2">
                  {jurisprudenceResults.map((r, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.05 }}
                    >
                      <Card className="hover:shadow-md transition-shadow">
                        <CardContent className="p-3">
                          <div className="flex items-start justify-between gap-2">
                            <a
                              href={r.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-sm font-medium text-primary hover:underline line-clamp-2"
                            >
                              {r.title}
                            </a>
                            {r.host_name && <Badge variant="outline" className="text-[9px] shrink-0">{r.host_name}</Badge>}
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground line-clamp-3">{r.snippet}</p>
                        </CardContent>
                      </Card>
                    </motion.div>
                  ))}
                </div>
              )}
              {jurisprudenceResults.length === 0 && !jurisprudenceLoading && (
                <p className="text-center text-sm text-muted-foreground py-8">
                  Digite um termo e clique em Buscar para pesquisar jurisprudência real.
                </p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
