import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/vault/$bubbleId")({
  component: VaultLayout,
});

function VaultLayout() {
  return <Outlet />;
}
