"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

interface Props {
  patientId: string;
  encounterId: string;
  facilityId: string;
}

/** Real create actions for the four internal workflows added under the
 * no-mock policy, scoped to this patient's most recent encounter. See
 * docs/REAL-INTEGRATION-AUDIT.md. */
export function PatientActionForms({ patientId, encounterId, facilityId }: Props) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <ReferralForm patientId={patientId} encounterId={encounterId} facilityId={facilityId} />
      <DiagnosticForm encounterId={encounterId} facilityId={facilityId} />
      <FollowUpForm patientId={patientId} encounterId={encounterId} facilityId={facilityId} />
      <TeleconsultForm patientId={patientId} encounterId={encounterId} facilityId={facilityId} />
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
      <div className="mt-2">{children}</div>
    </div>
  );
}

function useSubmitState() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [isError, setIsError] = useState(false);

  async function submit(endpoint: string, payload: Record<string, unknown>, successText: string) {
    setLoading(true);
    setMessage(null);
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setLoading(false);
    if (!res.ok) {
      setIsError(true);
      setMessage("Could not save. Please try again.");
      return false;
    }
    setIsError(false);
    setMessage(successText);
    router.refresh();
    return true;
  }

  return { loading, message, isError, submit };
}

function StatusLine({ message, isError }: { message: string | null; isError: boolean }) {
  if (!message) return null;
  return <p className={`mt-2 text-xs ${isError ? "text-severity-red" : "text-severity-green"}`}>{message}</p>;
}

function ReferralForm({ patientId, encounterId, facilityId }: Props) {
  const [toFacility, setToFacility] = useState("");
  const [reason, setReason] = useState("");
  const { loading, message, isError, submit } = useSubmitState();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const ok = await submit(
      "/api/referrals",
      {
        patient_id: patientId,
        encounter_id: encounterId,
        from_facility_id: facilityId,
        to_facility_id: toFacility,
        reason,
      },
      "Referral created.",
    );
    if (ok) {
      setToFacility("");
      setReason("");
    }
  }

  return (
    <Card title="Refer to another facility">
      <form onSubmit={onSubmit} className="space-y-2">
        <input
          required
          aria-label="Destination facility ID"
          placeholder="Destination facility ID"
          value={toFacility}
          onChange={(e) => setToFacility(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
        />
        <input
          required
          aria-label="Reason for referral"
          placeholder="Reason for referral"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
        />
        <button type="submit" disabled={loading} className="rounded-md bg-teal-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-50">
          {loading ? "Saving..." : "Create referral"}
        </button>
      </form>
      <StatusLine message={message} isError={isError} />
    </Card>
  );
}

function DiagnosticForm({ encounterId, facilityId }: { encounterId: string; facilityId: string }) {
  const [testName, setTestName] = useState("");
  const { loading, message, isError, submit } = useSubmitState();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const ok = await submit(
      "/api/diagnostics",
      { encounter_id: encounterId, facility_id: facilityId, test_name: testName },
      "Diagnostic test ordered.",
    );
    if (ok) setTestName("");
  }

  return (
    <Card title="Order a diagnostic test">
      <form onSubmit={onSubmit} className="space-y-2">
        <input
          required
          aria-label="Test name"
          placeholder="Test name (e.g. Malaria RDT)"
          value={testName}
          onChange={(e) => setTestName(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
        />
        <button type="submit" disabled={loading} className="rounded-md bg-teal-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-50">
          {loading ? "Saving..." : "Order test"}
        </button>
      </form>
      <StatusLine message={message} isError={isError} />
    </Card>
  );
}

function FollowUpForm({ patientId, encounterId, facilityId }: Props) {
  const [date, setDate] = useState("");
  const [reason, setReason] = useState("");
  const { loading, message, isError, submit } = useSubmitState();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const ok = await submit(
      "/api/follow-ups",
      { patient_id: patientId, encounter_id: encounterId, facility_id: facilityId, scheduled_date: date, reason },
      "Follow-up scheduled.",
    );
    if (ok) {
      setDate("");
      setReason("");
    }
  }

  return (
    <Card title="Schedule a follow-up">
      <form onSubmit={onSubmit} className="space-y-2">
        {/* A follow-up is by definition in the future; without min= the picker
            happily accepted 1900-01-01, which Core also stores (see the QA
            report -- whether the API should reject a past date is a product
            decision, so only the entry point is guarded here). */}
        <input
          required
          type="date"
          aria-label="Follow-up date"
          min={new Date().toISOString().slice(0, 10)}
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
        />
        <input
          required
          aria-label="Follow-up reason"
          placeholder="Reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
        />
        <button type="submit" disabled={loading} className="rounded-md bg-teal-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-50">
          {loading ? "Saving..." : "Schedule"}
        </button>
      </form>
      <StatusLine message={message} isError={isError} />
    </Card>
  );
}

function TeleconsultForm({ patientId, encounterId, facilityId }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [isError, setIsError] = useState(false);
  const router = useRouter();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setMessage(null);

    const createRes = await fetch("/api/teleconsults", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ encounter_id: encounterId, patient_id: patientId, facility_id: facilityId }),
    });
    if (!createRes.ok) {
      setLoading(false);
      setIsError(true);
      setMessage("Could not create teleconsult request.");
      return;
    }
    const teleconsult = await createRes.json();

    if (file) {
      const form = new FormData();
      form.append("file", file);
      const uploadRes = await fetch(`/api/teleconsults/${teleconsult.id}/media`, { method: "POST", body: form });
      if (!uploadRes.ok) {
        setLoading(false);
        setIsError(true);
        setMessage("Teleconsult created, but the recording upload failed.");
        return;
      }
    }

    setLoading(false);
    setIsError(false);
    setMessage("Teleconsult request saved.");
    setFile(null);
    router.refresh();
  }

  return (
    <Card title="Request a teleconsult">
      <form onSubmit={onSubmit} className="space-y-2">
        <input
          type="file"
          aria-label="Recording to attach (audio or video)"
          accept="audio/*,video/*"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="block w-full text-sm"
        />
        <button type="submit" disabled={loading} className="rounded-md bg-teal-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-50">
          {loading ? "Saving..." : "Send"}
        </button>
      </form>
      <StatusLine message={message} isError={isError} />
    </Card>
  );
}
