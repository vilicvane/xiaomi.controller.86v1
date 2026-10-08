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
import { useLocation, useNavigate } from "react-router";
import { normalizeDeviceEndpoint, queryEndpoint } from "./panel-api.ts";
import {
  connectionReturnTo,
  deviceSearch,
  resolvePanelEndpoint,
  savePanelEndpoint,
  type PanelAddressStorage,
} from "./panel-address.ts";

type PanelState = {
  address: string;
  endpoint: string | null;
  revision: number;
  error: string;
  search: string;
  inputRef: RefObject<HTMLInputElement | null>;
  setAddress(value: string): void;
  commitAddress(): boolean;
  focusAddress(): void;
  getRevision(): number;
};
type AddressState = {
  locationKey: string;
  pathname: string;
  endpoint: string | null;
  address: string;
  revision: number;
  error: string;
};

const PanelContext = createContext<PanelState | null>(null);

function browserStorage(): PanelAddressStorage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function PanelProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [state, setState] = useState<AddressState>(() => {
    const endpoint = resolvePanelEndpoint(location.search, browserStorage());
    return { locationKey: location.key, pathname: location.pathname, endpoint,
      address: endpoint?.slice(7) ?? "", revision: 0, error: "" };
  });
  const current = useRef(state);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reconcile history before rendering children, so their request guards see the new target.
  // Updating this component's own state here also avoids a child-first layout-effect gap.
  if (state.locationKey !== location.key) {
    const endpoint = resolvePanelEndpoint(location.search, browserStorage());
    const targetChanged = endpoint !== state.endpoint;
    const enteringConnection = location.pathname.replace(/\/$/, "") === "/connection" &&
      state.pathname.replace(/\/$/, "") !== "/connection";
    const next = { ...state, locationKey: location.key, pathname: location.pathname, endpoint,
      revision: state.revision + (targetChanged ? 1 : 0),
      ...((targetChanged || enteringConnection) ? { address: endpoint?.slice(7) ?? "", error: "" } : {}) };
    current.current = next;
    setState(next);
  } else {
    current.current = state;
  }

  const setAddress = useCallback((address: string) => {
    if (address === current.current.address) return;
    const next = { ...current.current, address, error: "" };
    current.current = next;
    setState(next);
  }, []);
  const getRevision = useCallback(() => current.current.revision, []);
  const focusAddress = useCallback(() => {
    if (location.pathname.replace(/\/$/, "") === "/connection") {
      inputRef.current?.focus();
      return;
    }
    void navigate({ pathname: "/connection", search: deviceSearch(location.search, current.current.endpoint) }, {
      state: { returnTo: connectionReturnTo({ returnTo: location }) },
    });
  }, [location.pathname, location.hash, location.search, navigate]);

  useLayoutEffect(() => {
    const incoming = queryEndpoint(location.search);
    if (!incoming) return;
    // Redirects remain usable when storage is unavailable; only explicit save promises persistence.
    try {
      savePanelEndpoint(incoming, browserStorage());
    } catch { /* Best-effort automatic remember. */ }
  }, [location.key, location.search]);

  function commitAddress() {
    let endpoint: string;
    try {
      endpoint = normalizeDeviceEndpoint(current.current.address);
    } catch (cause) {
      const next = { ...current.current, error: (cause as Error).message };
      current.current = next;
      setState(next);
      inputRef.current?.focus();
      return false;
    }
    try {
      savePanelEndpoint(endpoint, browserStorage());
    } catch {
      const next = { ...current.current, error: "无法在此浏览器保存面板地址，请检查浏览器存储权限后重试。" };
      current.current = next;
      setState(next);
      return false;
    }
    const next = { ...current.current, endpoint, address: endpoint.slice(7), error: "",
      revision: current.current.revision + (endpoint === current.current.endpoint ? 0 : 1) };
    current.current = next;
    setState(next);
    return true;
  }

  return (
    <PanelContext.Provider value={{ address: state.address, endpoint: state.endpoint, revision: state.revision,
      error: state.error, search: deviceSearch(location.search, state.endpoint), inputRef,
      setAddress, commitAddress, focusAddress, getRevision }}>
      {children}
    </PanelContext.Provider>
  );
}

export function usePanel() {
  return useContext(PanelContext)!;
}
