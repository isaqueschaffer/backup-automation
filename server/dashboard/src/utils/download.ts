// Salva um blob como arquivo no navegador
export function saveBlob(data: BlobPart, filename: string, type = "application/zip") {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Erro de download com responseType "blob": o JSON de erro vem dentro do blob
export async function extractBlobError(err: unknown): Promise<string> {
  let msg = "Erro ao baixar o arquivo.";
  try {
    const axiosErr = err as { response?: { data?: Blob } };
    if (axiosErr?.response?.data instanceof Blob) {
      const text = await axiosErr.response.data.text();
      const json = JSON.parse(text);
      if (json?.detail) msg = json.detail;
    }
  } catch { /* ignora */ }
  return msg;
}
