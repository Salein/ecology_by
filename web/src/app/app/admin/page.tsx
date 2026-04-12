import { redirect } from "next/navigation";

/** Удобный URL: /app/admin → основная админка на /admin */
export default function AdminAliasPage() {
  redirect("/admin");
}
