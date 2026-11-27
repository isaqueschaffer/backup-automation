// Mensagem de erro vinda da API (campo detail) ou texto padrão
export function apiErrorMessage(err: unknown, fallback: string): string {
  const e = err as { response?: { data?: { detail?: unknown } } };
  const detail = e?.response?.data?.detail;
  return typeof detail === "string" && detail ? detail : fallback;
}
