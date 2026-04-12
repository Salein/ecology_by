"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";

export function WelcomePage() {
  const { user, loading, login, register } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace("/app");
  }, [loading, user, router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, name);
      }
      router.replace("/app");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-emerald-900/70">
        Загрузка…
      </div>
    );
  }
  if (user) return null;

  return (
    <div className="mx-auto flex w-full max-w-lg flex-col gap-8 px-4 py-16 sm:px-6">
      <div className="text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-emerald-950">Экология</h1>
        <p className="mt-2 text-sm text-emerald-900/60">
          Поиск объектов обращения с отходами. Войдите или зарегистрируйтесь для доступа к приложению.
        </p>
      </div>

      <div className="flex rounded-2xl border border-emerald-100/90 bg-emerald-50/40 p-1 shadow-sm">
        <button
          type="button"
          onClick={() => {
            setMode("login");
            setError(null);
          }}
          className={`flex-1 rounded-xl py-2.5 text-sm font-medium transition ${
            mode === "login"
              ? "bg-white text-emerald-950 shadow-sm"
              : "text-emerald-800/60 hover:text-emerald-900"
          }`}
        >
          Вход
        </button>
        <button
          type="button"
          onClick={() => {
            setMode("register");
            setError(null);
          }}
          className={`flex-1 rounded-xl py-2.5 text-sm font-medium transition ${
            mode === "register"
              ? "bg-white text-emerald-950 shadow-sm"
              : "text-emerald-800/60 hover:text-emerald-900"
          }`}
        >
          Регистрация
        </button>
      </div>

      <form
        onSubmit={(e) => void onSubmit(e)}
        className="flex flex-col gap-4 rounded-2xl border border-emerald-100/90 bg-white/95 p-6 shadow-sm shadow-emerald-900/5"
      >
        {mode === "register" ? (
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-emerald-950">Имя</span>
            <input
              type="text"
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="rounded-xl border border-emerald-100 bg-white px-4 py-3 text-stone-800 outline-none ring-emerald-200/50 focus:border-emerald-300 focus:ring-2"
              placeholder="Как к вам обращаться"
            />
          </label>
        ) : null}
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-emerald-950">Электронная почта</span>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded-xl border border-emerald-100 bg-white px-4 py-3 text-stone-800 outline-none ring-emerald-200/50 focus:border-emerald-300 focus:ring-2"
            placeholder="you@example.com"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-emerald-950">Пароль</span>
          <input
            type="password"
            required
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded-xl border border-emerald-100 bg-white px-4 py-3 text-stone-800 outline-none ring-emerald-200/50 focus:border-emerald-300 focus:ring-2"
            placeholder={mode === "register" ? "Не менее 8 символов" : "••••••••"}
            minLength={mode === "register" ? 8 : undefined}
          />
        </label>
        {error ? <p className="text-sm text-red-700">{error}</p> : null}
        <button
          type="submit"
          disabled={busy}
          className="mt-2 rounded-2xl bg-emerald-700 py-3.5 text-sm font-medium text-white shadow-sm transition hover:bg-emerald-800 disabled:opacity-60"
        >
          {busy ? "Подождите…" : mode === "login" ? "Войти" : "Зарегистрироваться"}
        </button>
      </form>

      <p className="text-center text-xs text-emerald-800/50">
        Первый зарегистрированный пользователь получает роль администратора и может загружать реестры.
      </p>
    </div>
  );
}
