import BackendStatus from "@/components/BackendStatus";

export default function Home() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">
        Property Risk &amp; Hazard Exposure
      </h1>
      <p className="mt-3 text-slate-600">
        Enter a US address to get a transparent, source-traceable multi-peril
        risk profile built on FEMA National Risk Index and National Flood Hazard
        Layer data.
      </p>

      <div className="mt-8 rounded-lg border border-slate-200 bg-white p-4 text-sm">
        <BackendStatus />
      </div>

      <p className="mt-8 text-sm text-slate-500">
        Sprint 0 foundation. The address lookup, map, and scoring UI arrive in
        Sprints 1–4.
      </p>
    </main>
  );
}
