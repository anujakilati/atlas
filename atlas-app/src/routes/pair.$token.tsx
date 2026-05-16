import { createFileRoute, redirect } from "@tanstack/react-router";

/** Legacy pairing links → device token flow */
export const Route = createFileRoute("/pair/$token")({
  beforeLoad: () => {
    throw redirect({ to: "/device" });
  },
});
