"use client";

/**
 * AddressSearch — address input + search button.
 *
 * Sprint 2 refactor: delegates all async logic to the parent via onSearch(address).
 * The parent (page.tsx) chains geocode → flood zone and manages state. This keeps
 * AddressSearch a thin UI component with no knowledge of what comes after the submit.
 */

import { useState, type FormEvent } from "react";

interface Props {
  onSearch: (address: string) => Promise<void>;
}

export default function AddressSearch({ onSearch }: Props) {
  const [address, setAddress] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = address.trim();
    if (!trimmed) return;

    setLoading(true);
    try {
      await onSearch(trimmed);
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={address}
        onChange={(e) => setAddress(e.target.value)}
        placeholder="e.g. 1600 Pennsylvania Ave NW, Washington, DC"
        aria-label="US property address"
        className="flex-1 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
      />
      <button
        type="submit"
        disabled={loading || !address.trim()}
        className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? "Searching…" : "Search"}
      </button>
    </form>
  );
}
