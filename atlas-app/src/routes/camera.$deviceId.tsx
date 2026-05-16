import { createFileRoute, redirect } from "@tanstack/react-router";

/** Legacy camera links → device token flow */
export const Route = createFileRoute("/camera/$deviceId")({
  beforeLoad: () => {
    throw redirect({ to: "/device" });
  },
});
