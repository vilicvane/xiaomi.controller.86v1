import {
  createContext,
  useCallback,
  useContext,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { useLocation, useNavigate, useNavigationType } from "react-router";
import { normalizeDeviceEndpoint, queryEndpoint } from "./panel-api.ts";

type PanelState = {
  address: string;
  endpoint: string | null;
  revision: number;
  error: string;
  search: string;
  inputRef: RefObject<HTMLInputElement | null>;
  setAddress(value: string): void;
  commitAddress(): void;
  focusAddress(): void;
  getRevision(): number;
};

const PanelContext = createContext<PanelState | null>(null);

function endpointOf(address: string): string | null {
  try {
    return normalizeDeviceEndpoint(address);
  } catch {
    return null;
  }
}

export function PanelProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const navigationType = useNavigationType();
  const [state, setState] = useState(() => ({
    address: queryEndpoint(location.search)?.slice(7) ?? "",
    revision: 0,
  }));
  const current = useRef(state);
  const lastLocation = useRef(location.key);
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState("");
  const setAddress = useCallback((address: string) => {
    if (address === current.current.address) return;
    current.current = { address, revision: current.current.revision + 1 };
    setState(current.current);
    setError("");
  }, []);
  const getRevision = useCallback(() => current.current.revision, []);
  const focusAddress = useCallback(() => inputRef.current?.focus(), []);

  useLayoutEffect(() => {
    if (lastLocation.current === location.key) return;
    lastLocation.current = location.key;
    const incoming = queryEndpoint(location.search);
    // Internal navigation keeps even incomplete drafts. History restores its URL target.
    if (navigationType === "POP") setAddress(incoming?.slice(7) ?? "");
    else if (incoming !== endpointOf(current.current.address))
      setAddress(incoming?.slice(7) ?? "");
  }, [location.key, location.search, navigationType, setAddress]);

  const endpoint = endpointOf(state.address);
  const params = new URLSearchParams(location.search);
  params.delete("device");
  if (endpoint) params.set("device", endpoint);
  const search = params.size ? "?" + params.toString() : "";

  function commitAddress() {
    if (state.address.trim() && !endpoint) {
      try {
        normalizeDeviceEndpoint(state.address);
      } catch (cause) {
        setError((cause as Error).message);
      }
    }
    if (search !== location.search)
      void navigate({ pathname: location.pathname, search, hash: location.hash }, { replace: true });
  }

  return (
    <PanelContext.Provider value={{ ...state, endpoint, error, search, inputRef,
      setAddress, commitAddress, focusAddress, getRevision }}>
      {children}
    </PanelContext.Provider>
  );
}

export function usePanel() {
  return useContext(PanelContext)!;
}
