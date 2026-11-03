import path from "node:path";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./app"),
      "@shared": path.resolve(__dirname, "./shared"),
    },
  },
  test: {
    server: {
      deps: {
        // The provider-schema conformance loader does a native dynamic import()
        // of the generated actions registry, whose imports are extensionless
        // (the pinned generator emits them that way). Externalized, that import
        // bypasses Vite resolution and fails; inline just this module so the
        // registry loads through the Vite pipeline. No dependency changes.
        // (whole package: the testing.js entry re-exports the conformance
        // module, so inlining only the leaf never reaches it through Vite)
        inline: [/@agent-native\/core/],
      },
    },
    exclude: [
      "**/node_modules/**",
      "**/.git/**",
      "**/dist/**",
      "**/.react-router/**",
    ],
  },
});
