import { Sidebar } from "@/components/Sidebar";
import { syncCurrentUserProfile } from "@/lib/profile-sync";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  // Fire-and-(mostly)-forget: upsert the Clerk user into Supabase so the
  // profiles table stays in sync. Cheap and lets us track "last_seen_at"
  // accurately even if the user never visits an analytics endpoint.
  await syncCurrentUserProfile().catch(() => {});

  return (
    <div className="flex h-screen overflow-hidden bg-paper">
      <Sidebar />
      <div className="flex-1 overflow-y-auto">
        <main className="max-w-5xl mx-auto px-8 py-8">
          {children}
        </main>
      </div>
    </div>
  );
}
