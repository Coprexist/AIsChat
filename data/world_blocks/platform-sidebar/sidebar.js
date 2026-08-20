/* 平台侧边栏积木 — 用法：
   1. 引入 sidebar.css + 本文件
   2. 设置 window.SIDEBAR_ITEMS = [{ label, href }]（世界自己的菜单）
   3. window.SidebarBlock.init()
   结构：平台基础菜单（首页/聊天/世界列表/设置，必保留，可折叠的「平台」组，跳转主应用）
         + 世界自定义菜单（世界内跳转）
   自动：隐藏平台悬浮图标（WorldUI.hideFloatingIcon），本积木自带折叠开关
   DIY：本积木同目录下 diy/custom.css 与 diy/custom.js 会在主文件加载后自动引入——
        改样式/加逻辑写那里，平台更新积木不会覆盖 diy/（主文件旧版备份在 .bak/）。
*/
(function () {
  // 平台基础菜单：四个目的地必保留，但组名/项名可自定义（样式可直接改 sidebar.css）
  // 跳转目标拼 WORLD_UI 前缀：独立部署为空串（/worlds），宿主嵌入时
  // （DSH）为 /aischat-ui（/aischat-ui/worlds），否则会落到宿主的 SPA fallback。
  var UI_BASE = window.WORLD_UI || "";
  var PLATFORM_TITLE = window.SIDEBAR_PLATFORM_TITLE || "平台";
  var PLATFORM_LABELS = window.SIDEBAR_PLATFORM_LABELS || {};
  var PLATFORM_ITEMS = [
    { label: PLATFORM_LABELS.home || "首页", href: UI_BASE + "/" },
    { label: PLATFORM_LABELS.chat || "聊天", href: UI_BASE + "/chat" },
    { label: PLATFORM_LABELS.worlds || "世界列表", href: UI_BASE + "/worlds" },
    { label: PLATFORM_LABELS.settings || "设置", href: UI_BASE + "/settings" }
  ];
  var CUSTOM_ITEMS = window.SIDEBAR_ITEMS || [];
  var BRAND = window.SIDEBAR_BRAND || (window.WORLD_AI_NAME || "世界");

  var sidebarEl, toggleEl;

  // ── DIY 定制加载：diy/custom.css 后置覆盖 + diy/custom.js（存在才引入；平台更新不动 diy/）──
  function loadDiy() {
    var script = document.currentScript;
    if (!script || !script.src) return;
    var base = script.src.replace(/[^/]*$/, "");
    ["diy/custom.css", "diy/custom.js"].forEach(function (rel) {
      fetch(base + rel).then(function (r) {
        if (!r.ok) return;
        if (rel.endsWith(".css")) {
          var link = document.createElement("link");
          link.rel = "stylesheet";
          link.href = base + rel;
          document.head.appendChild(link);
        } else {
          var s = document.createElement("script");
          s.src = base + rel;
          document.head.appendChild(s);
        }
      }).catch(function () {});
    });
  }
  loadDiy();

  function goParent(href) {
    try {
      window.parent.location.href = href;
    } catch (e) {
      window.location.href = href;
    }
  }

  function build() {
    sidebarEl = document.createElement("aside");
    // 2026-08-13：侧边导航栏默认收起（桌面端+移动端一致）——用户点击展开入口才显示
    sidebarEl.className = "sidebar-block collapsed";

    var brand = document.createElement("div");
    brand.className = "sb-brand";
    brand.textContent = BRAND;
    sidebarEl.appendChild(brand);

    var items = document.createElement("nav");
    items.className = "sb-items";

    // ── 平台基础组（必保留，可折叠） ──
    var platWrap = document.createElement("details");
    platWrap.className = "sb-group";
    platWrap.open = true;
    var platSum = document.createElement("summary");
    platSum.className = "sb-group-title";
    platSum.textContent = PLATFORM_TITLE;
    platWrap.appendChild(platSum);
    PLATFORM_ITEMS.forEach(function (it) {
      var a = document.createElement("a");
      a.className = "sb-item sb-item-platform";
      a.textContent = it.label;
      a.href = it.href;
      a.addEventListener("click", function (ev) {
        ev.preventDefault();
        goParent(it.href);
      });
      platWrap.appendChild(a);
    });
    items.appendChild(platWrap);

    // ── 世界自定义菜单 ──
    if (CUSTOM_ITEMS.length > 0) {
      var customWrap = document.createElement("div");
      customWrap.className = "sb-group-custom";
      CUSTOM_ITEMS.forEach(function (it) {
        var a = document.createElement("a");
        a.className = "sb-item";
        a.textContent = it.label;
        if (it.icon) a.textContent = it.icon + " " + it.label;
        a.href = it.href || "#";
        a.addEventListener("click", function () {
          document.querySelectorAll(".sb-item").forEach(function (el) { el.classList.remove("active"); });
          a.classList.add("active");
          if (window.innerWidth <= 768) setCollapsed(true);
        });
        customWrap.appendChild(a);
      });
      items.appendChild(customWrap);
    }

    sidebarEl.appendChild(items);

    var footer = document.createElement("div");
    footer.className = "sb-footer";
    footer.textContent = window.WORLD_ID != null ? "world-" + window.WORLD_ID : "";
    sidebarEl.appendChild(footer);

    toggleEl = document.createElement("button");
    toggleEl.className = "sb-toggle";
    toggleEl.textContent = "»";  // 默认收起态：显示展开箭头
    toggleEl.title = "切换侧边栏";
    toggleEl.addEventListener("click", function () { setCollapsed(!sidebarEl.classList.contains("collapsed")); });

    document.body.appendChild(sidebarEl);
    document.body.appendChild(toggleEl);

    // 本积木即世界的导航 → 隐藏平台悬浮图标，避免两套 UI 重复
    if (window.WorldUI && window.WorldUI.hideFloatingIcon) {
      window.WorldUI.hideFloatingIcon();
    }
    // 页面主体让出侧边栏空间
    applyBodyPadding();
    window.addEventListener("resize", applyBodyPadding);
  }

  function applyBodyPadding() {
    var collapsed = sidebarEl && sidebarEl.classList.contains("collapsed");
    document.body.style.paddingLeft = collapsed ? "0px" : (window.innerWidth <= 768 ? "0px" : "240px");
  }

  function setCollapsed(c) {
    if (!sidebarEl) return;
    sidebarEl.classList.toggle("collapsed", c);
    if (c) { toggleEl.textContent = "»"; } else { toggleEl.textContent = "«"; }
    applyBodyPadding();
  }

  window.SidebarBlock = {
    init: function (items, brand) {
      if (items) CUSTOM_ITEMS = items;
      if (brand) BRAND = brand;
      if (!sidebarEl) build();
      return window.SidebarBlock;
    },
    setItems: function (items) { CUSTOM_ITEMS = items; if (sidebarEl) { sidebarEl.remove(); toggleEl.remove(); sidebarEl = null; build(); } },
    toggle: function () { setCollapsed(!sidebarEl.classList.contains("collapsed")); },
    setCollapsed: setCollapsed
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { window.SidebarBlock.init(); });
  } else {
    window.SidebarBlock.init();
  }
})();
