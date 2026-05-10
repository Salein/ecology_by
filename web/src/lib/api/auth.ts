import { apiUrl, cred } from "./client";

export async function authLogout(): Promise<void> {
  await fetch(apiUrl("/api/v1/auth/logout"), { ...cred, method: "POST" });
}
