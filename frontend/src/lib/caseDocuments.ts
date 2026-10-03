import api from "./api";

export function uploadCaseDocument(
  caseId: string,
  file: File,
  titulo: string,
  tipo: string,
) {
  const body = new FormData();
  body.append("file", file);
  body.append("titulo", titulo.trim() || file.name);
  body.append("tipo", tipo);
  body.append("case_id", caseId);
  return api.post("/documents/upload", body, {
    headers: { "Content-Type": "multipart/form-data" },
  });
}
