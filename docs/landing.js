(() => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const touch = matchMedia("(pointer: coarse)").matches || "ontouchstart" in window;
  if (touch) document.body.classList.add("touch");

  const HERO_N = 4;
  const CAPS = [
    "概览页",
    "数据源",
    "活动页",
    "参加活动",
  ];
  const SUBS = [
    "账号与统计",
    "监控用户动态",
    "筛选与参与",
    "三连与定时",
  ];

  /* ---------- Hero carousel ---------- */
  /* Right → left loop: next slide enters from the right */
  let heroI = 0;
  let railPos = 0;
  let heroBusy = false;
  let heroJump = null;
  let heroResizePending = false;
  const rail = document.getElementById("hero-rail");
  const frame = document.getElementById("hero-frame");
  const heroEl = document.getElementById("top");
  const heroStage = document.getElementById("hero-stage");
  const navBrand = document.getElementById("nav-brand");
  const scrollCue = document.getElementById("scroll-cue");
  const dockTabs = [...document.querySelectorAll(".hero-dock-tab")];
  const captionPanes = [...document.querySelectorAll(".hero-caption-pane")];
  let captionPane = 0;
  const HERO_TOTAL = HERO_N + 1;
  const HERO_DUR = 780;
  const HERO_EASE = "cubic-bezier(0.65, 0, 0.35, 1)";
  /* Product carousel motion is essential feedback — keep the slide even if OS asks to reduce decorative motion */
  const heroSlideMotion = true;

  if (rail) {
    const first = rail.querySelector(".hero-slide");
    if (first) {
      const clone = first.cloneNode(true);
      clone.classList.remove("is-on");
      clone.setAttribute("aria-hidden", "true");
      rail.appendChild(clone);
    }
  }

  const slideWidth = () => (frame ? frame.getBoundingClientRect().width : 0);

  const layoutHeroRail = () => {
    if (!rail || !frame) return;
    const w = slideWidth();
    if (!w) return;
    rail.querySelectorAll(".hero-slide").forEach((slide) => {
      slide.style.flex = `0 0 ${w}px`;
      slide.style.width = `${w}px`;
      slide.style.minWidth = `${w}px`;
    });
    rail.style.width = `${w * HERO_TOTAL}px`;
  };

  const setRailPos = (pos, { animate = false } = {}) => {
    if (!rail) return;
    const w = slideWidth();
    rail.style.transition = animate && heroSlideMotion
      ? `transform ${HERO_DUR}ms ${HERO_EASE}`
      : "none";
    rail.style.transform = `translate3d(-${pos * w}px, 0, 0)`;
  };

  /* If a viewport resize lands while a slide transition is mid-flight, the
     resize handler must NOT force the rail back to the old railPos (that
     would fight the in-flight CSS transition and leave the transform out of
     sync with heroI/railPos until the next auto-advance). Instead it defers
     the resync until the current transition finishes. */
  const finishHeroBusy = () => {
    if (!heroResizePending) return;
    heroResizePending = false;
    layoutHeroRail();
    setRailPos(railPos, { animate: false });
  };

  const syncHeroDock = (i) => {
    dockTabs.forEach((t, idx) => {
      const on = idx === i;
      t.classList.toggle("is-on", on);
      t.setAttribute("aria-selected", on ? "true" : "false");
    });
  };

  const bumpHeroProgress = () => {
    dockTabs.forEach((t) => {
      const m = t.querySelector(".hero-dock-meter");
      if (!m) return;
      m.style.animation = "none";
      m.style.transform = "scaleX(0)";
    });
    if (reduce) return;
    const meter = dockTabs[heroI]?.querySelector(".hero-dock-meter");
    if (!meter) return;
    void meter.offsetWidth;
    meter.style.transform = "";
    meter.style.animation = "";
  };

  let capToken = 0;
  const setHeroCap = (text, subText, { initial = false, dir = 1 } = {}) => {
    if (!captionPanes.length) return;
    const fill = (pane, titleText, subTextVal) => {
      const title = pane.querySelector(".hero-cap-t");
      const subEl = pane.querySelector(".hero-cap-s");
      if (title) title.textContent = titleText;
      if (subEl) subEl.textContent = subTextVal;
    };
    if (initial) {
      fill(captionPanes[0], text, subText);
      captionPanes[0].className = "hero-caption-pane is-show";
      captionPanes[0].removeAttribute("aria-hidden");
      if (captionPanes[1]) {
        captionPanes[1].className = "hero-caption-pane is-prep-right";
        captionPanes[1].setAttribute("aria-hidden", "true");
      }
      captionPane = 0;
      return;
    }
    const token = ++capToken;
    const cur = captionPanes[captionPane];
    const nextIdx = 1 - captionPane;
    const next = captionPanes[nextIdx];
    if (!cur || !next) return;
    fill(next, text, subText);
    next.className = dir > 0 ? "hero-caption-pane is-prep-right" : "hero-caption-pane is-prep-left";
    next.setAttribute("aria-hidden", "true");
    void next.offsetWidth;
    requestAnimationFrame(() => {
      if (token !== capToken) return;
      cur.className = dir > 0 ? "hero-caption-pane is-exit-left" : "hero-caption-pane is-exit-right";
      cur.setAttribute("aria-hidden", "true");
      next.className = "hero-caption-pane is-show";
      next.removeAttribute("aria-hidden");
      captionPane = nextIdx;
      setTimeout(() => {
        if (token !== capToken) return;
        cur.className = dir > 0 ? "hero-caption-pane is-prep-right" : "hero-caption-pane is-prep-left";
      }, HERO_DUR + 40);
    });
  };

  const markSlides = () => {
    if (!rail) return;
    rail.querySelectorAll(".hero-slide").forEach((slide, idx) => {
      slide.classList.toggle("is-on", idx === heroI || (heroI === 0 && idx === HERO_N));
    });
  };

  const commitHero = ({ initial = false, dir = 1, skipCap = false } = {}) => {
    markSlides();
    syncHeroDock(heroI);
    if (!skipCap) setHeroCap(CAPS[heroI], SUBS[heroI], { initial, dir });
    bumpHeroProgress();
  };

  const waitRail = () => new Promise((resolve) => {
    if (!rail || !heroSlideMotion) {
      resolve();
      return;
    }
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      rail.removeEventListener("transitionend", onEnd);
      resolve();
    };
    const onEnd = (e) => {
      if (e.propertyName === "transform") finish();
    };
    rail.addEventListener("transitionend", onEnd);
    setTimeout(finish, HERO_DUR + 80);
  });

  const goHeroForward = async (steps = 1) => {
    if (!rail || !frame || heroBusy || steps <= 0) return;
    heroBusy = true;
    layoutHeroRail();
    const from = railPos;
    const target = from + steps;
    const firstLeg = Math.min(target, HERO_N);
    const nextLogical = (heroI + steps) % HERO_N;

    /* Caption slides with the rail: exit left, enter from right */
    setHeroCap(CAPS[nextLogical], SUBS[nextLogical], { dir: 1 });
    setRailPos(firstLeg, { animate: true });
    await waitRail();

    if (firstLeg === HERO_N) {
      setRailPos(0, { animate: false });
      const remain = target - HERO_N;
      if (remain > 0) {
        void rail.offsetWidth;
        setRailPos(remain, { animate: true });
        await waitRail();
        heroI = remain % HERO_N;
        railPos = remain % HERO_N;
      } else {
        heroI = 0;
        railPos = 0;
      }
    } else {
      heroI = firstLeg % HERO_N;
      railPos = firstLeg;
    }
    heroBusy = false;
    finishHeroBusy();
    commitHero({ dir: 1, skipCap: true });
  };

  const goHeroBack = async () => {
    if (!rail || !frame || heroBusy) return;
    heroBusy = true;
    layoutHeroRail();
    const nextLogical = (heroI - 1 + HERO_N) % HERO_N;
    setHeroCap(CAPS[nextLogical], SUBS[nextLogical], { dir: -1 });
    if (railPos === 0) {
      setRailPos(HERO_N, { animate: false });
      void rail.offsetWidth;
      setRailPos(HERO_N - 1, { animate: true });
      await waitRail();
      heroI = HERO_N - 1;
      railPos = HERO_N - 1;
    } else {
      const to = railPos - 1;
      setRailPos(to, { animate: true });
      await waitRail();
      heroI = to;
      railPos = to;
    }
    heroBusy = false;
    finishHeroBusy();
    commitHero({ dir: -1, skipCap: true });
  };

  const goHeroTo = (i) => {
    const next = ((Number(i) % HERO_N) + HERO_N) % HERO_N;
    if (next === heroI || heroBusy) return;
    const steps = (next - heroI + HERO_N) % HERO_N;
    goHeroForward(steps);
  };

  const paintHero = (i, { initial = false } = {}) => {
    if (initial) {
      heroI = ((i % HERO_N) + HERO_N) % HERO_N;
      railPos = heroI;
      layoutHeroRail();
      setRailPos(railPos, { animate: false });
      commitHero({ initial: true });
      return;
    }
    const next = ((i % HERO_N) + HERO_N) % HERO_N;
    const forward = (next - heroI + HERO_N) % HERO_N;
    const backward = (heroI - next + HERO_N) % HERO_N;
    if (forward === 0) return;
    if (backward === 1 && forward > 1) goHeroBack();
    else goHeroForward(forward);
  };

  dockTabs.forEach((t) => {
    t.addEventListener("click", () => {
      goHeroTo(Number(t.dataset.hero));
      resetHeroAuto();
    });
  });

  const heroPrev = document.getElementById("hero-prev");
  const heroNext = document.getElementById("hero-next");
  heroPrev?.addEventListener("click", (e) => {
    e.stopPropagation();
    goHeroBack();
    resetHeroAuto();
  });
  heroNext?.addEventListener("click", (e) => {
    e.stopPropagation();
    goHeroForward(1);
    resetHeroAuto();
  });

  let heroDidDrag = false;
  if (frame && rail) {
    let down = false;
    let startX = 0;
    let dragFrom = 0;
    let dragPos = 0;
    const onDown = (x) => {
      if (heroBusy) return;
      down = true;
      heroDidDrag = false;
      startX = x;
      dragFrom = railPos;
      dragPos = railPos;
      layoutHeroRail();
      frame.style.cursor = "grabbing";
    };
    const onMove = (x) => {
      if (!down || heroBusy) return;
      const w = slideWidth() || 1;
      const dx = x - startX;
      if (Math.abs(dx) > 8) heroDidDrag = true;
      dragPos = dragFrom - dx / w;
      setRailPos(dragPos, { animate: false });
    };
    const onUp = async (x) => {
      if (!down) return;
      down = false;
      frame.style.cursor = "grab";
      const dx = x - startX;
      if (dx < -50) {
        heroBusy = true;
        const to = Math.min(dragFrom + 1, HERO_N);
        const nextLogical = to >= HERO_N ? 0 : to;
        setHeroCap(CAPS[nextLogical], SUBS[nextLogical], { dir: 1 });
        setRailPos(to, { animate: true });
        await waitRail();
        if (to >= HERO_N) {
          setRailPos(0, { animate: false });
          heroI = 0;
          railPos = 0;
        } else {
          heroI = to;
          railPos = to;
        }
        heroBusy = false;
        finishHeroBusy();
        commitHero({ dir: 1, skipCap: true });
        resetHeroAuto();
      } else if (dx > 50) {
        heroBusy = true;
        const nextLogical = dragFrom === 0 ? HERO_N - 1 : dragFrom - 1;
        setHeroCap(CAPS[nextLogical], SUBS[nextLogical], { dir: -1 });
        if (dragFrom === 0) {
          setRailPos(HERO_N, { animate: false });
          void rail.offsetWidth;
          setRailPos(HERO_N - 1, { animate: true });
          await waitRail();
          heroI = HERO_N - 1;
          railPos = HERO_N - 1;
        } else {
          setRailPos(dragFrom - 1, { animate: true });
          await waitRail();
          heroI = dragFrom - 1;
          railPos = dragFrom - 1;
        }
        heroBusy = false;
        finishHeroBusy();
        commitHero({ dir: -1, skipCap: true });
        resetHeroAuto();
      } else if (heroDidDrag) {
        setRailPos(dragFrom, { animate: true });
        await waitRail();
        railPos = dragFrom;
        resetHeroAuto();
      } else {
        setRailPos(dragFrom, { animate: false });
        heroJump?.(heroI);
      }
    };
    frame.addEventListener("pointerdown", (e) => {
      if (e.button != null && e.button !== 0) return;
      frame.setPointerCapture(e.pointerId);
      onDown(e.clientX);
    });
    frame.addEventListener("pointermove", (e) => onMove(e.clientX));
    frame.addEventListener("pointerup", (e) => onUp(e.clientX));
    frame.addEventListener("pointercancel", (e) => onUp(e.clientX));
    frame.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        heroJump?.(heroI);
      }
    });
  }

  let heroTimer = null;
  let heroPaused = false;
  const HERO_MS = 3600;
  const resetHeroAuto = () => {
    clearInterval(heroTimer);
    heroTimer = null;
    if (heroPaused) return;
    bumpHeroProgress();
    heroTimer = setInterval(() => {
      if (!heroBusy && !heroPaused) goHeroForward(1);
    }, HERO_MS);
  };

  if (frame) {
    frame.addEventListener("pointerdown", () => {
      heroPaused = true;
      heroStage?.classList.add("is-paused");
      clearInterval(heroTimer);
    });
    frame.addEventListener("pointerup", () => {
      heroPaused = false;
      heroStage?.classList.remove("is-paused");
      resetHeroAuto();
    });
    frame.addEventListener("pointercancel", () => {
      heroPaused = false;
      heroStage?.classList.remove("is-paused");
      resetHeroAuto();
    });
  }

  addEventListener("resize", () => {
    if (heroBusy) {
      /* A transition is animating right now — resizing the slide boxes is
         still safe (keeps the correct aspect ratio mid-flight), but jumping
         the transform to `railPos` (the PRE-transition index) would yank the
         rail backwards and desync it from the transition already in flight.
         Defer the position resync until the transition's own completion
         handler (finishHeroBusy) runs. */
      layoutHeroRail();
      heroResizePending = true;
      return;
    }
    layoutHeroRail();
    setRailPos(railPos, { animate: false });
  });

  paintHero(0, { initial: true });
  requestAnimationFrame(() => {
    layoutHeroRail();
    setRailPos(railPos, { animate: false });
    resetHeroAuto();
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      clearInterval(heroTimer);
      heroTimer = null;
    } else if (!heroPaused) {
      resetHeroAuto();
    }
  });

  /* hero scroll parallax + cue */
  const updateHeroParallax = () => {
    if (!heroEl) return;
    const y = Math.max(0, scrollY);
    const range = Math.max(240, heroEl.offsetHeight * 0.55);
    const p = reduce ? 0 : Math.min(1, y / range);
    heroEl.style.setProperty("--hero-p", p.toFixed(3));
    if (scrollCue) scrollCue.classList.toggle("is-gone", y > 48);
  };
  updateHeroParallax();
  addEventListener("scroll", updateHeroParallax, { passive: true });

  /* ---------- Tour · editorial copy + soft scene flip ---------- */
  const TOUR_SCENES = [
    {
      num: 'I',
      label: '概览',
      caption: '统计与快捷操作',
      title: '打开就看清全局',
      desc: '登录态、活动统计与快捷操作同屏铺开，你先确认账号是否就绪，再决定今天更新监控、刷新状态，还是走进活动列表',
    },
    {
      num: 'II',
      label: '数据源',
      caption: '监控名单与动态窗口',
      title: '把漏网的动态补回来',
      desc: '把常转发抽奖的 UP 放进监控名单，Binggo 按时间窗口增量拉取动态，把合集漏掉的新活动一点点补进本地库',
    },
    {
      num: 'III',
      label: '活动',
      caption: '筛选后单条或三连',
      title: '筛好再点一次清光',
      desc: '按类型、状态与关键词收窄列表后，你可以单条参与，也可以用三连一次带走最前面几条尚未参加的活动',
    },
    {
      num: 'IV',
      label: '参加活动',
      caption: '进度、定时与日志同屏',
      title: '参加过程随时看得见',
      desc: '三连并行进度、定时点击与任务日志落在同一屏，当前跑到哪一步、卡在哪一条，不用再猜有没有真的点下去',
    },
  ];

  const tourStepDir = (from, to, n) => {
    if (from === to) return 1;
    const d = (to - from + n) % n;
    return d <= n / 2 ? 1 : -1;
  };

  let tourI = 0;
  let tourBusy = false;
  let tourTimer = 0;
  const tourCopy = document.getElementById('tour-copy');
  const tourTitle = document.getElementById('tour-title');
  const tourDesc = document.getElementById('tour-desc');
  const tourNum = document.getElementById('tour-num');
  const tourViewport = document.getElementById('tour-viewport');
  const tourStage = document.getElementById('tour-stage');
  const tourDevice = document.getElementById('tour-device');
  const tourFrameLabel = document.getElementById('tour-frame-label');
  const tourFrameTitle = document.getElementById('tour-frame-title');
  const tourFrameSub = document.getElementById('tour-frame-sub');
  const tourDeviceMeter = document.getElementById('tour-device-meter');
  const tourSlides = [...document.querySelectorAll('[data-tour-slide]')];
  const tourTabs = [...document.querySelectorAll('[data-tour-scene]')];
  const TOUR_N = TOUR_SCENES.length;
  const tourSceneMotion = true;
  const TOUR_SCENE_MS = 740;
  const TOUR_SCENE_EASE = 'cubic-bezier(0.45, 0, 0.2, 1)';
  /* Revolver: pivot right; firing at 180°. Cylinder spins one way — every chamber moves the same angular direction. */
  const TOUR_ARC_RADIUS = 14;
  const TOUR_ARC_SWEEP = 0.52;
  const TOUR_ARC_REST = 180;
  const TOUR_ARC_STEPS = 12;

  const tourArcPose = (deg) => {
    const rad = (deg * Math.PI) / 180;
    return {
      dx: TOUR_ARC_RADIUS * (Math.cos(rad) + 1),
      dy: TOUR_ARC_RADIUS * Math.sin(rad),
    };
  };

  const tourFadeMix = (t, mode) => {
    const s = t * t * (3 - 2 * t);
    if (mode === 'out') return 1 - s;
    if (mode === 'in') return s;
    return 1;
  };

  const tourCylinderKf = (fromDeg, toDeg, fadeMode) => {
    const kf = [];
    for (let i = 0; i <= TOUR_ARC_STEPS; i++) {
      const t = i / TOUR_ARC_STEPS;
      const theta = fromDeg + (toDeg - fromDeg) * t;
      const { dx, dy } = tourArcPose(theta);
      kf.push({
        offset: t,
        opacity: tourFadeMix(t, fadeMode),
        transform: `translate(${dx.toFixed(2)}%, ${dy.toFixed(2)}%)`,
      });
    }
    return kf;
  };
  const TOUR_AUTO_MS = reduce ? 0 : 7200;
  if (tourStage && TOUR_AUTO_MS) {
    tourStage.style.setProperty('--tour-auto-ms', `${TOUR_AUTO_MS}ms`);
  }
  if (tourViewport) {
    tourViewport.style.removeProperty('--tour-slide-bias-x');
  }

  const clearTourSlideInner = (slide) => {
    const inner = slide?.querySelector('.tour-slide-inner');
    if (!inner) return;
    inner.getAnimations().forEach((a) => a.cancel());
    inner.style.removeProperty('transform');
    inner.style.removeProperty('filter');
    inner.style.removeProperty('opacity');
    inner.style.removeProperty('box-shadow');
  };

  const syncTourSlides = (i, { fromMotion = false } = {}) => {
    tourSlides.forEach((slide, idx) => {
      const inner = slide?.querySelector('.tour-slide-inner');
      if (inner) inner.getAnimations().forEach((a) => a.cancel());
      clearTourSlideInner(slide);
      const on = idx === i;
      slide.classList.toggle('is-active', on);
      slide.classList.remove('is-exit', 'is-enter', 'is-ahead', 'is-behind');
      slide.style.removeProperty('opacity');
      slide.style.removeProperty('z-index');
      slide.style.removeProperty('visibility');
      if (inner) {
        if (on) {
          inner.style.removeProperty('transform');
          inner.style.opacity = '1';
        } else {
          inner.style.removeProperty('transform');
          inner.style.removeProperty('opacity');
        }
      }
    });
    const settleAnimState = () => {
      tourViewport?.classList.remove('is-animating');
      tourStage?.classList.remove('is-focus');
    };
    if (fromMotion) {
      requestAnimationFrame(() => requestAnimationFrame(settleAnimState));
    } else {
      settleAnimState();
    }
  };

  const playTourScene = (prev, next, dir) => {
    const outgoing = tourSlides[prev];
    const incoming = tourSlides[next];
    const outInner = outgoing?.querySelector('.tour-slide-inner');
    const inInner = incoming?.querySelector('.tour-slide-inner');
    if (!outgoing || !incoming || !outInner || !inInner) {
      return Promise.resolve();
    }

    const ahead = dir > 0;
    const chamberDeg = (360 / TOUR_N) * TOUR_ARC_SWEEP;
    let outFrom;
    let outTo;
    let inFrom;
    let inTo;
    if (ahead) {
      outFrom = TOUR_ARC_REST;
      outTo = TOUR_ARC_REST + chamberDeg;
      inFrom = TOUR_ARC_REST - chamberDeg;
      inTo = TOUR_ARC_REST;
    } else {
      outFrom = TOUR_ARC_REST;
      outTo = TOUR_ARC_REST - chamberDeg;
      inFrom = TOUR_ARC_REST + chamberDeg;
      inTo = TOUR_ARC_REST;
    }
    const outKf = tourCylinderKf(outFrom, outTo, 'out');
    const inKf = tourCylinderKf(inFrom, inTo, 'in');

    tourSlides.forEach((slide, idx) => {
      slide.classList.remove('is-exit', 'is-enter', 'is-ahead', 'is-behind');
      if (idx !== prev && idx !== next) clearTourSlideInner(slide);
      const live = idx === prev || idx === next;
      slide.style.opacity = live ? '1' : '0';
      slide.style.visibility = live ? 'visible' : 'hidden';
      slide.style.zIndex = idx === next ? '4' : idx === prev ? '2' : '1';
      slide.classList.toggle('is-active', idx === prev);
    });

    outgoing.classList.add('is-exit', ahead ? 'is-ahead' : 'is-behind');
    incoming.classList.add('is-enter', ahead ? 'is-ahead' : 'is-behind');
    outInner.getAnimations().forEach((a) => a.cancel());
    inInner.getAnimations().forEach((a) => a.cancel());

    tourViewport?.classList.add('is-animating');
    tourStage?.classList.add('is-focus');

    const opts = {
      duration: TOUR_SCENE_MS,
      easing: TOUR_SCENE_EASE,
      fill: 'forwards',
    };
    return new Promise((resolve) => {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          const outAnim = outInner.animate(outKf, opts);
          const inAnim = inInner.animate(inKf, opts);
          outAnim.addEventListener('finish', () => {
            outgoing.style.visibility = 'hidden';
            outgoing.style.opacity = '0';
          });
          Promise.all([outAnim.finished, inAnim.finished]).catch(() => {}).then(resolve);
        });
      });
    });
  };

  const setTourFrame = (s, { animate = false } = {}) => {
    const apply = () => {
      if (tourFrameTitle) tourFrameTitle.textContent = s.label;
      if (tourFrameSub) tourFrameSub.textContent = s.caption;
    };
    if (!animate || reduce || !tourFrameLabel) {
      apply();
      tourFrameLabel?.classList.remove('is-swapping');
      return;
    }
    tourFrameLabel.classList.add('is-swapping');
    window.setTimeout(() => {
      apply();
      tourFrameLabel.classList.remove('is-swapping');
    }, 180);
  };

  const setTourCopy = (i, { animate = false } = {}) => {
    const s = TOUR_SCENES[i];
    const apply = () => {
      if (tourNum) tourNum.textContent = s.num;
      if (tourTitle) tourTitle.textContent = s.title;
      if (tourDesc) tourDesc.textContent = s.desc;
    };
    tourTabs.forEach((tab, idx) => {
      const on = idx === i;
      tab.classList.toggle('is-on', on);
      tab.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    if (!animate || reduce || !tourCopy) {
      apply();
      setTourFrame(s, { animate: false });
      tourCopy?.classList.remove('is-leaving', 'is-entering');
      return;
    }
    tourCopy.classList.remove('is-entering');
    tourCopy.classList.add('is-leaving');
    window.setTimeout(() => {
      apply();
      setTourFrame(s, { animate: true });
      tourCopy.classList.remove('is-leaving');
      void tourCopy.offsetWidth;
      tourCopy.classList.add('is-entering');
    }, 220);
  };

  const stopTourAuto = () => {
    if (tourTimer) {
      clearTimeout(tourTimer);
      tourTimer = 0;
    }
    tourTabs.forEach((tab) => tab.classList.remove('is-timing'));
    tourStage?.classList.remove('is-cycling');
    if (tourDeviceMeter) {
      tourDeviceMeter.style.animation = 'none';
    }
  };

  const armTourAuto = () => {
    stopTourAuto();
    if (!TOUR_AUTO_MS) return;
    const on = tourTabs[tourI];
    on?.classList.add('is-timing');
    tourStage?.classList.add('is-cycling');
    if (tourDeviceMeter) {
      tourDeviceMeter.style.animation = 'none';
      void tourDeviceMeter.offsetWidth;
      tourDeviceMeter.style.animation = '';
    }
    tourTimer = window.setTimeout(() => {
      renderTourScene(tourI + 1);
    }, TOUR_AUTO_MS);
  };

  const renderTourScene = async (i, { animate = true, animateCopy = animate } = {}) => {
    const next = (i + TOUR_N) % TOUR_N;
    if (next === tourI && animate) {
      armTourAuto();
      return;
    }
    if (tourBusy) return;

    const prev = tourI;
    const dir = tourStepDir(prev, next, TOUR_N);
    if (tourViewport) tourViewport.dataset.dir = String(dir);

    setTourCopy(next, { animate: animateCopy });
    setTourFrame(TOUR_SCENES[next], { animate: animateCopy && !reduce });

    const useMotion = animate && tourSceneMotion && prev !== next && tourSlides.length > 0;
    if (!useMotion) {
      tourI = next;
      syncTourSlides(next);
      armTourAuto();
      return;
    }

    tourBusy = true;
    stopTourAuto();
    await playTourScene(prev, next, dir);
    tourI = next;
    syncTourSlides(next, { fromMotion: true });
    tourBusy = false;
    armTourAuto();
  };

  tourTabs.forEach((tab) => {
    tab.addEventListener('click', () => renderTourScene(Number(tab.dataset.tourScene), { animateCopy: false }));
  });

  const tourRail = document.querySelector('.tour-rail');
  if (tourRail) {
    const setTourRailHover = (tab) => {
      tourTabs.forEach((el) => el.classList.toggle('is-rail-hover', el === tab));
    };
    tourTabs.forEach((tab) => {
      tab.addEventListener('mouseenter', () => setTourRailHover(tab));
      tab.addEventListener('focus', () => setTourRailHover(tab));
    });
    tourRail.addEventListener('mouseleave', () => {
      tourTabs.forEach((el) => el.classList.remove('is-rail-hover'));
    });
  }

  const tourSection = document.getElementById('tour');
  if (tourSection && TOUR_AUTO_MS) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) armTourAuto();
        else stopTourAuto();
      });
    }, { threshold: 0.35 });
    io.observe(tourSection);
    tourSection.addEventListener('pointerenter', stopTourAuto);
    tourSection.addEventListener('pointerleave', () => {
      if (!tourBusy) armTourAuto();
    });
  }

  const jump = (i) => {
    const idx = Number(i);
    if (!Number.isNaN(idx) && idx >= 0 && idx < HERO_N) {
      paintHero(idx);
      const map = [0, 1, 2, 3];
      renderTourScene(map[idx] ?? 0, { animate: false });
    }
    setActiveNav('tour');
    scrollToEl(document.getElementById('tour'));
  };
  heroJump = (i) => jump(i);
  scrollCue?.addEventListener('click', () => jump(heroI));
  document.querySelectorAll('[data-jump]').forEach((el) => {
    el.addEventListener('click', () => jump(el.getAttribute('data-jump')));
  });

  addEventListener('keydown', (e) => {
    if (['INPUT', 'TEXTAREA'].includes(e.target?.tagName)) return;
    const tourEl = document.getElementById('tour');
    const tourNear =
      tourEl &&
      tourEl.getBoundingClientRect().top < innerHeight * 0.55 &&
      tourEl.getBoundingClientRect().bottom > innerHeight * 0.2;
    if (tourNear && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
      e.preventDefault();
      renderTourScene(tourI + (e.key === 'ArrowRight' ? 1 : -1));
      return;
    }
    if (e.key === 'ArrowLeft') {
      paintHero(heroI - 1);
      resetHeroAuto();
    }
    if (e.key === 'ArrowRight') {
      paintHero(heroI + 1);
      resetHeroAuto();
    }
  });

  setTourCopy(0);
  syncTourSlides(0);

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
    document.querySelectorAll(".why-item").forEach((item) => {
      item.addEventListener("pointerenter", () => cursor?.classList.add("hot"));
      item.addEventListener("pointerleave", () => cursor?.classList.remove("hot"));
    });
  }

  /* ---------- Nav travel beam (CSS) + playful indicator ---------- */
  const navShell = document.getElementById("nav-shell");
  const navTravelCtl = (() => {
    const FADE_OUT = 580;
    const ALPHA_IN_END = 0.08;
    let phase = "idle";
    let journeyP = 0;
    let alpha = 0;
    let fadeT0 = 0;
    let fadeRaf = null;
    let onDone = null;

    const smooth = (t) => t * t * (3 - 2 * t);

    const syncProgress = () => {
      navShell?.style.setProperty("--travel-p", String(journeyP));
      navShell?.style.setProperty("--travel-alpha", String(alpha));
    };

    const fadeOut = (now) => {
      const t = Math.min(1, (now - fadeT0) / FADE_OUT);
      alpha = 1 - smooth(t);
      syncProgress();
      if (t < 1) {
        fadeRaf = requestAnimationFrame(fadeOut);
        return;
      }
      alpha = 0;
      phase = "idle";
      syncProgress();
      fadeRaf = null;
      onDone?.();
      onDone = null;
    };

    return {
      start({ dir = 1 } = {}) {
        if (fadeRaf) cancelAnimationFrame(fadeRaf);
        journeyP = 0;
        alpha = 0;
        phase = "active";
        const d = dir >= 0 ? "1" : "-1";
        nav?.setAttribute("data-travel-dir", d);
        navShell?.style.setProperty("--travel-dir", d);
        syncProgress();
      },
      setProgress(p) {
        journeyP = Math.max(0, Math.min(1, p));
        if (phase !== "active") return;
        alpha = journeyP < ALPHA_IN_END ? smooth(journeyP / ALPHA_IN_END) : 1;
        syncProgress();
      },
      end(cb) {
        if (phase === "idle") {
          cb?.();
          return;
        }
        journeyP = 1;
        syncProgress();
        onDone = cb || null;
        phase = "out";
        fadeT0 = performance.now();
        fadeRaf = requestAnimationFrame(fadeOut);
      },
    };
  })();

  const scrollDurationFor = (delta) =>
    Math.min(3200, Math.max(1600, Math.abs(delta) * 1.05));

  /* ---------- Premium nav + cinematic scroll ---------- */
  const nav = document.getElementById("nav");
  const navLinks = document.querySelector(".nav-links");
  const navIndicator = document.getElementById("nav-indicator");
  const navAnchors = [...document.querySelectorAll("[data-nav]")];
  const navSections = [
    { id: "why", el: document.getElementById("why") },
    { id: "tour", el: document.getElementById("tour") },
    { id: "start", el: document.getElementById("start") },
    { id: "blast", el: document.getElementById("blast") },
    { id: "faq", el: document.getElementById("faq") },
    { id: "notice", el: document.getElementById("notice") },
  ].filter((s) => s.el);

  const sectionLabels = {
    top: "首页",
    tour: "界面",
    why: "能力",
    start: "上手",
    blast: "联系",
    faq: "问答",
    notice: "注意",
  };

  let scrollAnim = null;
  let indicatorAnim = null;
  let indicatorX = 0;
  let indicatorW = 0;
  let scrollingNav = false;
  let travelTarget = null;
  let travelLink = null;
  let startRailAfterClick = null;
  let faqSpyHold = 0;

  const navLinkList = () => [...(navLinks?.querySelectorAll("a") || [])];

  const getLinkIndex = (link) => {
    if (!link) return -1;
    return navLinkList().indexOf(link);
  };

  const getLinkFromIndicator = () => {
    if (!navIndicator || !navLinks || indicatorW <= 0) return null;
    const cx = indicatorX + indicatorW / 2;
    let best = null;
    let bestD = Infinity;
    navLinkList().forEach((a) => {
      const acx = a.offsetLeft + a.offsetWidth / 2;
      const d = Math.abs(acx - cx);
      if (d < bestD) {
        bestD = d;
        best = a;
      }
    });
    return best;
  };

  const getTravelDirection = (sourceLink, destLink) => {
    const fromIdx = getLinkIndex(sourceLink);
    const toIdx = getLinkIndex(destLink);
    if (fromIdx < 0 || toIdx < 0) return 1;
    return toIdx >= fromIdx ? 1 : -1;
  };

  const easeInOutQuart = (t) =>
    t < 0.5 ? 8 * t * t * t * t : 1 - Math.pow(-2 * t + 2, 4) / 2;

  const easePlayful = (t) => {
    const c1 = 1.22;
    const c3 = c1 + 1;
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2;
  };

  const setScrollY = (y) => {
    const top = Math.max(0, Math.min(y, maxScrollY()));
    document.documentElement.scrollTop = top;
  };

  const readIndicator = () => {
    if (!navIndicator) return;
    const m = navIndicator.style.transform.match(/translateX\(([-\d.]+)px\)/);
    if (m) indicatorX = parseFloat(m[1]);
    const w = parseFloat(navIndicator.style.width);
    if (w) indicatorW = w;
  };

  const snapIndicator = (link) => {
    if (!navIndicator || !link) return;
    indicatorX = link.offsetLeft;
    indicatorW = link.offsetWidth;
    navIndicator.style.transform = `translateX(${indicatorX}px)`;
    navIndicator.style.width = `${indicatorW}px`;
    navIndicator.classList.add("is-ready");
  };

  const initNavIndicator = () => {
    if (!navLinks || !navIndicator) return;
    const link =
      navLinks.querySelector("a.is-active") ||
      navLinks.querySelector('a[href="#top"]') ||
      navLinks.querySelector('a[href="#tour"]');
    if (!link) return;
    navLinks.querySelectorAll("a").forEach((a) => a.classList.toggle("is-active", a === link));
    snapIndicator(link);
  };

  const isAtPageTop = () => scrollY < getNavOffset() * 0.55;

  const glideIndicator = (link, duration = 680) => {
    if (!navIndicator || !navLinks || !link) return;
    readIndicator();
    const startX = indicatorX;
    const startW = indicatorW || link.offsetWidth;
    const endX = link.offsetLeft;
    const endW = link.offsetWidth;
    if (Math.abs(startX - endX) < 0.5 && Math.abs(startW - endW) < 0.5) return;
    if (indicatorAnim) cancelAnimationFrame(indicatorAnim);
    navIndicator.classList.add("is-ready");
    const t0 = performance.now();
    const dur = Math.max(520, Math.min(duration, 1400));

    const apply = (x, w) => {
      navIndicator.style.transform = `translateX(${x}px)`;
      navIndicator.style.width = `${w}px`;
      indicatorX = x;
      indicatorW = w;
    };

    const step = (now) => {
      const t = Math.min(1, (now - t0) / dur);
      const e = easePlayful(t);
      apply(startX + (endX - startX) * e, startW + (endW - startW) * e);
      if (t < 1) indicatorAnim = requestAnimationFrame(step);
      else indicatorAnim = null;
    };
    indicatorAnim = requestAnimationFrame(step);
  };

  const moveIndicator = (link, duration = 560) => {
    if (!duration) snapIndicator(link);
    else glideIndicator(link, duration);
  };

  const getNavOffset = () => (nav?.offsetHeight ?? 80) + 24;
  const maxScrollY = () => document.documentElement.scrollHeight - innerHeight;

  const revealSection = (el) => {
    if (!el) return;
    if (el.matches("[data-in]")) el.classList.add("show");
    el.querySelectorAll("[data-in]").forEach((n) => n.classList.add("show"));
  };

  const getCurrentNavLink = () => {
    if (isAtPageTop()) return navLinks?.querySelector('a[href="#top"]') || null;
    const fromBar = getLinkFromIndicator();
    if (fromBar) return fromBar;
    const active = navLinks?.querySelector("a.is-active");
    if (active) return active;
    const mark = getNavOffset() + innerHeight * 0.28;
    let currentId = "";
    for (const { id, el } of navSections) {
      if (el.getBoundingClientRect().top <= mark) currentId = id;
    }
    if (scrollY >= maxScrollY() - 12) currentId = "notice";
    return currentId ? navLinks?.querySelector(`a[href="#${currentId}"]`) : null;
  };

  const setTravelUi = (easedProgress) => {
    navTravelCtl.setProgress(easedProgress);
  };

  const clearTravelUi = () => {
    nav?.removeAttribute("data-travel-dir");
    navShell?.style.removeProperty("--travel-p");
    navShell?.style.removeProperty("--travel-alpha");
    navShell?.style.removeProperty("--travel-dir");
  };

  const beginTravel = (label, targetEl, sourceLink, destLink) => {
    scrollingNav = true;
    travelTarget = targetEl || null;
    nav?.classList.add("is-traveling");
    navLinks?.querySelectorAll("a").forEach((a) => a.classList.remove("is-heading"));
    travelLink = destLink || (targetEl?.id ? navLinks?.querySelector(`a[href="#${targetEl.id}"]`) : null);
    travelLink?.classList.add("is-heading");
    const dir = getTravelDirection(sourceLink, destLink);
    navTravelCtl.start({ dir });
    setTravelUi(0);
  };

  const endTravel = () => {
    if (travelTarget) {
      revealSection(travelTarget);
      travelTarget.classList.add("is-arriving");
      setTimeout(() => travelTarget?.classList.remove("is-arriving"), 1000);
      travelTarget = null;
    }
    navTravelCtl.end(() => {
      scrollingNav = false;
      if (travelLink) {
        const id = travelLink.getAttribute("href")?.slice(1);
        if (id) setActiveNav(id);
        if (!indicatorAnim) snapIndicator(travelLink);
      }
      nav?.classList.remove("is-traveling");
      clearTravelUi();
      travelLink?.classList.remove("is-heading");
      travelLink = null;
      updateSpy();
    });
  };

  const scrollToY = (targetY, { label, targetEl, onDone, forceSmooth = false, sourceLink, destLink, duration } = {}) => {
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
    beginTravel(label, targetEl, sourceLink, destLink);
    const scrollDur = duration ?? scrollDurationFor(y - scrollY);
    const start = scrollY;
    const delta = y - start;
    const t0 = performance.now();

    const step = (now) => {
      const p = Math.min(1, (now - t0) / scrollDur);
      const eased = easeInOutQuart(p);
      setScrollY(start + delta * eased);
      setTravelUi(eased);
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
    const sourceLink = getCurrentNavLink();
    const delta = targetY - scrollY;
    const duration = scrollDurationFor(delta);
    if (link) glideIndicator(link, duration);
    scrollToY(targetY, {
      label,
      targetEl: el.id ? el : null,
      forceSmooth: true,
      sourceLink,
      destLink: link,
      duration,
      onDone: meta.onDone,
    });
  };

  const setActiveNav = (id) => {
    navAnchors.forEach((a) => {
      const on = a.getAttribute("href") === `#${id}`;
      a.classList.toggle("is-active", on);
      if (on) a.setAttribute("aria-current", "true");
      else a.removeAttribute("aria-current");
    });
    navBrand?.classList.toggle("is-at-home", id === "top");
    const link = navLinks?.querySelector(`a[href="#${id}"]`);
    if (link && !scrollingNav && !indicatorAnim) snapIndicator(link);
  };

  const updateSpy = () => {
    if (scrollingNav || indicatorAnim) return;
    if (performance.now() < faqSpyHold) return;
    if (isAtPageTop()) {
      setActiveNav("top");
      return;
    }
    const max = maxScrollY();
    if (scrollY >= max - 12) {
      setActiveNav("notice");
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
        if (!scrollingNav) moveIndicator(link, 480);
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

  /* start manual · TOC highlight (before hash nav — shares getNavOffset) */
  const startChapters = document.querySelectorAll(".start-chapter[id]");
  const startTocLinks = document.querySelectorAll(".start-rail-link[data-start-chapter]");
  let startRailLock = 0;
  if (startChapters.length && startTocLinks.length) {
    const setStartRailCurrent = (id) => {
      startTocLinks.forEach((a) => {
        a.classList.toggle("is-current", a.getAttribute("data-start-chapter") === id);
      });
    };
    const startRailLine = () => getNavOffset() + 20;
    const updateStartRailSpy = () => {
      const startSec = document.getElementById("start");
      if (!startSec) return;
      const box = startSec.getBoundingClientRect();
      if (box.bottom < startRailLine() || box.top > innerHeight * 0.92) return;
      if (performance.now() < startRailLock) return;
      const line = startRailLine();
      let id = startChapters[0].id;
      startChapters.forEach((ch) => {
        if (ch.getBoundingClientRect().top <= line) id = ch.id;
      });
      setStartRailCurrent(id);
    };
    startRailAfterClick = (id) => {
      if (id) setStartRailCurrent(id);
      startRailLock = performance.now() + 380;
    };
    updateStartRailSpy();
    addEventListener("scroll", updateStartRailSpy, { passive: true });
    addEventListener("resize", updateStartRailSpy, { passive: true });
  }

  document.querySelectorAll('a[href^="#"]').forEach((a) => {
    a.addEventListener("click", (e) => {
      const href = a.getAttribute("href");
      if (!href || href === "#") return;
      const el = document.querySelector(href);
      if (!el) return;
      e.preventDefault();

      /* 上手目录：页内锚点，不触发顶栏 travel 动画 */
      if (a.classList.contains("start-rail-link")) {
        if (scrollAnim) cancelAnimationFrame(scrollAnim);
        scrollAnim = null;
        scrollingNav = false;
        nav?.classList.remove("is-traveling");
        clearTravelUi();
        travelTarget = null;
        travelLink = null;
        const y = Math.max(
          0,
          Math.min(el.getBoundingClientRect().top + scrollY - getNavOffset(), maxScrollY())
        );
        setScrollY(y);
        const id = a.getAttribute("data-start-chapter");
        if (id) startRailAfterClick?.(id);
        return;
      }

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
  initNavIndicator();
  addEventListener("scroll", onScroll, { passive: true });
  addEventListener("resize", () => {
    const active = navLinks?.querySelector("a.is-active");
    if (active) snapIndicator(active);
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

  const faqItems = document.querySelectorAll(".faq-item");

  const applyFaqScroll = (meta) => {
    if (!meta) return;
    const root = document.documentElement;
    let top = meta.scroll;
    if (meta.pinBottom) {
      top += root.scrollHeight - meta.height;
    }
    const max = Math.max(0, root.scrollHeight - innerHeight);
    top = Math.max(0, Math.min(top, max));
    root.scrollTop = top;
    faqSpyHold = performance.now() + 180;
  };

  const setFaqItemOpen = (item, open) => {
    const btn = item.querySelector(".faq-trigger");
    const panel = item.querySelector(".faq-answer");
    item.classList.toggle("is-open", open);
    btn?.setAttribute("aria-expanded", open ? "true" : "false");
    if (panel) {
      if (open) panel.removeAttribute("hidden");
      else panel.setAttribute("hidden", "");
    }
  };

  faqItems.forEach((item) => {
    const btn = item.querySelector(".faq-trigger");
    btn?.addEventListener("click", () => {
      const root = document.documentElement;
      const meta = {
        scroll: scrollY,
        height: root.scrollHeight,
        pinBottom: scrollY + innerHeight >= root.scrollHeight - 48,
      };
      const willOpen = !item.classList.contains("is-open");
      faqItems.forEach((o) => setFaqItemOpen(o, false));
      if (willOpen) setFaqItemOpen(item, true);

      applyFaqScroll(meta);
      requestAnimationFrame(() => applyFaqScroll(meta));
      requestAnimationFrame(() => requestAnimationFrame(() => applyFaqScroll(meta)));
    });
  });

  matchMedia("(min-width: 900px)").addEventListener?.("change", (e) => {
    if (e.matches) setOpen(false);
  });

  const blastContact = document.getElementById("blast-contact");
  const metaEmail = document.querySelector('meta[name="binggo-contact-email"]')?.getAttribute("content")?.trim();
  if (blastContact && metaEmail) {
    const emailEl = blastContact.querySelector("small");
    if (emailEl) emailEl.textContent = metaEmail;
  }

  const blastRail = document.getElementById("blast-rail");
  if (blastRail) {
    const blastLinks = [...blastRail.querySelectorAll(".blast-rail-link")];
    const setBlastActive = (link) => {
      if (!link) return;
      blastLinks.forEach((el) => el.classList.toggle("is-active", el === link));
    };
    blastLinks.forEach((link) => {
      link.addEventListener("mouseenter", () => setBlastActive(link));
      link.addEventListener("focus", () => setBlastActive(link));
    });
    blastRail.addEventListener("mouseleave", () => setBlastActive(blastLinks[0]));
    if (blastLinks[0] && !blastLinks.some((el) => el.classList.contains("is-active"))) {
      blastLinks[0].classList.add("is-active");
    }
  }
})();
