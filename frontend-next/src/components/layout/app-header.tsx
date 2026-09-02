"use client";

import { Menu, PanelLeft } from "lucide-react";

import { IconButton } from "@/components/ui/icon-button";

interface AppHeaderProps {
  onOpenMobileSidebar: () => void;
  onToggleSidebar: () => void;
}

export function AppHeader({
  onOpenMobileSidebar,
  onToggleSidebar,
}: AppHeaderProps) {
  return (
    <header className="flex h-14 shrink-0 items-center border-b border-border px-3">
      <div className="md:hidden">
        <IconButton label="Open sidebar" onClick={onOpenMobileSidebar}>
          <Menu className="size-5" />
        </IconButton>
      </div>

      <div className="hidden md:block">
        <IconButton label="Toggle sidebar" onClick={onToggleSidebar}>
          <PanelLeft className="size-4" />
        </IconButton>
      </div>

      <div className="ml-2 min-w-0">
        <h1 className="truncate text-sm font-medium">New chat</h1>
      </div>
    </header>
  );
}
