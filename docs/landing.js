(() => {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const touch = window.matchMedia("(pointer: coarse)").matches || "ontouchstart" in window;
  if (touch) document.body.classList.add("has-touch");

  /* Custom cursor + spotlight */
  const cursor = document.getElementById("cursor");
  const dot = document.getElementById("cursor-dot");
  const spot = document.getElementById("spot");
  let cx = window.innerWidth / 2;
  let cy = window.innerHeight / 3;
  let tx = cx;
  let ty = cy;

  if (!touch && !reduce) {
    window.addEventListener(
      "pointermove",
      (e) => {
        tx = e.clientX;
        ty = e.clientY;
        if (dot) dot.style.transform = `translate(${tx}px, ${ty}px) translate(-50%, -50%)`;
        if (spot) spot.style.transform = `translate(${tx}px, ${ty}px) translate(-50%, -50%)`;
      },
      { passive: true }
    );

    const tick = () => {
      cx += (tx - cx) * 0.18;
      cy += (ty - cy) * 0.18;
      if (cursor) cursor.style.transform = `translate(${cx}px, ${cy}px) translate(-50%, -50%)`;
      requestAnimationFrame(tick);
    };
    tick();

    document.querySelectorAll("a, button, [data-magnetic], summary").forEach((el) => {
      el.addEventListener("pointerenter", () => cursor?.classList.add("is-hot"));
      el.addEventListener("pointerleave", () => cursor?.classList.remove("is-hot"));
    });
  }

  /* Magnetic buttons */
  if (!touch && !reduce) {
    document.querySelectorAll("[data-magnetic]").forEach((el) => {
      el.addEventListener("pointermove", (e) => {
        const r = el.getBoundingClientRect();
        const x = e.clientX - (r.left + r.width / 2);
        const y = e.clientY - (r.top + r.height / 2);
        el.style.transform = `translate(${x * 0.18}px, ${y * 0.22}px)`;
      });
      el.addEventListener("pointerleave", () => {
        el.style.transform = "";
      });
    });
  }

  /* Scroll progress + nav solid */
  const bar = document.getElementById("scroll-progress");
  const nav = document.getElementById("topnav");
  const onScroll = () => {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    const p = max > 0 ? (window.scrollY / max) * 100 : 0;
    if (bar) bar.style.width = `${p}%`;
    nav?.classList.toggle("is-solid", window.scrollY > 40);
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  /* Burger */
  const burger = document.getElementById("burger");
  const drawer = document.getElementById("drawer");
  const setOpen = (open) => {
    nav?.classList.toggle("is-open", open);
    burger?.setAttribute("aria-expanded", open ? "true" : "false");
    if (drawer) drawer.hidden = !open;
    document.body.style.overflow = open ? "hidden" : "";
  };
  burger?.addEventListener("click", () => setOpen(!nav?.classList.contains("is-open")));
  drawer?.querySelectorAll("[data-close]").forEach((a) => a.addEventListener("click", () => setOpen(false)));
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") setOpen(false);
  });

  /* Split brand letters */
  const brand = document.querySelector("[data-split]");
  if (brand && !reduce) {
    const text = brand.textContent || "";
    brand.textContent = "";
    [...text].forEach((ch, i) => {
      const span = document.createElement("span");
      span.className = "ch";
      span.textContent = ch;
      span.style.animationDelay = `${0.05 + i * 0.05}s`;
      brand.appendChild(span);
    });
  }

  /* Reveal */
  const nodes = document.querySelectorAll("[data-reveal]");
  if (!reduce && "IntersectionObserver" in window) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("in");
          io.unobserve(entry.target);
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
    );
    nodes.forEach((n) => io.observe(n));
  } else {
    nodes.forEach((n) => n.classList.add("in"));
  }

  /* How steps */
  const steps = document.querySelectorAll(".how-step");
  const howBar = document.getElementById("how-bar");
  const howLabel = document.getElementById("how-step-label");
  const setStep = (n) => {
    steps.forEach((s) => s.classList.toggle("is-on", s.getAttribute("data-step") === String(n)));
    if (howBar) howBar.style.width = `${(n / 3) * 100}%`;
    if (howLabel) howLabel.textContent = `0${n} / 03`;
  };
  steps.forEach((s) => {
    s.querySelector("button")?.addEventListener("click", () => setStep(s.getAttribute("data-step")));
  });

  /* Look tabs */
  const tabs = document.querySelectorAll(".look-tab");
  const panelA = document.getElementById("look-a");
  const panelB = document.getElementById("look-b");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const key = tab.getAttribute("data-tab");
      tabs.forEach((t) => {
        const on = t === tab;
        t.classList.toggle("is-on", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      if (panelA && panelB) {
        panelA.hidden = key !== "a";
        panelB.hidden = key !== "b";
        panelA.classList.toggle("is-on", key === "a");
        panelB.classList.toggle("is-on", key === "b");
      }
    });
  });

  /* Product stage tilt */
  const stage = document.querySelector("[data-tilt-stage]");
  if (stage && !touch && !reduce) {
    stage.addEventListener("pointermove", (e) => {
      const r = stage.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5;
      const y = (e.clientY - r.top) / r.height - 0.5;
      stage.style.transform = `perspective(1200px) rotateY(${x * 8}deg) rotateX(${-y * 6}deg)`;
    });
    stage.addEventListener("pointerleave", () => {
      stage.style.transform = "";
    });
  }

  /* FAQ one-open */
  const faqs = document.querySelectorAll(".ask-item");
  faqs.forEach((item) => {
    item.addEventListener("toggle", () => {
      if (!item.open) return;
      faqs.forEach((o) => {
        if (o !== item) o.open = false;
      });
    });
  });

  /* Close drawer on desktop */
  const mq = window.matchMedia("(min-width: 768px)");
  mq.addEventListener?.("change", () => {
    if (mq.matches) setOpen(false);
  });
})();
