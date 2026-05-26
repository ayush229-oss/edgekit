// Legacy route — signup is now handled by Clerk on the landing page.
import { redirect } from "next/navigation";
export default function WaitlistPage() { redirect("/"); }
