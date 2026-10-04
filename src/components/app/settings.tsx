"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  User,
  Building2,
  PenLine,
  Sparkles,
  Save,
  Check,
  FileText,
  Briefcase,
  Mail,
  Phone,
  MapPin,
  Award,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAppStore, type WritingStyle } from "@/lib/store";
import { toast } from "@/hooks/use-toast";
import type { SkillDTO } from "@/lib/types";

const UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"];

const STYLES: { id: WritingStyle; label: string; desc: string; example: string }[] = [
  {
    id: "formal",
    label: "Formal técnico",
    desc: "Linguagem jurídica tradicional, com citações de artigos e fundamentação completa.",
    example: "O autor, com fundamento no art. 927 do Código Civil, pleiteia a condenação do réu...",
  },
  {
    id: "sintetico",
    label: "Sintético direto",
    desc: "Conciso, com fundamentos essenciais. Ideal para processos de massa e repetitivos.",
    example: "Cabível a indenização por dano moral (art. 927, CC), conforme fundamentos a seguir.",
  },
  {
    id: "academic",
    label: "Acadêmico doutrinário",
    desc: "Com citações doutrinárias e jurisprudência detalhada. Ideal para petições complexas.",
    example: "Conforme ensina Maria Helena Diniz, a responsabilidade civil objetiva...",
  },
  {
    id: "direto",
    label: "Linguagem simples",
    desc: "Redação clara e acessível, sem jargão excessivo. Para audiências de conciliação.",
    example: "O autor pede que o réu pague a indenização pelos danos sofridos...",
  },
];

export function Settings() {
  const { profile, setProfile, writingStyle, setWritingStyle, defaultSkills, toggleDefaultSkill } = useAppStore();
  const [skills, setSkills] = useState<SkillDTO[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch("/api/skills")
      .then((r) => r.json())
      .then((d) => setSkills(d.skills || []))
      .catch(() => null);
  }, []);

  function save() {
    setSaving(true);
    setTimeout(() => {
      setSaving(false);
      toast({
        title: "Perfil salvo",
        description: `Estilo de redação: ${STYLES.find((s) => s.id === writingStyle)?.label}`,
      });
    }, 600);
  }

  return (
    <div className="container-juridia py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight">Configurações</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Configure seu perfil de advogado e o estilo de redação que a IA usará
          ao gerar suas minutas.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Coluna principal */}
        <div className="space-y-6 lg:col-span-2">
          {/* Perfil profissional */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <User className="h-4 w-4 text-primary" />
                Perfil profissional
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="name" className="text-xs">
                    <User className="mr-1 inline h-3 w-3" /> Nome completo
                  </Label>
                  <Input
                    id="name"
                    value={profile.name}
                    onChange={(e) => setProfile({ name: e.target.value })}
                    placeholder="Seu nome"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="office" className="text-xs">
                    <Building2 className="mr-1 inline h-3 w-3" /> Escritório
                  </Label>
                  <Input
                    id="office"
                    value={profile.office}
                    onChange={(e) => setProfile({ office: e.target.value })}
                    placeholder="Nome do escritório"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="oab" className="text-xs">
                    <Award className="mr-1 inline h-3 w-3" /> Número OAB
                  </Label>
                  <Input
                    id="oab"
                    value={profile.oab}
                    onChange={(e) => setProfile({ oab: e.target.value })}
                    placeholder="000000"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="oabUf" className="text-xs">UF da OAB</Label>
                  <Select
                    value={profile.oabUf}
                    onValueChange={(v) => setProfile({ oabUf: v })}
                  >
                    <SelectTrigger id="oabUf">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {UFS.map((uf) => (
                        <SelectItem key={uf} value={uf}>{uf}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="email" className="text-xs">
                    <Mail className="mr-1 inline h-3 w-3" /> E-mail
                  </Label>
                  <Input
                    id="email"
                    type="email"
                    value={profile.email}
                    onChange={(e) => setProfile({ email: e.target.value })}
                    placeholder="voce@escritorio.com.br"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="phone" className="text-xs">
                    <Phone className="mr-1 inline h-3 w-3" /> Telefone
                  </Label>
                  <Input
                    id="phone"
                    value={profile.phone}
                    onChange={(e) => setProfile({ phone: e.target.value })}
                    placeholder="(00) 00000-0000"
                  />
                </div>
                <div className="space-y-1.5 sm:col-span-2">
                  <Label htmlFor="address" className="text-xs">
                    <MapPin className="mr-1 inline h-3 w-3" /> Endereço profissional
                  </Label>
                  <Input
                    id="address"
                    value={profile.address}
                    onChange={(e) => setProfile({ address: e.target.value })}
                    placeholder="Rua, número, cidade/UF"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Estilo de redação */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <PenLine className="h-4 w-4 text-primary" />
                Estilo de redação
              </CardTitle>
            </CardHeader>
            <CardContent>
              <RadioGroup
                value={writingStyle}
                onValueChange={(v) => setWritingStyle(v as WritingStyle)}
                className="space-y-3"
              >
                {STYLES.map((s) => (
                  <label
                    key={s.id}
                    htmlFor={`style-${s.id}`}
                    className={`flex cursor-pointer gap-3 rounded-lg border p-4 transition-all ${
                      writingStyle === s.id
                        ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                        : "border-border bg-card hover:border-primary/40"
                    }`}
                  >
                    <RadioGroupItem
                      id={`style-${s.id}`}
                      value={s.id}
                      className="mt-1"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between">
                        <span className="font-medium">{s.label}</span>
                        {writingStyle === s.id && (
                          <Badge variant="secondary" className="gap-1 text-[10px]">
                            <Check className="h-3 w-3" /> Selecionado
                          </Badge>
                        )}
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">{s.desc}</p>
                      <div className="mt-2 rounded-md border border-dashed border-border bg-secondary/40 p-2.5">
                        <p className="font-mono text-[11px] italic text-muted-foreground">
                          “{s.example}”
                        </p>
                      </div>
                    </div>
                  </label>
                ))}
              </RadioGroup>
            </CardContent>
          </Card>

          {/* Skills padrão */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Sparkles className="h-4 w-4 text-primary" />
                Habilidades padrão
                <Badge variant="outline" className="ml-auto text-[10px]">
                  {defaultSkills.length} ativas
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-3 text-xs text-muted-foreground">
                Estas habilidades serão aplicadas automaticamente em todas as
                minutas geradas, sem precisar selecioná-las manualmente.
              </p>
              <div className="grid gap-2 sm:grid-cols-2">
                {skills.map((s) => {
                  const active = defaultSkills.includes(s.slug);
                  return (
                    <button
                      key={s.slug}
                      onClick={() => toggleDefaultSkill(s.slug)}
                      className={`flex items-start gap-2 rounded-lg border p-3 text-left transition-all ${
                        active
                          ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                          : "border-border bg-card hover:border-primary/40"
                      }`}
                    >
                      {active ? (
                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                      ) : (
                        <div className="mt-0.5 h-4 w-4 shrink-0 rounded-full border-2 border-muted-foreground/30" />
                      )}
                      <div className="min-w-0">
                        <div className="text-xs font-semibold">{s.name}</div>
                        <div className="mt-0.5 text-[11px] text-muted-foreground line-clamp-2">
                          {s.description}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Sidebar: preview */}
        <div className="space-y-4">
          <Card className="sticky top-32">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <FileText className="h-4 w-4 text-primary" />
                Assinatura preview
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="rounded-lg border border-border bg-secondary/40 p-4">
                <div className="border-b border-border pb-3 text-center">
                  <Briefcase className="mx-auto mb-1 h-5 w-5 text-primary" />
                  <div className="text-sm font-semibold">{profile.office || "—"}</div>
                  <div className="mt-0.5 text-xs text-muted-foreground">
                    Advocacia & Consultoria Jurídica
                  </div>
                </div>
                <div className="space-y-1.5 py-3 text-xs">
                  <div className="font-semibold">{profile.name || "—"}</div>
                  <div className="text-muted-foreground">
                    OAB/{profile.oabUf} {profile.oab || "—"}
                  </div>
                  <div className="text-muted-foreground">{profile.email || "—"}</div>
                  <div className="text-muted-foreground">{profile.phone || "—"}</div>
                  <div className="text-muted-foreground">{profile.address || "—"}</div>
                </div>
                <div className="border-t border-border pt-3 text-center text-[10px] text-muted-foreground">
                  Estilo ativo: <strong className="text-foreground">
                    {STYLES.find((s) => s.id === writingStyle)?.label}
                  </strong>
                </div>
              </div>
              <Button className="mt-4 w-full" onClick={save} disabled={saving}>
                {saving ? (
                  <Save className="mr-2 h-4 w-4 animate-pulse" />
                ) : (
                  <Save className="mr-2 h-4 w-4" />
                )}
                Salvar configurações
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
