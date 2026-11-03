import {
  appBasePath,
  appPathFromLocalRoute,
} from "@agent-native/core/client/api-path";
import { useAgentRouteState } from "@agent-native/core/client/navigation";

import { TAB_ID } from "@/lib/tab-id";

export interface NavigationState {
  view?: string;
  path?: string;
  publicPath?: string;
  threadId?: string;
}

export function useNavigationState() {
  useAgentRouteState<NavigationState>({
    browserTabId: TAB_ID,
    requestSource: TAB_ID,
    getNavigationState: ({ pathname }) => ({
      view: viewForPath(pathname),
      path: pathname,
      publicPath: appPathFromLocalRoute(pathname),
    }),
    getCommandPath: commandPathForNavigation,
  });
}

// Router-local path for a navigation command. A thread id is only meaningful
// for chat views (chat and ask share the chat thread route); explicit home
// navigation stays at /home even when a stale thread id rides along.
export function pathForCommand(command: NavigationState): string {
  const base = pathForView(command?.view);
  const threadId = typeof command?.threadId === "string" ? command.threadId : "";
  if ((command?.view === "chat" || command?.view === "ask") && threadId) {
    return `${base}/${threadId}`;
  }
  return base;
}

// Navigation state for a router-local path: the view, the path itself, the
// mounted public path, and the thread id when the path names a chat thread.
export function navigationStateForPath(path: string): NavigationState {
  const suffixIndex = path.search(/[?#]/);
  const pathname = suffixIndex === -1 ? path : path.slice(0, suffixIndex);
  const view = viewForPath(pathname);
  const state: NavigationState = {
    view,
    path,
    publicPath: appPathFromLocalRoute(path),
  };
  if ((view === "chat" || view === "ask") && pathname.startsWith("/chat/")) {
    const id = pathname.slice("/chat/".length);
    if (id && !id.includes("/")) state.threadId = id;
  }
  return state;
}

export function commandPathForNavigation(command: NavigationState): string {
  const fallbackPath = pathForCommand(command);
  const path = typeof command?.path === "string" ? command.path : "";
  if (!path) return fallbackPath;

  const basePath = appBasePath();
  if (!basePath) return path;

  const suffixIndex = path.search(/[?#]/);
  const pathname = suffixIndex === -1 ? path : path.slice(0, suffixIndex);
  const suffix = suffixIndex === -1 ? "" : path.slice(suffixIndex);
  const publicPath =
    typeof command?.publicPath === "string" ? command.publicPath : "";
  const publicPathSuffixIndex = publicPath.search(/[?#]/);
  const declaredPublicPath =
    publicPathSuffixIndex === -1
      ? publicPath
      : publicPath.slice(0, publicPathSuffixIndex);
  const publicViewPath = appPathFromLocalRoute(pathForView(command?.view));
  if (
    matchesPathPrefix(pathname, basePath) &&
    (matchesPathPrefix(pathname, publicViewPath) ||
      (declaredPublicPath && declaredPublicPath === pathname))
  ) {
    return `${pathname.slice(basePath.length) || "/"}${suffix}`;
  }
  return path;
}

function matchesPathPrefix(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

function viewForPath(pathname: string): string {
  if (pathname === "/chat" || pathname.startsWith("/chat/")) return "chat";
  if (pathname === "/ask" || pathname.startsWith("/ask/")) return "ask";
  if (pathname === "/settings" || pathname.startsWith("/settings/")) return "settings";
  return "home";
}

function pathForView(view?: string): string {
  switch (view) {
    case "chat":
    case "ask":
      return "/chat";
    case "settings":
      return "/settings";
    case "home":
      return "/home";
    default:
      return "/";
  }
}
