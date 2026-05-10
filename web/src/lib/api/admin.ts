import { apiUrl, cred } from "./client";

export type AdminUserRow = {
  id: number;
  email: string;
  name: string;
  role: "user" | "admin";
  created_at: string;
  /** ISO UTC, обновляется при входе и при активности в приложении (не чаще ~5 мин) */
  last_seen_at: string | null;
  blocked: boolean;
  /** Подписка активна (в т.ч. включена администратором) */
  subscription_active: boolean;
  /** Учётная запись владельца (BOOTSTRAP_OWNER_EMAIL) — удалять нельзя */
  protected_account: boolean;
};

export async function fetchAdminUsers(): Promise<AdminUserRow[]> {
  const r = await fetch(apiUrl("/api/v1/admin/users"), { ...cred });
  if (!r.ok) throw new Error(`admin users: ${r.status}`);
  return (await r.json()) as AdminUserRow[];
}

export type AdminUserPatch = {
  role?: "user" | "admin";
  blocked?: boolean;
  subscription_active?: boolean;
};

export async function patchAdminUser(userId: number, patch: AdminUserPatch): Promise<AdminUserRow> {
  const r = await fetch(apiUrl(`/api/v1/admin/users/${userId}`), {
    ...cred,
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!r.ok) {
    let msg = `patch user: ${r.status}`;
    try {
      const j = (await r.json()) as { detail?: string };
      if (typeof j.detail === "string") msg = j.detail;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return (await r.json()) as AdminUserRow;
}

export async function deleteAdminUser(userId: number): Promise<void> {
  const r = await fetch(apiUrl(`/api/v1/admin/users/${userId}`), {
    ...cred,
    method: "DELETE",
  });
  if (!r.ok) {
    let msg = `delete user: ${r.status}`;
    try {
      const j = (await r.json()) as { detail?: string };
      if (typeof j.detail === "string") msg = j.detail;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
}
