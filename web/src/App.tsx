import { useLayoutEffect, useRef } from "react";
import { Link, NavLink, Outlet, Route, Routes, useLocation, useMatch } from "react-router";
import { ArrowRight, CodeXml, Image as ImageIcon, Settings2 } from "lucide-react";
import { PanelProvider, usePanel } from "./panel-context.tsx";
import { PanelConnection } from "./PanelConnection.tsx";
import { EditorProvider, ImageEditor, ImageActions } from "./ImageEditor.tsx";
import { SettingsProvider, SettingsPage } from "./SettingsPage.tsx";
import { ImageApi } from "./ImageApi.tsx";

const PROJECT = "https://github.com/vilicvane/xiaomi.controller.86v1";

function GitHubMark() {
  return <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M12 .8a11.2 11.2 0 0 0-3.54 21.83c.56.1.77-.24.77-.54v-2.1c-3.12.68-3.78-1.32-3.78-1.32-.51-1.3-1.24-1.65-1.24-1.65-1.02-.7.08-.68.08-.68 1.13.08 1.72 1.16 1.72 1.16 1 1.72 2.62 1.22 3.26.93.1-.73.39-1.22.71-1.5-2.49-.28-5.1-1.24-5.1-5.54 0-1.23.44-2.23 1.16-3.01-.12-.28-.5-1.42.11-2.96 0 0 .95-.3 3.08 1.15a10.7 10.7 0 0 1 5.6 0c2.14-1.45 3.08-1.15 3.08-1.15.61 1.54.23 2.68.11 2.96.73.78 1.16 1.78 1.16 3.01 0 4.32-2.61 5.26-5.11 5.54.4.35.76 1.03.76 2.08v3.08c0 .3.2.65.77.54A11.2 11.2 0 0 0 12 .8Z" />
  </svg>;
}

function AppLayout() {
  const { search } = usePanel();
  const location = useLocation();
  const editing = useMatch("/") !== null;
  const previousPath = useRef(location.pathname);
  const content = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const path = location.pathname.replace(/\/$/, "") || "/";
    document.title = (path === "/settings" ? "设置 · " : path === "/" ? "" : "页面未找到 · ") + "小米智能家庭面板";
    if (previousPath.current !== location.pathname) {
      window.scrollTo(0, 0);
      const heading = content.current!.querySelector<HTMLHeadingElement>("h2")!;
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }
    previousPath.current = location.pathname;
    if (location.hash === "#api") document.getElementById("api")?.scrollIntoView();
  }, [location.pathname, location.hash]);

  return <>
    <header className="site-header">
      <Link className="brand" to={{ pathname: "/", search }} data-page="editor">
        <span className="brand-mark"><ImageIcon aria-hidden="true" /></span>
        <h1>小米智能家庭面板</h1><span className="beta">86v1</span>
      </Link>
      <nav aria-label="主导航">
        <NavLink className="nav-link" to={{ pathname: "/", search }} end data-page="editor">
          <ImageIcon aria-hidden="true" /><span>画面</span>
        </NavLink>
        <NavLink className="nav-link" to={{ pathname: "/settings", search }} data-page="settings">
          <Settings2 aria-hidden="true" /><span>设置</span>
        </NavLink>
        <Link className="nav-link api-nav" to={{ pathname: "/", search, hash: "#api" }} data-anchor="api">
          <CodeXml aria-hidden="true" /><span>API 指南</span>
        </Link>
        <a className="github-link" href={PROJECT} target="_blank" rel="noopener noreferrer" aria-label="GitHub 项目">
          <GitHubMark /><span>GitHub</span>
        </a>
      </nav>
    </header>
    <main className={`app-layout${editing ? " with-editor" : ""}`}>
      <div className="page-content" ref={content}><Outlet /></div>
      <aside className="app-sidebar">
        <PanelConnection />
        {editing && <div className="image-actions"><ImageActions /></div>}
      </aside>
      {editing && <ImageApi />}
    </main>
    <footer><span><strong>xiaomi.controller.86v1</strong></span>
      <a href={PROJECT} target="_blank" rel="noopener noreferrer">vilicvane <ArrowRight aria-hidden="true" /></a>
    </footer>
  </>;
}

function EditorPage() {
  return <div id="editor-page"><ImageEditor /></div>;
}

function NotFoundPage() {
  const { search } = usePanel();
  return <section id="not-found-page" className="not-found card">
    <h2>找不到这个页面</h2>
    <Link className="button secondary" to={{ pathname: "/", search }}>返回画面 <ArrowRight aria-hidden="true" /></Link>
  </section>;
}

export function App() {
  return <PanelProvider><EditorProvider><SettingsProvider>
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<EditorPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  </SettingsProvider></EditorProvider></PanelProvider>;
}
