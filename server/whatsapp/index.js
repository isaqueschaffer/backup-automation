/**
 * Ponte de WhatsApp do Trilan.
 *
 * Mantém UMA sessão do WhatsApp (Baileys, protocolo do WhatsApp Web) e expõe uma API HTTP interna que a API do Trilan
 * chama. Rotas de envio:
 *
 *   POST /message/sendText/:instance    { number, text }
 *   POST /message/sendMedia/:instance   { number, mediatype:"image", mimetype, caption, media(base64), fileName }
 *
 * Extras (usados pelo painel, via API do Trilan):
 *   GET  /status   -> { instance, connected, hasQr, number }
 *   GET  /qr       -> { connected, qr: "data:image/png;base64,..." | null }
 *   POST /logout   -> desconecta o aparelho, apaga a sessão e volta a gerar QR
 *   GET  /health   -> sem autenticação (healthcheck do Docker)
 *
 * Autenticação: header "apikey" igual à variável API_KEY. Não exponha esta porta fora da rede do Docker.
 */
const crypto = require('crypto');
const fs = require('fs');
const express = require('express');
const QRCode = require('qrcode');
const pino = require('pino');
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require('@whiskeysockets/baileys');

const PORT = Number(process.env.PORT || 3000);
const API_KEY = process.env.API_KEY || '';
const INSTANCE = process.env.INSTANCE_NAME || 'trilan';
const AUTH_DIR = process.env.AUTH_DIR || '/data/auth';

if (!API_KEY || API_KEY.length < 16) {
  // Fica ocioso (em vez de encerrar): com `restart: unless-stopped`, sair viraria um loop de reinícios até a
  // chave ser definida (WHATSAPP_BRIDGE_KEY no .env/Dokploy, mínimo 16 caracteres). O WhatsApp fica desligado.
  console.error('[whatsapp] API_KEY ausente ou curta demais (mínimo 16 caracteres). WhatsApp DESLIGADO: defina WHATSAPP_BRIDGE_KEY e reinicie este container.');
  setInterval(() => {}, 1 << 30);
  process.on('SIGTERM', () => process.exit(0));
  return;
}

const logger = pino({ level: process.env.LOG_LEVEL || 'warn' });
const log = (...a) => console.log('[whatsapp]', ...a);

// ─── Sessão do WhatsApp ─────────────────────────────────────────────────────

let sock = null;
let connected = false;
let latestQr = null;
let starting = false;
let reconnectTimer = null;

function agendarReconexao(ms) {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => start().catch((e) => log('falha ao reconectar:', e.message)), ms);
}

async function start() {
  if (starting || connected) return;
  starting = true;
  try {
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

    // O WhatsApp recusa versões de protocolo antigas: usa a mais recente e, se não der, a embutida na biblioteca
    let version;
    try {
      ({ version } = await fetchLatestBaileysVersion());
    } catch (e) {
      log('não consegui buscar a versão mais recente do protocolo, usando a da biblioteca:', e.message);
    }

    sock = makeWASocket({
      auth: state,
      version,
      logger,
      browser: ['Trilan Backup', 'Chrome', '1.0.0'],
      syncFullHistory: false,
      markOnlineOnConnect: false,
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        latestQr = qr;
        log('QR code gerado. Escaneie pelo painel (Configurações > WhatsApp).');
      }

      if (connection === 'open') {
        connected = true;
        latestQr = null;
        log('Conectado ao WhatsApp.');
      }

      if (connection === 'close') {
        connected = false;
        sock = null;
        starting = false;
        const code = lastDisconnect?.error?.output?.statusCode;

        if (code === DisconnectReason.loggedOut) {
          log('Aparelho desconectado pelo celular. Limpando a sessão e gerando novo QR.');
          limparSessao();
          agendarReconexao(1000);
        } else {
          // inclui o "restartRequired" que o WhatsApp pede logo depois de ler o QR
          log(`Conexão encerrada (código ${code ?? 'desconhecido'}). Reconectando...`);
          agendarReconexao(code === DisconnectReason.restartRequired ? 500 : 3000);
        }
      }
    });
  } finally {
    starting = false;
  }
}

function limparSessao() {
  try {
    fs.rmSync(AUTH_DIR, { recursive: true, force: true });
    fs.mkdirSync(AUTH_DIR, { recursive: true });
  } catch (e) {
    log('erro ao limpar a sessão:', e.message);
  }
}

// ─── API HTTP ───────────────────────────────────────────────────────────────

const app = express();
app.use(express.json({ limit: '25mb' })); // fotos das câmeras vão em base64

app.get('/health', (_req, res) => res.json({ ok: true }));

function autenticar(req, res, next) {
  const recebida = Buffer.from(String(req.get('apikey') || ''));
  const esperada = Buffer.from(API_KEY);
  if (recebida.length !== esperada.length || !crypto.timingSafeEqual(recebida, esperada)) {
    return res.status(401).json({ error: 'apikey inválida' });
  }
  next();
}
app.use(autenticar);

function exigirConectado(_req, res, next) {
  if (!sock || !connected) return res.status(503).json({ error: 'WhatsApp não conectado. Leia o QR code no painel.' });
  next();
}

function exigirInstancia(req, res, next) {
  if (req.params.instance !== INSTANCE) return res.status(404).json({ error: `instância '${req.params.instance}' não existe` });
  next();
}

/** Resolve o número para o JID real (cobre a diferença do 9º dígito dos celulares brasileiros). */
async function resolverJid(number) {
  const digitos = String(number || '').replace(/\D/g, '');
  if (digitos.length < 8) throw Object.assign(new Error('número inválido'), { status: 400 });
  const [res] = (await sock.onWhatsApp(digitos)) || [];
  if (!res || !res.exists) throw Object.assign(new Error(`o número ${digitos} não tem WhatsApp`), { status: 404 });
  return res.jid;
}

function tratarErro(res, e) {
  const status = e.status || 500;
  if (status >= 500) log('erro no envio:', e.message);
  res.status(status).json({ error: e.message });
}

app.post('/message/sendText/:instance', exigirInstancia, exigirConectado, async (req, res) => {
  try {
    const { number, text } = req.body || {};
    if (!text) return res.status(400).json({ error: 'text obrigatório' });
    const jid = await resolverJid(number);
    const sent = await sock.sendMessage(jid, { text: String(text) });
    res.status(201).json({ key: sent?.key });
  } catch (e) {
    tratarErro(res, e);
  }
});

app.post('/message/sendMedia/:instance', exigirInstancia, exigirConectado, async (req, res) => {
  try {
    const { number, mediatype, caption, media, mimetype, fileName } = req.body || {};
    if (mediatype !== 'image') return res.status(400).json({ error: "só mediatype 'image' é suportado" });
    if (!media) return res.status(400).json({ error: 'media (base64) obrigatório' });
    const jid = await resolverJid(number);
    const buffer = Buffer.from(String(media).replace(/^data:[^,]*,/, ''), 'base64');
    const sent = await sock.sendMessage(jid, {
      image: buffer,
      caption: caption || undefined,
      mimetype: mimetype || 'image/jpeg',
      fileName: fileName || undefined,
    });
    res.status(201).json({ key: sent?.key });
  } catch (e) {
    tratarErro(res, e);
  }
});

app.get('/status', (_req, res) => {
  res.json({
    instance: INSTANCE,
    connected,
    hasQr: Boolean(latestQr),
    number: connected && sock?.user?.id ? sock.user.id.split(':')[0].split('@')[0] : null,
  });
});

app.get('/qr', async (_req, res) => {
  if (connected || !latestQr) return res.json({ connected, qr: null });
  try {
    res.json({ connected: false, qr: await QRCode.toDataURL(latestQr, { margin: 1, width: 320 }) });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/logout', async (_req, res) => {
  try {
    clearTimeout(reconnectTimer);
    if (sock) {
      try { await sock.logout(); } catch { /* já desconectado */ }
      try { sock.end(undefined); } catch { /* idem */ }
    }
    sock = null;
    connected = false;
    latestQr = null;
    limparSessao();
    agendarReconexao(500);
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.listen(PORT, () => {
  log(`API na porta ${PORT} (instância '${INSTANCE}')`);
  start().catch((e) => {
    log('falha ao iniciar a sessão:', e.message);
    agendarReconexao(5000);
  });
});

process.on('unhandledRejection', (e) => log('promessa rejeitada:', e?.message || e));
process.on('SIGTERM', () => process.exit(0));
