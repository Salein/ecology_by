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
      <div className="flex min-h-[50vh] flex-1 items-center justify-center text-emerald-900/70">
        Загрузка…
      </div>
    );
  }
  if (!user) return null;

  return (
    <div className="relative min-h-full flex-1 overflow-x-hidden">
      <LeafCornerAccent />
      <ObjectsExplorer canImportRegistry={user.role === "admin"} />
    </div>
  );
}
