import { defineNitroPlugin } from "@agent-native/core/server";
import { wakeVigilensBackend } from "../utils/vigilens-startup-wake";

export default defineNitroPlugin(() => {
  // Do not await: frontend/sign-in must serve even while the backend wakes or
  // refuses. One attempt only; status never changes analysis or review gates.
  void wakeVigilensBackend().then((status) => {
    console.info(JSON.stringify({ event: "vigilens.backend_startup_wake", status }));
  });
});
