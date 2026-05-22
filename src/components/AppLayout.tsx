/**
 * Layout principal — sidebar à esquerda + Outlet das páginas à direita.
 * Sidebar tem navegação fixa pra Home, Upload, Settings.
 */

import { NavLink, Outlet } from "react-router-dom";
import { ThemeToggle } from "@/components/ThemeToggle";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/", label: "Reuniões", end: true },
  { to: "/upload", label: "Nova reunião" },
  { to: "/settings", label: "Configurações" },
] as const;

export function AppLayout() {
  return (
    <div className="flex h-screen bg-background text-foreground">
      <aside className="w-56 shrink-0 border-r bg-card flex flex-col">
        <div className="px-6 py-5 border-b">
          <h1 className="text-xl font-semibold tracking-tight">Eskuta</h1>
          <p className="text-xs text-muted-foreground mt-1">
            Ata de reunião automática
          </p>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={"end" in item ? item.end : false}
              className={({ isActive }) =>
                cn(
                  "block rounded-md px-3 py-2 text-sm font-medium",
                  "transition-colors",
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="px-6 py-3 border-t text-xs text-muted-foreground flex items-center justify-between gap-2">
          <span>MVP · Fase 1</span>
          <ThemeToggle compact />
        </div>
      </aside>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
