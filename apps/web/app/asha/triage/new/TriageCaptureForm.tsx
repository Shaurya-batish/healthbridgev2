"use client";

import { useEffect, useState } from "react";
import { useOffline } from "@/lib/OfflineSyncProvider";
import { evaluateTriage, getRuleDescription } from "@/lib/rules-engine";
import { friendlyErrorMessage } from "@/lib/friendly-error";
import { useI18n } from "@/lib/i18n/LanguageProvider";
import { languageLabel, type CaptureLanguage } from "@/lib/i18n/languages";
import {
  applyMachineTranslation,
  buildCapturePayload,
  confirmedEnglish,
  createTypedDraft,
  createVoiceDraft,
  editEnglish,
  editOriginal,
  type CaptureDraft,
  type InputSource,
} from "@/lib/complaint-capture";
import {
  completeVoiceCapture,
  deleteVoiceCapture,
  enqueueVoiceCapture,
  getVoiceCapture,
  type QueuedVoiceCapture,
} from "@/lib/voice-queue";
import { transcribeAudio, transcriptionErrorKey } from "@/lib/voice-transcriber";
import { AshaButton } from "@/components/asha/AshaButton";
import { LanguageSelector } from "@/components/asha/LanguageSelector";
import { IconAlertTriangle, IconCheckCircle, IconArrowRight, IconInfoCircle } from "@/components/asha/icons";
import { VoiceRecorderPanel, type RecordedAudio } from "@/components/asha/triage/VoiceRecorderPanel";
import { ComplaintReview } from "@/components/asha/triage/ComplaintReview";
import { TriageResultCard } from "@/components/asha/triage/TriageResultCard";
import { ChecklistForm } from "@/components/asha/triage/ChecklistForm";
import type { ImnciFacts, TriageResult, TriageSource } from "@/lib/types";

type Stage = "capture" | "working" | "review" | "analyzing" | "checklist" | "result" | "submitting" | "done" | "error";

interface Notice {
  tone: "info" | "warn";
  text: string;
}

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

const nowIso = () => new Date().toISOString();

export function TriageCaptureForm({
  abhaNumber,
  facilityId,
  userId,
  resumeCaptureId,
}: {
  abhaNumber: string;
  facilityId: string;
  userId: string;
  resumeCaptureId?: string;
}) {
  const { submitEncounterAndTriage, isOnline } = useOffline();
  const { t, language: uiLanguage } = useI18n();

  const [abha, setAbha] = useState(abhaNumber);
  const [ageMonths, setAgeMonths] = useState<string>("");
  const [language, setLanguage] = useState<CaptureLanguage>("en");
  const [languageChosen, setLanguageChosen] = useState(false);
  const [mode, setMode] = useState<InputSource>("typed");
  const [typedText, setTypedText] = useState("");
  const [draft, setDraft] = useState<CaptureDraft | null>(null);
  const [capturePayload, setCapturePayload] = useState<Record<string, unknown> | null>(null);
  const [facts, setFacts] = useState<ImnciFacts>({});
  const [source, setSource] = useState<TriageSource>("llm");
  const [result, setResult] = useState<TriageResult | null>(null);
  const [stage, setStage] = useState<Stage>("capture");
  const [workingText, setWorkingText] = useState("");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [retranslating, setRetranslating] = useState(false);
  const [saveOutcome, setSaveOutcome] = useState<string | null>(null);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  // Becomes the encounter/triage Idempotency-Key: one visit, one encounter.
  const [visitId, setVisitId] = useState(newId);
  const [resumed, setResumed] = useState<QueuedVoiceCapture | null>(null);
  const [queuedCaptureId, setQueuedCaptureId] = useState<string | null>(null);
  // Whisper's own quality signals for the current voice capture.
  const [voiceWarnings, setVoiceWarnings] = useState<{ transcript: string[]; translation: string[] }>({ transcript: [], translation: [] });

  // Default the caregiver language to the app language until the ASHA picks one.
  useEffect(() => {
    if (!languageChosen && !resumed) setLanguage(uiLanguage);
  }, [uiLanguage, languageChosen, resumed]);

  // Re-open a delayed voice capture: bound to ITS patient, never the open one.
  useEffect(() => {
    if (!resumeCaptureId) return;
    let cancelled = false;
    (async () => {
      const capture = await getVoiceCapture(userId, resumeCaptureId);
      if (cancelled) return;
      if (!capture || capture.facilityId !== facilityId || capture.status !== "awaiting_confirmation" || !capture.transcript) {
        setNotice({ tone: "warn", text: t("pending.notFound") });
        return;
      }
      setResumed(capture);
      setVisitId(capture.visitId);
      setAbha(capture.abhaNumber);
      setAgeMonths(capture.ageMonths == null ? "" : String(capture.ageMonths));
      setLanguage(capture.language);
      setLanguageChosen(true);
      setMode("voice");
      setVoiceWarnings({ transcript: capture.transcript.transcript_warnings ?? [], translation: capture.transcript.translation_warnings ?? [] });
      setDraft(
        createVoiceDraft({
          id: capture.id,
          language: capture.language,
          transcript: capture.transcript.transcript,
          translationEn: capture.transcript.translation_en,
          engine: `${capture.transcript.engine} ${capture.transcript.model}`,
          audio: { sha256: capture.audioSha256, durationSeconds: capture.durationSeconds, mimeType: capture.mimeType },
          consentConfirmedAt: capture.consentConfirmedAt,
          capturedAt: capture.capturedAt,
        }),
      );
      setStage("review");
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resumeCaptureId, userId, facilityId]);

  function chooseLanguage(next: CaptureLanguage) {
    setLanguage(next);
    setLanguageChosen(true);
  }

  async function requestTranslation(current: CaptureDraft): Promise<CaptureDraft> {
    try {
      const res = await fetch("/api/triage/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: current.currentOriginal, source_language: current.language }),
      });
      const body = await res.json();
      if (res.ok && typeof body.translation_en === "string") {
        const engine = [body.engine, body.engine_version].filter(Boolean).join(" ");
        setNotice(null);
        return applyMachineTranslation(current, body.translation_en, engine);
      }
      const notInstalled = body?.reason === "language_not_installed" || body?.reason === "engine_not_installed";
      setNotice({
        tone: "warn",
        text: notInstalled ? t("capture.translationNotInstalled", { language: languageLabel(current.language) }) : t("capture.translationUnavailable"),
      });
    } catch {
      setNotice({ tone: "warn", text: t("capture.translationUnavailable") });
    }
    return current;
  }

  async function startTyped() {
    if (!typedText.trim()) return;
    const initial = createTypedDraft(newId(), language, typedText, nowIso());
    if (!isOnline) {
      setNotice({ tone: "warn", text: t("capture.offlineNotice") });
      setDraft(initial);
      setStage("checklist");
      return;
    }
    if (language === "en") {
      setDraft(initial);
      setStage("review");
      return;
    }
    setWorkingText(t("capture.translating"));
    setStage("working");
    setDraft(await requestTranslation(initial));
    setStage("review");
  }

  async function queueRecording(audio: RecordedAudio, messageKey: "voice.queuedOffline" | "voice.queuedUnavailable") {
    const id = newId();
    await enqueueVoiceCapture({
      id,
      visitId,
      userId,
      facilityId,
      abhaNumber: abha,
      ageMonths: ageMonths ? Number(ageMonths) : null,
      language,
      capturedAt: audio.capturedAt,
      consentConfirmedAt: audio.consentConfirmedAt,
      mimeType: audio.mimeType,
      durationSeconds: audio.durationSeconds,
      sizeBytes: audio.bytes.byteLength,
      audioSha256: audio.sha256,
      audioBytes: audio.bytes,
    });
    setQueuedCaptureId(id);
    setNotice({ tone: "warn", text: t(messageKey, { abha }) });
    setStage("capture");
  }

  async function submitRecording(audio: RecordedAudio) {
    if (!abha.trim()) return;
    if (!isOnline) return queueRecording(audio, "voice.queuedOffline");
    setWorkingText(t("voice.transcribing"));
    setStage("working");
    const out = await transcribeAudio(audio.bytes, audio.mimeType, language);
    if (out.ok) {
      setNotice(null);
      setVoiceWarnings({ transcript: out.transcript_warnings, translation: out.translation_warnings });
      setDraft(
        createVoiceDraft({
          id: newId(),
          language,
          transcript: out.transcript,
          translationEn: out.translation_en,
          engine: `${out.engine} ${out.model}`,
          audio: { sha256: audio.sha256, durationSeconds: out.duration_seconds ?? audio.durationSeconds, mimeType: audio.mimeType },
          consentConfirmedAt: audio.consentConfirmedAt,
          capturedAt: audio.capturedAt,
        }),
      );
      setStage("review");
      return;
    }
    if (out.retryable) return queueRecording(audio, "voice.queuedUnavailable");
    setNotice({ tone: "warn", text: t(transcriptionErrorKey(out.reason), { max: 120 }) });
    setStage("capture");
  }

  async function retranslate() {
    if (!draft) return;
    setRetranslating(true);
    setDraft(await requestTranslation(draft));
    setRetranslating(false);
  }

  async function confirmAndAnalyze() {
    if (!draft) return;
    let english: string;
    let payload: Record<string, unknown>;
    try {
      english = confirmedEnglish(draft);
      payload = buildCapturePayload(draft, nowIso());
    } catch {
      return; // the review step already shows why it can't be confirmed
    }
    setCapturePayload(payload);
    setStage("analyzing");
    try {
      const res = await fetch("/api/triage/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Only the ASHA-confirmed English and the age reach extraction.
        body: JSON.stringify({ complaint_text: english, age_months: ageMonths ? Number(ageMonths) : undefined }),
      });
      const body = await res.json();
      const valid = ["RED", "YELLOW", "GREEN"].includes(body.severity) && typeof body.rule_id === "string";
      if (body.ai_unavailable || !valid) throw new Error("ai_unavailable");
      setFacts(body.extracted_facts ?? {});
      setSource("llm");
      setResult({ severity: body.severity, rule_id: body.rule_id, rule_version: body.rule_version, matched_description: getRuleDescription(body.rule_id) });
      setStage("result");
    } catch {
      setNotice({ tone: "warn", text: t("analyze.unavailable") });
      setStage("checklist");
    }
  }

  function submitChecklist(collectedFacts: ImnciFacts) {
    const withAge: ImnciFacts = { ...collectedFacts, age_months: ageMonths ? Number(ageMonths) : null };
    setFacts(withAge);
    setSource("checklist");
    setResult(evaluateTriage(withAge));
    setStage("result");
  }

  async function confirmAndSave() {
    if (!result) return;
    setStage("submitting");
    setErrorDetail(null);

    // A confirmed capture is persisted whichever path decided severity: the
    // LLM path, or the checklist when extraction was unavailable afterwards.
    const confirmed = capturePayload !== null;
    const complaint = confirmed
      ? (capturePayload!.confirmed_text_en as string)
      : draft?.currentOriginal.trim() || typedText.trim() || null;

    const outcome = await submitEncounterAndTriage(
      "/api/encounters",
      { abha_number: abha, facility_id: facilityId, chief_complaint: complaint || "(structured checklist)" },
      "/api/triage",
      {
        complaint_text: complaint,
        source,
        extracted_facts: facts,
        severity: result.severity,
        rule_id: result.rule_id,
        rule_version: result.rule_version,
        ...(confirmed ? { complaint_capture: capturePayload } : {}),
      },
      visitId,
    );

    if (outcome.status === "rejected") {
      setErrorDetail(friendlyErrorMessage(outcome.detail));
      setStage("error");
      return;
    }

    // The visit is assessed: nothing from this visit should linger on the phone.
    if (resumed) await completeVoiceCapture(userId, resumed.id);
    if (queuedCaptureId) await deleteVoiceCapture(userId, queuedCaptureId);

    setSaveOutcome(outcome.status === "sent" ? t("save.sent") : t("save.queued"));
    setStage("done");
  }

  if (stage === "done") {
    return (
      <div className="space-y-4">
        <div className="flex items-start gap-3 rounded-2xl border border-severity-green bg-severity-green-bg p-5 text-severity-green">
          <IconCheckCircle className="mt-0.5 h-7 w-7 shrink-0" />
          <p className="text-lg font-semibold">{saveOutcome}</p>
        </div>
        <AshaButton href="/asha/queue" icon={<IconArrowRight />}>
          {t("save.viewQueue")}
        </AshaButton>
        <AshaButton href="/asha" variant="secondary">
          {t("save.home")}
        </AshaButton>
      </div>
    );
  }

  const showChecklistEscape = stage === "capture" || stage === "review" || stage === "working";

  return (
    <div className="space-y-4">
      {resumed && (
        <div className="flex items-start gap-3 rounded-2xl border-2 border-sky-400 bg-sky-50 p-4 text-sky-900" role="status">
          <IconInfoCircle className="mt-0.5 h-6 w-6 shrink-0" />
          <p className="text-base font-semibold">
            {t("pending.reviewingBanner", { abha: resumed.abhaNumber, time: new Date(resumed.capturedAt).toLocaleString() })}
          </p>
        </div>
      )}

      {notice && (
        <div
          className={`flex items-start gap-3 rounded-2xl border p-4 ${notice.tone === "warn" ? "border-amber-300 bg-amber-50 text-amber-900" : "border-slate-200 bg-white text-slate-700"}`}
          role="alert"
        >
          <IconAlertTriangle className="mt-0.5 h-6 w-6 shrink-0" />
          <p className="text-base">{notice.text}</p>
        </div>
      )}

      {(stage === "capture" || stage === "working") && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <h1 className="text-2xl font-bold text-slate-800">{t("visit.title")}</h1>

          <label className="mt-4 block">
            <span className="text-base font-semibold text-slate-700">{t("visit.abha")}</span>
            <input
              value={abha}
              disabled={!!resumed}
              onChange={(e) => setAbha(e.target.value)}
              className="mt-1.5 w-full rounded-xl border-2 border-slate-300 px-4 py-3 text-lg disabled:bg-slate-100"
            />
          </label>

          <label className="mt-4 block">
            <span className="text-base font-semibold text-slate-700">{t("visit.age")}</span>
            <input
              type="number"
              min={0}
              value={ageMonths}
              onChange={(e) => setAgeMonths(e.target.value)}
              className="mt-1.5 w-full rounded-xl border-2 border-slate-300 px-4 py-3 text-lg"
            />
          </label>

          <div className="mt-4">
            <LanguageSelector
              id="complaint-language"
              label={t("language.label")}
              help={t("language.help")}
              value={language}
              onChange={chooseLanguage}
              disabled={stage === "working"}
            />
          </div>

          <fieldset className="mt-4">
            <legend className="text-base font-semibold text-slate-700">{t("capture.howTitle")}</legend>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {(["typed", "voice"] as const).map((m) => (
                <label
                  key={m}
                  className={`flex min-h-[52px] cursor-pointer items-center justify-center rounded-xl border-2 text-lg font-semibold ${
                    mode === m ? "border-teal-700 bg-teal-50 text-teal-800" : "border-slate-300 bg-white text-slate-700"
                  }`}
                >
                  <input type="radio" name="capture-mode" value={m} checked={mode === m} onChange={() => setMode(m)} className="sr-only" />
                  {m === "typed" ? t("capture.modeTyped") : t("capture.modeVoice")}
                </label>
              ))}
            </div>
          </fieldset>

          {stage === "working" ? (
            <div className="mt-5 flex items-center gap-3 rounded-xl bg-slate-50 p-4 text-slate-600" role="status" aria-live="polite">
              <Spinner />
              <p className="text-lg font-medium">{workingText}</p>
            </div>
          ) : mode === "typed" ? (
            <>
              <label className="mt-4 block">
                <span className="text-base font-semibold text-slate-700">{t("capture.mainProblem", { language: languageLabel(language) })}</span>
                <textarea
                  lang={language}
                  value={typedText}
                  onChange={(e) => setTypedText(e.target.value)}
                  rows={4}
                  className="mt-1.5 w-full rounded-xl border-2 border-slate-300 px-4 py-3 text-lg"
                  placeholder={t("capture.placeholder")}
                />
              </label>
              <div className="mt-4">
                <AshaButton onClick={startTyped} disabled={!typedText.trim()}>
                  {language === "en" ? t("capture.continue") : t("capture.translate")}
                </AshaButton>
              </div>
            </>
          ) : (
            <VoiceRecorderPanel busy={!abha.trim()} onSubmit={submitRecording} />
          )}
        </div>
      )}

      {stage === "review" && draft && (
        <ComplaintReview
          draft={draft}
          onOriginalChange={(text) => setDraft((d) => (d ? editOriginal(d, text) : d))}
          onEnglishChange={(text) => setDraft((d) => (d ? editEnglish(d, text) : d))}
          onRetranslate={draft.language !== "en" && isOnline ? retranslate : null}
          retranslating={retranslating}
          onConfirm={confirmAndAnalyze}
          canAnalyze={isOnline}
          transcriptWarnings={draft.inputSource === "voice" && draft.currentOriginal === draft.originalText ? voiceWarnings.transcript : []}
          translationWarnings={draft.inputSource === "voice" ? voiceWarnings.translation : []}
        />
      )}

      {showChecklistEscape && (
        <AshaButton onClick={() => setStage("checklist")} variant="secondary">
          {t("capture.useChecklist")}
        </AshaButton>
      )}

      {stage === "analyzing" && (
        <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-5 text-slate-600" role="status" aria-live="polite">
          <Spinner />
          <p className="text-lg font-medium">{t("analyze.checking")}</p>
        </div>
      )}

      {stage === "checklist" && <ChecklistForm onSubmit={submitChecklist} />}

      {stage === "result" && result && <TriageResultCard result={result} source={source} onConfirm={confirmAndSave} />}

      {stage === "submitting" && (
        <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-5 text-slate-600" role="status">
          <Spinner />
          <p className="text-lg font-medium">{t("save.saving")}</p>
        </div>
      )}

      {stage === "error" && (
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-2xl border border-amber-300 bg-amber-50 p-4 text-amber-900">
            <IconAlertTriangle className="mt-0.5 h-6 w-6 shrink-0" />
            <p className="text-lg">{errorDetail}</p>
          </div>
          <AshaButton onClick={() => setStage("result")} variant="secondary">
            {t("save.tryAgain")}
          </AshaButton>
        </div>
      )}
    </div>
  );
}

function Spinner() {
  return <span className="h-6 w-6 shrink-0 animate-spin rounded-full border-4 border-slate-300 border-t-teal-700" aria-hidden="true" />;
}
