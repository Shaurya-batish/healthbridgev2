"use client";

import { useState } from "react";
import { AshaButton } from "@/components/asha/AshaButton";
import { IconArrowRight } from "@/components/asha/icons";
import { useI18n } from "@/lib/i18n/LanguageProvider";
import { languageLabel } from "@/lib/i18n/languages";
import type { ImnciFacts } from "@/lib/types";

/** Structured danger-sign checklist -- the offline/degraded path that runs the
 * same on-device rule table. Labels are clinical text and stay in canonical
 * English until a reviewed translation exists (lib/i18n/clinical). */
export function ChecklistForm({ onSubmit }: { onSubmit: (facts: ImnciFacts) => void }) {
  const { t, language } = useI18n();
  const [facts, setFacts] = useState<ImnciFacts>({});

  function toggle(field: keyof ImnciFacts) {
    setFacts((f) => ({ ...f, [field]: !f[field] }));
  }

  function setNumber(field: keyof ImnciFacts, value: string) {
    setFacts((f) => ({ ...f, [field]: value ? Number(value) : null }));
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5" lang="en">
      <h2 className="text-xl font-bold text-slate-800">Check Danger Signs</h2>
      {language !== "en" && (
        <p className="mt-2 rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700" lang={language}>
          {t("result.clinicalFallback", { language: languageLabel(language) })}
        </p>
      )}
      <p className="mt-1 text-slate-500">
        Tick anything that is true for this patient. Same rules as the automatic check — works without internet.
        6 short sections below, then the result.
      </p>

      <ChecklistSection index={1} total={6} title="General danger signs">
        <Check label="Unable to drink or breastfeed" checked={!!facts.unable_to_drink_or_feed} onChange={() => toggle("unable_to_drink_or_feed")} />
        <Check label="Vomits everything" checked={!!facts.vomits_everything} onChange={() => toggle("vomits_everything")} />
        <Check label="Convulsions (fits)" checked={!!facts.convulsions} onChange={() => toggle("convulsions")} />
        <Check label="Very sleepy or unconscious" checked={!!facts.lethargic_or_unconscious} onChange={() => toggle("lethargic_or_unconscious")} />
      </ChecklistSection>

      <ChecklistSection index={2} total={6} title="Breathing Problem">
        <Check label="Chest pulls in when breathing" checked={!!facts.chest_indrawing} onChange={() => toggle("chest_indrawing")} />
        <Check label="Noisy breathing (stridor) even when calm" checked={!!facts.stridor_when_calm} onChange={() => toggle("stridor_when_calm")} />
        <Check label="Cough present" checked={!!facts.cough_present} onChange={() => toggle("cough_present")} />
        <NumberField label="Breaths per minute" value={facts.respiratory_rate_per_min ?? ""} onChange={(v) => setNumber("respiratory_rate_per_min", v)} />
      </ChecklistSection>

      <ChecklistSection index={3} total={6} title="Loose Motions (Diarrhea)">
        <Check label="Loose motions present" checked={!!facts.diarrhea_present} onChange={() => toggle("diarrhea_present")} />
        <NumberField label="How many days" value={facts.diarrhea_duration_days ?? ""} onChange={(v) => setNumber("diarrhea_duration_days", v)} />
        <Check label="Blood in stool" checked={!!facts.blood_in_stool} onChange={() => toggle("blood_in_stool")} />
        <Check label="Restless or irritable" checked={!!facts.restless_or_irritable} onChange={() => toggle("restless_or_irritable")} />
        <Check label="Sunken eyes" checked={!!facts.sunken_eyes} onChange={() => toggle("sunken_eyes")} />
        <Check label="Drinks water eagerly, very thirsty" checked={!!facts.drinks_eagerly_thirsty} onChange={() => toggle("drinks_eagerly_thirsty")} />
        <Check label="Skin pinch: goes back slowly" checked={!!facts.skin_pinch_slow} onChange={() => toggle("skin_pinch_slow")} />
        <Check label="Skin pinch: goes back very slowly" checked={!!facts.skin_pinch_very_slow} onChange={() => toggle("skin_pinch_very_slow")} />
      </ChecklistSection>

      <ChecklistSection index={4} total={6} title="Temperature">
        <Check label="Fever present" checked={!!facts.fever_present} onChange={() => toggle("fever_present")} />
        <NumberField label="How many days" value={facts.fever_duration_days ?? ""} onChange={(v) => setNumber("fever_duration_days", v)} />
        <Check label="Stiff neck" checked={!!facts.stiff_neck} onChange={() => toggle("stiff_neck")} />
      </ChecklistSection>

      <ChecklistSection index={5} total={6} title="Ear">
        <Check label="Ear pain" checked={!!facts.ear_pain} onChange={() => toggle("ear_pain")} />
        <Check label="Ear discharge (pus/fluid)" checked={!!facts.ear_discharge} onChange={() => toggle("ear_discharge")} />
        <Check label="Painful swelling behind the ear" checked={!!facts.tender_swelling_behind_ear} onChange={() => toggle("tender_swelling_behind_ear")} />
      </ChecklistSection>

      <ChecklistSection index={6} total={6} title="Nutrition">
        <Check label="Visible severe thinness" checked={!!facts.visible_severe_wasting} onChange={() => toggle("visible_severe_wasting")} />
        <Check label="Swelling in both feet" checked={!!facts.edema_both_feet} onChange={() => toggle("edema_both_feet")} />
        <label className="flex items-center justify-between gap-3 py-2 text-lg text-slate-700">
          Paleness of palms
          <select
            value={facts.palmar_pallor ?? "none"}
            onChange={(e) => setFacts((f) => ({ ...f, palmar_pallor: e.target.value as ImnciFacts["palmar_pallor"] }))}
            className="rounded-lg border-2 border-slate-300 px-3 py-2 text-base"
          >
            <option value="none">None</option>
            <option value="some">Some</option>
            <option value="severe">Severe</option>
          </select>
        </label>
      </ChecklistSection>

      <div className="mt-5">
        <AshaButton onClick={() => onSubmit(facts)} icon={<IconArrowRight />}>
          See Result
        </AshaButton>
      </div>
    </div>
  );
}

function ChecklistSection({ title, index, total, children }: { title: string; index: number; total: number; children: React.ReactNode }) {
  return (
    <div className="mt-5 border-t border-slate-100 pt-4">
      <h3 className="text-sm font-bold uppercase tracking-wide text-slate-500">
        Section {index} of {total} · {title}
      </h3>
      <div className="mt-1 divide-y divide-slate-50">{children}</div>
    </div>
  );
}

function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: () => void }) {
  return (
    <label className="flex items-center justify-between gap-3 py-3 text-lg text-slate-700">
      <span>{label}</span>
      <input type="checkbox" checked={checked} onChange={onChange} className="h-7 w-7 shrink-0 accent-teal-700" />
    </label>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number | string; onChange: (v: string) => void }) {
  return (
    <label className="flex items-center justify-between gap-3 py-3 text-lg text-slate-700">
      <span>{label}</span>
      <input type="number" min={0} value={value} onChange={(e) => onChange(e.target.value)} className="w-24 rounded-lg border-2 border-slate-300 px-2 py-2 text-lg" />
    </label>
  );
}
