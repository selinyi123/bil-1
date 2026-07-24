(() => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const touch = matchMedia("(pointer: coarse)").matches || "ontouchstart" in window;
  if (touch) document.body.classList.add("touch");

  const CAPS = [
    "概览页 · 统计 / 快捷操作",
    "活动页 · 筛选 / 参与 / 三连",
    "数据源 · UP 合集更新",
    "监控名单 · 转发补漏",
    "定时监视器 · 到点自动点",
    "夜间模式 · 护眼长刷",
  ];
  const TALL = new Set([4]); /* scheduler is portrait */

  const TOURS = [
    {
      title: "概览页",
      url: "本地控制台 · 概览",
      img: "./images/overview.png",
      desc: "打开软件第一站：登录态、LLM 是否就绪、活动总数 / 未参加 / 已参加一眼看清。下方可更新监控、刷新状态、一键更新。",
      points: ["账号卡片：关注 / 动态 / 私信 / @", "六宫格统计实时汇总活动库", "参与文案：自定义或随机借用评论"],
      hotspots: [
        { x: 22, y: 28, tip: "<strong>账号区</strong> — 登录态与互动数字。" },
        { x: 58, y: 42, tip: "<strong>六宫格</strong> — 活动库核心统计。" },
        { x: 72, y: 72, tip: "<strong>快捷操作</strong> — 更新 / 刷新入口。" },
      ],
    },
    {
      title: "活动页",
      url: "本地控制台 · 活动",
      img: "./images/activities.png",
      desc: "抽奖工作台：按类型与状态筛选，单条「参与」或顶部「三连参与」一次清多条未参加。",
      points: ["三连参与：按筛选最多选 3 条", "筛选：互动 / 转发 / 预约", "列表含奖品、热度、开奖时间"],
      hotspots: [
        { x: 18, y: 18, tip: "<strong>三连参与</strong> — 批量处理未参加。" },
        { x: 48, y: 30, tip: "<strong>筛选条</strong> — 快速缩小范围。" },
        { x: 70, y: 55, tip: "<strong>活动列表</strong> — 单条操作入口。" },
      ],
    },
    {
      title: "数据源 · UP 合集",
      url: "本地控制台 · 数据源",
      img: "./images/sources.png",
      desc: "内置多个抽奖 UP 合集。日常优先「更新此源」做增量同步，更稳、更不易触发风控。",
      points: ["每个合集独立更新", "检查专栏 → 分类 → 详情 → 入库", "状态徽章提示有无更新"],
      hotspots: [
        { x: 30, y: 35, tip: "<strong>合集卡片</strong> — 各数据源独立维护。" },
        { x: 78, y: 42, tip: "<strong>更新此源</strong> — 推荐日常入口。" },
      ],
    },
    {
      title: "监控名单",
      url: "本地控制台 · 监控用户",
      img: "./images/sources-watch.png",
      desc: "第 7 条发现通道：添加常转发抽奖的 UP，从他们近期转发里补合集漏抓的活动。",
      points: ["名单可增删", "同步窗口与链接数可见", "与 UP 合集双通道互补"],
      hotspots: [
        { x: 40, y: 40, tip: "<strong>监控名单</strong> — 添加常转发抽奖的 UP。" },
        { x: 75, y: 22, tip: "<strong>更新动态</strong> — 从转发补漏。" },
      ],
    },
    {
      title: "定时点击监视器",
      url: "定时点击 · Auto Scheduler",
      img: "./images/scheduler.png",
      desc: "倒计时到点自动点四个按钮。整点刷新批次，其余时段可三连。撞车即停。",
      points: ["下一刻度倒计时", "调度状态与任务连通", "启动 / 停止一键切换"],
      hotspots: [
        { x: 50, y: 35, tip: "<strong>倒计时</strong> — 下一刻度等待。" },
        { x: 50, y: 72, tip: "<strong>启停</strong> — 开关定时调度。" },
      ],
    },
    {
      title: "夜间模式",
      url: "本地控制台 · 夜间概览",
      img: "./images/night.png",
      desc: "侧栏一键夜间主题：深色背景 + 暖色强调，长时间刷列表更护眼。布局与日间一致。",
      points: ["日 / 夜即时切换", "层次更清晰", "适合晚上挂机"],
      hotspots: [
        { x: 12, y: 55, tip: "<strong>主题切换</strong> — 侧栏一键日夜。" },
        { x: 55, y: 40, tip: "<strong>夜间概览</strong> — 深色护眼长刷。" },
      ],
    },
  ];

  /* ---------- Hero carousel ---------- */
  let heroI = 0;
  const rail = document.getElementById("hero-rail");
  const dots = document.getElementById("hero-dots");
  const cap = document.getElementById("hero-cap");
  const frame = document.getElementById("hero-frame");

  const paintHero = (i) => {
    heroI = (i + 6) % 6;
    if (rail) rail.style.transform = `translateX(-${(heroI * 100) / 6}%)`;
    dots?.querySelectorAll("button").forEach((d, idx) => d.classList.toggle("is-on", idx === heroI));
    if (cap) cap.textContent = CAPS[heroI];
  };

  if (dots) {
    for (let i = 0; i < 6; i++) {
      const b = document.createElement("button");
      b.type = "button";
      b.setAttribute("aria-label", CAPS[i]);
      b.addEventListener("click", () => {
        paintHero(i);
        resetHeroAuto();
      });
      dots.appendChild(b);
    }
  }
  document.getElementById("hero-prev")?.addEventListener("click", () => {
    paintHero(heroI - 1);
    resetHeroAuto();
  });
  document.getElementById("hero-next")?.addEventListener("click", () => {
    paintHero(heroI + 1);
    resetHeroAuto();
  });

  /* drag / swipe hero */
  if (frame && rail) {
    let down = false;
    let startX = 0;
    let base = 0;
    const onDown = (x) => {
      down = true;
      startX = x;
      base = heroI;
      frame.style.cursor = "grabbing";
      if (!reduce) frame.style.animationPlayState = "paused";
    };
    const onMove = (x) => {
      if (!down) return;
      const dx = x - startX;
      const pct = (base * 100) / 6 - (dx / frame.clientWidth) * (100 / 6);
      rail.style.transition = "none";
      rail.style.transform = `translateX(-${pct}%)`;
    };
    const onUp = (x) => {
      if (!down) return;
      down = false;
      frame.style.cursor = "";
      if (!reduce) frame.style.animationPlayState = "";
      rail.style.transition = "";
      const dx = x - startX;
      if (dx < -50) paintHero(base + 1);
      else if (dx > 50) paintHero(base - 1);
      else paintHero(base);
      resetHeroAuto();
    };
    frame.addEventListener("pointerdown", (e) => {
      frame.setPointerCapture(e.pointerId);
      onDown(e.clientX);
    });
    frame.addEventListener("pointermove", (e) => onMove(e.clientX));
    frame.addEventListener("pointerup", (e) => onUp(e.clientX));
    frame.addEventListener("pointercancel", (e) => onUp(e.clientX));
  }

  let heroTimer = null;
  const resetHeroAuto = () => {
    clearInterval(heroTimer);
    if (reduce) return;
    heroTimer = setInterval(() => paintHero(heroI + 1), 4200);
  };
  paintHero(0);
  resetHeroAuto();

  /* ---------- Tour ---------- */
  let tourI = 0;
  let autoPlay = !reduce;
  let autoT0 = performance.now();
  const AUTO_MS = 5600;
  const img = document.getElementById("tour-img");
  const title = document.getElementById("tour-title");
  const desc = document.getElementById("tour-desc");
  const points = document.getElementById("tour-points");
  const nEl = document.getElementById("tour-n");
  const urlEl = document.getElementById("tour-url");
  const hots = document.getElementById("tour-hots");
  const tip = document.getElementById("tour-tip");
  const meter = document.getElementById("tour-meter");
  const playBtn = document.getElementById("tour-play");
  const board = document.getElementById("tour-board");
  const shot = document.getElementById("tour-shot");
  const tabs = [...document.querySelectorAll(".tour-tab")];

  const showTip = (html) => {
    if (!tip) return;
    tip.hidden = false;
    tip.innerHTML = html;
  };
  const hideTip = () => {
    if (!tip) return;
    tip.hidden = true;
    tip.innerHTML = "";
  };

  const renderHots = (list) => {
    if (!hots) return;
    hots.innerHTML = "";
    (list || []).forEach((h) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "hot";
      b.style.left = `${h.x}%`;
      b.style.top = `${h.y}%`;
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        showTip(h.tip);
        autoT0 = performance.now();
      });
      b.addEventListener("pointerenter", () => showTip(h.tip));
      hots.appendChild(b);
    });
  };

  const setPlayUi = () => {
    if (playBtn) {
      playBtn.textContent = autoPlay ? "⏸" : "▶";
      playBtn.setAttribute("aria-pressed", autoPlay ? "true" : "false");
      playBtn.title = autoPlay ? "暂停自动播" : "开始自动播";
    }
    board?.classList.toggle("is-paused", !autoPlay);
  };

  const renderTour = (i, { soft = false } = {}) => {
    tourI = (i + TOURS.length) % TOURS.length;
    const t = TOURS[tourI];
    if (title) title.textContent = t.title;
    if (desc) desc.textContent = t.desc;
    if (urlEl) urlEl.textContent = t.url;
    if (nEl) nEl.textContent = `${String(tourI + 1).padStart(2, "0")} / 06`;
    if (points) points.innerHTML = t.points.map((p) => `<li>${p}</li>`).join("");
    hideTip();
    if (img) {
      img.style.animation = "none";
      void img.offsetWidth;
      img.src = t.img;
      img.alt = t.title;
      img.width = TALL.has(tourI) ? 395 : 2552;
      img.height = TALL.has(tourI) ? 714 : 1308;
      img.style.animation = "";
    }
    const body = document.getElementById("shot-body");
    body?.classList.toggle("is-tall", TALL.has(tourI));
    renderHots(TALL.has(tourI) ? [] : t.hotspots);
    tabs.forEach((tab, idx) => tab.classList.toggle("is-on", idx === tourI));
    if (!soft) autoT0 = performance.now();
    paintHero(tourI);
  };

  tabs.forEach((tab) => tab.addEventListener("click", () => renderTour(Number(tab.dataset.tour))));
  document.getElementById("tour-prev")?.addEventListener("click", () => renderTour(tourI - 1));
  document.getElementById("tour-next")?.addEventListener("click", () => renderTour(tourI + 1));
  playBtn?.addEventListener("click", () => {
    autoPlay = !autoPlay;
    autoT0 = performance.now();
    setPlayUi();
  });

  shot?.addEventListener("pointerenter", () => board?.classList.add("is-paused"));
  shot?.addEventListener("pointerleave", () => {
    if (autoPlay) board?.classList.remove("is-paused");
    hideTip();
  });
  shot?.addEventListener("click", (e) => {
    if (!e.target.closest(".hot")) hideTip();
  });

  addEventListener("keydown", (e) => {
    if (["INPUT", "TEXTAREA"].includes(e.target?.tagName)) return;
    if (e.key === "ArrowLeft") renderTour(tourI - 1);
    if (e.key === "ArrowRight") renderTour(tourI + 1);
  });

  const tick = (now) => {
    if (autoPlay && !board?.classList.contains("is-paused") && !reduce) {
      const p = Math.min(1, (now - autoT0) / AUTO_MS);
      if (meter) meter.style.width = `${p * 100}%`;
      if (p >= 1) {
        renderTour(tourI + 1, { soft: true });
        autoT0 = performance.now();
      }
    }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  setPlayUi();

  const jump = (i) => {
    renderTour(Number(i));
    setActiveNav("tour");
    scrollToEl(document.getElementById("tour"));
  };
  document.querySelectorAll("[data-jump]").forEach((el) => {
    el.addEventListener("click", () => jump(el.getAttribute("data-jump")));
  });

  /* ---------- Cursor / glow / magnet ---------- */
  const cursor = document.getElementById("cursor");
  const glow = document.getElementById("glow");
  let x = innerWidth / 2;
  let y = innerHeight / 3;
  let gx = x;
  let gy = y;
  if (!touch && !reduce) {
    addEventListener(
      "pointermove",
      (e) => {
        x = e.clientX;
        y = e.clientY;
        if (cursor) cursor.style.transform = `translate(${x}px, ${y}px) translate(-50%, -50%)`;
      },
      { passive: true }
    );
    const loop = () => {
      gx += (x - gx) * 0.1;
      gy += (y - gy) * 0.1;
      if (glow) glow.style.transform = `translate(${gx}px, ${gy}px) translate(-50%, -50%)`;
      requestAnimationFrame(loop);
    };
    loop();
    document.querySelectorAll("a, button, summary").forEach((el) => {
      el.addEventListener("pointerenter", () => cursor?.classList.add("hot"));
      el.addEventListener("pointerleave", () => cursor?.classList.remove("hot"));
    });
    document.querySelectorAll("[data-magnet]").forEach((el) => {
      if (el.closest(".site-nav")) return;
      el.addEventListener("pointermove", (e) => {
        const r = el.getBoundingClientRect();
        el.style.transform = `translate(${(e.clientX - r.left - r.width / 2) * 0.2}px, ${(e.clientY - r.top - r.height / 2) * 0.24}px)`;
      });
      el.addEventListener("pointerleave", () => {
        el.style.transform = "";
      });
    });
    document.querySelectorAll("[data-tilt]").forEach((card) => {
      card.addEventListener("pointermove", (e) => {
        const r = card.getBoundingClientRect();
        const px = (e.clientX - r.left) / r.width - 0.5;
        const py = (e.clientY - r.top) / r.height - 0.5;
        card.style.transform = `perspective(900px) rotateY(${px * 6}deg) rotateX(${-py * 5}deg) translateY(-6px)`;
      });
      card.addEventListener("pointerleave", () => {
        card.style.transform = "";
      });
    });
  }

  /* ---------- Premium nav + cinematic scroll ---------- */
  const nav = document.getElementById("nav");
  const navLinks = document.querySelector(".nav-links");
  const navIndicator = document.getElementById("nav-indicator");
  const navShell = document.getElementById("nav-shell");
  const navAnchors = [...document.querySelectorAll("[data-nav]")];
  const navSections = [
    { id: "tour", el: document.getElementById("tour") },
    { id: "why", el: document.getElementById("why") },
    { id: "start", el: document.getElementById("start") },
    { id: "faq", el: document.getElementById("faq") },
  ].filter((s) => s.el);

  const sectionLabels = {
    tour: "界面导览",
    why: "能力",
    start: "上手",
    faq: "问答",
    top: "顶部",
  };

  let scrollAnim = null;
  let scrollingNav = false;
  let travelTarget = null;
  let travelLink = null;

  const easeInOutQuart = (t) =>
    t < 0.5 ? 8 * t * t * t * t : 1 - Math.pow(-2 * t + 2, 4) / 2;

  const setScrollY = (y) => {
    const top = Math.max(0, Math.min(y, maxScrollY()));
    document.documentElement.scrollTop = top;
  };

  const moveIndicator = (link) => {
    if (!navIndicator || !navLinks || !link) return;
    navIndicator.style.width = `${link.offsetWidth}px`;
    navIndicator.style.transform = `translateX(${link.offsetLeft}px)`;
    navIndicator.classList.add("is-visible");
  };

  const getNavOffset = () => (nav?.offsetHeight ?? 80) + 24;
  const maxScrollY = () => document.documentElement.scrollHeight - innerHeight;

  const revealSection = (el) => {
    if (!el) return;
    if (el.matches("[data-in]")) el.classList.add("show");
    el.querySelectorAll("[data-in]").forEach((n) => n.classList.add("show"));
  };

  const setTravelUi = (progress) => {
    const p = Math.max(0, Math.min(1, progress));
    if (navProgress) navProgress.style.width = `${p * 100}%`;
  };

  const beginTravel = (label, targetEl) => {
    scrollingNav = true;
    travelTarget = targetEl || null;
    nav?.classList.add("is-traveling");
    navLinks?.querySelectorAll("a").forEach((a) => a.classList.remove("is-heading"));
    travelLink = targetEl?.id ? navLinks?.querySelector(`a[href="#${targetEl.id}"]`) : null;
    travelLink?.classList.add("is-heading");
    setTravelUi(0);
  };

  const endTravel = () => {
    scrollingNav = false;
    nav?.classList.remove("is-traveling");
    travelLink?.classList.remove("is-heading");
    travelLink = null;
    if (navProgress) navProgress.style.width = "0%";
    if (travelTarget) {
      revealSection(travelTarget);
      travelTarget.classList.add("is-arriving");
      setTimeout(() => travelTarget?.classList.remove("is-arriving"), 1000);
      travelTarget = null;
    }
    updateSpy();
  };

  const scrollToY = (targetY, { label, targetEl, onDone, forceSmooth = false } = {}) => {
    const y = Math.max(0, Math.min(targetY, maxScrollY()));
    const finish = () => {
      if (targetEl) revealSection(targetEl);
      onDone?.();
      updateSpy();
    };
    const useAnim = forceSmooth || !reduce;
    if (Math.abs(scrollY - y) < 1) {
      setScrollY(y);
      finish();
      return;
    }
    if (!useAnim) {
      setScrollY(y);
      finish();
      return;
    }
    if (scrollAnim) cancelAnimationFrame(scrollAnim);
    beginTravel(label, targetEl);
    const start = scrollY;
    const delta = y - start;
    const duration = Math.min(3200, Math.max(1600, Math.abs(delta) * 1.05));
    const t0 = performance.now();

    const step = (now) => {
      const p = Math.min(1, (now - t0) / duration);
      const eased = easeInOutQuart(p);
      const current = start + delta * eased;
      setScrollY(current);
      setTravelUi(p);
      if (p < 1) scrollAnim = requestAnimationFrame(step);
      else {
        scrollAnim = null;
        endTravel();
        onDone?.();
      }
    };
    scrollAnim = requestAnimationFrame(step);
  };

  const scrollToEl = (el, meta = {}) => {
    if (!el) return;
    const id = el.id || "top";
    const label = meta.label || sectionLabels[id] || el.getAttribute("data-label") || id;
    const targetY = Math.max(0, Math.min(el.getBoundingClientRect().top + scrollY - getNavOffset(), maxScrollY()));
    const link = id ? navLinks?.querySelector(`a[href="#${id}"]`) : null;
    if (link) moveIndicator(link);
    scrollToY(targetY, {
      label,
      targetEl: el.id ? el : null,
      forceSmooth: true,
      onDone: meta.onDone,
    });
  };

  const setActiveNav = (id) => {
    navAnchors.forEach((a) => {
      const on = a.getAttribute("href") === `#${id}`;
      a.classList.toggle("is-active", on);
      a.setAttribute("aria-current", on ? "true" : "false");
    });
    const link = navLinks?.querySelector(`a[href="#${id}"]`);
    if (link) moveIndicator(link);
  };

  const updateSpy = () => {
    if (scrollingNav) return;
    const max = maxScrollY();
    if (scrollY >= max - 12) {
      setActiveNav("faq");
      return;
    }
    const mark = getNavOffset() + innerHeight * 0.28;
    let current = "";
    for (const { id, el } of navSections) {
      if (el.getBoundingClientRect().top <= mark) current = id;
    }
    if (current) setActiveNav(current);
  };

  if (!touch && !reduce && navLinks) {
    navLinks.querySelectorAll("a").forEach((link) => {
      link.addEventListener("pointerenter", () => {
        link.classList.add("is-hover");
        if (!scrollingNav) moveIndicator(link);
      });
      link.addEventListener("pointerleave", () => {
        link.classList.remove("is-hover");
        if (!scrollingNav) {
          const active = navLinks.querySelector("a.is-active");
          if (active) moveIndicator(active);
        }
      });
    });
  }

  const menuBtn = document.getElementById("menu-btn");
  const sheet = document.getElementById("sheet");

  const setOpen = (open) => {
    nav?.classList.toggle("is-open", open);
    menuBtn?.setAttribute("aria-expanded", open ? "true" : "false");
    if (!sheet) return;
    if (open) {
      sheet.hidden = false;
      requestAnimationFrame(() => {
        sheet.classList.add("is-open");
        requestAnimationFrame(() => sheet.classList.add("is-ready"));
      });
    } else {
      sheet.classList.remove("is-ready", "is-open");
      const hide = () => {
        if (!sheet.classList.contains("is-open")) sheet.hidden = true;
      };
      sheet.addEventListener("transitionend", hide, { once: true });
      setTimeout(hide, 600);
    }
    document.body.style.overflow = open ? "hidden" : "";
  };

  menuBtn?.addEventListener("click", () => setOpen(!nav?.classList.contains("is-open")));
  sheet?.querySelector("[data-close]")?.addEventListener("click", () => setOpen(false));

  document.querySelectorAll('a[href^="#"]').forEach((a) => {
    a.addEventListener("click", (e) => {
      const href = a.getAttribute("href");
      if (!href || href === "#") return;
      const el = document.querySelector(href);
      if (!el) return;
      e.preventDefault();
      a.classList.add("is-pressing");
      setTimeout(() => a.classList.remove("is-pressing"), 220);
      const label = a.getAttribute("data-label") || sectionLabels[el.id] || "";
      if (el.id && navAnchors.some((n) => n.getAttribute("href") === `#${el.id}`)) {
        setActiveNav(el.id);
      }
      scrollToEl(el, {
        label,
        onDone: () => {
          if (nav?.classList.contains("is-open")) setOpen(false);
        },
      });
    });
  });

  const onScroll = () => {
    const y = scrollY;
    nav?.classList.toggle("is-solid", y > 48);
    if (!scrollingNav) updateSpy();
  };
  onScroll();
  addEventListener("scroll", onScroll, { passive: true });
  addEventListener("resize", () => {
    const active = navLinks?.querySelector("a.is-active");
    if (active) moveIndicator(active);
    updateSpy();
  });

  /* reveal */
  const nodes = document.querySelectorAll("[data-in]");
  if (!reduce && "IntersectionObserver" in window) {
    const io = new IntersectionObserver(
      (ents) => {
        ents.forEach((en) => {
          if (!en.isIntersecting) return;
          en.target.classList.add("show");
          io.unobserve(en.target);
        });
      },
      { threshold: 0.14, rootMargin: "0px 0px -5% 0px" }
    );
    nodes.forEach((n) => io.observe(n));
  } else nodes.forEach((n) => n.classList.add("show"));

  /* counters */
  document.querySelectorAll("[data-count]").forEach((el) => {
    const target = Number(el.getAttribute("data-count") || 0);
    const run = () => {
      if (reduce) {
        el.textContent = `${target}+`;
        return;
      }
      const t0 = performance.now();
      const step = (now) => {
        const t = Math.min(1, (now - t0) / 1200);
        el.textContent = `${Math.floor(target * (1 - Math.pow(1 - t, 3)))}+`;
        if (t < 1) requestAnimationFrame(step);
        else el.textContent = `${target}+`;
      };
      requestAnimationFrame(step);
    };
    if ("IntersectionObserver" in window) {
      const io = new IntersectionObserver(
        (ents) => {
          if (!ents[0]?.isIntersecting) return;
          run();
          io.disconnect();
        },
        { threshold: 0.4 }
      );
      io.observe(el);
    } else run();
  });

  /* start steps */
  const startImg = document.getElementById("start-img");
  document.querySelectorAll(".rung").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".rung").forEach((b) => b.classList.toggle("is-on", b === btn));
      if (startImg) {
        startImg.style.animation = "none";
        void startImg.offsetWidth;
        startImg.src = btn.getAttribute("data-img") || startImg.src;
        startImg.style.animation = "";
      }
    });
  });

  const faqs = document.querySelectorAll(".faq details");
  faqs.forEach((d) => {
    d.addEventListener("toggle", () => {
      if (!d.open) return;
      faqs.forEach((o) => {
        if (o !== d) o.open = false;
      });
    });
  });

  matchMedia("(min-width: 900px)").addEventListener?.("change", (e) => {
    if (e.matches) setOpen(false);
  });

  renderTour(0);
})();
