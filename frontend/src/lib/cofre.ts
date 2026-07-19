// ── lib/cofre.ts ─────────────────────────────────────────
// Client do Cofre de Credenciais (Configurações → Credenciais, PR-5).
//
// NÃO confundir com o módulo de API Keys: o COFRE guarda os segredos QUE O EJC
// USA para falar com serviços externos (DataJud, Groq, SMTP, Z-API…); API Keys
// emite as chaves QUE O EJC FORNECE a integradores externos.
//
// Contrato de segurança (backend routers/credential_vault.py): o valor do
// segredo NUNCA volta pela API — só last4 + metadados. Todas as rotas exigem
// superadmin; as mutadoras exigem step-up (senha_atual + código TOTP quando o
// usuário tem 2FA). Por isso NENHUM tipo aqui tem campo de valor.
import api from "./api";

// Estado do campo. `configurada`/`ausente` vêm do backend hoje; os demais são
// resultados de teste (last_test_status) reservados para os testadores (PR-4).
export type CredentialState =
  | "configurada"
  | "ausente"
  | "invalida"
  | "expirada"
  | "sem_permissao"
  | "indisponivel";

export type CredentialTipo =
  "api_key" | "token" | "login" | "senha" | "oauth_client";

/** Um campo do catálogo + estado da credencial vigente (GET /cofre-credenciais). */
export interface CampoStatus {
  field_key: string;
  tipo: CredentialTipo;
  rotulo: string;
  obrigatorio: boolean;
  estado: "configurada" | "ausente";
  last4?: string | null;
  versao?: number | null;
  origem?: string | null;
  expires_at?: string | null;
  last_test_at?: string | null;
  last_test_status?: string | null;
  last_test_detail?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ProviderStatus {
  provider_key: string;
  campos: CampoStatus[];
}

/** Metadados de uma versão (POST/DELETE e histórico). Nunca contém o valor. */
export interface CredencialMeta {
  id: string;
  provider_key: string;
  field_key: string;
  tipo: CredentialTipo;
  last4?: string | null;
  versao: number;
  ativo: boolean;
  origem: string;
  expires_at?: string | null;
  last_test_at?: string | null;
  last_test_status?: string | null;
  last_test_detail?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  revoked_at?: string | null;
  /** false ⇒ gravado mas o overlay no Settings falhou — recarregar/alertar. */
  overlay_aplicado: boolean;
}

export interface ImportItem {
  provider: string;
  field: string;
  last4: string;
}

export interface ImportResumo {
  total: number;
  importados: ImportItem[];
  overlay_aplicado: boolean;
}

/**
 * Resultado do teste de conexão de um provider (POST /{provider}/testar).
 * Nunca contém o valor — só o veredito da conexão + metadados. O backend
 * persiste last_test_* nas linhas ativas do provider.
 */
export interface TesteResultado {
  provider_key: string;
  estado: CredentialState;
  detalhe: string;
  last_test_at?: string | null;
  campos_atualizados: number;
}

/** Step-up de reautenticação enviado em toda operação mutadora. */
export interface Reauth {
  senha_atual: string;
  /** 6 dígitos — obrigatório só quando o usuário tem 2FA ativo. */
  codigo_totp?: string;
}

/** Só remove chaves vazias/undefined do corpo do step-up (o valor nunca é logado). */
function reauthBody(reauth: Reauth): Reauth {
  const body: Reauth = { senha_atual: reauth.senha_atual };
  if (reauth.codigo_totp) body.codigo_totp = reauth.codigo_totp;
  return body;
}

/** Estado do cofre agrupado por provider (só metadados; superadmin). */
export async function listarCofre(): Promise<ProviderStatus[]> {
  const { data } = await api.get<ProviderStatus[]>("/cofre-credenciais");
  return data;
}

/** Histórico de versões de um campo (só metadados). */
export async function historicoCampo(
  providerKey: string,
  fieldKey: string,
): Promise<CredencialMeta[]> {
  const { data } = await api.get<CredencialMeta[]>(
    `/cofre-credenciais/${providerKey}/${fieldKey}/historico`,
  );
  return data;
}

/**
 * Cadastra/substitui a credencial vigente de um campo. O `valor` é o segredo
 * digitado — trafega SÓ neste corpo, nunca é guardado em estado global/log; a
 * resposta traz apenas metadados (last4).
 */
export async function cadastrarCredencial(
  providerKey: string,
  fieldKey: string,
  valor: string,
  reauth: Reauth,
): Promise<CredencialMeta> {
  const { data } = await api.post<CredencialMeta>(
    `/cofre-credenciais/${providerKey}/${fieldKey}`,
    { valor, ...reauthBody(reauth) },
  );
  return data;
}

/** Revoga a credencial vigente de um campo (DELETE carrega o step-up no corpo). */
export async function revogarCredencial(
  providerKey: string,
  fieldKey: string,
  reauth: Reauth,
): Promise<CredencialMeta> {
  const { data } = await api.delete<CredencialMeta>(
    `/cofre-credenciais/${providerKey}/${fieldKey}`,
    { data: reauthBody(reauth) },
  );
  return data;
}

/** Importa para o cofre os segredos presentes no .env. Resumo sem valores. */
export async function importarEnv(reauth: Reauth): Promise<ImportResumo> {
  const { data } = await api.post<ImportResumo>(
    "/cofre-credenciais/importar-env",
    reauthBody(reauth),
  );
  return data;
}

/**
 * Testa a conexão da integração (superadmin). Não exige step-up — o teste não
 * expõe nem altera o segredo, só grava o resultado (last_test_*) no cofre.
 */
export async function testarProvider(
  providerKey: string,
): Promise<TesteResultado> {
  const { data } = await api.post<TesteResultado>(
    `/cofre-credenciais/${providerKey}/testar`,
  );
  return data;
}
