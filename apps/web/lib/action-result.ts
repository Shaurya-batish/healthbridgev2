/** Shared helper for the facility surface's small action controls.
 *
 * Several of them (Acknowledge, follow-up status, referral status, record
 * result, teleconsult response) fired a POST and called router.refresh()
 * without ever looking at the response. A failing request therefore produced
 * no message at all: the row stayed unchanged and -- where `loading` was
 * never reset -- the button was left permanently disabled. For a RED-case
 * acknowledgement that is a clinical-safety problem, so every control now
 * reports a failure in place.
 *
 * Kept deliberately plain: it mirrors what VerifySchemeButton already did by
 * hand, rather than introducing a new data-fetching abstraction.
 */
export async function postAction(url: string, body?: unknown): Promise<string | null> {
  try {
    const res = await fetch(url, {
      method: "POST",
      ...(body === undefined
        ? {}
        : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
    });
    if (res.ok) return null;
    if (res.status === 502 || res.status === 503) return "Couldn't reach the server — nothing was saved. Try again.";
    if (res.status === 403) return "You don't have access to this record.";
    if (res.status === 404) return "This record no longer exists. Refresh the page.";
    return "That didn't save. Nothing was changed — please try again.";
  } catch {
    return "Couldn't reach the server — nothing was saved. Try again.";
  }
}
