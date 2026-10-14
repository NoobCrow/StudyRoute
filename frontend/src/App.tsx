import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { SandboxBanner } from "./components/SandboxBanner";
import { Loading } from "./components/Ui";
import { AuditScreen } from "./screens/Audit";
import { CompareScreen } from "./screens/Compare";
import { DashboardScreen } from "./screens/Dashboard";
import { DocumentsScreen } from "./screens/Documents";
import { LoginScreen } from "./screens/Login";
import { PaymentScreen } from "./screens/Payment";
import { PaymentsScreen } from "./screens/Payments";
import { RecipientsScreen } from "./screens/Recipients";
import { ReportScreen } from "./screens/Report";
import { RulesScreen } from "./screens/Rules";
import { SandboxScreen } from "./screens/Sandbox";

function Protected() {
  const { user, ready } = useAuth();
  if (!ready) {
    return (
      <main className="page">
        <Loading what="Restoring your session" />
      </main>
    );
  }
  return user ? <Layout /> : <Navigate to="/login" replace />;
}

export function App() {
  return (
    <>
      <SandboxBanner />
      <Routes>
        <Route path="/login" element={<LoginScreen />} />
        <Route element={<Protected />}>
          <Route index element={<DashboardScreen />} />
          <Route path="compare" element={<CompareScreen />} />
          <Route path="payments" element={<PaymentsScreen />} />
          <Route path="payments/:paymentId" element={<PaymentScreen />} />
          <Route path="payments/:paymentId/report" element={<ReportScreen />} />
          <Route path="recipients" element={<RecipientsScreen />} />
          <Route path="documents" element={<DocumentsScreen />} />
          <Route path="audit" element={<AuditScreen />} />
          <Route path="rules" element={<RulesScreen />} />
          <Route path="sandbox" element={<SandboxScreen />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}
