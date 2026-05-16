import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/AppShell";

// Pathless layout: wraps all child routes with the AppShell (bottom nav).
export const Route = createFileRoute("/_layout" as never)({
  component: AppShell,
});
