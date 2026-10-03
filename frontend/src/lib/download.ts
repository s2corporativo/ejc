import api from "./api";

/** PDFs continuam passando pelo cliente autenticado em ambos os pedidos. */
export async function downloadGeneratedPdf(
  endpoint: string,
  filename: string,
  data?: unknown,
): Promise<void> {
  const response = await api.post(endpoint, data);
  const downloadUrl: string | undefined = response.data?.download_url;
  if (!downloadUrl) throw new Error("download_url ausente na resposta");
  const blob = await api.get(downloadUrl.replace(/^\/api/, ""), {
    responseType: "blob",
  });
  const url = URL.createObjectURL(blob.data as Blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
  } finally {
    URL.revokeObjectURL(url);
  }
}
