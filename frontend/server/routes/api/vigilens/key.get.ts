import { defineEventHandler } from "h3";
import { requireVigilensSession, requireSameOrigin } from "../../../utils/vigilens-proxy";
import { visitorKeyStatus } from "../../../utils/vigilens-keys";

export default defineEventHandler(async (event) => {
  const session = await requireVigilensSession(event);
  requireSameOrigin(event);
  return visitorKeyStatus(session);
});
