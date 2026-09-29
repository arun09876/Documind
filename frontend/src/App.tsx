import { Loader2 } from "lucide-react";
import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "@/components/Layout";
import { useApp } from "@/context/App";
import AuthPage from "@/pages/AuthPage";

const ChatPage = lazy(() => import("@/pages/ChatPage"));
const LibraryPage = lazy(() => import("@/pages/LibraryPage"));

function Spinner() {
  return <div className="grid h-full place-items-center"><Loader2 className="size-6 animate-spin text-accent" /></div>;
}

function Private({ children }: { children: ReactNode }) {
  const { user, loadingUser } = useApp();
  if (loadingUser) return <Spinner />;
  return user ? children : <Navigate to="/login" replace />;
}

function Guest({ children }: { children: ReactNode }) {
  const { user, loadingUser } = useApp();
  if (loadingUser) return <Spinner />;
  return user ? <Navigate to="/c" replace /> : children;
}

export default function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/login" element={<Guest><AuthPage mode="login" /></Guest>} />
        <Route path="/register" element={<Guest><AuthPage mode="register" /></Guest>} />
        <Route element={<Private><Layout /></Private>}>
          {/* One route with an optional id, so starting a new chat doesn't remount mid-stream. */}
          <Route path="/c/:id?" element={<ChatPage />} />
          <Route path="/library" element={<LibraryPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/c" replace />} />
      </Routes>
    </Suspense>
  );
}
