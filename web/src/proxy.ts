import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/** Должно совпадать с `SESSION_GATE_COOKIE` в `lib/sessionGate.ts` */
const SESSION_GATE = "ecology_has_session";

export function proxy(request: NextRequest) {
  const hasGate = request.cookies.get(SESSION_GATE)?.value === "1";
  if (!hasGate) {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/app", "/app/:path*", "/admin", "/admin/:path*"],
};
