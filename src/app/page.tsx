"use client";

import { useEffect } from "react";
import { useAppStore } from "@/lib/store";
import { SiteHeader } from "@/components/site-header";
import { SiteFooter } from "@/components/site-footer";
import { AuthDialog } from "@/components/auth-dialog";
import { CommandPalette } from "@/components/command-palette";
import { Landing } from "@/components/landing";
import { AppShell } from "@/components/app";

export default function Home() {
  const { view, setView, authOpen, setAuthOpen } = useAppStore();

  // Scroll para topo ao trocar de view
  useEffect(() => {
    if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
  }, [view]);

  return (
    <>
      <SiteHeader />
      <main className="flex-1">
        {view === "landing" ? <Landing /> : <AppShell />}
      </main>
      <SiteFooter />
      <AuthDialog />
      <CommandPalette />
    </>
  );
}
