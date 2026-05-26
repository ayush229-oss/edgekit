export const dynamic = "force-dynamic";

import { redirect } from "next/navigation";
import { isAdmin } from "@/lib/profile-sync";
import { supabaseAdmin } from "@/lib/supabase-server";
import { AdminTestimonials } from "./AdminTestimonials";

export default async function AdminPage() {
  const admin = await isAdmin();
  if (!admin) redirect("/home");

  const { data } = await supabaseAdmin
    .from("testimonials")
    .select("*")
    .order("created_at", { ascending: false });

  const testimonials = data ?? [];
  const pendingCount = testimonials.filter((t: any) => t.status === "pending").length;

  return (
    <div className="space-y-8 max-w-4xl">
      <div>
        <p className="text-[11px] uppercase tracking-[0.25em] text-money font-semibold mb-2">Admin</p>
        <h1 className="text-[32px] font-bold tracking-tight text-ink">Testimonials</h1>
        <p className="text-muted mt-2 text-[15px]">
          {pendingCount > 0
            ? `${pendingCount} pending review · ${testimonials.length} total`
            : `${testimonials.length} total · nothing pending`}
        </p>
      </div>
      <AdminTestimonials initialData={testimonials} />
    </div>
  );
}
