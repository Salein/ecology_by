"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { deleteAdminUser, fetchAdminUsers, patchAdminUser, type AdminUserRow } from "@/lib/api";

function cloneUserRows(list: AdminUserRow[]): AdminUserRow[] {
  return list.map((r) => ({ ...r }));
}

export default function AdminPage() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  /** Черновик в таблице */
  const [rows, setRows] = useState<AdminUserRow[]>([]);
  /** Последнее сохранённое на сервере состояние (роль / доступ) */
  const [savedRows, setSavedRows] = useState<AdminUserRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    setLoadingList(true);
    try {
      const list = await fetchAdminUsers();
      const copy = cloneUserRows(list);
      setRows(copy);
      setSavedRows(cloneUserRows(list));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Не удалось загрузить список");
      setRows([]);
      setSavedRows([]);
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [loading, user, router]);

  useEffect(() => {
    if (!loading && user && user.role !== "admin") router.replace("/app");
  }, [loading, user, router]);

  useEffect(() => {
    if (user?.role === "admin") void load();
  }, [user?.role, load]);

  const dirty = useMemo(() => {
    if (!user) return false;
    if (rows.length !== savedRows.length) return rows.length > 0 || savedRows.length > 0;
    const byId = new Map(savedRows.map((r) => [r.id, r]));
    return rows.some((r) => {
      const s = byId.get(r.id);
      if (!s) return true;
      if (r.role !== s.role) return true;
      /* у своей строки и у владельца (bootstrap) доступ не редактируется — только роль */
      if (r.id === user.id) return false;
      if (r.protected_account) return false;
      return r.blocked !== s.blocked;
    });
  }, [rows, savedRows, user]);

  function setDraftRole(uid: number, role: "user" | "admin") {
    setErr(null);
    setRows((prev) => prev.map((r) => (r.id === uid ? { ...r, role } : r)));
  }

  function setDraftBlocked(uid: number, blocked: boolean) {
    setErr(null);
    setRows((prev) => prev.map((r) => (r.id === uid ? { ...r, blocked } : r)));
  }

  async function saveChanges() {
    if (!dirty || saving) return;
    setErr(null);
    setSaving(true);
    const byId = new Map(savedRows.map((r) => [r.id, r]));
    try {
      for (const r of rows) {
        const prev = byId.get(r.id);
        if (!prev) continue;
        const isSelf = user != null && r.id === user.id;
        if (isSelf) {
          if (prev.role === r.role) continue;
          await patchAdminUser(r.id, { role: r.role });
          continue;
        }
        if (r.protected_account) {
          if (prev.role === r.role) continue;
          await patchAdminUser(r.id, { role: r.role });
          continue;
        }
        if (prev.role === r.role && prev.blocked === r.blocked) continue;
        const patch: { role?: "user" | "admin"; blocked?: boolean } = {};
        if (prev.role !== r.role) patch.role = r.role;
        if (prev.blocked !== r.blocked) patch.blocked = r.blocked;
        await patchAdminUser(r.id, patch);
      }
      setSavedRows(cloneUserRows(rows));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Ошибка сохранения");
      try {
        const list = await fetchAdminUsers();
        setRows(cloneUserRows(list));
        setSavedRows(cloneUserRows(list));
      } catch {
        /* список не подтянулся — остаётся черновик */
      }
    } finally {
      setSaving(false);
    }
  }

  async function removeUser(uid: number, email: string) {
    if (!window.confirm(`Удалить пользователя ${email} из системы? Это действие необратимо.`)) return;
    setErr(null);
    setDeletingId(uid);
    try {
      await deleteAdminUser(uid);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Не удалось удалить пользователя");
    } finally {
      setDeletingId(null);
    }
  }

  if (loading || !user || user.role !== "admin") {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-emerald-900/70">
        {loading ? "Загрузка…" : "Нет доступа"}
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-10 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-emerald-950">Админ-панель</h1>
          <p className="mt-1 text-sm text-emerald-900/55">Пользователи, роли и доступ</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href="/app"
            className="rounded-xl border border-emerald-200/90 bg-white px-4 py-2 text-sm font-medium text-emerald-900 shadow-sm transition hover:bg-emerald-50/90"
          >
            К приложению
          </Link>
          <button
            type="button"
            onClick={() => {
              void (async () => {
                await logout();
                window.location.href = "/";
              })();
            }}
            className="rounded-xl border border-stone-200 bg-white px-4 py-2 text-sm font-medium text-stone-700 transition hover:bg-stone-50"
          >
            Выйти
          </button>
        </div>
      </div>

      {err ? <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{err}</p> : null}

      <div className="overflow-x-auto rounded-2xl border border-emerald-100/90 bg-white/95 shadow-sm">
        <table className="w-full min-w-[36rem] text-left text-sm">
          <thead className="border-b border-emerald-100 bg-emerald-50/80 text-xs font-semibold uppercase tracking-wide text-emerald-800/60">
            <tr>
              <th className="px-4 py-3">Имя</th>
              <th className="px-4 py-3">Почта</th>
              <th className="px-4 py-3">Роль</th>
              <th className="px-4 py-3">Доступ</th>
              <th className="w-28 px-4 py-3">Действия</th>
            </tr>
          </thead>
          <tbody>
            {loadingList ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-emerald-800/50">
                  Загрузка…
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-emerald-800/50">
                  Нет пользователей
                </td>
              </tr>
            ) : (
              rows.map((r) => {
                const isSelf = user.id === r.id;
                return (
                  <tr key={r.id} className="border-b border-emerald-50/90 last:border-0">
                    <td className="px-4 py-3 font-medium text-stone-800">{r.name || "—"}</td>
                    <td className="px-4 py-3 text-stone-700">{r.email}</td>
                    <td className="px-4 py-3">
                      <select
                        value={r.role}
                        disabled={saving || deletingId != null}
                        onChange={(e) => setDraftRole(r.id, e.target.value as "user" | "admin")}
                        className="rounded-lg border border-emerald-200/80 bg-white px-2 py-1.5 text-stone-800 outline-none focus:border-emerald-400 focus:ring-1 focus:ring-emerald-300 disabled:opacity-60"
                      >
                        <option value="user">Пользователь</option>
                        <option value="admin">Администратор</option>
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      {isSelf || r.protected_account ? (
                        <span
                          className="text-sm text-emerald-800/70"
                          title={
                            r.protected_account && !isSelf
                              ? "Доступ владельца системы нельзя закрыть"
                              : undefined
                          }
                        >
                          Всегда открыт
                        </span>
                      ) : (
                        <div className="inline-flex rounded-lg border border-emerald-200/90 bg-emerald-50/60 p-0.5 shadow-inner">
                          <button
                            type="button"
                            disabled={saving || deletingId != null}
                            onClick={() => setDraftBlocked(r.id, false)}
                            className={
                              !r.blocked
                                ? "rounded-md bg-white px-3 py-1.5 text-xs font-semibold text-emerald-900 shadow-sm ring-1 ring-emerald-200/80 sm:text-sm"
                                : "rounded-md px-3 py-1.5 text-xs font-medium text-emerald-800/55 transition hover:text-emerald-900 sm:text-sm"
                            }
                          >
                            Открыт
                          </button>
                          <button
                            type="button"
                            disabled={saving || deletingId != null}
                            onClick={() => setDraftBlocked(r.id, true)}
                            className={
                              r.blocked
                                ? "rounded-md bg-white px-3 py-1.5 text-xs font-semibold text-red-900 shadow-sm ring-1 ring-red-200/80 sm:text-sm"
                                : "rounded-md px-3 py-1.5 text-xs font-medium text-emerald-800/55 transition hover:text-emerald-900 sm:text-sm"
                            }
                          >
                            Закрыт
                          </button>
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {isSelf || r.protected_account ? (
                        <span
                          className="text-xs text-stone-400"
                          title={
                            r.protected_account && !isSelf
                              ? "Учётная запись владельца системы, удаление недоступно"
                              : undefined
                          }
                        >
                          —
                        </span>
                      ) : (
                        <button
                          type="button"
                          disabled={saving || deletingId != null}
                          onClick={() => void removeUser(r.id, r.email)}
                          className="rounded-lg border border-red-200/90 bg-white px-2.5 py-1.5 text-xs font-medium text-red-800 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {deletingId === r.id ? "Удаление…" : "Удалить"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-emerald-900/55">
          {dirty ? "Есть несохранённые изменения — нажмите «Сохранить», чтобы применить их на сервере." : "Изменения совпадают с сохранёнными."}
        </p>
        <button
          type="button"
          disabled={!dirty || loadingList || saving}
          onClick={() => void saveChanges()}
          className="shrink-0 rounded-xl bg-emerald-700 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-800 disabled:cursor-not-allowed disabled:bg-emerald-300 disabled:text-emerald-100"
        >
          {saving ? "Сохранение…" : "Сохранить изменения"}
        </button>
      </div>
    </div>
  );
}
