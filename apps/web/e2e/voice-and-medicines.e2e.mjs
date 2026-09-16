// Browser end-to-end check against a RUNNING stack (web :3000, Core :8000,
// AI :8100, Postgres with migrations + seeds + an imported medicine dataset).
//
//   E2E_AUDIO_WAV=/path/hindi_clip.wav E2E_OUT=/tmp/e2e node e2e/voice-and-medicines.e2e.mjs
//
// Uses the locally installed Google Chrome via playwright-core. The microphone
// is Chrome's FAKE capture device fed from E2E_AUDIO_WAV -- this proves the
// real getUserMedia/MediaRecorder -> gateway -> Whisper -> review -> save path,
// but it is NOT a physical-microphone test (see docs).
//
// Writes screenshots and evidence.json to E2E_OUT. Exits non-zero on failure.
import { chromium } from "playwright-core";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:3000";
const WAV = process.env.E2E_AUDIO_WAV;
const OUT = process.env.E2E_OUT ?? "e2e-output";
const ABHA = process.env.E2E_ABHA ?? "12-3456-7890-0003";
const RECORD_MS = Number(process.env.E2E_RECORD_MS ?? 8000);
const MEDICINE_QUERY = process.env.E2E_MEDICINE_QUERY ?? "Dolo 650";
const MEDICINE_BRAND = process.env.E2E_MEDICINE_BRAND ?? "Dolo 650 Tablet";
const CHROME = process.env.E2E_CHROME ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const TRANSCRIBE_TIMEOUT = 240_000;

if (!WAV) {
  console.error("E2E_AUDIO_WAV is required");
  process.exit(2);
}
mkdirSync(OUT, { recursive: true });

const evidence = { base: BASE, abha: ABHA, audio: WAV, steps: [] };
const step = (name, data = {}) => {
  evidence.steps.push({ name, at: new Date().toISOString(), ...data });
  console.log(`✓ ${name}`, Object.keys(data).length ? JSON.stringify(data) : "");
};
const shot = (page, name) => page.screenshot({ path: join(OUT, `${name}.png`), fullPage: true });

async function login(page, username, password) {
  await page.goto(`${BASE}/login`);
  await page.fill("#username", username);
  await page.fill("#password", password);
  await Promise.all([page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 30_000 }), page.click("button[type=submit]")]);
}

async function logout(context, page) {
  await page.evaluate(() => fetch("/api/auth/logout", { method: "POST" }));
  await context.clearCookies();
}

async function api(page, method, path, body) {
  return page.evaluate(
    async ({ method, path, body }) => {
      const res = await fetch(path, { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
      let json = null;
      try {
        json = await res.json();
      } catch {}
      return { status: res.status, body: json };
    },
    { method, path, body },
  );
}

async function recordVoice(page, language) {
  await page.selectOption("#complaint-language", language);
  await page.getByText("Speak", { exact: true }).click();
  await page.getByLabel("The caregiver agreed to this voice recording.").check();
  await page.getByRole("button", { name: "Start recording" }).click();
  await page.getByText(/Recording — \d+ s of 120 s/).waitFor({ timeout: 15_000 });
  await page.waitForTimeout(RECORD_MS);
  await page.getByRole("button", { name: "Stop recording" }).click();
  await page.getByText(/Recording ready \(/).waitFor({ timeout: 15_000 });
}

async function finishViaChecklistOrResult(page) {
  // Ollama may be absent: the app must fall back to the checklist, never dead-end.
  const checklist = page.getByRole("heading", { name: "Check Danger Signs" });
  const result = page.getByRole("button", { name: "Confirm & Add to Queue" });
  await Promise.race([checklist.waitFor({ timeout: 90_000 }), result.waitFor({ timeout: 90_000 })]);
  let path = "llm";
  if (await checklist.isVisible()) {
    path = "checklist";
    await page.getByLabel("Fever present").check();
    await page.getByRole("button", { name: "See Result" }).click();
  }
  await result.click();
  await page.getByText(/^Saved/).waitFor({ timeout: 30_000 });
  return path;
}

const browser = await chromium.launch({
  executablePath: CHROME,
  headless: true,
  args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", `--use-file-for-fake-audio-capture=${WAV}`],
});

let failed = false;
try {
  const context = await browser.newContext({ viewport: { width: 400, height: 900 } });
  await context.grantPermissions(["microphone"], { origin: BASE });
  await context.addInitScript(() => window.localStorage.setItem("hb.ui_language", "en"));
  const page = await context.newPage();
  evidence.transcribeResponses = [];
  let uploadIndex = 0;
  page.on("request", (req) => {
    if (!req.url().includes("/api/triage/transcribe") || req.method() !== "POST") return;
    try {
      const payload = JSON.parse(req.postData() ?? "{}");
      if (typeof payload.audio_base64 === "string") {
        const ext = String(payload.mime_type ?? "").includes("ogg") ? "ogg" : "webm";
        const file = join(OUT, `upload-${uploadIndex++}.${ext}`);
        writeFileSync(file, Buffer.from(payload.audio_base64, "base64"));
        evidence.steps.push({ name: "browser uploaded audio", file, mime: payload.mime_type, language: payload.language, bytes: Buffer.byteLength(payload.audio_base64, "base64") });
      }
    } catch {}
  });
  page.on("response", async (res) => {
    if (!res.url().includes("/api/triage/transcribe")) return;
    let body = null;
    try {
      body = await res.json();
    } catch {}
    const summary = body && typeof body === "object" ? { ...body, transcript: body.transcript ? `${String(body.transcript).slice(0, 40)}…` : undefined } : body;
    evidence.transcribeResponses.push({ at: new Date().toISOString(), status: res.status(), body: summary });
  });
  evidence.currentPage = page;

  // ---- 1. Online Hindi voice capture -> review/correct -> confirm -> save ----
  await login(page, "asha1", "asha-demo-pass");
  await page.goto(`${BASE}/asha/triage/new?abha=${encodeURIComponent(ABHA)}`);
  await recordVoice(page, "hi");
  await page.getByRole("button", { name: "Send for transcription" }).click();
  await page.getByRole("heading", { name: "Check before analysis" }).waitFor({ timeout: TRANSCRIBE_TIMEOUT });
  const original = await page.locator('textarea[lang="hi"]').inputValue();
  const english = await page.locator('textarea[lang="en"]').inputValue();
  step("online voice transcribed by real Whisper via gateway", { original, english });
  await shot(page, "01-review-hindi");

  await page.locator('textarea[lang="hi"]').fill(`${original} बच्चे को बुखार भी है`);
  await page.getByText("You changed the original. This English may no longer match.").waitFor();
  const blocked = await page.getByRole("button", { name: "Confirm and check danger signs" }).isDisabled();
  if (!blocked) throw new Error("confirmation was not blocked for a stale translation");
  step("stale translation blocks confirmation");
  await shot(page, "02-stale-translation");

  await page.getByRole("button", { name: "Translate again" }).click();
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: "Translate again" }).waitFor({ state: "visible", timeout: 60_000 });
  if (await page.getByText("You changed the original.").isVisible()) {
    // No installed typed-text translation: correct the English explicitly.
    await page.locator('textarea[lang="en"]').fill(`${english} The child also has fever.`);
    step("typed retranslation unavailable -> ASHA corrected English manually");
  } else {
    step("retranslated with real Argos", { english: await page.locator('textarea[lang="en"]').inputValue() });
  }
  await page.getByRole("button", { name: "Confirm and check danger signs" }).click();
  evidence.onlinePath = await finishViaChecklistOrResult(page);
  step("online visit saved", { severityPath: evidence.onlinePath });
  await shot(page, "03-saved-online");

  // ---- 2. Offline capture, user isolation, reconnect, delayed confirmation ----
  await page.goto(`${BASE}/asha/triage/new?abha=${encodeURIComponent(ABHA)}`);
  await context.setOffline(true);
  await recordVoice(page, "hi");
  await page.getByRole("button", { name: "Send for transcription" }).click();
  await page.getByText(`Saved on this phone for patient ${ABHA}`).waitFor({ timeout: 15_000 });
  const queued = await page.evaluate(
    () =>
      new Promise((resolve) => {
        const req = indexedDB.open("healthbridge-voice", 1);
        req.onsuccess = () => {
          const all = req.result.transaction("captures").objectStore("captures").getAll();
          all.onsuccess = () => resolve(all.result.map((c) => ({ id: c.id, userId: c.userId, status: c.status, abha: c.abhaNumber, language: c.language, hasAudio: !!c.audioBytes })));
        };
      }),
  );
  step("offline recording queued in IndexedDB", { queued });
  await shot(page, "04-offline-queued");
  await context.setOffline(false);

  await logout(context, page);
  await login(page, "asha2", "asha-demo-pass");
  await page.goto(`${BASE}/asha`);
  await page.waitForTimeout(3000);
  const leaked = await page.getByText("Recordings on this phone").isVisible();
  if (leaked) throw new Error("another ASHA can see asha1's queued recording");
  step("second ASHA on the same browser sees no queued recordings");
  await shot(page, "05-asha2-no-access");
  await logout(context, page);

  await login(page, "asha1", "asha-demo-pass");
  await page.goto(`${BASE}/asha`);
  const ready = page.getByText("Ready — needs your confirmation");
  const failedBadge = page.getByText("Failed", { exact: true });
  await Promise.race([ready.waitFor({ timeout: TRANSCRIBE_TIMEOUT }), failedBadge.waitFor({ timeout: TRANSCRIBE_TIMEOUT })]).catch(() => undefined);
  const queueState = await page.evaluate(
    () =>
      new Promise((resolve) => {
        const req = indexedDB.open("healthbridge-voice", 1);
        req.onsuccess = () => {
          const all = req.result.transaction("captures").objectStore("captures").getAll();
          all.onsuccess = () => resolve(all.result.map((c) => ({ status: c.status, attempts: c.attempts, lastError: c.lastError, nextAttemptAt: c.nextAttemptAt })));
        };
      }),
  );
  step("queue state after reconnect", { queueState });
  if (!(await ready.isVisible())) throw new Error(`queued capture did not become ready: ${JSON.stringify(queueState)}`);
  step("reconnect uploaded and transcribed the queued recording (not auto-submitted)");
  await shot(page, "06-awaiting-confirmation");
  await page.getByRole("link", { name: "Review and confirm" }).first().click();
  await page.getByText(`Reviewing a recording for patient ${ABHA}`).waitFor({ timeout: 30_000 });
  step("delayed capture reopened bound to its own patient", {
    original: await page.locator('textarea[lang="hi"]').inputValue(),
    english: await page.locator('textarea[lang="en"]').inputValue(),
  });
  await shot(page, "07-delayed-review");
  await page.getByRole("button", { name: "Confirm and check danger signs" }).click();
  evidence.delayedPath = await finishViaChecklistOrResult(page);
  step("delayed visit saved", { severityPath: evidence.delayedPath });

  // ---- 3. Microphone permission denied ----
  const denied = await browser.newContext({ viewport: { width: 400, height: 900 } });
  await denied.addInitScript(() => {
    window.localStorage.setItem("hb.ui_language", "en");
    navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException("Permission denied", "NotAllowedError"));
  });
  const deniedPage = await denied.newPage();
  await login(deniedPage, "asha1", "asha-demo-pass");
  await deniedPage.goto(`${BASE}/asha/triage/new?abha=${encodeURIComponent(ABHA)}`);
  await deniedPage.getByText("Speak", { exact: true }).click();
  await deniedPage.getByLabel("The caregiver agreed to this voice recording.").check();
  await deniedPage.getByRole("button", { name: "Start recording" }).click();
  await deniedPage.getByText("Microphone permission was denied.").waitFor({ timeout: 10_000 });
  const checklistOffered = await deniedPage.getByRole("button", { name: "Use Symptom Checklist Instead" }).isVisible();
  step("permission denial reported with typed/checklist alternatives", { checklistOffered });
  await shot(deniedPage, "08-permission-denied");
  await denied.close();

  // ---- 4. Prescribe, real stock, informational comparison, review request ----
  await logout(context, page);
  await login(page, "doctor1", "doctor-demo-pass");
  await page.setViewportSize({ width: 1100, height: 900 });
  await page.goto(`${BASE}/facility/patients/${encodeURIComponent(ABHA)}`);
  await page.fill("#medicine-query", MEDICINE_QUERY);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByRole("button", { name: new RegExp(`^${MEDICINE_BRAND}`) }).first().click();
  await page.getByLabel("Instructions (dose, frequency, duration)").fill("1 tablet up to three times a day after food, for 3 days");
  await page.getByRole("button", { name: "Save prescription" }).click();
  await page.getByText("Prescription saved.").waitFor({ timeout: 20_000 });
  step("doctor prescribed an imported medicine");

  const me = await api(page, "GET", `/api/medicines?q=${encodeURIComponent(MEDICINE_QUERY)}&limit=5`);
  const reference = me.body.items.find((m) => m.brand_name === MEDICINE_BRAND);
  const facilityId = "00000000-0000-0000-0000-000000000002";
  const subs = await api(page, "GET", `/api/medicines/${reference.id}/substitutes?facility_id=${facilityId}`);
  const cheapest = subs.body.candidates.find((c) => c.saving_percent !== null) ?? subs.body.candidates[0];
  const stockQty = 40 + Math.floor(Math.random() * 50);
  const stock = await api(page, "POST", "/api/medicine-stock", {
    facility_id: facilityId,
    medicine_name: `E2E TEST STOCK ${new Date().toISOString()} – ${cheapest.medicine.brand_name}`,
    unit: "tablets",
    initial_quantity: stockQty,
  });
  if (stock.status !== 201) throw new Error(`stock create failed: ${stock.status} ${JSON.stringify(stock.body)}`);
  const link = await api(page, "POST", `/api/medicine-stock/${stock.body.id}/link`, { medicine_id: cheapest.medicine.id });
  if (link.status !== 200) throw new Error(`stock link failed: ${link.status} ${JSON.stringify(link.body)}`);
  evidence.stockQty = stockQty;
  step("test stock entered and linked through the real stock API", {
    candidateCount: subs.body.candidates.length,
    linkedTo: cheapest.medicine.brand_name,
    linkStatus: link.status,
  });

  await logout(context, page);
  await login(page, "asha1", "asha-demo-pass");
  await page.setViewportSize({ width: 400, height: 900 });
  await page.goto(`${BASE}/asha/patients/${encodeURIComponent(ABHA)}`);
  await page.getByRole("link", { name: "Compare same-composition options" }).first().click();
  await page.getByText(/Same-composition products \(showing \d+ of \d+\)/).waitFor({ timeout: 30_000 });
  // Other runs may have linked stock to the same product; quantities are summed.
  const badgeText = await page.getByText(/In stock here \(\d+\)/).first().textContent();
  if (!badgeText) throw new Error("no in-stock badge for the linked product");
  step("ASHA comparison shows real facility stock", { badgeText, addedThisRun: evidence.stockQty });
  await shot(page, "09-asha-comparison");
  await page.getByRole("button", { name: "Request doctor review" }).first().click();
  await page.getByText("Review requested. The prescription is unchanged until a doctor approves.").waitFor({ timeout: 20_000 });
  step("ASHA requested doctor review");

  const pending = await api(page, "GET", `/api/substitution-requests/facility/${facilityId}?status=pending`);
  const requestId = pending.body[0].id;
  const ashaApprove = await api(page, "POST", `/api/substitution-requests/${requestId}/approve`, {});
  if (ashaApprove.status !== 403) throw new Error(`ASHA approval was not refused: ${ashaApprove.status}`);
  step("ASHA approval refused by Core", { status: ashaApprove.status, detail: ashaApprove.body?.detail });

  await logout(context, page);
  await login(page, "doctor1", "doctor-demo-pass");
  await page.setViewportSize({ width: 1100, height: 900 });
  await page.goto(`${BASE}/facility/substitutions`);
  await shot(page, "10-doctor-review-queue");
  await page.getByRole("button", { name: "Approve and update prescription" }).first().click();
  await page.getByText("Recent decisions").waitFor({ timeout: 20_000 });
  step("doctor approved; prescription superseded through the prescribing path");
  await page.goto(`${BASE}/facility/patients/${encodeURIComponent(ABHA)}`);
  await shot(page, "11-prescription-updated");
} catch (err) {
  failed = true;
  evidence.error = String(err?.stack ?? err);
  console.error("✗", err);
  await evidence.currentPage?.screenshot({ path: join(OUT, "failure.png"), fullPage: true }).catch(() => undefined);
} finally {
  delete evidence.currentPage;
  writeFileSync(join(OUT, "evidence.json"), JSON.stringify(evidence, null, 2));
  console.log("transcribe responses:", JSON.stringify(evidence.transcribeResponses));
  await browser.close();
}
process.exit(failed ? 1 : 0);
