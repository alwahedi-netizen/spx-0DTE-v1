// lab-nav.js — the section bar shared by every paper.sahmi.ae page.
// Mirrors the trader's desks: one sandbox per asset class, same discipline
// (SANDBOX_PLAYBOOK.md). Include with <script src="/static/lab-nav.js"></script>
// as the first element of <body>.
(function () {
  const SECTIONS = [
    { path: "/",            label: "Overview" },
    { path: "/stocks",      label: "Stocks & ETFs", tag: "paper" },
    { path: "/options",     label: "Options",       tag: "live pilot" },
    { path: "/crypto",      label: "Crypto",        tag: "planned" },
    { path: "/fx",          label: "FX",            tag: "planned" },
    { path: "/commodities", label: "Commodities",   tag: "planned" },
  ];
  const here = location.pathname.replace(/\/+$/, "") || "/";
  const css = `
    .labnav { position:sticky; top:0; z-index:50; background:#1e232b; color:#e9e6de;
      border-bottom:1px solid #0f1318; }
    .labnav .in { max-width:1100px; margin:0 auto; padding:0 16px; display:flex;
      align-items:center; gap:4px; overflow-x:auto; scrollbar-width:none; }
    .labnav .in::-webkit-scrollbar { display:none; }
    .labnav .brand { font:600 13px/1 system-ui,"Segoe UI",sans-serif; letter-spacing:.08em;
      text-transform:uppercase; color:#c9b98f; padding:14px 14px 14px 0; white-space:nowrap; }
    .labnav a { color:#b9bec8; text-decoration:none; white-space:nowrap;
      font:500 13px/1 system-ui,"Segoe UI",sans-serif; padding:14px 10px 12px;
      border-bottom:2px solid transparent; }
    .labnav a:hover { color:#fff; }
    .labnav a.on { color:#fff; border-bottom-color:#c9b98f; }
    .labnav a small { font-size:10px; color:#7d8594; margin-left:5px; letter-spacing:.04em; }
    .labnav a.on small { color:#c9b98f; }`;
  const st = document.createElement("style");
  st.textContent = css;
  document.head.appendChild(st);
  const nav = document.createElement("nav");
  nav.className = "labnav";
  nav.setAttribute("aria-label", "Sandbox sections");
  nav.innerHTML = `<div class="in"><span class="brand">Logicon Paper Lab</span>` +
    SECTIONS.map(s => `<a href="${s.path}" class="${s.path === here ? "on" : ""}"` +
      `${s.path === here ? ' aria-current="page"' : ""}>${s.label}` +
      `${s.tag ? `<small>${s.tag}</small>` : ""}</a>`).join("") + `</div>`;
  document.body.insertBefore(nav, document.body.firstChild);
})();
