// Legacy route — replaced by /home in the new app layout.
import { redirect } from "next/navigation";
export default function DashboardPage() { redirect("/home"); }
