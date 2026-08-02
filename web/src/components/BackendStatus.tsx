"use client";

import { useEffect, useState } from "react";
import { getHealth, type HealthResponse } from "@/lib/api";

type State =
  | { kind: "loading" }
  | { kind: "ok"; data: HealthResponse }
  | { kind: "error"; message: string };

export default function BackendStatus() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let active = true;
    getHealth()
      .then((data) => active && setState({ kind: "ok", data }))
      .catch((err) =>
        active &&
        setState({ kind: "error", message: err?.message ?? "Unreachable" }),
      );
    return () => {
      active = false;
    };
  }, []);

  if (state.kind === "loading") {
    return <span className="text-slate-500">Checking backend…</span>;
  }
  if (state.kind === "error") {
    return (
      <span className="text-red-600">
        Backend unreachable — {state.message}
      </span>
    );
  }
  return (
    <span className="text-green-700">
      Backend healthy · {state.data.service} · {state.data.environment}
    </span>
  );
}
