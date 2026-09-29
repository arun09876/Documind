import { ArrowRight, FileSearch, Quote, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button, Logo } from "@/components/ui";
import { DEMO, useApp } from "@/context/App";
import { errorMessage } from "@/lib/api";

const POINTS = [
  { icon: FileSearch, title: "Hybrid search", text: "Semantic vectors and BM25 keywords, fused, so paraphrases and exact terms both match." },
  { icon: Quote, title: "Answers you can check", text: "Every claim cites a numbered passage; click it to open the exact PDF page, highlighted." },
  { icon: ShieldCheck, title: "Private libraries", text: "Each account searches only its own documents." },
];

export default function AuthPage({ mode }: { mode: "login" | "register" }) {
  const { login, register } = useApp();
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: "", email: "", password: "" });
  const [busy, setBusy] = useState<"form" | "demo" | null>(null);
  const isLogin = mode === "login";

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy("form");
    try {
      if (isLogin) await login(form.username, form.password);
      else await register(form.username, form.email, form.password);
      navigate("/c", { replace: true });
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function demo() {
    setBusy("demo");
    try {
      await login(DEMO.username, DEMO.password);
      navigate("/c", { replace: true });
    } catch (err) {
      toast.error(errorMessage(err, "Demo account missing: run `python manage.py seed_demo`."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="grid min-h-full lg:grid-cols-[1fr_1.05fr]">
      <section className="flex flex-col px-6 py-8 sm:px-14">
        <Logo />
        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-10">
          <h1 className="font-serif text-4xl font-medium tracking-tight text-ink">{isLogin ? "Welcome back" : "Create your account"}</h1>
          <p className="mt-2 text-muted">{isLogin ? "Pick up where you left off." : "Upload PDFs and start asking questions."}</p>

          <button onClick={demo} disabled={busy !== null} className="group mt-8 flex items-center gap-3 rounded-2xl border border-accent/30 bg-accent-soft p-4 text-left transition hover:border-accent/60 disabled:opacity-60">
            <span className="grid size-10 place-items-center rounded-xl bg-accent text-white dark:text-[#1a0e05]"><FileSearch className="size-5" /></span>
            <span className="flex-1">
              <span className="block text-sm font-semibold text-ink">{busy === "demo" ? "Opening demo…" : "Try the demo library"}</span>
              <span className="block text-xs text-muted">An employee handbook and a vector-search guide, ready to query</span>
            </span>
            <ArrowRight className="size-4 text-accent transition group-hover:translate-x-0.5" />
          </button>

          <div className="my-6 flex items-center gap-3 text-xs text-muted"><div className="h-px flex-1 bg-line" />or<div className="h-px flex-1 bg-line" /></div>

          <form onSubmit={submit} className="space-y-4">
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-ink-2">{isLogin ? "Username or email" : "Username"}</span>
              <input className="input" required value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} autoComplete="username" />
            </label>
            {!isLogin && (
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-ink-2">Email</span>
                <input className="input" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} autoComplete="email" />
              </label>
            )}
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-ink-2">Password</span>
              <input className="input" type="password" required minLength={isLogin ? 1 : 8} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} autoComplete={isLogin ? "current-password" : "new-password"} />
            </label>
            <Button type="submit" size="lg" className="w-full" loading={busy === "form"} disabled={busy !== null}>{isLogin ? "Log in" : "Create account"}</Button>
          </form>
          <p className="mt-6 text-center text-sm text-muted">
            {isLogin ? "New to DocuMind? " : "Already have an account? "}
            <Link to={isLogin ? "/register" : "/login"} className="font-medium text-accent hover:underline">{isLogin ? "Create an account" : "Log in"}</Link>
          </p>
        </div>
      </section>

      <section className="relative hidden overflow-hidden bg-[#1f1b16] p-14 text-[#f1ebe3] lg:flex lg:flex-col lg:justify-between">
        <div className="pointer-events-none absolute -right-24 -top-24 size-96 rounded-full bg-[#c2410c]/30 blur-[110px]" />
        <div className="relative">
          <h2 className="max-w-md font-serif text-5xl font-medium leading-[1.05] tracking-tight">Ask your documents. <em className="text-[#fdba74]">Check every answer.</em></h2>
          <p className="mt-5 max-w-md text-[15px] leading-relaxed text-[#cfc6ba]">DocuMind reads your PDFs, finds the passages that matter, and answers with citations to the exact page.</p>
        </div>

        {/* A sample exchange */}
        <div className="relative my-10 space-y-3 rounded-3xl border border-white/10 bg-white/[0.04] p-6 backdrop-blur">
          <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-[#f1ebe3] px-4 py-2 text-sm text-[#1f1b16]">How long is parental leave for primary caregivers?</div>
          <p className="text-[15px] leading-relaxed">
            Primary caregivers get <b>26 weeks of fully paid leave</b>
            <span className="mx-1 rounded-md bg-[#c2410c]/30 px-1.5 text-[11px] font-semibold text-[#fdba74]">1 p. 3</span>
            which can be split into up to three blocks within 12 months
            <span className="mx-1 rounded-md bg-[#c2410c]/30 px-1.5 text-[11px] font-semibold text-[#fdba74]">1 p. 3</span>.
          </p>
          <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] p-2.5 text-xs text-[#cfc6ba]">
            <span className="grid size-5 place-items-center rounded bg-[#c2410c] text-[10px] font-bold text-white">1</span>
            Employee Handbook · p. 3: "Primary caregivers receive 26 weeks of fully paid parental leave…"
          </div>
        </div>

        <div className="relative grid gap-4">
          {POINTS.map(({ icon: Icon, title, text }) => (
            <div key={title} className="flex gap-3">
              <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-white/10 text-[#fdba74]"><Icon className="size-4" /></span>
              <span className="text-sm text-[#cfc6ba]"><b className="block text-[#f1ebe3]">{title}</b>{text}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
