// Tipos compartilhados entre frontend e backend

export interface TemplateField {
  key: string;
  label: string;
  type: "text" | "textarea" | "select";
  options?: string[];
  placeholder?: string;
}

export interface TemplateDTO {
  id: string;
  slug: string;
  name: string;
  category: string;
  description: string;
  icon: string;
  fields: TemplateField[];
}

export interface SkillDTO {
  id: string;
  slug: string;
  name: string;
  category: string;
  description: string;
  content: string;
  locked: boolean;
}

export interface NewsDTO {
  id: string;
  slug: string;
  title: string;
  summary: string;
  body: string;
  category: string;
  date: string;
}

export interface DocumentDTO {
  id: string;
  title: string;
  templateSlug: string;
  templateName: string;
  anonymizedFacts: string;
  generatedContent: string;
  skillSlugs: string[];
  status: string;
  batchId: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface GenerateMinutaRequest {
  templateSlug: string;
  fields: Record<string, string>;
  skillSlugs: string[];
  title?: string;
  batchId?: string;
}

export interface GenerateMinutaResponse {
  document: DocumentDTO;
  rawMarkers: Record<string, string>;
  tokensUsed?: number;
}

export interface JurisprudenceResult {
  url: string;
  name: string;
  snippet: string;
  host_name: string;
  rank: number;
  date?: string;
}

export interface JurisprudenceResponse {
  query: string;
  mode: string;
  results: JurisprudenceResult[];
  cached?: boolean;
}
