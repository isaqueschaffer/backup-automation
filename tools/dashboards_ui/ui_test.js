const puppeteer = require("puppeteer");
const fs = require("fs");

const seed = JSON.parse(fs.readFileSync("/work/seed.json", "utf8"));
const BASE = "http://host.docker.internal:7001";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const resultados = [];
const ok = (cond, msg) => { resultados.push((cond ? "OK    " : "FALHA ") + msg); };

(async () => {
  const browser = await puppeteer.launch({
    executablePath: "/usr/bin/chromium-browser",
    args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
  });
  const page = await browser.newPage();
  const erros = [];
  page.on("pageerror", (e) => erros.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error") erros.push("console: " + m.text()); });
  await page.setViewport({ width: 1500, height: 1000 });

  const clickText = async (sel, text) => {
    const achou = await page.evaluate((s, t) => {
      const el = [...document.querySelectorAll(s)].find((e) => e.textContent.trim().includes(t));
      if (!el) return false;
      el.click();
      return true;
    }, sel, text);
    if (!achou) throw new Error("nao achei " + sel + " com texto: " + text);
  };
  const corpo = () => page.evaluate(() => document.body.innerText);

  // ── Página pública ──
  await page.goto(`${BASE}/d#${seed.token}`, { waitUntil: "networkidle0" });
  await sleep(1500);
  let txt = await corpo();
  await page.screenshot({ path: "/work/pub_1.png" });
  ok(txt.includes("Cliente Demonstração"), "publico mostra o nome do cliente");
  ok(txt.includes("Saúde do servidor") && txt.includes("Servidor Principal"), "publico mostra saude do servidor com a maquina");
  ok(txt.includes("Câmeras e gravação") && txt.includes("Garagem"), "publico lista a camera com problema");
  ok(!txt.includes("10.0.0.5"), "publico sem IP");
  ok(txt.includes("Personalizar"), "botao Personalizar (link com edicao)");
  ok(!txt.includes("Compartilhar") && !txt.includes("Restaurar padrão"), "publico sem Compartilhar / Restaurar padrao");

  await clickText("button", "Personalizar");
  await sleep(1500);
  await page.screenshot({ path: "/work/pub_2_edicao.png" });
  txt = await corpo();
  ok(txt.includes("Adicionar componente") && txt.includes("Salvar") && txt.includes("Descartar"), "barra de edicao no publico");
  ok(!txt.includes("Restaurar padrão"), "edicao publica sem 'Restaurar padrao'");

  await clickText("button", "Adicionar componente");
  await sleep(500);
  await page.screenshot({ path: "/work/pub_3_adicionar.png" });
  await page.evaluate(() => {
    const cartoes = [...document.querySelectorAll(".modal *")].filter((e) => e.children.length > 0 && e.textContent.trim().startsWith("Texto"));
    const alvo = cartoes.sort((a, b) => a.textContent.length - b.textContent.length)[0];
    alvo.click();
  });
  await sleep(700);
  await page.screenshot({ path: "/work/pub_4_config.png" });
  await page.type("textarea", "Aviso de teste automático");
  await clickText("button", "Aplicar");
  await sleep(1500);
  txt = await corpo();
  ok(txt.includes("Aviso de teste automático"), "texto novo aparece na previa do rascunho");

  await clickText("button", "Salvar");
  await sleep(1500);
  await page.screenshot({ path: "/work/pub_5_salvo.png" });
  await page.reload({ waitUntil: "networkidle0" });
  await sleep(1500);
  txt = await corpo();
  ok(txt.includes("Aviso de teste automático"), "layout salvo persiste apos recarregar a pagina");

  // celular
  await page.setViewport({ width: 390, height: 844 });
  await sleep(500);
  await page.screenshot({ path: "/work/pub_mobile.png", fullPage: true });
  await page.setViewport({ width: 1500, height: 1000 });

  // ── Administração ──
  const admin = await browser.newPage();
  admin.on("pageerror", (e) => erros.push("admin pageerror: " + e.message));
  admin.on("console", (m) => { if (m.type() === "error") erros.push("admin console: " + m.text()); });
  admin.on("dialog", (d) => d.accept());
  await admin.setViewport({ width: 1500, height: 1000 });
  await admin.evaluateOnNewDocument((t) => localStorage.setItem("trilan_token", t), seed.jwt);
  const clickA = async (sel, text) => {
    const achou = await admin.evaluate((s, t) => {
      const el = [...document.querySelectorAll(s)].find((e) => e.textContent.trim().includes(t));
      if (!el) return false;
      el.click();
      return true;
    }, sel, text);
    if (!achou) throw new Error("admin: nao achei " + sel + " com texto: " + text);
  };
  const corpoA = () => admin.evaluate(() => document.body.innerText.toLowerCase());
  await admin.goto(`${BASE}/clientes/${seed.customer_id}/dashboard`, { waitUntil: "networkidle0" });
  await sleep(1500);
  await admin.screenshot({ path: "/work/admin_1.png" });
  txt = await corpoA();
  ok(txt.includes("dashboard — cliente demonstração"), "admin: titulo da pagina");
  ok(txt.includes("link ativo"), "admin: badge do link ativo");
  ok(txt.includes("compartilhar") && txt.includes("personalizar"), "admin: botoes Compartilhar e Personalizar");

  await clickA("button", "Compartilhar");
  await sleep(700);
  await admin.screenshot({ path: "/work/admin_2_compartilhar.png" });
  txt = await corpoA();
  ok(txt.includes("gerar novo link") && txt.includes("revogar link"), "admin: painel com link existente");
  ok(txt.includes("não pode ser exibido novamente"), "admin: aviso de que o link nao e exibido de novo");

  // gerar novo link: o antigo deve parar de funcionar
  await clickA("button", "Gerar novo link");
  await sleep(1500);
  await admin.screenshot({ path: "/work/admin_3_novo_link.png" });
  txt = await corpoA();
  ok(txt.includes("copie agora"), "admin: link novo mostrado uma vez, com aviso");
  const novoUrl = await admin.evaluate(() => (document.querySelector(".modal input[readonly]") || {}).value || "");
  ok(/\/d#dsh_/.test(novoUrl), "admin: URL do link no formato /d#token (" + novoUrl.slice(0, 40) + "...)");
  const novoToken = novoUrl.split("#")[1];

  const velho = await browser.newPage();
  await velho.goto(`${BASE}/d#${seed.token}`, { waitUntil: "networkidle0" });
  await sleep(800);
  ok((await velho.evaluate(() => document.body.innerText)).includes("Link inválido ou expirado"), "link antigo invalido apos gerar um novo");
  await velho.screenshot({ path: "/work/pub_invalido.png" });
  const novo = await browser.newPage();
  await novo.goto(`${BASE}/d#${novoToken}`, { waitUntil: "networkidle0" });
  await sleep(1200);
  ok((await novo.evaluate(() => document.body.innerText)).includes("Cliente Demonstração"), "link novo abre o dashboard");

  // tira a permissao de edicao pela API: visitante nao ve Personalizar
  await admin.evaluate(async (base, id, jwt) => {
    await fetch(`${base}/api/v1/clients/${id}/dashboard/share`, { method: "PUT", headers: { "Content-Type": "application/json", Authorization: "Bearer " + jwt }, body: JSON.stringify({ permite_edicao: false }) });
  }, BASE, seed.customer_id, seed.jwt);
  await novo.reload({ waitUntil: "networkidle0" });
  await sleep(1200);
  const semEdicao = await novo.evaluate(() => document.body.innerText);
  ok(!semEdicao.includes("Personalizar"), "sem permissao de edicao: botao Personalizar some");

  // admin: modo edicao
  await admin.keyboard.press("Escape");
  await sleep(300);
  await clickA("button", "Personalizar");
  await sleep(1500);
  await admin.screenshot({ path: "/work/admin_4_edicao.png" });
  txt = await corpoA();
  ok(txt.includes("restaurar padrão"), "admin: edicao tem 'Restaurar padrao'");

  // admin: revogar
  await clickA("button", "Descartar");
  await sleep(500);
  await clickA("button", "Compartilhar");
  await sleep(500);
  await clickA("button", "Revogar link");
  await sleep(1200);
  txt = await corpoA();
  ok(txt.includes("gerar link") && !txt.includes("revogar link"), "admin: apos revogar volta a oferecer 'Gerar link'");
  await novo.reload({ waitUntil: "networkidle0" });
  await sleep(1000);
  ok((await novo.evaluate(() => document.body.innerText)).includes("Link inválido ou expirado"), "link revogado deixa de funcionar");

  console.log(resultados.join("\n"));
  console.log("\nERROS NO NAVEGADOR (" + erros.length + "):");
  erros.slice(0, 15).forEach((e) => console.log(" - " + e));
  await browser.close();
})().catch((e) => { console.log(resultados.join("\n")); console.log("ERRO NO TESTE:", e.message); process.exit(1); });
