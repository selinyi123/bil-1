(() => {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const touch = window.matchMedia("(pointer: coarse)").matches || "ontouchstart" in window;
  if (touch) document.body.classList.add("touch");

  const TOURS = [
    {
      title: "概览页",
      url: "本地控制台 · 概览",
      img: "./images/overview.png",
      desc: "打开软件后的第一站：账号是否登录、LLM 是否就绪、活动总数 / 未参加 / 已参加一眼看清。下方快捷操作可更新监控、刷新状态、一键更新活动链接。",
      points: [
        "账号卡片：关注、动态、私信、@未读",
        "六宫格统计实时汇总活动库",
        "参与文案：自定义或随机借用评论",
      ],
      hotspots: [
        { x: 22, y: 28, label: "账号区", tip: "<strong>账号卡片</strong> — 登录态、关注数、动态与未读提醒。" },
        { x: 58, y: 42, label: "统计", tip: "<strong>六宫格统计</strong> — 总数 / 未参加 / 已参加等核心数字。" },
        { x: 72, y: 72, label: "快捷操作", tip: "<strong>快捷操作</strong> — 更新监控、刷新状态、一键更新入口。" },
      ],
    },
    {
      title: "活动页",
      url: "本地控制台 · 活动",
      img: "./images/activities.png",
      desc: "所有抽奖活动的工作台。按类型、参加状态、关键词筛选；点「参与」完成互动 / 转发 / 预约，或用顶部「三连参与」一次清多条未参加。",
      points: [
        "三连参与：按筛选自动选最多 3 条",
        "筛选：互动 / 转发 / 预约、未参加 / 已参加",
        "列表展示奖品、热度、开奖时间与操作",
      ],
      hotspots: [
        { x: 18, y: 18, label: "三连", tip: "<strong>三连参与</strong> — 按当前筛选一次处理多条未参加。" },
        { x: 48, y: 30, label: "筛选", tip: "<strong>筛选条</strong> — 类型与状态过滤，快速缩小范围。" },
        { x: 70, y: 58, label: "列表", tip: "<strong>活动列表</strong> — 奖品、热度、开奖时间与单条参与。" },
      ],
    },
    {
      title: "数据源 · UP 合集",
      url: "本地控制台 · 数据源",
      img: "./images/sources.png",
      desc: "内置多个抽奖 UP 合集。优先点「更新此源」做增量同步；新专栏才会拉新链接并入库。少用一键全更，更稳、更不易触发风控。",
      points: [
        "每个合集独立「更新此源」",
        "流程：检查专栏 → 分类 → 详情 → 入库",
        "状态徽章提示本次是否有更新",
      ],
      hotspots: [
        { x: 30, y: 35, label: "合集", tip: "<strong>UP 合集卡片</strong> — 各数据源独立维护。" },
        { x: 78, y: 42, label: "更新此源", tip: "<strong>更新此源</strong> — 推荐的日常增量同步入口。" },
      ],
    },
    {
      title: "数据源 · 监控名单",
      url: "本地控制台 · 监控用户",
      img: "./images/sources-watch.png",
      desc: "第 7 条发现通道：添加常转发抽奖的 UP MID，再「更新监控用户动态」，从他们近期转发里补合集漏抓的活动。",
      points: [
        "名单可增删，支持批量监控",
        "同步窗口与上次链接数一目了然",
        "与 UP 合集双通道互补",
      ],
      hotspots: [
        { x: 40, y: 40, label: "名单", tip: "<strong>监控名单</strong> — 添加常转发抽奖的 UP。" },
        { x: 75, y: 22, label: "更新动态", tip: "<strong>更新监控用户动态</strong> — 从转发补漏活动。" },
      ],
    },
    {
      title: "定时点击监视器",
      url: "定时点击 · Auto Scheduler",
      img: "./images/scheduler.png",
      desc: "嵌入控制台的调度面板：倒计时到点自动点四个按钮。整点刷新批次（一键更新 → 监控动态 → 刷新状态），其余时段可三连参与。撞车即停，不取消正在跑的抽奖任务。",
      points: [
        "下一刻度倒计时实时跳动",
        "可查看调度状态与抽奖任务连通",
        "启动 / 停止调度一键切换",
      ],
      hotspots: [
        { x: 50, y: 35, label: "倒计时", tip: "<strong>倒计时</strong> — 下一刻度自动执行前的等待。" },
        { x: 50, y: 72, label: "启停", tip: "<strong>启动 / 停止</strong> — 一键开关定时点击调度。" },
      ],
    },
    {
      title: "夜间模式",
      url: "本地控制台 · 夜间概览",
      img: "./images/night.png",
      desc: "侧栏一键切到夜间主题：深色背景 + 暖金强调，长时间盯活动列表更护眼。统计、快捷操作、文案设置布局与日间一致。",
      points: [
        "日间 / 夜间即时切换",
        "统计与操作区层次更清晰",
        "适合晚上挂机刷活动",
      ],
      hotspots: [
        { x: 12, y: 55, label: "侧栏主题", tip: "<strong>主题切换</strong> — 侧栏一键日间 / 夜间。" },
        { x: 55, y: 40, label: "夜间概览", tip: "<strong>夜间概览</strong> — 深色背景 + 暖色强调，护眼长刷。" },
      ],
    },
  ];

  const START_IMGS = [
    "./images/overview.png",
    "./images/overview.png",
    "./images/activities.png",
  ];

  let tourIndex = 0;
  let autoPlay = !reduce;
  let autoStart = performance.now();
  const AUTO_MS = 6500;

  const img = document.getElementById("tour-img");
  const title = document.getElementById("tour-title");
  const desc = document.getElementById("tour-desc");
  const points = document.getElementById("tour-points");
  const indexEl = document.getElementById("tour-index");
  const urlEl = document.getElementById("tour-url");
  const hotspotsEl = document.getElementById("tour-hotspots");
  const tipEl = document.getElementById("tour-tip");
  const autoBar = document.getElementById("tour-auto-bar");
  const playBtn = document.getElementById("tour-play");
  const shell = document.getElementById("tour-shell");
  const frame = document.getElementById("tour-frame");
  const themeBtn = document.getElementById("theme-btn");
  const tabs = [...document.querySelectorAll(".tour-tab")];

  const showTip = (html) => {
    if (!tipEl) return;
    tipEl.hidden = false;
    tipEl.innerHTML = html;
  };
  const hideTip = () => {
    if (!tipEl) return;
    tipEl.hidden = true;
    tipEl.innerHTML = "";
  };

  const renderHotspots = (list) => {
    if (!hotspotsEl) return;
    hotspotsEl.innerHTML = "";
    (list || []).forEach((h) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "hotspot";
      btn.style.left = `${h.x}%`;
      btn.style.top = `${h.y}%`;
      btn.setAttribute("aria-label", h.label);
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        showTip(h.tip);
        bumpAuto();
      });
      btn.addEventListener("pointerenter", () => showTip(h.tip));
      hotspotsEl.appendChild(btn);
    });
  };

  const bumpAuto = () => {
    autoStart = performance.now();
  };

  const setPlayUi = () => {
    if (playBtn) {
      playBtn.textContent = autoPlay ? "暂停自动播" : "开始自动播";
      playBtn.setAttribute("aria-pressed", autoPlay ? "true" : "false");
    }
    shell?.classList.toggle("is-paused", !autoPlay);
  };

  const renderTour = (i, { fromAuto = false } = {}) => {
    tourIndex = (i + TOURS.length) % TOURS.length;
    const t = TOURS[tourIndex];
    if (title) title.textContent = t.title;
    if (desc) desc.textContent = t.desc;
    if (urlEl) urlEl.textContent = t.url;
    if (indexEl) indexEl.textContent = `${String(tourIndex + 1).padStart(2, "0")} / 0${TOURS.length}`;
    if (points) points.innerHTML = t.points.map((p) => `<li>${p}</li>`).join("");
    hideTip();
    if (img) {
      img.style.animation = "none";
      void img.offsetWidth;
      img.src = t.img;
      img.alt = t.title;
      img.style.animation = "";
    }
    renderHotspots(t.hotspots);
    tabs.forEach((tab, idx) => {
      const on = idx === tourIndex;
      tab.classList.toggle("is-on", on);
      tab.setAttribute("aria-selected", on ? "true" : "false");
    });
    if (themeBtn) {
      if (tourIndex === 5) themeBtn.setAttribute("data-mode", "night");
      else if (tourIndex === 0) themeBtn.removeAttribute("data-mode");
    }
    if (!fromAuto) bumpAuto();
  };

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => renderTour(Number(tab.dataset.tour)));
  });
  document.getElementById("tour-prev")?.addEventListener("click", () => renderTour(tourIndex - 1));
  document.getElementById("tour-next")?.addEventListener("click", () => renderTour(tourIndex + 1));
  playBtn?.addEventListener("click", () => {
    autoPlay = !autoPlay;
    bumpAuto();
    setPlayUi();
  });

  frame?.addEventListener("pointerenter", () => {
    if (!touch) shell?.classList.add("is-paused");
  });
  frame?.addEventListener("pointerleave", () => {
    if (autoPlay) shell?.classList.remove("is-paused");
    hideTip();
  });
  frame?.addEventListener("click", (e) => {
    if (e.target.closest(".hotspot")) return;
    hideTip();
  });

  window.addEventListener("keydown", (e) => {
    if (e.target && ["INPUT", "TEXTAREA"].includes(e.target.tagName)) return;
    if (e.key === "ArrowLeft") renderTour(tourIndex - 1);
    if (e.key === "ArrowRight") renderTour(tourIndex + 1);
    if (e.key === " ") {
      const tourVisible = document.getElementById("tour")?.getBoundingClientRect().top < innerHeight;
      if (tourVisible) {
        e.preventDefault();
        autoPlay = !autoPlay;
        bumpAuto();
        setPlayUi();
      }
    }
  });

  const tickAuto = (now) => {
    if (autoPlay && !shell?.classList.contains("is-paused") && !reduce) {
      const elapsed = now - autoStart;
      const p = Math.min(1, elapsed / AUTO_MS);
      if (autoBar) autoBar.style.width = `${p * 100}%`;
      if (p >= 1) {
        renderTour(tourIndex + 1, { fromAuto: true });
        bumpAuto();
      }
    } else if (autoBar && !autoPlay) {
      /* freeze */
    } else if (autoBar && shell?.classList.contains("is-paused")) {
      /* freeze while hovering */
    }
    requestAnimationFrame(tickAuto);
  };
  requestAnimationFrame(tickAuto);
  setPlayUi();

  themeBtn?.addEventListener("click", () => {
    const night = themeBtn.getAttribute("data-mode") === "night";
    if (night) {
      themeBtn.removeAttribute("data-mode");
      renderTour(0);
    } else {
      themeBtn.setAttribute("data-mode", "night");
      renderTour(5);
    }
    document.getElementById("tour")?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  });

  const jumpToTour = (i) => {
    renderTour(Number(i));
    document.getElementById("tour")?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  };
  document.querySelectorAll("[data-jump]").forEach((el) => {
    el.addEventListener("click", () => jumpToTour(el.getAttribute("data-jump")));
  });

  const stack = document.getElementById("hero-stack");
  document.getElementById("hero-swap")?.addEventListener("click", () => {
    stack?.classList.toggle("swapped");
  });

  /* Hero 3D tilt on bezel */
  const bezel = document.querySelector(".hero-bezel");
  if (bezel && !touch && !reduce) {
    bezel.addEventListener("pointermove", (e) => {
      const r = bezel.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - 0.5;
      const py = (e.clientY - r.top) / r.height - 0.5;
      bezel.style.transform = `perspective(1200px) rotateY(${px * 7}deg) rotateX(${-py * 6}deg)`;
    });
    bezel.addEventListener("pointerleave", () => {
      bezel.style.transform = "";
    });
  }

  /* Cursor + glow */
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
      gx += (x - gx) * 0.12;
      gy += (y - gy) * 0.12;
      if (glow) glow.style.transform = `translate(${gx}px, ${gy}px) translate(-50%, -50%)`;
      requestAnimationFrame(loop);
    };
    loop();
    document.querySelectorAll("a, button, summary").forEach((el) => {
      el.addEventListener("pointerenter", () => cursor?.classList.add("hot"));
      el.addEventListener("pointerleave", () => cursor?.classList.remove("hot"));
    });
  }

  if (!touch && !reduce) {
    document.querySelectorAll("[data-magnet]").forEach((el) => {
      el.addEventListener("pointermove", (e) => {
        const r = el.getBoundingClientRect();
        el.style.transform = `translate(${(e.clientX - r.left - r.width / 2) * 0.18}px, ${(e.clientY - r.top - r.height / 2) * 0.22}px)`;
      });
      el.addEventListener("pointerleave", () => {
        el.style.transform = "";
      });
    });
  }

  const progress = document.getElementById("progress");
  const nav = document.getElementById("nav");
  const onScroll = () => {
    const max = document.documentElement.scrollHeight - innerHeight;
    if (progress) progress.style.width = `${max > 0 ? (scrollY / max) * 100 : 0}%`;
    nav?.classList.toggle("solid", scrollY > 36);
  };
  onScroll();
  addEventListener("scroll", onScroll, { passive: true });

  const menuBtn = document.getElementById("menu-btn");
  const sheet = document.getElementById("sheet");
  const setOpen = (open) => {
    nav?.classList.toggle("open", open);
    menuBtn?.setAttribute("aria-expanded", open ? "true" : "false");
    if (sheet) sheet.hidden = !open;
    document.body.style.overflow = open ? "hidden" : "";
  };
  menuBtn?.addEventListener("click", () => setOpen(!nav?.classList.contains("open")));
  sheet?.querySelectorAll("[data-x]").forEach((a) => a.addEventListener("click", () => setOpen(false)));

  const nodes = document.querySelectorAll("[data-in]");
  if (!reduce && "IntersectionObserver" in window) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((en) => {
          if (!en.isIntersecting) return;
          en.target.classList.add("show");
          io.unobserve(en.target);
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -6% 0px" }
    );
    nodes.forEach((n) => io.observe(n));
  } else {
    nodes.forEach((n) => n.classList.add("show"));
  }

  const counters = document.querySelectorAll("[data-count]");
  const animateCount = (el) => {
    const target = Number(el.getAttribute("data-count") || 0);
    if (reduce) {
      el.textContent = `${target}+`;
      return;
    }
    const start = performance.now();
    const dur = 1300;
    const tick = (now) => {
      const t = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - t, 3);
      el.textContent = `${Math.floor(target * eased)}+`;
      if (t < 1) requestAnimationFrame(tick);
      else el.textContent = `${target}+`;
    };
    requestAnimationFrame(tick);
  };
  if ("IntersectionObserver" in window) {
    const cio = new IntersectionObserver(
      (entries) => {
        entries.forEach((en) => {
          if (!en.isIntersecting) return;
          animateCount(en.target);
          cio.unobserve(en.target);
        });
      },
      { threshold: 0.5 }
    );
    counters.forEach((c) => cio.observe(c));
  }

  const startImg = document.getElementById("start-img");
  document.querySelectorAll(".step").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".step").forEach((b) => b.classList.toggle("is-on", b === btn));
      const idx = Number(btn.getAttribute("data-step") || 0);
      if (startImg) {
        startImg.style.animation = "none";
        void startImg.offsetWidth;
        startImg.src = START_IMGS[idx] || START_IMGS[0];
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

  if (!touch && !reduce) {
    document.querySelectorAll("[data-tilt]").forEach((card) => {
      card.addEventListener("pointermove", (e) => {
        const r = card.getBoundingClientRect();
        const px = (e.clientX - r.left) / r.width - 0.5;
        const py = (e.clientY - r.top) / r.height - 0.5;
        card.style.transform = `perspective(900px) rotateY(${px * 5}deg) rotateX(${-py * 5}deg) translateY(-4px)`;
      });
      card.addEventListener("pointerleave", () => {
        card.style.transform = "";
      });
    });
  }

  matchMedia("(min-width: 900px)").addEventListener?.("change", (e) => {
    if (e.matches) setOpen(false);
  });

  renderTour(0);
})();
