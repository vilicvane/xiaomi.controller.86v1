import { Wifi } from "lucide-react";
import { usePanel } from "./panel-context.tsx";

export function PanelConnection() {
  const panel = usePanel();
  return (
    <section className="panel-connection" aria-label="面板连接">
      <div className="panel-address">
        <label htmlFor="device">面板地址</label>
        <div className="device-field">
          <Wifi aria-hidden="true" />
          <input id="device" ref={panel.inputRef} value={panel.address}
            onChange={(event) => panel.setAddress(event.target.value)}
            onBlur={panel.commitAddress}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                panel.commitAddress();
              }
            }}
            type="text" inputMode="url" autoComplete="off" spellCheck={false}
            placeholder="输入 IP 地址或 IP:端口"
            aria-describedby={panel.error ? "device-error device-help" : "device-help"}
            aria-invalid={Boolean(panel.error)} />
        </div>
      </div>
      <p id="device-help">双击面板画面查看地址，默认端口 18086。
        此地址用于所有页面；设备需在同一局域网。如浏览器询问本地网络访问，请允许。</p>
      {panel.error && <p id="device-error" role="alert">{panel.error}</p>}
    </section>
  );
}
