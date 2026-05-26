/**
 * GET /api/me — returns basic info about the current user.
 * Used by the sidebar to conditionally show admin links.
 */
import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { isAdmin } from "@/lib/profile-sync";

export async function GET() {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ isAdmin: false });
  const admin = await isAdmin();
  return NextResponse.json({ isAdmin: admin });
}
