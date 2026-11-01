import { defineEventHandler, readBody, createError } from "h3";
import { requireVigilensSession, requireSameOrigin } from "../../../utils/vigilens-proxy";
import { setVisitorKey, validateKeyShape, visitorKeyStatus, KeySetRateLimited, SessionCannotHoldKey } from "../../../utils/vigilens-keys";

export default defineEventHandler(async (event) => {
  const session = await requireVigilensSession(event);
  requireSameOrigin(event);
  const body = await readBody(event).catch(() => null);
  // Errors never echo the submitted value.
  if (!body || typeof body !== "object" || !validateKeyShape((body as Record<string, unknown>).key)) {
    throw createError({ statusCode: 400, statusMessage: "A valid API key value is required" });
  }
  try {
    setVisitorKey(session, (body as { key: string }).key);
  } catch (e) {
    if (e instanceof KeySetRateLimited) {
      throw createError({ statusCode: 429, statusMessage: "Too many key updates; try again later" });
    }
    if (e instanceof SessionCannotHoldKey) {
      throw createError({ statusCode: 503, statusMessage: "This session cannot hold a key; sign in again" });
    }
    throw e;
  }
  return visitorKeyStatus(session);
});
