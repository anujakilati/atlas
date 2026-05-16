import type { BubbleType } from "@/lib/bubbles";
import { GraduationCap, Home, Store } from "lucide-react";

export const bubbleTypeConfig: Record<
  BubbleType,
  {
    label: string;
    icon: typeof Home;
    card: string;
    accent: string;
    pattern: string;
  }
> = {
  house: {
    label: "House",
    icon: Home,
    card: "border-amber-500/30 bg-gradient-to-br from-amber-500/20 via-card to-card",
    accent: "text-amber-300",
    pattern: "bg-[radial-gradient(circle_at_20%_20%,oklch(0.78_0.11_78/0.35),transparent_55%)]",
  },
  store: {
    label: "Store",
    icon: Store,
    card: "border-sky-500/30 bg-gradient-to-br from-sky-500/20 via-card to-card",
    accent: "text-sky-300",
    pattern: "bg-[radial-gradient(circle_at_80%_20%,oklch(0.65_0.12_230/0.35),transparent_55%)]",
  },
  school: {
    label: "School",
    icon: GraduationCap,
    card: "border-violet-500/30 bg-gradient-to-br from-violet-500/20 via-card to-card",
    accent: "text-violet-300",
    pattern: "bg-[radial-gradient(circle_at_50%_0%,oklch(0.62_0.14_300/0.35),transparent_60%)]",
  },
};
