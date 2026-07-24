(() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* Sticky nav state */
  const nav = document.getElementById("nav");
  const onScroll = () => {
    if (!nav) return;
    nav.classList.toggle("is-scrolled", window.scrollY > 24);
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  /* Mobile menu */
  const toggle = document.getElementById("nav-toggle");
  const sheet = document.getElementById("nav-sheet");
  const setMenu = (open) => {
    if (!nav || !toggle || !sheet) return;
    nav.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.setAttribute("aria-label", open ? "关闭菜单" : "打开菜单");
    sheet.hidden = !open;
    document.body.style.overflow = open ? "hidden" : "";
  };

  toggle?.addEventListener("click", () => {
    setMenu(!nav.classList.contains("is-open"));
  });

  sheet?.querySelectorAll("[data-close-nav]").forEach((el) => {
    el.addEventListener("click", () => setMenu(false));
  });

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") setMenu(false);
  });

  /* Scroll reveal */
  const reveals = document.querySelectorAll(".reveal");
  if (!reduceMotion && "IntersectionObserver" in window) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const el = entry.target;
          const delay = el.getAttribute("data-delay");
          if (delay) el.style.setProperty("--delay", `${delay}ms`);
          el.classList.add("is-in");
          io.unobserve(el);
        });
      },
      { threshold: 0.14, rootMargin: "0px 0px -8% 0px" }
    );
    reveals.forEach((el) => io.observe(el));
  } else {
    reveals.forEach((el) => el.classList.add("is-in"));
  }

  /* Product tabs */
  const tabs = document.querySelectorAll(".product-tab");
  const panels = {
    activities: document.getElementById("panel-activities"),
    overview: document.getElementById("panel-overview"),
  };

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const key = tab.getAttribute("data-panel");
      tabs.forEach((t) => {
        const on = t === tab;
        t.classList.toggle("is-active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      Object.entries(panels).forEach(([id, panel]) => {
        if (!panel) return;
        panel.hidden = id !== key;
        panel.classList.toggle("is-active", id === key);
      });
    });
  });

  /* FAQ: one open at a time */
  const faqs = document.querySelectorAll(".faq-item");
  faqs.forEach((item) => {
    item.addEventListener("toggle", () => {
      if (!item.open) return;
      faqs.forEach((other) => {
        if (other !== item) other.open = false;
      });
    });
  });

  /* Flow accordion highlight */
  const flowTriggers = document.querySelectorAll(".flow-trigger");
  flowTriggers.forEach((btn) => {
    btn.addEventListener("click", () => {
      flowTriggers.forEach((b) => b.setAttribute("aria-expanded", b === btn ? "true" : "false"));
    });
  });

  /* Soft tilt on bento cards */
  if (!reduceMotion && window.matchMedia("(pointer: fine)").matches) {
    document.querySelectorAll("[data-tilt]").forEach((card) => {
      card.addEventListener("pointermove", (e) => {
        const rect = card.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width - 0.5;
        const y = (e.clientY - rect.top) / rect.height - 0.5;
        card.style.transform = `perspective(900px) rotateY(${x * 6}deg) rotateX(${-y * 6}deg) translateY(-2px)`;
      });
      card.addEventListener("pointerleave", () => {
        card.style.transform = "";
      });
    });
  }

  /* Smooth close menu on resize to desktop */
  const mq = window.matchMedia("(min-width: 768px)");
  const onMq = () => {
    if (mq.matches) setMenu(false);
  };
  mq.addEventListener?.("change", onMq);
})();
