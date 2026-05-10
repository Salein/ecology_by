"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { LeafCornerAccent } from "@/components/ecology/LeafCornerAccent";
import { ObjectsExplorer } from "@/components/ecology/ObjectsExplorer";
import { useAuth } from "@/context/AuthContext";

export default function ApplicationPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="flex min-h-[50vh] flex-1 flex-col items-center justify-center gap-3 text-emerald-900/70">
        <span
          className="h-9 w-9 animate-spin rounded-full border-2 border-emerald-200 border-t-emerald-600"
          aria-hidden
        />
        <p className="text-sm font-medium text-emerald-900/75">Загрузка…</p>
      </div>
    );
  }
  if (!user) return null;

  return (
    <div className="relative min-h-full flex-1 text-[15px] leading-relaxed md:text-base">
      <LeafCornerAccent />
      <ObjectsExplorer canImportRegistry={user.role === "admin"} />
    </div>
  );
}
