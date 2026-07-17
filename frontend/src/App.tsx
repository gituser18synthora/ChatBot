import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { ProtectedRoute } from "@/routes/ProtectedRoute";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { LoginPage } from "@/pages/LoginPage";
import { ChatPage } from "@/pages/ChatPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { DashboardPage } from "@/pages/admin/DashboardPage";
import { TenantsPage } from "@/pages/admin/TenantsPage";
import { KnowledgeBasesPage } from "@/pages/admin/KnowledgeBasesPage";
import { DocumentsPage } from "@/pages/admin/DocumentsPage";
import { UsersPage } from "@/pages/admin/UsersPage";
import { ProfilePage } from "@/pages/admin/ProfilePage";
import { ConversationsPage } from "@/pages/admin/ConversationsPage";
import { AnalyticsPage } from "@/pages/admin/AnalyticsPage";
import { AuditLogsPage } from "@/pages/admin/AuditLogsPage";
import { SettingsPage } from "@/pages/admin/SettingsPage";

function RootRedirect() {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={user.role === "chat_user" ? "/chat" : "/admin"} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/login" element={<LoginPage />} />

      <Route
        path="/chat"
        element={
          // Chat is tenant-scoped; Super Admins (no tenant) are redirected to /admin.
          <ProtectedRoute roles={["tenant_admin", "chat_user"]}>
            <ChatPage />
          </ProtectedRoute>
        }
      />

      <Route
        path="/admin"
        element={
          <ProtectedRoute roles={["super_admin", "tenant_admin"]}>
            <AdminLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route
          path="tenants"
          element={
            <ProtectedRoute roles={["super_admin"]}>
              <TenantsPage />
            </ProtectedRoute>
          }
        />
        <Route path="knowledge-bases" element={<KnowledgeBasesPage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="conversations" element={<ConversationsPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="audit-logs" element={<AuditLogsPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
