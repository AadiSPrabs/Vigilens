import { defineEventHandler } from "h3";
import { requireVigilensSession, requireSameOrigin } from "../../../utils/vigilens-proxy";
import { forgetVisitorKey } from "../../../utils/vigilens-keys";

export default defineEventHandler(async (event) => {
  const session = await requireVigilensSession(event);
  requireSameOrigin(event);
  const removed = forgetVisitorKey(session);
  return { present: false as const, removed };
});
