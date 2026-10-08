import { useEffect } from "react";
import { ArrowRight, Wifi } from "lucide-react";
import { useLocation, useNavigate } from "react-router";
import { usePanel } from "./panel-context.tsx";
import { normalizeDeviceEndpoint } from "./panel-api.ts";
import { connectionReturnTo, deviceSearch } from "./panel-address.ts";

export function PanelConnection() {
  const panel = usePanel();
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => { panel.inputRef.current?.focus(); }, [panel.inputRef]);
  return (
    <section id="connection-page" className="panel-connection card" aria-labelledby="connection-title">
      <h2 id="connection-title">面板地址</h2>
      <form id="connection-form" onSubmit={(event) => {
        event.preventDefault();
        if (!panel.commitAddress()) return;
        const target = connectionReturnTo(location.state);
        const endpoint = normalizeDeviceEndpoint(panel.address);
        void navigate({ ...target, search: deviceSearch("", endpoint) }, { replace: true });
      }}>
        <div className="panel-address">
          <label htmlFor="device">IP 地址与端口</label>
          <div className="device-field">
            <Wifi aria-hidden="true" />
            <input id="device" ref={panel.inputRef} value={panel.address}
              onChange={(event) => panel.setAddress(event.target.value)}
              type="text" inputMode="url" autoComplete="off" spellCheck={false}
              placeholder="输入 IP 地址或 IP:端口"
              aria-describedby={panel.error ? "device-error device-help" : "device-help"}
              aria-invalid={Boolean(panel.error)} />
          </div>
        </div>
        <p id="device-help">双击面板画面查看地址，默认端口 18086。保存后，此浏览器会记住地址，画面和设置页面共用同一面板。
          设备需在同一局域网；如浏览器询问本地网络访问，请允许。</p>
        {panel.error && <p id="device-error" role="alert">{panel.error}</p>}
        <div className="connection-actions"><button className="button primary" type="submit">
          <span>保存并继续</span><ArrowRight aria-hidden="true" />
        </button></div>
      </form>
    </section>
  );
}
