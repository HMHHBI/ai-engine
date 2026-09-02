import { AuthGuard } from "@/components/auth/auth-guard";
import { AppShell } from "@/components/layout/app-shell";

export default function DashboardPage() {
  return (
    <AuthGuard>
      <AppShell />
    </AuthGuard>
  );
}
