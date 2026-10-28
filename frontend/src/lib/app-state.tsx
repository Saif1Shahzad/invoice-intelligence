import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { createClient, type ApiClient } from "./api/client";
import type { ApiDocument } from "./api/types";
import { makeSampleDocs } from "./sample-data";
import type { SampleDoc } from "./review";

export type Mode = "sample" | "live";
export type Conn = "unconfigured" | "checking" | "reachable" | "unreachable";

interface AppState {
  mode: Mode;
  setMode: (m: Mode) => void;
  apiBase: string;
  setApiBase: (b: string) => void;
  conn: Conn;
  connError: string | null;
  recheck: () => void;
  client: ApiClient | null;
  sampleDocs: SampleDoc[];
  updateSample: (id: string, fn: (d: SampleDoc) => SampleDoc) => void;
  addSample: (d: SampleDoc) => void;
  resetSample: () => void;
  liveDocs: ApiDocument[];
  liveError: string | null;
  refreshLive: () => void;
}

const Ctx = createContext<AppState | null>(null);
const KEY = "ii.apiBase";

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<Mode>("sample");
  const [apiBase, setApiBaseState] = useState("");
  const [conn, setConn] = useState<Conn>("unconfigured");
  const [connError, setConnError] = useState<string | null>(null);
  const [sampleDocs, setSampleDocs] = useState<SampleDoc[]>(() => makeSampleDocs());
  const [liveDocs, setLiveDocs] = useState<ApiDocument[]>([]);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const saved = window.localStorage.getItem(KEY);
    if (saved === "/") setApiBaseState(saved);
  }, []);

  const setApiBase = useCallback((b: string) => {
    setApiBaseState(b);
    if (b) window.localStorage.setItem(KEY, b);
    else window.localStorage.removeItem(KEY);
  }, []);

  const client = useMemo(() => (apiBase ? createClient(apiBase) : null), [apiBase]);

  useEffect(() => {
    if (!client) {
      setConn("unconfigured");
      setConnError(null);
      setLiveDocs([]);
      return;
    }
    let off = false;
    setConn("checking");
    client
      .health()
      .then(() => !off && (setConn("reachable"), setConnError(null)))
      .catch((e: unknown) => !off && (setConn("unreachable"), setConnError(e instanceof Error ? e.message : String(e))));
    return () => {
      off = true;
    };
  }, [client, tick]);

  const refreshLive = useCallback(() => {
    if (!client || conn !== "reachable") return;
    client
      .listDocuments(50, 0)
      .then((d) => (setLiveDocs(d), setLiveError(null)))
      .catch((e: unknown) => setLiveError(e instanceof Error ? e.message : String(e)));
  }, [client, conn]);

  useEffect(() => {
    if (mode === "live") refreshLive();
  }, [mode, refreshLive]);

  const value: AppState = {
    mode, setMode, apiBase, setApiBase, conn, connError, recheck: () => setTick((t) => t + 1), client,
    sampleDocs,
    updateSample: (id, fn) => setSampleDocs((ds) => ds.map((d) => (d.id === id ? fn(d) : d))),
    addSample: (d) => setSampleDocs((ds) => [d, ...ds]),
    resetSample: () => setSampleDocs(makeSampleDocs()),
    liveDocs, liveError, refreshLive,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside provider");
  return v;
}

