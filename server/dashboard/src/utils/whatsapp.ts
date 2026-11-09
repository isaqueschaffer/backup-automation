// Números de WhatsApp: o servidor guarda só dígitos com DDI (ex.: 5511999998888); aqui só se lê e se mostra.

// "(11) 99999-8888; 21 98888-7777" → ["(11) 99999-8888", "21 98888-7777"]
// Aceita vírgula, ponto e vírgula e quebra de linha; remove vazios e repetidos. O servidor normaliza e valida.
export const parseWhatsappList = (s: string): string[] =>
  Array.from(new Set(s.split(/[,;\n]/).map(e => e.trim()).filter(Boolean)));

// "5511999998888" → "+55 11 99999-8888" (só exibição; número fora do padrão BR aparece como "+<dígitos>")
export const formatWhatsapp = (n: string): string => {
  const m = /^55(\d{2})(\d{4,5})(\d{4})$/.exec(n);
  return m ? `+55 ${m[1]} ${m[2]}-${m[3]}` : `+${n}`;
};
